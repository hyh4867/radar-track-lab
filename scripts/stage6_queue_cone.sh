#!/bin/bash
# Stage 6 part 1 (PREREGISTRATION_6 7): 13 windows, M4, EKF/IMM, 20 seeds; no-error M4/H1/H1+G1 and R (M4_err) H1/H1+G1.
# usage: <lane 0|1>
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
if [ "$1" = 0 ]; then W="KATL_1106_peak EHAM_1106_eval EGLL_1106_peak EGLL_1111_same EHAM_1106_busy2 EHAM_1111_same"
else W="KATL_1111_same ENGM_1106_peak ENGM_1111_same LSZH_1106_peak LSZH_1111_same YSSY_1106_peak YSSY_1111_same"; fi
for sid in $W; do
  scripts/stage4_guard.sh
  $PY -u scripts/stage6_cone_run.py --scenarios $sid --methods ekf,imm,ekf_h1,imm_h1,ekf_g1,imm_g1 || exit 1
  $PY -u scripts/stage6_cone_run.py --scenarios $sid --cond M4_err --methods ekf_h1,imm_h1,ekf_g1,imm_g1 || exit 1
done
echo "cone lane $1 done $(date '+%F %T')"
