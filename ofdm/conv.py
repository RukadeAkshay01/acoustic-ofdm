"""
Convolutional forward error correction with soft-decision Viterbi decoding.

Replaces repetition-3 as the "proper FEC" item from the midterm plan.

    code        : rate 1/2, constraint length K = 7, generators (171, 133) octal
                  - the NASA/802.11 standard code, free distance 10
    termination : K-1 = 6 zero tail bits, so the trellis ends in state 0
    interleaver : fixed pseudo-random permutation of the coded bits, known to
                  both ends

Why it beats repetition-3.  Repetition-3 has rate 1/3 and, even with soft
combining, only 10*log10(3) = 4.8 dB of gain.  The K=7 code has rate 1/2 - so
50 % more payload per second - and roughly 5-6 dB of coding gain at a BER of
1e-5 with soft decisions.

Why the interleaver matters.  The acoustic channel's errors are not random:
they cluster on the few subcarriers sitting in spectral nulls, and a Viterbi
decoder fails on bursts.  Spreading consecutive coded bits across different
subcarriers and OFDM symbols turns the null-subcarrier bursts into scattered
errors the decoder can correct.

Soft input.  The decoder takes the *equalised* QPSK symbol values rather than
hard bits.  After MMSE equalisation a symbol on a weak subcarrier is small, so
it contributes little to the path metric - the same reliability weighting the
live frame's soft repetition combiner relies on.
"""
import numpy as np

K = 7
G = (0o171, 0o133)
N_STATES = 1 << (K - 1)
TAIL = K - 1
RATE = 0.5
INTERLEAVE_SEED = 7331


def _parity(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.int64)
    p = np.zeros_like(x)
    while np.any(x):
        p ^= x & 1
        x = x >> 1
    return p


# Trellis tables.  The shift register holds the newest bit in bit K-1:
#     reg = (b << (K-1)) | state,   next_state = reg >> 1
_states = np.arange(N_STATES)
_OUT = np.zeros((N_STATES, 2, 2), dtype=np.int8)         # [state, input, output]
for _b in (0, 1):
    _reg = (_b << (K - 1)) | _states
    for _j, _g in enumerate(G):
        _OUT[:, _b, _j] = _parity(_reg & _g)

# For every next state ns, the input bit is its top bit and the two possible
# predecessors differ only in their lowest bit.
_NS = np.arange(N_STATES)
_IN_BIT = _NS >> (K - 2)
_PRED = np.stack([((_NS & (N_STATES // 2 - 1)) << 1) | x for x in (0, 1)], axis=1)
# Antipodal (+1/-1) expected outputs on each branch into ns from predecessor x
_BRANCH = np.stack([2 * _OUT[_PRED[:, x], _IN_BIT, :].astype(float) - 1
                    for x in (0, 1)], axis=1)            # [ns, x, output]


def encode(bits: np.ndarray) -> np.ndarray:
    """Rate-1/2 encode, appending the 6-bit zero tail."""
    bits = np.concatenate([np.asarray(bits, dtype=np.int8).ravel(),
                           np.zeros(TAIL, dtype=np.int8)])
    out = np.empty((bits.size, 2), dtype=np.int8)
    state = 0
    for i, b in enumerate(bits):
        out[i] = _OUT[state, b]
        state = ((int(b) << (K - 1)) | state) >> 1
    return out.ravel()


def viterbi_decode(soft: np.ndarray, n_info: int) -> np.ndarray:
    """
    Soft-decision Viterbi decoder.

    `soft` : one real value per coded bit, positive meaning "1".  Its scale
             is irrelevant; zeros are erasures and abstain.
    Returns the n_info decoded information bits.
    """
    n_steps = n_info + TAIL
    need = 2 * n_steps
    soft = np.asarray(soft, dtype=float).ravel()
    if soft.size < need:
        soft = np.concatenate([soft, np.zeros(need - soft.size)])
    soft = soft[:need].reshape(n_steps, 2)

    pm = np.full(N_STATES, -np.inf)
    pm[0] = 0.0
    decisions = np.empty((n_steps, N_STATES), dtype=np.int8)
    for t in range(n_steps):
        bm = _BRANCH @ soft[t]                          # [ns, x]
        cand = pm[_PRED] + bm
        x = np.argmax(cand, axis=1)
        decisions[t] = x
        pm = cand[_NS, x]
        pm -= pm.max()                                  # keep metrics bounded

    out = np.empty(n_steps, dtype=np.int8)
    ns = 0                                              # tail forces state 0
    for t in range(n_steps - 1, -1, -1):
        out[t] = ns >> (K - 2)
        ns = _PRED[ns, decisions[t, ns]]
    return out[:n_info]


def _perm(n: int) -> np.ndarray:
    return np.random.default_rng(INTERLEAVE_SEED).permutation(n)


def interleave(coded: np.ndarray) -> np.ndarray:
    coded = np.asarray(coded).ravel()
    return coded[_perm(coded.size)]


def deinterleave(values: np.ndarray, n_coded: int) -> np.ndarray:
    values = np.asarray(values).ravel()
    if values.size < n_coded:
        values = np.concatenate([values, np.zeros(n_coded - values.size,
                                                  dtype=values.dtype)])
    out = np.empty(n_coded, dtype=values.dtype)
    out[_perm(n_coded)] = values[:n_coded]
    return out


def coded_length(n_info: int) -> int:
    return 2 * (n_info + TAIL)


def fec_encode(bits: np.ndarray) -> np.ndarray:
    """Information bits -> interleaved coded bits ready for QPSK."""
    return interleave(encode(bits))


def fec_decode_soft(soft: np.ndarray, n_info: int) -> np.ndarray:
    """Soft values in transmit order -> decoded information bits."""
    return viterbi_decode(deinterleave(soft, coded_length(n_info)), n_info)


def symbols_to_soft(syms: np.ndarray) -> np.ndarray:
    """Equalised QPSK symbols -> per-bit soft values (bit0 = I, bit1 = Q)."""
    s = np.asarray(syms, dtype=complex).ravel()
    return np.stack([s.real, s.imag], axis=1).ravel()
