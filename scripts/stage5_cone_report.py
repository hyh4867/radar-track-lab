"""Stage 5 part 2 report (PREREGISTRATION_5 8): cone hold v2 (H1, H2) vs M4, the stage 4 hold and the cone off.

Reads results/stage5/cone/<sid>__M4__<m>[_cone|_h1|_h2].json, results/stage5/cone/<sid>__M4_nocone__<m>.json
(11 windows) and results/stage3/diag_near/<sid>__M4[_nocone]__<m>.json (EHAM_1106_eval, KATL_1106_peak).
Writes results/stage5/cone_summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from radar_track_lab.metrics import mean_ci  # noqa: E402

C, DN = ROOT / "results/stage5/cone", ROOT / "results/stage3/diag_near"
WINDOWS = ("EHAM_1106_eval", "EGLL_1106_peak", "EGLL_1111_same", "EHAM_1106_busy2", "EHAM_1111_same", "ENGM_1106_peak",
           "ENGM_1111_same", "KATL_1106_peak", "KATL_1111_same", "LSZH_1106_peak", "LSZH_1111_same", "YSSY_1106_peak",
           "YSSY_1111_same")
DIAG = ("EHAM_1106_eval", "KATL_1106_peak")
VARS = ("cone", "h1", "h2")
SIDE = ("false_tracks_per_scan", "gospa_mean_m", "rmse_m", "missed_per_scan")
MIN_EFFECT = 1.0


def runs(p):
    return {r["seed"]: r for r in json.loads(p.read_text())["runs"]} if p.exists() else None


def ci(x):
    m, h = mean_ci(np.asarray(x, float))
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h)}


def main() -> None:
    rng = np.random.default_rng(0)
    out = {"windows": {}}
    reg_ok = True
    for sid in WINDOWS:
        for m in ("ekf", "imm"):
            b = runs(C / f"{sid}__M4__{m}.json")
            n = runs((DN if sid in DIAG else C) / f"{sid}__M4_nocone__{m}.json")
            V = {v: runs(C / f"{sid}__M4__{m}_{v}.json") for v in VARS}
            if b is None or n is None or any(x is None for x in V.values()):
                continue
            ss = sorted(set(b) & set(n) & set.intersection(*(set(x) for x in V.values())))
            row = {"n": len(ss)}
            if sid in DIAG:
                d3 = runs(DN / f"{sid}__M4__{m}.json")
                row["m4_equals_stage3_diag_near"] = all(b[s][k] == d3[s][k] for s in ss
                                                        for k in ("id_switches", "misses_lost", "misses_lost_near"))
                reg_ok &= row["m4_equals_stage3_diag_near"]
            I = lambda d: np.array([d[s]["id_switches"] for s in ss], float)  # noqa: E731
            ib, inn = I(b), I(n)
            effect = ib.mean() - inn.mean()
            row.update({"idsw_m4": float(ib.mean()), "idsw_nocone": float(inn.mean()), "cone_effect": float(effect),
                        "near_other_m4": float(np.mean([b[s].get("causes", {}).get("near_other", 0) for s in ss]))})
            K = rng.integers(0, len(ss), (10_000, len(ss)))
            for v, d in V.items():
                iv = I(d)
                r = {"idsw": float(iv.mean()), "paired_minus_m4": ci(iv - ib)}
                if effect >= MIN_EFFECT:
                    den = ib[K].mean(1) - inn[K].mean(1)
                    bs = np.where(den != 0, (ib[K].mean(1) - iv[K].mean(1)) / np.where(den != 0, den, 1), np.nan)
                    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
                    r["recovery"], r["recovery_ci"] = float((ib.mean() - iv.mean()) / effect), [float(lo), float(hi)]
                else:
                    r["recovery"], r["recovery_ci"] = None, None
                r["side"] = {f: {**ci([d[s]["summary"][f] - b[s]["summary"][f] for s in ss]),
                                 "ratio": float(np.mean([d[s]["summary"][f] for s in ss]) /
                                                np.mean([b[s]["summary"][f] for s in ss]))} for f in SIDE}
                r["near_other"] = float(np.mean([d[s].get("causes", {}).get("near_other", 0) for s in ss]))
                r["misses_lost_near"] = float(np.mean([d[s]["misses_lost_near"] for s in ss]))
                cs = [d[s]["cone_stats"] for s in ss]
                r["held_track_scans"] = float(np.mean([c["held_track_scans"] for c in cs]))
                r["gate_rejected_pairs"] = float(np.mean([c.get("gate_rejected_pairs", 0) for c in cs]))
                row[v] = r
            row["misses_lost_near_m4"] = float(np.mean([b[s]["misses_lost_near"] for s in ss]))
            row["h1_minus_cone"] = ci(I(V["h1"]) - I(V["cone"]))
            row["h2_minus_h1"] = ci(I(V["h2"]) - I(V["h1"]))
            out["windows"][f"{sid}|{m}"] = row
    W = out["windows"]
    complete = all(f"{s}|{m}" in W for s in WINDOWS for m in ("ekf", "imm"))
    md = ["# 5단계 2부: 원뿔 유지 v2 (M4, seed 20개, 13개 구간)", "",
          "`scripts/stage5_cone_report.py`가 만든 파일. 회복률 = (M4 − 방법) / (M4 − 원뿔 끔), ID switch seed 평균, "
          f"원뿔 효과(M4 − 끔)가 run당 {MIN_EFFECT} 미만이면 '–'. 회복률 구간은 seed 묶음 bootstrap 10,000회(난수 seed 0). "
          "원뿔 끔은 EHAM_1106_eval·KATL_1106_peak만 3단계 diag_near, 나머지는 이 단계 새 실행.", ""]
    if complete:
        k = lambda s, m, v: W[f"{s}|{m}"][v]["recovery"]  # noqa: E731
        c1 = all((k("KATL_1106_peak", m, "h1") or -1) >= 0.5 for m in ("ekf", "imm"))
        c2 = all((k("EHAM_1106_eval", m, "h1") or -1) >= 0.8 for m in ("ekf", "imm"))
        fr = {f"{s}|{m}": W[f"{s}|{m}"]["h1"]["side"]["false_tracks_per_scan"]["ratio"] for s in WINDOWS for m in ("ekf", "imm")}
        c3 = all(x <= 1.10 for x in fr.values())
        n_less = sum(W[f"{s}|ekf"]["h1"]["idsw"] < W[f"{s}|ekf"]["idsw_m4"] for s in WINDOWS)
        c4 = n_less >= 11
        part = all(W[f"KATL_1106_peak|{m}"]["h1_minus_cone"]["hi"] < 0 for m in ("ekf", "imm"))
        verdict = "개선" if (c1 and c2 and c3 and c4) else ("부분 개선" if part else "개선 없음")
        out["verdict"] = {"verdict": verdict, "c1_katl_ge_50": c1, "c2_eham_ge_80": c2, "c3_false_le_1.1_all": c3,
                          "c3_ratios_over_1.1": {kk: x for kk, x in fr.items() if x > 1.10}, "c4_ekf_idsw_less_n": int(n_less),
                          "c4": c4, "partial_katl_h1_below_cone": part}
        md += [f"H1 판정: **{verdict}** (1 KATL EKF·IMM 회복률 ≥ 50%: {c1}, 2 EHAM ≥ 80%: {c2}, "
               f"3 가짜 항적 ≤ 1.10×M4 26개 모두: {c3}" + (f" (넘은 곳: " + ", ".join(f"{kk} {x:.3f}" for kk, x in fr.items() if x > 1.10) + ")" if not c3 else "") +
               f", 4 EKF ID switch < M4 구간 {n_less}/13: {c4}; 부분 개선 조건 KATL H1 − 4단계 유지 상한 < 0: {part})", ""]
    md += ["| 구간 | 방법 | ID switch M4 | 끔 | 4단계 유지 | H1 | H2 | 회복률 4단계 | H1 [95%] | H2 | H1 − 4단계 유지 | near_other M4 → H1 | 가짜 항적 비 4단계 / H1 / H2 |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    pc = lambda x: "–" if x is None else f"{x:.1%}"  # noqa: E731
    for key, r in W.items():
        sid, m = key.split("|")
        h1 = r["h1"]
        rc = "" if h1["recovery_ci"] is None else f" [{h1['recovery_ci'][0]:.1%}, {h1['recovery_ci'][1]:.1%}]"
        d = r["h1_minus_cone"]
        md.append(f"| {sid} | {m} | {r['idsw_m4']:.2f} | {r['idsw_nocone']:.2f} | {r['cone']['idsw']:.2f} | {h1['idsw']:.2f} | "
                  f"{r['h2']['idsw']:.2f} | {pc(r['cone']['recovery'])} | {pc(h1['recovery'])}{rc} | {pc(r['h2']['recovery'])} | "
                  f"{d['mean']:+.2f} [{d['lo']:+.2f}, {d['hi']:+.2f}] | {r['near_other_m4']:.2f} → {h1['near_other']:.2f} | "
                  + " / ".join(f"{r[v]['side']['false_tracks_per_scan']['ratio']:.3f}" for v in VARS) + " |")
    md += ["", "## 부작용과 진단 (H1 − M4, 짝 t-구간; 비 = H1/M4)", "",
           "| 구간 | 방법 | " + " | ".join(SIDE) + " | 15 km 안 misses 잃음 M4 → 4단계 → H1 → H2 | 게이트 거절 쌍 /run H1 |",
           "|---|---|" + "---:|" * (len(SIDE) + 2)]
    for key, r in W.items():
        sid, m = key.split("|")
        md.append(f"| {sid} | {m} | " + " | ".join(f"{x['mean']:+.3f} [{x['lo']:+.3f}, {x['hi']:+.3f}] (비 {x['ratio']:.3f})"
                                                  for x in r["h1"]["side"].values()) +
                  f" | {r['misses_lost_near_m4']:.2f} → {r['cone']['misses_lost_near']:.2f} → {r['h1']['misses_lost_near']:.2f} → "
                  f"{r['h2']['misses_lost_near']:.2f} | {r['h1']['gate_rejected_pairs']:.1f} |")
    md += ["", f"퇴행 확인(M4, 이 스크립트 경로 = 3단계 diag_near, EHAM·KATL, ID switch·misses 잃음): **{'모두 같음' if reg_ok else '다름'}**"]
    out["regression_m4_equals_diag_near"] = reg_ok
    (ROOT / "results/stage5/cone_summary.json").write_text(json.dumps(out, indent=1))
    (ROOT / "results/stage5/cone_summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
