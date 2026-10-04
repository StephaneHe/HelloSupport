"""Web demo: endpoints, SSE stream and guardrails, with a scripted LLM and the in-process MCP server."""

import asyncio
import json

from starlette.testclient import TestClient

from hello_support.config import Settings
from hello_support.llm import LLMResult, ToolCall
from hello_support.mcp_server import server
from hello_support.toolbox import ToolBox
from hello_support.webapp import Demo, create_app

from test_agents import ScriptedLLM

SETTINGS = Settings("http://127.0.0.1:9/v1", "slm-id", "large-id", "large", 5.0)


class FakeLLM(ScriptedLLM):
    def __init__(self, *results, models=("slm-id", "large-id"), offline=False):
        super().__init__(*results)
        self.models, self.offline = list(models), offline

    def list_models(self):
        if self.offline:
            raise ConnectionError("connection refused")
        return self.models


def client_for(llm, **kw):
    demo = Demo(settings=SETTINGS, llm=llm, toolbox_factory=lambda: ToolBox(server=server), **kw)
    return TestClient(create_app(demo)), demo


def sse_events(client, **params):
    events = []
    with client.stream("GET", "/api/ask", params=params) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        kind = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                events.append((kind, json.loads(line[6:])))
    return events


def test_page_static_files_and_config():
    c, _ = client_for(FakeLLM())
    with c:
        page = c.get("/")
        assert page.status_code == 200 and "HelloSupport" in page.text and "/static/app.js" in page.text
        assert c.get("/static/app.js").status_code == 200 and c.get("/static/style.css").status_code == 200
        cfg = c.get("/api/config").json()
        assert [x["id"] for x in cfg["cases"]] == ["C1", "C2", "C3", "C4", "C5", "C6"]
        assert {m["alias"] for m in cfg["models"]} == {"slm", "large"}
        assert {s["id"] for s in cfg["scenarios"]} == {"stopped", "running", "tool_error"}


def test_health_reports_lmstudio_and_tools():
    c, _ = client_for(FakeLLM())
    with c:
        h = c.get("/api/health").json()
        assert h["llm"]["reachable"] and h["tools"] == "ready" and not h["busy"]
        assert h["models"] == {"slm": "slm-id", "large": "large-id"}


def test_history_question_streams_trace_sql_rows_and_sources():
    sql = "SELECT count(*) AS n FROM incidents WHERE service = 'postgres'"
    llm = FakeLLM(
        LLMResult("large-id", '{"intent": "history", "service": "postgres"}'),
        LLMResult("large-id", None, [ToolCall("a", "query_incidents", {"sql": sql}, "")]),
        LLMResult("large-id", "6 incidents. Source : incidents database"),
    )
    c, _ = client_for(llm)
    with c:
        ev = sse_events(c, question="Combien d'incidents postgres ?", model="large", scenario="stopped")
    kinds = [k for k, _ in ev]
    assert kinds[0] == "accepted" and kinds[-1] == "done" and "result" in kinds and "error" not in kinds
    trace = [d for k, d in ev if k == "trace"]
    assert any(d["type"] == "llm" and d.get("route", {}).get("intent") == "history" for d in trace)
    assert any(d["type"] == "tool_call" and d["arguments"]["sql"] == sql for d in trace)
    rows = next(d for d in trace if d["type"] == "tool_result")["result"]["rows"]
    assert rows == [[6]]
    result = next(d for k, d in ev if k == "result")
    assert result["path"] == ["triage", "technician", "post-processing"]  # documentalist skipped
    assert "incidents database (SQL)" in result["sources"]
    assert result["metrics"]["llm_calls"] == 3


def test_scenario_is_switched_per_question_on_the_warm_tool_server():
    def script():
        return FakeLLM(
            LLMResult("large-id", '{"intent": "malfunction", "service": "postgres"}'),
            LLMResult("large-id", "EVIDENCE: none"),  # documentalist answers without searching
            LLMResult("large-id", None, [ToolCall("s", "get_service_status", {"service_name": "postgres"}, "")]),
            LLMResult("large-id", "Observation : voir le statut. Sources : postgres_connection.md#Service status"),
        )

    llm = script()
    c, demo = client_for(llm)
    with c:
        statuses = []
        for scenario in ("running", "stopped"):
            demo.llm = script()
            ev = sse_events(c, question="Postgres ne répond plus", model="large", scenario=scenario)
            result = next(d for k, d in ev if k == "result")
            statuses.append(result["observations"][0]["result"]["status"])
            assert result["sources"] == ["postgres_connection.md#Service status"]
            assert result["path"] == ["triage", "documentalist", "technician", "post-processing"]
    assert statuses == ["running", "stopped"]


def test_clear_errors_when_lmstudio_is_offline_or_model_missing():
    c, _ = client_for(FakeLLM(offline=True))
    with c:
        assert not c.get("/api/health").json()["llm"]["reachable"]
        ev = sse_events(c, question="hello", model="slm", scenario="stopped")
        err = next(d for k, d in ev if k == "error")
        assert "LM Studio is not reachable" in err["message"]
    c, _ = client_for(FakeLLM(models=["large-id"]))
    with c:
        ev = sse_events(c, question="hello", model="slm", scenario="stopped")
        assert "not available in LM Studio" in next(d for k, d in ev if k == "error")["message"]


def test_bad_parameters_are_rejected():
    c, _ = client_for(FakeLLM())
    with c:
        assert c.get("/api/ask", params={"question": "", "model": "large"}).status_code == 400
        assert c.get("/api/ask", params={"question": "x" * 501}).status_code == 400
        assert c.get("/api/ask", params={"question": "hi", "model": "gpt-9"}).status_code == 400
        assert c.get("/api/ask", params={"question": "hi", "scenario": "rm -rf"}).status_code == 400


def test_one_question_at_a_time_with_a_queue():
    async def go():
        demo = Demo(settings=SETTINGS, llm=FakeLLM(), toolbox_factory=lambda: ToolBox(server=server),
                    queue_timeout_s=0.2)
        events = []
        await demo.lock.acquire()  # another question is running
        await demo.ask("hello", "large", "stopped", lambda k, d: events.append((k, d)))
        demo.lock.release()
        return events

    events = asyncio.run(go())
    assert events[0] == ("queued", {"position": 1})
    assert events[1][0] == "error" and "busy" in events[1][1]["message"]
