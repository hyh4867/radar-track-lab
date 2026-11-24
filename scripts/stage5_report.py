"""Stage 5 part 1 report: JIPDA-amap vs JIPDA, JIPDA-est and the stage 4 JIPDA-map (PREREGISTRATION_5 5).

Reads results/stage5/eval/ (JIPDA-amap), results/stage3/b1/ (JIPDA, JIPDA-est lam1000), results/stage4/eval/
(JIPDA-est lam200/lam5, JIPDA-map), results/stage5/katl + results/stage4/katl (generalisation) and writes
results/stage5/summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.metrics import mean_ci  # noqa: E402

S3, S4, S5 = ROOT / "results/stage3/b1", ROOT / "results/stage4", ROOT / "results/stage5"
CONDS = ("lam1000_map", "lam1000_uniform", "lam200_map", "lam5_map", "lam5_uniform")
METHODS = ("jipda", "jipda_est", "jipda_map", "jipda_amap")
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


def sources(cond, scen="EHAM_1106_eval", d4="eval", d5="eval"):
    order = {"jipda": [S3, S4 / d4, S5 / d5], "jipda_est": [S3, S4 / d4, S5 / d5], "jipda_map": [S4 / d4],
             "jipda_amap": [S5 / d5]}
    src = {}
    for m in METHODS:
        for base in order[m]:
            if base == S3 and scen != "EHAM_1106_eval":
                continue
            d, rel = load(base / f"{scen}__{m}__{cond}.json")
            if d:
                src[m] = (d, rel)
                break
    return src


def block(src):
    out = {"methods": {}, "paired": {}, "files": {m: rel for m, (_, rel) in src.items()}}
    for m, (d, _) in src.items():
        out["methods"][m] = {f: ci([v(d[s], f) for s in sorted(d)]) for f in F + ("wall_s",)}
    if "jipda_amap" in src:
        da = src["jipda_amap"][0]
        for ref in ("jipda", "jipda_est", "jipda_map"):
            if ref in src:
                dr = src[ref][0]
                ss = sorted(set(da) & set(dr))
                out["paired"][f"jipda_amap-{ref}"] = {f: ci([v(da[s], f) - v(dr[s], f) for s in ss]) for f in F}
                out["paired"][f"jipda_amap-{ref}"]["n_pairs"] = len(ss)
        M = out["methods"]
        if "jipda" in M and "jipda_est" in M and all(
                M["jipda_est"][f]["mean"] > 1.10 * M["jipda"][f]["mean"] for f in ("false_tracks_per_scan", "gospa_mean_m")):
            out["gap_closed"] = {m: {f: (M["jipda_est"][f]["mean"] - M[m][f]["mean"]) /
                                     (M["jipda_est"][f]["mean"] - M["jipda"][f]["mean"])
                                     for f in ("false_tracks_per_scan", "gospa_mean_m")}
                                 for m in ("jipda_map", "jipda_amap") if m in M}
        if "jipda" in M:
            out["ratio_amap_over_jipda"] = {f: M["jipda_amap"][f]["mean"] / M["jipda"][f]["mean"]
                                            for f in ("false_tracks_per_scan", "gospa_mean_m", "id_switches")}
    return out


def verdict(C):
    a = {}
    for c in ("lam1000_map", "lam200_map"):
        p = C[c]["paired"]["jipda_amap-jipda_est"]["gospa_mean_m"]
        a[c] = bool(p["mean"] < 0 and p["hi"] < 0)
    b = {}
    for c in ("lam1000_uniform", "lam5_map", "lam5_uniform"):
        for f in ("gospa_mean_m", "false_tracks_per_scan"):
            b[f"{c}:{f}"] = bool(C[c]["ratio_amap_over_jipda"][f] <= 1.10)
    A, B = all(a.values()), all(b.values())
    return {"verdict": "개선" if A and B else ("부분 개선" if A or B else "개선 없음"), "A": A, "B": B,
            "A_items": a, "B_items": b}


def fmt(c):
    return f"{c['mean']:.2f}" if abs(c["mean"]) < 100 else f"{c['mean']:.0f}"


def fci(c):
    d = 2 if abs(c["mean"]) < 100 else 0
    return f"{c['mean']:+.{d}f} [{c['lo']:+.{d}f}, {c['hi']:+.{d}f}]"


def table(C, conds):
    L = ["| 조건 | 방법 | seed | " + " | ".join(LAB[f] for f in F + ("wall_s",)) + " |",
         "|---|---|---:|" + "---:|" * (len(F) + 1)]
    for c in conds:
        for m in METHODS:
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
    md = ["# 5단계 1부: 자료량에 맞춰 칸을 넓히는 클러터 지도 (JIPDA-amap)", "",
          "`scripts/stage5_report.py`가 만든 파일. 스히폴 평가 구간, 측정 모형 M0, [ ]는 seed 짝 차이의 95% t-구간.",
          "JIPDA-amap만 이 단계의 새 실행(`results/stage5/eval/`)이다. JIPDA·JIPDA-est(lam1000)는 3단계, JIPDA-est(lam200·lam5)와 "
          "JIPDA-map은 4단계 파일이다. 실행 시간은 다른 세션과 CPU를 나눈 값이다.", ""]
    sel = S5 / "tune_selection.json"
    if sel.exists():
        s = json.loads(sel.read_text())
        out["selection"] = s
        md += [f"선택(조정 구간, seed 20271106–20271110, 점수 = 두 조건 GOSPA/JIPDA GOSPA 중 큰 값, 최소): **{s['selected']}**", "",
               "| 후보 | 점수 | map GOSPA 비 | uniform GOSPA 비 | map GOSPA (m) | uniform GOSPA (m) | map 가짜 항적 | uniform 가짜 항적 | map 시간 (s) | uniform 시간 (s) |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for c, r in sorted(s["candidates"].items(), key=lambda kv: kv[1]["score"]):
            m = r["means"]
            md.append(f"| {c} | {r['score']:.3f} | {r['gospa_ratio']['map']:.3f} | {r['gospa_ratio']['uniform']:.3f} | "
                      f"{m['map']['gospa_mean_m']:.0f} | {m['uniform']['gospa_mean_m']:.0f} | {m['map']['false_tracks_per_scan']:.2f} | "
                      f"{m['uniform']['false_tracks_per_scan']:.2f} | {m['map']['wall_s']:.0f} | {m['uniform']['wall_s']:.0f} |")
        for c, r in s["reference_jipda"].items():
            md.append(f"| (기준) jipda {c} | | | | {r['gospa_mean_m']:.0f} | | {r['false_tracks_per_scan']:.2f} | | {r['wall_s']:.0f} | |"
                      if c == "map" else
                      f"| (기준) jipda {c} | | | | | {r['gospa_mean_m']:.0f} | | {r['false_tracks_per_scan']:.2f} | | {r['wall_s']:.0f} |")
        md.append("")
    if all("jipda_amap" in C[c]["methods"] for c in CONDS):
        V = verdict(C)
        out["verdict"] = V
        md += [f"판정: **{V['verdict']}** (조건 A {V['A']}: " + ", ".join(f"{k} {x}" for k, x in V["A_items"].items()) +
               f"; 조건 B {V['B']}: " + ", ".join(f"{k} {x}" for k, x in V["B_items"].items()) + ")", ""]
    md += ["## 평균", ""] + table(C, CONDS) + ["", "## 짝 차이", ""] + paired_table(C, CONDS) + [""]
    for c in CONDS:
        if "ratio_amap_over_jipda" in C[c]:
            r = C[c]["ratio_amap_over_jipda"]
            md.append(f"- {c} JIPDA-amap / JIPDA: 가짜 항적 {r['false_tracks_per_scan']:.3f}, GOSPA {r['gospa_mean_m']:.3f}, "
                      f"ID switch {r['id_switches']:.3f}")
    for c in CONDS:
        for m, g in C[c].get("gap_closed", {}).items():
            md.append(f"- {c} 메움 비율 {m}: 가짜 항적 {g['false_tracks_per_scan']:.3f}, GOSPA {g['gospa_mean_m']:.3f}")
    md.append("- 메움 비율은 JIPDA-est가 JIPDA보다 가짜 항적과 GOSPA 모두 10% 넘게 나쁜 조건에서만 계산한다.")
    K = {}
    for c in ("lam1000_map", "lam1000_uniform"):
        k = block(sources(c, "KATL_1106_peak", "katl", "katl"))
        if "jipda_amap" in k["methods"]:
            K[f"KATL {c}"] = k
    if K:
        out["katl"] = K
        md += ["", "## 일반화 확인: KATL_1106_peak (판정과 별도)", ""] + table(K, list(K)) + [""] + paired_table(K, list(K))
        for c, k in K.items():
            for m, g in k.get("gap_closed", {}).items():
                md.append(f"- {c} 메움 비율 {m}: 가짜 항적 {g['false_tracks_per_scan']:.3f}, GOSPA {g['gospa_mean_m']:.3f}")
            if "ratio_amap_over_jipda" in k:
                r = k["ratio_amap_over_jipda"]
                md.append(f"- {c} JIPDA-amap / JIPDA: 가짜 항적 {r['false_tracks_per_scan']:.3f}, GOSPA {r['gospa_mean_m']:.3f}")
    files = sorted({f"`{r}`" for c in CONDS for r in C[c]["files"].values()} |
                   {f"`{r}`" for k in K.values() for r in k["files"].values()})
    md.append("\n출처 파일: " + ", ".join(files))
    (S5 / "summary.json").write_text(json.dumps(out, indent=1))
    (S5 / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
