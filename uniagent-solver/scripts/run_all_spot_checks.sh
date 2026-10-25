#!/usr/bin/env bash
# Run predict.py in Docker on all three spot-check datasets, validate the traces and evaluate.
# Usage: scripts/run_all_spot_checks.sh <run-name> [predict.py options, e.g. --no-retrieval]
# Needs OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL in the environment. Results: runs/<run-name>/<dataset>/.
set -euo pipefail
name="$1"
shift
cd "$(dirname "$0")/.."
datasets=(business-trip-spot-check task-2-procurement-spot-check task-2-expense-reimbursement-spot-check)
outputs=()
pairs=()
for dataset in "${datasets[@]}"; do
  scripts/docker-run.sh python3 /app/predict.py --input "/data/$dataset/inputs" --output "/app/runs/$name/$dataset" "$@"
  outputs+=("/app/runs/$name/$dataset")
  pairs+=(--run "/app/runs/$name/$dataset" --truth "/data/$dataset/ground-truth.jsonl")
done
scripts/docker-run.sh python3 /app/scripts/validate_trace.py "${outputs[@]}"
scripts/docker-run.sh python3 /app/scripts/evaluate_local.py "${pairs[@]}" | tee "runs/$name/evaluation.md"
