"""Stage 3 B0 report: fixed 6 km pre-gate vs adaptive pre-gate, same seeds (docs/PREREGISTRATION_3.md 4.1).

Reads results/stage3/b0/*.json (scripts/stage3_b0.sh) and writes results/stage3/b0_summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.metrics import mean_ci  # noqa: E402

D = ROOT / "results/stage3/b0"
METRICS = ("id_switches", "gospa_mean_m", "rmse_m", "false_tracks_per_scan", "missed_per_scan", "fragmentations",
           "init_delay_mean_s")


def load(sid, method, tag):
    p = D / f"{sid}__{method}__{tag}.json"
    if not p.exists():
        return None
    return {r["seed"]: r for r in json.loads(p.read_text())["runs"]}


def paired(a, b, f):
    seeds = sorted(set(a) & set(b))
    x = np.array([(b[s]["summary"][f] if f != "wall_s" else b[s]["wall_s"]) for s in seeds], float)
    y = np.array([(a[s]["summary"][f] if f != "wall_s" else a[s]["wall_s"]) for s in seeds], float)
    d = x - y
    d = d[np.isfinite(d)]
    m, h = mean_ci(d)
    return {"mean": m, "lo": m - h, "hi": m + h, "n": int(d.size), "ref": float(np.nanmean(y)), "new": float(np.nanmean(x))}


def main() -> None:
    out = {"check": {}, "eval": {}, "oos": {}}
    for lam in (5, 200):
        for m in ("ekf", "imm"):
            a, b = load("EHAM_1106_eval", m, f"check_lam{lam}_adaptive"), load("EHAM_1106_eval", m, f"check_lam{lam}_none")
            if a and b:
                same = all(a[s]["summary"] == b[s]["summary"] for s in a)
                out["check"][f"lam{lam}_{m}"] = {"seeds": sorted(a), "identical": bool(same)}
    for lam in (5, 200, 1000):
        for m in ("ekf", "imm"):
            a, b = load("EHAM_1106_eval", m, f"lam{lam}_fixed"), load("EHAM_1106_eval", m, f"lam{lam}_adaptive")
            if a and b:
                out["eval"][f"lam{lam}_{m}"] = {f: paired(a, b, f) for f in METRICS + ("wall_s",)}
    sids = sorted({p.name.split("__")[0] for p in D.glob("*__lam5_fixed.json")})
    for sid in sids:
        for m in ("ekf", "imm"):
            a, b = load(sid, m, "lam5_fixed"), load(sid, m, "lam5_adaptive")
            if a and b:
                out["oos"][f"{sid}_{m}"] = {f: paired(a, b, f) for f in METRICS + ("wall_s",)}
    # preregistered predictions
    lam5 = {k: v for k, v in out["oos"].items()}
    out["predictions"] = {
        "lam5_abs_dIDsw_lt_0.3": {"n_ok": sum(abs(v["id_switches"]["mean"]) < 0.3 for v in lam5.values()), "n": len(lam5)},
        "lam5_gospa_rel_lt_0.1pct": {"n_ok": sum(abs(v["gospa_mean_m"]["mean"]) / v["gospa_mean_m"]["ref"] < 1e-3
                                                for v in lam5.values()), "n": len(lam5)},
    }
    if "lam1000_ekf" in out["eval"]:
        e = out["eval"]["lam1000_ekf"]
        out["predictions"]["lam1000_ekf_false_within_5pct"] = abs(e["false_tracks_per_scan"]["mean"]) / e["false_tracks_per_scan"]["ref"] <= 0.05
        out["predictions"]["lam1000_ekf_false_rel"] = e["false_tracks_per_scan"]["mean"] / e["false_tracks_per_scan"]["ref"]
        out["predictions"]["lam1000_ekf_wall_rel"] = e["wall_s"]["mean"] / e["wall_s"]["ref"]
    (ROOT / "results/stage3/b0_summary.json").write_text(json.dumps(out, indent=1))
    f2 = lambda c: f"{c['mean']:+.2f} [{c['lo']:+.2f}, {c['hi']:+.2f}]"  # noqa: E731
    L = ["# B0: 6 km 고정 앞단 걸러내기 → 항적별 반지름 (같은 seed 짝 차이, 고친 후 − 고치기 전)", "",
         "`scripts/stage3_b0_report.py`가 `results/stage3/b0/`에서 만든 파일. [ ]는 seed 20개 짝 차이의 95% t-구간.", "",
         "## 실제 장면에서 \"앞단 걸러내기 없음\"과의 일치 (seed 2개)", ""]
    for k, v in out["check"].items():
        L.append(f"- {k}: {'완전히 같음' if v['identical'] else '다름'}")
    L += ["", "## 스히폴 평가 구간", "", "| 조건 | 방법 | ID switch | GOSPA (m) | scan-end RMSE (m) | 가짜 항적 /scan | 놓친 표적 /scan | 실행 시간 (s) |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for k, v in out["eval"].items():
        lam, m = k.split("_")
        L.append(f"| λ {lam[3:]} | {m} | {f2(v['id_switches'])} | {f2(v['gospa_mean_m'])} | {f2(v['rmse_m'])} | "
                 f"{f2(v['false_tracks_per_scan'])} | {f2(v['missed_per_scan'])} | {f2(v['wall_s'])} |")
    L += ["", "고치기 전 값(같은 표의 기준): " + "; ".join(
        f"{k} ID switch {v['id_switches']['ref']:.2f}, 가짜 항적 {v['false_tracks_per_scan']['ref']:.2f}" for k, v in out["eval"].items()),
          "", "## 15개 구간 (λ 5)", "", "| 구간 | 방법 | ID switch | GOSPA (m) | scan-end RMSE (m) |", "|---|---|---:|---:|---:|"]
    for k, v in out["oos"].items():
        sid, m = k.rsplit("_", 1)
        L.append(f"| {sid} | {m} | {f2(v['id_switches'])} | {f2(v['gospa_mean_m'])} | {f2(v['rmse_m'])} |")
    p = out["predictions"]
    L += ["", "## 예측 대 실제", "",
          f"- λ 5에서 구간별 |ΔID switch| < 0.3: {p['lam5_abs_dIDsw_lt_0.3']['n_ok']}/{p['lam5_abs_dIDsw_lt_0.3']['n']}",
          f"- λ 5에서 GOSPA 변화 < 0.1%: {p['lam5_gospa_rel_lt_0.1pct']['n_ok']}/{p['lam5_gospa_rel_lt_0.1pct']['n']}"]
    if "lam1000_ekf_false_rel" in p:
        L += [f"- λ 1000 EKF 가짜 항적 변화 ±5% 안: {p['lam1000_ekf_false_within_5pct']} ({100 * p['lam1000_ekf_false_rel']:+.1f}%)",
              f"- λ 1000 EKF 실행 시간 변화: {100 * p['lam1000_ekf_wall_rel']:+.1f}% (예측 +0–30%)"]
    (ROOT / "results/stage3/b0_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
