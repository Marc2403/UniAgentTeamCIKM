#!/bin/bash
set -euo pipefail
main() {
project_dir="$(cd "$(dirname "$0")" && pwd)"
if command -v docker >/dev/null 2>&1; then
  default_docker_cli="docker"
else
  default_docker_cli="/Applications/Docker.app/Contents/Resources/bin/docker"
fi
docker_cli="${DOCKER_CLI:-$default_docker_cli}"
endpoint="${OPENAI_BASE_URL:-http://model-runner.docker.internal/engines/v1}"
if [ "$endpoint" = "http://model-runner.docker.internal/engines/v1" ]; then
  export OPENAI_API_KEY="${OPENAI_API_KEY:-local-unused}"
  export OPENAI_MODEL="${OPENAI_MODEL:-gareth/qwen2.5:7b-32k}"
  structured_output="${UNIAGENT_STRUCTURED_OUTPUT:-llamacpp}"
  max_output_tokens="${MAX_OUTPUT_TOKENS:-1024}"
else
  : "${OPENAI_API_KEY:?Set OPENAI_API_KEY privately before using a hosted endpoint}"
  : "${OPENAI_MODEL:?Set OPENAI_MODEL to your provider model ID}"
  export OPENAI_API_KEY OPENAI_MODEL
  structured_output="${UNIAGENT_STRUCTURED_OUTPUT:-off}"
  max_output_tokens="${MAX_OUTPUT_TOKENS:-8192}"
  export OPENAI_REASONING_EFFORT="${OPENAI_REASONING_EFFORT:-low}"
fi
export OPENAI_BASE_URL="$endpoint"
run_name="${RUN_NAME:-local-qwen-7b-$(date +%Y%m%d-%H%M%S)}"
if [ -e "$project_dir/runs/$run_name/predictions.jsonl" ]; then
  echo "Run already exists; choose a new RUN_NAME: $run_name" >&2
  exit 1
fi
input_dir="$(mktemp -d)"
trap 'rm -rf "$input_dir"' EXIT
for dataset in business-trip-spot-check task-2-expense-reimbursement-spot-check task-2-procurement-spot-check; do
  for source in "$project_dir/cikm26/datasets/$dataset/inputs/"*; do
    if [ -n "${CASE_IDS:-}" ] && [ "$(basename "$source")" != "retrieval-corpora" ]; then
      case ",${CASE_IDS}," in
        *",$(basename "$source"),"*) ;;
        *) continue ;;
      esac
    fi
    if [ "${SMOKE_TEST:-0}" = "1" ]; then
      case "$(basename "$source")" in
        retrieval-corpora|dienstreiseantrag-01|auslagenerstattung-01|beschaffungsantrag-01) ;;
        *) continue ;;
      esac
    fi
    if [ ! -e "$input_dir/$(basename "$source")" ]; then
      cp -R "$source" "$input_dir/"
    fi
  done
done
mkdir -p "$project_dir/runs/$run_name"
"$docker_cli" run --rm --platform linux/amd64 \
  --env OPENAI_BASE_URL \
  --env OPENAI_API_KEY \
  --env UNIAGENT_SNIPPET_MAX_CHARACTERS=700 \
  --env OPENAI_MODEL \
  --env OPENAI_REASONING_EFFORT \
  --env UNIAGENT_STRUCTURED_OUTPUT="$structured_output" \
  --volume "$input_dir:/input:ro" \
  --volume "$project_dir/runs/$run_name:/output" \
  gareth-uniagent-mvp --input /input --output /output --max-output-tokens "$max_output_tokens" --workers "${WORKERS:-2}"

}
main "$@"
