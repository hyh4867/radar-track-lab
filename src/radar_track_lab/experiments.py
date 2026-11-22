"""Shared helpers for the experiment scripts."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .config import load_config
from .radar import RadarParams
from .sim import build_scenario, utc_to_unix
from .truth import build_truth, load_points

ROOT = Path(__file__).resolve().parents[2]

METRICS = [
    "gospa_mean_m", "gospa_loc_m", "gospa_missed_m", "gospa_false_m", "missed_per_scan",
    "false_tracks_per_scan", "rmse_m", "rmse_at_update_m", "id_switches", "fragmentations",
    "init_delay_mean_s", "init_delay_median_s", "never_tracked", "tracks_per_scan", "truth_per_scan",
]


def load(config_path=None):
    cfg = load_config(config_path or ROOT / "configs/default.yaml")
    pts = load_points(ROOT / cfg["truth"]["points_file"])
    return cfg, pts


def load_stage2(config_path=None, stage2_path=None):
    """Default config with configs/stage2.yaml merged over it (top-level keys are replaced or added)."""
    cfg, pts = load(config_path)
    extra = load_config(stage2_path or ROOT / "configs/stage2.yaml") or {}
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k] = {**cfg[k], **v}
        else:
            cfg[k] = v
    return cfg, pts


def scenario_for(cfg, pts, which: str = "eval"):
    tc = cfg["truth"]
    t0 = utc_to_unix(tc[f"{which}_start_utc"])
    dur = float(tc[f"{which}_duration_s"])
    truth = build_truth(pts, cfg, t0 - 120, t0 + dur + 120)
    return build_scenario(truth, t0, dur, RadarParams.from_config(cfg), name=which), truth


def seeds(cfg, n=None):
    mc = cfg["monte_carlo"]
    return [int(mc["base_seed"]) + i for i in range(n or int(mc["runs"]))]


def summarize_runs(rows: list[dict]) -> dict:
    from .metrics import mean_ci

    out = {}
    for k in METRICS:
        vals = np.array([r[k] for r in rows], dtype=float)
        m, h = mean_ci(vals)
        out[k] = {"mean": m, "ci95": h}
    return out
