"""Modulator / demodulator round trips and configuration invariants."""
import unittest

import numpy as np

from ofdm import modem
from ofdm.config import OFDMConfig, DEFAULT


class TestQPSK(unittest.TestCase):
    def test_round_trip(self):
        bits = np.random.default_rng(0).integers(0, 2, 1000).astype(np.int8)
        self.assertTrue(np.array_equal(modem.qpsk_demodulate(modem.qpsk_modulate(bits)), bits))

    def test_unit_energy(self):
        s = modem.qpsk_modulate(np.array([0, 0, 0, 1, 1, 0, 1, 1]))
        self.assertTrue(np.allclose(np.abs(s), 1.0))

    def test_odd_length_rejected(self):
        with self.assertRaises(ValueError):
            modem.qpsk_modulate(np.array([1, 0, 1]))


class TestGrid(unittest.TestCase):
    def test_noiseless_grid_round_trip(self):
        cfg = DEFAULT
        bits = np.random.default_rng(1).integers(0, 2, 5 * cfg.bits_per_symbol).astype(np.int8)
        grid, n_pad = modem.build_grid(bits, cfg)
        self.assertEqual(n_pad, 0)
        x = modem.grid_to_time(grid, cfg)
        self.assertTrue(np.isrealobj(x))
        back = modem.time_to_grid(x, grid.shape[0], cfg)
        self.assertTrue(np.allclose(back, grid, atol=1e-9))

    def test_pilots_pin_both_edges(self):
        cfg = DEFAULT
        self.assertEqual(cfg.pilot_bins[0], cfg.data_bins[0])
        self.assertEqual(cfg.pilot_bins[-1], cfg.data_bins[-1])
        self.assertEqual(len(np.intersect1d(cfg.pilot_bins, cfg.payload_bins)), 0)

    def test_config_validation(self):
        with self.assertRaises(ValueError):
            OFDMConfig(f_high=30000)
        with self.assertRaises(ValueError):
            OFDMConfig(ncp=256)


class TestModulate(unittest.TestCase):
    def test_peak_amplitude(self):
        bits = np.random.default_rng(2).integers(0, 2, 2000).astype(np.int8)
        x, meta = modem.modulate(bits, DEFAULT)
        self.assertLessEqual(np.max(np.abs(x)), DEFAULT.amplitude + 1e-9)
        self.assertLess(meta["papr_after_db"], meta["papr_before_db"])


if __name__ == "__main__":
    unittest.main()
