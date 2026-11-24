#!/bin/bash
# Stage 5 selection runs (PREREGISTRATION_5 4): EHAM_1106_tune, M0, seeds 20271106-20271110,
# lam1000_map and lam1000_uniform. usage: stage5_queue_tune.sh <lane 0|1>
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
COMMON="--out tune --scenarios EHAM_1106_tune --model M0 --n-seeds 5 --set radar.clutter_lambda=1000 --set monte_carlo.base_seed=20271106"
if [ "$1" = 0 ]; then UNITS="ref:uniform n20_30:uniform n20_30:map n5_100:uniform n5_100:map"; else UNITS="n5_30:uniform n5_30:map n20_100:uniform n20_100:map"; fi
for u in $UNITS; do
  scripts/stage4_guard.sh
  cand=${u%%:*}; cm=${u##*:}
  if [ "$cm" = map ]; then CM=map; else CM=uniform_range_azimuth; fi
  if [ "$cand" = ref ]; then
    $PY -u scripts/stage5_run.py $COMMON --tag lam1000_$cm --methods jipda --set radar.clutter_model=$CM || exit 1
  else
    IFS=_ read -r n tau <<< "${cand#n}"
    $PY -u scripts/stage5_run.py $COMMON --tag lam1000_${cm}__$cand --methods jipda_amap --set radar.clutter_model=$CM \
      --set clutter_amap_est.n_min=$n --set clutter_amap_est.tau_scans=$tau || exit 1
  fi
done
echo "tune lane $1 done $(date '+%F %T')"
