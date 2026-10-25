#!/usr/bin/env bash
set -u
. /c/Users/marcm/AppData/Local/Temp/claude/C--Users-marcm-Desktop-CIKM/0c74be04-43c6-4507-9280-2164b5cf656c/scratchpad/env.sh
unset SOLVER_CACHE_DIR
cd /c/Users/marcm/Desktop/CIKM/uniagent-solver
scripts/run_all_spot_checks.sh r2-v3 > runs/r2.log 2>&1
scripts/run_all_spot_checks.sh r1-self-consistency --self-consistency 3 > runs/r1.log 2>&1
scripts/run_all_spot_checks.sh r3-no-retrieval --no-retrieval > runs/r3.log 2>&1
scripts/run_all_spot_checks.sh r4-no-checks --no-checks > runs/r4.log 2>&1
OPENAI_MODEL=qwen/qwen-2.5-7b-instruct scripts/run_all_spot_checks.sh r5-qwen > runs/r5.log 2>&1
echo ALL DONE
