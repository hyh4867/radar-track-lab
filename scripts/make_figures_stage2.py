"""Stage 2 figures (from results/data/stage2/summary.json and stonesoup_compare.json)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_figures import GRID, INK, INK2, SURFACE, style  # noqa: E402

D = ROOT / "results/data/stage2"
FIG = ROOT / "results/figures"
C = {"ekf": "#2a78d6", "nn": "#eb6834", "imm": "#1baf7a"}  # categorical slots 1-3
NAME = {"ekf": "EKF + GNN", "nn": "NN baseline", "imm": "IMM + GNN"}
CAUSE_GROUPS = [("after ADS-B gap", ("truth_gap",), "#9a9993"), ("another aircraft within 3 km", ("near_other",), "#eda100"),
                ("lost in a turn", ("turn",), "#2a78d6"), ("lost, other", ("misses", "near_radar", "speed_change", "unexplained"), "#e34948")]
EVAL = "EHAM_1106_eval"


def save(fig, name):
    fig.savefig(FIG / name, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def causes(s):
    m = s["scenarios"][EVAL]["methods"]
    fig, ax = plt.subplots(figsize=(8.6, 2.6), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="y", visible=False)
    for row, meth in enumerate(("imm", "ekf")):
        left = 0.0
        for label, keys, col in CAUSE_GROUPS:
            v = sum(m[meth][f"cause_{k}"]["mean"] for k in keys)
            ax.barh(row, v, left=left, color=col, height=0.5, edgecolor=SURFACE, linewidth=2,
                    label=label if row == 0 else None)
            if v >= 1.0:
                ax.text(left + v / 2, row, f"{v:.1f}", ha="center", va="center", fontsize=9,
                        color="white" if col != "#eda100" else INK)
            left += v
        ax.text(left + 0.4, row, f"total {m[meth]['id_switches']['mean']:.1f} ± {m[meth]['id_switches']['ci95']:.1f}",
                va="center", fontsize=9, color=INK)
    ax.set_yticks([0, 1], [NAME["imm"], NAME["ekf"]], fontsize=9.5, color=INK)
    ax.set_xlabel("ID switches per 30-minute run (mean of 20 runs)", fontsize=9, color=INK2)
    ax.set_xlim(0, m["ekf"]["id_switches"]["mean"] * 1.32)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=4, frameon=False, fontsize=8.5)
    ax.set_title("ID switches by cause, Schiphol evaluation window", fontsize=11, color=INK, loc="left")
    save(fig, "s2_id_switch_causes.png")


def straight_turn(s):
    m = s["scenarios"][EVAL]["methods"]
    fig, ax = plt.subplots(figsize=(6.6, 3.6), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="x", visible=False)
    w = 0.25
    for j, meth in enumerate(("nn", "ekf", "imm")):
        for i, key in enumerate(("rmse_straight_m", "rmse_turn_m")):
            v, h = m[meth][key]["mean"], m[meth][key]["ci95"]
            x = i + (j - 1) * (w + 0.02)
            ax.bar(x, v, w, color=C[meth], label=NAME[meth] if i == 0 else None)
            ax.errorbar(x, v, yerr=h, color=INK, linewidth=1, capsize=2)
            ax.text(x, v + h + 8, f"{v:.0f}", ha="center", fontsize=8.5, color=INK)
    share = s["scenarios"][EVAL]["turn_share"]
    ax.set_xticks([0, 1], [f"straight target-scans ({(1 - share) * 100:.0f}%)", f"turning, ≥ 1°/s ({share * 100:.0f}%)"],
                  fontsize=9.5, color=INK)
    ax.set_ylabel("position RMSE at end of scan [m]", fontsize=9, color=INK2)
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    ax.set_title("Position RMSE on straight and turning segments", fontsize=11, color=INK, loc="left")
    save(fig, "s2_rmse_straight_turn.png")


def scenarios(s):
    sc = {k: v for k, v in s["scenarios"].items() if v["valid"] and "imm_vs_ekf" in v and v["spec"]["kind"] != "tune"}
    order = sorted(sc, key=lambda k: (k != EVAL, sc[k]["spec"]["site"], sc[k]["spec"]["day"], k))
    lab = [f"{sc[k]['spec']['site']} {sc[k]['spec']['day'][5:]} {sc[k]['spec']['start_utc'][11:16]}  ({sc[k]['truth_per_scan']:.0f}/scan)"
           for k in order]
    y = np.arange(len(order))[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 0.38 * len(order) + 1.6), sharey=True, facecolor=SURFACE)
    for ax in axes:
        style(ax)
        ax.grid(axis="y", visible=False)
    ax = axes[0]
    for yi, k in zip(y, order):
        m = sc[k]["methods"]
        a, b = m["ekf"]["id_switches"]["mean"], m["imm"]["id_switches"]["mean"]
        ax.plot([a, b], [yi, yi], color=GRID, linewidth=3, zorder=1)
        for meth, v in (("ekf", a), ("imm", b)):
            ax.errorbar(v, yi, xerr=m[meth]["id_switches"]["ci95"], color=C[meth], linewidth=1.2, capsize=2, zorder=2)
            ax.scatter(v, yi, s=42, color=C[meth], edgecolor=SURFACE, linewidth=1.2, zorder=3,
                       label=NAME[meth] if k == order[0] else None)
    ax.set_xscale("log")
    ax.set_xlabel("ID switches per 30 min (log scale)", fontsize=9, color=INK2)
    ax.set_yticks(y, lab, fontsize=8.5, color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax = axes[1]
    for yi, k in zip(y, order):
        m = sc[k]["methods"]
        for meth in ("nn", "ekf", "imm"):
            ax.scatter(m[meth]["rmse_m"]["mean"], yi, s=42, color=C[meth], edgecolor=SURFACE, linewidth=1.2, zorder=3,
                       label=NAME[meth] if k == order[0] else None)
    ax.set_xlabel("position RMSE per track [m]", fontsize=9, color=INK2)
    ax.set_xlim(0, None)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    fig.suptitle("Frozen parameters on other airports, times and a second day (first row: stage 1 window)",
                 fontsize=11, color=INK, x=0.02, ha="left")
    fig.tight_layout()
    save(fig, "s2_scenarios.png")


def stonesoup():
    p = D / "stonesoup_compare.json"
    if not p.exists():
        return
    d = json.loads(p.read_text())
    cases = [f["case"] for f in d["filter"] if f["frame"] == "origin"]
    fig, ax = plt.subplots(figsize=(8.2, 3.3), facecolor=SURFACE)
    style(ax)
    ax.grid(axis="x", visible=False)
    w = 0.34
    for j, (frame, col, lab) in enumerate((("origin", "#eb6834", "radar at (0, 0): coordinates of both signs"),
                                           ("offset", "#2a78d6", "radar at (+200 km, +200 km): all coordinates positive"))):
        for i, c in enumerate(cases):
            f = next(f for f in d["filter"] if f["case"] == c and f["frame"] == frame)
            v = f["max_pos_diff_m"]
            ax.bar(i + (j - 0.5) * (w + 0.03), v, w, color=col, label=lab if i == 0 else None)
            ax.text(i + (j - 0.5) * (w + 0.03), v * 1.25, f"{v:.2g} m", ha="center", fontsize=8.5, color=INK)
    ax.axhline(0.01, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(len(cases) - 0.45, 0.013, "preregistered agreement limit: 1 cm", fontsize=8.5, color=INK2, ha="right")
    ax.set_yscale("log")
    ax.set_ylim(1e-6, 30)
    ax.set_xticks(range(len(cases)), [c.replace(", most scans in the window", "") for c in cases], fontsize=9, color=INK)
    ax.set_ylabel("largest position difference [m]", fontsize=9, color=INK2)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, 1.22), ncol=1)
    ax.set_title("This project's EKF vs Stone Soup 1.9.1, same detections", fontsize=11, color=INK, loc="left", pad=34)
    save(fig, "s2_stonesoup_filter.png")


def main() -> None:
    s = json.loads((D / "summary.json").read_text())
    causes(s)
    straight_turn(s)
    scenarios(s)
    stonesoup()


if __name__ == "__main__":
    main()
