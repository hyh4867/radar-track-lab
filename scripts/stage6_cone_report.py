"""Stage 6 part 1 report (PREREGISTRATION_6 7): H1 + G1 vs H1 vs M4, without and with assumed Mode C faults (R).

Reads results/stage6/cone/<sid>__{M4,M4_err}__<method>.json. Writes results/stage6/cone_summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from radar_track_lab.metrics import mean_ci  # noqa: E402

C = ROOT / "results/stage6/cone"
WINDOWS = ("EHAM_1106_eval", "EGLL_1106_peak", "EGLL_1111_same", "EHAM_1106_busy2", "EHAM_1111_same", "ENGM_1106_peak",
           "ENGM_1111_same", "KATL_1106_peak", "KATL_1111_same", "LSZH_1106_peak", "LSZH_1111_same", "YSSY_1106_peak",
           "YSSY_1111_same")
SIDE = ("false_tracks_per_scan", "gospa_mean_m", "rmse_m", "missed_per_scan")


def runs(p):
    return {r["seed"]: r for r in json.loads(p.read_text())["runs"]} if p.exists() else None


def ci(x):
    m, h = mean_ci(np.asarray(x, float))
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h)}


def val(r, k):
    if k == "near_other":
        return r["causes"].get("near_other", 0)
    if k in SIDE:
        return r["summary"][k]
    return r[k]


def main() -> None:
    out = {"windows": {}}
    for sid in WINDOWS:
        for m in ("ekf", "imm"):
            d = {"m4": runs(C / f"{sid}__M4__{m}.json"), "h1": runs(C / f"{sid}__M4__{m}_h1.json"),
                 "g1": runs(C / f"{sid}__M4__{m}_g1.json"), "h1_err": runs(C / f"{sid}__M4_err__{m}_h1.json"),
                 "g1_err": runs(C / f"{sid}__M4_err__{m}_g1.json")}
            if any(x is None for x in d.values()):
                continue
            ss = sorted(set.intersection(*(set(x) for x in d.values())))
            row = {"n": len(ss), "crossing_events": float(np.mean([d["m4"][s]["crossing_events"] for s in ss]))}
            for k in ("id_switches", "near_other", "crossing_switches") + SIDE:
                row[k] = {v: float(np.mean([val(d[v][s], k) for s in ss])) for v in d}
                row[k + "_g1_minus_h1"] = ci([val(d["g1"][s], k) - val(d["h1"][s], k) for s in ss])
                row[k + "_g1err_minus_h1err"] = ci([val(d["g1_err"][s], k) - val(d["h1_err"][s], k) for s in ss])
            row["g1_rejected_pairs"] = float(np.mean([d["g1"][s]["cone_stats"].get("g1_rejected_pairs", 0) for s in ss]))
            row["false_ratio_g1_h1"] = row["false_tracks_per_scan"]["g1"] / row["false_tracks_per_scan"]["h1"]
            out["windows"][f"{sid}|{m}"] = row
    W = out["windows"]
    complete = all(f"{s}|{m}" in W for s in WINDOWS for m in ("ekf", "imm"))
    md = ["# 6단계 1부: 모든 연관에 Mode C 고도 확인 (G1) (M4, 13개 구간, seed 20개)", "",
          "`scripts/stage6_cone_report.py`가 만든 파일. 방법: M4(유지 없음), H1(5단계 원뿔 유지 + 고도 확인), G1 = H1 + 모든 확정 항적 고도 확인. "
          "_err = 가정한 Mode C 오차(누락 2%, 잘못된 값 1%). [ ]는 seed 짝 차이 95% t-구간.", ""]
    if complete:
        n1 = {m: sum(W[f"{s}|{m}"]["id_switches"]["g1"] < W[f"{s}|{m}"]["id_switches"]["h1"] for s in WINDOWS) for m in ("ekf", "imm")}
        c1 = all(v >= 11 for v in n1.values())
        k = W["KATL_1106_peak|ekf"]["near_other"]
        c2 = k["g1"] < k["m4"]
        fr = {f"{s}|{m}": W[f"{s}|{m}"]["false_ratio_g1_h1"] for s in WINDOWS for m in ("ekf", "imm")}
        c3 = all(x <= 1.10 for x in fr.values())
        n4 = sum(W[f"{s}|ekf"]["id_switches"]["g1_err"] < W[f"{s}|ekf"]["id_switches"]["h1_err"] for s in WINDOWS)
        c4 = n4 >= 9
        nsat = sum((c1, c2, c3, c4))
        verdict = "개선" if nsat == 4 else ("부분 개선" if nsat else "개선 없음")
        ret = {}
        for m in ("ekf", "imm"):
            num = sum(W[f"{s}|{m}"]["id_switches"]["h1_err"] - W[f"{s}|{m}"]["id_switches"]["g1_err"] for s in WINDOWS)
            den = sum(W[f"{s}|{m}"]["id_switches"]["h1"] - W[f"{s}|{m}"]["id_switches"]["g1"] for s in WINDOWS)
            ret[m] = {"num": num, "den": den, "retained": num / den if den else None}
        tot = {v: sum(W[f"{s}|ekf"]["crossing_switches"][v] for s in WINDOWS) for v in ("m4", "h1", "g1", "h1_err", "g1_err")}
        out["verdict"] = {"verdict": verdict, "c1_n_less": n1, "c1": c1, "c2_katl_near_other": k, "c2": c2,
                          "c3": c3, "c3_max_ratio": max(fr.values()), "c3_over": {a: b for a, b in fr.items() if b > 1.10},
                          "c4_n_less_err": n4, "c4": c4, "g1_gain_retained_under_err": ret, "crossing_switches_total_ekf": tot}
        md += [f"G1 판정: **{verdict}** (1 ID switch < H1 구간 EKF {n1['ekf']}/13, IMM {n1['imm']}/13: {c1}; "
               f"2 KATL EKF near_other G1 {k['g1']:.2f} < M4 {k['m4']:.2f}: {c2}; 3 가짜 항적 비 최대 {max(fr.values()):.3f} ≤ 1.10: {c3}; "
               f"4 오차 있을 때 EKF ID switch < H1 구간 {n4}/13: {c4})", "",
               "오차를 넣었을 때 G1 이득이 남는 비율 Σ(H1_err − G1_err) / Σ(H1 − G1): " +
               ", ".join(f"{m} {r['num']:.2f} / {r['den']:.2f} = " + ("–" if r["retained"] is None else f"{r['retained']:.1%}") for m, r in ret.items()), "",
               "교차 사건 바뀜 합(EKF, 13개 구간, run당): " + ", ".join(f"{a} {b:.2f}" for a, b in tot.items()), ""]
    md += ["| 구간 | 방법 | 교차 사건 /run | ID switch M4 / H1 / G1 | G1 − H1 | near_other M4 / H1 / G1 | 교차 사건 바뀜 M4 / H1 / G1 | G1 − H1 (교차) | 오차: ID switch H1 / G1 | 오차: G1 − H1 | 가짜 항적 비 G1/H1 | G1 거절 쌍 /run |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    f = lambda c: f"{c['mean']:+.2f} [{c['lo']:+.2f}, {c['hi']:+.2f}]"  # noqa: E731
    for key, r in W.items():
        sid, m = key.split("|")
        i, n, x = r["id_switches"], r["near_other"], r["crossing_switches"]
        md.append(f"| {sid} | {m} | {r['crossing_events']:.1f} | {i['m4']:.2f} / {i['h1']:.2f} / {i['g1']:.2f} | {f(r['id_switches_g1_minus_h1'])} | "
                  f"{n['m4']:.2f} / {n['h1']:.2f} / {n['g1']:.2f} | {x['m4']:.2f} / {x['h1']:.2f} / {x['g1']:.2f} | {f(r['crossing_switches_g1_minus_h1'])} | "
                  f"{i['h1_err']:.2f} / {i['g1_err']:.2f} | {f(r['id_switches_g1err_minus_h1err'])} | {r['false_ratio_g1_h1']:.3f} | {r['g1_rejected_pairs']:.0f} |")
    md += ["", "## 부작용 (G1 − H1, 짝 t-구간)", "", "| 구간 | 방법 | " + " | ".join(SIDE) + " |", "|---|---|" + "---:|" * len(SIDE)]
    for key, r in W.items():
        sid, m = key.split("|")
        md.append(f"| {sid} | {m} | " + " | ".join(f(r[k + '_g1_minus_h1']) for k in SIDE) + " |")
    (ROOT / "results/stage6/cone_summary.json").write_text(json.dumps(out, indent=1))
    (ROOT / "results/stage6/cone_summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
