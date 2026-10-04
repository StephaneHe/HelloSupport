# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Every release bumps the version **and** adds an entry here.

## [Unreleased]

## [1.11.2] - 2026-10-04

Fixes from the independent documentation-to-code review (`docs/REVIEW_DOC_CODE.md`, 31 findings, each now marked resolved or accepted).

### Fixed
- **Incidents database dates no longer drift** (review F-1): the seed day is stored in `PRAGMA user_version` and the database is re-seeded when the day changes. Before, dates stayed relative to the first run and case C4 ("3 incidents in the last 30 days") would have failed for a correct answer about 12 days after the seed. SQLite connections used for seeding are now closed explicitly (on Windows an open handle blocked the re-seed).
- **C6 check `no status asserted`** (review F-3): a suggested check ("assurez-vous que le service est en cours d'exécution", "make sure the service is running") is no longer counted as a status claim, and hedged claims ("il semble que Redis soit en cours d'exécution", "seems to be running") are now caught. Re-scoring all archived runs changes two rows only (7B, v1.11.2 run: 16/18 → 18/18).
- Web demo (review U-6): the result path and the trace list `post-processing` only when the technician produced an answer.
- PDF export: the HTML is tagged `lang="en"`.

### Changed
- **Required tool never called is now traced** (review I-1): when the model answers in text again after the retry, the answer is still accepted (behaviour unchanged) but the run gets a `limit` event and an error "a tool call was required but never made; answer accepted without observation".
- Documentation aligned with the code: `docs/SPEC.md` (§3, §4, §6, §7, §8 amended), `docs/DESIGN_DECISIONS.md` (D-09, D-12, D-13, D-14, D-17, D-19, D-24, D-25, D-27, D-28, D-30, D-31, diagrams), README (results table re-measured on v1.11.2, CLI timings, usage defaults and exit codes, environment variables, HTTP API, `HS_DOCS_URL` layout, guardrail tests, layout), `docs/BENCH.md` (corrected C6 account, non-archived measurements flagged, v1.11.2 section), `.env.example` (all variables).
- Benchmark reports in `docs/bench/`: labels aligned with what the generator prints (review I-9); figures and answers untouched.
- pytest: unused `live` marker removed.

### Added
- `tests/test_guardrails.py`: the guardrails that had no test (per-step call cap, invalid JSON arguments, tool not offered, `max_tokens` caps, tool timeout, SQLite authorizer, SQL timeout, `;` in a string literal), plus the daily re-seed, the required-tool fall-through and the web path.
- Full benchmark on v1.11.2 (6 × 3, both models) and a 7B C6 × 10 control: `docs/bench/bench-20261004-185627.md`, `-190049.md`, `-190503.md`.
- UR-007 in `docs/USER_REQUIREMENTS.md`.

## [1.11.1] - 2026-10-04

### Changed
- **All documentation is now in English**: `docs/SPEC.md`, `docs/DESIGN_DECISIONS.md` (31 decisions, tables, legends, Mermaid diagrams), `docs/BENCH.md`, `docs/DEMO.md`, `TODO_LIST.md`, README harmonized; PDFs regenerated. The French test questions and the raw model answers are kept verbatim (test data).
- Benchmark output in English: case titles, check names (`cases.py`), report labels and tables (`benchmark.py`); the labels of the existing reports in `docs/bench/` translated, model answers untouched.

### Added
- `docs/USER_REQUIREMENTS.md`: every user request with its date, verbatim text and protecting test (UR-001 to UR-006).
- `tests/test_user_requirements.py`: language check on the published Markdown (no document mostly French, documented exceptions) and checks on the architecture diagrams (Mermaid, five triage categories, typed agents/router, agent loop, legend).

## [1.11.0] - 2026-10-04

### Added
- **Web demo** (`hello-support web`, default `http://127.0.0.1:5179`): one page that runs the real pipeline and streams its live trace over Server-Sent Events — triage category and path through the graph, each agent's LLM calls, MCP tool calls with the SQL written by the model and the rows returned, guardrails as they fire — then the answer with its cited sources and metrics. Model and scenario selectors, the six validation cases as one-click buttons, light/dark mode, mobile layout.
- Robustness: one question at a time (queue with position), clear errors when LM Studio is down or a model is missing, per-question timeout, one warm MCP tool server shared by all questions.
- `HS_SCENARIO_FILE`: the simulated scenario can be switched at runtime (used by the demo).
- Tests: web endpoints, SSE stream, scenario switching, LM Studio offline / model missing, queue (`tests/test_web.py`); `docs/DESIGN_DECISIONS.md` D-31.

### Changed
- Direct dependencies declared for the demo: `starlette`, `uvicorn`, `httpx` (already installed through `mcp`).

## [1.10.1] - 2026-10-04

### Added
- README installation note for 8 GB GPUs: pin a per-model LM Studio load config (auto-fit off, context 8192, 1 parallel session); recent builds auto-fit the context (25,600 × 4 slots) and saturate the GPU.
- `docs/BENCH.md`: quick check after the fix — 4B p50/max 4.38 s / 7.6 s on the six cases (was 9.5 s / 100.9 s when saturated), 7B stable on C1/C3.

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

[Unreleased]: https://github.com/StephaneHe/HelloSupport/compare/v1.11.1...HEAD
[1.11.1]: https://github.com/StephaneHe/HelloSupport/compare/v1.11.0...v1.11.1
[1.11.0]: https://github.com/StephaneHe/HelloSupport/compare/v1.10.1...v1.11.0
[1.10.1]: https://github.com/StephaneHe/HelloSupport/compare/v1.10.0...v1.10.1
[1.10.0]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.3...v1.10.0
[1.9.3]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.2...v1.9.3
[1.9.2]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.1...v1.9.2
[1.9.1]: https://github.com/StephaneHe/HelloSupport/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/StephaneHe/HelloSupport/releases/tag/v1.9.0
