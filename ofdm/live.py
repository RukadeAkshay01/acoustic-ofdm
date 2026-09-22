"""
Blind receive chain for the live demo and for two-device tests.

`receiver.demodulate` is told how many bits are coming, which is fine for a
scripted experiment.  Here the receiver knows nothing: it finds the chirp,
FFTs everything that follows, decodes the fixed-repetition header, and only
then knows how many payload symbols to keep.  Everything intermediate is
returned so the live page can draw the full pipeline.
"""
import numpy as np

from .config import OFDMConfig, DEFAULT
from . import modem, framing
from .receiver import bandpass, evm_db
from .sync import find_frame
from .equalizer import ChannelEstimator


def build_frame(text: bytes, name: str = "message.txt", repeat: int = 3,
                cfg: OFDMConfig = DEFAULT):
    """Bytes -> (waveform, bits, frame meta, modem meta)."""
    bits, fmeta = framing.encode_live(text, name, repeat)
    x, mmeta = modem.modulate(bits, cfg)
    return x, bits, fmeta, mmeta


def demodulate_blind(rx: np.ndarray, cfg: OFDMConfig = DEFAULT,
                     mode: str = "adaptive", noise_var: float = 1e-3,
                     skip_s: float = 0.0, max_seconds: float = 12.0,
                     tx_bits: np.ndarray = None, erase_db: float = 20.0):
    """
    Decode a recording containing one live frame of unknown length.

    `tx_bits`, if the transmitted bits happen to be known (loopback demo),
    is only used to report a BER - it never influences the decode.
    """
    rx = np.asarray(rx, dtype=float)
    rxf = bandpass(rx, cfg)
    fr = find_frame(rxf, cfg, skip_s=skip_s)
    if fr is None:
        return dict(ok=False, reason="no chirp found - nothing to synchronise to",
                    stage="sync", rx=rx)

    start = fr["data_start"]
    avail = (rxf.size - start) // cfg.sym_len
    n_total = int(min(avail, max_seconds * cfg.fs // cfg.sym_len))
    if n_total < 2:
        return dict(ok=False, reason="chirp found but recording ends before the payload",
                    stage="sync", rx=rx, sync=fr)

    seg = rxf[start:start + n_total * cfg.sym_len]
    grid = modem.time_to_grid(seg, n_total, cfg)

    est = ChannelEstimator(cfg, mode=mode, noise_var=noise_var)
    est.initial_estimate(grid[0])
    pay_pos = np.searchsorted(cfg.data_bins, cfg.payload_bins)

    # Erase subcarriers the reference symbol says are dead.  Over the air one
    # bin that the Stage-1 chirp rated "usable" measured -28 dB against its
    # neighbours during the frame and returned BER 0.37 - pure noise.  The
    # soft combiner treats a zero as an abstention, so the other copies decide.
    Hmag = np.abs(est.H)
    dead = Hmag < Hmag.max() * 10 ** (-erase_db / 20)
    keep = (~dead).astype(float)

    # The header decodes first, so the estimator only ever tracks across real
    # payload symbols and never wanders off into the trailing silence.
    hdr_syms = int(np.ceil(framing.HEADER_LEN * 8 * framing.HEADER_REPEAT / 2
                           / len(pay_pos)))
    eq_rows = [est.equalize_symbol(grid[i]) * keep
               for i in range(1, 1 + min(hdr_syms, n_total - 1))]
    dec = framing.decode_live(np.array(eq_rows)[:, pay_pos].ravel())
    if not dec["ok"]:
        # still return what we have so the page can show the constellation
        sym = np.array(eq_rows)[:, pay_pos]
        return dict(ok=False, reason="chirp found, but the header did not pass CRC",
                    stage="header", rx=rx, sync=fr, start=start, grid_raw=grid[:len(eq_rows)+1],
                    grid_eq=np.array(eq_rows), symbols=sym, H=est.H,
                    H_history=np.array(est.history), evm_db=evm_db(sym))

    need_syms = int(np.ceil(dec["used_syms"] / len(pay_pos)))
    for i in range(1 + len(eq_rows), 1 + min(need_syms, n_total - 1)):
        eq_rows.append(est.equalize_symbol(grid[i]) * keep)
    eq = np.array(eq_rows)
    sym = eq[:, pay_pos]
    dec = framing.decode_live(sym.ravel())

    out = dict(ok=dec["ok"], reason=dec["reason"], stage="done" if dec["ok"] else "payload",
               rx=rx, sync=fr, start=start, n_sym=len(eq_rows),
               grid_raw=grid[:len(eq_rows) + 1], grid_eq=eq, symbols=sym,
               H=est.H, H_history=np.array(est.history), cpe=np.array(est.cpe),
               evm_db=evm_db(sym[:, keep[pay_pos] > 0]), header=dec["header"], data=dec["data"],
               erased=int(dead.sum()),
               prr=dec["prr"], good=dec["good"], truncated=need_syms > n_total - 1)
    if tx_bits is not None:
        rxb = modem.qpsk_demodulate(sym.ravel())
        n = min(len(tx_bits), len(rxb))
        errs = int(np.sum(np.asarray(tx_bits[:n]) != rxb[:n]))
        out["raw_ber"] = errs / n if n else 1.0
        out["raw_errs"] = errs
        out["raw_bits"] = n
    return out
