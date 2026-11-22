"""Interacting multiple model (IMM) filter: nearly-constant velocity + coordinated turn.

Common state ``[east, north, v_east, v_north, omega]`` (omega in rad/s,
positive = counter-clockwise in the east/north plane). Model 0 is the NCV model
of ``ekf.py`` (omega pinned to 0 with a fixed variance so that it can be mixed
into the turn model). Model 1 is a coordinated-turn EKF with the turn rate in
the state (Bar-Shalom, Li, Kirubarajan 2001, sec. 11.7).

Model switching is a continuous-time two-state Markov chain with mean sojourn
times ``tau_cv`` and ``tau_ct``, evaluated for the actual time step, because
detection times differ from scan to scan and missed scans double the step.
All functions are batched over a leading axis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import ekf
from .geo import wrap_pi
from .tracker import _TrackerBase, _candidate_pairs, assign_pairs
from .geo import polar_to_cart, polar_to_cart_cov

CV, CT = 0, 1


@dataclass(frozen=True)
class IMMParams:
    q_cv: float
    q_ct: float
    omega_noise: float  # sqrt of the turn-rate random-walk PSD [rad/s/sqrt(s)]
    tau_cv_s: float
    tau_ct_s: float
    omega_prior_sigma: float  # [rad/s]
    cv_omega_sigma: float  # [rad/s] variance the CV model contributes when mixed into CT

    @classmethod
    def from_config(cls, cfg: dict) -> "IMMParams":
        m = cfg["imm"]
        return cls(
            q_cv=float(m["q_cv"]),
            q_ct=float(m["q_ct"]),
            omega_noise=float(np.radians(m["omega_noise_dps"])),
            tau_cv_s=float(m["tau_cv_s"]),
            tau_ct_s=float(m["tau_ct_s"]),
            omega_prior_sigma=float(np.radians(m.get("omega_prior_sigma_dps", 3.0))),
            cv_omega_sigma=float(np.radians(m.get("cv_omega_sigma_dps", 3.0))),
        )

    @property
    def stationary(self) -> np.ndarray:
        a, b = 1.0 / self.tau_cv_s, 1.0 / self.tau_ct_s
        return np.array([b, a]) / (a + b)


def transition_matrix(dt, p: IMMParams):
    """(N,2,2) with entry [i, j] = P(model j at t+dt | model i at t)."""
    dt = np.atleast_1d(np.asarray(dt, dtype=float))
    pi = p.stationary
    e = np.exp(-(1.0 / p.tau_cv_s + 1.0 / p.tau_ct_s) * np.maximum(dt, 0.0))
    return pi[None, None, :] + e[:, None, None] * (np.eye(2)[None] - pi[None, None, :])


def ct_predict(x, P, dt, q_ct: float, omega_noise: float):
    """Coordinated-turn prediction with Jacobian. ``x`` (N,5), ``P`` (N,5,5), ``dt`` (N,)."""
    dt = np.atleast_1d(np.asarray(dt, dtype=float))
    vx, vy, w = x[:, 2], x[:, 3], x[:, 4]
    wt = w * dt
    s, c = np.sin(wt), np.cos(wt)
    small = np.abs(w) < 1e-6
    ws = np.where(small, 1.0, w)
    a = np.where(small, dt * (1.0 - wt * wt / 6.0), s / ws)  # sin(wT)/w
    b = np.where(small, dt * wt / 2.0, (1.0 - c) / ws)  # (1-cos(wT))/w
    da = np.where(small, -w * dt**3 / 3.0, (wt * c - s) / ws**2)
    db = np.where(small, dt**2 / 2.0, (wt * s - (1.0 - c)) / ws**2)
    xp = x.copy()
    xp[:, 0] = x[:, 0] + a * vx - b * vy
    xp[:, 1] = x[:, 1] + b * vx + a * vy
    xp[:, 2] = c * vx - s * vy
    xp[:, 3] = s * vx + c * vy
    F = np.tile(np.eye(5), (x.shape[0], 1, 1))
    F[:, 0, 2], F[:, 0, 3], F[:, 0, 4] = a, -b, da * vx - db * vy
    F[:, 1, 2], F[:, 1, 3], F[:, 1, 4] = b, a, db * vx + da * vy
    F[:, 2, 2], F[:, 2, 3], F[:, 2, 4] = c, -s, -dt * (s * vx + c * vy)
    F[:, 3, 2], F[:, 3, 3], F[:, 3, 4] = s, c, dt * (c * vx - s * vy)
    Q = np.zeros((x.shape[0], 5, 5))
    Q[:, :4, :4] = ekf.Q_matrix(dt, q_ct)
    Q[:, 4, 4] = omega_noise**2 * dt
    return xp, F @ P @ np.swapaxes(F, 1, 2) + Q


def cv_predict(x, P, dt, q_cv: float, cv_omega_sigma: float):
    """NCV prediction on the 4-D part; omega is pinned to 0 with a fixed variance."""
    x4, P4 = ekf.predict(x[:, :4], P[:, :4, :4], dt, q_cv)
    xp = np.zeros_like(x)
    xp[:, :4] = x4
    Pp = np.zeros_like(P)
    Pp[:, :4, :4] = P4
    Pp[:, 4, 4] = cv_omega_sigma**2
    return xp, Pp


def mix(Xm, Pm, mu, dt, p: IMMParams):
    """IMM interaction step. Returns mixed ``X0`` (N,2,5), ``P0`` (N,2,5,5) and predicted model probabilities ``c`` (N,2)."""
    T = transition_matrix(dt, p)  # (N, i, j)
    joint = T * mu[:, :, None]  # P(i now, j next)
    c = joint.sum(axis=1)  # (N, j)
    w = joint / np.maximum(c[:, None, :], 1e-300)  # mu_{i|j}
    X0 = np.einsum("nij,nik->njk", w, Xm)
    d = Xm[:, :, None, :] - X0[:, None, :, :]  # (N, i, j, 5)
    P0 = np.einsum("nij,nikl->njkl", w, Pm) + np.einsum("nij,nijk,nijl->njkl", w, d, d)
    return X0, P0, c


def predict_models(Xm, Pm, mu, dt, p: IMMParams):
    """Mix and predict both models. Returns ``Xp`` (N,2,5), ``Pp`` (N,2,5,5), ``c`` (N,2)."""
    X0, P0, c = mix(Xm, Pm, mu, dt, p)
    Xp, Pp = np.empty_like(X0), np.empty_like(P0)
    Xp[:, CV], Pp[:, CV] = cv_predict(X0[:, CV], P0[:, CV], dt, p.q_cv, p.cv_omega_sigma)
    Xp[:, CT], Pp[:, CT] = ct_predict(X0[:, CT], P0[:, CT], dt, p.q_ct, p.omega_noise)
    return Xp, Pp, c


def combine(Xm, Pm, w):
    """Moment-matched single Gaussian of the model mixture with weights ``w`` (N,2)."""
    x = np.einsum("nj,njk->nk", w, Xm)
    d = Xm - x[:, None, :]
    P = np.einsum("nj,njkl->nkl", w, Pm) + np.einsum("nj,njk,njl->nkl", w, d, d)
    return x, P


def update_models(Xp, Pp, c, z, R):
    """EKF update of both models with one polar measurement each; returns ``Xm, Pm, mu``."""
    N = Xp.shape[0]
    Xm, Pm = np.empty_like(Xp), np.empty_like(Pp)
    lik = np.empty((N, 2))
    I5 = np.eye(5)[None]
    for j in (CV, CT):
        zp, H4 = ekf.h_polar(Xp[:, j, :4])
        H = np.zeros((N, 2, 5))
        H[:, :, :4] = H4
        nu = z - zp
        nu[:, 1] = wrap_pi(nu[:, 1])
        S = H @ Pp[:, j] @ np.swapaxes(H, 1, 2) + R
        Sinv = np.linalg.inv(S)
        K = Pp[:, j] @ np.swapaxes(H, 1, 2) @ Sinv
        Xm[:, j] = Xp[:, j] + np.einsum("nij,nj->ni", K, nu)
        IKH = I5 - K @ H
        Pj = IKH @ Pp[:, j] @ np.swapaxes(IKH, 1, 2) + K @ R @ np.swapaxes(K, 1, 2)
        Pm[:, j] = 0.5 * (Pj + np.swapaxes(Pj, 1, 2))
        d2 = np.einsum("ni,nij,nj->n", nu, Sinv, nu)
        lik[:, j] = np.exp(-0.5 * d2) / (2.0 * np.pi * np.sqrt(np.linalg.det(S)))
    mu = c * lik
    tot = mu.sum(axis=1, keepdims=True)
    mu = np.where(tot > 0, mu / np.maximum(tot, 1e-300), c)
    return Xm, Pm, mu


class IMMTracker(_TrackerBase):
    """Same gating, GNN association and track management as ``EKFTracker``; the filter is the IMM."""

    name = "IMM-GNN"
    _fields = _TrackerBase._fields + ("Xm", "Pm", "mu")

    def __init__(self, params, imm: IMMParams):
        super().__init__(params)
        self.imm = imm
        self.Xm = np.zeros((0, 2, 5))
        self.Pm = np.zeros((0, 2, 5, 5))
        self.mu = np.zeros((0, 2))

    def _new_tracks(self, scan, det_idx):
        n = det_idx.size
        r, az = scan.r[det_idx], scan.az[det_idx]
        e, nn = polar_to_cart(r, az)
        P5 = np.zeros((n, 5, 5))
        P5[:, :2, :2] = polar_to_cart_cov(r, az, self.p.sigma_r_m, self.p.sigma_az_rad)
        P5[:, 2, 2] = P5[:, 3, 3] = self.p.init_speed_sigma_mps**2
        P5[:, 4, 4] = self.imm.omega_prior_sigma**2
        X5 = np.zeros((n, 5))
        X5[:, 0], X5[:, 1] = e, nn
        self.Xm = np.concatenate([self.Xm, np.repeat(X5[:, None], 2, axis=1)])
        self.Pm = np.concatenate([self.Pm, np.repeat(P5[:, None], 2, axis=1)])
        self.mu = np.concatenate([self.mu, np.tile(self.imm.stationary, (n, 1))])
        super()._new_tracks(scan, det_idx)

    def _associate(self, group, dets, scan):
        p = self.p
        z = scan.z[dets]
        ze, zn = polar_to_cart(z[:, 0], z[:, 1])
        X = self.X[group]
        gi, dj = _candidate_pairs(X[:, 0], X[:, 1], self.T[group], X[:, 2], X[:, 3], scan.t[dets], ze, zn,
                                  self._pregate(group, scan))
        if gi.size == 0:
            return gi, dj, None
        g = group[gi]
        dt = scan.t[dets][dj] - self.T[g]
        Xp, Pp, c = predict_models(self.Xm[g], self.Pm[g], self.mu[g], dt, self.imm)
        xb, Pb = combine(Xp, Pp, c)
        nu, S, _ = ekf.innovation(xb[:, :4], Pb[:, :4, :4], z[dj], p.R)
        d2 = ekf.mahalanobis2(nu, S)
        ok = np.flatnonzero(d2 <= p.gate_threshold)
        if ok.size == 0:
            return np.zeros(0, int), np.zeros(0, int), None
        cost = d2[ok] + np.log(np.linalg.det(S[ok]))
        k = ok[assign_pairs(group.size, dets.size, gi[ok], dj[ok], cost)]
        return gi[k], dj[k], (Xp[k], Pp[k], c[k], d2[k])

    def _pregate_extra(self, group, t_end):
        """Exact largest position variance of the combined IMM prediction at the scan end (adds the turn model)."""
        if group.size == 0:
            return None
        Xp, Pp, c = predict_models(self.Xm[group], self.Pm[group], self.mu[group], np.maximum(t_end - self.T[group], 0.0),
                                   self.imm)
        xb, Pb = combine(Xp, Pp, c)
        A = Pb[:, :2, :2]
        lam = 0.5 * (A[:, 0, 0] + A[:, 1, 1]) + np.sqrt(0.25 * (A[:, 0, 0] - A[:, 1, 1]) ** 2 + A[:, 0, 1] ** 2)
        # distance between the turn-model mean and the straight-line mean used by the pre-gate
        dt = np.maximum(t_end - self.T[group], 0.0)
        lin = self.X[group, :2] + dt[:, None] * self.X[group, 2:4]
        off = np.hypot(*(xb[:, :2] - lin).T)
        return (np.sqrt(lam) + off) ** 2 + max(self.p.sigma_r_m**2, (self.p.max_range_m * self.p.sigma_az_rad) ** 2)

    def _update(self, tracks, dets, scan, extra):
        Xp, Pp, c, d2 = extra
        Xm, Pm, mu = update_models(Xp, Pp, c, scan.z[dets], self.p.R)
        x, P = combine(Xm, Pm, mu)
        self.Xm[tracks], self.Pm[tracks], self.mu[tracks] = Xm, Pm, mu
        self.X[tracks], self.P[tracks], self.T[tracks] = x[:, :4], P[:, :4, :4], scan.t[dets]
        self.n_upd[tracks] += 1
        return [
            (int(self.ids[i]), int(d), float(scan.t[d]), x[n, :4], P[n, :4, :4], int(self.n_upd[i]), float(d2[n]),
             int(self.status[i]))
            for n, (i, d) in enumerate(zip(tracks, dets))
        ]

    def estimates(self, t_eval: float, confirmed_only: bool = True):
        from .tracker import CONFIRMED

        sel = self.status == CONFIRMED if confirmed_only else np.ones(self.ids.size, bool)
        if not sel.any():
            return self.ids[sel].copy(), np.zeros((0, 2)), np.zeros((0, 2))
        Xp, Pp, c = predict_models(self.Xm[sel], self.Pm[sel], self.mu[sel], t_eval - self.T[sel], self.imm)
        x = np.einsum("nj,njk->nk", c, Xp)
        return self.ids[sel].copy(), x[:, :2].copy(), x[:, 2:4].copy()
