#!/usr/bin/env python3
"""
Figures for the final report, drawn from the results files - never from
hand-typed numbers.

    python3 experiments/make_report_figures.py
    -> reports/figures/fig4_fec.png, fig5_drift.png, fig6_clock_estimate.png

Needs matplotlib (report figures only; the modem itself does not).
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reports", "figures")
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID = "#1f1f1e", "#5f5e58", "#e4e3dd"
FLOOR = 1e-5

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 2, "savefig.dpi": 200, "savefig.bbox": "tight",
})


def load(name):
    with open(os.path.join(ROOT, "results", name)) as f:
        return json.load(f)


def label_end(ax, x, y, text, color, dy=0):
    ax.annotate(text, (x, y), xytext=(6, dy), textcoords="offset points",
                color=INK, fontsize=9, va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=color, lw=1))


def fig_fec():
    f = load("fec_results.json")
    snr = f["snr_db"]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for key, name, col, mk in (("uncoded", "uncoded", BLUE, "o"),
                               ("rep3", "repetition-3", ORANGE, "s"),
                               ("conv", "convolutional ½", AQUA, "^")):
        ber = f[key]["ber"]
        y = [max(v, FLOOR) for v in ber]
        ax.semilogy(snr, y, color=col, marker=mk, ms=6, label=
                    f"{name} ({round(f[key]['goodput_bps']):,} bit/s)")
        zero = [(s, FLOOR) for s, v in zip(snr, ber) if v == 0]
        if zero:
            ax.plot(*zip(*zero), ls="none", marker=mk, ms=7, mfc="white", mec=col, mew=1.6)
    ax.axhline(FLOOR, color=INK2, lw=0.8, ls=":")
    ax.text(snr[-1], FLOOR * 1.4, "zero errors", ha="right", fontsize=8, color=INK2)
    ax.set_ylim(FLOOR * 0.7, 1)
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("decoded bit error rate")
    ax.set_title("Decoded BER by FEC scheme (simulated room, 80 ppm clock)",
                 fontsize=10.5, loc="left", color=INK)
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    fig.savefig(os.path.join(OUT, "fig4_fec.png"))
    plt.close(fig)


def fig_drift():
    d = load("drift_results.json")["rows"]
    big = max(r["bytes"] for r in d)
    rows = [r for r in d if r["bytes"] == big]
    ppm = [r["ppm"] for r in rows]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(ppm, [100 * r["exact_uncorrected"] for r in rows], color=ORANGE,
            marker="s", ms=6)
    ax.plot(ppm, [100 * r["exact_corrected"] for r in rows], color=AQUA,
            marker="^", ms=6)
    label_end(ax, ppm[-1], 100 * rows[-1]["exact_corrected"], "with clock correction", AQUA)
    label_end(ax, ppm[-1], 100 * rows[-1]["exact_uncorrected"], "uncorrected", ORANGE)
    ax.set_ylim(-5, 108)
    ax.set_xlim(min(ppm) - 30, max(ppm) + 260)
    ax.set_xticks(ppm)
    ax.set_xlabel("sampling-clock offset (ppm)")
    ax.set_ylabel("frames recovered exactly (%)")
    ax.set_title(f"{rows[0]['frame_s']} s frames ({big} bytes) under clock offset",
                 fontsize=10.5, loc="left", color=INK)
    fig.savefig(os.path.join(OUT, "fig5_drift.png"))
    plt.close(fig)


def fig_clock():
    d = load("drift_results.json")["rows"]
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    for size, col, mk in ((256, BLUE, "o"), (768, ORANGE, "s"), (1536, AQUA, "^")):
        rs = [r for r in d if r["bytes"] == size and r["est_ppm"] is not None]
        if rs:
            ax.plot([r["ppm"] for r in rs], [r["est_ppm"] for r in rs], ls="none",
                    marker=mk, ms=7, color=col, label=f"{rs[0]['frame_s']} s frames")
    lim = [-450, 450]
    ax.plot(lim, lim, color=INK2, lw=1, ls="--", label="perfect estimate")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_aspect("equal")
    ax.set_xlabel("true clock offset (ppm)")
    ax.set_ylabel("estimated clock offset (ppm)")
    ax.set_title("Clock-offset estimate from pilots", fontsize=10.5, loc="left", color=INK)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.savefig(os.path.join(OUT, "fig6_clock_estimate.png"))
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    fig_fec()
    fig_drift()
    fig_clock()
    print("wrote fig4_fec.png, fig5_drift.png, fig6_clock_estimate.png to reports/figures/")
