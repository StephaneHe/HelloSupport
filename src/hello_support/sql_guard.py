"""Read-only SQL execution for the data agent (text-to-SQL), with defence in depth.

1. Static check: a single SELECT (or WITH ... SELECT) statement, no write/DDL keyword.
2. The query is wrapped so that at most MAX_ROWS rows are returned.
3. The database is opened read-only (`mode=ro`), so the engine itself refuses writes.
4. An SQLite authorizer allows only read operations (blocks ATTACH, PRAGMA, writes...).
5. A progress handler aborts queries that run too long.
"""

import re
import sqlite3
import time
from pathlib import Path

MAX_ROWS = 50
TIMEOUT_S = 2.0

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|replace|drop|alter|create|attach|detach|pragma|vacuum|reindex|analyze|"
    r"begin|commit|rollback|savepoint|release|load_extension)\b",
    re.IGNORECASE,
)
ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


class SQLRejected(ValueError):
    """The query was refused before (or while) running; the message is safe to show to the model."""


def check_sql(sql: str) -> str:
    """Return the normalized query, or raise SQLRejected with a reason the model can act on."""
    q = (sql or "").strip().rstrip(";").strip()
    if not q:
        raise SQLRejected("empty query")
    if ";" in q:
        raise SQLRejected("only one statement is allowed (found ';')")
    if not re.match(r"^(select|with)\b", q, re.IGNORECASE):
        raise SQLRejected("only SELECT queries are allowed")
    if m := FORBIDDEN.search(q):
        raise SQLRejected(f"keyword {m.group(1).upper()!r} is not allowed (read-only access)")
    return q


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def run_readonly_query(db_path: Path, sql: str) -> dict:
    """Execute a checked SELECT on a read-only connection; return columns, rows and truncation flag."""
    q = check_sql(sql)
    wrapped = f"SELECT * FROM ({q}) LIMIT {MAX_ROWS + 1}"
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        conn.set_authorizer(_authorizer)
        deadline = time.monotonic() + TIMEOUT_S
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            cur = conn.execute(wrapped)
            rows = cur.fetchall()
        except sqlite3.DatabaseError as e:
            # Syntax errors, unknown columns, authorizer denials, timeouts: give the reason back.
            raise SQLRejected(f"query failed: {e}") from e
        columns = [d[0] for d in cur.description]
    finally:
        conn.close()
    return {
        "columns": columns,
        "rows": [list(r) for r in rows[:MAX_ROWS]],
        "row_count": min(len(rows), MAX_ROWS),
        "truncated": len(rows) > MAX_ROWS,
    }
