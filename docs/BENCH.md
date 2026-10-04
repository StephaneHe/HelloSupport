# BENCH — measurements and observations

> Figures **measured** on the dev machine (Windows 11, RTX 2070 Super 8 GB, Python 3.12,
> torch 2.6.0+cu124), unless stated otherwise. One-off measurements: a single pass, no
> statistics. They are meant for reasoning, not for drawing general conclusions about performance.

## J1 — RAG: vector search then reranking (2026-10-02)

Pipeline: 12 sections (3 sheets × 4) → `paraphrase-multilingual-MiniLM-L12-v2` → Chroma
(cosine, top-5) → `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` → top-2. Device: `cuda`.

Command: `hello-support search "<question>"` (columns: final rank, vector rank, cosine,
reranker score).

### "connexion refusée postgres" (FR, sheets in English)

| final | vector | cosine | rerank | section |
|---|---|---|---|---|
| **1** | 2 | 0.507 | 7.41 | postgres_connection.md#Service status |
| **2** | 5 | 0.465 | 7.30 | postgres_connection.md#Symptoms |
| 3 | 1 | 0.519 | 2.70 | postgres_connection.md#Checks |
| 4 | 3 | 0.486 | -2.03 | nginx_unavailable.md#Service status |
| 5 | 4 | 0.474 | -2.92 | nginx_unavailable.md#Symptoms |

→ **Reranking changes the order**: the *Symptoms* section (which literally contains
"connection refused") moves from 5th to 2nd place. Two **nginx** sections were ahead of
it with vector search alone. Without reranking, the top-2 would have been *Checks* and
*Service status*: correct, but without the symptoms section.

### "My website shows 502 Bad Gateway"

| final | vector | cosine | rerank | section |
|---|---|---|---|---|
| **1** | 1 | 0.600 | 3.88 | nginx_unavailable.md#Symptoms |
| **2** | 5 | 0.451 | -4.30 | nginx_unavailable.md#Checks |
| 3 | 2 | 0.503 | -7.08 | nginx_unavailable.md#Service status |

→ *Checks* (which explains 502 = upstream down) moves from 5th to 2nd place.

### "Que vérifier si Redis répond NOAUTH ?" (What should I check if Redis answers NOAUTH?)

Top-2: `redis_unreachable.md#Checks` (6.08), then `#Symptoms` (-0.76, moved up from rank 3 to rank 2).

### "Kafka consumer lag is growing" (not in the knowledge base)

| final | vector | cosine | rerank | section |
|---|---|---|---|---|
| 1 | 2 | 0.122 | -9.25 | redis_unreachable.md#Symptoms |
| 2 | 3 | 0.120 | -9.65 | redis_unreachable.md#Limits |
| 5 | 1 | 0.212 | -10.56 | postgres_connection.md#Limits |

→ Vector search **always returns neighbors**, even when nothing matches.
All reranker scores are ≤ -9.2, whereas the useful passages of the other queries
are ≥ -4.3. Hence a coarse threshold `RELEVANCE_THRESHOLD = -5` that flags passages as
"off-topic". It lets the agent answer "not covered" (case C5).

### Latencies (J1)

| Step | Measurement |
|---|---|
| Import of `sentence_transformers` (cold) | ~15 s (fixed local cost: loading `transformers`, not network) |
| Full load of the `Retriever` (imports + 2 models on GPU + Chroma + warm-up) | ~27 s |
| First query without warm-up (CUDA kernel initialization) | ~2.9 s |
| Query after warm-up (encoding + Chroma + reranking of 5 pairs) | ~0.4–0.6 s |
| Index build (12 sections) | included in the first load; reused afterwards (content fingerprint) |

The loading cost is paid **once per session** of the MCP server (J2), not for every question.

## J3 — Agents + orchestration: first real runs (2026-10-02)

Default model: `qwen2.5-7b-instruct` (Q4_K_M), temperature 0. One run per case:
**this is not yet the J4 evaluation**. Full traces are in `runs/` (gitignored).

### Does the model choose to observe? (before triage, see D-17)

Real technician input (question + brief + 3 passages), tools offered with `tool_choice=auto`,
3 attempts:

| Model | Full input | Without brief | Question last |
|---|---|---|---|
| Qwen2.5-7B | 0/3 | 0/3 | 0/3 |
| Qwen3-4B-2507 | 0/3 | 0/3 | 0/3 |

### Triage via structured output (6 sample questions)

| Model | Correct | Errors |
|---|---|---|
| Qwen2.5-7B | 4/6 | Kafka → `vague` (expected `out_of_scope`); "ça marche pas" ("it doesn't work") → `malfunction` without a service (requalified as `vague` by the code) |
| Qwen3-4B-2507 | 4/6 | "ne parvient plus à se connecter… que vérifier ?" ("can no longer connect… what should I check?") → `documentation` (prompt clarified afterwards); "ça marche pas" → `malfunction/postgres` |

Triage latency: ~0.3 s warm, ~3–9 s for the first call (model loading by LM Studio).

### End-to-end runs after triage + guardrails (7B)

| Case | Observed behavior | Total duration |
|---|---|---|
| C1 postgres `stopped` | `get_service_status(postgres)` → `stopped`; diagnosis "service stopped, read the logs before restarting", source `Service status` | ~41 s |
| C2 postgres `running` | → `running` (simulated); different conclusion: network / config / credentials | ~40 s |
| C3 Redis documentation | no status call; list of sourced checks (an invented "Observation" in the 1st version, hence the added instruction) | ~44 s |
| C4 postgres incidents 30 d | valid SQL `COUNT(*), MAX(resolved)` → `[3, 1]`; "3 incidents" ✔; "the last one is not resolved" is **true but not derived** from the result ✘ | ~7 s |
| C5 "Mon Kafka est lent" ("My Kafka is slow") | request for clarification, no invented sheet | ~6.5 s |
| C5 "ça marche pas" | "Which service?" | ~32 s |
| C6 Redis `tool_error` | tool error traced; answer "status cannot be verified" + sourced leads; before the fix: 46 duplicate calls in 18 s | ~40 s |

Of the ~40 s, ~21–27 s correspond to **loading the RAG** in the MCP server (once per
session). LLM calls total ~11–13 s for 4–5 calls, and ~2,300–3,000 input tokens.

## J4 — Validation: 6 cases × 3 runs × 2 models (2026-10-02)

Command: `hello-support bench --models slm large --runs 3`. Automatic checks per case
(`src/hello_support/cases.py`), **warm** measurements (MCP session and model already loaded).
Full reports with **all answers**: [`bench/bench-20261002-172401.md`](bench/bench-20261002-172401.md)
(before fixes) and [`bench/bench-20261002-173250.md`](bench/bench-20261002-173250.md) (after).

### Before / after the J4 fixes

| | SLM Qwen3-4B before | SLM after | 7B before | 7B after |
|---|---|---|---|---|
| Cases passed | 7/18 | **15/18** | 10/18 | **18/18** |
| Checks passed | 81/108 | 105/108 | 98/108 | 108/108 |

Fixes between the two runs, each driven by an observed failure:
- **D-22**: citations normalized and simulation notice added by the code;
- **D-23**: SQL queries in the same step;
- **D-24**: rules and examples in the triage.

Two checks were themselves **wrong** and were fixed:
- parsing of citations separated by a space;
- an "asserted status" detected in a conditional sentence "if the Redis server is stopped".

### Final result (run no. 2)

| Indicator | `qwen/qwen3-4b-2507` | `qwen2.5-7b-instruct` |
|---|---|---|
| Cases passed (all checks) | 15/18 | 18/18 |
| Checks passed | 105/108 | 108/108 |
| p50 / max latency per request | 5.96 s / 11.52 s | 9.04 s / 15.65 s |
| LLM calls per request (avg.) | 4.5 | 4.22 |
| Tokens in / out per request (avg.) | 2774 / 347 | 2602 / 391 |
| Generation throughput (tokens out / LLM s) | 57.9 | 45.3 |
| Requests / min (sequential) | 9.9 | 6.9 |
| Local cost | €0 (electricity not counted) | €0 |
| Estimated cost with OpenAI gpt-4o-mini API, /1000 req. | ~$0.62 | ~$0.62 |
| Estimated cost with Anthropic Claude Haiku 4.5 API, /1000 req. | ~$4.51 | ~$4.56 |

| Case | SLM (passes · p50 latency) | 7B |
|---|---|---|
| C1 PostgreSQL stopped | 3/3 · 9.6 s | 3/3 · 13.7 s |
| C2 PostgreSQL running | 3/3 · 9.0 s | 3/3 · 9.0 s |
| C3 Documentation question | 3/3 · 5.7 s | 3/3 · 9.1 s |
| C4 Data question (SQL) | 3/3 · 3.5 s | 3/3 · 7.7 s |
| C5 Out-of-scope request | 3/3 · 1.5 s | 3/3 · 2.1 s |
| C6 Tool failure | **0/3** · 6.6 s | 3/3 · 11.2 s |

**Remaining failures (SLM, C6)**: the SLM **invents source identifiers**
(`unreachable.md#Checks`, `[service_status#Service status]`) when the status tool fails. The
post-processing flags them in the trace but does not fix them, and this is intentional.

**Reading limits**:
- keyword-based checks are coarse (D-21);
- temperature 0, so the 3 runs are very close: the measured variance is mostly that of
  latency;
- on review, the 7B sometimes presents the sheet's symptoms as "observed logs"
  (C6), which the checks do not detect.

**Cloud costs** are **estimates**: measured tokens × indicative public prices
(`REFERENCE_PRICES_USD_PER_MTOK`, to be re-checked), no calls and no account.

Cold start of a session (RAG + model loading by LM Studio): 20–26 s.

## J5 — Serving throughput (2026-10-02)

Command: `hello-support throughput --models slm large --concurrency 1 4 --requests 8`.
The same generation request (~160 tokens max, temperature 0.7) is sent 8 times, one at a
time and then 4 in parallel, to the LM Studio server (RTX 2070 Super 8 GB).

| Model | Concurrency | Requests | Duration | Tokens out/s (aggregate) | Req/min | p50 / max latency |
|---|---|---|---|---|---|---|
| `qwen/qwen3-4b-2507` | 1 | 8 | 8.61 s | 106.6 | 55.7 | 1.06 s / 1.18 s |
| `qwen/qwen3-4b-2507` | 4 | 8 | 5.34 s | 172.6 | 90.0 | 1.78 s / 4.17 s |
| `qwen2.5-7b-instruct` | 1 | 8 | 14.13 s | 71.1 | 34.0 | 1.62 s / 2.24 s |
| `qwen2.5-7b-instruct` | 4 | 8 | 8.26 s | 127.6 | 58.1 | 3.69 s / 6.29 s |

Reading:
- **Model size**: at concurrency 1, the 4B generates ~1.5× faster than the 7B (107 vs.
  71 tokens/s).
- **Concurrency**: with 4 simultaneous requests, aggregate throughput is multiplied by **1.6 (4B) to
  1.8 (7B)**, but individual latency **doubles**. This is the throughput / latency trade-off of a
  server that handles several requests in parallel.
- **Gap with the benchmark**: generation throughput is lower there (58 and 45 tokens/s) because
  LLM time includes processing prompts of ~600–900 tokens (RAG context, tool
  results) and several short calls.

This is not a load test: a single machine, LM Studio (a desktop tool), 8 requests. A real
throughput test would use vLLM (continuous batching) and a gradual ramp-up
("going further").

## v1.10.0 — `out_of_scope` and `vague` skip the documentalist (2026-10-04)

Change measured **before** (tag `pre-1.10.0`, v1.9.3) and **after** (v1.10.0), under the same
conditions: a single model loaded at a time in LM Studio (unloaded between series), warm measurements.
Decision: D-30.

### Targeted gain (5 runs per case and per model)

Two questions: `out_of_scope` = C5 "Mon Kafka est lent, que faire ?" ("My Kafka is slow, what should I do?"), `vague` = "ça marche pas, que faire ?" ("it doesn't work, what should I do?").

| Model | Category | Pass rate | p50 latency | LLM calls | Tokens in (avg.) | Tokens out (avg.) |
|---|---|---|---|---|---|---|
| Qwen3-4B | out_of_scope | 5/5 → 5/5 | 1.26 → **0.82 s (−35%)** | 3 → 2 | 1,139 → 724 | 79 → 63 |
| Qwen3-4B | vague | 5/5 → 5/5 | 3.07 → **0.44 s (−86%)** | 4 → 2 | 2,150 → 710 | 122 → 25 |
| Qwen2.5-7B | out_of_scope | 5/5 → 5/5 | 1.96 → 2.02 s (+3%) | 3 → 2 | 1,136 → 724 | 110 → 104 |
| Qwen2.5-7B | vague | 5/5 → 5/5 | 3.87 → **1.74 s (−55%)** | 4 → 2 | 1,968 → 710 | 147 → 83 |

Reading:
- **`vague`**: the old documentalist **searched** ("it is not working" → 3 off-topic passages) and then
  wrote a brief, i.e. 2 LLM calls and one tool call. They are removed, hence −55 to −86%.
- **`out_of_scope`**: the old documentalist already answered **without searching** (1 short call). The gain
  is real with the 4B (−35%), nil with the 7B, whose technician answer (~100 tokens) dominates the
  duration. In all cases, input tokens drop by 36 to 67%.

### Full benchmark (6 cases × 3, per model)

| | 4B before | 4B after | 7B before | 7B after |
|---|---|---|---|---|
| Cases passed | 15/18 | 15/18 | 18/18 | 17/18 |
| C1 · C2 · C3 · C4 · C5 · C6 | 3·3·3·3·3·0 | 3·3·2·3·3·1 | 3·3·3·3·3·3 | 3·3·3·3·3·2 |
| C5 p50 latency | 1.43 s | 0.92 s | 2.06 s | 1.72 s |
| p50 latency (all requests) | 9.5 s ⚠ | 4.4 s | 8.2 s | 7.8 s |

**Deviations on unchanged paths, verified as pre-existing** (re-measured on the old and the new code):

| Case (path) | Model | Failing check | Old code | New code |
|---|---|---|---|---|
| C6 (`malfunction`) | 7B | "says the check failed": answer "statut indéterminé… limitation de l'outil" ("status undetermined… tool limitation") | 8/10 (+ 5/5) | 8/10 (+ 4/5) |
| C3 (`documentation`) | 4B | exact citations / in French | 5/8 | 7/8 |

No regression attributable to the change. These two cases show **wording instability**
in the models despite temperature 0 (LM Studio parallel batches), combined with coarse
keyword-based checks (D-21).

⚠ **Machine conditions**: LM Studio now loads models with a default context of 25,600
tokens and 4 parallel slots. The `-c` option of `lms load` is ignored, and the LM Studio
configuration is outside the project. VRAM then rises to ~7 GB and, together with the MCP server's
embedding models, the GPU saturates at times: LLM calls of 50–100 s in the "4B before" series, then
a second series aborted at 590 s. The **overall 4B latencies are therefore not comparable** between the two
series. The targeted comparisons above, with their tight gaps, and the pass rates remain valid.

Reports: before [`bench-20261004-120325`](bench/bench-20261004-120325.md) (4B),
[`bench-20261004-121113`](bench/bench-20261004-121113.md) (7B); after
[`bench-20261004-121546`](bench/bench-20261004-121546.md) (4B), [`bench-20261004-122103`](bench/bench-20261004-122103.md)
(7B); C6 controls [`122349`](bench/bench-20261004-122349.md) (new ×5), [`122531`](bench/bench-20261004-122531.md)
(old ×5), [`122757`](bench/bench-20261004-122757.md) (old ×10), [`124927`](bench/bench-20261004-124927.md) (new ×10); C3 (4B) controls [`125119`](bench/bench-20261004-125119.md) (new ×8), [`125223`](bench/bench-20261004-125223.md) (old ×8).

### Stabilized LM Studio settings (2026-10-04, after the v1.10.0 measurement)

The GPU saturation reported above came from LM Studio's **context auto-adjustment**:
25,600 tokens × 4 parallel slots, ~7 GB of VRAM for the 4B. A per-model configuration
disables auto-adjustment and pins the **context to 8,192** and **parallelism to 1**. It is
applied to manual loads as well as on-demand (JIT) loads. VRAM with the model
loaded and the MCP server running: 4B ~4.6 GB, 7B ~5.9 GB.

Quick check after tuning, code v1.10.0:

| Series | Pass rate | p50 / max latency | Comparison |
|---|---|---|---|
| 4B, 6 cases × 3 ([`132504`](bench/bench-20261004-132504.md)) | 16/18 | **4.38 s / 7.6 s** | saturated "4B before": 9.5 s / **100.9 s** |
| 7B, C1 + C3 × 3 ([`132635`](bench/bench-20261004-132635.md)) | 6/6 | 8.8 s / 11.2 s | C1 and C3 were the cases with 50–100 s spikes |

Latencies are stable again. With a single parallel slot, the throughput measurement at
concurrency 4 (section J5, done with 4 slots) would no longer be reproduced as is: the
requests would be served one after the other.

### v1.11.0 non-regression (web demo)

Quick benchmark after adding the web demo (`hello-support bench --models slm large --runs 1`, stabilized LM Studio settings): **6/6 for both models**, p50 latency 4.9 s (4B) and 7.3 s (7B). Report: [`145500`](bench/bench-20261004-145500.md).
