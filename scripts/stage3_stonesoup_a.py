"""Stage 3 B1, Stone Soup cross-check (a): one scan at a time (docs/PREREGISTRATION_3.md 4.4).

Our JPDA tracker runs on the Schiphol evaluation window (ideal sensor, uniform clutter lambda 5 / 200 / 1000,
seed 20261106). At chosen scans, for every cluster of tracks sharing gated detections we rebuild the same
problem in Stone Soup 1.9.1 and compare
  * association probabilities beta_ij and beta_i0 (Stone Soup JPDA exact enumeration, PDA for one track),
  * the PDA update (Stone Soup PDAUpdater, innovation form): position, velocity, covariance,
  * loopy-BP marginals (Stone Soup JPDAwithLBP._loopy_belief_propagation) on the same weight matrices.
Stone Soup predicts each track to the timestamp of the detection; we predict each track once to its own
illumination time t_i. To give Stone Soup the same problem, each track gets copies of its cluster's detections
stamped t_i, and joint-event validity is checked on a detection id (subclass of JPDA). Positions are shifted
by +200 km (the stage 2 frame fix for Stone Soup's forward-difference Jacobian).

    .venv/bin/python scripts/stage3_stonesoup_a.py
Output: results/stage3/stonesoup_a.json
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")

from stonesoup.dataassociator.probability import JPDA, JPDAwithLBP  # noqa: E402
from stonesoup.hypothesiser.probability import PDAHypothesiser  # noqa: E402
from stonesoup.models.measurement.nonlinear import CartesianToBearingRange  # noqa: E402
from stonesoup.models.transition.linear import CombinedLinearGaussianTransitionModel, ConstantVelocity  # noqa: E402
from stonesoup.predictor.kalman import ExtendedKalmanPredictor  # noqa: E402
from stonesoup.types.angle import Bearing  # noqa: E402
from stonesoup.types.array import StateVector  # noqa: E402
from stonesoup.types.detection import Detection  # noqa: E402
from stonesoup.types.state import GaussianState  # noqa: E402
from stonesoup.types.track import Track  # noqa: E402
from stonesoup.updater.probability import PDAUpdater  # noqa: E402

from stage3_run import load_stage3  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.jpda import marginals_lbp  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.sim import make_tracker  # noqa: E402
from radar_track_lab.tracker import TrackerParams  # noqa: E402

OUT = ROOT / "results/stage3/stonesoup_a.json"
EPOCH = dt.datetime(2026, 1, 1)
OFF = 200_000.0
PERM = [0, 2, 1, 3]
SEED = 20261106
SCANS = (20, 21, 22)
MAX_CLUSTERS = 150  # per scan; clusters are sampled at random above this


class JPDAByID(JPDA):
    pre: dict = None

    def generate_hypotheses(self, tracks, detections, timestamp, **kwargs):
        return self.pre

    @staticmethod
    def isvalid(joint_hypothesis):
        seen = set()
        for h in joint_hypothesis:
            if h.measurement:
                j = h.measurement.metadata["j"]
                if j in seen:
                    return False
                seen.add(j)
        return True


def ts(t):
    return EPOCH + dt.timedelta(microseconds=int(round(t * 1e6)))


def compare_scan(trk, scan, p, pda, ss, rng):
    """Run our tracker on ``scan`` and compare every (sampled) cluster with Stone Soup."""
    trk.keep_last = True
    t_rel = lambda t: t - scan.t0  # noqa: E731  (relative times keep microsecond rounding small)
    trk.process_scan(scan, scan.t0 + p.rotation)
    L = trk.last
    a = L["assoc"]
    ids, gi, dj = L["ids"], a["gi"], a["dj"]
    n = ids.size
    # clusters
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    M = scan.t.size
    g = coo_matrix((np.ones(gi.size), (gi, n + dj)), shape=(n + M, n + M))
    _, lab = connected_components(g, directed=False)
    comps = {}
    for k in range(gi.size):
        comps.setdefault(lab[gi[k]], []).append(k)
    keys = list(comps)
    if len(keys) > MAX_CLUSTERS:
        keys = list(rng.choice(keys, MAX_CLUSTERS, replace=False))
    res = {"clusters": 0, "multi": 0, "skipped_large": 0, "pairs": 0, "max_dbeta": 0.0, "max_dbeta0": 0.0,
           "max_dpos_m": 0.0, "max_dvel_mps": 0.0, "max_dcov_rel": 0.0, "gate_mismatch": 0, "lbp_max_diff": 0.0}
    for key in keys:
        ks = np.asarray(comps[key])
        tr = np.unique(gi[ks])
        de = np.unique(dj[ks])
        Wc = np.zeros((tr.size, de.size))
        Wc[np.searchsorted(tr, gi[ks]), np.searchsorted(de, dj[ks])] = a["w"][ks]
        if tr.size > 1:
            from radar_track_lab.jpda import count_events

            # same switch rule as the tracker: exact only for <= exact_max_tracks tracks and <= exact_max_events events
            # (the track-count test comes first; enumerating events of a 1000-track cluster is not possible)
            if tr.size > pda.exact_max_tracks or count_events(Wc, pda.exact_max_events) > pda.exact_max_events:
                res["skipped_large"] += 1
                # LBP on the same weights: ours vs Stone Soup's routine (tight tolerance)
                lik = np.hstack([np.ones((tr.size, 1)), Wc / a["w0"][tr][:, None]])
                ssb = JPDAwithLBP._loopy_belief_propagation(lik, 50, 1e-12)
                b0, B, _ = marginals_lbp(a["w0"][tr], Wc)
                res["lbp_max_diff"] = max(res["lbp_max_diff"], float(np.max(np.abs(ssb[:, 1:] - B))),
                                          float(np.max(np.abs(ssb[:, 0] - b0))))
                continue
            res["multi"] += 1
        res["clusters"] += 1
        tracks, pre = {}, {}
        for i in tr:
            x0 = L["prior_X"][i].copy()
            x0[:2] += OFF
            st = GaussianState(StateVector(x0[PERM]), L["prior_P"][i][np.ix_(PERM, PERM)], timestamp=ts(t_rel(L["prior_T"][i])))
            track = Track([st])
            tracks[i] = track
            tstamp = ts(t_rel(a["ti"][i]))
            dets = [Detection(StateVector([[Bearing(np.pi / 2 - scan.az[j])], [scan.r[j]]]), timestamp=tstamp,
                              measurement_model=ss["mm"], metadata={"j": int(j)}) for j in de]
            pre[track] = ss["hyp"].hypothesise(track, dets, tstamp)
        assoc = JPDAByID(ss["hyp"])
        assoc.pre = pre
        out = assoc.associate(set(pre), None, ts(t_rel(a["ti"][tr[0]])))
        for i in tr:
            hy = out[tracks[i]]
            mine = {int(dj[k]): a["beta"][k] for k in ks[gi[ks] == i]}
            theirs = {int(h.measurement.metadata["j"]): float(h.probability) for h in hy if h}
            if set(mine) != set(theirs):
                res["gate_mismatch"] += 1
            for j in set(mine) & set(theirs):
                res["max_dbeta"] = max(res["max_dbeta"], abs(mine[j] - theirs[j]))
                res["pairs"] += 1
            miss = [float(h.probability) for h in hy if not h][0]
            res["max_dbeta0"] = max(res["max_dbeta0"], abs(a["beta0"][i] - miss))
            post = ss["upd"].update(hy)
            xs = np.asarray(post.state_vector, dtype=float).ravel()[np.argsort(PERM)]
            xs[:2] -= OFF
            Ps = np.asarray(post.covar, dtype=float)[np.ix_(np.argsort(PERM), np.argsort(PERM))]
            res["max_dpos_m"] = max(res["max_dpos_m"], float(np.max(np.abs(xs[:2] - L["x"][i][:2]))))
            res["max_dvel_mps"] = max(res["max_dvel_mps"], float(np.max(np.abs(xs[2:] - L["x"][i][2:]))))
            res["max_dcov_rel"] = max(res["max_dcov_rel"], float(np.max(np.abs(Ps - L["P"][i])) / np.max(np.abs(L["P"][i]))))
    return res


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--lams", default="5,200,1000")
    ap.add_argument("--scans", default=",".join(map(str, SCANS)))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    scans_cmp = tuple(int(x) for x in args.scans.split(","))
    rng = np.random.default_rng(0)
    report = {"seed": SEED, "scans": scans_cmp, "criteria": {"beta": 1e-6, "pos_m": 0.01, "cov_rel": 1e-6, "lbp": 1e-4},
              "conditions": {}}
    t_all = time.time()
    for lam in (int(x) for x in args.lams.split(",")):
        cfg0, _ = load_stage3([f"radar.clutter_lambda={lam}"], True, "M0")
        cfg0["jipda"] = {}
        sc, _, cfg = S.build(cfg0, S.specs()["EHAM_1106_eval"])
        radar = RadarParams.from_config(cfg)
        p = TrackerParams.from_config(cfg)
        p.__dict__  # frozen dataclass
        trk = make_tracker("jpda", p, cfg)
        pda = trk.pda
        tm = CombinedLinearGaussianTransitionModel([ConstantVelocity(p.q), ConstantVelocity(p.q)])
        mm = CartesianToBearingRange(ndim_state=4, mapping=(0, 2), noise_covar=np.diag([p.sigma_az_rad**2, p.sigma_r_m**2]),
                                     translation_offset=StateVector([[OFF], [OFF]]))
        pred = ExtendedKalmanPredictor(tm)
        upd = PDAUpdater(mm)
        rho = float(radar.clutter_density(np.array([50_000.0]), np.array([0.0]))[0])
        hyp = PDAHypothesiser(pred, upd, clutter_spatial_density=rho, prob_detect=pda.pd, prob_gate=p.gate_probability)
        ss = {"mm": mm, "hyp": hyp, "upd": upd}
        scans = simulate_scans(sc.scan_truths, radar, SEED)

        class _P:  # rotation period for the scan-end time passed to process_scan
            rotation = radar.rotation_period_s

        rows = []
        for k, scan in enumerate(scans[: max(scans_cmp) + 1]):
            if k in scans_cmp:
                rows.append({"k": k, **compare_scan(trk, scan, _P, pda, ss, rng)})
                print(lam, rows[-1], f"{time.time() - t_all:.0f}s", flush=True)
            else:
                trk.process_scan(scan, scan.t0 + radar.rotation_period_s)
        agg = {f: max(r[f] for r in rows) for f in ("max_dbeta", "max_dbeta0", "max_dpos_m", "max_dvel_mps", "max_dcov_rel",
                                                     "lbp_max_diff")}
        agg.update({f: sum(r[f] for r in rows) for f in ("clusters", "multi", "skipped_large", "pairs", "gate_mismatch")})
        c = report["criteria"]
        agg["agree"] = bool(agg["max_dbeta"] <= c["beta"] and agg["max_dbeta0"] <= c["beta"] and agg["max_dpos_m"] <= c["pos_m"]
                            and agg["max_dcov_rel"] <= c["cov_rel"] and agg["lbp_max_diff"] <= c["lbp"] and agg["gate_mismatch"] == 0)
        report["conditions"][str(lam)] = {"rows": rows, "aggregate": agg}
    report["wall_s"] = time.time() - t_all
    Path(args.out).write_text(json.dumps(report, indent=1))
    for lam, v in report["conditions"].items():
        print(lam, v["aggregate"])


if __name__ == "__main__":
    main()
