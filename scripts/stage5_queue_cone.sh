#!/bin/bash
# Stage 5 part 2 (PREREGISTRATION_5 8.1): 13 windows, M4, EKF/IMM, 20 seeds. usage: <lane 0|1>
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
if [ "$1" = 0 ]; then W="EHAM_1106_eval KATL_1106_peak EGLL_1106_peak EGLL_1111_same EHAM_1106_busy2 EHAM_1111_same"
else W="KATL_1111_same ENGM_1106_peak ENGM_1111_same LSZH_1106_peak LSZH_1111_same YSSY_1106_peak YSSY_1111_same"; fi
for sid in $W; do
  scripts/stage4_guard.sh
  $PY -u scripts/stage5_cone_run.py --scenarios $sid --methods ekf,imm,ekf_cone,imm_cone,ekf_h1,imm_h1,ekf_h2,imm_h2 || exit 1
  case $sid in EHAM_1106_eval|KATL_1106_peak) ;; *) $PY -u scripts/stage5_cone_run.py --scenarios $sid --cond M4_nocone --methods ekf,imm || exit 1;; esac
done
echo "cone lane $1 done $(date '+%F %T')"
