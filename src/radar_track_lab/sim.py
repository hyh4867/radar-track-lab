"""Scenario construction and single-run execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .metrics import evaluate_scan, summarize
from .radar import RadarParams, build_scan_truth, simulate_scans
from .tracker import EKFTracker, NearestNeighborBaseline, TrackerParams


def utc_to_unix(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


@dataclass
class Scenario:
    name: str
    t_start: float
    n_scans: int
    scan_truths: list
    eval_truths: list
    meta: dict = field(default_factory=dict)


def build_scenario(truth, t_start: float, duration_s: float, radar: RadarParams, name: str = "", method="hermite"):
    n_scans = int(duration_s // radar.rotation_period_s)
    sub = truth.in_window(t_start - 30.0, t_start + duration_s + 30.0)
    scans, evals = build_scan_truth(sub, t_start, n_scans, radar, method)
    meta = {
        "targets": int(len(set().union(*[set(e.ids.tolist()) for e in evals]))) if evals else 0,
        "truth_per_scan_mean": float(np.mean([e.ids.size for e in evals])) if evals else 0.0,
        "truth_per_scan_max": int(max(e.ids.size for e in evals)) if evals else 0,
    }
    return Scenario(name, t_start, n_scans, scans, evals, meta)


@dataclass
class RunResult:
    summary: dict
    nees: np.ndarray  # columns: track_id, n_updates, status, nees4, nees2, d2, truth_id, t, truth_range
    snapshots: list | None = None
    scans: list | None = None


def make_tracker(method: str, params: TrackerParams):
    if method == "ekf":
        return EKFTracker(params)
    if method == "nn":
        return NearestNeighborBaseline(params)
    raise ValueError(method)


def run(scenario: Scenario, cfg: dict, seed: int, method: str = "ekf", record: bool = False) -> RunResult:
    radar = RadarParams.from_config(cfg)
    params = TrackerParams.from_config(cfg)
    c = float(cfg["eval"]["gospa_c_m"])
    p = int(cfg["eval"]["gospa_p"])
    warmup = float(cfg["eval"].get("warmup_s", 60.0))
    scans = simulate_scans(scenario.scan_truths, radar, seed)
    trk = make_tracker(method, params)
    evals, nees_rows, snaps = [], [], [] if record else None
    upd_sq = []  # squared position error at update time, tracks confirmed before the scan
    for k, scan in enumerate(scans):
        et = scenario.eval_truths[k]
        recs = trk.process_scan(scan, et.t)
        ids, pos, vel = trk.estimates(et.t)
        evals.append(evaluate_scan(et, ids, pos, c, p))
        if recs:
            st = scenario.scan_truths[k]
            idx = {int(i): n for n, i in enumerate(st.ids)}
            for track_id, det, _t, x, P, n_upd, d2, status in recs:
                tid = int(scan.truth_id[det])
                if tid < 0 or tid not in idx:
                    continue
                j = idx[tid]
                e = np.r_[st.pos[j], st.vel[j]] - x
                if status == 1 and scan.t[det] >= scenario.t_start + warmup:
                    upd_sq.append(float(e[:2] @ e[:2]))
                if P is None:
                    continue
                n4 = float(e @ np.linalg.solve(P, e))
                n2 = float(e[:2] @ np.linalg.solve(P[:2, :2], e[:2]))
                nees_rows.append((track_id, n_upd, status, n4, n2, d2, tid, _t, float(np.hypot(*st.pos[j]))))
        if record:
            tids, tpos, tvel = trk.estimates(et.t, confirmed_only=False)
            conf = np.isin(tids, ids)
            snaps.append(
                {
                    "k": k,
                    "t": et.t,
                    "track_ids": tids,
                    "track_pos": tpos,
                    "track_vel": tvel,
                    "confirmed": conf,
                    "gospa": evals[-1].gospa,
                    "assigned": evals[-1].assigned,
                }
            )
    summary = summarize(evals, c, warmup, scenario.t_start)
    summary["rmse_at_update_m"] = float(np.sqrt(np.mean(upd_sq))) if upd_sq else float("nan")
    nees = np.asarray(nees_rows, dtype=float) if nees_rows else np.zeros((0, 9))
    return RunResult(summary, nees, snaps, scans if record else None)
