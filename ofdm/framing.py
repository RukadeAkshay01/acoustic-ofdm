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
HEADER_LEN = 32
PACKET_PAYLOAD = 64          # bytes of file data per packet


def bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8)).astype(np.int8)


def bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = np.asarray(bits, dtype=np.uint8).ravel()
    bits = bits[: len(bits) // 8 * 8]
    return np.packbits(bits).tobytes()


def build_header(name: str, nbytes: int) -> bytes:
    nm = name.encode()[:19].ljust(19, b"\0")
    body = MAGIC + struct.pack("<I", nbytes) + nm          # 4 + 4 + 19 = 27
    return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)[:4] + b"\0"


def parse_header(data: bytes):
    if len(data) < HEADER_LEN or data[:4] != MAGIC:
        return None
    body = data[:27]
    crc = struct.unpack("<I", data[27:31])[0]
    if (zlib.crc32(body) & 0xFFFFFFFF) != crc:
        return None
    nbytes = struct.unpack("<I", data[4:8])[0]
    name = data[8:27].rstrip(b"\0").decode(errors="replace")
    return dict(name=name, nbytes=nbytes)


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


def encode_file(data: bytes, name: str = "file.bin"):
    """File bytes -> transmit bit vector."""
    frame = build_header(name, len(data)) + packetize(data)
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
    bits, meta = encode_file(data, name)
    meta["n_info_bits"] = len(bits)
    meta["repeat"] = repeat
    meta["fec"] = f"rep{repeat}"
    return fec_encode(bits, repeat), meta


def decode_file_fec(bits: np.ndarray, meta: dict):
    info = fec_decode(bits, meta["n_info_bits"], meta.get("repeat", REPEAT))
    return decode_file(info, meta)
