#!/usr/bin/env python3
"""
Peak-to-average power reduction trade-off.

A speaker is peak-limited, so what matters is how much *average* power we can
push through it for a fixed peak.  An unclipped OFDM block wastes ~11 dB of
that budget.  Clipping and re-filtering buys it back, at the cost of in-band
distortion.  This sweep finds where the trade stops paying.
"""
import dataclasses
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ofdm.config import OFDMConfig                  # noqa: E402
from ofdm import modem, channel, receiver           # noqa: E402

BASE = OFDMConfig()
SNRS = [8, 14, 20, 26]


def main():
    bits = np.random.default_rng(1).integers(0, 2, 6200).astype(np.int8)
    out = {"clip_db": [], "papr_db": [], "power_gain_db": [], "snr_db": SNRS, "ber": []}
    ref = None
    for clip in (0.0, 8.0, 6.0, 5.0, 4.0, 3.0):
        cfg = dataclasses.replace(BASE, papr_clip_db=clip)
        x, m = modem.modulate(bits, cfg)
        rms = np.sqrt(np.mean(x[m["data_start"]:] ** 2))
        ref = ref if ref is not None else rms
        row = []
        for snr in SNRS:
            errs = tot = 0
            for t in range(6):
                rx, info = channel.apply_channel(
                    x, snr_db=snr, cfg=cfg, multipath=False, delay=2000,
                    rng=np.random.default_rng(100 * t + snr))
                r = receiver.demodulate(rx, len(bits), m["n_sym"], cfg,
                                        mode="static", noise_var=info["noise_var"])
                _, e, n = receiver.ber(bits, r["bits"])
                errs += e
                tot += n
            row.append(errs / tot)
        out["clip_db"].append(clip)
        out["papr_db"].append(round(m["papr_after_db"], 2))
        out["power_gain_db"].append(round(float(20 * np.log10(rms / ref)), 2))
        out["ber"].append(row)
        print(f"  clip {('off' if clip==0 else f'{clip:.0f} dB'):>6}  "
              f"PAPR {m['papr_after_db']:5.1f} dB  power {20*np.log10(rms/ref):+5.1f} dB  "
              + "  ".join(f"{v:.1e}" for v in row))

    os.makedirs("results", exist_ok=True)
    with open("results/papr_tradeoff.json", "w") as f:
        json.dump(out, f, indent=1)
    print("wrote results/papr_tradeoff.json")


if __name__ == "__main__":
    main()
