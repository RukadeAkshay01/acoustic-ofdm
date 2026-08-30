"""
Simulated acoustic channel.

The point of this module is to let us measure BER against a *known* channel,
which is impossible over a real speaker/mic pair.  It models the four effects
that actually break acoustic OFDM in practice:

  1. multipath  - the direct path plus wall/desk reflections, giving a
                  frequency-selective response that motivates equalisation;
  2. transducer colouration - a small laptop speaker rolls off badly below
                  ~3 kHz and a microphone adds its own tilt;
  3. additive noise - room noise / fan noise, set by a target SNR;
  4. sample-clock offset - two devices never share a crystal, so the receiver
                  samples at (1+eps)*fs.  This is what forces Phase 3's
                  per-symbol phase tracking to exist.
"""
import numpy as np
from scipy import signal

from .config import OFDMConfig, DEFAULT

SPEED_OF_SOUND = 343.0  # m/s at 20 degC


def room_impulse_response(cfg: OFDMConfig = DEFAULT, n_echo: int = 3,
                          max_delay_ms: float = 1.0, rng=None) -> np.ndarray:
    """Sparse multipath IR: unit direct path plus a few decaying reflections."""
    rng = rng or np.random.default_rng(7)
    max_d = int(max_delay_ms * 1e-3 * cfg.fs)
    h = np.zeros(max(max_d + 1, 2))
    h[0] = 1.0
    for _ in range(n_echo):
        d = int(rng.integers(1, max_d + 1))
        h[d] += rng.uniform(0.15, 0.5) * rng.choice([-1.0, 1.0])
    return h


def transducer_response(cfg: OFDMConfig = DEFAULT, ntaps: int = 65) -> np.ndarray:
    """Band-pass FIR standing in for the combined speaker + microphone."""
    return signal.firwin(ntaps, [2500 / (cfg.fs / 2), 14000 / (cfg.fs / 2)],
                         pass_zero=False)


def apply_channel(x: np.ndarray, snr_db: float, cfg: OFDMConfig = DEFAULT,
                  multipath: bool = True, transducer: bool = True,
                  clock_ppm: float = 0.0, delay: int = 0,
                  gain: float = 1.0, rng=None, h=None):
    """
    Push a transmit waveform through the simulated channel.

    `h` lets the caller supply a fixed impulse response.  BER-vs-SNR sweeps
    must do this: if the room is redrawn at every SNR point, each point sees a
    different set of spectral nulls and the resulting curve is non-monotonic
    for reasons that have nothing to do with SNR.

    Returns (rx, info) where info carries the ground-truth impulse response so
    that channel-estimation error can be scored later.
    """
    rng = rng or np.random.default_rng()
    y = np.asarray(x, dtype=float)

    if h is None:
        h = np.array([1.0])
        if multipath:
            h = np.convolve(h, room_impulse_response(cfg, rng=rng))
        if transducer:
            h = np.convolve(h, transducer_response(cfg))
    y = np.convolve(y, h)

    if clock_ppm:
        # receiver clock runs fast/slow -> resample onto its own grid
        n_out = int(round(len(y) / (1 + clock_ppm * 1e-6)))
        y = signal.resample(y, n_out)

    if delay:
        y = np.concatenate([np.zeros(delay), y])

    y = y * gain

    sig_p = np.mean(y[y != 0] ** 2) if np.any(y) else 1.0
    noise_p = sig_p / (10 ** (snr_db / 10.0))
    y = y + rng.normal(0.0, np.sqrt(noise_p), size=y.shape)

    return y, dict(h=h, snr_db=snr_db, noise_var=noise_p, delay=delay)


def true_channel_freq_response(h: np.ndarray, cfg: OFDMConfig = DEFAULT) -> np.ndarray:
    """Ground-truth H[k] on the occupied subcarriers, for scoring estimates."""
    H = np.fft.fft(h, cfg.nfft)
    return H[cfg.data_bins]
