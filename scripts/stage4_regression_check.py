"""Compare the stage 4 regression reruns (results/stage4/regression/) with results/stage3/b1 seed by seed.

Writes results/stage4/regression.json. PREREGISTRATION_4 3: every summary metric equal (relative 1e-9).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out = {"files": [], "pass": True}
    for p in sorted((ROOT / "results/stage4/regression").glob("*.json")):
        new = json.loads(p.read_text())
        old = json.loads((ROOT / "results/stage3/b1" / p.name).read_text())
        o = {r["seed"]: r["summary"] for r in old["runs"]}
        rows = []
        for r in new["runs"]:
            a, b = r["summary"], o[r["seed"]]
            bad = [k for k in a if isinstance(a[k], (int, float)) and
                   not (a[k] == b[k] or abs(a[k] - b[k]) <= 1e-9 * max(abs(a[k]), abs(b[k])))]
            rows.append({"seed": r["seed"], "n_metrics": len(a), "differ": bad,
                         "false_tracks_per_scan": [a["false_tracks_per_scan"], b["false_tracks_per_scan"]],
                         "gospa_mean_m": [a["gospa_mean_m"], b["gospa_mean_m"]]})
            out["pass"] &= not bad
        out["files"].append({"file": p.name, "code": new["code"], "rows": rows})
    (ROOT / "results/stage4/regression.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
