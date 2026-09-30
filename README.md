# DAIM – UniAgent 2026, Task 1 (Retrieval)

Multi-stage retrieval for the uni-kassel.de (DE/EN) and Hessian-law collections:
lexical candidates (PyTerrier, weighted query/description, optional decompounding,
title/URL fields, PRF, passages, RRF) → collection-specific post-processing
(law: abbreviations, `§`-reference injection, current-version collapsing,
norm/decision prior; web: near-duplicate demotion, priors) → optional dense,
cross-encoder and LLM reranking of the head. Every stage is a config switch
(`uniretrieval/config.py` lists all switches and defaults). Plan: `PLAN.md`.

Outputs per run: `run.txt.gz` (TREC), `run-trace.jsonl.log.gz`
([event-logging contract](../uniagent-code/cikm26/event-logging-contract/README.md)),
`stats.json` (per-stage seconds, LLM token usage). A complete lexical run is
written before any neural stage and rewritten after each one; a wall-clock
budget (`budget.total_seconds`, default 3.5 h) skips reranking for the remaining
queries when time runs out.

## Results on the spot-checks (nDCG@10)

| config | DE | EN | Law | mean |
|---|---|---|---|---|
| dph (organisers' baseline) | 0.738 | 0.860 | 0.395 | 0.664 |
| lexical-best (query×2 + description + narrative, decompounding) | 0.933 | 0.922 | 0.651 | 0.835 |
| lexical-plus (+ law abbreviations, §-injection, versions) | 0.933 | 0.922 | 0.890 | 0.915 |

Dense (e5-small, top-100) and cross-encoders (mMiniLM top-50, bge-m3 top-20)
all score lower than lexical-plus (mean 0.831–0.855) at 15–60× the runtime;
full-collection dense retrieval does not fit 4 CPUs (e5-small: 4.8 docs/s).
Full table: `eval/results-spot-check.md`. The spot-checks have one relevant
document per query; decisions are to be re-checked on the dev set.

## Build and test (Docker only)

```bash
docker build --tag daim-retrieval .          # runs pytest; downloads models to /models
```

## Run

`scripts/docker-run.sh` mounts this working copy at `/app` and
`../uniagent-code/cikm26/datasets` at `/data`, limited to 4 CPUs:

```bash
scripts/docker-run.sh python3 retrieve.py --dataset /data/retrieval-de-spot-check --output runs/manual --config configs/lexical-plus.yaml
```

Configs that call the LLM (`query_expansion`, `llm_rerank`) need
`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` (pass with `--env`) and fail
fast without them.

## Experiments

```bash
scripts/docker-run.sh python3 scripts/run_experiments.py \
  --dataset /data/retrieval-de-spot-check --dataset /data/retrieval-en-spot-check \
  --dataset /data/retrieval-hessian-law-de-spot-check \
  --config configs/dph.yaml --config configs/lexical-plus.yaml
scripts/docker-run.sh python3 eval/compare.py --runs runs --reference dph
```

Runs land in `runs/<dataset>/<config>/` with `metrics.json`; indexes and LLM
responses are cached under `.cache/` (never part of the image).
`eval/evaluate.py` reads runs in file order, like the official evaluator
(tira → trectools `get_ndcg`), and reproduces the baseline numbers in `PLAN.md`.
Cross-check with the official image: `docker build -t cikm26-evaluation ../uniagent-code/cikm26/evaluation`.

## Dev set (Phase 3)

`eval/devsets/{de,en,law}/queries.jsonl`: 80 drafted queries (qids 1001+, 2001+,
3001+), to be reviewed. Qrels are built like the organisers': run several configs
on a dev set (`--dataset devset-de=/data/retrieval-de-spot-check:/app/eval/devsets/de`),
then `scripts/judge_devset.sh de ../uniagent-code/cikm26/datasets/retrieval-de-spot-check`
(UMBRELA + gpt-oss-20b over the top-10 pool).

## Throughput

`scripts/benchmark_throughput.py --dataset /data/retrieval-de-spot-check`, run with
`docker run --cpus 4`, reports docs/s (embeddings) and pairs/s (cross-encoders)
and extrapolates to test-collection sizes.

## Submission (not yet)

```bash
tira-cli code-submission --path . --task uniagent-2026 \
  --dataset retrieval-de-spot-check-20260816-training \
  --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
  --command '/app/retrieve.py --dataset $inputDataset --output $outputDir --config /app/configs/lexical-plus.yaml' \
  --dry-run
```
