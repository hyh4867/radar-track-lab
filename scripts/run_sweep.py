"""Noise sweep: Pd x clutter lambda x sigma_azimuth, Monte Carlo runs per condition."""

from __future__ import annotations

import csv
import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.config import with_overrides  # noqa: E402
from radar_track_lab.experiments import METRICS, load, scenario_for, seeds, summarize_runs  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402


def main() -> None:
    cfg, pts = load()
    sc, _ = scenario_for(cfg, pts, "eval")
    sw = cfg["sweep"]
    out_rows, agg = [], []
    t0 = time.time()
    for pd, lam, saz in itertools.product(sw["pd"], sw["clutter_lambda"], sw["sigma_az_deg"]):
        c = with_overrides(cfg, **{"radar.pd": float(pd), "radar.clutter_lambda": float(lam),
                                   "radar.sigma_az_deg": float(saz)})
        for method in ("ekf", "nn"):
            rows = []
            for s in seeds(cfg):
                r = run(sc, c, seed=s, method=method).summary
                rows.append(r)
                out_rows.append({"pd": pd, "clutter_lambda": lam, "sigma_az_deg": saz, "method": method, "seed": s,
                                 **{k: r[k] for k in METRICS}})
            agg.append({"pd": pd, "clutter_lambda": lam, "sigma_az_deg": saz, "method": method,
                        "runs": len(rows), "summary": summarize_runs(rows)})
            g = agg[-1]["summary"]["gospa_mean_m"]
            print(f"Pd={pd} lam={lam} saz={saz} {method}: GOSPA {g['mean']:.0f} +- {g['ci95']:.0f}  "
                  f"[{time.time() - t0:.0f}s]", flush=True)
    d = ROOT / "results/data"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "sweep_runs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    (d / "sweep_summary.json").write_text(json.dumps({"scenario": sc.meta, "conditions": agg}, indent=1))


if __name__ == "__main__":
    main()
