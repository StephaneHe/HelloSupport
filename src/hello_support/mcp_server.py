"""MCP server exposing the three HelloSupport tools over stdio.

Run standalone (e.g. for MCP Inspector):  python -m hello_support.mcp_server
The agents never import these functions directly: they reach them through an MCP client,
so a tool can move to another process or machine without touching the agent code.
"""

import threading
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__
from .data_store import INCIDENTS_DB, ensure_incidents_db, service_status
from .sql_guard import MAX_ROWS, SQLRejected, run_readonly_query

server = MCPServer(
    name="hello-support-tools",
    version=__version__,
    instructions="Troubleshooting tools: knowledge-base search, simulated service status, read-only incidents SQL.",
    log_level="WARNING",
)

SEARCH_TOP_N = 3

# The retriever takes ~30 s to load (torch, two models, Chroma): start it in the background so the
# MCP handshake is immediate, and let the first search_docs call wait for it.
_retriever = None
_retriever_error: Exception | None = None
_retriever_ready = threading.Event()


def _load_retriever() -> None:
    global _retriever, _retriever_error
    try:
        from .retrieval import Retriever

        _retriever = Retriever()
    except Exception as e:  # surfaced to the caller of search_docs
        _retriever_error = e
    finally:
        _retriever_ready.set()


def start_background_loading() -> None:
    threading.Thread(target=_load_retriever, name="retriever-loader", daemon=True).start()


@server.tool()
def search_docs(query: str) -> list[dict]:
    """Search the troubleshooting knowledge base (PostgreSQL connection, nginx unavailable, Redis unreachable).

    Returns the 3 most relevant sections after vector search and reranking, each with
    doc_id, section, text, score (cosine similarity), rerank_score and relevant.
    relevant=false means the passage is off-topic: do not use it as evidence.
    """
    if not query or not query.strip():
        raise ToolError("query must be a non-empty string")
    if not _retriever_ready.wait(timeout=180):
        raise ToolError("knowledge base is still loading, try again")
    if _retriever_error is not None:
        raise ToolError(f"knowledge base unavailable: {_retriever_error}")
    return [h.to_dict() for h in _retriever.search(query, top_n=SEARCH_TOP_N)]


@server.tool()
def get_service_status(service_name: Literal["postgres", "nginx", "redis"]) -> dict:
    """Return the SIMULATED status of a known service: {service, status, simulated, scenario}.

    status is "running" or "stopped". This never touches a real service and never changes anything.
    """
    try:
        return service_status(service_name)
    except (ValueError, RuntimeError) as e:
        raise ToolError(str(e)) from e


@server.tool()
def query_incidents(sql: str) -> dict:
    """Run ONE read-only SQLite SELECT on the incidents database and return {columns, rows, row_count, truncated}.

    Schema:
      incidents(id INTEGER, service TEXT ('postgres'|'nginx'|'redis'), started_at TEXT ISO 8601 local time,
                severity TEXT ('low'|'medium'|'high'|'critical'), summary TEXT,
                resolved INTEGER (0|1), resolved_at TEXT or NULL)
    Use SQLite date functions, e.g. started_at >= datetime('now', 'localtime', '-30 days').
    Only SELECT is allowed; at most 50 rows are returned.
    """
    try:
        return run_readonly_query(ensure_incidents_db(INCIDENTS_DB), sql)
    except SQLRejected as e:
        raise ToolError(f"SQL rejected: {e}") from e


assert MAX_ROWS == 50  # keep the docstring above in sync


def main() -> None:
    start_background_loading()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
