"""Coordinate transforms.

Conventions
-----------
* Local frame: east-north (ENU without the up axis) on the tangent plane at the
  radar site. Positions in metres, shape ``(..., 2)`` as ``[east, north]``.
* Azimuth: radians, clockwise from true north, in ``[0, 2*pi)``.
  ``az = atan2(east, north)``.
* Range: horizontal distance on the tangent plane (the project is 2-D; slant
  range and altitude are ignored, see README "Limitations").
"""

from __future__ import annotations

import numpy as np

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)

TWO_PI = 2.0 * np.pi


def wrap_pi(a):
    """Wrap angle(s) to ``[-pi, pi)``."""
    return (np.asarray(a) + np.pi) % TWO_PI - np.pi


def wrap_2pi(a):
    """Wrap angle(s) to ``[0, 2*pi)``."""
    return np.asarray(a) % TWO_PI


def cart_to_polar(east, north):
    """Return ``(range, azimuth)`` for tangent-plane coordinates."""
    east = np.asarray(east, dtype=float)
    north = np.asarray(north, dtype=float)
    return np.hypot(east, north), wrap_2pi(np.arctan2(east, north))


def polar_to_cart(rng, az):
    """Return ``(east, north)`` for range / azimuth (clockwise from north)."""
    rng = np.asarray(rng, dtype=float)
    az = np.asarray(az, dtype=float)
    return rng * np.sin(az), rng * np.cos(az)


def polar_to_cart_cov(rng, az, sigma_r, sigma_az):
    """Linearised Cartesian covariance of a polar measurement, shape ``(..., 2, 2)``."""
    rng = np.asarray(rng, dtype=float)
    az = np.asarray(az, dtype=float)
    s, c = np.sin(az), np.cos(az)
    # d[east, north]/d[r, az]
    J = np.empty(rng.shape + (2, 2))
    J[..., 0, 0] = s
    J[..., 0, 1] = rng * c
    J[..., 1, 0] = c
    J[..., 1, 1] = -rng * s
    R = np.diag([sigma_r**2, sigma_az**2])
    return J @ R @ np.swapaxes(J, -1, -2)


def geodetic_to_ecef(lat_deg, lon_deg, h=0.0):
    lat = np.radians(np.asarray(lat_deg, dtype=float))
    lon = np.radians(np.asarray(lon_deg, dtype=float))
    h = np.asarray(h, dtype=float)
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
    x = (n + h) * np.cos(lat) * np.cos(lon)
    y = (n + h) * np.cos(lat) * np.sin(lon)
    z = (n * (1.0 - WGS84_E2) + h) * np.sin(lat)
    return x, y, z


def ecef_to_geodetic(x, y, z, iterations: int = 6):
    """Iterative ECEF -> geodetic (degrees, metres)."""
    x, y, z = (np.asarray(v, dtype=float) for v in (x, y, z))
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1.0 - WGS84_E2))
    h = np.zeros_like(p)
    for _ in range(iterations):
        n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))
    return np.degrees(lat), np.degrees(lon), h


def _enu_basis(lat_deg, lon_deg):
    """Unit vectors (east, north, up) in ECEF for each location, shape ``(..., 3)``."""
    lat = np.radians(np.asarray(lat_deg, dtype=float))
    lon = np.radians(np.asarray(lon_deg, dtype=float))
    sl, cl = np.sin(lat), np.cos(lat)
    so, co = np.sin(lon), np.cos(lon)
    e = np.stack([-so, co, np.zeros_like(so)], axis=-1)
    n = np.stack([-sl * co, -sl * so, cl], axis=-1)
    u = np.stack([cl * co, cl * so, sl], axis=-1)
    return e, n, u


def geodetic_to_enu(lat_deg, lon_deg, lat0_deg, lon0_deg, h=0.0, h0=0.0):
    """Geodetic -> local ENU at ``(lat0, lon0, h0)``. Returns ``(east, north, up)``."""
    x, y, z = geodetic_to_ecef(lat_deg, lon_deg, h)
    x0, y0, z0 = geodetic_to_ecef(lat0_deg, lon0_deg, h0)
    d = np.stack([x - x0, y - y0, z - z0], axis=-1)
    e0, n0, u0 = _enu_basis(lat0_deg, lon0_deg)
    return d @ e0, d @ n0, d @ u0


def enu_to_geodetic(east, north, up, lat0_deg, lon0_deg, h0=0.0):
    x0, y0, z0 = geodetic_to_ecef(lat0_deg, lon0_deg, h0)
    e0, n0, u0 = _enu_basis(lat0_deg, lon0_deg)
    east, north, up = (np.asarray(v, dtype=float)[..., None] for v in (east, north, up))
    d = east * e0 + north * n0 + up * u0
    return ecef_to_geodetic(x0 + d[..., 0], y0 + d[..., 1], z0 + d[..., 2])


def local_velocity_to_site_enu(ve_local, vn_local, lat_deg, lon_deg, lat0_deg, lon0_deg):
    """Rotate a velocity given in the aircraft's own east/north axes into the site frame.

    ADS-B ground speed / track are relative to true north at the aircraft. At
    100 km from the site the meridian convergence is about 1.3 deg, so the
    rotation is applied explicitly instead of being ignored.
    """
    e_l, n_l, _ = _enu_basis(lat_deg, lon_deg)
    e0, n0, _ = _enu_basis(lat0_deg, lon0_deg)
    v = np.asarray(ve_local, dtype=float)[..., None] * e_l + np.asarray(vn_local, dtype=float)[..., None] * n_l
    return v @ e0, v @ n0
