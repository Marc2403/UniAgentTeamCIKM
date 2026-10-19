# Results – Task 2 spot-checks (21 cases)

Model: `gpt-oss-20b` via OpenRouter (`openai/gpt-oss-20b`); provider-default reasoning for open decisions,
`reasoning_effort=low` for extraction and for writing the reason of a hard rejection. Docker, 4 CPUs, no
LLM cache. Accuracy from `scripts/evaluate_local.py`; every run's traces pass `scripts/validate_trace.py`.
Seconds and tokens per case from `run-stats.json` (index build, ~16 s per dataset, not included).

**Caveat:** checks and rule texts were written while looking at these 21 cases and their gold reasons
(no case IDs, names or amounts in the code). These numbers are training accuracy, not an estimate for the
~50 hidden test cases. Runs vary between repetitions (OpenRouter routes to different providers): the same
code scored 20/21 in `final-v4` before the last prompt fix.

## v2 with synthetic cases (`a017cb2`)

Changes, gate runs and reverted steps: [`../evaluation/IMPROVEMENT.md`](../evaluation/IMPROVEMENT.md). gpt-oss-20b, two
runs per configuration, accuracy summed over both runs; (?) cases excluded. All numbers are training accuracy on our
own labels (S, A, B, C were used for development); only the holdout H was not looked at before scoring it once.

| Set | `13618cf` (TIRA `several-step`) | `a017cb2` |
|---|---|---|
| S spot-checks (21) | 42/42 | 42/42 |
| A synthetic, Marc (32) | 47/64 | 56/64 |
| B synthetic, Rajesh (15) | 29/30 | 30/30 |
| C coverage (83) | 121/166 | 138/166 |
| H holdout (20) | 20/40 | 30/40 |
| S with `qwen/qwen-2.5-7b-instruct` (2 runs) | 19/21, 18/21 | 19/21, 18/21 |
| S / A with `openai/gpt-oss-120b` (1 run) | – | 21/21, 27/32 |

## Main comparison

| System | Business trip | Procurement | Expense | Total | s/case | tokens/case |
|---|---|---|---|---|---|---|
| `solving-always-rejected` (computed) | 0.60 (3/5) | 0.50 (4/8) | 0.50 (4/8) | 0.52 (11/21) | 0 | 0 |
| `solving-smolagents-with-retrieval` (organisers, `runs/baseline-smolagents-retrieval`) | 0.80 (4/5) | 0.50 (4/8) | 0.88 (7/8) | 0.71 (15/21) | 214–467 | n/a |
| this system v1 (`runs/full-v1`) | 0.60 (3/5) | 1.00 (8/8) | 0.88 (7/8) | 0.86 (18/21) | 38.7 | 6,856 |
| **this system, final** (`runs/final-v5`) | **1.00 (5/5)** | **1.00 (8/8)** | **1.00 (8/8)** | **1.00 (21/21)** | **23.5** (max 49) | **6,577** |

Fixes after v1, all general rather than case-specific:
- The decision prompt states that a not-yet-approved application ("Genehmigt von: ---") is the normal state,
  and that invoices are only required at the later settlement, not with the application.
- The reimbursement rule names the service reference as the criterion instead of "only small urgent purchases".
- The decision prompt states that figures a check confirmed with `pass` are not contradictions (the model had
  read a position number as a quantity).
- Every LLM call has a wall-clock deadline: the HTTP read timeout never fired while OpenRouter kept the
  connection alive, and one decision took 311 s (`runs/r3-no-retrieval`).

## Which check decides (final)

| Case | Result | Decided by |
|---|---|---|
| dienstreiseantrag-01 | abgelehnt | TRIP_SUBMITTED_BEFORE_START |
| dienstreiseantrag-03 | abgelehnt | TRIP_DATES_CONSISTENT, TRIP_COSTS_COMPLETE, TRIP_FOREIGN_TRAVEL |
| dienstreiseantrag-05 | abgelehnt | TRIP_THIRD_PARTY_FUNDING |
| auslagenerstattung-03 | abgelehnt | EXP_SERVICE_REFERENCE |
| auslagenerstattung-04 | abgelehnt | EXP_REAL_INVOICE |
| auslagenerstattung-06 | abgelehnt | EXP_DUPLICATE |
| auslagenerstattung-07 | abgelehnt | EXP_HOSPITALITY |
| beschaffungsantrag-03 | abgelehnt | PROC_FRAMEWORK_CONTRACT |
| beschaffungsantrag-04 | abgelehnt | PROC_TOTAL_MATCHES_ITEMS |
| beschaffungsantrag-06 | abgelehnt | PROC_COMPARISON_OFFERS |
| beschaffungsantrag-07 | abgelehnt | PROC_AWARD_MATCHES_OFFERS, PROC_CHEAPEST_OFFER |
| the 10 accepted cases | angenommen | model, no failed check |

## Ablations (candidates for TIRA runs R1–R5)

Run with the prompt state before the last two fixes (`runs/r*`); R2 is the same configuration as the final run.

| Run | Configuration | Business trip | Procurement | Expense | Total | s/case | tokens/case |
|---|---|---|---|---|---|---|---|
| R1 | full, `--self-consistency 3` | 1.00 | 1.00 | 1.00 | 1.00 | 37.5 | 8,441 |
| R2 | full | 1.00 | 1.00 | 1.00 | 1.00 | 22.8 | 6,654 |
| R3 | `--no-retrieval` | 1.00 | 1.00 | 1.00 | 1.00 | 49.7* | 6,476 |
| R4 | `--no-checks` (no extraction, model + curated rules) | 1.00 | 1.00 | 0.88 | 0.95 | 34.6 | 3,619 |
| R5 | full, `qwen/qwen-2.5-7b-instruct` | 0.60 | 0.88 | 1.00 | 0.86 | 6.0 | 7,415 |

\* includes the 311 s call that led to the deadline fix.

Reading: on the spot-checks, retrieval and self-consistency add cost but no accuracy; the curated rules and
prompt carry most of the gain over the baseline (R4); the checks add the remaining case and auditable reasons.
With Qwen2.5-7B, business trips 02/04 are rejected with the reason that application and travel dates are
missing, and beschaffungsantrag-07 is accepted; the traces in `runs/r5-qwen` have not been analysed further.

## Robustness

- Offline (`docker run --network none`, expense spot-check): no downloads at runtime; every case gets one
  valid line (fallback from the checks), trace valid, 48 s for 8 cases (`runs/offline`).
- 61 unit tests, run in `docker build`: parsers, every check, broken PDF, unreachable LLM, invalid JSON,
  unknown case prefix, case directory without PDFs, LLM call abandoned at its deadline.
- Index build over the three corpora (≈56k documents, 223 MB text): 16–24 s.
- Cost of all runs in this session incl. the baseline: about 0.15 USD on OpenRouter.
