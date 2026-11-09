"""Evaluation metrics: GOSPA with decomposition, track-continuity metrics, NEES."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist
from scipy.stats import chi2, t as student_t


@dataclass
class GospaResult:
    total: float  # GOSPA distance [m]
    loc_sq: float  # sum of squared distances of assigned pairs (p = 2)
    n_assigned: int
    n_missed: int
    n_false: int
    pairs: list  # (truth_index, estimate_index) with distance < c


def gospa(X: np.ndarray, Y: np.ndarray, c: float, p: int = 2) -> GospaResult:
    """GOSPA (alpha = 2) between truth set ``X`` (n,2) and estimates ``Y`` (m,2).

    Rahmathullah, Garcia-Fernandez, Svensson (FUSION 2017):
    d = ( sum_assigned d(x,y)^p + c^p/2 * (#missed + #false) )^(1/p)
    """
    n, m = len(X), len(Y)
    if n == 0 or m == 0:
        tot = (c**p / 2.0 * (n + m)) ** (1.0 / p)
        return GospaResult(tot, 0.0, 0, n, m, [])
    D = cdist(X, Y)
    rows, cols = linear_sum_assignment(np.minimum(D, c) ** p)
    d = D[rows, cols]
    ok = d < c
    loc = float(np.sum(d[ok] ** p))
    na = int(ok.sum())
    nmiss, nfalse = n - na, m - na
    tot = (loc + c**p / 2.0 * (nmiss + nfalse)) ** (1.0 / p)
    return GospaResult(tot, loc, na, nmiss, nfalse, list(zip(rows[ok].tolist(), cols[ok].tolist())))


@dataclass
class ScanEval:
    t: float
    gospa: GospaResult
    truth_ids: np.ndarray
    track_ids: np.ndarray
    assigned: dict  # truth_id -> track_id
    sq_err: np.ndarray  # squared position errors of assigned pairs


def evaluate_scan(eval_truth, track_ids, track_pos, c: float, p: int = 2) -> ScanEval:
    g = gospa(eval_truth.pos, track_pos, c, p)
    assigned = {int(eval_truth.ids[i]): int(track_ids[j]) for i, j in g.pairs}
    sq = np.array([np.sum((eval_truth.pos[i] - track_pos[j]) ** 2) for i, j in g.pairs])
    return ScanEval(eval_truth.t, g, eval_truth.ids.copy(), np.asarray(track_ids).copy(), assigned, sq)


def summarize(scan_evals: list[ScanEval], c: float, warmup_s: float, t_start: float) -> dict:
    """Aggregate per-scan evaluations into scalar metrics.

    * GOSPA terms are reported as root-mean of each additive part, so
      ``gospa_rms**2 == loc**2 + missed**2 + false**2``.
    * ID switch: a truth target's assigned track id changes between two scans
      in which it is assigned.
    * Fragmentation (track break): a target that was assigned becomes
      unassigned while it is still present in the next scan.
    * Initiation delay: for targets that appear after the warm-up, time from
      their first scan as truth to their first assignment to a confirmed track.
    """
    ev = [s for s in scan_evals if s.t >= t_start + warmup_s]
    if not ev:
        raise ValueError("no scans after warm-up")
    tot = np.array([s.gospa.total for s in ev])
    loc = np.array([s.gospa.loc_sq for s in ev])
    nmiss = np.array([s.gospa.n_missed for s in ev])
    nfalse = np.array([s.gospa.n_false for s in ev])
    nass = np.array([s.gospa.n_assigned for s in ev])
    ntruth = np.array([s.truth_ids.size for s in ev])
    ntracks = np.array([s.track_ids.size for s in ev])
    sq = np.concatenate([s.sq_err for s in ev]) if any(s.sq_err.size for s in ev) else np.zeros(0)

    # continuity metrics over all scans (warm-up included for history, counted after)
    last_track: dict[int, int] = {}
    prev_assigned: dict[int, int] = {}
    id_switches = 0
    fragments = 0
    first_seen: dict[int, float] = {}
    first_tracked: dict[int, float] = {}
    for i, s in enumerate(scan_evals):
        counted = s.t >= t_start + warmup_s
        present = set(int(x) for x in s.truth_ids)
        for tid in present:
            first_seen.setdefault(tid, s.t)
        for tid, trk in s.assigned.items():
            first_tracked.setdefault(tid, s.t)
            if tid in last_track and last_track[tid] != trk and counted:
                id_switches += 1
            last_track[tid] = trk
        if counted:
            for tid in prev_assigned:
                if tid not in s.assigned and tid in present:
                    fragments += 1
        prev_assigned = s.assigned

    delays, never = [], 0
    t_counted = t_start + warmup_s
    for tid, t0 in first_seen.items():
        if t0 < t_counted:
            continue  # present at start: initiation is not observed fairly
        if tid in first_tracked and first_tracked[tid] >= t0:
            delays.append(first_tracked[tid] - t0)
        else:
            never += 1
    delays = np.asarray(delays)
    halfc2 = c**2 / 2.0
    return {
        "scans": len(ev),
        "gospa_mean_m": float(tot.mean()),
        "gospa_rms_m": float(np.sqrt(np.mean(tot**2))),
        "gospa_loc_m": float(np.sqrt(loc.mean())),
        "gospa_missed_m": float(np.sqrt(halfc2 * nmiss.mean())),
        "gospa_false_m": float(np.sqrt(halfc2 * nfalse.mean())),
        "missed_per_scan": float(nmiss.mean()),
        "false_tracks_per_scan": float(nfalse.mean()),
        "truth_per_scan": float(ntruth.mean()),
        "tracks_per_scan": float(ntracks.mean()),
        "assigned_fraction": float(nass.sum() / max(ntruth.sum(), 1)),
        "rmse_m": float(np.sqrt(sq.mean())) if sq.size else float("nan"),
        "id_switches": int(id_switches),
        "fragmentations": int(fragments),
        "targets_entering": int(delays.size + never),
        "init_delay_mean_s": float(delays.mean()) if delays.size else float("nan"),
        "init_delay_median_s": float(np.median(delays)) if delays.size else float("nan"),
        "never_tracked": int(never),
    }


def anees_bounds(n_samples: int, dof: int = 4, prob: float = 0.95):
    """Two-sided interval for the average NEES of ``n_samples`` independent draws."""
    a = (1.0 - prob) / 2.0
    lo = chi2.ppf(a, dof * n_samples) / n_samples
    hi = chi2.ppf(1.0 - a, dof * n_samples) / n_samples
    return float(lo), float(hi)


def mean_ci(x, prob: float = 0.95):
    """Mean and two-sided t-interval half-width for the mean."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return float("nan"), float("nan")
    if x.size == 1:
        return float(x[0]), float("nan")
    h = student_t.ppf(0.5 + prob / 2.0, x.size - 1) * x.std(ddof=1) / np.sqrt(x.size)
    return float(x.mean()), float(h)
