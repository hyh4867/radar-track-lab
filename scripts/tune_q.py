"""Choose the NCV process-noise PSD q on the tuning window (never on the evaluation window)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.config import with_overrides  # noqa: E402
from radar_track_lab.experiments import load, scenario_for, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

GRID = [1, 4, 9, 16, 25, 36, 49, 64, 100, 200]


def main() -> None:
    cfg, pts = load()
    sc, _ = scenario_for(cfg, pts, "tune")
    out = {"window": [cfg["truth"]["tune_start_utc"], cfg["truth"]["tune_duration_s"]], "scenario": sc.meta, "grid": []}
    for q in GRID:
        c = with_overrides(cfg, **{"tracker.q": float(q)})
        rows = [run(sc, c, seed=s + 10_000, method="ekf").summary for s in seeds(cfg, 5)]
        agg = {k: float(np.mean([r[k] for r in rows])) for k in ("gospa_mean_m", "rmse_m", "id_switches", "fragmentations")}
        out["grid"].append({"q": q, **agg})
        print(q, {k: round(v, 1) for k, v in agg.items()})
    best = min(out["grid"], key=lambda g: g["gospa_mean_m"])
    out["selected_q"] = best["q"]
    out["criterion"] = "minimum mean GOSPA over 5 seeds on the tuning window"
    Path(ROOT / "results/data").mkdir(parents=True, exist_ok=True)
    (ROOT / "results/data/tune_q.json").write_text(json.dumps(out, indent=2))
    print("selected q =", best["q"], "(config:", cfg["tracker"]["q"], ")")


if __name__ == "__main__":
    main()
