"""Stage 4 report: JIPDA-map vs JIPDA (true density) vs JIPDA-est (PREREGISTRATION_4 5).

Reads results/stage4/eval/ (JIPDA-map; JIPDA-est for conditions stage 3 did not run), results/stage3/b1/ (JIPDA and
JIPDA-est as run in stage 3), results/stage4/katl/ (generalisation check) and writes results/stage4/summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.metrics import mean_ci  # noqa: E402

S3, S4 = ROOT / "results/stage3/b1", ROOT / "results/stage4"
CONDS = ("lam1000_map", "lam1000_uniform", "lam200_map", "lam5_map", "lam5_uniform")
F = ("false_tracks_per_scan", "gospa_mean_m", "missed_per_scan", "id_switches", "init_delay_mean_s", "rmse_m")
LAB = {"false_tracks_per_scan": "가짜 항적 /scan", "gospa_mean_m": "GOSPA (m)", "missed_per_scan": "놓친 표적 /scan",
       "id_switches": "ID switch", "init_delay_mean_s": "확정 지연 (s)", "rmse_m": "위치 RMSE (m)", "wall_s": "실행 시간 (s)"}


def ci(x):
    m, h = mean_ci(np.asarray(x, float))
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h), "n": int(np.isfinite(np.asarray(x, float)).sum())}


def load(path):
    if not path.exists():
        return None, None
    d = json.loads(path.read_text())
    return {r["seed"]: r for r in d["runs"]}, str(path.relative_to(ROOT))


def v(r, f):
    return r["wall_s"] if f == "wall_s" else r["summary"][f]


def sources(cond, scen="EHAM_1106_eval", s4dir="eval"):
    src = {}
    for m in ("jipda", "jipda_est", "jipda_map"):
        cands = [S4 / s4dir / f"{scen}__{m}__{cond}.json"]
        if m != "jipda_map" and scen == "EHAM_1106_eval":
            cands.insert(0, S3 / f"{scen}__{m}__{cond}.json")  # stage 3 files first (PREREGISTRATION_4 5.1)
        for p in cands:
            d, rel = load(p)
            if d:
                src[m] = (d, rel)
                break
    return src


def block(src):
    out = {"methods": {}, "paired": {}, "files": {m: rel for m, (_, rel) in src.items()}}
    for m, (d, _) in src.items():
        out["methods"][m] = {f: ci([v(d[s], f) for s in sorted(d)]) for f in F + ("wall_s",)}
    if "jipda_map" in src:
        dm = src["jipda_map"][0]
        for ref in ("jipda", "jipda_est"):
            if ref in src:
                dr = src[ref][0]
                ss = sorted(set(dm) & set(dr))
                out["paired"][f"jipda_map-{ref}"] = {f: ci([v(dm[s], f) - v(dr[s], f) for s in ss]) for f in F}
                out["paired"][f"jipda_map-{ref}"]["n_pairs"] = len(ss)
        M = out["methods"]
        # gap closed: only where JIPDA-est is > 10 % worse than JIPDA on both metrics (else the ratio is meaningless)
        if "jipda" in src and "jipda_est" in src and all(
                M["jipda_est"][f]["mean"] > 1.10 * M["jipda"][f]["mean"] for f in ("false_tracks_per_scan", "gospa_mean_m")):
            out["gap_closed"] = {f: (M["jipda_est"][f]["mean"] - M["jipda_map"][f]["mean"]) /
                                 (M["jipda_est"][f]["mean"] - M["jipda"][f]["mean"])
                                 for f in ("false_tracks_per_scan", "gospa_mean_m")}
    return out


def verdict(C):
    m1 = C["lam1000_map"]
    c1 = m1["methods"]["jipda_map"]["false_tracks_per_scan"]["mean"] <= 8.0
    p = m1["paired"]["jipda_map-jipda_est"]["gospa_mean_m"]
    c2 = p["mean"] < 0 and p["hi"] < 0
    c3 = all(C[c]["methods"]["jipda_map"]["false_tracks_per_scan"]["mean"] <=
             1.10 * C[c]["methods"]["jipda"]["false_tracks_per_scan"]["mean"] for c in ("lam5_map", "lam5_uniform"))
    c4 = all(C[c]["methods"]["jipda_map"]["id_switches"]["mean"] <=
             1.10 * C[c]["methods"]["jipda"]["id_switches"]["mean"] for c in ("lam5_map", "lam5_uniform"))
    v_ = "개선" if (c1 and c2 and c3 and c4) else ("부분 개선" if c2 else "개선 없음")
    ratios = {c: {f: C[c]["methods"]["jipda_map"][f]["mean"] / C[c]["methods"]["jipda"][f]["mean"]
                  for f in ("false_tracks_per_scan", "gospa_mean_m", "id_switches")}
              for c in CONDS if "jipda_map" in C[c]["methods"]}
    return {"verdict": v_, "c1_false_le_8": c1, "c2_gospa_below_est_ci": c2, "c3_lam5_false_le_1.1": c3,
            "c4_lam5_idsw_le_1.1": c4, "ratio_map_over_jipda": ratios,
            "no_loss_uniform_lam200map": {c: all(ratios[c][f] <= 1.10 for f in ("false_tracks_per_scan", "gospa_mean_m"))
                                          for c in ("lam1000_uniform", "lam200_map") if c in ratios}}


def fmt(c):
    return f"{c['mean']:.2f}" if abs(c["mean"]) < 100 else f"{c['mean']:.0f}"


def fci(c):
    d = 2 if abs(c["mean"]) < 100 else 0
    return f"{c['mean']:+.{d}f} [{c['lo']:+.{d}f}, {c['hi']:+.{d}f}]"


def table(C, conds):
    L = ["| 조건 | 방법 | seed | " + " | ".join(LAB[f] for f in F + ("wall_s",)) + " |",
         "|---|---|---:|" + "---:|" * (len(F) + 1)]
    for c in conds:
        for m in ("jipda", "jipda_est", "jipda_map"):
            if m in C[c]["methods"]:
                M = C[c]["methods"][m]
                L.append(f"| {c} | {m} | {M['gospa_mean_m']['n']} | " + " | ".join(fmt(M[f]) for f in F + ("wall_s",)) + " |")
    return L


def paired_table(C, conds):
    L = ["| 조건 | 차이 | 쌍 | " + " | ".join(LAB[f] for f in F) + " |", "|---|---|---:|" + "---:|" * len(F)]
    for c in conds:
        for k, P in C[c]["paired"].items():
            L.append(f"| {c} | {k} | {P['n_pairs']} | " + " | ".join(fci(P[f]) for f in F) + " |")
    return L


def main() -> None:
    C = {c: block(sources(c)) for c in CONDS}
    out = {"conditions": C}
    md = ["# 4단계: 자료로 추정한 세밀한 클러터 지도 (JIPDA-map)", "",
          "`scripts/stage4_report.py`가 만든 파일. 스히폴 평가 구간, 측정 모형 M0. [ ]는 seed 짝 차이의 95% t-구간.",
          "JIPDA·JIPDA-est는 3단계 파일(`results/stage3/b1/`)을 쓰고, 3단계에 없는 JIPDA-est 조건만 `results/stage4/eval/`의 새 실행이다.",
          "실행 시간은 다른 세션과 CPU를 나눠 쓴 밤의 값이라 3단계 값과 직접 비교하지 않는다.", ""]
    sel = S4 / "tune_selection.json"
    if sel.exists():
        s = json.loads(sel.read_text())
        out["selection"] = s
        md += [f"선택(조정 구간 lam1000_map, seed 20271106–20271110, GOSPA 최소): **{s['selected']}**", "",
               "| 후보 | GOSPA (m) | 가짜 항적 /scan | 놓친 표적 /scan | ID switch | 실행 시간 (s) |", "|---|---:|---:|---:|---:|---:|"]
        for c, r in sorted(s["candidates"].items(), key=lambda kv: kv[1]["gospa_mean_m"]):
            md.append(f"| {c} | {r['gospa_mean_m']:.0f} | {r['false_tracks_per_scan']:.2f} | {r['missed_per_scan']:.2f} | "
                      f"{r['id_switches']:.1f} | {r['wall_s']:.0f} |")
        for m, r in s["reference"].items():
            if r:
                md.append(f"| (참고) {m} | {r['gospa_mean_m']:.0f} | {r['false_tracks_per_scan']:.2f} | {r['missed_per_scan']:.2f} | "
                          f"{r['id_switches']:.1f} | {r['wall_s']:.0f} |")
        md.append("")
    if all("jipda_map" in C[c]["methods"] for c in CONDS):
        V = verdict(C)
        out["verdict"] = V
        md += [f"판정: **{V['verdict']}** (1 가짜 항적 ≤ 8: {V['c1_false_le_8']}, 2 GOSPA < JIPDA-est·구간 0 제외: "
               f"{V['c2_gospa_below_est_ci']}, 3 λ5 가짜 항적 ≤ 1.1×JIPDA: {V['c3_lam5_false_le_1.1']}, "
               f"4 λ5 ID switch ≤ 1.1×JIPDA: {V['c4_lam5_idsw_le_1.1']})", ""]
    md += ["## 평균", ""] + table(C, CONDS) + ["", "## 짝 차이", ""] + paired_table(C, CONDS) + [""]
    for c in CONDS:
        if "gap_closed" in C[c]:
            g = C[c]["gap_closed"]
            md.append(f"- {c} 메움 비율 (JIPDA-est→JIPDA 간격 중 JIPDA-map이 메운 몫): 가짜 항적 {g['false_tracks_per_scan']:.3f}, "
                      f"GOSPA {g['gospa_mean_m']:.3f}")
    md.append("- 메움 비율은 JIPDA-est가 JIPDA보다 가짜 항적과 GOSPA 모두 10% 넘게 나쁜 조건에서만 계산한다(나머지는 간격이 없어 비율이 뜻이 없음).")
    if "verdict" in out:
        md += ["", "JIPDA-map / JIPDA 비 (seed 평균):", ""]
        for c, r in out["verdict"]["ratio_map_over_jipda"].items():
            md.append(f"- {c}: 가짜 항적 {r['false_tracks_per_scan']:.3f}, GOSPA {r['gospa_mean_m']:.3f}, ID switch {r['id_switches']:.3f}")
    k = block(sources("lam1000_map", "KATL_1106_peak", "katl"))
    if k["methods"]:
        out["katl"] = k
        md += ["", "## 일반화 확인: KATL_1106_peak lam1000_map (판정과 별도)", ""]
        C2 = {"KATL lam1000_map": k}
        md += table(C2, ["KATL lam1000_map"]) + [""] + paired_table(C2, ["KATL lam1000_map"])
        if "gap_closed" in k:
            md.append(f"\n- 메움 비율: 가짜 항적 {k['gap_closed']['false_tracks_per_scan']:.3f}, GOSPA {k['gap_closed']['gospa_mean_m']:.3f}")
    md.append("\n출처 파일: " + ", ".join(sorted({f"`{r}`" for c in CONDS for r in C[c]["files"].values()})))
    (S4 / "summary.json").write_text(json.dumps(out, indent=1))
    (S4 / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
