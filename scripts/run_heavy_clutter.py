"""Extra sweep: dense clutter (lambda 200 and 1000 per scan) at Pd 0.9, sigma_az 0.15 deg."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.config import with_overrides  # noqa: E402
from radar_track_lab.experiments import load, scenario_for, seeds, summarize_runs  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

LAMBDAS = [200, 1000]


def main() -> None:
    cfg, pts = load()
    sc, _ = scenario_for(cfg, pts, "eval")
    out = []
    t0 = time.time()
    for lam in LAMBDAS:
        c = with_overrides(cfg, **{"radar.pd": 0.9, "radar.clutter_lambda": float(lam), "radar.sigma_az_deg": 0.15})
        for method in ("ekf", "nn"):
            rows = [run(sc, c, seed=s, method=method).summary for s in seeds(cfg)]
            out.append({"pd": 0.9, "clutter_lambda": lam, "sigma_az_deg": 0.15, "method": method,
                        "runs": len(rows), "summary": summarize_runs(rows)})
            g = out[-1]["summary"]["gospa_mean_m"]
            print(f"lambda={lam} {method}: GOSPA {g['mean']:.0f} +- {g['ci95']:.0f} [{time.time() - t0:.0f}s]", flush=True)
    (ROOT / "results/data/sweep_heavy_clutter.json").write_text(json.dumps({"scenario": sc.meta, "conditions": out},
                                                                           indent=1))


if __name__ == "__main__":
    main()
