"""Cone hold v2: altitude gate and vertical speed extrapolation (docs/PREREGISTRATION_5.md 9.3)."""

from __future__ import annotations

import numpy as np
import pytest
from test_stage4_cone import _cfg, _overflight

from radar_track_lab import cone as C
from radar_track_lab.radar import RadarParams, simulate_scans
from radar_track_lab.tracker import CONFIRMED, EKFTracker, TrackerParams

FT = 0.3048


class V2EKF(C.ConeHoldV2Mixin, EKFTracker):
    pass


def test_window_constants():
    assert C.alt_window(0.0) == pytest.approx(200 * FT)
    assert C.alt_window(10.0) == pytest.approx((200 + 500) * FT)
    assert C.alt_window(-3.0) == pytest.approx(200 * FT)


def test_vz_estimate_fit_clip_and_short_history():
    t = np.arange(0.0, 30.0, 4.8)
    assert C.vz_estimate(t, 1000.0 + 10.0 * t) == pytest.approx(10.0)
    assert C.vz_estimate(t, 1000.0 - 40.0 * t) == pytest.approx(-100 * FT)  # clipped at 100 ft/s
    assert C.vz_estimate([0.0, 4.8], [0.0, 100.0]) == 0.0  # span < 9.6 s
    assert C.vz_estimate([5.0], [1.0]) == 0.0
    # only the last 30 s are used
    t2 = np.concatenate([[-100.0], t])
    a2 = np.concatenate([[99_999.0], 1000.0 + 10.0 * t])
    assert C.vz_estimate(t2, a2) == pytest.approx(10.0)
    # quantised Mode C (100 ft) of a 25 ft/s climb gives about 25 ft/s
    tt = np.arange(0.0, 30.0, 4.8)
    q = np.round((3000.0 + 25.0 * tt) / 100.0) * 100.0 * FT
    assert C.vz_estimate(tt, q) == pytest.approx(25 * FT, abs=4 * FT)


def test_alt_gate():
    a_last, t_last, vz = 3000.0, 100.0, 5.0
    t = np.array([110.0, 110.0, 110.0, 110.0])
    pred = 3000.0 + 50.0
    w = C.alt_window(10.0)
    rep = np.array([pred + w - 0.01, pred - w + 0.01, pred + w + 0.01, np.nan])
    assert C.alt_gate(rep, a_last, t_last, vz, t).tolist() == [True, True, False, False]
    assert C.predicted_alt(a_last, t_last, vz, 110.0) == pytest.approx(pred)


def _tracker(variant):
    cfg = _cfg()
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    t = V2EKF(p)
    t.setup_cone_v2(radar, variant)
    return t, radar, p


def test_h1_holds_through_cone_like_stage4():
    t, radar, p = _tracker("h1")
    sc = _overflight()
    scans = C.with_modec(simulate_scans(sc.scan_truths, radar, 1), sc.scan_truths)
    ids = set()
    for k, s in enumerate(scans):
        t.process_scan(s, sc.eval_truths[k].t)
        ids |= set(t.ids[t.status == CONFIRMED].tolist())
    assert len(ids) == 1
    assert t.cone_stats["held_track_scans"] > 0 and t.cone_stats["held_updates"] >= 1
    assert not t.check_ids  # released after the first update outside the cone


def test_h1_gate_rejects_other_altitude_and_clutter():
    t, radar, p = _tracker("h1")
    sc = _overflight()
    scans = C.with_modec(simulate_scans(sc.scan_truths, radar, 1), sc.scan_truths)
    first_gap = next(k for k, s in enumerate(scans) if s.t.size == 0)
    for k, s in enumerate(scans[:first_gap + 1]):
        t.process_scan(s, sc.eval_truths[k].t)
    assert t.check_ids  # held now
    # the reports after the cone carry a wrong Mode C (20,000 ft off: outside even the widened window) or none: the held track must not take them
    trk_id = next(iter(t.check_ids))
    k_exit = next(k for k in range(first_gap, len(scans)) if scans[k].t.size)
    for k in range(first_gap + 1, k_exit + 1):
        s = scans[k]
        s.alt = s.alt + 20_000 * FT if k == k_exit else s.alt
        rec = t.process_scan(s, sc.eval_truths[k].t)
        assert all(r[0] != trk_id for r in rec)
    assert t.cone_stats["gate_rejected_pairs"] >= 1
    s = scans[k_exit + 1]
    s.alt = np.full(s.t.size, np.nan)  # no Mode C at all
    rec = t.process_scan(s, sc.eval_truths[k_exit + 1].t)
    assert all(r[0] != trk_id for r in rec)


def test_h2_extrapolates_altitude_for_cone_entry():
    """A climbing aircraft 4 km from the radar: its last Mode C (3,600 m) puts it just outside the 42 deg cone, its
    extrapolated altitude (climbing 30 m/s, about 4,350 m some 25 s later) inside. H1 does not hold it, H2 does."""
    t1, radar, p = _tracker("h1")
    t2, _, _ = _tracker("h2")
    for t in (t1, t2):
        t.X = np.array([[4_000.0, 0.0, 0.0, 1.0]])
        t.P = np.eye(4)[None] * 100.0
        t.T = np.array([60.0])
        t.ids = np.array([1])
        t.status = np.array([CONFIRMED], np.int8)
        t.hits = np.array([3], np.int32)
        t.scans = np.array([3], np.int32)
        t.misses = np.array([0], np.int32)
        t.n_upd = np.array([3], np.int32)
        t.hist = {1: [(float(s), 1800.0 + 30.0 * s) for s in np.arange(31.2, 60.1, 4.8)]}  # last: t=60, 3,600 m
        t.alt_by_id = {1: t.hist[1][-1][1]}
    assert C.vz_estimate(*zip(*t2.hist[1])) == pytest.approx(30.0)
    h = 3_600.0 - radar.antenna_height_m
    assert np.degrees(np.arctan2(h, 4_000.0)) < 42.0  # flat-earth check: outside with the last Mode C

    class S:
        t0 = 85.0

    assert not t1.held_mask(S)[0]
    assert t2.held_mask(S)[0]
