"""Independent recomputation of the stage 3 headline numbers from the run files (PREREGISTRATION_3 2).

Uses only json, numpy and scipy (no radar_track_lab import, no report script) and compares with
results/stage3/{a,b,b0}_summary.json to two decimals. Output: results/stage3/recompute.json and a table.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

R = Path(__file__).resolve().parents[1] / "results/stage3"
EVAL = "EHAM_1106_eval"


def tci(x):
    x = np.asarray(x, float)
    m = x.mean()
    h = stats.t.ppf(0.975, x.size - 1) * x.std(ddof=1) / np.sqrt(x.size)
    return m, m - h, m + h


def main() -> None:
    rows = []

    def add(name, mine, theirs):
        rows.append({"name": name, "recomputed": float(mine), "summary": float(theirs) if theirs is not None else None,
                     "match": theirs is not None and round(float(mine), 2) == round(float(theirs), 2)})

    a_sum = json.loads((R / "a_summary.json").read_text()) if (R / "a_summary.json").exists() else None
    if a_sum and (R / "a" / f"{EVAL}.json").exists():
        d = json.loads((R / "a" / f"{EVAL}.json").read_text())
        for mo in ("M0", "M4"):
            e = np.array([r["models"][mo]["methods"]["ekf"]["summary"]["id_switches"] for r in d["runs"]], float)
            i = np.array([r["models"][mo]["methods"]["imm"]["summary"]["id_switches"] for r in d["runs"]], float)
            s = a_sum["scenarios"][EVAL]["models"][mo]
            add(f"A {mo} Schiphol EKF ID switch", e.mean(), s["c1"]["ekf_idsw"]["mean"])
            m, lo, hi = tci(i - e)
            add(f"A {mo} Schiphol IMM-EKF ID switch", m, s["c1"]["imm_minus_ekf_idsw"]["mean"])
            add(f"A {mo} Schiphol IMM-EKF upper 95%", hi, s["c1"]["imm_minus_ekf_idsw"]["hi"])
            turn = sum(1 for r in d["runs"] for ev in r["models"][mo]["methods"]["ekf"]["lost_events"] if ev["cause"] == "turn")
            lost = sum(len(r["models"][mo]["methods"]["ekf"]["lost_events"]) for r in d["runs"])
            add(f"A {mo} Schiphol EKF turn share (%)", 100 * turn / lost if lost else float("nan"), 100 * s["c2"]["turn_share"])
            g = {k: np.array([r["models"][mo]["four"]["rmse_common"][k] for r in d["runs"]]) for k in ("nn", "nnp", "ekfh", "ekf")}
            tot = (g["ekf"] - g["nn"]).mean()
            add(f"A {mo} Schiphol s_A (%)", 100 * (g["nnp"] - g["nn"]).mean() / tot, 100 * s["c3"]["s_A"])
            add(f"A {mo} Schiphol s_B (%)", 100 * (g["ekf"] - g["ekfh"]).mean() / tot, 100 * s["c3"]["s_B"])
        n_hold = 0
        for s_ in a_sum["valid_oos"]:
            dd = json.loads((R / "a" / f"{s_}.json").read_text())
            e = np.array([r["models"]["M4"]["methods"]["ekf"]["summary"]["id_switches"] for r in dd["runs"]], float)
            i = np.array([r["models"]["M4"]["methods"]["imm"]["summary"]["id_switches"] for r in dd["runs"]], float)
            re = np.array([r["models"]["M4"]["methods"]["ekf"]["summary"]["rmse_m"] for r in dd["runs"]], float)
            ri = np.array([r["models"]["M4"]["methods"]["imm"]["summary"]["rmse_m"] for r in dd["runs"]], float)
            n_hold += int(tci(i - e)[2] < 0 and (ri / re).mean() <= 1.05)
        add("A M4 OOS scenarios where the IMM gain holds", n_hold, a_sum["verdicts"]["M4"]["C1"]["n_oos_imm_holds"])
    b_sum = json.loads((R / "b_summary.json").read_text()) if (R / "b_summary.json").exists() else None
    if b_sum:
        for tag in ("lam1000_uniform", "lam1000_map", "lam5_uniform"):
            pg, pj = R / "b1" / f"{EVAL}__ekf__{tag}.json", R / "b1" / f"{EVAL}__jipda__{tag}.json"
            if not (pg.exists() and pj.exists()):
                continue
            g = {r["seed"]: r["summary"] for r in json.loads(pg.read_text())["runs"]}
            j = {r["seed"]: r["summary"] for r in json.loads(pj.read_text())["runs"]}
            ss = sorted(set(g) & set(j))
            for f in ("false_tracks_per_scan", "gospa_mean_m"):
                m, lo, hi = tci([j[s][f] - g[s][f] for s in ss])
                ref = b_sum["conditions"][tag]["paired_vs_gnn"]["jipda"][f]
                add(f"B {tag} JIPDA-GNN {f}", m, ref["mean"])
                add(f"B {tag} JIPDA-GNN {f} upper 95%", hi, ref["hi"])
    b0 = json.loads((R / "b0_summary.json").read_text()) if (R / "b0_summary.json").exists() else None
    if b0:
        for tag in ("lam5", "lam1000"):
            pf, pa = R / "b0" / f"{EVAL}__ekf__{tag}_fixed.json", R / "b0" / f"{EVAL}__ekf__{tag}_adaptive.json"
            if pf.exists() and pa.exists():
                f_ = {r["seed"]: r["summary"] for r in json.loads(pf.read_text())["runs"]}
                a_ = {r["seed"]: r["summary"] for r in json.loads(pa.read_text())["runs"]}
                ss = sorted(set(f_) & set(a_))
                for f in ("id_switches", "false_tracks_per_scan"):
                    add(f"B0 {tag} EKF adaptive-fixed {f}", tci([a_[s][f] - f_[s][f] for s in ss])[0], b0["eval"][f"{tag}_ekf"][f]["mean"])
    out = {"rows": rows, "all_match": all(r["match"] for r in rows), "n": len(rows)}
    (R / "recompute.json").write_text(json.dumps(out, indent=1))
    print("| 수치 | 다시 계산 | 요약 파일 | 일치 |\n|---|---:|---:|---|")
    for r in rows:
        print(f"| {r['name']} | {r['recomputed']:.2f} | {r['summary'] if r['summary'] is None else round(r['summary'], 2)} | {r['match']} |")
    print("all match:", out["all_match"], f"({out['n']} numbers)")


if __name__ == "__main__":
    main()
