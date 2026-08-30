"""
System configuration for the acoustic OFDM modem.

All timing/frequency constants live here so that experiments can sweep them
without touching the DSP code.
"""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class OFDMConfig:
    # --- Sampling / band ---------------------------------------------------
    fs: int = 48000            # sample rate (Hz) - universally supported
    nfft: int = 256            # IFFT/FFT size
    ncp: int = 64              # cyclic prefix length (samples)
    f_low: float = 4000.0      # lowest occupied frequency (Hz)
    f_high: float = 12000.0    # highest occupied frequency (Hz)

    # --- Pilot / framing ---------------------------------------------------
    pilot_spacing: int = 4     # every Nth occupied subcarrier is a pilot
    symbols_per_frame: int = 20
    guard_symbols: int = 1     # silent guard between preamble and payload

    # --- Preamble ----------------------------------------------------------
    chirp_dur: float = 0.030   # 30 ms synchronisation chirp
    chirp_f0: float = 3000.0
    chirp_f1: float = 13000.0
    lead_silence: float = 0.10
    tail_silence: float = 0.15

    # --- Amplitude ---------------------------------------------------------
    amplitude: float = 0.60    # peak amplitude of transmitted waveform

    # Peak-to-average reduction.  An OFDM block is a sum of ~40 independent
    # subcarriers, so its envelope is nearly Gaussian and its PAPR is ~9 dB.
    # Since a speaker is peak-limited, that means the *average* transmitted
    # power - which is what sets the received SNR - is 9 dB below what the
    # hardware could deliver.  Clipping the waveform to this many dB above its
    # RMS buys most of that back.  0 disables it.
    papr_clip_db: float = 6.0

    # --- Stage-1 self-calibration -----------------------------------------
    # If set, only these FFT bins are used.  Populated by ofdm.calibrate from
    # a measured chirp response so that subcarriers landing in the speaker's
    # spectral nulls are never transmitted on in the first place.
    active_bins: tuple = ()

    def __post_init__(self):
        self._validate()

    # -- derived quantities -------------------------------------------------
    @property
    def df(self) -> float:
        """Subcarrier spacing (Hz)."""
        return self.fs / self.nfft

    @property
    def sym_len(self) -> int:
        """Samples per OFDM symbol including cyclic prefix."""
        return self.nfft + self.ncp

    @property
    def sym_dur(self) -> float:
        return self.sym_len / self.fs

    @property
    def data_bins(self) -> np.ndarray:
        """Occupied subcarrier indices (positive-frequency half only)."""
        k_lo = int(np.ceil(self.f_low / self.df))
        k_hi = int(np.floor(self.f_high / self.df))
        k_hi = min(k_hi, self.nfft // 2 - 1)
        band = np.arange(k_lo, k_hi + 1)
        if self.active_bins:
            band = np.intersect1d(band, np.asarray(self.active_bins, dtype=int))
        return band

    @property
    def pilot_bins(self) -> np.ndarray:
        """Subcarriers carrying pilots (always includes both band edges)."""
        used = self.data_bins
        idx = np.arange(0, len(used), self.pilot_spacing)
        if idx[-1] != len(used) - 1:            # pin the top edge too, so that
            idx = np.append(idx, len(used) - 1)  # interpolation never extrapolates
        return used[idx]

    @property
    def payload_bins(self) -> np.ndarray:
        """Subcarriers carrying QPSK payload."""
        return np.setdiff1d(self.data_bins, self.pilot_bins)

    @property
    def bits_per_symbol(self) -> int:
        return 2 * len(self.payload_bins)      # QPSK = 2 bits/subcarrier

    @property
    def raw_bitrate(self) -> float:
        """Payload bit rate in bit/s, ignoring preamble overhead."""
        return self.bits_per_symbol / self.sym_dur

    def _validate(self):
        if self.f_high >= self.fs / 2:
            raise ValueError("f_high must be below Nyquist")
        if self.ncp >= self.nfft:
            raise ValueError("cyclic prefix must be shorter than the FFT")
        if len(self.data_bins) < 8:
            raise ValueError("occupied band too narrow for a useful frame")

    def summary(self) -> str:
        return (
            f"fs={self.fs} Hz  N={self.nfft}  CP={self.ncp}  "
            f"df={self.df:.1f} Hz\n"
            f"band = {self.f_low:.0f}-{self.f_high:.0f} Hz -> "
            f"{len(self.data_bins)} subcarriers "
            f"({len(self.pilot_bins)} pilot, {len(self.payload_bins)} data)\n"
            f"symbol = {self.sym_len} samples ({self.sym_dur*1e3:.2f} ms), "
            f"{self.bits_per_symbol} bit/symbol\n"
            f"raw payload rate = {self.raw_bitrate:.0f} bit/s "
            f"({self.raw_bitrate/8:.0f} byte/s)\n"
            f"CP guards {self.ncp/self.fs*1e3:.2f} ms of delay spread "
            f"({343*self.ncp/self.fs:.2f} m of excess path length)"
        )


DEFAULT = OFDMConfig()
