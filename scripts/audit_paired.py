"""Paired-by-seed effects from the existing result files (light: reads CSV/JSON only).

    .venv/bin/python scripts/audit_paired.py

Inputs  results/data/sweep_runs.csv (stage 1 sweep, EKF and NN baseline)
        results/data/stage2/runs/<scenario>__<method>.json (stage 2: NN, EKF, IMM)
Outputs results/audit/paired_effects.csv   one row per condition x comparison x metric
        results/audit/paired_effects.md    readable tables + the reference check

Difference d_s = method value - reference value for the same condition and seed;
mean and 95% t-interval over seeds. Percent reduction = 100 * (mean(reference) -
mean(method)) / mean(reference). The interval describes simulation variability
(detection noise, misses, clutter) on ONE fixed traffic window, not other days or airports.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.audit import paired_diff, percent_reduction  # noqa: E402

OUT = ROOT / "results/audit"
METRICS = [("rmse_m", "scan-end RMSE [m]"), ("rmse_at_update_m", "update-time RMSE [m]"), ("id_switches", "ID switches"),
           ("fragmentations", "track breaks"), ("gospa_mean_m", "GOSPA [m]"), ("gospa_loc_m", "GOSPA localisation [m]"),
           ("gospa_missed_m", "GOSPA missed [m]"), ("gospa_false_m", "GOSPA false [m]"),
           ("missed_per_scan", "missed targets / scan"), ("false_tracks_per_scan", "false tracks / scan")]
REFERENCE = {"rmse_m": (-353.41, -355.13, -351.70), "rmse_at_update_m": (-47.02, -47.56, -46.49),
             "id_switches": (-434.25, -442.45, -426.05)}  # given by the user: default condition, EKF - NN, 20 seeds


def compare(rows_m: dict, rows_r: dict, label: dict, comparison: str, out: list, errors: list):
    """rows_*: seed -> metric dict. Appends one output row per metric."""
    if set(rows_m) != set(rows_r):
        errors.append({**label, "comparison": comparison, "error": "seed sets differ",
                       "only_method": sorted(set(rows_m) - set(rows_r)), "only_reference": sorted(set(rows_r) - set(rows_m))})
        return
    seeds = sorted(rows_m)
    for key, name in METRICS:
        x = np.array([rows_m[s][key] for s in seeds], dtype=float)
        y = np.array([rows_r[s][key] for s in seeds], dtype=float)
        d = paired_diff(x, y)
        out.append({**label, "comparison": comparison, "metric": key, "metric_name": name, "n_seeds": d["n"],
                    "mean_method": float(np.nanmean(x)), "mean_reference": float(np.nanmean(y)),
                    "paired_diff": d["mean"], "ci_lo": d["lo"], "ci_hi": d["hi"],
                    "percent_reduction": percent_reduction(y, x)})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    out, errors = [], []
    # ---- stage 1 sweep
    sweep = defaultdict(lambda: defaultdict(dict))
    with open(ROOT / "results/data/sweep_runs.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            cond = (float(r["pd"]), float(r["clutter_lambda"]), float(r["sigma_az_deg"]))
            sweep[cond][r["method"]][int(r["seed"])] = {k: float(r[k]) for k, _ in METRICS}
    for cond in sorted(sweep):
        label = {"source": "stage1_sweep", "scenario": "EHAM 2026-11-06 12:45", "pd": cond[0], "clutter_lambda": cond[1],
                 "sigma_az_deg": cond[2]}
        compare(sweep[cond]["ekf"], sweep[cond]["nn"], label, "EKF - NN", out, errors)
    # ---- stage 2 scenarios (default radar condition)
    runs = defaultdict(dict)
    for p in sorted((ROOT / "results/data/stage2/runs").glob("*.json")):
        parts = p.stem.split("__")
        if len(parts) != 2:
            continue  # tagged variants (dense clutter, pre-gate check) are not part of this table
        doc = json.loads(p.read_text())
        runs[parts[0]][parts[1]] = (doc["meta"], {r["seed"]: r["summary"] for r in doc["runs"]})
    for sid in sorted(runs):
        meta = next(iter(runs[sid].values()))[0]
        spec = meta["spec"]
        label = {"source": "stage2", "scenario": f"{spec['site']} {spec['day']} {spec['start_utc'][11:16]}",
                 "pd": meta["radar"]["pd"], "clutter_lambda": meta["radar"]["clutter_lambda"],
                 "sigma_az_deg": meta["radar"]["sigma_az_deg"], "truth_per_scan": meta["truth_per_scan_mean"]}
        if {"ekf", "nn"} <= set(runs[sid]):
            compare(runs[sid]["ekf"][1], runs[sid]["nn"][1], label, "EKF - NN", out, errors)
        if {"imm", "ekf"} <= set(runs[sid]):
            compare(runs[sid]["imm"][1], runs[sid]["ekf"][1], label, "IMM - EKF", out, errors)
        if {"imm", "nn"} <= set(runs[sid]):
            compare(runs[sid]["imm"][1], runs[sid]["nn"][1], label, "IMM - NN", out, errors)

    cols = ["source", "scenario", "pd", "clutter_lambda", "sigma_az_deg", "truth_per_scan", "comparison", "metric",
            "metric_name", "n_seeds", "mean_method", "mean_reference", "paired_diff", "ci_lo", "ci_hi", "percent_reduction"]
    with open(OUT / "paired_effects.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in out:
            w.writerow({k: (f"{r[k]:.6g}" if isinstance(r.get(k), float) else r.get(k, "")) for k in cols})

    # ---- reference check (default condition of the stage 1 sweep)
    ref_rows = {r["metric"]: r for r in out if r["source"] == "stage1_sweep" and r["comparison"] == "EKF - NN"
                and (r["pd"], r["clutter_lambda"], r["sigma_az_deg"]) == (0.9, 5.0, 0.15)}
    check = []
    for key, (m, lo, hi) in REFERENCE.items():
        r = ref_rows[key]
        got = (round(r["paired_diff"], 2), round(r["ci_lo"], 2), round(r["ci_hi"], 2))
        check.append({"metric": key, "reference": [m, lo, hi], "computed": list(got), "match": got == (m, lo, hi)})
    (OUT / "paired_reference_check.json").write_text(json.dumps({"check": check, "errors": errors}, indent=1))

    f = lambda r, nd: f"{r['paired_diff']:+,.{nd}f} [{r['ci_lo']:+,.{nd}f}, {r['ci_hi']:+,.{nd}f}]"  # noqa: E731
    L = ["# Paired effects (generated by `scripts/audit_paired.py`)", "",
         "Difference = method − reference for the same condition and seed; mean [95% t-interval over seeds]. "
         "Percent reduction = 100 × (mean(reference) − mean(method)) / mean(reference); the denominator is the "
         "reference method's mean over seeds.", "",
         "**Scope of the intervals.** The truth trajectories are fixed and only detection noise, misses and clutter change "
         "with the seed. Each interval therefore describes simulation variability on one fixed traffic window. It says "
         "nothing about other days or airports; for that see the separate rows per scenario.", "",
         "## Reference check (default condition Pd 0.9, λ 5, σθ 0.15°, EKF − NN, 20 seeds)", "",
         "| metric | reference given | computed | match at 0.01 |", "|---|---|---|---|"]
    for c in check:
        L.append(f"| {c['metric']} | {c['reference'][0]} ({c['reference'][1]} to {c['reference'][2]}) | "
                 f"{c['computed'][0]} ({c['computed'][1]} to {c['computed'][2]}) | {'yes' if c['match'] else 'NO'} |")
    L += ["", f"Seed-set errors: {len(errors)}.", "", "## Stage 1 sweep: EKF − NN baseline (Schiphol 2026-11-06 12:45–13:15 UTC, 20 seeds each)", "",
          "| Pd | λ | σθ | scan-end RMSE [m] | % | update-time RMSE [m] | % | ID switches | % | GOSPA [m] | GOSPA loc. [m] | GOSPA missed [m] | GOSPA false [m] |",
          "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    by = defaultdict(dict)
    for r in out:
        by[(r["source"], r["scenario"], r["pd"], r["clutter_lambda"], r["sigma_az_deg"], r["comparison"])][r["metric"]] = r
    for (src, scen, pd, lam, saz, cmp_), m in by.items():
        if src == "stage1_sweep":
            L.append(f"| {pd} | {lam:.0f} | {saz:.2f}° | {f(m['rmse_m'], 1)} | {m['rmse_m']['percent_reduction']:.1f} | "
                     f"{f(m['rmse_at_update_m'], 1)} | {m['rmse_at_update_m']['percent_reduction']:.1f} | "
                     f"{f(m['id_switches'], 1)} | {m['id_switches']['percent_reduction']:.1f} | {f(m['gospa_mean_m'], 0)} | "
                     f"{f(m['gospa_loc_m'], 0)} | {f(m['gospa_missed_m'], 0)} | {f(m['gospa_false_m'], 0)} |")
    for cmp_ in ("EKF - NN", "IMM - EKF", "IMM - NN"):
        L += ["", f"## Stage 2 scenarios, default condition: {cmp_.replace(' - ', ' − ')} (20 seeds each)", "",
              "| scenario (UTC) | aircraft / scan | scan-end RMSE [m] | % | update-time RMSE [m] | % | ID switches | % | track breaks | missed / scan | false / scan | GOSPA [m] |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for (src, scen, pd, lam, saz, c2), m in by.items():
            if src == "stage2" and c2 == cmp_:
                tps = m["rmse_m"].get("truth_per_scan", float("nan"))
                L.append(f"| {scen} | {tps:.1f} | {f(m['rmse_m'], 1)} | {m['rmse_m']['percent_reduction']:.1f} | "
                         f"{f(m['rmse_at_update_m'], 1)} | {m['rmse_at_update_m']['percent_reduction']:.1f} | "
                         f"{f(m['id_switches'], 1)} | {m['id_switches']['percent_reduction']:.1f} | {f(m['fragmentations'], 1)} | "
                         f"{f(m['missed_per_scan'], 2)} | {f(m['false_tracks_per_scan'], 2)} | {f(m['gospa_mean_m'], 0)} |")
    L += ["", "All rows and metrics: `results/audit/paired_effects.csv`.", ""]
    (OUT / "paired_effects.md").write_text("\n".join(L))
    for c in check:
        print(c)
    print("rows", len(out), "seed-set errors", len(errors))


if __name__ == "__main__":
    main()
