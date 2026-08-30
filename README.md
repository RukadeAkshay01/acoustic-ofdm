# Adaptive Self-Calibrating OFDM Acoustic Communication

Sends files between the speaker and microphone of ordinary devices using OFDM in
the 4–12 kHz audio band, with pilot-based channel estimation, adaptive tracking,
automatic self-calibration, and echo-based distance estimation.

Signal Processing mini project — Akshay Rukade, Krithika Jayganesh,
Ritesh Gajanan Sonar.

**Results dashboard:** https://rukadeakshay01.github.io/acoustic-ofdm/
**Reports:** `reports/`

## Requirements

Python 3 with `numpy` and `scipy` (both already present on the dev machine).
Real over-the-air tests additionally need ALSA (`aplay` / `arecord`), which ship
with any Linux desktop. No other dependencies — the dashboard is plain HTML/SVG.

## Layout

| Path | Purpose |
|---|---|
| `ofdm/config.py` | every system parameter, single source of truth |
| `ofdm/modem.py` | QPSK map/demap, Hermitian IFFT, cyclic prefix, PAPR reduction |
| `ofdm/sync.py` | chirp matched filter, frame detection, impulse-response estimation |
| `ofdm/equalizer.py` | LS channel estimation, pilot tracking, MMSE equalisation |
| `ofdm/calibrate.py` | Stage-1 response measurement and subcarrier selection |
| `ofdm/channel.py` | simulated acoustic channel (multipath, transducers, clock offset) |
| `ofdm/receiver.py` | full receive chain, band-pass front end, BER/EVM |
| `ofdm/framing.py` | CRC packets, file encode/decode, repetition FEC |
| `ofdm/echo.py` | Stage-4 echo distance estimation |
| `ofdm/audio_io.py` | ALSA playback/capture, automatic gain calibration |
| `experiments/` | every measurement in the reports |
| `dashboard/` | self-contained results dashboard |
| `results/` | generated JSON / NPZ results |

## Reproducing the results

```bash
python3 experiments/run_ber.py           # BER experiments A–D  (~2 min)
python3 experiments/run_papr.py          # peak-to-average trade-off
python3 experiments/export_dashboard.py  # rebuild dashboard/data.json
```

Rebuild the dashboard page after regenerating data:

```bash
python3 - <<'PY'
t=open('dashboard/index_template.html').read()
d=open('dashboard/data.json').read()
open('dashboard/index.html','w').write(t.replace('/*__DATA__*/', d))
PY
```

## Real over-the-air transfer

```bash
python3 experiments/run_acoustic.py --mode adaptive --backoff 8 --fec 3
```

This plays an audible ~1 s burst and records it. Options:

- `--mode none|static|adaptive` — equaliser mode
- `--backoff N` — keep subcarriers within N dB of the strongest (8 works best on
  the test laptop; larger keeps more subcarriers but includes weak ones)
- `--fec N` — repetition-N forward error correction (0 = off)
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

## Current status

Phases 1 and 2 are complete; Phase 3 adaptive tracking works in simulation and
echo ranging works. The outstanding gap is **testing across two separate
devices** — all over-the-air work so far is one laptop talking to itself, so both
ends share a clock. See `reports/00_midterm_report.md` §9.
