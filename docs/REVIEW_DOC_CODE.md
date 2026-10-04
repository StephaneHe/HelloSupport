# Documentation ↔ code consistency review

- **Date**: 2026-10-04 · **Version reviewed**: 1.11.1 (commit `94ae064`)
- **Reviewer**: independent pass by an AI assistant (Claude), fresh session, nothing reused from the sessions that wrote the code or the docs.
- **Scope read in full**: `README.md`, `CHANGELOG.md`, `TODO_LIST.md`, `docs/SPEC.md`, `docs/DESIGN_DECISIONS.md`, `docs/BENCH.md`, `docs/DEMO.md`, `docs/USER_REQUIREMENTS.md`, the summary tables of the 15 raw reports in `docs/bench/`, all of `src/hello_support/` (Python and `static/`), `tests/`, `tools/md2pdf.py`, `pyproject.toml`, `.env.example`, `data/`.
- **Checks actually run**: `uv run pytest` → 91 passed, 1 deselected, 15.5 s; one in-process MCP call to read two real error messages; `uv.lock` for the pinned versions; `git tag`.
- **Not done**: no LLM benchmark was re-run (it needs LM Studio and the GPU). Every benchmark figure was compared with the archived raw reports only. The two PDFs were not opened; they were committed together with their Markdown sources.
- **Rule of this review**: no code and no existing file was changed. Each row proposes a fix; none is applied.
- **Side effect of this file**: the language test is parametrized per published Markdown file, so adding this report raises the suite from 91 to **92** tests (all pass). The README badge and text (`README.md:9,289`) still say 91.

There is no `webdemo/README` in the repository: the web demo is documented in the README section *Web demo* and in D-31, and its code is `src/hello_support/webapp.py` and `static/`. A local, untracked launcher for the demo was also read; it is consistent with the code (port 5179, `HS_DOCS_URL`).

## Verdict

The **core architecture claims are confirmed by the code**: the five triage categories and their paths, the two agents and their loop limits, the three MCP tools, the five SQL guards, models and defaults, commands, scenarios, ports, and all 31 decisions are implemented as described. The headline benchmark tables match the raw reports digit for digit.

The gaps are concentrated in three places:

1. **`docs/SPEC.md` §3, §4 (layout) and §8** still describe the plan from before the implementation, although the status line says "implemented".
2. **Sections written for v1.8.0** (D-27, D-28, the README results table) were not refreshed after v1.10.0, v1.11.0 and v1.11.1.
3. **A few statements are stronger than what the code or the raw data supports** (incident dates, "required" tool, "every guardrail is tested", the cause of the 7B failures on C6).

| Severity | Meaning | Count |
|---|---|---|
| **False** | contradicted by the code or by the raw data, and never fully true | 4 |
| **Obsolete** | true at an earlier version, no longer true | 10 |
| **Imprecise** | partly true, overstated, or impossible to verify from the repository | 9 |
| **Undocumented** | significant code behavior absent from the docs | 8 |
| | **Total** | **31** |

## 1. False

| ID | Where the doc says it | What the code or data shows | Proposed fix |
|---|---|---|---|
| F-1 | `DESIGN_DECISIONS.md:492-498` (D-14): dates are "relative to today"; "the last 30 days" always has the same expected answer, which makes case C4 verifiable. `README.md:188`: the database is generated on first use. | The database is seeded **once** and never refreshed: `data_store.py:87-88` returns the existing file. Dates are relative to the day of the first run, not to today. The postgres incidents sit 2, 6 and 19 days before the seed (`data_store.py:30-34`), so **11 to 12 days after the seed the count drops from 3 to 2** (the exact day depends on the SQL the model writes) and the C4 check `answer "3 incidents"` (`cases.py:112`) fails for a correct answer. The local file is dated 2026-10-02, so this happens from 2026-10-13 or 14. The unit test pins `now` (`tests/test_sql_guard.py:12,60-66`) and cannot catch it. | Doc: say the dates are relative to the seed day and that `data/incidents.db` must be deleted to re-anchor them. Better, in code: reseed when the file is older than a day, or seed at each MCP server start. |
| F-2 | `README.md:253-254` (*Demo*, CLI commands): "The first question takes ~30 s (the tool server loads the retrieval models), then 2–15 s per question." | Each `hello-support ask` starts a **new** MCP server (`workflow.py:182-186`, `toolbox.py:30-32`), and the retriever loads in every server (`mcp_server.py:99-100`). Every CLI question on the retrieval path pays the load again. `DEMO.md:3` says so itself ("two cold runs, each with a fresh MCP server") and shows 31.9 s for C1 (`DEMO.md:59`). The sentence is true only for the web demo and for `bench`, which keep one warm server. | Reword: with `ask`, each `malfunction` or `documentation` question takes ~20–30 s because the tool server is restarted; `history`, `out_of_scope` and `vague` take 2–10 s; the 2–15 s warm figures apply to the web demo and the benchmark. |
| F-3 | `BENCH.md:235` and `DESIGN_DECISIONS.md:914-918` (D-30): the 7B failures on C6 are explained by one check, "says the check failed", and the wording "statut indéterminé"; described as wording instability only. | In the 10-run control on the new code, one of the two failures is a **different check**: `no status asserted` (`bench/bench-20261004-124927.md:29-30`). The 7B wrote that the Redis server appears to be running although the status tool had failed (same file, line 69). This is an invented observation by the default model, not a keyword miss. | Correct the table and D-30: new code 8/10 with one "says the check failed" and one "no status asserted". Add to *Known limitations* (`README.md:344-345`) and to the D-25 table that the 7B also asserted a status once in 10 runs when the tool fails. |
| F-4 | `README.md:296-298`: "Every guardrail is locked by a test that replays the failure it was built for." | Tested: per-tool budget, de-duplication, tool-free last call, required-tool retry, tool error (`tests/test_agents.py:55-79`, `tests/test_workflow_fake_llm.py:46-55`), SQL static check, row limit, read-only mode. **Not tested**: the cap of 3 calls per step (`agents.py:22,197-200`; the test has only 2 unique calls), invalid JSON arguments in the loop (`agents.py:214-215`), tool not offered (`agents.py:208-209`), the SQLite authorizer (`sql_guard.py:44-45,54`; the test at `tests/test_sql_guard.py:47-52` uses a raw connection without it), the 2 s SQL timeout (`sql_guard.py:55-56`), the `max_tokens` caps (`agents.py:23-24,166`), the tool timeout (`toolbox.py:56-59`). | Either write "the main guardrails are locked by tests" and list them, or add the seven missing tests. |

## 2. Obsolete

| ID | Where the doc says it | What the code shows now | Proposed fix |
|---|---|---|---|
| O-1 | `SPEC.md:76`: "Web API, UI" are explicitly out of scope. `SPEC.md:37-38`: the CLI is `ask`, `search`, `bench`, `--version`. Status line `SPEC.md:3`: implemented (v1.8.0). | A web UI and an HTTP API ship since v1.11.0: `webapp.py:264-270`, `static/`, command `web` (`cli.py:192-195`). The CLI also has `smoke` (`cli.py:168-170`) and `throughput` (`cli.py:187-191`). | Add a dated amendment in §3: web demo added in v1.11.0 (D-31), commands `smoke`, `throughput`, `web`. Remove "Web API, UI" from the exclusions or mark it superseded. |
| O-2 | `DESIGN_DECISIONS.md:827` (D-27): "Code, prompts and comments are in English, the documentation in French." | All published documentation is English since v1.11.1 (`USER_REQUIREMENTS.md:17`, `SPEC.md:72`, `README.md:329`), enforced by `tests/test_user_requirements.py:51-54`. | Replace with "everything is in English (UR-006)". |
| O-3 | `README.md:141-151,156` and `SPEC.md:4`: 7B 18/18, 4B 15/18, p50 6.0 s and 9.0 s, 4.5 and 4.2 LLM calls, "invents source ids (case C6, 3/3)". | These figures match `bench/bench-20261002-173250.md:5-9` exactly, but that run is **v1.7.0 code**. Since then the routing changed (v1.10.0) and the LM Studio settings were pinned. Latest full 6 × 3 runs on current routing: 7B **17/18** (`bench-20261004-122103.md:5`), 4B **16/18**, p50 **4.38 s**, 4.28 calls (`bench-20261004-132504.md:5-8`), with C6 source ids invented in 1 run of 3, not 3 of 3. No full 7B 6 × 3 run exists with the pinned settings. | Date the table ("measured on v1.7.0, 2026-10-02") and add the latest figures, or re-run `bench --runs 3` for both models on v1.11.1 and replace the table. |
| O-4 | `README.md:149,158`: 173 and 128 tok/s with 4 concurrent requests; "1.6–1.8× more aggregate throughput". | `README.md:190-196` tells the user to pin **1 parallel session**. `BENCH.md:270-272` states that with one slot the concurrency-4 measurement is no longer reproduced. The README promotes a result that its own installation advice disables. | Add the caveat from `BENCH.md:270-272` next to the two README lines, or move them under a "measured with 4 slots, before pinning" note. |
| O-5 | `DESIGN_DECISIONS.md:836` (D-28): "Unit, offline, < 3 s (`uv run pytest`, 40 tests)". | 91 tests in 15.5 s (run during this review); `README.md:9,289` already says 91 and ~15 s. D-28 also omits the web tests and the user-requirement tests. | Update the count and duration; add `tests/test_web.py` and `tests/test_user_requirements.py` to level 1. |
| O-6 | `DESIGN_DECISIONS.md:810-828` (D-27): module table and "~1,600 lines of code (+ ~400 of tests)". `README.md:304`: `cli.py` commands are `smoke, search, ask, bench, throughput`. `DESIGN_DECISIONS.md:18`: an assistant "in the terminal". | The table has no `webapp.py` and no `static/`; `cli.py` also has `web`. Current size: about 1,900 lines of Python and 415 of HTML/CSS/JS in `src/`, about 700 lines of tests. | Add the two rows and the `web` command; update the sizes; say "terminal and browser" in the summary. |
| O-7 | `DESIGN_DECISIONS.md:177` (index, D-09): "top-5 → top-2". `SPEC.md:43`: "→ top-2". | `search_docs` returns the top 3: `mcp_server.py:25,64`. The D-09 body (`:388-389`), the mapping table (`:127`) and the SPEC diagram (`SPEC.md:112`) already say top-3. Only the `search` command keeps a default of 2 (`cli.py:175`). | Fix the two lines; mention that the CLI `search` default stays at 2. |
| O-8 | `SPEC.md:54-55`: graph `documentalist → technician → END`, state `(question, evidence, observations, counters, errors, answer, trace)`. `SPEC.md:45`: "FastMCP". | The graph starts with a triage node and has two conditional edges (`workflow.py:130-137`). The state also has `model`, `scenario`, `route`, `brief`, `status` (`workflow.py:36-48`). The server class is `MCPServer` from SDK v2 (`mcp_server.py:11,18`; `uv.lock`: mcp 2.2.0). | Align §3 with the §4 diagram, which is correct; replace "FastMCP" with "`MCPServer` (SDK v2)". |
| O-9 | `SPEC.md:139-146` (target layout): `hello_support/` at the root, `metrics.py`, `data/seed_incidents.py`. `SPEC.md:228-230`: `langchain-openai`, `langchain-mcp-adapters`, `pydantic` as tools. `SPEC.md:159`: about 15 incidents. | Layout is `src/hello_support/`; there is no `metrics.py` (metrics live in `workflow.py:141-152` and `benchmark.py`); seeding is `data_store.py:71-84` with 14 rows. `pyproject.toml:10-21` has no LangChain package (D-05, D-20 explain why); Pydantic is only a transitive dependency. | Replace the target layout with a pointer to the README layout; strike the two LangChain packages with a reference to D-05 and D-20. |
| O-10 | `DESIGN_DECISIONS.md:494-495` (D-14): scenario selected by `HS_SCENARIO` "(soon `--scenario`)". `SPEC.md:37`: `--scenario stopped\|running`. | `--scenario` exists (`cli.py:178`) and four scenarios are accepted (`data/scenarios.json:5-8`). `HS_SCENARIO_FILE` now has priority over `HS_SCENARIO` (`data_store.py:51-54`). | Update both lines; state the order: file, then variable, then default. |

## 3. Imprecise

| ID | Where the doc says it | What the code or data shows | Proposed fix |
|---|---|---|---|
| I-1 | Diagrams and text: `get_service_status` and `query_incidents` are "REQUIRED" (`README.md:44,112`; `DESIGN_DECISIONS.md:38,115`); D-17 (`:575-576`): "the code guarantees the consequences". | The code retries **once**. If the model answers in text a second time, that answer is **accepted** without any observation (`agents.py:159,178-188`: `retried` is already true), with status `done` and no trace event that says so. The docs correctly say "retries once" but not what happens next. No test covers this path. | State the fall-through explicitly, or change the code to return a controlled failure (and emit a `limit` event) when the required tool was never called. |
| I-2 | Main diagrams (`README.md:46`, `SPEC.md:99`, `DESIGN_DECISIONS.md:40`): post-processing is drawn as a step of the LangGraph graph; the graph is called linear. | The graph has three nodes (`workflow.py:131-133`); post-processing runs **inside** the technician node (`workflow.py:108-112`). A fourth edge, documentalist → END on failure (`workflow.py:122-123,136`), is described in D-16 (`:533`) but drawn nowhere. | Draw post-processing inside the technician box (or note "same node"); add the failure edge as a dashed line. |
| I-3 | Measurements with no raw data in the repository: (a) the targeted gain table, 5 runs, `out_of_scope` and `vague` (`BENCH.md:204-213`, D-30 `:907-912`, `README.md:157`, `CHANGELOG.md:41`); (b) serving throughput (`BENCH.md:177-182`, `README.md:148-149`); (c) triage 12/12 on held-out paraphrases (D-24 `:732-734`) and 4/6 (D-17); (d) "0/3" tool calls (`BENCH.md:79-82`). | **Cannot conclude.** (a) No report in `docs/bench/` contains the `vague` question, and `bench` can only run the six cases (`cli.py:139`, `cases.py:77-139`), so the table cannot be reproduced with the shipped command. (b) `throughput` only prints (`cli.py:147-153`). (c) and (d): no script and no question set in `src/` or `tests/`. The figures are internally consistent across the docs. | Archive the raw outputs in `docs/bench/`; add the `vague` question and the 12 triage questions as data so the measurements can be replayed. |
| I-4 | `SPEC.md:180-183` (§6): C5 covers "Mon Kafka est lent" and "ça marche pas"; C6 covers an unknown service, a rejected SQL query or a reached call limit. All boxes are ticked. | The executable C5 has only the Kafka question (`cases.py:120-128`). The executable C6 is a **tool failure** in scenario `tool_error` (`cases.py:129-138`). The three situations listed for C6 are covered by unit tests instead (`tests/test_tools.py:40-55`, `tests/test_agents.py:55-71`). | Reword §6 to match `cases.py`, and cite the unit tests for the other situations. |
| I-5 | `SPEC.md:200`: "the host validates the arguments with Pydantic before executing". `DESIGN_DECISIONS.md:443` (D-12): example message "unknown service". | The host only checks that the arguments are valid JSON (`llm.py:72-75`, `agents.py:214-215`). Type validation is done by the MCP server. For an unknown service the real message is the Pydantic literal error ("Input should be 'postgres', 'nginx' or 'redis'", checked by a live call); the "unknown service" text of `data_store.py:62-63` is unreachable through MCP. §7 is flagged as written before implementation. | Fix the §7 sentence ("validated by the tool server"); replace the D-12 example with the real message. |
| I-6 | `SPEC.md:46-47`: `search_docs` returns `{doc_id, section, text, score, rerank_score}`; `get_service_status` returns `{service, status, simulated}`. | Hits also carry `vector_rank` and `relevant` (`retrieval.py:48-58`); the status also carries `scenario` (`data_store.py:68`). The tool docstring itself omits `vector_rank` (`mcp_server.py:54-55`). | Complete the three descriptions. |
| I-7 | `README.md:214`: `bench [--models slm large] [--runs 3]`; `README.md:293`: `uv run hello-support bench` takes ~6 min. `README.md:213`: `search "<text>"`. | The default is **1** run (`cli.py:185`); the README results need `--runs 3`. `search` also accepts `--top-k` and `--top-n` (`cli.py:174-175`). The 6 min cannot be verified here. | Show the defaults in the usage table; say which command line produced the results table. |
| I-8 | `DESIGN_DECISIONS.md:618-619` (D-19): events are `llm`, `tool_call`, `tool_result`, `limit`, `error`. | There is a sixth type, `start` (`workflow.py:73,96`), used by the CLI (`cli.py:96-97`) and by the web page to build the path (`webapp.py:174`). The triage `llm` event also carries `route` (`agents.py:132-134`). | Add `start` and the `route` field. |
| I-9 | `CHANGELOG.md:15`: the labels of the existing reports were translated. | The translated reports do not match what the generator prints: `(run 1) : check` with a space before the colon in every report versus `(run {n}): {k}` (`benchmark.py:142`); `no invented status` in `bench-20261002-172401.md:51` versus the check name `no status asserted` (`cases.py:135`, used in `bench-20261004-124927.md:30`). Figures are unaffected. | Harmless; align the two labels if the reports are ever regenerated. |

## 4. Undocumented

| ID | Code behavior | Where | Proposed documentation |
|---|---|---|---|
| U-1 | **Triage failure fallback**: if the triage call fails or returns invalid JSON, the route silently becomes `documentation` with no service; an `error` event is emitted. With LM Studio down this leads to the documentalist failing, the fixed English `FALLBACK_ANSWER`, status `failed` and exit code 1. | `agents.py:121-129`, `workflow.py:32-33,82-91`, `cli.py:131` | One paragraph in D-17 or D-18, and the exit codes of `ask` and `smoke` in the README usage table. |
| U-2 | **Environment variables** missing from the README table: `HS_WEB_TIMEOUT_S` (240), `HS_WEB_QUEUE_TIMEOUT_S` (300), `HS_SCENARIO_FILE` (only in the CHANGELOG and D-31; it overrides `HS_SCENARIO` and `--scenario`). `.env.example` lacks `HS_LLM_TIMEOUT_S` and `HS_SCENARIO`, which the table lists. | `webapp.py:54-55`, `data_store.py:47-57`, `README.md:200-206` | Add the three variables to the table and the two to `.env.example`. |
| U-3 | **Web HTTP API**: `/api/health`, `/api/config`, `/api/ask` (GET, SSE); event kinds `accepted`, `queued`, `status`, `trace`, `result`, `error`, `done`; 500-character limit; keep-alive comment every 15 s; model restricted to the aliases `slm` and `large`. Each web question is also saved under `runs/` (default `save=True`). | `webapp.py:41,154-156,225-270`, `workflow.py:163,189-190` | A short "HTTP API" table in the README or in D-31. |
| U-4 | **`HS_DOCS_URL` assumes a site layout**: links go to `<url>/#architecture` and `<url>/kb/<sheet>/#<section>`. Nothing in the repository builds such a site. | `static/app.js:35,190-194`, `README.md:281` | Say which layout is expected, or link to the GitHub files instead. |
| U-5 | **A `;` inside a string literal is rejected** by the static SQL check (confirmed by a live call), in addition to the keyword false positives that D-13 does mention. | `sql_guard.py:35-36`, `DESIGN_DECISIONS.md:476-478` | Add it to the D-13 trade-offs. |
| U-6 | **Web path display**: the result always lists `post-processing`, and the page always logs "citations normalised, simulation note added", even when the run failed before the technician and no post-processing ran. | `webapp.py:179`, `static/app.js:221` | Code fix preferred: add the step only when the technician produced an answer. |
| U-7 | **A running `web` server keeps the retrieval models on the GPU** (about 1 GB according to D-10) for its warm tool server; this matters when `bench` runs on the same 8 GB card. Nothing next to the benchmark instructions says so. | `webapp.py:65-75`, `DESIGN_DECISIONS.md:401`, `BENCH.md:255-261` | One line in the README *Tests* or *Web demo* section: stop the web demo before a benchmark. |
| U-8 | Small items: `config.py` is missing from the README layout (`README.md:302-317`); the pytest marker `live` is declared but used by no test (`pyproject.toml:52`); `tools/md2pdf.py:97` still writes `lang="fr"` in the HTML used for the English PDFs. | as cited | Add the layout line; drop the marker or use it; set `lang="en"`. |

## 5. Claims checked and confirmed

| Claim | Evidence in the code |
|---|---|
| Five categories: `malfunction`, `history`, `documentation`, `out_of_scope`, `vague` | `agents.py:26`, JSON schema `agents.py:51-54` |
| `malfunction` and `documentation` go through the documentalist; the three others go straight to the technician | `workflow.py:31,125-128,135`; tests `tests/test_workflow_fake_llm.py:28-87` |
| A malfunction without a known service becomes `vague` | `agents.py:130-131`; test `tests/test_agents.py:82-85` |
| `MAX_LLM_CALLS = 3`, last call without tools, at most 3 tool calls per step, de-duplication | `agents.py:21-22,154-157,190-200` |
| Budgets: `search_docs` ≤ 2, `get_service_status` ≤ 1, `query_incidents` ≤ 2 | `workflow.py:30`, `agents.py:88,91` |
| Tool policy per category; tool required for `malfunction` and `history`; one retry | `agents.py:87-107,159,178-186` |
| `max_tokens` 300 with tools and 700 for the answer; temperature 0 | `agents.py:23-24,166-167` |
| Timeouts: LLM 120 s, tools 240 s, retriever wait 180 s, SQL 2 s, `recursion_limit` 10 | `config.py:30`, `toolbox.py:14`, `mcp_server.py:60`, `sql_guard.py:16`, `workflow.py:179` |
| Three MCP tools over stdio, `enum` for the service, explicit `ToolError` | `mcp_server.py:50-93,101`; test `tests/test_tools.py:22-29` |
| Five SQL guards: single SELECT or WITH, forced limit of 50 (wrapped with 51), `mode=ro`, authorizer, timeout | `sql_guard.py:15-23,30-41,51-56` |
| Retrieval: section chunks with the sheet title, the two named models, cosine Chroma, fingerprint rebuild, top-5, threshold −5, warm-up, CUDA when available | `retrieval.py:18-26,61-69,76-79,95-118,120-137` |
| 3 sheets × 4 sections = 12 chunks; 14 incidents; 4 scenarios, default `stopped` | `data/kb/`, test `tests/test_retrieval.py:14-19`; `data_store.py:29-44`; `data/scenarios.json` |
| Models and defaults: `qwen/qwen3-4b-2507`, `qwen2.5-7b-instruct`, default `large`, endpoint `:1234/v1` | `config.py:26-30`, `.env.example` |
| Commands `ask`, `search`, `bench`, `throughput`, `web`, `smoke`, `--version`, and `hello-support-mcp` | `cli.py:164-196`, `pyproject.toml:23-25` |
| Web demo: `127.0.0.1:5179`, Starlette and SSE, one question at a time with a queue position, shared warm tool server, scenario switch by file, LM Studio and model checks, per-question timeout, three scenarios, light and dark theme, mobile layout | `cli.py:192-195`, `webapp.py:36-37,56-75,115-165,273-276`, `static/app.js:18-26`, `static/style.css:9,37`; 7 tests in `tests/test_web.py` |
| Post-processing: citation normalisation, unknown citations flagged and kept, simulation footer in the language of the question | `postprocess.py:20-54`, `workflow.py:108-112` |
| Six cases with 5 to 7 checks each (36 checks, 108 for 3 runs) | `cases.py:77-139` |
| Cost estimate from two list prices; no API call | `benchmark.py:26-29,100-102` |
| Versions: one source, 1.11.1; LangGraph 1.2, Chroma 1.5, MCP SDK 2.2, torch 2.6.0+cu124 | `__init__.py:3`, `pyproject.toml:46-47`, `uv.lock` |
| 91 offline tests, ~15 s | run during this review |
| Tags `pre-1.10.0` and `v1.9.0` to `v1.11.1` exist | `git tag` |
| All test names cited in `USER_REQUIREMENTS.md` exist | `tests/test_user_requirements.py`, `tests/test_workflow_fake_llm.py:63,74`, `tests/test_web.py` |
| `DEMO.md` transcript format, guardrail messages, 5 proposed queries with 3 dropped | `cli.py:93-113`, `agents.py:182-183,197-199` |

### Benchmark figures against the raw reports

| Figures in the docs | Raw report | Result |
|---|---|---|
| J4 before fixes: 7/18 and 10/18, 81/108 and 98/108 (`BENCH.md:117-120`) | `bench-20261002-172401.md:5-6` | match |
| J4 final and README table: 15/18, 18/18, 105/108, 108/108, 5.96 / 11.52 s, 9.04 / 15.65 s, 4.5 and 4.22 calls, 2774/347 and 2602/391 tokens, 57.9 and 45.3 tok/s, costs | `bench-20261002-173250.md:5-14,20-25` | match (README rounds) |
| Cold start 20–26 s (`BENCH.md:169`) | `bench-20261002-173250.md:33` (19.6–26.0 s) | match |
| v1.10.0 full table: 15/18 → 15/18, 18/18 → 17/18, per-case counts, C5 p50, global p50 (`BENCH.md:224-229`) | `120325`, `121113`, `121546`, `122103` | match |
| C6 controls 8/10, 5/5, 8/10, 4/5; C3 controls 5/8 and 7/8 (`BENCH.md:235-236`) | `122757`, `122531`, `124927`, `122349`, `125223`, `125119` | counts match; cause misreported, see F-3 |
| After pinning: 4B 16/18, 4.38 / 7.6 s; 7B C1 + C3 6/6, 8.8 / 11.2 s (`BENCH.md:267-268`) | `132504`, `132635` | match |
| v1.11.0: 6/6 for both, p50 4.9 s and 7.3 s (`BENCH.md:276`) | `145500` | match |
| Targeted gain table and throughput table | none archived | cannot conclude, see I-3 |

## 6. Suggested order of work

1. **F-1**: the C4 case starts failing around 2026-10-13 on this machine; fix before the next benchmark.
2. **F-3 and O-3**: correct the account of the 7B on C6 and re-run the 6 × 3 benchmark on v1.11.1 so the README table describes the current code.
3. **I-1**: decide whether a required tool that is never called should fail the request; then align the diagrams.
4. **O-1, O-8, O-9, O-10**: one amendment pass on `SPEC.md` §3, §4 (layout) and §8.
5. **O-2, O-5, O-6, O-7, F-2, F-4, O-4**: one-line edits in `README.md` and `DESIGN_DECISIONS.md`.
6. The remaining rows as time allows.
