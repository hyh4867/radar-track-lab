"""Stage 3 sensor elements against hand-computed values (docs/PREREGISTRATION_3.md 3.3)."""

import numpy as np
import pytest

from radar_track_lab import sensor as SE
from radar_track_lab.radar import RadarParams, ScanTruth, simulate_scan

from helpers import BASE_CFG

A_E = 4.0 / 3.0 * 6_371_000.0


# --- E1 -----------------------------------------------------------------------------------------
def test_swerling1_pd_by_hand():
    # Pd = Pfa^(1/(1+SNR)); Pfa 1e-6, SNR 130.1 (21.14 dB): exp(-13.8155/131.1) = 0.9000
    assert SE.pd_swerling1(130.1, 1e-6) == pytest.approx(0.9, abs=2e-4)
    assert 10 * np.log10(130.1) == pytest.approx(21.14, abs=0.01)
    assert SE.pd_swerling1(0.0, 1e-6) == pytest.approx(1e-6)
    # radar equation: twice the range -> 1/16 of the SNR
    assert SE.snr_at(2e5, 100.0, 1e5) == pytest.approx(100.0 / 16)


def test_swerling1_matches_monte_carlo():
    rng = np.random.default_rng(1)
    pfa, n = 1e-6, 1_000_000
    thr = -np.log(pfa)
    for snr in (5.0, 30.0, 130.1):
        power = rng.exponential(1.0 + snr, n)  # Swerling I: signal + noise power is exponential, noise power = 1
        p = SE.pd_swerling1(snr, pfa)
        assert np.mean(power > thr) == pytest.approx(p, abs=3 * np.sqrt(p * (1 - p) / n))


def test_calibration_by_hand():
    # every range at the reference range: SNR_ref must give Pd = 0.9 there, i.e. ln(Pfa)/ln(0.9) - 1
    want = np.log(1e-6) / np.log(0.9) - 1.0
    assert SE.calibrate_snr_ref(np.full(5, 1e5), 1e-6, 1e5) == pytest.approx(want, rel=1e-6)
    # two ranges: the mean Pd of the solution is 0.9
    s = SE.calibrate_snr_ref(np.array([5e4, 1e5]), 1e-6, 1e5)
    assert np.mean(SE.pd_swerling1(SE.snr_at(np.array([5e4, 1e5]), s, 1e5), 1e-6)) == pytest.approx(0.9, abs=1e-9)


# --- E2 -----------------------------------------------------------------------------------------
def test_horizon_by_hand():
    # Wikipedia "Radar horizon": 1.6 km altitude -> 164 km with 4/3 earth; 23 m -> 19 km
    assert SE.horizon_distance(0.0, 1609.0, A_E) == pytest.approx(165_339, abs=10)
    assert SE.horizon_distance(0.0, 23.0, A_E) == pytest.approx(19_768, abs=5)
    # both heights add: sqrt(2 a h_r) + sqrt(2 a h_t)
    assert SE.horizon_distance(17.0, 1000.0, A_E) == pytest.approx(np.sqrt(2 * A_E * 17) + np.sqrt(2 * A_E * 1000))


def test_slant_and_elevation_against_vector_geometry():
    for d, ht, hr in [(5_000.0, 10_000.0, 0.0), (50_000.0, 3_000.0, 17.0), (99_000.0, 11_000.0, 452.0)]:
        rs, el = SE.slant_and_elevation(d, hr, ht, A_E)
        th = d / A_E
        radar = np.array([0.0, A_E + hr])
        tgt = (A_E + ht) * np.array([np.sin(th), np.cos(th)])
        los = tgt - radar
        assert rs == pytest.approx(np.linalg.norm(los), abs=1e-3)
        # elevation = angle between line of sight and the local horizontal at the radar
        assert np.degrees(el) == pytest.approx(np.degrees(np.arctan2(los[1], los[0])), abs=1e-6)
    _, el = SE.slant_and_elevation(5_000.0, 0.0, 10_000.0, A_E)
    assert np.degrees(el) == pytest.approx(63.43, abs=0.05)  # inside the 42 deg cone of silence
    # 50 km, 3 km: horizontal offset d(1 + h/a_e) = 50,017.7 m, height above the radar's horizontal plane
    # h - d^2/(2 a_e) = 2,852.9 m -> slant 50,099.0 m, i.e. ~9 m longer than the flat sqrt(d^2 + h^2) = 50,089.9 m
    rs, _ = SE.slant_and_elevation(50_000.0, 0.0, 3_000.0, A_E)
    assert rs - np.hypot(50_000.0, 3_000.0) == pytest.approx(9.0, abs=0.4)


def test_slant_to_ground_round_trip_and_mode_c():
    d, hr, ht = 63_210.0, 23.0, 7_315.0
    rs, _ = SE.slant_and_elevation(d, hr, ht, A_E)
    assert SE.ground_from_slant(rs, hr, ht, A_E) == pytest.approx(d, abs=1e-3)
    # Mode C: 1234 m = 4048.6 ft -> 4000 ft = 1219.2 m (ICAO Annex 10 Vol IV 3.1.1.7.12.2.3, 100 ft increments)
    assert SE.mode_c(1234.0) == pytest.approx(1219.2)
    assert SE.mode_c(1234.0, 25.0) == pytest.approx(4050 * 0.3048)


# --- E3 -----------------------------------------------------------------------------------------
def test_clutter_map_fractions_and_near_mean():
    cm = SE.ClutterMap.for_site("EHAM", 1_000.0, 100_000.0)
    rng = np.random.default_rng(3)
    n = 1_000_000
    u_state = np.random.default_rng(3).random(n)
    r, az = cm.sample(n, rng)
    near = u_state < 0.6
    patch = (u_state >= 0.6) & (u_state < 0.9)
    assert near.mean() == pytest.approx(0.6, abs=3 * np.sqrt(0.24 / n))
    assert patch.mean() == pytest.approx(0.3, abs=3 * np.sqrt(0.21 / n))
    # truncated exponential: mean = r_min + L - span e^{-span/L} / (1 - e^{-span/L}) ~ 1 km + 8 km
    span, L = 99_000.0, 8_000.0
    want = 1_000.0 + L - span * np.exp(-span / L) / (1 - np.exp(-span / L))
    sd = L / np.sqrt(near.sum())
    assert r[near].mean() == pytest.approx(want, abs=3 * sd)
    assert (r >= 1_000.0).all() and (r <= 100_000.0).all() and ((az >= 0) & (az < 2 * np.pi)).all()


def test_clutter_map_density_integrates_to_lambda_and_is_fixed_per_site():
    cm = SE.ClutterMap.for_site("EHAM", 1_000.0, 100_000.0)
    rr = np.linspace(1_000.0, 100_000.0, 4_001)
    aa = np.linspace(0.0, 2 * np.pi, 4_001)
    R, A = np.meshgrid(0.5 * (rr[1:] + rr[:-1]), 0.5 * (aa[1:] + aa[:-1]), indexing="ij")
    tot = cm.density(R, A, 200.0).sum() * (rr[1] - rr[0]) * (aa[1] - aa[0])
    assert tot == pytest.approx(200.0, rel=0.01)
    again = SE.ClutterMap.for_site("EHAM", 1_000.0, 100_000.0)
    other = SE.ClutterMap.for_site("EGLL", 1_000.0, 100_000.0)
    assert np.array_equal(cm.patch_r, again.patch_r) and not np.array_equal(cm.patch_r, other.patch_r)


# --- E4 -----------------------------------------------------------------------------------------
def test_merge_groups_by_hand():
    d_r, d_az = 150.0, np.radians(1.4)
    a = np.radians([10.0, 11.0])
    assert len(set(SE.merge_groups(np.array([20_000.0, 20_100.0]), a, d_r, d_az))) == 1  # 100 m, 1.0 deg
    assert len(set(SE.merge_groups(np.array([20_000.0, 20_200.0]), a, d_r, d_az))) == 2  # 200 m apart
    assert len(set(SE.merge_groups(np.array([20_000.0, 20_000.0]), np.radians([10.0, 11.5]), d_r, d_az))) == 2
    # chain: 1-2 and 2-3 close, 1-3 not -> one group (single linkage)
    lab = SE.merge_groups(np.array([20_000.0, 20_120.0, 20_240.0]), np.radians([10.0, 10.0, 10.0]), d_r, d_az)
    assert len(set(lab)) == 1
    # across north (359.6 deg and 0.4 deg)
    assert len(set(SE.merge_groups(np.array([5_000.0, 5_050.0]), np.radians([359.6, 0.4]), d_r, d_az))) == 1


def _params(**kw):
    p = RadarParams.from_config(BASE_CFG)
    from dataclasses import replace

    return replace(p, **kw)


def _scan(pos, alt=None, ids=None):
    pos = np.asarray(pos, float)
    m = pos.shape[0]
    return ScanTruth(0, 0.0, np.arange(1, m + 1) if ids is None else np.asarray(ids), np.linspace(0.1, 0.2, m), pos,
                     np.zeros((m, 2)), None if alt is None else np.asarray(alt, float))


def test_simulate_merge_reports_one_detection_at_the_mean():
    p = _params(merge=True, sigma_r_m=1e-9, sigma_az_rad=1e-12, pd=1.0, clutter_lambda=0.0)
    az = np.radians(30.0)
    pos = [[20_000 * np.sin(az), 20_000 * np.cos(az)], [20_100 * np.sin(az + 0.01), 20_100 * np.cos(az + 0.01)]]
    s = simulate_scan(_scan(pos), p, np.random.default_rng(0))
    assert s.r.size == 1
    assert s.r[0] == pytest.approx(20_050.0, abs=1e-3)
    assert s.az[0] == pytest.approx(az + 0.005, abs=1e-9)


def test_simulate_cone_of_silence_and_slant_correction():
    p = _params(geometry="altitude", antenna_height_m=17.0, sigma_r_m=1e-9, sigma_az_rad=1e-12, pd=1.0,
                clutter_lambda=0.0, modec_step_ft=100.0)
    # overhead (5 km ground, 10 km up) is never detected; a target at 60 km is, and its range is converted to ground
    s = simulate_scan(_scan([[0.0, 5_000.0], [0.0, 60_000.0]], alt=[10_000.0, 3_048.0]), p, np.random.default_rng(0))
    assert s.truth_id.tolist() == [2]
    assert s.r[0] == pytest.approx(60_000.0, abs=1e-3)  # 3048 m = 10,000 ft exactly, so Mode C adds no error
    p2 = _params(geometry="altitude", antenna_height_m=17.0, sigma_r_m=1e-9, sigma_az_rad=1e-12, pd=1.0,
                 clutter_lambda=0.0, slant_correction="none")
    s2 = simulate_scan(_scan([[0.0, 60_000.0]], alt=[3_048.0]), p2, np.random.default_rng(0))
    rs, _ = SE.slant_and_elevation(60_000.0, 17.0, 3_048.0, p2.a_e)
    assert s2.r[0] == pytest.approx(rs, abs=1e-3)


def test_all_elements_off_reproduces_the_stage_1_model():
    cfg = dict(BASE_CFG, radar=dict(BASE_CFG["radar"], pd=0.9, clutter_lambda=5.0))
    a = RadarParams.from_config(cfg)
    b = RadarParams.from_config(dict(cfg, sensor={"pd_model": "constant", "geometry": "flat", "merge": False}))
    st = _scan(np.random.default_rng(9).uniform(-5e4, 5e4, (40, 2)))
    sa = simulate_scan(st, a, np.random.default_rng(5))
    sb = simulate_scan(st, b, np.random.default_rng(5))
    for f in ("t", "r", "az", "truth_id"):
        assert np.array_equal(getattr(sa, f), getattr(sb, f))
