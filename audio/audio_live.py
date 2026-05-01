import numpy as np
import sounddevice as sd
from scipy.signal import butter, lfilter
import time
import threading
import sys
import os

# --- ML Integration (optional) -----------------------------------------------
_ML_AVAILABLE = False
try:
    _ML_DIR = os.path.join(os.path.dirname(__file__), '..', 'machinelearning')
    sys.path.insert(0, os.path.abspath(_ML_DIR))
    import config as ml_config
    from utils.audio_features import RollingMelBuffer
    from model import load_model
    from utils.label_utils import phase_idx_to_name
    import torch
    _ML_AVAILABLE = True
except Exception as _ml_err:
    print(f"[audio_live] ML-Import nicht verfuegbar: {_ml_err}")

# Samplerate passend zum ML-Modell (22050Hz). Kick-Detection funktioniert
# bei 22050Hz genauso gut — Nyquist liegt bei 11025Hz, weit ueber 150Hz.
SAMPLE_RATE = ml_config.SAMPLE_RATE if _ML_AVAILABLE else 22050

# --- Globaler State (Interface nach aussen unveraendert) ----------------------
live_audio_state = {
    "is_listening":        False,
    "beat_triggered":      False,
    "beat_index":          0,
    "level":               0.0,
    "sensitivity":         3.5,
    "device_id":           None,
    "phase":               "WAITING",
    "volume":              0.0,
    "ml_active":           False,   # True wenn ML-Modell die Phase liefert
    "transient_triggered": False,   # High-Band Spike (Synth/Transient)
    "energy_level":        0.5,     # Langzeit-Energie-Verhältnis (0.0 - 1.0)
}

_stream                = None
_kick_energy_history   = np.zeros(20)
_last_kick_time        = 0.0
_short_term_energy     = np.zeros(10)   # ~0.5s
_long_term_energy      = np.zeros(100)  # ~5s

# Transient / High-Band Detektion (1-8 kHz)
_high_energy_history   = np.zeros(30)
_last_transient_time   = 0.0

# ML-Zustand
_mel_buffer        = None
_ml_model          = None
_ml_device         = None
_sample_remainder  = np.zeros(0, dtype=np.float32)
_inference_thread  = None


# -----------------------------------------------------------------------------

def get_input_devices():
    devices = sd.query_devices()
    inputs = {}
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            inputs[i] = f"{i}: {d['name']}"
    return inputs


def bandpass(data, low=40, high=150, fs=SAMPLE_RATE):
    b, a = butter(4, [low / (fs / 2), high / (fs / 2)], btype='band')
    return lfilter(b, a, data)


def _highband(data, low=1000, high=8000, fs=SAMPLE_RATE):
    nyq = fs / 2
    b, a = butter(4, [low / nyq, min(high / nyq, 0.999)], btype='band')
    return lfilter(b, a, data)


def _try_load_ml_model() -> bool:
    """Laedt das trainierte ML-Modell. Gibt True zurueck bei Erfolg."""
    global _ml_model, _ml_device, _mel_buffer
    if not _ML_AVAILABLE:
        return False
    try:
        if not os.path.exists(ml_config.MODEL_SAVE_PATH):
            print("[audio_live] Kein trainiertes Modell gefunden — einfache Erkennung aktiv.")
            return False
        _ml_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        _ml_model  = load_model(ml_config.MODEL_SAVE_PATH).to(_ml_device)
        _ml_model.eval()
        _mel_buffer = RollingMelBuffer()
        print(f"[audio_live] ML-Modell geladen ({_ml_device}) — Phase-Erkennung aktiv")
        return True
    except Exception as e:
        print(f"[audio_live] ML-Laden fehlgeschlagen: {e}")
        return False


def _run_ml_inference():
    """Laeuft in einem Daemon-Thread. Fuehrt Modell-Inferenz durch und
    aktualisiert live_audio_state['phase']."""
    if _ml_model is None or _mel_buffer is None or not _mel_buffer.is_ready:
        return
    try:
        window = _mel_buffer.get_window()                           # (CONTEXT_FRAMES, N_MELS)
        mel_t  = torch.from_numpy(window.T).unsqueeze(0).to(_ml_device)  # (1, N_MELS, CTX)
        with torch.no_grad():
            outputs = _ml_model(mel_t)
        phrase_type = int(torch.argmax(outputs['phase_type'][0]).item())
        phase_name  = phase_idx_to_name(phrase_type)
        if live_audio_state["is_listening"]:
            live_audio_state["phase"] = phase_name
    except Exception:
        pass


def _audio_callback(indata, frames, time_info, status):
    global _kick_energy_history, _last_kick_time
    global _short_term_energy, _long_term_energy
    global _high_energy_history, _last_transient_time
    global _sample_remainder, _inference_thread

    if not live_audio_state["is_listening"]:
        return

    mono = np.mean(indata, axis=1).astype(np.float32)

    # ── 1. Lautstaerke / einfache Phase (Fallback) ───────────────────────────
    overall_rms = float(np.sqrt(np.mean(mono ** 2)))
    if np.isnan(overall_rms):
        overall_rms = 0.0

    _short_term_energy = np.roll(_short_term_energy, -1)
    _short_term_energy[-1] = overall_rms
    _long_term_energy  = np.roll(_long_term_energy,  -1)
    _long_term_energy[-1]  = overall_rms

    short_avg = float(np.mean(_short_term_energy))
    long_avg  = float(np.mean(_long_term_energy))
    ratio     = 1.0

    if long_avg > 0:
        ratio = short_avg / long_avg
        if not live_audio_state["ml_active"]:
            # Einfache Schwellwert-Erkennung nur wenn kein ML aktiv
            if ratio < 0.8:
                live_audio_state["phase"] = "BREAK"
            elif ratio > 1.2:
                live_audio_state["phase"] = "DROP"
            else:
                if live_audio_state["phase"] == "BREAK":
                    live_audio_state["phase"] = "BUILDUP"

    # ── 2. Beat-Erkennung (Kick-Band 40–150 Hz) ──────────────────────────────
    kick_band = bandpass(mono)
    energy    = float(np.sum(kick_band ** 2))

    _kick_energy_history = np.roll(_kick_energy_history, -1)
    _kick_energy_history[-1] = energy

    threshold = float(np.mean(_kick_energy_history)) * live_audio_state["sensitivity"]

    live_audio_state["volume"] = min(overall_rms * 4.0, 1.0)
    live_audio_state["level"]  = min(energy / (threshold if threshold > 0 else 1), 1.5) / 1.5

    now = time.time()
    if energy > threshold and (now - _last_kick_time) > 0.25:
        _last_kick_time = now
        live_audio_state["beat_triggered"] = True
        live_audio_state["beat_index"]     = (live_audio_state["beat_index"] + 1) % 4
        # Beat-basierter Phase-Hint nur ohne ML
        if not live_audio_state["ml_active"] and ratio >= 0.9:
            live_audio_state["phase"] = "DROP"

    # ── 3. Transient / High-Band Detektion (1–8 kHz) ─────────────────────────
    high_band    = _highband(mono)
    high_energy  = float(np.sum(high_band ** 2))
    _high_energy_history = np.roll(_high_energy_history, -1)
    _high_energy_history[-1] = high_energy
    high_avg     = float(np.mean(_high_energy_history))
    high_thresh  = high_avg * 2.5
    if high_energy > high_thresh and high_avg > 1e-8 and (now - _last_transient_time) > 0.12:
        _last_transient_time = now
        live_audio_state["transient_triggered"] = True

    # ── 4. Langzeit-Energie (0–1) für Helligkeits-Skalierung ─────────────────
    # ratio = short_avg / long_avg; <1 = ruhig, >1 = energetisch
    if long_avg > 0:
        live_audio_state["energy_level"] = max(0.0, min(1.0, (ratio - 0.4) / 1.2))
    else:
        live_audio_state["energy_level"] = 0.5

    # ── 5. ML-Inferenz ───────────────────────────────────────────────────────
    if live_audio_state["ml_active"] and _mel_buffer is not None:
        hop      = ml_config.HOP_LENGTH
        combined = np.concatenate([_sample_remainder, mono])
        idx      = 0
        while idx + hop <= len(combined):
            _mel_buffer.push_samples(combined[idx:idx + hop])
            idx += hop
        _sample_remainder = combined[idx:].copy()

        # Inferenz-Thread starten wenn Buffer bereit und kein Thread laeuft
        if (_inference_thread is None or not _inference_thread.is_alive()) \
                and _mel_buffer.is_ready:
            _inference_thread = threading.Thread(
                target=_run_ml_inference, daemon=True
            )
            _inference_thread.start()


def start_listening(device_id):
    global _stream, _kick_energy_history, _short_term_energy, _long_term_energy
    global _high_energy_history, _last_transient_time
    global _mel_buffer, _sample_remainder

    if _stream is not None:
        stop_listening()

    try:
        dev_info = sd.query_devices(device_id)
        channels = min(2, dev_info['max_input_channels'])

        # State zuruecksetzen
        _kick_energy_history[:] = 0
        _short_term_energy[:]   = 0
        _long_term_energy[:]    = 0
        _high_energy_history[:] = 0
        _last_transient_time    = 0.0
        _sample_remainder       = np.zeros(0, dtype=np.float32)

        # ML-Modell laden
        ml_ok = _try_load_ml_model()
        live_audio_state["ml_active"] = ml_ok
        if ml_ok and _mel_buffer is not None:
            _mel_buffer = RollingMelBuffer()  # frischer Buffer

        live_audio_state["is_listening"]   = True
        live_audio_state["device_id"]      = device_id
        live_audio_state["phase"]          = "WAITING"
        live_audio_state["beat_triggered"] = False

        _stream = sd.InputStream(
            device=device_id,
            channels=channels,
            samplerate=SAMPLE_RATE,   # 22050 Hz (ML-kompatibel)
            blocksize=2048,
            callback=_audio_callback,
        )
        _stream.start()

        mode = "ML-Modell (BREAK/BUILDUP/DROP)" if ml_ok else "einfache RMS-Erkennung"
        print(f"[audio_live] Stream gestartet @ {SAMPLE_RATE}Hz | Modus: {mode}")
        return True, "Gestartet"

    except Exception as e:
        live_audio_state["is_listening"] = False
        live_audio_state["ml_active"]    = False
        return False, str(e)


def stop_listening():
    global _stream
    live_audio_state["is_listening"] = False
    live_audio_state["ml_active"]    = False
    if _stream:
        _stream.stop()
        _stream.close()
        _stream = None
