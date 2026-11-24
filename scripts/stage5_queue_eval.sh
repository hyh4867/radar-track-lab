#!/bin/bash
# Stage 5 evaluation (PREREGISTRATION_5 5.1), after clutter_amap_est is frozen and committed. usage: <lane 0|1>
# Slow conditions are split by seed: lane 0 seeds 20261106-20261115 -> eval/, lane 1 20261116-20261125 -> eval_p2/
# (scripts/stage5_merge.py eval).
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
grep -q "n_min: [0-9]" configs/stage5.yaml || { echo "clutter_amap_est not frozen; stop"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no configs/stage5.yaml)" ] || { echo "configs/stage5.yaml not committed; stop"; exit 1; }
RUN="$PY -u scripts/stage5_run.py --scenarios EHAM_1106_eval --model M0 --methods jipda_amap"
full() { scripts/stage4_guard.sh; $RUN --out eval --tag $1 --set radar.clutter_lambda=$2 --set radar.clutter_model=$3 || exit 1; }
half() {
  scripts/stage4_guard.sh
  if [ "$LANE" = 0 ]; then $RUN --out eval --tag $1 --n-seeds 10 --set radar.clutter_lambda=$2 --set radar.clutter_model=$3 || exit 1
  else $RUN --out eval_p2 --tag $1 --n-seeds 10 --set monte_carlo.base_seed=20261116 --set radar.clutter_lambda=$2 --set radar.clutter_model=$3 || exit 1; fi
}
LANE=$1
if [ "$LANE" = 0 ]; then full lam5_uniform 5 uniform_range_azimuth; else full lam5_map 5 map; fi
half lam1000_uniform 1000 uniform_range_azimuth
half lam200_map 200 map
half lam1000_map 1000 map
echo "eval lane $LANE done $(date '+%F %T')"
