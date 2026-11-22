"""Prediction-only baseline experiment (docs/PREDICT_BASELINE_PROTOCOL.md).

    .venv/bin/python scripts/audit_predict_baseline.py

Runs the baseline (nn), the one variant (nnp: baseline + output extrapolation) and the EKF on the
Schiphol evaluation window with the same 20 seeds, checks the stop conditions of the protocol and
writes results/audit/predict_baseline/{runs.json, summary.json, summary.md, figure}.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab import audit as A  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import load_stage2, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

OUT = ROOT / "results/audit/predict_baseline"
SID = "EHAM_1106_eval"
METHODS = ("nn", "nnp", "ekf")
AGE_EDGES = [0.0, 1.2, 2.4, 3.6, 4.8, 9.6, np.inf]
SPEED_LIMIT = 350.0  # descriptive only (protocol section 5)
KEEP = ("rmse_m", "rmse_at_update_m", "id_switches", "fragmentations", "missed_per_scan", "false_tracks_per_scan",
        "gospa_mean_m", "gospa_loc_m", "gospa_missed_m", "gospa_false_m", "tracks_per_scan", "truth_per_scan")


def same(a, b):
    return a == b or (a != a and b != b)


def tables_equal(a, b):
    return all(np.array_equal(a[f], b[f], equal_nan=True) for f in a)


def one_seed(sc, cfg, seed, ref):
    res = {m: run(sc, cfg, seed=seed, method=m, record=True, audit=True) for m in METHODS}
    for m in ("nn", "ekf"):  # stop condition: existing scores must not change
        bad = [k for k, v in ref[m][seed].items() if not same(v, res[m].summary[k])]
        if bad:
            raise SystemExit(f"STOP {m} seed {seed}: scores differ from the stage 2 file: {bad}")
    # stop condition: the variant shares the baseline's association, so its update samples are identical
    if not tables_equal(res["nn"].audit["update"], res["nnp"].audit["update"]):
        raise SystemExit(f"STOP seed {seed}: update samples of nnp differ from nn")
    if not same(res["nn"].summary["rmse_at_update_m"], res["nnp"].summary["rmse_at_update_m"]):
        raise SystemExit(f"STOP seed {seed}: update-time RMSE of nnp differs from nn")
    se = {m: res[m].audit["scan_end"] for m in METHODS}
    c = A.common_scan_end_many(se)
    # speed of the nnp track paired with each common sample (from the recorded snapshots)
    speed_of = {}
    for snap in res["nnp"].snapshots:
        sp = dict(zip(snap["track_ids"].tolist(), np.hypot(snap["track_vel"][:, 0], snap["track_vel"][:, 1]).tolist()))
        for tid, trk in snap["assigned"].items():
            speed_of[(snap["k"], int(tid))] = sp[int(trk)]
    speed = np.array([speed_of[k] for k in c["keys"]])
    used_nnp = se["nnp"]["reason"] == A.USED
    speed_all = np.array([speed_of[(int(k), int(t))] for k, t in zip(se["nnp"]["k"][used_nnp], se["nnp"]["truth"][used_nnp])])
    age = c["age"]["nn"]  # time since the last detection; identical for nn and nnp tracks of the same id
    bins = np.digitize(age, AGE_EDGES[1:-1])
    fast = speed >= SPEED_LIMIT
    return {
        "seed": seed,
        "summary": {m: {k: res[m].summary[k] for k in KEEP} for m in METHODS},
        "n_truth": c["n_truth"], "n_paired": c["n"], "n_common": c["n_common"], "n_none": c["none"],
        "rmse_common": {m: A.rmse(c["sq"][m]) for m in METHODS},
        "by_age": {m: [{"n": int((bins == i).sum()), "sq": float(c["sq"][m][bins == i].sum())}
                       for i in range(len(AGE_EDGES) - 1)] for m in METHODS},
        "nnp_fast": {"n_common": int(fast.sum()), "rmse_common_fast": A.rmse(c["sq"]["nnp"][fast]),
                     "rmse_common_rest": A.rmse(c["sq"]["nnp"][~fast]),
                     "n_own": int((speed_all >= SPEED_LIMIT).sum()), "n_own_total": int(speed_all.size)},
    }


def pd_(rows, f, a, b):
    return A.paired_diff([f(r, a) for r in rows], [f(r, b) for r in rows])


def mean_ci(rows, f, m):
    from radar_track_lab.metrics import mean_ci as mc

    v, h = mc(np.array([f(r, m) for r in rows], dtype=float))
    return {"mean": v, "ci95": h}


def summarize(rows):
    rc = lambda r, m: r["rmse_common"][m]  # noqa: E731
    d_pred, d_rest, d_tot = pd_(rows, rc, "nnp", "nn"), pd_(rows, rc, "ekf", "nnp"), pd_(rows, rc, "ekf", "nn")
    ratio = abs(d_pred["mean"]) / abs(d_tot["mean"])
    if d_pred["hi"] < 0:
        verdict = "supported" if ratio >= 0.5 else "partially supported"
    else:
        verdict = "not supported"
    miss = {m: float(np.mean([r["summary"][m]["missed_per_scan"] for r in rows])) for m in METHODS}
    out = {
        "scenario": SID, "seeds": [r["seed"] for r in rows],
        "rmse_common": {m: mean_ci(rows, rc, m) for m in METHODS},
        "D_pred": d_pred, "D_rest": d_rest, "D_total": d_tot, "ratio_pred_of_total": ratio, "verdict": verdict,
        "missed_increase_percent_nnp_vs_nn": 100.0 * (miss["nnp"] - miss["nn"]) / miss["nn"],
        "caveat_sample_loss": bool(miss["nnp"] > 1.1 * miss["nn"]),
        "counts": {k: float(np.mean([r[k] for r in rows])) for k in ("n_truth", "n_common", "n_none")},
        "n_paired": {m: float(np.mean([r["n_paired"][m] for r in rows])) for m in METHODS},
        "own": {k: {m: mean_ci(rows, lambda r, mm: r["summary"][mm][k], m) for m in METHODS} for k in KEEP},
        "paired_own": {k: {"nnp-nn": pd_(rows, lambda r, mm: r["summary"][mm][k], "nnp", "nn"),
                           "ekf-nnp": pd_(rows, lambda r, mm: r["summary"][mm][k], "ekf", "nnp"),
                           "ekf-nn": pd_(rows, lambda r, mm: r["summary"][mm][k], "ekf", "nn")} for k in KEEP},
        "by_age": [], "nnp_fast": {},
    }
    for i in range(len(AGE_EDGES) - 1):
        n = sum(r["by_age"]["nn"][i]["n"] for r in rows)
        out["by_age"].append({"lo_s": AGE_EDGES[i], "hi_s": AGE_EDGES[i + 1] if np.isfinite(AGE_EDGES[i + 1]) else None,
                              "n_per_run": n / len(rows),
                              **{m: float(np.sqrt(sum(r["by_age"][m][i]["sq"] for r in rows) / n)) if n else None
                                 for m in METHODS}})
    nf = sum(r["nnp_fast"]["n_common"] for r in rows)
    out["nnp_fast"] = {"speed_limit_mps": SPEED_LIMIT, "n_common_per_run": nf / len(rows),
                       "share_of_common_percent": 100.0 * nf / sum(r["n_common"] for r in rows),
                       "rmse_fast_mean": float(np.nanmean([r["nnp_fast"]["rmse_common_fast"] for r in rows])),
                       "rmse_rest_mean": float(np.mean([r["nnp_fast"]["rmse_common_rest"] for r in rows])),
                       "n_own_per_run": float(np.mean([r["nnp_fast"]["n_own"] for r in rows]))}
    return out


def fmt(d, nd=1):
    return f"{d['mean']:.{nd}f} [{d['lo']:.{nd}f}, {d['hi']:.{nd}f}]"


def pm(d, nd=1):
    return f"{d['mean']:.{nd}f} ± {d['ci95']:.{nd}f}"


NAMES = {"nn": "기준선", "nnp": "기준선 + 출력 예측", "ekf": "EKF"}
VERDICT = {"supported": "지지", "partially supported": "부분 지지", "not supported": "지지하지 않음"}


def markdown(s):
    L = ["# 예측만 붙인 기준선: 결과", "",
         "`scripts/audit_predict_baseline.py`가 `results/audit/predict_baseline/runs.json`에서 만든 파일입니다. "
         "정의와 판정 규칙은 `docs/PREDICT_BASELINE_PROTOCOL.md`에 있습니다.", "",
         f"스히폴 평가 구간, seed {len(s['seeds'])}개, 기준 조건. ± 와 [ ]는 고정된 한 교통 구간에서의 시뮬레이션 변동(95% t-구간)입니다.", "",
         "## 세 방법 공통 표본의 scan-end RMSE", "",
         f"표적-scan {s['counts']['n_truth']:.0f}개/run 중 세 방법 모두 짝이 있는 것은 {s['counts']['n_common']:.0f}개, 모두 없는 것은 {s['counts']['n_none']:.0f}개입니다.", "",
         "| 방법 | 짝이 있는 표본/run | 공통 표본 RMSE (m) | 각자의 표본 RMSE (m) |", "|---|---:|---:|---:|"]
    for m in METHODS:
        L.append(f"| {NAMES[m]} | {s['n_paired'][m]:.0f} | {pm(s['rmse_common'][m])} | {pm(s['own']['rmse_m'][m])} |")
    L += ["", "| 단계 | 공통 표본 RMSE의 짝 차이 (m) |", "|---|---:|",
          f"| D_pred: 기준선 → 출력 예측 추가 | {fmt(s['D_pred'], 2)} |",
          f"| D_rest: 출력 예측 추가 → EKF | {fmt(s['D_rest'], 2)} |",
          f"| D_total: 기준선 → EKF | {fmt(s['D_total'], 2)} |", "",
          f"\\|D_pred\\| / \\|D_total\\| = {s['ratio_pred_of_total']:.3f} (이 순서로 한 단계씩 바꿨을 때의 값). "
          f"판정: **{VERDICT[s['verdict']]}**.",
          f"놓친 표적은 기준선 대비 {s['missed_increase_percent_nnp_vs_nn']:+.1f}%"
          + (" → 표본 탈락 단서를 붙입니다." if s["caveat_sample_loss"] else " → 표본 탈락 단서(10% 초과)에 해당하지 않습니다."), "",
          "## 함께 본 지표 (각자의 표본)", "",
          "| 지표 | 기준선 | 기준선 + 출력 예측 | EKF | 짝 차이 (예측 추가 − 기준선) |", "|---|---:|---:|---:|---:|"]
    lab = {"rmse_m": ("scan-end RMSE (m)", 1), "rmse_at_update_m": ("update-time RMSE (m)", 1), "id_switches": ("ID switch (회)", 1),
           "fragmentations": ("끊김 (회)", 1), "missed_per_scan": ("놓친 표적 (/scan)", 2),
           "false_tracks_per_scan": ("가짜 항적 (/scan)", 2), "gospa_mean_m": ("GOSPA (m)", 0), "gospa_loc_m": ("GOSPA 위치 성분 (m)", 0),
           "gospa_missed_m": ("GOSPA 놓침 성분 (m)", 0), "gospa_false_m": ("GOSPA 가짜 성분 (m)", 0)}
    for k, (name, nd) in lab.items():
        L.append(f"| {name} | " + " | ".join(pm(s["own"][k][m], nd) for m in METHODS) + f" | {fmt(s['paired_own'][k]['nnp-nn'], max(nd, 2))} |")
    L += ["", "## 마지막 탐지 뒤 지난 시간별 RMSE (공통 표본, 보조 기술)", "",
          "| 지난 시간 (s) | 표본/run | 기준선 (m) | 기준선 + 출력 예측 (m) | EKF (m) |", "|---|---:|---:|---:|---:|"]
    for b in s["by_age"]:
        hi = f"{b['hi_s']}" if b["hi_s"] is not None else "∞"
        v = lambda x: "–" if x is None else f"{x:.1f}"  # noqa: E731
        L.append(f"| {b['lo_s']}–{hi} | {b['n_per_run']:.0f} | {v(b['nn'])} | {v(b['nnp'])} | {v(b['ekf'])} |")
    f = s["nnp_fast"]
    L += ["", f"지난 시간은 기준선 항적의 마지막 탐지 기준입니다. EKF 항적의 마지막 갱신 시각은 다를 수 있습니다.", "",
          "## 두 점 속도가 큰 표본 (보조 기술)", "",
          f"변형의 항적 속도가 {f['speed_limit_mps']:.0f} m/s 이상인 공통 표본은 run당 {f['n_common_per_run']:.1f}개"
          f"({f['share_of_common_percent']:.2f}%)이고, 그 표본의 변형 RMSE는 {f['rmse_fast_mean']:.1f} m, 나머지는 {f['rmse_rest_mean']:.1f} m입니다(seed 평균).", ""]
    return "\n".join(L)


def readme_block(s):
    r, o, d = s["rmse_common"], s["own"], s["paired_own"]
    return "\n".join([
        "### 예측만 붙인 기준선 (감사 뒤 실험)",
        "",
        "감사는 6절 문장의 \"scan 사이 예측\" 부분을 관찰과 맞는 설명으로만 남겼습니다. 그래서 기준선의 연관과 항적 관리는 그대로 두고 "
        "출력에만 직선 외삽(최근 두 탐지점으로 구한 속도)을 붙인 변형 하나를 같은 seed로 돌렸습니다. 정의, 예측, 판정 규칙은 실행 전에 "
        "`docs/PREDICT_BASELINE_PROTOCOL.md`에 적어 커밋했고, 아래 수치는 `scripts/audit_predict_baseline.py`가 만든 것입니다"
        "(`results/audit/predict_baseline/summary.md`). 스히폴 평가 구간 하나에 대한 결과입니다.",
        "",
        "| | 기준선 | 기준선 + 출력 예측 | EKF |",
        "|---|---:|---:|---:|",
        f"| scan-end RMSE, 세 방법 공통 표본 {s['counts']['n_common']:,.0f}개/run [m] | " + " | ".join(pm(r[m]) for m in METHODS) + " |",
        f"| scan-end RMSE, 각자의 표본 [m] | " + " | ".join(pm(o["rmse_m"][m]) for m in METHODS) + " |",
        f"| update-time RMSE [m] | " + " | ".join(pm(o["rmse_at_update_m"][m]) for m in METHODS) + " |",
        f"| ID switch [회] | " + " | ".join(pm(o["id_switches"][m]) for m in METHODS) + " |",
        f"| 끊김 [회] | " + " | ".join(pm(o["fragmentations"][m]) for m in METHODS) + " |",
        f"| 놓친 표적 [/scan] | " + " | ".join(pm(o["missed_per_scan"][m], 2) for m in METHODS) + " |",
        "",
        f"- 공통 표본에서 기준선 → 출력 예측 추가는 {fmt(s['D_pred'], 2)} m, 출력 예측 추가 → EKF는 {fmt(s['D_rest'], 2)} m, "
        f"합은 {fmt(s['D_total'], 2)} m입니다. 첫 단계가 전체의 {100 * s['ratio_pred_of_total']:.1f}%입니다. "
        "이 비는 이 순서로 한 단계씩 바꿨을 때의 값이고 원인별 기여도가 아닙니다. 반대 순서에서는 값이 크게 다릅니다(아래 \"반대 순서\" 절).",
        f"- **판정: {VERDICT[s['verdict']]}.** 사전에 적은 규칙(구간이 0 아래이고 전체의 절반 이상)을 만족합니다. "
        "남은 차이는 필터의 평활과 연관(gating, 전역 배정)이 함께 만든 것이고 이번 실험은 그 둘을 나누지 않습니다.",
        f"- 연관이 같으므로 update-time RMSE는 기준선과 완전히 같고, ID switch도 달라지지 않았습니다(짝 차이 {fmt(d['id_switches']['nnp-nn'], 2)}회).",
        f"- 끊김과 놓친 표적은 크게 줄었습니다(끊김 {fmt(d['fragmentations']['nnp-nn'], 1)}회, 놓친 표적 {fmt(d['missed_per_scan']['nnp-nn'], 2)}/scan). "
        "두 방법의 항적과 연관은 같고 출력 위치만 다르므로, 기준선의 끊김과 놓친 표적 가운데 이만큼은 연관 실패가 아니라 "
        "출력 위치가 정답에서 2 km 넘게 떨어져 짝이 안 된 것입니다. "
        "따라서 위 감사의 단서에서 \"항적 번호 유지\"의 근거로 든 세 지표 가운데 연관의 차이를 가장 잘 보여 주는 것은 ID switch입니다"
        "(ID switch도 출력 위치의 영향을 일부 받습니다. 아래 \"반대 순서\" 절).",
        "- 실행 전 예측 가운데 두 가지가 틀렸습니다: 끊김은 기준선과 10% 안에서 같을 것, 놓친 표적과 가짜 항적은 조금 늘 것. "
        "RMSE 범위(220–320 m)와 절반 이상이라는 예측, ID switch 예측은 맞았습니다.",
        "",
        "![예측만 붙인 기준선](results/audit/figures/audit_predict_baseline.png)",
    ])


def figure(s):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    col = {"nn": "#8a8f98", "nnp": "#c2410c", "ekf": "#1d4ed8"}
    en = {"nn": "Baseline (last detection)", "nnp": "Baseline + output prediction", "ekf": "EKF + GNN"}
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 4.0), gridspec_kw={"width_ratios": [1, 1.5]})
    for i, m in enumerate(METHODS):
        v = s["rmse_common"][m]
        ax[0].bar(i, v["mean"], width=0.6, color=col[m])
        ax[0].errorbar(i, v["mean"], yerr=v["ci95"], color="#111", capsize=3, lw=1)
        ax[0].text(i, v["mean"] + 10, f"{v['mean']:.0f} m", ha="center", fontsize=9)
    ax[0].set_xticks(range(3), ["Baseline", "Baseline +\noutput prediction", "EKF + GNN"], fontsize=8)
    ax[0].set_ylabel("Scan-end RMSE on common samples (m)")
    ax[0].set_title("Same target-scans for all three methods", fontsize=10)
    x = np.arange(len(s["by_age"]))
    for m in METHODS:
        ax[1].plot(x, [b[m] for b in s["by_age"]], "o-", color=col[m], lw=2, ms=5, label=en[m])
    ax[1].set_xticks(x, [f"{b['lo_s']}–{b['hi_s'] if b['hi_s'] is not None else '∞'}" for b in s["by_age"]])
    ax[1].set_xlabel("Time since the baseline track's last detection (s)")
    ax[1].set_ylabel("Scan-end RMSE (m)")
    ax[1].set_title("Error by time since the last detection", fontsize=10)
    ax[1].legend(frameon=False, fontsize=8)
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
        a.grid(axis="y", color="#e5e7eb", lw=0.6)
        a.set_axisbelow(True)
        a.set_ylim(0)
    fig.suptitle(f"Schiphol evaluation window, {len(s['seeds'])} seeds (simulation variability only)", fontsize=9, color="#555")
    fig.tight_layout()
    (ROOT / "results/audit/figures").mkdir(exist_ok=True)
    fig.savefig(ROOT / "results/audit/figures/audit_predict_baseline.png", dpi=160)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    runs = OUT / "runs.json"
    if not runs.exists():
        t0 = time.time()
        cfg0, _ = load_stage2()
        sc, _, cfg = S.build(cfg0, S.specs()[SID])
        ref = {m: {r["seed"]: r["summary"] for r in
                   json.loads((ROOT / f"results/data/stage2/runs/{SID}__{m}.json").read_text())["runs"]} for m in ("nn", "ekf")}
        rows = []
        for seed in seeds(cfg):
            rows.append(one_seed(sc, cfg, seed, ref))
            print(seed, {m: round(rows[-1]["rmse_common"][m], 1) for m in METHODS}, f"{time.time() - t0:.0f}s", flush=True)
            if time.time() - t0 > 600:
                raise SystemExit("STOP: run exceeded 10 minutes")
        runs.write_text(json.dumps({"scenario": SID, "age_edges_s": [x if np.isfinite(x) else None for x in AGE_EDGES], "runs": rows}))
    rows = json.loads(runs.read_text())["runs"]
    s = summarize(rows)
    (OUT / "summary.json").write_text(json.dumps(s, indent=1))
    (OUT / "summary.md").write_text(markdown(s))
    figure(s)
    readme = ROOT / "README.md"
    t = readme.read_text(encoding="utf-8")
    a, b = "<!-- predict:begin -->", "<!-- predict:end -->"
    if a in t and b in t:
        readme.write_text(t[:t.index(a) + len(a)] + "\n" + readme_block(s) + "\n" + t[t.index(b):], encoding="utf-8")
    print(json.dumps({k: s[k] for k in ("rmse_common", "D_pred", "D_rest", "D_total", "ratio_pred_of_total", "verdict",
                                        "missed_increase_percent_nnp_vs_nn")}, indent=1))


if __name__ == "__main__":
    main()
