"""Stage 2 diagnostics: truth turn rates, ID-switch causes, straight/turn RMSE.

Definitions are fixed in docs/PREREGISTRATION_2.md, section 2.
"""

from __future__ import annotations

import numpy as np

from .geo import wrap_pi

TURN_DPS = 1.0  # |turn rate| at or above this is a turn
SPEED_RATE = 1.0  # m/s^2
NEAR_OTHER_M = 3000.0
NEAR_RADAR_M = 5000.0
WINDOW = (-3, 2)  # scans relative to the last scan the old track was assigned
CAUSES = ("truth_gap", "near_other", "turn", "misses", "near_radar", "speed_change", "unexplained")
LOST = ("turn", "misses", "near_radar", "speed_change", "unexplained")


class TruthKinematics:
    """Per-scan truth turn rate [deg/s] and speed rate [m/s^2] at the evaluation times."""

    def __init__(self, scenario):
        ev = scenario.eval_truths
        ids = sorted(set().union(*[set(int(i) for i in e.ids) for e in ev])) if ev else []
        self.col = {tid: j for j, tid in enumerate(ids)}
        n, m = len(ev), len(ids)
        self.t = np.array([e.t for e in ev])
        psi = np.full((n, m), np.nan)
        spd = np.full((n, m), np.nan)
        self.pos = np.full((n, m, 2), np.nan)
        for k, e in enumerate(ev):
            j = [self.col[int(i)] for i in e.ids]
            psi[k, j] = np.arctan2(e.vel[:, 1], e.vel[:, 0])
            spd[k, j] = np.hypot(e.vel[:, 0], e.vel[:, 1])
            self.pos[k, j] = e.pos
        self.present = np.isfinite(psi)
        w = np.full((n, m), np.nan)
        a = np.full((n, m), np.nan)
        T = float(np.median(np.diff(self.t))) if n > 1 else 1.0
        for lo, hi in ((-1, 1), (0, 1), (-1, 0)):  # centred first, then one-sided
            k = np.arange(n)
            ka, kb = k + lo, k + hi
            ok = (ka >= 0) & (kb < n)
            ka, kb = np.clip(ka, 0, n - 1), np.clip(kb, 0, n - 1)
            dpsi = wrap_pi(psi[kb] - psi[ka]) / ((hi - lo) * T)
            dspd = (spd[kb] - spd[ka]) / ((hi - lo) * T)
            use = ok[:, None] & np.isfinite(dpsi) & ~np.isfinite(w) & self.present
            w[use] = dpsi[use]
            a[use] = dspd[use]
        self.turn_dps = np.degrees(w)
        self.speed = spd
        self.speed_rate = a
        self.range = np.hypot(self.pos[..., 0], self.pos[..., 1])

    def window_max(self, arr, k, tid, window=WINDOW):
        j = self.col[tid]
        lo, hi = max(k + window[0], 0), min(k + window[1], arr.shape[0] - 1)
        v = np.abs(arr[lo:hi + 1, j])
        return float(np.nanmax(v)) if np.isfinite(v).any() else float("nan")

    def turning(self, k, tid) -> bool:
        v = self.turn_dps[k, self.col[tid]]
        return bool(np.isfinite(v) and abs(v) >= TURN_DPS)


def _missed(scenario, scans):
    """Set of (scan, target) where the target was illuminated but not detected."""
    out = set()
    for k, (st, sc) in enumerate(zip(scenario.scan_truths, scans)):
        det = set(int(i) for i in sc.truth_id if i >= 0)
        out.update((k, int(i)) for i in st.ids if int(i) not in det)
    return out


def classify_switches(scenario, kin: TruthKinematics, result, warm_t: float):
    """One dict per ID switch of ``result`` (run with ``record=True``)."""
    missed = _missed(scenario, result.scans)
    events, last, last_k = [], {}, {}
    for k, ev in enumerate(result.evals):
        present_k = kin.present[k]
        for tid, trk in ev.assigned.items():
            if tid in last and last[tid] != trk and ev.t >= warm_t:
                j, kl = kin.col[tid], last_k[tid]
                gap = bool((~kin.present[kl + 1:k, j]).any())
                d = np.hypot(*(kin.pos[k] - kin.pos[k, j]).T)
                d[j] = np.inf
                d[~present_k] = np.inf
                nearest = float(d.min()) if d.size else float("inf")
                lo, hi = max(kl + WINDOW[0], 0), min(kl + WINDOW[1], len(result.evals) - 1)
                n_miss = sum((kk, tid) in missed for kk in range(lo, hi + 1))
                turn = kin.window_max(kin.turn_dps, kl, tid)
                srate = kin.window_max(kin.speed_rate, kl, tid)
                rng = float(kin.range[kl, j])
                is_turn = bool(np.isfinite(turn) and turn >= TURN_DPS)
                if gap:
                    cause = "truth_gap"
                elif nearest < NEAR_OTHER_M:
                    cause = "near_other"
                elif is_turn:
                    cause = "turn"
                elif n_miss >= 2:
                    cause = "misses"
                elif rng < NEAR_RADAR_M:
                    cause = "near_radar"
                elif np.isfinite(srate) and srate >= SPEED_RATE:
                    cause = "speed_change"
                else:
                    cause = "unexplained"
                events.append({
                    "target": tid, "k_last": kl, "k_new": k, "scans_unassigned": k - kl - 1, "cause": cause,
                    "max_turn_dps": turn, "misses_in_window": n_miss, "nearest_other_m": nearest,
                    "range_m": rng, "max_speed_rate": srate, "turn_and_misses": bool(is_turn and n_miss >= 2),
                    "speed_mps": float(kin.speed[kl, j]),
                })
            last[tid], last_k[tid] = trk, k
    return events


def base_rates(kin: TruthKinematics, result, warm_t: float) -> dict:
    """Share of assigned target-scans whose window has a turn / whose scan is a turn."""
    n = n_win = n_now = 0
    for k, ev in enumerate(result.evals):
        if ev.t < warm_t:
            continue
        for tid in ev.assigned:
            n += 1
            v = kin.window_max(kin.turn_dps, k, tid)
            n_win += bool(np.isfinite(v) and v >= TURN_DPS)
            n_now += kin.turning(k, tid)
    return {"assigned_target_scans": n, "window_turn": n_win, "scan_turn": n_now}


def split_rmse(kin: TruthKinematics, result, warm_t: float) -> dict:
    """Squared-error sums of assigned pairs on straight and turning target-scans."""
    s = {"straight": [0.0, 0], "turn": [0.0, 0]}
    for k, ev in enumerate(result.evals):
        if ev.t < warm_t:
            continue
        for tid, sq in zip(ev.pair_truth, ev.sq_err):
            key = "turn" if kin.turning(k, int(tid)) else "straight"
            s[key][0] += float(sq)
            s[key][1] += 1
    return {f"sq_{k}": v[0] for k, v in s.items()} | {f"n_{k}": v[1] for k, v in s.items()}
