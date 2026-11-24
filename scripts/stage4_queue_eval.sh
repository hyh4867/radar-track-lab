#!/bin/bash
# Stage 4 evaluation (PREREGISTRATION_4 5.1), after clutter_map_est is frozen and committed. usage: <lane 0|1>
# Verdict conditions first (lam5, lam1000_map), then the "no loss" conditions. Slow conditions are split by seed:
# lane 0 seeds 20261106-20261115 -> eval/, lane 1 seeds 20261116-20261125 -> eval_p2/ (scripts/stage4_merge.py).
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
grep -q "^clutter_map_est:" configs/stage4.yaml || { echo "clutter_map_est not frozen; stop"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no configs/stage4.yaml)" ] || { echo "configs/stage4.yaml not committed; stop"; exit 1; }
RUN="$PY -u scripts/stage4_run.py --scenarios EHAM_1106_eval --model M0"
full() { scripts/stage4_guard.sh; $RUN --out eval --tag $1 --methods $2 --set radar.clutter_lambda=$3 --set radar.clutter_model=$4 || exit 1; }
half() {
  scripts/stage4_guard.sh
  if [ "$LANE" = 0 ]; then $RUN --out eval --tag $1 --methods $2 --n-seeds 10 --set radar.clutter_lambda=$3 --set radar.clutter_model=$4 || exit 1
  else $RUN --out eval_p2 --tag $1 --methods $2 --n-seeds 10 --set monte_carlo.base_seed=20261116 --set radar.clutter_lambda=$3 --set radar.clutter_model=$4 || exit 1; fi
}
LANE=$1
if [ "$LANE" = 0 ]; then
  full lam5_uniform jipda_map 5 uniform_range_azimuth
  full lam5_uniform jipda_est 5 uniform_range_azimuth
else
  full lam5_map jipda_map 5 map
  full lam5_map jipda_est 5 map
fi
half lam1000_map jipda_map 1000 map
half lam1000_uniform jipda_map 1000 uniform_range_azimuth
half lam200_map jipda_map 200 map
half lam200_map jipda_est 200 map
echo "eval lane $LANE done $(date '+%F %T')"
