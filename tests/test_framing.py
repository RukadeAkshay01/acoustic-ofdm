"""Packetisation, headers and repetition FEC."""
import unittest

import numpy as np

from ofdm import framing


class TestFraming(unittest.TestCase):
    DATA = bytes(range(200))

    def test_header_round_trip(self):
        h = framing.build_header("report.pdf", 12345, 3)
        self.assertEqual(len(h), framing.HEADER_LEN)
        self.assertEqual(framing.parse_header(h),
                         dict(name="report.pdf", nbytes=12345, repeat=3, code="rep"))

    def test_header_crc_rejects_corruption(self):
        h = bytearray(framing.build_header("a.txt", 10, 1))
        h[6] ^= 0x01
        self.assertIsNone(framing.parse_header(bytes(h)))

    def test_file_round_trip(self):
        bits, meta = framing.encode_file(self.DATA, "x.bin")
        data, prr, hdr, good = framing.decode_file(bits, meta)
        self.assertEqual(data, self.DATA)
        self.assertEqual(prr, 1.0)
        self.assertEqual(hdr["nbytes"], len(self.DATA))

    def test_single_bit_error_kills_one_packet_only(self):
        bits, meta = framing.encode_file(self.DATA, "x.bin")
        bits = bits.copy()
        bits[framing.HEADER_LEN * 8 + 100] ^= 1           # inside packet 0
        _, prr, _, good = framing.decode_file(bits, meta)
        self.assertEqual(good, [False, True, True, True])
        self.assertEqual(prr, 0.75)

    def test_repetition_majority_vote(self):
        bits, meta = framing.encode_file_fec(self.DATA, "x.bin", 3)
        bits = bits.copy()
        n = meta["n_info_bits"]
        bits[5] ^= 1                                       # one copy wrong
        bits[n + 700] ^= 1
        data, prr, _, _ = framing.decode_file_fec(bits, meta)
        self.assertEqual(data, self.DATA)

    def test_live_frame_soft_decode(self):
        from ofdm import modem
        bits, meta = framing.encode_live(self.DATA, "m.txt", 3)
        syms = modem.qpsk_modulate(bits)
        # weaken and flip a scattered set of symbols: MRC must outvote them
        rng = np.random.default_rng(0)
        bad = rng.choice(syms.size, syms.size // 20, replace=False)
        syms[bad] *= -0.3
        out = framing.decode_live(syms)
        self.assertTrue(out["ok"])
        self.assertEqual(out["data"], self.DATA)

    def test_live_frame_conv(self):
        from ofdm import modem
        bits, meta = framing.encode_live(self.DATA, "m.txt", "conv")
        self.assertEqual(meta["repeat"], "conv")
        syms = modem.qpsk_modulate(bits)
        hdr_syms = framing.HEADER_LEN * 8 * framing.HEADER_REPEAT // 2
        rng = np.random.default_rng(1)
        pay = np.arange(hdr_syms, syms.size)
        syms[rng.choice(pay, pay.size // 25, replace=False)] *= -0.5
        out = framing.decode_live(syms)
        self.assertTrue(out["ok"])
        self.assertEqual(out["header"]["code"], "conv")
        self.assertEqual(out["data"], self.DATA)
        self.assertEqual(out["used_syms"], len(bits) // 2)


if __name__ == "__main__":
    unittest.main()
