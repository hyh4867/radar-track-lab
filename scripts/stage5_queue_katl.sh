#!/bin/bash
# Stage 5 generalisation (PREREGISTRATION_5 5.4): KATL_1106_peak, M0, seeds 20261106-20261113. usage: <lane 0|1>
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
RUN="$PY -u scripts/stage5_run.py --out katl --scenarios KATL_1106_peak --model M0 --n-seeds 8 --set radar.clutter_lambda=1000"
scripts/stage4_guard.sh
if [ "$1" = 0 ]; then
  $RUN --tag lam1000_uniform --methods jipda_amap,jipda,jipda_est --set radar.clutter_model=uniform_range_azimuth || exit 1
else
  $RUN --tag lam1000_map --methods jipda_amap --set radar.clutter_model=map || exit 1
fi
echo "katl lane $1 done $(date '+%F %T')"
