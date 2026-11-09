"""Count airborne ADS-B aircraft inside the radar coverage per 5-minute bin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.adsb import GROUND_SENTINEL_FT  # noqa: E402
from radar_track_lab.config import load_config  # noqa: E402
from radar_track_lab.geo import geodetic_to_enu  # noqa: E402
from radar_track_lab.truth import load_points  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs/default.yaml"))
    ap.add_argument("--out", default=str(ROOT / "results/data/traffic_profile.json"))
    args = ap.parse_args()
    cfg = load_config(args.config)
    pts = load_points(ROOT / cfg["truth"]["points_file"])
    e, n, _ = geodetic_to_enu(pts["lat"], pts["lon"], cfg["site"]["lat_deg"], cfg["site"]["lon_deg"])
    r = np.hypot(e, n)
    air = pts["alt"] > GROUND_SENTINEL_FT + 1
    inside = air & (r <= cfg["radar"]["max_range_m"])
    t = pts["t"]
    day0 = np.floor(t.min() / 86400) * 86400
    bins = ((t - day0) // 300).astype(int)
    out = []
    for b in range(288):
        m = inside & (bins == b)
        out.append({"utc_min": b * 5, "aircraft": int(np.unique(pts["ac"][m]).size)})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"day0_unix": day0, "bins": out}, indent=1))
    top = sorted(out, key=lambda d: -d["aircraft"])[:12]
    for d in sorted(out, key=lambda d: d["utc_min"]):
        if d["utc_min"] % 60 == 0:
            print(f"{d['utc_min']//60:02d}:00 UTC  {d['aircraft']:4d} " + "#" * (d["aircraft"] // 4))
    print("busiest 5-min bins:", [(f"{d['utc_min']//60:02d}:{d['utc_min']%60:02d}", d["aircraft"]) for d in top])


if __name__ == "__main__":
    main()
