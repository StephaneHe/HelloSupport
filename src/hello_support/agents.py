"""Triage + the two agents: shared bounded tool loop and role prompts.

- Triage: one short LLM call with a JSON schema (structured output) classifies the request.
- Documentalist and technician share one loop: the model proposes tool calls, the host checks
  budgets and arguments, executes the call through MCP and feeds the result back. The last
  allowed LLM call is made WITHOUT tools, so every agent ends with a text answer.
- The tool policy per intent (which tools are offered, whether a call is required) is decided
  by code from the triage result: small models proved unreliable at deciding on their own to
  observe before answering (docs/DESIGN_DECISIONS.md, D-17).
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .llm import LLMClient
from .toolbox import ToolBox

MAX_LLM_CALLS = 3
MAX_CALLS_PER_STEP = 3
TOOL_STEP_MAX_TOKENS = 300
ANSWER_MAX_TOKENS = 700
SERVICES = ["postgres", "nginx", "redis"]
INTENTS = ["malfunction", "history", "documentation", "out_of_scope", "vague"]

TRIAGE_PROMPT = """Classify the user's troubleshooting request. Known services: postgres, nginx, redis.
intent:
- "malfunction": the user reports that a known service does not work right now (cannot connect,
  down, errors, 502...). This holds EVEN IF the user also asks what to check.
- "history": the user asks about past incidents (how many, when, last one, resolved...)
- "documentation": the user only asks what to check / how something works, without reporting a
  current failure
- "out_of_scope": the request is about another product or topic than the known services
- "vague": impossible to tell which service is concerned
service: the known service concerned, or null.
Rules:
- If the request names another product (Kafka, MongoDB, Elasticsearch...), intent is "out_of_scope"
  and service is null: never map another product to postgres, nginx or redis.
- A failure the user is experiencing NOW ("cannot connect", "ne répond plus", "refuse", "502")
  is "malfunction", even when the sentence ends with "what should I check?".
Examples (wording differs from real requests):
- "Our nginx returns 502 since this morning, what should I look at?" -> malfunction, nginx
- "Je n'arrive plus à joindre mon cache Redis, que faut-il vérifier ?" -> malfunction, redis
- "What are the usual checks when PostgreSQL refuses connections?" -> documentation, postgres
- "How many redis incidents last week?" -> history, redis
- "Our Elasticsearch cluster is red" -> out_of_scope, null
- "Rien ne fonctionne depuis ce matin" -> vague, null"""

TRIAGE_SCHEMA = {"type": "json_schema", "json_schema": {"name": "triage", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["intent", "service"],
    "properties": {"intent": {"type": "string", "enum": INTENTS},
                   "service": {"type": ["string", "null"], "enum": [*SERVICES, None]}}}}}

DOCUMENTALIST_PROMPT = """You are the DOCUMENTALIST of a troubleshooting assistant.
Your only job is to find the relevant passages in the troubleshooting knowledge base with the
search_docs tool. The knowledge base only covers: PostgreSQL connection problems, nginx
unavailable, Redis unreachable.
- Call search_docs with a short, precise query (you may rephrase the user question in English).
- If no returned passage has relevant=true, you may rephrase and search ONE more time.
- Then reply with a short brief, without tool calls, in this format:
  EVIDENCE: <doc_id#section> - <one line on why it is useful> (one line per useful passage, or "none")
  MISSING: <what the documents do not cover, or "nothing">
Never invent a document or a section. Passages with relevant=false are NOT evidence."""

TECHNICIAN_PROMPT = """You are the TECHNICIAN of a troubleshooting assistant. You receive the user
question, a triage of the request, the documentalist's evidence, and possibly tools:
- get_service_status(service_name): SIMULATED status of postgres, nginx or redis.
- query_incidents(sql): ONE read-only SQLite SELECT on the incidents history.
Rules:
- Write the whole answer in the language given on the "Answer language" line (the language of the
  user question), whatever the language of the evidence.
- Be brief. Separate what was OBSERVED (tool results) from what is a HYPOTHESIS (documentation).
- Say that service statuses are simulated. Never claim you fixed, restarted or changed anything.
- Cite sources by copying the [doc_id#section] labels of the evidence EXACTLY (keep spaces, no
  underscores, no scores). Use only the evidence you were given and tool results.
- Never invent a sheet, a figure or an observation.
- If a tool returned an error, say that the check could not be done and why (tool failure).
- Every figure you give must come from a tool result; check that it really answers the question.
Format when you have a diagnosis:
Observation: ...
Possible explanation: ...
Suggested check: ...
Sources: ..."""

# What the technician is told, which tools it gets, and whether its first call must use a tool.
TECHNICIAN_POLICY: dict[str, dict[str, Any]] = {
    "malfunction": {"tools": {"get_service_status": 1}, "require_tool": True,
                    "instruction": "Check the current status of {service} with get_service_status first, "
                                   "then give the diagnosis. State that the observed status is simulated."},
    "history": {"tools": {"query_incidents": 2}, "require_tool": True,
                "instruction": "Answer from the incidents database with query_incidents. Issue ALL the queries "
                               "you need IN THE SAME STEP, one query per part of the question: e.g. a COUNT(*) for "
                               "'how many', and for 'the last one' a query with ORDER BY started_at DESC LIMIT 1 "
                               "returning its resolved value. Then answer only with what the returned rows show "
                               "(resolved=1 resolved, 0 unresolved). Never describe a query you did not run. "
                               "Give the source as 'incidents database'."},
    "documentation": {"tools": {}, "require_tool": False,
                      "instruction": "Answer from the evidence only; no tool is needed. Nothing was observed: do "
                                     "NOT write an Observation line, just list the checks with their sources."},
    "out_of_scope": {"tools": {}, "require_tool": False,
                     "instruction": "The request is outside the knowledge base and tools: say so plainly in one or "
                                    "two sentences, list what you can help with (postgres, nginx, redis), invent nothing."},
    "vague": {"tools": {}, "require_tool": False,
              "instruction": "The request is too vague: ask ONE short clarifying question (which service, which "
                             "symptom) and stop."},
}


@dataclass
class AgentRun:
    answer: str
    tool_results: list[dict] = field(default_factory=list)  # {tool, arguments, ok, result, duration_s}
    llm_calls: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


async def triage(question: str, llm: LLMClient, model: str, emit: Callable[[dict], None]) -> dict:
    """Classify the request with structured output; a malfunction without a known service is 'vague'."""
    try:
        res = await asyncio.to_thread(
            llm.chat, model, [{"role": "system", "content": TRIAGE_PROMPT}, {"role": "user", "content": question}],
            None, 0.0, 60, None, TRIAGE_SCHEMA)
        route = json.loads(res.content or "{}")
        assert route.get("intent") in INTENTS and route.get("service") in [*SERVICES, None]
    except Exception as e:
        emit({"agent": "triage", "type": "error", "detail": f"triage failed ({e}); falling back to 'documentation'"})
        return {"intent": "documentation", "service": None, "llm_calls": 0}
    if route["intent"] == "malfunction" and route["service"] is None:
        route["intent"] = "vague"
    emit({"agent": "triage", "type": "llm", "model": res.model, "latency_s": round(res.latency_s, 3),
          "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
          "tools_offered": [], "tool_calls": [], "route": route})
    return {**route, "llm_calls": 1}


async def run_agent(
    name: str,
    system_prompt: str,
    user_content: str,
    tool_limits: dict[str, int],
    llm: LLMClient,
    model: str,
    toolbox: ToolBox,
    emit: Callable[[dict], None],
    require_tool_first: bool = False,
) -> AgentRun:
    """Generic bounded tool loop shared by both agents."""
    run = AgentRun(answer="", tool_calls={t: 0 for t in tool_limits})
    retried = False
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt},
                                      {"role": "user", "content": user_content}]
    for i in range(MAX_LLM_CALLS):
        last_call = i == MAX_LLM_CALLS - 1
        available = [t for t, cap in tool_limits.items() if run.tool_calls[t] < cap]
        tools = None if last_call else toolbox.openai_tools(available)
        # Until the required observation is made, every call with tools is forced (first call + one retry).
        tool_choice = "required" if (tools and require_tool_first and not run.tool_results) else None
        if last_call and available:
            emit({"agent": name, "type": "limit",
                  "detail": f"LLM call {i + 1}/{MAX_LLM_CALLS}: tools withheld, final answer required"})
        try:
            # A tool-call step needs few tokens; the cap also bounds degenerate outputs (a 7B model once
            # emitted 46 identical calls in 1024 tokens when a call was required and the tool failed).
            max_tokens = TOOL_STEP_MAX_TOKENS if tools else ANSWER_MAX_TOKENS
            res = await asyncio.to_thread(llm.chat, model, messages, tools, 0.0, max_tokens, tool_choice)
        except Exception as e:  # server down, timeout...
            run.errors.append(f"{name}: LLM call failed: {e}")
            emit({"agent": name, "type": "error", "detail": run.errors[-1]})
            return run
        run.llm_calls += 1
        emit({"agent": name, "type": "llm", "model": res.model, "latency_s": round(res.latency_s, 3),
              "prompt_tokens": res.prompt_tokens, "completion_tokens": res.completion_tokens,
              "tools_offered": [t["function"]["name"] for t in tools or []],
              "tool_calls": [c.name for c in res.tool_calls]})

        if not res.tool_calls:
            if tool_choice == "required" and not retried:
                # LM Studio does not strictly enforce tool_choice="required": an answer written
                # without the required observation may invent it. Discard it and ask again once.
                emit({"agent": name, "type": "limit",
                      "detail": "a tool call was required but the model answered: answer discarded, retrying"})
                messages.append({"role": "user", "content": "Do not answer yet. Call the tool now."})
                retried = True
                continue
            if require_tool_first and not run.tool_results:
                # Second text answer after the retry: accepted, but traced as unobserved (D-17).
                run.errors.append(f"{name}: a tool call was required but never made; answer accepted "
                                  "without observation")
                emit({"agent": name, "type": "limit", "detail": run.errors[-1]})
            run.answer = (res.content or "").strip()
            return run

        # Drop duplicate calls (same tool, same arguments) and keep at most MAX_CALLS_PER_STEP.
        unique, seen = [], set()
        for c in res.tool_calls:
            key = (c.name, json.dumps(c.arguments, sort_keys=True) if c.arguments is not None else c.raw_arguments)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        dropped = len(res.tool_calls) - len(unique[:MAX_CALLS_PER_STEP])
        if dropped:
            emit({"agent": name, "type": "limit", "detail": f"{dropped} duplicate/extra tool call(s) dropped"})
        res.tool_calls = unique[:MAX_CALLS_PER_STEP]

        messages.append({
            "role": "assistant", "content": res.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.name, "arguments": c.raw_arguments}} for c in res.tool_calls],
        })
        for call in res.tool_calls:
            if call.name not in tool_limits:
                content = f"error: tool {call.name!r} is not available to you"
            elif run.tool_calls[call.name] >= tool_limits[call.name]:
                content = (f"error: limit reached for {call.name} ({tool_limits[call.name]} call(s)); "
                           "answer with what you have")
                emit({"agent": name, "type": "limit", "detail": content})
            elif call.arguments is None:
                content = f"error: arguments are not valid JSON: {call.raw_arguments!r}"
            else:
                run.tool_calls[call.name] += 1
                emit({"agent": name, "type": "tool_call", "tool": call.name, "arguments": call.arguments})
                out = await toolbox.call(call.name, call.arguments)
                run.tool_results.append({"tool": call.name, "arguments": call.arguments, "ok": out.ok,
                                         "result": out.payload, "duration_s": round(out.duration_s, 3)})
                emit({"agent": name, "type": "tool_result", "tool": call.name, "ok": out.ok,
                      "duration_s": round(out.duration_s, 3), "result": out.payload})
                if not out.ok:
                    run.errors.append(f"{name}: {call.name} failed: {out.payload}")
                content = json.dumps(out.payload, ensure_ascii=False) if out.ok else f"error: {out.payload}"
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
    # Unreachable in practice: the last call has no tools, so the model must answer in text.
    run.errors.append(f"{name}: LLM call limit reached without an answer")
    return run


def format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return "(no relevant passage found in the knowledge base)"
    return "\n\n".join(f"[{e['doc_id']}#{e['section']}] (rerank {e['rerank_score']})\n{e['text']}" for e in evidence)
