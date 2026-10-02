"""Host side of MCP: launch the tool server as a subprocess, list its tools, call them with timing."""

import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import Client, StdioServerParameters

TOOL_TIMEOUT_S = 240.0  # search_docs may wait for the retriever to finish loading (~30 s, up to 180 s)


@dataclass
class ToolOutcome:
    ok: bool
    payload: Any  # parsed JSON when possible, else the raw text (error message on failure)
    duration_s: float


class ToolBox:
    """Async context manager exposing the MCP tools in OpenAI `tools` format and executing calls."""

    def __init__(self, scenario: str | None = None, server: Any | None = None):
        # `server` lets tests connect an in-process MCPServer instead of a subprocess.
        env = {**os.environ, **({"HS_SCENARIO": scenario} if scenario else {})}
        self._target = server or StdioServerParameters(
            command=sys.executable, args=["-m", "hello_support.mcp_server"], env=env
        )
        self._stack = AsyncExitStack()
        self.client: Client | None = None
        self.schemas: dict[str, dict] = {}

    async def __aenter__(self) -> "ToolBox":
        self.client = await self._stack.enter_async_context(Client(self._target))
        for tool in (await self.client.list_tools()).tools:
            self.schemas[tool.name] = {
                "type": "function",
                "function": {"name": tool.name, "description": tool.description or "",
                             "parameters": tool.input_schema},
            }
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    def openai_tools(self, names: list[str]) -> list[dict]:
        return [self.schemas[n] for n in names if n in self.schemas]

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        start = time.perf_counter()
        try:
            r = await asyncio.wait_for(self.client.call_tool(name, arguments), TOOL_TIMEOUT_S)
        except TimeoutError:
            return ToolOutcome(False, f"tool {name!r} timed out after {TOOL_TIMEOUT_S:.0f}s",
                               time.perf_counter() - start)
        return ToolOutcome(not r.is_error, _payload(r), time.perf_counter() - start)


def _payload(r) -> Any:
    """Decode a CallToolResult: structured content first (list returns are wrapped in {"result": [...]}),
    else one JSON value per text block (a list return yields one block per item)."""
    if not r.is_error and isinstance(r.structured_content, dict) and set(r.structured_content) == {"result"}:
        return r.structured_content["result"]
    texts = [c.text for c in r.content if getattr(c, "text", None)]
    try:
        values = [json.loads(t) for t in texts]
    except json.JSONDecodeError:
        return "\n".join(texts)
    return values[0] if len(values) == 1 else values
