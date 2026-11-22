"""Stage 2 runner: methods x scenarios x seeds with per-seed checkpoints.

    .venv/bin/python scripts/run_stage2.py --scenarios EHAM_1106_eval --methods nn,ekf,imm

Writes results/data/stage2/runs/<scenario>__<method>[__<tag>].json after every
seed and skips seeds that are already there. Each seed row holds the summary,
ID-switch causes (preregistration section 2), straight / turn squared-error
sums, NEES statistics of confirmed tracks and the wall time.
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

from radar_track_lab import diagnose as D  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.config import with_overrides  # noqa: E402
from radar_track_lab.experiments import load_stage2, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

OUT = ROOT / "results/data/stage2/runs"


def one(sc, kin, cfg, seed, method, warm):
    t0 = time.perf_counter()
    r = run(sc, cfg, seed=seed, method=method, record=True)
    wall = time.perf_counter() - t0
    ev = D.classify_switches(sc, kin, r, warm)
    assert len(ev) == r.summary["id_switches"]
    causes = {c: sum(e["cause"] == c for e in ev) for c in D.CAUSES}
    row = {"seed": seed, "summary": r.summary, "causes": causes, "wall_s": wall,
           "lost_present": sum(causes[c] for c in D.LOST),
           "turn_and_misses": sum(e["turn_and_misses"] for e in ev if e["cause"] == "turn"),
           **D.split_rmse(kin, r, warm), "base": D.base_rates(kin, r, warm)}
    if r.nees.shape[0]:
        conf = r.nees[r.nees[:, 2] == 1]
        row["nees"] = {"n": int(conf.shape[0]), "mean4": float(conf[:, 3].mean()), "median4": float(np.median(conf[:, 3])),
                       "le_chi2_95": float(np.mean(conf[:, 3] <= 9.488)),
                       "mean4_ge5km": float(conf[conf[:, 8] >= 5000, 3].mean())}
    for e in ev:
        e["seed"] = seed
    return row, ev


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--methods", default="nn,ekf,imm")
    ap.add_argument("--n-seeds", type=int, default=None)
    ap.add_argument("--set", action="append", default=[], help="dotted override, e.g. radar.clutter_lambda=200")
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-events", action="store_true", help="keep cause counts only (dense-clutter runs)")
    args = ap.parse_args()
    cfg0, _ = load_stage2()
    ov = {}
    for kv in args.set:
        k, v = kv.split("=")
        ov[k] = float(v) if "." in v or "e" in v else int(v)
    cfg0 = with_overrides(cfg0, **ov) if ov else cfg0
    specs = S.specs()
    OUT.mkdir(parents=True, exist_ok=True)
    for sid in args.scenarios.split(","):
        sc, truth, cfg = S.build(cfg0, specs[sid])
        kin = D.TruthKinematics(sc)
        warm = sc.t_start + float(cfg["eval"]["warmup_s"])
        tr = kin.turn_dps[np.array([e.t for e in sc.eval_truths]) >= warm]
        meta = {**{k: v for k, v in sc.meta.items()}, "spec": specs[sid], "overrides": ov,
                "turn_share_of_target_scans": float(np.mean(np.abs(tr[np.isfinite(tr)]) >= D.TURN_DPS)) if np.isfinite(tr).any() else float("nan"),
                "imm": cfg.get("imm"), "tracker": cfg["tracker"], "radar": cfg["radar"]}
        for method in args.methods.split(","):
            path = OUT / (f"{sid}__{method}" + (f"__{args.tag}" if args.tag else "") + ".json")
            doc = json.loads(path.read_text()) if path.exists() else {"scenario": sid, "method": method, "meta": meta, "runs": [], "events": []}
            done = {r["seed"] for r in doc["runs"]}
            for seed in seeds(cfg, args.n_seeds):
                if seed in done:
                    continue
                if sc.meta["targets"] == 0:
                    break
                row, ev = one(sc, kin, cfg, seed, method, warm)
                doc["runs"].append(row)
                if method != "nn" and not args.no_events:  # the baseline has hundreds of switches per run; keep counts only
                    doc["events"].extend(ev)
                path.write_text(json.dumps(doc))
            if not path.exists():
                path.write_text(json.dumps(doc))
            if doc["runs"]:
                m = lambda f: float(np.mean([f(r) for r in doc["runs"]]))  # noqa: E731
                print(sid, method, f"n={len(doc['runs'])} truth/scan={sc.meta['truth_per_scan_mean']:.1f}",
                      f"rmse={m(lambda r: r['summary']['rmse_m']):.1f} idsw={m(lambda r: r['summary']['id_switches']):.1f}",
                      f"lost={m(lambda r: r['lost_present']):.1f} gospa={m(lambda r: r['summary']['gospa_mean_m']):.0f}",
                      f"wall={m(lambda r: r['wall_s']):.2f}s", flush=True)


if __name__ == "__main__":
    main()
