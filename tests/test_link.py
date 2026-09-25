"""End-to-end links through the simulated acoustic channel."""
import unittest

import numpy as np

from ofdm import channel, framing, live, modem, receiver, sync
from ofdm.config import DEFAULT

MSG = b"end-to-end test through the simulated room " * 4


class TestScriptedLink(unittest.TestCase):
    def _run(self, bits, meta_n_sym, snr, ppm=80):
        x, meta = modem.modulate(bits, DEFAULT)
        rx, info = channel.apply_channel(x, snr, DEFAULT, delay=4000, clock_ppm=ppm,
                                         rng=np.random.default_rng(5))
        return receiver.demodulate(rx, len(bits), meta["n_sym"], DEFAULT,
                                   noise_var=info["noise_var"])

    def test_awgn_high_snr_is_error_free(self):
        bits = np.random.default_rng(0).integers(0, 2, 3000).astype(np.int8)
        x, meta = modem.modulate(bits, DEFAULT)
        rx, info = channel.apply_channel(x, 30, DEFAULT, multipath=False,
                                         transducer=False, delay=2000,
                                         rng=np.random.default_rng(1))
        r = receiver.demodulate(rx, len(bits), meta["n_sym"], DEFAULT,
                                noise_var=info["noise_var"])
        self.assertTrue(r["ok"])
        self.assertEqual(receiver.ber(bits, r["bits"])[1], 0)

    def test_conv_coded_file_at_low_snr(self):
        bits, fmeta = framing.encode_file_conv(MSG, "t.txt")
        r = self._run(bits, None, snr=6)
        data, prr, _, _ = framing.decode_file_conv(r["symbols"], fmeta)
        self.assertEqual(data, MSG)


class TestBlindLink(unittest.TestCase):
    def test_blind_decode_with_clock_offset(self):
        x, bits, _, _ = live.build_frame(MSG, "m.txt", 3, DEFAULT)
        rx, info = channel.apply_channel(x, 15, DEFAULT, delay=6000, clock_ppm=-120,
                                         rng=np.random.default_rng(7))
        r = live.demodulate_blind(rx, DEFAULT, noise_var=info["noise_var"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"], MSG)
        self.assertAlmostEqual(r["clock_ppm"], -120, delta=15)

    def test_no_signal_reports_sync_failure(self):
        noise = np.random.default_rng(0).normal(0, 0.01, 48000)
        r = live.demodulate_blind(noise, DEFAULT)
        self.assertFalse(r["ok"])
        self.assertIn(r["stage"], ("sync", "header"))   # never a false decode

    def test_long_frame_needs_clock_correction(self):
        data = bytes(np.random.default_rng(1).integers(32, 127, 1200, dtype=np.uint8))
        x, _, _, _ = live.build_frame(data, "long.bin", 3, DEFAULT)
        rx, info = channel.apply_channel(x, 18, DEFAULT, delay=4000, clock_ppm=300,
                                         rng=np.random.default_rng(2))
        off = live.demodulate_blind(rx, DEFAULT, noise_var=info["noise_var"],
                                    clock_correct=False)
        on = live.demodulate_blind(rx, DEFAULT, noise_var=info["noise_var"])
        self.assertFalse(off.get("ok") and off["data"] == data)
        self.assertTrue(on["ok"])
        self.assertTrue(on["clock_corrected"])
        self.assertEqual(on["data"], data)


class TestClockEstimate(unittest.TestCase):
    def test_estimate_tracks_true_offset(self):
        x, _, _, _ = live.build_frame(MSG * 2, "m.txt", 3, DEFAULT)
        for ppm in (-200, 0, 150):
            rx, info = channel.apply_channel(x, 20, DEFAULT, delay=3000, clock_ppm=ppm,
                                             rng=np.random.default_rng(ppm + 500))
            r = live.demodulate_blind(rx, DEFAULT, noise_var=info["noise_var"],
                                      clock_correct=False)
            est, n = sync.estimate_clock_ppm(r["grid_raw"], DEFAULT)
            self.assertGreater(n, 50)
            self.assertAlmostEqual(est, ppm, delta=12, msg=f"true {ppm} ppm")


if __name__ == "__main__":
    unittest.main()
