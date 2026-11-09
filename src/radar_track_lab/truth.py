"""Ground truth from ADS-B traces: filtering, segmentation and interpolation.

Each aircraft (anonymous integer id) is split into *segments*: runs of
accepted ADS-B points with no gap longer than ``max_gap_s`` and no readsb
"new leg" flag. Inside a segment the position at any time is obtained by cubic
Hermite interpolation that uses the ADS-B ground-velocity vector at both ends
of the bracketing interval. Outside segments the aircraft is treated as absent
(it is neither simulated nor counted as truth).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .adsb import GROUND_SENTINEL_FT, TRACE_FLAG_NEW_LEG, TRACE_FLAG_STALE
from .geo import geodetic_to_enu, local_velocity_to_site_enu

KT_TO_MPS = 1852.0 / 3600.0


@dataclass
class Segment:
    target_id: int
    t: np.ndarray  # (n,)
    pos: np.ndarray  # (n, 2) east, north [m]
    vel: np.ndarray  # (n, 2) [m/s]

    @property
    def t0(self) -> float:
        return float(self.t[0])

    @property
    def t1(self) -> float:
        return float(self.t[-1])

    def state(self, tq, method: str = "hermite"):
        """Interpolated ``(pos, vel, valid)`` at query times ``tq`` (1-D array)."""
        tq = np.atleast_1d(np.asarray(tq, dtype=float))
        valid = (tq >= self.t[0]) & (tq <= self.t[-1])
        pos = np.full((tq.size, 2), np.nan)
        vel = np.full((tq.size, 2), np.nan)
        if not valid.any():
            return pos, vel, valid
        tv = tq[valid]
        i = np.clip(np.searchsorted(self.t, tv, side="right") - 1, 0, self.t.size - 2)
        p, v = interpolate(
            self.t[i], self.pos[i], self.vel[i], self.t[i + 1], self.pos[i + 1], self.vel[i + 1], tv, method
        )
        pos[valid] = p
        vel[valid] = v
        return pos, vel, valid

    def bracket_gap(self, tq):
        tq = np.atleast_1d(np.asarray(tq, dtype=float))
        i = np.clip(np.searchsorted(self.t, tq, side="right") - 1, 0, self.t.size - 2)
        return self.t[i + 1] - self.t[i]


def interpolate(ta, pa, va, tb, pb, vb, tq, method: str = "hermite"):
    """Interpolate between two states. Arrays broadcast over the leading axis."""
    h = (tb - ta)[:, None]
    s = ((tq - ta) / (tb - ta))[:, None]
    if method == "linear":
        pos = pa + s * (pb - pa)
        vel = np.broadcast_to((pb - pa) / h, pos.shape).copy()
        return pos, vel
    if method != "hermite":
        raise ValueError(f"unknown interpolation method {method!r}")
    s2, s3 = s * s, s * s * s
    h00 = 2 * s3 - 3 * s2 + 1
    h10 = s3 - 2 * s2 + s
    h01 = -2 * s3 + 3 * s2
    h11 = s3 - s2
    pos = h00 * pa + h10 * h * va + h01 * pb + h11 * h * vb
    # derivatives of the basis w.r.t. s, divided by h
    d00 = 6 * s2 - 6 * s
    d10 = 3 * s2 - 4 * s + 1
    d01 = -6 * s2 + 6 * s
    d11 = 3 * s2 - 2 * s
    vel = (d00 * pa + d01 * pb) / h + d10 * va + d11 * vb
    return pos, vel


@dataclass
class FilterStats:
    total_points: int = 0
    dropped_source: int = 0
    dropped_stale: int = 0
    dropped_ground: int = 0
    dropped_low_nacp: int = 0
    dropped_unknown_nacp: int = 0
    dropped_duplicate_time: int = 0
    kept_points: int = 0
    nacp_hist: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class TruthSet:
    segments: list[Segment]
    stats: FilterStats
    lat0: float
    lon0: float

    def in_window(self, t_start: float, t_end: float) -> "TruthSet":
        segs = [s for s in self.segments if s.t1 >= t_start and s.t0 <= t_end]
        return TruthSet(segs, self.stats, self.lat0, self.lon0)

    @property
    def target_ids(self) -> np.ndarray:
        return np.unique([s.target_id for s in self.segments])


def load_points(path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def build_truth(points: dict[str, np.ndarray], cfg: dict, t_start=None, t_end=None) -> TruthSet:
    """Filter ADS-B points and build Hermite segments in the site frame."""
    tcfg = cfg["truth"]
    lat0, lon0 = cfg["site"]["lat_deg"], cfg["site"]["lon_deg"]
    st = FilterStats()

    t = points["t"]
    sel = np.ones(t.size, dtype=bool)
    if t_start is not None:
        sel &= t >= t_start
    if t_end is not None:
        sel &= t <= t_end
    p = {k: v[sel] for k, v in points.items()}
    st.total_points = int(sel.sum())

    keep = np.isin(p["src"], np.asarray(tcfg["allowed_sources"]))
    st.dropped_source = int((~keep).sum())
    stale = (p["flags"] & TRACE_FLAG_STALE) > 0
    st.dropped_stale = int((keep & stale).sum())
    keep &= ~stale
    if tcfg.get("exclude_ground", True):
        ground = p["alt"] <= GROUND_SENTINEL_FT + 1
        st.dropped_ground = int((keep & ground).sum())
        keep &= ~ground
    unknown = p["nacp"] < 0
    st.dropped_unknown_nacp = int((keep & unknown).sum())
    keep &= ~unknown
    vals, cnts = np.unique(p["nacp"][keep], return_counts=True)
    st.nacp_hist = {int(v): int(c) for v, c in zip(vals, cnts)}
    low = p["nacp"] < tcfg["min_nacp"]
    st.dropped_low_nacp = int((keep & low).sum())
    keep &= ~low

    p = {k: v[keep] for k, v in p.items()}
    e, n, _ = geodetic_to_enu(p["lat"], p["lon"], lat0, lon0)
    gs = p["gs"].astype(float) * KT_TO_MPS
    trk = np.radians(p["trk"].astype(float))
    ve_l, vn_l = gs * np.sin(trk), gs * np.cos(trk)
    ve, vn = local_velocity_to_site_enu(ve_l, vn_l, p["lat"], p["lon"], lat0, lon0)

    max_gap = float(tcfg["max_gap_s"])
    segments: list[Segment] = []
    order = np.lexsort((p["t"], p["ac"]))
    ac, tt = p["ac"][order], p["t"][order]
    pos = np.stack([e[order], n[order]], axis=1)
    vel = np.stack([ve[order], vn[order]], axis=1)
    newleg = (p["flags"][order] & TRACE_FLAG_NEW_LEG) > 0
    bounds = np.flatnonzero(np.diff(ac)) + 1
    for lo, hi in zip(np.r_[0, bounds], np.r_[bounds, ac.size]):
        ta, pa, va, nl = tt[lo:hi], pos[lo:hi], vel[lo:hi], newleg[lo:hi]
        # drop near-duplicate timestamps
        good = np.r_[True, np.diff(ta) > 0.05]
        st.dropped_duplicate_time += int((~good).sum())
        ta, pa, va, nl = ta[good], pa[good], va[good], nl[good]
        if ta.size < 2:
            continue
        cut = np.flatnonzero((np.diff(ta) > max_gap) | nl[1:]) + 1
        for a, b in zip(np.r_[0, cut], np.r_[cut, ta.size]):
            if b - a < 2:
                continue
            sv = va[a:b].copy()
            bad = ~np.isfinite(sv).all(axis=1)
            if bad.any():  # fill missing velocity from finite differences
                fd = np.gradient(pa[a:b], ta[a:b], axis=0)
                sv[bad] = fd[bad]
            segments.append(Segment(int(ac[lo]), ta[a:b].copy(), pa[a:b].copy(), sv))
    st.kept_points = int(sum(s.t.size for s in segments))
    return TruthSet(segments, st, lat0, lon0)


def leave_one_out_errors(truth: TruthSet, max_gap_s: float):
    """Interpolation error estimated by dropping each interior point.

    Returns arrays ``gap`` (t[j+1]-t[j-1]), ``err_hermite``, ``err_linear`` [m].
    The gap of a leave-one-out sample is about twice the normal spacing, so the
    errors are grouped by gap and later matched to the gaps actually used.
    """
    gaps, eh, el = [], [], []
    for s in truth.segments:
        if s.t.size < 3:
            continue
        a, b, j = np.arange(0, s.t.size - 2), np.arange(2, s.t.size), np.arange(1, s.t.size - 1)
        g = s.t[b] - s.t[a]
        m = g <= max_gap_s
        if not m.any():
            continue
        a, b, j, g = a[m], b[m], j[m], g[m]
        ph, _ = interpolate(s.t[a], s.pos[a], s.vel[a], s.t[b], s.pos[b], s.vel[b], s.t[j], "hermite")
        pl, _ = interpolate(s.t[a], s.pos[a], s.vel[a], s.t[b], s.pos[b], s.vel[b], s.t[j], "linear")
        gaps.append(g)
        eh.append(np.linalg.norm(ph - s.pos[j], axis=1))
        el.append(np.linalg.norm(pl - s.pos[j], axis=1))
    if not gaps:
        return np.array([]), np.array([]), np.array([])
    return np.concatenate(gaps), np.concatenate(eh), np.concatenate(el)
