"""Synthetic scenarios for tests (no ADS-B data needed)."""

from __future__ import annotations

import numpy as np

from radar_track_lab.radar import EvalTruth, RadarParams, ScanTruth
from radar_track_lab.sim import Scenario

BASE_CFG = {
    "radar": {
        "rotation_period_s": 4.8,
        "max_range_m": 100000.0,
        "min_range_m": 1000.0,
        "sigma_r_m": 50.0,
        "sigma_az_deg": 0.15,
        "pd": 1.0,
        "clutter_lambda": 0.0,
        "clutter_model": "uniform_range_azimuth",
    },
    "tracker": {
        "q": 1.0,
        "gate_probability": 0.999,
        "init_speed_sigma_mps": 150.0,
        "confirm_m": 3,
        "confirm_n": 4,
        "delete_misses": 5,
    },
    "baseline": {"max_link_distance_m": 2000.0},
    "eval": {"gospa_c_m": 2000.0, "gospa_p": 2, "gospa_alpha": 2, "warmup_s": 0.0},
}


def straight_line_scenario(p0, v, n_scans=60, T=4.8, t0=0.0):
    """One target in exact straight-line motion; illumination time solved exactly."""
    p0, v = np.asarray(p0, float), np.asarray(v, float)
    omega = 2 * np.pi / T
    scans, evals = [], []
    for k in range(n_scans):
        tk = t0 + k * T
        tc = tk
        for _ in range(5):
            p = p0 + v * (tc - t0)
            az = np.arctan2(p[0], p[1]) % (2 * np.pi)
            tc = tk + az / omega
        p = p0 + v * (tc - t0)
        scans.append(ScanTruth(k, tk, np.array([7]), np.array([tc]), p[None], v[None]))
        te = tk + T
        evals.append(EvalTruth(k, te, np.array([7]), (p0 + v * (te - t0))[None], v[None]))
    return Scenario("line", t0, n_scans, scans, evals)


def radar_from(cfg) -> RadarParams:
    return RadarParams.from_config(cfg)
