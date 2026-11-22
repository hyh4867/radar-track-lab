"""Stage 3 follow-up: C2 broken down by scenario, the cause of the IMM gain, and where lost tracks happen.

Post-hoc analysis (not a verdict). Reads only results/stage3/a/*.json; uses json, numpy and scipy only
(no radar_track_lab import). Definitions (same as the stage 3 report):
  lost       = sum of causes except truth_gap and near_other
  turn share = turn / lost
  base rate  = sum base.window_turn / sum base.assigned_target_scans
  top-2 dependence = turn share after removing every lost event (any cause) of the two aircraft with the most
                     turn losses in that scenario. A sensitivity measure, not a corrected value.

    .venv/bin/python scripts/stage3_c2_breakdown.py
Output: results/stage3/c2_breakdown.json, c2_breakdown.md
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "results/stage3/a"
OUT = ROOT / "results/stage3"
EVAL = "EHAM_1106_eval"
# stage 2 valid out-of-sample list (>= 5 truth targets per scan under the ideal model), unchanged in stage 3
OOS = ["EGLL_1106_peak", "EGLL_1111_same", "EHAM_1106_busy2", "EHAM_1111_same", "ENGM_1106_peak", "ENGM_1111_same",
       "KATL_1106_peak", "KATL_1111_same", "LSZH_1106_peak", "LSZH_1111_same", "YSSY_1106_peak", "YSSY_1111_same"]
MODELS = ("M0", "M1", "M2", "M4")
METHODS = ("ekf", "imm")
NOT_LOST = ("truth_gap", "near_other")
BINS_KM = [0, 5, 10, 15, 40, 60, 80, 90, 100]


def lost_of(causes: dict) -> int:
    return int(sum(v for k, v in causes.items() if k not in NOT_LOST))


def breakdown(runs: list[dict]) -> dict:
    """``runs``: list of per-seed method records (``causes``, ``base``, ``lost_events``)."""
    c = Counter()
    asg = win = 0
    events = []
    for r in runs:
        c.update(r["causes"])
        asg += r["base"]["assigned_target_scans"]
        win += r["base"]["window_turn"]
        events += r["lost_events"]
    lost = lost_of(c)
    if len(events) != lost:
        raise ValueError(f"lost_events ({len(events)}) != lost from causes ({lost})")
    turn, misses = int(c["turn"]), int(c["misses"])
    base = win / asg if asg else float("nan")
    share = turn / lost if lost else float("nan")
    per_ac = Counter(e["target"] for e in events if e["cause"] == "turn")
    top2 = [t for t, _ in sorted(per_ac.items(), key=lambda kv: (-kv[1], kv[0]))[:2]]
    rest = [e for e in events if e["target"] not in top2]
    rest_turn = sum(e["cause"] == "turn" for e in rest)
    return {"lost": lost, "turn": turn, "misses": misses, "other": lost - turn - misses, "turn_share": share,
            "base_rate": base, "share_over_base": share / base if base else float("nan"),
            "top2": top2, "turn_share_wo_top2": rest_turn / len(rest) if rest else float("nan"),
            "turn_wo_top2": int(rest_turn), "lost_wo_top2": len(rest), "n_aircraft_turn": len(per_ac)}


def tci(x):
    x = np.asarray(x, float)
    m = x.mean()
    h = stats.t.ppf(0.975, x.size - 1) * x.std(ddof=1) / np.sqrt(x.size)
    return {"mean": float(m), "lo": float(m - h), "hi": float(m + h), "n": int(x.size)}


def range_hist(events, cause):
    r = np.array([e["range_m"] / 1e3 for e in events if e["cause"] == cause])
    h, _ = np.histogram(r, bins=BINS_KM)
    return {"n": int(r.size), "counts": h.tolist(), "median_km": float(np.median(r)) if r.size else float("nan"),
            "within_15km": int((r < 15).sum())}


def main() -> None:
    docs = {s: json.loads((A / f"{s}.json").read_text()) for s in [EVAL] + OOS}
    rec = lambda s, mo, me: [r["models"][mo]["methods"][me] for r in docs[s]["runs"]]  # noqa: E731
    table = {}
    for mo in MODELS:
        for me in METHODS:
            for s in [EVAL] + OOS:
                table[f"{s}|{mo}|{me}"] = breakdown(rec(s, mo, me))
            table[f"OOS12|{mo}|{me}"] = breakdown([x for s in OOS for x in rec(s, mo, me)])
    # cause of the IMM gain: per seed, OOS 12 summed, IMM - EKF
    imm_gain = {}
    for mo in ("M0", "M4"):
        seeds = [r["seed"] for r in docs[OOS[0]]["runs"]]
        d = {"turn": [], "misses": [], "lost": []}
        for k, sd in enumerate(seeds):
            tot = {me: Counter() for me in METHODS}
            for s in OOS:
                run = docs[s]["runs"][k]
                assert run["seed"] == sd
                for me in METHODS:
                    tot[me].update(run["models"][mo]["methods"][me]["causes"])
            d["turn"].append(tot["imm"]["turn"] - tot["ekf"]["turn"])
            d["misses"].append(tot["imm"]["misses"] - tot["ekf"]["misses"])
            d["lost"].append(lost_of(tot["imm"]) - lost_of(tot["ekf"]))
        imm_gain[mo] = {k: tci(v) for k, v in d.items()}
    # where turn / misses losses happen (all 13 scenarios and OOS 12), EKF
    ranges = {}
    for mo in ("M1", "M2", "M4"):
        for scope, ss in (("all13", [EVAL] + OOS), ("OOS12", OOS)):
            ev = [e for s in ss for x in rec(s, mo, "ekf") for e in x["lost_events"]]
            ranges[f"{scope}|{mo}"] = {c: range_hist(ev, c) for c in ("turn", "misses")}
        ranges[f"by_scenario|{mo}"] = {s: range_hist([e for x in rec(s, mo, "ekf") for e in x["lost_events"]], "misses")
                                       for s in [EVAL] + OOS}
    out = {"definitions": __doc__.split("Definitions")[1].split("Output")[0].strip(), "oos": OOS, "table": table,
           "imm_minus_ekf_oos12_per_seed": imm_gain, "range_bins_km": BINS_KM, "ranges_ekf": ranges}
    (OUT / "c2_breakdown.json").write_text(json.dumps(out, indent=1))
    write_md(out)


def pct(x):
    return f"{100 * x:.1f}%" if x == x else "–"


def write_md(out):
    L = ["# C2 구간별 분해, IMM 효과의 원인, 잃음 위치 (사후 분석)", "",
         "`scripts/stage3_c2_breakdown.py`가 `results/stage3/a/*.json`만 읽어 만든 파일. 판정 대상 아님.", "",
         "정의: 잃음 = causes − truth_gap − near_other. turn 비율 = turn / 잃음. 기저율 = Σ window_turn / Σ assigned_target_scans. "
         "상위 두 대를 뺀 비율 = 구간에서 turn 잃음이 가장 많은 두 항공기의 잃음 사건(원인 무관)을 모두 뺀 turn 비율"
         "(민감도 지표, 보정값 아님). seed 20개 합.", ""]
    for me in METHODS:
        L += [f"## {me.upper()}", "",
              "| 구간 | 모형 | 잃음 | turn | misses | 기타 | turn 비율 | 기저율 | 비율/기저율 | 상위 2대 뺀 turn 비율 | turn 잃음 항공기 수 |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for s in [EVAL] + out["oos"] + ["OOS12"]:
            for mo in MODELS:
                b = out["table"][f"{s}|{mo}|{me}"]
                name = "**표본 밖 12 합산**" if s == "OOS12" else s
                L.append(f"| {name} | {mo} | {b['lost']} | {b['turn']} | {b['misses']} | {b['other']} | {pct(b['turn_share'])} | "
                         f"{pct(b['base_rate'])} | {b['share_over_base']:.2f} | {pct(b['turn_share_wo_top2'])} "
                         f"({b['turn_wo_top2']}/{b['lost_wo_top2']}) | {b['n_aircraft_turn']} |")
        L.append("")
    L += ["## IMM 효과의 원인 (seed별 표본 밖 12구간 합, IMM − EKF, 95% t-구간, n = 20)", "",
          "| 모형 | turn 잃음 | misses 잃음 | 전체 잃음 |", "|---|---:|---:|---:|"]
    f = lambda c: f"{c['mean']:+.1f} [{c['lo']:+.1f}, {c['hi']:+.1f}]"  # noqa: E731
    for mo, g in out["imm_minus_ekf_oos12_per_seed"].items():
        L.append(f"| {mo} | {f(g['turn'])} | {f(g['misses'])} | {f(g['lost'])} |")
    bins = out["range_bins_km"]
    hdr = " | ".join(f"{a}–{b}" for a, b in zip(bins[:-1], bins[1:]))
    L += ["", "## 원인별 잃음 위치 (EKF, 레이더 거리 km, 구간 13개 합)", "", f"| 모형 | 원인 | n | 중앙값 (km) | {hdr} |",
          "|---|---|---:|---:|" + "---:|" * (len(bins) - 1)]
    for mo in ("M1", "M2", "M4"):
        for c in ("turn", "misses"):
            h = out["ranges_ekf"][f"all13|{mo}"][c]
            L.append(f"| {mo} | {c} | {h['n']} | {h['median_km']:.1f} | " + " | ".join(map(str, h["counts"])) + " |")
    L += ["", "## misses 잃음 중 15 km 안 (EKF, 구간별)", "", "| 구간 | M1 | M2 | M4 |", "|---|---:|---:|---:|"]
    for s in [EVAL] + out["oos"]:
        L.append(f"| {s} | " + " | ".join(f"{out['ranges_ekf'][f'by_scenario|{mo}'][s]['within_15km']}/"
                                          f"{out['ranges_ekf'][f'by_scenario|{mo}'][s]['n']}" for mo in ("M1", "M2", "M4")) + " |")
    (OUT / "c2_breakdown.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
