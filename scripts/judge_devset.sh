#!/usr/bin/env bash
# Pool the top-10 of all runs on a dev set and judge them with UMBRELA + gpt-oss-20b,
# exactly as the organisers build qrels (uniagent-code/cikm26/dataset-construction).
#
# Usage: scripts/judge_devset.sh <devset: de|en|law> <spot-check dataset dir providing the documents>
# Needs OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL and runs under runs/devset-<devset>/.
set -euo pipefail

devset="$1"
documents_dir="$(cd "$2" && pwd)"
root="$(cd "$(dirname "$0")/.." && pwd)"
construction="$root/../uniagent-code/cikm26/dataset-construction"
: "${OPENAI_BASE_URL:?}" "${OPENAI_API_KEY:?}" "${OPENAI_MODEL:?}"

docker build --quiet --file "$construction/.devcontainer/Dockerfile.dev" --tag uniagent-dataset-construction-dev "$construction"

input="$(mktemp -d)"
cp "$root/eval/devsets/$devset/queries.jsonl" "$input/"
cp "$documents_dir"/documents.jsonl.gz "$input/"

docker run --rm \
  --env OPENAI_BASE_URL --env OPENAI_API_KEY --env OPENAI_MODEL \
  --volume "$construction:/construction:ro" \
  --volume "$input:/dataset:ro" \
  --volume "$root/runs/devset-$devset:/runs:ro" \
  --volume "$root/eval/devsets/$devset/umbrela:/output" \
  --workdir /construction \
  uniagent-dataset-construction-dev \
  python create_qrels.py --dataset /dataset --runs /runs --k 10 --output /output

cp "$root/eval/devsets/$devset/umbrela/qrels.txt" "$root/eval/devsets/$devset/qrels.txt"
rm -rf "$input"
echo "Wrote eval/devsets/$devset/qrels.txt"
