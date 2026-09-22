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


# ---------------------------------------------------------------------------
# Probe-frame calibration: per-subcarrier SNR measured with the real modem
# ---------------------------------------------------------------------------
# The chirp measurement above sees the *linear* magnitude response at chirp
# resolution.  Over the air it rated several subcarriers as being within 8 dB
# of the best when the OFDM signal itself then found them 10-25 dB down
# (one bin at -28 dB returned BER 0.37, adjacent bins at the edge of the
# 6.5-9 kHz null were nearly as bad).  Whatever the mechanism - reverberation
# longer than the cyclic prefix, edge-of-null phase slope, transducer
# nonlinearity - the only measurement that captures all of it is the one the
# payload will actually experience.  So: transmit a frame of *known* bits,
# equalise it exactly as a payload would be, and score every subcarrier by the
# SNR of what came back.  This is how DSL modems train their bit-loading.

def probe_frame(cfg: OFDMConfig = DEFAULT, n_sym: int = 24, seed: int = 7):
    """A frame of known random bits used to measure per-subcarrier SNR."""
    bits = np.random.default_rng(seed).integers(0, 2, cfg.bits_per_symbol * n_sym)
    bits = bits.astype(np.int8)
    from .modem import modulate
    x, meta = modulate(bits, cfg)
    return x, bits, meta


def subcarrier_snr(rx: np.ndarray, bits: np.ndarray, meta: dict,
                   cfg: OFDMConfig = DEFAULT, skip_s: float = 0.25):
    """
    Per-subcarrier SNR (dB) of an equalised probe frame, on every occupied bin
    (pilots included - their transmitted values are known too).

    Returns (snr_db, report) or (None, reason) if the frame was not found.
    """
    from .receiver import demodulate
    r = demodulate(rx, len(bits), meta["n_sym"], cfg, mode="static",
                   skip_s=skip_s, tail_guard_s=0.15)
    if not r["ok"]:
        return None, r["reason"]
    tx = np.concatenate([meta["tx_grid"]])                 # (n_sym, n_used)
    eq = np.asarray(r["grid_eq"])[: tx.shape[0]]
    # MMSE leaves a per-bin gain bias; fit and remove it before scoring
    g = np.sum(eq * np.conj(tx), axis=0) / (np.sum(np.abs(tx) ** 2, axis=0) + 1e-18)
    err = eq - g[None, :] * tx
    sig = np.abs(g) ** 2 * np.mean(np.abs(tx) ** 2, axis=0)
    noise = np.mean(np.abs(err) ** 2, axis=0) + 1e-18
    snr_db = 10 * np.log10(sig / noise)
    return snr_db, dict(sync=r["sync"]["confidence"], H=r["H"], evm_db=r["evm_db"])


def select_by_snr(snr_db: np.ndarray, cfg: OFDMConfig = DEFAULT,
                  min_snr_db: float = 8.0, min_keep: int = 12):
    """
    Keep subcarriers whose measured SNR clears `min_snr_db`.

    8 dB is about raw BER 1e-2 for QPSK - comfortably inside what the
    repetition-3 soft combiner recovers - so this is a deliberately relaxed
    threshold that keeps throughput up.  `min_keep` guards against a bad
    probe capture calibrating the link into nothing.
    """
    bins = cfg.data_bins
    keep = bins[snr_db >= min_snr_db]
    if len(keep) < min_keep:
        keep = np.sort(bins[np.argsort(snr_db)[-min_keep:]])
    return keep


def calibrated_config_by_probe(rx: np.ndarray, bits: np.ndarray, meta: dict,
                               base: OFDMConfig = None, min_snr_db: float = 8.0,
                               skip_s: float = 0.25):
    """Return (config restricted to usable subcarriers, report) or (None, reason)."""
    import dataclasses
    base = base or DEFAULT
    snr_db, info = subcarrier_snr(rx, bits, meta, base, skip_s=skip_s)
    if snr_db is None:
        return None, info
    keep = select_by_snr(snr_db, base, min_snr_db=min_snr_db)
    report = dict(bins=base.data_bins, snr_db=snr_db, kept=keep,
                  min_snr_db=min_snr_db, kept_frac=len(keep) / len(base.data_bins),
                  freqs=keep * base.df, sync=info["sync"], evm_db=info["evm_db"])
    return dataclasses.replace(base, active_bins=tuple(int(k) for k in keep)), report
