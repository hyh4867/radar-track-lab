"""Stage 3 A report: do the stage 2 conclusions hold under the realistic sensor model? (PREREGISTRATION_3 3.5)

Reads results/stage3/a/<scenario>.json (scripts/stage3_a_run.py) and results/stage3/a_noslant/, writes
results/stage3/a_summary.{json,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.metrics import mean_ci  # noqa: E402

D = ROOT / "results/stage3/a"
EVAL = "EHAM_1106_eval"
MODELS = ("M0", "M1", "M2", "M3", "M4")
CIRCLERS = (252, 2233)  # the two aircraft behind 68% of the stage 2 Schiphol losses
TURN_KEYS = ("turn",)
LOST = ("turn", "misses", "near_radar", "speed_change", "unexplained")


def ci(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    m, h = mean_ci(x)
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h), "n": int(x.size)}


def col(doc, mo, method, f):
    return np.array([r["models"][mo]["methods"][method]["summary"][f] for r in doc["runs"]], float)


def c1(doc, mo):
    idsw = ci(col(doc, mo, "imm", "id_switches") - col(doc, mo, "ekf", "id_switches"))
    ratio = ci(col(doc, mo, "imm", "rmse_m") / col(doc, mo, "ekf", "rmse_m"))
    e_r = ci(col(doc, mo, "ekf", "rmse_m") - col(doc, mo, "nn", "rmse_m"))
    e_i = ci(col(doc, mo, "ekf", "id_switches") - col(doc, mo, "nn", "id_switches"))
    return {"imm_minus_ekf_idsw": idsw, "imm_over_ekf_rmse": ratio, "imm_holds": bool(idsw["hi"] < 0 and ratio["mean"] <= 1.05),
            "ekf_minus_nn_rmse": e_r, "ekf_minus_nn_idsw": e_i, "ekf_beats_nn": bool(e_r["hi"] < 0 and e_i["hi"] < 0),
            "ekf_idsw": ci(col(doc, mo, "ekf", "id_switches")), "imm_idsw": ci(col(doc, mo, "imm", "id_switches"))}


def c2_counts(doc, mo, method="ekf", exclude=()):
    causes = {c: 0 for c in LOST}
    n_win = n_all = 0
    for r in doc["runs"]:
        m = r["models"][mo]["methods"][method]
        for e in m["lost_events"]:
            if e["target"] in exclude:
                continue
            causes[e["cause"]] += 1
        n_win += m["base"]["window_turn"]
        n_all += m["base"]["assigned_target_scans"]
    return causes, n_win, n_all


def c2_verdict(causes, n_win, n_all):
    lost = sum(causes.values())
    share = causes["turn"] / lost if lost else float("nan")
    base = n_win / n_all if n_all else float("nan")
    if lost and share >= 0.5 and share >= 2 * base:
        v = "선회가 주원인"
    elif lost and share < 0.3:
        v = "주원인 아님"
    else:
        v = "부분적"
    return {"lost": lost, "causes": causes, "turn_share": share, "base_rate": base, "verdict": v}


def c3(doc, mo):
    g = lambda m: np.array([r["models"][mo]["four"]["rmse_common"][m] for r in doc["runs"]], float)  # noqa: E731
    nn, nnp, ekfh, ekf = g("nn"), g("nnp"), g("ekfh"), g("ekf")
    D_ = ekf - nn
    A_pred, B_pred, B_rest = nnp - nn, ekf - ekfh, ekfh - nn
    inter = (ekf - ekfh) - (nnp - nn)
    s_A, s_B = A_pred.mean() / D_.mean(), B_pred.mean() / D_.mean()
    Ac, Bc, Rc = ci(A_pred), ci(B_pred), ci(B_rest)
    out = {"rmse_common": {m: float(v.mean()) for m, v in (("nn", nn), ("nnp", nnp), ("ekfh", ekfh), ("ekf", ekf))},
           "D_total": ci(D_), "A_pred": Ac, "B_pred": Bc, "B_rest": Rc, "interaction": ci(inter),
           "s_A": float(s_A), "s_B": float(s_B), "interaction_share": float(inter.mean() / D_.mean()),
           "rest_ratio": float(abs(B_rest.mean()) / abs(D_.mean()))}
    out["G1"] = bool(Ac["hi"] < 0 and s_A >= 0.5 and Bc["hi"] < 0 and s_B >= 0.5)
    out["G2"] = bool(abs(s_B - s_A) > 0.10)
    out["G3"] = bool(out["rest_ratio"] <= 0.10)
    return out


def level(n_ok, eval_ok):
    if eval_ok and n_ok >= 10:
        return "유지"
    if eval_ok and n_ok >= 6:
        return "부분 유지"
    return "깨짐"


def main() -> None:
    docs = {p.stem: json.loads(p.read_text()) for p in sorted(D.glob("*.json"))}
    valid = {s for s, d in docs.items() if d["meta"]["M0"]["truth_per_scan"] >= 5.0}
    oos = sorted(s for s in valid if s != EVAL)
    out = {"scenarios": {}, "verdicts": {}, "valid_oos": oos, "n_runs": {s: len(d["runs"]) for s, d in docs.items()}}
    for s, d in docs.items():
        out["scenarios"][s] = {"valid": s in valid, "truth_per_scan": {mo: d["meta"][mo]["truth_per_scan"] for mo in d["models"]},
                               "models": {}}
        for mo in d["models"]:
            causes, nw, na = c2_counts(d, mo)
            ent = {"c1": c1(d, mo), "c2": c2_verdict(causes, nw, na), "c3": c3(d, mo),
                   "cross_model_rmse": {m: float(np.mean([r["cross_model"][m]["rmse"][mo] for r in d["runs"]]))
                                        for m in ("ekf", "imm", "nn")},
                   "metrics": {m: {f: float(col(d, mo, m, f).mean()) for f in ("id_switches", "rmse_m", "gospa_mean_m",
                                                                                "missed_per_scan", "false_tracks_per_scan",
                                                                                "fragmentations", "rmse_at_update_m")}
                               for m in ("nn", "nnp", "ekfh", "ekf", "imm")},
                   "wall_s": {m: float(np.mean([r["models"][mo]["methods"][m]["wall_s"] for r in d["runs"]]))
                              for m in ("nn", "nnp", "ekfh", "ekf", "imm")}}
            if s == EVAL:
                c_ex, nw2, na2 = c2_counts(d, mo, exclude=CIRCLERS)
                ent["c2_without_circlers"] = c2_verdict(c_ex, nw2, na2)
                ent["c2_imm"] = c2_verdict(*c2_counts(d, mo, "imm"))
            out["scenarios"][s]["models"][mo] = ent
    for mo in MODELS:
        if EVAL not in docs or any(mo not in docs[s]["models"] for s in oos):
            continue
        ev = out["scenarios"][EVAL]["models"][mo]
        n_imm = sum(out["scenarios"][s]["models"][mo]["c1"]["imm_holds"] for s in oos)
        n_ekf = sum(out["scenarios"][s]["models"][mo]["c1"]["ekf_beats_nn"] for s in oos)
        eval_c1 = bool(ev["c1"]["imm_minus_ekf_idsw"]["hi"] < 0)
        pooled = {c: 0 for c in LOST}
        nw = na = 0
        for s in oos:
            causes, a, b = c2_counts(docs[s], mo)
            for c in LOST:
                pooled[c] += causes[c]
            nw, na = nw + a, na + b
        c2_oos = c2_verdict(pooled, nw, na)
        main_e, main_o = ev["c2"]["verdict"] == "선회가 주원인", c2_oos["verdict"] == "선회가 주원인"
        g = {k: sum(out["scenarios"][s]["models"][mo]["c3"][k] for s in oos) for k in ("G1", "G2", "G3")}
        g_eval = {k: ev["c3"][k] for k in ("G1", "G2", "G3")}
        c3_levels = [level(g[k], g_eval[k]) for k in ("G1", "G2", "G3")]
        c3_v = "깨짐" if "깨짐" in c3_levels else ("부분 유지" if "부분 유지" in c3_levels else "유지")
        out["verdicts"][mo] = {
            "C1": {"eval_imm_holds": eval_c1, "n_oos_imm_holds": int(n_imm), "n_oos": len(oos), "verdict": level(n_imm, eval_c1),
                   "n_oos_ekf_beats_nn": int(n_ekf), "eval_ekf_beats_nn": ev["c1"]["ekf_beats_nn"]},
            "C2": {"eval": ev["c2"], "oos_pooled": c2_oos,
                   "verdict": "유지" if (main_e and main_o) else ("부분 유지" if (main_e or main_o) else "깨짐")},
            "C3": {"eval": g_eval, "n_oos": g, "levels": dict(zip(("G1", "G2", "G3"), c3_levels)), "verdict": c3_v,
                   "s_A_range": [min(out["scenarios"][s]["models"][mo]["c3"]["s_A"] for s in oos),
                                 max(out["scenarios"][s]["models"][mo]["c3"]["s_A"] for s in oos)],
                   "s_B_range": [min(out["scenarios"][s]["models"][mo]["c3"]["s_B"] for s in oos),
                                 max(out["scenarios"][s]["models"][mo]["c3"]["s_B"] for s in oos)],
                   "interaction_share_range": [min(out["scenarios"][s]["models"][mo]["c3"]["interaction_share"] for s in oos),
                                               max(out["scenarios"][s]["models"][mo]["c3"]["interaction_share"] for s in oos)]},
        }
    # E2 auxiliary: slant correction off
    ns = ROOT / "results/stage3/a_noslant"
    aux = {}
    for m in ("ekf", "imm"):
        pa, pb = ns / f"{EVAL}__{m}__M2.json", ns / f"{EVAL}__{m}__M2_noslant.json"
        if pa.exists() and pb.exists():
            a = {r["seed"]: r["summary"] for r in json.loads(pa.read_text())["runs"]}
            b = {r["seed"]: r["summary"] for r in json.loads(pb.read_text())["runs"]}
            ss = sorted(set(a) & set(b))
            aux[m] = {f: ci([b[s][f] - a[s][f] for s in ss]) for f in ("rmse_m", "id_switches", "gospa_mean_m")}
            aux[m]["rmse_M2"] = float(np.mean([a[s]["rmse_m"] for s in ss]))
    out["E2_noslant_minus_M2"] = aux
    # predictions
    if "M4" in out["verdicts"]:
        ev4 = out["scenarios"][EVAL]["models"]["M4"]
        v4 = out["verdicts"]["M4"]
        x = ev4["c1"]["ekf_idsw"]["mean"]
        sh = ev4["c2"]["turn_share"]
        out["predictions"] = {
            "M4_eval_ekf_idsw": x,
            "agent_ekf_idsw_40_80": bool(40 <= x <= 80), "independent_ekf_idsw_35_70": bool(35 <= x <= 70),
            "independent_point_45_abs_err": abs(x - 45),
            "M4_eval_turn_share": sh, "agent_turn_20_45": bool(0.20 <= sh <= 0.45), "independent_turn_30_50": bool(0.30 <= sh <= 0.50),
            "C2_verdict": v4["C2"]["verdict"], "agent_C2_broken_or_partial": v4["C2"]["verdict"] in ("깨짐", "부분 유지"),
            "independent_C2_partial": v4["C2"]["verdict"] == "부분 유지",
            "agent_C1_holds": v4["C1"]["verdict"] == "유지",
            "agent_imm_diff_-15_-5": bool(-15 <= ev4["c1"]["imm_minus_ekf_idsw"]["mean"] <= -5),
            "agent_C3_holds": v4["C3"]["verdict"] == "유지",
        }
    (ROOT / "results/stage3/a_summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    write_md(out)


def write_md(out):
    f2 = lambda c: f"{c['mean']:+.2f} [{c['lo']:+.2f}, {c['hi']:+.2f}]"  # noqa: E731
    L = ["# A. 현실적인 센서 모형에서 2단계 결론", "", "`scripts/stage3_a_report.py`가 `results/stage3/a/`에서 만든 파일.", ""]
    L += ["## 판정 (모형별; 판정 대상은 M4)", "", "| 모형 | C1 (IMM ID switch) | C2 (선회 집중) | C3 (분해 모양) |", "|---|---|---|---|"]
    for mo, v in out["verdicts"].items():
        c1v, c2v, c3v = v["C1"], v["C2"], v["C3"]
        L.append(f"| {mo} | {c1v['verdict']} (스히폴 {'성립' if c1v['eval_imm_holds'] else '불성립'}, 표본 밖 {c1v['n_oos_imm_holds']}/{c1v['n_oos']}) | "
                 f"{c2v['verdict']} (스히폴 turn {100 * c2v['eval']['turn_share']:.0f}%·{c2v['eval']['verdict']}, 표본 밖 합산 "
                 f"{100 * c2v['oos_pooled']['turn_share']:.0f}%·{c2v['oos_pooled']['verdict']}) | {c3v['verdict']} "
                 f"(G1 {c3v['n_oos']['G1']}, G2 {c3v['n_oos']['G2']}, G3 {c3v['n_oos']['G3']} / 12) |")
    ev = out["scenarios"].get(EVAL, {}).get("models", {})
    if ev:
        L += ["", "## 스히폴 평가 구간, 모형별 (seed 20개 평균)", "",
              "| 모형 | 정답/scan | EKF ID switch | IMM ID switch | IMM − EKF | EKF RMSE (m) | 기준선 RMSE (m) | EKF 놓친 표적 /scan | EKF 가짜 항적 /scan | 잃음 (EKF, /run) | turn 비율 | 기저율 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for mo, e in ev.items():
            tp = out["scenarios"][EVAL]["truth_per_scan"][mo]
            L.append(f"| {mo} | {tp:.1f} | {e['metrics']['ekf']['id_switches']:.1f} | {e['metrics']['imm']['id_switches']:.1f} | "
                     f"{f2(e['c1']['imm_minus_ekf_idsw'])} | {e['metrics']['ekf']['rmse_m']:.1f} | {e['metrics']['nn']['rmse_m']:.1f} | "
                     f"{e['metrics']['ekf']['missed_per_scan']:.2f} | {e['metrics']['ekf']['false_tracks_per_scan']:.2f} | "
                     f"{e['c2']['lost'] / out['n_runs'][EVAL]:.1f} | {100 * e['c2']['turn_share']:.0f}% | {100 * e['c2']['base_rate']:.0f}% |")
        L += ["", f"원인별 잃음 (EKF, seed {out['n_runs'][EVAL]}개 합): " + "; ".join(f"{mo} " + ", ".join(f"{c} {n}" for c, n in e["c2"]["causes"].items())
                                                       for mo, e in ev.items()),
              "", "두 선회 항공기(2단계 잃음의 68%)를 뺀 turn 비율: " + ", ".join(
                  f"{mo} {100 * e['c2_without_circlers']['turn_share']:.0f}% ({e['c2_without_circlers']['lost']}회)" for mo, e in ev.items()),
              "", "모형 사이 공통 표본 scan-end RMSE (m): " + "; ".join(
                  f"{mo} EKF {e['cross_model_rmse']['ekf']:.1f} / IMM {e['cross_model_rmse']['imm']:.1f} / 기준선 {e['cross_model_rmse']['nn']:.1f}"
                  for mo, e in ev.items())]
    if "M4" in out["verdicts"]:
        L += ["", "## C3: 네 방법 공통 표본 분해 (M4)", "", "| 구간 | 기준선 | +출력 예측 | EKF 출력 예측 없음 | EKF | s_A | s_B | 상호작용 몫 | G1 | G2 | G3 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|"]
        for s in [EVAL] + out["valid_oos"]:
            c = out["scenarios"][s]["models"]["M4"]["c3"]
            r = c["rmse_common"]
            L.append(f"| {s} | {r['nn']:.1f} | {r['nnp']:.1f} | {r['ekfh']:.1f} | {r['ekf']:.1f} | {100 * c['s_A']:.1f}% | "
                     f"{100 * c['s_B']:.1f}% | {100 * c['interaction_share']:.1f}% | {c['G1']} | {c['G2']} | {c['G3']} |")
        L += ["", "## C1: 표본 밖 구간별 (M4)", "", "| 구간 | 정답/scan (M0→M4) | IMM − EKF ID switch | RMSE 비 IMM/EKF | IMM 이득 유지 | EKF > 기준선 |",
              "|---|---:|---:|---:|---|---|"]
        for s in [EVAL] + out["valid_oos"]:
            sc = out["scenarios"][s]
            c = sc["models"]["M4"]["c1"]
            L.append(f"| {s} | {sc['truth_per_scan']['M0']:.1f}→{sc['truth_per_scan']['M4']:.1f} | {f2(c['imm_minus_ekf_idsw'])} | "
                     f"{c['imm_over_ekf_rmse']['mean']:.3f} | {c['imm_holds']} | {c['ekf_beats_nn']} |")
    if out.get("E2_noslant_minus_M2"):
        L += ["", "## E2 보조: 경사 거리 보정 없음 − M2 (스히폴)", ""]
        for m, v in out["E2_noslant_minus_M2"].items():
            L.append(f"- {m}: scan-end RMSE {f2(v['rmse_m'])} m (M2 {v['rmse_M2']:.1f} m), ID switch {f2(v['id_switches'])}, GOSPA {f2(v['gospa_mean_m'])} m")
    if out.get("predictions"):
        p = out["predictions"]
        L += ["", "## 예측 대 실제 (A)", "", "| 항목 | 작업 에이전트 | 독립 예측 | 실제 |", "|---|---|---|---|",
              f"| M4 스히폴 EKF ID switch | 40–80 ({'맞음' if p['agent_ekf_idsw_40_80'] else '틀림'}) | 45 (35–70) ({'맞음' if p['independent_ekf_idsw_35_70'] else '틀림'}) | {p['M4_eval_ekf_idsw']:.1f} |",
              f"| 스히폴 EKF turn 비율 | 20–45% ({'맞음' if p['agent_turn_20_45'] else '틀림'}) | 30–50% ({'맞음' if p['independent_turn_30_50'] else '틀림'}) | {100 * p['M4_eval_turn_share']:.0f}% |",
              f"| C2 판정 | 깨짐 또는 부분 유지 ({'맞음' if p['agent_C2_broken_or_partial'] else '틀림'}) | 부분 유지 ({'맞음' if p['independent_C2_partial'] else '틀림'}) | {p['C2_verdict']} |",
              f"| C1 판정 | 유지 ({'맞음' if p['agent_C1_holds'] else '틀림'}) | – | {out['verdicts']['M4']['C1']['verdict']} |",
              f"| IMM − EKF (스히폴) | −5 ~ −15 ({'맞음' if p['agent_imm_diff_-15_-5'] else '틀림'}) | – | {out['scenarios'][EVAL]['models']['M4']['c1']['imm_minus_ekf_idsw']['mean']:+.1f} |",
              f"| C3 판정 | 유지 ({'맞음' if p['agent_C3_holds'] else '틀림'}) | – | {out['verdicts']['M4']['C3']['verdict']} |"]
    (ROOT / "results/stage3/a_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
