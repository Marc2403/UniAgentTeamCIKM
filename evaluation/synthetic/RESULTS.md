# Results on the synthetic cases – 15 October 2026

One run per system on the 36 cases of [`README.md`](README.md), `openai/gpt-oss-20b` via OpenRouter, Docker with
`--cpus 4 --memory 40g`, the three systems in parallel, scored with the official evaluator image
(`cikm26-evaluation`). Images: `team-solver:release2` (source identical to `main` `87eeebf`), `eval-marc`,
`eval-rajesh` (the images of [`../EVALUATION.md`](../EVALUATION.md)). Raw runs: `evaluation/runs/synthetic/gpt-oss-20b/`
(git-ignored). All runs: exit 0, 0 invalid log lines.

| System | trip | proc | exp | total | new patterns | variants | wall s (3 runs) | max s/case | calls/case | tokens/case | fallbacks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Team release2 | 0.50 | 0.92 | 0.67 | 25/36 | 15/26 | 10/10 | 831 | 70 | 3.1 | 5,704 | 0 |
| Marc | 0.75 | 1.00 | 0.67 | **29/36** | 19/26 | 10/10 | 1,461 | 125 | 3.1 | 6,082 | 2 |
| Rajesh | 0.42 | 0.67 | 0.58 | 20/36 | 12/26 | 8/10 | 329 | 39 | 1.5 | 1,806 | 0 |

Caveats: one run each; OpenRouter is not deterministic, so single cases can flip. Marc's two fallbacks
(`auslagenerstattung-05`, `-08`) were model errors after which the checks decided `angenommen`, correct by luck.
The labels are ours (see the (?) cases in the README).

## Per case

`ok` = correct, **A**/**R** = wrongly `angenommen`/`abgelehnt`.

| Case | Gold | Kind | Team | Marc | Rajesh |
|---|---|---|---|---|---|
| dienstreiseantrag-01 | angenommen | variant | ok | ok | ok |
| dienstreiseantrag-02 | abgelehnt | new | **A** | ok | **A** |
| dienstreiseantrag-03 | angenommen | new | ok | ok | ok |
| dienstreiseantrag-04 | abgelehnt | new | **A** | ok | **A** |
| dienstreiseantrag-05 | abgelehnt | new | **A** | **A** | **A** |
| dienstreiseantrag-06 | angenommen | variant | ok | ok | ok |
| dienstreiseantrag-07 | abgelehnt | new | **A** | ok | **A** |
| dienstreiseantrag-08 | angenommen | variant | ok | ok | ok |
| dienstreiseantrag-09 | abgelehnt | new | **A** | **A** | **A** |
| dienstreiseantrag-10 | angenommen | new | ok | ok | ok |
| dienstreiseantrag-11 | abgelehnt | new | **A** | **A** | **A** |
| dienstreiseantrag-12 | angenommen | variant | ok | ok | **R** |
| auslagenerstattung-01 | angenommen | variant | ok | ok | ok |
| auslagenerstattung-02 | abgelehnt | new (?) | **A** | **A** | **A** |
| auslagenerstattung-03 | angenommen | new | ok | ok | ok |
| auslagenerstattung-04 | abgelehnt | new (?) | ok | ok | ok |
| auslagenerstattung-05 | angenommen | variant | ok | ok (fallback) | **R** |
| auslagenerstattung-06 | abgelehnt | variant | ok | ok | ok |
| auslagenerstattung-07 | abgelehnt | new | **A** | **A** | **A** |
| auslagenerstattung-08 | angenommen | new | ok | ok (fallback) | ok |
| auslagenerstattung-09 | abgelehnt | new | **A** | **A** | **A** |
| auslagenerstattung-10 | angenommen | variant | ok | ok | ok |
| auslagenerstattung-11 | abgelehnt | new | **A** | **A** | **A** |
| auslagenerstattung-12 | angenommen | new | ok | ok | ok |
| beschaffungsantrag-01 | angenommen | variant | ok | ok | ok |
| beschaffungsantrag-02 | abgelehnt | new | ok | ok | **A** |
| beschaffungsantrag-03 | angenommen | new | ok | ok | ok |
| beschaffungsantrag-04 | abgelehnt | new (?) | ok | ok | ok |
| beschaffungsantrag-05 | angenommen | new (?) | ok | ok | **R** |
| beschaffungsantrag-06 | abgelehnt | new | ok | ok | ok |
| beschaffungsantrag-07 | abgelehnt | new | ok | ok | **A** |
| beschaffungsantrag-08 | angenommen | new | ok | ok | ok |
| beschaffungsantrag-09 | abgelehnt | new | **A** | ok | **A** |
| beschaffungsantrag-10 | angenommen | variant | ok | ok | ok |
| beschaffungsantrag-11 | abgelehnt | new | ok | ok | ok |
| beschaffungsantrag-12 | angenommen | new | ok | ok | ok |

## Observations

- **Every error of Team and Marc is a wrong `angenommen` on an `abgelehnt` case**, and all of them are new
  patterns. All 10 variants of spot-check patterns are correct for both: the known rules generalise to new surface
  forms (neutral file names, scanned bundles, English and GBP documents, reverse charge, Sallstedt).
- **Missed by all three:** rules that are not in the curated rule files: fee for a talk (trip-05), online conference
  as a business trip (trip-09; the rule exists only as `EXP_ONLINE_CONFERENCE` for expenses), incomplete form
  without evidence of purpose (trip-11), Citavi campus licence (exp-02), framework product claimed as an expense
  (exp-07; `PROC_FRAMEWORK_CONTRACT` exists only for procurement), guest gift above 30 EUR (exp-09), decoration
  (exp-11). Retrieval does not compensate: the model accepts when no check fails.
- **Team below Marc on four cases** (trip-02 hotel above 80 EUR, trip-04 Lebanon, trip-07 domestic flight,
  proc-09 missing budget-holder signature): in each, Team's reason lists only the checks that passed. One
  difference to Marc's MVP is that the team solver decides with `reasoning_effort=low` (others: json-repair, date
  fallback, Gareth's rules, soft third-party funding); whether that causes the gap is a hypothesis from one run,
  not measured. A paired run with `--reasoning-effort medium` would test it.
- **Procurement generalises best** (Team 11/12, Marc 12/12): framework contracts for new product groups (Microsoft,
  office chairs, gases), order splitting, invoice above offer and the reverse-charge trap were all handled.
- **Rajesh** additionally rejects correct cases on format (trip-12 with `Anlage_N.pdf` names, exp-05 GBP invoice,
  proc-05 gross above 1,000 EUR) and misses award and framework errors in procurement (proc-02, proc-07).
