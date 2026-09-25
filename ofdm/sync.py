"""
Frame synchronisation (Phase 1, Member 3).

Acoustic packets arrive after an unknown propagation + buffering delay of
anywhere from a few ms to a few hundred ms, so the receiver has to find the
frame before it can do anything else.  We correlate against the known chirp:
a 30 ms 3-13 kHz sweep has a time-bandwidth product of ~300, so the matched
filter output is a sharp peak roughly 1/BW = 0.1 ms wide even at negative SNR.

After the coarse peak we back the symbol window *into* the cyclic prefix by
`cp_backoff` samples.  Any multipath delay then lands inside the ISI-free part
of the CP and shows up only as a phase ramp across subcarriers, which the
equaliser absorbs.  The backoff has to be small, though: a window that starts
D samples early makes the apparent channel rotate 2*pi*D/N radians per
subcarrier, and the pilot-based estimator can only track that ramp while it
stays under pi radians *between adjacent pilots*, i.e.

        D < N / (2 * pilot_spacing) = 256 / 8 = 32 samples.

A backoff of ncp//2 = 32 sits exactly on that aliasing limit and destroys the
interpolated estimate, so the default is a much smaller 8 samples.
"""
import numpy as np
from scipy import signal

from .config import OFDMConfig, DEFAULT
from .modem import sync_chirp


def matched_filter(rx: np.ndarray, cfg: OFDMConfig = DEFAULT) -> np.ndarray:
    """Correlate the received stream against the reference chirp."""
    ref = sync_chirp(cfg)
    corr = signal.correlate(rx, ref, mode="valid")
    return np.abs(signal.hilbert(corr))     # envelope, so timing is carrier-blind


def find_frame(rx: np.ndarray, cfg: OFDMConfig = DEFAULT,
               threshold: float = 6.0, cp_backoff: int = None,
               skip_s: float = 0.0, tail_guard_s: float = 0.0,
               need_samples: int = 0):
    """
    Locate the first frame in `rx`.

    `skip_s` blanks the first few hundred ms of the recording.  ALSA capture
    devices emit a large clipped transient when they start (we measured a
    full-scale 10 ms click, ~30 dB above the wanted signal), and the matched
    filter will happily lock onto that instead of the chirp.

    Returns
    -------
    dict with the correlation envelope, the detected peak, the derived start of
    the first OFDM symbol, and a detection-confidence figure (peak / median),
    or None if nothing crossed the threshold.
    """
    if cp_backoff is None:
        cp_backoff = 8

    env = matched_filter(rx, cfg)
    if env.size == 0:
        return None

    skip = min(int(skip_s * cfg.fs), max(env.size - 1, 0))
    stop = env.size - int(tail_guard_s * cfg.fs)
    if need_samples:
        stop = min(stop, env.size - need_samples)
    stop = max(stop, skip + 1)

    search = env[skip:stop]
    if search.size == 0:
        return None
    # 20th percentile rather than the median: once the search window is
    # narrowed to a region that is mostly occupied by the burst, the median is
    # itself signal and the confidence ratio collapses below threshold.
    noise_floor = np.percentile(search, 20) + 1e-12
    peak_idx = skip + int(np.argmax(search))
    confidence = env[peak_idx] / noise_floor
    if confidence < threshold:
        return None

    chirp_len = int(round(cfg.chirp_dur * cfg.fs))
    # 'valid' correlation index i means the chirp spans rx[i : i+chirp_len]
    chirp_end = peak_idx + chirp_len
    data_start = chirp_end + cfg.guard_symbols * cfg.sym_len - cp_backoff

    return dict(env=env, peak=peak_idx, chirp_end=chirp_end,
                data_start=int(data_start), confidence=float(confidence),
                noise_floor=float(noise_floor))


def estimate_impulse_response(rx: np.ndarray, cfg: OFDMConfig = DEFAULT,
                              length: int = None) -> np.ndarray:
    """
    Stage-1 calibration: the chirp is a known wideband probe, so the matched
    filter output around the peak *is* an estimate of the channel impulse
    response (band-limited to the chirp's sweep range).
    """
    if length is None:
        length = cfg.ncp
    ref = sync_chirp(cfg)
    corr = signal.correlate(rx, ref, mode="valid")
    peak = int(np.argmax(np.abs(signal.hilbert(corr))))
    seg = corr[peak: peak + length]
    if seg.size < length:
        seg = np.concatenate([seg, np.zeros(length - seg.size)])
    return seg / (np.max(np.abs(seg)) or 1.0)


def estimate_clock_ppm(grid_raw: np.ndarray, cfg: OFDMConfig = DEFAULT):
    """
    Sampling-clock offset between transmitter and receiver, in ppm.

    A clock offset eps makes the FFT window slide by eps*L samples per OFDM
    symbol (L = symbol length with CP), which rotates subcarrier k by an extra
    2*pi*k*eps*L/N every symbol.  Measured at the pilots, the phase *slope*
    across frequency therefore grows linearly with time.

    For each pair of neighbouring pilots (k_i, k_i+1) the product
        Z_n = P_n[i+1] conj(P_n[i])     (P = received pilot / known pilot)
    cancels the common phase and leaves the channel's fixed phase difference
    plus 2*pi*dk*eps*L*n/N.  Unwrapping angle(Z_n) along n and fitting a line
    gives the drift rate; a straight-line fit over the whole frame averages
    noise down as N^-1.5, far better than differencing adjacent symbols.
    Pairs are weighted by their mean |Z| so pilots in spectral nulls count
    for little.

    `grid_raw` is the un-equalised resource grid (row 0 is the reference
    symbol and is skipped).  Returns (ppm, n_symbols) or (nan, 0) if the frame
    is too short.  Positive ppm = the receiver's sample clock runs slow
    relative to the transmitter's (the channel.apply_channel convention).
    """
    from .modem import pilot_values
    g = np.asarray(grid_raw)
    if g.ndim != 2 or g.shape[0] < 6:
        return float("nan"), 0
    pil_pos = np.searchsorted(cfg.data_bins, cfg.pilot_bins)
    P = g[1:, pil_pos] / pilot_values(cfg)[None, :]
    Z = P[:, 1:] * np.conj(P[:, :-1])                 # [symbol, pair]
    n = np.arange(Z.shape[0], dtype=float)
    dk = np.diff(cfg.pilot_bins).astype(float)
    rates, weights = [], []
    for i in range(Z.shape[1]):
        w = float(np.mean(np.abs(Z[:, i])))
        if w <= 0:
            continue
        ph = np.unwrap(np.angle(Z[:, i]))
        rates.append(np.polyfit(n, ph, 1)[0] / dk[i])  # rad / symbol / bin
        weights.append(w)
    if not weights:
        return float("nan"), 0
    rate = float(np.average(rates, weights=weights))
    eps = rate / (2 * np.pi * cfg.sym_len / cfg.nfft)
    return float(eps * 1e6), int(P.shape[0])
