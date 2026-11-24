"""Crossing events at different altitudes (stage 6, docs/PREREGISTRATION_6.md).

A crossing event is a maximal run of consecutive scans in which two aircraft are within ``near_m`` horizontally
and differ in altitude by at least ``dalt_ft`` (truth positions and barometric altitudes at illumination, scan
truth). A crossing switch is an ID switch of either aircraft whose interval [k_last, k_new] overlaps the event
scans widened by ``pad`` scans on each side; each switch counts once.
"""

from __future__ import annotations

import numpy as np

FT = 0.3048


def crossing_events(scan_truths, near_m=2000.0, dalt_ft=1000.0):
    """List of (id_a, id_b, k_start, k_end), id_a < id_b."""
    active: dict[tuple[int, int], list] = {}
    out = []
    for k, st in enumerate(scan_truths):
        now = set()
        if st.alt is not None and st.ids.size > 1:
            p, a, ids = st.pos, st.alt, st.ids
            d = np.hypot(p[:, None, 0] - p[None, :, 0], p[:, None, 1] - p[None, :, 1])
            da = np.abs(a[:, None] - a[None, :])
            i, j = np.nonzero(np.triu((d < near_m) & (da >= dalt_ft * FT), 1))
            for x, y in zip(i, j):
                key = (int(min(ids[x], ids[y])), int(max(ids[x], ids[y])))
                now.add(key)
                if key in active and active[key][1] == k - 1:
                    active[key][1] = k
                else:
                    if key in active:
                        out.append((*key, *active[key]))
                    active[key] = [k, k]
        for key in [q for q in active if q not in now and active[q][1] < k]:
            out.append((*key, *active.pop(key)))
    out += [(*key, *v) for key, v in active.items()]
    return sorted(out, key=lambda e: (e[2], e[0], e[1]))


def crossing_switches(events, switches, pad=3):
    """Number of switches (dicts with target, k_last, k_new) overlapping a crossing event of their target."""
    by_id: dict[int, list] = {}
    for a, b, k0, k1 in events:
        by_id.setdefault(a, []).append((k0 - pad, k1 + pad))
        by_id.setdefault(b, []).append((k0 - pad, k1 + pad))
    n = 0
    for s in switches:
        if any(s["k_last"] <= hi and s["k_new"] >= lo for lo, hi in by_id.get(int(s["target"]), ())):
            n += 1
    return n
