"""Command-line entry point: `hello-support`."""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import load_settings
from .llm import LLMClient

GET_TIME_TOOL = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Return the current local time for a given IANA timezone.",
        "parameters": {
            "type": "object",
            "properties": {"timezone": {"type": "string", "description": "e.g. Europe/Brussels"}},
            "required": ["timezone"],
        },
    },
}


def cmd_smoke(args: argparse.Namespace) -> int:
    """J0 smoke test: plain chat + one fake tool call on each requested model."""
    settings = load_settings()
    llm = LLMClient(settings)
    available = llm.list_models()
    print(f"server  {settings.llm_base_url}  models: {', '.join(available)}")
    ok = True
    for alias in args.models or ["slm", "large"]:
        model = settings.resolve_model(alias)
        print(f"\n== {alias} -> {model}")
        if model not in available:
            print("   MISSING on server")
            ok = False
            continue
        # Warm-up call (JIT model load in LM Studio), excluded from the reported latency.
        llm.chat(model, [{"role": "user", "content": "ok"}], max_tokens=1)
        r = llm.chat(model, [{"role": "user", "content": "Say hello in one short sentence."}], max_tokens=40)
        print(f"   hello : {r.content!r}")
        print(f"           {r.latency_s:.2f}s  tokens in/out {r.prompt_tokens}/{r.completion_tokens}")
        r = llm.chat(
            model,
            [{"role": "user", "content": "What time is it in Brussels right now? Use the tool."}],
            tools=[GET_TIME_TOOL],
            max_tokens=200,
        )
        good = any(c.name == "get_time" and c.arguments and "timezone" in c.arguments for c in r.tool_calls)
        print(f"   tool  : {[(c.name, c.arguments) for c in r.tool_calls]}  -> {'OK' if good else 'FAIL'}")
        print(f"           {r.latency_s:.2f}s  tokens in/out {r.prompt_tokens}/{r.completion_tokens}")
        ok &= good
    print(f"\nsmoke {'PASSED' if ok else 'FAILED'}  ({datetime.now():%Y-%m-%d %H:%M})")
    return 0 if ok else 1


def cmd_search(args: argparse.Namespace) -> int:
    """J1: show the RAG pipeline on one query (vector candidates, then reranked top-n)."""
    import time

    from .retrieval import Retriever

    t0 = time.perf_counter()
    retriever = Retriever()
    load_s = time.perf_counter() - t0
    print(f"device {retriever.device}  index {'rebuilt' if retriever.rebuilt else 'reused'}  "
          f"{len(retriever.chunks)} sections  (load {load_s:.1f}s)")
    t0 = time.perf_counter()
    hits = retriever.search(args.query, top_k=args.top_k, top_n=0)
    search_ms = (time.perf_counter() - t0) * 1000
    print(f"query  {args.query!r}  ({search_ms:.0f} ms)\n")
    print(f"{'final':>5} {'vector':>6} {'cosine':>7} {'rerank':>7} {'relevant':>8}  section")
    for i, h in enumerate(hits, start=1):
        mark = "*" if i <= args.top_n else " "
        print(f"{mark}{i:>4} {h.vector_rank:>6} {h.score:>7.3f} {h.rerank_score:>7.2f} {str(h.relevant):>8}  "
              f"{h.doc_id}#{h.section}")
    moved = [h for i, h in enumerate(hits, start=1) if h.vector_rank != i]
    print(f"\n* = returned to the agent (top {args.top_n}); "
          f"{'reranking changed the order' if moved else 'reranking kept the vector order'}")
    return 0


def _short(value, limit: int = 160) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_event(e: dict) -> None:
    who = f"[{e['t']:6.1f}s] {e['agent']:<13}"
    kind = e["type"]
    if kind == "start":
        print(f"{who} >> active")
    elif kind == "llm":
        calls = f" -> proposes {', '.join(e['tool_calls'])}" if e["tool_calls"] else " -> answers"
        route = f" -> route {e['route']}" if "route" in e else ""
        print(f"{who} LLM {e['latency_s']:.2f}s, tokens {e['prompt_tokens']}/{e['completion_tokens']}{route or calls}")
    elif kind == "tool_call":
        print(f"{who} tool {e['tool']}({_short(e['arguments'])})")
    elif kind == "tool_result":
        if e["tool"] == "search_docs" and e["ok"]:
            hits = ", ".join(f"{h['doc_id']}#{h['section']} (rerank {h['rerank_score']:.1f}"
                             f"{'' if h['relevant'] else ', off-topic'})" for h in e["result"])
            res = hits or "no hit"
        else:
            res = _short(e["result"])
        print(f"{who}   {'ok' if e['ok'] else 'ERROR'} in {e['duration_s']:.2f}s: {res}")
    else:  # limit, error
        print(f"{who} {kind.upper()}: {e['detail']}")


def cmd_ask(args: argparse.Namespace) -> int:
    """J3: answer one troubleshooting question with the two agents."""
    from .workflow import run_request

    print(f"question: {args.question}\nscenario: {args.scenario or '(default)'}  model: {args.model or '(default)'}\n")
    result = asyncio.run(run_request(args.question, model=args.model, scenario=args.scenario,
                                     on_event=(lambda e: None) if args.quiet else print_event))
    m = result["metrics"]
    print(f"\n{'=' * 72}\n{result['answer']}\n{'=' * 72}")
    print(f"model {result['model']} | {m['total_s']}s total, LLM {m['llm_calls']} calls {m['llm_s']}s, "
          f"tokens {m['prompt_tokens']}/{m['completion_tokens']}, tools {m['tool_calls']} calls {m['tool_s']}s")
    if result.get("errors"):
        print("errors: " + " | ".join(result["errors"]))
    trace = Path(result["trace_file"])
    print(f"trace: {trace.relative_to(Path.cwd()) if trace.is_relative_to(Path.cwd()) else trace}")
    return 0 if result["status"] == "done" else 1


def cmd_bench(args: argparse.Namespace) -> int:
    """J4/J5: run the six validation cases on each model; write docs/bench/*.md and runs/bench-*.json."""
    from .benchmark import run_benchmark, save_report, to_markdown
    from .cases import CASES

    cases = [c for c in CASES if not args.cases or c.id in args.cases]
    report = asyncio.run(run_benchmark(args.models or ["slm", "large"], args.runs, cases))
    json_path, md_path = save_report(report)
    print("\n" + to_markdown(report))
    print(f"report: {md_path}\nraw:    {json_path}")
    return 0


def cmd_throughput(args: argparse.Namespace) -> int:
    """J5: LLM serving throughput at several concurrency levels (same request repeated)."""
    from .benchmark import measure_throughput, throughput_markdown

    rows = asyncio.run(measure_throughput(args.models or ["slm", "large"], args.concurrency, args.requests))
    print(throughput_markdown(rows))
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    """Web demo: live trace of one question in the browser (Server-Sent Events)."""
    from .webapp import serve

    serve(host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hello-support", description="Hello-world troubleshooting assistant.")
    p.add_argument("--version", action="version", version=f"hello-support {__version__}")
    sub = p.add_subparsers(dest="command")
    s = sub.add_parser("smoke", help="check the LLM server: hello + tool calling on each model")
    s.add_argument("models", nargs="*", help="aliases (slm, large) or model ids; default: both")
    s.set_defaults(func=cmd_smoke)
    s = sub.add_parser("search", help="run the RAG retrieval (vector search + rerank) on a query")
    s.add_argument("query")
    s.add_argument("--top-k", type=int, default=5, help="vector candidates (default 5)")
    s.add_argument("--top-n", type=int, default=2, help="hits kept after reranking (default 2)")
    s.set_defaults(func=cmd_search)
    s = sub.add_parser("ask", help="answer a troubleshooting question with the two agents")
    s.add_argument("question")
    s.add_argument("--scenario", help="simulated service states: stopped, running, redis_down, tool_error")
    s.add_argument("--model", help="slm, large, or a model id (default: HS_MODEL_DEFAULT)")
    s.add_argument("--quiet", action="store_true", help="only print the final answer")
    s.set_defaults(func=cmd_ask)
    s = sub.add_parser("bench", help="run the six validation cases on the models (checks, latency, tokens, cost)")
    s.add_argument("--models", nargs="*", help="aliases or ids (default: slm large)")
    s.add_argument("--runs", type=int, default=1, help="runs per case (default 1)")
    s.add_argument("--cases", nargs="*", help="subset, e.g. C1 C4")
    s.set_defaults(func=cmd_bench)
    s = sub.add_parser("throughput", help="measure LLM serving throughput at several concurrency levels")
    s.add_argument("--models", nargs="*", help="aliases or ids (default: slm large)")
    s.add_argument("--concurrency", nargs="*", type=int, default=[1, 4])
    s.add_argument("--requests", type=int, default=8)
    s.set_defaults(func=cmd_throughput)
    s = sub.add_parser("web", help="web demo with a live trace (http://127.0.0.1:5179 by default)")
    s.add_argument("--host", default="127.0.0.1", help="bind address (0.0.0.0 to serve the local network)")
    s.add_argument("--port", type=int, default=5179)
    s.set_defaults(func=cmd_web)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
