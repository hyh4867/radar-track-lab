"""Stage 5 selection (PREREGISTRATION_5 4): score = max over lam1000_map / lam1000_uniform of
GOSPA(JIPDA-amap) / GOSPA(JIPDA), seed means on the tuning window. Smallest score wins; tie (4 decimals) -> smaller
sum of false tracks. --write freezes n_min and tau_scans in configs/stage5.yaml.
Output: results/stage5/tune_selection.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "results/stage5/tune"
REF = {"map": ROOT / "results/stage4/tune/EHAM_1106_tune__jipda__lam1000_map.json",
       "uniform": T / "EHAM_1106_tune__jipda__lam1000_uniform.json"}
CANDS = ("n5_30", "n5_100", "n20_30", "n20_100")
SEEDS = list(range(20271106, 20271111))


def means(path):
    d = json.loads(path.read_text())
    runs = {r["seed"]: r for r in d["runs"]}
    if sorted(runs) != SEEDS:
        raise SystemExit(f"{path.name}: seeds {sorted(runs)}")
    f = lambda k: float(np.mean([runs[s]["summary"][k] for s in SEEDS]))  # noqa: E731
    return {"gospa_mean_m": f("gospa_mean_m"), "false_tracks_per_scan": f("false_tracks_per_scan"),
            "missed_per_scan": f("missed_per_scan"), "id_switches": f("id_switches"),
            "wall_s": float(np.mean([runs[s]["wall_s"] for s in SEEDS]))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    ref = {c: means(p) for c, p in REF.items()}
    rows = {}
    for cand in CANDS:
        m = {c: means(T / f"EHAM_1106_tune__jipda_amap__lam1000_{c}__{cand}.json") for c in ("map", "uniform")}
        ratio = {c: m[c]["gospa_mean_m"] / ref[c]["gospa_mean_m"] for c in m}
        rows[cand] = {"means": m, "gospa_ratio": ratio, "score": max(ratio.values()),
                      "false_sum": m["map"]["false_tracks_per_scan"] + m["uniform"]["false_tracks_per_scan"]}
    best = min(CANDS, key=lambda c: (round(rows[c]["score"], 4), rows[c]["false_sum"]))
    n, tau = (float(x) for x in re.fullmatch(r"n(\d+)_(\d+)", best).groups())
    out = {"reference_jipda": ref, "candidates": rows, "selected": best, "n_min": n, "tau_scans": tau}
    (ROOT / "results/stage5/tune_selection.json").write_text(json.dumps(out, indent=1))
    for c in CANDS:
        r = rows[c]
        print(f"{c}: score {r['score']:.4f} map {r['gospa_ratio']['map']:.3f} uniform {r['gospa_ratio']['uniform']:.3f} "
              f"false map {r['means']['map']['false_tracks_per_scan']:.2f} uniform {r['means']['uniform']['false_tracks_per_scan']:.2f}")
    print("selected", best)
    if a.write:
        p = ROOT / "configs/stage5.yaml"
        s = p.read_text()
        s = re.sub(r"  n_min: null.*", f"  n_min: {n}                # FROZEN by scripts/stage5_select.py --write ({best})", s)
        s = re.sub(r"  tau_scans: null.*", f"  tau_scans: {tau}            # FROZEN by scripts/stage5_select.py --write ({best})", s)
        p.write_text(s)
        print("written", p.name)


if __name__ == "__main__":
    main()
