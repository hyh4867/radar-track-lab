"""Stone Soup (b) lambda 200: find the first track whose state differs (> 1 cm, all tracks incl. tentative) and
compare that scan's association probabilities on both sides (post-hoc diagnostic).

    .venv/bin/python scripts/stage3_stonesoup_b_firstdiff.py [--seed 20261106] [--fd] [--n-events 5]
Output: results/stage3/stonesoup_b_firstdiff[_fd]_<seed>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import stage3_stonesoup_b as B  # noqa: E402
from scipy.sparse import coo_matrix  # noqa: E402
from scipy.sparse.csgraph import connected_components  # noqa: E402
from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.jpda import count_events  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.sim import make_tracker  # noqa: E402
from radar_track_lab.tracker import TrackerParams  # noqa: E402


def build(lam, analytic):
    cfg0, _ = load_stage3([f"radar.clutter_lambda={lam}"], True, "M0")
    cfg0["jipda"] = {}
    sc, _, cfg = S.build(cfg0, S.specs()["EHAM_1106_eval"])
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    ours = make_tracker("jpda", p, cfg)
    ssd = B.SSDriven(p, ours.pda, radar)
    tm = B.CombinedLinearGaussianTransitionModel([B.ConstantVelocity(p.q / B.TS**3), B.ConstantVelocity(p.q / B.TS**3)])
    MM = B.AnalyticBearingRange if analytic else B.CartesianToBearingRange
    mm = MM(ndim_state=4, mapping=(0, 2), noise_covar=np.diag([p.sigma_az_rad**2, p.sigma_r_m**2]),
            translation_offset=B.StateVector([[B.OFF], [B.OFF]]))
    rho = float(radar.clutter_density(np.array([50_000.0]), np.array([0.0]))[0])
    hyp = B.PDAHypothesiser(B.ExtendedKalmanPredictor(tm), B.PDAUpdater(mm), clutter_spatial_density=rho,
                            prob_detect=ours.pda.pd, prob_gate=p.gate_probability)
    ssd.setup({"mm": mm, "hyp": hyp, "upd": B.PDAUpdater(mm)}, sc.t_start)
    ours.keep_last = ssd.keep_last = True
    return sc, radar, ours, ssd


def cluster_of(a, n, M, i):
    gi, dj = a["gi"], a["dj"]
    g = coo_matrix((np.ones(gi.size), (gi, n + dj)), shape=(n + M, n + M))
    _, lab = connected_components(g, directed=False)
    ks = np.flatnonzero(lab[gi] == lab[i])
    return ks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--fd", action="store_true", help="Stone Soup default finite-difference Jacobian")
    ap.add_argument("--n-events", type=int, default=5)
    a_ = ap.parse_args()
    sc, radar, ours, ssd = build(200, not a_.fd)
    scans = simulate_scans(sc.scan_truths, radar, a_.seed)
    events = []
    for k, scan in enumerate(scans):
        ours.process_scan(scan, sc.eval_truths[k].t)
        ssd.process_scan(scan, sc.eval_truths[k].t)
        if not np.array_equal(ours.ids, ssd.ids):
            events.append({"k": k, "kind": "track list differs",
                           "only_ours": np.setdiff1d(ours.ids, ssd.ids).tolist(),
                           "only_ss": np.setdiff1d(ssd.ids, ours.ids).tolist()})
            break
        d = np.hypot(*(ours.X[:, :2] - ssd.X[:, :2]).T)
        bad = np.flatnonzero(d > 0.01)
        if not bad.size:
            continue
        Lo, Ls = ours.last, ssd.last
        ao, as_ = Lo["assoc"], Ls["assoc"]
        n, M = Lo["ids"].size, scan.t.size
        prior_d = np.hypot(*(Lo["prior_X"][:, :2] - Ls["prior_X"][:, :2]).T)
        for tid in ours.ids[bad][: a_.n_events]:
            i = int(np.flatnonzero(Lo["ids"] == tid)[0]) if tid in Lo["ids"] else None
            if i is None:
                continue
            ks = cluster_of(ao, n, M, i)
            tr = np.unique(ao["gi"][ks])
            de = np.unique(ao["dj"][ks])
            Wc = np.zeros((tr.size, de.size))
            Wc[np.searchsorted(tr, ao["gi"][ks]), np.searchsorted(de, ao["dj"][ks])] = 1.0
            exact = tr.size == 1 or (tr.size <= ours.pda.exact_max_tracks and
                                     count_events(Wc, ours.pda.exact_max_events) <= ours.pda.exact_max_events)
            mine = ks[ao["gi"][ks] == i]
            pairs = [{"j": int(ao["dj"][k]), "d2": float(ao["d2"][k]), "beta_ours": float(ao["beta"][k]),
                      "beta_ss": float(as_["beta"][k])} for k in mine]
            db = np.abs(ao["beta"][ks] - as_["beta"][ks])
            events.append({"k": k, "track_id": int(tid), "pos_diff_m": float(d[ours.ids == tid][0]),
                           "prior_diff_m": float(prior_d[i]), "cluster_tracks": int(tr.size), "cluster_pairs": int(ks.size),
                           "solver": "exact/single" if exact else "LBP",
                           "beta0_ours": float(ao["beta0"][i]), "beta0_ss": float(as_["beta0"][i]),
                           "max_dbeta_cluster": float(db.max()),
                           "ss_zero_ours_pos": int(((as_["beta"][ks] == 0) & (ao["beta"][ks] > 1e-12)).sum()),
                           "pairs_of_track": pairs})
        break
    out = {"seed": a_.seed, "analytic_jacobian": not a_.fd, "events": events}
    path = ROOT / f"results/stage3/stonesoup_b_firstdiff{'_fd' if a_.fd else ''}_{a_.seed}.json"
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:6000])


if __name__ == "__main__":
    main()
