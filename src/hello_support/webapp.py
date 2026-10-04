"""Web demo: one page that runs the real pipeline and streams its live trace (Server-Sent Events).

Nothing is re-implemented: a question goes through `workflow.run_request` (LangGraph graph, agents,
MCP tools, LM Studio) and every trace event it emits is forwarded to the browser as it happens.

- One question at a time: requests wait behind an asyncio lock (the browser sees its queue position).
- One warm MCP tool server is shared by all questions (the RAG models load once, ~30 s). The
  simulated scenario is switched per question through a small file (HS_SCENARIO_FILE).
- Clear errors when LM Studio is not reachable or a model is not available; a per-question timeout.
"""

import asyncio
import json
import os
import tempfile
import time
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__
from .cases import CASES, citations
from .config import Settings, load_settings
from .llm import LLMClient
from .toolbox import ToolBox
from .workflow import run_request

STATIC = Path(__file__).parent / "static"
SCENARIOS = {"stopped": "PostgreSQL stopped", "running": "all services running",
             "tool_error": "status tool fails"}
MODELS = {"slm": "Qwen3-4B (SLM)", "large": "Qwen2.5-7B (default)"}
CASE_LABELS = {"C1": "PostgreSQL down", "C2": "PostgreSQL running", "C3": "Documentation question",
               "C4": "Incident history (SQL)", "C5": "Out of scope", "C6": "Tool failure"}
MAX_QUESTION_CHARS = 500


class Demo:
    """State shared by the requests: LLM client, warm tool server, single-question lock."""

    def __init__(self, settings: Settings | None = None, llm: Any = None, toolbox_factory=None,
                 request_timeout_s: float | None = None, queue_timeout_s: float | None = None):
        self.settings = settings or load_settings()
        self.llm = llm or LLMClient(self.settings)
        # Tests pass a factory returning ToolBox(server=<in-process MCP server>); default: MCP subprocess.
        self.toolbox_factory = toolbox_factory
        self.toolbox: ToolBox | None = None
        self.request_timeout_s = request_timeout_s or float(os.getenv("HS_WEB_TIMEOUT_S", "240"))
        self.queue_timeout_s = queue_timeout_s or float(os.getenv("HS_WEB_QUEUE_TIMEOUT_S", "300"))
        self.lock = asyncio.Lock()
        self.waiting = 0
        self.tools_state = "starting"  # starting | loading | ready | error
        self.tools_error = ""
        self.tools_ready = asyncio.Event()
        self.scenario_file = Path(tempfile.gettempdir()) / f"hello-support-web-scenario-{os.getpid()}.txt"
        self._stack = AsyncExitStack()

    # ---------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        self.scenario_file.write_text("stopped", encoding="utf-8")
        os.environ["HS_SCENARIO_FILE"] = str(self.scenario_file)  # inherited by the MCP server process
        self.tools_state = "loading"
        factory = self.toolbox_factory or ToolBox
        self.toolbox = await self._stack.enter_async_context(factory())
        if self.toolbox_factory:  # injected tool server: nothing to warm up
            self.tools_state = "ready"
            self.tools_ready.set()
        else:
            asyncio.create_task(self._warm_up())

    async def _warm_up(self) -> None:
        try:
            out = await self.toolbox.call("search_docs", {"query": "warm-up"})  # waits for the RAG models
            if not out.ok:
                raise RuntimeError(out.payload)
            self.tools_state = "ready"
        except Exception as e:  # reported by /api/health and to the next question
            self.tools_state, self.tools_error = "error", str(e)
        finally:
            self.tools_ready.set()

    async def stop(self) -> None:
        await self._stack.aclose()
        self.scenario_file.unlink(missing_ok=True)
        if os.environ.get("HS_SCENARIO_FILE") == str(self.scenario_file):
            del os.environ["HS_SCENARIO_FILE"]

    # ---------------------------------------------------------------- LM Studio checks
    def _lmstudio_root(self) -> str:
        return self.settings.llm_base_url.rstrip("/").removesuffix("/v1")

    async def llm_status(self) -> dict:
        """Reachability, available and loaded models. Never raises."""
        status: dict = {"base_url": self.settings.llm_base_url, "reachable": False, "available": [], "loaded": []}
        try:
            status["available"] = await asyncio.to_thread(self.llm.list_models)
            status["reachable"] = True
        except Exception as e:
            status["error"] = f"{type(e).__name__}: {e}"
            return status
        try:  # LM Studio-specific endpoint: which models are currently loaded (optional)
            async with httpx.AsyncClient(timeout=3) as client:
                data = (await client.get(self._lmstudio_root() + "/api/v0/models")).json()["data"]
            status["loaded"] = [m["id"] for m in data if m.get("state") == "loaded"]
        except Exception:
            pass
        return status

    async def check_model(self, model_id: str) -> str | None:
        """Return a user-facing error message, or None if the model can be used."""
        status = await self.llm_status()
        if not status["reachable"]:
            return (f"LM Studio is not reachable at {status['base_url']}. Start it (lms server start) "
                    f"and try again.")
        if model_id not in status["available"]:
            return (f"Model '{model_id}' is not available in LM Studio. Download it first "
                    f"(see README › Installation).")
        return None

    # ---------------------------------------------------------------- one question
    async def ask(self, question: str, alias: str, scenario: str, emit) -> None:
        if self.lock.locked():
            emit("queued", {"position": self.waiting + 1})
        self.waiting += 1
        try:
            await asyncio.wait_for(self.lock.acquire(), self.queue_timeout_s)
        except TimeoutError:
            emit("error", {"message": "The demo is busy with another question. Please try again in a moment."})
            return
        finally:
            self.waiting -= 1
        try:
            model_id = self.settings.resolve_model(alias)
            emit("status", {"stage": "checking LM Studio", "model": model_id})
            problem = await self.check_model(model_id)
            if problem:
                emit("error", {"message": problem})
                return
            if not self.tools_ready.is_set():
                emit("status", {"stage": "loading the tool server (retrieval models, ~30 s, first question only)"})
                await asyncio.wait_for(self.tools_ready.wait(), self.request_timeout_s)
            if self.tools_state == "error":
                emit("error", {"message": f"The MCP tool server failed to start: {self.tools_error}"})
                return
            self.scenario_file.write_text(scenario, encoding="utf-8")  # read by get_service_status
            emit("status", {"stage": "running", "model": model_id, "scenario": scenario})
            start = time.perf_counter()
            result = await asyncio.wait_for(
                run_request(question, model=model_id, scenario=scenario, llm=self.llm, toolbox=self.toolbox,
                            settings=self.settings, on_event=lambda e: emit("trace", e)),
                self.request_timeout_s)
            emit("result", summarize(result, time.perf_counter() - start))
        except TimeoutError:
            emit("error", {"message": f"No answer after {self.request_timeout_s:.0f} s (timeout). Is LM Studio "
                                      f"busy or the model still loading?"})
        except Exception as e:
            emit("error", {"message": f"{type(e).__name__}: {e}"})
        finally:
            self.lock.release()


def summarize(result: dict, wall_s: float) -> dict:
    """What the page needs: answer, sources, route, path, tool results and metrics."""
    observations = result.get("observations", [])
    sources = list(dict.fromkeys(citations(result.get("answer", ""))))
    if any(o["tool"] == "query_incidents" and o["ok"] for o in observations):
        sources.append("incidents database (SQL)")
    agents = [e["agent"] for e in result.get("trace", []) if e.get("type") == "start"]
    # Post-processing only runs when the technician produced an answer (status "done").
    post = ["post-processing"] if "technician" in agents and result.get("status") == "done" else []
    return {
        "answer": result.get("answer", ""),
        "sources": sources,
        "route": result.get("route"),
        "path": ["triage", *agents, *post],
        "status": result.get("status"),
        "errors": result.get("errors", []),
        "evidence": [{k: e.get(k) for k in ("doc_id", "section", "rerank_score")} for e in result.get("evidence", [])],
        "observations": observations,
        "counters": result.get("counters", {}),
        "metrics": {**result.get("metrics", {}), "wall_s": round(wall_s, 2)},
        "model": result.get("model"),
        "scenario": result.get("scenario"),
    }


def sse(kind: str, data: Any) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def create_app(demo: Demo | None = None) -> Starlette:
    demo = demo or Demo()

    @asynccontextmanager
    async def lifespan(app):
        await demo.start()
        yield
        await demo.stop()

    async def index(request: Request):
        return FileResponse(STATIC / "index.html")

    async def health(request: Request):
        return JSONResponse({
            "version": __version__, "tools": demo.tools_state, "tools_error": demo.tools_error,
            "busy": demo.lock.locked(), "waiting": demo.waiting, "llm": await demo.llm_status(),
            "models": {a: demo.settings.resolve_model(a) for a in MODELS},
        })

    async def config(request: Request):
        return JSONResponse({
            "version": __version__,
            "docs_url": os.getenv("HS_DOCS_URL", "").rstrip("/"),
            "models": [{"alias": a, "label": l, "id": demo.settings.resolve_model(a)} for a, l in MODELS.items()],
            "default_model": "large" if demo.settings.model_default in ("large", demo.settings.model_large) else "slm",
            "scenarios": [{"id": s, "label": l} for s, l in SCENARIOS.items()],
            "cases": [{"id": c.id, "label": CASE_LABELS.get(c.id, c.title), "question": c.question,
                       "scenario": c.scenario} for c in CASES],
        })

    async def ask(request: Request):
        q = (request.query_params.get("question") or "").strip()
        alias = request.query_params.get("model", "large")
        scenario = request.query_params.get("scenario", "stopped")
        if not q or len(q) > MAX_QUESTION_CHARS:
            return JSONResponse({"error": f"question must be 1–{MAX_QUESTION_CHARS} characters"}, status_code=400)
        if alias not in MODELS or scenario not in SCENARIOS:
            return JSONResponse({"error": "unknown model or scenario"}, status_code=400)

        queue: asyncio.Queue = asyncio.Queue()

        def emit(kind: str, data: Any) -> None:
            queue.put_nowait((kind, data))

        async def work():
            try:
                await demo.ask(q, alias, scenario, emit)
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(work())

        async def stream():
            yield sse("accepted", {"question": q, "model": alias, "scenario": scenario})
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), 15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if item is None:
                    break
                yield sse(*item)
            await task
            yield sse("done", {})

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return Starlette(routes=[
        Route("/", index),
        Route("/api/health", health),
        Route("/api/config", config),
        Route("/api/ask", ask),
        Mount("/static", StaticFiles(directory=STATIC), name="static"),
    ], lifespan=lifespan)


def serve(host: str = "127.0.0.1", port: int = 5179) -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")
