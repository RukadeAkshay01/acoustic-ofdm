# Who's doing what

Signal Processing mini project — adaptive self-calibrating OFDM acoustic
communication. Full write-up in [`reports/00_midterm_report.md`](reports/00_midterm_report.md).

| Member | Owns | Code | Report |
|---|---|---|---|
| **Akshay Rukade** | OFDM modulation/demodulation engine — IFFT, cyclic prefix, QPSK, pilot & preamble design, PAPR reduction | `ofdm/modem.py`, `ofdm/config.py` | [01](reports/01_member1_modem_engine.md) |
| **Krithika Jayganesh** | Channel estimation, pilot design, equalisation, adaptive tracking, Stage-1 self-calibration | `ofdm/equalizer.py`, `ofdm/calibrate.py` | [02](reports/02_member2_channel_estimation.md) |
| **Ritesh Gajanan Sonar** | Synchronisation, framing, audio I/O, BER analysis, web dashboard | `ofdm/sync.py`, `ofdm/receiver.py`, `ofdm/channel.py`, `ofdm/framing.py`, `ofdm/audio_io.py`, `experiments/`, `dashboard/` | [03](reports/03_member3_sync_testing_dashboard.md) |

Shared: `ofdm/echo.py` (Stage 4), the experiment scripts, and integration debugging.

## Status

| Phase | State |
|---|---|
| 1 — OFDM end to end, BER vs theory | Done |
| 2 — Pilots, channel estimation, equalisation | Done |
| 2 — Two separate devices | **Open — next task** |
| 3 — Adaptive tracking | Done in simulation |
| 3 — Echo ranging | Working |
| Web dashboard | Done |

## Running it

```bash
python3 experiments/run_ber.py                    # BER experiments (~2 min)
python3 experiments/run_acoustic.py --sim         # file transfer, no audio hardware needed
python3 experiments/run_acoustic.py --mode adaptive --backoff 8 --fec 3   # real speaker → mic
```

See [`README.md`](README.md) for the full command reference and setup notes.
