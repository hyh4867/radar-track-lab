import numpy as np
import pytest

from radar_track_lab import ekf
from radar_track_lab.config import with_overrides
from radar_track_lab.radar import Scan
from radar_track_lab.sim import run
from radar_track_lab.tracker import CONFIRMED, TENTATIVE, EKFTracker, MofN, TrackerParams, assign

from helpers import BASE_CFG, straight_line_scenario


def test_single_target_straight_line_converges():
    sc = straight_line_scenario(p0=[-40_000.0, 30_000.0], v=[180.0, -60.0], n_scans=80)
    cfg = with_overrides(BASE_CFG, **{"eval.warmup_s": 150.0})
    res = run(sc, cfg, seed=1, method="ekf", record=True)
    s = res.summary
    assert s["false_tracks_per_scan"] == 0
    assert s["missed_per_scan"] == 0
    assert s["id_switches"] == 0
    # after convergence the error is well below the raw cross-range noise
    raw_cross = 50_000 * np.radians(0.15)  # ~131 m at the target range
    assert s["rmse_m"] < 0.6 * raw_cross
    snap = res.snapshots[-1]
    assert snap["confirmed"].sum() == 1
    v_est = snap["track_vel"][snap["confirmed"]][0]
    np.testing.assert_allclose(v_est, [180.0, -60.0], atol=5.0)


def test_ekf_reduces_error_vs_raw_measurement():
    sc = straight_line_scenario(p0=[0.0, 60_000.0], v=[200.0, 0.0], n_scans=80)
    cfg = with_overrides(BASE_CFG, **{"eval.warmup_s": 120.0})
    ekf_rmse = run(sc, cfg, seed=3, method="ekf").summary["rmse_m"]
    nn_rmse = run(sc, cfg, seed=3, method="nn").summary["rmse_m"]
    assert ekf_rmse < 0.5 * nn_rmse


def _params(**kw):
    base = dict(
        q=1.0, gate_probability=0.99, init_speed_sigma_mps=150.0, confirm_m=3, confirm_n=4,
        delete_misses=3, sigma_r_m=50.0, sigma_az_rad=np.radians(0.15), max_range_m=1e5,
    )
    base.update(kw)
    return TrackerParams(**base)


def test_gate_threshold_and_mahalanobis():
    p = _params(gate_probability=0.99)
    assert p.gate_threshold == pytest.approx(9.2103, abs=1e-3)
    nu = np.array([[3.0, 0.0], [0.0, 0.0]])
    S = np.tile(np.eye(2), (2, 1, 1))
    np.testing.assert_allclose(ekf.mahalanobis2(nu, S), [9.0, 0.0])


def test_gating_rejects_far_detection():
    p = _params(gate_probability=0.99)
    trk = EKFTracker(p)
    # confirmed track at (0, 50 km) moving east 100 m/s, small covariance
    trk._append(np.array([[0.0, 50_000.0, 100.0, 0.0]]), np.diag([30.0**2, 30.0**2, 5.0**2, 5.0**2])[None], np.array([0.0]))
    trk.status[:] = CONFIRMED
    from radar_track_lab.geo import cart_to_polar
    sig_cross = 50_000 * np.radians(0.15)
    near = cart_to_polar(480.0 + 0.5 * sig_cross, 50_000.0)  # inside gate after 4.8 s
    far = cart_to_polar(480.0 + 8 * sig_cross, 50_000.0)  # far outside
    for (r, az), expect in ((near, True), (far, False)):
        t = trk_copy = EKFTracker(p)
        trk_copy._append(trk.X.copy(), trk.P.copy(), trk.T.copy())
        trk_copy.status[:] = CONFIRMED
        scan = Scan(1, 0.0, np.array([4.8]), np.array([float(r)]), np.array([float(az)]), np.array([0]))
        recs = t.process_scan(scan, 9.6)
        assert (len(recs) == 1) is expect


def test_hungarian_assignment_global_optimum():
    # greedy row-wise would take (0,0)=1 then (1,1)=10 -> 11; optimum is (0,1)+(1,0)=2+3=5
    cost = np.array([[1.0, 2.0], [3.0, 10.0]])
    r, c = assign(cost)
    assert sorted(zip(r.tolist(), c.tolist())) == [(0, 1), (1, 0)]
    # forbidden pairs (>= BIG) are dropped, rectangular input allowed
    from radar_track_lab.tracker import BIG
    cost = np.array([[BIG, 1.0, BIG], [BIG, BIG, BIG]])
    r, c = assign(cost)
    assert list(zip(r.tolist(), c.tolist())) == [(0, 1)]


def test_m_of_n_confirmation_and_deletion():
    m = MofN(3, 4, 2)
    st = np.array([TENTATIVE]); hits = np.array([1]); scans = np.array([1]); miss = np.array([0])
    # hit, miss, hit -> 3 hits in 4 scans -> confirmed
    for h in (True, False, True):
        st, hits, scans, miss, keep = m.step(st, hits, scans, miss, np.array([h]))
        assert keep.all()
    assert st[0] == CONFIRMED
    # two consecutive misses delete a confirmed track (K = 2)
    st, hits, scans, miss, keep = m.step(st, hits, scans, miss, np.array([False]))
    assert keep.all()
    st, hits, scans, miss, keep = m.step(st, hits, scans, miss, np.array([False]))
    assert not keep.any()
    # tentative: miss, miss -> cannot reach 3 of 4 any more -> deleted
    st = np.array([TENTATIVE]); hits = np.array([1]); scans = np.array([1]); miss = np.array([0])
    st, hits, scans, miss, keep = m.step(st, hits, scans, miss, np.array([False]))
    assert keep.all()
    st, hits, scans, miss, keep = m.step(st, hits, scans, miss, np.array([False]))
    assert not keep.any()


def test_track_ids_persist_and_are_not_reused():
    sc = straight_line_scenario(p0=[10_000.0, 40_000.0], v=[0.0, 150.0], n_scans=40)
    res = run(sc, BASE_CFG, seed=5, method="ekf", record=True)
    conf_ids = {int(i) for s in res.snapshots for i in s["track_ids"][s["confirmed"]]}
    assert len(conf_ids) == 1


def test_componentwise_assignment_matches_dense_solve():
    from scipy.optimize import linear_sum_assignment

    from radar_track_lab.tracker import BIG, assign_pairs

    rng = np.random.default_rng(7)
    for _ in range(200):
        n, m = rng.integers(1, 12, size=2)
        cost = np.where(rng.random((n, m)) < 0.25, rng.uniform(-5, 20, (n, m)), BIG)
        r0, c0 = linear_sum_assignment(cost)
        ok0 = cost[r0, c0] < BIG
        r, c = np.nonzero(cost < BIG)
        sel = assign_pairs(n, m, r, c, cost[r, c])
        assert sel.size == ok0.sum()  # same number of gated assignments
        assert cost[r[sel], c[sel]].sum() == pytest.approx(cost[r0[ok0], c0[ok0]].sum())
        assert len(set(r[sel])) == sel.size and len(set(c[sel])) == sel.size
