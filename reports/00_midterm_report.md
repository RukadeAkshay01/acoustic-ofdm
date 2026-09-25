# Adaptive Self-Calibrating OFDM Acoustic Communication — Mid-Term Report

**Course:** Signal Processing (custom mini project)
**Team:** Akshay Rukade · Krithika Jayganesh · Ritesh Gajanan Sonar
**Date:** 30 August 2026 · approx. week 4 of 7
**Live results dashboard:** https://rukadeakshay01.github.io/acoustic-ofdm/

---

## 1. Status against the approved phase plan

The review comments asked us to follow a strict phased plan and to treat Phase 1
as the minimum viable product. We did, and we started coding on day one rather
than reading papers.

| Phase | Requirement | Status |
|---|---|---|
| **1** | Binary data → OFDM (IFFT + CP) → speaker → mic → sync → FFT → demod → recovered bits | **Complete.** Working end to end in simulation and over a real speaker/microphone pair. |
| **1** | Measure BER with and without noise | **Complete.** Measured AWGN BER tracks the coherent-QPSK theory curve. |
| **2** | Pilot symbols + one-time channel estimation | **Complete.** |
| **2** | Equalisation using the estimated channel | **Complete.** MMSE, with zero-forcing rejected for a measured reason (§5). |
| **2** | BER improvement, equalised vs not | **Complete.** The difference is between a link that never works and one that does. |
| **2** | Test across two separate devices | **Not done.** All over-the-air work so far is one laptop to itself. This is our main gap. |
| **3** | Adaptive channel tracking from pilot updates | **Complete in simulation.** |
| **3** | Adaptive vs static calibration comparison | **Complete.** This is our strongest result (§6). |
| **3** | Echo-based distance estimation | **Working.** Kept, not dropped — see §8 for why it cost almost nothing. |
| **3** | Multi-device testing | **Not done.** |
| — | Web dashboard showing the full pipeline | **Complete.** Link above. |

We did not drop Stage 4 as permitted, because it turned out to reuse the
synchroniser's matched filter essentially unchanged. It took a few hours, not
weeks, and it did not come at the expense of Phases 1 and 2.

---

## 2. System design

The whole system is parameterised from one file, `ofdm/config.py`, so experiments
can sweep the design without touching any DSP code.

| Parameter | Value | Why |
|---|---|---|
| Sample rate | 48 kHz | universally supported by consumer audio hardware |
| FFT size *N* | 256 | 6.7 ms symbol — short enough that the channel is static across it |
| Cyclic prefix | 64 samples (1.33 ms) | covers 0.46 m of excess path length |
| Occupied band | 4–12 kHz | below 4 kHz laptop speakers roll off; above 12 kHz the microphone does |
| Subcarriers | 43 total → 31 data + 12 pilot | pilot every 4th subcarrier |
| Modulation | QPSK, Gray coded | 2 bit/subcarrier |
| Raw payload rate | 9 300 bit/s | 62 bits per 6.67 ms symbol |
| Preamble | 30 ms linear chirp, 3–13 kHz | frame sync *and* channel sounding from one signal |

**One design decision worth calling out.** Rather than building a complex
baseband signal and mixing it up to an audio carrier, we place the QPSK symbols
directly on FFT bins 22–64 and enforce Hermitian symmetry, `X[N−k] = conj(X[k])`.
The IFFT output is then real-valued and already sits in the 4–12 kHz band, so it
can be written straight to a WAV file. This removes the up/down-conversion stage
entirely, and with it a whole class of carrier-phase bugs that we would otherwise
have spent days on.

---

## 3. Phase 1 — the modem works, and we can prove it

With multipath switched off, the measured BER should sit on the coherent-QPSK
theory curve, `Q(√(2·Eb/N0))`. It does. This is the single test that validates the
IFFT, the cyclic prefix, the synchroniser and the demapper simultaneously — if any
of them were wrong, the curve would not land.

| SNR | Measured BER | QPSK theory |
|---|---|---|
| 0 dB | 7.32 × 10⁻² | 7.86 × 10⁻² |
| 2 dB | 3.56 × 10⁻² | 3.75 × 10⁻² |
| 4 dB | 1.20 × 10⁻² | 1.25 × 10⁻² |
| 6 dB | 3.30 × 10⁻³ | 2.39 × 10⁻³ |
| 8 dB | 4.03 × 10⁻⁴ | 1.91 × 10⁻⁴ |
| 10 dB | 3.02 × 10⁻⁵ | 3.87 × 10⁻⁶ |
| ≥ 12 dB | 0 errors in 99 200 bits | — |

Every point is 16 independent transmissions of 6 200 bits. The small excess above
theory at high SNR is the in-band distortion from our peak-to-average reduction
(§7), which is a deliberate trade.

**Synchronisation** locks to the correct sample down to 0 dB SNR. The 30 ms chirp
sweeps 10 kHz, giving a time–bandwidth product near 300, so the matched-filter peak
stays sharp even when the waveform itself is buried in noise.

---

## 4. Phase 2 — equalisation is not an optimisation, it is the link

Over the simulated multipath acoustic channel:

| SNR | No equalisation | Static (one-shot) | Adaptive |
|---|---|---|---|
| 0 dB | 4.73 × 10⁻¹ | 1.21 × 10⁻¹ | 1.29 × 10⁻¹ |
| 6 dB | 4.69 × 10⁻¹ | 3.80 × 10⁻² | 3.94 × 10⁻² |
| 12 dB | 4.67 × 10⁻¹ | 1.21 × 10⁻² | 1.28 × 10⁻² |
| 18 dB | 4.68 × 10⁻¹ | 4.58 × 10⁻³ | 4.83 × 10⁻³ |
| 30 dB | 4.68 × 10⁻¹ | 3.63 × 10⁻³ | 3.62 × 10⁻³ |

Without equalisation the BER never leaves 0.47 at *any* SNR — the frequency
selectivity of the room, not noise, is what destroys the constellation. Channel
estimation NMSE at 20 dB SNR is **−14.7 dB**; EVM improves from −5.3 dB
unequalised to −7.4 dB equalised.

**The error floor at ~3.5 × 10⁻³ is real and we understand it.** It is not a bug.
The simulated room has deep spectral nulls, and an uncoded subcarrier sitting in a
40 dB null is a coin flip regardless of SNR. This is exactly why we chose MMSE
over zero-forcing: `1/H` in a null amplifies noise by the same 40 dB. Removing the
floor needs bit-loading or forward error correction, both listed in §9.

---

## 5. Phase 3 — where adaptive calibration earns its place

On a *fixed* channel, adaptive tracking and static calibration are
indistinguishable (compare the last two columns above). That is the correct
result, and it says the tracking costs nothing when it is not needed.

The case that separates them is the one the project was proposed for: two devices
that do not share a crystal, so the receiver samples at (1 + ε)·fs.

| Clock offset | Static calibration | Adaptive tracking |
|---|---|---|
| 0 ppm | 4.47 × 10⁻³ | 4.54 × 10⁻³ |
| 25 ppm | 5.40 × 10⁻² | 4.02 × 10⁻³ |
| 50 ppm | 2.20 × 10⁻¹ | 3.68 × 10⁻³ |
| **100 ppm** | **5.14 × 10⁻¹** | **3.79 × 10⁻³** |
| 200 ppm | 5.14 × 10⁻¹ | 4.63 × 10⁻³ |
| 400 ppm | 5.00 × 10⁻¹ | 1.05 × 10⁻² |
| 800 ppm | 5.02 × 10⁻¹ | 1.10 × 10⁻¹ |

At 100 ppm — an ordinary difference between two consumer devices — a one-shot
calibration produces a BER of 0.51. That is a coin flip; the link carries no
information at all. Static calibration does not degrade gracefully here, it fails
completely. Tracking the pilots every symbol holds the same link at 3.8 × 10⁻³, a
**135× improvement**.

**Step size.** The tracker uses a first-order update with step size μ. Sweeping it
at 14 dB SNR shows the classic tracking-versus-noise trade-off:

| μ | Fixed channel | 200 ppm drift |
|---|---|---|
| 0 (tracking off) | 1.01 × 10⁻² | 2.42 × 10⁻¹ |
| 0.05 | 1.02 × 10⁻² | 2.54 × 10⁻² |
| 0.15 | 1.03 × 10⁻² | 9.04 × 10⁻³ |
| 0.50 | 1.03 × 10⁻² | 8.39 × 10⁻³ |

We use **μ = 0.15**: it fixes the drifting case and costs nothing measurable on a
fixed channel.

---

## 6. Over the air, on real hardware

Everything in this section is a real transmission through a laptop speaker,
captured on the same laptop's microphone via ALSA at 48 kHz.

**The measurement that changed the design.** Sweeping the chirp through the real
hardware showed the speaker + microphone + room response varies by up to **43 dB
across the 4–12 kHz band**, with nulls 35–43 dB deep between roughly 6.5 and
9 kHz. Roughly a third of our subcarriers were landing in dead spectrum. The
uncoded over-the-air BER was stuck at 0.31 and no amount of equaliser tuning moved
it, because the problem was not the equaliser.

The fix is Stage 1 of our original proposal, taken more seriously than we first
intended: measure the response with a chirp *before* transmitting, then transmit
only on subcarriers within a set backoff of the strongest one. This is the
acoustic equivalent of DSL bit-loading.

| Configuration | Uncoded BER | Packets recovered |
|---|---|---|
| Full 4–12 kHz band, no calibration | 3.1 × 10⁻¹ | 0 / 5 |
| Stage-1 subcarrier selection, 12 dB backoff | 8.7 × 10⁻² | 0 / 5 |
| Stage-1 subcarrier selection, 8 dB backoff | **8.3 × 10⁻³** | 1 / 5 |
| + repetition-3 code | 1.8 × 10⁻² raw → 1.9 × 10⁻³ coded | 3 / 5 |
| + repetition-5 code | 5.2 × 10⁻² raw → 6.4 × 10⁻⁴ coded | 4 / 5 |
| best run to date (repetition-3, 8 dB backoff) | **1.2 × 10⁻² raw → 3.2 × 10⁻⁴ coded** | **4 / 5**, 229 / 293 bytes |

Run-to-run variation is significant, because the acoustic path changes with room
noise and with how the laptop is sitting on the desk. Sync detection confidence on
the best run reached 2 763× the noise floor.

Recovered text from a real over-the-air run:

> `ADAPTIVE OFDM ACOUSTIC LINK -- Signal Processing mini project. T` … `n the 4-12 kHz band, carried on 31 QPSK subcarriers with 12 pilots, and was recovered by FFT dem...`

The header (filename and length) parses correctly, so the framing layer survives
the real channel.

---

## 7. Engineering log — what actually went wrong

We think this section is the most useful part of the report, because none of these
were predictable from theory.

1. **The chirp was inaudible to the correlator.** We normalised the whole frame by
   its global peak. OFDM has a ~9 dB peak-to-average ratio and the chirp has 3 dB,
   so the chirp came out 6 dB too quiet and sync locked onto random payload
   correlation. *Fix:* scale the preamble and the payload separately.

2. **Pilot interpolation aliased.** The channel's bulk group delay made `H` rotate
   46° per subcarrier. With pilots every 4th subcarrier that is 184° between
   pilots — past the 180° limit — so the interpolated phase was nonsense. *Fix:*
   the FFT-window backoff must satisfy `D < N/(2·pilot_spacing)`; we reduced it
   from 32 to 8 samples.

3. **Adaptive tracking made things worse before it made them better.** Naively
   replacing the channel estimate with the pilot-interpolated one each symbol
   raised BER from 3 × 10⁻⁴ to 1 × 10⁻¹, because it swapped a 43-subcarrier
   estimate for 12 pilots interpolated across spectral nulls. *Fix:* track a
   *multiplicative correction* fitted to a two-parameter model (bulk gain + phase
   slope) instead. The fine structure keeps coming from the reference symbol; the
   pilots only supply the slow drift.

4. **Three separate hardware faults**, each of which looked like a DSP bug: the
   ALSA capture start-up transient (a full-scale 10 ms click) was being mistaken
   for the preamble; the microphone input gain was set 34 dB down; and at one
   point the speaker was simply muted. We now guard the head *and* tail of every
   capture and calibrate the capture gain automatically before transmitting.

5. **A framing bug that only appeared on the last packet.** Variable-length final
   packets shifted the CRC field and broke the receiver's fixed-stride parser.
   *Fix:* pad every packet to the same length.

6. **A metric that was measuring the wrong thing.** Our channel-estimation NMSE
   reported +22.9 dB — an "error" larger than the signal — for an estimate that
   was recovering data with zero bit errors. It was scoring the deliberate
   FFT-window phase ramp, which the equaliser divides straight out. *Fix:* remove
   the global gain and the linear phase ramp before scoring.

**Peak-to-average reduction.** Because a speaker is peak-limited, average power at
a fixed peak is what sets received SNR, and unclipped OFDM wastes ~11 dB of it. We
clip and re-filter iteratively:

| Clipping limit | PAPR | Avg power | BER @ 8 dB | BER @ 14 dB |
|---|---|---|---|---|
| none | 11.3 dB | +0.0 dB | 1.9 × 10⁻⁴ | 0 |
| 8 dB above RMS | 9.2 dB | +2.1 dB | 1.3 × 10⁻⁴ | 0 |
| **6 dB above RMS** | **8.0 dB** | **+3.3 dB** | **3.2 × 10⁻⁴** | **0** |
| 4 dB above RMS | 7.1 dB | +4.2 dB | 2.6 × 10⁻³ | 5.4 × 10⁻⁵ |

6 dB is the last setting that costs nothing at high SNR while gaining 3.3 dB of
transmit power. Clip harder and an irreducible distortion floor appears.

---

## 8. Stage 4 — echo ranging

> **Post-review note:** Stage 4 was dropped after the mid-term review, as the
> reviewer suggested, and `ofdm/echo.py` was removed from the repository. The
> section below is kept as submitted.

Kept because it reuses `sync.matched_filter` unchanged: transmit the chirp, find
the direct arrival, find the reflection after it, `distance = c·Δt/2`.

The one idea it adds is that the direct speaker-to-microphone leakage is 20–40 dB
stronger than any reflection, so the module deliberately blanks the first 25 cm of
range and searches for the strongest peak *after* the direct arrival, not the
largest peak overall.

Across 27 simulated measurements from 0.5 m to 5 m at 25, 15 and 10 dB SNR:
**mean absolute error 0.1 cm, worst case 0.2 cm.** Range resolution is bounded by
the chirp bandwidth at `c/2B ≈ 1.7 cm`. Physical-tape-measure validation is still
to be done.

---

## 9. Remaining work (weeks 5–7)

> **Post-review update:** proper FEC (a rate-½ K = 7 convolutional code,
> `ofdm/conv.py`) and long-frame drift (clock-offset estimation and correction,
> `ofdm/sync.py` / `ofdm/live.py`) are now implemented and verified in
> simulation. The two-device test tooling is in `experiments/run_two_device.py`,
> with the procedure in `reports/04_two_device_test_protocol.md`. Echo ranging
> was dropped. See `README.md` for current status.

| Item | Why it matters | Effort |
|---|---|---|
| **Two-device test** | The clock-offset result is our headline and has only been tested against a *simulated* offset. Both ends currently share a crystal. | High priority, ~1 week |
| **Bit-loading** | Would remove the 3.5 × 10⁻³ error floor by putting fewer bits on weak subcarriers instead of discarding them. | Medium |
| **Proper FEC** | Repetition-3 costs two-thirds of the throughput. A convolutional or Reed–Solomon code would do far better for the same redundancy. | Medium |
| **Long-frame drift** | Frames are currently under 2 s; clock drift over a real file transfer is uncharacterised. | Low |
| **Tape-measure validation of echo ranging** | Currently simulation-only. | Low |

---

## 10. Repository and reproduction

```
ofdm/config.py       all system parameters, one source of truth
ofdm/modem.py        QPSK map/demap, Hermitian IFFT, cyclic prefix, PAPR reduction
ofdm/sync.py         chirp matched filter, frame detection, IR estimation
ofdm/equalizer.py    LS estimation, pilot tracking, MMSE equalisation
ofdm/calibrate.py    Stage-1 response measurement and subcarrier selection
ofdm/channel.py      simulated acoustic channel (multipath, transducers, clock offset)
ofdm/receiver.py     full receive chain
ofdm/framing.py      CRC packets, file encode/decode, repetition FEC
ofdm/echo.py         Stage-4 distance estimation (removed after review)
ofdm/audio_io.py     ALSA playback/capture, automatic gain calibration

experiments/run_ber.py           BER experiments A–D
experiments/run_papr.py          peak-to-average trade-off sweep
experiments/run_acoustic.py      real over-the-air file transfer
experiments/diagnose_link.py     repeated-symbol link diagnostic
experiments/export_dashboard.py  builds dashboard/data.json
```

Reproduce every number in this report:

```bash
python3 experiments/run_ber.py          # simulation results
python3 experiments/run_papr.py         # PAPR trade-off
python3 experiments/run_acoustic.py --mode adaptive --backoff 8 --fec 3
python3 experiments/export_dashboard.py # rebuild dashboard data
```

No figure in this report or on the dashboard is illustrative — every one is
generated from measured output.
