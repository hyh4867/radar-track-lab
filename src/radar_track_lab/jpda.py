"""JPDA and JIPDA trackers (docs/PREREGISTRATION_3.md 4.2).

Same EKF (NCV, polar measurement), same gate, same single-point initiation as ``EKFTracker``.

Timing: each track is predicted once per scan, to its predicted illumination time ``t_i`` (the time the beam
crosses the predicted azimuth). Detections in its gate are treated as if taken at ``t_i``; their true times
differ by (azimuth difference) / (antenna rate), a fraction of a second for gated detections.

Association weights (Bar-Shalom, Daum & Huang 2009; the same form as Stone Soup's PDAHypothesiser):
    detection j for track i : w_ij = P_D * [E_i^-] * N(nu_ij; 0, S_i) / rho(z_j)
    no detection for track i: w_i0 = 1 - P_D * P_G * [E_i^-]
(``E_i^-`` only for JIPDA). A joint event assigns each detection to at most one track; its weight is the
product of the per-track weights. Marginals are exact (enumeration) for small clusters and loopy belief
propagation (Williams & Lau 2014) for large ones.

JIPDA existence (Musicki & Evans 2004 form; reduces to IPDA for a single track):
    E^- = p_s E,   E^+ = sum_j beta_ij + beta_i0 * E^-(1 - P_D P_G) / w_i0
and the state update uses the association probabilities conditioned on existence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from . import ekf
from .geo import TWO_PI, cart_to_polar, polar_to_cart, wrap_pi
from .tracker import CONFIRMED, TENTATIVE, _candidate_pairs, _TrackerBase


@dataclass(frozen=True)
class PDAParams:
    mode: str = "jpda"  # "jpda" (M-of-N management) | "jipda" (existence probability)
    pd: float = 0.9
    p0: float = 0.05  # JIPDA: initial existence probability
    confirm: float = 0.95  # JIPDA: confirm when E >= confirm
    delete: float = 0.01  # JIPDA: delete when E < delete
    p_survive: float = 0.98  # JIPDA: per scan
    new_track_below: float = 0.5  # a detection starts a track if its total association probability is below this
    exact_max_tracks: int = 10
    exact_max_events: int = 100_000
    lbp_tol: float = 1e-10
    lbp_max_iter: int = 2000
    density: str = "true"  # "true" | "estimated" (JIPDA-est, PREREGISTRATION_3 7.3)

    @classmethod
    def from_config(cls, cfg: dict, mode: str) -> "PDAParams":
        j = dict(cfg.get("jipda") or {})
        keep = {k: j[k] for k in ("pd", "p0", "confirm", "delete", "p_survive", "new_track_below", "exact_max_tracks",
                                  "exact_max_events") if k in j}
        return cls(mode=mode, **keep)


# --- marginal association probabilities ------------------------------------------------------------
def marginals_exact(w0, W):
    """Exact JPDA marginals. ``w0`` (n,), ``W`` (n, m) with 0 for non-gated pairs. Returns beta0 (n,), B (n, m)."""
    n, m = W.shape
    B = np.zeros((n, m))
    b0 = np.zeros(n)
    opts = [np.flatnonzero(W[i] > 0) for i in range(n)]
    order = np.argsort([o.size for o in opts])
    total = [0.0]
    choice = np.full(n, -1)
    used = np.zeros(m, dtype=bool)

    def rec(level, weight):
        if level == n:
            total[0] += weight
            for i in range(n):
                if choice[i] < 0:
                    b0[i] += weight
                else:
                    B[i, choice[i]] += weight
            return
        i = order[level]
        choice[i] = -1
        rec(level + 1, weight * w0[i])
        for j in opts[i]:
            if not used[j]:
                used[j] = True
                choice[i] = j
                rec(level + 1, weight * W[i, j])
                used[j] = False
        choice[i] = -1

    rec(0, 1.0)
    return b0 / total[0], B / total[0]


def count_events(W, limit):
    """Number of joint events, stopping once ``limit`` is exceeded (returns limit + 1 then)."""
    n, m = W.shape
    opts = [np.flatnonzero(W[i] > 0) for i in range(n)]
    order = np.argsort([o.size for o in opts])
    used = np.zeros(m, dtype=bool)
    cnt = [0]

    def rec(level):
        if cnt[0] > limit:
            return
        if level == n:
            cnt[0] += 1
            return
        i = order[level]
        rec(level + 1)
        for j in opts[i]:
            if not used[j]:
                used[j] = True
                rec(level + 1)
                used[j] = False

    rec(0)
    return cnt[0]


def marginals_lbp(w0, W, tol=1e-10, max_iter=2000):
    """Loopy belief propagation for JPDA marginals (Williams & Lau 2014). Returns beta0, B, iterations."""
    psi = W / w0[:, None]
    g = psi > 0
    nu = np.ones_like(psi)  # measurement -> track messages
    for it in range(1, max_iter + 1):
        s = (psi * nu).sum(axis=1, keepdims=True)
        mu = np.where(g, psi / (1.0 + s - psi * nu), 0.0)  # track -> measurement
        t = mu.sum(axis=0, keepdims=True)
        nu_new = np.where(g, 1.0 / (1.0 + t - mu), 1.0)
        if np.max(np.abs(nu_new - nu)) < tol:
            nu = nu_new
            break
        nu = nu_new
    s = (psi * nu).sum(axis=1)
    B = psi * nu / (1.0 + s)[:, None]
    return 1.0 / (1.0 + s), B, it


# --- clutter density estimator (JIPDA-est) -------------------------------------------------------------
class GridDensity:
    """Moving-average clutter density on a range x azimuth grid from the detections not explained by confirmed tracks."""

    def __init__(self, r_min, r_max, dr=10_000.0, n_az=16, window=10):
        self.r_min, self.r_max, self.dr, self.n_az, self.window = r_min, r_max, dr, n_az, window
        self.n_r = int(np.ceil((r_max - r_min) / dr))
        self.hist: list[np.ndarray] = []
        self.vol = np.full((self.n_r, n_az), dr * TWO_PI / n_az)
        self.vol[-1] = (r_max - (r_min + dr * (self.n_r - 1))) * TWO_PI / n_az

    def _cells(self, r, az):
        i = np.clip(((np.asarray(r) - self.r_min) // self.dr).astype(int), 0, self.n_r - 1)
        j = np.clip((np.asarray(az) % TWO_PI // (TWO_PI / self.n_az)).astype(int), 0, self.n_az - 1)
        return i, j

    def density(self, r, az):
        if not self.hist:
            counts = np.ones((self.n_r, self.n_az))  # floor only
            n = 1
        else:
            counts = np.sum(self.hist, axis=0)
            n = len(self.hist)
        dens = np.maximum(counts, 1.0 * n / self.window) / (n * self.vol)  # floor: 1 per cell per 10 scans
        i, j = self._cells(r, az)
        return dens[i, j]

    def add(self, r, az):
        c = np.zeros((self.n_r, self.n_az))
        i, j = self._cells(r, az)
        np.add.at(c, (i, j), 1.0)
        self.hist.append(c)
        if len(self.hist) > self.window:
            self.hist.pop(0)


# --- tracker -----------------------------------------------------------------------------------------
class JPDATracker(_TrackerBase):
    """JPDA (M-of-N) or JIPDA (existence) on the stage 1 EKF."""

    _fields = _TrackerBase._fields + ("E",)

    def __init__(self, params, pda: PDAParams, radar):
        super().__init__(params)
        self.pda = pda
        self.radar = radar
        self.E = np.zeros(0)
        self.name = {"jpda": "EKF-JPDA", "jipda": "EKF-JIPDA"}[pda.mode] + ("-est" if pda.density == "estimated" else "")
        self.est = GridDensity(radar.min_range_m, radar.max_range_m) if pda.density == "estimated" else None
        self.stats = {"clusters": 0, "multi": 0, "lbp": 0, "max_cluster_tracks": 0}
        self.keep_last = False
        self.last = None

    def _append(self, X, P, T):
        super()._append(X, P, T)
        self.E = np.concatenate([self.E, np.full(X.shape[0], self.pda.p0)])

    def clutter_density(self, r, az):
        if self.est is not None:
            return self.est.density(r, az)
        return self.radar.clutter_density(r, az)

    def illumination_time(self, scan):
        """Predicted time the beam crosses each track (two fixed-point steps)."""
        omega = self.radar.omega
        t = np.full(self.ids.size, scan.t0)
        for _ in range(2):
            pos = self.X[:, :2] + (t - self.T)[:, None] * self.X[:, 2:]
            _, az = cart_to_polar(pos[:, 0], pos[:, 1])
            t = scan.t0 + az / omega
        return np.maximum(t, self.T)

    def associate_scan(self, scan):
        """Gating, weights and marginals for one scan. Returns a dict used by ``process_scan`` and the tests."""
        p, pda = self.p, self.pda
        n, M = self.ids.size, scan.t.size
        ti = self.illumination_time(scan)
        xp, Pp = ekf.predict(self.X, self.P, ti - self.T, p.q)
        zp, H = ekf.h_polar(xp)
        S = H @ Pp @ np.swapaxes(H, 1, 2) + p.R
        Sinv = np.linalg.inv(S)
        detS = np.linalg.det(S)
        ze, zn = polar_to_cart(scan.r, scan.az)
        gi, dj = _candidate_pairs(self.X[:, 0], self.X[:, 1], self.T, self.X[:, 2], self.X[:, 3], scan.t, ze, zn,
                                  self._pregate(np.arange(n), scan))
        nu = np.stack([scan.r[dj] - zp[gi, 0], wrap_pi(scan.az[dj] - zp[gi, 1])], axis=1)
        d2 = np.einsum("ni,nij,nj->n", nu, Sinv[gi], nu)
        ok = d2 <= p.gate_threshold
        gi, dj, nu, d2 = gi[ok], dj[ok], nu[ok], d2[ok]
        lik = np.exp(-0.5 * d2) / (TWO_PI * np.sqrt(detS[gi]))
        rho = np.maximum(self.clutter_density(scan.r[dj], scan.az[dj]), 1e-300)  # lambda = 0: no clutter
        Em = pda.p_survive * self.E if pda.mode == "jipda" else np.ones(n)
        w = pda.pd * Em[gi] * lik / rho
        w0 = 1.0 - pda.pd * p.gate_probability * Em
        beta0 = np.ones(n)
        beta = np.zeros(gi.size)
        if gi.size:
            g = coo_matrix((np.ones(gi.size), (gi, n + dj)), shape=(n + M, n + M))
            _, lab = connected_components(g, directed=False)
            comp = lab[gi]
            order = np.argsort(comp, kind="stable")
            bounds = np.flatnonzero(np.diff(comp[order])) + 1
            for idx in np.split(order, bounds):
                self.stats["clusters"] += 1
                tr, ti_loc = np.unique(gi[idx], return_inverse=True)
                de, dj_loc = np.unique(dj[idx], return_inverse=True)
                if tr.size == 1:  # PDA closed form
                    tot = w0[tr[0]] + w[idx].sum()
                    beta[idx] = w[idx] / tot
                    beta0[tr[0]] = w0[tr[0]] / tot
                    continue
                self.stats["multi"] += 1
                self.stats["max_cluster_tracks"] = max(self.stats["max_cluster_tracks"], int(tr.size))
                Wc = np.zeros((tr.size, de.size))
                Wc[ti_loc, dj_loc] = w[idx]
                if tr.size <= pda.exact_max_tracks and count_events(Wc, pda.exact_max_events) <= pda.exact_max_events:
                    b0, Bc = marginals_exact(w0[tr], Wc)
                else:
                    self.stats["lbp"] += 1
                    b0, Bc, _ = marginals_lbp(w0[tr], Wc, pda.lbp_tol, pda.lbp_max_iter)
                beta[idx] = Bc[ti_loc, dj_loc]
                beta0[tr] = b0
        return dict(ti=ti, xp=xp, Pp=Pp, H=H, S=S, Sinv=Sinv, gi=gi, dj=dj, nu=nu, d2=d2, w=w, w0=w0, Em=Em,
                    beta=beta, beta0=beta0)

    def process_scan(self, scan, t_end: float):
        p, pda = self.p, self.pda
        n, M = self.ids.size, scan.t.size
        if n == 0:
            if self.est is not None:
                self.est.add(scan.r, scan.az)
            self._new_tracks(scan, np.arange(M))
            return []
        a = self.associate_scan(scan)
        gi, dj, beta, beta0 = a["gi"], a["dj"], a["beta"], a["beta0"]
        # existence and conditional association probabilities
        if pda.mode == "jipda":
            miss_exist = beta0 * a["Em"] * (1.0 - pda.pd * p.gate_probability) / a["w0"]
            Epost = np.bincount(gi, weights=beta, minlength=n) + miss_exist
            Epost = np.clip(Epost, 0.0, 1.0)
            safe = np.maximum(Epost, 1e-300)
            bc = beta / safe[gi]
            bc0 = miss_exist / safe
        else:
            Epost = self.E
            bc, bc0 = beta, beta0
        # PDA update (innovation form)
        K = a["Pp"] @ np.swapaxes(a["H"], 1, 2) @ a["Sinv"]
        nub = np.zeros((n, 2))
        np.add.at(nub, gi, bc[:, None] * a["nu"])
        spread = np.zeros((n, 2, 2))
        np.add.at(spread, gi, bc[:, None, None] * np.einsum("ni,nj->nij", a["nu"], a["nu"]))
        spread -= np.einsum("ni,nj->nij", nub, nub)
        x = a["xp"] + np.einsum("nij,nj->ni", K, nub)
        IKH = np.eye(4)[None] - K @ a["H"]
        Pc = IKH @ a["Pp"] @ np.swapaxes(IKH, 1, 2) + K @ p.R @ np.swapaxes(K, 1, 2)
        Pn = bc0[:, None, None] * a["Pp"] + (1.0 - bc0)[:, None, None] * Pc + K @ spread @ np.swapaxes(K, 1, 2)
        Pn = 0.5 * (Pn + np.swapaxes(Pn, 1, 2))
        gated = np.bincount(gi, minlength=n) > 0
        if self.keep_last:  # for the Stone Soup cross-check and tests
            self.last = dict(ids=self.ids.copy(), prior_X=self.X.copy(), prior_P=self.P.copy(), prior_T=self.T.copy(),
                             x=x.copy(), P=Pn.copy(), assoc=a, E_post=np.asarray(Epost).copy())
        self.X, self.P, self.T = x, Pn, a["ti"]
        self.n_upd = self.n_upd + gated
        records = []
        if gi.size:
            best = {}
            for k in np.argsort(-bc, kind="stable"):
                i = int(gi[k])
                if i not in best and bc[k] > 0.5:
                    best[i] = k
            for i, k in best.items():
                records.append((int(self.ids[i]), int(dj[k]), float(a["ti"][i]), x[i], Pn[i], int(self.n_upd[i]),
                                float(a["d2"][k]), int(self.status[i])))
        # detections explained by tracks
        claimed = np.bincount(dj, weights=beta, minlength=M)
        if self.est is not None:
            conf = self.status[gi] == CONFIRMED
            by_conf = np.bincount(dj[conf], weights=beta[conf], minlength=M)
            free = by_conf < pda.new_track_below
            self.est.add(scan.r[free], scan.az[free])
        # track management
        if pda.mode == "jipda":
            self.E = Epost
            self.status = np.where((self.status == TENTATIVE) & (self.E >= pda.confirm), CONFIRMED, self.status).astype(np.int8)
            keep = self.E >= pda.delete
            self.hits = self.hits + gated
            self.scans = self.scans + 1
            self.misses = np.where(gated, 0, self.misses + 1)
        else:
            # hit = probability that the track was detected >= 0.5. The preregistered "any detection in the gate"
            # confirmed tracks that only shared another track's detection (synthetic test, lambda 5: 3.6 false
            # tracks/scan with 10 targets); changed before any evaluation run (stage 3 report, deviations).
            hit = (1.0 - beta0) >= 0.5
            self.status, self.hits, self.scans, self.misses, keep = self.mofn.step(
                self.status, self.hits, self.scans, self.misses, hit)
        pos_end = self.X[:, :2] + (t_end - self.T)[:, None] * self.X[:, 2:]
        keep &= np.hypot(pos_end[:, 0], pos_end[:, 1]) <= p.max_range_m + 2000.0
        self._subset(keep)
        self._new_tracks(scan, np.flatnonzero(claimed < pda.new_track_below))
        return records
