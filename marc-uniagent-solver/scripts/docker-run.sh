#!/usr/bin/env bash
# Run a command in the uniagent-solver image with this working copy at /app and the
# organisers' datasets at /data, limited to the TIRA budget of 4 CPUs.
# Example: scripts/docker-run.sh python3 /app/scripts/evaluate_local.py --help
set -euo pipefail
# `pwd -W` gives the Windows path Docker Desktop needs under Git Bash; plain `pwd` elsewhere.
host_path() { (cd "$1" && (pwd -W 2>/dev/null || pwd)); }
root="$(host_path "$(dirname "$0")/..")"
data="$(host_path "$(dirname "$0")/../../uniagent-code/cikm26/datasets")"
MSYS_NO_PATHCONV=1 exec docker run --rm --cpus 4 --memory 40g \
  --env OPENAI_BASE_URL --env OPENAI_API_KEY --env OPENAI_MODEL --env OPENAI_REASONING_EFFORT --env SOLVER_CACHE_DIR \
  --volume "$root:/app" --volume "$data:/data:ro" \
  --workdir /app uniagent-solver "$@"
