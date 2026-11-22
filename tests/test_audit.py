"""Audit fixtures with hand-computed answers (docs/AUDIT_PROTOCOL.md)."""

import numpy as np
import pytest

from radar_track_lab import audit as A
from radar_track_lab.config import with_overrides
from radar_track_lab.metrics import evaluate_scan
from radar_track_lab.radar import EvalTruth
from radar_track_lab.sim import run

from helpers import BASE_CFG, straight_line_scenario


def upd(rows):  # (k, det, truth, t, sq, reason)
    return A.table([r + (1,) for r in rows], A.UPD_FIELDS)


def se(rows):  # (k, truth, t, sq, reason)
    return A.table([r + (1, 0.0) for r in rows], A.SE_FIELDS)


def test_update_common_sample_with_asynchronous_times_and_exclusions():
    # detection times are per detection (0.7 s, 3.1 s, ...), not scan boundaries
    a = upd([(0, 0, 7, 0.7, 100.0, A.USED), (0, 1, 8, 3.1, 400.0, A.USED), (1, 0, 7, 5.2, 900.0, A.USED),
             (1, 2, 9, 8.9, 2500.0, A.UPD_TENTATIVE)])
    b = upd([(0, 0, 7, 0.7, 225.0, A.USED), (1, 0, 7, 5.2, 625.0, A.UPD_WARMUP), (1, 2, 9, 8.9, 49.0, A.USED),
             (2, 0, 7, 10.1, 1.0, A.USED)])
    c = A.common_update(a, b)
    # used by a: (0,0) (0,1) (1,0); used by b: (0,0) (1,2) (2,0); both: (0,0) only
    assert (c["n_a"], c["n_b"], c["n_common"], c["only_a"], c["only_b"]) == (3, 3, 1, 2, 2)
    assert A.rmse(c["sq_a"]) == pytest.approx(10.0) and A.rmse(c["sq_b"]) == pytest.approx(15.0)
    # original (own-sample) RMSEs differ from the common-sample ones
    assert A.rmse(a["sq"][a["reason"] == A.USED]) == pytest.approx(np.sqrt((100 + 400 + 900) / 3))
    assert A.rmse(b["sq"][b["reason"] == A.USED]) == pytest.approx(np.sqrt((225 + 49 + 1) / 3))


def test_scan_end_common_sample_drops_the_hard_pair_and_can_flip_the_comparison():
    # method a keeps a hard target (1000 m error) that method b lost; warm-up rows are not counted
    a = se([(0, 5, 4.8, 1.0, A.SE_WARMUP), (3, 5, 19.2, 100.0, A.USED), (3, 6, 19.2, 100.0, A.USED),
            (4, 6, 24.0, 1_000_000.0, A.USED), (4, 7, 24.0, np.nan, A.SE_UNPAIRED)])
    b = se([(0, 5, 4.8, 1.0, A.SE_WARMUP), (3, 5, 19.2, 400.0, A.USED), (3, 6, 19.2, 400.0, A.USED),
            (4, 6, 24.0, np.nan, A.SE_UNPAIRED), (4, 7, 24.0, np.nan, A.SE_UNPAIRED)])
    c = A.common_scan_end(a, b)
    assert (c["n_truth"], c["n_a"], c["n_b"], c["n_common"], c["only_a"], c["only_b"], c["neither"]) == (4, 3, 2, 2, 1, 0, 1)
    own_a = A.rmse(a["sq"][a["reason"] == A.USED])
    own_b = A.rmse(b["sq"][b["reason"] == A.USED])
    assert own_a == pytest.approx(np.sqrt((100 + 100 + 1_000_000) / 3)) and own_b == pytest.approx(20.0)
    assert own_a > own_b  # on its own samples a looks worse ...
    assert A.rmse(c["sq_a"]) == pytest.approx(10.0) and A.rmse(c["sq_b"]) == pytest.approx(20.0)  # ... on common samples better
    assert A.rmse(c["sq_only_a"]) == pytest.approx(1000.0)  # the dropped hard pair is still reported


def test_duplicate_and_mismatched_keys_are_errors():
    a = upd([(0, 0, 7, 0.7, 1.0, A.USED), (0, 0, 7, 0.7, 2.0, A.USED)])
    with pytest.raises(ValueError, match="duplicate"):
        A.common_update(a, a)
    a = upd([(0, 0, 7, 0.7, 1.0, A.USED)])
    with pytest.raises(ValueError, match="different truth or time"):
        A.common_update(a, upd([(0, 0, 8, 0.7, 1.0, A.USED)]))  # same detection key, other truth target
    with pytest.raises(ValueError, match="different truth or time"):
        A.common_update(a, upd([(0, 0, 7, 0.9, 1.0, A.USED)]))  # same detection key, other time
    s = se([(1, 5, 9.6, 1.0, A.USED)])
    with pytest.raises(ValueError, match="different truth target-scans"):
        A.common_scan_end(s, se([(1, 6, 9.6, 1.0, A.USED)]))
    with pytest.raises(ValueError, match="duplicate"):
        A.common_scan_end(se([(1, 5, 9.6, 1.0, A.USED), (1, 5, 9.6, 1.0, A.USED)]), s)


def test_paired_difference_and_percent_reduction_by_hand():
    d = A.paired_diff([1.0, 2.0, 3.0], [2.0, 4.0, 7.0])  # differences -1, -2, -4
    assert d["mean"] == pytest.approx(-7 / 3) and d["n"] == 3
    half = 4.302652729911275 * np.sqrt(7 / 3) / np.sqrt(3)  # t(0.975, 2) * sd / sqrt(n), sd^2 = 7/3
    assert d["hi"] - d["mean"] == pytest.approx(half) and d["mean"] - d["lo"] == pytest.approx(half)
    assert A.percent_reduction([2.0, 4.0, 7.0], [1.0, 2.0, 3.0]) == pytest.approx(100 * (13 / 3 - 2) / (13 / 3))


def test_unpaired_target_is_excluded_from_the_scan_end_sample():
    # truth 11 has an estimate 500 m away (paired); truth 12 has one 2500 m away, beyond c = 2000 m
    et = EvalTruth(0, 4.8, np.array([11, 12]), np.array([[0.0, 0.0], [10_000.0, 0.0]]), np.zeros((2, 2)))
    ev = evaluate_scan(et, np.array([1, 2]), np.array([[300.0, 400.0], [10_000.0, 2500.0]]), 2000.0)
    assert ev.pair_truth.tolist() == [11] and ev.sq_err.tolist() == [250_000.0]
    assert (ev.gospa.n_missed, ev.gospa.n_false) == (1, 1)
    assert ev.gospa.total == pytest.approx(np.sqrt(250_000.0 + 2000.0**2 / 2 * 2))


@pytest.mark.parametrize("method", ["ekf", "nn", "imm"])
def test_recording_does_not_change_scores_and_reproduces_both_rmses(method):
    from pathlib import Path

    from radar_track_lab.config import load_config

    cfg = with_overrides(BASE_CFG, **{"radar.pd": 0.8, "radar.clutter_lambda": 5.0, "eval.warmup_s": 30.0, "tracker.q": 25.0})
    cfg["imm"] = load_config(Path(__file__).resolve().parents[1] / "configs/stage2.yaml")["imm"]
    sc = straight_line_scenario(p0=[-20_000.0, 50_000.0], v=[150.0, 20.0], n_scans=40)
    off, on = run(sc, cfg, seed=3, method=method), run(sc, cfg, seed=3, method=method, audit=True)
    assert off.audit is None
    for k, v in off.summary.items():
        assert v == on.summary[k] or (v != v and on.summary[k] != on.summary[k]), k
    u, s = on.audit["update"], on.audit["scan_end"]
    assert A.rmse(s["sq"][s["reason"] == A.USED]) == pytest.approx(on.summary["rmse_m"], rel=1e-12)
    assert A.rmse(u["sq"][u["reason"] == A.USED]) == pytest.approx(on.summary["rmse_at_update_m"], rel=1e-12)
    warm = sc.t_start + 30.0
    assert np.all(s["reason"][s["t"] < warm] == A.SE_WARMUP) and not np.any(s["reason"][s["t"] >= warm] == A.SE_WARMUP)
    assert not np.any((u["reason"] == A.USED) & (u["t"] < warm))
    # asynchronous times: an update happens when the beam passes the target, the scan-end sample when the scan ends
    T = 4.8
    n = (s["t"] - sc.t_start) / T
    assert np.allclose(n, np.round(n), atol=1e-9)  # scan-end samples sit on scan boundaries
    n = (u["t"] - sc.t_start) / T
    assert np.all(np.abs(n - np.round(n)) > 1e-3)  # update samples do not
    assert set(np.unique(u["truth"])) <= {7, -1}  # the one target of the fixture or clutter; no other identifier exists


def test_prediction_only_baseline_extrapolates_the_last_two_detections_by_hand():
    from radar_track_lab.tracker import NearestNeighborPredictBaseline, TrackerParams

    class Scan:  # two detections of one target: due east at 10 km, then 480 m further east and 240 m north
        def __init__(self, t, e, n):
            self.t = np.array([t])
            self.r = np.array([np.hypot(e, n)])
            self.az = np.array([np.arctan2(e, n)])
            self.z = np.stack([self.r, self.az], axis=1)

    trk = NearestNeighborPredictBaseline(TrackerParams.from_config(BASE_CFG))
    trk.process_scan(Scan(1.0, 10_000.0, 0.0), 4.8)
    trk.process_scan(Scan(5.8, 10_480.0, 240.0), 9.6)
    # velocity = (480, 240) / 4.8 s = (100, 50) m/s; 2.0 s after the last detection: (10680, 340)
    _, pos, vel = trk.estimates(7.8, confirmed_only=False)
    np.testing.assert_allclose(vel[0], [100.0, 50.0], atol=1e-6)
    np.testing.assert_allclose(pos[0], [10_680.0, 340.0], atol=1e-6)


def test_prediction_only_baseline_shares_the_baseline_association_and_leaves_its_scores_alone():
    cfg = with_overrides(BASE_CFG, **{"radar.pd": 0.9, "radar.clutter_lambda": 5.0})
    sc = straight_line_scenario([-20_000.0, 30_000.0], [180.0, -60.0], n_scans=50)
    nn, nnp = run(sc, cfg, seed=3, method="nn", audit=True), run(sc, cfg, seed=3, method="nnp", audit=True)
    for f in A.UPD_FIELDS:  # same links, same update samples
        np.testing.assert_array_equal(nn.audit["update"][f], nnp.audit["update"][f])
    assert nn.summary["rmse_at_update_m"] == nnp.summary["rmse_at_update_m"]
    assert nn.summary == run(sc, cfg, seed=3, method="nn").summary  # the new method does not touch the baseline
    assert nnp.summary["rmse_m"] < nn.summary["rmse_m"]  # exact straight line: extrapolation must help


def test_three_way_common_scan_end_sample():
    a = se([(3, 5, 19.2, 100.0, A.USED), (3, 6, 19.2, 100.0, A.USED), (4, 6, 24.0, 900.0, A.USED), (0, 5, 4.8, 1.0, A.SE_WARMUP)])
    b = se([(3, 5, 19.2, 400.0, A.USED), (3, 6, 19.2, np.nan, A.SE_UNPAIRED), (4, 6, 24.0, 400.0, A.USED), (0, 5, 4.8, 1.0, A.SE_WARMUP)])
    c = se([(3, 5, 19.2, 25.0, A.USED), (3, 6, 19.2, 25.0, A.USED), (4, 6, 24.0, np.nan, A.SE_UNPAIRED), (0, 5, 4.8, 1.0, A.SE_WARMUP)])
    m = A.common_scan_end_many({"a": a, "b": b, "c": c})
    assert (m["n_truth"], m["n"], m["n_common"], m["none"]) == (3, {"a": 3, "b": 2, "c": 2}, 1, 0)
    assert [A.rmse(m["sq"][k]) for k in "abc"] == pytest.approx([10.0, 20.0, 5.0])


def test_ekf_hold_output_reports_the_last_updated_position_and_shares_the_ekf_updates():
    cfg = with_overrides(BASE_CFG, **{"radar.pd": 0.9, "radar.clutter_lambda": 5.0, "tracker.q": 25.0})
    sc = straight_line_scenario([-20_000.0, 30_000.0], [180.0, -60.0], n_scans=50)
    ekf_, hold = run(sc, cfg, seed=3, method="ekf", audit=True), run(sc, cfg, seed=3, method="ekfh", audit=True)
    for f in A.UPD_FIELDS:  # same filter and association, same update samples
        np.testing.assert_array_equal(ekf_.audit["update"][f], hold.audit["update"][f])
    assert ekf_.summary["rmse_at_update_m"] == hold.summary["rmse_at_update_m"]
    assert ekf_.summary == run(sc, cfg, seed=3, method="ekf").summary  # the new method does not touch the EKF
    # a target at 189.7 m/s seen on average half a revolution before the scan end lags by hundreds of metres
    assert hold.summary["rmse_m"] > 2 * ekf_.summary["rmse_m"]


def test_ekf_hold_output_position_by_hand():
    from radar_track_lab.tracker import EKFHoldOutputTracker, EKFTracker, TrackerParams

    p = TrackerParams.from_config(BASE_CFG)
    a, b = EKFTracker(p), EKFHoldOutputTracker(p)
    for t in (a, b):  # one track: updated at t = 1 s at (10 km, 0) moving (100, 50) m/s
        t.X, t.T = np.array([[10_000.0, 0.0, 100.0, 50.0]]), np.array([1.0])
        t.P, t.ids, t.status = np.eye(4)[None], np.array([1]), np.array([1], dtype=np.int8)
    np.testing.assert_allclose(a.estimates(3.0)[1][0], [10_200.0, 100.0])  # predicted 2 s ahead
    np.testing.assert_allclose(b.estimates(3.0)[1][0], [10_000.0, 0.0])  # held
