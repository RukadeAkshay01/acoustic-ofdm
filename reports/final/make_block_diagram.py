#!/usr/bin/env python3
"""System block diagram for the final report -> figures/fig0_block_diagram.png"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
INK, BLUE, ORANGE, AQUA = "#1f1f1e", "#2a78d6", "#eb6834", "#1baf7a"

tx = ["File bytes", "CRC packets\n+ header", "FEC encode\n(conv. / rep.)", "QPSK map\n+ pilots",
      "Hermitian\nIFFT + CP", "PAPR clip\n+ filter", "Chirp\npreamble"]
rx = ["Band-pass\nfilter", "Chirp matched\nfilter (sync)", "FFT", "LS estimate\n+ pilot tracking",
      "Clock offset\n+ resample", "MMSE\nequaliser", "Soft Viterbi\n/ MRC decode", "CRC check\n→ file"]

fig, ax = plt.subplots(figsize=(12, 4.2))
ax.set_xlim(0, 12); ax.set_ylim(0, 4.2); ax.axis("off")

def row(labels, y, col, x0=0.15, w=1.35, gap=0.12):
    xs = []
    for i, t in enumerate(labels):
        x = x0 + i * (w + gap)
        ax.add_patch(FancyBboxPatch((x, y), w, 0.9, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    fc="white", ec=col, lw=1.8))
        ax.text(x + w / 2, y + 0.45, t, ha="center", va="center", fontsize=8.6, color=INK)
        if i:
            ax.annotate("", (x, y + 0.45), (x - gap, y + 0.45),
                        arrowprops=dict(arrowstyle="-|>", color=INK, lw=1))
        xs.append(x)
    return xs, w

txs, w = row(tx, 3.0, BLUE, x0=0.15 + 0.5 * (1.35 + 0.12))
rxs, _ = row(rx, 0.35, AQUA)
ax.text(0.15, 3.45, "TX", fontsize=11, fontweight="bold", color=BLUE, va="center")
ax.text(rxs[0] + 0.02, 1.45, "RX", fontsize=11, fontweight="bold", color=AQUA)
# acoustic channel
cx = txs[-1] + w / 2
ax.add_patch(FancyBboxPatch((cx - 1.5, 1.72), 3.0, 0.8, boxstyle="round,pad=0.02,rounding_size=0.08",
                            fc="#fdf0ea", ec=ORANGE, lw=1.8))
ax.text(cx, 2.12, "speaker → room → microphone\n(multipath, nulls, noise, clock offset)",
        ha="center", va="center", fontsize=8.6, color=INK)
ax.annotate("", (cx, 2.52), (cx, 3.0), arrowprops=dict(arrowstyle="-|>", color=INK, lw=1))
ax.annotate("", (rxs[0] + w / 2, 1.25), (cx - 1.5, 2.12),
            arrowprops=dict(arrowstyle="-|>", color=INK, lw=1, connectionstyle="angle,angleA=180,angleB=90"))
ax.text(rxs[3] + w / 2, 1.42, "Stage-1 calibration: chirp response → usable subcarriers",
        ha="center", fontsize=8, color=INK, style="italic")
fig.savefig(os.path.join(HERE, "figures", "fig0_block_diagram.png"), dpi=200, bbox_inches="tight")
