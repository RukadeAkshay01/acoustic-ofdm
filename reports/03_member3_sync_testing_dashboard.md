# Individual Report — Member 3: Synchronisation, Testing, BER Analysis and Web Dashboard

**Name:** Ritesh Gajanan Sonar
**Modules:** `ofdm/sync.py`, `ofdm/receiver.py`, `ofdm/channel.py`, `ofdm/framing.py`, `ofdm/audio_io.py`, `experiments/`, `dashboard/`
**Project:** Adaptive Self-Calibrating OFDM Acoustic Communication
**Date:** 30 August 2026

---

## 1. My responsibility

Frame synchronisation, the simulated channel that lets us measure BER against a
known truth, the file framing layer, the real audio I/O path, all four BER
experiments, and the web dashboard.

Synchronisation is the part the review comments warned could "take weeks", so I
started with it.

---

## 2. Frame synchronisation

An acoustic packet arrives after an unknown delay of anywhere from a few
milliseconds to a few hundred, so nothing else can run until the frame is found.
I correlate the received stream against Member 1's known chirp and take the
envelope via the Hilbert transform, which makes the timing estimate blind to
carrier phase.

A 30 ms sweep across 10 kHz has a time–bandwidth product near 300, so the matched
filter output is a peak roughly `1/B ≈ 0.1 ms` wide even when the waveform itself
is buried in noise.

| SNR | Detection confidence (peak / noise floor) | Timing error |
|---|---|---|
| 30 dB | 121× | 0 samples |
| 20 dB | 121× | 0 samples |
| 10 dB | 105× | 0 samples |
| 5 dB | 77× | 0 samples |
| 0 dB | 54× | 0 samples |

Sample-exact down to 0 dB SNR.

### The cyclic-prefix backoff, and the constraint I got wrong

After finding the peak I deliberately start the FFT window a few samples *early*,
inside the cyclic prefix. Any multipath delay then lands in the ISI-free region and
appears only as a phase ramp across subcarriers, which Member 2's equaliser absorbs.
Sitting exactly on the peak would let the first echo bleed into the next symbol.

My first version backed off by `ncp/2` = 32 samples, which broke Member 2's pilot
interpolation completely. A window that starts *D* samples early makes the apparent
channel rotate `2πD/N` radians per subcarrier, and a pilot-based estimator can only
track that while the rotation stays under π radians **between adjacent pilots**:

```
D < N / (2 · pilot_spacing) = 256 / 8 = 32 samples
```

32 samples sits exactly on the aliasing limit. I measured the actual channel phase
rotating 46° per subcarrier — 184° between pilots, past the 180° limit — so the
unwrapped phase was nonsense and interpolation could not recover. Reducing the
backoff to 8 samples fixed it.

This is the most useful thing I learned in the project: the synchroniser and the
channel estimator are not independent modules. My timing choice sets a hard
constraint on their pilot spacing, and neither of us could see it from our own module
alone.

---

## 3. Simulated channel

To measure BER I need a channel whose truth I know, which is impossible over a real
speaker. `ofdm/channel.py` models the four effects that actually break acoustic
OFDM: sparse multipath (direct path plus decaying reflections), a band-pass FIR
standing in for the speaker and microphone, additive noise at a target SNR, and a
sampling-clock offset implemented by resampling.

**A methodology bug I had to fix.** My first BER sweeps were non-monotonic — BER at
26 dB was better than at 28 dB — which made the curves useless. The cause was that
I redrew the random room at every SNR point, so each point saw a different set of
spectral nulls and the differences had nothing to do with SNR. I changed the impulse
response seed to depend only on the trial index, so every SNR point in a sweep sees
the *same* set of rooms. The curves became monotonic immediately.

---

## 4. BER experiments

Four experiments, 16 trials × 6 200 bits per point (~99 000 bits).

**A — modem validation on AWGN.** With multipath off, the measured curve should sit
on the coherent-QPSK theory curve `Q(√(2·Eb/N0))`. It does (0 dB: 7.32 × 10⁻² vs
7.86 × 10⁻² theory; 4 dB: 1.20 × 10⁻² vs 1.25 × 10⁻²; zero errors in 99 200 bits
from 12 dB up). This single test validates the IFFT, cyclic prefix, synchroniser and
demapper simultaneously.

**B — equaliser comparison on the multipath channel.** Unequalised BER never leaves
0.47 at any SNR; equalised it falls to a 3.5 × 10⁻³ floor set by spectral nulls.

**C — sampling-clock offset.** The headline result: at 100 ppm, static calibration
gives 0.51 and adaptive tracking gives 3.8 × 10⁻³.

**D — adaptive step size μ.** Establishes μ = 0.15 as the operating point.

Full tables are in the team report and on the dashboard.

---

## 5. File framing

Files are carried as a CRC-protected 32-byte header (filename + length) followed by
fixed-length CRC-tagged packets, which gives us the packet-recovery-rate metric the
proposal asked for.

**A bug worth recording.** My first version wrote a variable-length final packet.
That shifted the CRC field for the last packet and broke the receiver's fixed-stride
parser — a clean round-trip with zero bit errors still failed to reconstruct the
file. Padding every packet to the same length fixed it. The general lesson is that a
parser which assumes a fixed stride must be given a fixed stride, including at the
end.

I also added an interleaved repetition code after the over-the-air tests showed that
a single bit error destroys an entire 72-byte packet. Repetition-3 turns a raw BER
of 1.8 × 10⁻² into a coded 1.9 × 10⁻³ and took packet recovery from 1/5 to 3/5;
on our best over-the-air run it reached a coded BER of 3.2 × 10⁻⁴ with 4/5 packets
and 229 of 293 bytes recovered. In simulation at 20 dB SNR with an 80 ppm clock
offset the same configuration recovers the file **exactly** — 293/293 bytes,
5/5 packets, zero coded bit errors — so the framing and FEC layers are correct and
the remaining over-the-air shortfall is link SNR, not logic.

---

## 6. Real audio I/O — where most of the debugging went

I used ALSA `aplay`/`arecord` directly so the project needs no extra Python audio
packages. Getting a real acoustic link working took four separate fixes, none of
which were DSP problems, and all of which initially looked like DSP problems.

1. **Capture start-up transient.** ALSA emits a full-scale, clipped 10 ms click when
   a capture device starts — about 30 dB above our wanted signal. The matched filter
   locked onto it instead of the chirp, reporting a frame at sample 145 when the real
   chirp was at 20 912. Fixed by blanking the first 250 ms.

2. **Capture stop transient.** The same thing happens at the other end. On one run
   the correlator locked onto a peak 2.73 s into a 3 s recording. Fixed with a tail
   guard, plus a rule rejecting any candidate too close to the end of the buffer to
   contain a whole frame.

3. **Noise-floor estimate.** Once the search window was narrowed, the median of the
   window was itself signal, and the confidence ratio collapsed below threshold so
   nothing was detected at all. Switched to a 20th-percentile estimate.

4. **Levels.** The microphone input was set 34 dB down, and later the speaker was
   simply muted — I spent an hour on what looked like a demodulation failure before
   checking `pactl get-sink-mute`. Diagnosing it properly took a spectrum check: the
   recording energy was completely flat across all forty 50 ms blocks, meaning no
   signal had been transmitted at all.

I now calibrate the capture gain automatically before every transmission by binary
searching the device volume for a target recorded peak. This turned out to be
necessary rather than convenient: the usable window is narrow and very steep
(30% volume gave a recorded peak of 0.07 while 50% clipped outright, because
PipeWire volume is roughly cubic in amplitude).

**Diagnostic that unblocked us.** When BER was stuck at 0.31 with no obvious cause,
I wrote `experiments/diagnose_link.py`, which transmits one identical OFDM symbol
40 times and measures how repeatable the received copies are. That separated noise
from distortion from receiver bugs in one run, and showed the recording was clipping
(348 saturated samples) — which no linear equaliser can undo.

---

## 7. Web dashboard

Built as a single self-contained HTML page with hand-written SVG charts, showing
the full pipeline the review comments asked for: transmitted signal, received
signal, matched-filter output, FFT spectrum, channel estimate, per-symbol phase
correction, equalised constellations for all three modes, decoded results and BER
metrics — plus the measured hardware response and the echo-ranging accuracy.

Charts are generated from `dashboard/data.json`, which is exported directly from the
experiment scripts, so the page cannot drift from the measurements. It has crosshair
tooltips, data tables under every BER chart, and works in both light and dark themes.

**Live:** https://rukadeakshay01.github.io/acoustic-ofdm/

---

## 8. What I would do next

- **The two-device test**, which is our biggest gap. All over-the-air work so far is
  one laptop talking to itself, so both ends share a crystal — the clock-offset
  result that the whole Phase 3 argument rests on has only been verified against a
  *simulated* offset. This is my top priority for week 5.
- **A better sync metric.** Peak-to-noise-floor ratio is crude; a normalised
  correlation with a proper detection threshold would give a false-alarm rate we
  could actually quote.
- **Characterise clock drift over long frames.** Our frames are under 2 seconds; a
  real file transfer is much longer and the drift is uncharacterised.
- **Automate the level calibration further** so it adapts mid-transfer rather than
  only at the start.
