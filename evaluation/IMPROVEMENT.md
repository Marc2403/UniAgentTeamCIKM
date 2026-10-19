# Improving Marc's MVP with synthetic cases

Plan: `PLAN-MVP-VERBESSERUNG.md` (CIKM folder). Branch `marc-mvp-v2`. Baseline = `marc-uniagent-solver` at `13618cf`
(the `several-step` TIRA submission), image `marc-baseline`.

Sets: **S** spot-checks (21), **A** `synthetic-*` (36, 4 marked (?)), **B** `rajesh-*` (18, 3 (?)), **C** `coverage-*`
(83, families C1–C5, see [`synthetic/README.md`](synthetic/README.md)), **H** `holdout-*` (20, scored once as a sum).
Rules and coverage: [`synthetic/RULES.md`](synthetic/RULES.md). Runs: `evaluation/runs/<step>/<model>-r<n>/` (git-ignored),
scored with the official evaluator image and compared with `evaluation/compare_runs.py`.
`ok` = right, **A**/**R** = wrongly `angenommen`/`abgelehnt`; counts are summed over the runs of a configuration;
(?) cases are reported separately and never decide the gate.

Setup notes: the evaluator image had to be built from an LF copy of `uniagent-code/cikm26/evaluation` (the Windows
checkout has CRLF, so `#!/usr/bin/env python3\r` fails). The spot-check PDFs in that checkout are CRLF-damaged too
(`pdftotext` reports a broken xref table and reconstructs it); text extraction is unaffected, and TIRA has the originals.

## Gate runs

All gate runs use `openai/gpt-oss-20b` via OpenRouter, two runs per configuration, sets S A B C.

### Baseline (19.10.2026, `13618cf`, image `marc-baseline`)

| Set | right/total | A | R |
|---|---|---|---|
| S | 42/42 | 0 | 0 |
| A | 47/64 | 13 | 4 |
| B | 29/30 | 0 | 1 |
| C | 121/166 | 22 | 23 |
| A+B+C | 197/260 | 35 | 28 |

C by family: C1 39/58, C2 28/32, C3 24/32, C4 24/30, C5 6/14. `qwen/qwen-2.5-7b-instruct` on S: 19/21.
The OpenRouter key expired during the first baseline run; the affected datasets (C expense, C procurement, H) were rerun
with the new key, and five coverage cases fixed in `e34ab1d` were rerun and merged.

### Step 4a: rules into the YAML (reverted)

Seven prompt-only rules (`TRIP_FEE_SIDE_ACTIVITY`, `TRIP_ONLINE_EVENT`, `TRIP_EVIDENCE_OF_PURPOSE`,
`TRIP_DOMESTIC_FLIGHT`, `TRIP_MEALS`, `TRIP_TRANSPORT_COSTS`, `EXP_HOSPITALITY_EVIDENCE`) plus sharper texts for
`PROC_BUDGET_HOLDER` and `PROC_FRAMEWORK_CONTRACT`. The entries that the new checks of 4b cite (`TRIP_EXCLUDED_COUNTRIES`,
`EXP_FRAMEWORK_PRODUCTS`, `EXP_REPRESENTATION`, gases in `PROC_FRAMEWORK_CONTRACT`) moved to step 4b.

| Attempt | S | A | B | C | A+B+C | A / R (A+B+C) | Gate |
|---|---|---|---|---|---|---|---|
| 1 (19.10.) | 40/42 | 60/64 | 26/30 | 130/166 | 216/260 | 3 / 41 | fails points 2 and 4 |
| 2 (19.10.) | 41/42 | 60/64 | 30/30 | 133/166 | 223/260 | 10 / 27 | fails point 2 |

Attempt 1 regressed c104, c204, c405, c214 and B e01 (stable right to stable wrong): the texts for evidence of purpose,
budget holder, fee and framework products were stricter than the sources. Attempt 2 worded them closer to the sources
and still regressed two cases:

- c303 (gold abgelehnt): the travel office asked for a programme and none was supplied. The model cites the new
  sentence "a missing invitation alone is not a defect" and accepts. The probe under step 4b later showed that the
  baseline gets c303 wrong in 3 of 3 extra runs, so this regression is not shown to come from 4a.
- c110 (gold angenommen): flight to Porto; the model applies the domestic 80 € hotel cap to 90 € per night abroad.
  `TRIP_HOTEL_RATE` is unchanged; why the model now applies it abroad is not verified.

A change that fails the gate twice is reverted (plan). Attempt 2 gained +26 on A+B+C (C1 +9, C5 +6, A +13) and had
8 fallback decisions; its YAML is kept as a proposal in the final report.

### Step 4b: new checks (passed with a documented exception)

Checks `TRIP_EXCLUDED_COUNTRIES`, `EXP_FRAMEWORK_PRODUCTS`, `EXP_REPRESENTATION` (gifts, give-aways, decoration);
framework matching that ignores accessories (cables, bags, "für ... Monitor") and covers gases; `PROC_TOTAL_MATCHES_ITEMS`
accepts items that match the stated net or gross total, also after adding VAT; credit-card statements and pro-forma
invoices classified correctly; a pro-forma invoice is no duplicate; the service reference may come from any document of
the case. Commit `408a748`.

| Run (19.10.) | S | A | B | C | A+B+C | A / R (A+B+C) | Gate |
|---|---|---|---|---|---|---|---|
| 4b | 42/42 | 57/64 | 30/30 | 137/166 | 224/260 | 22 / 14 | points 1, 3, 4, 5 pass; point 2: c303, c214 |

C by family: C1 48/58, C2 30/32, C3 19/32, C4 30/30, C5 10/14.

Point 2 flagged c303 and c214 (right in both baseline runs, wrong in both 4b runs). Both cases were rerun three more
times on the baseline image and on 4b (`marc-baseline`, `marc-v2-4b`, same model):

| Case (gold) | Baseline right, 5 runs | 4b right, 5 runs |
|---|---|---|
| c303 (abgelehnt) | 2/5 | 0/5 |
| c214 (angenommen) | 3/5 | 2/5 |

Neither case is stable in the baseline; two runs per configuration cannot separate them from noise. **Deviation from
the plan:** 4b is counted as passed although point 2 fails as defined on two runs. c303 stays a weak case for every
version (the model accepts when the travel office's unanswered request is the only defect).

### Step 4c: decision prompt

Principles 7 (the listed rules are binding; reject on a clear violation even without a failed check) and 8 (in an
expense claim the applicant paid, a payment note on an invoice to the university does not mean the university paid).

| Run (19.10.) | S | A | B | C | A+B+C | A / R (A+B+C) | Gate vs baseline | vs 4b |
|---|---|---|---|---|---|---|---|---|
| 4c attempt 1 | 42/42 | 54/64 | 29/30 | 138/166 | 221/260 | 17 / 22 | point 2: c303 | −3, R +8, regresses c415, A exp-08 |
| 4c attempt 2 | 41/42 | 55/64 | 29/30 | 139/166 | 223/260 | 20 / 17 | point 2: c303, c310, c214 | −1, R +3, regresses A proc-09 |

4c attempt 1 adds nothing over 4b. New wrong rejections: the domestic 80 € hotel cap applied abroad (c403), the
give-away check counting a one-off print fee (25 €, quantity 1) as a give-away (A exp-08), an invitation required
although no rule asks for one (c302). Attempt 2 (`marc-v2-4c2`): give-away pieces only at quantity > 1, the abroad
hotel finding and rule text say that the 80 € cap does not apply abroad, and principle 7 adds "requirements that
neither a rule nor the correspondence sets are no reason to reject".

Attempt 2 does not beat 4b either (223 vs 224, wrong rejections 17 vs 14). **4c is reverted**; the final state is 4b
(`408a748`). The give-away fix (one-off fees with quantity 1 are no pieces) was part of attempt 2 and is therefore only
proposed, although it is a correction of a 4b check.

### Step 4d: Qwen2.5-7B robustness

`qwen/qwen-2.5-7b-instruct` on the 4b image scored 17/21 on S. trip-04: for an invitation that says no travel costs
are covered, Qwen returned `third_party_funding: {provider: null, max_amount: null, covers: [""]}`, and the check read
that as a funding commitment (hard double-funding failure). Fix: a funding object without payer, amount or covered
costs is no commitment (`a017cb2`, unit test). Qwen's unparseable extraction answers (6 in S+A: it copies the schema
descriptions into keys and values) never changed a decision, so `json-repair` was not added.

| Run (19.10.) | S | A | B | C | A+B+C | A / R (A+B+C) | Gate vs baseline | vs 4b |
|---|---|---|---|---|---|---|---|---|
| 4d, gpt-oss-20b | 42/42 | 56/64 | 30/30 | 138/166 | 224/260 | 18 / 18 | point 2: c110, c113, c303 | equal accuracy, R +4, c415 |

C by family: C1 48/58, C2 30/32, C3 21/32, C4 26/30, C5 13/14.

**The 4d change never fired for gpt-oss-20b:** no trip extraction in the 4d runs (nor in the H runs) returned an empty
funding object (searched in the raw responses). The 4d gpt runs are therefore a repetition of 4b, and their difference
to 4b is the run-to-run noise of this setup: wrong rejections 14 vs 18, C4 30/30 vs 26/30, C5 10/14 vs 13/14, and one
case (c415) flips from stable right to stable wrong. Two runs per configuration cannot resolve differences of this size;
the point-2 failures of 4b, 4c and 4d are within it.

| Qwen on S | run 1 | run 2 |
|---|---|---|
| baseline (`13618cf`) | 19/21 | 18/21 |
| 4b | 17/21 | – |
| 4d (final) | 19/21 | 18/21 |

Qwen errors on S in the final state: trip-02 and trip-04 (`TRIP_COSTS_COMPLETE`, also in the baseline), proc-07
(model accepts, also in the baseline), proc-05. proc-05 fails `PROC_TOTAL_MATCHES_ITEMS` in all three Qwen runs after
4b and in neither baseline run, with an identical extraction prompt (Qwen returns different item amounts); no code
path of 4b touches the extraction, so the cause is open. Qwen on A (4d): 23/32, (?) 2/4.

## Phase 5: final state (`a017cb2`)

| Check | Requirement | Result |
|---|---|---|
| Gate on S/A/B/C (gpt-oss-20b, 2 runs) | points 1–5 | points 1, 3, 4, 5 pass; point 2 fails on c110, c113, c303, within the measured noise (see 4b, 4d) |
| H, holdout, scored once (gpt-oss-20b, 2 runs, on 4b; 4d is identical for gpt-oss there) | not below baseline | **30/40** vs 20/40 (A 13 → 6, R 7 → 4) |
| Qwen on S | not below 19/21 | 19/21 and 18/21; baseline 19/21 and 18/21 |
| gpt-oss-120b on S and A (1 run, on 4b) | no crash | S 21/21, A 27/32, (?) 3/4; 2 invalid answers recovered by the retry, max 98 s per case |

Exit code 0 and valid traces in every run; max 212 s per case (gpt-oss-20b, 4d), below the 240 s limit of the plan and
the 300 s of TIRA; 7 fallback decisions (model gave no valid answer in time) in 316 case runs of the final state.

## Final report

### What changed (`13618cf` → `a017cb2`)

- `408a748` checks: excluded travel countries (hard), framework products bought privately and representation costs
  (gifts > 30 €, give-aways > 10 €, decoration; soft), framework matching that ignores accessories and covers gases,
  VAT-tolerant totals, credit-card statements and pro-forma invoices classified correctly, service reference from any
  document of the case. Four rule entries for these checks, each citing its Kassel `doc_id`.
- `a017cb2` empty funding objects are no funding commitment.

| Set (gpt-oss-20b, 2 runs) | baseline | final |
|---|---|---|
| S | 42/42 | 42/42 |
| A | 47/64 | 56/64 |
| B | 29/30 | 30/30 |
| C | 121/166 | 138/166 |
| A+B+C | 197/260 (A 35, R 28) | 224/260 (A 18, R 18) |
| H | 20/40 | 30/40 |

These are accuracies on our own labels; S, A, B and C were used for development, only H was not.

### Reverted

- 4a (rules into the YAML), two attempts: attempt 2 gained most (+26 on A+B+C, C1 +9) but failed point 2.
- 4c (decision-prompt principles 7 and 8), two attempts: no gain over 4b, more wrong rejections.

### Open (?) cases (excluded from the gate)

A: auslagenerstattung-02, -04, beschaffungsantrag-04, -05. B: dienstreiseantrag-s01-clean-trip, -k01-private-weekend,
auslagenerstattung-r05-hotel-over-cap. Right: baseline 8/14, final 6/14 (A exp-04 now accepted in both runs).

### Notes

- The evaluator image and the spot-check PDFs in the Windows checkout of `uniagent-code` are CRLF-damaged (see setup).
- The OpenRouter key expired during the baseline; affected runs were repeated. OpenRouter cost of all runs with the new
  key: 0.85 USD.
- `rajesh-procurement` has 3 cases, below the 5-line minimum of the official evaluator; it is scored by
  `compare_runs.py` only.
- The holdout was measured on 4b in parallel to the 4d gate, not after it; the 4d change does not fire on any H case.

### Proposals (not applied)

1. Gate with at least four runs per configuration, or only count point-2 cases that are stable in more baseline runs:
   the 4b/4d repetition shows ±4 wrong rejections and single flips from noise alone.
2. 4a attempt 2 as a new candidate under such a gate (rule texts for fee/side activity, online events, evidence of
   purpose, domestic flights, meals, transport, hospitality evidence; sharper budget-holder text).
3. Give-away check: count only positions bought in quantity (a one-off print fee was flagged); the hotel finding for
   trips abroad should say that the 80 € cap does not apply (gpt-oss applies it to Porto and Spain).
4. c303 pattern (the travel office's request for a programme stays unanswered) is wrong for every version; a check on
   unanswered requests in the correspondence would need an extraction field.
5. Qwen: a shorter extraction prompt without inline descriptions, since Qwen copies them into keys and values.
