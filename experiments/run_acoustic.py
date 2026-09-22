#!/usr/bin/env python3
"""
Real over-the-air test: transmit a file through the laptop speaker and
recover it from the laptop microphone.

Usage:  python3 experiments/run_acoustic.py [--mode adaptive] [--sim]
        --sim replaces the real speaker/mic with the channel model, so the
        script can be demonstrated on a machine with no audio access.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ofdm.config import OFDMConfig                        # noqa: E402
from ofdm import modem, receiver, framing, channel, audio_io, calibrate  # noqa: E402

CFG = OFDMConfig()
MESSAGE = (b"ADAPTIVE OFDM ACOUSTIC LINK -- Signal Processing mini project. "
           b"This text travelled from the speaker to the microphone as sound "
           b"in the 4-12 kHz band, carried on 31 QPSK subcarriers with 12 "
           b"pilots, and was recovered by FFT demodulation with pilot-based "
           b"channel estimation and MMSE equalisation. ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="adaptive",
                    choices=["none", "static", "adaptive"])
    ap.add_argument("--sim", action="store_true", help="simulate instead of using audio hardware")
    ap.add_argument("--snr", type=float, default=18.0, help="simulated SNR (dB)")
    ap.add_argument("--out", default=None,
                    help="output .npz (default: acoustic_run.npz for real "
                         "captures, acoustic_sim.npz for --sim)")
    ap.add_argument("--backoff", type=float, default=15.0,
                    help="keep subcarriers within this many dB of the best one")
    ap.add_argument("--fec", type=int, default=0, metavar="N",
                    help="repetition-N forward error correction (0 = off)")
    ap.add_argument("--no-calib", action="store_true",
                    help="skip Stage-1 subcarrier calibration")
    args = ap.parse_args()
    if args.out is None:
        # Never let a simulated run land on the real capture's filename - the
        # dashboard reads that file and would present the model as hardware.
        args.out = ("results/acoustic_sim.npz" if args.sim
                    else "results/acoustic_run.npz")

    cfg = CFG
    calib_report = None
    if not args.no_calib and not args.sim:
        print("Stage 1a: calibrating capture gain...")
        probe_bits = np.random.default_rng(0).integers(0, 2, 2000).astype(np.int8)
        probe_wave, _ = modem.modulate(probe_bits, CFG)
        vol, pk, glog = audio_io.find_capture_gain(probe_wave, CFG.fs,
                                                   target_peak=0.45)
        for v, p in glog:
            print(f"    capture {v:3d}% -> recorded peak {p:.3f}"
                  + ("  CLIPPED" if p > 0.95 else ""))
        print(f"  chosen capture gain     : {vol}% (peak {pk:.3f})")
        if pk < 0.05:
            print("  WARNING: recorded level very low; check that the speaker "
                  "is not muted and the microphone is not blocked")

        print("Stage 1b: probing the acoustic channel with a chirp...")
        probe = modem.sync_chirp(CFG) * CFG.amplitude
        rx_probe, _ = audio_io.loopback(probe, CFG.fs)
        cfg, calib_report = calibrate.calibrated_config(
            rx_probe, CFG, backoff_db=args.backoff,
            skip_s=audio_io.STARTUP_GUARD_S)
        print(f"  measured response range : {calib_report['dynamic_range_db']:.1f} dB")
        print(f"  usable subcarriers      : {len(calib_report['kept'])}/"
              f"{len(calib_report['bins'])} "
              f"({calib_report['kept_frac']*100:.0f}%)\n")

    if args.fec:
        bits, fmeta = framing.encode_file_fec(MESSAGE, "message.txt", args.fec)
    else:
        bits, fmeta = framing.encode_file(MESSAGE, "message.txt")
    x, meta = modem.modulate(bits, cfg)
    dur = len(x) / cfg.fs
    print(cfg.summary())
    print(f"\npayload      : {len(MESSAGE)} bytes -> {len(bits)} bits "
          f"({fmeta['n_packets']} packets)")
    print(f"waveform     : {len(x)} samples, {dur:.2f} s, "
          f"{meta['n_sym']} payload OFDM symbols")

    if args.sim:
        rx, info = channel.apply_channel(x, snr_db=args.snr, cfg=cfg,
                                         delay=4000, clock_ppm=80,
                                         rng=np.random.default_rng(5))
        print(f"channel      : SIMULATED (SNR {args.snr} dB, multipath, 80 ppm clock)")
    else:
        print("channel      : REAL speaker -> microphone (playing now, please stay quiet)")
        rx, fs = audio_io.loopback(x, cfg.fs)
        info = {"noise_var": 1e-3}
        print(f"               captured {len(rx)} samples at {fs} Hz")

    skip_s = 0.0 if args.sim else audio_io.STARTUP_GUARD_S
    r = receiver.demodulate(rx, len(bits), meta["n_sym"], cfg, mode=args.mode,
                            noise_var=info.get("noise_var", 1e-3), skip_s=skip_s,
                            tail_guard_s=0.0 if args.sim else 0.15)
    if not r["ok"]:
        print("FAILED: " + r["reason"])
        return 1

    b, errs, n = receiver.ber(bits, r["bits"])
    if args.fec:
        info_tx = bits[: fmeta["n_info_bits"]]
        info_rx = framing.fec_decode(r["bits"], fmeta["n_info_bits"], args.fec)
        b_post, errs_post, n_post = receiver.ber(info_tx, info_rx)
    if args.fec:
        data, prr, hdr, good = framing.decode_file_fec(r["bits"], fmeta)
    else:
        data, prr, hdr, good = framing.decode_file(r["bits"], fmeta)

    print(f"\nsync         : frame at sample {r['start']} "
          f"(confidence {r['sync']['confidence']:.0f}x noise floor)")
    print(f"equaliser    : {args.mode}")
    print(f"EVM          : {r['evm_db']:.1f} dB")
    print(f"BER (raw)    : {b:.3e}  ({errs}/{n} bits)")
    if args.fec:
        print(f"BER (coded)  : {b_post:.3e}  ({errs_post}/{n_post} bits)")
    print(f"packets      : {sum(good)}/{len(good)} passed CRC  (PRR {prr*100:.1f}%)")
    print(f"header       : {hdr}")
    print(f"throughput   : {len(MESSAGE)*8/dur:.0f} bit/s over the air")
    ok = data == MESSAGE
    print(f"file match   : {'EXACT' if ok else 'partial'}  "
          f"({len(data)}/{len(MESSAGE)} bytes)")
    if data:
        print(f"\nrecovered text:\n  {data[:160].decode(errors='replace')}...")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    np.savez_compressed(
        args.out, tx=x, rx=rx, ber=b, prr=prr, mode=args.mode,
        evm=r["evm_db"], symbols=r["symbols"], H=r["H"],
        H_history=r["H_history"], grid_raw=r["grid_raw"], grid_eq=r["grid_eq"],
        env=r["sync"]["env"], start=r["start"], cpe=r["cpe"],
        n_sym=meta["n_sym"], real=not args.sim, ok=ok, n_bits=len(bits),
        active_bins=np.array(cfg.active_bins, dtype=int),
        data_bins=cfg.data_bins, pilot_bins=cfg.pilot_bins,
        calib_db=(calib_report["bin_db"] if calib_report else np.array([])),
        calib_bins=(calib_report["bins"] if calib_report else np.array([])),
        calib_kept=(calib_report["kept"] if calib_report else np.array([])),
        calib_ir=(calib_report["ir"] if calib_report else np.array([])))
    print(f"\nsaved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
