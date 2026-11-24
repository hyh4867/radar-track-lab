#!/bin/bash
# Stage 5 regression (PREREGISTRATION_5 6): rerun stage 3/4 methods with the stage 5 code, 2 seeds.
# usage: stage5_regression.sh <lane A|B>; then scripts/stage5_regression_check.py
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
scripts/stage4_guard.sh
if [ "$1" = A ]; then
  $PY -u scripts/stage5_run.py --out regression --tag lam1000_map --scenarios EHAM_1106_eval --methods jipda,jipda_est \
    --model M0 --n-seeds 2 --set radar.clutter_lambda=1000 --set radar.clutter_model=map || exit 1
else
  $PY -u scripts/stage5_run.py --out regression --tag lam200_map --scenarios EHAM_1106_eval --methods jipda_map \
    --model M0 --n-seeds 2 --set radar.clutter_lambda=200 --set radar.clutter_model=map || exit 1
  $PY -u scripts/stage5_cone_run.py --scenarios EHAM_1106_eval,KATL_1106_peak --methods ekf,imm,ekf_cone,imm_cone \
    --n-seeds 2 --out results/stage5/regression/cone || exit 1
fi
echo "regression lane $1 done $(date '+%F %T')"
