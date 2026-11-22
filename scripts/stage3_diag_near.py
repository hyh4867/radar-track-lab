"""Stage 3 follow-up diagnostic: why do "misses" losses appear within 15 km of the radar from M2 on?

Not a verdict and not a change to any frozen result. Two conditions on EHAM_1106_eval and KATL_1106_peak,
EKF and IMM, 20 evaluation seeds: M4 as frozen, and M4 with the overhead cone switched off
(sensor.cone_max_elev_deg = 90). For each "misses" loss within 15 km it records, for every scan of the
stage 2 classification window (last assigned scan -3 .. +2), the truth altitude, ground range, elevation,
whether the target was illuminated and whether it was detected, so undetected scans split into
"inside the 42 deg cone" and "outside it" (low Pd, merging).

    .venv/bin/python scripts/stage3_diag_near.py
Output: results/stage3/diag_near/<scenario>__<cond>__<method>.json and summary.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import diagnose as D  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab import sensor as SE  # noqa: E402
from radar_track_lab.experiments import seeds  # noqa: E402
from radar_track_lab.radar import RadarParams  # noqa: E402
from radar_track_lab.runtime import code_version, wait_for_memory  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

OUT = ROOT / "results/stage3/diag_near"
SCEN = ("EHAM_1106_eval", "KATL_1106_peak")
CONDS = {"M4": [], "M4_nocone": ["sensor.cone_max_elev_deg=90"]}
NEAR_M = 15_000.0


def window_detail(sc, result, radar, ev, cone_deg):
    tid, kl = int(ev["target"]), int(ev["k_last"])
    rows = []
    for k in range(max(kl + D.WINDOW[0], 0), min(kl + D.WINDOW[1], len(sc.scan_truths) - 1) + 1):
        st = sc.scan_truths[k]
        hit = np.flatnonzero(st.ids == tid)
        if hit.size == 0:
            rows.append({"k": k, "illuminated": False})
            continue
        j = int(hit[0])
        d = float(np.hypot(*st.pos[j]))
        alt = float(st.alt[j]) if st.alt is not None else float("nan")
        _, el = SE.slant_and_elevation(d, radar.antenna_height_m, alt, radar.a_e)
        el = float(np.degrees(el))
        det = bool(np.any(result.scans[k].truth_id == tid))
        rows.append({"k": k, "illuminated": True, "detected": det, "ground_m": d, "alt_m": alt, "elev_deg": el,
                     "in_cone": bool(el > cone_deg)})
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log = lambda m: print(time.strftime("%H:%M:%S"), m, flush=True)  # noqa: E731
    for sid in SCEN:
        for cond, sets in CONDS.items():
            cfg0, _ = load_stage3(sets, True, "M4")
            sc, _, cfg = S.build(cfg0, S.specs()[sid])
            radar = RadarParams.from_config(cfg)
            kin = D.TruthKinematics(sc)
            warm = sc.t_start + float(cfg["eval"]["warmup_s"])
            for method in ("ekf", "imm"):
                path = OUT / f"{sid}__{cond}__{method}.json"
                if path.exists():
                    continue
                wait_for_memory(log)
                runs = []
                for seed in seeds(cfg):
                    r = run(sc, cfg, seed=seed, method=method, record=True)
                    evs = D.classify_switches(sc, kin, r, warm)
                    lost = [e for e in evs if e["cause"] in D.LOST]
                    near = [e for e in lost if e["cause"] == "misses" and e["range_m"] < NEAR_M]
                    runs.append({"seed": seed, "id_switches": r.summary["id_switches"],
                                 "misses_lost": sum(e["cause"] == "misses" for e in lost),
                                 "misses_lost_near": len(near),
                                 "lost_near_any_cause": sum(e["range_m"] < NEAR_M for e in lost),
                                 "near_events": [{"target": int(e["target"]), "k_last": int(e["k_last"]),
                                                  "range_m": e["range_m"],
                                                  "window": window_detail(sc, r, radar, e, radar.cone_max_elev_deg)}
                                                 for e in near]})
                doc = {"scenario": sid, "cond": cond, "method": method, "cone_max_elev_deg": radar.cone_max_elev_deg,
                       "runs": runs, "code": code_version()}
                path.write_text(json.dumps(doc))
                log(f"{sid} {cond} {method} misses_near {np.mean([x['misses_lost_near'] for x in runs]):.2f} "
                    f"misses {np.mean([x['misses_lost'] for x in runs]):.2f} idsw {np.mean([x['id_switches'] for x in runs]):.2f}")


if __name__ == "__main__":
    main()
