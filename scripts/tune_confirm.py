"""Q5 (optional): choose a stricter M-of-N confirmation rule on the tuning window.

Candidates 3/4 (stage 1), 4/5, 4/6, 5/6, 6/8, EKF only, 5 seeds. Rule: the
smallest sum of mean GOSPA at clutter lambda 200 and 1000, excluding rules
whose GOSPA at lambda 5 is more than 5% above the 3/4 rule's. Checkpointed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.config import with_overrides  # noqa: E402
from radar_track_lab.experiments import load_stage2, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

RULES = [(3, 4), (4, 5), (4, 6), (5, 6), (6, 8)]
LAMBDAS = [5.0, 200.0, 1000.0]
KEYS = ("gospa_mean_m", "false_tracks_per_scan", "missed_per_scan", "init_delay_mean_s", "id_switches", "rmse_m")
OUT = ROOT / "results/data/stage2/tune_confirm.json"


def main() -> None:
    cfg, _ = load_stage2()
    sc, _, cfg = S.build(cfg, S.specs()["EHAM_1106_tune"])
    sd = [s + 10_000 for s in seeds(cfg, 5)]
    doc = json.loads(OUT.read_text()) if OUT.exists() else {"seeds": sd, "rows": []}
    done = {(r["m"], r["n"], r["clutter_lambda"]) for r in doc["rows"]}
    for (m, n) in RULES:
        for lam in LAMBDAS:
            if (m, n, lam) in done:
                continue
            c = with_overrides(cfg, **{"tracker.confirm_m": m, "tracker.confirm_n": n, "radar.clutter_lambda": lam})
            rows = [run(sc, c, seed=s, method="ekf").summary for s in sd]
            row = {"m": m, "n": n, "clutter_lambda": lam, **{k: float(np.nanmean([r[k] for r in rows])) for k in KEYS}}
            doc["rows"].append(row)
            OUT.write_text(json.dumps(doc, indent=1))
            print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()}, flush=True)
    g = {(r["m"], r["n"], r["clutter_lambda"]): r["gospa_mean_m"] for r in doc["rows"]}
    ok = [r for r in RULES if g[(*r, 5.0)] <= 1.05 * g[(3, 4, 5.0)]]
    best = min(ok, key=lambda r: g[(*r, 200.0)] + g[(*r, 1000.0)])
    doc["allowed_by_lambda5_constraint"] = ok
    doc["selected"] = list(best)
    OUT.write_text(json.dumps(doc, indent=1))
    print("allowed", ok, "selected", best)


if __name__ == "__main__":
    main()
