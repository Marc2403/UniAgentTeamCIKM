# Ablations – team solver, 12 October 2026

How every candidate component was decided. Each component was integrated on its own branch
(`ablation/<name>`, local) on top of the same base and run on all three spot-check datasets; it was kept only if
it raised accuracy, or kept it equal while improving robustness or efficiency. Kept components were then
cherry-picked onto `team-mvp` and the combination re-run.

## Setup

- Base: Marc's MVP made compliant, tag `team-m1` (`3f6968d`) + daemon-thread LLM requests (`e502e09`).
- Data: the 21 spot-check cases (business trip 5, procurement 8, expense 8).
- Models via OpenRouter: `openai/gpt-oss-20b` (main) and `qwen/qwen-2.5-7b-instruct`.
- Runs: `evaluation/run-mvp.sh`, Docker with 4 CPUs / 40 GB, three containers in parallel, on the internal network
  `uniagent-internal` whose only egress is an allowlist proxy admitting `openrouter.ai`
  (`evaluation/egress-proxy/Dockerfile`; checked: OpenRouter 200, huggingface.co and pypi.org blocked, direct
  egress blocked). Accuracy from the official evaluator image; the release runs also with `tira-cli evaluate`.
- Columns: wall s = all three datasets incl. index build (~25 s each); max s = slowest case; tokens = prompt +
  completion per case. **†** = the laptop was in standby during the run (Windows Kernel-Power 506/507 at
  13:06–13:26 and 14:31–14:39 local time); its accuracy is valid, its times are not.

**Noise.** Identical configurations gave gpt-oss-20b 21/21 and 21/21 (base), 20/21 and 21/21 (combination before
the last fix); Qwen2.5-7B 19/21 and 17/21 (base). Qwen on OpenRouter is not deterministic at temperature 0
(identical extraction prompts returned dates in one run and none in the next), so single Qwen runs cannot
separate effects within ±2 cases; decisions rest on gpt-oss-20b and on whether a component was triggered at all.

## One component at a time (vs. base)

| # | Component | From | gpt-oss trip / proc / exp | total | wall s | max s | tokens | Qwen total | Decision | Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | Base (`team-m1`), two runs | Marc | 1.00 / 1.00 / 1.00 | 21, 21 | 738, † | 100, † | 6,651, 6,554 | 19, 17 | – | reference |
| 1 | Reason-first decision JSON | Gareth | 1.00 / 1.00 / 1.00 | 21 | † | † | 6,615 | 17 | dropped | no gain on gpt-oss; nothing indicates it helps Qwen |
| 2 | `json-repair` last-resort parser | Omar | 1.00 / 1.00 / 1.00 | 21 | † | 110 | 7,058 | 17 | **kept** | equal accuracy; truncated-JSON mock: error events 13 → 1, model decisions instead of fallbacks; Qwen difference is noise (misses on unrelated cases) |
| 3 | JSON mode (`response_format: json_object`) | Omar, Gareth | 0.80 / 1.00 / 1.00 | 20 | 721 | 121 | 7,558 | 18 | dropped | gpt-oss answered `[  ]` and `""` under JSON mode → fallback on `dienstreiseantrag-04`; 5 error events |
| 4 | Policy coverage: meals/evening events, A1 lead time, exclusion period | Gareth | 0.80 / 1.00 / 1.00 | 20 | 687 | 146 | 6,422 | 17 | see #10 | the miss was a provider stall (decision call >120 s, not retried) — led to fix #8, re-run as #10 |
| 5 | Source-faithful wording of `EXP_SERVICE_REFERENCE`, `TRIP_PRIVATE_STAY` | Team (Marc's rules) | 0.80 / 1.00 / 0.88 | 19 | 751 | 142 | 6,308 | 18 | dropped | `auslagenerstattung-01` rejected on content ("invoice to the university, so not privately advanced"); trip miss = same provider stall as #4 |
| 6 | Trip dates from labelled form fields (gap filling) | Rajesh | 1.00 / 1.00 / 1.00 | 21 | 538 | 65 | 6,549 | 18 | **kept** | equal; never triggered with gpt-oss, filled all five dates of two Qwen applications whose extraction had none |
| 7 | LLM item labeler (framework product group, catering) | Rajesh (L3, L4) | 1.00 / 1.00 / 1.00 | 21 | 509 | 37 | 6,804 | 17 | dropped | equal accuracy at +0.7 calls/case; on every procurement and expense case the result and the failed checks were the same as in the base run |
| 8 | Decision call retried after timeout/error within the case budget | Team | – | – | – | – | – | – | **kept** | bug fix from #4/#5: two cases fell back after 45 s of a 240 s budget; unit-tested |
| 9 | `--no-retrieval` (no corpora, no rule passages) | Marc (ablation flag) | 0.80 / 1.00 / 1.00 | 20 | 507 | 60 | 6,003 | 18 | dropped | lost `dienstreiseantrag-04` (the model read the transfer line "2 × 35 €" as 70 € and saw a sum mismatch); −10% tokens does not outweigh a lost case and the hidden set may bring an intranet corpus |
| 10 | #4 on top of #2, #6, #8, #11 | Gareth | 1.00 / 1.00 / 1.00 | 21, 21 | 519, 569 | 33, 93 | 6,577, 6,681 | 17 | **kept** | equal accuracy at +3% tokens; no spot-check case needs these rules, but the business-trip dataset README lists them among the rules its cases use. Alternative rejected: dropping it for lack of a measurable gain |
| 11 | Decision with `reasoning_effort=low` (default) | Team (config) | 1.00 / 1.00 / 1.00 | 21 | 387 | 23 | 6,347 | – | **kept** | equal accuracy, slowest case 23 s instead of 65–100 s, −3% tokens |
| 12 | Third-party funding as soft finding | Team | 1.00 / 1.00 / 1.00 | 21, 21, 21 | †, †, 296 | 35, 29, 27 | 6,394, 6,348, 6,342 | 19, 18 | **kept** | the combination of #2, #6, #8, #11 (20/21, 21/21) once rejected `dienstreiseantrag-04` because extraction read an invitation that explicitly does not cover travel as a funding commitment, and the hard check rejected on that alone (Qwen's base run did the same); as a soft finding the model decides, real double funding (`-05`) still rejected |
| 13 | `TRIP_MEALS` states that claiming the Tagegeld is regular | Team | 1.00 / 1.00 / 1.00 | 21, 21 (low), 21, 21 (medium) | 341–495 | 27–71 | 6,491–6,957 | 18, 18 | **kept** | fix for the misreading of #10 described under Release |

Considered and not run, with the reason:

| Candidate | From | Why not |
|---|---|---|
| Deterministic rules T1, T2, E1, E3, P1 | Rajesh | duplicates of `TRIP_SUBMITTED_BEFORE_START`, `TRIP_DATES_CONSISTENT`, `EXP_REAL_INVOICE`, `EXP_SERVICE_REFERENCE`, `PROC_COMPARISON_OFFERS` (which uses the order's net value, not the largest amount anywhere in the case) |
| Labelers L1, L2, L5, L6 | Rajesh | deterministic equivalents exist (`TRIP_THIRD_PARTY_FUNDING`, `EXP_DUPLICATE`, `PROC_TOTAL_MATCHES_ITEMS`, `PROC_AWARD_MATCHES_OFFERS`); L2 caused Rajesh's only miss |
| Multi-query retrieval fusion with topical title filter, pyterrier | Gareth | retrieval did not change accuracy (#9 lost a case to model noise, Marc's earlier ablation R3 none), so a costlier retrieval cannot pass the keep rule on these data; pyterrier needs a JVM image of 2.7 GB |
| Source-bound `duty_evidence` for expense approvals | Gareth | same function as `EXP_SERVICE_REFERENCE` |
| Single decision call without extraction | Omar | equals Marc's `--no-checks` ablation (R4: 20/21); Omar's own model decisions 6/7 |
| Self-consistency (3 samples) | Marc | Marc's ablation R1: no gain, +27% tokens |

## Release (`team-mvp` at `ae4f6f5`: components 2, 6, 8, 10, 11, 12, 13)

| Run | Model / decision effort | trip / proc / exp | total | wall s | max s | calls | tokens | errors | fallbacks |
|---|---|---|---|---|---|---|---|---|---|
| release2-r1 | gpt-oss-20b, low (default) | 1.00 / 1.00 / 1.00 | 21/21 | 341 | 29 | 3.3 | 6,491 | 0 | 0 |
| release2-r2 | gpt-oss-20b, low (default) | 1.00 / 1.00 / 1.00 | 21/21 | 362 | 27 | 3.3 | 6,497 | 0 | 0 |
| release2-medium-r1 | gpt-oss-20b, medium | 1.00 / 1.00 / 1.00 | 21/21 | 465 | 71 | 3.3 | 6,934 | 0 | 0 |
| release2-medium-r2 | gpt-oss-20b, medium | 1.00 / 1.00 / 1.00 | 21/21 | 495 | 51 | 3.3 | 6,957 | 0 | 0 |
| release2-r1 | Qwen2.5-7B, low (default) | 0.80 / 0.75 / 1.00 | 18/21 | 209 | 9 | 3.3 | 7,787 | 1 | 0 |
| release2-r2 | Qwen2.5-7B, low (default) | 1.00 / 0.75 / 0.88 | 18/21 | 186 | 8 | 3.3 | 7,764 | 0 | 0 |
| release2-r3 | Qwen2.5-7B, low (default), paired with base | 0.80 / 0.75 / 1.00 | 18/21 | 206 | 11 | 3.3 | 7,796 | 1 | 0 |

`tira-cli evaluate` (v0.0.205, truths and evaluator image from TIRA): release2-r1, release2-r2 and
release2-medium-r1 with gpt-oss-20b score 1.0 on all three datasets with 0 invalid log lines; Qwen release2-r1
scores 0.8 / 0.75 / 1.0 with 0 invalid log lines. All release2 traces pass `scripts/validate_trace.py`.
No standby during these runs.

The commit before the last (`90d634e`, same as release2 except `TRIP_MEALS` wording) scored 21/21 twice with
gpt-oss-20b at the default effort and 18/21 twice with Qwen; with `medium` it scored 20/21 and 21/21. The 20/21
was `dienstreiseantrag-02`, rejected because the model read "Verpflegungskosten sind über das Tagegeld
abgegolten" as forbidding the requested daily allowance, a misreading of the new rule #10. Fix #13 states that
claiming the Tagegeld is regular and only a necessary flat fee comes on top; with it, `medium` scored 21/21 twice.

Qwen misses: `beschaffungsantrag-07` (accepted; does not catch the award-note amount) in 15 of 16 ablation runs
and every release run, `beschaffungsantrag-05` in 9 of 16 ablation runs across unrelated variants and every release
run (the extraction drops part of a position, so `PROC_TOTAL_MATCHES_ITEMS` fails), `dienstreiseantrag-04` or
`auslagenerstattung-02` in some. None of these occurred with gpt-oss-20b in any release run. `beschaffungsantrag-05` failed in every run with
`json-repair` but only in some without, so base (no `json-repair`) and release2 were run side by side on Qwen:
both 18/21 with the same misses, including `-05` (the extraction calls never produced invalid JSON, so the repair
never fired). The pattern follows when a run happened, i.e. OpenRouter's provider for Qwen, not the component. Making the arithmetic
checks robust to a weak extractor (e.g. a second extraction before a hard fail) is the next step if Qwen matters.

## Final comparison with the MVPs (gpt-oss-20b)

| System | trip | proc | exp | total | wall s | slowest case s | tokens/case | fallbacks |
|---|---|---|---|---|---|---|---|---|
| **Team release2** (2 runs) | 1.00 | 1.00 | 1.00 | **21/21, 21/21** | 341, 362 | 29 | 6,491, 6,497 | 0 |
| Marc | 1.00 | 1.00 | 1.00 | 21/21 | 810 | 77 | 6,560 | 0 |
| Rajesh | 1.00 | 1.00 | 0.88 | 20/21 | 161 | 24 | 2,216 | 0 |
| Gareth | 1.00 | 0.88 | 0.88 | 19/21 | 988 | 361 | 5,379 | 3 |
| Omar | 0.80 | 0.62 | 0.50 | 13/21 | 1,252 | 364 | 3,219 | 14 |

MVP figures from `../evaluation/EVALUATION.md` (one run each, four containers in parallel). Against Marc's MVP the
team release is equally accurate on the spot-checks, 2.3× faster in wall time, removes one hard rule that rested on an LLM
reading, covers three more documented rules, and survives every robustness case below. Rajesh's MVP remains
cheaper in tokens (2.9×) and has the fastest slowest case (24 s); its accuracy relies on form-specific regexes and it has no time limits.

## Robustness (`evaluation/robustness/run.sh`, image of `90d634e`; release2 adds only one rule text and the `--reasoning-effort` flag)

Inputs: a real procurement case, an unparseable PDF with a `.txt` note, an empty case folder, a 400-page PDF.
Mock LLM modes: garbage prose, JSON cut off mid-string, HTTP 500, never answering.

| Mode | exit | predictions | trace | seconds | behaviour |
|---|---|---|---|---|---|
| garbage | 0 | 4/4 | valid | 5 | broken/empty cases rejected as `no_documents`, the others fall back to the checks |
| truncated | 0 | 4/4 | valid | 4 | repaired by `json-repair`, decisions come from the model |
| error (HTTP 500) | 0 | 4/4 | valid | 16 | retries, then fallback |
| slow (no answer) | 0 | 4/4 | valid | 483 | each case stops at its 240 s deadline |

The 400-page PDF is read in ~4 s and cut to 12,000 characters per extraction and 30,000 per decision prompt.

**Caveat:** the checks and curated rules of the base were written while looking at these 21 cases. Spot-check
accuracy is training accuracy, not an estimate for the ~50 hidden test cases.

## Recommended TIRA submissions

Ordered by priority. `OPENAI_MODEL` must name the model as the TIRA endpoint does (here OpenRouter ids were
used; the TIRA ids are not verified).

| # | Submission | Command suffix | Evidence | Why |
|---|---|---|---|---|
| 1 | Team release2, gpt-oss-20b | (none; decision effort `low`) | 21/21 ×2, slowest case 29 s, 6,494 tokens/case | best accuracy and well inside the time limits |
| 2 | Team release2, gpt-oss-20b, more deliberate decisions | `--reasoning-effort medium` | 21/21 ×2, slowest case 71 s, 6,946 tokens/case | hedge for hidden cases that need more judgment than the spot-checks |
| 3 | Team release2, Qwen2.5-7B-Instruct | (none) | 18/21 in all five Qwen runs of `90d634e` and release2 | the second allowed model; clearly weaker here, so only if a Qwen run is wanted |
| 4 | Tag `team-m1` (Marc's MVP made compliant), gpt-oss-20b | (none) | 21/21 ×2 | hedge against the post-M1 changes; keeps the hard third-party-funding check and the provider's default effort |

No fifth submission: no other variant was both strong and meaningfully different. Rajesh's MVP (20/21, 3× fewer
tokens) would be the diverse candidate but first needs call timeouts, the `model` field on every event and a
per-case deadline.
