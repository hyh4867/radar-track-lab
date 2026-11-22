"""Stage 2 checks: privacy / identifier rules, site list, truth kinematics, switch classification."""

import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from radar_track_lab import diagnose as D
from radar_track_lab.config import load_config, with_overrides
from radar_track_lab.sim import run
from radar_track_lab.synthetic import maneuver_scenario

from helpers import BASE_CFG

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"ac", "t", "lat", "lon", "alt", "gs", "trk", "flags", "src", "nacp"}
FORBIDDEN = ("hex", "icao", "reg", "registration", "flight", "callsign", "squawk", "tail", "operator", "owner")


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_extractor_writes_no_identifier_column():
    cols = set(_load_script("extract_sites").COLS)
    assert cols == ALLOWED  # "ac" is an index in archive order, not an address or a hash of one


def test_processed_point_files_hold_only_allowed_columns():
    files = list((ROOT / "data/processed").glob("**/*.npz"))
    if not files:
        pytest.skip("no extracted data on this machine")
    for f in files:
        with np.load(f) as z:
            assert set(z.files) == ALLOWED, f.name


def test_committed_outputs_carry_no_identifier_fields():
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(o, list):
            for v in o[:50]:
                yield from keys(v)

    for f in list((ROOT / "results/data").glob("**/*.json")) + list((ROOT / "web/data").glob("*.json")):
        for k in set(keys(json.loads(f.read_text()))):
            assert not any(k == b or k.startswith(b + "_") for b in FORBIDDEN), (f.name, k)
    import gzip

    tables = list((ROOT / "results").glob("**/*.csv")) + list((ROOT / "results").glob("**/*.csv.gz"))
    assert tables
    for f in tables:
        with (gzip.open(f, "rt", newline="") if f.suffix == ".gz" else open(f, newline="")) as fh:
            header = [h.lower() for h in next(csv.reader(fh))]
        assert not any(h == b or h.startswith(b + "_") for h in header for b in FORBIDDEN), (f.name, header)
    for f in (ROOT / "results/audit").glob("**/*.json"):
        for k in set(keys(json.loads(f.read_text()))):
            assert not any(k == b or k.startswith(b + "_") for b in FORBIDDEN), (f.name, k)


def test_sites_are_outside_korea_and_extract_script_applies_dbflags():
    sites = load_config(ROOT / "configs/sites.yaml")["sites"]
    assert len([s for s in sites.values() if s["role"] == "primary"]) >= 4
    for name, s in sites.items():
        assert not (32.0 <= s["lat_deg"] <= 40.0 and 123.0 <= s["lon_deg"] <= 133.0), name
    src = (ROOT / "scripts/extract_sites.py").read_text()
    for flag in ("DBFLAG_MILITARY", "DBFLAG_PIA", "DBFLAG_LADD"):
        assert f"flags & {flag}" in src


def _turn():
    return maneuver_scenario([-30_000.0, 25_000.0], 130.0, np.radians(20.0),
                             [(20 * 4.8, 0.0), (60.0, np.radians(3.0)), (30 * 4.8, 0.0)])


def test_truth_turn_rate_matches_the_known_manoeuvre():
    sc = _turn()
    kin = D.TruthKinematics(sc)
    w = sc.meta["omega_eval"]
    inside = np.flatnonzero(np.abs(w) > 0)[1:-1]  # centred differences straddle the ends of the turn
    np.testing.assert_allclose(kin.turn_dps[inside, 0], 3.0, atol=0.05)
    straight = np.flatnonzero(w == 0)
    straight = straight[(straight < inside[0] - 2) | (straight > inside[-1] + 2)]
    np.testing.assert_allclose(kin.turn_dps[straight, 0], 0.0, atol=1e-6)
    np.testing.assert_allclose(kin.speed[:, 0], 130.0, atol=1e-6)


def test_lost_track_in_a_known_turn_is_classified_as_turn():
    sc = _turn()
    kin = D.TruthKinematics(sc)
    cfg = with_overrides(BASE_CFG, **{"tracker.q": 25.0})
    causes, n_sq, n_pairs = [], 0, 0
    for seed in range(6):
        r = run(sc, cfg, seed=seed, method="ekf", record=True)
        ev = D.classify_switches(sc, kin, r, 0.0)
        assert len(ev) == r.summary["id_switches"]
        causes += [e["cause"] for e in ev]
        s = D.split_rmse(kin, r, 0.0)
        n_sq += s["n_straight"] + s["n_turn"]
        n_pairs += sum(e.sq_err.size for e in r.evals)
    assert causes and set(causes) == {"turn"}  # the single NCV filter loses this 3 deg/s turn; nothing else is going on
    assert n_sq == n_pairs
