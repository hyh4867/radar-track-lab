"""Summary of results/stage3/diag_near/ (scripts/stage3_diag_near.py). json, numpy, scipy only.

Output: results/stage3/diag_near/summary.json and summary.md
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

D = Path(__file__).resolve().parents[1] / "results/stage3/diag_near"


def tci(x):
    x = np.asarray(x, float)
    m = x.mean()
    h = stats.t.ppf(0.975, x.size - 1) * x.std(ddof=1) / np.sqrt(x.size) if x.std() > 0 else 0.0
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h)}


def main() -> None:
    out, L = {}, ["# 레이더 15 km 안 misses 잃음: 원뿔 켬(M4) 대 끔(M4, 고각 상한 90°)", "",
                  "`scripts/stage3_diag_near.py` → `scripts/stage3_diag_near_summary.py`. 사후 진단, 판정 대상 아님. seed 20개.", "",
                  "| 구간 | 방법 | 15 km 안 misses 잃음 /run (M4 → 끔) | 전체 misses 잃음 /run | ID switch /run | 짝 차이 ID switch (M4 − 끔) |",
                  "|---|---|---:|---:|---:|---:|"]
    windows = []
    for sid in ("EHAM_1106_eval", "KATL_1106_peak"):
        for me in ("ekf", "imm"):
            a = json.loads((D / f"{sid}__M4__{me}.json").read_text())
            b = json.loads((D / f"{sid}__M4_nocone__{me}.json").read_text())
            assert [r["seed"] for r in a["runs"]] == [r["seed"] for r in b["runs"]]
            g = lambda doc, f: np.array([r[f] for r in doc["runs"]], float)  # noqa: E731
            row = {f: {"M4": float(g(a, f).mean()), "nocone": float(g(b, f).mean()), "diff": tci(g(a, f) - g(b, f))}
                   for f in ("misses_lost_near", "misses_lost", "id_switches", "lost_near_any_cause")}
            out[f"{sid}|{me}"] = row
            d = row["id_switches"]["diff"]
            L.append(f"| {sid} | {me} | {row['misses_lost_near']['M4']:.2f} → {row['misses_lost_near']['nocone']:.2f} | "
                     f"{row['misses_lost']['M4']:.2f} → {row['misses_lost']['nocone']:.2f} | "
                     f"{row['id_switches']['M4']:.2f} → {row['id_switches']['nocone']:.2f} | "
                     f"{d['mean']:+.2f} [{d['lo']:+.2f}, {d['hi']:+.2f}] |")
            windows += [(sid, me, w) for r in a["runs"] for e in r["near_events"] for w in e["window"]]
    ill = [w for _, _, w in windows if w["illuminated"]]
    und = [w for w in ill if not w["detected"]]
    inc = [w for w in und if w["in_cone"]]
    det = [w for w in ill if w["detected"]]
    alt_und = np.array([w["alt_m"] for w in inc])
    gr_und = np.array([w["ground_m"] for w in inc])
    ev = {"window_scans": len(windows), "illuminated": len(ill), "undetected": len(und), "undetected_in_cone": len(inc),
          "undetected_outside_cone": len(und) - len(inc), "detected": len(det),
          "detected_in_cone": sum(w["in_cone"] for w in det),
          "in_cone_alt_m_quantiles": np.percentile(alt_und, [10, 50, 90]).tolist() if alt_und.size else [],
          "in_cone_ground_km_quantiles": (np.percentile(gr_und, [10, 50, 90]) / 1e3).tolist() if gr_und.size else []}
    out["m4_near_event_windows"] = ev
    L += ["", "## M4의 15 km 안 misses 잃음 사건: 분류 창(마지막 배정 scan −3…+2)의 scan별 상태 (네 조합 합)", "",
          f"- 창 scan {ev['window_scans']}개 중 조사됨 {ev['illuminated']}개: 탐지 안 됨 {ev['undetected']}개"
          f"(그중 원뿔 안 {ev['undetected_in_cone']}개, 원뿔 밖 {ev['undetected_outside_cone']}개), 탐지됨 {ev['detected']}개"
          f"(원뿔 안인데 탐지됨 {ev['detected_in_cone']}개).",
          f"- 원뿔 안에서 탐지 안 된 scan의 정답 고도 10/50/90%: {', '.join(f'{x:,.0f}' for x in ev['in_cone_alt_m_quantiles'])} m, "
          f"지상 거리: {', '.join(f'{x:.1f}' for x in ev['in_cone_ground_km_quantiles'])} km."]
    (D / "summary.json").write_text(json.dumps(out, indent=1))
    (D / "summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
