"""Post hoc (not preregistered): what does G1 reject? EHAM_1106_eval, YSSY_1106_peak, KATL_1106_peak, EKF, 5 seeds.

For each pair G1 rejects: is the report from the aircraft the track last updated on ("own"), another aircraft, and
how far its Mode C is from the prediction, with the elapsed time and the vertical speed estimate. Also the same for
H1 runs under Mode C faults (cond M4_err): how often held tracks have a wrong last Mode C.
Output: results/stage6/g1_diag.json
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

import stage6_cone_run as CR  # noqa: E402  (installs the wrappers)
from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import cone as CN  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import seeds  # noqa: E402
from radar_track_lab.tracker import CONFIRMED  # noqa: E402

LOG = {"rej": []}
_orig_gate = CN.ConeHoldV2Mixin._extra_gate
_orig_proc = CN.ConeHoldV2Mixin.process_scan


def gate(self, ok, tracks, dets, scan):
    kept = _orig_gate(self, ok, tracks, dets, scan)
    if getattr(self, "gate_all", False):
        rej = np.setdiff1d(ok, kept)
        for o in rej:
            i = int(self.ids[tracks[o]])
            if i in self.check_ids:
                continue
            d = int(dets[o])
            h = self.hist.get(i)
            a_last, t_last = h[-1][1], h[-1][0]
            vz = CN.vz_estimate([x[0] for x in h], [x[1] for x in h])
            pred = CN.predicted_alt(a_last, t_last, vz, scan.t[d])
            LOG["rej"].append({"own": int(scan.truth_id[d]) == self._last_truth.get(i, -9), "tgt": int(scan.truth_id[d]) >= 0,
                               "err_ft": float((scan.alt[d] - pred) / 0.3048), "dt": float(scan.t[d] - t_last),
                               "vz_fts": float(vz / 0.3048), "hist_span_ft": float((max(x[1] for x in h) - min(x[1] for x in h)) / 0.3048)})
    return kept


def proc(self, scan, t_end):
    if not hasattr(self, "_last_truth"):
        self._last_truth = {}
    rec = _orig_proc(self, scan, t_end)
    for r in rec:
        self._last_truth[r[0]] = int(scan.truth_id[r[1]])
    return rec


CN.ConeHoldV2Mixin._extra_gate, CN.ConeHoldV2Mixin.process_scan = gate, proc


def main() -> None:
    out = {}
    cfg0, _ = load_stage3([], True, "M4")
    for sid in ("EHAM_1106_eval", "YSSY_1106_peak", "KATL_1106_peak"):
        sc, _, cfg = S.build(cfg0, S.specs()[sid])
        LOG["rej"] = []
        for seed in seeds(cfg, 5):
            CR.sim.run(sc, cfg, seed=seed, method="ekf_g1", record=True)
        R = LOG["rej"]
        own = [r for r in R if r["own"]]
        e = np.abs([r["err_ft"] for r in own]) if own else np.zeros(0)
        out[sid] = {"rejected_per_run": len(R) / 5, "own_share": len(own) / max(len(R), 1),
                    "other_target_share": sum(r["tgt"] and not r["own"] for r in R) / max(len(R), 1),
                    "own_err_ft_pct50_90_max": [float(np.percentile(e, 50)), float(np.percentile(e, 90)), float(e.max())] if e.size else None,
                    "own_dt_s_median": float(np.median([r["dt"] for r in own])) if own else None,
                    "own_abs_vz_fts_median": float(np.median(np.abs([r["vz_fts"] for r in own]))) if own else None,
                    "own_hist_span_gt_3000ft_share": float(np.mean([r["hist_span_ft"] > 3000 for r in own])) if own else None}
        print(sid, json.dumps(out[sid]), flush=True)
    (ROOT / "results/stage6/g1_diag.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
