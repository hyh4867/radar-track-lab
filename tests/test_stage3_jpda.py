"""Stage 3 B1: JPDA / JIPDA against hand computation (docs/PREREGISTRATION_3.md 4.2)."""

import itertools

import numpy as np
import pytest

from radar_track_lab.config import with_overrides
from radar_track_lab.jpda import GridDensity, marginals_exact, marginals_lbp
from radar_track_lab.sim import run
from radar_track_lab.synthetic import ncv_scenario

from helpers import BASE_CFG


def brute(w0, W):
    """Joint events by itertools.product, independent of the recursive enumeration."""
    n, m = W.shape
    B, b0, tot = np.zeros((n, m)), np.zeros(n), 0.0
    for ch in itertools.product(*[[-1] + list(np.flatnonzero(W[i] > 0)) for i in range(n)]):
        js = [j for j in ch if j >= 0]
        if len(js) != len(set(js)):
            continue
        wt = np.prod([w0[i] if j < 0 else W[i, j] for i, j in enumerate(ch)])
        tot += wt
        for i, j in enumerate(ch):
            if j < 0:
                b0[i] += wt
            else:
                B[i, j] += wt
    return b0 / tot, B / tot


def test_two_tracks_one_shared_detection_by_hand():
    # tracks 1, 2; detection a gated by both. Events: (0,0) w01 w02, (a,0) Wa1 w02, (0,a) w01 Wa2
    w0 = np.array([0.1, 0.2])
    W = np.array([[3.0], [5.0]])
    tot = 0.1 * 0.2 + 3.0 * 0.2 + 0.1 * 5.0
    b0, B = marginals_exact(w0, W)
    assert B[0, 0] == pytest.approx(3.0 * 0.2 / tot)
    assert B[1, 0] == pytest.approx(0.1 * 5.0 / tot)
    assert b0[0] == pytest.approx((0.1 * 0.2 + 0.1 * 5.0) / tot)


def test_exact_matches_brute_force_and_lbp_is_close():
    rng = np.random.default_rng(4)
    for _ in range(20):
        n, m = rng.integers(2, 6), rng.integers(2, 6)
        W = rng.exponential(1.0, (n, m)) * (rng.random((n, m)) < 0.6)
        w0 = rng.uniform(0.05, 1.0, n)
        b0, B = marginals_exact(w0, W)
        c0, C = brute(w0, W)
        assert np.allclose(B, C, atol=1e-12) and np.allclose(b0, c0, atol=1e-12)
        assert np.allclose(B.sum(axis=1) + b0, 1.0)
        l0, L, _ = marginals_lbp(w0, W)
        assert np.max(np.abs(L - B)) < 0.08  # BP is approximate on loopy graphs
    # on a tree (one track) BP is exact
    w0, W = np.array([0.3]), np.array([[1.0, 2.0, 0.5]])
    l0, L, _ = marginals_lbp(w0, W)
    assert np.allclose(L, W / (0.3 + 3.5)) and l0[0] == pytest.approx(0.3 / 3.8)


def test_single_track_jipda_reduces_to_ipda():
    """Musicki IPDA: delta = PdPg (1 - sum_j g_j / rho_j), g_j = N_j / Pg; E+ = (1 - delta) E- / (1 - delta E-)."""
    pd, pg, Em = 0.9, 0.999, 0.4
    N = np.array([2e-7, 5e-8])  # Gaussian densities of two gated detections
    rho = np.array([1e-7, 1e-7])
    w = pd * Em * N / rho
    w0 = 1 - pd * pg * Em
    tot = w0 + w.sum()
    beta, beta0 = w / tot, w0 / tot
    E_jipda = beta.sum() + beta0 * Em * (1 - pd * pg) / w0
    delta = pd * pg * (1 - np.sum((N / pg) / rho))
    E_ipda = (1 - delta) * Em / (1 - delta * Em)
    assert E_jipda == pytest.approx(E_ipda, rel=1e-12)


def test_pda_update_reduces_to_kalman_with_one_certain_detection():
    """beta0 = 0, one detection with beta 1: the PDA covariance is the EKF covariance (no spread term)."""
    from radar_track_lab import ekf

    x = np.array([[10_000.0, 20_000.0, 100.0, -50.0]])
    P = np.diag([400.0, 400.0, 100.0, 100.0])[None]
    R = np.diag([50.0**2, np.radians(0.15) ** 2])
    z = np.array([[np.hypot(10_050.0, 20_010.0), np.arctan2(10_050.0, 20_010.0)]])
    xk, Pk, nu, S = ekf.update(x, P, z, R)
    _, H = ekf.h_polar(x)
    K = P @ np.swapaxes(H, 1, 2) @ np.linalg.inv(S)
    IKH = np.eye(4)[None] - K @ H
    Pc = IKH @ P @ np.swapaxes(IKH, 1, 2) + K @ R @ np.swapaxes(K, 1, 2)
    assert np.allclose(Pc, Pk) and np.allclose(x + np.einsum("nij,nj->ni", K, nu), xk)


def test_grid_density_floor_and_average():
    g = GridDensity(1_000.0, 101_000.0, dr=10_000.0, n_az=16, window=10)
    vol = 10_000.0 * 2 * np.pi / 16
    assert g.density(5_000.0, 0.1) == pytest.approx(1.0 / vol)  # nothing seen yet: floor 1 per cell
    for _ in range(10):
        g.add(np.array([5_000.0] * 4), np.array([0.1] * 4))
    assert g.density(5_000.0, 0.1) == pytest.approx(4.0 / vol)  # 4 per scan
    assert g.density(55_000.0, 3.0) == pytest.approx(0.1 / vol)  # floor: 1 per 10 scans


def _cfg(lam, mode_cfg=None):
    c = with_overrides(BASE_CFG, **{"radar.clutter_lambda": lam, "radar.pd": 0.9, "tracker.q": 25.0})
    c["tracker"]["pregate"] = "adaptive"
    c["jipda"] = mode_cfg or {"p0": 0.05, "confirm": 0.95, "delete": 0.01}
    return c


@pytest.mark.parametrize("method", ["jpda", "jipda"])
def test_trackers_follow_ncv_targets(method):
    sc = ncv_scenario(10, 60, 4.8, 25.0, 150.0, seed=3)
    r = run(sc, _cfg(5.0), seed=1, method=method)
    s = r.summary
    assert s["missed_per_scan"] < 1.5 and s["false_tracks_per_scan"] < 1.0 and s["rmse_m"] < 300.0


def test_jipda_rejects_dense_clutter_better_than_gnn():
    sc = ncv_scenario(10, 40, 4.8, 25.0, 150.0, seed=3)
    g = run(sc, _cfg(500.0), seed=1, method="ekf").summary
    j = run(sc, _cfg(500.0), seed=1, method="jipda").summary
    assert j["false_tracks_per_scan"] < g["false_tracks_per_scan"]


def test_jipda_with_certain_existence_equals_jpda():
    """E = 1 and p_s = 1: the JIPDA weights, marginals and update are those of JPDA."""
    from radar_track_lab.radar import RadarParams, simulate_scans
    from radar_track_lab.sim import make_tracker
    from radar_track_lab.tracker import TrackerParams

    c = _cfg(200.0, {"p0": 1.0, "confirm": 0.5, "delete": 0.0, "p_survive": 1.0})
    sc = ncv_scenario(8, 12, 4.8, 25.0, 150.0, seed=2)
    scans = simulate_scans(sc.scan_truths, RadarParams.from_config(c), 3)
    a = make_tracker("jpda", TrackerParams.from_config(c), c)
    b = make_tracker("jipda", TrackerParams.from_config(c), c)
    a.keep_last = b.keep_last = True
    for k, s in enumerate(scans[:6]):
        b.X, b.P, b.T, b.ids, b.E = a.X.copy(), a.P.copy(), a.T.copy(), a.ids.copy(), np.ones(a.ids.size)
        for f in ("status", "hits", "scans", "misses", "n_upd"):
            setattr(b, f, getattr(a, f).copy())
        a.process_scan(s, sc.eval_truths[k].t)
        b.process_scan(s, sc.eval_truths[k].t)
        if a.last is None:
            continue
        assert np.allclose(a.last["assoc"]["beta"], b.last["assoc"]["beta"])
        assert np.allclose(a.last["x"], b.last["x"]) and np.allclose(a.last["P"], b.last["P"])
        assert np.allclose(b.last["E_post"], 1.0)
