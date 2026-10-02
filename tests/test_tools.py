"""Contract tests of the MCP tools, through a real MCP client connected in-process."""

import asyncio
import json

import pytest
from mcp import Client

from hello_support.mcp_server import server


def call(tool: str, args: dict):
    async def run():
        async with Client(server) as c:
            return await c.call_tool(tool, args)

    r = asyncio.run(run())
    text = r.content[0].text if r.content else ""
    return r.is_error, text


def test_three_tools_with_typed_inputs():
    async def run():
        async with Client(server) as c:
            return {t.name: t.input_schema for t in (await c.list_tools()).tools}

    tools = asyncio.run(run())
    assert set(tools) == {"search_docs", "get_service_status", "query_incidents"}
    assert tools["get_service_status"]["properties"]["service_name"]["enum"] == ["postgres", "nginx", "redis"]


@pytest.mark.parametrize("scenario,expected", [("stopped", "stopped"), ("running", "running")])
def test_service_status_follows_scenario(monkeypatch, scenario, expected):
    monkeypatch.setenv("HS_SCENARIO", scenario)
    is_error, text = call("get_service_status", {"service_name": "postgres"})
    assert not is_error
    assert json.loads(text) == {"service": "postgres", "status": expected, "simulated": True, "scenario": scenario}


def test_unknown_service_is_an_explicit_error():
    is_error, text = call("get_service_status", {"service_name": "kafka"})
    assert is_error and "postgres" in text


def test_simulated_tool_failure(monkeypatch):
    monkeypatch.setenv("HS_SCENARIO", "tool_error")
    is_error, text = call("get_service_status", {"service_name": "redis"})
    assert is_error and "simulated tool failure" in text


def test_query_incidents_select_and_rejection():
    is_error, text = call("query_incidents", {"sql": "SELECT count(*) AS n FROM incidents"})
    assert not is_error and json.loads(text)["rows"] == [[14]]
    is_error, text = call("query_incidents", {"sql": "DELETE FROM incidents"})
    assert is_error and "SQL rejected" in text


def test_search_docs_rejects_empty_query():
    is_error, text = call("search_docs", {"query": "  "})
    assert is_error and "non-empty" in text
