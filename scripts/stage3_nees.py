"""Stage 3 B: NEES on model-matched synthetic NCV truth (docs/PREREGISTRATION_3.md 4.3).

40 targets moving exactly as the trackers' NCV model (q = 25), Pd 0.9, uniform clutter lambda 5 / 200 / 1000,
GNN (EKF), JPDA, JIPDA, seeds 20261106 + i. Reported per run:
  * scan-end NEES: confirmed tracks paired with a truth target by the GOSPA assignment; state and covariance
    predicted to the evaluation time (the same instant for every tracker),
  * update-time NEES from the tracker's update records (stage 1 definition; for JPDA/JIPDA the track time t_i
    and the detection time differ by a fraction of a second, so this one carries a small timing error).

    .venv/bin/python scripts/stage3_nees.py [--methods ekf,jpda,jipda] [--lams 5,200,1000] [--n-seeds 20]
Output: results/stage3/nees.json (checkpoint per condition).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import ekf  # noqa: E402
from radar_track_lab.metrics import evaluate_scan  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402
from radar_track_lab.sim import make_tracker, run  # noqa: E402
from radar_track_lab.synthetic import ncv_scenario  # noqa: E402
from radar_track_lab.tracker import CONFIRMED, TrackerParams  # noqa: E402

OUT = ROOT / "results/stage3/nees.json"


def scan_end_nees(sc, cfg, seed, method):
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    trk = make_tracker(method, p, cfg)
    scans = simulate_scans(sc.scan_truths, radar, seed)
    c, pw = float(cfg["eval"]["gospa_c_m"]), int(cfg["eval"]["gospa_p"])
    vals = []
    for k, scan in enumerate(scans):
        et = sc.eval_truths[k]
        trk.process_scan(scan, et.t)
        if k < 12:  # warm-up: 1 minute
            continue
        ids, pos, vel = trk.estimates(et.t)
        ev = evaluate_scan(et, ids, pos, c, pw)
        sel = np.flatnonzero(trk.status == CONFIRMED)
        idx = {int(trk.ids[i]): i for i in sel}
        tpos = {int(t): j for j, t in enumerate(et.ids)}
        for tid, trid in ev.assigned.items():
            i = idx[int(trid)]
            xp, Pp = ekf.predict(trk.X[i:i + 1], trk.P[i:i + 1], np.array([et.t - trk.T[i]]), p.q)
            j = tpos[int(tid)]
            e = np.r_[et.pos[j], et.vel[j]] - xp[0]
            vals.append(float(e @ np.linalg.solve(Pp[0], e)))
    return np.asarray(vals)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", default="ekf,jpda,jipda")
    ap.add_argument("--lams", default="5,200,1000")
    ap.add_argument("--n-seeds", type=int, default=20)
    a = ap.parse_args()
    doc = json.loads(OUT.read_text()) if OUT.exists() else {"rows": {}, "code": code_version()}
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    for lam in (int(x) for x in a.lams.split(",")):
        cfg, _ = load_stage3([f"radar.clutter_lambda={lam}", "radar.pd=0.9"], True, "M0")
        for method in a.methods.split(","):
            key = f"{method}|{lam}"
            if key in doc["rows"] and len(doc["rows"][key]["runs"]) >= a.n_seeds:
                continue
            wait_for_memory(log)
            runs = []
            for i in range(a.n_seeds):
                seed = 20261106 + i
                sc = ncv_scenario(40, 150, 4.8, float(cfg["tracker"]["q"]), 150.0, seed=seed, r_min=10_000.0, r_max=90_000.0)
                se = scan_end_nees(sc, cfg, seed, method)
                r = run(sc, cfg, seed=seed, method=method)
                conf = r.nees[r.nees[:, 2] == 1] if r.nees.shape[0] else np.zeros((0, 9))
                runs.append({"seed": seed, "scan_end_n": int(se.size), "scan_end_mean": float(se.mean()) if se.size else float("nan"),
                             "scan_end_median": float(np.median(se)) if se.size else float("nan"),
                             "update_n": int(conf.shape[0]), "update_mean": float(conf[:, 3].mean()) if conf.shape[0] else float("nan"),
                             "false_tracks_per_scan": r.summary["false_tracks_per_scan"], "missed_per_scan": r.summary["missed_per_scan"]})
            doc["rows"][key] = {"method": method, "lam": lam, "runs": runs}
            OUT.write_text(json.dumps(doc, indent=1))
            log(f"{key} scan-end NEES {np.nanmean([x['scan_end_mean'] for x in runs]):.2f} "
                f"update NEES {np.nanmean([x['update_mean'] for x in runs]):.2f}")


if __name__ == "__main__":
    main()
