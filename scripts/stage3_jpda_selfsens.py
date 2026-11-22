"""Self-sensitivity of our JPDA tracker (post-hoc diagnostic for Stone Soup cross-check (b)).

Runs our JPDA tracker twice on the same detections (Schiphol evaluation window, ideal sensor, uniform clutter):
the second copy multiplies every association probability by (1 + eps * N(0, 1)) with eps = 1e-7, the size of
the beta differences seen between our tracker and the Stone Soup-driven one at the first diverging scan.
The comparison is the same as scripts/stage3_stonesoup_b.py (confirmed tracks, 1 cm, ID switches, first scan the
confirmed sets differ). If the perturbed copy diverges from the original like Stone Soup does at lambda 200 and stays
identical at lambda 5, the lambda 200 mismatch is numerical sensitivity, not a logic difference.

    .venv/bin/python scripts/stage3_jpda_selfsens.py [--lams 5,200] [--seeds 3] [--eps 1e-7]
Output: results/stage3/jpda_selfsens.json
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
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.jpda import JPDATracker  # noqa: E402
from radar_track_lab.metrics import evaluate_scan, summarize  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.sim import make_tracker  # noqa: E402
from radar_track_lab.tracker import TrackerParams  # noqa: E402


class Perturbed(JPDATracker):
    def __init__(self, *a, eps=1e-7, seed=0, **k):
        super().__init__(*a, **k)
        self.eps, self.rng = eps, np.random.default_rng(seed)

    def associate_scan(self, scan):
        a = super().associate_scan(scan)
        if a["beta"].size:
            a["beta"] = a["beta"] * (1.0 + self.eps * self.rng.standard_normal(a["beta"].size))
        return a


def one(lam, seed, eps):
    cfg0, _ = load_stage3([f"radar.clutter_lambda={lam}"], True, "M0")
    cfg0["jipda"] = {}
    sc, _, cfg = S.build(cfg0, S.specs()["EHAM_1106_eval"])
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    ours = make_tracker("jpda", p, cfg)
    pert = Perturbed(p, ours.pda, radar, eps=eps, seed=seed)
    scans = simulate_scans(sc.scan_truths, radar, seed)
    c, pw = float(cfg["eval"]["gospa_c_m"]), int(cfg["eval"]["gospa_p"])
    ev_o, ev_p, n_conf, n_close, set_diff, first_split, first_cm = [], [], 0, 0, 0, None, None
    for k, scan in enumerate(scans):
        et = sc.eval_truths[k]
        ours.process_scan(scan, et.t)
        pert.process_scan(scan, et.t)
        if first_cm is None and np.array_equal(ours.ids, pert.ids):
            if np.any(np.hypot(*(ours.X[:, :2] - pert.X[:, :2]).T) > 0.01):
                first_cm = k
        io, po, _ = ours.estimates(et.t)
        ip, pp, _ = pert.estimates(et.t)
        ev_o.append(evaluate_scan(et, io, po, c, pw))
        ev_p.append(evaluate_scan(et, ip, pp, c, pw))
        common = np.intersect1d(io, ip)
        x = np.setxor1d(io, ip).size
        set_diff += x
        if x and first_split is None:
            first_split = k
        if common.size:
            d = np.hypot(*(po[np.searchsorted(io, common)] - pp[np.searchsorted(ip, common)]).T)
            n_conf += common.size
            n_close += int((d <= 0.01).sum())
    w = float(cfg["eval"]["warmup_s"])
    so, sp = summarize(ev_o, c, w, sc.t_start), summarize(ev_p, c, w, sc.t_start)
    total = n_conf + set_diff
    keys = ("rmse_m", "gospa_mean_m", "false_tracks_per_scan", "missed_per_scan", "id_switches")
    return {"lam": lam, "seed": seed, "eps": eps, "share_within_1cm": n_close / total if total else float("nan"),
            "first_scan_any_track_over_1cm": first_cm, "first_scan_sets_differ": first_split,
            "summary_ours": {k: so[k] for k in keys}, "summary_perturbed": {k: sp[k] for k in keys}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lams", default="5,200")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--eps", type=float, default=1e-7)
    a = ap.parse_args()
    rows = []
    for lam in (int(x) for x in a.lams.split(",")):
        for seed in range(20261106, 20261106 + a.seeds):
            t0 = time.time()
            r = one(lam, seed, a.eps)
            r["wall_s"] = time.time() - t0
            rows.append(r)
            print(time.strftime("%H:%M:%S"), json.dumps(r), flush=True)
            (ROOT / "results/stage3/jpda_selfsens.json").write_text(json.dumps({"rows": rows}, indent=1))


if __name__ == "__main__":
    main()
