"""Stage 6 part 2 report (PREREGISTRATION_6 8): JIPDA-amap with the data-driven floor vs stage 5 JIPDA-amap and JIPDA.

Reads results/stage6/eval/ (new), results/stage5/eval/ (stage 5 JIPDA-amap), results/stage3/b1/ (JIPDA).
Writes results/stage6/summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from radar_track_lab.metrics import mean_ci  # noqa: E402

CONDS = ("lam1000_map", "lam1000_uniform", "lam200_map", "lam5_map", "lam5_uniform")
F = ("false_tracks_per_scan", "gospa_mean_m", "missed_per_scan", "id_switches", "init_delay_mean_s", "rmse_m")
SRC = {"jipda": ROOT / "results/stage3/b1/EHAM_1106_eval__jipda__{c}.json",
       "amap5": ROOT / "results/stage5/eval/EHAM_1106_eval__jipda_amap__{c}.json",
       "amap6": ROOT / "results/stage6/eval/EHAM_1106_eval__jipda_amap__{c}.json"}


def ci(x):
    m, h = mean_ci(np.asarray(x, float))
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h)}


def main() -> None:
    out = {"conditions": {}}
    md = ["# 6단계 2부: 데이터로 정하는 바닥값 (JIPDA-amap)", "",
          "`scripts/stage6_report.py`가 만든 파일. 스히폴 평가 구간, M0, seed 20개. amap5 = 5단계 JIPDA-amap(고정 바닥값), "
          "amap6 = 바닥값을 상한 창 추정에서 정한 것. [ ]는 짝 t-구간.", ""]
    sel = ROOT / "results/stage6/tune_selection.json"
    if sel.exists():
        s = json.loads(sel.read_text())
        out["selection"] = s
        md += [f"선택(조정 구간, 점수 = lam5_map·lam1000_uniform GOSPA/JIPDA 중 큰 값): **f = {s['selected']}**", "",
               "| 후보 | 점수 | lam5_map 비 | lam1000_uniform 비 | lam5_map 놓친 표적 | lam5_map 확정 지연 (s) |", "|---|---:|---:|---:|---:|---:|"]
        for f, r in s["candidates"].items():
            md.append(f"| f={f} | {r['score']:.4f} | {r['gospa_ratio']['lam5_map']:.3f} | {r['gospa_ratio']['lam1000_uniform']:.3f} | "
                      f"{r['means']['lam5_map']['missed_per_scan']:.3f} | – |")
        r = s["stage5_amap"]
        md += [f"| (참고) 5단계 고정 바닥값 | {r['score']:.4f} | {r['gospa_ratio']['lam5_map']:.3f} | {r['gospa_ratio']['lam1000_uniform']:.3f} | "
               f"{r['means']['lam5_map']['missed_per_scan']:.3f} | – |", ""]
    md += ["| 조건 | 방법 | " + " | ".join(F) + " |", "|---|---|" + "---:|" * len(F)]
    pmd = ["", "## 짝 차이 amap6 − amap5", "", "| 조건 | " + " | ".join(F) + " |", "|---|" + "---:|" * len(F)]
    files = []
    for c in CONDS:
        d = {}
        for k, p in SRC.items():
            p = Path(str(p).format(c=c))
            if p.exists():
                d[k] = {r["seed"]: r for r in json.loads(p.read_text())["runs"]}
                files.append(str(p.relative_to(ROOT)))
        if "amap6" not in d:
            continue
        ss = sorted(set.intersection(*(set(x) for x in d.values())))
        row = {"means": {k: {f: float(np.mean([x[s]["summary"][f] for s in ss])) for f in F} for k, x in d.items()}, "n": len(ss)}
        row["paired_6_minus_5"] = {f: ci([d["amap6"][s]["summary"][f] - d["amap5"][s]["summary"][f] for s in ss]) for f in F}
        row["paired_6_minus_jipda"] = {f: ci([d["amap6"][s]["summary"][f] - d["jipda"][s]["summary"][f] for s in ss]) for f in F}
        row["gospa_ratio_6_over_5"] = row["means"]["amap6"]["gospa_mean_m"] / row["means"]["amap5"]["gospa_mean_m"]
        out["conditions"][c] = row
        for k in ("jipda", "amap5", "amap6"):
            md.append(f"| {c} | {k} | " + " | ".join(f"{row['means'][k][f]:.2f}" if row['means'][k][f] < 100 else f"{row['means'][k][f]:.0f}" for f in F) + " |")
        pmd.append(f"| {c} | " + " | ".join(f"{v['mean']:+.3f} [{v['lo']:+.3f}, {v['hi']:+.3f}]" for v in row["paired_6_minus_5"].values()) + " |")
    md += pmd
    C = out["conditions"]
    if all(c in C for c in CONDS):
        a = {c: C[c]["gospa_ratio_6_over_5"] <= 1.01 for c in CONDS}
        b = {f"{c}:{f}": C[c]["paired_6_minus_5"][f]["hi"] < 0 for c in ("lam5_map", "lam5_uniform") for f in ("missed_per_scan", "init_delay_mean_s")}
        A, B = all(a.values()), all(b.values())
        v = "개선" if A and B else ("부분 개선" if A or B else "개선 없음")
        out["verdict"] = {"verdict": v, "a_not_worse": A, "a_items": a, "b_lam5_reduced": B, "b_items": b}
        md = md[:4] + [f"판정: **{v}** ((a) GOSPA 비 ≤ 1.01 다섯 조건: {A} — " + ", ".join(f"{c} {C[c]['gospa_ratio_6_over_5']:.4f}" for c in CONDS) +
                       f"; (b) λ5 놓친 표적·확정 지연 감소: {B} — " + ", ".join(f"{k} {x}" for k, x in b.items()) + ")", ""] + md[4:]
    md.append("\n출처 파일: " + ", ".join(f"`{x}`" for x in sorted(set(files))))
    (ROOT / "results/stage6/summary.json").write_text(json.dumps(out, indent=1))
    (ROOT / "results/stage6/summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
