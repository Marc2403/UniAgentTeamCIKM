# Combined evaluation: spot-check, dev and dev-extra queries with UMBRELA qrels

173 queries (de: 67, en: 56, law: 50; spot: 65, dev: 65, extra: 43). Qrels: gpt-oss-20b with the unchanged UMBRELA 0.0.7 prompt, robust parser, over the top-10 of all configs (spot-checks: plus the organisers' relevant document). nDCG@10; in brackets two-sided paired randomization test p-values against lexical-plus / llm-k20.

Unjudged documents in the top 10: dph 0, lexical-plus 0, ce-minilm 0, llm-k10 0, llm-k20 0, llm-k20-desc 0, llm-k30 0.

### Overall and per collection

| config | all (n=173) | de (n=67) | en (n=56) | law (n=50) |
|---|---|---|---|---|
| dph | 0.688 (0.00/0.00) | 0.680 (0.00/0.00) | 0.700 (0.02/0.00) | 0.686 (0.04/0.00) |
| lexical-plus | 0.783 (–/0.00) | 0.826 (–/0.01) | 0.763 (–/0.00) | 0.746 (–/0.01) |
| ce-minilm | 0.780 (0.72/0.00) | 0.792 (0.01/0.00) | 0.782 (0.23/0.00) | 0.760 (0.47/0.07) |
| llm-k10 | 0.793 (0.02/0.00) | 0.831 (0.43/0.00) | 0.778 (0.04/0.00) | 0.758 (0.30/0.00) |
| llm-k20 | 0.836 (0.00/–) | 0.863 (0.01/–) | 0.839 (0.00/–) | 0.796 (0.01/–) |
| llm-k20-desc | 0.826 (0.00/0.13) | 0.859 (0.01/0.63) | 0.810 (0.00/0.01) | 0.801 (0.00/0.67) |
| llm-k30 | 0.849 (0.00/0.00) | 0.870 (0.02/0.32) | 0.871 (0.00/0.00) | 0.795 (0.02/0.86) |

### Per origin

| config | spot (n=65) | dev (n=65) | extra (n=43) |
|---|---|---|---|
| dph | 0.817 (0.02/0.00) | 0.656 (0.00/0.00) | 0.543 (0.00/0.00) |
| lexical-plus | 0.862 (–/0.02) | 0.787 (–/0.00) | 0.656 (–/0.00) |
| ce-minilm | 0.867 (0.67/0.01) | 0.793 (0.66/0.01) | 0.627 (0.25/0.00) |
| llm-k10 | 0.862 (0.98/0.00) | 0.796 (0.10/0.00) | 0.683 (0.05/0.00) |
| llm-k20 | 0.894 (0.02/–) | 0.834 (0.00/–) | 0.752 (0.00/–) |
| llm-k20-desc | 0.892 (0.01/0.84) | 0.831 (0.00/0.69) | 0.721 (0.01/0.08) |
| llm-k30 | 0.897 (0.03/0.57) | 0.853 (0.00/0.02) | 0.769 (0.00/0.09) |

### Law: spot-check vs. dev/extra, and § reference in the narrative

| config | law spot (n=15) | law dev+extra (n=35) | law with § (n=7) | law without § (n=43) |
|---|---|---|---|---|
| dph | 0.776 (0.48/0.40) | 0.648 (0.05/0.00) | 0.737 (0.57/0.11) | 0.678 (0.05/0.01) |
| lexical-plus | 0.819 (–/0.71) | 0.715 (–/0.00) | 0.810 (–/0.03) | 0.736 (–/0.05) |
| ce-minilm | 0.847 (0.06/0.70) | 0.723 (0.77/0.03) | 0.863 (0.03/0.24) | 0.743 (0.73/0.12) |
| llm-k10 | 0.807 (0.76/0.18) | 0.736 (0.08/0.01) | 0.835 (0.06/0.03) | 0.745 (0.47/0.02) |
| llm-k20 | 0.834 (0.71/–) | 0.779 (0.00/–) | 0.900 (0.03/–) | 0.779 (0.05/–) |
| llm-k20-desc | 0.872 (0.04/0.07) | 0.771 (0.01/0.46) | 0.915 (0.02/0.34) | 0.783 (0.02/0.80) |
| llm-k30 | 0.834 (0.73/1.00) | 0.778 (0.01/0.85) | 0.916 (0.03/0.49) | 0.775 (0.11/0.57) |

### Cross-validation (5-fold, stratified by collection × origin, 10 seeds)

Each round picks the config with the best mean nDCG@10 on the 4 training folds and scores it on the test fold.

- Selection procedure: **0.849 ± 0.000** (mean ± sd over repetitions)
- Chosen in 50 rounds: llm-k30 50×
- Fixed config (all queries): dph 0.688, lexical-plus 0.783, ce-minilm 0.780, llm-k10 0.793, llm-k20 0.836, llm-k20-desc 0.826, llm-k30 0.849

### LLM reranking cost without cache

Tokens: from the run traces (cached answers keep their original usage), mean over all 173 queries. Time: measured wall clock per call in uncached runs with 8 parallel requests, 0.25–0.68 s (mean 0.40 s), times depth. Price: OpenRouter list price for openai/gpt-oss-20b ($0.02 / $0.10 per million prompt / completion tokens).

| config | prompt tokens/query | completion tokens/query | seconds/query | 50 queries: tokens | 50 queries: minutes | 50 queries: USD |
|---|---|---|---|---|---|---|
| llm-k10 | 7,664 | 714 | 4.0 (2.5–6.8) | 418,897 | 3.3 (2.1–5.7) | 0.011 |
| llm-k20 | 15,344 | 1,426 | 8.0 (5.0–13.6) | 838,482 | 6.7 (4.1–11.3) | 0.022 |
| llm-k30 | 22,902 | 2,098 | 12.0 (7.5–20.4) | 1,249,982 | 10.0 (6.2–17.0) | 0.033 |

### Plausibility and judging cost

- Grade of the organisers' relevant spot-check document in the new qrels: 2: 1, 3: 64
- All qrels: 3,758 judgments, 12,717,524 prompt + 911,462 completion tokens, $0.35 at list price.
