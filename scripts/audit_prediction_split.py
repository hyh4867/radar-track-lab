"""Split the scan-end RMSE gap (baseline -> EKF) into the output-prediction part
and the filter/gating/association part, from run files that already exist.

No simulation is run. Inputs (seed-level common-sample scan-end RMSE):
  results/audit/predict_baseline/runs.json   nn, nnp, ekf      (3-way common sample)
  results/audit/hold_ekf/runs.json           nn, nnp, ekfh, ekf (4-way common sample)
  results/audit/four_methods_oos/runs/*.json nn, nnp, ekfh, ekf (4-way, 14 scenarios)

The four methods form a 2x2 layout: tracker (NN baseline / EKF+GNN) x output
prediction (held at last update / extrapolated to scan end). The "prediction"
level is not the same content in both rows (two-point velocity for NN, filter
velocity for EKF), so the interaction term is descriptive only.

Output: results/audit/prediction_split/summary.json and summary.md
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "audit" / "prediction_split"
MIN_TRUTH_PER_SCAN = 5.0  # validity rule of FOUR_METHODS_OOS_PROTOCOL.md (stage 2)


def ci(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    m = float(x.mean())
    h = float(stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x)))
    return {"mean": m, "lo": m - h, "hi": m + h, "n": int(len(x))}


def col(runs: list, key: str) -> np.ndarray:
    return np.array([r["rmse_common"][key] for r in runs], dtype=float)


def split4(runs: list) -> dict:
    nn, nnp, ekfh, ekf = (col(runs, k) for k in ("nn", "nnp", "ekfh", "ekf"))
    total = ekf - nn
    terms = {
        "total": total,
        "pred_on_nn": nnp - nn,          # order A, first step
        "rest_after_pred": ekf - nnp,    # order A, second step
        "filter_no_pred": ekfh - nn,     # order B, first step
        "pred_on_ekf": ekf - ekfh,       # order B, second step
        "interaction": (ekf - ekfh) - (nnp - nn),
    }
    out = {k: ci(v) for k, v in terms.items()}
    out["share_of_total"] = {k: float(v.mean() / total.mean()) for k, v in terms.items()}
    out["rmse_common"] = {k: ci(col(runs, k)) for k in ("nn", "nnp", "ekfh", "ekf")}
    out["seeds"] = sorted(int(r["seed"]) for r in runs)
    return out


def fmt(c: dict) -> str:
    return f"{c['mean']:.2f} [{c['lo']:.2f}, {c['hi']:.2f}]"


def main() -> None:
    pb = json.loads((ROOT / "results/audit/predict_baseline/runs.json").read_text())["runs"]
    nn, nnp, ekf = (col(pb, k) for k in ("nn", "nnp", "ekf"))
    three = {
        "seeds": sorted(int(r["seed"]) for r in pb),
        "D_pred": ci(nnp - nn),
        "D_rest": ci(ekf - nnp),
        "D_total": ci(ekf - nn),
        "share_pred_per_seed": ci((nnp - nn) / (ekf - nn)),
    }
    hold = json.loads((ROOT / "results/audit/hold_ekf/runs.json").read_text())["runs"]
    four = split4(hold)

    oos = []
    for p in sorted(glob.glob(str(ROOT / "results/audit/four_methods_oos/runs/*.json"))):
        d = json.loads(Path(p).read_text())
        s = split4(d["runs"])
        s["scenario"] = d["scenario"]
        s["truth_per_scan"] = float(d["truth_per_scan"])
        s["valid"] = bool(d["truth_per_scan"] >= MIN_TRUTH_PER_SCAN)
        oos.append(s)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(
        json.dumps({"three_way_eham": three, "four_way_eham": four, "oos": oos}, indent=1)
    )

    L = []
    L.append("# scan-end RMSE 차이의 분해 (기존 run 파일에서 계산)\n")
    L.append("`scripts/audit_prediction_split.py`가 만든 파일입니다. 새 시뮬레이션은 없습니다. "
             "[ ]는 seed 20개의 짝 차이에 대한 95% t-구간입니다.\n")
    L.append("## 스히폴 평가 구간, 세 방법 공통 표본 (predict_baseline/runs.json)\n")
    L.append("| 단계 | 짝 차이 (m) |\n|---|---:|")
    L.append(f"| 기준선 → 기준선 + 출력 예측 | {fmt(three['D_pred'])} |")
    L.append(f"| 기준선 + 출력 예측 → EKF | {fmt(three['D_rest'])} |")
    L.append(f"| 기준선 → EKF | {fmt(three['D_total'])} |")
    sp = three["share_pred_per_seed"]
    L.append(f"\n출력 예측 단계의 몫 (seed별 비의 평균): {100*sp['mean']:.1f}% [{100*sp['lo']:.1f}, {100*sp['hi']:.1f}]\n")
    L.append("## 스히폴 평가 구간, 네 방법 공통 표본 (hold_ekf/runs.json)\n")
    L.append("| 항 | 짝 차이 (m) | 전체 대비 |\n|---|---:|---:|")
    names = [
        ("total", "전체: 기준선 → EKF"),
        ("pred_on_nn", "A1: 기준선에 출력 예측만 추가"),
        ("rest_after_pred", "A2: 그 위에 필터·gating·할당"),
        ("filter_no_pred", "B1: 필터·gating·할당만 (출력 예측 없음)"),
        ("pred_on_ekf", "B2: 그 위에 EKF 출력 예측"),
        ("interaction", "상호작용: B2 − A1 (= A2 − B1)"),
    ]
    for k, label in names:
        L.append(f"| {label} | {fmt(four[k])} | {100*four['share_of_total'][k]:.1f}% |")
    L.append("\n## 표본 밖 14개 시나리오 (four_methods_oos/runs, 네 방법 공통 표본)\n")
    L.append("| 시나리오 | 표적/scan | 전체 (m) | A1 출력 예측만 | B1 필터·gating·할당만 | 상호작용 | A1 몫 | B1 몫 | 상호작용 몫 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in oos:
        sh = s["share_of_total"]
        tag = "" if s["valid"] else " (유효하지 않음)"
        L.append(
            f"| {s['scenario']}{tag} | {s['truth_per_scan']:.1f} | {s['total']['mean']:.1f} | "
            f"{s['pred_on_nn']['mean']:.1f} | {s['filter_no_pred']['mean']:.1f} | {s['interaction']['mean']:.1f} | "
            f"{100*sh['pred_on_nn']:.1f}% | {100*sh['filter_no_pred']:.1f}% | {100*sh['interaction']:.1f}% |"
        )
    valid = [s for s in oos if s["valid"]]
    rng = lambda k: (min(100 * s["share_of_total"][k] for s in valid), max(100 * s["share_of_total"][k] for s in valid))
    L.append(
        f"\n유효 {len(valid)}개 범위: A1 {rng('pred_on_nn')[0]:.1f}–{rng('pred_on_nn')[1]:.1f}%, "
        f"B1 {rng('filter_no_pred')[0]:.1f}–{rng('filter_no_pred')[1]:.1f}%, "
        f"상호작용 {rng('interaction')[0]:.1f}–{rng('interaction')[1]:.1f}%."
    )
    L.append("\n상호작용 항은 사전 등록하지 않은 기술 통계입니다. 두 행의 \"출력 예측\"은 내용이 다릅니다"
             "(기준선은 두 점 속도, EKF는 필터 속도).")
    (OUT / "summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
