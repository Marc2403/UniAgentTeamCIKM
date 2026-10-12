#!/usr/bin/env bash
# Robustness run: the solver image against make_inputs.py's edge cases, once per misbehaving mock LLM mode.
# Usage: evaluation/robustness/run.sh <image> <out-dir> [modes...]   (default modes: garbage truncated error slow)
# Needs the Docker network uniagent-internal (docker network create --internal uniagent-internal).
set -uo pipefail
image=$1 out=$2; shift 2
modes=${*:-garbage truncated error slow}
host_path() { (cd "$1" && (pwd -W 2>/dev/null || pwd)); }
here="$(host_path "$(dirname "$0")")"
datasets="$(dirname "$0")/../../../uniagent-code/cikm26/datasets"
mkdir -p "$out/inputs"
python "$(dirname "$0")/make_inputs.py" "$datasets/task-2-procurement-spot-check/inputs" "$out/inputs"
for mode in $modes; do
  docker rm -f mockllm > /dev/null 2>&1
  MSYS_NO_PATHCONV=1 docker run -d --name mockllm --network uniagent-internal -e MODE="$mode" \
    -v "$here:/mock:ro" "$image" python3 /mock/mock_llm.py > /dev/null
  rm -rf "$out/$mode"; mkdir -p "$out/$mode"
  started=$(date +%s)
  MSYS_NO_PATHCONV=1 docker run --rm --cpus 4 --memory 40g --network uniagent-internal \
    -e OPENAI_BASE_URL=http://mockllm:8000/v1 -e OPENAI_API_KEY=mock -e OPENAI_MODEL=mock-llm \
    -v "$(host_path "$out/inputs"):/input:ro" -v "$(host_path "$out/$mode"):/output" \
    "$image" python3 /app/predict.py --input /input --output /output > "$out/$mode/stdout.log" 2>&1
  status=$?
  MSYS_NO_PATHCONV=1 docker run --rm -v "$(host_path "$out/$mode"):/run" "$image" python3 /app/scripts/validate_trace.py /run > "$out/$mode/validate.log" 2>&1
  echo "$mode: exit=$status seconds=$(( $(date +%s) - started )) predictions=$(wc -l < "$out/$mode/predictions.jsonl") trace=$(tail -1 "$out/$mode/validate.log" | sed 's/.*: //')"
  sed -n 's/^  \(.*\): \(.*\)$/    \1: \2/p' "$out/$mode/stdout.log"
done
docker rm -f mockllm > /dev/null 2>&1
