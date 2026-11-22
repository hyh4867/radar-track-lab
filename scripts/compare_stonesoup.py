"""Q3: compare this project's EKF + GNN tracker with Stone Soup 1.9.1 (MIT) on identical detections.

(a) Filter level: one target, Pd = 1, no clutter; state and covariance after every update.
(b) Tracker level: evaluation window, default condition, seeds 20261106-08.
    Stone Soup supplies the transition / measurement models, EKF predictor and
    updater, the Mahalanobis hypothesiser and (variant "native") its GNN 2-D
    assignment. Track management (confirmed tracks first, 3-of-4, 5 misses,
    initiation, coverage limit) is glue code written to the same rules.
      native : Stone Soup's own assignment (minimises the sum of Mahalanobis distances,
               a miss costs the gate distance).
      matched: same Stone Soup hypotheses, but the pairs are chosen with this
               project's cost d^2 + ln|S| (scipy dense assignment).
Detection times are rounded to 1 microsecond (Stone Soup uses datetime) for both sides.

Frames. Stone Soup 1.9.1 takes the measurement Jacobian by forward differences
(stonesoup.functions.jacobian) and its step falls back to 1e-8 m for negative
state components, which leaves a relative Jacobian error of about 1e-3 there.
Every comparison is therefore run in two frames, with unmodified Stone Soup:
  origin: radar at (0, 0), as in this project (coordinates of both signs);
  offset: radar at (+200 km, +200 km) through the model's translation_offset,
          so all position coordinates are positive and the step is adequate.
Checkpointed per seed and variant in results/data/stage2/stonesoup_compare.json.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore")

from stonesoup.dataassociator.neighbour import GNNWith2DAssignment  # noqa: E402
from stonesoup.hypothesiser.distance import DistanceHypothesiser  # noqa: E402
from stonesoup.measures import Mahalanobis  # noqa: E402
from stonesoup.models.measurement.nonlinear import CartesianToBearingRange  # noqa: E402
from stonesoup.models.transition.linear import CombinedLinearGaussianTransitionModel, ConstantVelocity  # noqa: E402
from stonesoup.predictor.kalman import ExtendedKalmanPredictor  # noqa: E402
from stonesoup.types.angle import Bearing  # noqa: E402
from stonesoup.types.array import StateVector  # noqa: E402
from stonesoup.types.detection import Detection  # noqa: E402
from stonesoup.types.hypothesis import SingleHypothesis  # noqa: E402
from stonesoup.types.state import GaussianState  # noqa: E402
from stonesoup.types.track import Track  # noqa: E402
from stonesoup.updater.kalman import ExtendedKalmanUpdater  # noqa: E402

from radar_track_lab import ekf  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.experiments import load_stage2  # noqa: E402
from radar_track_lab.geo import polar_to_cart, polar_to_cart_cov  # noqa: E402
from radar_track_lab.metrics import evaluate_scan, summarize  # noqa: E402
from radar_track_lab.radar import EvalTruth, RadarParams, Scan, simulate_scans  # noqa: E402
from radar_track_lab.synthetic import maneuver_scenario  # noqa: E402
from radar_track_lab.tracker import BIG, EKFTracker, TrackerParams  # noqa: E402

OUT = ROOT / "results/data/stage2/stonesoup_compare.json"
EPOCH = dt.datetime(2026, 1, 1)
OFFSET = 200_000.0
PERM = [0, 2, 1, 3]  # [e, n, ve, vn] <-> Stone Soup [x, vx, y, vy]
SUMMARY_KEYS = ("rmse_m", "id_switches", "fragmentations", "missed_per_scan", "false_tracks_per_scan", "gospa_mean_m")


def ts(t_rel: float) -> dt.datetime:
    return EPOCH + dt.timedelta(microseconds=int(round(t_rel * 1e6)))


def shifted(scans, evals, t_start):
    """Scans / evaluation truths with times relative to t_start, rounded to 1 microsecond."""
    r6 = lambda x: np.round(np.asarray(x) - t_start, 6)  # noqa: E731
    sc = [Scan(s.k, float(r6(s.t0)), r6(s.t), s.r, s.az, s.truth_id) for s in scans]
    ev = [EvalTruth(e.k, float(r6(e.t)), e.ids, e.pos, e.vel) for e in evals]
    return sc, ev


class SS:
    """Stone Soup models and filter components for one parameter set."""

    def __init__(self, p: TrackerParams, offset: float = 0.0):
        self.p, self.off = p, offset
        self.tm = CombinedLinearGaussianTransitionModel([ConstantVelocity(p.q), ConstantVelocity(p.q)])
        self.mm = CartesianToBearingRange(ndim_state=4, mapping=(0, 2),
                                          noise_covar=np.diag([p.sigma_az_rad**2, p.sigma_r_m**2]),
                                          translation_offset=StateVector([[offset], [offset]]))
        self.pred = ExtendedKalmanPredictor(self.tm)
        self.upd = ExtendedKalmanUpdater(self.mm)
        self.hyp = DistanceHypothesiser(self.pred, self.upd, measure=Mahalanobis(),
                                        missed_distance=float(np.sqrt(p.gate_threshold)))
        self.assoc = GNNWith2DAssignment(self.hyp)

    def detection(self, r, az, t_rel, i):
        # Stone Soup bearing is counter-clockwise from east; azimuth is clockwise from north
        return Detection(StateVector([[Bearing(np.pi / 2 - az)], [r]]), timestamp=ts(t_rel),
                         measurement_model=self.mm, metadata={"i": i})

    def initial(self, r, az, t_rel):
        e, n = polar_to_cart(r, az)
        P = np.zeros((4, 4))
        P[:2, :2] = polar_to_cart_cov(r, az, self.p.sigma_r_m, self.p.sigma_az_rad)
        P[2, 2] = P[3, 3] = self.p.init_speed_sigma_mps**2
        return GaussianState(StateVector([e + self.off, 0.0, n + self.off, 0.0]), P[np.ix_(PERM, PERM)], timestamp=ts(t_rel))


class SSTracker:
    def __init__(self, p: TrackerParams, variant: str, offset: float = 0.0):
        self.ss, self.p, self.variant = SS(p, offset), p, variant
        self.tracks, self.next_id = [], 1
        self.cost_rule_differs = 0  # scans where the two cost rules pick different pairs from the same hypotheses

    @staticmethod
    def _matched_assignment(hyps, n_det):
        cost = np.full((len(hyps), n_det), BIG)
        table = {}
        for a, hs in enumerate(hyps):
            for h in hs:
                if h:
                    j = h.measurement.metadata["col"]
                    cost[a, j] = float(h.distance) ** 2 + np.log(np.linalg.det(np.asarray(h.measurement_prediction.covar, float)))
                    table[(a, j)] = h
        rr, cc = linear_sum_assignment(cost)
        return {a: table[(a, j)] for a, j in zip(rr, cc) if cost[a, j] < BIG}

    def process_scan(self, scan, t_end):
        ss = self.ss
        dets = [ss.detection(r, az, t, i) for i, (r, az, t) in enumerate(zip(scan.r, scan.az, scan.t))]
        used, hit, assoc_log = set(), set(), []
        start = list(self.tracks)
        for status in (1, 0):
            grp = [t for t in start if t["status"] == status]
            avail = [d for d in dets if d.metadata["i"] not in used]
            if not grp or not avail:
                continue
            for c, d in enumerate(avail):
                d.metadata["col"] = c
            hyps = [ss.hyp.hypothesise(t["track"], avail, ts(t_end)) for t in grp]
            matched = self._matched_assignment(hyps, len(avail))
            if self.variant == "native":
                res = ss.assoc.associate([t["track"] for t in grp], avail, ts(t_end))
                chosen = {a: res[t["track"]] for a, t in enumerate(grp) if res[t["track"]]}
                same = {a: h.measurement.metadata["i"] for a, h in chosen.items()} == \
                       {a: h.measurement.metadata["i"] for a, h in matched.items()}
                self.cost_rule_differs += not same
            else:
                chosen = matched
            for a, h in chosen.items():
                t = grp[a]
                t["track"].append(ss.upd.update(SingleHypothesis(h.prediction, h.measurement, h.measurement_prediction)))
                used.add(h.measurement.metadata["i"])
                hit.add(t["id"])
                assoc_log.append((t["id"], h.measurement.metadata["i"]))
        keep = []
        m, n, k = self.p.confirm_m, self.p.confirm_n, self.p.delete_misses
        for t in start:
            h = t["id"] in hit
            t["hits"] += h
            t["scans"] += 1
            t["misses"] = 0 if h else t["misses"] + 1
            was_tentative = t["status"] == 0
            if was_tentative and t["hits"] >= m and t["scans"] <= n:
                t["status"] = 1
            if was_tentative and t["status"] == 0 and (t["scans"] - t["hits"]) > (n - m):
                continue
            if t["status"] == 1 and t["misses"] >= k:
                continue
            pos = self._extrapolate(t, t_end)[0] - self.ss.off
            if np.hypot(pos[0], pos[1]) > self.p.max_range_m + 2000.0:
                continue
            keep.append(t)
        self.tracks = keep
        for i in range(len(dets)):
            if i not in used:
                self.tracks.append({"id": self.next_id, "status": 0, "hits": 1, "scans": 1, "misses": 0,
                                    "track": Track([self.ss.initial(scan.r[i], scan.az[i], scan.t[i])])})
                self.next_id += 1
        return assoc_log

    @staticmethod
    def _extrapolate(t, t_end):
        s = t["track"].state
        x = np.asarray(s.state_vector, float).ravel()[PERM]
        d = (ts(t_end) - s.timestamp).total_seconds()
        return x[:2] + d * x[2:], x[2:]

    def estimates(self, t_end):
        conf = [t for t in self.tracks if t["status"] == 1]
        pos = np.array([self._extrapolate(t, t_end)[0] - self.ss.off for t in conf]).reshape(-1, 2)
        return np.array([t["id"] for t in conf], dtype=np.int64), pos


def filter_level(p: TrackerParams, name, scans, offset=0.0):
    """Every detection of a single target is used; returns the largest differences."""
    ss = SS(p, offset)
    s0 = scans[0]
    x = np.zeros((1, 4))
    x[0, 0], x[0, 1] = polar_to_cart(s0.r[0], s0.az[0])
    P = np.zeros((1, 4, 4))
    P[0, :2, :2] = polar_to_cart_cov(s0.r[0], s0.az[0], p.sigma_r_m, p.sigma_az_rad)
    P[0, 2, 2] = P[0, 3, 3] = p.init_speed_sigma_mps**2
    t_prev = s0.t[0]
    state = ss.initial(s0.r[0], s0.az[0], s0.t[0])
    dpos = dvel = dcov = 0.0
    n = 0
    for s in scans[1:]:
        if s.t.size == 0:
            continue
        xp, Pp = ekf.predict(x, P, np.array([s.t[0] - t_prev]), p.q)
        x, P, _, _ = ekf.update(xp, Pp, s.z[:1], p.R)
        t_prev = s.t[0]
        d = ss.detection(s.r[0], s.az[0], s.t[0], 0)
        pred = ss.pred.predict(state, timestamp=d.timestamp)
        state = ss.upd.update(SingleHypothesis(pred, d))
        xs = np.asarray(state.state_vector, float).ravel()[PERM] - np.array([offset, offset, 0.0, 0.0])
        Ps = np.asarray(state.covar, float)[np.ix_(PERM, PERM)]
        dpos = max(dpos, float(np.hypot(*(xs[:2] - x[0, :2]))))
        dvel = max(dvel, float(np.hypot(*(xs[2:] - x[0, 2:]))))
        dcov = max(dcov, float(np.max(np.abs(Ps - P[0]) / np.sqrt(np.outer(np.diag(P[0]), np.diag(P[0]))))))
        n += 1
    return {"case": name, "frame": "offset" if offset else "origin", "updates": n, "max_pos_diff_m": dpos, "max_vel_diff_mps": dvel, "max_cov_rel_diff": dcov,
            "agree": bool(dpos <= 0.01 and dvel <= 0.001 and dcov <= 1e-6)}


def tracker_level(cfg, sc, seed, variant, offset=0.0):
    radar, p = RadarParams.from_config(cfg), TrackerParams.from_config(cfg)
    scans, evals = shifted(simulate_scans(sc.scan_truths, radar, seed), sc.eval_truths, sc.t_start)
    c, warm = float(cfg["eval"]["gospa_c_m"]), float(cfg["eval"]["warmup_s"])
    from dataclasses import replace

    wide = variant.endswith("_wide")  # this project's coarse pre-gate widened from 6 km to 12 km
    mine = EKFTracker(replace(p, prune_radius_m=12_000.0) if wide else p)
    theirs = SSTracker(p, "matched" if wide else variant, offset)
    ev_m, ev_s = [], []
    n_union = n_same = assoc_diff_scans = n_ss = n_ss_pos = 0
    max_d, first = 0.0, None
    t0 = time.perf_counter()
    for k, (scan, et) in enumerate(zip(scans, evals)):
        a_m = sorted((r[0], r[1]) for r in mine.process_scan(scan, et.t))
        a_s = sorted(theirs.process_scan(scan, et.t))
        im, pm, _ = mine.estimates(et.t)
        is_, ps = theirs.estimates(et.t)
        ev_m.append(evaluate_scan(et, im, pm, c))
        ev_s.append(evaluate_scan(et, is_, ps, c))
        dm, ds = dict(zip(im.tolist(), pm)), dict(zip(is_.tolist(), ps))
        n_union += len(set(dm) | set(ds))
        for i in set(dm) & set(ds):
            d = float(np.hypot(*(dm[i] - ds[i])))
            n_same += d <= 0.01
            max_d = max(max_d, d) if d <= 0.01 else max_d
        if len(ps):  # id-free check: a track of this project within 1 cm of each Stone Soup track
            n_ss += len(ps)
            if len(pm):
                n_ss_pos += int((np.hypot(ps[:, None, 0] - pm[None, :, 0], ps[:, None, 1] - pm[None, :, 1]).min(axis=1) <= 0.01).sum())
        if a_m != a_s:
            assoc_diff_scans += 1
            if first is None:
                first = {"scan": k, "only_this_project": [list(x) for x in sorted(set(a_m) - set(a_s))][:6],
                         "only_stone_soup": [list(x) for x in sorted(set(a_s) - set(a_m))][:6]}
    sm, s_s = summarize(ev_m, c, warm, 0.0), summarize(ev_s, c, warm, 0.0)
    return {"seed": seed, "variant": variant, "frame": "offset" if offset else "origin", "scans": len(scans), "track_scans_union": n_union,
            "track_scans_within_1cm": n_same, "share_within_1cm": n_same / max(n_union, 1),
            "max_diff_of_matching_m": max_d,
            "stone_soup_track_scans": n_ss, "share_with_counterpart_within_1cm": n_ss_pos / max(n_ss, 1), "scans_with_different_associations": assoc_diff_scans,
            "first_difference": first, "scans_where_cost_rules_disagree": theirs.cost_rule_differs,
            "this_project": {k: sm[k] for k in SUMMARY_KEYS}, "stone_soup": {k: s_s[k] for k in SUMMARY_KEYS},
            "same_answer": bool(n_same / max(n_union, 1) >= 0.999 and sm["id_switches"] == s_s["id_switches"]),
            "wall_s": time.perf_counter() - t0}


def main() -> None:
    cfg, _ = load_stage2()
    sc, _, cfg = S.build(cfg, S.specs()["EHAM_1106_eval"])
    p = TrackerParams.from_config(cfg)
    doc = json.loads(OUT.read_text()) if OUT.exists() else {"stonesoup_version": "1.9.1", "filter": [], "tracker": []}
    if not doc["filter"]:
        clean = {**cfg, "radar": {**cfg["radar"], "pd": 1.0, "clutter_lambda": 0.0}}
        radar = RadarParams.from_config(clean)
        line = maneuver_scenario([-40_000.0, 30_000.0], 190.0, np.radians(-18.0), [(80 * 4.8, 0.0)])
        turn = maneuver_scenario([-30_000.0, 25_000.0], 130.0, np.radians(20.0),
                                 [(20 * 4.8, 0.0), (120.0, np.radians(1.0)), (30 * 4.8, 0.0)])
        cases = [("synthetic straight line", line), ("synthetic 1 deg/s turn", turn)]
        # real ADS-B truth: the aircraft present in the most scans of the evaluation window
        ids = np.concatenate([s.ids for s in sc.scan_truths])
        top = int(np.bincount(ids).argmax())
        real = []
        for s in simulate_scans(sc.scan_truths, radar, 20261106):
            m = s.truth_id == top
            real.append(Scan(s.k, s.t0, s.t[m], s.r[m], s.az[m], s.truth_id[m]))
        real = [s for s in real if s.t.size]
        for off in (0.0, OFFSET):
            for name, s in cases:
                scans, _ = shifted(simulate_scans(s.scan_truths, radar, 20261106), s.eval_truths, s.t_start)
                doc["filter"].append(filter_level(p, name, scans, off))
            scans, _ = shifted(real, [], sc.t_start)
            doc["filter"].append(filter_level(p, "real ADS-B aircraft, most scans in the window", scans, off))
        # Jacobian accuracy of unmodified Stone Soup by quadrant (exact formulas as reference)
        from stonesoup.types.state import State
        ss0 = SS(p)
        doc["jacobian_check"] = []
        for e, n in ((38000.0, 29000.0), (-38000.0, 29000.0), (38000.0, -29000.0), (-38000.0, -29000.0)):
            r2 = e * e + n * n
            He = np.array([[-n / r2, e / r2], [e / np.sqrt(r2), n / np.sqrt(r2)]])
            Hs = np.asarray(ss0.mm.jacobian(State(StateVector([e, 0.0, n, 0.0]))), float)[:, [0, 2]]
            doc["jacobian_check"].append({"east_m": e, "north_m": n, "max_rel_error": float(np.max(np.abs(Hs - He) / np.abs(He)))})
        OUT.write_text(json.dumps(doc, indent=1))
    for f in doc["filter"]:
        print(f, flush=True)
    done = {(r["seed"], r["variant"], r["frame"]) for r in doc["tracker"]}
    plan = [(v, s, OFFSET) for v in ("matched", "native") for s in (20261106, 20261107, 20261108)]
    plan += [("matched", 20261106, 0.0)]
    plan += [("matched_wide", s, OFFSET) for s in (20261106, 20261107, 20261108)]
    for variant, seed, off in plan:
            if (seed, variant, "offset" if off else "origin") in done:
                continue
            r = tracker_level(cfg, sc, seed, variant, off)
            doc["tracker"].append(r)
            OUT.write_text(json.dumps(doc, indent=1))
            print({k: v for k, v in r.items() if k != "first_difference"}, flush=True)


if __name__ == "__main__":
    main()
