"""
Label-Erzeugung für das ML-Training.

Beat-Labels:   aus PQT2 Beat-Grid (exakte Ground Truth von Rekordbox)
Phasen-Labels: aus Librosa Audio-Analyse (auto-generiert, song-relativ)

Phasen-Logik (BREAK / BUILDUP / DROP):
  Wir nutzen 4 Features pro Beat, normiert auf den jeweiligen Song:
    1. RMS Energie          → wie laut ist der Moment
    2. Bass Ratio           → wie viel Bassanteil (40-250Hz)
    3. Spectral Flux        → wie stark ändert sich das Spektrum (Onset-Dichte)
    4. Spectral Centroid    → Helligkeit (hoch bei vollen Drops, niedrig bei Breaks)

  Daraus ein "Energie-Score" [0-1] pro Beat → Percentile-basierte Labels:
    Score < 30. Percentile  → BREAK
    Score > 65. Percentile  → DROP
    Dazwischen              → BUILDUP

  Weil der Score relativ zum Song normiert ist, funktioniert das bei
  lautem Techno genauso wie bei leisem Ambient.
"""
import numpy as np
import librosa

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


# ─── BEAT LABELS ──────────────────────────────────────────────────────────────

def compute_beat_labels(beat_times: np.ndarray, n_frames: int):
    """
    Berechnet frame-level Beat-Labels aus dem PQT2 Beat-Grid.

    Returns:
        beat_phase_sin:  (n_frames,) float32  — sin(2π × phase)
        beat_phase_cos:  (n_frames,) float32  — cos(2π × phase)
        beat_in_bar:     (n_frames,) int64    — 0-3 (Viertelnote im 4/4 Takt)
    """
    frame_times = np.arange(n_frames) * config.HOP_LENGTH / config.SAMPLE_RATE

    beat_phase_sin = np.zeros(n_frames, dtype=np.float32)
    beat_phase_cos = np.ones(n_frames, dtype=np.float32)
    beat_in_bar    = np.zeros(n_frames, dtype=np.int64)

    if len(beat_times) < 2:
        return beat_phase_sin, beat_phase_cos, beat_in_bar

    for i, t in enumerate(frame_times):
        # Letzter Beat vor diesem Frame
        beat_idx = int(np.searchsorted(beat_times, t, side='right')) - 1
        beat_idx = max(0, min(beat_idx, len(beat_times) - 2))

        beat_start = beat_times[beat_idx]
        beat_dur   = beat_times[beat_idx + 1] - beat_start

        phase = float(np.clip((t - beat_start) / beat_dur, 0.0, 1.0)) if beat_dur > 0 else 0.0

        angle = 2.0 * np.pi * phase
        beat_phase_sin[i] = np.sin(angle)
        beat_phase_cos[i] = np.cos(angle)
        beat_in_bar[i]    = beat_idx % config.NUM_BEATS_IN_BAR

    return beat_phase_sin, beat_phase_cos, beat_in_bar


# ─── PHASEN LABELS (LIBROSA) ──────────────────────────────────────────────────

def compute_phase_labels(y: np.ndarray, beat_times: np.ndarray, n_frames: int) -> np.ndarray:
    """
    Erzeugt frame-level Phasen-Labels (BREAK=0, BUILDUP=1, DROP=2)
    aus dem Audio-Signal mittels Librosa.

    Strategie:
      1. Berechne 4 Audio-Features für jeden Beat
      2. Kombiniere sie zu einem Energie-Score pro Beat
      3. Mappe via Percentile auf BREAK/BUILDUP/DROP
      4. Interpoliere auf Frame-Ebene

    Args:
        y:           Audio-Signal (mono, float32)
        beat_times:  Beat-Zeiten in Sekunden (aus PQT2)
        n_frames:    Anzahl Mel-Frames im Track

    Returns:
        phase_labels: (n_frames,) int64, Werte 0/1/2
    """
    sr = config.SAMPLE_RATE
    hop = config.HOP_LENGTH
    n_beats = len(beat_times)

    if n_beats < 4:
        return np.full(n_frames, config.PHASE_DROP, dtype=np.int64)

    # ── Feature 1: RMS Energie pro Frame ─────────────────────────────────────
    rms = librosa.feature.rms(y=y, frame_length=config.N_FFT, hop_length=hop)[0]  # (n_frames,)

    # ── Feature 2: Bass Ratio (40–250Hz vs Gesamt) ───────────────────────────
    # Kurzes STFT für Frequenzanalyse
    S = np.abs(librosa.stft(y, n_fft=config.N_FFT, hop_length=hop))  # (n_fft/2+1, n_frames)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=config.N_FFT)

    bass_mask = (freqs >= 40) & (freqs <= 250)
    bass_energy   = S[bass_mask].sum(axis=0)
    total_energy  = S.sum(axis=0) + 1e-8
    bass_ratio    = bass_energy / total_energy  # (n_frames,)

    # ── Feature 3: Spectral Flux (Onset-Dichte) ──────────────────────────────
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)  # (n_frames,)

    # ── Feature 4: Spectral Centroid (Helligkeit) ────────────────────────────
    centroid = librosa.feature.spectral_centroid(S=S, sr=sr)[0]  # (n_frames,)

    # ── Beat-Synchrone Aggregation ────────────────────────────────────────────
    # Für jeden Beat: Mittelwert der Features in diesem Beat-Intervall
    beat_rms      = np.zeros(n_beats)
    beat_bass     = np.zeros(n_beats)
    beat_flux     = np.zeros(n_beats)
    beat_centroid = np.zeros(n_beats)

    n_mel_frames = len(rms)

    for b_idx in range(n_beats):
        t_start = beat_times[b_idx]
        t_end   = beat_times[b_idx + 1] if b_idx + 1 < n_beats else t_start + 0.5

        f_start = int(t_start * sr / hop)
        f_end   = int(t_end   * sr / hop)
        f_start = max(0, min(f_start, n_mel_frames - 1))
        f_end   = max(f_start + 1, min(f_end, n_mel_frames))

        beat_rms[b_idx]      = rms[f_start:f_end].mean()
        beat_bass[b_idx]     = bass_ratio[f_start:f_end].mean()
        beat_flux[b_idx]     = onset_env[f_start:f_end].mean()
        beat_centroid[b_idx] = centroid[f_start:f_end].mean()

    # ── Energie-Score: gewichtete Kombination ────────────────────────────────
    def normalize(x):
        mn, mx = x.min(), x.max()
        return (x - mn) / (mx - mn + 1e-8)

    score = (
        0.35 * normalize(beat_rms)      +   # Gesamtlautstärke
        0.30 * normalize(beat_flux)     +   # Onset-Dichte (viele Events = Drop)
        0.20 * normalize(beat_bass)     +   # Bass-Anteil (Kick = Drop)
        0.15 * normalize(beat_centroid)     # Helligkeit
    )

    # ── Glättung über 4 Beats (verhindert Flackern) ──────────────────────────
    kernel = np.ones(4) / 4
    score = np.convolve(score, kernel, mode='same')

    # ── Percentile-basierte Labels ───────────────────────────────────────────
    p_break  = np.percentile(score, 30)  # untere 30% = BREAK
    p_drop   = np.percentile(score, 65)  # obere 35% = DROP

    beat_phase_labels = np.where(
        score < p_break,  config.PHASE_BREAK,
        np.where(
            score > p_drop, config.PHASE_DROP,
            config.PHASE_BUILDUP
        )
    ).astype(np.int64)

    # ── Auf Frame-Ebene interpolieren ────────────────────────────────────────
    frame_times = np.arange(n_frames) * hop / sr
    phase_labels = np.zeros(n_frames, dtype=np.int64)

    for i, t in enumerate(frame_times):
        beat_idx = int(np.searchsorted(beat_times, t, side='right')) - 1
        beat_idx = max(0, min(beat_idx, n_beats - 1))
        phase_labels[i] = beat_phase_labels[beat_idx]

    return phase_labels


# ─── HILFSFUNKTIONEN ──────────────────────────────────────────────────────────

def decode_beat_phase(sin_val: float, cos_val: float) -> float:
    """Wandelt sin/cos Output zurück in Phase [0, 1]."""
    angle = np.arctan2(sin_val, cos_val)
    return float((angle / (2.0 * np.pi)) % 1.0)


def phase_idx_to_name(idx: int) -> str:
    """0→'BREAK', 1→'BUILDUP', 2→'DROP'"""
    return config.PHASE_NAMES[int(idx)] if 0 <= idx < len(config.PHASE_NAMES) else "BREAK"


def phase_name_to_idx(name: str) -> int:
    """'BREAK'→0, 'BUILDUP'→1, 'DROP'→2"""
    try:
        return config.PHASE_NAMES.index(name.upper())
    except ValueError:
        return config.PHASE_BREAK
