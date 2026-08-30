"""
Real acoustic I/O over ALSA (aplay/arecord), so the project needs no extra
Python audio packages.  Playback and capture are started as subprocesses with
capture running slightly longer than playback to guarantee the whole frame is
inside the recording.
"""
import subprocess
import time
import wave
import numpy as np


def write_wav(path: str, x: np.ndarray, fs: int = 48000):
    pcm = np.clip(x, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())


def read_wav(path: str):
    with wave.open(path, "rb") as w:
        fs = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
        ch = w.getnchannels()
    x = np.frombuffer(raw, dtype="<i2").astype(float) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch)[:, 0]
    return x, fs


def loopback(x: np.ndarray, fs: int = 48000, pad_s: float = 0.6,
             play_dev: str = "default", rec_dev: str = "default",
             tmpdir: str = "/tmp"):
    """
    Play `x` through the speaker while recording the microphone.

    Returns the captured signal, or raises RuntimeError if ALSA is unavailable.
    """
    tx_path = f"{tmpdir}/aofdm_tx.wav"
    rx_path = f"{tmpdir}/aofdm_rx.wav"
    write_wav(tx_path, x, fs)

    dur = len(x) / fs + pad_s
    rec = subprocess.Popen(
        ["arecord", "-D", rec_dev, "-f", "S16_LE", "-r", str(fs), "-c", "1",
         "-d", str(int(np.ceil(dur))), rx_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(0.35)                       # let the capture device settle
    play = subprocess.Popen(["aplay", "-D", play_dev, tx_path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    play.wait()
    rec.wait()
    if rec.returncode != 0:
        raise RuntimeError(rec.stderr.read().decode()[:300])
    return read_wav(rx_path)


STARTUP_GUARD_S = 0.25   # ALSA capture start transient, measured at full scale


def _peak_of(x):
    return float(np.max(np.abs(x))) if len(x) else 0.0


def calibrate_level(probe, fs=48000, target_peak=0.45, tries=4,
                    start_amp=0.5, tmpdir="/tmp"):
    """
    Automatic transmit-level self-calibration (Stage 1).

    The right playback amplitude is device-specific: too quiet and the signal
    sits in the microphone's noise floor, too loud and the ADC clips, which is
    far worse because clipping is *nonlinear* - it spreads energy across all
    subcarriers and no linear equaliser can undo it.  We measured a 5.6 dB
    post-FFT SNR from a clipped capture whose waveform SNR looked fine.

    So before transmitting we send a short probe, look at the recorded peak,
    and scale the amplitude to land at `target_peak` of full scale.  Returns
    (amplitude, measured_peak, log).
    """
    amp = start_amp
    log = []
    for _ in range(tries):
        rx, _ = loopback(probe / (_peak_of(probe) or 1.0) * amp, fs, tmpdir=tmpdir)
        guard = int(STARTUP_GUARD_S * fs)
        pk = _peak_of(rx[guard:])
        log.append((amp, pk))
        if 0.7 * target_peak <= pk <= 1.25 * target_peak:
            break
        if pk < 1e-4:                      # nothing came back at all
            amp = min(amp * 4, 0.95)
            continue
        amp = float(np.clip(amp * target_peak / pk, 0.02, 0.95))
    return amp, log[-1][1], log


def find_capture_gain(probe, fs=48000, source=None, target_peak=0.5,
                      lo=10, hi=70, iters=5):
    """
    Binary-search the capture gain so the recorded peak lands near
    `target_peak` of full scale.

    On the test laptop the usable window was narrow and very steep - 30%
    capture volume gave a recorded peak of 0.07 while 50% clipped outright,
    because PulseAudio/PipeWire volume is roughly cubic in amplitude.  Guessing
    by hand wastes a play/record cycle each time, so we search.

    Returns (best_volume_percent, measured_peak, log).
    """
    import subprocess
    if source is None:
        out = subprocess.run(["pactl", "get-default-source"],
                             capture_output=True, text=True)
        source = out.stdout.strip()

    log = []
    best = (None, 0.0)
    for _ in range(iters):
        mid = (lo + hi) // 2
        subprocess.run(["pactl", "set-source-volume", source, f"{mid}%"],
                       capture_output=True)
        rx, _ = loopback(probe, fs)
        pk = _peak_of(rx[int(STARTUP_GUARD_S * fs):])
        log.append((mid, pk))
        if pk > 0.95:                       # clipping - back off
            hi = mid - 1
        else:
            if abs(pk - target_peak) < abs(best[1] - target_peak) or best[0] is None:
                best = (mid, pk)
            if pk < target_peak:
                lo = mid + 1
            else:
                hi = mid - 1
        if lo > hi:
            break
    if best[0] is not None:
        subprocess.run(["pactl", "set-source-volume", source, f"{best[0]}%"],
                       capture_output=True)
    return best[0], best[1], log
