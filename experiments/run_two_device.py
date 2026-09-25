#!/usr/bin/env python3
"""
Two-device over-the-air test - the open Phase 2 item.

Every earlier over-the-air result is one laptop talking to itself, so both ends
share one crystal and the clock-offset tracking has only been exercised
against a *simulated* offset.  This script runs the link between two separate
devices and measures the clock offset between them directly from the sound.

The receiver is blind: it is told nothing about the transmission and
bootstraps from the CRC-protected header carried in the frame (ofdm/live.py).

Transmitter (device A) - any one of:
    python3 experiments/run_two_device.py tx --play --count 5 --gap 4
    python3 experiments/run_two_device.py tx --wav frame.wav
        (copy frame.wav to a phone and play it from there - that tests a
         third, completely unrelated clock and speaker)

Receiver (device B):
    python3 experiments/run_two_device.py rx --seconds 30 --distance 1.0
        records for 30 s, decodes every frame it hears, logs each one
    python3 experiments/run_two_device.py rx --wav capture.wav --distance 1.0
        decodes a recording made with any other tool (phone voice memo
        exported as 48 kHz WAV, Audacity, ...)

Simulation (no audio hardware, sanity check before going to the lab):
    python3 experiments/run_two_device.py sim --ppm -150 -50 0 50 150

Every received frame is appended to results/two_device_log.jsonl; summarise
with `python3 experiments/run_two_device.py report`.

Both ends must use the same TEXT (the default is fine) for the BER column to
be meaningful; the decode itself never uses it.
"""
import argparse
import datetime
import json
import os
import sys

import numpy as np
from scipy.signal import find_peaks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ofdm.config import DEFAULT                           # noqa: E402
from ofdm import live, audio_io, channel, sync            # noqa: E402
from ofdm.receiver import bandpass                        # noqa: E402

LOG = os.path.join(ROOT, "results", "two_device_log.jsonl")
TEXT = (b"TWO-DEVICE TEST -- adaptive OFDM acoustic link. Separate speaker, "
        b"separate microphone, separate sample clocks. If you can read this "
        b"line the clock-offset tracking works on real hardware. 0123456789")


def load_payload(args):
    if getattr(args, "file", None):
        with open(args.file, "rb") as f:
            return f.read(), os.path.basename(args.file)
    if getattr(args, "text", None):
        return args.text.encode(), "message.txt"
    return TEXT, "message.txt"


# ---------------------------------------------------------------------------
# transmit
# ---------------------------------------------------------------------------
def cmd_tx(args):
    data, name = load_payload(args)
    x, bits, fmeta, _ = live.build_frame(data, name, args.repeat, DEFAULT)
    print(DEFAULT.summary())
    print(f"\nframe: {len(data)} bytes, repetition {args.repeat}, "
          f"{len(x) / DEFAULT.fs:.2f} s of audio")
    if args.wav:
        gap = np.zeros(int(args.gap * DEFAULT.fs))
        seq = np.concatenate([np.concatenate([x, gap]) for _ in range(args.count)])
        audio_io.write_wav(args.wav, seq, DEFAULT.fs)
        print(f"wrote {args.wav}  ({args.count} frame(s), {len(seq)/DEFAULT.fs:.1f} s)")
    if args.play:
        import time
        for i in range(args.count):
            print(f"playing frame {i + 1}/{args.count} ...")
            audio_io.play(x, DEFAULT.fs)
            if i + 1 < args.count:
                time.sleep(args.gap)
    if not (args.wav or args.play):
        print("nothing to do: pass --play and/or --wav PATH")
    return 0


# ---------------------------------------------------------------------------
# receive
# ---------------------------------------------------------------------------
def decode_all(rx, fs, expect, skip_s=0.0, max_frames=50):
    """Decode every frame in a recording; returns a list of result dicts."""
    if fs != DEFAULT.fs:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(int(fs), DEFAULT.fs)
        rx = resample_poly(rx, DEFAULT.fs // g, int(fs) // g)
    tx_bits = None
    if expect is not None:
        _, tx_bits, _, _ = live.build_frame(expect[0], expect[1], expect[2], DEFAULT)

    # find_frame locks onto the *strongest* chirp in whatever it is given, so
    # locate every chirp first and hand each frame its own window.
    env = sync.matched_filter(bandpass(rx, DEFAULT), DEFAULT)
    skip = min(int(skip_s * DEFAULT.fs), env.size)
    env[:skip] = 0
    if env.size == 0 or env.max() <= 0:
        return []
    floor = np.percentile(env[skip:], 20) + 1e-12
    height = max(0.3 * env.max(), 6.0 * floor)
    peaks, _ = find_peaks(env, height=height, distance=int(0.4 * DEFAULT.fs))

    results, busy_until = [], 0
    lead = int(0.05 * DEFAULT.fs)
    for j, pk in enumerate(peaks[:max_frames]):
        if pk < busy_until:                         # inside a decoded frame
            continue
        end = peaks[j + 1] - lead if j + 1 < len(peaks) else len(rx)
        lo = max(pk - lead, 0)
        r = live.demodulate_blind(rx[lo:end], DEFAULT, tx_bits=tx_bits)
        if "start" not in r:
            continue
        results.append(summarise(r, lo, expect))
        if r.get("ok"):
            busy_until = lo + r["start"] + (r.get("n_sym", 1) + 1) * DEFAULT.sym_len
    return results


def summarise(r, offset, expect):
    # live.demodulate_blind measures the offset before any correction; fall
    # back to measuring it here if that pass did not run
    ppm = r.get("clock_ppm", float("nan"))
    if not np.isfinite(ppm) and "grid_raw" in r:
        ppm, _ = sync.estimate_clock_ppm(r["grid_raw"], DEFAULT)
    n_sym = r.get("n_sym", 0)
    rec = dict(
        ok=bool(r.get("ok")), stage=r.get("stage"), reason=r.get("reason", ""),
        at_s=round((offset + r.get("start", 0)) / DEFAULT.fs, 3),
        sync_conf=round(float(r["sync"]["confidence"]), 1) if r.get("sync") else None,
        evm_db=round(float(r["evm_db"]), 2) if "evm_db" in r else None,
        clock_ppm=None if np.isnan(ppm) else round(ppm, 1), n_sym=n_sym,
        prr=r.get("prr"), erased=r.get("erased"),
        clock_corrected=bool(r.get("clock_corrected")),
        header=r.get("header"),
    )
    if "raw_ber" in r:
        rec.update(raw_ber=r["raw_ber"], raw_errs=r["raw_errs"], raw_bits=r["raw_bits"])
    data = r.get("data") or b""
    rec["bytes"] = len(data)
    if expect is not None:
        rec["exact"] = data == expect[0]
    rec["preview"] = data[:60].decode(errors="replace")
    return rec


def print_rec(i, rec):
    ber = f"{rec['raw_ber']:.2e}" if "raw_ber" in rec else "  n/a  "
    ppm = f"{rec['clock_ppm']:+7.1f}" if rec["clock_ppm"] is not None else "    n/a"
    evm = f"{rec['evm_db']:6.1f}" if rec["evm_db"] is not None else "   n/a"
    state = ("EXACT" if rec.get("exact") else "ok") if rec["ok"] else f"FAIL({rec['stage']})"
    prr = f"{rec['prr']*100:5.1f}%" if rec.get("prr") is not None else "   - "
    print(f"  #{i:<2d} t={rec['at_s']:7.2f}s  clock {ppm} ppm  EVM {evm} dB  "
          f"raw BER {ber}  PRR {prr}  {state}")


def log_records(recs, args, source):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    with open(LOG, "a") as f:
        for rec in recs:
            rec = dict(rec, time=stamp, source=source, distance_m=args.distance,
                       label=args.label, notes=args.notes)
            f.write(json.dumps(rec, default=str) + "\n")
    print(f"\nappended {len(recs)} record(s) to {os.path.relpath(LOG, ROOT)}")


def cmd_rx(args):
    data, name = load_payload(args)
    expect = None if args.no_expect else (data, name, args.repeat)
    if args.wav:
        rx, fs = audio_io.read_wav(args.wav)
        source, skip = f"wav:{os.path.basename(args.wav)}", 0.0
        print(f"decoding {args.wav}: {len(rx)/fs:.1f} s at {fs} Hz")
    else:
        print(f"recording {args.seconds:.0f} s - start the transmitter now")
        rx, fs = audio_io.record(args.seconds, DEFAULT.fs)
        source, skip = "mic", audio_io.STARTUP_GUARD_S
        if args.save:
            audio_io.write_wav(args.save, rx, fs)
            print(f"saved raw capture to {args.save}")
    pk = float(np.max(np.abs(rx))) if len(rx) else 0.0
    print(f"recorded peak {pk:.3f}" + ("  (very quiet - raise TX volume or move closer)"
                                       if pk < 0.03 else ""))
    recs = decode_all(rx, fs, expect, skip_s=skip)
    if not recs:
        print("no frames found (no synchronisation chirp detected)")
        return 1
    print(f"\n{len(recs)} frame(s):")
    for i, rec in enumerate(recs, 1):
        print_rec(i, rec)
    good = [r for r in recs if r["ok"]]
    if good and good[0]["preview"]:
        print(f"\nfirst decoded text: {good[0]['preview']!r}...")
    log_records(recs, args, source)
    return 0 if good else 1


# ---------------------------------------------------------------------------
# simulation
# ---------------------------------------------------------------------------
def cmd_sim(args):
    data, name = load_payload(args)
    x, bits, _, _ = live.build_frame(data, name, args.repeat, DEFAULT)
    gap = np.zeros(int(1.0 * DEFAULT.fs))
    print(f"simulated two-device link: SNR {args.snr} dB, multipath, "
          f"{len(x)/DEFAULT.fs:.2f} s frames\n")
    print(f"  {'true ppm':>9s}  {'estimated':>9s}  {'EVM':>6s}  {'raw BER':>8s}  result")
    rows = []
    for ppm in args.ppm:
        rng = np.random.default_rng(int(abs(ppm)) + 11)
        stream = np.concatenate([gap, x, gap])
        rx, info = channel.apply_channel(stream, args.snr, DEFAULT, clock_ppm=ppm,
                                         rng=rng)
        recs = decode_all(rx, DEFAULT.fs, (data, name, args.repeat))
        rec = recs[0] if recs else dict(ok=False, clock_ppm=None, evm_db=None)
        est = rec.get("clock_ppm")
        print(f"  {ppm:+9.1f}  {est if est is not None else float('nan'):+9.1f}  "
              f"{rec.get('evm_db') or float('nan'):6.1f}  "
              f"{rec.get('raw_ber', float('nan')):8.1e}  "
              f"{'EXACT' if rec.get('exact') else ('ok' if rec['ok'] else 'FAIL')}")
        rows.append(dict(true_ppm=ppm, est_ppm=est, ok=rec["ok"],
                         exact=bool(rec.get("exact"))))
    return 0 if all(r["exact"] for r in rows) else 1


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def cmd_report(args):
    if not os.path.exists(LOG):
        print(f"no log yet at {os.path.relpath(LOG, ROOT)}")
        return 1
    recs = [json.loads(l) for l in open(LOG) if l.strip()]
    groups = {}
    for r in recs:
        groups.setdefault((r.get("label") or "", r.get("distance_m")), []).append(r)
    print(f"{'label':<16s} {'dist m':>6s} {'frames':>6s} {'decoded':>8s} "
          f"{'exact':>6s} {'mean ppm':>9s} {'ppm sd':>7s} {'mean EVM':>9s} {'mean BER':>9s}")
    summary = []
    for (label, dist), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        ppms = [r["clock_ppm"] for r in rs if r.get("clock_ppm") is not None and r["ok"]]
        evms = [r["evm_db"] for r in rs if r.get("evm_db") is not None and r["ok"]]
        bers = [r["raw_ber"] for r in rs if "raw_ber" in r and r["ok"]]
        row = dict(label=label, distance_m=dist, frames=len(rs),
                   decoded=sum(r["ok"] for r in rs),
                   exact=sum(bool(r.get("exact")) for r in rs),
                   mean_ppm=float(np.mean(ppms)) if ppms else None,
                   sd_ppm=float(np.std(ppms)) if len(ppms) > 1 else None,
                   mean_evm_db=float(np.mean(evms)) if evms else None,
                   mean_raw_ber=float(np.mean(bers)) if bers else None)
        summary.append(row)
        f = lambda v, fmt: format(v, fmt) if v is not None else "-"
        print(f"{label[:16]:<16s} {f(dist, '6.2f'):>6s} {row['frames']:6d} "
              f"{row['decoded']:8d} {row['exact']:6d} {f(row['mean_ppm'], '+9.1f'):>9s} "
              f"{f(row['sd_ppm'], '7.1f'):>7s} {f(row['mean_evm_db'], '9.1f'):>9s} "
              f"{f(row['mean_raw_ber'], '9.2e'):>9s}")
    out = os.path.join(ROOT, "results", "two_device_summary.json")
    with open(out, "w") as fh:
        json.dump(summary, fh, indent=1)
    print(f"\nsaved {os.path.relpath(out, ROOT)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def payload_opts(p):
        p.add_argument("--text", help="message to send (default: built-in test text)")
        p.add_argument("--file", help="send / expect this file instead")
        p.add_argument("--repeat", type=int, default=3,
                       help="repetition factor of the live frame (default 3)")

    p = sub.add_parser("tx", help="transmit from this device")
    payload_opts(p)
    p.add_argument("--play", action="store_true", help="play through the speaker")
    p.add_argument("--wav", help="write the frame(s) to this WAV file")
    p.add_argument("--count", type=int, default=1, help="number of frames")
    p.add_argument("--gap", type=float, default=3.0, help="seconds between frames")

    p = sub.add_parser("rx", help="receive on this device")
    payload_opts(p)
    p.add_argument("--seconds", type=float, default=15.0, help="recording length")
    p.add_argument("--wav", help="decode this recording instead of the microphone")
    p.add_argument("--save", help="also save the raw capture to this WAV")
    p.add_argument("--distance", type=float, default=None, help="speaker-mic distance (m)")
    p.add_argument("--label", default="", help="free-text label, e.g. 'laptopA->laptopB'")
    p.add_argument("--notes", default="", help="room, volume, obstacles, ...")
    p.add_argument("--no-expect", action="store_true",
                   help="payload unknown: skip BER / exact-match scoring")

    p = sub.add_parser("sim", help="simulated two-device run (no audio hardware)")
    payload_opts(p)
    p.add_argument("--ppm", type=float, nargs="+", default=[-150, -50, 0, 50, 150])
    p.add_argument("--snr", type=float, default=15.0)

    sub.add_parser("report", help="summarise results/two_device_log.jsonl")

    args = ap.parse_args()
    return dict(tx=cmd_tx, rx=cmd_rx, sim=cmd_sim, report=cmd_report)[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
