"""
audio_live.py — Live-Audio-Eingang fuer light2wave.

Duenne Wrapper-Schicht um die `PLOEngine` (audio/plo_engine.py).
Behaelt den ueberlappenden `live_audio_state`-Vertrag damit alle
existierenden Konsumenten (backend/audio_loop.py, backend/state.py,
gui/tabs/audio.py, audio/prolink_source.py) ohne Aenderung weiterlaufen.

Frueheres Setup mit ML-Modell + Kick-Bandpass-Detection wurde durch
die deterministische PLO-Engine ersetzt — sauberer, schneller, ohne
PyTorch-Abhaengigkeit im Live-Pfad.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from audio.plo_engine import PLOEngine, get_input_devices  # noqa: F401


# -----------------------------------------------------------------------------
# Public State - Vertrag mit Konsumenten
# -----------------------------------------------------------------------------
live_audio_state = {
    "is_listening":        False,
    "device_id":           None,
    "sensitivity":         3.5,        # nicht mehr genutzt, fuer Compat behalten

    # Beat-Events
    "beat_triggered":      False,      # einmal True pro Beat — Konsument loescht
    "beat_index":          0,          # 0..3 (Beat in Bar — Compat-Name)
    "beat_in_bar":         0,          # 0..3 (PLO-Engine Counter)
    "beat_in_phrase":      0,          # 0..31 (32-Beat-Phrase)
    "bar_in_phrase":       0,          # 0..7 (Bar in 8-Bar-Phrase)
    "beat_phase":          0.0,        # 0..1 — kontinuierliche Oszillator-Phase

    # Tempo
    "bpm":                 120.0,
    "bpm_locked":          False,
    "bar_locked":          False,
    "tempo_status":        "INIT",     # INIT | SEEK | LOCK | BREAK | MANUAL

    # Phrase
    "phase":               "WAITING",  # WAITING | BREAK | BUILDUP | DROP

    # Pegel
    "volume":              0.0,        # 0..1 Input-Peak
    "level":               0.0,        # 0..1 (Compat — wird auf input_peak gemappt)
    "transient_triggered": False,      # Compat — wird bei Beat-1-Wechsel getriggert
    "energy_level":        0.5,        # 0..1 normalisierte Energie

    # Mode
    "mode":                "AUTO",     # AUTO | MANUAL
    "ml_active":           False,      # immer False - Compat
}


# -----------------------------------------------------------------------------
# Engine + Bridge-Thread
# -----------------------------------------------------------------------------
_engine: Optional[PLOEngine] = None
_bridge_stop = threading.Event()
_bridge_th: Optional[threading.Thread] = None
_BRIDGE_HZ = 60   # Snapshot-Rate fuer live_audio_state-Updates


def _ensure_engine() -> PLOEngine:
    global _engine
    if _engine is None:
        _engine = PLOEngine()
    return _engine


def _bridge_loop() -> None:
    """Pollt die Engine periodisch und schreibt in live_audio_state."""
    global _engine
    last_phrase = None
    last_beat_in_bar = None
    period = 1.0 / _BRIDGE_HZ

    # Geglaettete Werte fuer ruhige Lampen-Ansteuerung
    smooth = {
        "energy_level": 0.5,   # konvergiert langsam, treibt energy_brightness
        "volume":       0.0,
        "level":        0.0,
    }
    # EMA-Faktoren bei 60 Hz Bridge-Rate
    # 0.05 = ~250 ms Zeitkonstante (energy/dimmer), 0.25 = ~60 ms (Pegelmeter)
    A_ENERGY = 0.05
    A_PEAK   = 0.25

    while not _bridge_stop.is_set():
        time.sleep(period)
        eng = _engine
        if eng is None:
            continue
        snap = eng.snapshot()
        n_beats      = eng.consume_beat_events()
        n_transients = eng.consume_transient_events()

        if n_beats > 0:
            live_audio_state["beat_triggered"] = True
        if n_transients > 0:
            # ECHTE Hi-Band-Spikes (Claps/Synth) - keine kuenstlichen Beat-Wechsel
            live_audio_state["transient_triggered"] = True

        # Counter / Phase
        live_audio_state["beat_index"]     = snap["beat_in_bar"]
        live_audio_state["beat_in_bar"]    = snap["beat_in_bar"]
        live_audio_state["beat_in_phrase"] = snap["beat_in_phrase"]
        live_audio_state["bar_in_phrase"]  = snap["bar_in_phrase"]
        live_audio_state["beat_phase"]     = round(snap["phase"], 4)

        # Tempo / Status
        live_audio_state["bpm"]           = round(snap["bpm"], 2)
        live_audio_state["bpm_locked"]    = snap["bpm_locked"]
        live_audio_state["bar_locked"]    = snap["bar_locked"]
        live_audio_state["tempo_status"]  = snap["tempo_status"]
        live_audio_state["mode"]          = snap["mode"]
        live_audio_state["phase"]         = snap["phrase"]

        # Geglaettete Pegel (60 ms Zeitkonstante) — verhindert VU-Meter-Zucken
        peak = snap["input_peak"]
        smooth["volume"] = (1 - A_PEAK) * smooth["volume"] + A_PEAK * min(peak * 1.5, 1.0)
        smooth["level"]  = (1 - A_PEAK) * smooth["level"]  + A_PEAK * min(peak * 2.5, 1.0)
        live_audio_state["volume"] = smooth["volume"]
        live_audio_state["level"]  = smooth["level"]

        # Energy-Level aus bias-korrigierter Ratio: musikalisch sinnvoll,
        # Mid-Track ~1.0 -> 0.5, Drop ~1.6 -> 1.0, Break ~0.5 -> 0.08.
        # Stark geglaettet (250 ms) damit Magic-Auto-Dimmer NICHT jeden
        # Bridge-Tick wackelt → 'zucken' weg.
        ratio  = snap.get("energy_ratio", 1.0)
        target = max(0.0, min(1.0, (ratio - 0.4) / 1.2))
        smooth["energy_level"] = (1 - A_ENERGY) * smooth["energy_level"] + A_ENERGY * target
        live_audio_state["energy_level"] = smooth["energy_level"]

        # last_beat_in_bar fuer evtl. zukuenftige Per-Bar-Logik beibehalten
        if snap["beat_in_bar"] != last_beat_in_bar:
            last_beat_in_bar = snap["beat_in_bar"]

        if snap["phrase"] != last_phrase:
            print(f"[audio_live] Phrase: {last_phrase or 'INIT'} -> {snap['phrase']}")
            last_phrase = snap["phrase"]


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def start_listening(device_id):
    """Startet Audio-Stream + PLO-Engine + Bridge-Thread."""
    global _bridge_th
    eng = _ensure_engine()

    if eng.is_running():
        stop_listening()

    ok, msg = eng.start(int(device_id))
    if not ok:
        live_audio_state["is_listening"] = False
        return False, msg

    live_audio_state["is_listening"] = True
    live_audio_state["device_id"]    = device_id
    live_audio_state["phase"]        = "WAITING"
    live_audio_state["beat_triggered"] = False
    live_audio_state["bpm"]          = 120.0
    live_audio_state["beat_count"]   = 0

    _bridge_stop.clear()
    _bridge_th = threading.Thread(target=_bridge_loop, daemon=True, name='audio-bridge')
    _bridge_th.start()

    print(f"[audio_live] Stream + PLO-Engine gestartet: {msg}")
    return True, msg


def stop_listening():
    """Beendet Bridge + Engine + Stream."""
    global _bridge_th
    live_audio_state["is_listening"] = False

    _bridge_stop.set()
    if _bridge_th is not None:
        _bridge_th.join(timeout=1.5)
    _bridge_th = None

    if _engine is not None:
        _engine.stop()


# -----------------------------------------------------------------------------
# Mode + Manual-Kontrollen
# -----------------------------------------------------------------------------
def set_mode(mode: str) -> None:
    """AUTO | MANUAL — schaltet zwischen Auto-Tracking und manueller BPM."""
    eng = _ensure_engine()
    eng.set_mode(mode)
    live_audio_state["mode"] = mode


def set_manual_bpm(bpm: float) -> None:
    """Setzt die manuelle BPM (wird in MANUAL-Mode benutzt)."""
    eng = _ensure_engine()
    eng.set_manual_bpm(float(bpm))


def mark_downbeat() -> None:
    """'Das hier ist Beat 1.' — Phase + Bar-Offset werden so gesetzt
    dass der aktuelle Moment als Beat 1 gilt."""
    if _engine is not None:
        _engine.mark_downbeat()


def set_input_gain(gain: float) -> None:
    """Software-Gain auf das Input-Signal (0..8)."""
    if _engine is not None:
        _engine.set_gain(gain)
