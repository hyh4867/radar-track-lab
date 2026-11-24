"""Stage 4 runner (docs/PREREGISTRATION_4.md): the stage 3 runner with configs/stage4.yaml merged and output in
results/stage4/<out>/. Per-seed checkpoints; seeds already in the file are skipped.

    .venv/bin/python scripts/stage4_run.py --out tune --tag lam1000_map__c1 --scenarios EHAM_1106_tune \
        --methods jipda_map --model M0 --set radar.clutter_lambda=1000 --set radar.clutter_model=map \
        --set monte_carlo.base_seed=20271106 --n-seeds 5 --set clutter_map_est.dr_m=1000 ...
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

from stage3_run import load_stage3, one  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.config import load_config  # noqa: E402
from radar_track_lab.experiments import seeds  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402


def load_stage4(sets, model):
    """Stage 3 config (+ model step), then configs/stage4.yaml, then the --set overrides (applied last)."""
    cfg, _ = load_stage3([], True, model)
    extra = load_config(ROOT / "configs/stage4.yaml") or {}
    for k, v in extra.items():
        cfg[k] = {**cfg[k], **v} if isinstance(v, dict) and isinstance(cfg.get(k), dict) else v
    from stage3_run import parse_value
    from radar_track_lab.config import with_overrides

    ov = {}
    for kv in sets:
        k, v = kv.split("=", 1)
        node = cfg
        for part in k.split(".")[:-1]:
            node = node.setdefault(part, {})
        ov[k] = parse_value(v)
    return (with_overrides(cfg, **ov) if ov else cfg), ov


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--methods", required=True)
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--n-seeds", type=int, default=None)
    ap.add_argument("--model", default="M0")
    args = ap.parse_args()
    cfg0, ov = load_stage4(args.set, args.model)
    out = ROOT / "results/stage4" / args.out
    out.mkdir(parents=True, exist_ok=True)
    specs = S.specs()
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    for sid in args.scenarios.split(","):
        sc, _, cfg = S.build(cfg0, specs[sid])
        for method in args.methods.split(","):
            if method == "jipda_map" and not cfg.get("clutter_map_est"):
                raise SystemExit("jipda_map needs clutter_map_est (configs/stage4.yaml or --set)")
            path = out / f"{sid}__{method}__{args.tag}.json"
            doc = json.loads(path.read_text()) if path.exists() else {
                "scenario": sid, "method": method, "tag": args.tag, "model": args.model, "overrides": ov,
                "meta": {**sc.meta, "radar": cfg["radar"], "tracker": cfg["tracker"], "sensor": cfg.get("sensor"),
                         "jipda": cfg.get("jipda"), "clutter_map_est": cfg.get("clutter_map_est")},
                "runs": [], "code": code_version()}
            done = {r["seed"] for r in doc["runs"]}
            todo = [s for s in seeds(cfg, args.n_seeds) if s not in done]
            if not todo:
                continue
            doc["memory_wait_s"] = doc.get("memory_wait_s", 0.0) + wait_for_memory(log)
            for seed in todo:
                doc["runs"].append(one(sc, cfg, seed, method, False, None, None))
                doc.setdefault("codes", []).append(code_version()["commit"])
                path.write_text(json.dumps(doc))
                r = doc["runs"][-1]
                log(f"{sid} {method} {args.tag} seed={seed} false={r['summary']['false_tracks_per_scan']:.2f} "
                    f"gospa={r['summary']['gospa_mean_m']:.0f} wall={r['wall_s']:.1f}s")
            m = lambda f: float(np.mean([f(r) for r in doc["runs"]]))  # noqa: E731
            log(f"{sid} {method} {args.tag} n={len(doc['runs'])} "
                f"false={m(lambda r: r['summary']['false_tracks_per_scan']):.2f} "
                f"gospa={m(lambda r: r['summary']['gospa_mean_m']):.0f} wall={m(lambda r: r['wall_s']):.1f}s")


if __name__ == "__main__":
    main()
