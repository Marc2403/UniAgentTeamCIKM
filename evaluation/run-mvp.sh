#!/usr/bin/env bash
# Run one solver image on the three Task 2 spot-check datasets and evaluate each run with the
# official evaluator image (cikm26-evaluation, built from uniagent-code/cikm26/evaluation).
# Usage: evaluation/run-mvp.sh <name> <image> <out-root> [network] -- <command and args before --input>
# The command gets `--input /input --output /output` appended. OPENAI_*, SOLVER_* and HTTPS_PROXY are forwarded.
set -uo pipefail
name=$1 image=$2 out_root=$3 network=${4:-bridge}
shift 4; [[ ${1:-} == -- ]] && shift
host_path() { (cd "$1" && (pwd -W 2>/dev/null || pwd)); }
datasets="$(host_path "$(dirname "$0")/../../uniagent-code/cikm26/datasets")"
mkdir -p "$out_root/$name"
for dataset in business-trip-spot-check task-2-procurement-spot-check task-2-expense-reimbursement-spot-check; do
  out="$out_root/$name/$dataset"; rm -rf "$out"; mkdir -p "$out"
  started=$(date +%s)
  MSYS_NO_PATHCONV=1 timeout 14400 docker run --rm --cpus 4 --memory 40g --network "$network" \
    --env OPENAI_BASE_URL --env OPENAI_API_KEY --env OPENAI_MODEL --env OPENAI_REASONING_EFFORT \
    --env UNIAGENT_STRUCTURED_OUTPUT=off --env HTTPS_PROXY $(env | grep -o '^SOLVER_[A-Z_]*' | sed 's/^/--env /') \
    --volume "$datasets/$dataset/inputs:/input:ro" --volume "$(host_path "$out"):/output" \
    "$image" "$@" --input /input --output /output > "$out/stdout.log" 2>&1
  status=$?
  echo "{\"exit_code\": $status, \"wall_seconds\": $(( $(date +%s) - started ))}" > "$out/run.json"
  MSYS_NO_PATHCONV=1 docker run --rm --volume "$(host_path "$out"):/predictions:ro" \
    --volume "$datasets/$dataset:/truths:ro" cikm26-evaluation \
    --predictions /predictions --task solving --truths /truths > "$out/evaluation.json" 2> "$out/evaluation.err"
  echo "$name $dataset exit=$status $(tr -d '\n ' < "$out/evaluation.json") $(cat "$out/run.json")"
done
