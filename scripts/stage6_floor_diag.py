"""Post hoc (not preregistered): at lam5, what feeds the JIPDA-amap clutter map, and how large is the estimated density
at target reports compared with the true clutter density? Tuning window EHAM_1106_tune, seed 20271106, lam5_map,
stage 5 amap (fixed floor) and stage 6 amap (floor_frac 0.25). Output: results/stage6/floor_diag.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stage6_run import load_stage6  # noqa: E402
from radar_track_lab import jpda as J  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.sim import make_tracker  # noqa: E402
from radar_track_lab.tracker import TrackerParams  # noqa: E402


def main() -> None:
    out = {}
    for name, ff in (("stage5_fixed_floor", None), ("stage6_floor_0.25", 0.25)):
        cfg0, _ = load_stage6(["radar.clutter_lambda=5", "radar.clutter_model=map"], "M0")
        cfg0["clutter_amap_est"] = {**cfg0["clutter_amap_est"], "floor_frac": ff}
        sc, _, cfg = S.build(cfg0, S.specs()["EHAM_1106_tune"])
        radar = RadarParams.from_config(cfg)
        trk = make_tracker("jipda_amap", TrackerParams.from_config(cfg), cfg)
        fed_t = fed_c = 0
        ratio_t, ratio_c = [], []
        orig = trk.est.add
        cur = {}

        def add(r, az):
            nonlocal fed_t, fed_c
            s = cur["scan"]
            m = np.isin(np.asarray(r), s.r[s.truth_id >= 0])
            fed_t += int(m.sum())
            fed_c += int((~m).sum())
            orig(r, az)

        trk.est.add = add
        for k, scan in enumerate(simulate_scans(sc.scan_truths, radar, 20271106)):
            cur["scan"] = scan
            if k >= 30 and trk.est.N > 0:
                d = trk.est.density(scan.r, scan.az) / radar.clutter_density(scan.r, scan.az)
                tg = scan.truth_id >= 0
                ratio_t += list(d[tg])
                ratio_c += list(d[~tg])
            trk.process_scan(scan, sc.eval_truths[k].t)
        out[name] = {"fed_target_reports": fed_t, "fed_clutter_reports": fed_c,
                     "target_share_of_fed": fed_t / max(fed_t + fed_c, 1),
                     "est_over_true_at_target_reports_median": float(np.median(ratio_t)),
                     "est_over_true_at_clutter_reports_median": float(np.median(ratio_c)) if ratio_c else None,
                     "floor_over_true_median_density": float(J.ClutterMapDensity.FLOOR / np.median(radar.clutter_density(
                         np.full(100, 50_000.0), np.linspace(0, 6.28, 100))))}
        print(name, json.dumps(out[name]), flush=True)
    (ROOT / "results/stage6/floor_diag.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
