"""
File <-> bitstream packetisation with CRC (Member 3).

Wraps the raw modem in something that can actually carry a file:

    header (32 bytes, CRC-protected) + payload packets (each CRC-protected)

The header repeats the filename and length so the receiver knows how much to
keep; per-packet CRCs give the packet-recovery-rate metric the proposal asks
for, and let us report *which* parts of a file survived rather than just a BER.
"""
import struct
import zlib
import numpy as np

MAGIC = b"AOFD"
# A repetition factor of 0 is never sent as such (encode_live clamps to >= 1),
# so the live frame uses it to mean "payload is convolutionally coded".
CONV_MARK = 0
HEADER_LEN = 32
PACKET_PAYLOAD = 64          # bytes of file data per packet


def bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8)).astype(np.int8)


def bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = np.asarray(bits, dtype=np.uint8).ravel()
    bits = bits[: len(bits) // 8 * 8]
    return np.packbits(bits).tobytes()


def build_header(name: str, nbytes: int, repeat: int = 1) -> bytes:
    """
    [magic:4][nbytes:4][repeat:1][name:18][crc:4][pad:1] = 32 bytes.

    `repeat` is the repetition factor of the payload that follows.  Carrying it
    inside the CRC-protected header is what lets a receiver that knows nothing
    about the transmission (a second device, or the live demo) work out how
    many bits to expect from the sound alone.
    """
    nm = name.encode()[:18].ljust(18, b"\0")
    body = MAGIC + struct.pack("<IB", nbytes, repeat & 0xFF) + nm   # 4+4+1+18 = 27
    return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF) + b"\0"


def parse_header(data: bytes):
    if len(data) < HEADER_LEN or data[:4] != MAGIC:
        return None
    body = data[:27]
    crc = struct.unpack("<I", data[27:31])[0]
    if (zlib.crc32(body) & 0xFFFFFFFF) != crc:
        return None
    nbytes, repeat = struct.unpack("<IB", data[4:9])
    name = data[9:27].rstrip(b"\0").decode(errors="replace")
    code = "conv" if repeat == CONV_MARK else "rep"
    return dict(name=name, nbytes=nbytes, repeat=max(repeat, 1), code=code)


def packetize(data: bytes) -> bytes:
    """
    Split payload into CRC-tagged packets: [seq:2][len:2][data:64][crc:4].

    Every packet is padded to the same 72-byte length, including the last one.
    A variable-length final packet would shift the CRC field and break the
    receiver's fixed-stride parsing, which is exactly the bug this padding
    exists to avoid.
    """
    out = bytearray()
    for i in range(0, len(data), PACKET_PAYLOAD):
        chunk = data[i:i + PACKET_PAYLOAD]
        body = (struct.pack("<HH", i // PACKET_PAYLOAD, len(chunk))
                + chunk.ljust(PACKET_PAYLOAD, b"\0"))
        out += body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)
    return bytes(out)


def depacketize(data: bytes, n_packets: int):
    """Recover packets, reporting which ones passed CRC."""
    chunks, good = {}, []
    pos = 0
    for _ in range(n_packets):
        if pos + 8 > len(data):
            break
        seq, ln = struct.unpack("<HH", data[pos:pos + 4])
        ln = min(ln, PACKET_PAYLOAD)
        body = data[pos:pos + 4 + PACKET_PAYLOAD]     # CRC covers the padding
        crc_off = pos + 4 + PACKET_PAYLOAD
        if crc_off + 4 > len(data):
            break
        crc = struct.unpack("<I", data[crc_off:crc_off + 4])[0]
        ok = (zlib.crc32(body) & 0xFFFFFFFF) == crc
        good.append(ok)
        if ok:
            chunks[seq] = body[4:4 + ln]        # strip padding back off
        pos = crc_off + 4
    recovered = b"".join(chunks[k] for k in sorted(chunks))
    prr = float(np.mean(good)) if good else 0.0
    return recovered, prr, good


def n_packets_for(nbytes: int) -> int:
    return (nbytes + PACKET_PAYLOAD - 1) // PACKET_PAYLOAD


def encode_file(data: bytes, name: str = "file.bin", repeat: int = 1):
    """File bytes -> transmit bit vector."""
    frame = build_header(name, len(data), repeat) + packetize(data)
    n_packets = (len(data) + PACKET_PAYLOAD - 1) // PACKET_PAYLOAD
    return bytes_to_bits(frame), dict(n_packets=n_packets, nbytes=len(data),
                                      frame_len=len(frame))


def decode_file(bits: np.ndarray, meta: dict):
    """Received bit vector -> (file bytes, packet recovery rate, header)."""
    raw = bits_to_bytes(bits)
    hdr = parse_header(raw[:HEADER_LEN])
    body = raw[HEADER_LEN:]
    data, prr, good = depacketize(body, meta["n_packets"])
    if hdr:
        data = data[:hdr["nbytes"]]
    return data, prr, hdr, good


# ---------------------------------------------------------------------------
# Forward error correction: interleaved repetition-3 with majority vote
# ---------------------------------------------------------------------------
# Over the real acoustic channel we measured an uncoded BER of 8.3e-3, which
# is only 26 bit errors in 3136 bits - but a single bit error destroys a whole
# 72-byte packet, so only 1 packet in 5 survived.  Repetition-3 with majority
# voting turns a raw BER p into roughly 3p^2, i.e. 8.3e-3 -> ~2e-4, at the cost
# of a third of the throughput.
#
# The three copies must not land on the same subcarrier: the acoustic channel's
# errors are strongly clustered on the subcarriers that sit in spectral nulls,
# so three copies in a row would simply all be wrong together.  Writing the
# copies a full block apart interleaves them across different subcarriers and
# different OFDM symbols, which is what makes the majority vote independent.

REPEAT = 3


def fec_encode(bits: np.ndarray, repeat: int = REPEAT) -> np.ndarray:
    """Repetition code, block-interleaved."""
    bits = np.asarray(bits, dtype=np.int8).ravel()
    return np.tile(bits, repeat)


def fec_decode(bits: np.ndarray, n_info: int, repeat: int = REPEAT) -> np.ndarray:
    """Majority vote over the interleaved copies."""
    bits = np.asarray(bits, dtype=np.int8).ravel()
    need = n_info * repeat
    if bits.size < need:
        bits = np.concatenate([bits, np.zeros(need - bits.size, dtype=np.int8)])
    votes = bits[:need].reshape(repeat, n_info)
    return (votes.sum(axis=0) > repeat / 2).astype(np.int8)


def encode_file_fec(data: bytes, name: str = "file.bin", repeat: int = REPEAT):
    bits, meta = encode_file(data, name, repeat)
    meta["n_info_bits"] = len(bits)
    meta["repeat"] = repeat
    meta["fec"] = f"rep{repeat}"
    return fec_encode(bits, repeat), meta


def decode_file_fec(bits: np.ndarray, meta: dict):
    info = fec_decode(bits, meta["n_info_bits"], meta.get("repeat", REPEAT))
    return decode_file(info, meta)


# ---------------------------------------------------------------------------
# Forward error correction: rate-1/2 convolutional code (see ofdm/conv.py)
# ---------------------------------------------------------------------------
# Same frame as encode_file, but protected by the K=7 convolutional code with
# soft-decision Viterbi decoding.  Rate 1/2 instead of repetition-3's 1/3, and
# a stronger code, so both throughput and robustness improve.

def encode_file_conv(data: bytes, name: str = "file.bin"):
    from . import conv
    bits, meta = encode_file(data, name, 1)
    meta["n_info_bits"] = len(bits)
    meta["fec"] = "conv"
    return conv.fec_encode(bits), meta


def decode_file_conv(syms: np.ndarray, meta: dict):
    """Equalised QPSK symbols (transmit order) -> (data, prr, header, good)."""
    from . import conv
    info = conv.fec_decode_soft(conv.symbols_to_soft(syms), meta["n_info_bits"])
    return decode_file(info, meta)


# ---------------------------------------------------------------------------
# Self-describing "live" frame - the receiver is told nothing in advance
# ---------------------------------------------------------------------------
# The scripted experiments hand the receiver the exact bit count.  A second
# device, or a person typing into the live demo, cannot do that, so this
# layout lets the receiver bootstrap itself from the sound alone:
#
#     rep-HEADER_REPEAT( header )  +  rep-r( packets )
#
# The header always uses the same fixed repetition so the receiver can decode
# it blind; it then reads the payload length and repetition factor `r` from
# the header and knows exactly how many more symbols to take.
#
# Decoding is *soft*: instead of majority-voting hard bits, the r equalised
# QPSK symbols carrying each bit are summed before the sign decision.  After
# MMSE equalisation a symbol from a subcarrier sitting in a spectral null is
# small, so it contributes little to the sum and a copy from a strong
# subcarrier dominates.  That is maximal-ratio combining, and it is what makes
# a full-band transmission from an uncalibrated device decodable.

HEADER_REPEAT = 5


def _copy_perm(n_pairs: int, k: int, seed: int = 9001) -> np.ndarray:
    """Fixed pseudo-random symbol order for repetition copy k, known to both ends."""
    return np.random.default_rng(seed + k).permutation(n_pairs)


def live_fec_encode(bits: np.ndarray, repeat: int) -> np.ndarray:
    """
    Repetition code with a pseudo-random *symbol-level* interleaver per copy.

    The plain block-tiled code in :func:`fec_encode` puts copy k of QPSK symbol
    i at position k*n + i.  Whenever n is a multiple of the number of data
    subcarriers, every copy of a bit lands on the *same* subcarrier - and
    n = 576 symbols for a 2-packet payload is a multiple of 9, 12 and 18, which
    are exactly the sizes Stage-1 calibration produces.  Measured over the air:
    one subcarrier at -28 dB had BER 0.37 and repetition-3 rescued nothing.
    A random permutation per copy makes the copies independent whatever the
    subcarrier count.
    """
    pairs = np.asarray(bits, dtype=np.int8).ravel().reshape(-1, 2)
    copies = [pairs[_copy_perm(len(pairs), k)] for k in range(repeat)]
    return np.concatenate(copies).ravel()


def encode_live(data: bytes, name: str = "message.txt", repeat=REPEAT):
    """
    File bytes -> self-describing transmit bit vector (+ metadata).

    `repeat` is a repetition factor, or "conv" for the rate-1/2 convolutional
    code (ofdm/conv.py).  The header always uses fixed repetition so a blind
    receiver can read it first and learn which code the payload uses.
    """
    pay = bytes_to_bits(packetize(data))
    if str(repeat).lower() == "conv":
        from . import conv
        hdr = bytes_to_bits(build_header(name, len(data), CONV_MARK))
        pay_coded = conv.fec_encode(pay)
        repeat = "conv"
    else:
        repeat = max(1, int(repeat))
        hdr = bytes_to_bits(build_header(name, len(data), repeat))
        pay_coded = live_fec_encode(pay, repeat)
    bits = np.concatenate([live_fec_encode(hdr, HEADER_REPEAT), pay_coded])
    meta = dict(n_packets=n_packets_for(len(data)), nbytes=len(data),
                repeat=repeat, n_header_bits=len(hdr), n_payload_bits=len(pay),
                header_syms=len(hdr) * HEADER_REPEAT // 2,
                payload_syms=len(pay_coded) // 2)
    return bits, meta


def soft_fec_decode(syms: np.ndarray, n_info_bits: int, repeat: int) -> np.ndarray:
    """
    Maximal-ratio combine `repeat` interleaved copies of n_info_bits/2 QPSK
    symbols, then hard-decide.  Missing symbols (a truncated recording) count
    as zero, i.e. they abstain from the vote.
    """
    n_sym = n_info_bits // 2
    need = n_sym * repeat
    syms = np.asarray(syms, dtype=complex).ravel()
    if syms.size < need:
        syms = np.concatenate([syms, np.zeros(need - syms.size, dtype=complex)])
    combined = np.zeros(n_sym, dtype=complex)
    for k in range(repeat):                     # undo each copy's interleaver
        combined[_copy_perm(n_sym, k)] += syms[k * n_sym:(k + 1) * n_sym]
    out = np.empty((n_sym, 2), dtype=np.int8)
    out[:, 0] = combined.real > 0
    out[:, 1] = combined.imag > 0
    return out.ravel()


def decode_live(syms: np.ndarray):
    """
    Equalised payload QPSK symbols (in transmit order) -> decoded file.

    Returns dict(ok, reason, header, data, prr, good, used_syms).
    """
    syms = np.asarray(syms, dtype=complex).ravel()
    n_hdr_bits = HEADER_LEN * 8
    hdr_syms = n_hdr_bits * HEADER_REPEAT // 2
    hdr_bits = soft_fec_decode(syms[:hdr_syms], n_hdr_bits, HEADER_REPEAT)
    hdr = parse_header(bits_to_bytes(hdr_bits))
    if hdr is None:
        return dict(ok=False, reason="header failed CRC", header=None,
                    data=b"", prr=0.0, good=[], used_syms=hdr_syms)
    n_pk = n_packets_for(hdr["nbytes"])
    n_pay_bits = n_pk * (4 + PACKET_PAYLOAD + 4) * 8
    if hdr["code"] == "conv":
        from . import conv
        pay_syms = conv.coded_length(n_pay_bits) // 2
        pay_bits = conv.fec_decode_soft(
            conv.symbols_to_soft(syms[hdr_syms:hdr_syms + pay_syms]), n_pay_bits)
    else:
        pay_syms = n_pay_bits * hdr["repeat"] // 2
        pay_bits = soft_fec_decode(syms[hdr_syms:hdr_syms + pay_syms],
                                   n_pay_bits, hdr["repeat"])
    data, prr, good = depacketize(bits_to_bytes(pay_bits), n_pk)
    return dict(ok=True, reason="", header=hdr, data=data[:hdr["nbytes"]],
                prr=prr, good=good, used_syms=hdr_syms + pay_syms)
