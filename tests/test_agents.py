"""Agent loop and workflow tests with a scripted fake LLM and the in-process MCP server (no GPU, no LM Studio)."""

import asyncio
import json

from hello_support.agents import run_agent, triage
from hello_support.config import Settings
from hello_support.llm import LLMResult, ToolCall
from hello_support.mcp_server import server
from hello_support.toolbox import ToolBox

SETTINGS = Settings("http://x/v1", "slm", "large", "large", 5.0)


class ScriptedLLM:
    """Returns the scripted LLMResults in order and records what it was given."""

    def __init__(self, *results: LLMResult):
        self.results = list(results)
        self.calls: list[dict] = []

    def chat(self, model, messages, tools=None, temperature=0.0, max_tokens=1024, tool_choice=None,
             response_format=None):
        self.calls.append({"tools": [t["function"]["name"] for t in tools or []], "tool_choice": tool_choice,
                           "messages": messages})
        return self.results.pop(0)


def call(name, **args):
    return ToolCall(f"id-{name}-{len(args)}", name, args, json.dumps(args))


def run(llm, limits, require=False):
    events = []

    async def go():
        async with ToolBox(server=server) as tb:
            return await run_agent("technician", "sys", "user", limits, llm, "m", tb, events.append,
                                   require_tool_first=require)

    return asyncio.run(go()), events


def test_tool_result_is_fed_back_and_answer_returned(monkeypatch):
    monkeypatch.setenv("HS_SCENARIO", "stopped")
    llm = ScriptedLLM(LLMResult("m", None, [call("get_service_status", service_name="postgres")]),
                      LLMResult("m", "PostgreSQL is stopped (simulated)."))
    r, _ = run(llm, {"get_service_status": 1}, require=True)
    assert r.answer == "PostgreSQL is stopped (simulated)."
    assert r.tool_results[0]["result"]["status"] == "stopped"
    assert llm.calls[0]["tool_choice"] == "required" and llm.calls[1]["tool_choice"] is None
    assert '"stopped"' in llm.calls[1]["messages"][-1]["content"]


def test_budget_and_duplicates_are_enforced(monkeypatch):
    monkeypatch.setenv("HS_SCENARIO", "running")
    dup = [call("get_service_status", service_name="redis")] * 5 + [call("get_service_status", service_name="nginx")]
    llm = ScriptedLLM(LLMResult("m", None, dup), LLMResult("m", "done"))
    r, events = run(llm, {"get_service_status": 1})
    assert r.tool_calls == {"get_service_status": 1}  # nginx call refused: budget of 1
    assert any("dropped" in e.get("detail", "") for e in events)
    assert any("limit reached" in e.get("detail", "") for e in events)


def test_last_llm_call_has_no_tools_so_the_loop_always_ends():
    always_tool = [LLMResult("m", None, [call("query_incidents", sql=f"SELECT {i}")]) for i in range(2)]
    llm = ScriptedLLM(*always_tool, LLMResult("m", "final"))
    r, events = run(llm, {"query_incidents": 5})
    assert r.answer == "final" and r.llm_calls == 3
    assert llm.calls[2]["tools"] == []
    assert any(e["type"] == "limit" for e in events)


def test_tool_error_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("HS_SCENARIO", "tool_error")
    llm = ScriptedLLM(LLMResult("m", None, [call("get_service_status", service_name="redis")]),
                      LLMResult("m", "could not check"))
    r, _ = run(llm, {"get_service_status": 1})
    assert r.answer == "could not check" and "simulated tool failure" in r.errors[0]


def test_triage_falls_back_and_normalizes():
    llm = ScriptedLLM(LLMResult("m", '{"intent": "malfunction", "service": null}'))
    route = asyncio.run(triage("it does not work", llm, "m", lambda e: None))
    assert route["intent"] == "vague"  # a malfunction without a known service needs a clarification
    llm = ScriptedLLM(LLMResult("m", "not json"))
    assert asyncio.run(triage("x", llm, "m", lambda e: None))["intent"] == "documentation"
