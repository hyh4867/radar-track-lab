"""EKF-GNN tracker vs nearest-neighbour baseline at the default radar condition."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.experiments import load, scenario_for, seeds, summarize_runs  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402


def main() -> None:
    cfg, pts = load()
    sc, truth = scenario_for(cfg, pts, "eval")
    res = {"condition": cfg["radar"], "tracker": cfg["tracker"], "scenario": sc.meta, "methods": {}}
    nees_real = []
    for method in ("ekf", "nn"):
        rows = []
        for s in seeds(cfg):
            r = run(sc, cfg, seed=s, method=method)
            rows.append(r.summary)
            if method == "ekf":
                nees_real.append(r.nees)
        res["methods"][method] = {"runs": rows, "summary": summarize_runs(rows)}
    nr = np.concatenate(nees_real)
    conf = nr[nr[:, 2] == 1]
    res["nees_real_adsb"] = {
        "samples_confirmed": int(conf.shape[0]),
        "anees4_confirmed": float(conf[:, 3].mean()),
        "median_nees4_confirmed": float(np.median(conf[:, 3])),
        "anees2_pos_confirmed": float(conf[:, 4].mean()),
        "frac_nees4_le_chi2_95": float(np.mean(conf[:, 3] <= 9.488)),
        "frac_nees4_le_chi2_99": float(np.mean(conf[:, 3] <= 13.277)),
    }
    (ROOT / "results/data").mkdir(parents=True, exist_ok=True)
    (ROOT / "results/data/compare.json").write_text(json.dumps(res, indent=2))
    for m in ("ekf", "nn"):
        s = res["methods"][m]["summary"]
        print(m, {k: (round(v["mean"], 2), round(v["ci95"], 2)) for k, v in s.items()})
    print(res["nees_real_adsb"])


if __name__ == "__main__":
    main()
