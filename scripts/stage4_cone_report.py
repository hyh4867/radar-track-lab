"""Stage 4 priority 2 report (PREREGISTRATION_4 9.4): recovery of the overhead-cone ID-switch effect by cone hold.

Reads results/stage4/cone/<sid>__M4__<m>_cone.json (hold), results/stage4/cone/<sid>__M4_regression__<m>.json
(M4 rerun, must equal results/stage3/diag_near M4) and results/stage3/diag_near/<sid>__M4_nocone__<m>.json.
Writes results/stage4/cone_summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from radar_track_lab.metrics import mean_ci  # noqa: E402

C, DN = ROOT / "results/stage4/cone", ROOT / "results/stage3/diag_near"
SIDE = ("false_tracks_per_scan", "gospa_mean_m", "rmse_m", "missed_per_scan")


def runs(p):
    return {r["seed"]: r for r in json.loads(p.read_text())["runs"]}


def ci(x):
    m, h = mean_ci(np.asarray(x, float))
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h)}


def main() -> None:
    rng = np.random.default_rng(0)
    out, md = {}, ["# 4단계 우선순위 2: 원뿔 안을 아는 항적 유지 (M4, seed 20개)", "",
                   "`scripts/stage4_cone_report.py`가 만든 파일. 회복률 = (M4 − 유지) / (M4 − 원뿔 끔), ID switch seed 평균. "
                   "회복률 구간은 seed 묶음 bootstrap 10,000회(난수 seed 0, M4·유지·끔을 같은 seed로 묶어 뽑음). 차이 [ ]는 짝 t-구간.", "",
                   "| 구간 | 방법 | ID switch M4 | 유지 | 원뿔 끔 | 회복률 [95%] | 짝 차이 유지 − M4 | misses 잃음 M4 → 유지 (끔) | 15 km 안 misses 잃음 M4 → 유지 | 유지 항적-scan /run | 유지 시간 초과 /run |",
                   "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    side_md = ["", "## 부작용 (유지 − M4, 짝 t-구간; 비 = 유지/M4)", "",
               "| 구간 | 방법 | " + " | ".join(SIDE) + " |", "|---|---|" + "---:|" * len(SIDE)]
    reg_ok = True
    for sid in ("EHAM_1106_eval", "KATL_1106_peak"):
        for m in ("ekf", "imm"):
            h, b, n = runs(C / f"{sid}__M4__{m}_cone.json"), runs(C / f"{sid}__M4_regression__{m}.json"), runs(DN / f"{sid}__M4_nocone__{m}.json")
            d3 = runs(DN / f"{sid}__M4__{m}.json")
            ss = sorted(set(h) & set(b) & set(n))
            reg = all(b[s][k] == d3[s][k] for s in b for k in ("id_switches", "misses_lost", "misses_lost_near"))
            reg_ok &= reg
            I = lambda d: np.array([d[s]["id_switches"] for s in ss], float)  # noqa: E731
            ib, ih, inn = I(b), I(h), I(n)
            rec = (ib.mean() - ih.mean()) / (ib.mean() - inn.mean())
            bs = []
            for _ in range(10_000):
                k = rng.integers(0, len(ss), len(ss))
                den = ib[k].mean() - inn[k].mean()
                bs.append((ib[k].mean() - ih[k].mean()) / den if den != 0 else np.nan)
            lo, hi = np.nanpercentile(bs, [2.5, 97.5])
            g = lambda d, f: np.mean([d[s][f] for s in ss])  # noqa: E731
            hs = np.mean([h[s]["cone_stats"]["held_track_scans"] for s in ss])
            he = np.mean([h[s]["cone_stats"]["hold_expired"] for s in ss])
            pdiff = ci(ih - ib)
            side = {f: {**ci([h[s]["summary"][f] - b[s]["summary"][f] for s in ss]),
                        "ratio": float(np.mean([h[s]["summary"][f] for s in ss]) / np.mean([b[s]["summary"][f] for s in ss]))}
                    for f in SIDE}
            out[f"{sid}|{m}"] = {"idsw_m4": float(ib.mean()), "idsw_hold": float(ih.mean()), "idsw_nocone": float(inn.mean()),
                                  "recovery": float(rec), "recovery_ci": [float(lo), float(hi)], "paired_hold_minus_m4": pdiff,
                                  "misses_lost": [g(b, "misses_lost"), g(h, "misses_lost"), g(n, "misses_lost")],
                                  "misses_lost_near": [g(b, "misses_lost_near"), g(h, "misses_lost_near"), g(n, "misses_lost_near")],
                                  "held_track_scans_per_run": float(hs), "hold_expired_per_run": float(he),
                                  "side_effects": side, "regression_equal_stage3": reg, "n": len(ss)}
            md.append(f"| {sid} | {m} | {ib.mean():.2f} | {ih.mean():.2f} | {inn.mean():.2f} | {rec:.1%} [{lo:.1%}, {hi:.1%}] | "
                      f"{pdiff['mean']:+.2f} [{pdiff['lo']:+.2f}, {pdiff['hi']:+.2f}] | "
                      f"{g(b, 'misses_lost'):.2f} → {g(h, 'misses_lost'):.2f} ({g(n, 'misses_lost'):.2f}) | "
                      f"{g(b, 'misses_lost_near'):.2f} → {g(h, 'misses_lost_near'):.2f} | {hs:.0f} | {he:.1f} |")
            side_md.append(f"| {sid} | {m} | " + " | ".join(
                f"{v['mean']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}] (비 {v['ratio']:.3f})" for v in side.values()) + " |")
    md += side_md + ["", f"퇴행 확인(유지 끔, 이 스크립트 경로 = 3단계 diag_near M4, seed 20개 × ID switch·misses 잃음·15 km 안): "
                     f"**{'모두 같음' if reg_ok else '다름'}**", ""]
    out["regression_all_equal"] = reg_ok
    (ROOT / "results/stage4/cone_summary.json").write_text(json.dumps(out, indent=1))
    (ROOT / "results/stage4/cone_summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
