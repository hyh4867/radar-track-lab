"""Stage 3 B1, Stone Soup cross-check (b): whole tracker (docs/PREREGISTRATION_3.md 4.4).

Two trackers run side by side on the same detections (Schiphol evaluation window, ideal sensor, uniform clutter):
  ours : JPDATracker (JPDA, M-of-N management)
  ss   : the same gating and track management, but every scan the association probabilities and the PDA update
         come from Stone Soup 1.9.1 (JPDA exact enumeration per cluster; for clusters too large to enumerate, the
         Stone Soup loopy-BP routine on Stone Soup's own hypothesis weights; PDAUpdater for the state).
"Same answer" = >= 99.9% of confirmed track-scans within 1 cm and the same number of ID switches.
lambda 5 and 200 over the full 30 min; lambda 1000 over the first 5 min (62 scans). Seeds 20261106-08.

    .venv/bin/python scripts/stage3_stonesoup_b.py [--lams 5,200,1000] [--seeds 3]
Output: results/stage3/stonesoup_b.json (checkpoint per condition and seed)
"""

from __future__ import annotations

import argparse
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

from scipy.sparse import coo_matrix  # noqa: E402
from scipy.sparse.csgraph import connected_components  # noqa: E402
from stonesoup.dataassociator.probability import JPDAwithLBP  # noqa: E402
from stonesoup.hypothesiser.probability import PDAHypothesiser  # noqa: E402
from stonesoup.models.measurement.nonlinear import CartesianToBearingRange  # noqa: E402
from stonesoup.models.transition.linear import CombinedLinearGaussianTransitionModel, ConstantVelocity  # noqa: E402
from stonesoup.predictor.kalman import ExtendedKalmanPredictor  # noqa: E402
from stonesoup.types.angle import Bearing  # noqa: E402
from stonesoup.types.array import StateVector  # noqa: E402
from stonesoup.types.detection import Detection  # noqa: E402
from stonesoup.types.hypothesis import SingleProbabilityHypothesis  # noqa: E402
from stonesoup.types.multihypothesis import MultipleHypothesis  # noqa: E402
from stonesoup.types.state import GaussianState  # noqa: E402
from stonesoup.types.track import Track  # noqa: E402
from stonesoup.updater.probability import PDAUpdater  # noqa: E402

from stage3_run import load_stage3  # noqa: E402
from stage3_stonesoup_a import EPOCH, OFF, PERM, JPDAByID  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.jpda import JPDATracker, count_events  # noqa: E402
from radar_track_lab.metrics import evaluate_scan, summarize  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.sim import make_tracker  # noqa: E402
from radar_track_lab.tracker import CONFIRMED, TrackerParams  # noqa: E402

OUT = ROOT / "results/stage3/stonesoup_b.json"
# Stone Soup timestamps are datetimes (1 us). To keep its time rounding far below our float times, Stone Soup runs on a
# stretched clock: 1 Stone Soup second = 1 ms. Velocities are divided by TS and q by TS^3; the model is unchanged
# (position variance q dt^3/3, velocity variance q dt in real units) and the rounding becomes 1 ns of real time.
TS = 1000.0
SCALE = np.array([1.0, 1.0, 1.0 / TS, 1.0 / TS])  # [e, n, ve, vn] -> Stone Soup units


def sts(t):
    return EPOCH + __import__("datetime").timedelta(microseconds=int(round(t * TS * 1e6)))


class AnalyticBearingRange(CartesianToBearingRange):
    """Diagnostic only: Stone Soup's bearing-range model with the analytic Jacobian instead of forward differences."""

    def jacobian(self, state, **kwargs):
        x = np.asarray(state.state_vector, float).ravel()
        dx = x[self.mapping[0]] - float(self.translation_offset[0])
        dy = x[self.mapping[1]] - float(self.translation_offset[1])
        r2 = dx * dx + dy * dy
        r = np.sqrt(r2)
        J = np.zeros((2, self.ndim_state))
        J[0, self.mapping[0]], J[0, self.mapping[1]] = -dy / r2, dx / r2
        J[1, self.mapping[0]], J[1, self.mapping[1]] = dx / r, dy / r
        return J


class SSDriven(JPDATracker):
    """Our gating and management; association probabilities and state update from Stone Soup."""

    def setup(self, ss, scan_t0_ref):
        self.ss = ss
        self.t_ref = scan_t0_ref
        self.post = {}
        self.ss_stats = {"exact": 0, "lbp": 0, "single": 0}

    def associate_scan(self, scan):
        a = super().associate_scan(scan)
        n, M = self.ids.size, scan.t.size
        gi, dj = a["gi"], a["dj"]
        beta, beta0 = np.zeros(gi.size), np.ones(n)
        rel = lambda t: t - self.t_ref  # noqa: E731
        self.post = {}
        if gi.size:
            g = coo_matrix((np.ones(gi.size), (gi, n + dj)), shape=(n + M, n + M))
            _, lab = connected_components(g, directed=False)
            comps = {}
            for k in range(gi.size):
                comps.setdefault(lab[gi[k]], []).append(k)
            for ks in comps.values():
                ks = np.asarray(ks)
                tr, de = np.unique(gi[ks]), np.unique(dj[ks])
                tracks, pre = {}, {}
                for i in tr:
                    x0 = self.X[i] * SCALE
                    x0[:2] += OFF
                    P0 = self.P[i] * np.outer(SCALE, SCALE)
                    track = Track([GaussianState(StateVector(x0[PERM]), P0[np.ix_(PERM, PERM)], timestamp=sts(rel(self.T[i])))])
                    tracks[i] = track
                    tstamp = sts(rel(a["ti"][i]))
                    dets = [Detection(StateVector([[Bearing(np.pi / 2 - scan.az[j])], [scan.r[j]]]), timestamp=tstamp,
                                      measurement_model=self.ss["mm"], metadata={"j": int(j)}) for j in de]
                    pre[track] = self.ss["hyp"].hypothesise(track, dets, tstamp)
                Wc = np.zeros((tr.size, de.size))
                Wc[np.searchsorted(tr, gi[ks]), np.searchsorted(de, dj[ks])] = 1.0
                # same switch rule as our tracker: exact if <= exact_max_tracks tracks and <= exact_max_events events
                if tr.size == 1 or (tr.size <= self.pda.exact_max_tracks
                                    and count_events(Wc, self.pda.exact_max_events) <= self.pda.exact_max_events):
                    assoc = JPDAByID(self.ss["hyp"])
                    assoc.pre = pre
                    out = assoc.associate(set(pre), None, sts(rel(a["ti"][tr[0]])))
                    self.ss_stats["single" if tr.size == 1 else "exact"] += 1
                else:  # Stone Soup loopy BP on Stone Soup's own per-track weights
                    self.ss_stats["lbp"] += 1
                    lik = np.zeros((tr.size, de.size + 1))
                    for r_, i in enumerate(tr):
                        for h in pre[tracks[i]]:
                            if h:
                                lik[r_, 1 + np.searchsorted(de, h.measurement.metadata["j"])] = float(h.probability)
                            else:
                                lik[r_, 0] = float(h.probability)
                    lik = lik / lik[:, [0]]
                    P_ = JPDAwithLBP._loopy_belief_propagation(lik, 50, 1e-12)
                    out = {}
                    for r_, i in enumerate(tr):
                        hs = []
                        for h in pre[tracks[i]]:
                            p_ = P_[r_, 0] if not h else P_[r_, 1 + np.searchsorted(de, h.measurement.metadata["j"])]
                            hs.append(SingleProbabilityHypothesis(h.prediction, h.measurement,
                                                                  measurement_prediction=h.measurement_prediction,
                                                                  probability=max(float(p_), 1e-300)))
                        out[tracks[i]] = MultipleHypothesis(hs, True, 1)
                for i in tr:
                    hy = out[tracks[i]]
                    probs = {int(h.measurement.metadata["j"]): float(h.probability) for h in hy if h}
                    for k in ks[gi[ks] == i]:
                        beta[k] = probs.get(int(dj[k]), 0.0)
                    beta0[i] = [float(h.probability) for h in hy if not h][0]
                    post = self.ss["upd"].update(hy)
                    xs = np.asarray(post.state_vector, dtype=float).ravel()[np.argsort(PERM)]
                    xs[:2] -= OFF
                    xs = xs / SCALE
                    Ps = np.asarray(post.covar, float)[np.ix_(np.argsort(PERM), np.argsort(PERM))] / np.outer(SCALE, SCALE)
                    self.post[int(self.ids[i])] = (xs, Ps)
        a["beta"], a["beta0"] = beta, beta0
        return a

    def process_scan(self, scan, t_end):
        recs = super().process_scan(scan, t_end)
        for n, tid in enumerate(self.ids.tolist()):
            if tid in self.post:
                self.X[n], self.P[n] = self.post[tid]
        return recs


def one(lam, seed, n_scans, analytic=False):
    cfg0, _ = load_stage3([f"radar.clutter_lambda={lam}"], True, "M0")
    cfg0["jipda"] = {}
    sc, _, cfg = S.build(cfg0, S.specs()["EHAM_1106_eval"])
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    ours = make_tracker("jpda", p, cfg)
    ssd = SSDriven(p, ours.pda, radar)
    tm = CombinedLinearGaussianTransitionModel([ConstantVelocity(p.q / TS**3), ConstantVelocity(p.q / TS**3)])
    MM = AnalyticBearingRange if analytic else CartesianToBearingRange
    mm = MM(ndim_state=4, mapping=(0, 2), noise_covar=np.diag([p.sigma_az_rad**2, p.sigma_r_m**2]),
            translation_offset=StateVector([[OFF], [OFF]]))
    rho = float(radar.clutter_density(np.array([50_000.0]), np.array([0.0]))[0])
    hyp = PDAHypothesiser(ExtendedKalmanPredictor(tm), PDAUpdater(mm), clutter_spatial_density=rho, prob_detect=ours.pda.pd,
                          prob_gate=p.gate_probability)
    ssd.setup({"mm": mm, "hyp": hyp, "upd": PDAUpdater(mm)}, sc.t_start)
    scans = simulate_scans(sc.scan_truths, radar, seed)[:n_scans]
    c, pw = float(cfg["eval"]["gospa_c_m"]), int(cfg["eval"]["gospa_p"])
    ev_o, ev_s, diffs, n_conf, n_close, set_diff, first_split = [], [], [], 0, 0, 0, None
    t0 = time.time()
    for k, scan in enumerate(scans):
        et = sc.eval_truths[k]
        ours.process_scan(scan, et.t)
        ssd.process_scan(scan, et.t)
        io, po, _ = ours.estimates(et.t)
        is_, ps, _ = ssd.estimates(et.t)
        ev_o.append(evaluate_scan(et, io, po, c, pw))
        ev_s.append(evaluate_scan(et, is_, ps, c, pw))
        common = np.intersect1d(io, is_)
        set_diff += np.setxor1d(io, is_).size
        if np.setxor1d(io, is_).size and first_split is None:
            first_split = k
        if common.size:
            d = np.hypot(*(po[np.searchsorted(io, common)] - ps[np.searchsorted(is_, common)]).T)
            diffs.append(float(d.max()))
            n_conf += common.size
            n_close += int((d <= 0.01).sum())
    so, ss_ = summarize(ev_o, c, float(cfg["eval"]["warmup_s"]), sc.t_start), summarize(ev_s, c, float(cfg["eval"]["warmup_s"]), sc.t_start)
    total = n_conf + set_diff
    return {"lam": lam, "seed": seed, "analytic_jacobian": analytic, "scans": len(scans), "confirmed_track_scans": total,
            "share_within_1cm": (n_close / total) if total else float("nan"), "max_pos_diff_m": max(diffs) if diffs else 0.0,
            "confirmed_set_differences": int(set_diff), "first_scan_sets_differ": first_split,
            "idsw_ours": so["id_switches"], "idsw_ss": ss_["id_switches"],
            "summary_ours": {k: so[k] for k in ("rmse_m", "gospa_mean_m", "false_tracks_per_scan", "missed_per_scan")},
            "summary_ss": {k: ss_[k] for k in ("rmse_m", "gospa_mean_m", "false_tracks_per_scan", "missed_per_scan")},
            "ss_cluster_counts": ssd.ss_stats, "wall_s": time.time() - t0,
            "same_answer": bool(total and n_close / total >= 0.999 and so["id_switches"] == ss_["id_switches"])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lams", default="5,200,1000")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--analytic-jacobian", action="store_true", help="diagnostic variant (not the Stone Soup default)")
    a = ap.parse_args()
    doc = json.loads(OUT.read_text()) if OUT.exists() else {"rows": []}
    done = {(r["lam"], r["seed"], r.get("analytic_jacobian", False)) for r in doc["rows"]}
    for lam in (int(x) for x in a.lams.split(",")):
        for seed in range(20261106, 20261106 + a.seeds):
            if (lam, seed, a.analytic_jacobian) in done:
                continue
            row = one(lam, seed, 62 if lam >= 1000 else 10_000, a.analytic_jacobian)
            doc["rows"].append(row)
            OUT.write_text(json.dumps(doc, indent=1))
            print(time.strftime("%H:%M:%S"), {k: row[k] for k in ("lam", "seed", "share_within_1cm", "max_pos_diff_m",
                                                                  "idsw_ours", "idsw_ss", "same_answer", "wall_s")}, flush=True)


if __name__ == "__main__":
    main()
