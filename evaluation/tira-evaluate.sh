#!/usr/bin/env bash
# Score a run directory written by run-mvp.sh with `tira-cli evaluate` (truths and evaluator image from TIRA).
# Usage: TIRA_CLI=/path/to/tira-cli evaluation/tira-evaluate.sh evaluation/runs/<model>/<system>
set -uo pipefail
tira=${TIRA_CLI:-tira-cli}
declare -A ids=(
  [business-trip-spot-check]=uniagent-2026/business-trip-spot-check-20260907-training
  [task-2-procurement-spot-check]=uniagent-2026/task-2-procurement-spot-check-20260928-training
  [task-2-expense-reimbursement-spot-check]=uniagent-2026/task-2-expense-reimbursement-spot-check-20260928-training
)
for dataset in "${!ids[@]}"; do
  run="$1/$dataset"
  result=$(PYTHONIOENCODING=utf-8 "$tira" evaluate --dataset "${ids[$dataset]}" --predictions "$(cd "$run" && (pwd -W 2>/dev/null || pwd))" 2>&1 | grep -A1 '^Result:' | tail -1)
  echo "$dataset ${result:-FAILED}" | tee "$run/tira-evaluate.txt"
done
