"""Guardrails that had no test before the documentation-to-code review (docs/REVIEW_DOC_CODE.md).

F-4: per-step call cap, invalid JSON arguments, tool not offered, max_tokens caps, tool timeout,
SQLite authorizer, SQL timeout. F-1: the incidents database is re-anchored on the current day.
I-1: a required tool that is never called is traced. U-6: the web path only shows post-processing
when it ran.
"""

import asyncio
import sqlite3
from datetime import datetime

import pytest

import hello_support.sql_guard as sql_guard
import hello_support.toolbox as toolbox_mod
from hello_support.agents import ANSWER_MAX_TOKENS, MAX_CALLS_PER_STEP, TOOL_STEP_MAX_TOKENS
from hello_support.data_store import ensure_incidents_db, seed_incidents, seeded_on
from hello_support.llm import LLMResult, ToolCall
from hello_support.sql_guard import SQLRejected, run_readonly_query
from hello_support.toolbox import ToolBox
from hello_support.webapp import summarize

from test_agents import ScriptedLLM, call, run

DAY = datetime(2026, 10, 2, 12)


@pytest.fixture
def db(tmp_path):
    return seed_incidents(tmp_path / "incidents.db", now=DAY)


# ---------------------------------------------------------------- agent loop (F-4)
def test_at_most_three_tool_calls_per_step():
    many = [call("query_incidents", sql=f"SELECT {i}") for i in range(5)]
    llm = ScriptedLLM(LLMResult("m", None, many), LLMResult("m", "done"))
    r, events = run(llm, {"query_incidents": 10})
    assert r.tool_calls == {"query_incidents": MAX_CALLS_PER_STEP} == {"query_incidents": 3}
    assert any("2 duplicate/extra tool call(s) dropped" in e.get("detail", "") for e in events)


def test_invalid_json_arguments_are_refused_and_reported_to_the_model():
    bad = ToolCall("x", "query_incidents", None, "{not json")
    llm = ScriptedLLM(LLMResult("m", None, [bad]), LLMResult("m", "done"))
    r, _ = run(llm, {"query_incidents": 2})
    assert r.tool_calls == {"query_incidents": 0} and not r.tool_results
    assert "not valid JSON" in llm.calls[1]["messages"][-1]["content"]


def test_a_tool_that_was_not_offered_is_not_executed():
    llm = ScriptedLLM(LLMResult("m", None, [call("query_incidents", sql="SELECT 1")]), LLMResult("m", "done"))
    r, _ = run(llm, {"get_service_status": 1})
    assert not r.tool_results
    assert "not available to you" in llm.calls[1]["messages"][-1]["content"]


def test_max_tokens_caps_tool_steps_and_answers():
    llm = ScriptedLLM(LLMResult("m", None, [call("query_incidents", sql="SELECT 1")]),
                      LLMResult("m", None, [call("query_incidents", sql="SELECT 2")]),
                      LLMResult("m", "final"))
    run(llm, {"query_incidents": 5})
    assert [c["max_tokens"] for c in llm.calls] == [TOOL_STEP_MAX_TOKENS] * 2 + [ANSWER_MAX_TOKENS]
    assert (TOOL_STEP_MAX_TOKENS, ANSWER_MAX_TOKENS) == (300, 700)


def test_required_tool_never_called_is_traced(monkeypatch):
    # I-1: after one retry, a second text answer is accepted but marked as unobserved.
    llm = ScriptedLLM(LLMResult("m", "Postgres is stopped."), LLMResult("m", "Postgres is stopped, really."))
    r, events = run(llm, {"get_service_status": 1}, require=True)
    assert r.answer == "Postgres is stopped, really." and not r.tool_results
    assert any("never made" in e for e in r.errors)
    assert [e["detail"] for e in events if e["type"] == "limit"][-1].endswith("answer accepted without observation")


def test_tool_timeout_becomes_a_tool_error(monkeypatch):
    class SlowClient:
        async def call_tool(self, name, arguments):
            await asyncio.sleep(5)

    monkeypatch.setattr(toolbox_mod, "TOOL_TIMEOUT_S", 0.05)
    tb = ToolBox(server=object())
    tb.client = SlowClient()
    out = asyncio.run(tb.call("search_docs", {"query": "x"}))
    assert not out.ok and "timed out" in out.payload


# ---------------------------------------------------------------- SQL engine guards (F-4, U-5)
def test_authorizer_blocks_what_the_static_check_lets_through(db):
    sql = "SELECT * FROM pragma_table_info('incidents')"  # no PRAGMA keyword: passes the regex
    assert sql_guard.check_sql(sql) == sql
    with pytest.raises(SQLRejected, match="not authorized"):
        run_readonly_query(db, sql)


def test_long_queries_are_interrupted(db, monkeypatch):
    monkeypatch.setattr(sql_guard, "TIMEOUT_S", 0.0)
    slow = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n LIMIT 5000000) SELECT count(*) FROM n"
    with pytest.raises(SQLRejected, match="interrupted"):
        run_readonly_query(db, slow)


def test_semicolon_inside_a_string_literal_is_rejected():
    # Known false positive of the static check (documented in D-13).
    with pytest.raises(SQLRejected, match="one statement"):
        sql_guard.check_sql("SELECT * FROM incidents WHERE summary = 'a;b'")


# ---------------------------------------------------------------- incidents database dates (F-1)
def test_database_is_reseeded_when_the_day_changes(db):
    assert seeded_on(db) == 20261002
    assert ensure_incidents_db(db, now=DAY.replace(hour=23)) == db and seeded_on(db) == 20261002
    later = datetime(2026, 10, 20, 9)  # 18 days later: the old seed would only show 2 recent postgres incidents
    ensure_incidents_db(db, now=later)
    assert seeded_on(db) == 20261020
    sql = ("SELECT count(*) FROM incidents WHERE service = 'postgres' "
           "AND started_at >= datetime('2026-10-20T09:00:00', '-30 days')")
    assert run_readonly_query(db, sql)["rows"] == [[3]]


def test_database_without_a_seed_day_is_reseeded(tmp_path):
    old = tmp_path / "incidents.db"
    sqlite3.connect(old).close()  # file from an older version: user_version 0
    ensure_incidents_db(old, now=DAY)
    assert seeded_on(old) == 20261002
    assert run_readonly_query(old, "SELECT count(*) FROM incidents")["rows"] == [[14]]


# ---------------------------------------------------------------- web path (U-6)
def _result(status, agents):
    return {"status": status, "trace": [{"agent": a, "type": "start"} for a in agents], "answer": "x"}


def test_web_path_lists_post_processing_only_when_it_ran():
    assert summarize(_result("done", ["technician"]), 1)["path"] == ["triage", "technician", "post-processing"]
    assert summarize(_result("failed", ["documentalist"]), 1)["path"] == ["triage", "documentalist"]
    assert summarize(_result("failed", ["documentalist", "technician"]), 1)["path"] == [
        "triage", "documentalist", "technician"]
