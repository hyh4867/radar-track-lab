"""Aggregate the stage 2 runs and apply the preregistered verdict rules.

Reads results/data/stage2/runs/*.json, writes results/data/stage2/summary.json
and results/data/stage2/lost_tracks_ekf_eval.csv (one row per lost track, Q1).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.diagnose import CAUSES, LOST  # noqa: E402
from radar_track_lab.metrics import mean_ci  # noqa: E402

D = ROOT / "results/data/stage2"
EVAL = "EHAM_1106_eval"
SUMMARY_KEYS = ("rmse_m", "rmse_at_update_m", "id_switches", "fragmentations", "missed_per_scan",
                "false_tracks_per_scan", "gospa_mean_m", "gospa_loc_m", "gospa_missed_m", "gospa_false_m",
                "init_delay_mean_s", "truth_per_scan")


def per_seed(doc):
    """seed -> flat metric dict."""
    out = {}
    for r in doc["runs"]:
        m = {k: r["summary"][k] for k in SUMMARY_KEYS}
        m.update({f"cause_{c}": r["causes"][c] for c in CAUSES})
        m["lost_present"] = r["lost_present"]
        m["rmse_straight_m"] = np.sqrt(r["sq_straight"] / r["n_straight"]) if r["n_straight"] else np.nan
        m["rmse_turn_m"] = np.sqrt(r["sq_turn"] / r["n_turn"]) if r["n_turn"] else np.nan
        m["wall_s"] = r["wall_s"]
        if "nees" in r:
            m["nees_mean4"] = r["nees"]["mean4"]
            m["nees_median4"] = r["nees"]["median4"]
            m["nees_le_chi2_95"] = r["nees"]["le_chi2_95"]
        out[r["seed"]] = m
    return out


def stat(vals):
    m, h = mean_ci(np.asarray(vals, dtype=float))
    return {"mean": m, "ci95": h}


def paired(a, b, key, ratio=False):
    """Mean and 95% t-interval of a - b (or a / b) over the common seeds."""
    seeds = sorted(set(a) & set(b))
    x = np.array([a[s][key] for s in seeds], dtype=float)
    y = np.array([b[s][key] for s in seeds], dtype=float)
    d = x / y if ratio else x - y
    d = d[np.isfinite(d)]
    m, h = mean_ci(d)
    return {"mean": m, "ci95": h, "lo": m - h, "hi": m + h, "n": int(d.size)}


def main() -> None:
    runs = {}
    for p in sorted((D / "runs").glob("*.json")):
        parts = p.stem.split("__")
        if len(parts) == 2:
            runs.setdefault(parts[0], {})[parts[1]] = json.loads(p.read_text())
    out = {"scenarios": {}}
    for sid, by in runs.items():
        meta = by[next(iter(by))]["meta"]
        ps = {m: per_seed(doc) for m, doc in by.items()}
        keys = sorted({k for m in ps for s in ps[m] for k in ps[m][s]})
        entry = {
            "spec": meta["spec"], "targets": meta["targets"], "truth_per_scan": meta["truth_per_scan_mean"],
            "turn_share": meta["turn_share_of_target_scans"],
            "segments_per_aircraft": meta["segments"] / max(meta["aircraft_with_segments"], 1),
            "valid": bool(meta["truth_per_scan_mean"] >= 5.0),
            "methods": {m: {k: stat([ps[m][s].get(k, np.nan) for s in ps[m]]) for k in keys} for m in ps},
        }
        if "ekf" in ps and "nn" in ps:
            e = {k: paired(ps["ekf"], ps["nn"], k) for k in ("rmse_m", "id_switches")}
            e["rmse_ratio_nn_over_ekf"] = paired(ps["nn"], ps["ekf"], "rmse_m", ratio=True)
            e["holds"] = bool(e["rmse_m"]["hi"] < 0 and e["id_switches"]["hi"] < 0)
            entry["ekf_vs_nn"] = e
        if "ekf" in ps and "imm" in ps:
            i = {k: paired(ps["imm"], ps["ekf"], k) for k in
                 ("id_switches", "lost_present", "fragmentations", "missed_per_scan", "false_tracks_per_scan",
                  "gospa_mean_m", "rmse_m", "cause_truth_gap", "cause_near_other", "cause_turn")}
            i["rmse_ratio"] = paired(ps["imm"], ps["ekf"], "rmse_m", ratio=True)
            i["rmse_straight_ratio"] = paired(ps["imm"], ps["ekf"], "rmse_straight_m", ratio=True)
            i["rmse_turn_ratio"] = paired(ps["imm"], ps["ekf"], "rmse_turn_m", ratio=True)
            i["wall_ratio"] = paired(ps["imm"], ps["ekf"], "wall_s", ratio=True)
            i["holds"] = bool(i["id_switches"]["hi"] < 0 and i["rmse_ratio"]["mean"] <= 1.05)
            entry["imm_vs_ekf"] = i
        out["scenarios"][sid] = entry

    # Q1: lost tracks of the stage 1 EKF on the evaluation window
    ekf = runs[EVAL]["ekf"]
    ev = [e for e in ekf["events"] if e["cause"] in LOST]
    n_runs = len(ekf["runs"])
    base = {k: sum(r["base"][k] for r in ekf["runs"]) for k in ("assigned_target_scans", "window_turn", "scan_turn")}
    share = sum(e["cause"] == "turn" for e in ev) / len(ev)
    base_rate = base["window_turn"] / base["assigned_target_scans"]
    per_target = Counter(e["target"] for e in ev)
    top2 = sum(c for _, c in per_target.most_common(2))
    spd = np.array([e["speed_mps"] for e in ev])
    trn = np.array([e["max_turn_dps"] for e in ev])
    rest = [e for e in ev if e["target"] not in {t for t, _ in per_target.most_common(2)}]
    out["q1"] = {
        "runs": n_runs, "lost_events": len(ev), "lost_per_run": len(ev) / n_runs,
        "by_cause": {c: sum(e["cause"] == c for e in ev) for c in LOST},
        "turn_share": share, "base_rate_window_turn": base_rate, "enrichment": share / base_rate,
        "turn_and_two_or_more_misses": sum(e["turn_and_misses"] for e in ev),
        "with_at_least_one_miss": sum(e["misses_in_window"] >= 1 for e in ev),
        "max_turn_dps_percentiles_10_50_90": np.percentile(trn, [10, 50, 90]).tolist(),
        "speed_mps_percentiles_10_50_90": np.percentile(spd, [10, 50, 90]).tolist(),
        "range_km_percentiles_10_50_90": (np.percentile([e["range_m"] for e in ev], [10, 50, 90]) / 1000).tolist(),
        "distinct_targets": len(per_target), "events_from_two_most_frequent_targets": top2,
        "share_from_two_most_frequent_targets": top2 / len(ev),
        "two_most_frequent": [{"events": c,
                               "median_speed_mps": float(np.median([e["speed_mps"] for e in ev if e["target"] == t])),
                               "median_max_turn_dps": float(np.median([e["max_turn_dps"] for e in ev if e["target"] == t]))}
                              for t, c in per_target.most_common(2)],
        "other_targets": {"events": len(rest), "per_run": len(rest) / n_runs,
                          "turn_share": sum(e["cause"] == "turn" for e in rest) / max(len(rest), 1),
                          "median_speed_mps": float(np.median([e["speed_mps"] for e in rest])) if rest else None,
                          "median_max_turn_dps": float(np.median([e["max_turn_dps"] for e in rest])) if rest else None},
        "verdict": ("turn is the main cause" if share >= 0.5 and share >= 2 * base_rate
                    else "turn is not the main cause" if share < 0.3 else "partly"),
    }
    with open(D / "lost_tracks_ekf_eval.csv", "w", newline="") as fh:
        cols = ["seed", "target", "k_last", "k_new", "scans_unassigned", "cause", "max_turn_dps", "misses_in_window",
                "nearest_other_m", "range_m", "speed_mps", "max_speed_rate", "turn_and_misses"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for e in sorted(ev, key=lambda e: (e["seed"], e["k_last"])):
            w.writerow({k: (round(e[k], 2) if isinstance(e[k], float) else e[k]) for k in cols})

    # Q2 verdicts on the evaluation window
    iv = out["scenarios"][EVAL]["imm_vs_ekf"]
    lp = iv["lost_present"]
    out["q2"] = {
        "lost_present_diff": lp,
        "verdict_lost": "reduces" if lp["hi"] < 0 else "increases" if lp["lo"] > 0 else "no difference shown",
        "straight_ratio": iv["rmse_straight_ratio"],
        "verdict_straight": "does not harm straight-segment accuracy" if iv["rmse_straight_ratio"]["hi"] <= 1.02 else "harms straight-segment accuracy",
        "imm_lost_by_cause": {c: out["scenarios"][EVAL]["methods"]["imm"][f"cause_{c}"]["mean"] for c in CAUSES},
        "ekf_lost_by_cause": {c: out["scenarios"][EVAL]["methods"]["ekf"][f"cause_{c}"]["mean"] for c in CAUSES},
    }
    two = {tid for tid, _ in per_target.most_common(2)}
    imm_ev = [e for e in runs[EVAL]["imm"]["events"] if e["cause"] in LOST]
    n_imm = len(runs[EVAL]["imm"]["runs"])
    out["q2"]["lost_split"] = {
        "ekf_two_circling_per_run": top2 / n_runs, "ekf_others_per_run": len(rest) / n_runs,
        "imm_two_circling_per_run": sum(e["target"] in two for e in imm_ev) / n_imm,
        "imm_others_per_run": sum(e["target"] not in two for e in imm_ev) / n_imm,
        "imm_lost_events": len(imm_ev),
        "imm_median_max_turn_dps": float(np.median([e["max_turn_dps"] for e in imm_ev])) if imm_ev else None,
    }
    # Q4 overall
    oos = {s: e for s, e in out["scenarios"].items() if e["spec"]["kind"].startswith("oos")}
    valid = {s: e for s, e in oos.items() if e["valid"]}
    out["q4"] = {
        "scenarios_run": sorted(oos), "valid": sorted(valid), "invalid": sorted(set(oos) - set(valid)),
        "ekf_better_than_nn": sorted(s for s, e in valid.items() if e["ekf_vs_nn"]["holds"]),
        "imm_gain_holds": sorted(s for s, e in valid.items() if e["imm_vs_ekf"]["holds"]),
        "imm_gain_fails": sorted(s for s, e in valid.items() if not e["imm_vs_ekf"]["holds"]),
        "valid_primary_sites_day1": sorted(s for s, e in valid.items() if e["spec"]["kind"] == "oos_site_primary"),
    }
    # sensitivity to the coarse pre-gate radius (found through the Stone Soup comparison): 6 km (frozen) vs 12 km
    pc = {}
    for p in sorted((D / "runs").glob("*__prune12km.json")):
        sid, method, _ = p.stem.split("__")
        wide, base = per_seed(json.loads(p.read_text())), per_seed(runs[sid][method])
        pc.setdefault(sid, {})[method] = {k: paired(wide, base, k) for k in ("id_switches", "lost_present", "rmse_m", "gospa_mean_m")}
        pc[sid][method]["runs_with_any_change"] = int(sum(any(wide[s][k] != base[s][k] for k in ("id_switches", "rmse_m", "gospa_mean_m")) for s in wide))
    out["prune_check"] = pc
    (D / "summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("q1", "q2", "q4")}, indent=1))
    for s, e in out["scenarios"].items():
        if "imm_vs_ekf" in e:
            i = e["imm_vs_ekf"]
            print(f"{s:16s} valid={e['valid']!s:5} truth/scan={e['truth_per_scan']:6.1f} turn={e['turn_share']:.3f} "
                  f"idsw d={i['id_switches']['mean']:+6.1f}±{i['id_switches']['ci95']:.1f} lost d={i['lost_present']['mean']:+6.1f}±{i['lost_present']['ci95']:.1f} "
                  f"rmse ratio={i['rmse_ratio']['mean']:.3f} straight={i['rmse_straight_ratio']['mean']:.3f}±{i['rmse_straight_ratio']['ci95']:.3f} turn={i['rmse_turn_ratio']['mean']:.3f} "
                  f"holds={i['holds']} | nn/ekf rmse={e['ekf_vs_nn']['rmse_ratio_nn_over_ekf']['mean']:.2f} ekf>nn={e['ekf_vs_nn']['holds']}")


if __name__ == "__main__":
    main()
