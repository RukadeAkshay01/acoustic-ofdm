#!/usr/bin/env python3
"""
Live demo server: type a message in the browser, hear it go through the
speaker, watch the receiver decode it from the microphone.

    python3 live_server.py            # then open http://localhost:8765/

Only the Python standard library plus the project's own numpy/scipy code is
used - no Flask, no extra packages.  Three ways to use it:

  loopback   this laptop plays AND records          (Phase 1/2 demo)
  receive    this laptop records; another device    (two-device test)
             opens the same page over Wi-Fi and plays the frame from its
             own speaker (or a second laptop runs `--play`)
  transmit   this laptop plays only; a second laptop runs the server in
             listen mode and decodes

The receiver is always blind: it learns the message length and FEC factor
from the CRC-protected header carried in the sound (ofdm/live.py).
"""
import argparse
import dataclasses
import json
import os
import socket
import sys
import threading
import time
import traceback
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ofdm.config import OFDMConfig, DEFAULT               # noqa: E402
from ofdm import modem, audio_io, calibrate, live         # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(ROOT, "dashboard", "live.html")

STATE = dict(cfg=DEFAULT, calib=None, jobs={}, busy=False)
LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def dec(x, n):
    """Decimate an array to at most n points (peak-preserving for waveforms)."""
    x = np.asarray(x, dtype=float).ravel()
    if x.size <= n:
        return [round(float(v), 4) for v in x]
    k = int(np.ceil(x.size / n))
    m = x[: x.size // k * k].reshape(-1, k)
    # keep the extreme of each bucket so waveform envelopes survive
    idx = np.argmax(np.abs(m), axis=1)
    return [round(float(v), 4) for v in m[np.arange(m.shape[0]), idx]]


def lan_addresses():
    addrs = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        addrs.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = a[4][0]
            if not ip.startswith("127."):
                addrs.add(ip)
    except socket.gaierror:
        pass
    return sorted(addrs)


def cfg_json(cfg: OFDMConfig):
    return dict(fs=cfg.fs, nfft=cfg.nfft, ncp=cfg.ncp, f_low=cfg.f_low,
                f_high=cfg.f_high, n_data=int(len(cfg.payload_bins)),
                n_pilot=int(len(cfg.pilot_bins)), bitrate=cfg.raw_bitrate,
                symbol_ms=cfg.sym_dur * 1e3, df=cfg.df,
                calibrated=bool(cfg.active_bins))


def pack_result(r, x=None, cfg=DEFAULT, repeat=3, t_ms=None, source=""):
    """Turn the receiver's numpy output into small JSON the page can draw."""
    out = dict(ok=bool(r["ok"]), reason=r.get("reason", ""), stage=r["stage"],
               source=source, config=cfg_json(cfg), time_ms=t_ms)
    rx = np.asarray(r["rx"], dtype=float)
    out["rx_wave"] = dec(rx, 1200)
    out["rx_peak"] = round(float(np.max(np.abs(rx))) if rx.size else 0.0, 3)
    out["rx_seconds"] = round(rx.size / cfg.fs, 2)
    if x is not None:
        out["tx_wave"] = dec(x, 1200)
        out["tx_seconds"] = round(len(x) / cfg.fs, 2)
    if r.get("sync"):
        env = np.asarray(r["sync"]["env"])
        out["sync"] = dict(env=dec(env, 1200), peak=int(r["sync"]["peak"]),
                           n=int(env.size), confidence=round(r["sync"]["confidence"], 1),
                           start=int(r.get("start", 0)))
    # received spectrum over the frame (or the whole capture if no frame)
    start = int(r.get("start", 0))
    seg = rx[start:start + 8192] if rx.size - start >= 8192 else rx[-8192:]
    if seg.size >= 1024:
        n = 1 << int(np.log2(seg.size))
        S = np.abs(np.fft.rfft(seg[:n] * np.hanning(n)))
        f = np.fft.rfftfreq(n, 1 / cfg.fs)
        m = f <= 16000
        out["spec_f"] = dec(f[m], 400)
        out["spec_db"] = dec(20 * np.log10(S[m] / (S[m].max() or 1) + 1e-12), 400)
    if "H" in r:
        H = np.asarray(r["H"])
        out["H_f"] = [round(float(v), 1) for v in cfg.data_bins * cfg.df]
        out["H_db"] = [round(float(v), 2) for v in 20 * np.log10(np.abs(H) + 1e-9)]
        out["H_deg"] = [round(float(v), 1) for v in np.degrees(np.angle(H))]
    if "grid_raw" in r and "symbols" in r:
        pay_pos = np.searchsorted(cfg.data_bins, cfg.payload_bins)
        raw = np.asarray(r["grid_raw"])[1:, pay_pos].ravel()[:1200]
        raw = raw / (np.mean(np.abs(raw)) or 1) / np.sqrt(2)
        eq = np.asarray(r["symbols"]).ravel()[:1200]
        eq = eq / (np.mean(np.abs(eq)) or 1) / np.sqrt(2)
        out["const_raw"] = [[round(float(v.real), 3), round(float(v.imag), 3)] for v in raw]
        out["const_eq"] = [[round(float(v.real), 3), round(float(v.imag), 3)] for v in eq]
    if "evm_db" in r and np.isfinite(r["evm_db"]):
        out["evm_db"] = round(float(r["evm_db"]), 2)
    if "cpe" in r:
        out["cpe_deg"] = [round(float(v), 2) for v in np.degrees(np.unwrap(r["cpe"]))]
    if r.get("header"):
        out["header"] = r["header"]
        out["text"] = r["data"].decode("utf-8", errors="replace")
        out["nbytes_rx"] = len(r["data"])
        out["prr"] = round(float(r["prr"]), 4)
        out["packets"] = [bool(g) for g in r["good"]]
        out["n_sym"] = int(r.get("n_sym", 0))
        out["truncated"] = bool(r.get("truncated", False))
    if "raw_ber" in r:
        out["raw_ber"] = float(r["raw_ber"])
        out["raw_errs"] = int(r["raw_errs"])
        out["raw_bits"] = int(r["raw_bits"])
    if "erased" in r:
        out["erased"] = int(r["erased"])
    out["repeat"] = repeat
    return out


def do_calibrate(backoff_db):
    cfg0 = DEFAULT
    probe_bits = np.random.default_rng(0).integers(0, 2, 2000).astype(np.int8)
    probe_wave, _ = modem.modulate(probe_bits, cfg0)
    vol, pk, glog = audio_io.find_capture_gain(probe_wave, cfg0.fs, target_peak=0.45)
    probe = modem.sync_chirp(cfg0) * cfg0.amplitude
    rx_probe, _ = audio_io.loopback(probe, cfg0.fs)
    cfg, rep = calibrate.calibrated_config(rx_probe, cfg0, backoff_db=backoff_db,
                                           skip_s=audio_io.STARTUP_GUARD_S)
    db = np.asarray(rep["bin_db"], dtype=float)
    calib = dict(
        capture_volume=vol, capture_peak=round(float(pk), 3),
        gain_log=[[int(v), round(float(p), 3)] for v, p in glog],
        dynamic_range_db=round(float(rep["dynamic_range_db"]), 1),
        kept=int(len(rep["kept"])), total=int(len(rep["bins"])),
        backoff_db=backoff_db,
        resp_f=[round(float(v), 1) for v in np.asarray(rep["bins"]) * cfg0.df],
        resp_db=[round(float(v), 2) for v in db - db.max()],
        kept_f=[round(float(v), 1) for v in np.asarray(rep["kept"]) * cfg0.df],
        ir=dec(np.real(rep["ir"]), 400),
        config=cfg_json(cfg),
    )
    return cfg, calib


def pick_cfg(use_calib):
    return STATE["cfg"] if (use_calib and STATE["cfg"].active_bins) else DEFAULT


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------
def new_job(**kw):
    jid = uuid.uuid4().hex[:8]
    job = dict(id=jid, state="new", created=time.time(), result=None, error=None, **kw)
    STATE["jobs"][jid] = job
    # keep the table small
    for k in sorted(STATE["jobs"], key=lambda k: STATE["jobs"][k]["created"])[:-20]:
        STATE["jobs"].pop(k, None)
    return job


def run_capture(job, seconds, mode):
    """Background thread: record, then decode blind."""
    try:
        job["state"] = "recording"
        t0 = time.time()
        rx, _ = audio_io.record(seconds, DEFAULT.fs)
        job["state"] = "decoding"
        r = live.demodulate_blind(rx, job["cfg"], mode=mode,
                                  skip_s=audio_io.STARTUP_GUARD_S,
                                  tx_bits=job.get("bits"))
        job["result"] = pack_result(r, job.get("x"), job["cfg"], job.get("repeat", 3),
                                    round((time.time() - t0) * 1e3), source=job["source"])
        job["state"] = "done"
    except Exception as e:                       # report, never crash the server
        job["error"] = f"{type(e).__name__}: {e}"
        job["state"] = "failed"
        traceback.print_exc()
    finally:
        STATE["busy"] = False


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "AcousticOFDM/1.0"

    def log_message(self, fmt, *args):            # quieter console
        if "/api/result" not in (args[0] if args else ""):
            sys.stderr.write("%s  %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- plumbing -----------------------------------------------------------
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _job(self, jid):
        job = STATE["jobs"].get(jid)
        if job is None:
            self._send(404, dict(error="unknown job"))
        return job

    # -- GET ----------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p in ("/", "/live", "/live.html"):
            with open(PAGE, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if p == "/api/info":
            return self._send(200, dict(
                config=cfg_json(STATE["cfg"]), default=cfg_json(DEFAULT),
                calib=STATE["calib"], busy=STATE["busy"],
                addresses=lan_addresses(), port=self.server.server_port,
                audio=bool(os.path.exists("/usr/bin/arecord"))))
        if p.startswith("/api/wav/"):
            job = self._job(p.rsplit("/", 1)[1])
            if job is None:
                return
            return self._send(200, audio_io.wav_bytes(job["x"], job["cfg"].fs), "audio/wav")
        if p.startswith("/api/result/"):
            job = self._job(p.rsplit("/", 1)[1])
            if job is None:
                return
            return self._send(200, dict(id=job["id"], state=job["state"],
                                        error=job["error"], result=job["result"],
                                        seconds=job.get("seconds")))
        self._send(404, dict(error="not found"))

    # -- POST ---------------------------------------------------------------
    def do_POST(self):
        p = urlparse(self.path).path
        try:
            body = self._json()
        except ValueError:
            return self._send(400, dict(error="bad json"))
        try:
            if p == "/api/calibrate":
                return self._calibrate(body)
            if p == "/api/prepare":
                return self._prepare(body)
            if p == "/api/loopback":
                return self._loopback(body)
            if p == "/api/arm":
                return self._arm(body)
            if p == "/api/listen":
                return self._listen(body)
            if p == "/api/play":
                return self._play(body)
            if p == "/api/reset_calibration":
                STATE["cfg"], STATE["calib"] = DEFAULT, None
                return self._send(200, dict(ok=True))
        except Exception as e:
            traceback.print_exc()
            STATE["busy"] = False
            return self._send(500, dict(error=f"{type(e).__name__}: {e}"))
        self._send(404, dict(error="not found"))

    def _claim(self):
        with LOCK:
            if STATE["busy"]:
                self._send(409, dict(error="the audio device is busy with another run"))
                return False
            STATE["busy"] = True
            return True

    def _calibrate(self, body):
        if not self._claim():
            return
        try:
            cfg, calib = do_calibrate(float(body.get("backoff", 8.0)))
            STATE["cfg"], STATE["calib"] = cfg, calib
        finally:
            STATE["busy"] = False
        self._send(200, dict(ok=True, calib=calib))

    def _build(self, body, cfg):
        text = str(body.get("text", "")).encode("utf-8")
        if not text:
            raise ValueError("empty message")
        if len(text) > 2000:
            raise ValueError("message too long for one frame (2000 bytes max)")
        name = str(body.get("name") or "message.txt")[:18]
        repeat = int(body.get("repeat", 3))
        x, bits, fmeta, mmeta = live.build_frame(text, name, repeat, cfg)
        return x, bits, fmeta, mmeta, repeat, name, text

    def _prepare(self, body):
        """Build a frame for another device to play (always full band)."""
        x, bits, fm, mm, repeat, name, text = self._build(body, DEFAULT)
        job = new_job(x=x, bits=bits, cfg=DEFAULT, repeat=repeat, source="remote",
                      seconds=len(x) / DEFAULT.fs)
        self._send(200, dict(id=job["id"], seconds=round(job["seconds"], 2),
                             wav=f"/api/wav/{job['id']}", n_sym=mm["n_sym"],
                             n_bits=int(len(bits)), nbytes=len(text)))

    def _loopback(self, body):
        """This laptop plays and records at once."""
        if not self._claim():
            return
        try:
            cfg = pick_cfg(body.get("use_calib", True))
            mode = body.get("mode", "adaptive")
            x, bits, fm, mm, repeat, name, text = self._build(body, cfg)
            t0 = time.time()
            rx, _ = audio_io.loopback(x, cfg.fs)
            r = live.demodulate_blind(rx, cfg, mode=mode,
                                      skip_s=audio_io.STARTUP_GUARD_S, tx_bits=bits)
            res = pack_result(r, x, cfg, repeat, round((time.time() - t0) * 1e3),
                              source="loopback")
            res["sent_text"] = text.decode("utf-8", errors="replace")
        finally:
            STATE["busy"] = False
        self._send(200, res)

    def _arm(self, body):
        """Start recording; the caller will play /api/wav/<id> from its own speaker."""
        job = self._job(str(body.get("id", "")))
        if job is None:
            return
        if not self._claim():
            return
        seconds = float(job["seconds"]) + float(body.get("extra", 2.5))
        job["seconds"] = seconds
        t = threading.Thread(target=run_capture,
                             args=(job, seconds, body.get("mode", "adaptive")), daemon=True)
        t.start()
        self._send(200, dict(id=job["id"], seconds=round(seconds, 2)))

    def _listen(self, body):
        """Record for N seconds with no knowledge of what is coming."""
        if not self._claim():
            return
        seconds = float(body.get("seconds", 6))
        job = new_job(cfg=DEFAULT, source="listen", seconds=seconds)
        t = threading.Thread(target=run_capture,
                             args=(job, seconds, body.get("mode", "adaptive")), daemon=True)
        t.start()
        self._send(200, dict(id=job["id"], seconds=seconds))

    def _play(self, body):
        """Play a prepared frame from this laptop's speaker only."""
        job = self._job(str(body.get("id", "")))
        if job is None:
            return
        if not self._claim():
            return
        try:
            audio_io.play(job["x"], job["cfg"].fs)
        finally:
            STATE["busy"] = False
        self._send(200, dict(ok=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="0.0.0.0",
                    help="0.0.0.0 lets a phone on the same Wi-Fi open the page")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(DEFAULT.summary())
    print(f"\nlive demo:  http://localhost:{args.port}/")
    for a in lan_addresses():
        print(f"from another device on this Wi-Fi:  http://{a}:{args.port}/")
    print("Ctrl-C to stop\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
