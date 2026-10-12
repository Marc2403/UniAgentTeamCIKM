# MVP comparison – Task 2 (Solving), 12 October 2026

Compact evaluation of the four MVPs as committed on `main` (`9db3378`): a compliance check against the
official requirements and one spot-check run per MVP under identical LLM settings. It decides which MVP
becomes the base of `team-uniagent-solver/` and which components are candidates for it.

## Setup

- Data: the three Task 2 spot-check datasets from `uniagent-code` (`aaba38d`): business trip 5, procurement 8,
  expense 8 cases (21 total).
- LLM: `openai/gpt-oss-20b` via OpenRouter (`OPENAI_BASE_URL=https://openrouter.ai/api/v1`),
  `OPENAI_REASONING_EFFORT` unset for every MVP; temperature and token limits are each MVP's own.
- Execution: `evaluation/run-mvp.sh`, Docker with `--cpus 4 --memory 40g`, the four MVPs in parallel. Images built
  from the committed sources with LF line endings (`git -c core.autocrlf=false archive`), as TIRA builds them.
  Omar's MVP ships only an Apptainer `uniagent.def`; it was run from a Dockerfile that mirrors it line by line.
- Scoring: the official evaluator image (`uniagent-code/cikm26/evaluation`, built locally as `cikm26-evaluation`);
  trace structure additionally with `team-uniagent-solver/scripts/validate_trace.py` (decision is the last
  event of every case, parents exist, one prediction per case).
- Token and time figures: `evaluation/summarize.py` over the run traces. "max s/case" is first-to-last event of
  a case; Gareth's MVP prepares all cases before reviewing them, so its figure is the slowest single LLM call
  instead (measured separately below).

**Caveat:** one run per MVP; OpenRouter routes to varying providers, so single cases flip between runs. Marc's and
Rajesh's rules were written while looking at these 21 cases and their gold labels, so their spot-check accuracy
is training accuracy, not an estimate for the ~50 hidden test cases.

## Results (gpt-oss-20b)

| MVP | trip | proc | exp | total | wall s (3 datasets) | slowest case/call s | LLM calls/case | tokens/case | fallback decisions | image |
|---|---|---|---|---|---|---|---|---|---|---|
| Marc | 1.00 | 1.00 | 1.00 | **21/21** | 810 | 77 | 3.3 | 6,560 | 0 | 517 MB |
| Rajesh | 1.00 | 1.00 | 0.88 | 20/21 | **161** | **24** | 1.4 | **2,216** | 0 | 222 MB |
| Gareth | 1.00 | 0.88 | 0.88 | 19/21 | 988 | **361** | 1.0 | 5,379 | 3 | 2.73 GB |
| Omar | 0.80 | 0.62 | 0.50 | 13/21 | 1,252 | **364** | 0.4 | 3,219 | 14 | 334 MB |
| *always `abgelehnt`* | 0.60 | 0.50 | 0.50 | 11/21 | 0 | 0 | 0 | 0 | – | – |

Bold times above 300 s break the TIRA limit of 5 min per case.

Misses:
- **Rajesh**: `auslagenerstattung-08` rejected: labeler L2 ("same order billed twice") read the receipt and the card
  statement of one payment as a duplicate.
- **Gareth**: `beschaffungsantrag-07` accepted (did not compare the award note with the offer documents);
  `auslagenerstattung-08` fell back to `abgelehnt` after `Connection error`. Two more expense cases fell back
  the same way but happened to be correct. All three failing calls hung 361–362 s.
- **Omar**: 14 cases fell back to `abgelehnt`, 12 after `APIConnectionError` (per-call timeout 300 s,
  `max_retries=0`) and 2 after an unusable answer; 7 of them happened to be correct. Of the 7 model decisions,
  6 were correct; the miss is `beschaffungsantrag-03` (framework-contract monitors from a web shop, accepted).

Without a reachable LLM (`--network none`, endpoint `http://127.0.0.1:9/v1`) all four finish every dataset with
valid output and 0 invalid log lines; all degrade to (almost) always `abgelehnt` (0.60/0.50/0.50).

## Compliance

| Requirement | Marc | Omar | Rajesh | Gareth |
|---|---|---|---|---|
| Dockerfile, builds from source | yes, runs 61 tests in build | **no** (Apptainer only) | yes | yes (organisers' pyterrier base, JVM) |
| No downloads at runtime | yes | yes | yes | yes |
| LLM only via `OPENAI_*`, fail fast if unset | yes | yes | partly (crashes per case, not at start) | yes |
| `predictions.jsonl` accepted by official evaluator | yes | yes | yes | yes |
| Trace valid (evaluator + structural check) | yes | yes | yes | yes |
| `model` set on every event | yes | yes | **no**: `"-"` on all non-LLM events | yes |
| Decision event with decision/answer/evidence | result/begruendung/evidence | yes | answer holds the label, no evidence | result/begruendung (+citations) |
| Wall-clock limit per LLM call | 120 s, abandoned at deadline | 300 s HTTP timeout, observed 357 s | **none** (SDK default 600 s × 3 tries) | **none**, observed 361 s |
| Per-case deadline / run budget | 240 s / 3.75 h shared fairly | none | none | none |
| Fallback decision on any error | yes (checks, else `abgelehnt`) | yes | yes | yes |
| Retries | 1 per call, JSON repair prompt | none | 2 (parse only) | 1 repair |
| Wasted time | – | `time.sleep(22)` per case (18 min on 50 cases) | – | index build ~60–90 s/run |

## Components and where they come from

| MVP | Components worth considering | Concerns |
|---|---|---|
| Marc | LLM extraction into Pydantic schemas with printed-amount verification; deterministic checks per case type, each citing a curated rule with corpus `doc_id`; hard-fail override; BM25 (`bm25s`) for failed/unclear findings; deadlines and fallbacks; tests | ~3 LLM calls/case; checks and prompt tuned on these 21 cases |
| Rajesh | narrow yes/no labelers wired to one rejection reason each (L1–L6); deterministic regex rules T1/T2/E1/E3/P1; very low cost | regexes bound to exact form labels and file names; P1 uses the largest EUR amount anywhere; L2 false positive on a card statement |
| Gareth | broader policy coverage (optional evening events, invoice recipient, A1 lead time); multi-query retrieval fusion with a topical title filter; source-bound `duty_evidence` for expense approvals; one review/repair attempt | policies are hardcoded text without source; heavy image; no call deadline |
| Omar | `json-repair` as last-resort JSON parsing; `response_format` JSON schema; lean single-call prompt | no Dockerfile, no timeouts/retries, sleep per case |

## Decision

Base: **Marc's MVP**. It is the only one that is compliant on every row above, enforces the time limits itself
(slowest case 77 s), never fell back, and is structured so components can be swapped one at a time.
Rajesh's MVP is the strongest on efficiency (8× fewer seconds, 3× fewer tokens) and second on accuracy, but its
time limits, `model` field and form-label regexes would need the same work, and its accuracy rests on the same
spot-check tuning. Candidates for integration, tested one at a time in `team-uniagent-solver/ABLATIONS.md`:
Rajesh's labelers, Gareth's policy coverage, review step and retrieval fusion, and Omar's JSON repair and
structured output.

Raw runs: `evaluation/runs/` (git-ignored); reproduce with
`evaluation/run-mvp.sh <name> <image> evaluation/runs/gpt-oss-20b bridge -- <command>`.
