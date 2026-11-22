"""JIPDA tuning on the TUNING window only (docs/PREREGISTRATION_3.md 4.2).

Grid: initial existence {0.01, 0.05, 0.1, 0.2} x confirm {0.9, 0.95, 0.99} x delete {0.01, 0.05} = 24,
uniform clutter lambda {5, 200, 1000}, seeds 20271106-20271110, plus the GNN reference (EKF, adaptive pre-gate).
Selection: among combinations whose lambda-5 mean GOSPA <= 1.02 x GNN's, the smallest sum of mean GOSPA at
lambda 200 and 1000; if none qualifies, the smallest lambda-5 GOSPA (and say so).

    .venv/bin/python scripts/stage3_tune_jipda.py --lams 5,200      # job 1
    .venv/bin/python scripts/stage3_tune_jipda.py --lams 1000       # job 2
    .venv/bin/python scripts/stage3_tune_jipda.py --select          # writes the jipda block of configs/stage3.yaml
Checkpoint: results/stage3/tune_jipda.json (one row per combination, lambda and seed).
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

OUT = ROOT / "results/stage3/tune_jipda.json"
GRID = list(itertools.product([0.01, 0.05, 0.1, 0.2], [0.9, 0.95, 0.99], [0.01, 0.05]))
SEEDS = [20271106 + i for i in range(5)]
LAMS = (5, 200, 1000)
KEEP = ("gospa_mean_m", "gospa_loc_m", "gospa_missed_m", "gospa_false_m", "false_tracks_per_scan", "missed_per_scan",
        "id_switches", "init_delay_mean_s", "rmse_m")


def key(method, combo, lam, seed):
    return f"{method}|{combo}|{lam}|{seed}"


def tune(lams):
    doc = json.loads(OUT.read_text()) if OUT.exists() else {"grid": GRID, "seeds": SEEDS, "rows": {}, "code": code_version()}
    spec = S.specs()["EHAM_1106_tune"]
    assert spec["kind"] == "tune"
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    for lam in lams:
        cfg0, _ = load_stage3([f"radar.clutter_lambda={lam}"], True, "M0")
        sc, _, cfg = S.build(cfg0, spec)
        todo = [("ekf", None)] + [("jipda", c) for c in GRID]
        for method, combo in todo:
            wait_for_memory(log)
            c = dict(cfg)
            if combo:
                c["jipda"] = {"p0": combo[0], "confirm": combo[1], "delete": combo[2]}
            for seed in SEEDS:
                k = key(method, combo, lam, seed)
                if k in doc["rows"]:
                    continue
                t0 = time.perf_counter()
                r = run(sc, c, seed=seed, method=method)
                doc["rows"][k] = {**{m: r.summary[m] for m in KEEP}, "wall_s": time.perf_counter() - t0}
            OUT.write_text(json.dumps(doc))
            g = np.mean([doc["rows"][key(method, combo, lam, s)]["gospa_mean_m"] for s in SEEDS])
            f = np.mean([doc["rows"][key(method, combo, lam, s)]["false_tracks_per_scan"] for s in SEEDS])
            log(f"lam {lam} {method} {combo} gospa {g:.0f} false {f:.2f}")


def select():
    doc = json.loads(OUT.read_text())
    mean = lambda method, combo, lam, f="gospa_mean_m": float(np.mean(  # noqa: E731
        [doc["rows"][key(method, combo, lam, s)][f] for s in SEEDS]))
    gnn5 = mean("ekf", None, 5)
    table = []
    for c in GRID:
        c = tuple(c)
        table.append({"combo": c, "gospa5": mean("jipda", c, 5), "gospa200": mean("jipda", c, 200),
                      "gospa1000": mean("jipda", c, 1000), "false1000": mean("jipda", c, 1000, "false_tracks_per_scan"),
                      "delay5": mean("jipda", c, 5, "init_delay_mean_s")})
    ok = [t for t in table if t["gospa5"] <= 1.02 * gnn5]
    if ok:
        best = min(ok, key=lambda t: t["gospa200"] + t["gospa1000"])
        rule = "constraint met"
    else:
        best = min(table, key=lambda t: t["gospa5"])
        rule = "no combination met the lambda-5 constraint; smallest lambda-5 GOSPA"
    res = {"gnn": {lam: {"gospa": mean("ekf", None, lam), "false": mean("ekf", None, lam, "false_tracks_per_scan"),
                         "delay": mean("ekf", None, lam, "init_delay_mean_s")} for lam in LAMS},
           "constraint_gospa5_max": 1.02 * gnn5, "n_meeting_constraint": len(ok), "rule": rule, "selected": best,
           "table": table}
    (ROOT / "results/stage3/tune_jipda_selection.json").write_text(json.dumps(res, indent=1))
    y = ROOT / "configs/stage3.yaml"
    txt = y.read_text()
    block = (f"jipda:                       # FROZEN by scripts/stage3_tune_jipda.py --select (tuning window, 5 seeds)\n"
             f"  p0: {best['combo'][0]}\n  confirm: {best['combo'][1]}\n  delete: {best['combo'][2]}\n"
             f"  p_survive: 0.98\n  pd: 0.9\n")
    if "\njipda:" in txt:
        raise SystemExit("configs/stage3.yaml already has a jipda block (frozen); not overwriting")
    txt = txt.replace("# Sensor model steps", block + "# Sensor model steps")
    y.write_text(txt)
    print(json.dumps({k: res[k] for k in ("gnn", "constraint_gospa5_max", "n_meeting_constraint", "rule", "selected")}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lams", default=None)
    ap.add_argument("--select", action="store_true")
    a = ap.parse_args()
    if a.select:
        select()
    else:
        tune([int(x) for x in (a.lams or "5,200,1000").split(",")])


if __name__ == "__main__":
    main()
