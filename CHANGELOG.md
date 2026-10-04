# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Every release bumps the version **and** adds an entry here.

## [Unreleased]

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

[Unreleased]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.1...HEAD
[1.9.1]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/StephaneHe/HelloSupport/releases/tag/v1.9.0
