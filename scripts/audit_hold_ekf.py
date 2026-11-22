"""EKF with output prediction removed: reverse-order ablation (docs/HOLD_EKF_PROTOCOL.md).

    .venv/bin/python scripts/audit_hold_ekf.py

Runs nn, nnp, ekfh (EKF + GNN, output held at the last update) and ekf on the Schiphol evaluation
window with the same 20 seeds, checks the stop conditions and writes
results/audit/hold_ekf/{runs.json, summary.json, summary.md} and one figure.
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
from radar_track_lab.metrics import mean_ci as _mean_ci  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

OUT = ROOT / "results/audit/hold_ekf"
SID = "EHAM_1106_eval"
METHODS = ("nn", "nnp", "ekfh", "ekf")
KEEP = ("rmse_m", "rmse_at_update_m", "id_switches", "fragmentations", "missed_per_scan", "false_tracks_per_scan",
        "gospa_mean_m", "gospa_loc_m", "gospa_missed_m", "gospa_false_m", "tracks_per_scan", "truth_per_scan")
NAMES = {"nn": "기준선", "nnp": "기준선 + 출력 예측", "ekfh": "EKF, 출력 예측 없음", "ekf": "EKF"}


def same(a, b):
    return a == b or (a != a and b != b)


def one_seed(sc, cfg, seed, ref):
    res = {m: run(sc, cfg, seed=seed, method=m, audit=True) for m in METHODS}
    for m in ("nn", "ekf", "nnp"):  # stop condition: existing scores must not change
        bad = [k for k, v in ref[m][seed].items() if not same(v, res[m].summary[k])]
        if bad:
            raise SystemExit(f"STOP {m} seed {seed}: scores differ from the existing file: {bad}")
    a, b = res["ekf"].audit["update"], res["ekfh"].audit["update"]
    if not all(np.array_equal(a[f], b[f], equal_nan=True) for f in a):
        raise SystemExit(f"STOP seed {seed}: update samples of ekfh differ from ekf")
    if not same(res["ekf"].summary["rmse_at_update_m"], res["ekfh"].summary["rmse_at_update_m"]):
        raise SystemExit(f"STOP seed {seed}: update-time RMSE of ekfh differs from ekf")
    c = A.common_scan_end_many({m: res[m].audit["scan_end"] for m in METHODS})
    return {"seed": seed, "summary": {m: {k: res[m].summary[k] for k in KEEP} for m in METHODS},
            "n_truth": c["n_truth"], "n_paired": c["n"], "n_common": c["n_common"], "n_none": c["none"],
            "rmse_common": {m: A.rmse(c["sq"][m]) for m in METHODS}}


def ci(rows, f, m):
    v, h = _mean_ci(np.array([f(r, m) for r in rows], dtype=float))
    return {"mean": v, "ci95": h}


def summarize(rows):
    rc = lambda r, m: r["rmse_common"][m]  # noqa: E731
    pd = lambda f, a, b: A.paired_diff([f(r, a) for r in rows], [f(r, b) for r in rows])  # noqa: E731
    d = {"A_pred": pd(rc, "nnp", "nn"), "A_rest": pd(rc, "ekf", "nnp"), "B_rest": pd(rc, "ekfh", "nn"),
         "B_pred": pd(rc, "ekf", "ekfh"), "D_total": pd(rc, "ekf", "nn")}
    s_a, s_b = d["A_pred"]["mean"] / d["D_total"]["mean"], d["B_pred"]["mean"] / d["D_total"]["mean"]
    h1 = ("supported" if s_b >= 0.5 else "partially supported") if d["B_pred"]["hi"] < 0 else "not supported"
    h2 = "similar" if abs(s_b - s_a) <= 0.10 else "order-dependent"
    own = lambda r, m, k: r["summary"][m][k]  # noqa: E731
    return {"scenario": SID, "seeds": [r["seed"] for r in rows],
            "counts": {k: float(np.mean([r[k] for r in rows])) for k in ("n_truth", "n_common", "n_none")},
            "n_paired": {m: float(np.mean([r["n_paired"][m] for r in rows])) for m in METHODS},
            "rmse_common": {m: ci(rows, rc, m) for m in METHODS}, **d, "s_A": s_a, "s_B": s_b, "H1": h1, "H2": h2,
            "own": {k: {m: ci(rows, lambda r, mm: own(r, mm, k), m) for m in METHODS} for k in KEEP},
            "paired_own": {k: {"ekfh-ekf": pd(lambda r, mm: own(r, mm, k), "ekfh", "ekf"),
                               "ekfh-nn": pd(lambda r, mm: own(r, mm, k), "ekfh", "nn")} for k in KEEP}}


def fmt(d, nd=2):
    return f"{d['mean']:.{nd}f} [{d['lo']:.{nd}f}, {d['hi']:.{nd}f}]"


def pm(d, nd=1):
    return f"{d['mean']:.{nd}f} ± {d['ci95']:.{nd}f}"


H1 = {"supported": "지지", "partially supported": "부분 지지", "not supported": "지지하지 않음"}
H2 = {"similar": "순서와 무관하게 비슷함", "order-dependent": "순서에 따라 다름"}
LAB = {"rmse_m": ("scan-end RMSE, 각자의 표본 (m)", 1), "rmse_at_update_m": ("update-time RMSE (m)", 1),
       "id_switches": ("ID switch (회)", 1), "fragmentations": ("끊김 (회)", 1), "missed_per_scan": ("놓친 표적 (/scan)", 2),
       "false_tracks_per_scan": ("가짜 항적 (/scan)", 2), "gospa_mean_m": ("GOSPA (m)", 0)}


def table_main(s):
    L = ["| | " + " | ".join(NAMES[m] for m in METHODS) + " |", "|---|" + "---:|" * len(METHODS),
         f"| scan-end RMSE, 네 방법 공통 표본 {s['counts']['n_common']:,.0f}개/run (m) | " + " | ".join(pm(s["rmse_common"][m]) for m in METHODS) + " |",
         "| 짝이 있는 표본/run | " + " | ".join(f"{s['n_paired'][m]:,.0f}" for m in METHODS) + " |"]
    for k, (name, nd) in LAB.items():
        L.append(f"| {name} | " + " | ".join(pm(s["own"][k][m], nd) for m in METHODS) + " |")
    return L


def table_paths(s):
    return ["| 순서 | 출력 예측 단계 (m) | 나머지 단계 (m) | 출력 예측의 몫 |", "|---|---:|---:|---:|",
            f"| A: 기준선 → 출력 예측 추가 → EKF | {fmt(s['A_pred'])} | {fmt(s['A_rest'])} | {100 * s['s_A']:.1f}% |",
            f"| B: 기준선 → EKF(출력 예측 없음) → EKF | {fmt(s['B_pred'])} | {fmt(s['B_rest'])} | {100 * s['s_B']:.1f}% |",
            "", f"전체 D_total = {fmt(s['D_total'])} m."]


def markdown(s):
    p = s["paired_own"]
    return "\n".join([
        "# 출력 예측을 뺀 EKF: 결과", "",
        "`scripts/audit_hold_ekf.py`가 `results/audit/hold_ekf/runs.json`에서 만든 파일입니다. 정의와 판정 규칙은 `docs/HOLD_EKF_PROTOCOL.md`에 있습니다.", "",
        f"스히폴 평가 구간, seed {len(s['seeds'])}개, 기준 조건. ± 와 [ ]는 고정된 한 교통 구간에서의 시뮬레이션 변동(95% t-구간)입니다.", "",
        f"표적-scan {s['counts']['n_truth']:,.0f}개/run 중 네 방법 모두 짝이 있는 것은 {s['counts']['n_common']:,.0f}개, 모두 없는 것은 {s['counts']['n_none']:,.0f}개입니다.", "",
        *table_main(s), "", "## 두 순서 (네 방법 공통 표본의 scan-end RMSE, 짝 차이)", "", *table_paths(s), "",
        f"- H1: **{H1[s['H1']]}**. H2: **{H2[s['H2']]}** (몫의 차이 {100 * abs(s['s_B'] - s['s_A']):.1f}%p).",
        "- 두 줄의 \"출력 예측\"은 내용이 다릅니다. 기준선 쪽은 두 점 속도, EKF 쪽은 필터가 추정한 속도입니다.", "",
        "## 출력 예측을 뺀 EKF의 짝 차이 (각자의 표본, ekfh − ekf)", "",
        "| 지표 | 짝 차이 |", "|---|---:|",
        *[f"| {LAB[k][0]} | {fmt(p[k]['ekfh-ekf'])} |" for k in LAB], ""])


def readme_block(s):
    p = s["paired_own"]
    return "\n".join([
        "### 반대 순서: 출력 예측을 뺀 EKF",
        "",
        "위 59.9%는 한 순서에서의 값이라, 반대 순서도 돌렸습니다. EKF의 필터와 연관은 그대로 두고 출력만 \"마지막 갱신 위치 유지\"로 바꾼 변형 하나입니다. "
        "정의, 예측, 판정 규칙은 실행 전에 `docs/HOLD_EKF_PROTOCOL.md`에 적어 커밋했고, 아래 수치는 `scripts/audit_hold_ekf.py`가 만든 것입니다"
        "(`results/audit/hold_ekf/summary.md`). 스히폴 평가 구간 하나에 대한 결과입니다.",
        "", *table_main(s), "", *table_paths(s), "",
        f"- **판정: {H1[s['H1']]}, {H2[s['H2']]}.** 출력 예측 단계의 몫은 순서 A에서 {100 * s['s_A']:.1f}%, 순서 B에서 {100 * s['s_B']:.1f}%입니다. "
        "어느 한 값을 \"예측의 기여도\"로 쓰지 않고 두 값을 함께 적습니다.",
        "- 두 순서의 \"출력 예측\"은 내용이 다릅니다. 기준선 쪽은 잡음이 큰 두 점 속도로 외삽하고, EKF 쪽은 필터가 추정한 속도로 예측합니다.",
        f"- 필터와 연관이 EKF와 같으므로 update-time RMSE는 EKF와 완전히 같습니다. 출력만 바꿨을 때 ID switch는 {fmt(p['id_switches']['ekfh-ekf'])}회, "
        f"끊김은 {fmt(p['fragmentations']['ekfh-ekf'])}회, 놓친 표적은 {fmt(p['missed_per_scan']['ekfh-ekf'])}/scan 달라졌습니다(변형 − EKF).",
        "",
        "![두 순서의 단계별 RMSE](results/audit/figures/audit_hold_ekf.png)",
    ])


def figure(s):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    col = {"nn": "#8a8f98", "nnp": "#c2410c", "ekfh": "#0f766e", "ekf": "#1d4ed8"}
    en = {"nn": "Baseline\n(last detection)", "nnp": "Baseline +\noutput prediction", "ekfh": "EKF + GNN,\noutput held", "ekf": "EKF + GNN"}
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    for i, m in enumerate(METHODS):
        v = s["rmse_common"][m]
        ax.bar(i, v["mean"], width=0.6, color=col[m])
        ax.errorbar(i, v["mean"], yerr=v["ci95"], color="#111", capsize=3, lw=1)
        ax.text(i, v["mean"] + 10, f"{v['mean']:.0f} m", ha="center", fontsize=9)
    ax.set_xticks(range(4), [en[m] for m in METHODS], fontsize=8)
    ax.set_ylabel("Scan-end RMSE on common samples (m)")
    ax.set_title("Same target-scans for all four methods", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e7eb", lw=0.6)
    ax.set_axisbelow(True)
    fig.suptitle(f"Schiphol evaluation window, {len(s['seeds'])} seeds (simulation variability only)", fontsize=9, color="#555")
    fig.tight_layout()
    fig.savefig(ROOT / "results/audit/figures/audit_hold_ekf.png", dpi=160)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    runs = OUT / "runs.json"
    if not runs.exists():
        t0 = time.time()
        cfg0, _ = load_stage2()
        sc, _, cfg = S.build(cfg0, S.specs()[SID])
        ref = {m: {r["seed"]: r["summary"] for r in
                   json.loads((ROOT / f"results/data/stage2/runs/{SID}__{m}.json").read_text())["runs"]} for m in ("nn", "ekf")}
        ref["nnp"] = {r["seed"]: r["summary"]["nnp"] for r in
                      json.loads((ROOT / "results/audit/predict_baseline/runs.json").read_text())["runs"]}
        rows = []
        for seed in seeds(cfg):
            rows.append(one_seed(sc, cfg, seed, ref))
            print(seed, {m: round(rows[-1]["rmse_common"][m], 1) for m in METHODS}, f"{time.time() - t0:.0f}s", flush=True)
            if time.time() - t0 > 600:
                raise SystemExit("STOP: run exceeded 10 minutes")
        runs.write_text(json.dumps({"scenario": SID, "runs": rows}))
    s = summarize(json.loads(runs.read_text())["runs"])
    (OUT / "summary.json").write_text(json.dumps(s, indent=1))
    (OUT / "summary.md").write_text(markdown(s))
    figure(s)
    readme = ROOT / "README.md"
    t = readme.read_text(encoding="utf-8")
    a, b = "<!-- hold:begin -->", "<!-- hold:end -->"
    if a in t and b in t:
        readme.write_text(t[:t.index(a) + len(a)] + "\n" + readme_block(s) + "\n" + t[t.index(b):], encoding="utf-8")
    print(markdown(s))


if __name__ == "__main__":
    main()
