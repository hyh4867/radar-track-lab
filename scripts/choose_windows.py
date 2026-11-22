"""Apply the preregistered window rules and write results/data/stage2/scenarios.json.

Rule for a new site: the 30 minutes that start 10 minutes before the busiest
5-minute bin of the day (airborne aircraft within 100 km; earliest bin on a
tie), shifted into 00:03-23:27 UTC if needed. Only traffic counts are used.
The second day reuses the UTC windows found on the first day.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.adsb import GROUND_SENTINEL_FT  # noqa: E402
from radar_track_lab.config import load_config  # noqa: E402
from radar_track_lab.geo import geodetic_to_enu  # noqa: E402
from radar_track_lab.scenarios import points_path  # noqa: E402
from radar_track_lab.truth import load_points  # noqa: E402

DAY1, DAY2 = "2026-11-06", "2026-11-11"


def profile(day, site, lat0, lon0):
    pts = load_points(points_path(day, site))
    e, n, _ = geodetic_to_enu(pts["lat"], pts["lon"], lat0, lon0)
    inside = (pts["alt"] > GROUND_SENTINEL_FT + 1) & (np.hypot(e, n) <= 100_000.0)
    day0 = np.datetime64(day + "T00:00:00").astype("datetime64[s]").astype(np.int64)
    b = ((pts["t"] - day0) // 300).astype(int)
    return [int(np.unique(pts["ac"][inside & (b == i)]).size) for i in range(288)]


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def main() -> None:
    sites = load_config(ROOT / "configs/sites.yaml")["sites"]
    scen, prof = [], {}

    def add(sid, site, day, start_min, dur, kind, note=""):
        scen.append({"id": sid, "site": site, "day": day, "start_utc": f"{day}T{hhmm(start_min)}:00Z",
                     "duration_s": dur, "kind": kind, "note": note})

    add("EHAM_1106_eval", "EHAM", DAY1, 12 * 60 + 45, 1800, "stage1_eval", "stage 1 evaluation window")
    add("EHAM_1106_tune", "EHAM", DAY1, 10 * 60, 900, "tune", "tuning window (never used for evaluation)")
    add("EHAM_1106_night", "EHAM", DAY1, 2 * 60, 1800, "oos_time", "deep night, fixed in the preregistration")
    add("EHAM_1106_early", "EHAM", DAY1, 4 * 60 + 30, 1800, "oos_time", "early morning, fixed in the preregistration")
    add("EHAM_1106_busy2", "EHAM", DAY1, 14 * 60 + 40, 1800, "oos_time", "other busy period, fixed in the preregistration")
    windows = {"EHAM": 12 * 60 + 45}
    for site, s in sites.items():
        if site == "EHAM" or not points_path(DAY1, site).exists():
            continue
        p = profile(DAY1, site, s["lat_deg"], s["lon_deg"])
        peak = int(np.argmax(p))  # earliest on a tie
        start = min(max(peak * 5 - 10, 3), 23 * 60 + 27 - 30)
        prof[site] = {"busiest_bin_utc": hhmm(peak * 5), "aircraft_in_busiest_bin": p[peak], "hourly_max": [max(p[h * 12:(h + 1) * 12]) for h in range(24)]}
        windows[site] = start
        add(f"{site}_1106_peak", site, DAY1, start, 1800, "oos_site_" + s["role"], f"busiest 5-min bin {hhmm(peak * 5)} ({p[peak]} aircraft)")
    for site, start in windows.items():
        if points_path(DAY2, site).exists():
            add(f"{site}_1111_same", site, DAY2, start, 1800, "oos_day_" + sites[site]["role"], "same UTC window on the second day")
    out = {"rule": __doc__.strip(), "profiles": prof, "scenarios": scen}
    (ROOT / "results/data/stage2").mkdir(parents=True, exist_ok=True)
    (ROOT / "results/data/stage2/scenarios.json").write_text(json.dumps(out, indent=1))
    for s in scen:
        print(s["id"], s["start_utc"], s["kind"], s["note"])


if __name__ == "__main__":
    main()
