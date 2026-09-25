"""Rate-1/2 K=7 convolutional code with soft Viterbi decoding."""
import unittest

import numpy as np

from ofdm import conv, framing, modem


class TestConv(unittest.TestCase):
    def setUp(self):
        self.bits = np.random.default_rng(3).integers(0, 2, 1500).astype(np.int8)

    def test_rate_and_tail(self):
        c = conv.encode(self.bits)
        self.assertEqual(c.size, 2 * (self.bits.size + conv.TAIL))
        self.assertEqual(conv.coded_length(self.bits.size), c.size)

    def test_known_impulse_response(self):
        # a single 1 followed by zeros reads the generators out bit by bit
        c = conv.encode(np.array([1], dtype=np.int8)).reshape(-1, 2)
        g0 = int("".join(map(str, c[:, 0])), 2)
        g1 = int("".join(map(str, c[:, 1])), 2)
        self.assertEqual((g0, g1), conv.G)

    def test_clean_round_trip(self):
        soft = 2.0 * conv.fec_encode(self.bits) - 1
        self.assertTrue(np.array_equal(conv.fec_decode_soft(soft, self.bits.size), self.bits))

    def test_interleaver_is_a_permutation(self):
        x = np.arange(500)
        self.assertTrue(np.array_equal(conv.deinterleave(conv.interleave(x), 500), x))

    def test_corrects_noise_that_breaks_uncoded(self):
        rng = np.random.default_rng(4)
        c = conv.fec_encode(self.bits)
        y = (2.0 * c - 1) + rng.normal(0, 0.7, c.size)     # Eb/N0 ~3 dB, raw BER ~8 %
        self.assertGreater(np.mean((y > 0) != c), 0.05)
        dec = conv.fec_decode_soft(y, self.bits.size)
        self.assertLess(np.mean(dec != self.bits), 1e-3)

    def test_corrects_a_burst_of_erasures(self):
        c = conv.fec_encode(self.bits)
        y = 2.0 * c - 1
        y[1000:1060] = 0                                     # 60 coded bits lost
        self.assertTrue(np.array_equal(conv.fec_decode_soft(y, self.bits.size), self.bits))

    def test_file_level_round_trip(self):
        data = b"convolutional code round trip " * 5
        bits, meta = framing.encode_file_conv(data, "c.txt")
        syms = modem.qpsk_modulate(bits)
        out, prr, hdr, _ = framing.decode_file_conv(syms, meta)
        self.assertEqual(out, data)
        self.assertEqual(prr, 1.0)


if __name__ == "__main__":
    unittest.main()
