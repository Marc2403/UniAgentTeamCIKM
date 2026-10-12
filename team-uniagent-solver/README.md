# Team solver – UniAgent 2026, Task 2 (Solving)

Decides business-trip applications (`dienstreiseantrag-*`), expense reimbursements (`auslagenerstattung-*`)
and procurement requests (`beschaffungsantrag-*`) as `angenommen` / `abgelehnt`. Principle: **the LLM reads,
Python checks, the LLM judges what Python cannot check.** Built from Marc's MVP as base plus the parts of the
other MVPs that survived one-at-a-time ablation. Base choice: [`../evaluation/EVALUATION.md`](../evaluation/EVALUATION.md);
every kept and dropped component with its numbers: [`ABLATIONS.md`](ABLATIONS.md).

## Architecture

`predict.py` discovers the cases and corpora, builds the BM25 index once, then runs each case in a watchdog
thread (`solver/pipeline.py`):

1. **Read** every PDF with `pdftotext -raw`, fallback `pdfplumber`, only while the case deadline allows. A case
   folder without readable text is rejected deterministically (incomplete application, no LLM call).
2. **Classify** each document by file name, corrected by content keywords (pro-forma, credit note, grant).
3. **Extract** facts per document type into Pydantic schemas with the LLM (`reasoning_effort=low`, in parallel).
   Amounts the document does not print are discarded; malformed JSON is repaired (`json-repair`); trip dates the
   model missed are filled from the form's labelled fields.
4. **Check** deterministic rules per case type (`solver/checks/`), each `pass | fail | unclear`, `hard` or soft,
   with a detail text and the source documents. Hard checks are limited to facts Python can verify (dates,
   arithmetic, offer counts, amounts against documents, product groups named in the rules).
5. **Look up** the wording of the curated rules (`solver/knowledge/*.yaml`, every rule citing the corpus `doc_id`
   it is taken from) and BM25 passages for failed or unclear findings.
6. **Decide**: a hard `fail` rejects (the model only writes the reason); otherwise the model decides on rules,
   findings, facts and documents (`reasoning_effort=low`). A failed or timed-out decision call is retried once
   within the case budget; if the model stays unusable, the checks decide (fallback).

Every case logs `input`, `tool_call` (PDF reads, index, retrieval), `model_call` (prompt, response, token usage),
one `observation` per rule finding (rule, status, detail, sources) and ends with exactly one `decision` event
(`decision`, `answer`, `evidence`, method, failed rules), per the
[event-logging contract](../../uniagent-code/cikm26/event-logging-contract/README.md).

Time limits (TIRA: 5 min per case, 4 h per run): each LLM call is abandoned after 120 s, each case has a 240 s
deadline (or its fair share of the 3.75 h run budget), and a watchdog gives up on a case 30 s after its deadline
with a fallback decision. Institutions under another state's law (the dataset READMEs name Sallstedt) get no
Kassel-specific hard checks.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` | required | OpenAI-compatible endpoint; the run stops at start if one is missing |
| `--reasoning-effort` or `OPENAI_REASONING_EFFORT` | `low` | reasoning effort of the decision call, flag first (extraction always uses `low`) |
| `SOLVER_CACHE_DIR` | unset | caches LLM answers on disk; local development only |
| `--no-checks` | off | ablation: no extraction and checks, model decides on curated rules |
| `--no-retrieval` | off | ablation: no corpora, no rule passages |
| `--no-hard-fail-override` | off | let the model overrule hard check failures |
| `--self-consistency N` | 1 | N decision samples when a check stays unclear |
| `--case-timeout S` | 240 | per-case deadline in seconds |

## Build and run locally (Docker)

```bash
docker build --tag team-solver .          # runs the 64 tests (mock LLM, no data needed)
export OPENAI_BASE_URL=https://openrouter.ai/api/v1 OPENAI_API_KEY=... OPENAI_MODEL=openai/gpt-oss-20b
../evaluation/run-mvp.sh team team-solver ../evaluation/runs/gpt-oss-20b bridge -- python3 /app/predict.py
TIRA_CLI=tira-cli ../evaluation/tira-evaluate.sh ../evaluation/runs/gpt-oss-20b/team
```

`run-mvp.sh` runs the three spot-check datasets from `../../uniagent-code/cikm26/datasets` with 4 CPUs and
40 GB and scores them with the official evaluator image; `tira-evaluate.sh` scores them with
`tira-cli evaluate`. To check that nothing but the LLM endpoint is reached, run on an internal Docker network
whose only egress is an allowlist proxy (how: [`ABLATIONS.md`](ABLATIONS.md#setup)) and pass
`uniagent-internal` instead of `bridge` with `HTTPS_PROXY` set. Edge cases with a misbehaving LLM:
`../evaluation/robustness/run.sh team-solver <out-dir>`.

## Submit to TIRA

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset business-trip-spot-check-20260907-training \
  --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
  --command '/app/predict.py --input $inputDataset --output $outputDir' \
  --dry-run
```

Remove `--dry-run` to submit; the procurement and expense spot-checks are
`task-2-procurement-spot-check-20260928-training` and `task-2-expense-reimbursement-spot-check-20260928-training`.
Variants are selected by `OPENAI_MODEL` and by appending flags to `--command`. Recommended submissions:
[`ABLATIONS.md`](ABLATIONS.md#recommended-tira-submissions).

## Component attribution

| Part | From | Notes |
|---|---|---|
| Pipeline, PDF reading, classification, extraction schemas with printed-amount verification | Marc | unchanged |
| Deterministic checks and curated rules with corpus `doc_id` sources | Marc | two citations corrected; third-party funding made a soft finding (team) |
| BM25 retrieval (`bm25s`), hard-fail override, LLM call deadline, fallback decision, tests | Marc | requests now in daemon threads (team) |
| `json-repair` as last-resort JSON parser | Omar | |
| Business-trip dates from labelled form fields (gap filling only) | Rajesh | with a fix to `TRIP_COSTS_COMPLETE` it exposed |
| Policy coverage: meals/evening events, A1 lead time, six-month exclusion period | Gareth | re-worded after and citing the corpus |
| Per-case watchdog, deadline-aware reading, empty case folders, decision retry, per-finding log events, contract fields on decision events, `reasoning_effort=low` default | Team | compliance and robustness work |

Left out, with the measurements in [`ABLATIONS.md`](ABLATIONS.md): JSON mode (`response_format`, Omar/Gareth:
gpt-oss-20b answered with empty JSON), reason-first decision JSON (Gareth: no gain), the LLM item labeler
(Rajesh L3/L4: one more call per case, no gain), source-faithful rewording of two rules (lost a case), dropping
retrieval (lost a case), Rajesh's regex rules and labelers L1/L2/L5/L6 (duplicates of Marc's checks; L2 caused
Rajesh's only miss), Gareth's retrieval fusion and pyterrier stack (retrieval adds no measurable accuracy here;
2.7 GB image), Gareth's duty-evidence check (duplicate of `EXP_SERVICE_REFERENCE`), Omar's single-call design and
per-case sleep.
