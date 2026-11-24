"""Stage 6 part 2 selection (PREREGISTRATION_6 8): score = max over lam5_map / lam1000_uniform of
GOSPA(JIPDA-amap, floor f) / GOSPA(JIPDA), tuning window seed means. Smallest wins; tie (4 decimals) -> smaller sum of
missed targets. --write freezes floor_frac in configs/stage6.yaml. Output: results/stage6/tune_selection.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stage5_select import means  # noqa: E402

T = ROOT / "results/stage6/tune"
REF = {"lam5_map": T / "EHAM_1106_tune__jipda__lam5_map.json",
       "lam1000_uniform": ROOT / "results/stage5/tune/EHAM_1106_tune__jipda__lam1000_uniform.json"}
STAGE5 = {"lam5_map": T / "EHAM_1106_tune__jipda_amap__lam5_map.json",
          "lam1000_uniform": ROOT / "results/stage5/tune/EHAM_1106_tune__jipda_amap__lam1000_uniform__n20_30.json"}
CANDS = ("0.25", "0.5", "1.0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    ref = {c: means(p) for c, p in REF.items()}
    s5 = {c: means(p) for c, p in STAGE5.items()}
    rows = {}
    for f in CANDS:
        m = {c: means(T / f"EHAM_1106_tune__jipda_amap__{c}__f{f}.json") for c in REF}
        ratio = {c: m[c]["gospa_mean_m"] / ref[c]["gospa_mean_m"] for c in m}
        rows[f] = {"means": m, "gospa_ratio": ratio, "score": max(ratio.values()),
                   "missed_sum": sum(m[c]["missed_per_scan"] for c in m)}
    best = min(CANDS, key=lambda f: (round(rows[f]["score"], 4), rows[f]["missed_sum"]))
    s5_ratio = {c: s5[c]["gospa_mean_m"] / ref[c]["gospa_mean_m"] for c in s5}
    out = {"reference_jipda": ref, "stage5_amap": {"means": s5, "gospa_ratio": s5_ratio, "score": max(s5_ratio.values())},
           "candidates": rows, "selected": best, "floor_frac": float(best)}
    (ROOT / "results/stage6/tune_selection.json").write_text(json.dumps(out, indent=1))
    for f in CANDS:
        r = rows[f]
        print(f"f={f}: score {r['score']:.4f} lam5 {r['gospa_ratio']['lam5_map']:.3f} uniform {r['gospa_ratio']['lam1000_uniform']:.3f} "
              f"missed lam5 {r['means']['lam5_map']['missed_per_scan']:.3f}")
    print(f"stage5 amap: score {max(s5_ratio.values()):.4f} lam5 {s5_ratio['lam5_map']:.3f} uniform {s5_ratio['lam1000_uniform']:.3f} "
          f"missed lam5 {s5['lam5_map']['missed_per_scan']:.3f}")
    print("selected", best)
    if a.write:
        p = ROOT / "configs/stage6.yaml"
        s = re.sub(r"  floor_frac: null.*", f"  floor_frac: {float(best)}            # FROZEN by scripts/stage6_select.py --write",
                   p.read_text())
        p.write_text(s)
        print("written")


if __name__ == "__main__":
    main()
