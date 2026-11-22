"""readsb / adsb.lol trace handling: privacy filter constants."""

from __future__ import annotations

# readsb dbFlags bitfield (README-json.md, "aircraft.json")
DBFLAG_MILITARY = 1
DBFLAG_INTERESTING = 2
DBFLAG_PIA = 4
DBFLAG_LADD = 8
EXCLUDE_MASK = DBFLAG_MILITARY | DBFLAG_PIA | DBFLAG_LADD

# trace point flag bits
TRACE_FLAG_STALE = 1
TRACE_FLAG_NEW_LEG = 2

GROUND_SENTINEL_FT = -1.0e4


def is_excluded(db_flags: int | None) -> bool:
    """True for military, PIA or LADD aircraft (never used as truth or shown)."""
    return bool(int(db_flags or 0) & EXCLUDE_MASK)

# readsb position source -> small integer stored with each point
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
