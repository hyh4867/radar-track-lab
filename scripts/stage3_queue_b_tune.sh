#!/bin/bash
# Stage 3 driver, after A: Stone Soup cross-check (a), then JIPDA tuning in two jobs (tuning window only).
# Stops before the B evaluation: the selected JIPDA parameters are frozen and committed first (PREREGISTRATION_3 4.2).
set -uo pipefail
cd "$(dirname "$0")/.."
HR=../../tools/heavy-run.sh
PY=.venv/bin/python
wait_mem() { $PY -c "import sys; sys.path.insert(0,'src'); from radar_track_lab.runtime import wait_for_memory; wait_for_memory()"; }
until grep -q "^A finished" results/stage3/logs/a_queue.log 2>/dev/null; do
  if grep -q "stop" results/stage3/logs/a_queue.log 2>/dev/null; then echo "A queue stopped; not starting B"; exit 1; fi
  sleep 60
done
echo "stonesoup (a) start $(date '+%F %T %z')"; wait_mem
$HR $PY -u scripts/stage3_stonesoup_a.py
echo "tune 5,200 start $(date '+%F %T %z')"; wait_mem
$HR $PY -u scripts/stage3_tune_jipda.py --lams 5,200
echo "tune 1000 start $(date '+%F %T %z')"; wait_mem
$HR $PY -u scripts/stage3_tune_jipda.py --lams 1000
echo "B tuning finished $(date '+%F %T %z')"
