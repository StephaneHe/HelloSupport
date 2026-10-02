"""Whole LangGraph workflow with a scripted LLM and the in-process MCP server (offline, deterministic)."""

import asyncio

from hello_support.config import Settings
from hello_support.llm import LLMResult, ToolCall
from hello_support.mcp_server import server
from hello_support.toolbox import ToolBox
from hello_support.workflow import run_request

from test_agents import ScriptedLLM

SETTINGS = Settings("http://x/v1", "slm", "large", "large", 5.0)
COUNT_SQL = "SELECT count(*) FROM incidents WHERE service = 'postgres'"
LAST_SQL = "SELECT resolved FROM incidents WHERE service = 'postgres' ORDER BY started_at DESC LIMIT 1"


def run(llm, question):
    async def go():
        async with ToolBox(server=server) as tb:
            return await run_request(question, llm=llm, toolbox=tb, settings=SETTINGS, save=False)

    return asyncio.run(go())


def test_history_question_goes_straight_to_the_technician_with_sql():
    llm = ScriptedLLM(
        LLMResult("m", '{"intent": "history", "service": "postgres"}'),  # triage
        LLMResult("m", None, [ToolCall("a", "query_incidents", {"sql": COUNT_SQL}, ""),
                              ToolCall("b", "query_incidents", {"sql": LAST_SQL}, "")]),
        LLMResult("m", "6 incidents postgres ; le dernier n'est pas résolu. Source : incidents database"),
    )
    state = run(llm, "Combien d'incidents postgres, et le dernier est-il résolu ?")
    assert state["route"] == {"intent": "history", "service": "postgres"}
    assert "documentalist" not in state["counters"]  # conditional edge skipped the knowledge base
    assert [o["result"]["rows"] for o in state["observations"]] == [[[6]], [[0]]]
    assert llm.calls[1]["tools"] == ["query_incidents"] and llm.calls[1]["tool_choice"] == "required"
    assert state["status"] == "done" and state["answer"].endswith("Aucune action corrective n'a été exécutée.")
    agents = [e["agent"] for e in state["trace"]]
    assert agents[0] == "triage" and "technician" in agents
    assert state["metrics"]["llm_calls"] == 3


def test_required_tool_is_enforced_when_the_model_answers_without_it():
    llm = ScriptedLLM(
        LLMResult("m", '{"intent": "history", "service": "postgres"}'),
        LLMResult("m", "There were probably 2 incidents."),  # no tool call: must be discarded
        LLMResult("m", None, [ToolCall("a", "query_incidents", {"sql": COUNT_SQL}, "")]),
        LLMResult("m", "6 incidents."),
    )
    state = run(llm, "How many postgres incidents?")
    assert state["answer"].startswith("6 incidents.")
    assert any("answer discarded" in e.get("detail", "") for e in state["trace"])
