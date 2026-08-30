"""
Stage 1 - automatic self-calibration.

Measuring a real laptop speaker/microphone pair with the sync chirp gave a
43 dB spread across the 4-12 kHz band: strong around 4-5 kHz and 10-11 kHz,
but with nulls 35-43 dB deep between 6.5 and 9 kHz.  Uncoded QPSK on a
subcarrier sitting in a 40 dB null is a coin flip, and with roughly a third of
the subcarriers dead the link BER floors at ~0.3 no matter how good the
equaliser is.  No amount of equalisation fixes this - a zero-forcing equaliser
just amplifies the noise in the null by the same 40 dB.

So the receiver measures the response once with a chirp, decides which
subcarriers are actually usable, and both ends restrict themselves to that
set.  This is the "automatic self-calibration" of the project title, and it is
the acoustic equivalent of DSL bit-loading.
"""
import numpy as np
from scipy import signal

from .config import OFDMConfig, DEFAULT
from .modem import sync_chirp


def measure_response(rx: np.ndarray, cfg: OFDMConfig = DEFAULT,
                     skip_s: float = 0.25, ir_len: int = 600):
    """
    Estimate the end-to-end magnitude response from a recorded chirp.

    Returns (freqs, magnitude_db, impulse_response).
    """
    ref = sync_chirp(cfg)
    skip = min(int(skip_s * cfg.fs), max(len(rx) - 1, 0))
    corr = signal.correlate(rx[skip:], ref, mode="valid")
    pk = int(np.argmax(np.abs(signal.hilbert(corr))))
    lo = max(pk - 10, 0)
    h = corr[lo:lo + ir_len]
    h = h / (np.max(np.abs(h)) or 1.0)

    H = np.fft.rfft(h, cfg.nfft * 8)
    f = np.fft.rfftfreq(cfg.nfft * 8, 1.0 / cfg.fs)
    mag_db = 20 * np.log10(np.abs(H) + 1e-12)
    return f, mag_db, h


def select_subcarriers(rx: np.ndarray, cfg: OFDMConfig = DEFAULT,
                       backoff_db: float = 15.0, min_keep: int = 12,
                       skip_s: float = 0.25):
    """
    Choose the usable subcarriers.

    A bin is kept if its measured response is within `backoff_db` of the best
    bin in the band.  `min_keep` guarantees we never calibrate ourselves down
    to an unusably narrow link if the measurement was bad.

    Returns (kept_bins, report_dict).
    """
    f, mag_db, h = measure_response(rx, cfg, skip_s=skip_s)

    bins = np.arange(int(np.ceil(cfg.f_low / cfg.df)),
                     min(int(np.floor(cfg.f_high / cfg.df)), cfg.nfft // 2 - 1) + 1)
    bin_db = np.interp(bins * cfg.df, f, mag_db)
    ref_db = bin_db.max()
    keep = bins[bin_db >= ref_db - backoff_db]

    if len(keep) < min_keep:                     # fall back to the best N bins
        keep = bins[np.argsort(bin_db)[-min_keep:]]
        keep = np.sort(keep)

    report = dict(
        bins=bins, bin_db=bin_db, kept=keep, ref_db=float(ref_db),
        backoff_db=backoff_db,
        dynamic_range_db=float(bin_db.max() - bin_db.min()),
        kept_frac=len(keep) / len(bins),
        freqs=(keep * cfg.df),
        ir=h, resp_f=f, resp_db=mag_db,
    )
    return keep, report


def calibrated_config(rx: np.ndarray, base: OFDMConfig = None,
                      backoff_db: float = 15.0, skip_s: float = 0.25):
    """Return a copy of `base` restricted to the subcarriers worth using."""
    import dataclasses
    base = base or DEFAULT
    keep, report = select_subcarriers(rx, base, backoff_db=backoff_db, skip_s=skip_s)
    return dataclasses.replace(base, active_bins=tuple(int(k) for k in keep)), report
