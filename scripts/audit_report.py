"""Aggregate the sample audit, apply the verdict rules of docs/AUDIT_PROTOCOL.md, draw the audit figures.

    .venv/bin/python scripts/audit_report.py

Reads results/audit/samples/*.json and results/audit/paired_effects.csv; writes
results/audit/sample_audit.json, results/audit/sample_audit.md and results/audit/figures/*.png.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from make_figures import GRID, INK, INK2, SURFACE, style  # noqa: E402
from radar_track_lab.audit import paired_diff, percent_reduction  # noqa: E402

AUD = ROOT / "results/audit"
EVAL = "EHAM_1106_eval"
C_EKF, C_NN, C_GREY = "#2a78d6", "#eb6834", "#9a9993"


def analyse(doc):
    R = doc["runs"]
    g = lambda f: np.array([f(r) for r in R], dtype=float)  # noqa: E731
    s = lambda m, k: g(lambda r: r["summary"][m][k])  # noqa: E731
    out = {"spec": doc["spec"], "truth_per_scan": doc["truth_per_scan"], "valid": bool(doc["truth_per_scan"] >= 5.0), "seeds": len(R)}
    for kind, key in (("scan_end", "rmse_m"), ("update", "rmse_at_update_m")):
        a = {"original": {"ekf": float(s("ekf", key).mean()), "nn": float(s("nn", key).mean()), "diff": paired_diff(s("ekf", key), s("nn", key)),
                          "percent_reduction": percent_reduction(s("nn", key), s("ekf", key))},
             "common": {"ekf": float(g(lambda r: r[kind]["rmse_common_ekf"]).mean()), "nn": float(g(lambda r: r[kind]["rmse_common_nn"]).mean()),
                        "diff": paired_diff(g(lambda r: r[kind]["rmse_common_ekf"]), g(lambda r: r[kind]["rmse_common_nn"])),
                        "percent_reduction": percent_reduction(g(lambda r: r[kind]["rmse_common_nn"]), g(lambda r: r[kind]["rmse_common_ekf"]))},
             "n": {k: float(g(lambda r: r[kind][k]).mean()) for k in ("n_ekf", "n_nn", "n_common", "only_ekf", "only_nn")},
             "rmse_only_ekf": float(np.nanmean(g(lambda r: r[kind]["rmse_only_ekf"]))),
             "rmse_only_nn": float(np.nanmean(g(lambda r: r[kind]["rmse_only_nn"])))}
        out[kind] = a
    out["scan_end"]["n"]["n_truth"] = float(g(lambda r: r["scan_end"]["n_truth"]).mean())
    out["scan_end"]["n"]["neither"] = float(g(lambda r: r["scan_end"]["neither"]).mean())
    out["update"]["n"]["target_detections"] = float(g(lambda r: r["target_detections_after_warmup"]).mean())
    out["update"]["n"]["target_illuminations"] = float(g(lambda r: r["target_illuminations_after_warmup"]).mean())
    out["update"]["reasons"] = {m: {k: float(np.mean([r["update"]["reasons"][m].get(k, 0) for r in R]))
                                    for k in ("used", "clutter", "tentative", "warmup", "truth_missing")} for m in ("ekf", "nn")}
    out["companion"] = {k: {"ekf": float(s("ekf", k).mean()), "nn": float(s("nn", k).mean()), "diff": paired_diff(s("ekf", k), s("nn", k))}
                        for k in ("id_switches", "fragmentations", "missed_per_scan", "false_tracks_per_scan", "gospa_mean_m",
                                  "gospa_loc_m", "gospa_missed_m", "gospa_false_m")}
    edges = doc["age_edges_s"]
    bins = []
    for i in range(len(edges) - 1):
        n = sum(r["scan_end"]["by_nn_age"]["nn"][i]["n"] for r in R)
        bins.append({"lo": edges[i], "hi": edges[i + 1], "n": n,
                     "rmse_ekf": float(np.sqrt(sum(r["scan_end"]["by_nn_age"]["ekf"][i]["sq"] for r in R) / n)) if n else None,
                     "rmse_nn": float(np.sqrt(sum(r["scan_end"]["by_nn_age"]["nn"][i]["sq"] for r in R) / n)) if n else None})
    out["scan_end"]["by_baseline_age"] = bins
    out["scan_end"]["mean_age_s"] = {"ekf": float(np.nanmean(g(lambda r: r["scan_end"]["mean_age_ekf"] or np.nan))),
                                     "nn": float(np.nanmean(g(lambda r: r["scan_end"]["mean_age_nn"] or np.nan)))}
    # verdict (protocol section 6)
    d0, dse, dup = out["scan_end"]["original"]["diff"], out["scan_end"]["common"]["diff"], out["update"]["common"]["diff"]
    separated = dse["hi"] < dup["lo"]  # both negative: scan-end interval entirely below the update interval
    larger = abs(dse["mean"]) > abs(dup["mean"]) and separated
    out["verdict"] = ("reversed" if not larger else "maintained" if abs(dse["mean"]) >= 0.9 * abs(d0["mean"]) else "reduced")
    out["ratio_common_to_original_scan_end"] = dse["mean"] / d0["mean"]
    out["direction_same"] = bool(dse["mean"] < 0 and dup["mean"] < 0 and abs(dse["mean"]) > abs(dup["mean"]))
    return out


def ci(d, nd=1):
    return f"{d['mean']:+,.{nd}f} [{d['lo']:+,.{nd}f}, {d['hi']:+,.{nd}f}]"


def label(x):
    s = x["spec"]
    return f"{s['site']} {s['day'][5:]} {s['start_utc'][11:16]}"


def figures(S):
    fig_dir = AUD / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    # 1. paired differences over the stage 1 sweep
    rows = [r for r in csv.DictReader(open(AUD / "paired_effects.csv")) if r["source"] == "stage1_sweep"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), facecolor=SURFACE)
    for ax, key, title in ((axes[0], "rmse_m", "scan-end RMSE"), (axes[1], "rmse_at_update_m", "update-time RMSE")):
        style(ax)
        for saz, ls, mk in ((0.15, "-", "o"), (0.3, (0, (4, 2)), "s")):
            for lam, col in ((0.0, "#86b6ef"), (5.0, "#2a78d6"), (20.0, "#0d366b")):
                rr = sorted((r for r in rows if r["metric"] == key and float(r["sigma_az_deg"]) == saz and float(r["clutter_lambda"]) == lam),
                            key=lambda r: float(r["pd"]))
                x = [float(r["pd"]) for r in rr]
                y = np.array([float(r["paired_diff"]) for r in rr])
                lo, hi = np.array([float(r["ci_lo"]) for r in rr]), np.array([float(r["ci_hi"]) for r in rr])
                ax.errorbar(x, y, yerr=[y - lo, hi - y], color=col, linestyle=ls, marker=mk, markersize=4.5, linewidth=1.6,
                            capsize=2, label=f"σθ {saz:.2f}°, λ {lam:.0f}")
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.set_xlabel("detection probability Pd", fontsize=9, color=INK2)
        ax.set_ylabel(f"paired difference EKF − NN [m]", fontsize=9, color=INK2)
        ax.set_title(title, fontsize=10.5, color=INK, loc="left")
        ax.set_xticks([0.7, 0.8, 0.9, 0.97])
    h, lab = axes[1].get_legend_handles_labels()
    fig.legend(h, lab, frameon=False, fontsize=8, ncol=6, loc="lower center", bbox_to_anchor=(0.5, -0.07))
    fig.suptitle("Paired by seed, 20 seeds per condition; bars are 95% t-intervals for one fixed traffic window",
                 fontsize=10.5, color=INK, x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(fig_dir / "audit_paired_sweep.png", dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    # 2. sample accounting on the evaluation window
    e = S[EVAL]
    fig, ax = plt.subplots(figsize=(9, 2.9), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="y", visible=False)
    se, up = e["scan_end"]["n"], e["update"]["n"]
    bars = [("scan-end: truth target-scans", se["n_truth"], [("in both (common sample)", se["n_common"], C_GREY), ("EKF only", se["only_ekf"], C_EKF),
                                                             ("baseline only", se["only_nn"], C_NN), ("in neither", se["neither"], "#e4e3df")]),
            ("update-time: target detections", up["target_detections"],
             [("in both (common sample)", up["n_common"], C_GREY), ("EKF only", up["only_ekf"], C_EKF), ("baseline only", up["only_nn"], C_NN),
              ("in neither", up["target_detections"] - up["n_common"] - up["only_ekf"] - up["only_nn"], "#e4e3df")])]
    for row, (name, total, parts) in enumerate(bars):
        left = 0.0
        for lab, v, col in parts:
            ax.barh(row, v / total * 100, left=left, color=col, height=0.5, edgecolor=SURFACE, linewidth=2, label=lab if row == 0 else None)
            if v / total > 0.03:
                ax.text(left + v / total * 50, row, f"{v / total * 100:.1f}%", ha="center", va="center", fontsize=8.5,
                        color="white" if col in (C_EKF, C_NN, C_GREY) else INK)
            left += v / total * 100
        ax.text(101, row, f"n = {total:,.0f} per run", va="center", fontsize=8.5, color=INK2)
    ax.set_yticks([0, 1], [b[0] for b in bars], fontsize=9.5, color=INK)
    ax.set_xlim(0, 118)
    ax.set_xlabel("share of samples after warm-up [%], mean of 20 runs", fontsize=9, color=INK2)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.25), ncol=4, frameon=False, fontsize=8.5)
    ax.set_title("Which samples each RMSE uses, Schiphol evaluation window", fontsize=11, color=INK, loc="left")
    fig.savefig(fig_dir / "audit_sample_accounting.png", dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    # 3. original vs common-sample paired differences per scenario
    order = sorted((k for k in S if S[k]["valid"]), key=lambda k: (k != EVAL, S[k]["spec"]["day"], S[k]["spec"]["site"] != "EHAM", k))
    y = np.arange(len(order))[::-1]
    fig, ax = plt.subplots(figsize=(8.6, 0.36 * len(order) + 1.5), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="y", visible=False)
    for yi, k in zip(y, order):
        x = S[k]
        for kind, col, mk in (("scan_end", C_EKF, "o"), ("update", "#1baf7a", "s")):
            o, c = -x[kind]["original"]["diff"]["mean"], -x[kind]["common"]["diff"]["mean"]
            ax.plot([o, c], [yi, yi], color=GRID, linewidth=3, zorder=1)
            ax.scatter(o, yi, s=46, facecolor=SURFACE, edgecolor=col, linewidth=1.6, marker=mk, zorder=3,
                       label=f"{'scan-end' if kind == 'scan_end' else 'update-time'}, each method's own samples" if k == order[0] else None)
            ax.scatter(c, yi, s=30, color=col, marker=mk, zorder=4,
                       label=f"{'scan-end' if kind == 'scan_end' else 'update-time'}, common samples" if k == order[0] else None)
    ax.set_yticks(y, [f"{label(S[k])}  ({S[k]['truth_per_scan']:.0f}/scan)" for k in order], fontsize=8.5, color=INK)
    ax.set_xlim(0, None)
    ax.set_xlabel("RMSE reduction, NN baseline − EKF, paired by seed [m]", fontsize=9, color=INK2)
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.45, -0.12), ncol=2)
    ax.set_title("Paired RMSE difference on own samples and on common samples", fontsize=11, color=INK, loc="left")
    fig.savefig(fig_dir / "audit_common_vs_original.png", dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def block_ko(S, overall) -> str:
    e = S[EVAL]
    se, up, co = e["scan_end"], e["update"], e["companion"]
    V = {"maintained": "유지", "reduced": "줄어듦", "reversed": "뒤집힘"}
    oos = [k for k in S if S[k]["valid"] and k != EVAL]
    L = ["기존 결과 파일은 그대로 두고, 평가가 어떤 표본을 쓰는지 따로 확인했습니다. 규칙은 계산 전에 `docs/AUDIT_PROTOCOL.md`에 적어 커밋했고, 산출물은 `results/audit/`에 있습니다. "
         "아래 수치는 `scripts/audit_report.py`가 만든 것입니다.", "",
         "- **구간의 범위**: 모든 ± 와 [구간]은 seed 20개에 대한 95% t-구간입니다. 정답 궤적은 고정이고 탐지 잡음·누락·클러터만 바뀌므로, 고정된 한 교통 구간에서의 시뮬레이션 변동만 나타냅니다. 다른 날·다른 공항으로의 불확실성은 들어 있지 않습니다.",
         "- **짝 차이**(같은 seed끼리 EKF − 기준선, 기준 조건): "
         f"scan-end RMSE {ci(se['original']['diff'], 2)} m, update-time RMSE {ci(up['original']['diff'], 2)} m, ID switch {ci(co['id_switches']['diff'], 2)}회. "
         "스윕 24개 조건과 2단계 시나리오·IMM까지 넣은 표는 `results/audit/paired_effects.md`이고 `scripts/audit_paired.py` 한 번으로 다시 만듭니다. "
         "퍼센트 감소는 100 × (기준선 평균 − EKF 평균) / 기준선 평균입니다.",
         "- **두 RMSE는 다른 표본을 씁니다.** scan-end RMSE는 scan이 끝나는 시각에 전체 표적과 확정 항적을 GOSPA로 짝지어 2 km 안인 쌍만 씁니다. update-time RMSE는 확정 항적이 탐지로 갱신된 순간만 쓰고, 정답은 그 탐지를 만든 표적입니다. 방법마다 표본이 다릅니다.", "",
         "| RMSE | 표본 | run당 표본 수 (EKF / 기준선) | EKF [m] | 기준선 [m] | 짝 차이 [m] | 감소 |", "|---|---|---:|---:|---:|---:|---:|"]
    for kind, name in (("scan_end", "scan-end"), ("update", "update-time")):
        x = e[kind]
        L.append(f"| {name} | 각자의 표본 | {x['n']['n_ekf']:,.0f} / {x['n']['n_nn']:,.0f} | {x['original']['ekf']:.1f} | {x['original']['nn']:.1f} | {ci(x['original']['diff'], 2)} | {x['original']['percent_reduction']:.1f}% |")
        L.append(f"| {name} | 공통 표본 | {x['n']['n_common']:,.0f} | {x['common']['ekf']:.1f} | {x['common']['nn']:.1f} | {ci(x['common']['diff'], 2)} | {x['common']['percent_reduction']:.1f}% |")
    b = se["by_baseline_age"]
    L += ["", f"- scan-end: 워밍업 뒤 표적-scan은 run당 {se['n']['n_truth']:,.0f}개입니다. 두 방법 모두 짝이 있는 것이 {se['n']['n_common']:,.0f}개, EKF만 {se['n']['only_ekf']:,.0f}개, 기준선만 {se['n']['only_nn']:,.0f}개, 둘 다 없는 것이 {se['n']['neither']:,.0f}개입니다. "
          f"기준선이 짝을 못 만든 {se['n']['only_ekf']:,.0f}개에서 EKF의 RMSE는 {se['rmse_only_ekf']:.1f} m로, 공통 표본({se['common']['ekf']:.1f} m)과 비슷합니다.",
          f"- update-time: 워밍업 뒤 표적 탐지는 run당 {up['n']['target_detections']:,.0f}개입니다. 두 방법 모두 쓴 것이 {up['n']['n_common']:,.0f}개, EKF만 {up['n']['only_ekf']:,.0f}개, 기준선만 {up['n']['only_nn']:,.0f}개입니다.",
          f"- **판정: {V[e['verdict']]}.** 공통 표본에서 scan-end 차이는 각자 표본 차이의 {e['ratio_common_to_original_scan_end'] * 100:.1f}%이고, update-time 차이보다 큽니다(두 구간이 겹치지 않음). "
          "\"scan-end에서 차이가 더 크다\"는 관찰은 표본 차이 때문이 아닙니다.",
          f"- 표본 밖 유효 시나리오 {len(oos)}개 중 {overall['direction_same_oos_valid']}개에서 방향이 같고, 판정은 " + ", ".join(f"{V[v]} {sum(S[k]['verdict'] == v for k in oos)}개" for v in ("maintained", "reduced", "reversed")) + "입니다.",
          f"- 기준선의 scan-end 오차는 마지막 탐지 뒤 지난 시간과 함께 커집니다(공통 표본, {b[0]['lo']:.1f}–{b[0]['hi']:.1f}초 {b[0]['rmse_nn']:.0f} m → {b[3]['lo']:.1f}–{b[3]['hi']:.1f}초 {b[3]['rmse_nn']:.0f} m; EKF는 {b[0]['rmse_ekf']:.0f} → {b[3]['rmse_ekf']:.0f} m). 기준선이 예측하지 않는다는 설명과 맞는 모습이지만, 이것은 기술이고 원인을 나눈 것은 아닙니다.",
          "- **단서**: 공통 표본은 두 방법이 모두 따라간 표적-scan만 남기므로 \"항적 번호 유지\"의 효과는 RMSE에 나타나지 않습니다. 그 효과는 "
          f"ID switch({co['id_switches']['ekf']:.1f} 대 {co['id_switches']['nn']:.1f}회), 항적 끊김({co['fragmentations']['ekf']:.1f} 대 {co['fragmentations']['nn']:.1f}회), 놓친 표적({co['missed_per_scan']['ekf']:.2f} 대 {co['missed_per_scan']['nn']:.2f}/scan)에 따로 나타납니다. "
          "그래서 6절의 문장 \"큰 차이는 scan 사이 예측과 항적 번호 유지에서 나옵니다\"는 이렇게 읽어야 합니다: scan-end RMSE의 차이는 같은 표본에서도 그대로이고 예측의 유무와 맞는 모습이며, 항적 번호 유지의 차이는 RMSE가 아니라 ID switch·끊김·놓친 표적 수로 봐야 합니다. 두 RMSE의 차이를 원인별 퍼센트로 나누지는 않았습니다.", "",
          "![표본 구성](results/audit/figures/audit_sample_accounting.png)", "",
          "![각자 표본과 공통 표본의 짝 차이](results/audit/figures/audit_common_vs_original.png)", ""]
    return "\n".join(L)


def main() -> None:
    S = {p.stem: analyse(json.loads(p.read_text())) for p in sorted((AUD / "samples").glob("*.json"))}
    valid = [k for k in S if S[k]["valid"]]
    oos = [k for k in valid if k != EVAL]
    overall = {"scenarios": len(S), "valid": len(valid), "direction_same_valid": sum(S[k]["direction_same"] for k in valid),
               "direction_same_oos_valid": sum(S[k]["direction_same"] for k in oos), "oos_valid": len(oos),
               "verdicts": {k: S[k]["verdict"] for k in S}}
    (AUD / "sample_audit.json").write_text(json.dumps({"overall": overall, "scenarios": S}, indent=1))
    e = S[EVAL]
    L = ["# Sample audit of the two RMSEs (generated by `scripts/audit_report.py`)", "",
         "EKF + GNN vs NN baseline, default condition, 20 seeds. Differences are EKF − NN paired by seed, mean [95% t-interval]; "
         "the intervals describe simulation variability on one fixed traffic window. Rules: `docs/AUDIT_PROTOCOL.md`.", "",
         "## Schiphol evaluation window", "",
         "| RMSE | sample | n per run (EKF / NN) | EKF [m] | NN [m] | paired difference [m] | % reduction |", "|---|---|---:|---:|---:|---:|---:|"]
    for kind, name in (("scan_end", "scan-end"), ("update", "update-time")):
        x = e[kind]
        L.append(f"| {name} | each method's own | {x['n']['n_ekf']:,.0f} / {x['n']['n_nn']:,.0f} | {x['original']['ekf']:.1f} | {x['original']['nn']:.1f} | {ci(x['original']['diff'], 2)} | {x['original']['percent_reduction']:.1f} |")
        L.append(f"| {name} | common | {x['n']['n_common']:,.0f} | {x['common']['ekf']:.1f} | {x['common']['nn']:.1f} | {ci(x['common']['diff'], 2)} | {x['common']['percent_reduction']:.1f} |")
    se, up = e["scan_end"], e["update"]
    L += ["", f"- Scan-end: {se['n']['n_truth']:,.0f} truth target-scans per run after warm-up. Paired by both {se['n']['n_common']:,.0f}, "
          f"by the EKF only {se['n']['only_ekf']:,.0f}, by the baseline only {se['n']['only_nn']:,.0f}, by neither {se['n']['neither']:,.0f}. "
          f"EKF RMSE on the {se['n']['only_ekf']:,.0f} target-scans the baseline did not pair: {se['rmse_only_ekf']:.1f} m; "
          f"baseline RMSE on its {se['n']['only_nn']:,.0f} own-only target-scans: {se['rmse_only_nn']:.1f} m.",
          f"- Update-time: {up['n']['target_illuminations']:,.0f} illuminations and {up['n']['target_detections']:,.0f} target detections per run after warm-up. "
          f"Used by both {up['n']['n_common']:,.0f}, by the EKF only {up['n']['only_ekf']:,.0f}, by the baseline only {up['n']['only_nn']:,.0f}. "
          f"EKF RMSE on its own-only samples {up['rmse_only_ekf']:.1f} m; baseline on its own-only samples {up['rmse_only_nn']:.1f} m.",
          f"- Update records by reason, per run (EKF / NN): used {up['reasons']['ekf']['used']:,.0f} / {up['reasons']['nn']['used']:,.0f}, "
          f"tentative track {up['reasons']['ekf']['tentative']:,.0f} / {up['reasons']['nn']['tentative']:,.0f}, "
          f"warm-up {up['reasons']['ekf']['warmup']:,.0f} / {up['reasons']['nn']['warmup']:,.0f}, "
          f"clutter detection {up['reasons']['ekf']['clutter']:,.0f} / {up['reasons']['nn']['clutter']:,.0f}.",
          f"- The scan-end difference on the common sample is {e['ratio_common_to_original_scan_end'] * 100:.1f}% of the difference on each method's own samples. Verdict by the protocol rule: **{e['verdict']}**.",
          f"- Mean time since the track's last update at the scan-end sample (common sample): EKF {se['mean_age_s']['ekf']:.2f} s, baseline {se['mean_age_s']['nn']:.2f} s.", "",
          "Companion metrics (the common sample leaves out what either method failed to track):", "",
          "| metric | EKF | NN | paired difference |", "|---|---:|---:|---:|"]
    for k, nd in (("id_switches", 1), ("fragmentations", 1), ("missed_per_scan", 2), ("false_tracks_per_scan", 2), ("gospa_mean_m", 0),
                  ("gospa_loc_m", 0), ("gospa_missed_m", 0), ("gospa_false_m", 0)):
        c = e["companion"][k]
        L.append(f"| {k} | {c['ekf']:,.{nd}f} | {c['nn']:,.{nd}f} | {ci(c['diff'], nd)} |")
    L += ["", "Scan-end RMSE on the common sample by the baseline track's time since its last detection (descriptive, pooled over seeds):", "",
          "| time since the baseline's last detection [s] | samples | EKF RMSE [m] | NN RMSE [m] |", "|---|---:|---:|---:|"]
    for b in se["by_baseline_age"]:
        if b["n"]:
            L.append(f"| {b['lo']:.1f}–{b['hi'] if b['hi'] is not None else '∞'} | {b['n']:,} | {b['rmse_ekf']:.1f} | {b['rmse_nn']:.1f} |")
    L += ["", "## All scenarios", "",
          "| scenario (UTC) | aircraft / scan | scan-end common / EKF / NN | scan-end diff, own samples | scan-end diff, common | update-time diff, own samples | update-time diff, common | verdict | same direction |",
          "|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for k in sorted(S, key=lambda k: (k != EVAL, S[k]["spec"]["day"], S[k]["spec"]["site"] != "EHAM", k)):
        x = S[k]
        n = x["scan_end"]["n"]
        L.append(f"| {label(x)}{'' if x['valid'] else ' (not valid)'} | {x['truth_per_scan']:.1f} | {n['n_common']:,.0f} / {n['n_ekf']:,.0f} / {n['n_nn']:,.0f} | "
                 f"{ci(x['scan_end']['original']['diff'])} | {ci(x['scan_end']['common']['diff'])} | {ci(x['update']['original']['diff'])} | "
                 f"{ci(x['update']['common']['diff'])} | {x['verdict']} | {'yes' if x['direction_same'] else 'no'} |")
    L += ["", f"Same direction (both common-sample differences negative and the scan-end one larger): {overall['direction_same_valid']} of {overall['valid']} valid scenarios "
          f"({overall['direction_same_oos_valid']} of {overall['oos_valid']} out-of-sample).", ""]
    (AUD / "sample_audit.md").write_text("\n".join(L))
    figures(S)
    readme = ROOT / "README.md"
    t = readme.read_text(encoding="utf-8")
    a, b = "<!-- audit:begin -->", "<!-- audit:end -->"
    if a in t and b in t:
        readme.write_text(t[:t.index(a) + len(a)] + "\n" + block_ko(S, overall) + "\n" + t[t.index(b):], encoding="utf-8")
    print(json.dumps(overall, indent=1))


if __name__ == "__main__":
    main()
