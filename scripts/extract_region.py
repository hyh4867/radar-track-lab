"""Stream an adsb.lol globe_history day archive and keep only traces near a site.

Usage (the split tar is read from stdin so nothing is extracted to disk):

    cat data/raw/<day>/*.tar.a? | .venv/bin/python -I scripts/extract_region.py \
        --config configs/default.yaml --out data/processed/region_points.npz

Privacy rules applied here, before anything is written:
  * aircraft with dbFlags military (1), PIA (4) or LADD (8) are dropped;
  * non-ICAO addresses (hex starting with "~", e.g. TIS-B) are dropped;
  * the ICAO hex, registration, type and callsign are NOT written. Each kept
    aircraft gets an integer index in archive order (no hash of the hex).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import tarfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab.adsb import DBFLAG_LADD, DBFLAG_MILITARY, DBFLAG_PIA  # noqa: E402
from radar_track_lab.config import load_config  # noqa: E402

SOURCE_CODES = {
    "adsb_icao": 0,
    "adsb_icao_nt": 1,
    "adsr_icao": 2,
    "tisb_icao": 3,
    "mlat": 4,
    "other": 5,
    "mode_s": 6,
    "adsb_other": 7,
    "adsr_other": 8,
    "tisb_other": 9,
    "tisb_trackfile": 10,
    "adsc": 11,
    "unknown": 12,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs/default.yaml"))
    ap.add_argument("--out", default=str(ROOT / "data/processed/region_points.npz"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    lat0 = cfg["site"]["lat_deg"]
    lon0 = cfg["site"]["lon_deg"]
    margin_km = cfg["site"]["extract_radius_km"]
    dlat = margin_km / 111.0
    dlon = margin_km / (111.0 * np.cos(np.radians(lat0)))
    lat_lo, lat_hi = lat0 - dlat, lat0 + dlat
    lon_lo, lon_hi = lon0 - dlon, lon0 + dlon
    lat_tokens = tuple(f",{int(v)}." .encode() for v in range(int(np.floor(lat_lo)), int(np.floor(lat_hi)) + 1))

    counts = {
        "trace_files": 0,
        "non_icao_skipped": 0,
        "prefilter_skipped": 0,
        "parsed": 0,
        "excluded_military": 0,
        "excluded_pia": 0,
        "excluded_ladd": 0,
        "no_points_in_box": 0,
        "kept_aircraft": 0,
        "kept_points": 0,
    }
    cols: dict[str, list] = {k: [] for k in ("ac", "t", "lat", "lon", "alt", "gs", "trk", "flags", "src", "nacp")}

    tf = tarfile.open(fileobj=sys.stdin.buffer, mode="r|")
    for member in tf:
        name = member.name
        if not member.isfile() or "/traces/" not in name or "trace_full_" not in name:
            continue
        counts["trace_files"] += 1
        if "trace_full_~" in name:
            counts["non_icao_skipped"] += 1
            continue
        raw = tf.extractfile(member).read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        if not any(tok in raw for tok in lat_tokens):
            counts["prefilter_skipped"] += 1
            continue
        doc = json.loads(raw)
        counts["parsed"] += 1
        flags = int(doc.get("dbFlags", 0) or 0)

        t0 = float(doc["timestamp"])
        nacp = -1  # carried forward from the last aircraft-details object
        rows = []
        for p in doc.get("trace", []):
            det = p[8] if len(p) > 8 else None
            if isinstance(det, dict) and det.get("nac_p") is not None:
                nacp = int(det["nac_p"])
            lat, lon = p[1], p[2]
            if lat is None or lon is None:
                continue
            if not (lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi):
                continue
            alt = p[3]
            if alt == "ground":
                alt_v = -1.0e4  # sentinel for "on ground"
            elif alt is None:
                alt_v = np.nan
            else:
                alt_v = float(alt)
            src = p[9] if len(p) > 9 and p[9] is not None else "unknown"
            rows.append(
                (
                    t0 + float(p[0]),
                    float(lat),
                    float(lon),
                    alt_v,
                    np.nan if p[4] is None else float(p[4]),
                    np.nan if p[5] is None else float(p[5]),
                    int(p[6]),
                    SOURCE_CODES.get(src, SOURCE_CODES["unknown"]),
                    nacp,
                )
            )
        if not rows:
            counts["no_points_in_box"] += 1
            continue
        # privacy exclusion, counted only for aircraft that were inside the box
        if flags & DBFLAG_MILITARY:
            counts["excluded_military"] += 1
            continue
        if flags & DBFLAG_PIA:
            counts["excluded_pia"] += 1
            continue
        if flags & DBFLAG_LADD:
            counts["excluded_ladd"] += 1
            continue
        idx = counts["kept_aircraft"]
        counts["kept_aircraft"] += 1
        counts["kept_points"] += len(rows)
        for r in rows:
            cols["ac"].append(idx)
            for key, v in zip(("t", "lat", "lon", "alt", "gs", "trk", "flags", "src", "nacp"), r):
                cols[key].append(v)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out,
        ac=np.asarray(cols["ac"], dtype=np.int32),
        t=np.asarray(cols["t"], dtype=np.float64),
        lat=np.asarray(cols["lat"], dtype=np.float64),
        lon=np.asarray(cols["lon"], dtype=np.float64),
        alt=np.asarray(cols["alt"], dtype=np.float32),
        gs=np.asarray(cols["gs"], dtype=np.float32),
        trk=np.asarray(cols["trk"], dtype=np.float32),
        flags=np.asarray(cols["flags"], dtype=np.int16),
        src=np.asarray(cols["src"], dtype=np.int8),
        nacp=np.asarray(cols["nacp"], dtype=np.int8),
    )
    summary = {"counts": counts, "box": [lat_lo, lat_hi, lon_lo, lon_hi], "source_codes": SOURCE_CODES}
    out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
