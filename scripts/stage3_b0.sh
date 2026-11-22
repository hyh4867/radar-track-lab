#!/bin/bash
# Stage 3, B0: fixed 6 km pre-gate vs adaptive pre-gate (docs/PREREGISTRATION_3.md 4.1). Run inside tools/heavy-run.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=".venv/bin/python -u scripts/stage3_run.py --out b0 --no-stage3-yaml"
OOS=$(ls results/data/stage2/runs/*__ekf.json | xargs -n1 basename | sed 's/__ekf.json//' | paste -sd, -)  # the 14 stage 2 scenarios
echo "scenarios: $OOS"
# 1. brute-force check on real scenes: adaptive must equal no pre-gate (2 seeds)
for lam in 5 200; do
  for pg in adaptive none; do
    $PY --tag check_lam${lam}_${pg} --scenarios EHAM_1106_eval --methods ekf,imm --n-seeds 2 \
        --set radar.clutter_lambda=$lam --set tracker.pregate=$pg
  done
done
# 2. Schiphol eval window, three clutter levels
for lam in 5 200 1000; do
  for pg in fixed adaptive; do
    $PY --tag lam${lam}_${pg} --scenarios EHAM_1106_eval --methods ekf,imm \
        --set radar.clutter_lambda=$lam --set tracker.pregate=$pg
  done
done
# 3. all stage 2 scenarios at lambda 5
for pg in fixed adaptive; do
  $PY --tag lam5_${pg} --scenarios "$OOS" --methods ekf,imm --set radar.clutter_lambda=5 --set tracker.pregate=$pg
done
echo "B0 finished $(date '+%F %T %z')"
