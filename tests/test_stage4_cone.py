"""Cone-aware track hold (docs/PREREGISTRATION_4.md 9)."""

from __future__ import annotations

import copy

import numpy as np
import pytest
from helpers import BASE_CFG, straight_line_scenario

from radar_track_lab import cone as C
from radar_track_lab.radar import RadarParams, simulate_scans
from radar_track_lab.tracker import CONFIRMED, EKFTracker, TrackerParams


def _cfg():
    c = copy.deepcopy(BASE_CFG)
    c["radar"]["pd"] = 1.0
    c["tracker"]["q"] = 1.0
    c["tracker"]["pregate"] = "adaptive"
    c["sensor"] = {"pd_model": "constant", "geometry": "altitude", "mast_height_m": 20.0, "cone_max_elev_deg": 42.0,
                   "slant_correction": "modec", "modec_step_ft": 100.0, "site_elevation_m": {"EHAM": 0.0}}
    return c


class ConeEKF(C.ConeHoldMixin, EKFTracker):
    pass


def _overflight(alt=10_000.0, n=60):
    # straight line passing 2 km from the radar at 220 m/s
    sc = straight_line_scenario([2_000.0, -30_000.0], [0.0, 220.0], n_scans=n)
    for st in sc.scan_truths:
        st.alt = np.full(st.ids.size, alt)
    return sc


def test_hold_time_formula():
    rc = C.cone_radius(10_020.0, 20.0, 42.0)
    assert rc == pytest.approx(10_000.0 / np.tan(np.radians(42.0)))
    assert C.hold_time(10_020.0, 200.0, 20.0, 42.0) == pytest.approx(2 * rc / 200.0 + 9.6)
    assert C.hold_time(10_020.0, 10.0, 20.0, 42.0) == pytest.approx(2 * rc / 50.0 + 9.6)  # speed floor


def test_with_modec_attaches_quantised_altitude_to_target_reports_only():
    cfg = _cfg()
    cfg["radar"]["clutter_lambda"] = 20.0
    radar = RadarParams.from_config(cfg)
    sc = _overflight(alt=3_333.0, n=5)
    scans = C.with_modec(simulate_scans(sc.scan_truths, radar, 3), sc.scan_truths)
    for s in scans:
        tgt = s.truth_id >= 0
        assert np.all(np.isnan(s.alt[~tgt]))
        assert np.allclose(s.alt[tgt], np.round(3_333.0 / 30.48) * 30.48)


def test_track_held_through_cone_and_not_deleted():
    cfg = _cfg()
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    sc = _overflight()
    scans = C.with_modec(simulate_scans(sc.scan_truths, radar, 1), sc.scan_truths)
    gaps = [k for k, s in enumerate(scans) if s.t.size == 0]
    assert len(gaps) > p.delete_misses  # the cone is longer than the K-miss rule allows
    plain, held = EKFTracker(p), ConeEKF(p)
    held.setup_cone(radar)
    ids_plain, ids_held = set(), set()
    for k, s in enumerate(scans):
        plain.process_scan(s, sc.eval_truths[k].t)
        held.process_scan(s, sc.eval_truths[k].t)
        ids_plain |= set(plain.ids[plain.status == CONFIRMED].tolist())
        ids_held |= set(held.ids[held.status == CONFIRMED].tolist())
    assert len(ids_plain) == 2  # the plain tracker loses the target in the cone and starts again
    assert len(ids_held) == 1  # the held track survives and picks the target up again
    assert held.cone_stats["held_track_scans"] >= len(gaps) - 1


def test_hold_expires_after_t_max():
    cfg = _cfg()
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    sc = _overflight()
    scans = C.with_modec(simulate_scans(sc.scan_truths, radar, 1), sc.scan_truths)
    first_gap = next(k for k, s in enumerate(scans) if s.t.size == 0)
    t = ConeEKF(p)
    t.setup_cone(radar, margin_s=-1e9)  # T_max < 0: never hold -> behaves like the plain tracker
    for k, s in enumerate(scans[: first_gap + p.delete_misses + 1]):
        t.process_scan(s, sc.eval_truths[k].t)
    assert t.cone_stats["held_track_scans"] == 0
    assert not (t.status == CONFIRMED).any()
