import numpy as np
import pytest

from radar_track_lab.config import with_overrides
from radar_track_lab.metrics import anees_bounds, gospa
from radar_track_lab.radar import simulate_scans
from radar_track_lab.sim import run
from radar_track_lab.truth import Segment, interpolate

from helpers import BASE_CFG, radar_from, straight_line_scenario


def test_gospa_known_values():
    c = 10.0
    X = np.array([[0.0, 0.0], [100.0, 0.0]])
    Y = np.array([[3.0, 4.0]])  # one localised (d=5), one missed
    g = gospa(X, Y, c)
    assert g.n_assigned == 1 and g.n_missed == 1 and g.n_false == 0
    assert g.total == pytest.approx(np.sqrt(25 + c**2 / 2))
    g2 = gospa(np.zeros((0, 2)), Y, c)
    assert g2.n_false == 1 and g2.total == pytest.approx(np.sqrt(c**2 / 2))
    # a pair farther than c counts as one missed + one false
    g3 = gospa(np.array([[0.0, 0.0]]), np.array([[50.0, 0.0]]), c)
    assert (g3.n_missed, g3.n_false, g3.n_assigned) == (1, 1, 0)


def test_same_seed_reproducible_and_different_seed_differs():
    cfg = with_overrides(BASE_CFG, **{"radar.pd": 0.8, "radar.clutter_lambda": 5.0})
    sc = straight_line_scenario(p0=[-20_000.0, 50_000.0], v=[150.0, 20.0], n_scans=50)
    a = simulate_scans(sc.scan_truths, radar_from(cfg), seed=11)
    b = simulate_scans(sc.scan_truths, radar_from(cfg), seed=11)
    c = simulate_scans(sc.scan_truths, radar_from(cfg), seed=12)
    for sa, sb in zip(a, b):
        np.testing.assert_array_equal(sa.r, sb.r)
        np.testing.assert_array_equal(sa.az, sb.az)
        np.testing.assert_array_equal(sa.truth_id, sb.truth_id)
    assert any(sa.r.size != sc_.r.size or not np.array_equal(sa.r, sc_.r) for sa, sc_ in zip(a, c))
    ra = run(sc, cfg, seed=11, method="ekf").summary
    rb = run(sc, cfg, seed=11, method="ekf").summary
    assert ra == rb


def test_clutter_rate_matches_lambda():
    cfg = with_overrides(BASE_CFG, **{"radar.clutter_lambda": 20.0, "radar.pd": 0.0})
    sc = straight_line_scenario(p0=[0.0, 50_000.0], v=[0.0, 0.0], n_scans=400)
    scans = simulate_scans(sc.scan_truths, radar_from(cfg), seed=2)
    n = np.array([s.r.size for s in scans])
    assert n.mean() == pytest.approx(20.0, rel=0.05)
    assert all(np.all(s.truth_id == -1) for s in scans)


def test_hermite_exact_for_constant_acceleration():
    a = np.array([2.0, -1.0])
    t = np.array([0.0, 10.0])
    v0 = np.array([100.0, 50.0])
    pos = np.array([[0.0, 0.0], 10 * v0 + 0.5 * a * 100])
    vel = np.array([v0, v0 + 10 * a])
    seg = Segment(1, t, pos, vel)
    p, v, ok = seg.state(np.array([3.0, 7.5, 12.0]))
    np.testing.assert_allclose(p[0], 3 * v0 + 0.5 * a * 9, atol=1e-9)
    np.testing.assert_allclose(v[1], v0 + 7.5 * a, atol=1e-9)
    assert ok.tolist() == [True, True, False]
    pl, _ = interpolate(t[:1], pos[:1], vel[:1], t[1:], pos[1:], vel[1:], np.array([5.0]), "linear")
    assert np.linalg.norm(pl[0] - (5 * v0 + 0.5 * a * 25)) > 1.0  # linear misses the curvature


def test_anees_bounds_contain_dof():
    lo, hi = anees_bounds(100, dof=4)
    assert lo < 4.0 < hi
    # chi2(400) 2.5% / 97.5% quantiles are about 346 and 457
    assert lo == pytest.approx(3.46, abs=0.02) and hi == pytest.approx(4.57, abs=0.02)
