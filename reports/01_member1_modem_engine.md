# Individual Report — Member 1: OFDM Modulation / Demodulation Engine

**Name:** Akshay Rukade
**Module:** `ofdm/modem.py`, `ofdm/config.py`
**Project:** Adaptive Self-Calibrating OFDM Acoustic Communication
**Date:** 30 August 2026

---

## 1. My responsibility

I own the modem core: turning a bit vector into a real-valued waveform that a
speaker can play, and turning received samples back into a resource grid. That
covers QPSK mapping, the IFFT and cyclic prefix, the pilot and preamble structure,
the peak-to-average power problem, and the system parameter set that everything
else in the project reads from.

---

## 2. The main design decision: real-valued output straight from the IFFT

The textbook OFDM transmitter produces a complex baseband signal and then mixes it
up to a carrier. For an acoustic link that stage is pure overhead and a large
source of bugs, because any carrier phase or frequency error at the receiver has
to be undone before demodulation can work at all.

Instead I place the QPSK symbols directly on FFT bins 22–64 of a 256-point IFFT
and enforce **Hermitian symmetry**:

```
X[k]     = data symbol        for k in 22..64
X[N−k]   = conj(X[k])
X[0] = X[N/2] = 0
```

A spectrum with this property has a purely real inverse transform. The IFFT output
is therefore already a real audio signal occupying 4–12 kHz, and can be written
straight to a WAV file. I verified this numerically: the residual imaginary part
after the transform is 7 × 10⁻¹⁷, i.e. floating-point noise.

There is no up-conversion stage in this project, and consequently no carrier
frequency offset to estimate.

### Parameter choice

| Parameter | Value | Reasoning |
|---|---|---|
| Sample rate | 48 kHz | supported by every consumer device without resampling |
| FFT size *N* | 256 | subcarrier spacing 187.5 Hz; symbol 6.67 ms, short enough that the room is static across it |
| Cyclic prefix | 64 samples | 1.33 ms, covering 0.46 m of excess path length |
| Band | 4–12 kHz | laptop speakers roll off below ~4 kHz, microphones above ~12 kHz |
| Modulation | QPSK, Gray coded | 2 bit/subcarrier; Gray coding means one symbol error costs one bit, not two |

This yields 43 occupied subcarriers → 31 data + 12 pilot → 62 bits per symbol →
**9 300 bit/s** raw payload rate.

I deliberately put every one of these in a single dataclass (`ofdm/config.py`) with
derived quantities as properties, so my teammates' experiments could sweep FFT
size or bandwidth without editing DSP code. This paid off later when we needed to
restrict the modem to a calibrated subset of subcarriers — that became a one-line
addition to the config rather than a change to my modulator.

---

## 3. Pilot and preamble design

**Pilots** are a deterministic pseudo-random ±1 BPSK sequence, not an all-ones
pattern. An all-ones pilot set adds coherently in the time domain and produces a
loud impulse that clips a small speaker. The pseudo-random pattern has the same
estimation properties with a much lower peak.

**The reference symbol** at the head of every frame is a fully-known QPSK symbol
on *all* occupied subcarriers. This is what Member 2's one-shot channel estimator
consumes. Using a full symbol rather than only the pilots gives them a
43-subcarrier estimate instead of a 12-point interpolation — a decision that
turned out to matter a great deal (see their report).

**The preamble** is a 30 ms linear chirp from 3 to 13 kHz with a raised-cosine
taper on both ends. The taper is not cosmetic: a hard-edged chirp produces an
audible click and spectral splatter on a small speaker.

---

## 4. Peak-to-average power — my largest contribution to real-world performance

An OFDM symbol is the sum of 43 independent subcarriers, so by the central limit
theorem its envelope is close to Gaussian and its peak-to-average power ratio is
about 11 dB. A speaker is **peak-limited**, not average-limited. That means an
unclipped OFDM waveform throws away roughly 11 dB of the transmit power the
hardware could actually deliver — and received SNR follows average power, not peak.

I implemented **iterative clipping and filtering**. Each pass clips the waveform to
a set level above its RMS, then transforms to the frequency domain, zeros every bin
outside 4–12 kHz, and transforms back. The filtering step matters because raw
clipping splatters energy out of band, which is both audible and useless. Clipping
regrows a little after filtering, hence the iteration; three passes is enough.

Measured trade-off (AWGN, 6 trials × 6 200 bits per point):

| Clipping limit | Resulting PAPR | Avg power gain | BER @ 8 dB | BER @ 14 dB | BER @ 26 dB |
|---|---|---|---|---|---|
| none | 11.3 dB | +0.0 dB | 1.9 × 10⁻⁴ | 0 | 0 |
| 8 dB above RMS | 9.2 dB | +2.1 dB | 1.3 × 10⁻⁴ | 0 | 0 |
| **6 dB above RMS** | **8.0 dB** | **+3.3 dB** | **3.2 × 10⁻⁴** | **0** | **0** |
| 5 dB above RMS | 7.5 dB | +3.8 dB | 7.8 × 10⁻⁴ | 0 | 0 |
| 4 dB above RMS | 7.1 dB | +4.2 dB | 2.6 × 10⁻³ | 5.4 × 10⁻⁵ | 2.7 × 10⁻⁵ |
| 3 dB above RMS | 7.1 dB | +4.3 dB | 5.1 × 10⁻³ | 4.6 × 10⁻⁴ | 2.2 × 10⁻⁴ |

I chose **6 dB**. It is the last setting that still reaches zero errors from 14 dB
SNR upward, and it recovers 3.3 dB of transmit power. Below 4 dB an irreducible
error floor appears, because the clipping distortion is now larger than the noise —
visible as BER that stops falling no matter how much SNR is added.

---

## 5. A bug I introduced and had to find

My first version normalised the entire transmit frame — preamble and payload
together — by its single global peak. This is wrong, and it broke the
synchroniser rather than the modulator, which made it hard to attribute.

The chirp is a constant-envelope signal with a 3 dB PAPR; the OFDM block has 9 dB.
Normalising both by the same global peak therefore left the chirp about 6 dB
quieter in RMS than it should have been. The receiver's matched filter locked onto
random correlation inside the payload instead of the preamble, and the recovered
BER was 0.49.

The fix is to normalise the preamble and the payload **separately**, each to the
target amplitude. Detection confidence went from a marginal 8.6× the noise floor
to 121×, and timing became sample-exact down to 0 dB SNR.

The lesson I took from this: in a system with heterogeneous signal types, "one
normalisation for the whole frame" is almost always wrong, because different
signals have different crest factors.

---

## 6. Verification of my module

| Test | Result |
|---|---|
| Hermitian symmetry produces a real signal | max residual imaginary part 7 × 10⁻¹⁷ |
| Ideal loopback (modulate → demodulate, no channel) | BER = 0 |
| AWGN BER vs coherent-QPSK theory | tracks theory 0–10 dB (see team report §3) |
| PAPR reduction preserves demodulation | BER = 0 in clean loopback at 6 dB clipping |
| Config restricted to a subset of subcarriers | pilot/payload/bitrate all re-derive correctly |

---

## 7. What I would do next

- **Bit-loading.** My modulator currently uses QPSK on every subcarrier. The
  measured hardware response varies by 43 dB across the band, so the right answer
  is more bits on strong subcarriers and fewer (or BPSK) on weak ones, rather than
  Member 2's current approach of discarding weak ones entirely. This would remove
  the 3.5 × 10⁻³ error floor and recover throughput at the same time.
- **A longer cyclic prefix option.** 1.33 ms covers our measured impulse response
  (90% of its energy) but would not survive a reverberant room. The config already
  supports changing it; what is missing is the measurement to justify a value.
- **Windowed OFDM** to reduce out-of-band splatter further, which would let us sit
  closer to the band edges.
