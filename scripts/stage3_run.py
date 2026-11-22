"""Stage 3 runner: scenarios x methods x seeds under one configuration, with per-seed checkpoints.

    .venv/bin/python scripts/stage3_run.py --out b0 --tag lam5_fixed --scenarios EHAM_1106_eval \
        --methods ekf,imm --set radar.clutter_lambda=5 --set tracker.pregate=fixed

Writes results/stage3/<out>/<scenario>__<method>__<tag>.json after every seed and skips seeds already
there. Before each (scenario, method) unit it waits until free memory is >= 15% (PREREGISTRATION_3 7.4).
``--diag`` also records the stage 2 ID-switch causes and turn/straight error split (slower).
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

from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.config import load_config, with_overrides  # noqa: E402
from radar_track_lab.experiments import load_stage2, seeds  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402


def parse_value(v: str):
    for f in (int, float):
        try:
            return f(v)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(v.lower(), v)


def load_stage3(sets: list[str], stage3_yaml: bool, model: str | None = None):
    cfg, _ = load_stage2()
    models = {}
    if stage3_yaml and (ROOT / "configs/stage3.yaml").exists():
        extra = load_config(ROOT / "configs/stage3.yaml") or {}
        models = extra.pop("models", {}) or {}
        for k, v in extra.items():
            cfg[k] = {**cfg[k], **v} if isinstance(v, dict) and isinstance(cfg.get(k), dict) else v
    if model:
        if model not in models:
            raise SystemExit(f"unknown model {model!r}; configs/stage3.yaml has {sorted(models)}")
        sets = [f"{k}={v}" for k, v in models[model].items()] + list(sets)
        if (cfg.get("sensor") or {}).get("snr_ref") is None and models[model].get("sensor.pd_model") == "swerling1":
            raise SystemExit("sensor.snr_ref is not calibrated (scripts/stage3_calibrate_pd.py)")
    ov = {}
    for kv in sets:
        k, v = kv.split("=", 1)
        node = cfg
        for part in k.split(".")[:-1]:
            node = node.setdefault(part, {})
        ov[k] = parse_value(v)
    return (with_overrides(cfg, **ov) if ov else cfg), ov


def one(sc, cfg, seed, method, diag, kin, warm):
    t0 = time.perf_counter()
    r = run(sc, cfg, seed=seed, method=method, record=diag)
    row = {"seed": seed, "summary": r.summary, "wall_s": time.perf_counter() - t0}
    if diag:
        from radar_track_lab import diagnose as D

        ev = D.classify_switches(sc, kin, r, warm)
        row["causes"] = {c: sum(e["cause"] == c for e in ev) for c in D.CAUSES}
        row["lost_present"] = sum(row["causes"][c] for c in D.LOST)
        row["base"] = D.base_rates(kin, r, warm)
        row.update(D.split_rmse(kin, r, warm))
        row["lost_targets"] = [int(e["target"]) for e in ev if e["cause"] in D.LOST]
    if r.nees.shape[0]:
        conf = r.nees[r.nees[:, 2] == 1]
        if conf.shape[0]:
            row["nees"] = {"n": int(conf.shape[0]), "mean4": float(conf[:, 3].mean())}
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--methods", required=True)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--n-seeds", type=int, default=None)
    ap.add_argument("--no-stage3-yaml", action="store_true")
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--model", default=None, help="sensor model step from configs/stage3.yaml (M0..M4)")
    args = ap.parse_args()
    cfg0, ov = load_stage3(args.set, not args.no_stage3_yaml, args.model)
    out = ROOT / "results/stage3" / args.out
    out.mkdir(parents=True, exist_ok=True)
    specs = S.specs()
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    waited_total = 0.0
    for sid in args.scenarios.split(","):
        sc, truth, cfg = S.build(cfg0, specs[sid])
        kin = warm = None
        if args.diag:
            from radar_track_lab import diagnose as D

            kin = D.TruthKinematics(sc)
        warm = sc.t_start + float(cfg["eval"]["warmup_s"])
        for method in args.methods.split(","):
            path = out / f"{sid}__{method}__{args.tag}.json"
            doc = json.loads(path.read_text()) if path.exists() else {
                "scenario": sid, "method": method, "tag": args.tag, "model": args.model, "overrides": ov,
                "meta": {**sc.meta, "radar": cfg["radar"], "tracker": cfg["tracker"],
                         "sensor": cfg.get("sensor"), "jipda": cfg.get("jipda")}, "runs": [], "code": code_version()}
            done = {r["seed"] for r in doc["runs"]}
            todo = [s for s in seeds(cfg, args.n_seeds) if s not in done]
            if not todo:
                continue
            w = wait_for_memory(log)
            waited_total += w
            doc.setdefault("memory_wait_s", 0.0)
            doc["memory_wait_s"] += w
            for seed in todo:
                if sc.meta["targets"] == 0:
                    break
                doc["runs"].append(one(sc, cfg, seed, method, args.diag, kin, warm))
                path.write_text(json.dumps(doc))
            m = lambda f: float(np.mean([f(r) for r in doc["runs"]]))  # noqa: E731
            log(f"{sid} {method} {args.tag} n={len(doc['runs'])} rmse={m(lambda r: r['summary']['rmse_m']):.1f} "
                f"idsw={m(lambda r: r['summary']['id_switches']):.1f} "
                f"false={m(lambda r: r['summary']['false_tracks_per_scan']):.2f} "
                f"gospa={m(lambda r: r['summary']['gospa_mean_m']):.0f} wall={m(lambda r: r['wall_s']):.2f}s")
    log(f"done; memory wait {waited_total:.0f}s")


if __name__ == "__main__":
    main()
