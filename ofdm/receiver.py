"""
Receiver chain: synchronise -> FFT -> estimate -> equalise -> demap.

Ties together sync.py (Member 3), modem.py (Member 1) and equalizer.py
(Member 2) and returns every intermediate signal so the web dashboard can
plot the full pipeline.
"""
import numpy as np
from scipy import signal as _sig

from .config import OFDMConfig, DEFAULT
from .modem import time_to_grid, qpsk_demodulate
from .sync import find_frame, estimate_impulse_response
from .equalizer import ChannelEstimator


def bandpass(rx: np.ndarray, cfg: OFDMConfig = DEFAULT, order: int = 4,
             margin: float = 1.15) -> np.ndarray:
    """
    Receiver input filter.

    Measured on a real laptop capture, the 0-1 kHz band (fan, mains hum,
    desk rumble) sat 21 dB *above* the 4-12 kHz band carrying the signal.
    None of that energy is useful and all of it eats headroom, so the first
    thing the receiver does is throw it away.

    filtfilt is used rather than lfilter because it is zero-phase: an ordinary
    IIR filter would add its own group delay and shift the frame timing that
    the synchroniser is about to measure.
    """
    nyq = cfg.fs / 2
    lo = max(cfg.f_low / margin, 50.0) / nyq
    hi = min(cfg.f_high * margin, nyq * 0.98) / nyq
    b, a = _sig.butter(order, [lo, hi], btype="band")
    return _sig.filtfilt(b, a, np.asarray(rx, dtype=float))


def evm_db(sym: np.ndarray) -> float:
    """Error-vector magnitude against the nearest QPSK point, in dB."""
    s = np.asarray(sym).ravel()
    if s.size == 0:
        return float("nan")
    gain = np.mean(np.abs(s)) / (1 / np.sqrt(2)) or 1.0
    s = s / gain
    ideal = (np.sign(s.real) + 1j * np.sign(s.imag)) / np.sqrt(2)
    return 10 * np.log10(np.mean(np.abs(s - ideal) ** 2) /
                         np.mean(np.abs(ideal) ** 2) + 1e-18)


def demodulate(rx: np.ndarray, n_bits: int, n_sym: int, cfg: OFDMConfig = DEFAULT,
               mode: str = "adaptive", has_reference: bool = True,
               noise_var: float = 1e-3, mu: float = 0.15,
               skip_s: float = 0.0, filter_input: bool = True,
               tail_guard_s: float = 0.0):
    """
    Full receive chain.

    Parameters
    ----------
    rx        : recorded samples
    n_bits    : number of payload bits expected (for trimming the pad)
    n_sym     : number of payload OFDM symbols
    mode      : 'none' | 'static' | 'adaptive'   (see equalizer.py)

    Returns a dict of everything downstream stages and the dashboard need.
    """
    if filter_input:
        rx = bandpass(rx, cfg)
    n_total_pre = (n_sym + (1 if has_reference else 0)) * cfg.sym_len
    fr = find_frame(rx, cfg, skip_s=skip_s, tail_guard_s=tail_guard_s,
                    need_samples=n_total_pre)
    if fr is None:
        return dict(ok=False, reason="no frame detected", sync=None)

    start = fr["data_start"]
    n_total = n_sym + (1 if has_reference else 0)
    seg = rx[start:start + n_total * cfg.sym_len]
    if seg.size < n_total * cfg.sym_len:
        seg = np.concatenate([seg, np.zeros(n_total * cfg.sym_len - seg.size)])

    grid = time_to_grid(seg, n_total, cfg)

    est = ChannelEstimator(cfg, mode=mode, noise_var=noise_var, mu=mu)
    if has_reference:
        est.initial_estimate(grid[0])
        payload_grid = grid[1:]
    else:
        payload_grid = grid

    eq = np.array([est.equalize_symbol(row) for row in payload_grid])

    pay_pos = np.searchsorted(cfg.data_bins, cfg.payload_bins)
    sym = eq[:, pay_pos]
    bits = qpsk_demodulate(sym.ravel())[:n_bits]

    return dict(
        ok=True, bits=bits, sync=fr, grid_raw=grid, grid_eq=eq,
        symbols=sym, estimator=est, H=est.H, H_history=np.array(est.history),
        cpe=np.array(est.cpe), evm_db=evm_db(sym),
        ir=estimate_impulse_response(rx, cfg), start=start, segment=seg,
    )


def ber(tx_bits: np.ndarray, rx_bits: np.ndarray):
    """Bit error rate over the overlapping portion of the two bit vectors."""
    n = min(len(tx_bits), len(rx_bits))
    if n == 0:
        return 1.0, 0, 0
    errs = int(np.sum(np.asarray(tx_bits[:n]) != np.asarray(rx_bits[:n])))
    return errs / n, errs, n
