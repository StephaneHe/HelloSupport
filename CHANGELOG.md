# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Every release bumps the version **and** adds an entry here.

## [Unreleased]

## [1.10.0] - 2026-10-04

### Changed
- **Routing**: `out_of_scope` and `vague` questions now skip the documentalist and go straight to the technician (no tool), like `history`; only `malfunction` and `documentation` use retrieval (`NEEDS_RETRIEVAL` in `workflow.py`). Measured before/after on both models: `vague` −55 % (7B) to −86 % (4B) median latency, `out_of_scope` −35 % (4B) / unchanged (7B), 2 LLM calls instead of 3–4, 36–67 % fewer input tokens; no regression on the six validation cases (`docs/BENCH.md`, D-30).
- Diagrams (README, SPEC §4, DESIGN_DECISIONS) show the new paths of the 5 triage categories; PDFs regenerated.

### Added
- Tests: `out_of_scope` / `vague` / malfunction-without-service skip the documentalist; `documentation` still uses it.
- `docs/DESIGN_DECISIONS.md` D-30; `docs/BENCH.md` v1.10.0 before/after section.

## [1.9.3] - 2026-10-04

### Added
- Diagram **legend** (README, `docs/DESIGN_DECISIONS.md`, `docs/SPEC.md`): each block is typed and styled — 🟦 **agent** (Documentalist, Technician), 🟧 **router** (triage), ⬜ deterministic **code**, 🟩 **MCP tool**, 🟪 served **model**.
- Second diagram, **inside an agent**: the bounded LLM ↔ tools loop (≤ 3 LLM calls, ≤ 3 tool calls per step, last call without tools, required tool → rejected answer → retry, exit on a text answer).
- `docs/DESIGN_DECISIONS.md` **D-29**: agent vs router vs code, and why the LangGraph graph is linear with no loop between agents.

### Changed
- Architecture diagrams redrawn: agents show their loop, the triage is drawn as a router (1 structured-output LLM call, no tool, no loop), post-processing as code, and the graph is labelled linear. Assistant behaviour unchanged. PDFs regenerated.

## [1.9.2] - 2026-10-04

### Changed
- Diagrams (README, `docs/SPEC.md` §4, `docs/DESIGN_DECISIONS.md` synthesis) now show the **5 fixed triage categories** and the path each one actually takes in `workflow.py` / `agents.py`: `malfunction`, `documentation`, `out_of_scope` and `vague` go through the documentalist, then the technician with its per-category tools (`get_service_status` required for `malfunction`, no tool otherwise); `history` (incident history) skips retrieval and requires `query_incidents` (SQL).
- `docs/SPEC.md` §4 diagram: reranking returns the top-3 (it said top-2). PDFs regenerated.

## [1.9.1] - 2026-10-04

### Changed
- Architecture diagrams (README, `docs/SPEC.md`, `docs/DESIGN_DECISIONS.md`) converted from ASCII art to **Mermaid** flowcharts, rendered natively by GitHub.
- `tools/md2pdf.py` renders Mermaid blocks to SVG with mermaid-cli (`mmdc`, driving the installed Edge/Chrome) and embeds them in the PDFs; `SPEC.pdf` and `DESIGN_DECISIONS.pdf` regenerated.

## [1.9.0] - 2026-10-02

### Added
- Professional English `README.md` (pitch, architecture, measured results, setup, usage, limits, roadmap).
- `LICENSE` (MIT).
- `tools/md2pdf.py` handles GitHub-style lists when exporting PDFs.

### Changed
- First public release: the repository was re-initialised from a clean snapshot. Personal working notes are no longer tracked.
- Docs (`SPEC`, `DESIGN_DECISIONS`) now link each decision to the **skill it demonstrates**; PDFs regenerated.
- `pyproject.toml`: license and author metadata.

## [1.8.0] - 2026-10-02

### Added
- J5 — serving throughput command (`hello-support throughput`, concurrency 1 vs 4): 1.6–1.8× aggregate throughput, per-request latency doubled.
- Consolidated `docs/DESIGN_DECISIONS.md` (synthesis, component → decision → skill table, lessons, 28 decisions including ADR D-25 "default model") and its PDF.
- `docs/DEMO.md`: commented end-to-end demo transcript (the "required tool" guardrail is visible).

### Changed
- `docs/SPEC.md` marked as implemented; `docs/BENCH.md` J5 section.

## [1.7.0] - 2026-10-02

### Added
- J4 — executable validation cases (`cases.py`) and `hello-support bench` (cases × runs × models, latency, tokens, throughput, estimated cloud cost, Markdown report with every answer in `docs/bench/`).
- `postprocess.py`: citations mapped back to exact ids; "simulated status / no action executed" footer written by code.
- Whole-graph tests with a scripted LLM; decisions D-21 to D-24.

### Changed
- Triage prompt: explicit rules + examples (12/12 on bench questions and held-out paraphrases, both models).
- SQL instruction: issue all queries in the same step (fixes a conclusion invented after a narrated, unexecuted query).
- Results: 7B 10/18 → 18/18 cases, 4B 7/18 → 15/18.

## [1.6.0] - 2026-10-02

### Added
- J3 — LangGraph orchestration: `triage` (structured JSON output) → `documentalist` → `technician`, direct branch for incident-history questions.
- `hello-support ask` with live trace and JSON export to `runs/`.
- MCP host (`toolbox.py`); agent loop guardrails: tool and LLM-call budgets, tool-free last call, de-duplication, verified `tool_choice=required`.

## [1.5.0] - 2026-10-02

### Added
- J2 — MCP server `hello-support-mcp` (stdio) with `search_docs`, `get_service_status` (simulated scenarios) and `query_incidents` (read-only SQL).
- `sql_guard.py`: single SELECT, LIMIT 50, `mode=ro` connection, SQLite authorizer, timeout.

## [1.4.0] - 2026-10-02

### Added
- J1 — RAG: section chunking, multilingual Sentence-Transformers embeddings on GPU, embedded Chroma, cross-encoder reranking, off-topic threshold; `hello-support search`.

## [1.3.0] - 2026-10-02

### Added
- J0 — `uv` package, CLI (`--version`, `smoke`), OpenAI-compatible LLM client measuring latency and tokens; local models via LM Studio.

## [1.2.0] - 2026-10-02

### Added
- Design-decision log (`docs/DESIGN_DECISIONS.md`, ADR style), kept up to date at each milestone.

## [1.1.0] - 2026-10-02

### Added
- Project specification (`docs/SPEC.md` + PDF): scope, milestones, acceptance cases.

## [1.0.0] - 2026-10-02

### Added
- Initial project scaffold.

[Unreleased]: https://github.com/StephaneHe/HelloSupport/compare/v1.10.0...HEAD
[1.10.0]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.3...v1.10.0
[1.9.3]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.2...v1.9.3
[1.9.2]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.1...v1.9.2
[1.9.1]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/StephaneHe/HelloSupport/releases/tag/v1.9.0
