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


def maneuver_scenario(p0, speed: float, heading_rad: float, legs, T: float = 4.8, target_id: int = 7,
                      t0: float = 0.0) -> Scenario:
    """One target flying exact straight / constant-turn-rate legs.

    ``legs`` is a list of ``(duration_s, omega_rad_s)``; ``omega`` is positive
    counter-clockwise in the east/north plane (0 = straight). ``heading_rad``
    is the initial direction of motion, measured counter-clockwise from east.
    Illumination times are solved exactly. The scenario meta holds the true
    turn rate at every scan.
    """
    p0 = np.asarray(p0, dtype=float)
    starts, states = [], []
    t, p, th = 0.0, p0.copy(), float(heading_rad)
    for dur, w in legs:
        starts.append(t)
        states.append((p.copy(), th, float(w)))
        if abs(w) < 1e-12:
            p = p + speed * dur * np.array([np.cos(th), np.sin(th)])
        else:
            p = p + speed / w * np.array([np.sin(th + w * dur) - np.sin(th), -np.cos(th + w * dur) + np.cos(th)])
            th = th + w * dur
        t += dur
    starts = np.asarray(starts)
    total = t

    def state(tq):
        tq = min(max(tq - t0, 0.0), total)
        i = int(np.searchsorted(starts, tq, side="right") - 1)
        pa, tha, w = states[i]
        d = tq - starts[i]
        if abs(w) < 1e-12:
            pos = pa + speed * d * np.array([np.cos(tha), np.sin(tha)])
            thq = tha
        else:
            thq = tha + w * d
            pos = pa + speed / w * np.array([np.sin(thq) - np.sin(tha), -np.cos(thq) + np.cos(tha)])
        return pos, speed * np.array([np.cos(thq), np.sin(thq)]), w

    omega_radar = TWO_PI / T
    n_scans = int(total // T) - 1
    scans, evals, w_scan, w_eval = [], [], [], []
    for k in range(n_scans):
        tk = t0 + k * T
        tc = tk
        for _ in range(8):
            pos, _, _ = state(tc)
            tc = tk + cart_to_polar(pos[0], pos[1])[1] / omega_radar
        pos, vel, w = state(tc)
        scans.append(ScanTruth(k, tk, np.array([target_id]), np.array([tc]), pos[None], vel[None]))
        w_scan.append(w)
        pe, ve, we = state(tk + T)
        evals.append(EvalTruth(k, tk + T, np.array([target_id]), pe[None], ve[None]))
        w_eval.append(we)
    return Scenario("maneuver", t0, n_scans, scans, evals,
                    {"omega_scan": np.asarray(w_scan), "omega_eval": np.asarray(w_eval)})


def imm_model_scenario(n_targets: int, n_scans: int, T: float, imm, speed_sigma: float, seed: int,
                       r_min: float = 15_000.0, r_max: float = 40_000.0, max_range: float = 100_000.0,
                       min_range: float = 1_000.0) -> Scenario:
    """Targets that follow the IMM's own two-model assumptions (for a NEES check).

    The mode can change once per scan, at the illumination time, with the
    filter's transition probabilities for the elapsed time. Entering the turn
    mode draws the turn rate from N(0, cv_omega_sigma^2); in turn mode the rate
    random-walks with ``omega_noise``. Both modes add white-noise acceleration
    (``q_cv`` / ``q_ct``).
    """
    from .imm import transition_matrix

    rng = np.random.default_rng(seed)
    omega_radar = TWO_PI / T
    az0 = (np.arange(n_targets) + rng.uniform(0.2, 0.8, n_targets)) * TWO_PI / n_targets
    r0 = rng.uniform(r_min, r_max, n_targets)
    X = np.zeros((n_targets, 5))
    X[:, 0], X[:, 1] = r0 * np.sin(az0), r0 * np.cos(az0)
    X[:, 2:4] = rng.normal(0.0, speed_sigma, (n_targets, 2))
    mode = (rng.random(n_targets) < imm.stationary[1]).astype(int)
    X[:, 4] = np.where(mode == 1, rng.normal(0.0, imm.omega_prior_sigma, n_targets), 0.0)
    t_last = np.zeros(n_targets)

    def step(x, m, dt):
        x = x.copy()
        if dt <= 0:
            return x
        if m == 0:
            x[0] += dt * x[2]
            x[1] += dt * x[3]
            x[:4] += rng.multivariate_normal(np.zeros(4), Q_matrix(dt, imm.q_cv)[0])
        else:
            w = x[4]
            wt = w * dt
            s, c = np.sin(wt), np.cos(wt)
            a = dt if abs(w) < 1e-9 else s / w
            b = 0.0 if abs(w) < 1e-9 else (1.0 - c) / w
            vx, vy = x[2], x[3]
            x[0] += a * vx - b * vy
            x[1] += b * vx + a * vy
            x[2], x[3] = c * vx - s * vy, s * vx + c * vy
            x[:4] += rng.multivariate_normal(np.zeros(4), Q_matrix(dt, imm.q_ct)[0])
            x[4] += rng.normal(0.0, imm.omega_noise * np.sqrt(dt))
        return x

    scans, evals = [], []
    t_mode = np.zeros(n_targets)
    for k in range(n_scans):
        tk = k * T
        rows = []
        for i in range(n_targets):
            tc = tk
            for _ in range(3):
                p = X[i, :2] + (tc - t_last[i]) * X[i, 2:4]
                tc = tk + cart_to_polar(p[0], p[1])[1] / omega_radar
            tc = max(float(tc), t_last[i])
            # mode change (once per scan), decided for the time since the last illumination
            Tm = transition_matrix(tc - t_mode[i], imm)[0]
            new = int(rng.random() < Tm[mode[i], 1])
            if new != mode[i]:
                X[i, 4] = rng.normal(0.0, imm.cv_omega_sigma) if new == 1 else 0.0
            # the filter applies the new mode over the whole step, so the truth does too
            X[i] = step(X[i], new, tc - t_last[i])
            mode[i], t_mode[i], t_last[i] = new, tc, tc
            r = np.hypot(X[i, 0], X[i, 1])
            if min_range <= r <= max_range:
                rows.append((i, tc, X[i, :2].copy(), X[i, 2:4].copy()))
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
            xe = step(X[i], mode[i], te - t_last[i])  # evaluation point only; the chain continues from t_last
            if min_range <= np.hypot(xe[0], xe[1]) <= max_range:
                ids.append(i)
                pos.append(xe[:2].copy())
                vel.append(xe[2:4].copy())
        evals.append(EvalTruth(k, te, np.array(ids, dtype=np.int64), np.array(pos).reshape(-1, 2),
                               np.array(vel).reshape(-1, 2)))
    return Scenario("synthetic-imm", 0.0, n_scans, scans, evals, {"targets": n_targets})
