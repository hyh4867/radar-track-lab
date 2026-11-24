#!/bin/bash
# Stage 4 generalisation check (PREREGISTRATION_4 5.4, 10): KATL_1106_peak lam1000_map, JIPDA / JIPDA-est / JIPDA-map.
# usage: stage4_queue_katl.sh pilot <lane>   (seed 20261106 only; lane 0 jipda_map, lane 1 jipda,jipda_est)
#        stage4_queue_katl.sh main <lane>    (n = 8: lane 0 jipda_map seeds ..20261111; lane 1 jipda,jipda_est 8 seeds
#                                             then jipda_map seeds 20261112-20261113 -> katl_p2/)
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
RUN="$PY -u scripts/stage4_run.py --scenarios KATL_1106_peak --model M0 --tag lam1000_map --set radar.clutter_lambda=1000 --set radar.clutter_model=map"
scripts/stage4_guard.sh
if [ "$1" = pilot ]; then
  if [ "$2" = 0 ]; then $RUN --out katl --n-seeds 1 --methods jipda_map || exit 1
  else $RUN --out katl --n-seeds 1 --methods jipda,jipda_est || exit 1; fi
else
  if [ "$2" = 0 ]; then $RUN --out katl --n-seeds 6 --methods jipda_map || exit 1
  else
    $RUN --out katl --n-seeds 8 --methods jipda,jipda_est || exit 1
    scripts/stage4_guard.sh
    $RUN --out katl_p2 --n-seeds 2 --set monte_carlo.base_seed=20261112 --methods jipda_map || exit 1
  fi
fi
echo "katl $1 lane $2 done $(date '+%F %T')"
