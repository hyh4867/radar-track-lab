"""Post-hoc (not preregistered): what are the "misses" losses within 15 km that remain with the cone hold?

KATL_1106_peak and EHAM_1106_eval, ekf_cone, 20 seeds. For each remaining near "misses" loss, the stage 3
classification window (diag_near.window_detail): undetected scans inside / outside the cone, and whether the target
was ever inside the cone. Also the ID-switch causes (stage 3 diagnose) for M4 vs hold.
Output: results/stage4/cone_diag.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import stage4_cone_run as CR  # noqa: E402  (installs the Mode C / cone-hold wrappers)
from stage3_diag_near import window_detail  # noqa: E402
from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import diagnose as D  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import seeds  # noqa: E402
from radar_track_lab.radar import RadarParams  # noqa: E402


def main() -> None:
    out = {}
    cfg0, _ = load_stage3([], True, "M4")
    for sid in ("EHAM_1106_eval", "KATL_1106_peak"):
        sc, _, cfg = S.build(cfg0, S.specs()[sid])
        radar = RadarParams.from_config(cfg)
        kin = D.TruthKinematics(sc)
        warm = sc.t_start + float(cfg["eval"]["warmup_s"])
        for method in ("ekf", "ekf_cone"):
            causes, kinds = Counter(), Counter()
            for seed in seeds(cfg):
                r = CR.sim.run(sc, cfg, seed=seed, method=method, record=True)
                evs = D.classify_switches(sc, kin, r, warm)
                causes.update(e["cause"] for e in evs)
                for e in evs:
                    if e["cause"] == "misses" and e["range_m"] < CR.NEAR_M:
                        w = window_detail(sc, r, radar, e, radar.cone_max_elev_deg)
                        und = [x for x in w if x.get("illuminated") and not x.get("detected")]
                        inc = sum(x["in_cone"] for x in und)
                        kinds["undetected scans all in cone" if und and inc == len(und) else
                              "some undetected scans outside cone" if und else "no undetected scan in window"] += 1
            n = len(seeds(cfg))
            out[f"{sid}|{method}"] = {"causes_per_run": {k: v / n for k, v in causes.items()},
                                      "near_misses_kinds_per_run": {k: v / n for k, v in kinds.items()}}
            print(sid, method, json.dumps(out[f"{sid}|{method}"]), flush=True)
    (ROOT / "results/stage4/cone_diag.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
