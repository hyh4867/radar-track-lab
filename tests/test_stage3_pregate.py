"""Stage 3, B0: the adaptive pre-gate must not drop any pair the chi-square gate would accept."""

import numpy as np
import pytest

from radar_track_lab.config import with_overrides
from radar_track_lab.sim import run
from radar_track_lab.synthetic import imm_model_scenario, ncv_scenario
from radar_track_lab.tracker import TrackerParams, pregate_radius

from helpers import BASE_CFG

IMM_CFG = {"q_cv": 25.0, "q_ct": 25.0, "omega_noise_dps": 0.3, "tau_cv_s": 300.0, "tau_ct_s": 40.0,
           "omega_prior_sigma_dps": 3.0, "cv_omega_sigma_dps": 3.0}


def _cfg(pregate, lam, pd=0.9, q=25.0):
    c = with_overrides(BASE_CFG, **{"radar.clutter_lambda": lam, "radar.pd": pd, "tracker.q": q})
    c["tracker"]["pregate"] = pregate
    c["imm"] = dict(IMM_CFG)
    return c


def _same(a, b):
    assert a.summary == b.summary
    for sa, sb in zip(a.snapshots, b.snapshots):
        assert np.array_equal(sa["track_ids"], sb["track_ids"])
        assert np.array_equal(sa["track_pos"], sb["track_pos"])


@pytest.mark.parametrize("lam", [5.0, 200.0])
def test_adaptive_pregate_equals_no_pregate_ekf(lam):
    sc = ncv_scenario(30, 60, 4.8, 25.0, 150.0, seed=11, r_min=2_000.0, r_max=60_000.0)
    for seed in (1, 2):
        a = run(sc, _cfg("adaptive", lam), seed=seed, method="ekf", record=True)
        b = run(sc, _cfg("none", lam), seed=seed, method="ekf", record=True)
        _same(a, b)


def test_adaptive_pregate_equals_no_pregate_imm():
    from radar_track_lab.imm import IMMParams

    imm = IMMParams.from_config({"imm": IMM_CFG})
    sc = imm_model_scenario(20, 60, 4.8, imm, 150.0, seed=5)
    for seed in (1, 2):
        a = run(sc, _cfg("adaptive", 200.0), seed=seed, method="imm", record=True)
        b = run(sc, _cfg("none", 200.0), seed=seed, method="imm", record=True)
        _same(a, b)


def test_pregate_radius_by_hand():
    p = TrackerParams.from_config(with_overrides(_cfg("adaptive", 0.0), **{"tracker.q": 25.0}))
    P = np.zeros((1, 4, 4))
    P[0, :2, :2] = np.diag([100.0**2, 50.0**2])
    P[0, 2:, 2:] = np.diag([10.0**2, 20.0**2])
    dt = 4.0
    # std bound 100 + 4*20 = 180 m; process noise 25*64/3; worst measurement variance (1e5 m * 0.15 deg)^2
    var = 180.0**2 + 25.0 * dt**3 / 3 + (1e5 * np.radians(0.15)) ** 2
    want = 1.5 * np.sqrt(p.gate_threshold * var) + 500.0
    assert pregate_radius(P, np.array([0.0]), dt, p)[0] == pytest.approx(want)


def test_fixed_6km_drops_a_gated_pair_that_adaptive_keeps():
    """A tentative track (speed sigma 150 m/s) that missed one scan: the gate reaches past 6 km."""
    p = TrackerParams.from_config(with_overrides(_cfg("adaptive", 0.0), **{"tracker.q": 25.0}))
    P = np.zeros((1, 4, 4))
    P[0, :2, :2] = np.eye(2) * 60.0**2
    P[0, 2:, 2:] = np.eye(2) * 150.0**2
    r = pregate_radius(P, np.array([0.0]), 9.6, p)[0]
    gate_1sigma = 150.0 * 9.6  # velocity spread alone after two revolutions
    assert np.sqrt(p.gate_threshold) * gate_1sigma > 5_000.0  # the chi-square gate reaches about 5.4 km on one axis
    assert r > 6_000.0
