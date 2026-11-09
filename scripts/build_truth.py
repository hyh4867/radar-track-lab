"""Build ADS-B truth for the evaluation window and estimate interpolation error.

Writes ``results/data/truth_report.json``. No aircraft identifiers are written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.config import load_config  # noqa: E402
from radar_track_lab.radar import RadarParams  # noqa: E402
from radar_track_lab.sim import build_scenario, utc_to_unix  # noqa: E402
from radar_track_lab.truth import build_truth, leave_one_out_errors, load_points  # noqa: E402

GAP_BINS = [0, 2, 4, 6, 8, 10, 12, 15, 20]


def stats(x):
    x = np.asarray(x)
    if x.size == 0:
        return {"n": 0}
    return {
        "n": int(x.size),
        "median_m": float(np.median(x)),
        "rms_m": float(np.sqrt(np.mean(x**2))),
        "p95_m": float(np.percentile(x, 95)),
        "max_m": float(x.max()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs/default.yaml"))
    ap.add_argument("--out", default=str(ROOT / "results/data/truth_report.json"))
    args = ap.parse_args()
    cfg = load_config(args.config)
    tc = cfg["truth"]
    radar = RadarParams.from_config(cfg)
    pts = load_points(ROOT / tc["points_file"])
    t0 = utc_to_unix(tc["eval_start_utc"])
    dur = float(tc["eval_duration_s"])
    truth = build_truth(pts, cfg, t_start=t0 - 120, t_end=t0 + dur + 120)

    # leave-one-out interpolation error, all segments in the window
    gap, eh, el = leave_one_out_errors(truth, tc["max_gap_s"])
    by_bin = []
    for lo, hi in zip(GAP_BINS[:-1], GAP_BINS[1:]):
        m = (gap > lo) & (gap <= hi)
        by_bin.append({"gap_s": [lo, hi], "hermite": stats(eh[m]), "linear": stats(el[m])})

    # gaps actually bracketing the radar illumination times
    sc = build_scenario(truth, t0, dur, radar)
    seg_by_target = {}
    for s in truth.segments:
        seg_by_target.setdefault(s.target_id, []).append(s)
    used_gaps = []
    for st in sc.scan_truths:
        for tid, tt in zip(st.ids, st.t):
            for s in seg_by_target[int(tid)]:
                if s.t0 <= tt <= s.t1:
                    used_gaps.append(float(s.bracket_gap(tt)[0]))
                    break
    used_gaps = np.asarray(used_gaps)

    # expected error at the used gaps: map each used gap g to LOO samples with gap in [g-1, g+1]
    est = []
    rng = np.random.default_rng(0)
    for g in rng.choice(used_gaps, size=min(5000, used_gaps.size), replace=False):
        m = np.abs(gap - g) <= 1.0
        if m.sum() >= 20:
            est.append(np.sqrt(np.mean(eh[m] ** 2)))
    est = np.asarray(est)

    report = {
        "window_utc": [tc["eval_start_utc"], dur],
        "filter_stats": truth.stats.as_dict(),
        "segments": len(truth.segments),
        "aircraft": int(truth.target_ids.size),
        "scenario": sc.meta,
        "scan_count": sc.n_scans,
        "point_spacing_s": {
            "median": float(np.median(np.concatenate([np.diff(s.t) for s in truth.segments]))),
            "p95": float(np.percentile(np.concatenate([np.diff(s.t) for s in truth.segments]), 95)),
        },
        "used_bracket_gap_s": {
            "median": float(np.median(used_gaps)),
            "p95": float(np.percentile(used_gaps, 95)),
            "max": float(used_gaps.max()),
        },
        "loo_all": {"hermite": stats(eh), "linear": stats(el), "gap_median_s": float(np.median(gap))},
        "loo_by_gap": by_bin,
        "estimated_interp_rms_at_used_gaps_m": {
            "mean_of_bin_rms": float(est.mean()),
            "median_of_bin_rms": float(np.median(est)),
            "note": "LOO RMS error of Hermite interpolation at gaps within +-1 s of the gaps used at "
            "illumination times. Conservative: LOO places the query near the middle of a gap.",
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("filter_stats", "segments", "aircraft", "scenario", "point_spacing_s",
                                             "used_bracket_gap_s", "loo_all", "estimated_interp_rms_at_used_gaps_m")}, indent=2))
    for b in by_bin:
        print(b["gap_s"], "hermite", b["hermite"].get("rms_m"), "linear", b["linear"].get("rms_m"), "n", b["hermite"]["n"])


if __name__ == "__main__":
    main()
