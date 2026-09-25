#!/usr/bin/env python3
"""
FEC comparison: uncoded vs repetition-3 vs rate-1/2 convolutional (K=7).

Every scheme carries the same 293-byte file through the same simulated room
(multipath, transducer roll-off, 80 ppm clock offset) with the adaptive
equaliser, and we record coded BER and packet recovery rate against SNR.
The channel realisation is fixed per trial and shared between schemes, so the
comparison is paired - differences come from the code, not the room.

    python3 experiments/run_fec.py            # ~1-2 min
    -> results/fec_results.json
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ofdm.config import OFDMConfig                          # noqa: E402
from ofdm import modem, receiver, framing, channel, conv    # noqa: E402

CFG = OFDMConfig()
SNRS = [-6, -4, -2, 0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
TRIALS = 8
PAYLOAD = bytes(np.random.default_rng(42).integers(32, 127, 293, dtype=np.uint8))


def encode(scheme):
    if scheme == "uncoded":
        return framing.encode_file(PAYLOAD, "fec.bin")
    if scheme == "rep3":
        return framing.encode_file_fec(PAYLOAD, "fec.bin", 3)
    return framing.encode_file_conv(PAYLOAD, "fec.bin")


def decode(scheme, r, fmeta):
    if scheme == "uncoded":
        return framing.decode_file(r["bits"], fmeta), r["bits"]
    if scheme == "rep3":
        info = framing.fec_decode(r["bits"], fmeta["n_info_bits"], 3)
        return framing.decode_file(info, fmeta), info
    info = conv.fec_decode_soft(conv.symbols_to_soft(r["symbols"]),
                                fmeta["n_info_bits"])
    return framing.decode_file(info, fmeta), info


def main():
    info_bits, _ = framing.encode_file(PAYLOAD, "fec.bin")
    schemes = ["uncoded", "rep3", "conv"]
    out = {"snr_db": SNRS, "trials": TRIALS, "payload_bytes": len(PAYLOAD)}
    for scheme in schemes:
        bits, fmeta = encode(scheme)
        x, meta = modem.modulate(bits, CFG)
        rate_eff = len(PAYLOAD) * 8 / (len(x) / CFG.fs)
        bers, prrs, exact = [], [], []
        for snr in SNRS:
            errs = n = 0
            prr_acc, ex = [], 0
            for t in range(TRIALS):
                rng = np.random.default_rng(1000 + t)       # same room per trial
                rx, info = channel.apply_channel(x, snr_db=snr, cfg=CFG,
                                                 delay=3000, clock_ppm=80,
                                                 rng=rng)
                r = receiver.demodulate(rx, len(bits), meta["n_sym"], CFG,
                                        mode="adaptive",
                                        noise_var=info["noise_var"])
                if not r["ok"]:
                    errs += len(info_bits); n += len(info_bits)
                    prr_acc.append(0.0)
                    continue
                (data, prr, _, _), info_rx = decode(scheme, r, fmeta)
                _, e, m = receiver.ber(info_bits, info_rx)
                errs += e; n += m
                prr_acc.append(prr)
                ex += data == PAYLOAD
            bers.append(errs / max(n, 1))
            prrs.append(float(np.mean(prr_acc)))
            exact.append(ex / TRIALS)
            print(f"{scheme:8s} SNR {snr:2d} dB  BER {bers[-1]:.2e}  "
                  f"PRR {prrs[-1]*100:5.1f}%  exact {exact[-1]*100:3.0f}%")
        out[scheme] = dict(ber=bers, prr=prrs, exact=exact,
                           airtime_s=len(x) / CFG.fs, goodput_bps=rate_eff)
        print(f"{scheme:8s} air time {len(x)/CFG.fs:.2f} s -> "
              f"{rate_eff:.0f} bit/s of file data\n")

    os.makedirs("results", exist_ok=True)
    with open("results/fec_results.json", "w") as f:
        json.dump(out, f, indent=1)
    print("saved results/fec_results.json")


if __name__ == "__main__":
    main()
