# DAIM – UniAgent 2026, Task 2 (Solving)

Decides business-trip applications (`dienstreiseantrag-*`), expense reimbursements
(`auslagenerstattung-*`) and procurement requests (`beschaffungsantrag-*`) as
`angenommen` / `abgelehnt`. Principle: **the LLM extracts, Python checks, the LLM decides on
pre-checked findings.** Plan: `PLAN.md`, results: `RESULTS.md`.

## Pipeline (`predict.py` → `solver/pipeline.py`)

1. **Discover** cases (directories with PDFs) and corpora (`retrieval-corpora/*/documents.jsonl.gz`, found at runtime).
2. **Index** every corpus once with BM25 (`bm25s`, German/English stemming; ~25 s for the three spot-check corpora on 4 CPUs).
3. Per case (deadline 240 s, fair share of the 3.75 h run budget):
   - **Parse** PDFs with `pdftotext -raw` (reading order; `-layout` interleaves table columns), fallback `pdfplumber`.
   - **Classify** each document by file name, corrected by keywords (pro-forma, credit note, grant).
   - **Extract** facts per document type into Pydantic schemas (`solver/schemas.py`), in parallel, with
     `reasoning_effort=low`; amounts the document does not print are discarded.
   - **Check** deterministic rules (`solver/checks/`), each `pass | fail | unclear` with detail and source.
   - **Retrieve** the wording of the curated rules (`solver/knowledge/*.yaml`, each citing corpus `doc_id`s)
     and BM25 passages for failed/unclear findings.
   - **Decide**: a hard `fail` rejects (the model writes the reason); otherwise the model decides on rules,
     findings, facts and documents. Model errors fall back to the checks alone.
4. Write `predictions.jsonl`, `run-trace.jsonl.log.gz`
   ([event-logging contract](../uniagent-code/cikm26/event-logging-contract/README.md)) and `run-stats.json`.

Institutions under another state's law (the dataset READMEs name Sallstedt) get no Kassel-specific hard checks.

## Configuration

```bash
export OPENAI_BASE_URL=https://your-endpoint/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-oss-20b
export OPENAI_REASONING_EFFORT=low   # optional, for the decision call
```

Ablation flags of `predict.py`: `--no-checks`, `--no-retrieval`, `--no-hard-fail-override`,
`--self-consistency N` (N decision samples when a check stays unclear), `--case-timeout S`.
`SOLVER_CACHE_DIR` caches LLM answers for local development only.

## Build, test, run (Docker only)

```bash
docker build --tag uniagent-solver .            # runs the tests (mock LLM, no data needed)
scripts/run_all_spot_checks.sh full             # all three spot-checks -> runs/full/, validates traces, evaluates
scripts/docker-run.sh python3 /app/scripts/validate_trace.py /app/runs/full/<dataset>
```

`scripts/docker-run.sh` mounts this directory at `/app` and `../uniagent-code/cikm26/datasets` at `/data`.

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

Remove `--dry-run` to submit; use the procurement/expense dataset names for the other spot-checks.
