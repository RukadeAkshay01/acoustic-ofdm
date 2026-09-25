#!/usr/bin/env python3
r"""
Generate the three per-member final reports from the course LaTeX template.

The body is shared - the project is a group project - and only the author and
the "Individual Contribution" chapter differ. Edit the shared text or a
member's entry here, then re-run:

    python3 reports/final/make_final_reports.py
    cd reports/final && pdflatex SP_Final_Report_Akshay_Rukade.tex  (twice, for the TOC)

Anything the team still has to supply is typeset in red by \fillin{...}.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Names exactly as they should appear on the title page.
AKSHAY = "Akshay Ajit Rukade"
KRITHIKA = "J Krithika"
RITESH = "Ritesh Gajanan Sonar"
TEAM = f"{AKSHAY}, {KRITHIKA} and {RITESH}"
ROLL = {AKSHAY: "24F2100357", KRITHIKA: "24F2100165", RITESH: "23F3000249"}
SUBMISSION_DATE = "25-09-2026"
TEAM_BLOCK = r"\begin{tabular}[t]{@{}l@{}}" + r" \\ ".join(
    f"{n} --- {ROLL[n]}" for n in (AKSHAY, KRITHIKA, RITESH)) + r"\end{tabular}"

MEMBERS = [
    dict(slug="Akshay_Rukade", name=AKSHAY, role="OFDM modulation/demodulation engine",
         individual=r"""
I owned the modem core (\texttt{ofdm/modem.py}, \texttt{ofdm/config.py}): turning a
bit vector into a waveform a speaker can play, and received samples back into a
resource grid.

\begin{itemize}
    \item \textbf{Real-valued OFDM without a mixer:} designed the Hermitian-symmetric
    IFFT mapping (QPSK on bins 22--64 of a 256-point IFFT), so the transmitter output
    is already a real 4--12\,kHz audio signal. Verified numerically: the residual
    imaginary part is $7\times10^{-17}$. This removed the up/down-conversion stage and
    every carrier-offset problem with it.
    \item \textbf{System parameter set:} chose and justified the sample rate, FFT size,
    cyclic prefix, band and modulation (Section~\ref{sec:params}), and put them in one
    dataclass with derived properties. This let Stage-1 calibration later restrict the
    modem to a subset of subcarriers with a one-line change.
    \item \textbf{Pilots and preamble:} a pseudo-random BPSK pilot sequence (an all-ones
    pattern produces a loud, clipping impulse), a fully-known reference symbol on all
    43 subcarriers for the one-shot channel estimate, and the raised-cosine-tapered
    30\,ms synchronisation chirp.
    \item \textbf{Peak-to-average power reduction:} implemented iterative clipping and
    frequency-domain filtering and ran the trade-off sweep
    (Table~\ref{tab:papr}). Chose clipping at 6\,dB above RMS, which recovers 3.3\,dB of
    average transmit power and still reaches zero errors from 14\,dB SNR.
    \item \textbf{Debugging:} found that normalising the whole frame by one global peak
    left the chirp 6\,dB too quiet to detect (Problem~\ref{prob:chirp}). Separate
    normalisation raised detection confidence from $8.6\times$ to $121\times$ the
    noise floor.
    \item \textbf{Verification of the module:} ideal loopback BER $=0$, AWGN BER against
    theory, PAPR reduction preserving demodulation, and correct re-derivation of pilot
    and payload sets for a restricted subcarrier configuration.
    \item \textbf{Post-mid-term --- forward error correction:} implemented the
    rate-$\tfrac12$, $K=7$ convolutional code with generators $(171,133)_8$, the
    vectorised soft-decision Viterbi decoder (\texttt{ofdm/conv.py}) and the
    pseudo-random interleaver, and fed it the equalised QPSK values as soft inputs.
    Integrated it into the file framing and the self-describing live frame (header
    repetition byte 0 marks a convolutionally coded payload), and ran the FEC
    comparison (\texttt{run\_fec.py}): 2\,408\,bit/s of file data against
    1\,794 for repetition-3, with every file intact from 4\,dB SNR instead of 18\,dB.
    Also wrote the script that generates the report figures from the results files.
    \item \textbf{Documentation:} individual mid-term report (Member~1: modem engine);
    in this report, the Abstract and Chapters 1--4 (Introduction, Problem Statement,
    Goals and Objectives, Methodology).
\end{itemize}
"""),
    dict(slug="J_Krithika", name=KRITHIKA, role="channel estimation, equalisation and self-calibration",
         individual=r"""
I owned everything between the receiver's FFT and its demapper
(\texttt{ofdm/equalizer.py}, \texttt{ofdm/calibrate.py}): estimating what the acoustic
channel did to each subcarrier, undoing it, and deciding which subcarriers are
worth using.

\begin{itemize}
    \item \textbf{Three estimator modes} (\texttt{none}, \texttt{static},
    \texttt{adaptive}), so the project could measure the value of each stage rather
    than assert it.
    \item \textbf{Phase 2 estimation and equalisation:} least-squares estimation from the
    reference symbol with 3-tap frequency smoothing, and an MMSE equaliser instead of
    zero-forcing, because the channel's 40\,dB nulls would otherwise amplify the noise by
    the same amount. Result: BER that never leaves 0.47 without equalisation falls to a
    $3.6\times10^{-3}$ floor with it; channel NMSE $-14.7$\,dB at 20\,dB SNR.
    \item \textbf{Phase 3 adaptive tracker:} the naive recursion made BER worse
    ($3\times10^{-4}\rightarrow10^{-1}$, Problem~\ref{prob:track}). Designed the working
    tracker instead: a two-parameter correction $C(k)=g\,e^{j(a+bk)}$ fitted to the
    pilots by $|H|^2$-weighted least squares. The phase slope $b$ is the
    sampling-clock-offset signature. At 100\,ppm this gives $3.8\times10^{-3}$ against
    0.51 for static calibration, a $135\times$ improvement. Chose $\mu=0.15$ from the
    step-size sweep.
    \item \textbf{Stage-1 self-calibration:} measured the real speaker + microphone
    response (43\,dB of dynamic range across the band) and implemented subcarrier
    selection by backoff. With 8\,dB backoff (18 of 43 subcarriers) the over-the-air
    uncoded BER fell from 0.31 to $8.3\times10^{-3}$, a $37\times$ improvement.
    \item \textbf{Metric correction:} channel-estimation NMSE was reporting $+22.9$\,dB
    for an estimate recovering data with zero errors. Removing the global complex gain
    and the fitted linear phase ramp before scoring gave the correct $-14.7$\,dB.
    \item \textbf{Post-mid-term --- clock-offset estimation and correction:} extended
    the phase-slope idea from the adaptive tracker into a stand-alone estimator in
    \texttt{ofdm/sync.py}: a line fit to the unwrapped phase of
    neighbouring-pilot products over the whole frame, accurate to a few ppm. Replaced
    a first version that differenced adjacent symbols and was off by tens of ppm. Added
    the resample-and-redecode pass to the blind receiver (\texttt{ofdm/live.py}) and ran
    the long-frame drift sweep (\texttt{run\_drift.py}), which found the
    asymmetric failure limit and showed 4.89\,s frames surviving $\pm400$\,ppm with
    correction, against failing from 200\,ppm without it.
    \item \textbf{Documentation:} individual mid-term report (Member~2: channel
    estimation and equalisation); in this report, Chapters 7 and 8 (Results and
    Discussion, Conclusions).
\end{itemize}
"""),
    dict(slug="Ritesh_Gajanan_Sonar", name=RITESH,
         role="synchronisation, testing, audio I/O and dashboard",
         individual=r"""
{\sloppy
I owned frame synchronisation, the simulated channel, file framing, the real audio
path, the BER experiments and the web dashboard (\texttt{ofdm/sync.py},
\texttt{ofdm/receiver.py}, \texttt{ofdm/channel.py}, \texttt{ofdm/framing.py},
\texttt{ofdm/audio\_io.py}, \texttt{experiments/}, \texttt{dashboard/}).\par}

\begin{itemize}
    \item \textbf{Frame synchronisation:} chirp matched filter with a Hilbert-envelope
    detector, sample-exact down to 0\,dB SNR (detection confidence $54\times$ the noise
    floor at 0\,dB). Found and fixed the FFT-window backoff constraint
    $D<N/(2\cdot\text{pilot spacing})$ (Problem~\ref{prob:alias}), reducing the backoff
    from 32 to 8 samples.
    \item \textbf{Simulated acoustic channel:} multipath, transducer band-pass, noise and
    sampling-clock offset. Fixed a methodology bug where the room was redrawn at every
    SNR point, making BER curves non-monotonic, by seeding the room from the trial index.
    \item \textbf{BER experiments A--D:} AWGN validation against theory, equaliser
    comparison, clock-offset sweep and step-size sweep, at 16 trials $\times$ 6\,200 bits
    per point.
    \item \textbf{File framing:} CRC-protected header and fixed-length CRC-tagged
    packets, giving the packet-recovery-rate metric. Fixed the variable-length
    last-packet bug, and added the interleaved repetition code used over the air.
    \item \textbf{Real audio I/O over ALSA:} found and fixed four hardware problems that
    looked like DSP bugs: the capture start-up click, the capture stop transient, the
    noise-floor estimator collapsing, and the input and output levels
    (Problem~\ref{prob:hw}). Added automatic capture-gain calibration and the
    repeated-symbol link diagnostic (\texttt{experiments/diagnose\_link.py}), which
    showed the recording was clipping.
    \item \textbf{Web dashboard:} a self-contained HTML/SVG page generated from the
    measurement exports, showing the whole pipeline, all BER results and the hardware
    measurements (Section~\ref{sec:ui}).
    \item \textbf{Post-mid-term --- two-device tooling, testing and publication:}
    built the two-device tool \texttt{run\_two\_device.py} (transmit, receive, simulate and
    report, with per-frame clock-offset, EVM, BER and PRR logging) and fixed a bug where
    recordings holding several frames lost all but the loudest, by locating every chirp
    before decoding. Ran the simulated two-device sweep
    (script \texttt{run\_two\_device\_sim.py}). Wrote the 28-test suite and the
    GitHub Actions workflow that runs it on every push, extended the dashboard with the
    error-correction and clock-drift results, and recorded the demonstration video.
    \item \textbf{Documentation:} individual mid-term report (Member~3: synchronisation,
    testing and dashboard); in this report, Chapters 5, 6 and 10 (Implementation
    Details, Problems Faced and Solutions, Annexure).
\end{itemize}
"""),
]

PREAMBLE = r"""\documentclass[11pt,a4paper]{report}

\usepackage[utf8]{inputenc}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{setspace}

\hypersetup{
    colorlinks=true,
    linkcolor=blue,
    urlcolor=blue,
    citecolor=blue
}

\titleformat{\chapter}[display]
  {\normalfont\huge\bfseries}{\chaptertitlename\ \thechapter}{20pt}{\Huge}

\pagestyle{fancy}
\fancyhf{}
\rhead{Signal Processing Project Report}
\lhead{\leftmark}
\rfoot{\thepage}
\setlength{\headheight}{14pt}

\graphicspath{{figures/}}
% Anything still to be supplied by the team is printed in red.
\emergencystretch=2em
\newcommand{\fillin}[1]{\textcolor{red}{[#1]}}

\begin{document}
"""

TITLE = r"""
% ===== TITLE PAGE =====
\begin{titlepage}
    \centering
    \vspace*{1cm}

    {\Large \textbf{Indian Institute of Technology Madras}}\\[0.3cm]
    {\large BS Electronic Systems}\\[2cm]

    \rule{\linewidth}{0.5mm}\\[0.5cm]
    {\Huge \textbf{Adaptive Self-Calibrating OFDM-Based Acoustic Communication System}\par}
    \vspace{0.4cm}
    {\Large for Reliable Cross-Device File Transfer}\\
    \rule{\linewidth}{0.5mm}\\[2cm]

    {\large Signal Processing Project Report}\\[2cm]

    \begin{flushleft}
    \textbf{Author:} %%NAME%%\\[0.3cm]
    \textbf{Roll Number:} %%ROLL%%\\[0.3cm]
    \textbf{Project Code (if any):} Custom (self-proposed)\\[0.3cm]
    \textbf{Submission Date:} %%DATE%%\\[0.3cm]
    \textbf{Instructor:} Vishal\\[0.3cm]
    \textbf{Team Members:} %%TEAMBLOCK%%
    \end{flushleft}

    \vfill
\end{titlepage}

% ===== TABLE OF CONTENTS =====
\tableofcontents
\newpage
"""

BODY = r"""
% ===== 1. ABSTRACT =====
\chapter*{Abstract}
\addcontentsline{toc}{chapter}{Abstract}

Consumer devices all have a speaker and a microphone, but no common way to exchange
data through them. We built a software OFDM modem that sends files as sound in the
4--12\,kHz band, using nothing but the device's own audio hardware. The transmitter
maps QPSK symbols onto a Hermitian-symmetric 256-point IFFT, so its output is already
a real audio signal. It adds a cyclic prefix, clips and re-filters the waveform to
lower its peak-to-average power ratio, and prepends a linear chirp. The receiver
band-pass filters the recording and finds the frame with a chirp matched filter.
It then estimates the channel from a reference symbol, tracks it with pilots, and
equalises with an MMSE filter. A self-calibration stage measures the hardware's
frequency response first and transmits only on usable subcarriers. Payloads are
protected by a rate-$\tfrac12$ convolutional code with soft-decision Viterbi
decoding. The receiver estimates the sampling-clock offset between devices from its
pilots and corrects it. Measured AWGN BER matches coherent-QPSK theory. Without
equalisation the multipath channel carries nothing (BER 0.47 at every SNR). At a
100\,ppm clock offset, adaptive tracking gives $3.8\times10^{-3}$ against 0.51 for
one-shot calibration. Self-calibration took the real over-the-air BER from 0.31 to
$8.3\times10^{-3}$. In simulation, the convolutional code delivers 2\,408\,bit/s of
file data and every file intact from 4\,dB SNR, where repetition coding needs 18\,dB.
In a simulated two-device link with independent clocks, the blind receiver measured
the clock offset with a mean error below 5\,ppm at 6\,dB SNR and above, and the
convolutional code recovered every frame exactly down to 0\,dB. Results are published on an
interactive web dashboard.

% ===== 2. INTRODUCTION =====
\chapter{Introduction}

Acoustic data transfer is attractive precisely because it needs no pairing, no
radio and no shared network: any two devices with a speaker and a microphone can
talk. It is also a hard channel. A laptop speaker and microphone in a real room form
a strongly frequency-selective filter with deep nulls; the two devices run from
independent crystals, so their sample clocks disagree; and a speaker is
peak-limited, which penalises the high crest factor of multicarrier signals.
Orthogonal frequency-division multiplexing (OFDM) is the standard answer to
frequency-selective channels in Wi-Fi, LTE and DSL, and this project applies it to
sound.

\section{Motivation}
We chose this project because it exercises nearly every core DSP idea in one working
system: the DFT and its symmetry properties, filtering, correlation and matched
filtering, spectral estimation, and estimation under noise. Every idea can be
checked against real hardware rather than only in simulation. The "adaptive,
self-calibrating" framing comes from a concrete real-world problem: a one-shot
channel estimate is useless between two devices whose sample clocks drift apart.

\section{Scope of the Project}
\textbf{In scope:}
\begin{itemize}
    \item A complete OFDM transmitter and receiver in the 4--12\,kHz audio band.
    \item Pilot-based channel estimation, MMSE equalisation and adaptive tracking.
    \item Self-calibration of the usable band from a measured hardware response.
    \item CRC framing, forward error correction and blind (self-describing) frames.
    \item Sampling-clock-offset estimation and correction.
    \item BER/PRR measurement in simulation and over real audio hardware, and a web
    dashboard presenting the results.
\end{itemize}
\textbf{Out of scope:} inaudible (ultrasonic) operation; multi-user access;
full-duplex links and feedback handshakes; bit-loading and higher-order modulation;
mobile apps. Echo-based distance estimation was prototyped and dropped after the
mid-term review.

% ===== 3. PROBLEM STATEMENT =====
\chapter{Problem Statement}

Transmit an arbitrary file from one device's speaker to a microphone, and recover it
exactly, using OFDM in the 4--12\,kHz band. The receiver must find the frame in a
continuous recording with an unknown delay. It must estimate and equalise a
frequency-selective acoustic channel with nulls up to 43\,dB deep, and remain
correct when transmitter and receiver sample at slightly different rates (a
sampling-clock offset of tens to hundreds of ppm). It must also report bit error
rate (BER) and packet recovery rate (PRR) so each stage's contribution can be
measured.

\textbf{Assumptions and constraints.} Standard 48\,kHz audio hardware with no
special drivers (ALSA \texttt{aplay}/\texttt{arecord} on Linux); a quasi-static
channel over one 6.7\,ms OFDM symbol; a single transmitter at a time; a
speaker-to-microphone distance of a few metres; excess path length under
0.46\,m (the cyclic prefix); and a peak-limited transmitter.

% ===== 4. GOALS AND OBJECTIVES =====
\chapter{Goals and Objectives}

\section{Primary Goal}
To build and measure an adaptive, self-calibrating OFDM modem that reliably transfers
files through ordinary speakers and microphones.

\section{Specific Objectives}
\begin{itemize}
    \item Objective 1 (Phase 1): implement OFDM end to end --- bits $\rightarrow$
    IFFT + cyclic prefix $\rightarrow$ speaker $\rightarrow$ microphone $\rightarrow$
    synchronisation $\rightarrow$ FFT $\rightarrow$ bits --- and validate the measured
    BER against coherent-QPSK theory.
    \item Objective 2 (Phase 2): add pilots, least-squares channel estimation and
    equalisation, and quantify the BER improvement over no equalisation.
    \item Objective 3 (Phase 3): track the channel adaptively from the pilots and show
    where it outperforms one-shot calibration, particularly under sampling-clock offset.
    \item Objective 4: measure the real hardware response and transmit only on usable
    subcarriers (Stage-1 self-calibration).
    \item Objective 5: add forward error correction and characterise long frames under
    clock drift.
    \item Objective 6: test between two separate devices.
    \item Objective 7: publish an interactive dashboard showing the complete signal chain
    and every measurement.
\end{itemize}

% ===== 5. METHODOLOGY =====
\chapter{Methodology}

\section{System Overview}
Figure~\ref{fig:block} shows the end-to-end pipeline. The transmitter packetises the
file, encodes it, maps it onto QPSK subcarriers with pilots, and synthesises a real
audio waveform with a single IFFT per symbol. The receiver synchronises to the chirp,
returns to the frequency domain, estimates and tracks the channel, corrects the
clock offset, equalises and decodes.

\begin{figure}[htbp]
    \centering
    \includegraphics[width=\textwidth]{fig0_block_diagram.png}
    \caption{System architecture block diagram}
    \label{fig:block}
\end{figure}

\section{Signal Processing Techniques Used}

\subsection{Filtering}
\textbf{Receiver front end.} On a real laptop recording, the 0--1\,kHz band (fan,
mains hum, desk rumble) sat 21\,dB \emph{above} the signal band. The first receiver
stage is a 4th-order Butterworth band-pass IIR filter, with edges 15\,\% outside the
4--12\,kHz band. It is applied with \texttt{filtfilt}, i.e.\ forward and backward. The
resulting zero phase matters: an ordinary causal IIR filter would add group delay and
shift the frame timing the synchroniser is about to measure.

\textbf{Peak-to-average power reduction.} After clipping at $\gamma$\,dB above RMS,
the block is transformed with an FFT and every bin outside the occupied band is
zeroed. This is an ideal brick-wall filter applied in the frequency domain. It
removes the out-of-band splatter that clipping creates. Three clip-and-filter
iterations are used.

\textbf{Equalisation} is itself a per-subcarrier filter (Section~\ref{sec:mmse}).

\subsection{Transform-Domain Analysis}
The Discrete Fourier Transform is
\begin{equation}
X[k] = \sum_{n=0}^{N-1} x[n] e^{-j2\pi kn/N}, \quad k = 0, 1, \ldots, N-1
\end{equation}
and OFDM uses its inverse as the modulator: each subcarrier $k$ carries one complex
QPSK symbol $X[k]$ for one symbol period.

\textbf{Real-valued OFDM through Hermitian symmetry.} We place QPSK symbols on bins
$k\in\{22,\ldots,64\}$ of an $N=256$ IFFT at $f_s=48$\,kHz ($\Delta f=187.5$\,Hz, so
4.1--12\,kHz) and set
\begin{equation}
X[N-k] = X^*[k], \qquad X[0]=X[N/2]=0 .
\end{equation}
The IDFT of a Hermitian-symmetric spectrum is purely real, so $x[n]$ is already an
audio-band signal. No complex baseband, mixer or carrier recovery is needed.

\textbf{Cyclic prefix.} Copying the last $L_{cp}=64$ samples to the front of each
symbol makes the channel's linear convolution look circular over the FFT window,
provided the channel impulse response is shorter than the prefix. Each subcarrier
then sees a single complex gain:
\begin{equation}
Y[k] = H[k]\,X[k] + W[k].
\end{equation}

\textbf{Spectral measurement.} The hardware response used for self-calibration is
estimated in the frequency domain from the recorded chirp,
$|H[k]| = |Y[k]|/|X_{\text{chirp}}[k]|$, and averaged over each subcarrier's bin.

\subsection{Additional Techniques}

\textbf{Matched filtering and cross-correlation (synchronisation).} The received
signal is correlated with the known chirp $c[n]$, and the envelope of the result is
taken with the Hilbert transform:
\begin{equation}
r[m] = \left|\mathcal{H}\left\{\sum_n y[n+m]\,c[n]\right\}\right| .
\end{equation}
A 30\,ms sweep over 10\,kHz has a time--bandwidth product near 300. The correlation
peak is therefore about $1/B=0.1$\,ms wide even at 0\,dB SNR, and the envelope makes
timing independent of carrier phase. Detection uses the peak-to-20th-percentile
ratio.

\textbf{Least-squares channel estimation} from the known reference symbol,
$\hat H[k]=Y[k]/X[k]$, followed by a 3-tap moving average across frequency.

\label{sec:mmse}\textbf{MMSE equalisation.}
\begin{equation}
\hat X[k] = \frac{\hat H^*[k]}{|\hat H[k]|^2+\sigma^2}\,Y[k].
\end{equation}
This reduces to $1/\hat H$ where the channel is strong. In a 40\,dB null it does not
amplify the noise by 40\,dB, as zero-forcing would.

\textbf{Adaptive tracking.} At the pilot subcarriers the receiver forms the
correction $C[k]=\hat H_{\text{pilot}}[k]/\hat H[k]$ and fits the physical model
\begin{equation}
C(k) = g\,e^{j(a+bk)}
\end{equation}
by $|\hat H|^2$-weighted least squares, then updates
$\hat H\leftarrow \hat H\,(1-\mu+\mu C)$ with $\mu=0.15$. Here $g$ is a gain change,
$a$ a common phase and $b$ a phase slope across frequency. The slope is the
signature of a timing drift, since a delay of $\tau$ samples rotates subcarrier $k$
by $2\pi k\tau/N$.

\textbf{Sampling-clock-offset estimation.} A relative clock offset $\varepsilon$
slides the FFT window by $\varepsilon L$ samples per symbol ($L=N+L_{cp}=320$). For
each neighbouring pilot pair we form
$Z_n = P_n[i+1]\,P_n^*[i]$, which cancels the common phase. Its angle grows linearly
in the symbol index:
\begin{equation}
\angle Z_n = \phi_0 + \frac{2\pi\,\Delta k\,\varepsilon L}{N}\,n .
\end{equation}
Unwrapping and fitting a line over the frame gives $\varepsilon$, with error falling
as $N_{\text{sym}}^{-3/2}$. The receiver then resamples the recording by
$(1+\varepsilon)$ and decodes again.

\textbf{Forward error correction.} A rate-$\tfrac12$, constraint-length-7
convolutional code with generators $(171,133)_8$ (free distance 10, as in IEEE
802.11a). It is decoded by the Viterbi algorithm with soft inputs, the equalised
in-phase and quadrature values, so weak subcarriers carry proportionally less weight.
A fixed pseudo-random interleaver breaks up the error bursts caused by spectral nulls.

\textbf{Peak-to-average power ratio (PAPR)} is
$\max|x[n]|^2/\mathbb{E}|x[n]|^2$. Clipping to 6\,dB above RMS lowers it from
11.3 to 8.0\,dB.

\section{Theoretical Background}
\begin{itemize}
    \item \textbf{QPSK in AWGN.} With Gray coding, coherent QPSK has bit error
    probability $P_b = Q\left(\sqrt{2E_b/N_0}\right)$, the benchmark for Phase~1
    \cite{proakis}.
    \item \textbf{Circular convolution.} A cyclic prefix at least as long as the channel
    impulse response turns linear convolution into circular convolution, so the DFT
    diagonalises the channel \cite{oppenheim}.
    \item \textbf{Matched filter.} Correlating with the known waveform maximises output
    SNR in white noise, and the resolution of a chirp is set by its bandwidth
    \cite{proakis-dsp}.
    \item \textbf{Clipping and filtering} for OFDM PAPR reduction \cite{armstrong}.
    \item \textbf{Sampling-clock offset} in OFDM appears as a phase rotation
    proportional to subcarrier index and growing with time \cite{speth}.
    \item \textbf{Viterbi decoding} is maximum-likelihood sequence detection on the
    code trellis \cite{viterbi}.
\end{itemize}

% ===== 6. IMPLEMENTATION DETAILS =====
\chapter{Implementation Details}

\section{Tools and Technologies}
\begin{itemize}
    \item \textbf{Programming Language:} Python 3
    \item \textbf{Libraries:} NumPy and SciPy only (all DSP written from scratch); ALSA
    \texttt{aplay}/\texttt{arecord} for audio; Matplotlib only for report figures
    \item \textbf{Platform:} Linux desktop (command line), plus a browser-based live
    demo served from the laptop; the dashboard is plain HTML/SVG with no framework
    \item \textbf{Hosting (if deployed):} GitHub Pages (URL in the Annexure);
    continuous integration with GitHub Actions (28 unit and end-to-end tests)
\end{itemize}

\section{System Architecture}
\label{sec:params}
\begin{table}[htbp]
\centering
\small
\begin{tabular}{|l|l|}
\hline
\textbf{Module} & \textbf{Responsibility} \\
\hline
\texttt{ofdm/config.py} & every system parameter, one source of truth \\
\texttt{ofdm/modem.py} & QPSK map/demap, Hermitian IFFT, cyclic prefix, pilots, chirp, PAPR \\
\texttt{ofdm/sync.py} & matched filter, frame detection, clock-offset estimation \\
\texttt{ofdm/equalizer.py} & LS estimation, adaptive tracking, MMSE equalisation \\
\texttt{ofdm/calibrate.py} & Stage-1 response measurement and subcarrier selection \\
\texttt{ofdm/channel.py} & simulated acoustic channel (multipath, transducers, clock offset) \\
\texttt{ofdm/receiver.py} & scripted receive chain, band-pass front end, BER/EVM \\
\texttt{ofdm/live.py} & blind receiver for self-describing frames, clock correction \\
\texttt{ofdm/framing.py} & CRC packets, headers, repetition FEC, live frame format \\
\texttt{ofdm/conv.py} & convolutional code, soft Viterbi decoder, interleaver \\
\texttt{ofdm/audio\_io.py} & ALSA playback/capture, automatic gain calibration \\
\texttt{experiments/} & every measurement in this report \\
\texttt{live\_server.py} & browser live demo (type a message, hear it, decode it) \\
\texttt{dashboard/}, \texttt{docs/} & results dashboard and its published copy \\
\texttt{tests/} & 28 unit and end-to-end tests \\
\hline
\end{tabular}
\caption{Code modules}
\end{table}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|l|l|l|}
\hline
\textbf{Parameter} & \textbf{Value} & \textbf{Reason} \\
\hline
Sample rate & 48\,kHz & supported by all consumer hardware \\
FFT size $N$ & 256 & 6.67\,ms symbol; channel static across it \\
Cyclic prefix & 64 samples (1.33\,ms) & covers 0.46\,m of excess path \\
Band & 4--12\,kHz & speaker roll-off below, microphone roll-off above \\
Subcarriers & 43 = 31 data + 12 pilot & pilot every 4th, both edges pinned \\
Modulation & QPSK, Gray coded & 2 bits per subcarrier \\
Raw payload rate & 9\,300\,bit/s & 62 bits per symbol \\
Preamble & 30\,ms chirp, 3--13\,kHz & sync and channel sounding \\
FFT-window backoff & 8 samples & below $N/(2\cdot 4)=32$ aliasing limit \\
Tracker step size $\mu$ & 0.15 & from the step-size sweep \\
\hline
\end{tabular}
\caption{System parameters}
\end{table}

\section{Key Algorithms / Pseudocode}

\textbf{Transmitter: Hermitian IFFT with cyclic prefix} (\texttt{modem.py}):
\begin{verbatim}
def grid_to_time(grid, cfg):
    spec = np.zeros((n_sym, cfg.nfft), dtype=complex)
    spec[:, used] = grid                      # QPSK + pilots on bins 22..64
    spec[:, cfg.nfft - used] = np.conj(grid)  # Hermitian symmetry
    x = np.fft.ifft(spec, axis=1).real * cfg.nfft
    return np.concatenate([x[:, -cfg.ncp:], x], axis=1).ravel()  # add CP
\end{verbatim}

\textbf{Receiver: blind decode with clock correction} (\texttt{live.py}):
\begin{verbatim}
def demodulate_blind(rx, cfg):
    rxf   = bandpass(rx, cfg)                    # zero-phase Butterworth
    frame = find_frame(rxf, cfg)                 # chirp matched filter
    out   = decode(rxf, frame.start)             # FFT, LS, track, MMSE, FEC
    ppm   = estimate_clock_ppm(out.grid[:1 s])   # pilot phase-slope fit
    if abs(ppm) * n_symbols * L > 3 samples:     # drift would matter
        rx2  = resample(rxf, 1 + ppm * 1e-6)     # onto the TX clock
        out2 = decode(rx2, frame.start)
        out  = better_of(out, out2)              # by packets recovered
    return out
\end{verbatim}

\textbf{Clock-offset estimator} (\texttt{sync.py}):
\begin{verbatim}
P = grid[1:, pilots] / pilot_values          # [symbol, pilot]
Z = P[:, 1:] * np.conj(P[:, :-1])            # neighbouring-pilot products
for each pair i:
    rate[i] = polyfit(n, unwrap(angle(Z[:, i])), 1).slope / dk[i]
eps = weighted_mean(rate, |Z|) / (2*pi*L/N)
\end{verbatim}

\textbf{Soft-decision Viterbi} (\texttt{conv.py}), vectorised over the 64 trellis
states:
\begin{verbatim}
for t in range(n_steps):
    bm   = BRANCH @ soft[t]          # correlation metric, [state, pred]
    cand = pm[PRED] + bm
    x    = argmax(cand, axis=1)      # survivor choice per state
    decisions[t] = x
    pm   = cand[states, x]
# trace back from state 0 (6 tail bits force the trellis there)
\end{verbatim}

\section{User Interface}
\label{sec:ui}
Results are published as an interactive dashboard on GitHub Pages (URL in the
Annexure). The page is built from
\texttt{dashboard/data.json}, which is exported directly from the experiment
scripts, so no number on it is typed by hand. It shows the project status, the
headline metrics, the complete signal chain (Figure~\ref{fig:uipipe}), every BER
experiment with hover tooltips and data tables, the real hardware measurements, and
the error-correction and clock-drift results. It works in light and dark themes and
on phones. A separate live demo (\texttt{live\_server.py}) lets a user type a
message in the browser, hear it played, and watch it decoded from the microphone,
including from a second device on the same Wi-Fi.

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.95\textwidth]{fig7_dashboard_top.png}
    \caption{Dashboard: project status and headline metrics}
\end{figure}

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.95\textwidth]{fig8_dashboard_pipeline.png}
    \caption{Dashboard: the signal chain end to end, one stage per panel}
    \label{fig:uipipe}
\end{figure}

% ===== 7. PROBLEMS FACED AND SOLUTIONS =====
\chapter{Problems Faced and Solutions}

\section{Problem 1: The synchroniser could not find the chirp}
\label{prob:chirp}
\textbf{Issue:} The recovered BER was 0.49 with no obvious cause. The matched filter
was locking onto random correlation inside the payload.

\textbf{Solution:} The whole frame had been normalised by its global peak. OFDM has
a crest factor of about 9\,dB and the chirp about 3\,dB, so the chirp came out 6\,dB
too quiet. Normalising the preamble and the payload separately raised detection
confidence from $8.6\times$ to $121\times$ the noise floor. Timing became
sample-exact down to 0\,dB SNR.

\section{Problem 2: Pilot interpolation aliased}
\label{prob:alias}
\textbf{Issue:} Channel estimates were nonsense even at high SNR.

\textbf{Solution:} Starting the FFT window $D$ samples early rotates the apparent
channel by $2\pi D/N$ per subcarrier. Pilot interpolation only works while the
rotation between adjacent pilots stays under $\pi$, i.e.\
$D<N/(2\cdot\text{pilot spacing})=32$. The first backoff was exactly 32; the measured
rotation was $184^\circ$ between pilots. Reducing the backoff to 8 samples fixed it.
The synchroniser's timing choice turned out to set a hard constraint on the channel
estimator's pilot spacing.

\section{Problem 3: Adaptive tracking made the link worse}
\label{prob:track}
\textbf{Issue:} Replacing the channel estimate with the pilot-interpolated one each
symbol raised BER from $3\times10^{-4}$ to $10^{-1}$. It did not improve with SNR,
so it was systematic.

\textbf{Solution:} That update discards a 43-subcarrier reference estimate for 12
pilots interpolated across spectral nulls. Instead we track a smooth multiplicative
correction fitted to a two-parameter physical model (gain and phase slope), leaving
the null structure from the reference symbol intact. Piecewise interpolation of the
correction was tried first and left a $10^{-2}$ floor; the parametric fit removed it.

\section{Problem 4: Real hardware failures that looked like DSP bugs}
\label{prob:hw}
\textbf{Issue:} Over the air the receiver locked onto the wrong place, or decoded
nothing.

\textbf{Solution:} Four separate faults. (i) The ALSA capture device emits a
full-scale 10\,ms click at start-up, 30\,dB above the signal; the first 250\,ms are
now blanked. (ii) A similar transient at capture stop; a tail guard was added.
(iii) The noise-floor estimate collapsed once the search window narrowed; a
20th-percentile estimate replaced the median. (iv) The microphone gain was 34\,dB
down, and on one occasion the speaker was muted. Capture gain is now calibrated
automatically before every transmission. A repeated-symbol diagnostic separated
noise, distortion and receiver bugs, and showed the recording was clipping.

\section{Problem 5: A third of the band was unusable}
\textbf{Issue:} Over the air, the uncoded BER was stuck at 0.31 and no equaliser
tuning moved it.

\textbf{Solution:} Measuring the real speaker + microphone + room response with the
chirp showed 43\,dB of variation across the band, with nulls 35--43\,dB deep between
6.5 and 9\,kHz. No equaliser can recover a subcarrier in such a null. Stage-1
self-calibration measures the response first and transmits only on subcarriers
within a backoff of the strongest. With 8\,dB backoff the BER fell to
$8.3\times10^{-3}$.

\section{Problem 6: Repetition coding had an error floor}
\textbf{Issue:} One bit error destroys a 72-byte packet, so uncoded frames failed
even in simulation. Repetition-3 helped but its decoded BER stopped at
$5\times10^{-3}$ at every SNR, and it spent two-thirds of the airtime on redundancy.

\textbf{Solution:} Block-tiled copies of a bit can land on the same faded subcarrier,
so all three copies fail together. We replaced it with an interleaved rate-$\tfrac12$
convolutional code decoded by soft-decision Viterbi (Section~\ref{sec:fec}).

\section{Problem 7: Long frames broke under clock drift}
\textbf{Issue:} Frames longer than about 2.5\,s failed at clock offsets of 200\,ppm
or more, even though adaptive tracking handles the phase rotation. Failures were
asymmetric: $+200$\,ppm failed while $-200$\,ppm survived.

\textbf{Solution:} The FFT window slides $\varepsilon L$ samples per symbol. It
starts 8 samples inside the 64-sample prefix, so it has 56 samples of margin in one
direction but only 8 in the other before symbols overlap. We added a clock-offset
estimator and a resample-and-redecode pass. The first estimator differenced
adjacent symbols and was off by tens of ppm (it read $+80$\,ppm as $-34$). Fitting a
line over the whole frame cut the error to a few ppm.

% ===== 8. RESULTS AND DISCUSSION =====
\chapter{Results and Discussion}

\section{Experimental Setup}
\begin{itemize}
    \item \textbf{Simulation.} A known channel lets BER be measured exactly: sparse
    multipath (direct path and three reflections within 1\,ms), a band-pass FIR for the
    transducers, additive white noise at a set SNR, and sampling-clock offset by
    resampling. Each SNR point in a sweep sees the same set of rooms. BER experiments
    use 16 trials $\times$ 6\,200 bits per point (about 99\,000 bits).
    \item \textbf{Hardware.} A laptop speaker to the same laptop's microphone via ALSA at
    48\,kHz, carrying a 293-byte text file.
    \item \textbf{Two devices (simulated).} The blind receiver of the two-device test,
    run through the channel model with the transmitter's clock offset by $-150$, $-50$,
    $+50$ and $+150$\,ppm, at SNRs from 15 to 0\,dB, carrying a 197-byte message with
    either code (script \texttt{run\_two\_device\_sim.py}). A hardware test
    between two separate physical devices was not carried out.
    \item \textbf{Metrics.} Bit error rate (BER), packet recovery rate (PRR, share of
    72-byte packets passing CRC), error-vector magnitude (EVM), exact-file recovery,
    and clock-offset estimation error.
\end{itemize}

\section{Quantitative Results}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|c|c|c|}
\hline
\textbf{SNR} & \textbf{Measured BER} & \textbf{QPSK theory} \\
\hline
0\,dB & $7.32\times10^{-2}$ & $7.86\times10^{-2}$ \\
2\,dB & $3.56\times10^{-2}$ & $3.75\times10^{-2}$ \\
4\,dB & $1.20\times10^{-2}$ & $1.25\times10^{-2}$ \\
6\,dB & $3.30\times10^{-3}$ & $2.39\times10^{-3}$ \\
8\,dB & $4.03\times10^{-4}$ & $1.91\times10^{-4}$ \\
10\,dB & $3.02\times10^{-5}$ & $3.87\times10^{-6}$ \\
$\geq$12\,dB & 0 errors in 99\,200 bits & --- \\
\hline
\end{tabular}
\caption{Phase 1: AWGN BER against coherent-QPSK theory}
\end{table}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|c|c|c|c|}
\hline
\textbf{SNR} & \textbf{No equalisation} & \textbf{Static} & \textbf{Adaptive} \\
\hline
0\,dB & $4.73\times10^{-1}$ & $1.21\times10^{-1}$ & $1.29\times10^{-1}$ \\
6\,dB & $4.69\times10^{-1}$ & $3.80\times10^{-2}$ & $3.94\times10^{-2}$ \\
12\,dB & $4.67\times10^{-1}$ & $1.21\times10^{-2}$ & $1.28\times10^{-2}$ \\
18\,dB & $4.68\times10^{-1}$ & $4.58\times10^{-3}$ & $4.83\times10^{-3}$ \\
30\,dB & $4.68\times10^{-1}$ & $3.63\times10^{-3}$ & $3.62\times10^{-3}$ \\
\hline
\end{tabular}
\caption{Phase 2: BER over the multipath channel by equaliser mode}
\end{table}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|c|c|c|}
\hline
\textbf{Clock offset} & \textbf{Static calibration} & \textbf{Adaptive tracking} \\
\hline
0\,ppm & $4.47\times10^{-3}$ & $4.54\times10^{-3}$ \\
25\,ppm & $5.40\times10^{-2}$ & $4.02\times10^{-3}$ \\
50\,ppm & $2.20\times10^{-1}$ & $3.68\times10^{-3}$ \\
\textbf{100\,ppm} & $\mathbf{5.14\times10^{-1}}$ & $\mathbf{3.79\times10^{-3}}$ \\
200\,ppm & $5.14\times10^{-1}$ & $4.63\times10^{-3}$ \\
400\,ppm & $5.00\times10^{-1}$ & $1.05\times10^{-2}$ \\
800\,ppm & $5.02\times10^{-1}$ & $1.10\times10^{-1}$ \\
\hline
\end{tabular}
\caption{Phase 3: BER under sampling-clock offset}
\end{table}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{Clipping limit} & \textbf{PAPR} & \textbf{Avg power} & \textbf{BER @ 8\,dB} & \textbf{BER @ 14\,dB} \\
\hline
none & 11.3\,dB & +0.0\,dB & $1.9\times10^{-4}$ & 0 \\
8\,dB above RMS & 9.2\,dB & +2.1\,dB & $1.3\times10^{-4}$ & 0 \\
\textbf{6\,dB above RMS} & \textbf{8.0\,dB} & \textbf{+3.3\,dB} & $\mathbf{3.2\times10^{-4}}$ & \textbf{0} \\
4\,dB above RMS & 7.1\,dB & +4.2\,dB & $2.6\times10^{-3}$ & $5.4\times10^{-5}$ \\
\hline
\end{tabular}
\caption{Peak-to-average power reduction trade-off}
\label{tab:papr}
\end{table}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|l|c|c|}
\hline
\textbf{Configuration} & \textbf{BER} & \textbf{Packets} \\
\hline
Full band, no calibration & $3.1\times10^{-1}$ & 0/5 \\
Stage 1, 12\,dB backoff & $8.7\times10^{-2}$ & 0/5 \\
Stage 1, 8\,dB backoff & $8.3\times10^{-3}$ & 1/5 \\
+ repetition-3 & $1.8\times10^{-2}\rightarrow1.9\times10^{-3}$ coded & 3/5 \\
+ repetition-5 & $5.2\times10^{-2}\rightarrow6.4\times10^{-4}$ coded & 4/5 \\
Best run (repetition-3, 8\,dB) & $1.2\times10^{-2}\rightarrow3.2\times10^{-4}$ coded & 4/5 \\
\hline
\end{tabular}
\caption{Over the air on real hardware (one laptop, speaker to microphone)}
\end{table}

\label{sec:fec}
\begin{table}[htbp]
\centering
\footnotesize
\begin{tabular}{|l|c|c|c|c|c|c|}
\hline
\textbf{Scheme} & \textbf{Air time} & \textbf{bit/s} & \textbf{BER, 0\,dB} & \textbf{BER, 2\,dB} & \textbf{BER, 6\,dB} & \textbf{All intact} \\
\hline
Uncoded & 0.63\,s & 3\,701 & $9.0\times10^{-2}$ & $5.9\times10^{-2}$ & $2.4\times10^{-2}$ & never \\
Repetition-3 & 1.31\,s & 1\,794 & $3.8\times10^{-2}$ & $2.0\times10^{-2}$ & $7.9\times10^{-3}$ & from 18\,dB \\
\textbf{Conv.\ rate $\tfrac12$} & \textbf{0.97\,s} & \textbf{2\,408} & $\mathbf{3.4\times10^{-3}}$ & $\mathbf{1.6\times10^{-4}}$ & \textbf{0} & \textbf{from 4\,dB} \\
\hline
\end{tabular}
\caption{Forward error correction: 293-byte file, simulated room with 80\,ppm clock
offset, 8 paired trials per point}
\end{table}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|l|c|c|c|c|c|c|c|}
\hline
\textbf{Frame} & $-400$ & $-200$ & $-100$ & 0 & $+100$ & $+200$ & $+400$\,ppm \\
\hline
2.67\,s, uncorrected & 33\,\% & 100\,\% & 100\,\% & 100\,\% & 100\,\% & 67\,\% & 0\,\% \\
2.67\,s, corrected & 100\,\% & 100\,\% & 100\,\% & 100\,\% & 100\,\% & 100\,\% & 100\,\% \\
4.89\,s, uncorrected & 0\,\% & 100\,\% & 100\,\% & 100\,\% & 100\,\% & 0\,\% & 0\,\% \\
4.89\,s, corrected & 100\,\% & 100\,\% & 100\,\% & 100\,\% & 100\,\% & 100\,\% & 100\,\% \\
\hline
\end{tabular}
\caption{Frames recovered exactly under clock offset, with and without correction
(simulated, 18\,dB SNR, 3 trials per cell)}
\end{table}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|c|c|c|}
\hline
\textbf{Frame length} & \textbf{Mean absolute error} & \textbf{Worst error} \\
\hline
0.62\,s & 21\,ppm & 31\,ppm \\
1.18\,s & 7\,ppm & 23\,ppm \\
2.67\,s & 5\,ppm & 11\,ppm \\
4.89\,s & 4\,ppm & 9\,ppm \\
\hline
\end{tabular}
\caption{Clock-offset estimation accuracy over offsets from $-400$ to $+400$\,ppm}
\end{table}

\begin{table}[htbp]
\centering
\small
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{Code (frame length)} & \textbf{SNR} & \textbf{Frames decoded} & \textbf{Exact} & \textbf{Mean clock-estimate error} \\
\hline
Repetition-3 (1.18\,s) & 15\,dB & 4/4 & 4/4 & 4.7\,ppm \\
 & 10\,dB & 4/4 & 4/4 & 1.7\,ppm \\
 & 6\,dB & 4/4 & 4/4 & 4.7\,ppm \\
 & 3\,dB & 4/4 & 4/4 & 25.6\,ppm \\
 & 0\,dB & 4/4 & 1/4 & 73.0\,ppm \\
\hline
Convolutional (0.93\,s) & 15\,dB & 4/4 & 4/4 & 2.2\,ppm \\
 & 10\,dB & 4/4 & 4/4 & 2.1\,ppm \\
 & 6\,dB & 4/4 & 4/4 & 3.6\,ppm \\
 & 3\,dB & 4/4 & 4/4 & 24.2\,ppm \\
 & 0\,dB & 4/4 & \textbf{4/4} & 127.8\,ppm \\
\hline
\end{tabular}
\caption{Simulated two-device link: blind receiver, transmitter clock offset by
$\pm50$ and $\pm150$\,ppm, 197-byte message (\texttt{results/two\_device\_sim.json})}
\end{table}

\clearpage
\section{Qualitative Results}

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.95\textwidth]{fig1_chain.png}
    \caption{Signal chain: transmitted frame, microphone recording, chirp matched-filter
    output and transmit spectrum}
\end{figure}

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.95\textwidth]{fig2_ber.png}
    \caption{BER curves: AWGN against theory, equaliser comparison and clock offset}
\end{figure}

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.95\textwidth]{fig3_const.png}
    \caption{Equalised constellations}
\end{figure}

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.8\textwidth]{fig4_fec.png}
    \caption{Decoded BER by FEC scheme (hollow markers: zero errors)}
\end{figure}

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.8\textwidth]{fig5_drift.png}
    \caption{Exact frame recovery against clock offset, 4.89\,s frames}
\end{figure}

\begin{figure}[htbp]
    \centering
    \includegraphics[width=0.55\textwidth]{fig6_clock_estimate.png}
    \caption{Estimated against true clock offset}
\end{figure}

\clearpage
\section{Discussion}
\begin{itemize}
    \item \textbf{Theory is met where it should be.} On AWGN, measured BER sits on the
    QPSK curve from 0 to 8\,dB. The small excess at high SNR is the deliberate clipping
    distortion from PAPR reduction, which buys 3.3\,dB of transmit power.
    \item \textbf{Equalisation is the link, not an optimisation.} Without it, BER stays
    at 0.47 at every SNR: the room's frequency selectivity, not noise, destroys the
    constellation. The equalised floor near $3.6\times10^{-3}$ is set by spectral nulls,
    which is why error correction mattered so much.
    \item \textbf{Adaptive tracking earns its place only when the channel moves.} On a
    fixed channel it matches static calibration exactly, so it costs nothing. Under an
    ordinary 100\,ppm clock offset, static calibration fails completely and tracking
    holds the link: a $135\times$ improvement.
    \item \textbf{Measuring the hardware mattered more than any receiver refinement.}
    Stage-1 self-calibration gave a $37\times$ BER improvement over the air; no
    equaliser change came close.
    \item \textbf{A standard code beats an ad-hoc one.} The convolutional code is 34\,\%
    faster than repetition-3 and needs about 14\,dB less SNR to deliver every file
    intact. Soft decisions and interleaving are essential to that.
    \item \textbf{Two-device result (simulated).} With independent transmitter and
    receiver clocks, the blind receiver measured the offset with a mean error under
    5\,ppm at 6\,dB SNR and above; at 3\,dB and below the estimate degrades to tens of
    ppm, although decoding still succeeds. The convolutional code recovered all four
    frames exactly even at 0\,dB, where repetition-3 recovered one. The same test between
    two physical devices was not carried out, so the clock-offset result is verified in
    simulation and on a single laptop only.
    \item \textbf{Limitations of the evidence.} The convolutional-code and drift-correction
    results are from simulation. The single-laptop hardware tests share one clock. Run-to-run
    variation over the air is significant, because the acoustic path changes with room
    noise and device placement.
\end{itemize}

% ===== 9. CONCLUSIONS =====
\chapter{Conclusions}

\section{Summary of Contributions}
We built a complete, from-scratch OFDM acoustic modem and measured every stage of
it. The measurements show that equalisation is essential over a real acoustic
channel, and that one-shot calibration fails at ordinary cross-device clock offsets
where adaptive tracking works. Measuring the hardware response first was the single
largest improvement on real hardware. An interleaved convolutional code with
soft-decision decoding, plus pilot-based clock-offset correction, make the link both
faster and far more robust in simulation. A simulated two-device link confirms that
the receiver measures the clock offset between independent devices and decodes
blind; the same test on two physical devices remains to be done.

\section{Limitations}
\begin{itemize}
    \item The strongest results (convolutional code, drift correction) are verified in
    simulation; neither they nor a link between two physical devices have been tested
    over the air.
    \item Every subcarrier uses QPSK, so weak subcarriers are discarded rather than
    loaded with fewer bits; the uncoded equalised error floor remains.
    \item Throughput is about 2.4\,kbit/s of file data: suitable for text and small
    files only.
    \item The 4--12\,kHz band is audible, and performance depends strongly on volume,
    distance and room noise.
    \item Calibration assumes both ends can be configured together; there is no
    feedback channel.
\end{itemize}

\section{Future Work}
\begin{itemize}
    \item \textbf{Bit-loading:} BPSK on weak subcarriers and 16-QAM on strong ones,
    driven by the Stage-1 measurement, to remove the error floor and raise throughput.
    \item \textbf{Decision-directed tracking} between pilots for more tracking bandwidth
    without extra overhead.
    \item \textbf{A feedback handshake} so the receiver can report its chosen subcarrier
    set to the transmitter.
    \item \textbf{A mobile implementation} of the receiver, so a phone can decode as
    well as transmit.
\end{itemize}

% ===== 10. INDIVIDUAL CONTRIBUTION =====
\chapter{Individual Contribution}

This was a three-member group project (%%TEAM%%). The work was divided by module;
integration debugging and the experiment scripts were shared. My own contribution
(%%NAME%%, %%ROLE%%):

%%INDIVIDUAL%%

% ===== 11. ANNEXURE =====
\chapter{Annexure}

\section*{Important: Access Permissions}
\textbf{All linked files must have ``Anyone with the link'' access. If files are inaccessible during evaluation, no marks will be awarded for those components.}

\section{Video Demonstration}
\textbf{Video link:} \url{https://rukadeakshay01.github.io/acoustic-ofdm/demo.html}

The page plays a 2-minute screen recording (test suite, simulated file transfer with
the convolutional code, simulated two-device receiver, dashboard walkthrough) and
includes an audio clip of a real transmitted frame. The recording has no voice-over,
and no hardware is shown; the hardware results are presented on the dashboard.

The video should clearly demonstrate:
\begin{itemize}
    \item The working application/system end-to-end
    \item Key features and outputs
    \item Any hardware involved (if applicable)
    \item Brief walkthrough of the UI
\end{itemize}

\section{Source Code}
\textbf{ZIP file:}\\
\url{https://github.com/RukadeAkshay01/acoustic-ofdm/archive/refs/heads/main.zip}

\textbf{GitHub repository:} \url{https://github.com/RukadeAkshay01/acoustic-ofdm}

The ZIP file should contain:
\begin{itemize}
    \item All source code files (organized in folders)
    \item \texttt{README.md} with setup and run instructions
    \item \texttt{requirements.txt} or equivalent dependency list
    \item Sample input data (if applicable)
\end{itemize}

\section{Live Deployment (if applicable)}
\textbf{App URL:} \url{https://rukadeakshay01.github.io/acoustic-ofdm/}

% ===== REFERENCES =====
\chapter*{References}
\addcontentsline{toc}{chapter}{References}

\begin{enumerate}
    \item \label{oppenheim} A. V. Oppenheim and R. W. Schafer, \textit{Discrete-Time Signal Processing}, 3rd ed., Pearson, 2010.
    \item \label{proakis-dsp} J. G. Proakis and D. G. Manolakis, \textit{Digital Signal Processing: Principles, Algorithms, and Applications}, 4th ed., Pearson, 2007.
    \item \label{proakis} J. G. Proakis and M. Salehi, \textit{Digital Communications}, 5th ed., McGraw-Hill, 2008.
    \item \label{armstrong} J. Armstrong, ``Peak-to-average power reduction for OFDM by repeated clipping and frequency domain filtering,'' \textit{Electronics Letters}, vol. 38, no. 5, pp. 246--247, 2002.
    \item \label{speth} M. Speth, S. A. Fechtel, G. Fock and H. Meyr, ``Optimum receiver design for wireless broad-band systems using OFDM---Part I,'' \textit{IEEE Trans. Communications}, vol. 47, no. 11, pp. 1668--1677, 1999.
    \item \label{viterbi} A. J. Viterbi, ``Error bounds for convolutional codes and an asymptotically optimum decoding algorithm,'' \textit{IEEE Trans. Information Theory}, vol. 13, no. 2, pp. 260--269, 1967.
    \item IEEE Std 802.11a-1999, \textit{Wireless LAN Medium Access Control (MAC) and Physical Layer (PHY) specifications: High-speed Physical Layer in the 5 GHz Band}.
\end{enumerate}

\end{document}
"""


def cite_numbers(tex):
    """Resolve \\cite{key} to the reference list's numbers, [n]."""
    import re
    refs = re.search(r"\\chapter\*\{References\}.*", tex, re.S).group(0)
    order = re.findall(r"\\item \\label\{([^}]+)\}", refs)
    num = {k: i + 1 for i, k in enumerate(order)}
    tex = re.sub(r"\\cite\{([^}]+)\}", lambda m: "[" + ", ".join(
        str(num[k.strip()]) for k in m.group(1).split(",")) + "]", tex)
    return re.sub(r"\\item \\label\{[^}]+\} ", r"\\item ", tex)


def main():
    for m in MEMBERS:
        tex = PREAMBLE + TITLE + BODY
        for key, val in (("%%NAME%%", m["name"]), ("%%TEAMBLOCK%%", TEAM_BLOCK), ("%%TEAM%%", TEAM),
                         ("%%ROLL%%", ROLL[m["name"]]), ("%%DATE%%", SUBMISSION_DATE),
                         ("%%ROLE%%", m["role"]), ("%%INDIVIDUAL%%", m["individual"].strip())):
            tex = tex.replace(key, val)
        tex = cite_numbers(tex)
        path = os.path.join(HERE, f"SP_Final_Report_{m['slug']}.tex")
        with open(path, "w") as f:
            f.write(tex)
        print("wrote", os.path.relpath(path, os.path.dirname(os.path.dirname(HERE))))


if __name__ == "__main__":
    main()
