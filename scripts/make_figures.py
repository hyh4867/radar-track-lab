"""Figures for the README: noise sweep curves and NEES consistency."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "results/data"
FIG = ROOT / "results/figures"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SERIES = {"ekf": "#2a78d6", "nn": "#eb6834"}  # categorical slots 1, 2
LABEL = {"ekf": "EKF + GNN tracker", "nn": "Nearest-neighbour baseline"}
MARKER = {"ekf": "o", "nn": "s"}


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelsize=8.5)
    ax.grid(True, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)


def sweep_figure(metric: str, ylabel: str, fname: str, title: str):
    d = json.loads((DATA / "sweep_summary.json").read_text())["conditions"]
    lams = sorted({c["clutter_lambda"] for c in d})
    sazs = sorted({c["sigma_az_deg"] for c in d})
    fig, axes = plt.subplots(len(sazs), len(lams), figsize=(10, 6.2), sharex=True, sharey=True,
                             facecolor=SURFACE)
    for i, saz in enumerate(sazs):
        for j, lam in enumerate(lams):
            ax = axes[i, j]
            style(ax)
            for m in ("ekf", "nn"):
                rows = sorted([c for c in d if c["method"] == m and c["clutter_lambda"] == lam
                               and c["sigma_az_deg"] == saz], key=lambda c: c["pd"])
                x = np.array([c["pd"] for c in rows])
                y = np.array([c["summary"][metric]["mean"] for c in rows])
                h = np.array([c["summary"][metric]["ci95"] for c in rows])
                ax.fill_between(x, y - h, y + h, color=SERIES[m], alpha=0.18, linewidth=0)
                ax.plot(x, y, color=SERIES[m], linewidth=2, marker=MARKER[m], markersize=5,
                        markeredgecolor=SURFACE, markeredgewidth=1.2, label=LABEL[m])
                if i == 0 and j == len(lams) - 1:
                    ax.annotate("EKF" if m == "ekf" else "NN", (x[-1], y[-1]), xytext=(6, 0),
                                textcoords="offset points", va="center", fontsize=8.5, color=INK2)
            ax.set_title(f"clutter λ = {lam:g}/scan, σθ = {saz:.2f}°", fontsize=9, color=INK)
            if i == len(sazs) - 1:
                ax.set_xlabel("Probability of detection Pd", fontsize=9, color=INK2)
            if j == 0:
                ax.set_ylabel(ylabel, fontsize=9, color=INK2)
            ax.set_xticks([0.7, 0.8, 0.9, 0.97])
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=2, frameon=False, fontsize=9, labelcolor=INK)
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.005, "Mean of 20 Monte Carlo runs per point; band = 95% t-interval of the mean. "
             "Truth: ADS-B, EHAM area, 2026-11-06 12:45-13:15 UTC.", fontsize=7.5, color=INK2)
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / fname, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def nees_figure():
    d = json.loads((DATA / "nees_synthetic.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True, facecolor=SURFACE)
    for ax, key in zip(axes, d):
        style(ax)
        st = d[key]["steps"]
        k = np.array([s["update"] for s in st])
        a = np.array([s["anees4"] for s in st])
        lo = np.array([s["lo4"] for s in st])
        hi = np.array([s["hi4"] for s in st])
        ax.fill_between(k, lo, hi, color="#9ec5f4", alpha=0.6, linewidth=0, label="95% χ² interval")
        ax.axhline(4.0, color=INK2, linewidth=0.8, linestyle=(0, (3, 3)))
        ax.plot(k, a, color=SERIES["ekf"], linewidth=2, marker="o", markersize=3.5, label="ANEES (4-D state)")
        out = ~((a >= lo) & (a <= hi))
        ax.scatter(k[out], a[out], s=40, facecolors="none", edgecolors="#e34948", linewidths=1.4, zorder=5,
                   label="outside interval")
        label = d[key]["label"].replace("lambda", "\u03bb")
        ax.set_title(f"{label}  ({d[key]['frac_steps_inside4']*100:.0f}% of steps inside)",
                     fontsize=9, color=INK)
        ax.set_xlabel("Track update number", fontsize=9, color=INK2)
        ymax = 8.0
        ax.set_ylim(2.5, ymax)
        for kk, aa in zip(k, a):
            if aa > ymax:  # clipped point: mark it at the top edge with its value
                ax.scatter([kk], [ymax - 0.12], s=40, facecolors="none", edgecolors="#e34948", linewidths=1.4,
                           zorder=6, clip_on=False)
                ax.annotate(f"{aa:.1f} (off scale)", (kk, ymax - 0.12), xytext=(8, -3), textcoords="offset points",
                            fontsize=8, color=INK2)
    axes[0].set_ylabel("Average NEES over runs × targets", fontsize=9, color=INK2)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("Filter consistency on synthetic NCV truth (50 runs × 10 targets)", x=0.01, ha="left",
                 fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(FIG / "nees_synthetic.png", dpi=160, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    sweep_figure("gospa_mean_m", "Mean GOSPA [m]  (c = 2 km, p = 2)", "sweep_gospa.png",
                 "GOSPA vs detection probability")
    sweep_figure("rmse_m", "Position RMSE per track [m]", "sweep_rmse.png",
                 "Per-track position RMSE vs detection probability")
    sweep_figure("id_switches", "ID switches per 30 min", "sweep_id_switches.png",
                 "ID switches vs detection probability")
    sweep_figure("false_tracks_per_scan", "False tracks per scan", "sweep_false_tracks.png",
                 "False tracks vs detection probability")
    nees_figure()
    print("figures written to", FIG)


if __name__ == "__main__":
    sys.exit(main())
