"""Figure (PREREGISTRATION_5 5.3): estimated / true clutter density of JIPDA-map (stage 4) and JIPDA-amap (frozen
configs/stage5.yaml) at the last scan of EHAM_1106_eval seed 20261106, lam1000_uniform and lam1000_map, on the fine grid.
Each cell is weighted by its expected clutter count (true density x cell volume).
Output: results/stage5/figures/density_ratio.png and results/stage5/density_ratio.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stage5_run import load_stage5  # noqa: E402
from radar_track_lab import scenarios as S  # noqa: E402
from radar_track_lab.radar import RadarParams, simulate_scans  # noqa: E402
from radar_track_lab.sim import make_tracker  # noqa: E402
from radar_track_lab.tracker import TrackerParams  # noqa: E402

SEED = 20261106
COND = {"lam1000_uniform": "uniform_range_azimuth", "lam1000_map": "map"}
INK = {"jipda_map": "#c0602a", "jipda_amap": "#2a6fb0"}
LAB = {"jipda_map": "JIPDA-map (stage 4)", "jipda_amap": "JIPDA-amap (stage 5)"}


def run(cond):
    cfg0, _ = load_stage5(["radar.clutter_lambda=1000", f"radar.clutter_model={COND[cond]}"], "M0")
    sc, _, cfg = S.build(cfg0, S.specs()["EHAM_1106_eval"])
    radar = RadarParams.from_config(cfg)
    p = TrackerParams.from_config(cfg)
    trk = {m: make_tracker(m, p, cfg) for m in ("jipda_map", "jipda_amap")}
    for k, scan in enumerate(simulate_scans(sc.scan_truths, radar, SEED)):
        for t in trk.values():
            t.process_scan(scan, sc.eval_truths[k].t)
    g = trk["jipda_map"].est
    sub = (np.arange(8) + 0.5) / 8
    rr = (g.r_min + (np.arange(g.n_r)[:, None] + sub[None]) * g.dr).clip(max=g.r_max - 1e-6)
    aa = (np.arange(g.n_az)[:, None] + sub[None]) * g.daz
    true = radar.clutter_density(rr[:, None, :, None] + 0 * aa[None, :, None, :],
                                 aa[None, :, None, :] + 0 * rr[:, None, :, None]).mean(axis=(2, 3))
    w = true * g.vol
    lr = {m: np.log10(t.est.grid() / true) for m, t in trk.items()}
    stats = {m: {"weighted_median_ratio": float(10 ** np.median(np.repeat(x.ravel(), np.maximum(1, (w.ravel() * 10).astype(int))))),
                 "share_clutter_within_factor2": float(w[np.abs(x) <= np.log10(2)].sum() / w.sum()),
                 "share_clutter_under_half": float(w[x < -np.log10(2)].sum() / w.sum())} for m, x in lr.items()}
    lv = trk["jipda_amap"].est.level
    stats["jipda_amap"]["share_clutter_by_level"] = {int(k): float(w[lv == k].sum() / w.sum()) for k in np.unique(lv)}
    return lr, w, stats


def main() -> None:
    out, res = {"seed": SEED, "scan": "last"}, {}
    for c in COND:
        res[c] = run(c)
        out[c] = res[c][2]
        print(c, json.dumps(res[c][2]), flush=True)
    (ROOT / "results/stage5/density_ratio.json").write_text(json.dumps(out, indent=1))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
    bins = np.linspace(-2, 1, 61)
    for ax, c in zip(axes, COND):
        lr, w, st = res[c]
        for m in ("jipda_map", "jipda_amap"):
            h, _ = np.histogram(np.clip(lr[m].ravel(), -2, 1), bins=bins, weights=w.ravel())
            ax.step(bins[1:], h / w.sum(), where="pre", color=INK[m], lw=2,
                    label=f"{LAB[m]}: median {st[m]['weighted_median_ratio']:.2f}, under ½ {st[m]['share_clutter_under_half']:.0%}")
        ax.axvline(0, color="#222222", lw=1, ls="--")
        ax.set_title(f"{c} (λ 1000, last scan, seed {SEED})", fontsize=10)
        ax.set_xlabel("log10(estimated / true density), cells weighted by expected clutter")
        ax.grid(alpha=0.25, lw=0.6)
        ax.legend(frameon=False, fontsize=8, loc="upper left")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("share of clutter")
    p = ROOT / "results/stage5/figures/density_ratio.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=130, bbox_inches="tight")
    print(p)


if __name__ == "__main__":
    main()
