# Gareth MVP — review package, 7 October 2026

Build assistant: Codex. Runtime: openai/gpt-oss-20b via OpenRouter.

The full 21-case run matched 21/21 supplied labels, but two cases were error fallbacks. This is not 21 successful model decisions and must not be reported as an error-free benchmark.

A subsequent two-case run used low reasoning effort. Expense 07 and Procurement 04 both returned correct model decisions without fallback. Procurement 04 required one JSON-format repair; the trace retains this recovered error. The two runs use different settings/code and are preserved separately, not merged into a benchmark.

Validation: 76 local tests passed before the reasoning configuration change; 31 relevant tests passed after that change. Live retest: 2/2 correct, three successful model calls with token usage, one recovered formatting error, no final decision fallback.

Pending: a complete run of the final configuration, official trace evaluation, TIRA dry-run, and the team's shared-model comparison runs. This is a review package, not confirmation of formal submission readiness or hidden-test performance.

## Build and run

Docker Desktop must be running. Build from this package:

    docker build --platform linux/amd64 -t gareth-uniagent-mvp ./agent

Load your own provider key privately in Terminal. Do not put it in source, Jira, or the image. Set OPENAI_BASE_URL=https://openrouter.ai/api/v1, OPENAI_MODEL=openai/gpt-oss-20b, OPENAI_REASONING_EFFORT=low.

Run with an input directory containing case folders and retrieval-corpora:

    docker run --rm --platform linux/amd64 -e OPENAI_BASE_URL -e OPENAI_API_KEY -e OPENAI_MODEL -e OPENAI_REASONING_EFFORT -e UNIAGENT_STRUCTURED_OUTPUT=off -v /absolute/path/to/inputs:/input:ro -v /absolute/path/to/output:/output gareth-uniagent-mvp --input /input --output /output --workers 1 --max-output-tokens 8192

Outputs: predictions.jsonl and run-trace.jsonl.log.gz. Spot-check fixtures are available in the official repository https://github.com/uniagent-webis-de/uniagent-code under cikm26/datasets. They are not duplicated in this small package. The copied run-local.sh and evaluate-local.py expect the original cikm26/datasets layout beside them; the Docker command above works with any supplied dataset.

No API key is included. All evidence comes from public development spot-check cases. No hosted requests are made by opening or building this package.
