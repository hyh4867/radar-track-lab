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

import numpy as np

from .geo import TWO_PI, cart_to_polar, wrap_2pi


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

    @classmethod
    def from_config(cls, cfg: dict) -> "RadarParams":
        r = cfg["radar"]
        return cls(
            rotation_period_s=float(r["rotation_period_s"]),
            max_range_m=float(r["max_range_m"]),
            min_range_m=float(r["min_range_m"]),
            sigma_r_m=float(r["sigma_r_m"]),
            sigma_az_rad=float(np.radians(r["sigma_az_deg"])),
            pd=float(r["pd"]),
            clutter_lambda=float(r["clutter_lambda"]),
            clutter_model=str(r.get("clutter_model", "uniform_range_azimuth")),
        )

    @property
    def omega(self) -> float:
        return TWO_PI / self.rotation_period_s


@dataclass
class ScanTruth:
    """Truth for one revolution: targets illuminated in scan ``k``."""

    k: int
    t0: float
    ids: np.ndarray  # (m,) target ids
    t: np.ndarray  # (m,) illumination time
    pos: np.ndarray  # (m, 2)
    vel: np.ndarray  # (m, 2)


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


def _in_coverage(pos, params: RadarParams):
    r = np.hypot(pos[:, 0], pos[:, 1])
    return (r >= params.min_range_m) & (r <= params.max_range_m)


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
            ok[ok] = _in_coverage(pc[ok], params)
            for k, t_, p_, v_ in zip(ks[ok], tc[ok], pc[ok], vel[ok]):
                per_scan[k].append((seg.target_id, t_, p_, v_))
        ke = np.flatnonzero((te >= seg.t0) & (te <= seg.t1))
        if ke.size:
            pe, ve, vv = seg.state(te[ke], method)
            ok = vv.copy()
            ok[ok] = _in_coverage(pe[ok], params)
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
        else:
            ids, tt, pp, vv = np.zeros(0, np.int64), np.zeros(0), np.zeros((0, 2)), np.zeros((0, 2))
        scans.append(ScanTruth(k, float(tk[k]), ids, tt, pp, vv))
        rows = per_eval[k]
        if rows:
            ids = np.array([r[0] for r in rows], dtype=np.int64)
            pp = np.array([r[1] for r in rows])
            vv = np.array([r[2] for r in rows])
        else:
            ids, pp, vv = np.zeros(0, np.int64), np.zeros((0, 2)), np.zeros((0, 2))
        evals.append(EvalTruth(k, float(te[k]), ids, pp, vv))
    return scans, evals


def simulate_scan(st: ScanTruth, params: RadarParams, rng: np.random.Generator) -> Scan:
    """Polar detections for one revolution (targets + clutter), sorted by time."""
    m = st.ids.size
    det = rng.random(m) < params.pd
    r_true, az_true = cart_to_polar(st.pos[:, 0], st.pos[:, 1])
    nr = rng.standard_normal(m) * params.sigma_r_m
    na = rng.standard_normal(m) * params.sigma_az_rad
    r = (r_true + nr)[det]
    az = wrap_2pi(az_true + na)[det]
    t = st.t[det]
    tid = st.ids[det]

    nc = rng.poisson(params.clutter_lambda)
    if params.clutter_model == "uniform_range_azimuth":
        rc = rng.uniform(params.min_range_m, params.max_range_m, nc)
    elif params.clutter_model == "uniform_area":
        rc = np.sqrt(rng.uniform(params.min_range_m**2, params.max_range_m**2, nc))
    else:
        raise ValueError(params.clutter_model)
    azc = rng.uniform(0.0, TWO_PI, nc)
    tc = st.t0 + azc / params.omega

    r = np.r_[r, rc]
    az = np.r_[az, azc]
    t = np.r_[t, tc]
    tid = np.r_[tid, -np.ones(nc, dtype=np.int64)]
    o = np.argsort(t, kind="stable")
    return Scan(st.k, st.t0, t[o], r[o], az[o], tid[o])


def simulate_scans(scan_truths, params: RadarParams, seed: int):
    rng = np.random.default_rng(seed)
    return [simulate_scan(st, params, rng) for st in scan_truths]
