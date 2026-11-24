"""Stage 6 part 2: data-driven floor for JIPDA-amap (docs/PREREGISTRATION_6.md)."""

from __future__ import annotations

import numpy as np
import pytest

from radar_track_lab.jpda import AdaptiveClutterMapDensity, ClutterMapDensity

R0, R1 = 1_000.0, 100_000.0


def _g(frac):
    return AdaptiveClutterMapDensity(R0, R1, 1000.0, 1.5, 30.0, 20.0, floor_frac=frac)


def test_floor_none_is_stage5():
    g = _g(None)
    g.add(np.zeros(0), np.zeros(0))
    assert float(g.density(50_000.0, 1.0)) == pytest.approx(ClutterMapDensity.FLOOR)


def test_empty_map_uses_absolute_minimum():
    g = _g(0.5)
    g.add(np.zeros(0), np.zeros(0))
    assert float(g.density(50_000.0, 1.0)) == pytest.approx(ClutterMapDensity.FLOOR / 10)


def test_floor_is_fraction_of_cap_window():
    g = _g(0.5)
    dr, daz = 1000.0, np.radians(1.5)
    # 1,000 detections in one cell at the window edge; the centre cell's own 3x3..cap windows hold them only at the cap
    r = np.full(1000, R0 + 50.5 * dr + 4 * dr)
    az = np.full(1000, (100.5 + 7) * daz)
    g.add(r, az)
    rc, ac = R0 + 50.5 * dr, 100.5 * daz
    cap = 1000.0 / (9 * 15 * dr * daz)
    assert float(g.density(rc, ac)) == pytest.approx(cap)  # n_min reached only at the cap: cap value (> floor)
    g2 = AdaptiveClutterMapDensity(R0, R1, 1000.0, 1.5, 30.0, 5.0, floor_frac=0.5)
    g2.add(np.concatenate([r, np.full(5, rc)]), np.concatenate([az, np.full(5, ac)]))
    own = 5.0 / (dr * daz)
    assert float(g2.density(rc, ac)) == pytest.approx(max(own, 0.5 * 1005.0 / (9 * 15 * dr * daz)))
    far = float(g2.density(R0 + 20.5 * dr, 30.5 * daz))
    assert far == pytest.approx(ClutterMapDensity.FLOOR / 10)


def test_low_uniform_clutter_tracks_truth_not_fixed_floor():
    rng = np.random.default_rng(3)
    lam = 5.0
    true = lam / ((R1 - R0) * 2 * np.pi)
    fixed, adapt = _g(None), _g(0.5)
    for _ in range(300):
        m = rng.poisson(lam)
        r, az = rng.uniform(R0, R1, m), rng.uniform(0, 2 * np.pi, m)
        fixed.add(r, az)
        adapt.add(r, az)
    assert np.median(fixed.grid()) == pytest.approx(ClutterMapDensity.FLOOR)  # stage 5: about 3x the truth
    assert ClutterMapDensity.FLOOR > 3 * true
    assert np.median(adapt.grid()) / true == pytest.approx(1.0, abs=0.35)
