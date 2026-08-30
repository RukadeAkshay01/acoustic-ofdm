"""
OFDM modulation / demodulation engine  (Phase 1, Member 1).

Real-valued baseband-at-passband generation: instead of building a complex
baseband signal and mixing it up to an audio carrier, we place the QPSK
symbols directly on FFT bins 22..64 of a 256-point IFFT and enforce Hermitian
symmetry (X[N-k] = conj(X[k])).  The IFFT output is then real-valued and
already sits in the 4-12 kHz audio band, so it can be written straight to a
WAV file.  This removes the up/down-conversion stage entirely and with it a
whole class of carrier-phase bugs.
"""
import numpy as np

from .config import OFDMConfig, DEFAULT

# ---------------------------------------------------------------------------
# QPSK constellation, Gray-coded
#   bits (b0,b1) -> (2*b0-1 + j(2*b1-1)) / sqrt(2)
# ---------------------------------------------------------------------------
QPSK_SCALE = 1.0 / np.sqrt(2.0)


def qpsk_modulate(bits: np.ndarray) -> np.ndarray:
    """Map a bit vector (even length) onto Gray-coded QPSK symbols."""
    bits = np.asarray(bits, dtype=np.int8).ravel()
    if bits.size % 2:
        raise ValueError("QPSK needs an even number of bits")
    b = bits.reshape(-1, 2)
    return (2 * b[:, 0] - 1 + 1j * (2 * b[:, 1] - 1)) * QPSK_SCALE


def qpsk_demodulate(syms: np.ndarray) -> np.ndarray:
    """Hard-decision QPSK demapper (inverse of :func:`qpsk_modulate`)."""
    syms = np.asarray(syms).ravel()
    out = np.empty((syms.size, 2), dtype=np.int8)
    out[:, 0] = (syms.real > 0).astype(np.int8)
    out[:, 1] = (syms.imag > 0).astype(np.int8)
    return out.ravel()


def qpsk_soft_llr(syms: np.ndarray, noise_var: float = 1.0) -> np.ndarray:
    """Soft LLRs, used by the BER analysis to show the decision margin."""
    syms = np.asarray(syms).ravel()
    llr = np.empty((syms.size, 2))
    llr[:, 0] = 2 * np.sqrt(2) * syms.real / max(noise_var, 1e-12)
    llr[:, 1] = 2 * np.sqrt(2) * syms.imag / max(noise_var, 1e-12)
    return llr.ravel()


# ---------------------------------------------------------------------------
# Pilot sequence
# ---------------------------------------------------------------------------
def pilot_values(cfg: OFDMConfig = DEFAULT, seed: int = 1234) -> np.ndarray:
    """
    Deterministic BPSK pilot sequence, known to both ends.

    A pseudo-random +-1 pattern is used rather than an all-ones pattern so the
    preamble has a low peak-to-average power ratio and does not put a loud
    impulse through the speaker.
    """
    rng = np.random.default_rng(seed)
    return (2 * rng.integers(0, 2, size=len(cfg.pilot_bins)) - 1).astype(complex)


def reference_symbol(cfg: OFDMConfig = DEFAULT, seed: int = 4321) -> np.ndarray:
    """
    Fully-known OFDM symbol used for one-shot channel estimation (Phase 2).
    Returns the frequency-domain values on *all* occupied subcarriers.
    """
    rng = np.random.default_rng(seed)
    b = rng.integers(0, 2, size=(len(cfg.data_bins), 2))
    return (2 * b[:, 0] - 1 + 1j * (2 * b[:, 1] - 1)) * QPSK_SCALE


# ---------------------------------------------------------------------------
# Frequency-domain frame assembly
# ---------------------------------------------------------------------------
def build_grid(bits: np.ndarray, cfg: OFDMConfig = DEFAULT):
    """
    Lay bits out on a (n_symbols x n_used) resource grid with pilots inserted.

    Returns
    -------
    grid : complex array, shape (n_symbols, len(cfg.data_bins))
    n_pad : number of zero bits appended to fill the last symbol
    """
    bits = np.asarray(bits, dtype=np.int8).ravel()
    bps = cfg.bits_per_symbol
    n_pad = (-bits.size) % bps
    if n_pad:
        bits = np.concatenate([bits, np.zeros(n_pad, dtype=np.int8)])
    n_sym = bits.size // bps

    used = cfg.data_bins
    pil_pos = np.searchsorted(used, cfg.pilot_bins)
    pay_pos = np.searchsorted(used, cfg.payload_bins)
    pv = pilot_values(cfg)

    grid = np.zeros((n_sym, used.size), dtype=complex)
    payload = qpsk_modulate(bits).reshape(n_sym, len(pay_pos))
    grid[:, pay_pos] = payload
    grid[:, pil_pos] = pv                       # same pilots in every symbol
    return grid, n_pad


def grid_to_time(grid: np.ndarray, cfg: OFDMConfig = DEFAULT) -> np.ndarray:
    """Hermitian IFFT + cyclic prefix for every row of the resource grid."""
    n_sym = grid.shape[0]
    used = cfg.data_bins
    spec = np.zeros((n_sym, cfg.nfft), dtype=complex)
    spec[:, used] = grid
    spec[:, cfg.nfft - used] = np.conj(grid)    # enforce a real time signal
    x = np.fft.ifft(spec, axis=1).real * cfg.nfft
    with_cp = np.concatenate([x[:, -cfg.ncp:], x], axis=1)
    return with_cp.ravel()


def time_to_grid(rx: np.ndarray, n_sym: int, cfg: OFDMConfig = DEFAULT) -> np.ndarray:
    """Strip cyclic prefixes and FFT back to the resource grid."""
    need = n_sym * cfg.sym_len
    if rx.size < need:
        rx = np.concatenate([rx, np.zeros(need - rx.size)])
    blocks = rx[:need].reshape(n_sym, cfg.sym_len)[:, cfg.ncp:]
    spec = np.fft.fft(blocks, axis=1) / cfg.nfft
    return spec[:, cfg.data_bins]


# ---------------------------------------------------------------------------
# Preamble
# ---------------------------------------------------------------------------
def sync_chirp(cfg: OFDMConfig = DEFAULT) -> np.ndarray:
    """
    Linear chirp used for frame synchronisation and for the Stage-1 impulse
    response measurement.  A short raised-cosine taper suppresses the clicks
    that a hard-edged chirp would otherwise produce on a small speaker.
    """
    n = int(round(cfg.chirp_dur * cfg.fs))
    t = np.arange(n) / cfg.fs
    k = (cfg.chirp_f1 - cfg.chirp_f0) / cfg.chirp_dur
    s = np.sin(2 * np.pi * (cfg.chirp_f0 * t + 0.5 * k * t ** 2))
    taper = int(0.1 * n)
    w = np.ones(n)
    ramp = 0.5 * (1 - np.cos(np.pi * np.arange(taper) / taper))
    w[:taper] = ramp
    w[-taper:] = ramp[::-1]
    return s * w


def reduce_papr(x: np.ndarray, cfg: OFDMConfig, target_db: float,
                iterations: int = 3) -> np.ndarray:
    """
    Iterative clipping and filtering.

    Hard-clipping alone would splatter energy outside the 4-12 kHz band, which
    is both audible and useless, so after each clip we FFT the block, zero
    every bin outside the occupied band, and transform back.  Clipping regrows
    a little each time, hence the iteration.  Three passes takes a 9.2 dB PAPR
    to roughly 5.5 dB, which is ~4 dB more average transmit power for the same
    speaker peak, at a cost of about -20 dB of in-band distortion.
    """
    if target_db <= 0:
        return x
    y = x.copy()
    keep = np.zeros(len(y) // 2 + 1, dtype=bool)
    f = np.fft.rfftfreq(len(y), 1.0 / cfg.fs)
    keep[(f >= cfg.f_low - cfg.df) & (f <= cfg.f_high + cfg.df)] = True
    for _ in range(iterations):
        rms = np.sqrt(np.mean(y ** 2)) or 1.0
        limit = rms * 10 ** (target_db / 20.0)
        y = np.clip(y, -limit, limit)
        Y = np.fft.rfft(y)
        Y[~keep] = 0
        y = np.fft.irfft(Y, len(y))
    return y


def papr_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.max(np.abs(x)) / (np.sqrt(np.mean(x ** 2)) + 1e-18)))


def modulate(bits: np.ndarray, cfg: OFDMConfig = DEFAULT, with_reference: bool = True):
    """
    Full transmit chain: bits -> analogue-ready waveform.

    Frame layout
        [lead silence][chirp][guard][reference symbol][payload symbols][tail]

    The reference symbol is what Phase 2 uses for its one-shot channel
    estimate; Phase 3 keeps refining that estimate from the pilots carried in
    the payload symbols.
    """
    grid, n_pad = build_grid(bits, cfg)

    chirp = sync_chirp(cfg)                     # peak is already ~1.0
    body = [grid_to_time(reference_symbol(cfg)[None, :], cfg)] if with_reference else []
    n_ref = len(body)
    body.append(grid_to_time(grid, cfg))
    ofdm = np.concatenate(body)
    papr_before = papr_db(ofdm)
    ofdm = reduce_papr(ofdm, cfg, cfg.papr_clip_db)

    # Normalise the chirp and the OFDM block *separately*.  A 64-subcarrier
    # OFDM symbol has a peak-to-average ratio of ~10 dB, so scaling the whole
    # frame by one global peak would leave the chirp far too quiet to detect
    # over a real acoustic channel.
    ofdm_scale = cfg.amplitude / (np.max(np.abs(ofdm)) or 1.0)
    ofdm = ofdm * ofdm_scale
    chirp = chirp * cfg.amplitude / (np.max(np.abs(chirp)) or 1.0)

    lead = np.zeros(int(cfg.lead_silence * cfg.fs))
    guard = np.zeros(cfg.guard_symbols * cfg.sym_len)
    tail = np.zeros(int(cfg.tail_silence * cfg.fs))
    x = np.concatenate([lead, chirp, guard, ofdm, tail])

    meta = dict(
        n_sym=grid.shape[0], n_ref=n_ref, n_pad=n_pad, n_bits=int(np.size(bits)),
        data_start=len(lead) + len(chirp) + len(guard),
        scale=ofdm_scale, tx_grid=grid,
        papr_before_db=papr_before, papr_after_db=papr_db(ofdm),
    )
    return x, meta
