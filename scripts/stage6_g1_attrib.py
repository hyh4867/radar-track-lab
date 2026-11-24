"""Post hoc (not preregistered): which aircraft carry the extra ID switches of H1+G1 over H1?

EHAM_1106_eval, YSSY_1106_peak, KATL_1106_peak, EKF, seeds 20261106-20261110. Per aircraft: switches (G1 - H1) and the
largest truth altitude rate between scans [ft/s]. Output: results/stage6/g1_attrib.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import stage6_cone_run as CR  # noqa: E402
from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import diagnose as D  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import seeds  # noqa: E402


def max_rate(sc):
    d = {}
    for s in sc.scan_truths:
        for i, t, a in zip(s.ids, s.t, s.alt):
            d.setdefault(int(i), []).append((t, a))
    out = {}
    for i, l in d.items():
        l = np.array(sorted(l))
        r = np.abs(np.diff(l[:, 1]) / np.diff(l[:, 0])) / 0.3048 if len(l) > 1 else np.zeros(1)
        out[i] = float(np.nanmax(r)) if np.isfinite(r).any() else float("nan")
    return out


def main() -> None:
    out = {}
    cfg0, _ = load_stage3([], True, "M4")
    for sid in ("EHAM_1106_eval", "YSSY_1106_peak", "KATL_1106_peak"):
        sc, _, cfg = S.build(cfg0, S.specs()[sid])
        kin = D.TruthKinematics(sc)
        warm = sc.t_start + float(cfg["eval"]["warmup_s"])
        mr = max_rate(sc)
        c = {m: Counter() for m in ("ekf_h1", "ekf_g1")}
        ss = seeds(cfg, 5)
        for seed in ss:
            for m in c:
                r = CR.sim.run(sc, cfg, seed=seed, method=m, record=True)
                c[m].update(e["target"] for e in D.classify_switches(sc, kin, r, warm))
        diff = {k: c["ekf_g1"][k] - c["ekf_h1"][k] for k in set(c["ekf_g1"]) | set(c["ekf_h1"])}
        fast = {i for i, v in mr.items() if v > 120.0}
        out[sid] = {"n_seeds": len(ss), "g1_minus_h1_per_run": sum(diff.values()) / len(ss),
                    "from_aircraft_with_truth_rate_gt_120fts_per_run": sum(v for k, v in diff.items() if k in fast) / len(ss),
                    "aircraft_with_truth_rate_gt_120fts": {str(i): round(mr[i]) for i in sorted(fast)},
                    "top_increase": [(int(k), int(v), round(mr.get(k, float("nan")))) for k, v in sorted(diff.items(), key=lambda x: -x[1])[:5]],
                    "top_decrease": [(int(k), int(v)) for k, v in sorted(diff.items(), key=lambda x: x[1])[:5]]}
        print(sid, json.dumps(out[sid]), flush=True)
    (ROOT / "results/stage6/g1_attrib.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
