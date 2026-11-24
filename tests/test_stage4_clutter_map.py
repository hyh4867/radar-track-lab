"""JIPDA-map clutter map density estimator (docs/PREREGISTRATION_4.md 3)."""

from __future__ import annotations

import numpy as np
import pytest

from radar_track_lab.jpda import ClutterMapDensity
from radar_track_lab.sensor import ClutterMap

R0, R1 = 1_000.0, 100_000.0


def test_cell_boundaries():
    g = ClutterMapDensity(R0, R1, dr=2000.0, daz_deg=3.0, tau=100.0)
    assert (g.n_r, g.n_az) == (50, 120)  # 99 km / 2 km -> 49.5 -> 50 cells, last one 1 km
    i, j = g._cells([R0, R0 + 1999.999, R0 + 2000.0, R1, R1 + 5.0], [0.0, np.radians(2.999), np.radians(3.0),
                                                                        2 * np.pi - 1e-9, 2 * np.pi])
    assert i.tolist() == [0, 0, 1, 49, 49]
    assert j.tolist() == [0, 0, 1, 119, 0]  # 2 pi wraps to cell 0
    assert g.vol[0, 0] == pytest.approx(2000.0 * np.radians(3.0))
    assert g.vol[-1, 0] == pytest.approx(1000.0 * np.radians(3.0))  # partial last range cell
    assert g.vol.sum() == pytest.approx((R1 - R0) * 2 * np.pi)
    g1 = ClutterMapDensity(R0, R1, dr=1000.0, daz_deg=1.5, tau=30.0)
    assert (g1.n_r, g1.n_az) == (99, 240)
    with pytest.raises(ValueError):
        ClutterMapDensity(R0, R1, daz_deg=7.0)


def test_exponential_forgetting_arithmetic():
    tau = 30.0
    a = np.exp(-1.0 / tau)
    g = ClutterMapDensity(R0, R1, dr=1000.0, daz_deg=1.5, tau=tau)
    r, az = np.array([5_500.0]), np.array([0.01])
    vol = 1000.0 * np.radians(1.5)
    counts = [3, 0, 5, 1]
    C = N = 0.0
    for c in counts:
        g.add(np.repeat(r, c), np.repeat(az, c))
        C, N = a * C + c, a * N + 1.0
    assert g.N == pytest.approx(N)
    assert g.density(r, az)[0] == pytest.approx(C / (N * vol))
    # a constant count k per scan gives density k / vol at any time (normalised weights)
    h = ClutterMapDensity(R0, R1, dr=1000.0, daz_deg=1.5, tau=tau)
    for _ in range(7):
        h.add(np.repeat(r, 4), np.repeat(az, 4))
    assert h.density(r, az)[0] == pytest.approx(4.0 / vol)
    # after the source stops, the count decays by a per scan
    h.add(np.zeros(0), np.zeros(0))
    N7 = sum(a ** k for k in range(7))
    assert h.density(r, az)[0] == pytest.approx(4.0 * a * N7 / ((a * N7 + 1.0) * vol))


def test_floor_is_jipda_est_floor_density():
    g = ClutterMapDensity(R0, R1, dr=1000.0, daz_deg=1.5, tau=100.0)
    assert float(g.density(50_000.0, 1.0)) == pytest.approx(1.0 / (1000.0 * np.radians(1.5)))  # nothing seen yet
    g.add(np.zeros(0), np.zeros(0))
    assert float(g.density(50_000.0, 1.0)) == pytest.approx(0.1 / (10_000.0 * 2 * np.pi / 16))


@pytest.mark.parametrize("dr,daz,tau", [(1000.0, 1.5, 30.0), (2000.0, 3.0, 100.0)])
def test_converges_to_true_map_density(dr, daz, tau):
    """Synthetic map clutter (the E3 model, lambda 1000): cell estimates match the cell-averaged true density."""
    cm = ClutterMap.for_site("TEST", R0, R1)
    lam = 1000.0
    rng = np.random.default_rng(1)
    g = ClutterMapDensity(R0, R1, dr=dr, daz_deg=daz, tau=tau)
    for _ in range(int(6 * tau)):
        r, az = cm.sample(rng.poisson(lam), rng)
        g.add(r, az)
    # true cell means by Monte Carlo integration inside each cell
    rr = R0 + (np.arange(g.n_r)[:, None] + rng.random((g.n_r, 64))) * dr
    rr = np.minimum(rr, R1 - 1e-6)
    est = g.grid()
    rel = []
    for i in range(g.n_r):
        aa = (np.arange(g.n_az)[:, None] + rng.random((g.n_az, 64))) * g.daz
        true = cm.density(np.broadcast_to(rr[i][None, :], aa.shape), aa, lam).mean(axis=1)
        expect_count = true * g.vol[i, 0]
        m = expect_count >= 2.0  # cells with enough clutter for a 2-3 % statistical check
        if m.any():
            rel.append((est[i, m] / true[m])[:, None])
    rel = np.concatenate(rel).ravel()
    assert abs(np.median(rel) - 1.0) < 0.05
    # total expected clutter is recovered
    assert (est * g.vol).sum() == pytest.approx(lam, rel=0.03)


def test_uniform_clutter_matches_uniform_density():
    lam = 1000.0
    rng = np.random.default_rng(2)
    g = ClutterMapDensity(R0, R1, dr=2000.0, daz_deg=3.0, tau=100.0)
    for _ in range(600):
        n = rng.poisson(lam)
        g.add(rng.uniform(R0, R1, n), rng.uniform(0, 2 * np.pi, n))
    true = lam / ((R1 - R0) * 2 * np.pi)
    est = g.grid()
    assert np.median(est) == pytest.approx(true, rel=0.03)
