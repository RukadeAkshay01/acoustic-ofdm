# Two-Device Test Protocol

The last open item in Phase 2. Every over-the-air result so far is one laptop
talking to itself, so both ends shared one crystal. The clock-offset tracking,
which is the project's headline result, has only been tested against a
*simulated* offset. This test runs the link between two separate devices and
measures their actual clock offset from the sound.

Tooling: `experiments/run_two_device.py`. The receiver is blind. It learns the
payload length and repetition factor from the CRC-protected header in the
frame. It measures the sampling-clock offset from the pilots
(`sync.estimate_clock_ppm`, accurate to a few ppm in simulation) and resamples
onto the transmitter's clock when drift over the frame would matter.

---

## 0. Before going to the lab

Check the whole chain in simulation on both machines:

```bash
pip install -r requirements.txt
python3 -m unittest discover -s tests -t .
python3 experiments/run_two_device.py sim --ppm -300 -100 0 100 300
```

Every row should say `EXACT`, with the estimated ppm within about 10 of the
true value.

## 1. Setup

| | |
|---|---|
| **Device A (transmitter)** | laptop, or any phone that can play a WAV |
| **Device B (receiver)** | Linux laptop with ALSA (`arecord`) |
| **Room** | quiet, note it (lab / hostel room / corridor) |
| **Volume** | TX system volume near 100 %; check `pactl get-sink-mute @DEFAULT_SINK@` |
| **Geometry** | TX speaker pointing at RX microphone, nothing in between |

Write down both device models. The clock offset is a property of the pair.

## 2. Procedure

Run each distance as one block of 5 frames. Measure distance with a tape
measure, speaker grille to microphone.

**Receiver (B)**, start first:

```bash
python3 experiments/run_two_device.py rx --seconds 30 --distance 0.5 \
    --label "A-laptop->B-laptop" --notes "lab, quiet" --save results/cap_0p5m.wav
```

**Transmitter (A)**, within a few seconds:

```bash
python3 experiments/run_two_device.py tx --play --count 5 --gap 3
```

Or, for a phone as transmitter, generate the file once, copy it to the phone
and press play:

```bash
python3 experiments/run_two_device.py tx --wav frames.wav --count 5 --gap 3
```

Repeat at **0.5 m, 1 m, 2 m, 3 m**. Then repeat each distance with the
convolutional code. Add `--repeat conv` on **both** ends and use a different
`--label`, e.g. `"A->B conv"`. The receiver reads the code from the frame
header either way. On the tx side the flag picks the code; on the rx side it is
only used to score BER. In simulation, conv frames are 20 % shorter and decode
exactly down to 0 dB SNR, where repetition-3 frames only partly recover. This
is the over-the-air check the code still needs.

Then, if time allows:

- swap roles (B transmits, A receives). The measured ppm should flip sign;
- a phone as the transmitter (a third, unrelated clock);
- a long payload, to exercise drift correction on real hardware:
  `--file some_2kB_file.txt` on **both** ends (the receiver needs it only to
  score BER).

`rx` also decodes any recording made by another tool. A phone voice memo
exported as WAV works too, and non-48 kHz files are resampled:

```bash
python3 experiments/run_two_device.py rx --wav memo.wav --distance 1 --label "phone rec"
```

## 3. Results

```bash
python3 experiments/run_two_device.py report     # table + results/two_device_summary.json
python3 experiments/export_dashboard.py && python3 build_dashboard.py
```

The dashboard shows the two-device table automatically once the summary
exists. Commit `results/two_device_log.jsonl`,
`results/two_device_summary.json` and the rebuilt `dashboard/` + `docs/`.

Record for the final report:

| Setup | Distance (m) | Frames | Decoded | Exact | Clock (ppm) | EVM (dB) | Raw BER |
|---|---|---|---|---|---|---|---|
| A→B | 0.5 | | | | | | |
| A→B | 1.0 | | | | | | |
| A→B | 2.0 | | | | | | |
| A→B | 3.0 | | | | | | |
| A→B conv | 1.0 | | | | | | |
| A→B conv | 3.0 | | | | | | |
| B→A | 1.0 | | | | | | |
| phone→B | 1.0 | | | | | | |

## 4. What to look for

- **Clock offset.** Consumer devices typically sit 10–100 ppm apart. A stable
  value across frames (a small ± spread) confirms the estimator is measuring
  the hardware, not noise. Compare it with the simulated sweep: at that offset,
  static calibration fails and adaptive tracking works.
- **Sign flip on role swap.** This is strong evidence the ppm is real.
- **Failure mode vs distance.** `FAIL(sync)` means the chirp was not heard
  (level or distance). `FAIL(header)` or partial PRR means synchronised but
  noisy. Compare the same distance with `--repeat conv`, which should push
  the failure point further out.

## 5. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `recorded peak` < 0.03 | TX muted or volume low; RX capture gain low (`pavucontrol`) |
| no frames found | same as above, or TX started before RX was recording |
| every frame `FAIL(header)` | too far or too noisy; move closer, raise volume |
| ppm wildly different frame to frame | very low SNR; results at that distance are not usable |
