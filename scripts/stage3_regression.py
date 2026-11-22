"""Stage 3, step 0: do the stored stage 1 and stage 2 results still reproduce?

Re-runs, with the current code and the stored settings, every seed of
  * results/data/compare.json                (stage 1: ekf, nn on the Schiphol eval window)
  * results/data/stage2/runs/*.json          (stage 2: every scenario x method x tag file)
and compares every number in each seed's ``summary`` dict with the stored one.
Nothing is written to the stage 1/2 result folders.

    .venv/bin/python scripts/stage3_regression.py [--only GLOB] [--n-seeds N]

Output: results/stage3/regression.json (one entry per file: seeds compared,
largest absolute difference per metric, pass/fail) and a one-line verdict.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.config import with_overrides  # noqa: E402
from radar_track_lab.experiments import load, load_stage2, scenario_for, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

OUT = ROOT / "results/stage3/regression.json"
TOL = 1e-9  # relative; the code is deterministic, so any real change shows up far above this


def compare(stored: dict, new: dict) -> dict:
    worst = {}
    for k, v in stored.items():
        w = new.get(k)
        if isinstance(v, (int, float)) and isinstance(w, (int, float)):
            if (isinstance(v, float) and math.isnan(v)) and (isinstance(w, float) and math.isnan(w)):
                d = 0.0
            else:
                d = abs(float(v) - float(w))
            worst[k] = d
        elif v != w:
            worst[k] = float("inf")
    return worst


def ok(worst: dict, stored: dict) -> bool:
    return all(d <= TOL * max(1.0, abs(float(stored[k]))) for k, d in worst.items())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="*")
    ap.add_argument("--n-seeds", type=int, default=None)
    ap.add_argument("--out", default=str(OUT), help="output JSON (default: the committed stage 3 regression file)")
    args = ap.parse_args()
    report = {"tolerance_rel": TOL, "files": {}}
    t_all = time.perf_counter()

    # stage 1
    if fnmatch.fnmatch("compare.json", args.only):
        cfg, pts = load()
        sc, _ = scenario_for(cfg, pts, "eval")
        stored = json.loads((ROOT / "results/data/compare.json").read_text())
        for method in ("ekf", "nn"):
            rows = stored["methods"][method]["runs"]
            ss = seeds(cfg)[: args.n_seeds or len(rows)]
            res = []
            for s, row in zip(ss, rows):
                r = run(sc, cfg, seed=s, method=method)
                res.append((s, compare(row, r.summary), ok(compare(row, r.summary), row)))
            key = f"compare.json:{method}"
            report["files"][key] = summarize(res)
            print(key, report["files"][key]["pass"], flush=True)

    # stage 2
    cfg0, _ = load_stage2()
    specs = S.specs()
    for path in sorted((ROOT / "results/data/stage2/runs").glob("*.json")):
        if not fnmatch.fnmatch(path.name, args.only):
            continue
        doc = json.loads(path.read_text())
        ov = doc["meta"].get("overrides") or {}
        cfg = with_overrides(cfg0, **ov) if ov else cfg0
        sc, _, c = S.build(cfg, specs[doc["scenario"]])
        rows = doc["runs"][: args.n_seeds or len(doc["runs"])]
        res = []
        for row in rows:
            r = run(sc, c, seed=row["seed"], method=doc["method"], record=False)
            w = compare(row["summary"], r.summary)
            res.append((row["seed"], w, ok(w, row["summary"])))
        report["files"][path.name] = summarize(res)
        print(path.name, report["files"][path.name]["pass"], f"n={len(res)}", flush=True)

    report["all_pass"] = all(v["pass"] for v in report["files"].values())
    report["n_files"] = len(report["files"])
    report["n_seed_runs"] = sum(v["n_seeds"] for v in report["files"].values())
    report["wall_s"] = time.perf_counter() - t_all
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(f"regression: {'PASS' if report['all_pass'] else 'FAIL'} files={report['n_files']} "
          f"seed_runs={report['n_seed_runs']} wall={report['wall_s']:.0f}s")


def summarize(res):
    worst = {}
    for _, w, _ in res:
        for k, d in w.items():
            worst[k] = max(worst.get(k, 0.0), d)
    bad = [s for s, _, good in res if not good]
    return {"n_seeds": len(res), "pass": not bad, "failed_seeds": bad,
            "max_abs_diff": {k: v for k, v in worst.items() if v > 0}}


if __name__ == "__main__":
    main()
