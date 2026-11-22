"""The four methods on the out-of-sample scenarios (docs/FOUR_METHODS_OOS_PROTOCOL.md).

    .venv/bin/python scripts/audit_four_methods_oos.py

Runs nn, nnp, ekfh and ekf on the 14 stage 2 out-of-sample scenarios (20 seeds each, checkpoint per
scenario in results/audit/four_methods_oos/runs/) and writes summary.json, summary.md, one figure
and the README block.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import audit_hold_ekf as H  # noqa: E402
from radar_track_lab import audit as A  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import load_stage2, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

OUT = ROOT / "results/audit/four_methods_oos"
METHODS = H.METHODS
EVAL = "EHAM_1106_eval"
KIND = {"oos_time": "다른 시간대", "oos_site_primary": "다른 공항", "oos_day_stage1": "다른 날", "oos_day_primary": "다른 공항·다른 날"}


def same(a, b):
    return a == b or (a != a and b != b)


def eq(a, b):
    return all(np.array_equal(a[f], b[f], equal_nan=True) for f in a)


def one_seed(sc, cfg, seed, ref, sid):
    res = {m: run(sc, cfg, seed=seed, method=m, audit=True) for m in METHODS}
    for m in ("nn", "ekf"):
        bad = [k for k, v in ref[m][seed].items() if not same(v, res[m].summary[k])]
        if bad:
            raise SystemExit(f"STOP {sid} {m} seed {seed}: scores differ from the stage 2 file: {bad}")
    if not eq(res["nn"].audit["update"], res["nnp"].audit["update"]):
        raise SystemExit(f"STOP {sid} seed {seed}: update samples of nnp differ from nn")
    if not eq(res["ekf"].audit["update"], res["ekfh"].audit["update"]):
        raise SystemExit(f"STOP {sid} seed {seed}: update samples of ekfh differ from ekf")
    c = A.common_scan_end_many({m: res[m].audit["scan_end"] for m in METHODS})
    return {"seed": seed, "summary": {m: {k: res[m].summary[k] for k in H.KEEP} for m in METHODS},
            "n_truth": c["n_truth"], "n_paired": c["n"], "n_common": c["n_common"], "n_none": c["none"],
            "rmse_common": {m: A.rmse(c["sq"][m]) for m in METHODS}}


def run_all():
    (OUT / "runs").mkdir(parents=True, exist_ok=True)
    cfg0, _ = load_stage2()
    specs = S.specs()
    t0 = time.time()
    for sid, spec in specs.items():
        if spec["kind"] not in KIND or (OUT / "runs" / f"{sid}.json").exists():
            continue
        if not (ROOT / f"results/data/stage2/runs/{sid}__ekf.json").exists():
            raise SystemExit(f"STOP {sid}: no stage 2 result file")
        sc, _, cfg = S.build(cfg0, spec)
        ref = {m: {r["seed"]: r["summary"] for r in
                   json.loads((ROOT / f"results/data/stage2/runs/{sid}__{m}.json").read_text())["runs"]} for m in ("nn", "ekf")}
        rows = []
        for seed in seeds(cfg):
            rows.append(one_seed(sc, cfg, seed, ref, sid))
            if time.time() - t0 > 3600:
                raise SystemExit("STOP: run exceeded 1 hour")
        (OUT / "runs" / f"{sid}.json").write_text(json.dumps({"scenario": sid, "spec": spec,
                                                               "truth_per_scan": sc.meta["truth_per_scan_mean"], "runs": rows}))
        print(sid, {m: round(float(np.mean([r["rmse_common"][m] for r in rows])), 1) for m in METHODS},
              f"{time.time() - t0:.0f}s", flush=True)


def verdict(n):
    return "다른 곳에서도 성립" if n >= 10 else ("일부에서만 성립" if n >= 6 else "성립하지 않음")


def label(x):
    return f"{x['spec']['site']} {x['spec']['day'][5:]} {x['spec']['start_utc'][11:16]}"


def summarize():
    out = {}
    for f in sorted((OUT / "runs").glob("*.json")):
        doc = json.loads(f.read_text())
        s = H.summarize(doc["runs"])
        s.update(spec=doc["spec"], truth_per_scan=doc["truth_per_scan"], valid=bool(doc["truth_per_scan"] >= 5.0))
        s["A_ok"] = bool(s["A_pred"]["hi"] < 0 and s["s_A"] >= 0.5)
        s["B_ok"] = bool(s["B_pred"]["hi"] < 0 and s["s_B"] >= 0.5)
        s["order_dependent"] = bool(abs(s["s_B"] - s["s_A"]) > 0.10)
        s["rest_ratio"] = abs(s["B_rest"]["mean"]) / abs(s["D_total"]["mean"])
        s["near_baseline"] = bool(s["rest_ratio"] <= 0.10)
        out[f.stem] = s
    v = [k for k in out if out[k]["valid"]]
    cnt = {"G1": sum(out[k]["A_ok"] and out[k]["B_ok"] for k in v), "G2": sum(out[k]["order_dependent"] for k in v),
           "G3": sum(out[k]["near_baseline"] for k in v)}
    pred = {"s_B>=0.9": sum(out[k]["s_B"] >= 0.9 for k in v), "0.45<=s_A<=0.75": sum(0.45 <= out[k]["s_A"] <= 0.75 for k in v),
            "order_gap>0.10": cnt["G2"], "rest<=10%": cnt["G3"]}
    rng = lambda key: [min(out[k][key] for k in v), max(out[k][key] for k in v)]  # noqa: E731
    overall = {"scenarios": len(out), "valid": len(v), "counts": cnt, "verdicts": {g: verdict(n) for g, n in cnt.items()},
               "predictions": pred, "s_A_range": rng("s_A"), "s_B_range": rng("s_B"), "rest_ratio_range": rng("rest_ratio"),
               "failing": {"A": [k for k in v if not out[k]["A_ok"]], "B": [k for k in v if not out[k]["B_ok"]],
                           "order": [k for k in v if not out[k]["order_dependent"]],
                           "near_baseline": [k for k in v if not out[k]["near_baseline"]]}}
    return out, overall


def table(out, ref):
    order = sorted(out, key=lambda k: (not out[k]["valid"], out[k]["spec"]["day"], out[k]["spec"]["site"] != "EHAM", k))
    L = ["| 시나리오 (UTC) | 표적/scan | 공통 표본/run | 기준선 | 기준선 + 출력 예측 | EKF, 출력 예측 없음 | EKF | s_A | s_B | \\|B_rest\\|/\\|D_total\\| |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    r = ref["rmse_common"]
    L.append(f"| (참고) EHAM 11-06 12:45, 앞 실험 | 50.4 | {ref['counts']['n_common']:,.0f} | " + " | ".join(f"{r[m]['mean']:.1f}" for m in METHODS)
             + f" | {100 * ref['s_A']:.1f}% | {100 * ref['s_B']:.1f}% | {100 * abs(ref['B_rest']['mean']) / abs(ref['D_total']['mean']):.1f}% |")
    for k in order:
        x = out[k]
        L.append(f"| {label(x)}{'' if x['valid'] else ' (유효하지 않음)'} | {x['truth_per_scan']:.1f} | {x['counts']['n_common']:,.0f} | "
                 + " | ".join(f"{x['rmse_common'][m]['mean']:.1f}" for m in METHODS)
                 + f" | {100 * x['s_A']:.1f}% | {100 * x['s_B']:.1f}% | {100 * x['rest_ratio']:.1f}% |")
    return L


def bullets(o):
    c, v, n = o["counts"], o["verdicts"], o["valid"]
    names = lambda ks: ", ".join(ks) if ks else "없음"  # noqa: E731
    return [
        f"- **G1 (두 순서 모두 절반 이상): {v['G1']}.** 유효 {n}개 중 {c['G1']}개. 순서 A에서 규칙을 못 채운 시나리오: {names(o['failing']['A'])}. 순서 B: {names(o['failing']['B'])}.",
        f"- **G2 (두 순서의 몫이 10%p 넘게 다름): {v['G2']}.** {n}개 중 {c['G2']}개. s_A의 범위는 {100 * o['s_A_range'][0]:.1f}–{100 * o['s_A_range'][1]:.1f}%, "
        f"s_B의 범위는 {100 * o['s_B_range'][0]:.1f}–{100 * o['s_B_range'][1]:.1f}%입니다.",
        f"- **G3 (출력 예측을 뺀 EKF와 기준선의 차이가 전체의 10% 이하): {v['G3']}.** {n}개 중 {c['G3']}개. 비의 범위는 "
        f"{100 * o['rest_ratio_range'][0]:.1f}–{100 * o['rest_ratio_range'][1]:.1f}%입니다. 넘은 시나리오: {names(o['failing']['near_baseline'])}.",
    ]


def companion(out):
    order = sorted((k for k in out if out[k]["valid"]), key=lambda k: (out[k]["spec"]["day"], out[k]["spec"]["site"] != "EHAM", k))
    L = ["| 시나리오 (UTC) | ID switch (기준선 / +예측 / EKF 예측 없음 / EKF) | 끊김 | 놓친 표적 /scan |", "|---|---:|---:|---:|"]
    g = lambda x, k, nd: " / ".join(f"{x['own'][k][m]['mean']:.{nd}f}" for m in METHODS)  # noqa: E731
    for k in order:
        x = out[k]
        L.append(f"| {label(x)} | {g(x, 'id_switches', 1)} | {g(x, 'fragmentations', 1)} | {g(x, 'missed_per_scan', 2)} |")
    return L


def markdown(out, o, ref):
    p = o["predictions"]
    n = o["valid"]
    return "\n".join([
        "# 네 방법을 다른 공항·날짜에 돌린 결과", "",
        "`scripts/audit_four_methods_oos.py`가 `results/audit/four_methods_oos/runs/`에서 만든 파일입니다. 정의와 판정 규칙은 `docs/FOUR_METHODS_OOS_PROTOCOL.md`에 있습니다.", "",
        "수치는 네 방법 공통 표본의 scan-end RMSE(m), seed 20개 평균입니다. s_A는 \"기준선 → 출력 예측 추가 → EKF\" 순서에서, s_B는 "
        "\"기준선 → EKF(출력 예측 없음) → EKF\" 순서에서 출력 예측 단계가 전체 차이에서 차지하는 몫입니다. "
        "시나리오 사이의 퍼짐은 범위와 개수로만 적습니다. 같은 공항의 두 날과 같은 날의 여러 공항은 독립 표본이 아닙니다.", "",
        *table(out, ref), "", "## 판정", "", *bullets(o), "",
        "## 실행 전 예측과 실제", "",
        f"| 예측 | 실제 (유효 {n}개 중) |", "|---|---:|",
        f"| s_B ≥ 0.9, 12개 모두 | {p['s_B>=0.9']}개 |", f"| 0.45 ≤ s_A ≤ 0.75, 10개 이상 | {p['0.45<=s_A<=0.75']}개 |",
        f"| 몫의 차이 > 0.10, 12개 모두 | {p['order_gap>0.10']}개 |", f"| \\|B_rest\\| ≤ 10%, 12개 모두 | {p['rest<=10%']}개 |", "",
        "## 함께 본 지표 (각자의 표본, 유효 시나리오)", "", *companion(out), ""])


def readme_block(out, o, ref):
    return "\n".join([
        "### 다른 공항·날짜에서의 네 방법",
        "",
        "위 두 실험은 스히폴 한 구간의 결과라, 같은 네 방법을 2단계의 표본 밖 시나리오 14개에 그대로 돌렸습니다. 새 변형과 조정은 없습니다. "
        "판정 규칙은 실행 전에 `docs/FOUR_METHODS_OOS_PROTOCOL.md`에 적어 커밋했고, 아래 수치는 `scripts/audit_four_methods_oos.py`가 만든 것입니다"
        "(`results/audit/four_methods_oos/summary.md`). 수치는 네 방법 공통 표본의 scan-end RMSE(m)입니다.",
        "", *table(out, ref), "", *bullets(o),
        "- 시나리오 사이의 퍼짐은 범위와 개수로만 적었습니다. 같은 공항의 두 날과 같은 날의 여러 공항은 독립 표본이 아니어서 12개에 대한 구간이나 검정은 만들지 않았습니다.",
        "",
        "![시나리오별 두 순서의 몫](results/audit/figures/audit_four_methods_oos.png)",
    ])


def figure(out, ref):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = sorted((k for k in out if out[k]["valid"]), key=lambda k: (out[k]["spec"]["day"], out[k]["spec"]["site"] != "EHAM", k))
    rows = [("Schiphol 11-06 12:45 (earlier experiment)", ref["s_A"], ref["s_B"])] + [
        (f"{label(out[k])}  ({out[k]['truth_per_scan']:.0f}/scan)", out[k]["s_A"], out[k]["s_B"]) for k in order]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    y = np.arange(len(rows))[::-1]
    for yi, (_, a, b) in zip(y, rows):
        ax.plot([100 * a, 100 * b], [yi, yi], color="#cbd5e1", lw=2, zorder=1)
    ax.scatter([100 * r[1] for r in rows], y, s=42, color="#c2410c", zorder=2, label="Order A: baseline → + output prediction → EKF")
    ax.scatter([100 * r[2] for r in rows], y, s=42, color="#1d4ed8", zorder=2, label="Order B: baseline → EKF, output held → EKF")
    ax.axvline(50, color="#94a3b8", lw=1, ls="--")
    ax.set_yticks(y, [r[0] for r in rows], fontsize=8.5)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Share of the scan-end RMSE gap removed by the output-prediction step (%)")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#e5e7eb", lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.0))
    fig.tight_layout()
    fig.savefig(ROOT / "results/audit/figures/audit_four_methods_oos.png", dpi=160)


def main() -> None:
    run_all()
    out, o = summarize()
    ref = json.loads((ROOT / "results/audit/hold_ekf/summary.json").read_text())
    (OUT / "summary.json").write_text(json.dumps({"overall": o, "scenarios": out}, indent=1))
    (OUT / "summary.md").write_text(markdown(out, o, ref))
    figure(out, ref)
    readme = ROOT / "README.md"
    t = readme.read_text(encoding="utf-8")
    a, b = "<!-- oos4:begin -->", "<!-- oos4:end -->"
    if a in t and b in t:
        readme.write_text(t[:t.index(a) + len(a)] + "\n" + readme_block(out, o, ref) + "\n" + t[t.index(b):], encoding="utf-8")
    print(json.dumps(o, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
