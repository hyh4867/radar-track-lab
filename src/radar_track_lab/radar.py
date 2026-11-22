"""Virtual rotating 2-D surveillance radar.

The antenna starts each revolution at azimuth 0 (north) at ``t_k = t_start + k*T``
and turns clockwise at ``2*pi/T`` rad/s. A target is illuminated when the beam
azimuth equals the target azimuth, so every detection has its own time stamp
``t_k + az/omega``. Detections are generated in polar coordinates with
Gaussian range / azimuth noise, a constant detection probability ``Pd`` and
Poisson clutter.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from . import sensor as SE
from .geo import TWO_PI, cart_to_polar, wrap_2pi, wrap_pi


@dataclass(frozen=True)
class RadarParams:
    rotation_period_s: float
    max_range_m: float
    min_range_m: float
    sigma_r_m: float
    sigma_az_rad: float
    pd: float
    clutter_lambda: float
    clutter_model: str = "uniform_range_azimuth"
    # stage 3 sensor elements (docs/PREREGISTRATION_3.md 3.1); all off by default
    pd_model: str = "constant"  # "constant" | "swerling1" (E1)
    pfa: float = 1e-6
    snr_ref: float = 0.0  # linear SNR at snr_ref_range_m
    snr_ref_range_m: float = 100_000.0
    geometry: str = "flat"  # "flat" | "altitude" (E2)
    antenna_height_m: float = 0.0  # above mean sea level
    k_earth: float = 4.0 / 3.0
    cone_max_elev_deg: float = 42.0
    slant_correction: str = "modec"  # "modec" | "none"
    modec_step_ft: float = 100.0
    clutter_map_key: str = ""  # E3: clutter_model == "map"
    merge: bool = False  # E4
    merge_dr_m: float = 150.0
    merge_daz_deg: float = 1.4

    @classmethod
    def from_config(cls, cfg: dict) -> "RadarParams":
        r = cfg["radar"]
        se = cfg.get("sensor") or {}
        site = (cfg.get("site") or {}).get("id", "EHAM")
        elev = float((se.get("site_elevation_m") or {}).get(site, 0.0))
        extra = {}
        if se:
            extra = dict(
                pd_model=str(se.get("pd_model", "constant")),
                pfa=float(se.get("pfa", 1e-6)),
                snr_ref=float(se.get("snr_ref", 0.0)),
                snr_ref_range_m=float(se.get("snr_ref_range_m", 100_000.0)),
                geometry=str(se.get("geometry", "flat")),
                antenna_height_m=elev + float(se.get("mast_height_m", 20.0)),
                k_earth=float(se.get("k_earth", 4.0 / 3.0)),
                cone_max_elev_deg=float(se.get("cone_max_elev_deg", 42.0)),
                slant_correction=str(se.get("slant_correction", "modec")),
                modec_step_ft=float(se.get("modec_step_ft", 100.0)),
                clutter_map_key=str(se.get("clutter_map_key") or site),
                merge=bool(se.get("merge", False)),
                merge_dr_m=float(se.get("merge_dr_m", 150.0)),
                merge_daz_deg=float(se.get("merge_daz_deg", 1.4)),
            )
        return cls(
            rotation_period_s=float(r["rotation_period_s"]),
            max_range_m=float(r["max_range_m"]),
            min_range_m=float(r["min_range_m"]),
            sigma_r_m=float(r["sigma_r_m"]),
            sigma_az_rad=float(np.radians(r["sigma_az_deg"])),
            pd=float(r["pd"]),
            clutter_lambda=float(r["clutter_lambda"]),
            clutter_model=str(r.get("clutter_model", "uniform_range_azimuth")),
            **extra,
        )

    @property
    def omega(self) -> float:
        return TWO_PI / self.rotation_period_s

    @property
    def a_e(self) -> float:
        return SE.effective_radius(self.k_earth)

    def clutter_map(self) -> "SE.ClutterMap":
        return _clutter_map(self.clutter_map_key, self.min_range_m, self.max_range_m)

    def clutter_density(self, r, az):
        """True clutter density per scan [1/(m rad)] at measured (r, az)."""
        if self.clutter_model == "map":
            return self.clutter_map().density(r, az, self.clutter_lambda)
        if self.clutter_model != "uniform_range_azimuth":
            raise ValueError(self.clutter_model)
        return np.full(np.shape(r), SE.uniform_clutter_density(self.clutter_lambda, self.min_range_m, self.max_range_m))


@lru_cache(maxsize=32)
def _clutter_map(key, r_min, r_max):
    return SE.ClutterMap.for_site(key, r_min, r_max)


@dataclass
class ScanTruth:
    """Truth for one revolution: targets illuminated in scan ``k``."""

    k: int
    t0: float
    ids: np.ndarray  # (m,) target ids
    t: np.ndarray  # (m,) illumination time
    pos: np.ndarray  # (m, 2)
    vel: np.ndarray  # (m, 2)
    alt: np.ndarray | None = None  # (m,) barometric altitude [m] (geometry == "altitude" only)


@dataclass
class EvalTruth:
    """Truth at the evaluation instant of scan ``k`` (end of the revolution)."""

    k: int
    t: float
    ids: np.ndarray
    pos: np.ndarray
    vel: np.ndarray


@dataclass
class Scan:
    k: int
    t0: float
    t: np.ndarray  # (d,) detection time
    r: np.ndarray  # (d,) measured range
    az: np.ndarray  # (d,) measured azimuth [0, 2pi)
    truth_id: np.ndarray  # (d,) -1 for clutter

    @property
    def z(self) -> np.ndarray:
        return np.stack([self.r, self.az], axis=1)


def _in_coverage(pos, params: RadarParams, alt=None):
    r = np.hypot(pos[:, 0], pos[:, 1])
    ok = (r >= params.min_range_m) & (r <= params.max_range_m)
    if params.geometry == "altitude" and alt is not None:
        hor = SE.horizon_distance(params.antenna_height_m, alt, params.a_e)
        ok &= ~(np.isfinite(alt) & (r > hor))  # below the radar horizon = outside coverage
    return ok


def build_scan_truth(truth, t_start: float, n_scans: int, params: RadarParams, method: str = "hermite"):
    """Deterministic illumination times / states for every scan and target.

    Returns ``(scan_truths, eval_truths)``. Noise is added later, so these can
    be reused across Monte Carlo runs.
    """
    T, omega = params.rotation_period_s, params.omega
    tk = t_start + T * np.arange(n_scans)
    te = tk + T
    per_scan = [[] for _ in range(n_scans)]
    per_eval = [[] for _ in range(n_scans)]
    for seg in truth.segments:
        ks = np.flatnonzero((tk + T >= seg.t0) & (tk <= seg.t1))
        if ks.size:
            p0, _, v0 = seg.state(tk[ks], method)
            # target may start mid-revolution: use first valid time in the revolution
            t_ref = np.where(v0, tk[ks], np.clip(seg.t0, tk[ks], tk[ks] + T))
            p0, _, v0 = seg.state(t_ref, method)
            _, az = cart_to_polar(p0[:, 0], p0[:, 1])
            tc = tk[ks] + np.where(v0, az, 0.0) / omega
            for _ in range(2):  # fixed-point refinement of the crossing time
                pc, _, vc = seg.state(tc, method)
                _, az = cart_to_polar(np.nan_to_num(pc[:, 0]), np.nan_to_num(pc[:, 1]))
                tc = tk[ks] + az / omega
            pc, vel, vc = seg.state(tc, method)
            ok = vc & v0
            geo = params.geometry == "altitude"
            al = seg.altitude(tc) if geo else np.full(tc.size, np.nan)
            ok[ok] = _in_coverage(pc[ok], params, al[ok] if geo else None)
            for k, t_, p_, v_, a_ in zip(ks[ok], tc[ok], pc[ok], vel[ok], al[ok]):
                per_scan[k].append((seg.target_id, t_, p_, v_, a_))
        ke = np.flatnonzero((te >= seg.t0) & (te <= seg.t1))
        if ke.size:
            pe, ve, vv = seg.state(te[ke], method)
            ok = vv.copy()
            ok[ok] = _in_coverage(pe[ok], params, seg.altitude(te[ke])[ok] if params.geometry == "altitude" else None)
            for k, p_, v_ in zip(ke[ok], pe[ok], ve[ok]):
                per_eval[k].append((seg.target_id, p_, v_))

    scans, evals = [], []
    for k in range(n_scans):
        rows = sorted(per_scan[k], key=lambda r: r[1])
        if rows:
            ids = np.array([r[0] for r in rows], dtype=np.int64)
            tt = np.array([r[1] for r in rows])
            pp = np.array([r[2] for r in rows])
            vv = np.array([r[3] for r in rows])
            aa = np.array([r[4] for r in rows])
        else:
            ids, tt, pp, vv = np.zeros(0, np.int64), np.zeros(0), np.zeros((0, 2)), np.zeros((0, 2))
            aa = np.zeros(0)
        scans.append(ScanTruth(k, float(tk[k]), ids, tt, pp, vv, aa if params.geometry == "altitude" else None))
        rows = per_eval[k]
        if rows:
            ids = np.array([r[0] for r in rows], dtype=np.int64)
            pp = np.array([r[1] for r in rows])
            vv = np.array([r[2] for r in rows])
        else:
            ids, pp, vv = np.zeros(0, np.int64), np.zeros((0, 2)), np.zeros((0, 2))
        evals.append(EvalTruth(k, float(te[k]), ids, pp, vv))
    return scans, evals


def _stage3_active(params: RadarParams) -> bool:
    return params.pd_model != "constant" or params.geometry != "flat" or params.merge


def simulate_scan(st: ScanTruth, params: RadarParams, rng: np.random.Generator) -> Scan:
    """Polar detections for one revolution (targets + clutter), sorted by time.

    With every stage 3 element off this is the stage 1-2 model and consumes the generator in the same order.
    """
    m = st.ids.size
    u = rng.random(m)
    r_true, az_true = cart_to_polar(st.pos[:, 0], st.pos[:, 1])
    if not _stage3_active(params):
        det = u < params.pd
        nr = rng.standard_normal(m) * params.sigma_r_m
        na = rng.standard_normal(m) * params.sigma_az_rad
        r = (r_true + nr)[det]
        az = wrap_2pi(az_true + na)[det]
        t = st.t[det]
        tid = st.ids[det]
    else:
        r, az, t, tid = _stage3_targets(st, params, rng, u, r_true, az_true)

    nc = rng.poisson(params.clutter_lambda)
    if params.clutter_model == "uniform_range_azimuth":
        rc = rng.uniform(params.min_range_m, params.max_range_m, nc)
        azc = rng.uniform(0.0, TWO_PI, nc)
    elif params.clutter_model == "uniform_area":
        rc = np.sqrt(rng.uniform(params.min_range_m**2, params.max_range_m**2, nc))
        azc = rng.uniform(0.0, TWO_PI, nc)
    elif params.clutter_model == "map":
        rc, azc = params.clutter_map().sample(nc, rng)
    else:
        raise ValueError(params.clutter_model)
    tc = st.t0 + azc / params.omega

    r = np.r_[r, rc]
    az = np.r_[az, azc]
    t = np.r_[t, tc]
    tid = np.r_[tid, -np.ones(nc, dtype=np.int64)]
    o = np.argsort(t, kind="stable")
    return Scan(st.k, st.t0, t[o], r[o], az[o], tid[o])


def _stage3_targets(st: ScanTruth, params: RadarParams, rng, u, r_ground, az_true):
    """Target reports with E1 (Swerling I Pd), E2 (altitude geometry) and E4 (merging) as configured."""
    m = st.ids.size
    geo = params.geometry == "altitude" and st.alt is not None
    alt = st.alt if geo else np.full(m, np.nan)
    known = np.isfinite(alt)
    r_meas = r_ground.copy()  # the quantity the radar measures: slant range with E2, else ground range
    visible = np.ones(m, dtype=bool)
    if geo and known.any():
        rs, el = SE.slant_and_elevation(r_ground[known], params.antenna_height_m, alt[known], params.a_e)
        r_meas[known] = rs
        visible[known] = el <= np.radians(params.cone_max_elev_deg)
    if params.pd_model == "swerling1":
        pd = SE.pd_swerling1(SE.snr_at(r_meas, params.snr_ref, params.snr_ref_range_m), params.pfa)
    elif params.pd_model == "constant":
        pd = np.full(m, params.pd)
    else:
        raise ValueError(params.pd_model)
    det = (u < pd) & visible
    nr = rng.standard_normal(m) * params.sigma_r_m
    na = rng.standard_normal(m) * params.sigma_az_rad
    idx = np.flatnonzero(det)
    rr, aa = r_meas[idx], az_true[idx]
    rep = idx
    if params.merge and idx.size > 1:
        lab = SE.merge_groups(rr, aa, params.merge_dr_m, np.radians(params.merge_daz_deg))
        reps, r_c, a_c = [], [], []
        for g in np.unique(lab):
            mem = np.flatnonzero(lab == g)
            if mem.size == 1:
                reps.append(idx[mem[0]])
                r_c.append(rr[mem[0]])
                a_c.append(aa[mem[0]])
                continue
            a0 = aa[mem[0]]
            am = (a0 + np.mean(wrap_pi(aa[mem] - a0))) % TWO_PI
            rm = float(np.mean(rr[mem]))
            dist = np.hypot(rr[mem] - rm, rm * wrap_pi(aa[mem] - am))
            reps.append(idx[mem[np.argmin(dist)]])
            r_c.append(rm)
            a_c.append(am)
        o = np.argsort(reps)
        rep = np.asarray(reps)[o]
        rr, aa = np.asarray(r_c)[o], np.asarray(a_c)[o]
    r = rr + nr[rep]
    az = wrap_2pi(aa + na[rep])
    if geo and params.slant_correction == "modec":
        k = np.isfinite(alt[rep])
        r[k] = SE.ground_from_slant(r[k], params.antenna_height_m, SE.mode_c(alt[rep][k], params.modec_step_ft),
                                    params.a_e)
    elif geo and params.slant_correction != "none":
        raise ValueError(params.slant_correction)
    return r, az, st.t[rep], st.ids[rep]


def simulate_scans(scan_truths, params: RadarParams, seed: int):
    rng = np.random.default_rng(seed)
    return [simulate_scan(st, params, rng) for st in scan_truths]
