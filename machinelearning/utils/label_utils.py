"""
Label-Erzeugung: Wandelt Beat-Zeiten und Phrasen-Infos in frame-level Labels um.

Für jeden Mel-Frame berechnen wir:
  1. beat_phase  [0.0 – 1.0]   Position innerhalb des aktuellen Beats
                               (0 = Beat, 0.5 = Mitte, 0.99 = kurz vor dem nächsten Beat)
                               Als sin/cos kodiert → kein Sprung am Übergang!

  2. beat_in_bar [0 – 15]      Welcher Beat innerhalb einer 16-Beat Phrase
                               (0 = erster Beat / Downbeat, 15 = letzter)

  3. phrase_type [0 – 9]       Pioneer Phrasen-Kategorie
                               (0 = unbekannt, 1 = Intro, 4 = Chorus, ...)
"""
import numpy as np
from typing import List

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from utils.rekordbox_parser import TrackData


def compute_labels(track: TrackData, n_frames: int):
    """
    Berechnet frame-level Labels für einen Track.

    Args:
        track:    TrackData Objekt mit beat_times und phrases
        n_frames: Anzahl der Frames im Mel-Spektrogramm

    Returns:
        beat_phase_sin: np.ndarray shape (n_frames,)  sin(2π × phase)
        beat_phase_cos: np.ndarray shape (n_frames,)  cos(2π × phase)
        beat_in_bar:    np.ndarray shape (n_frames,)  int, 0-15
        phrase_type:    np.ndarray shape (n_frames,)  int, 0-9
    """
    frame_times = np.arange(n_frames) * config.HOP_LENGTH / config.SAMPLE_RATE

    beat_phase_sin = np.zeros(n_frames, dtype=np.float32)
    beat_phase_cos = np.ones(n_frames, dtype=np.float32)   # cos(0) = 1 als Default
    beat_in_bar    = np.zeros(n_frames, dtype=np.int64)
    phrase_type    = np.zeros(n_frames, dtype=np.int64)    # 0 = unknown

    beats = track.beat_times
    if len(beats) < 2:
        return beat_phase_sin, beat_phase_cos, beat_in_bar, phrase_type

    # ── Beat-Phase und Beat-in-Bar ──────────────────────────────────────────
    for frame_idx, t in enumerate(frame_times):
        # Finde den letzten Beat vor diesem Frame
        beat_idx = np.searchsorted(beats, t, side='right') - 1
        beat_idx = max(0, min(beat_idx, len(beats) - 2))

        beat_start = beats[beat_idx]
        beat_end   = beats[beat_idx + 1]
        beat_dur   = beat_end - beat_start

        if beat_dur > 0:
            phase = (t - beat_start) / beat_dur
        else:
            phase = 0.0
        phase = float(np.clip(phase, 0.0, 1.0))

        # sin/cos Kodierung → kein Sprung am 0→1 Übergang
        angle = 2.0 * np.pi * phase
        beat_phase_sin[frame_idx] = np.sin(angle)
        beat_phase_cos[frame_idx] = np.cos(angle)

        # Beat-Position innerhalb 16er-Raster
        beat_in_bar[frame_idx] = beat_idx % config.NUM_BEATS_IN_BAR

    # ── Phrasen-Typ ──────────────────────────────────────────────────────────
    if track.has_phrases:
        phrase_times = np.array([p.time_sec for p in track.phrases])
        phrase_kinds = np.array([p.kind for p in track.phrases])

        for frame_idx, t in enumerate(frame_times):
            # Letzter Phrasen-Start vor diesem Frame
            pidx = np.searchsorted(phrase_times, t, side='right') - 1
            if 0 <= pidx < len(phrase_kinds):
                kind = int(phrase_kinds[pidx])
                # Clamp auf gültige Klassen
                phrase_type[frame_idx] = min(kind, config.NUM_PHRASE_TYPES - 1)

    return beat_phase_sin, beat_phase_cos, beat_in_bar, phrase_type


def decode_beat_phase(sin_val: float, cos_val: float) -> float:
    """Wandelt sin/cos Outputs des Modells zurück in Phase [0, 1]."""
    angle = np.arctan2(sin_val, cos_val)
    phase = angle / (2.0 * np.pi)
    return float(phase % 1.0)


def phrase_kind_to_name(kind: int) -> str:
    """Gibt den menschenlesbaren Namen für einen Phrasen-Typ zurück."""
    return config.PHRASE_KINDS.get(kind, f"kind_{kind}")


def label_summary(phrase_type_array: np.ndarray) -> dict:
    """Gibt Statistiken über die Phrasen-Verteilung zurück (für Debugging)."""
    unique, counts = np.unique(phrase_type_array, return_counts=True)
    total = len(phrase_type_array)
    return {
        phrase_kind_to_name(int(k)): f"{c/total*100:.1f}%"
        for k, c in zip(unique, counts)
    }
