"""Figure: estimated vs true clutter density (PREREGISTRATION_4 5.2).

Runs JIPDA-est and JIPDA-map (frozen configs/stage4.yaml) on EHAM_1106_eval lam1000_map seed 20261106 and plots the
density each one uses at the last scan next to the true map density, all on the JIPDA-map grid.
Output: results/stage4/figures/density_map.png and results/stage4/density_map.json (cell-level comparison numbers).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stage4_run import load_stage4  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.sim import make_tracker  # noqa: E402
from radar_track_lab.tracker import TrackerParams  # noqa: E402

SEED = 20261106


def main() -> None:
    cfg0, _ = load_stage4(["radar.clutter_lambda=1000", "radar.clutter_model=map"], "M0")
    sc, _, cfg = S.build(cfg0, S.specs()["EHAM_1106_eval"])
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    trk = {m: make_tracker(m, p, cfg) for m in ("jipda_est", "jipda_map")}
    for k, scan in enumerate(simulate_scans(sc.scan_truths, radar, SEED)):
        for t in trk.values():
            t.process_scan(scan, sc.eval_truths[k].t)
    g = trk["jipda_map"].est
    edges = np.minimum(g.r_min + g.dr * np.arange(g.n_r + 1), g.r_max)
    rc = 0.5 * (edges[:-1] + edges[1:])
    ac = (np.arange(g.n_az) + 0.5) * g.daz
    R, A = np.meshgrid(rc, ac, indexing="ij")
    # true cell means: 8 x 8 sub-samples per cell
    sub = (np.arange(8) + 0.5) / 8
    rr = (g.r_min + (np.arange(g.n_r)[:, None] + sub[None]) * g.dr).clip(max=g.r_max - 1e-6)
    aa = (np.arange(g.n_az)[:, None] + sub[None]) * g.daz
    true = radar.clutter_density(rr[:, None, :, None] + 0 * aa[None, :, None, :],
                                 aa[None, :, None, :] + 0 * rr[:, None, :, None]).mean(axis=(2, 3))
    dens = {"true": true, "jipda_est": trk["jipda_est"].clutter_density(R, A), "jipda_map": g.grid()}
    w = true * g.vol  # weight cells by expected clutter count
    stats = {}
    for m in ("jipda_est", "jipda_map"):
        lr = np.log10(dens[m] / true)
        stats[m] = {"weighted_median_ratio": float(10 ** np.median(np.repeat(lr.ravel(), np.maximum(1, (w.ravel() * 10).astype(int))))),
                    "share_clutter_within_factor2": float(w[np.abs(lr) <= np.log10(2)].sum() / w.sum()),
                    "share_clutter_under_half": float(w[lr < -np.log10(2)].sum() / w.sum())}
    out = {"seed": SEED, "scan": "last", "grid": {"dr_m": g.dr, "daz_deg": float(np.degrees(g.daz)), "tau": -1 / np.log(g.a)},
           "stats": stats}
    (ROOT / "results/stage4").mkdir(parents=True, exist_ok=True)
    (ROOT / "results/stage4/density_map.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))

    rmax = 50_000.0
    keep = rc <= rmax
    fig = plt.figure(figsize=(13, 8.2))
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 0.85], hspace=0.38, wspace=0.12)
    norm = LogNorm(vmin=1e-5, vmax=float(true[keep].max()))
    titles = {"true": "True density (map clutter, λ 1000)", "jipda_est": "JIPDA-est (10 km × 22.5°, 10 scans)",
              "jipda_map": f"JIPDA-map ({g.dr / 1000:.0f} km × {np.degrees(g.daz):.1f}°, τ {-1 / np.log(g.a):.0f} scans)"}
    for i, m in enumerate(("true", "jipda_est", "jipda_map")):
        ax = fig.add_subplot(gs[0, i])
        im = ax.pcolormesh(np.degrees(ac), rc[keep] / 1000, dens[m][keep], norm=norm, cmap="Blues", shading="nearest")
        ax.set_title(titles[m], fontsize=10)
        ax.set_xlabel("azimuth (deg)")
        if i == 0:
            ax.set_ylabel("range (km)")
        else:
            ax.set_yticklabels([])
        ax.set_xticks([0, 90, 180, 270, 360])
    cb = fig.colorbar(im, ax=fig.axes[:3], shrink=0.85, pad=0.01)
    cb.set_label("clutter density per scan [1/(m·rad)]")
    ax = fig.add_subplot(gs[1, :])
    ink = {"true": "#222222", "jipda_est": "#c0602a", "jipda_map": "#2a6fb0"}
    lab = {"true": "true", "jipda_est": "JIPDA-est", "jipda_map": "JIPDA-map"}
    for m in ("true", "jipda_est", "jipda_map"):
        prof = (dens[m] * g.vol).sum(axis=1) / g.vol.sum(axis=1)  # azimuth mean
        ax.plot(rc / 1000, prof, color=ink[m], lw=2, label=lab[m], ls="--" if m == "true" else "-")
    ax.set_yscale("log")
    ax.set_xlabel("range (km)")
    ax.set_ylabel("azimuth-mean density")
    ax.set_title("Azimuth-averaged density vs range (last scan, seed 20261106)", fontsize=10)
    ax.grid(alpha=0.25, lw=0.6)
    ax.legend(frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    p = ROOT / "results/stage4/figures/density_map.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=130, bbox_inches="tight")
    print(p)


if __name__ == "__main__":
    main()
