"""Choose the IMM parameters on the tuning window only (preregistration Q2).

Grid: q_cv x q_ct x omega noise x tau_cv x tau_ct = 64 combinations, 10 seeds
(20271106...). Rule: among combinations whose mean GOSPA is not above the
EKF's (q = 25) on the same window and seeds, the fewest mean ID switches; a
difference below 0.2 switches is broken by the lower GOSPA. Checkpointed.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import load_stage2, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

GRID = {"q_cv": [1.0, 4.0, 9.0, 25.0], "q_ct": [9.0, 25.0], "omega_noise_dps": [0.1, 0.3],
        "tau_cv_s": [100.0, 300.0], "tau_ct_s": [20.0, 40.0]}
KEYS = ("gospa_mean_m", "id_switches", "fragmentations", "rmse_m", "missed_per_scan", "false_tracks_per_scan")
OUT = ROOT / "results/data/stage2/tune_imm.json"


def main() -> None:
    cfg, _ = load_stage2()
    sc, _, cfg = S.build(cfg, S.specs()["EHAM_1106_tune"])
    sd = [s + 10_000 for s in seeds(cfg, 10)]
    doc = json.loads(OUT.read_text()) if OUT.exists() else {"window": S.specs()["EHAM_1106_tune"], "seeds": sd, "grid": []}
    if "ekf" not in doc:
        rows = [run(sc, cfg, seed=s, method="ekf").summary for s in sd]
        doc["ekf"] = {k: float(np.mean([r[k] for r in rows])) for k in KEYS}
        OUT.write_text(json.dumps(doc, indent=1))
    print("ekf", doc["ekf"], flush=True)
    done = {json.dumps(g["params"], sort_keys=True) for g in doc["grid"]}
    for vals in itertools.product(*GRID.values()):
        prm = dict(zip(GRID.keys(), vals))
        if json.dumps(prm, sort_keys=True) in done:
            continue
        c = {**cfg, "imm": {**cfg["imm"], **prm}}
        rows = [run(sc, c, seed=s, method="imm").summary for s in sd]
        g = {"params": prm, **{k: float(np.mean([r[k] for r in rows])) for k in KEYS}}
        doc["grid"].append(g)
        OUT.write_text(json.dumps(doc, indent=1))
        print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in g.items()}, flush=True)
    ok = [g for g in doc["grid"] if g["gospa_mean_m"] <= doc["ekf"]["gospa_mean_m"]]
    doc["n_meeting_gospa_constraint"] = len(ok)
    if ok:
        best_sw = min(g["id_switches"] for g in ok)
        best = min((g for g in ok if g["id_switches"] - best_sw < 0.2), key=lambda g: g["gospa_mean_m"])
        doc["rule_applied"] = "fewest ID switches among GOSPA <= EKF; ties below 0.2 switches by lower GOSPA"
    else:
        best = min(doc["grid"], key=lambda g: g["gospa_mean_m"])
        doc["rule_applied"] = "no combination met the GOSPA constraint; lowest GOSPA used"
    doc["selected"] = best
    OUT.write_text(json.dumps(doc, indent=1))
    print("selected", best)


if __name__ == "__main__":
    main()
