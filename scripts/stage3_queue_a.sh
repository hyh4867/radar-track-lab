#!/bin/bash
# Stage 3 driver: regression after implementation, then A in two jobs. Each job takes the heavy-work lock
# separately (tools/heavy-run.sh) and starts only when free memory >= 15% (PREREGISTRATION_3 7.4).
set -uo pipefail
cd "$(dirname "$0")/.."
HR=../../tools/heavy-run.sh
PY=.venv/bin/python
wait_mem() { $PY -c "import sys; sys.path.insert(0,'src'); from radar_track_lab.runtime import wait_for_memory; wait_for_memory()"; }
stamp() { date '+%F %T %z'; }
echo "regression start $(stamp)"; wait_mem
$HR $PY -u scripts/stage3_regression.py --out results/stage3/regression_after_impl.json || { echo "regression FAILED, stop"; exit 1; }
$PY -c "import json,sys; d=json.load(open('results/stage3/regression_after_impl.json')); sys.exit(0 if d['all_pass'] else 1)" \
  || { echo "regression did not reproduce stages 1-2, stop before A"; exit 1; }
echo "A part 1 start $(stamp)"; wait_mem
$HR bash -c 'for s in EHAM_1106_eval KATL_1106_peak EGLL_1106_peak LSZH_1106_peak YSSY_1106_peak ENGM_1106_peak EHAM_1106_busy2 EHAM_1106_early; do .venv/bin/python -u scripts/stage3_a_run.py --scenario $s || exit 1; done'
echo "A part 2 start $(stamp)"; wait_mem
$HR bash -c 'for s in EHAM_1106_night EHAM_1111_same EGLL_1111_same KATL_1111_same LSZH_1111_same YSSY_1111_same ENGM_1111_same; do .venv/bin/python -u scripts/stage3_a_run.py --scenario $s || exit 1; done
.venv/bin/python -u scripts/stage3_run.py --out a_noslant --tag M2_noslant --model M2_noslant --scenarios EHAM_1106_eval --methods ekf,imm
.venv/bin/python -u scripts/stage3_run.py --out a_noslant --tag M2 --model M2 --scenarios EHAM_1106_eval --methods ekf,imm'
echo "A finished $(stamp)"
