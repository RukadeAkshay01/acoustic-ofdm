"""
Channel estimation and equalisation  (Phase 2 + Phase 3, Member 2).

Three estimator modes are provided so the report can compare them directly:

  'none'      no equalisation at all - the Phase 1 baseline.  The frequency
              selectivity of the room shows up as a rotated, unequal-radius
              constellation and the BER floors out.

  'static'    Phase 2.  One least-squares estimate taken from the known
              reference symbol at the head of the frame, held fixed for the
              whole burst.  H_hat[k] = Y[k] / X[k].

  'adaptive'  Phase 3.  Start from the static estimate, then track it with the
              pilots carried in every payload symbol.

              The obvious recursion H <- (1-mu) H + mu H_pilot turns out to
              make things *worse*: it throws away a 43-subcarrier reference
              estimate and replaces it with 12 pilots interpolated across the
              spectral nulls of the room, so the estimate gets noisier every
              symbol.  We measured BER rising from 3e-4 to 1e-1 doing that.

              Instead we track a *multiplicative correction*.  At the pilots we
              form C = H_pilot_LS / H_current, which is a smooth, near-unity
              function of frequency because the sharp spectral structure has
              already been divided out.  That is safe to interpolate.  Then

                    H <- H * (1 - mu + mu * C_interp)

              so the fine structure keeps coming from the reference symbol
              while the pilots supply the slow drift.  A separate common-phase
              estimate removes the fast rotation caused by the sampling-clock
              offset between two devices.  This is the "self-calibrating"
              behaviour the proposal is built around.
"""
import numpy as np

from .config import OFDMConfig, DEFAULT
from .modem import pilot_values, reference_symbol


def ls_estimate(Y: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Least-squares channel estimate on subcarriers where X is known."""
    return Y / np.where(np.abs(X) < 1e-12, 1e-12, X)


def interpolate_pilots(H_pilot: np.ndarray, cfg: OFDMConfig = DEFAULT) -> np.ndarray:
    """
    Interpolate a pilot-only channel estimate onto every occupied subcarrier.

    Magnitude and unwrapped phase are interpolated separately.  Interpolating
    the complex value directly would pull the estimate toward zero wherever the
    phase rotates quickly between pilots, which is exactly what happens when
    there is a residual timing offset.
    """
    used = cfg.data_bins
    pb = cfg.pilot_bins
    mag = np.interp(used, pb, np.abs(H_pilot))
    ph = np.interp(used, pb, np.unwrap(np.angle(H_pilot)))
    return mag * np.exp(1j * ph)


def smooth_estimate(H: np.ndarray, span: int = 3) -> np.ndarray:
    """Short moving average across frequency; trades resolution for noise."""
    if span <= 1:
        return H
    k = np.ones(span) / span
    return np.convolve(H, k, mode="same")


def mmse_weights(H: np.ndarray, noise_var: float) -> np.ndarray:
    """
    MMSE equaliser taps.  Zero-forcing (1/H) blows up on deep spectral nulls
    and amplifies noise there; the MMSE regulariser caps that gain.
    """
    return np.conj(H) / (np.abs(H) ** 2 + max(noise_var, 1e-9))


class ChannelEstimator:
    """Stateful estimator; call :meth:`equalize_symbol` once per OFDM symbol."""

    def __init__(self, cfg: OFDMConfig = DEFAULT, mode: str = "adaptive",
                 mu: float = 0.15, noise_var: float = 1e-3,
                 track_phase: bool = True, smooth: int = 3):
        if mode not in ("none", "static", "adaptive"):
            raise ValueError(f"unknown equaliser mode {mode!r}")
        self.cfg = cfg
        self.mode = mode
        self.mu = mu
        self.noise_var = noise_var
        self.track_phase = track_phase
        self.smooth = smooth

        self.H = np.ones(len(cfg.data_bins), dtype=complex)
        self.pilot_pos = np.searchsorted(cfg.data_bins, cfg.pilot_bins)
        self.pilot_ref = pilot_values(cfg)
        self.history = []          # H after every symbol, for the dashboard
        self.cpe = []              # common phase error per symbol (radians)
        self.gain_track = []       # bulk gain correction per symbol
        self.slope_track = []      # phase slope per symbol (clock-offset signature)

    # -- Phase 2: one-shot estimate from the known reference symbol ---------
    def initial_estimate(self, Y_ref: np.ndarray):
        H = ls_estimate(Y_ref, reference_symbol(self.cfg))
        self.H = smooth_estimate(H, self.smooth)
        self.history.append(self.H.copy())
        return self.H

    # -- Phase 3: per-symbol pilot update ----------------------------------
    def _pilot_update(self, Y: np.ndarray):
        """
        Track the channel from the pilots of the current symbol.

        The correction C = H_pilot_LS / H_current is fitted to a two-parameter
        model rather than interpolated point-by-point:

            C(k) = g * exp(j (a + b k))

        g is a bulk gain change (the talker drifting closer or the AGC moving),
        a is residual common phase and b is a phase *slope*, which is precisely
        the signature of a sampling-clock offset - a timing drift of tau
        samples rotates subcarrier k by 2*pi*k*tau/N.

        Piecewise interpolation of C was tried first and produced a BER floor
        of ~1e-2 that would not fall with SNR: between two pilots straddling a
        spectral null the interpolated correction is simply wrong, so every
        symbol nudged the good reference estimate further away from the truth.
        The parametric fit cannot do that - it only ever applies a smooth,
        physically meaningful correction and leaves the null structure from the
        reference symbol intact.

        The fit is weighted by |H|^2 so that pilots sitting in a null, whose
        LS estimates are dominated by noise, carry little influence.
        """
        H_cur = self.H[self.pilot_pos]
        H_p = ls_estimate(Y[self.pilot_pos], self.pilot_ref)
        C_p = H_p / np.where(np.abs(H_cur) < 1e-12, 1e-12, H_cur)

        k = self.cfg.pilot_bins.astype(float)
        w = np.abs(H_cur) ** 2
        if not np.any(w > 0):
            return
        w = w / np.sum(w)

        # weighted least squares for the phase line a + b k
        ph = np.angle(C_p)
        A = np.stack([np.ones_like(k), k], axis=1)
        Aw = A * w[:, None]
        try:
            coef = np.linalg.solve(A.T @ Aw, Aw.T @ ph)
        except np.linalg.LinAlgError:
            return
        a, b = coef
        g = float(np.sum(w * np.abs(C_p)))

        kk = self.cfg.data_bins.astype(float)
        C = g * np.exp(1j * (a + b * kk))
        self.H = self.H * (1 - self.mu + self.mu * C)
        self.gain_track.append(g)
        self.slope_track.append(float(b))

    def _common_phase(self, Y: np.ndarray) -> float:
        """
        Residual phase rotation shared by all subcarriers, caused by sampling
        clock offset.  Estimated as the angle of the summed pilot correlation,
        which is the maximum-likelihood estimate under white noise.
        """
        expect = self.H[self.pilot_pos] * self.pilot_ref
        return float(np.angle(np.sum(Y[self.pilot_pos] * np.conj(expect))))

    def equalize_symbol(self, Y: np.ndarray) -> np.ndarray:
        """Equalise one received resource-grid row and return the estimate."""
        if self.mode == "none":
            self.history.append(self.H.copy())
            self.cpe.append(0.0)
            return Y

        phi = 0.0
        if self.mode == "adaptive":
            if self.track_phase:
                phi = self._common_phase(Y)
                Y = Y * np.exp(-1j * phi)
            self._pilot_update(Y)

        W = mmse_weights(self.H, self.noise_var)
        self.history.append(self.H.copy())
        self.cpe.append(phi)
        return Y * W

    # -- diagnostics --------------------------------------------------------
    def estimation_error_db(self, H_true: np.ndarray) -> float:
        """
        Normalised MSE of the current estimate against ground truth, in dB.

        Two nuisance terms have to be removed first or the number is
        meaningless.  A global complex gain is arbitrary - the receiver never
        knows the absolute transmit level - and so is a *linear phase ramp*,
        because the synchroniser deliberately starts the FFT window a few
        samples early and that shows up as exp(-j 2 pi k d / N) across the
        subcarriers.  Neither costs a single bit: the equaliser divides both
        straight out.  Scoring without removing them gave +22.9 dB, i.e. an
        "error" larger than the signal, for an estimate that was in fact
        recovering the data with zero bit errors.
        """
        a = np.asarray(self.H)
        b = np.asarray(H_true)
        k = self.cfg.data_bins.astype(float)

        # fit and remove the linear phase ramp, weighted by channel strength
        r = a * np.conj(b)
        w = np.abs(b) ** 2
        if np.any(w > 0):
            w = w / np.sum(w)
            ph = np.unwrap(np.angle(r))
            A = np.stack([np.ones_like(k), k], axis=1)
            Aw = A * w[:, None]
            try:
                c0, c1 = np.linalg.solve(A.T @ Aw, Aw.T @ ph)
                a = a * np.exp(-1j * (c0 + c1 * k))
            except np.linalg.LinAlgError:
                pass

        scale = np.vdot(b, a) / (np.vdot(b, b) + 1e-18)   # remove global gain
        err = (np.mean(np.abs(a - scale * b) ** 2) /
               (np.mean(np.abs(scale * b) ** 2) + 1e-18))
        return float(10 * np.log10(err + 1e-18))
