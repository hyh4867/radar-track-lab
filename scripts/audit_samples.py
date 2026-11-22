"""Sample audit of the two RMSEs: EKF vs NN baseline on common samples (docs/AUDIT_PROTOCOL.md).

    .venv/bin/python scripts/audit_samples.py [--scenarios id1,id2]

Re-runs both methods with ``audit=True`` on the same seeds, checks that the scores equal the
existing stage 2 result files, and writes per-seed sample accounting to
results/audit/samples/<scenario>.json (checkpoint per scenario). Per-sample tables of one seed of
the Schiphol evaluation window are written to results/audit/samples_example/ as an example.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab import audit as A  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import load_stage2, seeds  # noqa: E402
from radar_track_lab.sim import run  # noqa: E402

OUT = ROOT / "results/audit/samples"
EVAL = "EHAM_1106_eval"
AGE_EDGES = [0.0, 1.2, 2.4, 3.6, 4.8, 9.6, np.inf]
KEEP = ("rmse_m", "rmse_at_update_m", "id_switches", "fragmentations", "missed_per_scan", "false_tracks_per_scan",
        "gospa_mean_m", "gospa_loc_m", "gospa_missed_m", "gospa_false_m")


def same(a, b):
    return a == b or (a != a and b != b)


def age_bins(age, sq):
    idx = np.digitize(age, AGE_EDGES[1:-1])
    return [{"n": int((idx == i).sum()), "sq": float(sq[idx == i].sum())} for i in range(len(AGE_EDGES) - 1)]


def write_example(sid, seed, method, aud):
    d = ROOT / "results/audit/samples_example"
    d.mkdir(parents=True, exist_ok=True)
    for name, fields, reasons in (("update", A.UPD_FIELDS, A.UPD_REASON), ("scan_end", A.SE_FIELDS, A.SE_REASON)):
        t = aud[name]
        with gzip.open(d / f"{sid}_seed{seed}_{method}_{name}.csv.gz", "wt", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([f if f != "truth" else "anonymous_truth_id" for f in fields] + ["reason_name"])
            for i in range(t["k"].size):
                w.writerow([(f"{t[f][i]:.3f}" if t[f].dtype.kind == "f" else int(t[f][i])) for f in fields]
                           + [reasons[int(t["reason"][i])]])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="")
    args = ap.parse_args()
    cfg0, _ = load_stage2()
    specs = S.specs()
    ids = args.scenarios.split(",") if args.scenarios else [k for k, v in specs.items() if v["kind"] != "tune"]
    OUT.mkdir(parents=True, exist_ok=True)
    for sid in ids:
        path = OUT / f"{sid}.json"
        if path.exists():
            continue
        if not (ROOT / f"results/data/stage2/runs/{sid}__ekf.json").exists():
            print(sid, "skipped: not run in stage 2 (reserve airport)", flush=True)
            continue
        sc, _, cfg = S.build(cfg0, specs[sid])
        warm = sc.t_start + float(cfg["eval"]["warmup_s"])
        ref = {m: {r["seed"]: r["summary"] for r in json.loads((ROOT / f"results/data/stage2/runs/{sid}__{m}.json").read_text())["runs"]}
               for m in ("ekf", "nn")}
        rows = []
        for seed in seeds(cfg):
            res = {m: run(sc, cfg, seed=seed, method=m, record=True, audit=True) for m in ("ekf", "nn")}
            for m in res:  # stop condition of the protocol: recording must not change the scores
                bad = [k for k, v in ref[m][seed].items() if not same(v, res[m].summary[k])]
                if bad:
                    raise SystemExit(f"{sid} {m} seed {seed}: scores differ from the stage 2 file: {bad}")
            e, n = res["ekf"].audit, res["nn"].audit
            scans = res["ekf"].scans
            n_det = sum(int(((s.truth_id >= 0) & (s.t >= warm)).sum()) for s in scans)
            n_illum = sum(int((st.t >= warm).sum()) for st in sc.scan_truths)
            cu, cs = A.common_update(e["update"], n["update"]), A.common_scan_end(e["scan_end"], n["scan_end"])
            row = {"seed": seed, "target_detections_after_warmup": n_det, "target_illuminations_after_warmup": n_illum,
                   "summary": {m: {k: res[m].summary[k] for k in KEEP} for m in res},
                   "update": {"n_ekf": cu["n_a"], "n_nn": cu["n_b"], "n_common": cu["n_common"], "only_ekf": cu["only_a"],
                              "only_nn": cu["only_b"],
                              "reasons": {m: {A.UPD_REASON[int(c)]: int(v) for c, v in
                                              zip(*np.unique(res[m].audit["update"]["reason"], return_counts=True))} for m in res},
                              "rmse_common_ekf": A.rmse(cu["sq_a"]), "rmse_common_nn": A.rmse(cu["sq_b"]),
                              "rmse_only_ekf": A.rmse(cu["sq_only_a"]), "rmse_only_nn": A.rmse(cu["sq_only_b"])},
                   "scan_end": {"n_truth": cs["n_truth"], "n_ekf": cs["n_a"], "n_nn": cs["n_b"], "n_common": cs["n_common"],
                                "only_ekf": cs["only_a"], "only_nn": cs["only_b"], "neither": cs["neither"],
                                "rmse_common_ekf": A.rmse(cs["sq_a"]), "rmse_common_nn": A.rmse(cs["sq_b"]),
                                "rmse_only_ekf": A.rmse(cs["sq_only_a"]), "rmse_only_nn": A.rmse(cs["sq_only_b"]),
                                "by_nn_age": {"ekf": age_bins(cs["age_b"], cs["sq_a"]), "nn": age_bins(cs["age_b"], cs["sq_b"])},
                                "mean_age_ekf": float(cs["age_a"].mean()) if cs["n_common"] else None,
                                "mean_age_nn": float(cs["age_b"].mean()) if cs["n_common"] else None}}
            rows.append(row)
            if sid == EVAL and seed == seeds(cfg)[0]:
                for m in res:
                    write_example(sid, seed, m, res[m].audit)
        path.write_text(json.dumps({"scenario": sid, "spec": specs[sid], "truth_per_scan": sc.meta["truth_per_scan_mean"],
                                    "age_edges_s": [x if np.isfinite(x) else None for x in AGE_EDGES], "runs": rows}))
        mean = lambda f: float(np.mean([f(r) for r in rows]))  # noqa: E731
        print(sid, f"upd common {mean(lambda r: r['update']['n_common']):.0f}/{mean(lambda r: r['update']['n_ekf']):.0f}/{mean(lambda r: r['update']['n_nn']):.0f}",
              f"rmse {mean(lambda r: r['update']['rmse_common_ekf']):.1f} vs {mean(lambda r: r['update']['rmse_common_nn']):.1f} |",
              f"scan-end common {mean(lambda r: r['scan_end']['n_common']):.0f}/{mean(lambda r: r['scan_end']['n_ekf']):.0f}/{mean(lambda r: r['scan_end']['n_nn']):.0f}",
              f"rmse {mean(lambda r: r['scan_end']['rmse_common_ekf']):.1f} vs {mean(lambda r: r['scan_end']['rmse_common_nn']):.1f}", flush=True)


if __name__ == "__main__":
    main()
