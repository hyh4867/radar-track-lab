import numpy as np
import pytest

from radar_track_lab.geo import (
    cart_to_polar,
    enu_to_geodetic,
    geodetic_to_enu,
    local_velocity_to_site_enu,
    polar_to_cart,
    polar_to_cart_cov,
    wrap_pi,
)


def test_azimuth_convention_clockwise_from_north():
    r, az = cart_to_polar([0.0, 1000.0, 0.0, -1000.0], [1000.0, 0.0, -1000.0, 0.0])
    np.testing.assert_allclose(r, 1000.0)
    np.testing.assert_allclose(np.degrees(az), [0.0, 90.0, 180.0, 270.0], atol=1e-9)


def test_polar_cartesian_round_trip():
    rng = np.random.default_rng(0)
    e, n = rng.uniform(-1e5, 1e5, 500), rng.uniform(-1e5, 1e5, 500)
    r, az = cart_to_polar(e, n)
    assert np.all((az >= 0) & (az < 2 * np.pi))
    e2, n2 = polar_to_cart(r, az)
    np.testing.assert_allclose(e2, e, atol=1e-6)
    np.testing.assert_allclose(n2, n, atol=1e-6)


def test_wrap_pi():
    np.testing.assert_allclose(wrap_pi([0.0, 3 * np.pi / 2, -3 * np.pi / 2, 2 * np.pi]), [0, -np.pi / 2, np.pi / 2, 0], atol=1e-12)


def test_polar_cov_cross_range():
    # target due east at 50 km: range error along east, azimuth error along north
    P = polar_to_cart_cov(50_000.0, np.pi / 2, 50.0, np.radians(0.15))
    assert P[0, 0] == pytest.approx(50.0**2)
    assert P[1, 1] == pytest.approx((50_000 * np.radians(0.15)) ** 2)
    assert abs(P[0, 1]) < 1e-6


def test_geodetic_enu_round_trip_and_scale():
    lat0, lon0 = 52.3081, 4.7642
    e, n, u = geodetic_to_enu(52.3081 + 0.5, 4.7642, lat0, lon0)
    assert abs(e) < 1.0
    assert n == pytest.approx(55_660, rel=0.01)  # ~111.3 km per degree of latitude
    lat, lon, h = enu_to_geodetic(30_000.0, -40_000.0, 0.0, lat0, lon0)
    e2, n2, u2 = geodetic_to_enu(lat, lon, lat0, lon0, h=h)
    assert e2 == pytest.approx(30_000.0, abs=1e-3)
    assert n2 == pytest.approx(-40_000.0, abs=1e-3)


def test_velocity_rotation_meridian_convergence():
    lat0, lon0 = 52.3081, 4.7642
    # aircraft 1.5 deg east flying due local north: in the site frame it points slightly west
    ve, vn = local_velocity_to_site_enu(0.0, 200.0, lat0, lon0 + 1.5, lat0, lon0)
    ang = np.degrees(np.arctan2(ve, vn))
    assert ang == pytest.approx(-1.5 * np.sin(np.radians(lat0)), abs=0.05)
    assert np.hypot(ve, vn) == pytest.approx(200.0, rel=1e-4)
