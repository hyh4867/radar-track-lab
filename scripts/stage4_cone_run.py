"""Stage 4 priority 2: cone-aware track hold on M4 (docs/PREREGISTRATION_4.md 9).

Wraps ``sim.simulate_scans`` (attach Mode C to target reports) and ``sim.make_tracker`` (``ekf_cone``, ``imm_cone``)
inside this process only, then runs the stage 3 diag_near measurement. Methods ``ekf``/``imm`` here are the
regression check against results/stage3/diag_near (hold off).

    .venv/bin/python scripts/stage4_cone_run.py --scenarios EHAM_1106_eval --methods ekf_cone [--n-seeds 2]
Output: results/stage4/cone/<scenario>__M4__<method>.json (per-seed checkpoint)
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
from radar_track_lab import cone as CN  # noqa: E402
from radar_track_lab import diagnose as D  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab import sim  # noqa: E402
from radar_track_lab.experiments import seeds  # noqa: E402
from radar_track_lab.radar import RadarParams  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402

OUT = ROOT / "results/stage4/cone"
NEAR_M = 15_000.0
_orig_scans, _orig_make = sim.simulate_scans, sim.make_tracker
_last = {}


def _scans(scan_truths, radar, seed):
    return CN.with_modec(_orig_scans(scan_truths, radar, seed), scan_truths, radar.modec_step_ft)


def _make(method, params, cfg):
    if method == "ekf_cone":
        from radar_track_lab.tracker import EKFTracker

        trk = type("EKFCone", (CN.ConeHoldMixin, EKFTracker), {})(params)
    elif method == "imm_cone":
        from radar_track_lab.imm import IMMParams, IMMTracker

        trk = type("IMMCone", (CN.ConeHoldMixin, IMMTracker), {})(params, IMMParams.from_config(cfg))
    else:
        trk = _orig_make(method, params, cfg)
    if method.endswith("_cone"):
        trk.setup_cone(RadarParams.from_config(cfg))
    _last["trk"] = trk
    return trk


sim.simulate_scans, sim.make_tracker = _scans, _make


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="EHAM_1106_eval,KATL_1106_peak")
    ap.add_argument("--methods", default="ekf_cone,imm_cone")
    ap.add_argument("--n-seeds", type=int, default=None)
    ap.add_argument("--tag", default="M4")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    cfg0, _ = load_stage3([], True, "M4")
    for sid in a.scenarios.split(","):
        sc, _, cfg = S.build(cfg0, S.specs()[sid])
        kin = D.TruthKinematics(sc)
        warm = sc.t_start + float(cfg["eval"]["warmup_s"])
        for method in a.methods.split(","):
            path = OUT / f"{sid}__{a.tag}__{method}.json"
            doc = json.loads(path.read_text()) if path.exists() else {
                "scenario": sid, "model": "M4", "method": method, "runs": [], "code": code_version()}
            done = {r["seed"] for r in doc["runs"]}
            todo = [s for s in seeds(cfg, a.n_seeds) if s not in done]
            if todo:
                wait_for_memory(log)
            for seed in todo:
                t0 = time.perf_counter()
                r = sim.run(sc, cfg, seed=seed, method=method, record=True)
                evs = D.classify_switches(sc, kin, r, warm)
                lost = [e for e in evs if e["cause"] in D.LOST]
                trk = _last["trk"]
                doc["runs"].append({
                    "seed": seed, "id_switches": r.summary["id_switches"],
                    "misses_lost": sum(e["cause"] == "misses" for e in lost),
                    "misses_lost_near": sum(e["cause"] == "misses" and e["range_m"] < NEAR_M for e in lost),
                    "summary": r.summary, "cone_stats": getattr(trk, "cone_stats", None),
                    "wall_s": time.perf_counter() - t0})
                path.write_text(json.dumps(doc))
            m = lambda k: float(np.mean([x[k] for x in doc["runs"]]))  # noqa: E731
            log(f"{sid} {method} n={len(doc['runs'])} idsw={m('id_switches'):.2f} misses_lost={m('misses_lost'):.2f} "
                f"near={m('misses_lost_near'):.2f}")


if __name__ == "__main__":
    main()
