# Individual Report — Member 2: Channel Estimation, Pilot Design and Equalisation

**Name:** Krithika Jayganesh
**Module:** `ofdm/equalizer.py`, `ofdm/calibrate.py`
**Project:** Adaptive Self-Calibrating OFDM Acoustic Communication
**Date:** 30 August 2026

---

## 1. My responsibility

I own everything between the receiver's FFT and its demapper: estimating what the
acoustic channel did to each subcarrier, and undoing it. That covers the one-shot
(Phase 2) estimator, the adaptive tracker (Phase 3), the equaliser itself, and —
added after a hardware measurement forced it — the Stage-1 self-calibration that
decides which subcarriers are worth using at all.

I implemented three modes so the project could measure the value of each stage
rather than assert it:

| Mode | What it does |
|---|---|
| `none` | no equalisation — the Phase 1 baseline |
| `static` | one least-squares estimate from the reference symbol, held for the whole burst |
| `adaptive` | static estimate, then tracked from the pilots in every payload symbol |

---

## 2. Phase 2 — one-shot least-squares estimation

Member 1's frame carries a fully-known reference symbol on all 43 occupied
subcarriers. The least-squares estimate is simply

```
Ĥ[k] = Y[k] / X[k]
```

followed by a short 3-tap moving average across frequency, which trades a little
resolution for noise reduction.

**Equaliser choice: MMSE, not zero-forcing.** The obvious equaliser is `1/Ĥ`, but
the acoustic channel has deep spectral nulls, and dividing by a near-zero `Ĥ`
amplifies the noise on that subcarrier by the same enormous factor. I use

```
W[k] = conj(Ĥ[k]) / (|Ĥ[k]|² + σ²)
```

which reduces to `1/Ĥ` where the channel is strong and rolls off gracefully where
it is not.

### Result

| SNR | No equalisation | Static equalisation |
|---|---|---|
| 0 dB | 4.73 × 10⁻¹ | 1.21 × 10⁻¹ |
| 6 dB | 4.69 × 10⁻¹ | 3.80 × 10⁻² |
| 12 dB | 4.67 × 10⁻¹ | 1.21 × 10⁻² |
| 18 dB | 4.68 × 10⁻¹ | 4.58 × 10⁻³ |
| 30 dB | 4.68 × 10⁻¹ | 3.63 × 10⁻³ |

The unequalised BER never leaves 0.47 at any SNR. This is the clearest result in
the project: over a frequency-selective channel, equalisation is not an
optimisation, it is the difference between a working link and no link. EVM
improves from −5.3 dB to −7.3 dB and channel-estimation NMSE reaches −14.7 dB at
20 dB SNR.

The residual floor at ~3.5 × 10⁻³ is set by the channel's deepest null, not by
noise — an uncoded subcarrier in a 40 dB null is a coin flip however good the
estimate is.

---

## 3. Phase 3 — the adaptive tracker, and the version that failed

### What I tried first, and why it was wrong

The obvious recursion is to blend the pilot-derived estimate into the running one
each symbol:

```
Ĥ ← (1 − μ)·Ĥ + μ·Ĥ_pilot
```

This made performance **worse**: BER rose from 3 × 10⁻⁴ to about 1 × 10⁻¹, and the
degradation did not shrink as SNR increased, which told me it was systematic
rather than noise.

The reason is that it throws away a 43-subcarrier reference estimate and replaces
it with 12 pilots interpolated across the spectrum. Between two pilots that
straddle a spectral null, the interpolated value is simply wrong — so every symbol
nudged a good estimate further from the truth.

### What works: track a smooth *correction*, not the channel

Instead of re-estimating the channel, I estimate a correction relative to what I
already have. At the pilot subcarriers,

```
C[k] = Ĥ_pilot_LS[k] / Ĥ_current[k]
```

`C` is near unity and smooth in frequency, because the sharp spectral structure
has already been divided out. I then fit it to a two-parameter physical model:

```
C(k) = g · exp( j (a + b·k) )
```

- **g** — bulk gain change (the devices moving, or an AGC stepping)
- **a** — residual common phase
- **b** — a phase *slope*, which is exactly the signature of a sampling-clock
  offset: a timing drift of τ samples rotates subcarrier *k* by 2πkτ/N

and update `Ĥ ← Ĥ · (1 − μ + μ·C)`. The fit is weighted by `|Ĥ|²` so that pilots
sitting in a null, whose estimates are mostly noise, carry little influence.

This cannot corrupt the null structure, because it only ever applies a smooth,
physically meaningful correction. The fine detail keeps coming from Member 1's
reference symbol; the pilots supply only the slow drift.

### Result — the case this was built for

Two devices never share a crystal. At a sampling-clock offset of 100 ppm:

| Clock offset | Static | Adaptive | Improvement |
|---|---|---|---|
| 0 ppm | 4.47 × 10⁻³ | 4.54 × 10⁻³ | — |
| 25 ppm | 5.40 × 10⁻² | 4.02 × 10⁻³ | 13× |
| 50 ppm | 2.20 × 10⁻¹ | 3.68 × 10⁻³ | 60× |
| **100 ppm** | **5.14 × 10⁻¹** | **3.79 × 10⁻³** | **135×** |
| 200 ppm | 5.14 × 10⁻¹ | 4.63 × 10⁻³ | 111× |
| 400 ppm | 5.00 × 10⁻¹ | 1.05 × 10⁻² | 48× |
| 800 ppm | 5.02 × 10⁻¹ | 1.10 × 10⁻¹ | 4.6× |

Static calibration at 100 ppm gives BER 0.51 — a coin flip, carrying no
information. It does not degrade gracefully; it fails outright. On a *fixed*
channel the two modes are indistinguishable, which is the correct behaviour: the
tracking costs nothing when it is not needed.

### Step size

| μ | Fixed channel | 200 ppm drift |
|---|---|---|
| 0 (off) | 1.01 × 10⁻² | 2.42 × 10⁻¹ |
| 0.02 | 1.02 × 10⁻² | 1.09 × 10⁻¹ |
| 0.05 | 1.02 × 10⁻² | 2.54 × 10⁻² |
| **0.15** | **1.03 × 10⁻²** | **9.04 × 10⁻³** |
| 0.50 | 1.03 × 10⁻² | 8.39 × 10⁻³ |

μ = 0.15 fixes the drifting case at no measurable cost on a fixed channel. Note
that μ = 0 (common-phase correction only, no pilot update) still gives 0.24 on the
drifting channel — so both mechanisms are necessary, not just the phase term.

---

## 4. Stage 1 — self-calibration, added because the hardware demanded it

When we first ran over a real speaker and microphone, the uncoded BER stuck at
0.31 and none of my equaliser tuning moved it. I swept the chirp through the real
hardware and measured the end-to-end magnitude response:

| Band | Response (rel. peak) |
|---|---|
| 4.0–5.5 kHz | −5 to −11 dB |
| 6.0–6.5 kHz | −16 dB, min −34 dB |
| 6.5–7.0 kHz | −21 dB, min −40 dB |
| 7.5–8.5 kHz | −23 dB, **min −43 dB** |
| 9.5–11.0 kHz | −5 to −11 dB |
| 11.5–12.0 kHz | −15 dB |

**43 dB of dynamic range across the band.** Roughly a third of our subcarriers were
sitting in dead spectrum. No equaliser can repair that — MMSE correctly refuses to
amplify them, but the bits carried there are lost either way.

So I implemented `ofdm/calibrate.py`: measure the response from the chirp once
before transmitting, keep only subcarriers within a set backoff of the strongest
one, and restrict both ends to that set. This is the acoustic equivalent of DSL
bit-loading, and it is Stage 1 of our original proposal taken more seriously than
we first intended.

| Backoff | Subcarriers kept | Over-the-air uncoded BER |
|---|---|---|
| none (full band) | 43 / 43 | 3.1 × 10⁻¹ |
| 12 dB | 33 / 43 | 8.7 × 10⁻² |
| **8 dB** | **18 / 43** | **8.3 × 10⁻³** |

A 37× BER improvement, for the cost of a one-second probe before transmission.

---

## 5. A metric I had to fix

My channel-estimation NMSE was reporting **+22.9 dB** — an error larger than the
signal — for an estimate that was simultaneously recovering data with zero bit
errors. Both could not be true.

The metric was scoring the FFT-window phase ramp. Our synchroniser deliberately
starts the window a few samples early, which appears as `exp(−j2πkd/N)` across the
subcarriers. That costs nothing — my equaliser divides it straight out — but a
naive NMSE counts it as pure error. The corrected metric removes a global complex
gain *and* a fitted linear phase ramp before scoring, and now reports −14.7 dB at
20 dB SNR, improving with SNR and flooring on estimator noise as expected.

The lesson: a metric that disagrees with the BER is a broken metric until proven
otherwise.

---

## 6. What I would do next

- **Bit-loading instead of subcarrier rejection.** Discarding a subcarrier that is
  12 dB down throws away capacity that BPSK could still carry. Loading bits
  according to measured per-subcarrier SNR is the standard answer and would remove
  the error floor.
- **Decision-directed tracking** between pilots, using the demapped data symbols as
  additional references — more tracking bandwidth for no extra overhead.
- **A two-device feedback handshake.** My calibration currently assumes both ends
  can be configured together. A real two-device system needs the receiver to report
  its chosen subcarrier set back to the transmitter.
