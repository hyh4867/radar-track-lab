"""Stage 6 part 1: Mode C altitude check on every association (G1) on M4 (docs/PREREGISTRATION_6.md).

The stage 5 runner (scripts/stage5_cone_run.py) plus: method suffix ``_g1`` (H1 + G1), cond ``M4_err`` (assumed Mode C
faults on target reports, cone.apply_modec_errors) and the crossing-event switch count (crossing.py) per run.
Stage 5 description follows.

Wraps ``sim.simulate_scans`` (Mode C on target reports) and ``sim.make_tracker`` inside this process only:
    ekf, imm                  M4, no hold (with --cond M4_nocone: the cone switched off, sensor.cone_max_elev_deg=90)
    ekf_cone, imm_cone        the stage 4 hold (cone.ConeHoldMixin)
    ekf_h1, imm_h1            H1: hold + altitude check (cone.ConeHoldV2Mixin, variant h1)
    ekf_h2, imm_h2            H2: H1 + extrapolated altitude for the cone entry test
Per run it stores the summary, the ID-switch causes (stage 3 diagnose) and the misses losses within 15 km.

    .venv/bin/python scripts/stage6_cone_run.py --scenarios EHAM_1106_eval --methods ekf_g1 [--cond M4|M4_err] [--n-seeds 2]
Output: results/stage6/cone/<scenario>__<cond>__<method>.json (per-seed checkpoint)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import cone as CN  # noqa: E402
from radar_track_lab import crossing as X  # noqa: E402
from radar_track_lab import diagnose as D  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab import sim  # noqa: E402
from radar_track_lab.experiments import seeds  # noqa: E402
from radar_track_lab.radar import RadarParams  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402

OUT = ROOT / "results/stage6/cone"
NEAR_M = 15_000.0
CONDS = {"M4": [], "M4_err": []}
ERR = {"on": False}
_orig_scans, _orig_make = sim.simulate_scans, sim.make_tracker
_last = {}


def _scans(scan_truths, radar, seed):
    scans = CN.with_modec(_orig_scans(scan_truths, radar, seed), scan_truths, radar.modec_step_ft)
    if ERR["on"]:
        CN.apply_modec_errors(scans, seed, step_ft=radar.modec_step_ft)
    return scans


def _make(method, params, cfg):
    base, _, var = method.partition("_")
    if var in ("cone", "h1", "h2", "g1"):
        if base == "ekf":
            from radar_track_lab.tracker import EKFTracker as B

            args = (params,)
        else:
            from radar_track_lab.imm import IMMParams, IMMTracker as B

            args = (params, IMMParams.from_config(cfg))
        mix = CN.ConeHoldMixin if var == "cone" else CN.ConeHoldV2Mixin
        trk = type(f"{base}_{var}", (mix, B), {})(*args)
        if var == "cone":
            trk.setup_cone(RadarParams.from_config(cfg))
        else:
            trk.setup_cone_v2(RadarParams.from_config(cfg), "h1" if var == "g1" else var, gate_all=var == "g1")
    else:
        trk = _orig_make(method, params, cfg)
    _last["trk"] = trk
    return trk


sim.simulate_scans, sim.make_tracker = _scans, _make


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--methods", required=True)
    ap.add_argument("--cond", default="M4", choices=list(CONDS))
    ap.add_argument("--n-seeds", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else OUT
    out.mkdir(parents=True, exist_ok=True)
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    cfg0, _ = load_stage3(CONDS[a.cond], True, "M4")
    ERR["on"] = a.cond == "M4_err"
    for sid in a.scenarios.split(","):
        sc, _, cfg = S.build(cfg0, S.specs()[sid])
        kin = D.TruthKinematics(sc)
        warm = sc.t_start + float(cfg["eval"]["warmup_s"])
        xev = X.crossing_events(sc.scan_truths)
        for method in a.methods.split(","):
            path = out / f"{sid}__{a.cond}__{method}.json"
            doc = json.loads(path.read_text()) if path.exists() else {
                "scenario": sid, "cond": a.cond, "model": "M4", "method": method, "runs": [], "code": code_version()}
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
                    "causes": dict(Counter(e["cause"] for e in evs)),
                    "crossing_switches": X.crossing_switches(xev, evs), "crossing_events": len(xev),
                    "summary": r.summary, "cone_stats": getattr(trk, "cone_stats", None),
                    "wall_s": time.perf_counter() - t0})
                doc.setdefault("codes", []).append(code_version()["commit"])
                path.write_text(json.dumps(doc))
            m = lambda k: float(np.mean([x[k] for x in doc["runs"]]))  # noqa: E731
            log(f"{sid} {a.cond} {method} n={len(doc['runs'])} idsw={m('id_switches'):.2f} "
                f"misses_lost={m('misses_lost'):.2f} near={m('misses_lost_near'):.2f} cross={m('crossing_switches'):.2f}")


if __name__ == "__main__":
    main()
