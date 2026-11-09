"""Filter consistency (NEES) on synthetic truth that follows the NCV model exactly.

Case A: Pd = 1, no clutter (pure filter consistency).
Case B: Pd = 0.9, clutter lambda = 5 (gating / association effects included).
The real-ADS-B NEES (model mismatch) is computed in run_compare.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.config import load_config, with_overrides  # noqa: E402
from radar_track_lab.metrics import anees_bounds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402
from radar_track_lab.synthetic import ncv_scenario  # noqa: E402

N_RUNS, N_TARGETS, N_SCANS = 50, 10, 50


def case(cfg, pd, lam, label):
    c = with_overrides(cfg, **{"radar.pd": pd, "radar.clutter_lambda": lam, "eval.warmup_s": 0.0})
    q = float(c["tracker"]["q"])
    rows = []
    for i in range(N_RUNS):
        sc = ncv_scenario(N_TARGETS, N_SCANS, c["radar"]["rotation_period_s"], q,
                          c["tracker"]["init_speed_sigma_mps"], seed=500 + i)
        r = run(sc, c, seed=900 + i, method="ekf")
        rows.append(r.nees)
    nees = np.concatenate(rows)
    steps = []
    for k in range(2, N_SCANS + 1):
        m = nees[:, 1] == k
        n = int(m.sum())
        if n < 20:
            continue
        lo, hi = anees_bounds(n, 4)
        a = float(nees[m, 3].mean())
        lo2, hi2 = anees_bounds(n, 2)
        a2 = float(nees[m, 4].mean())
        steps.append({"update": k, "n": n, "anees4": a, "lo4": lo, "hi4": hi, "inside4": lo <= a <= hi,
                      "anees2": a2, "lo2": lo2, "hi2": hi2, "inside2": lo2 <= a2 <= hi2})
    inside = np.mean([s["inside4"] for s in steps])
    inside2 = np.mean([s["inside2"] for s in steps])
    late = [s for s in steps if s["update"] >= 5]
    lo_all, hi_all = anees_bounds(nees.shape[0], 4)
    near = nees[:, 8] < 5000.0
    lo_far, hi_far = anees_bounds(int((~near).sum()), 4)
    res = {
        "anees4_range_ge_5km": float(nees[~near, 3].mean()), "bounds4_range_ge_5km": [lo_far, hi_far],
        "anees4_range_lt_5km": float(nees[near, 3].mean()) if near.any() else float("nan"),
        "samples_range_lt_5km": int(near.sum()),
        "max_nees4": float(nees[:, 3].max()), "range_of_max_nees4_m": float(nees[np.argmax(nees[:, 3]), 8]),
        "label": label, "pd": pd, "clutter_lambda": lam, "q": q,
        "runs": N_RUNS, "targets": N_TARGETS, "scans": N_SCANS, "samples": int(nees.shape[0]),
        "anees4_overall": float(nees[:, 3].mean()), "overall_bounds4": [lo_all, hi_all],
        "frac_steps_inside4": float(inside), "frac_steps_inside2": float(inside2),
        "frac_steps_inside4_from_update5": float(np.mean([s["inside4"] for s in late])),
        "steps": steps,
    }
    print(label, {k: res[k] for k in ("samples", "anees4_overall", "overall_bounds4", "frac_steps_inside4",
                                      "frac_steps_inside2", "frac_steps_inside4_from_update5", "anees4_range_ge_5km",
                                      "bounds4_range_ge_5km", "anees4_range_lt_5km", "samples_range_lt_5km")})
    return res


def main() -> None:
    cfg = load_config(ROOT / "configs/default.yaml")
    out = {"A_pd1_clutter0": case(cfg, 1.0, 0.0, "A: Pd=1, lambda=0"),
           "B_pd0.9_clutter5": case(cfg, 0.9, 5.0, "B: Pd=0.9, lambda=5")}
    (ROOT / "results/data/nees_synthetic.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
