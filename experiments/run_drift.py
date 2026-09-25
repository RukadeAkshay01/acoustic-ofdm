#!/usr/bin/env python3
"""
Long-frame clock drift: how long can one frame be before a sample-clock offset
between two devices breaks it?

With an offset of eps, the FFT window slides eps * L samples per OFDM symbol.
The adaptive equaliser tracks the resulting phase slope, but the window can
only slide so far before it leaves the cyclic prefix (64 samples, less the
8-sample back-off the synchroniser applies) and inter-symbol interference
sets in.  Every earlier test used frames under 2 s, so this limit was never
reached.  Here we sweep frame length x clock offset through the simulated
channel with the blind live receiver the two-device test uses, with and
without the receiver's sample-clock correction pass (ofdm/live.py).

    python3 experiments/run_drift.py        # ~1-2 min
    -> results/drift_results.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ofdm.config import DEFAULT                  # noqa: E402
from ofdm import live, channel, sync             # noqa: E402

PPMS = [-400, -200, -100, 0, 100, 200, 400]
SIZES = [64, 256, 768, 1536]                     # payload bytes
SNR = 18.0
TRIALS = 3


def main():
    cfg = DEFAULT
    rows = []
    print(f"SNR {SNR} dB, multipath, repetition-3 live frames, adaptive equaliser\n")
    print(f"{'bytes':>6s} {'frame s':>8s} {'ppm':>5s} {'drift smp':>9s} "
          f"{'est ppm':>8s} {'PRR raw':>8s} {'PRR corr':>9s} {'exact raw':>10s} "
          f"{'exact corr':>11s}")
    for size in SIZES:
        data = bytes(np.random.default_rng(size).integers(32, 127, size, dtype=np.uint8))
        x, bits, fmeta, mmeta = live.build_frame(data, "drift.bin", 3, cfg)
        dur = len(x) / cfg.fs
        n_sym = mmeta["n_sym"] + 1
        for ppm in PPMS:
            res = {False: ([], 0), True: ([], 0)}
            est = []
            for t in range(TRIALS):
                rx, info = channel.apply_channel(
                    x, SNR, cfg, clock_ppm=ppm, delay=4000,
                    rng=np.random.default_rng([t, size, ppm + 1000]))
                for corr in (False, True):
                    r = live.demodulate_blind(rx, cfg, noise_var=info["noise_var"],
                                              max_seconds=30, clock_correct=corr)
                    prr, ex = res[corr]
                    prr.append(r.get("prr", 0.0) if r.get("ok") else 0.0)
                    res[corr] = (prr, ex + bool(r.get("ok") and r["data"] == data))
                    if corr and np.isfinite(r.get("clock_ppm", np.nan)):
                        est.append(r["clock_ppm"])
            drift = ppm * 1e-6 * n_sym * cfg.sym_len
            row = dict(bytes=size, frame_s=round(dur, 2), n_sym=n_sym, ppm=ppm,
                       drift_samples=round(drift, 1),
                       est_ppm=float(np.mean(est)) if est else None,
                       prr_uncorrected=float(np.mean(res[False][0])),
                       prr_corrected=float(np.mean(res[True][0])),
                       exact_uncorrected=res[False][1] / TRIALS,
                       exact_corrected=res[True][1] / TRIALS)
            rows.append(row)
            print(f"{size:6d} {dur:8.2f} {ppm:5d} {drift:9.1f} "
                  f"{row['est_ppm'] if row['est_ppm'] is not None else float('nan'):8.1f} "
                  f"{row['prr_uncorrected']*100:7.0f}% {row['prr_corrected']*100:8.0f}% "
                  f"{row['exact_uncorrected']*100:9.0f}% {row['exact_corrected']*100:10.0f}%")
        print()

    out = dict(snr_db=SNR, trials=TRIALS, cp=cfg.ncp, rows=rows)
    os.makedirs("results", exist_ok=True)
    with open("results/drift_results.json", "w") as f:
        json.dump(out, f, indent=1)
    print("saved results/drift_results.json")


if __name__ == "__main__":
    main()
