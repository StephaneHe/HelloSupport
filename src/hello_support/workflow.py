"""LangGraph workflow with an explicit shared state:

    START -> triage -> documentalist -> technician -> END
                  \\-- (history) --------/

The graph (code) decides the sequence of steps and the tool policy per intent; inside each
step the model chooses the tool arguments and writes the answer (bounded by agents.run_agent).
Every event is recorded in the state trace; the run is exported to runs/<timestamp>.json.
"""

import json
import operator
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import (DOCUMENTALIST_PROMPT, TECHNICIAN_POLICY, TECHNICIAN_PROMPT, format_evidence, run_agent,
                     triage)
from .config import Settings, load_settings
from .llm import LLMClient
from .postprocess import normalize_citations, simulation_footer
from .retrieval import PROJECT_ROOT
from .toolbox import ToolBox

RUNS_DIR = PROJECT_ROOT / "runs"
DOCUMENTALIST_TOOLS = {"search_docs": 2}
FALLBACK_ANSWER = ("I could not produce an answer (see errors in the trace). "
                   "No corrective action was executed.")


class State(TypedDict, total=False):
    question: str  # the user request, never modified
    model: str
    scenario: str | None
    route: dict  # triage result: intent (malfunction|history|documentation|out_of_scope|vague), service
    evidence: list[dict]  # relevant passages: doc_id, section, text, score, rerank_score
    brief: str  # documentalist's summary handed to the technician
    observations: list[dict]  # technician tool calls and their real (simulated) results
    counters: dict[str, Any]  # per agent: llm calls, tool calls
    status: str  # active / last step: retrieving, diagnosing, done, failed
    errors: Annotated[list[str], operator.add]
    answer: str
    trace: Annotated[list[dict], operator.add]


def build_graph(llm: LLMClient, toolbox: ToolBox, on_event: Callable[[dict], None]):
    t0 = time.perf_counter()

    def recorder():
        events: list[dict] = []

        def emit(event: dict) -> None:
            event = {"t": round(time.perf_counter() - t0, 3), **event}
            events.append(event)
            on_event(event)

        return events, emit

    async def triage_node(state: State) -> dict:
        events, emit = recorder()
        route = await triage(state["question"], llm, state["model"], emit)
        return {"route": {"intent": route["intent"], "service": route["service"]},
                "counters": {"triage": {"llm_calls": route["llm_calls"]}},
                "status": "retrieving", "trace": events}

    async def documentalist(state: State) -> dict:
        events, emit = recorder()
        emit({"agent": "documentalist", "type": "start"})
        run = await run_agent("documentalist", DOCUMENTALIST_PROMPT, state["question"], DOCUMENTALIST_TOOLS,
                              llm, state["model"], toolbox, emit)
        evidence: dict[str, dict] = {}
        for r in run.tool_results:
            if r["ok"] and isinstance(r["result"], list):
                for hit in r["result"]:
                    if hit.get("relevant"):
                        evidence.setdefault(f"{hit['doc_id']}#{hit['section']}", hit)
        failed = run.llm_calls == 0
        return {
            "evidence": list(evidence.values()),
            "brief": run.answer,
            "counters": {**state.get("counters", {}),
                         "documentalist": {"llm_calls": run.llm_calls, "tool_calls": run.tool_calls}},
            "status": "failed" if failed else "diagnosing",
            "errors": run.errors,
            "trace": events,
            **({"answer": FALLBACK_ANSWER} if failed else {}),
        }

    async def technician(state: State) -> dict:
        events, emit = recorder()
        emit({"agent": "technician", "type": "start"})
        route = state["route"]
        policy = TECHNICIAN_POLICY[route["intent"]]
        user = (f"User question:\n{state['question']}\n\n"
                f"Triage: intent={route['intent']}, service={route['service']}\n\n"
                f"Documentalist brief:\n{state.get('brief') or '(none)'}\n\n"
                f"Evidence passages:\n{format_evidence(state.get('evidence', []))}\n\n"
                f"Task: {policy['instruction'].format(service=route['service'])}")
        run = await run_agent("technician", TECHNICIAN_PROMPT, user, policy["tools"],
                              llm, state["model"], toolbox, emit, require_tool_first=policy["require_tool"])
        counters = {**state.get("counters", {}),
                    "technician": {"llm_calls": run.llm_calls, "tool_calls": run.tool_calls}}
        answer, unknown = normalize_citations(run.answer) if run.answer else (FALLBACK_ANSWER, [])
        if unknown:
            emit({"agent": "technician", "type": "limit", "detail": f"unknown citation(s) kept as is: {unknown}"})
        if run.answer:
            answer += simulation_footer(run.tool_results, state["question"])
        return {
            "observations": run.tool_results,
            "counters": counters,
            "answer": answer,
            "status": "done" if run.answer else "failed",
            "errors": run.errors,
            "trace": events,
        }

    def after_documentalist(state: State) -> str:
        return END if state.get("status") == "failed" else "technician"

    def after_triage(state: State) -> str:
        # Incident history questions are answered from the database: the knowledge base is not needed.
        return "technician" if state["route"]["intent"] == "history" else "documentalist"

    g = StateGraph(State)
    g.add_node("triage", triage_node)
    g.add_node("documentalist", documentalist)
    g.add_node("technician", technician)
    g.add_edge(START, "triage")
    g.add_conditional_edges("triage", after_triage, ["documentalist", "technician"])
    g.add_conditional_edges("documentalist", after_documentalist, ["technician", END])
    g.add_edge("technician", END)
    return g.compile()


def summarize(state: State, total_s: float) -> dict:
    llm_events = [e for e in state.get("trace", []) if e["type"] == "llm"]
    tool_events = [e for e in state.get("trace", []) if e["type"] == "tool_result"]
    return {
        "total_s": round(total_s, 2),
        "llm_calls": len(llm_events),
        "llm_s": round(sum(e["latency_s"] for e in llm_events), 2),
        "prompt_tokens": sum(e["prompt_tokens"] for e in llm_events),
        "completion_tokens": sum(e["completion_tokens"] for e in llm_events),
        "tool_calls": len(tool_events),
        "tool_s": round(sum(e["duration_s"] for e in tool_events), 2),
    }


async def run_request(
    question: str,
    model: str | None = None,
    scenario: str | None = None,
    on_event: Callable[[dict], None] = lambda e: None,
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    toolbox: ToolBox | None = None,
    save: bool = True,
) -> dict:
    """Run one request end to end; return the final state plus metrics (and save it as JSON).

    `toolbox`: an already-open ToolBox (the benchmark reuses one MCP session so that the RAG
    loading cost is paid once); otherwise a new MCP server is spawned for this request.
    """
    settings = settings or load_settings()
    llm = llm or LLMClient(settings)
    model_id = settings.resolve_model(model)
    start = time.perf_counter()

    async def invoke(tb: ToolBox) -> State:
        return await build_graph(llm, tb, on_event).ainvoke(
            {"question": question, "model": model_id, "scenario": scenario, "status": "retrieving",
             "errors": [], "trace": []},
            {"recursion_limit": 10},
        )

    if toolbox is not None:
        state = await invoke(toolbox)
    else:
        async with ToolBox(scenario=scenario) as tb:
            state = await invoke(tb)
    result = {**state, "metrics": summarize(state, time.perf_counter() - start),
              "finished_at": datetime.now().isoformat(timespec="seconds")}
    if save:
        result["trace_file"] = str(save_run(result))
    return result


def save_run(result: dict, runs_dir: Path = RUNS_DIR) -> Path:
    runs_dir.mkdir(exist_ok=True)
    path = runs_dir / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
