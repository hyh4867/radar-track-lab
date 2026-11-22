"""Stage 3 B report: GNN vs JPDA vs JIPDA under dense / mapped clutter (docs/PREREGISTRATION_3.md 4.3, 7.3).

Reads results/stage3/b1/, nees.json, stonesoup_a.json, stonesoup_b.json, tune_jipda_selection.json and writes
results/stage3/b_summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.metrics import mean_ci  # noqa: E402

R = ROOT / "results/stage3"
METRICS = ("gospa_mean_m", "gospa_loc_m", "gospa_missed_m", "gospa_false_m", "id_switches", "false_tracks_per_scan",
           "missed_per_scan", "init_delay_mean_s", "rmse_m")


def ci(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    m, h = mean_ci(x)
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h), "n": int(x.size)}


def load(method, tag):
    p = R / "b1" / f"EHAM_1106_eval__{method}__{tag}.json"
    return {r["seed"]: r for r in json.loads(p.read_text())["runs"]} if p.exists() else None


def val(r, f):
    return r["wall_s"] if f == "wall_s" else r["summary"][f]


def main() -> None:
    out = {"conditions": {}}
    tags = sorted({p.name.split("__")[2][:-5] for p in (R / "b1").glob("*.json")})
    for tag in tags:
        g = load("ekf", tag)
        if not g:
            continue
        cond = {"methods": {}, "paired_vs_gnn": {}}
        for m in ("ekf", "jpda", "jipda", "jipda_est"):
            d = load(m, tag)
            if not d:
                continue
            cond["methods"][m] = {f: ci([val(d[s], f) for s in sorted(d)]) for f in METRICS + ("wall_s",)}
            if m != "ekf":
                ss = sorted(set(d) & set(g))
                cond["paired_vs_gnn"][m] = {f: ci([val(d[s], f) - val(g[s], f) for s in ss]) for f in METRICS + ("wall_s",)}
                cond["paired_vs_gnn"][m]["gospa_ratio"] = ci([val(d[s], "gospa_mean_m") / val(g[s], "gospa_mean_m") for s in ss])
                cond["paired_vs_gnn"][m]["wall_ratio"] = ci([val(d[s], "wall_s") / val(g[s], "wall_s") for s in ss])
        if "jipda" in cond["methods"] and "jipda_est" in cond["methods"]:
            a, b = load("jipda", tag), load("jipda_est", tag)
            ss = sorted(set(a) & set(b))
            cond["est_minus_true"] = {f: ci([val(b[s], f) - val(a[s], f) for s in ss]) for f in METRICS}
            cond["est_over_true_false"] = float(np.mean([val(b[s], "false_tracks_per_scan") for s in ss]) /
                                                np.mean([val(a[s], "false_tracks_per_scan") for s in ss]))
        out["conditions"][tag] = cond
    c = out["conditions"]
    pj = lambda tag: c.get(tag, {}).get("paired_vs_gnn", {}).get("jipda")  # noqa: E731
    v = {}
    if pj("lam1000_uniform") and pj("lam1000_map") and pj("lam5_uniform"):
        dense_ok = all(pj(t)["false_tracks_per_scan"]["hi"] < 0 and pj(t)["gospa_mean_m"]["hi"] < 0
                       for t in ("lam1000_uniform", "lam1000_map"))
        low_ok = pj("lam5_uniform")["gospa_ratio"]["hi"] <= 1.02 and pj("lam5_uniform")["init_delay_mean_s"]["mean"] <= 5.0
        v = {"dense_improved": dense_ok, "lam5_ok": low_ok,
             "verdict": "개선" if dense_ok and low_ok else ("대가 있는 개선" if dense_ok else "개선 없음")}
    out["verdict"] = v
    for name in ("nees", "stonesoup_a", "stonesoup_b", "tune_jipda_selection"):
        p = R / f"{name}.json"
        out[name] = json.loads(p.read_text()) if p.exists() else None
    if out["nees"]:
        out["nees_summary"] = {k: {"scan_end": ci([r["scan_end_mean"] for r in v_["runs"]]),
                                   "update": ci([r["update_mean"] for r in v_["runs"]])}
                               for k, v_ in out["nees"]["rows"].items()}
    # predictions
    pr = {}
    if "lam1000_uniform" in c and "jipda" in c["lam1000_uniform"]["methods"]:
        u = c["lam1000_uniform"]
        pr["gnn_false_1000"] = u["methods"]["ekf"]["false_tracks_per_scan"]["mean"]
        pr["jipda_false_1000"] = u["methods"]["jipda"]["false_tracks_per_scan"]["mean"]
        pr["jipda_false_1000_in_1_10"] = bool(1 <= pr["jipda_false_1000"] <= 10)
        pr["jipda_gospa_rel_1000"] = u["methods"]["jipda"]["gospa_mean_m"]["mean"] / u["methods"]["ekf"]["gospa_mean_m"]["mean"] - 1
        pr["jipda_gospa_rel_in_-80_-60"] = bool(-0.80 <= pr["jipda_gospa_rel_1000"] <= -0.60)
        if "jpda" in u["methods"]:
            pr["jpda_false_rel_1000"] = u["methods"]["jpda"]["false_tracks_per_scan"]["mean"] / pr["gnn_false_1000"] - 1
            pr["jpda_false_rel_in_-30_0"] = bool(-0.30 <= pr["jpda_false_rel_1000"] <= 0.0)
        pr["wall_ratio_jipda_1000"] = u["paired_vs_gnn"]["jipda"]["wall_ratio"]["mean"]
        pr["wall_ratio_in_3_10"] = bool(3 <= pr["wall_ratio_jipda_1000"] <= 10)
    if "lam1000_map" in c and "jipda" in c["lam1000_map"]["methods"]:
        pr["jipda_false_1000_map"] = c["lam1000_map"]["methods"]["jipda"]["false_tracks_per_scan"]["mean"]
        pr["jipda_false_1000_map_le_20"] = bool(pr["jipda_false_1000_map"] <= 20)
    if pj("lam5_uniform"):
        pr["lam5_delay_diff"] = pj("lam5_uniform")["init_delay_mean_s"]["mean"]
        pr["lam5_delay_in_0_5"] = bool(0 <= pr["lam5_delay_diff"] <= 5)
        pr["lam5_gospa_ratio"] = pj("lam5_uniform")["gospa_ratio"]["mean"]
        pr["lam5_gospa_ratio_in_0.97_1.02"] = bool(0.97 <= pr["lam5_gospa_ratio"] <= 1.02)
    for tag in ("lam1000_uniform", "lam1000_map"):
        if tag in c and "est_over_true_false" in c[tag]:
            pr[f"est_over_true_false_{tag}"] = c[tag]["est_over_true_false"]
    out["predictions"] = pr
    (R / "b_summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    write_md(out)


def write_md(out):
    f = lambda x, d=2: f"{x['mean']:.{d}f}"  # noqa: E731
    fd = lambda x, d=2: f"{x['mean']:+.{d}f} [{x['lo']:+.{d}f}, {x['hi']:+.{d}f}]"  # noqa: E731
    L = ["# B. 조밀한 클러터: GNN, JPDA, JIPDA (스히폴 평가 구간, 이상적 측정 모형)", "",
         "`scripts/stage3_b_report.py`가 만든 파일. [ ]는 seed 짝 차이의 95% t-구간.", ""]
    if out["verdict"]:
        L += [f"판정: **{out['verdict']['verdict']}** (λ 1000 균일·지도에서 가짜 항적과 GOSPA 개선: {out['verdict']['dense_improved']}, "
              f"λ 5 조건 충족: {out['verdict']['lam5_ok']})", ""]
    L += ["| 조건 | 방법 | seed | GOSPA (m) | 위치 | 놓침 | 가짜 | ID switch | 가짜 항적 /scan | 놓친 표적 /scan | 확정 지연 (s) | 실행 시간 (s) |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for tag, c in out["conditions"].items():
        for m, s in c["methods"].items():
            L.append(f"| {tag} | {m} | {s['gospa_mean_m']['n']} | {f(s['gospa_mean_m'], 0)} | {f(s['gospa_loc_m'], 0)} | {f(s['gospa_missed_m'], 0)} | "
                     f"{f(s['gospa_false_m'], 0)} | {f(s['id_switches'], 1)} | {f(s['false_tracks_per_scan'])} | {f(s['missed_per_scan'])} | "
                     f"{f(s['init_delay_mean_s'], 1)} | {f(s['wall_s'], 1)} |")
    L += ["", "## 짝 차이 (방법 − GNN)", "", "| 조건 | 방법 | GOSPA (m) | GOSPA 비 | 가짜 항적 /scan | ID switch | 확정 지연 (s) | 실행 시간 비 |",
          "|---|---|---:|---:|---:|---:|---:|---:|"]
    for tag, c in out["conditions"].items():
        for m, d in c["paired_vs_gnn"].items():
            L.append(f"| {tag} | {m} | {fd(d['gospa_mean_m'], 0)} | {fd(d['gospa_ratio'], 3)} | {fd(d['false_tracks_per_scan'])} | "
                     f"{fd(d['id_switches'], 1)} | {fd(d['init_delay_mean_s'], 1)} | {f(d['wall_ratio'], 1)} |")
    est = [(t, c) for t, c in out["conditions"].items() if "est_minus_true" in c]
    if est:
        L += ["", "## JIPDA-est (클러터 밀도 추정, 설명용) − JIPDA (참 밀도)", ""]
        for t, c in est:
            e = c["est_minus_true"]
            L.append(f"- {t}: 가짜 항적 {fd(e['false_tracks_per_scan'])} /scan (비 {c['est_over_true_false']:.2f}), GOSPA {fd(e['gospa_mean_m'], 0)} m, 놓친 표적 {fd(e['missed_per_scan'])}")
    if out.get("nees_summary"):
        L += ["", "## 합성 NCV 정답 NEES (확정 항적, 4차원)", "", "| 방법·λ | scan 끝 | 갱신 시각 |", "|---|---:|---:|"]
        for k, v in out["nees_summary"].items():
            L.append(f"| {k.replace('|', ' λ ')} | {fd(v['scan_end'])} | {fd(v['update'])} |")
    if out.get("stonesoup_a"):
        L += ["", "## Stone Soup 대조 (a): 한 scan", ""]
        for lam, v in out["stonesoup_a"]["conditions"].items():
            a = v["aggregate"]
            L.append(f"- λ {lam}: 덩어리 {a['clusters']}(여러 항적 {a['multi']}), 짝 {a['pairs']}, 최대 |Δβ| {a['max_dbeta']:.1e}, "
                     f"최대 위치 차 {1000 * a['max_dpos_m']:.2f} mm, 공분산 상대 차 {a['max_dcov_rel']:.1e}, LBP 차 {a['lbp_max_diff']:.1e}, "
                     f"gate 불일치 {a['gate_mismatch']} → {'일치' if a['agree'] else '불일치'}")
    if out.get("stonesoup_b"):
        L += ["", "## Stone Soup 대조 (b): 추적기 전체", "", "| λ | seed | Jacobian | scan | 1 cm 안 비율 | 최대 위치 차 (m) | ID switch (우리/SS) | 같은 답 |",
              "|---:|---:|---|---:|---:|---:|---|---|"]
        for r in out["stonesoup_b"]["rows"]:
            L.append(f"| {r['lam']} | {r['seed']} | {'해석적(진단)' if r.get('analytic_jacobian') else 'Stone Soup 기본(차분)'} | {r['scans']} | "
                     f"{100 * r['share_within_1cm']:.2f}% | {r['max_pos_diff_m']:.4f} | {r['idsw_ours']}/{r['idsw_ss']} | {r['same_answer']} |")
    if out.get("tune_jipda_selection"):
        t = out["tune_jipda_selection"]
        L += ["", "## JIPDA 조정 (조정 구간, seed 5개)", "",
              f"선택: 초기 존재 확률 {t['selected']['combo'][0]}, 확정 {t['selected']['combo'][1]}, 삭제 {t['selected']['combo'][2]} "
              f"({t['rule']}; λ 5 제약을 맞춘 조합 {t['n_meeting_constraint']}/24)."]
    p = out.get("predictions") or {}
    if p:
        L += ["", "## 예측 대 실제 (B)", ""] + [f"- {k}: {v}" for k, v in p.items()]
    (R / "b_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
