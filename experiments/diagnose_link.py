#!/usr/bin/env python3
"""
Link diagnostic: transmit one identical OFDM symbol many times.

If the received copies are nearly identical, the acoustic path is linear and
quiet and any BER problem is in the receiver.  If they scatter, we are limited
by noise or by nonlinear distortion, and the per-subcarrier spread says which.
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ofdm.config import OFDMConfig                       # noqa: E402
from ofdm import modem, receiver, audio_io               # noqa: E402

cfg = OFDMConfig()
N_REP = 40


def main():
    ref = modem.reference_symbol(cfg)[None, :]
    one = modem.grid_to_time(ref, cfg)
    block = np.tile(one, N_REP)

    chirp = modem.sync_chirp(cfg)
    chirp = chirp / np.max(np.abs(chirp)) * cfg.amplitude
    papr_db = 20 * np.log10(np.max(np.abs(block)) / np.sqrt(np.mean(block ** 2)))
    block = block / np.max(np.abs(block)) * cfg.amplitude

    x = np.concatenate([np.zeros(int(0.1 * cfg.fs)), chirp,
                        np.zeros(cfg.sym_len), block,
                        np.zeros(int(0.15 * cfg.fs))])
    print(f"OFDM PAPR = {papr_db:.1f} dB  (chirp PAPR = 3.0 dB)")
    print(f"transmitted RMS: chirp {np.sqrt(np.mean(chirp**2)):.4f}, "
          f"OFDM {np.sqrt(np.mean(block**2)):.4f} "
          f"-> OFDM is {20*np.log10(np.sqrt(np.mean(chirp**2))/np.sqrt(np.mean(block**2))):.1f} dB quieter")

    rx, _ = audio_io.loopback(x, cfg.fs)
    rxf = receiver.bandpass(rx, cfg)
    fr = receiver.find_frame(rxf, cfg, skip_s=audio_io.STARTUP_GUARD_S)
    print(f"\nsync confidence {fr['confidence']:.0f}x, start {fr['data_start']}")

    seg = rxf[fr["data_start"]:fr["data_start"] + N_REP * cfg.sym_len]
    G = modem.time_to_grid(seg, N_REP, cfg)
    G = G[2:-2]                                # drop edges

    mean = G.mean(axis=0)
    dev = G - mean
    snr = 10 * np.log10(np.abs(mean) ** 2 / (np.mean(np.abs(dev) ** 2, axis=0) + 1e-30))
    print(f"\nrepeatability SNR per subcarrier (dB), mean {snr.mean():.1f} dB:")
    for i in range(0, len(snr), 8):
        print("  %5.0f Hz: " % (cfg.data_bins[i] * cfg.df) +
              " ".join(f"{v:5.1f}" for v in snr[i:i + 8]))

    # is the residual noise-like (random) or a stable distortion?
    drift = np.abs(np.mean(dev[: len(dev) // 2], axis=0)) / (np.abs(mean) + 1e-18)
    print(f"\nsystematic drift between first and second half: "
          f"{20*np.log10(np.mean(drift)+1e-18):.1f} dB below signal")

    # measure received level vs full scale
    print(f"recorded OFDM region: rms {np.sqrt(np.mean(seg**2)):.4f}, "
          f"peak {np.max(np.abs(seg)):.3f}, "
          f"clipped samples {int(np.sum(np.abs(rx[fr['data_start']:fr['data_start']+N_REP*cfg.sym_len])>0.98))}")
    np.savez_compressed("results/diagnostic.npz", G=G, snr=snr, rx=rx, mean=mean)
    return 0


if __name__ == "__main__":
    sys.exit(main())
