"""Extended Kalman filter: nearly-constant-velocity motion, polar measurements.

State ``x = [east, north, v_east, v_north]`` (m, m/s).
Measurement ``z = [range, azimuth]`` with azimuth clockwise from north.
All functions are batched over a leading axis.
"""

from __future__ import annotations

import numpy as np

from .geo import wrap_pi


def F_matrix(dt):
    dt = np.atleast_1d(np.asarray(dt, dtype=float))
    F = np.tile(np.eye(4), (dt.size, 1, 1))
    F[:, 0, 2] = dt
    F[:, 1, 3] = dt
    return F


def Q_matrix(dt, q: float):
    """Discretised continuous white-noise acceleration (PSD ``q`` per axis)."""
    dt = np.atleast_1d(np.asarray(dt, dtype=float))
    Q = np.zeros((dt.size, 4, 4))
    a, b, c = q * dt**3 / 3.0, q * dt**2 / 2.0, q * dt
    Q[:, 0, 0] = Q[:, 1, 1] = a
    Q[:, 0, 2] = Q[:, 2, 0] = Q[:, 1, 3] = Q[:, 3, 1] = b
    Q[:, 2, 2] = Q[:, 3, 3] = c
    return Q


def predict(x, P, dt, q: float):
    """Batched prediction. ``x`` (N,4), ``P`` (N,4,4), ``dt`` (N,)."""
    dt = np.atleast_1d(np.asarray(dt, dtype=float))
    xp = x.copy()
    xp[:, 0] += dt * x[:, 2]
    xp[:, 1] += dt * x[:, 3]
    F = F_matrix(dt)
    Pp = F @ P @ np.swapaxes(F, 1, 2) + Q_matrix(dt, q)
    return xp, Pp


def h_polar(x):
    """Predicted [range, azimuth] and Jacobian H (N,2,4)."""
    e, n = x[:, 0], x[:, 1]
    r2 = np.maximum(e * e + n * n, 1.0)
    r = np.sqrt(r2)
    z = np.stack([r, np.arctan2(e, n) % (2 * np.pi)], axis=1)
    H = np.zeros((x.shape[0], 2, 4))
    H[:, 0, 0] = e / r
    H[:, 0, 1] = n / r
    H[:, 1, 0] = n / r2
    H[:, 1, 1] = -e / r2
    return z, H


def innovation(xp, Pp, z, R):
    """Innovation ``nu`` (N,2), covariance ``S`` (N,2,2), Jacobian ``H``."""
    zp, H = h_polar(xp)
    nu = z - zp
    nu[:, 1] = wrap_pi(nu[:, 1])
    S = H @ Pp @ np.swapaxes(H, 1, 2) + R
    return nu, S, H


def mahalanobis2(nu, S):
    Sinv = np.linalg.inv(S)
    return np.einsum("ni,nij,nj->n", nu, Sinv, nu)


def update(xp, Pp, z, R):
    """Batched EKF update (Joseph form). Returns ``x, P, nu, S``."""
    nu, S, H = innovation(xp, Pp, z, R)
    Sinv = np.linalg.inv(S)
    K = Pp @ np.swapaxes(H, 1, 2) @ Sinv
    x = xp + np.einsum("nij,nj->ni", K, nu)
    I_KH = np.eye(4)[None] - K @ H
    P = I_KH @ Pp @ np.swapaxes(I_KH, 1, 2) + K @ R @ np.swapaxes(K, 1, 2)
    return x, 0.5 * (P + np.swapaxes(P, 1, 2)), nu, S


def nees(x_est, P, x_true):
    """Normalised estimation error squared, batched."""
    e = x_true - x_est
    return np.einsum("ni,nij,nj->n", e, np.linalg.inv(P), e)
