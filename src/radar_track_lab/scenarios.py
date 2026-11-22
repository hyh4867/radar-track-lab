"""Stage 2 scenario registry: site + day + UTC window -> Scenario."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

from .config import load_config
from .radar import RadarParams
from .sim import build_scenario, utc_to_unix
from .truth import build_truth, load_points

ROOT = Path(__file__).resolve().parents[2]
SCEN_FILE = ROOT / "results/data/stage2/scenarios.json"
STAGE1_DAY, STAGE1_SITE = "2026-11-06", "EHAM"


def points_path(day: str, site: str) -> Path:
    if (day, site) == (STAGE1_DAY, STAGE1_SITE):
        return ROOT / "data/processed/region_points.npz"  # the stage 1 file, unchanged
    return ROOT / f"data/processed/sites/{day}_{site}.npz"


def site_cfg(cfg: dict, site: str) -> dict:
    sites = load_config(ROOT / "configs/sites.yaml")["sites"]
    out = copy.deepcopy(cfg)
    out["site"] = {"name": sites[site]["name"], "lat_deg": sites[site]["lat_deg"], "lon_deg": sites[site]["lon_deg"],
                   "id": site}
    return out


def specs() -> dict:
    return {s["id"]: s for s in json.loads(SCEN_FILE.read_text())["scenarios"]}


_points_cache: dict = {}


def build(cfg: dict, spec: dict):
    """Return ``(scenario, truth, cfg_for_site)``."""
    key = (spec["day"], spec["site"])
    if key not in _points_cache:
        _points_cache.clear()
        _points_cache[key] = load_points(points_path(*key))
    c = site_cfg(cfg, spec["site"])
    t0 = utc_to_unix(spec["start_utc"])
    dur = float(spec["duration_s"])
    truth = build_truth(_points_cache[key], c, t0 - 120, t0 + dur + 120)
    sc = build_scenario(truth, t0, dur, RadarParams.from_config(c), name=spec["id"])
    win = truth.in_window(t0, t0 + dur)
    sc.meta["segments"] = len(win.segments)
    sc.meta["aircraft_with_segments"] = int(np.unique([s.target_id for s in win.segments]).size) if win.segments else 0
    sc.meta["filter_stats"] = truth.stats.as_dict()
    return sc, truth, c
