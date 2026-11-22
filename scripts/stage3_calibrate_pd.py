"""E1 calibration (docs/PREREGISTRATION_3.md 3.1): SNR at 100 km such that the mean Swerling I Pd over every
truth target-scan of the TUNING window (Schiphol 2026-11-06 10:00-10:15 UTC) is 0.9. No tracker is run.

Writes sensor.snr_ref into configs/stage3.yaml and results/stage3/calibration.json.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab import sensor as SE  # noqa: E402
from radar_track_lab.experiments import load_stage2  # noqa: E402

PFA, R_REF, MEAN_PD = 1e-6, 100_000.0, 0.9


def main() -> None:
    cfg, _ = load_stage2()
    spec = S.specs()["EHAM_1106_tune"]
    assert spec["kind"] == "tune"
    sc, _, _ = S.build(cfg, spec)
    r = np.concatenate([np.hypot(st.pos[:, 0], st.pos[:, 1]) for st in sc.scan_truths])
    snr = SE.calibrate_snr_ref(r, PFA, R_REF, MEAN_PD)
    pd = SE.pd_swerling1(SE.snr_at(r, snr, R_REF), PFA)
    curve = {f"{k} km": float(SE.pd_swerling1(SE.snr_at(k * 1e3, snr, R_REF), PFA)) for k in (10, 30, 50, 70, 90, 100)}
    out = {"window": spec, "target_scans": int(r.size), "pfa": PFA, "r_ref_m": R_REF, "mean_pd_target": MEAN_PD,
           "snr_ref": snr, "snr_ref_db": 10 * np.log10(snr), "mean_pd": float(pd.mean()),
           "share_pd_below_0_8": float(np.mean(pd < 0.8)), "pd_by_range": curve,
           "range_quantiles_km": {q: float(np.percentile(r, q) / 1e3) for q in (5, 25, 50, 75, 95)}}
    (ROOT / "results/stage3").mkdir(parents=True, exist_ok=True)
    (ROOT / "results/stage3/calibration.json").write_text(json.dumps(out, indent=1))
    y = ROOT / "configs/stage3.yaml"
    txt = re.sub(r"(\n  snr_ref: )\S+", lambda m: f"{m.group(1)}{snr:.6f}", y.read_text(), count=1)
    y.write_text(txt)
    print(json.dumps({k: out[k] for k in ("target_scans", "snr_ref", "snr_ref_db", "mean_pd", "share_pd_below_0_8",
                                          "pd_by_range")}, indent=1))


if __name__ == "__main__":
    main()
