Reviewer: Omar | Assistant: DeepSeek (model/mode: TODO) | Commit reviewed: 9db3378 | Date: 13 Oct 2026

Note: line numbers in this review are approximate; spot-checks found several pointing to the wrong lines.

I've read the code for all four MVPs at commit `9db3378`. Here is the review.

---

## 1. What each MVP does best

### Marc (`marc-uniagent-solver/`)

1. **Deterministic-first architecture with a curated rule base.** Every rule has a YAML entry with a `query` and one or more `sources` citing corpus `doc_id`s (`solver/knowledge/rules_procurement.yaml:5-11`, `rules_business_trip.yaml`, `rules_expense.yaml`). This directly satisfies the "every rule must have a cited source" generalisation requirement, unlike any other MVP.
2. **Hard-fail override and checks-alone fallback.** A deterministic `FAIL` rejects regardless of the model (`solver/decide.py:3-4`, `solver/decide.py:73-80`). If the model is unavailable, `fallback_decision()` produces a decision from the checks alone, so every case still gets a prediction.
3. **Parallel document extraction with per-case timeouts.** `extract_facts()` uses `ThreadPoolExecutor` (`solver/pipeline.py:32-42`), and `Settings` caps each case at 240 s and the run at 3.75 h (`solver/config.py:6-8`). Ablation flags (`--no-checks`, `--no-retrieval`, `--self-consistency`) are built in (`predict.py:14-20`).

### Rajesh (`rajesh-uniagent-solver/`)

1. **Cleanest separation of concerns.** The LLM only answers yes/no questions (`llm_label.py:22-28`); all decision logic stays in `predict.py` (`predict.py:3-12`). This is the simplest to audit and explain.
2. **Minimal dependencies and Dockerfile.** `requirements.txt` has only `pypdf==5.1.0` and `openai==1.60.0`; the Dockerfile is six lines (`Dockerfile:1-6`). This is by far the lightest image.
3. **Explicit fallback for reasoning_effort.** `llm_label.py:38-42` catches `TypeError` and retries with `extra_body`, so the code works with both older and newer `openai` clients.

### Gareth (`gareth-uniagent-solver/agent/`)

1. **Schema-constrained output with citation identity validation.** `decision_response_format()` restricts `source_id` to a fixed enum of sources actually extracted from the case (`predict_fast.py:16-24`), and forces `minLength` on `begruendung` and `relevance`. This is the strongest guard against hallucinated citations of any MVP.
2. **Expense-specific `duty_evidence` field.** For expense cases, the schema requires the model to select a verified excerpt proving institutional/work use (`predict_fast.py:26-28`, `RUN.md:41-43`). No other MVP enforces this.
3. **Ordered predictions despite concurrency.** `write_ordered_predictions()` re-sorts results by `antrag` ID (`predict_fast.py:84-86`), so the evaluator sees cases in the expected order.

### Omar (`omar-uniagent-solver/`)

1. **Simplest end-to-end pipeline.** One file walks the case, extracts text, retrieves passages, makes one LLM call, writes the trace (`predict.py:48-97`). Easy to reason about and modify.
2. **Robust JSON fallback chain.** `extract_json_object()` tries four strategies in order: direct parse, markdown-fence strip, brace slice, and `json_repair` (`llm.py:31-42`). This is the most defensive parser of the four.
3. **Structured output via `response_format`.** The `DECISION_SCHEMA` is passed to the API (`llm.py:5-12`), so on endpoints that support it (vLLM, OpenRouter) the model cannot return prose.

---

## 2. Main risks

### Marc

- **Rule thresholds may not be sourced.** `DOMESTIC_HOTEL_LIMIT = 80.0` (`solver/checks/business_trip.py:6`), `DIRECT_AWARD_LIMIT = 1000.0` and `REQUIRED_OFFERS = 3` (`solver/checks/procurement.py:7`) are hardcoded. The YAML rules cite sources for the *rule text*, but the numeric thresholds are in Python, not YAML, so a test case that changes the threshold would break silently.
- **`bm25s` is an extra dependency.** `solver/retrieval.py:5` imports `bm25s`, which is not the `rank-bm25` used by Omar. It works, but adds build weight.
- **`pdftotext` requires `poppler-utils`.** Installed in the Dockerfile (`Dockerfile:3-4`), but if the base image changes, this is a silent failure point.
- **Complexity.** 20+ files across `solver/checks/`, `solver/knowledge/`, `solver/extract.py`, `solver/classify.py`, etc. The Dockerfile runs `pytest` at build time (`Dockerfile:8`), which is good, but any test failure blocks the build.

### Rajesh

- **Six LLM calls per case.** `decide_trip` calls `llm_check` for L1 (`predict.py:75-80`), `decide_expense` calls L2 and L3 (`predict.py:102-115`), and `decide_procurement` calls L4-L6. This is the most token-expensive design of the four.
- **No corpus retrieval.** The LLM labelers rely entirely on the model's internal knowledge of German administrative rules. There is no BM25 look-up of the corpora. On hidden cases with unfamiliar rules, this is the weakest design.
- **Deterministic rules are spot-check-specific.** `PROFORMA_PATTERN` (`predict.py:87`), `UNIVERSITY_KEYWORDS` (`predict.py:84-86`), and `FRAMEWORK_EXEMPTION_HINT` (`predict.py:118-120`) are regexes tuned to the public cases. They may misfire on new wording.
- **`openai==1.60.0` may still hit the `proxies` bug.** We saw `openai==1.54.0` fail with `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'` in this session. 1.60.0 is later, but not verified.

### Gareth

- **Heavy external base image.** `FROM ghcr.io/uniagent-webis-de/uniagent-pyterrier-baseline:dev-0.0.1` (`Dockerfile:3`). If that image is not available at TIRA build time, the build fails. TIRA may not have access to `ghcr.io`.
- **`smolagents` framework.** `case_tools.py:5` and `event_logging.py:5` import `smolagents.Tool`. This is an extra framework that must be installed and version-pinned.
- **PyTerrier is Java-based.** `retrieval_tools.py:4` imports `pyterrier`, which requires a JVM. This adds startup time and memory pressure.
- **Local development used a different model.** `RUN.md:13-15` says the local runs used Qwen2.5 7B Q4_K_M, not `gpt-oss-20b`. The structured-output modes differ (`llamacpp` vs `openai`), so the tested path is not the TIRA path.
- **No TIRA dry run yet.** `READ-ME-FIRST.md:14-15` explicitly says "Pending: a complete run of the final configuration, official trace evaluation, TIRA dry-run".

### Omar

- **One LLM call decides everything.** There is no deterministic check that can override a wrong model decision. If the model hallucinates "angenommen" on a case with a missing form, the case is accepted.
- **22-second sleep between cases.** `predict.py:49` sleeps 22 s before each case to avoid Groq rate limits. On 50 hidden cases that is **18 minutes of pure sleep**, which eats into the 4-hour budget.
- **Prompt caps may truncate evidence.** `MAX_CASE_CHARS_FOR_PROMPT = 6000` (`predict.py:13`). A case with multiple long PDFs could lose the document that contains the decisive fact.
- **Procurement accuracy 0.50.** The README admits this (`README.md:10-11`), and the cause is not diagnosed.
- **No `response_format` fallback for endpoints that ignore it.** If the TIRA vLLM version does not support `json_schema`, the model returns prose and the parser must save it. The fallback chain helps but is not guaranteed.

---

## 3. Parts worth integrating into another MVP

| Source | Component | Where | Why |
|---|---|---|---|
| **Marc** | Curated rules YAML with cited sources | `solver/knowledge/*.yaml` | Every rule has a `doc_id`. No other MVP does this. |
| **Marc** | Hard-fail override | `solver/decide.py:3-4`, `73-80` | Deterministic `FAIL` rejects regardless of model. |
| **Marc** | Checks-alone fallback | `solver/decide.py:73-80` | Every case gets a decision even if the model is down. |
| **Marc** | Ablation flags | `predict.py:14-20` | Enables systematic measurement. |
| **Gareth** | Citation identity validation | `predict_fast.py:16-24` | Prevents hallucinated `source_id`s. |
| **Gareth** | Expense `duty_evidence` field | `predict_fast.py:26-28` | Forces proof of institutional use. |
| **Gareth** | Ordered predictions | `predict_fast.py:84-86` | Evaluator-safe ordering. |
| **Omar** | 4-level JSON fallback | `llm.py:31-42` | Survives prose responses. |
| **Omar** | `response_format` schema | `llm.py:5-12` | Constrains output on supported endpoints. |
| **Rajesh** | Try/except for `reasoning_effort` | `llm_label.py:38-42` | Works with old and new `openai` clients. |
| **Rajesh** | Minimal Dockerfile | `Dockerfile:1-6` | Fewest moving parts. |

---

## 4. Scoring table (1–5)

| MVP | Generalisation | Model robustness | Efficiency | Trace quality | TIRA readiness | Ease of extension |
|---|---:|---:|---:|---:|---:|---:|
| **Marc** | **5** — curated rules with sources | **4** — fallback + hard-fail override | **3** — many LLM calls for extraction + decision | **5** — full contract + run-stats | **4** — Dockerfile runs tests; `bm25s` extra dep | **4** — modular but complex |
| **Rajesh** | **2** — regexes tuned to spot-check | **3** — try/except for reasoning_effort | **2** — six LLM calls per case | **3** — contract followed; no token usage in model_call | **3** — simple Docker; no structured output | **3** — simple but hard to extend |
| **Gareth** | **4** — schema + citation identity | **3** — structured output; heavy deps | **3** — one call + repair; pyterrier cost | **4** — contract + source identity | **2** — external base image + smolagents + pyterrier | **3** — framework-bound |
| **Omar** | **3** — retrieval + structured output | **4** — 4-level JSON fallback | **2** — 22 s sleep; one call | **4** — contract + token usage + settings | **4** — minimal deps; no test at build | **4** — easy to read; hard to add checks |

**One-line reasons:**
- **Marc generalisation 5:** `solver/knowledge/*.yaml` cite corpus `doc_id`s for every rule.
- **Marc model robustness 4:** `fallback_decision()` and hard-fail override mean no case is skipped.
- **Marc efficiency 3:** extraction + decision calls multiply token cost.
- **Marc trace quality 5:** `run-trace.jsonl.log.gz` + `run-stats.json` with per-case seconds and tokens.
- **Marc TIRA readiness 4:** Dockerfile is self-contained but `bm25s` is an extra wheel.
- **Marc ease of extension 4:** adding a check is one file in `solver/checks/`, but the pipeline is long.
- **Rajesh generalisation 2:** `PROFORMA_PATTERN`, `UNIVERSITY_KEYWORDS`, `FRAMEWORK_EXEMPTION_HINT` are regexes tuned to the public cases.
- **Rajesh model robustness 3:** try/except for reasoning_effort is good; but no structured output means prose is possible.
- **Rajesh efficiency 2:** up to six LLM calls per case.
- **Rajesh trace quality 3:** contract followed, but `model_call` output lacks token usage details.
- **Rajesh TIRA readiness 3:** Dockerfile is trivial, but `openai==1.60.0` is not verified against the `proxies` bug.
- **Rajesh ease of extension 3:** adding a labeler means a new `llm_check` call; adding a rule means a new regex.
- **Gareth generalisation 4:** schema constrains `source_id` to actual case sources; but no rule YAML with citations.
- **Gareth model robustness 3:** structured output is strong, but the local test model was Qwen2.5 7B, not `gpt-oss-20b`.
- **Gareth efficiency 3:** one decision call plus retrieval; PyTerrier adds startup cost.
- **Gareth trace quality 4:** contract followed; source identity is logged.
- **Gareth TIRA readiness 2:** external base image `ghcr.io/...` may not be reachable at TIRA build time; `smolagents` and `pyterrier` are heavy.
- **Gareth ease of extension 3:** adding a check means editing `case_tools.py`; the smolagents wrapper adds indirection.
- **Omar generalisation 3:** retrieval grounds decisions in corpora, but no curated rule citations.
- **Omar model robustness 4:** 4-level JSON fallback; `extra_body` for reasoning_effort.
- **Omar efficiency 2:** 22 s sleep per case is pure waste on TIRA.
- **Omar trace quality 4:** contract followed, token usage and settings logged.
- **Omar TIRA readiness 4:** minimal deps (`pypdf`, `rank-bm25`, `openai`, `httpx`, `json-repair`).
- **Omar ease of extension 4:** flat file structure; adding a deterministic check is straightforward.

---

## 5. Strongest base and integration priority

### Strongest base: **Marc's `marc-uniagent-solver/`**

It already has the two hardest pieces right: a curated rule base with cited sources, and a hard-fail override with a checks-alone fallback. No other MVP has both. Gareth's schema validation and Omar's JSON fallback are improvements *on top of* Marc's pipeline, not replacements for it.

### Parts to integrate, in priority order

| Priority | Part | Source | Effort | Why first |
|---|---|---:|---|---|
| 1 | Citation identity validation (`source_id` enum) | Gareth `predict_fast.py:16-24` | **S** | Marc's `parse_decision()` accepts any `belege`; this closes the hallucinated-source gap. |
| 2 | Expense `duty_evidence` field | Gareth `predict_fast.py:26-28` | **S** | Marc's expense checks do not require proof of institutional use. |
| 3 | 4-level JSON fallback (`json_repair`) | Omar `llm.py:31-42` | **S** | Marc's `extract_json_object` has only two strategies; add the last two. |
| 4 | Try/except for `reasoning_effort` | Rajesh `llm_label.py:38-42` | **S** | Marc's `llm.py` passes `reasoning_effort` directly; the same `TypeError` we saw could recur. |
| 5 | Remove the 22 s sleep (Marc has no sleep) | Omar `predict.py:49` | **S** | Not an integration; a confirmation that Marc's design already avoids this waste. |
| 6 | Ordered predictions writer | Gareth `predict_fast.py:84-86` | **S** | Marc writes predictions sequentially, so this is only relevant if concurrency is added. |
| 7 | Minimal Docker base (`python:3.12-slim` + `poppler-utils`) | Marc `Dockerfile:3-4` | **S** | Already in place; verify `bm25s` builds cleanly on TIRA. |
| 8 | Ablation flags | Marc `predict.py:14-20` | **S** | Already in place; run them to measure each component's contribution. |

**Total effort: all S.** None of these require restructuring Marc's pipeline.

---

## 6. What I couldn't check

- **I did not run any of the code.** All observations are from reading the source at commit `9db3378`. I did not build any Docker image, run any case, or execute any evaluation.
- **I could not verify TIRA build behaviour.** Whether `bm25s` (Marc), `smolagents` (Gareth), or `openai==1.60.0` (Rajesh) install cleanly in the TIRA sandbox is unverified.
- **I could not verify the `ghcr.io/uniagent-webis-de/uniagent-pyterrier-baseline:dev-0.0.1` image is reachable** from TIRA. Gareth's Dockerfile depends on it.
- **I could not verify the `reasoning_effort` pass-through on the TIRA vLLM version.** Marc and Omar both send it; whether the TIRA vLLM accepts it is unknown.
- **I could not verify the accuracy claims** in any README. Only the code was read.
- **I did not check the `team-uniagent-solver/` folder** or the `evaluation/` folder, which the repo README lists. The request specified four MVPs, and those are the four I read.
- **I did not check whether Marc's YAML `doc_id`s actually exist** in the corpora at runtime. That would require running the retrieval.
- **I did not check the `tests/` directories** for any MVP except to note that Marc's Dockerfile runs them (`Dockerfile:8`).