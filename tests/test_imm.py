"""Known-answer tests for the IMM (preregistered in docs/PREREGISTRATION_2.md, Q2).

They use the IMM parameters in configs/stage2.yaml, so they are re-run after tuning.
"""

from pathlib import Path

import numpy as np
import pytest

from radar_track_lab import imm as I
from radar_track_lab.config import load_config, with_overrides
from radar_track_lab.sim import run
from radar_track_lab.synthetic import imm_model_scenario, maneuver_scenario

from helpers import BASE_CFG, straight_line_scenario

ROOT = Path(__file__).resolve().parents[1]
IMM_CFG = load_config(ROOT / "configs/stage2.yaml")["imm"]
CFG = {**with_overrides(BASE_CFG, **{"tracker.q": 25.0}), "imm": IMM_CFG}
P = I.IMMParams.from_config(CFG)
W3 = np.radians(3.0)


def test_transition_matrix_is_a_markov_semigroup():
    a, b, ab = (I.transition_matrix(d, P)[0] for d in (4.8, 9.6, 14.4))
    np.testing.assert_allclose(a.sum(axis=1), 1.0)
    np.testing.assert_allclose(a @ b, ab, atol=1e-12)
    np.testing.assert_allclose(P.stationary @ a, P.stationary, atol=1e-12)
    np.testing.assert_allclose(I.transition_matrix(0.0, P)[0], np.eye(2))


def test_ct_predict_exact_circle_small_omega_and_jacobian():
    x = np.array([[1000.0, -2000.0, 120.0, 50.0, W3]])
    P0 = np.diag([100.0, 100.0, 25.0, 25.0, 1e-4])[None]
    xp, Pp = I.ct_predict(x, P0, 4.8, 0.0, 0.0)
    # exact: velocity rotates by w*dt, speed is kept, position follows the arc
    th = W3 * 4.8
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    np.testing.assert_allclose(xp[0, 2:4], R @ x[0, 2:4], atol=1e-9)
    centre = x[0, :2] + np.array([-x[0, 3], x[0, 2]]) / W3
    np.testing.assert_allclose(xp[0, :2], centre + R @ (x[0, :2] - centre), atol=1e-6)
    # omega -> 0 is straight-line motion
    x0 = x.copy()
    x0[0, 4] = 1e-9
    np.testing.assert_allclose(I.ct_predict(x0, P0, 4.8, 0.0, 0.0)[0][0, :2], x[0, :2] + 4.8 * x[0, 2:4], atol=1e-4)
    # Jacobian against central differences (P' = F P F^T with Q = 0)
    F = np.zeros((5, 5))
    for j, h in enumerate([1.0, 1.0, 1e-3, 1e-3, 1e-7]):
        d = np.zeros(5)
        d[j] = h
        F[:, j] = (I.ct_predict(x + d, P0, 4.8, 0.0, 0.0)[0][0] - I.ct_predict(x - d, P0, 4.8, 0.0, 0.0)[0][0]) / (2 * h)
    np.testing.assert_allclose(Pp[0], F @ P0[0] @ F.T, rtol=1e-5, atol=1e-6)


def _turn_scenario():
    # 20 scans straight, 60 s at +3 deg/s (180 deg), 30 scans straight; 130 m/s, about 40 km from the radar
    return maneuver_scenario([-30_000.0, 25_000.0], 130.0, np.radians(20.0),
                             [(20 * 4.8, 0.0), (60.0, W3), (30 * 4.8, 0.0)])


def _segment_rmse(res, sc, mask):
    err = []
    for k, ev in enumerate(res.evals):
        if mask[k] and ev.sq_err.size:
            err.append(ev.sq_err[0])
    return float(np.sqrt(np.mean(err)))


def test_turn_is_detected_and_tracked_better_than_cv():
    sc = _turn_scenario()
    w = sc.meta["omega_eval"]
    turning = np.abs(w) > 0
    k_end = int(np.flatnonzero(turning)[-1])
    after = np.arange(sc.n_scans) >= k_end + 10
    mu_turn, mu_after, w_est, r_imm, r_ekf, sw_imm, sw_ekf = [], [], [], [], [], 0, 0
    for seed in range(20):
        a = run(sc, CFG, seed=seed, method="imm", record=True)
        e = run(sc, CFG, seed=seed, method="ekf", record=True)
        sw_imm += a.summary["id_switches"]
        sw_ekf += e.summary["id_switches"]
        mu = np.array([s["mu_ct"][s["confirmed"]][0] if s["confirmed"].any() else np.nan for s in a.snapshots])
        om = np.array([s["omega_ct"][s["confirmed"]][0] if s["confirmed"].any() else np.nan for s in a.snapshots])
        mu_turn.append(np.nanmean(mu[turning]))
        mu_after.append(np.nanmean(mu[after]))
        second_half = np.flatnonzero(turning)[turning.sum() // 2:]
        w_est.append(np.nanmean(om[second_half]))
        r_imm.append(_segment_rmse(a, sc, turning))
        r_ekf.append(_segment_rmse(e, sc, turning))
    assert sw_imm < sw_ekf  # fewer lost tracks than the single NCV filter in a 3 deg/s turn
    assert np.mean(mu_turn) > 0.5  # turn model dominates during the turn
    assert np.mean(mu_after) < 0.5  # and gives way again on the straight leg
    assert abs(np.degrees(np.mean(w_est)) - 3.0) < 1.0  # sign and size of the turn rate
    assert np.mean(r_imm) < np.mean(r_ekf)  # better than the single NCV filter (q = 25) in the turn


def test_straight_line_accuracy_not_worse_than_cv():
    sc = straight_line_scenario(p0=[-40_000.0, 30_000.0], v=[180.0, -60.0], n_scans=80)
    cfg = with_overrides(CFG, **{"eval.warmup_s": 60.0})
    r_imm = np.mean([run(sc, cfg, seed=s, method="imm").summary["rmse_m"] for s in range(20)])
    r_ekf = np.mean([run(sc, cfg, seed=s, method="ekf").summary["rmse_m"] for s in range(20)])
    assert r_imm <= 1.05 * r_ekf


def test_nees_on_model_matched_truth():
    rows = []
    for i in range(12):
        sc = imm_model_scenario(10, 50, 4.8, P, 150.0, seed=700 + i)
        rows.append(run(sc, CFG, seed=800 + i, method="imm").nees)
    nees = np.concatenate(rows)
    far = nees[nees[:, 8] >= 5000.0]
    assert far.shape[0] > 3000
    assert 3.0 <= far[:, 3].mean() <= 5.5


def test_imm_single_target_management_like_ekf():
    sc = straight_line_scenario(p0=[20_000.0, 40_000.0], v=[-150.0, 30.0], n_scans=60)
    s = run(sc, with_overrides(CFG, **{"eval.warmup_s": 100.0}), seed=3, method="imm").summary
    assert s["false_tracks_per_scan"] == 0 and s["missed_per_scan"] == 0 and s["id_switches"] == 0
