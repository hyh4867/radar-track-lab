"""Stage 6: altitude check on every association (G1), Mode C faults, crossing events (docs/PREREGISTRATION_6.md)."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import straight_line_scenario
from test_stage4_cone import _cfg

from radar_track_lab import cone as C
from radar_track_lab import crossing as X
from radar_track_lab.radar import RadarParams
from radar_track_lab.tracker import CONFIRMED, TENTATIVE, EKFTracker, TrackerParams

FT = 0.3048


class V2EKF(C.ConeHoldV2Mixin, EKFTracker):
    pass


def _trk(gate_all):
    cfg = _cfg()
    t = V2EKF(TrackerParams.from_config(cfg))
    t.setup_cone_v2(RadarParams.from_config(cfg), "h1", gate_all=gate_all)
    # three tracks: 0 confirmed with Mode C 3,000 m (level), 1 confirmed without history, 2 tentative with history
    t.ids = np.array([1, 2, 3])
    t.status = np.array([CONFIRMED, CONFIRMED, TENTATIVE], np.int8)
    t.hist = {1: [(90.0, 3000.0), (95.0, 3000.0), (100.0, 3000.0)], 3: [(100.0, 3000.0)]}
    return t


def _scan(alts):
    return SimpleNamespace(alt=np.asarray(alts, float), t=np.full(len(alts), 104.8))


def test_g1_gates_confirmed_tracks_with_history_only():
    w = C.alt_window(4.8)
    alts = [3000.0, 3000.0 + w + 1.0, np.nan, 3000.0 + 2000 * FT]  # in, out, no Mode C, other level
    sc = _scan(alts)
    tr = np.array([0, 0, 0, 0, 1, 1, 2, 2])
    de = np.array([0, 1, 2, 3, 1, 3, 1, 3])
    ok = np.arange(tr.size)
    g = _trk(True)
    kept = g._extra_gate(ok, tr, de, sc).tolist()
    # track 0 keeps the matching report and the report without Mode C; tracks 1 (no history) and 2 (tentative): 2-D only
    assert kept == [0, 2, 4, 5, 6, 7]
    assert g.cone_stats["g1_rejected_pairs"] == 2
    h = _trk(False)  # H1 alone: no gate for tracks that are not held
    assert h._extra_gate(ok, tr, de, sc).tolist() == ok.tolist()


def test_g1_keeps_h1_rule_for_held_tracks():
    g = _trk(True)
    g.check_ids = {1}
    sc = _scan([3000.0, np.nan])
    kept = g._extra_gate(np.arange(2), np.array([0, 0]), np.array([0, 1]), sc).tolist()
    assert kept == [0]  # held / just released: report without Mode C is still refused (H1)


def test_g1_uses_vertical_speed():
    g = _trk(True)
    g.hist = {1: [(float(s), 3000.0 + 10.0 * (s - 100.0)) for s in (85.6, 90.4, 95.2, 100.0)]}  # climbing 10 m/s
    pred = 3000.0 + 10.0 * 4.8
    sc = _scan([pred + C.alt_window(4.8) - 0.5, 3000.0 - C.alt_window(4.8) + 0.5 - 0.0])
    kept = g._extra_gate(np.arange(2), np.array([0, 0]), np.array([0, 1]), sc).tolist()
    assert kept == [0]  # the level-at-3,000 m report is outside the window around the climbing prediction


def test_modec_errors_rates_and_stream():
    rng = np.random.default_rng(0)
    base = float(C.SE.mode_c(3000.0))
    scans = [SimpleNamespace(alt=np.where(rng.random(400) < 0.8, base, np.nan)) for _ in range(100)]
    before = [s.alt.copy() for s in scans]
    C.apply_modec_errors(scans, seed=7)
    fin = np.concatenate([np.isfinite(b) for b in before])
    a = np.concatenate([s.alt for s in scans])
    b = np.concatenate(before)
    assert np.all(np.isnan(a[~fin]))  # clutter stays without Mode C
    miss = np.isnan(a[fin]).mean()
    wrong = (np.isfinite(a[fin]) & (a[fin] != b[fin])).mean()
    assert miss == pytest.approx(0.02, abs=0.004)
    assert wrong == pytest.approx(0.01 * (1 - 1 / 450), abs=0.003)
    assert np.allclose(a[np.isfinite(a)] / (100 * FT), np.round(a[np.isfinite(a)] / (100 * FT)))  # quantised
    again = [SimpleNamespace(alt=x.copy()) for x in before]
    C.apply_modec_errors(again, seed=7)
    assert np.array_equal(np.concatenate([s.alt for s in again]), a, equal_nan=True)  # reproducible per seed


def _two_aircraft(dalt_m, n=80):
    sc = straight_line_scenario([0.0, -20_000.0], [0.0, 100.0], n_scans=n)
    st = sc.scan_truths
    for s in st:  # second aircraft: same track 1 km east, opposite direction -> horizontal distance < 2 km near the middle
        s.ids = np.array([1, 2])
        p2 = np.array([1000.0, 20_000.0 - (s.pos[0, 1] + 20_000.0)])
        s.pos = np.vstack([s.pos[:1], p2])
        s.vel = np.vstack([s.vel[:1], -s.vel[:1]])
        s.alt = np.array([3000.0, 3000.0 + dalt_m])
    return st


def test_crossing_event_detection():
    st = _two_aircraft(1000 * FT + 1.0)
    ev = X.crossing_events(st)
    assert len(ev) == 1
    a, b, k0, k1 = ev[0]
    assert (a, b) == (1, 2)
    d = [np.hypot(*(s.pos[0] - s.pos[1])) for s in st]
    inside = [k for k, x in enumerate(d) if x < 2000.0]
    assert (k0, k1) == (inside[0], inside[-1])
    assert X.crossing_events(_two_aircraft(1000 * FT - 1.0)) == []  # less than 1,000 ft apart: not a crossing
    sw = [{"target": 2, "k_last": k0 - 5, "k_new": k0 - 3}, {"target": 2, "k_last": k0 - 6, "k_new": k0 - 4},
          {"target": 1, "k_last": k1, "k_new": k1 + 1}, {"target": 9, "k_last": k0, "k_new": k0 + 1}]
    assert X.crossing_switches(ev, sw, pad=3) == 2
