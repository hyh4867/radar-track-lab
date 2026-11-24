"""Pick the JIPDA-map cell size and forgetting constant on the tuning window (PREREGISTRATION_4 4) and freeze it.

Reads results/stage4/tune/EHAM_1106_tune__jipda_map__lam1000_map__<cand>.json (5 seeds each), writes
results/stage4/tune_selection.json and, with --write, the clutter_map_est block of configs/stage4.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "results/stage4/tune"
CANDS = [f"c{dr}_{daz}_{tau}" for dr in (1, 2) for daz in ("1.5", "3") for tau in (30, 100)]
SEEDS = list(range(20271106, 20271111))


def stats(p):
    runs = {r["seed"]: r for r in json.loads(p.read_text())["runs"]}
    if sorted(runs) != SEEDS:
        return None
    f = lambda k: float(np.mean([runs[s]["summary"][k] for s in SEEDS]))  # noqa: E731
    return {"gospa_mean_m": f("gospa_mean_m"), "false_tracks_per_scan": f("false_tracks_per_scan"),
            "missed_per_scan": f("missed_per_scan"), "id_switches": f("id_switches"),
            "init_delay_mean_s": f("init_delay_mean_s"), "wall_s": float(np.mean([runs[s]["wall_s"] for s in SEEDS]))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    rows = {}
    for c in CANDS:
        p = T / f"EHAM_1106_tune__jipda_map__lam1000_map__{c}.json"
        s = stats(p) if p.exists() else None
        if s is None:
            sys.exit(f"{c}: missing or incomplete")
        dr, daz, tau = c[1:].split("_")
        rows[c] = {**s, "dr_m": float(dr) * 1000, "daz_deg": float(daz), "tau_scans": float(tau)}
    ref = {m: stats(T / f"EHAM_1106_tune__{m}__lam1000_map.json") for m in ("jipda", "jipda_est")}
    # rule: min GOSPA; ties (< 1 m): fewer false tracks, then larger cells, then longer tau
    best_g = min(r["gospa_mean_m"] for r in rows.values())
    tied = [c for c, r in rows.items() if r["gospa_mean_m"] - best_g < 1.0]
    tied.sort(key=lambda c: (rows[c]["false_tracks_per_scan"], -rows[c]["dr_m"] * rows[c]["daz_deg"], -rows[c]["tau_scans"]))
    pick = tied[0]
    out = {"rule": "PREREGISTRATION_4 4", "seeds": SEEDS, "candidates": rows, "reference": ref, "selected": pick}
    (ROOT / "results/stage4/tune_selection.json").write_text(json.dumps(out, indent=1))
    for c, r in sorted(rows.items(), key=lambda kv: kv[1]["gospa_mean_m"]):
        print(f"{c:12s} gospa={r['gospa_mean_m']:7.0f} false={r['false_tracks_per_scan']:6.2f} "
              f"missed={r['missed_per_scan']:.2f} idsw={r['id_switches']:.1f} wall={r['wall_s']:.0f}s")
    print("reference", json.dumps(ref))
    print("selected", pick)
    if a.write:
        r = rows[pick]
        y = ROOT / "configs/stage4.yaml"
        txt = y.read_text().split("clutter_map_est:")[0].rstrip() + "\n"
        txt += (f"clutter_map_est:             # FROZEN by scripts/stage4_select.py --write (tuning window, 5 seeds): {pick}\n"
                f"  dr_m: {r['dr_m']}\n  daz_deg: {r['daz_deg']}\n  tau_scans: {r['tau_scans']}\n")
        y.write_text(txt)


if __name__ == "__main__":
    main()
