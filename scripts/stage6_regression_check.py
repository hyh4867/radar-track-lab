"""Compare stage 6 regression reruns with the stage 5 files seed by seed (PREREGISTRATION_6 6).

Also usable on the full part 1 runs: --full compares results/stage6/cone/<sid>__M4__{ekf,imm,ekf_h1,imm_h1}.json
with results/stage5/cone/ for all 13 windows and 20 seeds. Writes results/stage6/regression[_full].json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from stage5_regression_check import same  # noqa: E402

KEYS = ("id_switches", "misses_lost", "misses_lost_near")
WINDOWS = ("EHAM_1106_eval", "EGLL_1106_peak", "EGLL_1111_same", "EHAM_1106_busy2", "EHAM_1111_same", "ENGM_1106_peak",
           "ENGM_1111_same", "KATL_1106_peak", "KATL_1111_same", "LSZH_1106_peak", "LSZH_1111_same", "YSSY_1106_peak",
           "YSSY_1111_same")


def compare(new_path, old_path, keys, n_expected):
    new, old = json.loads(new_path.read_text()), json.loads(old_path.read_text())
    o = {r["seed"]: r for r in old["runs"]}
    bad_rows = []
    for r in new["runs"]:
        b = o[r["seed"]]
        bad = [k for k in r["summary"] if isinstance(r["summary"][k], (int, float)) and not same(r["summary"][k], b["summary"].get(k))]
        bad += [k for k in keys if not same(r[k], b[k])]
        if bad:
            bad_rows.append({"seed": r["seed"], "differ": bad})
    return {"new": str(new_path.relative_to(ROOT)), "old": str(old_path.relative_to(ROOT)), "n": len(new["runs"]),
            "bad": bad_rows, "pass": not bad_rows and len(new["runs"]) == n_expected}


def main() -> None:
    full = "--full" in sys.argv
    files = []
    if full:
        for sid in WINDOWS:
            for m in ("ekf", "imm", "ekf_h1", "imm_h1"):
                n = f"{sid}__M4__{m}.json"
                files.append(compare(ROOT / "results/stage6/cone" / n, ROOT / "results/stage5/cone" / n, KEYS, 20))
    else:
        R = ROOT / "results/stage6/regression"
        for sid in ("EHAM_1106_eval", "KATL_1106_peak"):
            for m in ("ekf", "imm", "ekf_h1", "imm_h1"):
                n = f"{sid}__M4__{m}.json"
                files.append(compare(R / "cone" / n, ROOT / "results/stage5/cone" / n, KEYS, 2))
        n = "EHAM_1106_eval__jipda_amap__lam200_map.json"
        files.append(compare(R / n, ROOT / "results/stage5/eval" / n, (), 2))
    out = {"files": files, "pass": all(f["pass"] for f in files)}
    (ROOT / f"results/stage6/regression{'_full' if full else ''}.json").write_text(json.dumps(out, indent=1))
    for f in files:
        print(f["pass"], f["new"], f["n"], f["bad"][:2])
    print("ALL PASS" if out["pass"] else "FAIL")


if __name__ == "__main__":
    main()
