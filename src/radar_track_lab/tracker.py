"""Multi-target trackers.

``EKFTracker``
    EKF (NCV motion, polar measurement) + chi-square Mahalanobis gating +
    global-nearest-neighbour association solved with the Hungarian algorithm
    (``scipy.optimize.linear_sum_assignment``). Confirmed tracks are
    associated first, tentative tracks second, leftover detections start new
    tentative tracks.

``NearestNeighborBaseline``
    No filter. A track is just its last detection; detections are linked to
    the nearest track within a fixed radius (greedy). It shares the same
    M-of-N / K-miss track management so that differences come from filtering,
    prediction and gating only.

Track management (both)
    * a new detection starts a tentative track (1 hit in 1 scan);
    * a tentative track is confirmed once it has ``M`` hits within its first
      ``N`` scans, and deleted as soon as that becomes impossible;
    * a confirmed track is deleted after ``K`` consecutive missed scans;
    * track ids are never reused.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.stats import chi2

from . import ekf
from .geo import polar_to_cart, polar_to_cart_cov

BIG = 1.0e9
TENTATIVE, CONFIRMED = 0, 1


@dataclass(frozen=True)
class TrackerParams:
    q: float
    gate_probability: float
    init_speed_sigma_mps: float
    confirm_m: int
    confirm_n: int
    delete_misses: int
    sigma_r_m: float
    sigma_az_rad: float
    max_range_m: float
    prune_radius_m: float = 6000.0
    max_link_distance_m: float = 2000.0

    @classmethod
    def from_config(cls, cfg: dict) -> "TrackerParams":
        t, r = cfg["tracker"], cfg["radar"]
        return cls(
            q=float(t["q"]),
            gate_probability=float(t["gate_probability"]),
            init_speed_sigma_mps=float(t["init_speed_sigma_mps"]),
            confirm_m=int(t["confirm_m"]),
            confirm_n=int(t["confirm_n"]),
            delete_misses=int(t["delete_misses"]),
            sigma_r_m=float(r["sigma_r_m"]),
            sigma_az_rad=float(np.radians(r["sigma_az_deg"])),
            max_range_m=float(r["max_range_m"]),
            max_link_distance_m=float(cfg.get("baseline", {}).get("max_link_distance_m", 2000.0)),
        )

    @property
    def gate_threshold(self) -> float:
        return float(chi2.ppf(self.gate_probability, df=2))

    @property
    def R(self) -> np.ndarray:
        return np.diag([self.sigma_r_m**2, self.sigma_az_rad**2])


def assign_pairs(n_rows: int, n_cols: int, r: np.ndarray, c: np.ndarray, cost: np.ndarray) -> np.ndarray:
    """Hungarian assignment over the gated pairs ``(r[i], c[i], cost[i])``.

    The bipartite graph of gated pairs is split into connected components and
    ``linear_sum_assignment`` is solved per component (forbidden entries get
    ``BIG``). Components do not interact, so the result is the same optimum as
    one dense solve: the most gated pairs, then the smallest total cost.
    Returns the indices of the selected pairs.
    """
    if r.size == 0:
        return np.zeros(0, dtype=int)
    g = coo_matrix((np.ones(r.size), (r, n_rows + c)), shape=(n_rows + n_cols, n_rows + n_cols))
    _, lab = connected_components(g, directed=False)
    comp = lab[r]
    counts = np.bincount(comp)
    single = counts[comp] == 1
    chosen = [np.flatnonzero(single)]  # isolated pairs need no solve
    multi = np.flatnonzero(~single)
    if multi.size:
        order = multi[np.argsort(comp[multi], kind="stable")]
        bounds = np.flatnonzero(np.diff(comp[order])) + 1
        for idx in np.split(order, bounds):
            ru, ri = np.unique(r[idx], return_inverse=True)
            cu, ci = np.unique(c[idx], return_inverse=True)
            sub = np.full((ru.size, cu.size), BIG)
            pair = np.full((ru.size, cu.size), -1, dtype=np.int64)
            sub[ri, ci] = cost[idx]
            pair[ri, ci] = idx
            a, b = linear_sum_assignment(sub)
            ok = sub[a, b] < BIG
            chosen.append(pair[a[ok], b[ok]])
    return np.sort(np.concatenate(chosen))


def assign(cost: np.ndarray):
    """Hungarian assignment on a dense matrix; pairs whose cost is ``>= BIG`` are dropped."""
    if cost.size == 0:
        return np.zeros(0, int), np.zeros(0, int)
    r, c = np.nonzero(cost < BIG)
    sel = assign_pairs(cost.shape[0], cost.shape[1], r, c, cost[r, c])
    return r[sel], c[sel]


def _candidate_pairs(px, py, T, vx, vy, t_det, ex, ey, radius, use_velocity=True, chunk=512):
    """Track/detection pairs whose (linearly predicted) distance is below ``radius``."""
    gi, dj = [], []
    for s in range(0, px.size, chunk):
        sl = slice(s, s + chunk)
        if use_velocity:
            dt = t_det[None, :] - T[sl, None]
            qx = px[sl, None] + dt * vx[sl, None]
            qy = py[sl, None] + dt * vy[sl, None]
        else:
            qx, qy = px[sl, None], py[sl, None]
        a, b = np.nonzero(np.hypot(qx - ex[None, :], qy - ey[None, :]) < radius)
        gi.append(a + s)
        dj.append(b)
    return np.concatenate(gi), np.concatenate(dj)


class MofN:
    """Pure M-of-N / K-miss bookkeeping, separated for unit testing."""

    def __init__(self, m: int, n: int, k: int):
        if not 1 <= m <= n:
            raise ValueError("need 1 <= M <= N")
        self.m, self.n, self.k = m, n, k

    def step(self, status, hits, scans, misses, hit):
        """Advance one scan. All args are arrays; returns new arrays and a keep mask."""
        status, hits, scans, misses = status.copy(), hits.copy(), scans.copy(), misses.copy()
        hits = hits + hit
        scans = scans + 1
        misses = np.where(hit, 0, misses + 1)
        tent = status == TENTATIVE
        confirm = tent & (hits >= self.m) & (scans <= self.n)
        status[confirm] = CONFIRMED
        keep = np.ones(status.size, dtype=bool)
        keep &= ~(tent & ~confirm & ((scans - hits) > (self.n - self.m)))
        keep &= ~((status == CONFIRMED) & (misses >= self.k))
        return status, hits, scans, misses, keep


class _TrackerBase:
    def __init__(self, params: TrackerParams):
        self.p = params
        self.mofn = MofN(params.confirm_m, params.confirm_n, params.delete_misses)
        self.next_id = 1
        self.X = np.zeros((0, 4))
        self.P = np.zeros((0, 4, 4))
        self.T = np.zeros(0)
        self.ids = np.zeros(0, dtype=np.int64)
        self.status = np.zeros(0, dtype=np.int8)
        self.hits = np.zeros(0, dtype=np.int32)
        self.scans = np.zeros(0, dtype=np.int32)
        self.misses = np.zeros(0, dtype=np.int32)
        self.n_upd = np.zeros(0, dtype=np.int32)

    # -- helpers ---------------------------------------------------------
    def _subset(self, keep):
        for name in ("X", "P", "T", "ids", "status", "hits", "scans", "misses", "n_upd"):
            setattr(self, name, getattr(self, name)[keep])

    def _append(self, X, P, T):
        n = X.shape[0]
        if n == 0:
            return
        self.X = np.concatenate([self.X, X])
        self.P = np.concatenate([self.P, P])
        self.T = np.concatenate([self.T, T])
        self.ids = np.concatenate([self.ids, np.arange(self.next_id, self.next_id + n)])
        self.next_id += n
        self.status = np.concatenate([self.status, np.zeros(n, np.int8)])
        self.hits = np.concatenate([self.hits, np.ones(n, np.int32)])
        self.scans = np.concatenate([self.scans, np.ones(n, np.int32)])
        self.misses = np.concatenate([self.misses, np.zeros(n, np.int32)])
        self.n_upd = np.concatenate([self.n_upd, np.ones(n, np.int32)])

    def _new_tracks(self, scan, det_idx):
        r, az = scan.r[det_idx], scan.az[det_idx]
        e, n = polar_to_cart(r, az)
        X = np.zeros((det_idx.size, 4))
        X[:, 0], X[:, 1] = e, n
        P = np.zeros((det_idx.size, 4, 4))
        P[:, :2, :2] = polar_to_cart_cov(r, az, self.p.sigma_r_m, self.p.sigma_az_rad)
        P[:, 2, 2] = P[:, 3, 3] = self.p.init_speed_sigma_mps**2
        self._append(X, P, scan.t[det_idx])

    def _manage(self, scan, hit, t_end):
        self.status, self.hits, self.scans, self.misses, keep = self.mofn.step(
            self.status, self.hits, self.scans, self.misses, hit
        )
        pos_end = self.X[:, :2] + self._extrapolate_factor() * (t_end - self.T)[:, None] * self.X[:, 2:]
        keep &= np.hypot(pos_end[:, 0], pos_end[:, 1]) <= self.p.max_range_m + 2000.0
        self._subset(keep)

    # -- public ------------------------------------------------------------
    def process_scan(self, scan, t_end: float):
        """Process one revolution of detections. Returns a list of update records."""
        M = scan.t.size
        used = np.zeros(M, dtype=bool)
        hit = np.zeros(self.ids.size, dtype=bool)
        records = []
        for group_status in (CONFIRMED, TENTATIVE):
            group = np.flatnonzero(self.status == group_status)
            dets = np.flatnonzero(~used)
            if group.size == 0 or dets.size == 0:
                continue
            gi, dj, extra = self._associate(group, dets, scan)
            if gi.size == 0:
                continue
            rec = self._update(group[gi], dets[dj], scan, extra)
            hit[group[gi]] = True
            used[dets[dj]] = True
            records.extend(rec)
        self._manage(scan, hit, t_end)
        self._new_tracks(scan, np.flatnonzero(~used))
        return records

    def estimates(self, t_eval: float, confirmed_only: bool = True):
        """Track ids, positions and velocities at ``t_eval``."""
        sel = self.status == CONFIRMED if confirmed_only else np.ones(self.ids.size, bool)
        dt = t_eval - self.T[sel]
        X = self.X[sel]
        pos = X[:, :2] + self._extrapolate_factor() * dt[:, None] * X[:, 2:]
        return self.ids[sel].copy(), pos, X[:, 2:].copy()

    def _extrapolate_factor(self) -> float:
        return 1.0


class EKFTracker(_TrackerBase):
    name = "EKF-GNN"

    def _associate(self, group, dets, scan):
        p = self.p
        z = scan.z[dets]
        ze, zn = polar_to_cart(z[:, 0], z[:, 1])
        X = self.X[group]
        gi, dj = _candidate_pairs(X[:, 0], X[:, 1], self.T[group], X[:, 2], X[:, 3], scan.t[dets], ze, zn,
                                  p.prune_radius_m)
        if gi.size == 0:
            return gi, dj, None
        dt = scan.t[dets][dj] - self.T[group][gi]
        xp, Pp = ekf.predict(X[gi], self.P[group[gi]], dt, p.q)
        nu, S, _ = ekf.innovation(xp, Pp, z[dj], p.R)
        d2 = ekf.mahalanobis2(nu, S)
        ok = np.flatnonzero(d2 <= p.gate_threshold)
        if ok.size == 0:
            return np.zeros(0, int), np.zeros(0, int), None
        cost = d2[ok] + np.log(np.linalg.det(S[ok]))
        k = ok[assign_pairs(group.size, dets.size, gi[ok], dj[ok], cost)]
        return gi[k], dj[k], (xp[k], Pp[k], d2[k])

    def _update(self, tracks, dets, scan, extra):
        xp, Pp, d2 = extra
        x, P, _, _ = ekf.update(xp, Pp, scan.z[dets], self.p.R)
        self.X[tracks], self.P[tracks], self.T[tracks] = x, P, scan.t[dets]
        self.n_upd[tracks] += 1
        return [
            (int(self.ids[i]), int(d), float(scan.t[d]), x[n], P[n], int(self.n_upd[i]), float(d2[n]),
             int(self.status[i]))
            for n, (i, d) in enumerate(zip(tracks, dets))
        ]


class NearestNeighborBaseline(_TrackerBase):
    """Connect detections to the nearest previous detection; no filtering."""

    name = "NN-baseline"

    def _associate(self, group, dets, scan):
        ze, zn = polar_to_cart(scan.r[dets], scan.az[dets])
        X = self.X[group]
        gi, dj = _candidate_pairs(X[:, 0], X[:, 1], None, None, None, None, ze, zn,
                                  np.nextafter(self.p.max_link_distance_m, np.inf), use_velocity=False)
        if gi.size == 0:
            return gi, dj, None
        dist = np.hypot(X[gi, 0] - ze[dj], X[gi, 1] - zn[dj])
        order = np.lexsort((dj, gi, dist))  # nearest first; ties broken by track, then detection
        used_t, used_d, rows, cols = set(), set(), [], []
        for o in order:  # greedy nearest-first
            a, b = int(gi[o]), int(dj[o])
            if a in used_t or b in used_d:
                continue
            used_t.add(a)
            used_d.add(b)
            rows.append(a)
            cols.append(b)
        return np.asarray(rows, int), np.asarray(cols, int), None

    def _update(self, tracks, dets, scan, extra):
        e, n = polar_to_cart(scan.r[dets], scan.az[dets])
        t_new = scan.t[dets]
        dt = np.maximum(t_new - self.T[tracks], 1e-3)
        v = np.stack([(e - self.X[tracks, 0]) / dt, (n - self.X[tracks, 1]) / dt], axis=1)
        self.X[tracks, 0], self.X[tracks, 1] = e, n
        self.X[tracks, 2:] = v  # display only; never used for association or estimates
        self.T[tracks] = t_new
        self.n_upd[tracks] += 1
        return [
            (int(self.ids[i]), int(d), float(scan.t[d]), self.X[i].copy(), None, int(self.n_upd[i]), float("nan"),
             int(self.status[i]))
            for i, d in zip(tracks, dets)
        ]

    def _extrapolate_factor(self) -> float:
        return 0.0  # estimate = last detection, held until the next one
