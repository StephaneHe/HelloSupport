"""Local data behind the tools: simulated service states (JSON) and the incidents database (SQLite)."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from .retrieval import PROJECT_ROOT

DATA_DIR = PROJECT_ROOT / "data"
SCENARIOS_FILE = DATA_DIR / "scenarios.json"
INCIDENTS_DB = DATA_DIR / "incidents.db"
SERVICES = ("postgres", "nginx", "redis")

SCHEMA = """
CREATE TABLE incidents (
    id          INTEGER PRIMARY KEY,
    service     TEXT    NOT NULL CHECK (service IN ('postgres', 'nginx', 'redis')),
    started_at  TEXT    NOT NULL,  -- ISO 8601 local time, e.g. 2026-09-28T03:12:00
    severity    TEXT    NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    summary     TEXT    NOT NULL,
    resolved    INTEGER NOT NULL CHECK (resolved IN (0, 1)),
    resolved_at TEXT              -- NULL while unresolved
);
"""

# (days ago, hour, service, severity, summary, hours to resolve or None if unresolved)
SEED_INCIDENTS = [
    (2, 3, "postgres", "critical", "Service stopped after disk full on /var/lib/postgresql", None),
    (6, 14, "postgres", "high", "Connection pool exhausted: too many clients already", 2),
    (11, 9, "nginx", "high", "502 Bad Gateway: upstream app crashed after deploy", 1),
    (13, 22, "redis", "medium", "maxmemory reached, writes rejected (noeviction)", 3),
    (19, 8, "postgres", "medium", "pg_hba.conf rule missing for new app server", 5),
    (27, 16, "nginx", "low", "TLS certificate expiring in 7 days", 24),
    (33, 11, "redis", "high", "NOAUTH errors after password rotation", 1),
    (41, 2, "postgres", "high", "Failed minor upgrade left service stopped", 4),
    (48, 10, "nginx", "medium", "Config syntax error blocked reload", 1),
    (55, 19, "postgres", "low", "Slow connection setup due to DNS lookups", 48),
    (63, 7, "redis", "critical", "Redis killed by OOM killer", 2),
    (70, 15, "nginx", "high", "Port 443 already in use after package update", 1),
    (84, 4, "postgres", "critical", "Replica promoted, apps still pointing to old primary", 3),
    (90, 13, "redis", "low", "protected-mode refused remote connection", 2),
]


def active_scenario() -> str:
    """Scenario from HS_SCENARIO_FILE (switchable at runtime, used by the web demo), else HS_SCENARIO, else default."""
    data = json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))
    name = None
    scenario_file = os.getenv("HS_SCENARIO_FILE")
    if scenario_file and Path(scenario_file).exists():
        name = Path(scenario_file).read_text(encoding="utf-8").strip() or None
    name = name or os.getenv("HS_SCENARIO") or data["default"]
    if name not in data["scenarios"]:
        raise ValueError(f"unknown scenario {name!r}; known: {', '.join(data['scenarios'])}")
    return name


def service_status(service_name: str) -> dict:
    """Return the simulated status of a known service, or raise ValueError."""
    if service_name not in SERVICES:
        raise ValueError(f"unknown service {service_name!r}; known services: {', '.join(SERVICES)}")
    scenario = active_scenario()
    status = json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))["scenarios"][scenario][service_name]
    if status == "error":
        raise RuntimeError(f"status backend unavailable for {service_name!r} (simulated tool failure)")
    return {"service": service_name, "status": status, "simulated": True, "scenario": scenario}


def _seed_day(now: datetime) -> int:
    return int(now.strftime("%Y%m%d"))


def seed_incidents(db_path: Path = INCIDENTS_DB, now: datetime | None = None) -> Path:
    """(Re)create the incidents database with dates relative to `now`, so "last 30 days" stays meaningful.

    The seed day is stored in `PRAGMA user_version` (invisible to the model's queries).
    """
    now = (now or datetime.now()).replace(minute=0, second=0, microsecond=0)
    db_path.unlink(missing_ok=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {_seed_day(now)}")
        for i, (days, hour, service, severity, summary, ttr) in enumerate(SEED_INCIDENTS, start=1):
            started = (now - timedelta(days=days)).replace(hour=hour)
            resolved_at = (started + timedelta(hours=ttr)).isoformat() if ttr is not None else None
            conn.execute(
                "INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (i, service, started.isoformat(), severity, summary, int(ttr is not None), resolved_at),
            )
    return db_path


def seeded_on(db_path: Path) -> int:
    """Seed day of the database as YYYYMMDD (0 if unknown, e.g. a file created before v1.11.2)."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()  # `with` only commits: an open handle would block the reseed on Windows


def ensure_incidents_db(db_path: Path = INCIDENTS_DB, now: datetime | None = None) -> Path:
    """Return the database, reseeding it when it is missing or was seeded on another day.

    Without this, the dates would stay relative to the first run and "the last 30 days" would
    lose incidents as days pass (the C4 answer drops from 3 to 2 about 12 days after the seed).
    """
    now = now or datetime.now()
    try:
        if db_path.exists() and seeded_on(db_path) == _seed_day(now):
            return db_path
        return seed_incidents(db_path, now)
    except (OSError, sqlite3.Error):
        # Another process holds the file open (Windows): keep the existing data for this query.
        if db_path.exists():
            return db_path
        raise
