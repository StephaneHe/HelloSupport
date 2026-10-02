"""Benchmark: the six validation cases x N runs x models, warm, with checks, latency, tokens and cost.

One MCP session is opened per scenario and warmed up (RAG loaded, model loaded by LM Studio)
before measuring, so the reported latencies are per-request, not per-session. The cold
loading time is reported separately.
"""

import asyncio
import json
import statistics
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .cases import CASES, Case, evaluate
from .config import load_settings
from .llm import LLMClient
from .retrieval import PROJECT_ROOT
from .toolbox import ToolBox
from .workflow import RUNS_DIR, run_request

# Public list prices in USD per 1M tokens (input, output), used only to ESTIMATE what the measured
# token volumes would cost on a hosted API. Indicative values at the time of writing (2026-10):
# check the providers' pricing pages before quoting them. No account or API call is involved.
REFERENCE_PRICES_USD_PER_MTOK = {
    "OpenAI gpt-4o-mini": (0.15, 0.60),
    "Anthropic Claude Haiku 4.5": (1.00, 5.00),
}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


async def _warm_up(tb: ToolBox, llm: LLMClient, model: str) -> float:
    start = time.perf_counter()
    await tb.call("search_docs", {"query": "warm-up"})  # waits for the RAG to finish loading
    await asyncio.to_thread(llm.chat, model, [{"role": "user", "content": "ok"}], None, 0.0, 1)
    return time.perf_counter() - start


async def run_benchmark(models: list[str], runs: int, cases: list[Case] = CASES,
                        progress: Callable[[str], None] = print) -> dict:
    settings = load_settings()
    llm = LLMClient(settings)
    rows, warmups = [], []
    for alias in models:
        model = settings.resolve_model(alias)
        for scenario in dict.fromkeys(c.scenario for c in cases):
            group = [c for c in cases if c.scenario == scenario]
            async with ToolBox(scenario=scenario) as tb:
                cold = await _warm_up(tb, llm, model)
                warmups.append({"model": model, "scenario": scenario, "cold_start_s": round(cold, 1)})
                progress(f"{model} / scenario {scenario}: session ready in {cold:.1f}s")
                for run in range(1, runs + 1):
                    for case in group:
                        result = await run_request(case.question, model=model, scenario=scenario,
                                                   llm=llm, toolbox=tb, save=False)
                        checks = evaluate(case, result)
                        rows.append({
                            "model": model, "case": case.id, "title": case.title, "run": run,
                            "passed": all(checks.values()), "checks": checks,
                            "route": result.get("route"), "status": result.get("status"),
                            "tools": [(o["tool"], o["arguments"], o["ok"]) for o in result.get("observations", [])],
                            "answer": result.get("answer"), "errors": result.get("errors", []),
                            "metrics": result["metrics"],
                        })
                        progress(f"  {case.id} run {run}: {'PASS' if rows[-1]['passed'] else 'FAIL'} "
                                 f"{sum(checks.values())}/{len(checks)} checks, {result['metrics']['total_s']}s")
    return {"date": datetime.now().isoformat(timespec="seconds"), "runs": runs, "rows": rows,
            "warmups": warmups, "summary": summarize(rows)}


def summarize(rows: list[dict]) -> dict:
    out = {}
    for model in dict.fromkeys(r["model"] for r in rows):
        rs = [r for r in rows if r["model"] == model]
        m = [r["metrics"] for r in rs]
        llm_s = sum(x["llm_s"] for x in m)
        tok_in = statistics.mean(x["prompt_tokens"] for x in m)
        tok_out = statistics.mean(x["completion_tokens"] for x in m)
        out[model] = {
            "requests": len(rs),
            "cases_passed": sum(r["passed"] for r in rs),
            "checks_passed": sum(sum(r["checks"].values()) for r in rs),
            "checks_total": sum(len(r["checks"]) for r in rs),
            "latency_p50_s": round(percentile([x["total_s"] for x in m], 0.5), 2),
            "latency_max_s": round(max(x["total_s"] for x in m), 2),
            "llm_calls_mean": round(statistics.mean(x["llm_calls"] for x in m), 2),
            "tokens_in_mean": round(tok_in),
            "tokens_out_mean": round(tok_out),
            "output_tokens_per_s": round(sum(x["completion_tokens"] for x in m) / llm_s, 1) if llm_s else 0,
            "requests_per_min": round(60 * len(rs) / sum(x["total_s"] for x in m), 1),
            "est_cost_usd_per_1000_requests": {
                name: round(1000 * (tok_in * pin + tok_out * pout) / 1e6, 2)
                for name, (pin, pout) in REFERENCE_PRICES_USD_PER_MTOK.items()},
            "per_case": {
                c: {"passed": sum(r["passed"] for r in rs if r["case"] == c),
                    "runs": sum(1 for r in rs if r["case"] == c),
                    "latency_p50_s": round(percentile([r["metrics"]["total_s"] for r in rs if r["case"] == c], .5), 2)}
                for c in dict.fromkeys(r["case"] for r in rs)},
        }
    return out


def to_markdown(report: dict) -> str:
    s = report["summary"]
    models = list(s)
    lines = [f"Date : {report['date']} · {report['runs']} exécution(s) par cas · mesures **à chaud** "
             "(session MCP et modèle chargés).", "",
             "| Indicateur | " + " | ".join(f"`{m}`" for m in models) + " |",
             "|---|" + "---|" * len(models)]

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(s[m]) for m in models) + " |")

    row("Cas réussis (toutes vérifications)", lambda x: f"{x['cases_passed']}/{x['requests']}")
    row("Vérifications réussies", lambda x: f"{x['checks_passed']}/{x['checks_total']}")
    row("Latence p50 / max par requête", lambda x: f"{x['latency_p50_s']} s / {x['latency_max_s']} s")
    row("Appels LLM par requête (moy.)", lambda x: str(x["llm_calls_mean"]))
    row("Tokens in / out par requête (moy.)", lambda x: f"{x['tokens_in_mean']} / {x['tokens_out_mean']}")
    row("Débit de génération (tokens out / s LLM)", lambda x: str(x["output_tokens_per_s"]))
    row("Requêtes / min (séquentiel)", lambda x: str(x["requests_per_min"]))
    row("Coût local", lambda x: "0 € (électricité non comptée)")
    for name in REFERENCE_PRICES_USD_PER_MTOK:
        row(f"Coût estimé si API {name}, /1000 req.",
            lambda x, n=name: f"~{x['est_cost_usd_per_1000_requests'][n]} $")
    lines += ["", "Par cas (réussites / exécutions, latence p50) :", "",
              "| Cas | " + " | ".join(f"`{m}`" for m in models) + " |", "|---|" + "---|" * len(models)]
    for c in CASES:
        lines.append(f"| {c.id} {c.title} | " + " | ".join(
            f"{s[m]['per_case'][c.id]['passed']}/{s[m]['per_case'][c.id]['runs']} · "
            f"{s[m]['per_case'][c.id]['latency_p50_s']} s" if c.id in s[m]["per_case"] else "—" for m in models) + " |")
    lines += ["", "Vérifications échouées :", ""]
    fails = [(r["model"], r["case"], r["run"], k) for r in report["rows"] for k, v in r["checks"].items() if not v]
    lines += [f"- `{m}` {c} (run {n}) : {k}" for m, c, n, k in fails] or ["- aucune"]
    lines += ["", "Démarrage à froid d'une session (RAG + modèle) : " + ", ".join(
        f"{w['model']}/{w['scenario']} {w['cold_start_s']} s" for w in report["warmups"]), ""]
    return "\n".join(lines)


THROUGHPUT_PROMPT = ("In 5 short bullet points, list what to check when an application cannot connect to "
                     "its PostgreSQL database.")


async def measure_throughput(models: list[str], concurrencies: list[int], requests: int,
                             max_tokens: int = 160) -> list[dict]:
    """Same chat request sent `requests` times at each concurrency level; aggregate tokens/s and latency."""
    settings = load_settings()
    llm = LLMClient(settings)
    out = []
    for alias in models:
        model = settings.resolve_model(alias)
        await asyncio.to_thread(llm.chat, model, [{"role": "user", "content": "ok"}], None, 0.0, 1)  # load
        for conc in concurrencies:
            sem = asyncio.Semaphore(conc)

            async def one():
                async with sem:
                    return await asyncio.to_thread(llm.chat, model, [{"role": "user", "content": THROUGHPUT_PROMPT}],
                                                   None, 0.7, max_tokens)

            start = time.perf_counter()
            results = await asyncio.gather(*(one() for _ in range(requests)))
            wall = time.perf_counter() - start
            toks = sum(r.completion_tokens for r in results)
            lat = [r.latency_s for r in results]
            out.append({"model": model, "concurrency": conc, "requests": requests, "wall_s": round(wall, 2),
                        "output_tokens": toks, "tokens_per_s": round(toks / wall, 1),
                        "requests_per_min": round(60 * requests / wall, 1),
                        "latency_p50_s": round(percentile(lat, .5), 2), "latency_max_s": round(max(lat), 2)})
    return out


def throughput_markdown(rows: list[dict]) -> str:
    lines = ["| Modèle | Concurrence | Requêtes | Durée | Tokens out/s (agrégé) | Req/min | Latence p50 / max |",
             "|---|---|---|---|---|---|---|"]
    lines += [f"| `{r['model']}` | {r['concurrency']} | {r['requests']} | {r['wall_s']} s | {r['tokens_per_s']} | "
              f"{r['requests_per_min']} | {r['latency_p50_s']} s / {r['latency_max_s']} s |" for r in rows]
    return "\n".join(lines)


def save_report(report: dict, runs_dir: Path = RUNS_DIR) -> tuple[Path, Path]:
    runs_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    j = runs_dir / f"bench-{stamp}.json"
    j.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_dir = PROJECT_ROOT / "docs" / "bench"
    md_dir.mkdir(exist_ok=True)
    md = md_dir / f"bench-{stamp}.md"
    md.write_text(to_markdown(report) + "\n\n## Réponses\n\n" + "\n\n".join(
        f"### {r['model']} — {r['case']} run {r['run']} ({'PASS' if r['passed'] else 'FAIL'})\n\n"
        f"route `{r['route']}` · outils `{r['tools']}`\n\n{r['answer']}" for r in report["rows"]) + "\n",
        encoding="utf-8")
    return j, md
