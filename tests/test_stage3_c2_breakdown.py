"""Fixes the definitions of scripts/stage3_c2_breakdown.py on hand-made records."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stage3_c2_breakdown import breakdown  # noqa: E402


def _rec(causes, events, asg, win):
    return {"causes": causes, "base": {"assigned_target_scans": asg, "window_turn": win}, "lost_events": events}


def _ev(target, cause, r=10_000.0):
    return {"target": target, "cause": cause, "range_m": r, "misses": 0}


def test_breakdown_definitions():
    # seed 1: aircraft 1 has 3 turn losses + 1 miss, aircraft 2 has 2 turns, aircraft 3 one turn, aircraft 4 one miss
    r1 = _rec({"truth_gap": 5, "near_other": 2, "turn": 4, "misses": 2, "near_radar": 0, "speed_change": 0, "unexplained": 1},
              [_ev(1, "turn"), _ev(1, "turn"), _ev(2, "turn"), _ev(3, "turn"), _ev(1, "misses"), _ev(4, "misses"),
               _ev(5, "unexplained")], 1000, 100)
    r2 = _rec({"truth_gap": 0, "near_other": 0, "turn": 2, "misses": 0, "near_radar": 0, "speed_change": 0, "unexplained": 0},
              [_ev(1, "turn"), _ev(2, "turn")], 1000, 300)
    b = breakdown([r1, r2])
    assert b["lost"] == 9  # truth_gap and near_other excluded
    assert (b["turn"], b["misses"], b["other"]) == (6, 2, 1)
    assert b["turn_share"] == pytest.approx(6 / 9)
    assert b["base_rate"] == pytest.approx(400 / 2000)  # pooled ratio, not the mean of per-seed ratios
    assert b["share_over_base"] == pytest.approx((6 / 9) / 0.2)
    assert b["top2"] == [1, 2]  # aircraft 1 (3 turn), aircraft 2 (2 turn)
    # removing every lost event of aircraft 1 and 2 (including aircraft 1's miss) leaves 3 events, 1 turn
    assert (b["turn_wo_top2"], b["lost_wo_top2"]) == (1, 3)
    assert b["n_aircraft_turn"] == 3


def test_breakdown_rejects_inconsistent_events():
    r = _rec({"turn": 2, "misses": 0}, [_ev(1, "turn")], 10, 1)
    with pytest.raises(ValueError):
        breakdown([r])
