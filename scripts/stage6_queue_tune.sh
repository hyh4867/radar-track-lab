#!/bin/bash
# Stage 6 part 2 selection (PREREGISTRATION_6 8): EHAM_1106_tune, M0, seeds 20271106-20271110, lam5_map + lam1000_uniform.
# usage: <lane 0|1>
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--out tune --scenarios EHAM_1106_tune --model M0 --n-seeds 5 --set monte_carlo.base_seed=20271106"
L5="--set radar.clutter_lambda=5 --set radar.clutter_model=map"
LU="--set radar.clutter_lambda=1000 --set radar.clutter_model=uniform_range_azimuth"
scripts/stage4_guard.sh
if [ "$1" = 0 ]; then
  $PY -u scripts/stage6_run.py $COMMON --tag lam5_map --methods jipda,jipda_amap $L5 || exit 1
  for f in 0.25 0.5; do $PY -u scripts/stage6_run.py $COMMON --tag lam5_map__f$f --methods jipda_amap $L5 --set clutter_amap_est.floor_frac=$f || exit 1; done
  $PY -u scripts/stage6_run.py $COMMON --tag lam1000_uniform__f1.0 --methods jipda_amap $LU --set clutter_amap_est.floor_frac=1.0 || exit 1
else
  $PY -u scripts/stage6_run.py $COMMON --tag lam5_map__f1.0 --methods jipda_amap $L5 --set clutter_amap_est.floor_frac=1.0 || exit 1
  for f in 0.25 0.5; do $PY -u scripts/stage6_run.py $COMMON --tag lam1000_uniform__f$f --methods jipda_amap $LU --set clutter_amap_est.floor_frac=$f || exit 1; done
fi
echo "tune lane $1 done $(date '+%F %T')"
