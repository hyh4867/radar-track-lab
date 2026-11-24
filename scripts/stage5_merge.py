"""Merge results/stage5/<dst>_p2/*.json into results/stage5/<dst>/ (same file names). usage: [eval|katl]"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
dst = sys.argv[1] if len(sys.argv) > 1 else "eval"  # merge <dst>_p2 into <dst>
for p2 in sorted((ROOT / f"results/stage5/{dst}_p2").glob("*.json")):
    p1 = ROOT / f"results/stage5/{dst}" / p2.name
    a, b = json.loads(p1.read_text()), json.loads(p2.read_text())
    seen = {r["seed"] for r in a["runs"]}
    a["runs"] += [r for r in b["runs"] if r["seed"] not in seen]
    a["runs"].sort(key=lambda r: r["seed"])
    a.setdefault("merged_from", []).append({"file": str(p2.relative_to(ROOT)), "overrides": b["overrides"],
                                            "code": b["code"], "memory_wait_s": b.get("memory_wait_s")})
    p1.write_text(json.dumps(a))
    print(p1.name, len(a["runs"]), [r["seed"] for r in a["runs"]][:1], "...", a["runs"][-1]["seed"])
