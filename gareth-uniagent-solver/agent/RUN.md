# Gareth’s single-pass agent

The Docker entrypoint is predict_fast.py. It extracts case PDFs and retrieves policy
excerpts deterministically, then makes one decision-model call per case (one repair
attempt on invalid outputs). It validates citation source identity and preserves
final decision evidence. It does not prove that evidence logically supports a claim.
The inherited multi-stage pipeline is retained in predict.py for comparison.

Build from this directory:

    docker build --tag gareth-uniagent-mvp .

Run the tests (mount the cikm26 directory so tests can find sample inputs):

    docker run --rm --platform linux/amd64 --volume "$PWD/../..:/cikm26:ro" --entrypoint python3 gareth-uniagent-mvp -m unittest discover -s /cikm26/baselines/gareth-agent -p 'test_*.py'

From the project root, ./run-local.sh runs all 21 cases with the local Qwen2.5 7B
model, 700-character policy excerpts, two workers and 1024 output tokens per call.
Set RUN_NAME to the generated run directory name when invoking ./evaluate-local.py. It sorts predictions by application ID, uses the official Task 2 evaluator and checks the reported accuracy independently by ID.
The excerpt budget and local model are development settings. The run script chooses a fresh timestamped directory by default and refuses to overwrite existing predictions. Two workers improve throughput on a local model service
that supports concurrent requests; the default is one worker.

For a hosted development endpoint or TIRA, supply OPENAI_BASE_URL,
OPENAI_API_KEY and OPENAI_MODEL. The same program runs as:

    /app/predict_fast.py --input /input --output /output --workers 1

TIRA dry-run template (must use your actual dataset and endpoint configuration):

    tira-cli code-submission --path . --task uniagent-2026 --dataset business-trip-spot-check-20260907-training --forward-environment-variable OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL --command '/app/predict_fast.py --input $inputDataset --output $outputDir' --dry-run

Do not put a real API key into this document or Git. The local Docker model requires
only a placeholder key. Formal comparison still requires the agreed runtime model,
at least three runs, the team’s evaluation script and its results ledger.

Structured output is optional: set UNIAGENT_STRUCTURED_OUTPUT=llamacpp for Docker Model Runner's schema-constrained JSON, or openai for an endpoint supporting strict JSON Schema. Default off preserves compatibility with other endpoints. An unsupported mode produces an explicit error; there is no silent unconstrained retry. Syntax and source identity do not establish correct reasoning. The project-root run-sample.sh selects case 01 from each task area and uses the downloaded 7B model with one worker; it supplies no ground truths to the agent. This three-case development sample is not a full accuracy benchmark.

The current review writes its explanation before selecting the decision. Expense approvals must select internal duty_evidence from a source-bound list of excerpts extracted from the case text. Each excerpt identifies an institution or explicit work-use marker and is already verified, including PDF column text. Freehand quotes are not required in structured mode. It is preserved in the trace; predictions retain the three official fields. This is a necessary evidence check, not proof that every reimbursement condition holds. The original multi-stage path does not enable this new expense check.
