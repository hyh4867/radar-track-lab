"""Synthetic truth that follows the tracker's own NCV model (for NEES checks)."""

from __future__ import annotations

import numpy as np

from .ekf import Q_matrix
from .geo import TWO_PI, cart_to_polar
from .radar import EvalTruth, ScanTruth
from .sim import Scenario


def _step(x, dt, q, rng):
    x = x.copy()
    x[0] += dt * x[2]
    x[1] += dt * x[3]
    if dt > 0:
        x += rng.multivariate_normal(np.zeros(4), Q_matrix(dt, q)[0])
    return x


def ncv_scenario(n_targets: int, n_scans: int, T: float, q: float, speed_sigma: float, seed: int,
                 r_min: float = 15_000.0, r_max: float = 40_000.0, max_range: float = 100_000.0,
                 min_range: float = 1_000.0) -> Scenario:
    """Targets moving exactly as the NCV model with PSD ``q``.

    Initial velocity per axis ~ N(0, speed_sigma^2), i.e. the tracker's own
    initialisation prior, so the filter is Bayesian-consistent by construction
    apart from linearisation and gating.
    """
    rng = np.random.default_rng(seed)
    omega = TWO_PI / T
    az0 = (np.arange(n_targets) + rng.uniform(0.2, 0.8, n_targets)) * TWO_PI / n_targets
    r0 = rng.uniform(r_min, r_max, n_targets)
    X = np.zeros((n_targets, 4))
    X[:, 0], X[:, 1] = r0 * np.sin(az0), r0 * np.cos(az0)
    X[:, 2:] = rng.normal(0.0, speed_sigma, (n_targets, 2))
    t_last = np.zeros(n_targets)
    scans, evals = [], []
    for k in range(n_scans):
        tk = k * T
        rows = []
        for i in range(n_targets):
            # illumination time from the mean motion (sub-second accuracy is enough)
            tc = tk
            for _ in range(3):
                p = X[i, :2] + (tc - t_last[i]) * X[i, 2:]
                tc = tk + cart_to_polar(p[0], p[1])[1] / omega
            tc = max(float(tc), t_last[i])
            X[i] = _step(X[i], tc - t_last[i], q, rng)
            t_last[i] = tc
            r = np.hypot(X[i, 0], X[i, 1])
            if min_range <= r <= max_range:
                rows.append((i, tc, X[i, :2].copy(), X[i, 2:].copy()))
        rows.sort(key=lambda r: r[1])
        scans.append(ScanTruth(
            k, tk,
            np.array([r[0] for r in rows], dtype=np.int64),
            np.array([r[1] for r in rows]),
            np.array([r[2] for r in rows]).reshape(-1, 2),
            np.array([r[3] for r in rows]).reshape(-1, 2),
        ))
        te = tk + T
        ids, pos, vel = [], [], []
        for i in range(n_targets):
            X[i] = _step(X[i], te - t_last[i], q, rng)
            t_last[i] = te
            if min_range <= np.hypot(X[i, 0], X[i, 1]) <= max_range:
                ids.append(i)
                pos.append(X[i, :2].copy())
                vel.append(X[i, 2:].copy())
        evals.append(EvalTruth(k, te, np.array(ids, dtype=np.int64), np.array(pos).reshape(-1, 2),
                               np.array(vel).reshape(-1, 2)))
    return Scenario("synthetic-ncv", 0.0, n_scans, scans, evals, {"targets": n_targets})
