"""Export pre-computed scenarios for the static web demo (web/data/*.json).

Each scenario re-runs the tracker (and the baseline, for the GOSPA readout) on
the evaluation window with one fixed seed and stores a 10-minute slice that
starts after the tracker has warmed up.

Privacy: no ICAO address, registration or callsign exists in the input file.
Truth and tracks get new sequential numbers per scenario.

Encoding (flat integer arrays to keep files small):
  d  detections   [dt_cs, range_dam, az_cdeg, is_clutter] * n   (dt from scan start, 1/100 s)
  k  tracks       [num, x_dam, y_dam, vx_dmps, vy_dmps, flags] * n   (flags: 1 confirmed, 2 false track)
  r  truth        [num, x_dam, y_dam] * n
  g  [gospa_m, missed, false, n_truth, n_confirmed, baseline_gospa_m]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.config import with_overrides  # noqa: E402
from radar_track_lab.experiments import load, scenario_for  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

SCENARIOS = [
    ("base", "기준 조건", 0.90, 5, 0.15),
    ("low-pd", "탐지 확률 낮음", 0.70, 5, 0.15),
    ("clutter", "클러터 많음", 0.90, 20, 0.15),
    ("az-noise", "방위 잡음 큼", 0.90, 5, 0.30),
    ("hard", "모두 나쁨", 0.70, 20, 0.30),
    ("clean", "좋은 조건", 0.97, 0, 0.15),
]
START_SCAN = 75  # 6 min into the window: tracks are established
HIST = 62  # GOSPA history before the slice, for the sparkline
N_SCANS = 125  # 10 min


def main() -> None:
    cfg, pts = load()
    sc, _ = scenario_for(cfg, pts, "eval")
    seed = int(cfg["monte_carlo"]["base_seed"])
    out_dir = ROOT / "web/data"
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for sid, label, pd, lam, saz in SCENARIOS:
        c = with_overrides(cfg, **{"radar.pd": pd, "radar.clutter_lambda": float(lam), "radar.sigma_az_deg": saz})
        ekf = run(sc, c, seed=seed, method="ekf", record=True)
        nn = run(sc, c, seed=seed, method="nn", record=True)
        truth_num, track_num = {}, {}
        scans = []
        for k in range(START_SCAN, START_SCAN + N_SCANS):
            scan, snap, et = ekf.scans[k], ekf.snapshots[k], sc.eval_truths[k]
            d = []
            for t, r, az, tid in zip(scan.t, scan.r, scan.az, scan.truth_id):
                d += [int(round((t - scan.t0) * 100)), int(round(r / 10)), int(round(np.degrees(az) * 100)) % 36000,
                      int(tid < 0)]
            assigned_tracks = set(snap["assigned"].values())
            kk = []
            for tid, p, v, conf in zip(snap["track_ids"], snap["track_pos"], snap["track_vel"], snap["confirmed"]):
                if conf:
                    num = track_num.setdefault(int(tid), len(track_num) + 1)
                    flags = 1 | (0 if int(tid) in assigned_tracks else 2)
                else:
                    num, flags = 0, 0
                kk += [num, int(round(p[0] / 10)), int(round(p[1] / 10)), int(round(v[0] * 10)),
                       int(round(v[1] * 10)), flags]
            rr = []
            for tid, p in zip(et.ids, et.pos):
                rr += [truth_num.setdefault(int(tid), len(truth_num) + 1), int(round(p[0] / 10)), int(round(p[1] / 10))]
            g = snap["gospa"]
            scans.append({
                "d": d, "k": kk, "r": rr,
                "g": [round(g.total), g.n_missed, g.n_false, int(et.ids.size), int(snap["confirmed"].sum()),
                      round(nn.snapshots[k]["gospa"].total)],
            })
        doc = {
            "id": sid, "label": label,
            "radar": {"pd": pd, "clutter_lambda": lam, "sigma_az_deg": saz, "sigma_r_m": c["radar"]["sigma_r_m"],
                      "rotation_period_s": c["radar"]["rotation_period_s"], "max_range_m": c["radar"]["max_range_m"]},
            "tracker": {"q": c["tracker"]["q"], "confirm": f"{c['tracker']['confirm_m']}/{c['tracker']['confirm_n']}",
                        "delete_misses": c["tracker"]["delete_misses"]},
            "gospa_c_m": c["eval"]["gospa_c_m"],
            "t0_unix": sc.scan_truths[START_SCAN].t0, "seed": seed, "scan_offset": START_SCAN, "scans": scans,
            "g_hist": [[round(ekf.snapshots[k]["gospa"].total), ekf.snapshots[k]["gospa"].n_missed,
                        ekf.snapshots[k]["gospa"].n_false, int(sc.eval_truths[k].ids.size),
                        int(ekf.snapshots[k]["confirmed"].sum()), round(nn.snapshots[k]["gospa"].total)]
                       for k in range(START_SCAN - HIST, START_SCAN)],
            "run_summary": {"ekf_gospa_mean_m": round(ekf.summary["gospa_mean_m"]),
                            "nn_gospa_mean_m": round(nn.summary["gospa_mean_m"])},
        }
        path = out_dir / f"{sid}.json"
        path.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
        index.append({"id": sid, "label": label, "pd": pd, "clutter_lambda": lam, "sigma_az_deg": saz,
                      "file": f"data/{sid}.json", "bytes": path.stat().st_size})
        print(sid, f"{path.stat().st_size/1024:.0f} KiB", doc["run_summary"])
    meta = {
        "scenarios": index,
        "window_utc": cfg["truth"]["eval_start_utc"],
        "attribution": "Contains information from adsb.lol (globe_history_2026, 2026-11-06), "
                       "made available under the ODbL 1.0.",
        "license": "ODbL-1.0",
    }
    (out_dir / "index.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
