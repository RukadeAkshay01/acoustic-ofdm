#!/usr/bin/env python3
"""
BER experiments for the mid-term evaluation.

  Experiment A (Phase 1): BER vs SNR over an AWGN-only channel, against the
                          QPSK theory curve.  Validates the modem itself.
  Experiment B (Phase 2): BER vs SNR over the multipath acoustic channel for
                          no / static / adaptive equalisation.
  Experiment C (Phase 3): BER vs sampling-clock offset - the cross-device case
                          where a static calibration cannot survive.
  Experiment D (Phase 3): equaliser step size mu - the tracking/noise tradeoff.

Writes results/ber_results.json.
"""
import json
import os
import sys

import numpy as np
from scipy.special import erfc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ofdm.config import OFDMConfig                      # noqa: E402
from ofdm import modem, channel, receiver               # noqa: E402

CFG = OFDMConfig()
N_BITS = 6200
TRIALS = 16


def theory_qpsk(snr_db):
    """Coherent QPSK BER on AWGN: Q(sqrt(2 Eb/N0))."""
    ebn0 = 10 ** (np.asarray(snr_db, float) / 10.0)
    return 0.5 * erfc(np.sqrt(ebn0))


def make_channel(trial, multipath):
    """
    Impulse response for one trial, drawn from a seed that depends only on the
    trial index.  Every SNR point in a sweep therefore sees the *same* set of
    rooms, so differences between points are due to noise alone.
    """
    rng = np.random.default_rng(90000 + trial)
    h = np.array([1.0])
    if multipath:
        h = np.convolve(h, channel.room_impulse_response(CFG, rng=rng))
    h = np.convolve(h, channel.transducer_response(CFG))
    return h


def run_point(snr_db, mode, clock_ppm=0.0, multipath=True, mu=0.15, trials=TRIALS):
    errs = tot = 0
    evms, cest = [], []
    for t in range(trials):
        rng = np.random.default_rng(1000 * t + int(snr_db * 7) + 3)
        bits = rng.integers(0, 2, N_BITS).astype(np.int8)
        x, meta = modem.modulate(bits, CFG)
        rx, info = channel.apply_channel(
            x, snr_db=snr_db, cfg=CFG, multipath=multipath,
            clock_ppm=clock_ppm, delay=int(rng.integers(500, 8000)), rng=rng,
            h=make_channel(t, multipath))
        r = receiver.demodulate(rx, len(bits), meta["n_sym"], CFG, mode=mode,
                                noise_var=info["noise_var"], mu=mu)
        if not r["ok"]:
            errs += N_BITS
            tot += N_BITS
            continue
        _, e, n = receiver.ber(bits, r["bits"])
        errs += e
        tot += n
        evms.append(r["evm_db"])
        if mode != "none":
            H_true = channel.true_channel_freq_response(info["h"], CFG)
            cest.append(r["estimator"].estimation_error_db(H_true))
    return dict(ber=errs / max(tot, 1), errors=errs, bits=tot,
                evm_db=float(np.mean(evms)) if evms else None,
                chan_err_db=float(np.mean(cest)) if cest else None)


def main():
    out = {"config": {k: getattr(CFG, k) for k in
                      ("fs", "nfft", "ncp", "f_low", "f_high", "pilot_spacing")},
           "derived": {"n_data_sc": len(CFG.payload_bins),
                       "n_pilot_sc": len(CFG.pilot_bins),
                       "bitrate": CFG.raw_bitrate,
                       "symbol_ms": CFG.sym_dur * 1e3}}

    snrs = list(range(0, 31, 2))

    print("Experiment A: AWGN only (Phase 1 modem validation)")
    a = {"snr_db": snrs, "ber": [], "theory": list(theory_qpsk(snrs))}
    for s in snrs:
        p = run_point(s, "static", multipath=False)
        a["ber"].append(p["ber"])
        print(f"  SNR {s:2d} dB  BER {p['ber']:.3e}  (theory {theory_qpsk(s):.3e})")
    out["awgn"] = a

    print("\nExperiment B: multipath acoustic channel, equaliser comparison")
    b = {"snr_db": snrs}
    for mode in ("none", "static", "adaptive"):
        b[mode] = {"ber": [], "evm_db": [], "chan_err_db": []}
        for s in snrs:
            p = run_point(s, mode)
            b[mode]["ber"].append(p["ber"])
            b[mode]["evm_db"].append(p["evm_db"])
            b[mode]["chan_err_db"].append(p["chan_err_db"])
        print(f"  {mode:9s} " + " ".join(f"{v:.1e}" for v in b[mode]["ber"]))
    out["multipath"] = b

    print("\nExperiment C: sampling-clock offset (cross-device)")
    ppms = [0, 25, 50, 100, 200, 400, 800]
    c = {"ppm": ppms}
    for mode in ("static", "adaptive"):
        c[mode] = []
        for ppm in ppms:
            c[mode].append(run_point(20, mode, clock_ppm=ppm)["ber"])
        print(f"  {mode:9s} " + " ".join(f"{v:.1e}" for v in c[mode]))
    out["clock"] = c

    print("\nExperiment D: adaptive step size mu")
    mus = [0.0, 0.01, 0.02, 0.05, 0.08, 0.15, 0.3, 0.5]
    d = {"mu": mus, "static_channel": [], "clock_200ppm": []}
    for mu in mus:
        d["static_channel"].append(run_point(14, "adaptive", mu=mu)["ber"])
        d["clock_200ppm"].append(run_point(14, "adaptive", clock_ppm=200, mu=mu)["ber"])
    print("  static ch :", " ".join(f"{v:.1e}" for v in d["static_channel"]))
    print("  200 ppm   :", " ".join(f"{v:.1e}" for v in d["clock_200ppm"]))
    out["mu_sweep"] = d

    os.makedirs("results", exist_ok=True)
    with open("results/ber_results.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\nwrote results/ber_results.json")


if __name__ == "__main__":
    main()
