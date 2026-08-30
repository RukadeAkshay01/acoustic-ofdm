#!/usr/bin/env python3
"""
Collect simulation results + the real over-the-air capture into one JSON
bundle for the web dashboard.  Arrays are decimated so the page stays small.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ofdm.config import OFDMConfig                       # noqa: E402
from ofdm import modem, channel, receiver, echo          # noqa: E402


def dec(x, n=600):
    x = np.asarray(x, dtype=float).ravel()
    if x.size <= n:
        return [round(float(v), 6) for v in x]
    step = int(np.ceil(x.size / n))
    return [round(float(v), 6) for v in x[::step]]


def main():
    out = {}
    with open("results/ber_results.json") as f:
        out["sim"] = json.load(f)

    cfg = OFDMConfig()
    out["config_summary"] = cfg.summary()
    if os.path.exists("results/papr_tradeoff.json"):
        with open("results/papr_tradeoff.json") as f:
            out["papr"] = json.load(f)

    # ---- a clean simulated pipeline snapshot, for the pipeline plots -------
    rng = np.random.default_rng(4)
    bits = rng.integers(0, 2, 3000).astype(np.int8)
    x, meta = modem.modulate(bits, cfg)
    rx, info = channel.apply_channel(x, snr_db=18, cfg=cfg, delay=3000,
                                     clock_ppm=60, rng=rng)
    pipe = {}
    for mode in ("none", "static", "adaptive"):
        r = receiver.demodulate(rx, len(bits), meta["n_sym"], cfg, mode=mode,
                                noise_var=info["noise_var"])
        b, e, n = receiver.ber(bits, r["bits"])
        s = r["symbols"].ravel()[:1500]
        pipe[mode] = dict(
            ber=b, errors=e, bits=n, evm=r["evm_db"],
            I=[round(float(v), 4) for v in s.real],
            Q=[round(float(v), 4) for v in s.imag],
        )
        if mode == "adaptive":
            H = r["H"]
            pipe["H_mag_db"] = [round(float(v), 2) for v in
                                20 * np.log10(np.abs(H) / np.max(np.abs(H)) + 1e-12)]
            pipe["H_phase"] = [round(float(v), 3) for v in np.angle(H)]
            pipe["sync_env"] = dec(r["sync"]["env"], 800)
            pipe["sync_peak"] = int(r["sync"]["peak"])
            pipe["cpe_deg"] = [round(float(v), 3) for v in np.degrees(r["cpe"])]
    pipe["freqs"] = [round(float(v), 1) for v in cfg.data_bins * cfg.df]
    pipe["tx_wave"] = dec(x, 900)
    pipe["rx_wave"] = dec(rx, 900)
    pipe["fs"] = cfg.fs
    # transmit spectrum
    X = np.abs(np.fft.rfft(x[meta["data_start"]:meta["data_start"] + 4096] *
                           np.hanning(4096)))
    f = np.fft.rfftfreq(4096, 1 / cfg.fs)
    m = f <= 16000
    pipe["spec_f"] = dec(f[m], 500)
    pipe["spec_db"] = dec(20 * np.log10(X[m] / X[m].max() + 1e-12), 500)
    out["pipeline"] = pipe

    # ---- echo ranging -----------------------------------------------------
    er = {"true": [], "est": [], "err_cm": []}
    for dm in [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        for snr in (25, 15, 10):
            y = echo.simulate_echo(dm, cfg, snr_db=snr,
                                   rng=np.random.default_rng(int(dm * 10) + snr))
            r = echo.estimate_distance(y, cfg)
            if r["ok"]:
                er["true"].append(dm)
                er["est"].append(round(r["distance_m"], 4))
                er["err_cm"].append(round(abs(r["distance_m"] - dm) * 100, 2))
    out["echo"] = er

    # ---- real over-the-air capture ---------------------------------------
    if os.path.exists("results/acoustic_run.npz"):
        d = np.load("results/acoustic_run.npz", allow_pickle=True)
        if not bool(d["real"]):
            raise SystemExit(
                "results/acoustic_run.npz holds a SIMULATED run - refusing to "
                "publish it as hardware. Re-run experiments/run_acoustic.py "
                "without --sim.")
        real = dict(
            ber=float(d["ber"]), prr=float(d["prr"]), evm=float(d["evm"]),
            mode=str(d["mode"]), ok=bool(d["ok"]), n_sym=int(d["n_sym"]),
            rx_wave=dec(d["rx"], 900), env=dec(d["env"], 800),
            start=int(d["start"]),
        )
        s = np.asarray(d["symbols"]).ravel()[:1500]
        real["I"] = [round(float(v), 4) for v in s.real]
        real["Q"] = [round(float(v), 4) for v in s.imag]
        if len(d["calib_db"]):
            cb = np.asarray(d["calib_bins"], dtype=int)
            real["calib_f"] = [round(float(v), 1) for v in cb * cfg.df]
            db = np.asarray(d["calib_db"], dtype=float)
            real["calib_db"] = [round(float(v), 2) for v in db - db.max()]
            real["calib_kept_f"] = [round(float(v), 1) for v in
                                    np.asarray(d["calib_kept"], dtype=int) * cfg.df]
        if len(d["calib_ir"]):
            real["ir"] = dec(np.asarray(d["calib_ir"], dtype=float), 400)
        out["real"] = real

    os.makedirs("dashboard", exist_ok=True)
    with open("dashboard/data.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print("wrote dashboard/data.json  (%.0f kB)"
          % (os.path.getsize("dashboard/data.json") / 1024))
    for m in ("none", "static", "adaptive"):
        print(f"  pipeline {m:9s}: BER {pipe[m]['ber']:.2e}  EVM {pipe[m]['evm']:.1f} dB")
    if "real" in out:
        print(f"  real OTA: BER {out['real']['ber']:.2e}  PRR {out['real']['prr']*100:.0f}%")
    print(f"  echo: mean error {np.mean(er['err_cm']):.1f} cm over "
          f"{len(er['true'])} measurements")


if __name__ == "__main__":
    main()
