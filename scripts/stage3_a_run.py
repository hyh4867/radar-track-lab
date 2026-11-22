"""Stage 3 A: sensor models M0-M4 x five methods on one scenario (docs/PREREGISTRATION_3.md 3.4).

    .venv/bin/python scripts/stage3_a_run.py --scenario EHAM_1106_eval [--models M0,M1,M2,M3,M4] [--n-seeds 20]

For every seed all models run in this process, so the cross-model common sample can be formed in memory
(the per-sample tables are not stored). Per seed it stores, for every model:
  * the summary of nn, nnp, ekfh, ekf, imm (+ wall time),
  * stage 2 ID-switch causes, base rate and lost targets for ekf and imm,
  * the four-method common-sample scan-end RMSE (nn, nnp, ekfh, ekf) for C3,
  * the cross-model common-sample scan-end RMSE of ekf and imm (keys used by that method in every model).
Checkpoint: results/stage3/a/<scenario>.json after every seed. Waits for >= 15% free memory before each seed.
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
from radar_track_lab import audit as A  # noqa: E402
from radar_track_lab import diagnose as D  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import seeds  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

FOUR = ("nn", "nnp", "ekfh", "ekf")
METHODS = FOUR + ("imm",)
DIAG = ("ekf", "imm")
OUT = ROOT / "results/stage3/a"


def used_keys(tab):
    m = tab["reason"] == A.USED
    return {(int(k), int(t)): float(s) for k, t, s in zip(tab["k"][m], tab["truth"][m], tab["sq"][m])}


def one_model(sc, cfg, seed, kin, warm):
    res, rows = {}, {}
    for m in METHODS:
        t0 = time.perf_counter()
        r = run(sc, cfg, seed=seed, method=m, audit=True, record=m in DIAG)
        wall = time.perf_counter() - t0
        row = {"summary": r.summary, "wall_s": wall}
        if m in DIAG:
            ev = D.classify_switches(sc, kin, r, warm)
            row["causes"] = {c: sum(e["cause"] == c for e in ev) for c in D.CAUSES}
            row["lost_present"] = sum(row["causes"][c] for c in D.LOST)
            row["lost_events"] = [{"target": int(e["target"]), "cause": e["cause"], "range_m": e["range_m"],
                                   "misses": int(e["misses_in_window"])} for e in ev if e["cause"] in D.LOST]
            row["base"] = D.base_rates(kin, r, warm)
            row.update(D.split_rmse(kin, r, warm))
        rows[m] = row
        res[m] = r.audit["scan_end"]
    c = A.common_scan_end_many({m: res[m] for m in FOUR})
    four = {"n_truth": c["n_truth"], "n_common": c["n_common"], "n_paired": c["n"],
            "rmse_common": {m: A.rmse(c["sq"][m]) for m in FOUR}}
    return rows, four, {m: used_keys(res[m]) for m in DIAG + ("nn",)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--models", default="M0,M1,M2,M3,M4")
    ap.add_argument("--n-seeds", type=int, default=None)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    models = args.models.split(",")
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    spec = S.specs()[args.scenario]
    built = {}
    for mo in models:
        cfg0, ov = load_stage3([], True, mo)
        sc, _, cfg = S.build(cfg0, spec)
        built[mo] = (sc, cfg, ov, D.TruthKinematics(sc), sc.t_start + float(cfg["eval"]["warmup_s"]))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{args.scenario}.json"
    doc = json.loads(path.read_text()) if path.exists() else {
        "scenario": args.scenario, "spec": spec, "models": models,
        "meta": {mo: {"overrides": b[2], "truth_per_scan": b[0].meta["truth_per_scan_mean"], "targets": b[0].meta["targets"],
                      "radar": b[1]["radar"], "sensor": b[1].get("sensor"), "tracker": b[1]["tracker"]}
                 for mo, b in built.items()}, "runs": [], "memory_wait_s": 0.0, "code": code_version()}
    if doc["models"] != models:
        raise SystemExit(f"checkpoint has models {doc['models']}, asked for {models}")
    done = {r["seed"] for r in doc["runs"]}
    for seed in seeds(built[models[0]][1], args.n_seeds):
        if seed in done:
            continue
        doc["memory_wait_s"] += wait_for_memory(log)
        t0 = time.perf_counter()
        per, keys = {}, {}
        for mo in models:
            sc, cfg, _, kin, warm = built[mo]
            rows, four, k = one_model(sc, cfg, seed, kin, warm)
            per[mo] = {"methods": rows, "four": four}
            keys[mo] = k
        cross = {}
        for m in DIAG + ("nn",):
            com = set.intersection(*(set(keys[mo][m]) for mo in models))
            cross[m] = {"n_common": len(com),
                        "rmse": {mo: float(np.sqrt(np.mean([keys[mo][m][q] for q in com]))) if com else float("nan")
                                 for mo in models}}
        doc["runs"].append({"seed": seed, "models": per, "cross_model": cross, "wall_s": time.perf_counter() - t0})
        path.write_text(json.dumps(doc))
        s = {mo: per[mo]["methods"]["ekf"]["summary"]["id_switches"] for mo in models}
        log(f"{args.scenario} seed {seed} ekf idsw {s} {time.perf_counter() - t0:.1f}s")
    log(f"{args.scenario} done n={len(doc['runs'])}")


if __name__ == "__main__":
    main()
