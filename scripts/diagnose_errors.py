"""Classify EKF errors at the default condition (all Monte Carlo seeds).

ID switches:

after_truth_gap: the target was absent from the truth (ADS-B gap > max_gap_s, so it
                 was not simulated either) between the two assignments.
near_other:      while continuously present, another truth target was within 3 km.
other:           remaining switches (track lost while the target was present).

False-track scans (confirmed track not matched within c):
  after_truth_end: the track was last matched to a target that is no longer in the truth
                   (landed, left coverage or ADS-B gap) and is coasting;
  never_matched:   the track was never matched to any target (clutter-born or duplicate);
  other:           its last matched target is still present (duplicate / lagging track).
Missed-target scans:
  before_first_track: the target has never been matched yet (entering, M-of-N delay);
  other:              the target was matched before (lost track or out of c).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.experiments import load, scenario_for, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402


def main() -> None:
    cfg, pts = load()
    sc, _ = scenario_for(cfg, pts, "eval")
    warm = sc.t_start + float(cfg["eval"]["warmup_s"])
    present = [set(int(i) for i in e.ids) for e in sc.eval_truths]
    totals = {"after_truth_gap": 0, "near_other": 0, "other": 0}
    ft = {"after_truth_end": 0, "never_matched": 0, "other": 0}
    ms = {"before_first_track": 0, "other": 0}
    n_scans_counted = 0
    per_seed = []
    for s in seeds(cfg):
        r = run(sc, cfg, seed=s, method="ekf", record=True)
        last, last_k = {}, {}
        track_owner, ever_matched = {}, set()
        cnt = {"after_truth_gap": 0, "near_other": 0, "other": 0}
        for k, snap in enumerate(r.snapshots):
            et = sc.eval_truths[k]
            pos = {int(i): p for i, p in zip(et.ids, et.pos)}
            if snap["t"] >= warm:
                n_scans_counted += 1
                matched_tracks = set(snap["assigned"].values())
                for trk in snap["track_ids"][snap["confirmed"]]:
                    trk = int(trk)
                    if trk in matched_tracks:
                        continue
                    if trk not in track_owner:
                        ft["never_matched"] += 1
                    elif track_owner[trk] not in present[k]:
                        ft["after_truth_end"] += 1
                    else:
                        ft["other"] += 1
                for tid in present[k]:
                    if tid not in snap["assigned"]:
                        ms["before_first_track" if tid not in ever_matched else "other"] += 1
            for tid, trk in snap["assigned"].items():
                track_owner[trk] = tid
                ever_matched.add(tid)
            for tid, trk in snap["assigned"].items():
                if tid in last and last[tid] != trk and snap["t"] >= warm:
                    if any(tid not in present[j] for j in range(last_k[tid] + 1, k)):
                        cnt["after_truth_gap"] += 1
                    else:
                        d = [np.hypot(*(pos[o] - pos[tid])) for o in pos if o != tid]
                        cnt["near_other" if d and min(d) < 3000 else "other"] += 1
                last[tid], last_k[tid] = trk, k
        assert sum(cnt.values()) == r.summary["id_switches"]
        per_seed.append(cnt)
        for key in totals:
            totals[key] += cnt[key]
    n = len(per_seed)
    out = {"runs": n, "mean_per_run": {k: v / n for k, v in totals.items()}, "per_seed": per_seed,
           "false_tracks_per_scan": {k: v / n_scans_counted for k, v in ft.items()},
           "missed_per_scan": {k: v / n_scans_counted for k, v in ms.items()}}
    (ROOT / "results/data/id_switch_diagnosis.json").write_text(json.dumps(out, indent=2))
    print(out["mean_per_run"], out["false_tracks_per_scan"], out["missed_per_scan"])


if __name__ == "__main__":
    main()
