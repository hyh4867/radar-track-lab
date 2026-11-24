#!/bin/bash
# Stage 4 step 3: after the code change, rerun JIPDA and JIPDA-est (2 seeds, stage 3 B eval settings) and compare
# with results/stage3/b1 (scripts/stage4_regression_check.py).
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
RUN="$PY -u scripts/stage3_run.py --model M0 --n-seeds 2"
# stage3_run writes under results/stage3/<out>; use a stage4-owned subfolder name and move it after
$RUN --out ../stage4/regression --tag lam1000_map --scenarios EHAM_1106_eval --methods "$1" --set radar.clutter_lambda=1000 --set radar.clutter_model=map
