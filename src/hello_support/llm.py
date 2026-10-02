"""Thin wrapper around an OpenAI-compatible chat endpoint (LM Studio by default).

Returns a normalized result with the content, the tool calls proposed by the model,
token usage and wall-clock latency, so every call can be traced and measured.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None  # None when the model produced invalid JSON
    raw_arguments: str


@dataclass
class LLMResult:
    model: str
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    finish_reason: str | None = None


class LLMClient:
    def __init__(self, settings: Settings, client: Any | None = None):
        self.settings = settings
        # api_key is required by the SDK but ignored by LM Studio.
        self._client = client or OpenAI(
            base_url=settings.llm_base_url, api_key="lm-studio", timeout=settings.llm_timeout_s
        )

    def list_models(self) -> list[str]:
        return [m.id for m in self._client.models.list().data]

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResult:
        kwargs: dict[str, Any] = {"model": model, "messages": messages,
                                  "temperature": temperature, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice  # "auto" | "required" | "none"
        if response_format:
            kwargs["response_format"] = response_format
        start = time.perf_counter()
        resp = self._client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - start

        choice = resp.choices[0]
        calls = []
        for tc in choice.message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None
            calls.append(ToolCall(tc.id, tc.function.name, args, tc.function.arguments or ""))
        usage = resp.usage
        return LLMResult(
            model=resp.model or model,
            content=choice.message.content,
            tool_calls=calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_s=latency,
            finish_reason=choice.finish_reason,
        )
