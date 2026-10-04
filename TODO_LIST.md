# TODO_LIST — HelloSupport

Convention: `(+ date)` = added, `(✔ date)` = done. Milestones defined in `docs/SPEC.md` §5.

## Framing

- [x] Analysis of an initial minimal project proposal; final spec `docs/SPEC.md` (+ PDF) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] Spec approved (100% local); added the `DESIGN_DECISIONS.md` deliverable `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] Download the LM Studio models (3–4B SLM + qwen2.5-7b-instruct Q4_K_M) `(+ 2026-10-02)` `(✔ 2026-10-02)`

## Milestones

- [x] J0 — Foundation (uv, version, llm.py, SLM + 7B smoke test, fake tool calling) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J1 — RAG (knowledge-base sheets, ST → Chroma → reranker, `search` command, GPU) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J2 — Data + MCP (scenarios, SQLite incidents, sql_guard, MCP server with 3 tools) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J3 — Agents + LangGraph orchestration (state, limits, trace) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J4 — Fixes: C4 (inconsistent SQL reasoning); C3 (format without "Observation"); sources kept unaltered (`Service_status`) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] J4 — Validation (6 real cases + pytest with fake LLM, BENCH.md): 7B 18/18, SLM 15/18 `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [ ] Known, not fixed: the SLM invents source identifiers when the status tool fails (C6) `(+ 2026-10-02)`
- [x] J5 — SLM vs 7B benchmark, consolidated DESIGN_DECISIONS + PDF, README, release `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] Open-source release: English README, MIT license, fresh history without personal documents `(+ 2026-10-02)` `(✔ 2026-10-02)`

## Decision log

- [x] Add the `D-xx` entries at each milestone in `docs/DESIGN_DECISIONS.md` (28 decisions, consolidated + PDF) `(+ 2026-10-02)` `(✔ 2026-10-02)`
- [x] D-29 and diagrams with legend: agents (LLM ↔ tools loop) vs router vs code `(+ 2026-10-04)` `(✔ 2026-10-04)`
- [x] D-30: `out_of_scope` and `vague` skip the documentalist; before/after benchmark, no regression `(+ 2026-10-04)` `(✔ 2026-10-04)`
- [x] Per-model LM Studio settings (auto-fit off, context 8192, parallelism 1): latencies stabilized `(+ 2026-10-04)` `(✔ 2026-10-04)`
- [x] Web demo (`hello-support web`, served locally): live trace, 6 cases × 2 models checked in Edge `(+ 2026-10-04)` `(✔ 2026-10-04)`
- [x] All documentation in English, locked by a language test (`docs/USER_REQUIREMENTS.md`) `(+ 2026-10-04)` `(✔ 2026-10-04)`
- [x] Doc-to-code review (31 findings) resolved or accepted; C6 status-claim check fixed; daily re-seed of the incidents database `(+ 2026-10-04)` `(✔ 2026-10-04)`
- [ ] C6/C3 checks sensitive to wording ("statut indéterminé" (undetermined status), citations): consider a semantic check `(+ 2026-10-04)`

## Ideas (beyond the hello world, see SPEC §10)

- [ ] Measure the hybrid "triage by the SLM, answer by the 7B" with `hello-support bench` (D-25) `(+ 2026-10-02)`
- [ ] PostgreSQL + pgvector (incidents and vectors in the same engine) `(+ 2026-10-02)`
- [ ] LangGraph checkpointer (resume, human-in-the-loop) `(+ 2026-10-02)`
- [ ] RAG evaluation (recall@k, MRR before/after rerank) on a question set `(+ 2026-10-02)`
- [ ] MCP over streamable HTTP (separate tool server); vLLM for a real throughput test `(+ 2026-10-02)`
