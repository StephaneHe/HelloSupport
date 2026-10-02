import sqlite3
from datetime import datetime

import pytest

from hello_support.data_store import seed_incidents
from hello_support.sql_guard import MAX_ROWS, SQLRejected, check_sql, run_readonly_query


@pytest.fixture
def db(tmp_path):
    return seed_incidents(tmp_path / "incidents.db", now=datetime(2026, 10, 2, 12))


@pytest.mark.parametrize("sql", [
    "DELETE FROM incidents",
    "SELECT 1; DROP TABLE incidents",
    "UPDATE incidents SET resolved = 1",
    "PRAGMA table_info(incidents)",
    "ATTACH DATABASE 'x.db' AS x",
    "select * from incidents where summary = 'x' union select load_extension('evil')",
    "",
    "   ;  ",
])
def test_check_sql_rejects_non_select(sql):
    with pytest.raises(SQLRejected):
        check_sql(sql)


def test_check_sql_accepts_select_and_cte():
    assert check_sql("  SELECT count(*) FROM incidents ; ") == "SELECT count(*) FROM incidents"
    assert check_sql("with x as (select 1) select * from x").startswith("with")


def test_query_returns_rows_and_columns(db):
    r = run_readonly_query(db, "SELECT service, count(*) AS n FROM incidents GROUP BY service ORDER BY service")
    assert r["columns"] == ["service", "n"]
    assert r["rows"] == [["nginx", 4], ["postgres", 6], ["redis", 4]]
    assert not r["truncated"]


def test_query_is_limited(db):
    r = run_readonly_query(db, "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n LIMIT 500) SELECT i FROM n")
    assert r["row_count"] == MAX_ROWS and r["truncated"]


def test_engine_level_guards_block_what_the_regex_misses(db):
    # sqlite_master reads are allowed (READ), but writes are impossible even if the static check were bypassed.
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM incidents")
    conn.close()


def test_bad_sql_gives_actionable_error(db):
    with pytest.raises(SQLRejected, match="no such column"):
        run_readonly_query(db, "SELECT nope FROM incidents")


def test_last_30_days_question_has_a_stable_answer(db):
    # The seed is relative to "now": 3 postgres incidents in the last 30 days, the latest unresolved.
    sql = ("SELECT count(*) FROM incidents WHERE service = 'postgres' "
           "AND started_at >= datetime('2026-10-02T12:00:00', '-30 days')")
    assert run_readonly_query(db, sql)["rows"] == [[3]]
    latest = run_readonly_query(db, "SELECT resolved FROM incidents WHERE service='postgres' ORDER BY started_at DESC LIMIT 1")
    assert latest["rows"] == [[0]]
