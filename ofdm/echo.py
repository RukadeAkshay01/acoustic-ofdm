"""
Stage 4 - echo-based distance estimation (Phase 3, optional module).

Same chirp, same matched filter as the synchroniser: transmit a sweep, record,
correlate.  The direct speaker->mic leakage arrives first and is enormous; the
reflection off a wall or an object arrives later and is 20-40 dB weaker, so the
job is to find the second peak, not the largest one.

    distance = c * (t_echo - t_direct) / 2       (out and back)
"""
import numpy as np
from scipy import signal

from .config import OFDMConfig, DEFAULT
from .modem import sync_chirp

SPEED_OF_SOUND = 343.0


def correlate_echo(rx: np.ndarray, cfg: OFDMConfig = DEFAULT) -> np.ndarray:
    ref = sync_chirp(cfg)
    return np.abs(signal.hilbert(signal.correlate(rx, ref, mode="valid")))


def estimate_distance(rx: np.ndarray, cfg: OFDMConfig = DEFAULT,
                      min_range_m: float = 0.25, max_range_m: float = 6.0,
                      prominence: float = 4.0):
    """
    Find the direct path then the strongest echo after it.

    `min_range_m` blanks out the region right after the direct arrival, where
    the chirp's own correlation sidelobes and the speaker's ringing dominate.
    """
    env = correlate_echo(rx, cfg)
    direct = int(np.argmax(env))

    guard = int(2 * min_range_m / SPEED_OF_SOUND * cfg.fs)
    far = int(2 * max_range_m / SPEED_OF_SOUND * cfg.fs)
    lo, hi = direct + guard, min(direct + far, len(env))
    if lo >= hi:
        return dict(ok=False, reason="search window empty", env=env, direct=direct)

    window = env[lo:hi]
    floor = np.median(env[lo:hi]) + 1e-12
    pk = int(np.argmax(window))
    snr = window[pk] / floor
    if snr < prominence:
        return dict(ok=False, reason=f"no echo above threshold (peak/floor={snr:.1f})",
                    env=env, direct=direct, snr=float(snr))

    echo = lo + pk
    dt = (echo - direct) / cfg.fs
    return dict(ok=True, env=env, direct=direct, echo=echo, delay_s=dt,
                distance_m=SPEED_OF_SOUND * dt / 2.0, snr=float(snr),
                search=(lo, hi))


def simulate_echo(distance_m: float, cfg: OFDMConfig = DEFAULT,
                  snr_db: float = 20.0, echo_atten_db: float = 25.0, rng=None):
    """Synthesise a recording containing a direct path plus one reflection."""
    rng = rng or np.random.default_rng(0)
    c = sync_chirp(cfg)
    delay = int(round(2 * distance_m / SPEED_OF_SOUND * cfg.fs))
    n = int(0.1 * cfg.fs) + delay + len(c) + int(0.05 * cfg.fs)
    y = np.zeros(n)
    d0 = int(0.1 * cfg.fs)
    y[d0:d0 + len(c)] += c
    a = 10 ** (-echo_atten_db / 20.0)
    y[d0 + delay:d0 + delay + len(c)] += a * c
    p = np.mean(y ** 2)
    y += rng.normal(0, np.sqrt(p / 10 ** (snr_db / 10)), n)
    return y
