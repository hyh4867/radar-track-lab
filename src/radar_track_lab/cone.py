"""Cone-aware track hold (stage 4 priority 2, docs/PREREGISTRATION_4.md 9).

Above the radar there is a cone (elevation > ``cone_max_elev_deg``, 42 deg) where the sensor model gives no
detections. A confirmed track that knows its Mode C altitude (from its last associated report) and whose predicted
position is inside the cone is *held*: it takes part in no association, its miss counter does not advance and its
state is only predicted. The hold for a track lasts at most

    T_max = 2 r_c / max(|v|, v_min) + margin,   r_c = (h - h_radar) / tan(cone)

measured from its last update (cone diameter at its altitude over its speed; flat-earth r_c, the curvature term is
under 20 m inside 15 km). After T_max the usual K-miss rule runs again.

Mode C is attached to each target report from the scan truth (the same quantised altitude the sensor model already
uses for its slant-range correction); clutter reports have none (NaN).
"""

from __future__ import annotations

import numpy as np

from . import sensor as SE
from .geo import cart_to_polar
from .tracker import CONFIRMED

HOLD = 7  # temporary status while a track is held (not CONFIRMED/TENTATIVE: skipped by association and M-of-N)


def with_modec(scans, scan_truths, step_ft: float = 100.0):
    """Attach ``alt`` (Mode C [m], NaN for clutter) to each scan. Scan k must come from scan_truths[k]."""
    for sc, st in zip(scans, scan_truths):
        alt = np.full(sc.t.size, np.nan)
        if st.alt is not None and st.ids.size:
            o = np.argsort(st.ids)
            tgt = sc.truth_id >= 0
            k = o[np.searchsorted(st.ids[o], sc.truth_id[tgt])]
            alt[tgt] = SE.mode_c(st.alt[k], step_ft)
        sc.alt = alt
    return scans


def cone_radius(alt_m, h_radar_m, cone_deg):
    return np.maximum(np.asarray(alt_m, float) - h_radar_m, 0.0) / np.tan(np.radians(cone_deg))


def hold_time(alt_m, speed_mps, h_radar_m, cone_deg, v_min=50.0, margin_s=9.6):
    return 2.0 * cone_radius(alt_m, h_radar_m, cone_deg) / np.maximum(speed_mps, v_min) + margin_s


class ConeHoldMixin:
    """Mix in before EKFTracker / IMMTracker. Call ``setup_cone`` after construction."""

    def setup_cone(self, radar, v_min=50.0, margin_s=9.6):
        self.radar_c, self.v_min, self.margin_s = radar, float(v_min), float(margin_s)
        self.alt_by_id: dict[int, float] = {}
        self.cone_stats = {"held_track_scans": 0, "hold_expired": 0}
        self.name = self.name + " + cone hold"

    def held_mask(self, scan):
        n = self.ids.size
        if n == 0:
            return np.zeros(0, bool)
        alt = np.array([self.alt_by_id.get(int(i), np.nan) for i in self.ids])
        rd = self.radar_c
        cand = (self.status == CONFIRMED) & np.isfinite(alt)
        if not cand.any():
            return cand
        # predicted position at the predicted illumination time (two fixed-point steps, as JPDATracker)
        t = np.full(n, float(scan.t0))
        for _ in range(2):
            pos = self.X[:, :2] + (t - self.T)[:, None] * self.X[:, 2:]
            _, az = cart_to_polar(pos[:, 0], pos[:, 1])
            t = scan.t0 + az / rd.omega
        t = np.maximum(t, self.T)
        pos = self.X[:, :2] + (t - self.T)[:, None] * self.X[:, 2:]
        d = np.hypot(pos[:, 0], pos[:, 1])
        _, el = SE.slant_and_elevation(d, rd.antenna_height_m, np.where(np.isfinite(alt), alt, 0.0), rd.a_e)
        inside = el > np.radians(rd.cone_max_elev_deg)
        tmax = hold_time(alt, np.hypot(self.X[:, 2], self.X[:, 3]), rd.antenna_height_m, rd.cone_max_elev_deg,
                         self.v_min, self.margin_s)
        within = (t - self.T) <= tmax
        self.cone_stats["hold_expired"] += int((cand & inside & ~within).sum())
        return cand & inside & within

    def process_scan(self, scan, t_end: float):
        held = self.held_mask(scan)
        saved = {}
        if held.any():
            for i in np.flatnonzero(held):
                saved[int(self.ids[i])] = (self.status[i], self.hits[i], self.scans[i], self.misses[i])
                self.status[i] = HOLD
            self.cone_stats["held_track_scans"] += int(held.sum())
        records = super().process_scan(scan, t_end)
        if saved:
            for i in np.flatnonzero(np.isin(self.ids, list(saved))):
                self.status[i], self.hits[i], self.scans[i], self.misses[i] = saved[int(self.ids[i])]
        alt = getattr(scan, "alt", None)
        if alt is not None:
            for rec in records:
                a = alt[rec[1]]
                if np.isfinite(a):
                    self.alt_by_id[rec[0]] = float(a)
        return records


# --- stage 5: cone hold v2 (docs/PREREGISTRATION_5.md, part 2) ---------------------------------------------------
FT = 0.3048
DH0_M = 200.0 * FT  # altitude window at zero elapsed time: two Mode C steps
DH_RATE_MPS = 50.0 * FT  # window growth per second since the last Mode C
VZ_MAX_MPS = 100.0 * FT  # vertical speed estimate is clipped to this
VZ_SPAN_S = 30.0  # Mode C history used for the vertical speed fit
VZ_MIN_SPAN_S = 9.6  # fewer seconds of history than this -> vertical speed 0


def vz_estimate(times, alts, span_s=VZ_SPAN_S, min_span_s=VZ_MIN_SPAN_S, vz_max=VZ_MAX_MPS):
    """Least-squares vertical speed [m/s] from the Mode C history of the last ``span_s`` seconds (0 if too short)."""
    t = np.asarray(times, float)
    a = np.asarray(alts, float)
    if t.size < 2:
        return 0.0
    sel = t >= t[-1] - span_s
    t, a = t[sel], a[sel]
    if t.size < 2 or t[-1] - t[0] < min_span_s:
        return 0.0
    tc = t - t.mean()
    vz = float(np.dot(tc, a - a.mean()) / np.dot(tc, tc))
    return float(np.clip(vz, -vz_max, vz_max))


def predicted_alt(alt_last, t_last, vz, t):
    return alt_last + vz * (np.asarray(t, float) - t_last)


def alt_window(dt_s):
    return DH0_M + DH_RATE_MPS * np.maximum(np.asarray(dt_s, float), 0.0)


def alt_gate(report_alt, alt_last, t_last, vz, t_report):
    """True where the report has Mode C within the window around the predicted altitude (NaN -> False)."""
    ra = np.asarray(report_alt, float)
    pred = predicted_alt(alt_last, t_last, vz, t_report)
    with np.errstate(invalid="ignore"):
        return np.isfinite(ra) & (np.abs(ra - pred) <= alt_window(np.asarray(t_report, float) - t_last))


class ConeHoldV2Mixin(ConeHoldMixin):
    """H1 (``variant='h1'``): the stage 4 hold plus an altitude check. A track that is held, or was held and has not
    been updated since, takes part in association but only with target reports whose Mode C is within
    ``alt_window`` of its predicted altitude (last Mode C + vertical speed x elapsed); reports without Mode C
    (clutter) never join it. A held track that gets no report keeps its miss count (as in stage 4).
    H2 (``variant='h2'``): H1, and the cone entry test and the hold time use the extrapolated altitude instead of
    the last Mode C. Mix in before EKFTracker / IMMTracker; call ``setup_cone_v2`` after construction."""

    def setup_cone_v2(self, radar, variant="h1", v_min=50.0, margin_s=9.6, hist_n=8, gate_all=False):
        """``gate_all`` (stage 6 G1, docs/PREREGISTRATION_6.md): the altitude check also for every other confirmed
        track with a Mode C history, applied to reports that carry Mode C (reports without Mode C: 2-D gate only)."""
        self.setup_cone(radar, v_min, margin_s)
        self.gate_all = bool(gate_all)
        if variant not in ("h1", "h2"):
            raise ValueError(variant)
        self.variant, self.hist_n = variant, int(hist_n)
        self.name = self.name.replace(" + cone hold", f" + cone hold v2 {variant.upper()}") + (" + G1" if gate_all else "")
        self.hist: dict[int, list] = {}  # id -> [(t, Mode C)] (last hist_n)
        self.check_ids: set[int] = set()  # held, or held and not updated since
        self._held_now = np.zeros(0, bool)
        self.cone_stats.update({"gate_rejected_pairs": 0, "held_updates": 0})

    def _alt_state(self, ids):
        """Last Mode C, its time and vertical speed per id (NaN where unknown)."""
        n = len(ids)
        a, t, vz = np.full(n, np.nan), np.full(n, np.nan), np.zeros(n)
        for k, i in enumerate(ids):
            h = self.hist.get(int(i))
            if h:
                t[k], a[k] = h[-1]
                vz[k] = vz_estimate([x[0] for x in h], [x[1] for x in h])
        return a, t, vz

    def held_mask(self, scan):
        if self.variant == "h1":
            return super().held_mask(scan)
        n = self.ids.size
        if n == 0:
            return np.zeros(0, bool)
        a_last, t_last, vz = self._alt_state(self.ids)
        rd = self.radar_c
        cand = (self.status == CONFIRMED) & np.isfinite(a_last)
        if not cand.any():
            return cand
        t = np.full(n, float(scan.t0))
        for _ in range(2):
            pos = self.X[:, :2] + (t - self.T)[:, None] * self.X[:, 2:]
            _, az = cart_to_polar(pos[:, 0], pos[:, 1])
            t = scan.t0 + az / rd.omega
        t = np.maximum(t, self.T)
        pos = self.X[:, :2] + (t - self.T)[:, None] * self.X[:, 2:]
        d = np.hypot(pos[:, 0], pos[:, 1])
        alt = np.where(cand, predicted_alt(np.where(cand, a_last, 0.0), np.where(cand, t_last, 0.0), vz, t), 0.0)
        _, el = SE.slant_and_elevation(d, rd.antenna_height_m, alt, rd.a_e)
        inside = el > np.radians(rd.cone_max_elev_deg)
        tmax = hold_time(alt, np.hypot(self.X[:, 2], self.X[:, 3]), rd.antenna_height_m, rd.cone_max_elev_deg,
                         self.v_min, self.margin_s)
        within = (t - self.T) <= tmax
        self.cone_stats["hold_expired"] += int((cand & inside & ~within).sum())
        return cand & inside & within

    def _extra_gate(self, ok, tracks, dets, scan):
        gate_all = getattr(self, "gate_all", False)
        if ok.size == 0 or (not self.check_ids and not gate_all):
            return ok
        tid = self.ids[tracks[ok]]
        chk = np.isin(tid, list(self.check_ids)) if self.check_ids else np.zeros(ok.size, bool)
        alt = getattr(scan, "alt", None)
        rep = np.full(ok.size, np.nan) if alt is None else alt[dets[ok]]
        good = np.ones(ok.size, bool)
        if chk.any():  # H1: held / just released -> only reports with matching Mode C
            a_last, t_last, vz = self._alt_state(tid[chk])
            g = alt_gate(rep[chk], a_last, t_last, vz, scan.t[dets[ok]][chk])
            good[np.flatnonzero(chk)] = g & np.isfinite(a_last)
            self.cone_stats["gate_rejected_pairs"] += int((~good[chk]).sum())
        if gate_all:  # G1 (stage 6): every other confirmed track with a Mode C history, reports with Mode C only
            cand = (~chk) & (self.status[tracks[ok]] == CONFIRMED) & np.isfinite(rep)
            if cand.any():
                cand &= np.array([int(i) in self.hist and bool(self.hist[int(i)]) for i in tid])
            if cand.any():
                u, inv = np.unique(tid[cand], return_inverse=True)
                a_last, t_last, vz = self._alt_state(u)
                g = alt_gate(rep[cand], a_last[inv], t_last[inv], vz[inv], scan.t[dets[ok]][cand])
                good[np.flatnonzero(cand)] = g
                self.cone_stats["g1_rejected_pairs"] = self.cone_stats.get("g1_rejected_pairs", 0) + int((~g).sum())
        return ok[good]

    def _manage(self, scan, hit, t_end):
        dec = self._held_now & ~hit
        if dec.any():  # held and not updated: the miss count does not advance (MofN adds 1)
            self.misses[dec] -= 1
        super()._manage(scan, hit, t_end)

    def process_scan(self, scan, t_end: float):
        held = self.held_mask(scan)
        self._held_now = held
        if held.any():
            self.check_ids.update(int(i) for i in self.ids[held])
            self.cone_stats["held_track_scans"] += int(held.sum())
        records = _TrackerBaseProcess(self, scan, t_end)
        self._held_now = np.zeros(self.ids.size, bool)
        alt = getattr(scan, "alt", None)
        for rec in records:
            i = rec[0]
            if i in self.check_ids:
                self.check_ids.discard(i)
                self.cone_stats["held_updates"] += 1
            if alt is not None and np.isfinite(alt[rec[1]]):
                a = float(alt[rec[1]])
                self.alt_by_id[i] = a
                h = self.hist.setdefault(i, [])
                h.append((float(rec[2]), a))
                del h[:-self.hist_n]
        live = set(int(i) for i in self.ids)
        self.check_ids &= live
        for i in [i for i in self.hist if i not in live]:
            del self.hist[i]
        return records


def _TrackerBaseProcess(trk, scan, t_end):
    """The tracker's own process_scan, skipping ConeHoldMixin.process_scan (v2 keeps held tracks CONFIRMED)."""
    return super(ConeHoldMixin, trk).process_scan(scan, t_end)


# --- stage 6: Mode C errors (docs/PREREGISTRATION_6.md) --------------------------------------------------------
MODEC_ERR_MAX_FT = 45_000.0


def apply_modec_errors(scans, seed, p_missing=0.02, p_wrong=0.01, step_ft=100.0, max_ft=MODEC_ERR_MAX_FT):
    """Assumed Mode C faults on target reports (not literature values): each report with Mode C independently loses
    it (NaN) with ``p_missing`` or, otherwise, carries a wrong value (uniform 0..max_ft, quantised) with ``p_wrong``.
    Own random stream (seed, 6060): detections and clutter are unchanged."""
    rng = np.random.default_rng([int(seed), 6060])
    for sc in scans:
        a = sc.alt
        fin = np.isfinite(a)
        u = rng.random(a.size)
        w = rng.uniform(0.0, max_ft * FT, a.size)
        miss = fin & (u < p_missing)
        wrong = fin & (u >= p_missing) & (u < p_missing + p_wrong)
        a = a.copy()
        a[miss] = np.nan
        a[wrong] = SE.mode_c(w[wrong], step_ft)
        sc.alt = a
    return scans
