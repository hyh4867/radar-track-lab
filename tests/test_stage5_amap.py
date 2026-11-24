"""JIPDA-amap: clutter map with data-driven widening (docs/PREREGISTRATION_5.md 3)."""

from __future__ import annotations

import numpy as np
import pytest

from radar_track_lab.jpda import AdaptiveClutterMapDensity, ClutterMapDensity

R0, R1 = 1_000.0, 100_000.0
DR, DAZ = 1000.0, np.radians(1.5)


def _cell_centre(i, j):
    return R0 + (i + 0.5) * DR, (j + 0.5) * DAZ


def _amap(n_min=5.0, tau=30.0):
    return AdaptiveClutterMapDensity(R0, R1, 1000.0, 1.5, tau, n_min)


def test_cap_half_widths():
    g = _amap()
    assert (g.K_r, g.K_a) == (4, 7)  # 9 km x 22.5 deg fits in the 10 km x 22.5 deg cap
    g2 = AdaptiveClutterMapDensity(R0, R1, 2000.0, 3.0, 30.0, 5.0)
    assert (g2.K_r, g2.K_a) == (2, 3)  # 10 km x 21 deg


def test_widening_stops_at_n_min():
    g = _amap(n_min=5.0, tau=1e12)  # a ~ 1: C = plain counts, N = scans
    i0, j0 = 50, 100
    # 4 detections in the centre cell, 1 more in a 3x3 neighbour, 10 more in a 5x5 neighbour
    pts = [_cell_centre(i0, j0)] * 4 + [_cell_centre(i0 + 1, j0 - 1)] + [_cell_centre(i0 - 2, j0 + 2)] * 10
    r, az = np.array(pts).T
    g.add(r, az)
    rc, ac = _cell_centre(i0, j0)
    assert g.level[i0, j0] == 1  # 1x1 has 4 < 5, 3x3 has 5 >= 5
    assert float(g.density(rc, ac)) == pytest.approx(5.0 / (9 * DR * DAZ))
    h = _amap(n_min=4.0, tau=1e12)
    h.add(r, az)
    assert h.level[i0, j0] == 0 and float(h.density(rc, ac)) == pytest.approx(4.0 / (DR * DAZ))
    k = _amap(n_min=6.0, tau=1e12)
    k.add(r, az)
    assert k.level[i0, j0] == 2 and float(k.density(rc, ac)) == pytest.approx(15.0 / (25 * DR * DAZ))


def test_cap_used_when_short_and_floor_kept():
    g = _amap(n_min=20.0, tau=1e12)
    i0, j0 = 50, 100
    pts = [_cell_centre(i0 + 4, j0 - 7)] * 10 + [_cell_centre(i0 + 5, j0)] * 100  # second one outside the cap
    r, az = np.array(pts).T
    g.add(r, az)
    rc, ac = _cell_centre(i0, j0)
    assert g.level[i0, j0] == 7
    assert float(g.density(rc, ac)) == pytest.approx(10.0 / (9 * 15 * DR * DAZ))  # cap window value (9 km x 22.5 deg)
    e = _amap(n_min=20.0, tau=1e12)
    e.add(np.zeros(0), np.zeros(0))
    assert float(e.density(rc, ac)) == pytest.approx(ClutterMapDensity.FLOOR)


def test_azimuth_wraps_and_range_edge_is_cut():
    g = _amap(n_min=3.0, tau=1e12)
    pts = [_cell_centre(10, 239)] * 3
    r, az = np.array(pts).T
    g.add(r, az)
    rc, ac = _cell_centre(10, 0)
    assert g.level[10, 0] == 1  # neighbour across 0/360 deg
    assert float(g.density(rc, ac)) == pytest.approx(3.0 / (9 * DR * DAZ))
    h = _amap(n_min=3.0, tau=1e12)
    h.add(*np.array([_cell_centre(0, 5)] * 3).T)
    rc, ac = _cell_centre(0, 6)
    assert h.level[0, 6] == 1
    assert float(h.density(rc, ac)) == pytest.approx(3.0 / (6 * DR * DAZ))  # rows -1 cut: 2 x 3 cells


def test_box_sums_match_brute_force():
    rng = np.random.default_rng(0)
    A = rng.random((12, 30))
    for kr, ka in ((0, 0), (1, 2), (3, 5), (4, 7)):
        S = AdaptiveClutterMapDensity._box(A, kr, ka, 7)
        for i in (0, 5, 11):
            for j in (0, 3, 29):
                rows = range(max(0, i - kr), min(12, i + kr + 1))
                cols = [(j + d) % 30 for d in range(-ka, ka + 1)]
                assert S[i, j] == pytest.approx(A[np.ix_(list(rows), cols)].sum())


def test_uniform_synthetic_clutter_converges_to_truth():
    """Uniform clutter at the stage 4 failure level: lambda = 1000 per scan over 99 km x 360 deg."""
    rng = np.random.default_rng(1)
    lam = 1000.0
    true = lam / ((R1 - R0) * 2 * np.pi)
    fine = ClutterMapDensity(R0, R1, 1000.0, 1.5, 30.0)
    amap = {n: _amap(n_min=n, tau=30.0) for n in (5.0, 20.0)}
    for _ in range(300):
        m = rng.poisson(lam)
        r = rng.uniform(R0, R1, m)  # uniform per (m rad), as the uniform clutter model
        az = rng.uniform(0, 2 * np.pi, m)
        fine.add(r, az)
        for g in amap.values():
            g.add(r, az)
    ratio_fine = fine.grid() / true
    for n, g in amap.items():
        ratio = g.grid() / true
        assert np.median(ratio) == pytest.approx(1.0, abs=0.08)
        # the fraction of cells under half the true density is small and far below the fine map's
        assert np.mean(ratio < 0.5) < 0.02
        assert np.mean(ratio < 0.5) < 0.2 * np.mean(ratio_fine < 0.5)
    assert np.mean(ratio_fine < 0.5) > 0.1  # the stage 4 fine map underestimates many cells
    assert np.std(amap[20.0].grid() / true) < np.std(amap[5.0].grid() / true)
