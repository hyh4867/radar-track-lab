#!/bin/bash
# Stage 6 regression (PREREGISTRATION_6 6), 2 seeds; then scripts/stage6_regression_check.py
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
scripts/stage4_guard.sh
$PY -u scripts/stage6_cone_run.py --scenarios EHAM_1106_eval,KATL_1106_peak --methods ekf,imm,ekf_h1,imm_h1 \
  --n-seeds 2 --out results/stage6/regression/cone || exit 1
$PY -u scripts/stage6_run.py --out regression --tag lam200_map --scenarios EHAM_1106_eval --methods jipda_amap \
  --model M0 --n-seeds 2 --set radar.clutter_lambda=200 --set radar.clutter_model=map || exit 1
echo "regression done $(date '+%F %T')"
