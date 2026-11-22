"""Stream one adsb.lol day archive once and keep the traces near several sites.

    cat data/raw/<day>/*.tar.a? | .venv/bin/python -I scripts/extract_sites.py --day 2026-11-06

Same privacy rules as scripts/extract_region.py, applied before anything is
kept: dbFlags military / PIA / LADD aircraft and non-ICAO addresses are
dropped; no ICAO hex, registration, type or callsign is written. Each kept
aircraft gets an integer index per site in archive order.

Output: data/processed/sites/<day>_<SITE>.npz (same columns as
region_points.npz) and results/data/stage2/extract_<day>.json (counts only).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import tarfile
import time
from array import array
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.adsb import DBFLAG_LADD, DBFLAG_MILITARY, DBFLAG_PIA, SOURCE_CODES  # noqa: E402
from radar_track_lab.config import load_config  # noqa: E402

COLS = ("ac", "t", "lat", "lon", "alt", "gs", "trk", "flags", "src", "nacp")  # no identifier column exists
TYPES = {"ac": "i", "t": "d", "lat": "d", "lon": "d", "alt": "f", "gs": "f", "trk": "f", "flags": "h", "src": "b",
         "nacp": "b"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--sites", default=str(ROOT / "configs/sites.yaml"))
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    sc = load_config(args.sites)
    margin = float(sc["extract_radius_km"])
    names = [s for s in sc["sites"] if not args.only or s in args.only.split(",")]
    box = {}
    for s in names:
        lat0, lon0 = sc["sites"][s]["lat_deg"], sc["sites"][s]["lon_deg"]
        dlat = margin / 111.0
        dlon = margin / (111.0 * np.cos(np.radians(lat0)))
        box[s] = (lat0 - dlat, lat0 + dlat, lon0 - dlon, lon0 + dlon)
    blo = np.array([[box[s][0], box[s][2]] for s in names])
    bhi = np.array([[box[s][1], box[s][3]] for s in names])
    cols = {s: {k: array(TYPES[k]) for k in COLS} for s in names}
    counts = {s: {"aircraft_in_box": 0, "excluded_military": 0, "excluded_pia": 0, "excluded_ladd": 0,
                  "kept_aircraft": 0, "kept_points": 0} for s in names}
    tot = {"trace_files": 0, "non_icao_skipped": 0, "parsed": 0}
    t_start = time.time()
    log = ROOT / f"data/processed/sites/extract_{args.day}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    tf = tarfile.open(fileobj=sys.stdin.buffer, mode="r|")
    for member in tf:
        name = member.name
        if not member.isfile() or "/traces/" not in name or "trace_full_" not in name:
            continue
        tot["trace_files"] += 1
        if tot["trace_files"] % 5000 == 0:
            with open(log, "a") as fh:
                fh.write(f"{time.time()-t_start:7.0f}s files={tot['trace_files']} "
                         + " ".join(f"{s}={counts[s]['kept_points']}" for s in names) + "\n")
        if "trace_full_~" in name:
            tot["non_icao_skipped"] += 1
            continue
        raw = tf.extractfile(member).read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        doc = json.loads(raw)
        tot["parsed"] += 1
        tr = doc.get("trace", [])
        if not tr:
            continue
        ll = np.array([(p[1] if p[1] is not None else np.nan, p[2] if p[2] is not None else np.nan) for p in tr])
        inside = (ll[:, None, :] >= blo[None]) & (ll[:, None, :] <= bhi[None])
        inside = inside.all(axis=2)  # (points, sites)
        hit = np.flatnonzero(inside.any(axis=0))
        if hit.size == 0:
            continue
        flags = int(doc.get("dbFlags", 0) or 0)
        t0 = float(doc["timestamp"])
        nacp = np.empty(len(tr), dtype=np.int16)
        cur = -1  # carried forward from the last aircraft-details object
        for i, p in enumerate(tr):
            det = p[8] if len(p) > 8 else None
            if isinstance(det, dict) and det.get("nac_p") is not None:
                cur = int(det["nac_p"])
            nacp[i] = cur
        for si in hit:
            s = names[si]
            c = counts[s]
            c["aircraft_in_box"] += 1
            if flags & DBFLAG_MILITARY:
                c["excluded_military"] += 1
                continue
            if flags & DBFLAG_PIA:
                c["excluded_pia"] += 1
                continue
            if flags & DBFLAG_LADD:
                c["excluded_ladd"] += 1
                continue
            idx = c["kept_aircraft"]
            c["kept_aircraft"] += 1
            col = cols[s]
            for i in np.flatnonzero(inside[:, si]):
                p = tr[i]
                alt = p[3]
                src = p[9] if len(p) > 9 and p[9] is not None else "unknown"
                col["ac"].append(idx)
                col["t"].append(t0 + float(p[0]))
                col["lat"].append(float(p[1]))
                col["lon"].append(float(p[2]))
                col["alt"].append(-1.0e4 if alt == "ground" else (float("nan") if alt is None else float(alt)))
                col["gs"].append(float("nan") if p[4] is None else float(p[4]))
                col["trk"].append(float("nan") if p[5] is None else float(p[5]))
                col["flags"].append(int(p[6]))
                col["src"].append(SOURCE_CODES.get(src, SOURCE_CODES["unknown"]))
                col["nacp"].append(int(nacp[i]))
                c["kept_points"] += 1

    dt = {"ac": np.int32, "t": np.float64, "lat": np.float64, "lon": np.float64, "alt": np.float32, "gs": np.float32,
          "trk": np.float32, "flags": np.int16, "src": np.int8, "nacp": np.int8}
    for s in names:
        np.savez_compressed(ROOT / f"data/processed/sites/{args.day}_{s}.npz",
                            **{k: np.asarray(cols[s][k], dtype=dt[k]) for k in COLS})
    out = {"day": args.day, "totals": tot, "sites": {s: {**counts[s], "box": list(box[s])} for s in names},
           "seconds": time.time() - t_start}
    (ROOT / "results/data/stage2").mkdir(parents=True, exist_ok=True)
    (ROOT / f"results/data/stage2/extract_{args.day}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
