# Adaptive Self-Calibrating OFDM Acoustic Communication

Sends files between the speaker and microphone of ordinary devices using OFDM in
the 4–12 kHz audio band, with pilot-based channel estimation, adaptive tracking
and automatic self-calibration.

Signal Processing mini project — Akshay Rukade, Krithika Jayganesh,
Ritesh Gajanan Sonar.

**Results dashboard:** https://rukadeakshay01.github.io/acoustic-ofdm/
**Reports:** `reports/`

## Requirements

Python 3 with `numpy` and `scipy`:

```bash
pip install -r requirements.txt
python3 -m unittest discover -s tests -t .     # 26 tests, ~1 s
```

Real over-the-air tests additionally need ALSA (`aplay` / `arecord`), which ship
with any Linux desktop. No other dependencies — the dashboard is plain HTML/SVG.

## Layout

| Path | Purpose |
|---|---|
| `ofdm/config.py` | every system parameter, single source of truth |
| `ofdm/modem.py` | QPSK map/demap, Hermitian IFFT, cyclic prefix, PAPR reduction |
| `ofdm/sync.py` | chirp matched filter, frame detection, impulse-response estimation, clock-offset (ppm) estimation |
| `ofdm/equalizer.py` | LS channel estimation, pilot tracking, MMSE equalisation |
| `ofdm/calibrate.py` | Stage-1 response measurement and subcarrier selection |
| `ofdm/channel.py` | simulated acoustic channel (multipath, transducers, clock offset) |
| `ofdm/receiver.py` | full receive chain, band-pass front end, BER/EVM |
| `ofdm/framing.py` | CRC packets, file encode/decode, repetition and convolutional FEC framing |
| `ofdm/conv.py` | rate-½ K=7 convolutional code, soft-decision Viterbi, interleaver |
| `ofdm/live.py` | blind receiver for self-describing frames, with clock correction |
| `ofdm/audio_io.py` | ALSA playback/capture, automatic gain calibration |
| `experiments/` | every measurement in the reports |
| `tests/` | unit and end-to-end tests |
| `dashboard/` | self-contained results dashboard (`docs/` is the GitHub Pages copy) |
| `results/` | generated JSON / NPZ results |

## Reproducing the results

```bash
python3 experiments/run_ber.py           # BER experiments A–D  (~2 min)
python3 experiments/run_papr.py          # peak-to-average trade-off
python3 experiments/run_fec.py           # uncoded vs repetition-3 vs convolutional  (~10 s)
python3 experiments/run_drift.py         # long frames x clock offset, with/without correction  (~20 s)
python3 experiments/export_dashboard.py  # rebuild dashboard/data.json
python3 build_dashboard.py               # rebuild dashboard/index.html and docs/index.html
```

## Real over-the-air transfer

```bash
python3 experiments/run_acoustic.py --mode adaptive --backoff 8 --fec 3
python3 experiments/run_acoustic.py --mode adaptive --fec conv      # convolutional code
```

This plays an audible ~1 s burst and records it. Options:

- `--mode none|static|adaptive` — equaliser mode
- `--backoff N` — keep subcarriers within N dB of the strongest (default 8, which
  works best on the test laptop; larger keeps more subcarriers but includes weak ones)
- `--fec N|conv` — repetition-N forward error correction (default 3; 0 = off, which
  fails even in simulation), or `conv` for the rate-½ convolutional code
- `--sim` — use the channel model instead of real audio, for machines with no
  sound device
- `--no-calib` — skip Stage-1 calibration

**Set the output volume high before running.** The script calibrates the *capture*
gain automatically, but not playback. On the test laptop, results above assume
system volume near 100%; at low volume the link is noise-limited and will not
decode. If sync fails, check `pactl get-sink-mute @DEFAULT_SINK@` first — a muted
speaker looks exactly like a DSP bug.

Other diagnostics:

```bash
python3 experiments/diagnose_link.py     # repeated-symbol link quality probe
```

## Two separate devices

```bash
# on the receiving device
python3 experiments/run_two_device.py rx --seconds 30 --distance 1.0 --label "A->B"
# on the transmitting device
python3 experiments/run_two_device.py tx --play --count 5
# afterwards, on the receiver
python3 experiments/run_two_device.py report
```

The receiver is blind, measures the clock offset between the two devices in ppm,
and logs every frame to `results/two_device_log.jsonl`. `tx --wav frames.wav`
writes the frames to a file so a phone can be the transmitter, and `rx --wav`
decodes any recording. `sim` runs the same thing through the channel model. Full
procedure: [`reports/04_two_device_test_protocol.md`](reports/04_two_device_test_protocol.md).

## Current status

| Item | State |
|---|---|
| Phase 1 — OFDM end to end, BER vs theory | Done |
| Phase 2 — pilots, estimation, equalisation | Done |
| Phase 3 — adaptive tracking | Done in simulation |
| Proper FEC (convolutional, soft Viterbi) | Done in simulation: 2408 vs 1794 bit/s, decodes ~12 dB lower than repetition-3 |
| Long-frame clock drift | Done in simulation: offset estimated to a few ppm and corrected; 5 s frames survive ±400 ppm |
| Echo ranging (Stage 4) | Dropped, as the reviewer suggested |
| **Two-device test** | **Tooling ready; measurement not yet done** |
| Bit-loading | Not implemented |

What remains:

1. **Run the two-device test** on real hardware (protocol above) and record the
   measured clock offset, EVM and BER against distance.
2. **Confirm the convolutional code and drift correction over the air.** Both
   are verified in simulation only. The live frame format (`ofdm/live.py`) still
   uses soft repetition; moving it to the convolutional code needs a header field
   for the code type.
3. **Bit-loading** (optional): put fewer bits on weak subcarriers instead of
   dropping them, to remove the ~3 × 10⁻³ equalised error floor.
4. **Final report**, built from the regenerated dashboard data.
