"""Compare the stage 5 regression reruns (results/stage5/regression/) with the stage 3/4 files seed by seed.

PREREGISTRATION_5 6: every summary metric equal (relative 1e-9); for the cone runs also ID switches and misses losses.
Writes results/stage5/regression.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results/stage5/regression"


def same(a, b):
    return a == b or (isinstance(a, (int, float)) and isinstance(b, (int, float))
                      and abs(a - b) <= 1e-9 * max(abs(a), abs(b)))


def compare(new_path, old_path, keys=()):
    new, old = json.loads(new_path.read_text()), json.loads(old_path.read_text())
    o = {r["seed"]: r for r in old["runs"]}
    rows = []
    for r in new["runs"]:
        b = o[r["seed"]]
        bad = [k for k in r["summary"] if isinstance(r["summary"][k], (int, float))
               and not same(r["summary"][k], b["summary"].get(k))]
        bad += [k for k in keys if not same(r[k], b[k])]
        rows.append({"seed": r["seed"], "n_compared": len(r["summary"]) + len(keys), "differ": bad,
                     "id_switches": [r["summary"]["id_switches"], b["summary"]["id_switches"]],
                     "false_tracks_per_scan": [r["summary"]["false_tracks_per_scan"],
                                               b["summary"]["false_tracks_per_scan"]]})
    return {"new": str(new_path.relative_to(ROOT)), "old": str(old_path.relative_to(ROOT)), "code": new["code"],
            "rows": rows, "pass": all(not x["differ"] for x in rows) and len(rows) == 2}


def main() -> None:
    pairs = []
    for m in ("jipda", "jipda_est"):
        n = f"EHAM_1106_eval__{m}__lam1000_map.json"
        pairs.append((R / n, ROOT / "results/stage3/b1" / n, ()))
    n = "EHAM_1106_eval__jipda_map__lam200_map.json"
    pairs.append((R / n, ROOT / "results/stage4/eval" / n, ()))
    ck = ("id_switches", "misses_lost", "misses_lost_near")
    for sid in ("EHAM_1106_eval", "KATL_1106_peak"):
        for m in ("ekf", "imm"):
            pairs.append((R / "cone" / f"{sid}__M4__{m}.json", ROOT / f"results/stage4/cone/{sid}__M4_regression__{m}.json", ck))
            pairs.append((R / "cone" / f"{sid}__M4__{m}_cone.json", ROOT / f"results/stage4/cone/{sid}__M4__{m}_cone.json", ck))
    out = {"files": [compare(*p) for p in pairs]}
    out["pass"] = all(f["pass"] for f in out["files"])
    (ROOT / "results/stage5/regression.json").write_text(json.dumps(out, indent=1))
    for f in out["files"]:
        print(f["pass"], f["new"], [x["differ"] for x in f["rows"]])
    print("ALL PASS" if out["pass"] else "FAIL")


if __name__ == "__main__":
    main()
