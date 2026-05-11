"""
PLO Engine - Phase-Locked Oscillator Live Beat-Tracking-Engine

Eigenstaendige, GUI-freie Engine fuer Echtzeit-Beat-Tracking aus einem
Audio-Eingang (sounddevice). Reine Library-Komponente — schreibt nichts in
globale State-Dicts. Konsumenten greifen via snapshot()/consume_beat_events()
auf den Zustand zu.

Pipeline:
  1. Spectral-Flux Onset-Envelope (im Audio-Callback, RT-safe)
  2. Autokorrelation -> grobe BPM-Schaetzung (Tempo-Loop, 0.5 Hz)
  3. Phase-Locked Oscillator + PLL fuer Phase + Periode (PLO-Loop, ~200 Hz)
  4. Phase-Snap bei systematischer Onset-Drift
  5. BPM-Lock + BREAK-Timeout
  6. Backbeat-Detection -> Bar-Offset (Beats 2/4 = Clap)
  7. Phrase-Detection (BREAK / BUILDUP / DROP) aus Energy-Ratios

Mode:
  AUTO    - alles automatisch (BPM via Autokorrelation + PLL)
  MANUAL  - BPM ist fix (vom Benutzer gesetzt), Phase wird trotzdem
            durch Onsets korrigiert. Tap-Tempo bzw. Leertaste setzt
            den Beat-1-Anker.
"""
from __future__ import annotations

import time
import threading
import collections
import math
from typing import Optional, Dict, Any, Tuple

import numpy as np
import sounddevice as sd


# -----------------------------------------------------------------------------
# Konfiguration / Konstanten
# -----------------------------------------------------------------------------
BLOCK_SIZE  = 512
N_FFT       = 512
DISPLAY_SEC = 8.0
BPM_MIN, BPM_MAX  = 70, 180
TEMPO_UPDATE_SEC  = 0.5

PLO_ALPHA          = 0.18
PLO_BETA           = 0.006
ONSET_K_MAD        = 2.5
ONSET_ABS_FLOOR    = 6.0
MIN_ONSET_GAP_SEC  = 0.10

TEMPO_CONF_MIN     = 1.6
ONSET_SILENCE_STD  = 1.5
BPM_LOCK_REQUIRED  = 5
BPM_LOCK_TOLERANCE = 2.0
BPM_MAX_DRIFT_PCT  = 0.06
BPM_MAX_STEP       = 0.5
BPM_UNLOCK_SPREAD  = 10.0
BREAK_UNLOCK_SEC   = 8.0

PHASE_SNAP_MIN_N   = 6
PHASE_SNAP_CONSIS  = 0.65
PHASE_SNAP_THRESH  = 0.10

PHRASE_KICK_BREAK    = 0.45
PHRASE_KICK_PRESENT  = 0.75
PHRASE_RATIO_DROP    = 1.05
PHRASE_RATIO_BREAK   = 0.70
PHRASE_TREND_RISE    = 0.12
PHRASE_HOLD_TICKS    = 2

EMA_ALPHA_SHORT = 0.012     # ~1 s @ 86 fps
EMA_ALPHA_LONG  = 0.0005    # ~25 s @ 86 fps


# -----------------------------------------------------------------------------
# Engine
# -----------------------------------------------------------------------------
class PLOEngine:
    """Phase-Locked Oscillator Beat-Tracking-Engine."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Stream
        self._stream: Optional[sd.InputStream] = None
        self._stream_sr   = 44100
        self._stream_dev: Optional[int] = None
        self._stream_ch   = 1

        # Audio-Verarbeitung
        self._window  = np.hanning(N_FFT).astype(np.float32)
        self._prev_mag = np.zeros(N_FFT // 2 + 1, dtype=np.float32)
        self._gain    = 1.0
        self._onset_fps = self._stream_sr / BLOCK_SIZE

        # Onset-Ringe (Kapazitaet wird in start() gesetzt)
        self._onset_history: collections.deque = collections.deque()
        self._onset_times:   collections.deque = collections.deque()

        # Beat / Tempo State
        self._mode = "AUTO"   # AUTO | MANUAL
        self._bpm = 120.0
        self._bpm_display = 120.0
        self._manual_bpm  = 120.0
        self._phase = 0.0
        self._last_update_t: Optional[float] = None
        self._last_onset_t = 0.0
        self._beat_count   = 0
        self._beats_buffer: collections.deque = collections.deque(maxlen=400)
        self._pending_beats = 0   # Wird durch consume_beat_events() drainiert
        self._input_peak = 0.0

        # BPM-Lock
        self._bpm_locked     = False
        self._bpm_confidence = 0.0
        self._bpm_recent: collections.deque = collections.deque(maxlen=8)
        self._tempo_status = "INIT"
        self._break_started: Optional[float] = None
        self._phase_at_onset: collections.deque = collections.deque(maxlen=8)

        # Bar / Downbeat
        self._high_band_now = 0.0
        self._beat_energies: collections.deque = collections.deque(maxlen=12)
        self._bar_offset = 0
        self._bar_locked = False

        # Hi-Band Transient-Detection (Synth-Spikes / Claps)
        self._high_band_history: collections.deque = collections.deque(maxlen=64)
        self._last_transient_t = 0.0
        self._pending_transients = 0

        # Phrase
        self._energy_short = 0.0
        self._energy_long  = 0.0
        self._low_short    = 0.0
        self._low_long     = 0.0
        self._ema_count    = 0
        self._ratio_history: collections.deque = collections.deque(maxlen=12)
        self._phrase = "WAITING"
        self._phrase_hold = {"phrase": "WAITING", "ticks": 0}

        # Threads
        self._stop_evt = threading.Event()
        self._tempo_th: Optional[threading.Thread] = None
        self._plo_th:   Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self, device_id: int) -> Tuple[bool, str]:
        """Oeffnet Stream. Gibt (ok, message)."""
        self.stop()
        try:
            dev = sd.query_devices(device_id)
            sr  = int(dev['default_samplerate'])
            ch  = min(2, dev['max_input_channels'])
            self._reset_state(sr, ch, device_id)

            self._stream = sd.InputStream(
                device=device_id, channels=ch, samplerate=sr,
                blocksize=BLOCK_SIZE, callback=self._audio_callback,
            )
            self._stream.start()

            self._stop_evt.clear()
            self._tempo_th = threading.Thread(target=self._tempo_loop, daemon=True, name='plo-tempo')
            self._plo_th   = threading.Thread(target=self._plo_loop,   daemon=True, name='plo-osc')
            self._tempo_th.start()
            self._plo_th.start()

            return True, f"[{device_id}] {dev['name']} @ {sr} Hz / {ch} ch"
        except Exception as e:
            return False, str(e)

    def stop(self) -> None:
        self._stop_evt.set()
        if self._stream is not None:
            try: self._stream.stop()
            except Exception: pass
            try: self._stream.close()
            except Exception: pass
            self._stream = None
        for th in (self._tempo_th, self._plo_th):
            if th is not None:
                th.join(timeout=1.0)
        self._tempo_th = None
        self._plo_th   = None

    def is_running(self) -> bool:
        return self._stream is not None

    def set_mode(self, mode: str) -> None:
        if mode not in ("AUTO", "MANUAL"):
            raise ValueError(f"mode must be AUTO or MANUAL, got {mode!r}")
        with self._lock:
            self._mode = mode
            if mode == "MANUAL":
                self._bpm = self._manual_bpm
                self._bpm_display = self._manual_bpm
                # In MANUAL kein Auto-Lock notwendig — Bar-Detection laeuft weiter.
                self._bpm_locked = True
                self._tempo_status = "MANUAL"

    def set_manual_bpm(self, bpm: float) -> None:
        with self._lock:
            self._manual_bpm = float(bpm)
            if self._mode == "MANUAL":
                self._bpm = float(bpm)
                self._bpm_display = float(bpm)

    def mark_downbeat(self) -> None:
        """'Das hier ist Beat 1.' Setzt Phase=0 + Bar-Offset entsprechend."""
        with self._lock:
            cnt = self._beat_count
            self._bar_offset = (-cnt) % 4
            self._bar_locked = True
            self._phase = 0.0
            self._phase_at_onset.clear()
            # Frischer Beat zaehlt sofort
            self._beat_count += 1
            self._pending_beats += 1
            self._beats_buffer.append(time.time())

    def set_gain(self, gain: float) -> None:
        self._gain = max(0.0, float(gain))

    def consume_beat_events(self) -> int:
        """Gibt Anzahl gefeuerter Beats seit letztem Aufruf zurueck (atomar)."""
        with self._lock:
            n = self._pending_beats
            self._pending_beats = 0
            return n

    def consume_transient_events(self) -> int:
        """Gibt Anzahl Hi-Band-Transients (Claps/Synth) seit letztem Aufruf zurueck."""
        with self._lock:
            n = self._pending_transients
            self._pending_transients = 0
            return n

    def snapshot(self) -> Dict[str, Any]:
        """Atomic snapshot des aktuellen Zustands fuer GUI / Bridge."""
        with self._lock:
            cnt = self._beat_count
            bar_off = self._bar_offset
            if cnt > 0:
                beat_in_bar = (cnt - 1 + bar_off) % 4         # 0..3
                bar_in_phr  = ((cnt - 1 + bar_off) // 4) % 8  # 0..7
                beat_in_phr = (cnt - 1 + bar_off) % 32        # 0..31
            else:
                beat_in_bar = 0
                bar_in_phr  = 0
                beat_in_phr = 0

            # Bias-korrigierte Energy-Ratio (short/long) — musikalisch sinnvoll
            # ~1.0 = normal, ~1.5+ = drop, ~0.6 = break.
            n = self._ema_count
            if n > 100:
                bs = 1.0 - (1.0 - EMA_ALPHA_SHORT) ** min(n, 100000)
                bl = 1.0 - (1.0 - EMA_ALPHA_LONG)  ** min(n, 100000)
                es = self._energy_short / max(bs, 1e-9)
                el = self._energy_long  / max(bl, 1e-9)
                energy_ratio = es / max(el, 1e-9) if el > 1e-8 else 1.0
            else:
                energy_ratio = 1.0

            return {
                "mode":           self._mode,
                "bpm":            self._bpm_display,
                "bpm_internal":   self._bpm,
                "phase":          self._phase,
                "beat_count":     cnt,
                "beat_in_bar":    beat_in_bar,    # 0..3
                "bar_in_phrase":  bar_in_phr,     # 0..7
                "beat_in_phrase": beat_in_phr,    # 0..31
                "tempo_status":   self._tempo_status,
                "bpm_locked":     self._bpm_locked,
                "bpm_confidence": self._bpm_confidence,
                "bar_locked":     self._bar_locked,
                "bar_offset":     bar_off,
                "phrase":         self._phrase,
                "input_peak":     self._input_peak,
                "energy_ratio":   energy_ratio,
            }

    # ------------------------------------------------------------------
    # State-Reset
    # ------------------------------------------------------------------
    def _reset_state(self, sr: int, ch: int, device_id: int) -> None:
        self._stream_sr  = sr
        self._stream_ch  = ch
        self._stream_dev = device_id
        self._onset_fps  = sr / BLOCK_SIZE
        cap = int(DISPLAY_SEC * self._onset_fps) + 16

        with self._lock:
            self._onset_history = collections.deque(maxlen=cap)
            self._onset_times   = collections.deque(maxlen=cap)
            self._prev_mag = np.zeros(N_FFT // 2 + 1, dtype=np.float32)

            # Beat/PLO State - in MANUAL bleibt manual_bpm erhalten
            self._phase = 0.0
            self._last_update_t = None
            self._last_onset_t  = 0.0
            self._beat_count    = 0
            self._beats_buffer.clear()
            self._pending_beats = 0
            self._input_peak    = 0.0

            if self._mode == "MANUAL":
                self._bpm = self._manual_bpm
                self._bpm_display = self._manual_bpm
                self._bpm_locked  = True
                self._tempo_status = "MANUAL"
            else:
                self._bpm = 120.0
                self._bpm_display = 120.0
                self._bpm_locked = False
                self._tempo_status = "INIT"

            self._bpm_confidence = 0.0
            self._bpm_recent.clear()
            self._break_started  = None
            self._phase_at_onset.clear()

            self._high_band_now = 0.0
            self._beat_energies.clear()
            self._bar_offset = 0
            self._bar_locked = False
            self._high_band_history.clear()
            self._last_transient_t = 0.0
            self._pending_transients = 0

            self._energy_short = 0.0
            self._energy_long  = 0.0
            self._low_short    = 0.0
            self._low_long     = 0.0
            self._ema_count    = 0
            self._ratio_history.clear()
            self._phrase = "WAITING"
            self._phrase_hold = {"phrase": "WAITING", "ticks": 0}

    # ------------------------------------------------------------------
    # Audio-Callback - RT-Thread, KEIN librosa, KEINE blockierenden Ops
    # ------------------------------------------------------------------
    def _audio_callback(self, indata, frames, time_info, status):
        mono = (np.mean(indata, axis=1) if indata.ndim > 1 else indata[:, 0]).astype(np.float32)
        mono *= self._gain

        if len(mono) < N_FFT:
            mono = np.pad(mono, (0, N_FFT - len(mono)))
        elif len(mono) > N_FFT:
            mono = mono[:N_FFT]

        spec = np.abs(np.fft.rfft(mono * self._window))
        log_mag = np.log1p(spec * 100.0)

        n_bins = log_mag.shape[0]
        f_cut  = int(n_bins * 0.30)
        diff = log_mag - self._prev_mag
        diff[diff < 0] = 0.0
        flux = float(np.sum(diff[:f_cut]) + 0.3 * np.sum(diff[f_cut:]))

        bin_lo = max(int(n_bins * 0.10), 1)
        bin_hi = max(int(n_bins * 0.40), bin_lo + 1)
        high_band = float(np.sum(log_mag[bin_lo:bin_hi]))

        # Low-Band Spectral Flux fuer Kick-Detection (nur Transienten)
        bin_low_end = max(int(n_bins * 0.025), 2)
        low_flux = float(np.sum(diff[1:bin_low_end]))

        self._prev_mag = log_mag
        total_rms = float(np.sqrt(np.mean(mono ** 2)))
        peak = float(np.max(np.abs(mono))) if len(mono) else 0.0

        now = time.time()
        with self._lock:
            self._onset_history.append(flux)
            self._onset_times.append(now)
            self._input_peak    = max(peak, self._input_peak * 0.85)
            self._high_band_now = high_band

            # Hi-Band Transient-Detection: lokales Maximum > median + 2.5*MAD,
            # Min-Abstand 120 ms (gleiche Logik wie alter audio_live.py).
            self._high_band_history.append(high_band)
            if len(self._high_band_history) >= 8:
                hh = np.asarray(self._high_band_history, dtype=np.float32)
                med = float(np.median(hh))
                mad = float(np.median(np.abs(hh - med))) + 1e-6
                thresh = med + 2.5 * mad
                if (high_band > thresh
                        and high_band > 1.5     # absoluter Floor
                        and (now - self._last_transient_t) > 0.12):
                    self._last_transient_t = now
                    self._pending_transients += 1

            a_s = EMA_ALPHA_SHORT
            a_l = EMA_ALPHA_LONG
            self._energy_short = (1 - a_s) * self._energy_short + a_s * total_rms
            self._energy_long  = (1 - a_l) * self._energy_long  + a_l * total_rms
            self._low_short    = (1 - a_s) * self._low_short    + a_s * low_flux
            self._low_long     = (1 - a_l) * self._low_long     + a_l * low_flux
            self._ema_count   += 1

    # ------------------------------------------------------------------
    # Tempo-Loop - Autokorrelation + Phrase
    # ------------------------------------------------------------------
    def _tempo_loop(self) -> None:
        while not self._stop_evt.is_set():
            time.sleep(TEMPO_UPDATE_SEC)
            self._update_phrase()
            if self._mode == "MANUAL":
                # Keine BPM-Schaetzung — Tempo ist fix
                continue
            self._update_tempo_auto()

    def _update_tempo_auto(self) -> None:
        with self._lock:
            arr = np.array(self._onset_history, dtype=np.float32)
            locked = self._bpm_locked
            current_bpm = self._bpm

        if len(arr) < int(2.0 * self._onset_fps):
            return

        # 1) Break / Silence -> BPM nicht updaten
        if float(np.std(arr)) < ONSET_SILENCE_STD:
            now = time.time()
            with self._lock:
                self._bpm_confidence = 0.0
                if locked:
                    self._tempo_status = "BREAK"
                    if self._break_started is None:
                        self._break_started = now
                    elif now - self._break_started > BREAK_UNLOCK_SEC:
                        self._bpm_locked = False
                        self._tempo_status = "SEEK"
                        self._bpm_recent.clear()
                        self._phase_at_onset.clear()
                        self._break_started = None
                else:
                    self._tempo_status = "SEEK"
            return

        with self._lock:
            self._break_started = None

        # 2) Suchbereich + Prior
        if locked:
            lo = current_bpm * (1.0 - BPM_MAX_DRIFT_PCT)
            hi = current_bpm * (1.0 + BPM_MAX_DRIFT_PCT)
            prior = current_bpm
        else:
            lo, hi = BPM_MIN, BPM_MAX
            prior = current_bpm if 80 <= current_bpm <= 160 else 125.0

        result = self._estimate_bpm(arr, prior, lo, hi)
        if result is None:
            return
        new_bpm, conf = result

        if conf < TEMPO_CONF_MIN:
            with self._lock:
                self._bpm_confidence = conf
                if locked:
                    self._tempo_status = "BREAK"
            return

        with self._lock:
            self._bpm_confidence = conf
            self._bpm_recent.append(new_bpm)
            alpha = 0.10 if locked else 0.30
            target = (1 - alpha) * self._bpm + alpha * new_bpm
            if locked:
                delta = target - self._bpm
                if abs(delta) > BPM_MAX_STEP:
                    delta = BPM_MAX_STEP if delta > 0 else -BPM_MAX_STEP
                self._bpm = self._bpm + delta
            else:
                self._bpm = target

            recent = list(self._bpm_recent)
            if len(recent) >= BPM_LOCK_REQUIRED:
                last_n = recent[-BPM_LOCK_REQUIRED:]
                if not locked and (max(last_n) - min(last_n)) < BPM_LOCK_TOLERANCE:
                    self._bpm_locked   = True
                    self._tempo_status = "LOCK"
                elif locked:
                    self._tempo_status = "LOCK"
                    if (max(recent) - min(recent)) > BPM_UNLOCK_SPREAD:
                        self._bpm_locked   = False
                        self._tempo_status = "SEEK"
                else:
                    self._tempo_status = "SEEK"
            else:
                self._tempo_status = "INIT"

    @staticmethod
    def _estimate_bpm(onset_arr: np.ndarray, prior_bpm: float,
                      bpm_lo: float, bpm_hi: float) -> Optional[Tuple[float, float]]:
        fps_local = len(onset_arr) / DISPLAY_SEC if len(onset_arr) > 1 else 86.0
        if len(onset_arr) < int(2.0 * fps_local):
            return None
        x = onset_arr - np.mean(onset_arr)
        if np.std(x) < 1e-6:
            return None
        ac = np.correlate(x, x, mode='full')
        ac = ac[len(ac) // 2:]

        lag_min = int(60.0 / bpm_hi * fps_local)
        lag_max = int(60.0 / bpm_lo * fps_local)
        lag_max = min(lag_max, len(ac) - 1)
        if lag_max <= lag_min + 1:
            return None
        region = ac[lag_min:lag_max].copy()
        if np.max(region) <= 0:
            return None

        idx = np.arange(lag_min, lag_max)
        bpms = 60.0 * fps_local / idx
        sigma = max(8.0, prior_bpm * 0.10)
        pref = np.exp(-((bpms - prior_bpm) / sigma) ** 2)
        weighted = region * pref
        peak_idx = int(np.argmax(weighted))
        peak = peak_idx + lag_min
        peak_val = float(region[peak_idx])
        region_mean = float(np.mean(region) + 1e-9)
        confidence = peak_val / region_mean

        if lag_min < peak < lag_max - 1:
            a, b, c = ac[peak - 1], ac[peak], ac[peak + 1]
            denom = (a - 2 * b + c)
            peak_f = peak + 0.5 * (a - c) / denom if abs(denom) > 1e-9 else peak
        else:
            peak_f = peak
        return float(60.0 * fps_local / peak_f), confidence

    # ------------------------------------------------------------------
    # PLO-Loop - hochfrequente Phasen-Aktualisierung
    # ------------------------------------------------------------------
    def _plo_loop(self) -> None:
        while not self._stop_evt.is_set():
            self._plo_step(time.time())
            time.sleep(0.005)

    def _plo_step(self, t_now: float) -> None:
        with self._lock:
            last_t = self._last_update_t
            if last_t is None:
                self._last_update_t = t_now
                return
            dt = t_now - last_t
            if dt <= 0 or dt > 1.0:
                self._last_update_t = t_now
                return

            period = 60.0 / max(self._bpm, 1e-3)
            phase  = self._phase + dt / period
            beats_fired = 0
            while phase >= 1.0:
                phase -= 1.0
                beats_fired += 1
            self._phase = phase
            self._last_update_t = t_now

            if beats_fired:
                for _ in range(beats_fired):
                    self._beat_count += 1
                    self._beats_buffer.append(t_now)
                    self._beat_energies.append((self._beat_count, self._high_band_now))
                self._pending_beats += beats_fired
                self._update_bar_offset_locked()

            # Display-BPM glaetten
            disp_alpha = 0.04 if self._bpm_locked else 0.20
            self._bpm_display = (1 - disp_alpha) * self._bpm_display + disp_alpha * self._bpm

            onsets = list(self._onset_history)
            last_onset_t = self._last_onset_t

        if len(onsets) < 4:
            return

        recent = np.array(onsets[-int(self._onset_fps * 1.5):], dtype=np.float32)
        median = float(np.median(recent))
        mad    = float(np.median(np.abs(recent - median))) + 1e-6
        threshold = max(median + ONSET_K_MAD * mad, ONSET_ABS_FLOOR)

        flux_now  = onsets[-1]
        flux_prev = onsets[-2]
        flux_prv2 = onsets[-3]
        is_peak = flux_prev > flux_prv2 and flux_prev > flux_now and flux_prev > threshold
        if not is_peak:
            return
        if (t_now - last_onset_t) < MIN_ONSET_GAP_SEC:
            return

        with self._lock:
            self._last_onset_t = t_now
            p = self._phase
            err = p if p <= 0.5 else p - 1.0
            self._phase = (p - PLO_ALPHA * err) % 1.0

            # PLL-Frequenzadaption nur in AUTO + bei Lock
            if self._mode == "AUTO" and self._bpm_locked:
                period = 60.0 / max(self._bpm, 1e-3)
                period_new = period + PLO_BETA * err
                new_bpm = 60.0 / max(period_new, 1e-3)
                if abs(new_bpm - self._bpm) <= self._bpm * 0.03:
                    self._bpm = new_bpm

            # Phase-Snap
            self._phase_at_onset.append(p)
            buf = self._phase_at_onset
            if len(buf) >= PHASE_SNAP_MIN_N:
                angles = np.asarray(list(buf)) * 2.0 * np.pi
                mx = float(np.mean(np.cos(angles)))
                my = float(np.mean(np.sin(angles)))
                consistency = (mx * mx + my * my) ** 0.5
                mean_phase  = (math.atan2(my, mx) / (2.0 * math.pi)) % 1.0
                mean_err    = mean_phase if mean_phase <= 0.5 else mean_phase - 1.0
                if consistency >= PHASE_SNAP_CONSIS and abs(mean_err) > PHASE_SNAP_THRESH:
                    self._phase = (self._phase - mean_err) % 1.0
                    self._phase_at_onset.clear()

    # ------------------------------------------------------------------
    # Bar-Offset (Backbeat-Detection) - erwartet _lock GEHALTEN
    # ------------------------------------------------------------------
    def _update_bar_offset_locked(self) -> None:
        energies = list(self._beat_energies)
        if len(energies) < 6:
            return
        energies = energies[-8:]
        counters = [c for c, _ in energies]
        vals     = np.array([e for _, e in energies], dtype=np.float32)
        if float(np.std(vals)) < 1e-3:
            self._bar_locked = False
            return

        median = float(np.median(vals))
        high_mask = vals > median

        best_offset = self._bar_offset
        best_score  = -1
        for offset in range(4):
            score = 0
            for c, h in zip(counters, high_mask):
                bib = (c - 1 + offset) % 4 + 1
                if h and bib in (2, 4):
                    score += 1
                elif (not h) and bib in (1, 3):
                    score += 1
            if score > best_score:
                best_score  = score
                best_offset = offset

        if best_score >= 6:
            self._bar_offset = best_offset
            self._bar_locked = True
        else:
            self._bar_locked = False

    # ------------------------------------------------------------------
    # Phrase-Detection (BREAK / BUILDUP / DROP)
    # ------------------------------------------------------------------
    def _update_phrase(self) -> None:
        with self._lock:
            es_raw = self._energy_short
            el_raw = self._energy_long
            ls_raw = self._low_short
            ll_raw = self._low_long
            n      = self._ema_count
            current = self._phrase
            rh = self._ratio_history

        if n < int(5.0 * self._onset_fps):
            return

        a_s = EMA_ALPHA_SHORT
        a_l = EMA_ALPHA_LONG
        n_eff = min(n, 100000)
        bs = 1.0 - (1.0 - a_s) ** n_eff
        bl = 1.0 - (1.0 - a_l) ** n_eff

        es = es_raw / max(bs, 1e-9)
        el = el_raw / max(bl, 1e-9)
        ls = ls_raw / max(bs, 1e-9)
        ll = ll_raw / max(bl, 1e-9)

        if el < 1e-5 or ll < 1e-9:
            return

        ratio_total = es / el
        ratio_low   = ls / ll

        rh.append(ratio_total)
        if len(rh) >= 6:
            trend = float(np.mean(list(rh)[-3:]) - np.mean(list(rh)[:3]))
        else:
            trend = 0.0

        candidate = current
        if ratio_low < PHRASE_KICK_BREAK or ratio_total < PHRASE_RATIO_BREAK:
            candidate = "BREAK"
        elif ratio_low >= PHRASE_KICK_PRESENT and ratio_total >= PHRASE_RATIO_DROP:
            candidate = "DROP"
        elif trend >= PHRASE_TREND_RISE:
            candidate = "BUILDUP"
        elif current == "WAITING":
            candidate = "BREAK"

        if candidate == self._phrase_hold["phrase"]:
            self._phrase_hold["ticks"] += 1
        else:
            self._phrase_hold["phrase"] = candidate
            self._phrase_hold["ticks"]  = 1

        if candidate != current and self._phrase_hold["ticks"] >= PHRASE_HOLD_TICKS:
            with self._lock:
                self._phrase = candidate


# -----------------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------------
def get_input_devices() -> Dict[int, str]:
    """Liefert {device_id: 'id: name'} aller Eingabegeraete."""
    out = {}
    for i, d in enumerate(sd.query_devices()):
        if d['max_input_channels'] > 0:
            out[i] = f"{i}: {d['name']}"
    return out
