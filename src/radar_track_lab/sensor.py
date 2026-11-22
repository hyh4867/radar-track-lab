"""Stage 3 sensor elements (docs/PREREGISTRATION_3.md 3.1). Pure functions, unit-tested by hand.

E1  Swerling I detection: one exponentially distributed power sample per target per scan,
    square-law detection with threshold set by the false-alarm probability:
        Pd = P(power > T) = exp(-T / (1 + SNR)),  P_fa = exp(-T)  =>  Pd = P_fa ** (1 / (1 + SNR)).
    SNR(R) = SNR_ref * (R_ref / R)^4 (radar equation, same mean RCS for every target).
E2  4/3-earth geometry: slant range, elevation angle, radar horizon, slant -> ground conversion.
E3  Non-uniform clutter map: near-range exponential + fixed patches + uniform remainder.
E4  Merge of detections that share a resolution cell (range difference < dR and azimuth difference < dAz).
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from .geo import TWO_PI, wrap_pi

EARTH_RADIUS_M = 6_371_000.0
FT = 0.3048


# --- E1 ---------------------------------------------------------------------------------------
def pd_swerling1(snr, pfa: float):
    """Single-sample Swerling I detection probability for linear SNR."""
    snr = np.asarray(snr, dtype=float)
    return np.power(pfa, 1.0 / (1.0 + np.maximum(snr, 0.0)))


def snr_at(r_m, snr_ref: float, r_ref_m: float):
    r = np.maximum(np.asarray(r_m, dtype=float), 1.0)
    return snr_ref * (r_ref_m / r) ** 4


def calibrate_snr_ref(r_m, pfa: float, r_ref_m: float, mean_pd: float = 0.9) -> float:
    """SNR at ``r_ref_m`` such that the mean Pd over the ranges ``r_m`` equals ``mean_pd`` (bisection in log SNR)."""
    r_m = np.asarray(r_m, dtype=float)
    f = lambda s: float(np.mean(pd_swerling1(snr_at(r_m, s, r_ref_m), pfa))) - mean_pd  # noqa: E731
    lo, hi = 1e-3, 1e9
    if f(lo) > 0 or f(hi) < 0:
        raise ValueError("mean Pd target not bracketed")
    for _ in range(200):
        mid = np.sqrt(lo * hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return float(np.sqrt(lo * hi))


# --- E2 ---------------------------------------------------------------------------------------
def effective_radius(k: float = 4.0 / 3.0) -> float:
    return k * EARTH_RADIUS_M


def horizon_distance(h_radar_m, h_target_m, a_e: float):
    """Ground distance to the radar horizon: sqrt(2 a_e h_r) + sqrt(2 a_e h_t) (heights clipped at 0)."""
    return np.sqrt(2 * a_e * np.maximum(h_radar_m, 0.0)) + np.sqrt(2 * a_e * np.maximum(np.asarray(h_target_m, float), 0.0))


def slant_and_elevation(d_m, h_radar_m, h_target_m, a_e: float):
    """Slant range and elevation angle [rad] on a sphere of radius ``a_e`` for ground (arc) distance ``d_m``."""
    d = np.asarray(d_m, dtype=float)
    ra, rt = a_e + h_radar_m, a_e + np.asarray(h_target_m, dtype=float)
    th = d / a_e
    rs = np.sqrt(np.maximum(ra**2 + rt**2 - 2 * ra * rt * np.cos(th), 0.0))
    sin_el = (rt**2 - ra**2 - rs**2) / (2 * ra * np.maximum(rs, 1e-9))
    return rs, np.arcsin(np.clip(sin_el, -1.0, 1.0))


def ground_from_slant(rs_m, h_radar_m, h_target_m, a_e: float):
    """Inverse of ``slant_and_elevation`` for the distance: arc length from slant range and both heights."""
    rs = np.asarray(rs_m, dtype=float)
    ra, rt = a_e + h_radar_m, a_e + np.asarray(h_target_m, dtype=float)
    c = (ra**2 + rt**2 - rs**2) / (2 * ra * rt)
    return a_e * np.arccos(np.clip(c, -1.0, 1.0))


def mode_c(alt_m, step_ft: float = 100.0):
    """Mode C pressure altitude: reported in ``step_ft`` increments (ICAO Annex 10 Vol IV 3.1.1.7.12.2.3)."""
    return np.round(np.asarray(alt_m, dtype=float) / (step_ft * FT)) * step_ft * FT


# --- E3 ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ClutterMap:
    r_min: float
    r_max: float
    near_frac: float
    near_scale_m: float
    patch_frac: float
    patch_r: np.ndarray  # (n,) centres [m]
    patch_az: np.ndarray  # (n,) centres [rad]
    patch_dr: float
    patch_daz: float

    @classmethod
    def for_site(cls, key: str, r_min, r_max, near_frac=0.6, near_scale_m=8000.0, patch_frac=0.3, n_patches=6,
                 patch_r_range=(5000.0, 40000.0), patch_dr=4000.0, patch_daz_deg=3.0):
        rng = np.random.default_rng(zlib.crc32(key.encode("utf-8")))
        pr = rng.uniform(*patch_r_range, n_patches)
        pa = rng.uniform(0.0, TWO_PI, n_patches)
        return cls(float(r_min), float(r_max), near_frac, near_scale_m, patch_frac, pr, pa, patch_dr,
                   float(np.radians(patch_daz_deg)))

    @property
    def uniform_frac(self) -> float:
        return 1.0 - self.near_frac - self.patch_frac

    def _near_norm(self) -> float:
        return 1.0 - np.exp(-(self.r_max - self.r_min) / self.near_scale_m)

    def sample(self, n: int, rng: np.random.Generator):
        """``n`` clutter points (range, azimuth)."""
        u = rng.random(n)
        comp = np.where(u < self.near_frac, 0, np.where(u < self.near_frac + self.patch_frac, 1, 2))
        r = np.empty(n)
        az = np.empty(n)
        m = comp == 0
        k = int(m.sum())
        r[m] = self.r_min - self.near_scale_m * np.log(1.0 - rng.random(k) * self._near_norm())  # truncated exp
        az[m] = rng.uniform(0.0, TWO_PI, k)
        m = comp == 1
        k = int(m.sum())
        j = rng.integers(0, self.patch_r.size, k)
        r[m] = np.clip(self.patch_r[j] + rng.uniform(-0.5, 0.5, k) * self.patch_dr, self.r_min, self.r_max)
        az[m] = (self.patch_az[j] + rng.uniform(-0.5, 0.5, k) * self.patch_daz) % TWO_PI
        m = comp == 2
        k = int(m.sum())
        r[m] = rng.uniform(self.r_min, self.r_max, k)
        az[m] = rng.uniform(0.0, TWO_PI, k)
        return r, az

    def density(self, r, az, lam: float):
        """Expected clutter per scan per unit measurement volume [1/(m rad)] at (r, az)."""
        r = np.asarray(r, dtype=float)
        az = np.asarray(az, dtype=float)
        near = np.where((r >= self.r_min) & (r <= self.r_max),
                        np.exp(-(r - self.r_min) / self.near_scale_m) / (self.near_scale_m * self._near_norm()), 0.0)
        out = self.near_frac * near / TWO_PI
        n = self.patch_r.size
        inside = (np.abs(r[..., None] - self.patch_r) <= 0.5 * self.patch_dr) & \
                 (np.abs(wrap_pi(az[..., None] - self.patch_az)) <= 0.5 * self.patch_daz)
        out = out + self.patch_frac * inside.sum(axis=-1) / (n * self.patch_dr * self.patch_daz)
        out = out + self.uniform_frac / ((self.r_max - self.r_min) * TWO_PI)
        return lam * out


def uniform_clutter_density(lam: float, r_min: float, r_max: float) -> float:
    return lam / ((r_max - r_min) * TWO_PI)


# --- E4 ---------------------------------------------------------------------------------------
def merge_groups(r, az, d_r: float, d_az: float) -> np.ndarray:
    """Single-linkage groups of points closer than ``d_r`` in range AND ``d_az`` in azimuth. Returns labels."""
    n = np.asarray(r).size
    lab = np.arange(n)
    if n < 2:
        return lab
    r = np.asarray(r, dtype=float)
    az = np.asarray(az, dtype=float)
    close = (np.abs(r[:, None] - r[None, :]) < d_r) & (np.abs(wrap_pi(az[:, None] - az[None, :])) < d_az)
    from scipy.sparse.csgraph import connected_components

    _, lab = connected_components(close, directed=False)
    return lab
