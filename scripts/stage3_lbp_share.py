"""Share of gated clusters solved with loopy BP instead of exact enumeration (PREREGISTRATION_3 4.2).

The B1 run files do not store the tracker's cluster counters, so this re-runs one evaluation seed
(20261106) per condition with the same configuration as scripts/stage3_queue_b_eval.sh and reads
JPDATracker.stats. Post-hoc diagnostic; it does not change any B1 number.

    .venv/bin/python scripts/stage3_lbp_share.py
Output: results/stage3/lbp_share.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402
from radar_track_lab.sim import make_tracker  # noqa: E402
from radar_track_lab.tracker import TrackerParams  # noqa: E402

OUT = ROOT / "results/stage3/lbp_share.json"
SEED = 20261106


def main() -> None:
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    doc = json.loads(OUT.read_text()) if OUT.exists() else {"seed": SEED, "rows": {}, "code": code_version()}
    for lam in (5, 200, 1000):
        for clutter in ("uniform", "map"):
            sets = [f"radar.clutter_lambda={lam}"] + (["radar.clutter_model=map"] if clutter == "map" else [])
            cfg0, _ = load_stage3(sets, True, "M0")
            sc, _, cfg = S.build(cfg0, S.specs()["EHAM_1106_eval"])
            for method in ("jpda", "jipda"):
                key = f"{method}|lam{lam}_{clutter}"
                if key in doc["rows"]:
                    continue
                wait_for_memory(log)
                trk = make_tracker(method, TrackerParams.from_config(cfg), cfg)
                scans = simulate_scans(sc.scan_truths, RadarParams.from_config(cfg), SEED)
                t0 = time.perf_counter()
                for k, scan in enumerate(scans):
                    trk.process_scan(scan, sc.eval_truths[k].t)
                st = dict(trk.stats)
                st["lbp_share_of_multi"] = st["lbp"] / st["multi"] if st["multi"] else 0.0
                st["lbp_share_of_all"] = st["lbp"] / st["clusters"] if st["clusters"] else 0.0
                st["wall_s"] = time.perf_counter() - t0
                doc["rows"][key] = st
                OUT.write_text(json.dumps(doc, indent=1))
                log(f"{key} {st}")


if __name__ == "__main__":
    main()
