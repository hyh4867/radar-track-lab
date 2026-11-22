"""Evaluation audit: per-sample records of the two RMSEs and common-sample comparisons.

Definitions are fixed in docs/AUDIT_PROTOCOL.md.

Two sample tables come out of ``sim.run(..., audit=True)``:

``update``   one row per track update by a detection (the samples behind ``rmse_at_update_m``)
             key = (scan k, detection index within the scan); the detections of a seed are the
             same for every method, so the key is shared between methods.
``scan_end`` one row per truth target per scan (the samples behind ``rmse_m``)
             key = (scan k, anonymous truth id).

Both tables are plain dicts of equal-length numpy arrays.
"""

from __future__ import annotations

import numpy as np

from .metrics import mean_ci

# exclusion reasons (0 = sample is used)
USED = 0
UPD_CLUTTER, UPD_TENTATIVE, UPD_WARMUP, UPD_NO_TRUTH = 1, 2, 3, 4
SE_WARMUP, SE_UNPAIRED = 1, 2
UPD_REASON = {USED: "used", UPD_CLUTTER: "clutter", UPD_TENTATIVE: "tentative", UPD_WARMUP: "warmup",
              UPD_NO_TRUTH: "truth_missing"}
SE_REASON = {USED: "used", SE_WARMUP: "warmup", SE_UNPAIRED: "unpaired"}

UPD_FIELDS = ("k", "det", "truth", "t", "sq", "reason", "track")
SE_FIELDS = ("k", "truth", "t", "sq", "reason", "track", "age")


def table(rows, fields) -> dict:
    a = np.asarray(rows, dtype=float).reshape(-1, len(fields))
    out = {f: a[:, i] for i, f in enumerate(fields)}
    for f in ("k", "det", "truth", "reason", "track"):
        if f in out:
            out[f] = out[f].astype(np.int64)
    return out


def rmse(sq) -> float:
    sq = np.asarray(sq, dtype=float)
    return float(np.sqrt(sq.mean())) if sq.size else float("nan")


def _unique_keys(tab, cols, name):
    key = np.stack([tab[c] for c in cols], axis=1)
    if np.unique(key, axis=0).shape[0] != key.shape[0]:
        raise ValueError(f"duplicate {name} key")
    return {tuple(int(v) for v in r): i for i, r in enumerate(key)}


def common_update(a: dict, b: dict) -> dict:
    """Update-time samples of two methods on the same detections.

    A key present in both tables must refer to the same truth target and the
    same detection time, otherwise the tables do not come from the same
    detections and a ``ValueError`` is raised. The common sample is the set of
    keys used (reason 0) by both methods.
    """
    ia, ib = _unique_keys(a, ("k", "det"), "update"), _unique_keys(b, ("k", "det"), "update")
    both = sorted(set(ia) & set(ib))
    pa = np.array([ia[k] for k in both], dtype=int)
    pb = np.array([ib[k] for k in both], dtype=int)
    if both and (np.any(a["truth"][pa] != b["truth"][pb]) or np.any(a["t"][pa] != b["t"][pb])):
        raise ValueError("update key refers to different truth or time in the two tables")
    ua = {k for k, i in ia.items() if a["reason"][i] == USED}
    ub = {k for k, i in ib.items() if b["reason"][i] == USED}
    com = sorted(ua & ub)
    ca = np.array([ia[k] for k in com], dtype=int)
    cb = np.array([ib[k] for k in com], dtype=int)
    return {"n_a": len(ua), "n_b": len(ub), "n_common": len(com), "only_a": len(ua - ub), "only_b": len(ub - ua),
            "sq_a": a["sq"][ca], "sq_b": b["sq"][cb], "sq_only_a": a["sq"][[ia[k] for k in sorted(ua - ub)]],
            "sq_only_b": b["sq"][[ib[k] for k in sorted(ub - ua)]], "keys": com}


def common_scan_end(a: dict, b: dict) -> dict:
    """Scan-end samples of two methods on the same truth target-scans.

    Both tables must list exactly the same (scan, truth) keys, because the
    truth does not depend on the method. The common sample is the set of keys
    paired within the cut-off (reason 0) by both methods.
    """
    ia, ib = _unique_keys(a, ("k", "truth"), "scan-end"), _unique_keys(b, ("k", "truth"), "scan-end")
    if set(ia) != set(ib):
        raise ValueError("scan-end tables list different truth target-scans")
    counted = {k for k, i in ia.items() if a["reason"][i] != SE_WARMUP}
    ua = {k for k, i in ia.items() if a["reason"][i] == USED}
    ub = {k for k, i in ib.items() if b["reason"][i] == USED}
    com = sorted(ua & ub)
    ca = np.array([ia[k] for k in com], dtype=int)
    cb = np.array([ib[k] for k in com], dtype=int)
    oa, ob = sorted(ua - ub), sorted(ub - ua)
    return {"n_truth": len(counted), "n_a": len(ua), "n_b": len(ub), "n_common": len(com), "only_a": len(oa),
            "only_b": len(ob), "neither": len(counted - ua - ub),
            "sq_a": a["sq"][ca], "sq_b": b["sq"][cb], "age_a": a["age"][ca], "age_b": b["age"][cb],
            "sq_only_a": a["sq"][[ia[k] for k in oa]], "sq_only_b": b["sq"][[ib[k] for k in ob]], "keys": com}


def common_scan_end_many(tabs: dict) -> dict:
    """Scan-end samples paired within the cut-off by every method in ``tabs`` (name -> table)."""
    names = list(tabs)
    idx = {m: _unique_keys(tabs[m], ("k", "truth"), "scan-end") for m in names}
    if any(set(idx[m]) != set(idx[names[0]]) for m in names):
        raise ValueError("scan-end tables list different truth target-scans")
    first = tabs[names[0]]
    counted = {k for k, i in idx[names[0]].items() if first["reason"][i] != SE_WARMUP}
    used = {m: {k for k, i in idx[m].items() if tabs[m]["reason"][i] == USED} for m in names}
    com = sorted(set.intersection(*used.values()))
    rows = {m: np.array([idx[m][k] for k in com], dtype=int) for m in names}
    return {"n_truth": len(counted), "n": {m: len(used[m]) for m in names}, "n_common": len(com),
            "none": len(counted - set.union(*used.values())), "keys": com, "rows": rows,
            "sq": {m: tabs[m]["sq"][rows[m]] for m in names}, "age": {m: tabs[m]["age"][rows[m]] for m in names}}


def paired_diff(x, y) -> dict:
    """Mean and 95% t-interval of ``x - y`` over paired entries (same seeds, same order)."""
    d = np.asarray(x, dtype=float) - np.asarray(y, dtype=float)
    d = d[np.isfinite(d)]
    m, h = mean_ci(d)
    return {"mean": m, "lo": m - h, "hi": m + h, "n": int(d.size)}


def percent_reduction(baseline, method) -> float:
    """100 * (mean(baseline) - mean(method)) / mean(baseline); the denominator is the baseline's seed mean."""
    b, m = float(np.mean(baseline)), float(np.mean(method))
    return 100.0 * (b - m) / b if b else float("nan")
