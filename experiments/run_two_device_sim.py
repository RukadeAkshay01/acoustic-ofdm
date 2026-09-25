#!/usr/bin/env python3
"""
Simulated two-device sweep: the blind receiver used for the two-device test,
run through the channel model with independent transmitter and receiver
clocks, for both payload codes.

    python3 experiments/run_two_device_sim.py      # ~20 s
    -> results/two_device_sim.json

This is a rehearsal of the hardware test, not a substitute for it: the room,
transducers and clock offset are all modelled.
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ofdm.config import DEFAULT                      # noqa: E402
from ofdm import live, channel                       # noqa: E402

TEXT = (b"TWO-DEVICE TEST -- adaptive OFDM acoustic link. Separate speaker, "
        b"separate microphone, separate sample clocks. If you can read this "
        b"line the clock-offset tracking works on real hardware. 0123456789")
SNRS = [15, 10, 6, 3, 0]
PPMS = [-150, -50, 50, 150]


def main():
    rows = []
    print(f"{'code':>6s} {'SNR':>4s} {'frames':>6s} {'decoded':>7s} {'exact':>5s} "
          f"{'mean |ppm err|':>14s} {'frame s':>7s}")
    for code in (3, "conv"):
        x, bits, _, _ = live.build_frame(TEXT, "message.txt", code, DEFAULT)
        for snr in SNRS:
            dec = exact = 0
            errs = []
            for ppm in PPMS:
                rng = np.random.default_rng([int(abs(ppm)), 11 if ppm >= 0 else 12, snr])
                gap = np.zeros(DEFAULT.fs)
                rx, info = channel.apply_channel(np.concatenate([gap, x, gap]), snr,
                                                 DEFAULT, clock_ppm=ppm, rng=rng)
                r = live.demodulate_blind(rx, DEFAULT, noise_var=info["noise_var"])
                dec += bool(r.get("ok"))
                exact += bool(r.get("ok") and r["data"] == TEXT)
                if np.isfinite(r.get("clock_ppm", np.nan)):
                    errs.append(abs(r["clock_ppm"] - ppm))
            row = dict(code="conv" if code == "conv" else f"rep{code}", snr_db=snr,
                       frames=len(PPMS), decoded=dec, exact=exact,
                       mean_ppm_err=float(np.mean(errs)) if errs else None,
                       frame_s=round(len(x) / DEFAULT.fs, 2))
            rows.append(row)
            print(f"{row['code']:>6s} {snr:4d} {len(PPMS):6d} {dec:7d} {exact:5d} "
                  f"{row['mean_ppm_err'] or float('nan'):14.1f} {row['frame_s']:7.2f}")
    out = dict(text_bytes=len(TEXT), ppm=PPMS, rows=rows)
    with open(os.path.join(ROOT, "results", "two_device_sim.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("saved results/two_device_sim.json")


if __name__ == "__main__":
    main()
