"""
PLO (Phase-Locked Oscillator) Live Beat Tracker
================================================

Echtzeit-Beat-Tracking aus dem Audio-Interface — Vorbild SoundSwitch.

Pipeline:
  1. Audio-Callback (sounddevice)        Mono-Block @ ~23ms
  2. Spectral-Flux Onset-Envelope        log-magnitude STFT diff, halbwellengleich.
  3. Autokorrelation auf 6-s-Fenster     BPM-Schaetzung 70-180 BPM, alle 0.5s
  4. Phase-Locked Oscillator (PLO)       Phase laeuft mit BPM, Onsets ziehen
                                         Phase Richtung naechstes Beat
  5. Matplotlib Live-Plot                Onset, BPM, Beat-Counter
                                         + Geraete-Selektor + Gain-Slider

Aufruf:
  python plo_beat_test.py [device_id]
"""

import sys
import time
import threading
import collections
import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Slider, RadioButtons


# -----------------------------------------------------------------------------
# Konfiguration
# -----------------------------------------------------------------------------
BLOCK_SIZE  = 512             # ~12ms @ 44100 Hz   -> ~86 Hz Onset-Rate
N_FFT       = 512             # halbiert Hop -> doppelte AC-Aufloesung (~3 BPM)
DISPLAY_SEC = 8.0
BPM_MIN, BPM_MAX = 70, 180
TEMPO_UPDATE_SEC = 0.5

# PLO Parameter
PLO_ALPHA          = 0.18     # Phase-Korrektur pro Onset (proportional)
PLO_BETA           = 0.006    # Periode-Korrektur pro Onset (integral / PLL)
                              #   wirkt nur wenn gelockt -> sub-BPM-Genauigkeit
ONSET_K_MAD        = 2.5
ONSET_ABS_FLOOR    = 6.0      # leicht reduziert da Flux mit kleinerem N_FFT kleiner
MIN_ONSET_GAP_SEC  = 0.10

# BPM-Tracking / Lock
TEMPO_CONF_MIN     = 1.6      # min. AC-Peak/Mittel damit Schaetzung akzeptiert wird
ONSET_SILENCE_STD  = 1.5      # < diesem std(onsets) -> Break/Silence, BPM einfrieren
BPM_LOCK_REQUIRED  = 5        # so viele konsistente Schaetzungen in Folge -> Lock
BPM_LOCK_TOLERANCE = 2.0      # +/- BPM Streuung damit "konsistent"
BPM_MAX_DRIFT_PCT  = 0.06     # bei Lock: nur +/- 6 % Suchbereich (DJ-Mix)
BPM_MAX_STEP       = 0.5      # bei Lock: max. BPM-Aenderung pro 0.5 s
BPM_UNLOCK_SPREAD  = 10.0     # wenn Streuung der recent-Liste so gross -> Lock loesen
BREAK_UNLOCK_SEC   = 8.0      # nach so viel Sekunden BREAK -> Lock loesen (Track-Wechsel)

# PLO Phase-Snap: wenn Onsets konsistent neben Phase=0 landen, Phase hart neu setzen
PHASE_SNAP_MIN_N   = 6        # min. Onsets im Buffer fuer Snap-Check
PHASE_SNAP_CONSIS  = 0.65     # zirkulaere Konsistenz (0..1, 1 = alle gleiche Phase)
PHASE_SNAP_THRESH  = 0.10     # mittlere Phase-Abweichung > diesem Wert -> Snap

MAX_DEVICES_IN_RADIO = 10

# Wird beim Stream-Open aktualisiert
SAMPLE_RATE = 44100
ONSET_FPS   = SAMPLE_RATE / BLOCK_SIZE


# -----------------------------------------------------------------------------
# Geteilter Zustand
# -----------------------------------------------------------------------------
_lock = threading.Lock()

_onset_history: collections.deque = collections.deque()
_onset_times:   collections.deque = collections.deque()

_prev_mag = np.zeros(N_FFT // 2 + 1, dtype=np.float32)
_window   = np.hanning(N_FFT).astype(np.float32)

_state = {
    "bpm":              120.0,
    "bpm_display":      120.0,    # geglaetteter Wert nur fuer Anzeige
    "phase":            0.0,
    "last_update_t":    None,
    "last_onset_t":     0.0,
    "beat_count":       0,
    "beats":            collections.deque(maxlen=400),
    "input_peak":       0.0,
    # BPM-Lock-Mechanik
    "bpm_locked":       False,
    "bpm_confidence":   0.0,
    "bpm_recent":       collections.deque(maxlen=8),
    "tempo_status":     "INIT",   # INIT | LOCK | SEEK | BREAK
    "break_started":    None,     # Zeitstempel als BREAK begann
    # PLO Phase-Snap: Onset-Phasen-Buffer
    "phase_at_onset":   collections.deque(maxlen=8),
    # Bar / Downbeat
    "high_band_now":    0.0,      # letzter Hi-Band-Pegel aus dem Callback
    "beat_energies":    collections.deque(maxlen=12),  # Hi-Band pro Beat
    "bar_offset":       0,        # 0..3, so dass beats 2/4 auf Backbeats landen
    "bar_locked":       False,    # True wenn Backbeat-Pattern erkannt
    # Phrase-Analyse (BREAK / BUILDUP / DROP)
    "energy_short":     0.0,      # ~1 s EMA Gesamtenergie (raw, biased)
    "energy_long":      0.0,      # ~25 s EMA Gesamtenergie (raw, biased)
    "low_short":        0.0,      # ~1 s EMA Kick/Sub-Bass
    "low_long":         0.0,      # ~25 s EMA Kick/Sub-Bass
    "ema_count":        0,        # Anzahl Updates fuer Bias-Korrektur
    "ratio_history":    collections.deque(maxlen=12),  # short/long Ratios fuer Trend
    "phrase":           "WAITING",
}

# Phrase-Detection-Parameter
PHRASE_KICK_BREAK    = 0.45     # low_short/low_long darunter -> Kick weg -> BREAK
PHRASE_KICK_PRESENT  = 0.75     # darueber -> Kick wieder voll da
PHRASE_RATIO_DROP    = 1.05     # energy short/long > x -> energetisch
PHRASE_RATIO_BREAK   = 0.70     # darunter -> ruhig
PHRASE_TREND_RISE    = 0.12     # Ratio-Anstieg in letzten ~3 s -> BUILDUP
PHRASE_HOLD_TICKS    = 2        # min Ticks (a 0.5 s) bevor Phrase-Wechsel

# Stream-Management
_stream     = None
_stream_dev = None
_stream_sr  = None
_stream_ch  = None
_gain       = 1.0


# -----------------------------------------------------------------------------
# Audio-Callback - Spectral-Flux Onset-Envelope
# -----------------------------------------------------------------------------
def _audio_callback(indata, frames, time_info, status):
    global _prev_mag

    mono = (np.mean(indata, axis=1) if indata.ndim > 1 else indata[:, 0]).astype(np.float32)
    mono *= _gain

    if len(mono) < N_FFT:
        mono = np.pad(mono, (0, N_FFT - len(mono)))
    elif len(mono) > N_FFT:
        mono = mono[:N_FFT]

    spec = np.abs(np.fft.rfft(mono * _window))
    log_mag = np.log1p(spec * 100.0)

    n_bins = log_mag.shape[0]
    f_cut  = int(n_bins * 0.30)
    diff = log_mag - _prev_mag
    diff[diff < 0] = 0.0
    flux = float(np.sum(diff[:f_cut]) + 0.3 * np.sum(diff[f_cut:]))
    _prev_mag = log_mag

    # Hi-Band-Energie fuer Backbeat-/Downbeat-Erkennung (Clap/Snare-Bereich)
    # Bei N_FFT=512 / SR=44100 -> bin 24 ~ 2 kHz, bin 96 ~ 8 kHz
    bin_lo = max(int(n_bins * 0.10), 1)
    bin_hi = max(int(n_bins * 0.40), bin_lo + 1)
    high_band = float(np.sum(log_mag[bin_lo:bin_hi]))

    # Low-Band TRANSIENT (Spectral Flux im Sub-Bass) — entscheidend fuer
    # Kick-Detection. Sustained Bass / Synth-Riser haben hohe Bass-ENERGIE aber
    # kaum Bass-FLUX, ein Kick hingegen liefert einen scharfen positiven Delta
    # in den unteren Bins. Das unterscheidet Kicks von melodischem Sub-Bass.
    bin_low_end = max(int(n_bins * 0.025), 2)   # ~430 Hz @ N_FFT=512
    low_flux    = float(np.sum(diff[1:bin_low_end]))

    # Gesamt-RMS (linear) fuer Phrase-Energy-Tracking
    total_rms = float(np.sqrt(np.mean(mono ** 2)))

    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0

    now = time.time()
    with _lock:
        _onset_history.append(flux)
        _onset_times.append(now)
        # Glaetten fuer ruhigere Anzeige
        _state["input_peak"]    = max(peak, _state["input_peak"] * 0.85)
        _state["high_band_now"] = high_band
        # Phrase-EMAs: short ~1s, long ~25s. Mit ONSET_FPS ~86 Hz:
        #   alpha_short = 1 - exp(-1/(fps*1.0)) ≈ 0.011
        #   alpha_long  = 1 - exp(-1/(fps*25))  ≈ 0.00046
        a_s = 0.012
        a_l = 0.0005
        _state["energy_short"] = (1 - a_s) * _state["energy_short"] + a_s * total_rms
        _state["energy_long"]  = (1 - a_l) * _state["energy_long"]  + a_l * total_rms
        _state["low_short"]    = (1 - a_s) * _state["low_short"]    + a_s * low_flux
        _state["low_long"]     = (1 - a_l) * _state["low_long"]     + a_l * low_flux
        _state["ema_count"]   += 1


# -----------------------------------------------------------------------------
# BPM-Schaetzung: Autokorrelation der Onset-Envelope
# -----------------------------------------------------------------------------
def estimate_bpm(onset_arr: np.ndarray, fps: float,
                 prior_bpm: float = 125.0,
                 bpm_lo: float = BPM_MIN,
                 bpm_hi: float = BPM_MAX):
    """Schaetzt BPM via Autokorrelation. Gibt (bpm, confidence) oder None zurueck.
    confidence = AC-Peak / Mittelwert der AC-Region (>~1.5 = scharfer Peak)."""
    if len(onset_arr) < int(2.0 * fps):
        return None
    x = onset_arr - np.mean(onset_arr)
    if np.std(x) < 1e-6:
        return None

    ac = np.correlate(x, x, mode='full')
    ac = ac[len(ac) // 2:]

    lag_min = int(60.0 / bpm_hi * fps)
    lag_max = int(60.0 / bpm_lo * fps)
    lag_max = min(lag_max, len(ac) - 1)
    if lag_max <= lag_min + 1:
        return None

    region = ac[lag_min:lag_max].copy()
    if np.max(region) <= 0:
        return None

    # Tempo-Prior: Gauss um prior_bpm — bei Lock: scharfes Prior, sonst weiches
    idx = np.arange(lag_min, lag_max)
    bpms = 60.0 * fps / idx
    sigma = max(8.0, prior_bpm * 0.10)
    pref = np.exp(-((bpms - prior_bpm) / sigma) ** 2)
    weighted = region * pref

    peak_idx = int(np.argmax(weighted))
    peak     = peak_idx + lag_min
    peak_val = float(region[peak_idx])

    # Confidence = wie deutlich der Peak ueber dem Mittel liegt
    region_mean = float(np.mean(region) + 1e-9)
    confidence  = peak_val / region_mean

    # Parabolische Interpolation
    if lag_min < peak < lag_max - 1:
        a, b, c = ac[peak - 1], ac[peak], ac[peak + 1]
        denom = (a - 2 * b + c)
        if abs(denom) > 1e-9:
            peak_f = peak + 0.5 * (a - c) / denom
        else:
            peak_f = peak
    else:
        peak_f = peak

    return float(60.0 * fps / peak_f), confidence


# -----------------------------------------------------------------------------
# Phrase-Analyse (BREAK / BUILDUP / DROP)
# -----------------------------------------------------------------------------
_phrase_hold = {"phrase": "WAITING", "ticks": 0}


def _update_phrase():
    """State-Machine fuer Phrase-Erkennung. Wird im Tempo-Loop aufgerufen."""
    with _lock:
        es_raw = _state["energy_short"]
        el_raw = _state["energy_long"]
        ls_raw = _state["low_short"]
        ll_raw = _state["low_long"]
        n      = _state["ema_count"]
        current = _state["phrase"]
        rh = _state["ratio_history"]

    # Mindestens 5 s Audio damit Ratios stabil werden
    if n < int(5.0 * ONSET_FPS):
        return

    # Bias-Korrektur (Adam-Style): EMA / (1 - (1-alpha)^n)
    # Korrigiert die Anlauf-Verzerrung wenn EMAs bei 0 starten.
    a_s = 0.012
    a_l = 0.0005
    n_eff = min(n, 100000)   # cap gegen ueberlauf
    bs = 1.0 - (1.0 - a_s) ** n_eff   # short-Korrektur (schnell -> nach ~3 s ~1.0)
    bl = 1.0 - (1.0 - a_l) ** n_eff   # long-Korrektur  (langsam -> nach ~25 s ~0.63)

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

    # State-Machine: BREAK ist Default, DROP/BUILDUP brauchen positive Evidenz.
    # So bleibt der Status BREAK auch wenn EMAs ohne Kontrast pendeln (~1.0)
    # — denn ohne Kontrast koennen wir "leise spielende Musik" nicht von einem
    # echten DROP unterscheiden, also sicherer Default = BREAK.
    candidate = current
    if ratio_low < PHRASE_KICK_BREAK or ratio_total < PHRASE_RATIO_BREAK:
        # Kick weg ODER Energie deutlich unter Trend -> BREAK
        candidate = "BREAK"
    elif ratio_low >= PHRASE_KICK_PRESENT and ratio_total >= PHRASE_RATIO_DROP:
        # Kick voll da UND Energie ueber Trend -> DROP
        candidate = "DROP"
    elif trend >= PHRASE_TREND_RISE:
        # Energie steigt schnell an -> BUILDUP
        candidate = "BUILDUP"
    elif current == "WAITING":
        # Erste Klassifikation nach Warmup ohne klare Evidenz -> BREAK (sicher)
        candidate = "BREAK"
    # else: aktueller Zustand bleibt

    # Hysterese: Phrase muss sich PHRASE_HOLD_TICKS in Folge halten bevor wir wechseln
    if candidate == _phrase_hold["phrase"]:
        _phrase_hold["ticks"] += 1
    else:
        _phrase_hold["phrase"] = candidate
        _phrase_hold["ticks"]  = 1

    if candidate != current and _phrase_hold["ticks"] >= PHRASE_HOLD_TICKS:
        with _lock:
            _state["phrase"] = candidate


# -----------------------------------------------------------------------------
# Bar / Downbeat-Detection aus Backbeat-Energie
# -----------------------------------------------------------------------------
def _update_bar_offset():
    """Sucht den Bar-Offset (0..3) so, dass die hochenergetischen Beats
    (Clap/Snare = Beats 2 und 4 in House/Techno) korrekt aufgeloest werden.

    Erwartet _lock GEHALTEN (wird aus _plo_step heraus aufgerufen)."""
    energies = list(_state["beat_energies"])
    if len(energies) < 6:
        return

    # Letzte 8 Beats betrachten — alte Werte koennen aus anderem Track sein
    energies = energies[-8:]
    counters = [c for c, _ in energies]
    vals     = np.array([e for _, e in energies], dtype=np.float32)

    if float(np.std(vals)) < 1e-3:
        # Keine Varianz -> kein Backbeat-Pattern erkennbar (z.B. nur Kick)
        _state["bar_locked"] = False
        return

    median = float(np.median(vals))
    high_mask = vals > median   # True = "Backbeat-verdaechtig"

    # Fuer jeden Offset 0..3 zaehlen wie viele Beats korrekt klassifiziert werden:
    #   high (Clap)  -> beat_in_bar in {2, 4}
    #   low  (Kick)  -> beat_in_bar in {1, 3}
    best_offset = _state["bar_offset"]
    best_score  = -1
    for offset in range(4):
        score = 0
        for c, h in zip(counters, high_mask):
            # Identische Formel wie im Display: bib in {1..4}
            bib = (c - 1 + offset) % 4 + 1
            if h and bib in (2, 4):
                score += 1
            elif (not h) and bib in (1, 3):
                score += 1
        if score > best_score:
            best_score  = score
            best_offset = offset

    # Mindestens 6 von 8 muessen passen -> sonst kein eindeutiges Pattern
    if best_score >= 6:
        _state["bar_offset"] = best_offset
        _state["bar_locked"] = True
    else:
        _state["bar_locked"] = False


# -----------------------------------------------------------------------------
# PLO Update
# -----------------------------------------------------------------------------
def _plo_step(t_now: float):
    with _lock:
        last_t = _state["last_update_t"]
        if last_t is None:
            _state["last_update_t"] = t_now
            return
        dt = t_now - last_t
        if dt <= 0 or dt > 1.0:
            _state["last_update_t"] = t_now
            return

        period = 60.0 / max(_state["bpm"], 1e-3)
        phase  = _state["phase"] + dt / period

        beats_fired = 0
        while phase >= 1.0:
            phase -= 1.0
            beats_fired += 1

        _state["phase"]         = phase
        _state["last_update_t"] = t_now

        if beats_fired:
            for _ in range(beats_fired):
                _state["beat_count"] += 1
                _state["beats"].append(t_now)
                # Hi-Band-Energie zum Beat-Zeitpunkt speichern (Backbeat-Hinweis)
                _state["beat_energies"].append(
                    (_state["beat_count"], _state["high_band_now"])
                )
            # Bar-Alignment aktualisieren wenn genug Beats vorliegen
            _update_bar_offset()

        onsets = list(_onset_history)
        last_onset_t = _state["last_onset_t"]

    if len(onsets) < 4:
        return

    recent = np.array(onsets[-int(ONSET_FPS * 1.5):], dtype=np.float32)
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

    with _lock:
        _state["last_onset_t"] = t_now
        p = _state["phase"]
        # Soft Nudge wie gehabt (proportionaler Anteil)
        err = p if p <= 0.5 else p - 1.0
        _state["phase"] = (p - PLO_ALPHA * err) % 1.0

        # PLL-Frequenz-Adaption (integraler Anteil): nur wenn gelockt.
        # Wenn Onsets konsistent zu spaet (err > 0): Oszillator laeuft zu schnell
        # -> Periode VERLAENGERN -> BPM verkleinern (und umgekehrt).
        # Das gibt sub-BPM-Genauigkeit indem jeder Onset die Periode minimal nachzieht.
        if _state["bpm_locked"]:
            period = 60.0 / max(_state["bpm"], 1e-3)
            period_new = period + PLO_BETA * err
            new_bpm = 60.0 / max(period_new, 1e-3)
            # gegen wegdriften: PLL-Korrektur darf BPM nie weiter als 3 % vom alten Wert ziehen
            if abs(new_bpm - _state["bpm"]) <= _state["bpm"] * 0.03:
                _state["bpm"] = new_bpm

        # Phase-Snap: zirkulaere Statistik der letzten Onset-Phasen.
        # Wenn alle Onsets konsistent NEBEN Phase=0 landen, sitzt der PLO
        # auf einer falschen Stelle (z.B. Off-Beat oder verschoben nach Break).
        # Dann hart snappen statt nur weich nudgen.
        _state["phase_at_onset"].append(p)
        buf = _state["phase_at_onset"]
        if len(buf) >= PHASE_SNAP_MIN_N:
            angles = np.asarray(list(buf)) * 2.0 * np.pi
            mx = float(np.mean(np.cos(angles)))
            my = float(np.mean(np.sin(angles)))
            consistency = (mx * mx + my * my) ** 0.5    # 0..1
            mean_phase  = (np.arctan2(my, mx) / (2.0 * np.pi)) % 1.0
            mean_err    = mean_phase if mean_phase <= 0.5 else mean_phase - 1.0
            if consistency >= PHASE_SNAP_CONSIS and abs(mean_err) > PHASE_SNAP_THRESH:
                # Phase so verschieben, dass kuenftige Onsets bei 0 landen
                _state["phase"] = (_state["phase"] - mean_err) % 1.0
                _state["phase_at_onset"].clear()
                # debug-print bewusst sparsam halten
                # print(f"[plo] phase-snap (err={mean_err:+.3f}, c={consistency:.2f})")


# -----------------------------------------------------------------------------
# Hintergrund-Threads
# -----------------------------------------------------------------------------
def _tempo_loop(stop_evt: threading.Event):
    while not stop_evt.is_set():
        time.sleep(TEMPO_UPDATE_SEC)

        # Phrase-Analyse laeuft unabhaengig von BPM-Tracking
        _update_phrase()

        with _lock:
            arr         = np.array(_onset_history, dtype=np.float32)
            locked      = _state["bpm_locked"]
            current_bpm = _state["bpm"]

        if len(arr) < int(2.0 * ONSET_FPS):
            continue

        # 1) Break / Silence: zu wenig Onset-Aktivitaet -> BPM nicht updaten
        if float(np.std(arr)) < ONSET_SILENCE_STD:
            now = time.time()
            with _lock:
                _state["bpm_confidence"] = 0.0
                if locked:
                    _state["tempo_status"] = "BREAK"
                    if _state["break_started"] is None:
                        _state["break_started"] = now
                    elif now - _state["break_started"] > BREAK_UNLOCK_SEC:
                        # zu lange BREAK -> Lock loesen, Phase-Buffer leeren
                        _state["bpm_locked"]   = False
                        _state["tempo_status"] = "SEEK"
                        _state["bpm_recent"].clear()
                        _state["phase_at_onset"].clear()
                        _state["break_started"] = None
                        print(f"[plo] BPM-UNLOCK nach {BREAK_UNLOCK_SEC}s BREAK")
                else:
                    _state["tempo_status"] = "SEEK"
            continue

        # Onset-Aktivitaet wieder da -> Break-Timer ruecksetzen
        with _lock:
            _state["break_started"] = None

        # 2) Suchbereich + Prior: bei Lock eng um aktuelles BPM, sonst weit
        if locked:
            lo = current_bpm * (1.0 - BPM_MAX_DRIFT_PCT)
            hi = current_bpm * (1.0 + BPM_MAX_DRIFT_PCT)
            prior = current_bpm
        else:
            lo, hi = BPM_MIN, BPM_MAX
            prior  = current_bpm if 80 <= current_bpm <= 160 else 125.0

        result = estimate_bpm(arr, ONSET_FPS, prior_bpm=prior,
                              bpm_lo=lo, bpm_hi=hi)
        if result is None:
            continue
        new_bpm, conf = result

        # 3) Confidence-Gate: schwacher AC-Peak -> nicht uebernehmen
        if conf < TEMPO_CONF_MIN:
            with _lock:
                _state["bpm_confidence"] = conf
                if locked:
                    _state["tempo_status"] = "BREAK"
            continue

        # 4) Akzeptieren + Glaetten + Lock-Pflege
        with _lock:
            _state["bpm_confidence"] = conf
            _state["bpm_recent"].append(new_bpm)

            # Gelockt -> sehr langsam folgen + harter Step-Cap, ungelockt -> schneller einrasten
            alpha = 0.10 if locked else 0.30
            target = (1.0 - alpha) * _state["bpm"] + alpha * new_bpm
            if locked:
                delta = target - _state["bpm"]
                if abs(delta) > BPM_MAX_STEP:
                    delta = BPM_MAX_STEP if delta > 0 else -BPM_MAX_STEP
                _state["bpm"] = _state["bpm"] + delta
            else:
                _state["bpm"] = target

            recent = list(_state["bpm_recent"])
            if len(recent) >= BPM_LOCK_REQUIRED:
                last_n = recent[-BPM_LOCK_REQUIRED:]
                spread = max(last_n) - min(last_n)
                if not locked and spread < BPM_LOCK_TOLERANCE:
                    _state["bpm_locked"]   = True
                    _state["tempo_status"] = "LOCK"
                    print(f"[plo] BPM-LOCK @ {_state['bpm']:.1f}")
                elif locked:
                    _state["tempo_status"] = "LOCK"
                    # Bei dauerhaft sehr breiter Streuung Lock loesen (Track-Wechsel)
                    if (max(recent) - min(recent)) > BPM_UNLOCK_SPREAD:
                        _state["bpm_locked"]   = False
                        _state["tempo_status"] = "SEEK"
                        print(f"[plo] BPM-UNLOCK (Streuung {max(recent)-min(recent):.1f})")
                else:
                    _state["tempo_status"] = "SEEK"
            else:
                _state["tempo_status"] = "INIT"


def _plo_loop(stop_evt: threading.Event):
    while not stop_evt.is_set():
        _plo_step(time.time())
        time.sleep(0.005)


# -----------------------------------------------------------------------------
# Stream-Management
# -----------------------------------------------------------------------------
def _list_input_devices():
    """[(device_id, name, default_samplerate, channels), ...]"""
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d['max_input_channels'] > 0:
            out.append((i, d['name'], int(d['default_samplerate']),
                        min(2, d['max_input_channels'])))
    return out


def _close_stream():
    global _stream
    if _stream is not None:
        try:
            _stream.stop()
        except Exception:
            pass
        try:
            _stream.close()
        except Exception:
            pass
        _stream = None


def _open_stream(device_id: int) -> str:
    """Oeffnet (oder wechselt) den Input-Stream. Gibt Status-Text zurueck."""
    global _stream, _stream_dev, _stream_sr, _stream_ch
    global _onset_history, _onset_times, _prev_mag, ONSET_FPS, SAMPLE_RATE

    _close_stream()

    try:
        dev = sd.query_devices(device_id)
        sr  = int(dev['default_samplerate'])
        ch  = min(2, dev['max_input_channels'])

        SAMPLE_RATE = sr
        ONSET_FPS   = sr / BLOCK_SIZE
        cap = int(DISPLAY_SEC * ONSET_FPS) + 16

        with _lock:
            _onset_history = collections.deque(maxlen=cap)
            _onset_times   = collections.deque(maxlen=cap)
            _prev_mag = np.zeros(N_FFT // 2 + 1, dtype=np.float32)
            _state["last_update_t"] = None
            _state["beats"].clear()
            _state["beat_count"]     = 0
            _state["phase"]          = 0.0
            _state["input_peak"]     = 0.0
            _state["bpm_locked"]     = False
            _state["bpm_confidence"] = 0.0
            _state["bpm_recent"].clear()
            _state["tempo_status"]   = "INIT"
            _state["break_started"]  = None
            _state["phase_at_onset"].clear()
            _state["beat_energies"].clear()
            _state["bar_offset"]     = 0
            _state["bar_locked"]     = False
            _state["high_band_now"]  = 0.0
            _state["energy_short"]   = 0.0
            _state["energy_long"]    = 0.0
            _state["low_short"]      = 0.0
            _state["low_long"]       = 0.0
            _state["ema_count"]      = 0
            _state["ratio_history"].clear()
            _state["phrase"]         = "WAITING"
        _phrase_hold["phrase"] = "WAITING"
        _phrase_hold["ticks"]  = 0

        _stream = sd.InputStream(device=device_id, channels=ch, samplerate=sr,
                                 blocksize=BLOCK_SIZE, callback=_audio_callback)
        _stream.start()
        _stream_dev, _stream_sr, _stream_ch = device_id, sr, ch
        msg = f"[{device_id}] {dev['name']}  @ {sr} Hz / {ch} ch"
        print(f"[plo] Stream offen: {msg}")
        return msg
    except Exception as e:
        print(f"[plo] Stream-Fehler: {e}")
        return f"FEHLER: {e}"


# -----------------------------------------------------------------------------
# Plot + Widgets
# -----------------------------------------------------------------------------
def run(initial_device):
    print("Verfuegbare Eingabegeraete:")
    devices = _list_input_devices()
    for i, name, sr, ch in devices:
        print(f"  [{i}] {name}  ({ch} ch, {sr} Hz)")

    if initial_device is None:
        initial_device = sd.default.device[0] if sd.default.device else (devices[0][0] if devices else None)
    if initial_device is None:
        print("Kein Eingabegeraet gefunden.")
        return

    plt.style.use('dark_background')
    fig = plt.figure(figsize=(14, 7.5))
    fig.canvas.manager.set_window_title("PLO Beat Tracker")

    # --- Plot-Achsen (linke 70 % der Figure) ---
    ax_onset = fig.add_axes([0.06, 0.58, 0.62, 0.36])
    ax_bpm   = fig.add_axes([0.06, 0.27, 0.62, 0.25])
    ax_text  = fig.add_axes([0.06, 0.05, 0.62, 0.16])

    line_onset, = ax_onset.plot([], [], lw=1.2, color='#4fc3f7')
    thresh_line, = ax_onset.plot([], [], lw=0.8, color='#888', linestyle='--', alpha=0.6)
    beat_marks  = ax_onset.scatter([], [], color='#ff5252', s=60, zorder=4, marker='v')
    ax_onset.set_xlim(0, DISPLAY_SEC)
    ax_onset.set_ylim(0, 50)
    ax_onset.set_xlabel("t [s] (rolling)")
    ax_onset.set_ylabel("Onset (Spectral Flux)")
    ax_onset.grid(True, alpha=0.2)

    bpm_history_t   = collections.deque(maxlen=600)
    bpm_history_val = collections.deque(maxlen=600)
    line_bpm, = ax_bpm.plot([], [], lw=2, color='#ffb74d')
    ax_bpm.set_xlim(0, 60)
    ax_bpm.set_ylim(BPM_MIN - 5, BPM_MAX + 5)
    ax_bpm.set_xlabel("t [s]")
    ax_bpm.set_ylabel("BPM")
    ax_bpm.grid(True, alpha=0.2)

    ax_text.axis('off')
    txt_main   = ax_text.text(0.01, 0.70, "", fontsize=24, family='monospace', color='white')
    txt_sub    = ax_text.text(0.01, 0.35, "", fontsize=10, family='monospace', color='#aaa')
    txt_device = ax_text.text(0.01, 0.05, "", fontsize=10, family='monospace', color='#9ae')
    # Phrase-Badge (BREAK / BUILDUP / DROP) rechts in der Hauptzeile
    txt_phrase = ax_text.text(0.99, 0.70, "", fontsize=22, family='monospace',
                              color='white', ha='right', va='center',
                              bbox=dict(boxstyle='round,pad=0.4',
                                        facecolor='#333', edgecolor='#555'))

    # Pegel-Meter — eigene Achse zwischen BPM-Plot und Text-Panel (kein Ueberlapp)
    meter_ax = fig.add_axes([0.06, 0.225, 0.62, 0.025])
    meter_ax.set_xticks([]); meter_ax.set_yticks([])
    meter_ax.set_xlim(0, 1); meter_ax.set_ylim(0, 1)
    for spine in meter_ax.spines.values():
        spine.set_color('#444')
    meter_bar = meter_ax.barh([0.5], [0.0], height=1.0, color='#4caf50')[0]
    fig.text(0.06, 0.255, "INPUT", fontsize=7, color='#888', family='monospace')

    # --- Widgets (rechte 30 %) ---
    fig.text(0.72, 0.93, "Audio Input", fontsize=11, color='#9ae', family='monospace')

    radio_devices = devices[:MAX_DEVICES_IN_RADIO]
    radio_labels  = [f"[{i}] {n[:24]}" for i, n, _, _ in radio_devices]

    # Hoehe abhaengig von Anzahl
    n_dev = max(1, len(radio_labels))
    radio_h = min(0.55, 0.05 * n_dev + 0.05)
    ax_radio = fig.add_axes([0.72, 0.93 - radio_h, 0.26, radio_h])
    ax_radio.set_facecolor('#1a1a1a')

    initial_label_idx = 0
    for k, (i, _, _, _) in enumerate(radio_devices):
        if i == initial_device:
            initial_label_idx = k
            break
    radio = RadioButtons(ax_radio, radio_labels, active=initial_label_idx,
                         activecolor='#4fc3f7')
    for lbl in radio.labels:
        lbl.set_fontsize(8)
        lbl.set_color('white')
        lbl.set_family('monospace')

    fig.text(0.72, 0.20, "Input Gain", fontsize=11, color='#9ae', family='monospace')
    ax_gain = fig.add_axes([0.74, 0.13, 0.22, 0.04])
    gain_slider = Slider(ax_gain, '', 0.0, 8.0, valinit=1.0, valstep=0.1,
                         color='#ffb74d')
    gain_slider.label.set_color('white')
    gain_slider.valtext.set_color('white')

    # Bedienhinweise
    fig.text(0.72, 0.07,
             "LEERTASTE: 'das hier ist Beat 1'\n"
             "Klick auf Counter-Plot: Counter reset",
             fontsize=8, color='#888', family='monospace')

    # --- Callbacks ---
    def on_device_change(label):
        for k, l in enumerate(radio_labels):
            if l == label:
                dev_id = radio_devices[k][0]
                msg = _open_stream(dev_id)
                txt_device.set_text(f"DEVICE: {msg}")
                fig.canvas.draw_idle()
                return
    radio.on_clicked(on_device_change)

    def on_gain_change(val):
        global _gain
        _gain = float(val)
    gain_slider.on_changed(on_gain_change)

    def on_key(event):
        # Leertaste: aktuellen Beat als Beat 1 setzen + Phase auf 0 snappen
        if event.key == ' ':
            with _lock:
                cnt = _state["beat_count"]
                # bar_offset so setzen, dass (cnt + offset) % 4 + 1 == 1
                _state["bar_offset"] = (-cnt) % 4
                _state["bar_locked"] = True
                # Phase hart auf 0 (jetzt = exakter Beat-Zeitpunkt)
                _state["phase"] = 0.0
                _state["phase_at_onset"].clear()
            print(f"[plo] Beat 1 manuell gesetzt (offset={_state['bar_offset']})")
    fig.canvas.mpl_connect('key_press_event', on_key)

    def on_click(event):
        # Klick in den BPM- oder Text-Plot resettet den Counter
        if event.inaxes in (ax_bpm, ax_text):
            with _lock:
                _state["beat_count"]   = 0
                _state["beats"].clear()
                _state["beat_energies"].clear()
                _state["bar_offset"]   = 0
                _state["bar_locked"]   = False
    fig.canvas.mpl_connect('button_press_event', on_click)

    # --- Threads + Stream starten ---
    t_start = time.time()
    stop_evt = threading.Event()
    tempo_th = threading.Thread(target=_tempo_loop, args=(stop_evt,), daemon=True)
    plo_th   = threading.Thread(target=_plo_loop,   args=(stop_evt,), daemon=True)

    msg = _open_stream(initial_device)
    txt_device.set_text(f"DEVICE: {msg}")

    def update(_):
        now = time.time()
        with _lock:
            ts        = list(_onset_times)
            os_       = list(_onset_history)
            bpm       = _state["bpm"]
            cnt       = _state["beat_count"]
            phase     = _state["phase"]
            beats     = list(_state["beats"])
            peak      = _state["input_peak"]
            locked    = _state["bpm_locked"]
            conf      = _state["bpm_confidence"]
            status    = _state["tempo_status"]
            bar_off   = _state["bar_offset"]
            bar_lock  = _state["bar_locked"]
            phrase    = _state["phrase"]
            # Display-BPM ist sehr langsamer EMA des internen Werts.
            # Bei Lock noch staerker glaetten (alpha=0.04, ~0.8s Zeitkonstante @30Hz),
            # bei SEEK soll man die schnellen Spruenge sehen (alpha=0.20).
            disp_alpha = 0.04 if locked else 0.20
            _state["bpm_display"] = (1.0 - disp_alpha) * _state["bpm_display"] + disp_alpha * bpm
            bpm_display = _state["bpm_display"]

        if ts:
            t0 = now - DISPLAY_SEC
            xs, ys = [], []
            for t, v in zip(ts, os_):
                if t >= t0:
                    xs.append(t - t0); ys.append(v)
            line_onset.set_data(xs, ys)
            ax_onset.set_xlim(0, DISPLAY_SEC)
            if ys:
                ymax = max(20.0, max(ys) * 1.15)
                ax_onset.set_ylim(0, ymax)
                arr = np.array(ys[-int(ONSET_FPS * 1.5):]) if len(ys) >= 4 else np.array(ys)
                med = float(np.median(arr))
                mad = float(np.median(np.abs(arr - med))) + 1e-6
                th  = max(med + ONSET_K_MAD * mad, ONSET_ABS_FLOOR)
                thresh_line.set_data([0, DISPLAY_SEC], [th, th])

            beat_xs = [b - t0 for b in beats if b >= t0]
            if beat_xs:
                ymax = ax_onset.get_ylim()[1]
                beat_marks.set_offsets(np.column_stack([beat_xs, np.full(len(beat_xs), ymax * 0.93)]))
            else:
                beat_marks.set_offsets(np.empty((0, 2)))

        bpm_history_t.append(now - t_start)
        bpm_history_val.append(bpm_display)
        line_bpm.set_data(list(bpm_history_t), list(bpm_history_val))
        if bpm_history_t:
            xmax = bpm_history_t[-1]
            ax_bpm.set_xlim(max(0, xmax - 60), max(60, xmax + 1))

        # Bar-Aware Counting: bar_off so verschoben dass Backbeats auf 2/4 landen
        if cnt > 0:
            adj         = (cnt - 1 + bar_off) % 4
            beat_in_bar = adj + 1                   # 1..4
            bar_in_phr  = ((cnt - 1 + bar_off) // 4) % 8 + 1   # 1..8 (32-Beat-Phrase)
            beat_in_phr = (cnt - 1 + bar_off) % 32 + 1         # 1..32
        else:
            beat_in_bar, bar_in_phr, beat_in_phr = 1, 1, 1

        flash = " <" if phase < 0.10 or phase > 0.90 else "  "
        bar_tag  = "BAR-LOCK" if bar_lock else "bar?  "
        downbeat = "*" if beat_in_bar == 1 else " "   # Hervorhebung Beat 1
        lock_tag = "[LOCK]" if locked else f"[{status}]"
        txt_main.set_text(
            f"BPM:{bpm_display:6.1f} {lock_tag:8} {downbeat}Beat:{beat_in_bar}/4{flash}"
            f"  Bar:{bar_in_phr}/8  #{beat_in_phr}/32"
        )
        # Farbe gibt sofortiges Feedback ueber Tempo-Status
        if status == "LOCK":
            txt_main.set_color('#69f0ae')        # gruen = stabil
        elif status == "BREAK":
            txt_main.set_color('#ffb74d')        # orange = Break, BPM eingefroren
        elif status == "SEEK":
            txt_main.set_color('#4fc3f7')        # blau = sucht
        else:
            txt_main.set_color('white')          # init
        txt_sub.set_text(
            f"phase={phase:.3f}  conf={conf:.2f}  {bar_tag}  off={bar_off}  "
            f"onset_fps={ONSET_FPS:.1f}  alpha={PLO_ALPHA}  gain={_gain:.1f}x"
        )

        # Phrase-Badge mit Farbe
        phrase_colors = {
            "BREAK":   ('#1976d2', '#0d47a1'),   # blau (ruhig)
            "BUILDUP": ('#f57c00', '#e65100'),   # orange (steigend)
            "DROP":    ('#d32f2f', '#b71c1c'),   # rot (Peak)
            "WAITING": ('#444',    '#666'),
        }
        bg, edge = phrase_colors.get(phrase, ('#333', '#555'))
        txt_phrase.set_text(f" {phrase:8s}")
        txt_phrase.get_bbox_patch().set_facecolor(bg)
        txt_phrase.get_bbox_patch().set_edgecolor(edge)

        meter_bar.set_width(min(1.0, peak))
        if peak > 0.9:    meter_bar.set_color('#ff5252')
        elif peak > 0.6:  meter_bar.set_color('#ffb74d')
        else:             meter_bar.set_color('#4caf50')

        return (line_onset, thresh_line, beat_marks, line_bpm,
                txt_main, txt_sub, txt_device, txt_phrase, meter_bar)

    try:
        tempo_th.start()
        plo_th.start()
        print(">> Plot offen. Geraet rechts auswaehlen, Gain einstellen.\n")
        ani = FuncAnimation(fig, update, interval=33, blit=False, cache_frame_data=False)
        plt.show()
    finally:
        stop_evt.set()
        tempo_th.join(timeout=1.0)
        plo_th.join(timeout=1.0)
        _close_stream()


if __name__ == "__main__":
    dev = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run(dev)
