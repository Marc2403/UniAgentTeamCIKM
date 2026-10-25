# Smolagents Solving Baseline with Retrieval

This baseline extends `../solving-smolagents/` with retrieval-augmented
context from the background corpora shipped under
`inputs/retrieval-corpora/` (see the dataset README). It builds one BM25
retrieval tool per corpus using the same PyTerrier indexing approach as
`../retrieval-baseline-pyterrier/` (language-specific stemmer, stopwords, and
tokeniser), then folds the retrieved knowledge into the evidence package
handed to the model.

It handles all three UNIAGENT'26 "solving" task areas from a single
`predict.py`:

| Directory prefix | Task | Example spot-check dataset |
|---|---|---|
| `dienstreiseantrag-XX` | business-trip approval | [`business-trip-spot-check`](../../datasets/business-trip-spot-check) |
| `auslagenerstattung-XX` | reimbursement of privately advanced costs | [`task-2-expense-reimbursement-spot-check`](../../datasets/task-2-expense-reimbursement-spot-check) |
| `beschaffungsantrag-XX` | internal procurement | [`task-2-procurement-spot-check`](../../datasets/task-2-procurement-spot-check) |

Each application directory's name prefix (`case_type_for()` in
`case_tools.py`) selects the matching policy set, system prompt, and
retrieval/search keywords; an input directory with a name matching none of
the three prefixes fails explicitly instead of being processed with the
wrong rules. A single `--input` run may freely mix directories from
different task types. The same three retrieval corpora ship with all three
datasets, so `build_retrieval_tools()` and the retrieval loop are shared
unchanged across case types; only the case-type-specific prompts, policies,
and keywords (`CASE_TYPE_INFO` in `predict.py`, `POLICIES_BY_CASE_TYPE` in
`case_tools.py`) differ.

## Pipeline

`predict.py` runs in three phases:

1. **Scan all tasks.** `input_cases()` lists every application directory
   under `--input` matching one of the three prefixes above (the
   `retrieval-corpora/` folder is excluded automatically since it has no
   PDFs directly inside it).
2. **Identify the key accept/reject aspects via retrieval, for every case.**
   `build_retrieval_tools()` discovers every
   `retrieval-corpora/<name>/documents.jsonl.gz`, and builds a dedicated tool
   per corpus, e.g. `retrieve_hessian_law_de`,
   `retrieve_university_kassel_public_de`, `retrieve_university_kassel_public_en`
   (an index is built once per corpus and reused for every case). For every
   case, `identify_key_aspects()` runs an iterative retrieval loop instead of
   a single fixed lookup:
   - Round 1 queries every corpus with the application text combined with a
     fixed set of rule keywords, then asks the model (via a dedicated
     aspect-analysis prompt, separate from the final decision prompt) to name
     the aspects that decide the case, each grounded in a concrete
     `(corpus, doc_id)` citation from the retrieved hits — the model may not
     invent rules that aren't in the retrieved text.
   - If the model reports an aspect as unclear, it provides a short follow-up
     query, which drives the next retrieval round instead of the fixed query;
     retrieval stops as soon as the model reports the aspects are
     sufficiently clear, or after `RETRIEVAL_MAX_ITERATIONS` rounds (2-3;
     see `predict.py`), whichever comes first — so the extra iterations are
     only spent when the aspects are genuinely unclear.
   - Once the loop stops, the case's key aspects (short title, finding, and
     citation) are printed to stdout so the retrieval basis for the decision
     is visible without inspecting the tool-call log.
3. **Decide with knowledge and key aspects included.** The case evidence
   (documents, search results, policies, completeness check — same as the
   non-retrieval baseline) is extended with an `external_knowledge` list of
   all ranked, cited corpus hits seen across the retrieval rounds and a
   `key_aspects` list of the aspects identified above; the model is
   instructed to ground its decision in `key_aspects` and their citations
   (i.e. the correct law/policy for the case) rather than rules it might
   otherwise recall imprecisely, and to decide `angenommen`/`abgelehnt` as
   before.

The dataset README notes that the final test set may ship additional or
larger corpora (for instance an intranet crawl) that are not present in the
spot-check. `build_retrieval_tools()` discovers corpora at runtime instead of
hard-coding the three known folders, so it also builds a tool for any future
corpus automatically; only the corpus language must be inferable from a
`-de`/`-en` folder suffix or a `language` document field.

## Event-trace logging

Every tool call (case-scoped `list_case_documents`/`read_pdf`/`search_case`,
the global `lookup_policy`/`check_facts`, and every `retrieve_<corpus>`) and
every model call (the aspect-analysis pass and the final decision) is logged
as one contract-compliant event, per
[`../../event-logging-contract/README.md`](../../event-logging-contract/README.md),
via `event_logging.py`.

`predict.py` writes these events as one gzip-compressed JSON object per line
to `run-trace.jsonl.log.gz` next to `predictions.jsonl` under `--output` (opened
once via `log_to_file()` at the start of the run, so it captures events from
retrieval-tool building onward, and tagged with the configured
`OPENAI_MODEL` via `model_context()` for the whole run). The plain-text
progress messages `predict.py` prints (phase headers, per-case summaries) go
to stdout as before and are not part of this file. Tests and other callers
that don't use `log_to_file()` get the JSONL lines on stdout instead (the
default destination), e.g. pulled out of a combined stdout stream with
`zcat run-trace.jsonl.log.gz | jq` or `grep '"tool":' | jq`.

Each case's events are chained via `parent_event_id` from its first tool
call through retrieval, the aspect-analysis model call(s), the final
decision model call, and end in one `decision` event — reconstructable as a
per-`case_id` trace, as the contract requires.

Example lines (pretty-printed here; actually emitted as single lines):

```json
{"case_id": "dienstreiseantrag-01", "event_id": "evt-0002", "parent_event_id": "evt-0001", "timestamp": "2026-09-07T17:30:12.345+00:00", "event_type": "tool_call", "model": "gpt-oss-20b", "tool": "read_pdf", "input": {"case_id": "dienstreiseantrag-01", "filename": "antrag-dienstreisegenehmigung.pdf"}, "output": "Jonas Ahlgrim Universitaet Kassel ...", "status": "ok", "error": null}
{"case_id": "dienstreiseantrag-01", "event_id": "evt-0009", "parent_event_id": "evt-0008", "timestamp": "2026-09-07T17:30:14.201+00:00", "event_type": "tool_call", "model": "gpt-oss-20b", "tool": "retrieve_hessian_law_de", "input": {"query": "Lyon, FRANKREICH ...", "max_results": 5}, "output": "[{\"corpus\": \"hessian-law-de\", ...}]", "status": "ok", "error": null}
{"case_id": "dienstreiseantrag-01", "event_id": "evt-0015", "parent_event_id": "evt-0014", "timestamp": "2026-09-07T17:30:20.512+00:00", "event_type": "model_call", "model": "gpt-oss-20b", "tool": null, "input": {"prompt": "..."}, "output": {"response": "{\"aspects\": [...], \"sufficient\": true, ...}"}, "status": "ok", "error": null}
{"case_id": "dienstreiseantrag-03", "event_id": "evt-0022", "parent_event_id": "evt-0021", "timestamp": "2026-09-07T17:30:25.009+00:00", "event_type": "tool_call", "model": "gpt-oss-20b", "tool": "check_facts", "input": {"facts": {"kind": "compare_dates", "comparisons": [...]}}, "output": null, "status": "error", "error": "Unsupported date operator: !="}
{"case_id": "dienstreiseantrag-01", "event_id": "evt-0030", "parent_event_id": "evt-0029", "timestamp": "2026-09-07T17:30:31.777+00:00", "event_type": "decision", "model": "gpt-oss-20b", "tool": null, "input": null, "output": {"antrag": "dienstreiseantrag-01", "result": "abgelehnt", "begruendung": "..."}, "status": "ok", "error": null}
```

Field-by-field details (`case_id`, `event_id`, `parent_event_id`,
`timestamp`, `event_type`, `model`, `tool`, `input`, `output`, `status`,
`error`) are specified in the contract; `model` is always the run's
configured `OPENAI_MODEL`, on every event, not only `model_call`/`decision`
events.

**Truncation rule** (applied to each `input`/`output` value, mirroring the
prior tool-call-only convention): string values are whitespace-normalised
and cut to 200 characters with a trailing `…`. Other JSON values (numbers,
booleans, `null`, lists, dicts) are kept as native JSON when their JSON
encoding is at most 200 characters (so small structured inputs like
`check_facts`' `facts` object stay queryable, e.g.
`jq 'select(.input.facts.kind == "compare_dates")'`); larger ones fall back
to a truncated string preview of their JSON encoding. Errors are always
logged in full (not swallowed) so a failing call is never silently missing
from the log.

Because the tool is wrapped once in `build_tools()`/`build_retrieval_tools()`,
this works uniformly whether a tool is rebuilt per case (the case tools) or
built once and reused across all cases (the retrieval tools) — the shared
retrieval tools are simply tagged with whichever case is currently active
when they are called.

### Handling invalid model output

Models occasionally answer with text that is not the required strict JSON
object (extra prose, markdown fences, or truncated output), both during
aspect analysis and the final decision. `_call_model_expecting_json()`
handles this without crashing the run or leaving `predictions.jsonl`
incomplete:

- a response that fails to parse logs an `error` event and is retried once
  with a corrective follow-up message;
- in `identify_key_aspects()`, if the retry still fails, retrieval for that
  case stops with whatever aspects/knowledge were already gathered instead
  of raising;
- in `decide_case()`, if the retry still fails (or any other unexpected
  error occurs while processing the case, e.g. a tool call raising), a safe
  fallback `decision` (`abgelehnt`, with the parse error as `begruendung`)
  is logged with `status: "error"` and written to `predictions.jsonl`, so
  every case still gets exactly one valid prediction line and every trace
  still ends in a `decision` event.

## Configuration

Set an OpenAI-compatible proxy or endpoint:

```bash
export OPENAI_BASE_URL=https://your-proxy.example/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=your-model
# Optional for reasoning models:
export OPENAI_REASONING_EFFORT=low
```

Use a dedicated, short-lived proxy credential rather than a production API
key. TIRA requires network access for this baseline.

## Run locally

```bash
docker build --tag solving-smolagents-with-retrieval .
docker run --rm \
  --env OPENAI_BASE_URL \
  --env OPENAI_API_KEY \
  --env OPENAI_MODEL \
  --env OPENAI_REASONING_EFFORT \
  --volume "$PWD/../../datasets/business-trip-spot-check/inputs:/input:ro" \
  --volume "$PWD/output:/output" \
  solving-smolagents-with-retrieval \
  --input /input \
  --output /output
```

Point `--volume` at any of the three datasets' `inputs/` directory (see the
table above) to run the same image against expense-reimbursement or
procurement cases instead; no other change is needed.

## Submit to TIRA

The following command can be used to submit the solution to TIRA (Please remove the `--dry-run` flag to submit to TIRA):

```bash
tira-cli code-submission \
  --path . \
  --task uniagent-2026 \
  --dataset business-trip-spot-check-20260907-training \
  --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL \
  --command '/app/predict.py --input $inputDataset --output $outputDir' \
  --dry-run
```

The same image and command work unchanged for the expense-reimbursement and
procurement datasets; only `--dataset` needs to point at the target dataset's
name.

## Run the spot-check datasets for the solving task on your machine (for fast evaluation)

`run_and_evaluate_all_tasks.py` automates the above for all three datasets in
one go: for each, it runs the same `tira-cli code-submission --dry-run`
command shown above in a subshell, extracts the local directory holding that
run's results from tira-cli's output, evaluates it with
`tira-cli evaluate` (as documented in
[`../../datasets/README.md`](../../datasets/README.md)), and prints each
task's accuracy:

```bash
export OPENAI_BASE_URL=https://your-proxy.example/v1
export OPENAI_API_KEY=...
export OPENAI_MODEL=your-model
./run_and_evaluate_all_tasks.py
```

It requires `tira-cli` (with network access to TIRA to fetch each dataset)
and Docker; a failure on one dataset is reported but does not stop the
others from being tried, and the script exits non-zero if any dataset
failed.

## Tests

The tests build real BM25 indices over the shipped corpora and exercise the
full retrieval and evidence pipeline for all three case types (business-trip,
expense-reimbursement, procurement) without calling an LLM. They require
Java/PyTerrier, so run them inside the Docker image, as for
`../retrieval-baseline-pyterrier/`:

```bash
docker build --tag solving-smolagents-with-retrieval .
docker run --rm \
  --volume "$PWD/../..:/cikm26:ro" \
  --entrypoint python3 \
  solving-smolagents-with-retrieval \
  -m unittest discover \
  -s /cikm26/baselines/solving-smolagents-with-retrieval \
  -p 'test_*.py'
```

