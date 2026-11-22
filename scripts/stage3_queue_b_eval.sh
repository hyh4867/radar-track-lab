#!/bin/bash
# Stage 3 B evaluation driver (PREREGISTRATION_3 4.3, 4.4, 7.3), launched after the JIPDA parameters are frozen.
# User time limit (2026-11-21): if B1 cannot START by 2026-11-22 16:00 KST, run only GNN reference + JIPDA,
# 10 seeds, lambda 5 and 1000 uniform + clutter map; Stone Soup (b) lambda 5 only. Recorded as deviations.
set -uo pipefail
cd "$(dirname "$0")/.."
HR=../../tools/heavy-run.sh
PY=.venv/bin/python
wait_mem() { $PY -c "import sys; sys.path.insert(0,'src'); from radar_track_lab.runtime import wait_for_memory; wait_for_memory()"; }
grep -q "^jipda:" configs/stage3.yaml || { echo "jipda block not frozen in configs/stage3.yaml; stop"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no configs/stage3.yaml)" ] || { echo "configs/stage3.yaml not committed; stop"; exit 1; }
CUTOFF=$(date -j -f "%Y-%m-%d %H:%M" "2026-11-22 16:00" +%s)
wait_mem
NOW=$(date +%s)
if [ "$NOW" -lt "$CUTOFF" ]; then MODE=full; else MODE=reduced; fi
echo "B mode: $MODE ($(date '+%F %T %z'))"
RUN="$PY -u scripts/stage3_run.py --out b1 --model M0"
if [ "$MODE" = full ]; then
  # split so that no single job exceeds the 2 h limit (PREREGISTRATION_3 5)
  $HR bash -c "
  for lam in 5 200; do
    $RUN --tag lam\${lam}_uniform --scenarios EHAM_1106_eval --methods ekf,jpda,jipda --set radar.clutter_lambda=\$lam || exit 1
    $RUN --tag lam\${lam}_map --scenarios EHAM_1106_eval --methods ekf,jpda,jipda --set radar.clutter_lambda=\$lam --set radar.clutter_model=map || exit 1
  done
  $RUN --tag lam1000_uniform --scenarios EHAM_1106_eval --methods ekf,jipda --set radar.clutter_lambda=1000 || exit 1
  $RUN --tag lam1000_map --scenarios EHAM_1106_eval --methods ekf,jipda --set radar.clutter_lambda=1000 --set radar.clutter_model=map"
  echo "B1 job 1 done $(date '+%F %T %z')"; wait_mem
  $HR bash -c "$RUN --tag lam1000_uniform --scenarios EHAM_1106_eval --methods jpda --set radar.clutter_lambda=1000"
  echo "B1 job 2 done $(date '+%F %T %z')"; wait_mem
  $HR bash -c "$RUN --tag lam1000_map --scenarios EHAM_1106_eval --methods jpda --set radar.clutter_lambda=1000 --set radar.clutter_model=map"
  echo "B1 job 3 done $(date '+%F %T %z')"; wait_mem
  $HR bash -c "$RUN --tag lam1000_uniform --scenarios EHAM_1106_eval --methods jipda_est --set radar.clutter_lambda=1000
  $RUN --tag lam1000_map --scenarios EHAM_1106_eval --methods jipda_est --set radar.clutter_lambda=1000 --set radar.clutter_model=map"
  echo "B1 job 4 done $(date '+%F %T %z')"; wait_mem
  $HR bash -c "$PY -u scripts/stage3_nees.py; $PY -u scripts/stage3_stonesoup_b.py --lams 5,200,1000; $PY -u scripts/stage3_stonesoup_b.py --lams 200 --seeds 1 --analytic-jacobian"
else
  $HR bash -c "
  for lam in 5 1000; do
    $RUN --tag lam\${lam}_uniform --scenarios EHAM_1106_eval --methods ekf,jipda --n-seeds 10 --set radar.clutter_lambda=\$lam || exit 1
    $RUN --tag lam\${lam}_map --scenarios EHAM_1106_eval --methods ekf,jipda --n-seeds 10 --set radar.clutter_lambda=\$lam --set radar.clutter_model=map || exit 1
  done
  $PY -u scripts/stage3_stonesoup_b.py --lams 5"
fi
echo "B finished ($MODE) $(date '+%F %T %z')"
