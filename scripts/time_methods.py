"""Wall time of one 30-minute run per method on the evaluation window (run when the machine is otherwise idle)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import load_stage2, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402


def main() -> None:
    cfg, _ = load_stage2()
    sc, _, cfg = S.build(cfg, S.specs()["EHAM_1106_eval"])
    t = {"nn": [], "ekf": [], "imm": []}
    for s in seeds(cfg, 7):  # methods alternate so that drift in machine load affects them equally
        for m in t:
            t0 = time.perf_counter()
            run(sc, cfg, seed=s, method=m)
            t[m].append(time.perf_counter() - t0)
    out = {"repeats": 7, **{f"{m}_s": float(np.median(v)) for m, v in t.items()},
           "ratio": float(np.median(np.array(t["imm"]) / np.array(t["ekf"]))), "all": t}
    (ROOT / "results/data/stage2/timing.json").write_text(json.dumps(out, indent=1))
    print({k: v for k, v in out.items() if k != "all"})


if __name__ == "__main__":
    main()
