#!/bin/bash
# Stage 4 selection runs (PREREGISTRATION_4 4): tuning window, lam1000_map, seeds 20271106-20271110.
# usage: stage4_queue_tune.sh <lane 0|1>  (two lanes = two processes)
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--out tune --scenarios EHAM_1106_tune --model M0 --n-seeds 5 --set radar.clutter_lambda=1000 --set radar.clutter_model=map --set monte_carlo.base_seed=20271106"
if [ "$1" = 0 ]; then UNITS="ref:jipda c2_3_100 c1_1.5_30 c2_1.5_100 c1_3_30"; else UNITS="ref:jipda_est c2_3_30 c1_1.5_100 c2_1.5_30 c1_3_100"; fi
for u in $UNITS; do
  scripts/stage4_guard.sh
  if [[ $u == ref:* ]]; then
    $PY -u scripts/stage4_run.py $COMMON --tag lam1000_map --methods ${u#ref:} || exit 1
  else
    IFS=_ read -r dr daz tau <<< "${u#c}"
    $PY -u scripts/stage4_run.py $COMMON --tag lam1000_map__$u --methods jipda_map \
      --set clutter_map_est.dr_m=$((dr*1000)) --set clutter_map_est.daz_deg=$daz --set clutter_map_est.tau_scans=$tau || exit 1
  fi
done
echo "lane $1 done $(date '+%F %T')"
