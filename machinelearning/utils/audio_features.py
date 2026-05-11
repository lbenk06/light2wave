"""
Audio-Feature Extraktion für die ML-Pipeline.

Kern: Mel-Spektrogramm Extraktion mit librosa.
Alles ist auf SAMPLE_RATE und HOP_LENGTH aus config.py normiert,
damit Train- und Live-Daten identisch sind.
"""
import numpy as np
import librosa

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def load_audio(audio_path: str) -> np.ndarray:
    """
    Lädt Audio-Datei und re-samplet auf config.SAMPLE_RATE (Mono).
    Gibt float32 Array zurück.
    """
    y, _ = librosa.load(audio_path, sr=config.SAMPLE_RATE, mono=True)
    return y.astype(np.float32)


def extract_mel(y: np.ndarray) -> np.ndarray:
    """
    Berechnet Mel-Spektrogramm (log-skaliert, normiert).

    Input:  y       → Audio-Signal, shape (n_samples,)
    Output: mel_db  → shape (n_frames, N_MELS), float32

    Jede Spalte = ein Frame (~23ms bei 22050Hz/512 hop)
    """
    mel = librosa.feature.melspectrogram(
        y=y,
        sr=config.SAMPLE_RATE,
        n_fft=config.N_FFT,
        hop_length=config.HOP_LENGTH,
        n_mels=config.N_MELS,
        fmin=config.F_MIN,
        fmax=config.F_MAX,
        power=2.0,
    )
    # Log-Kompression (dB) + Normierung auf [-1, 1]
    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_db = (mel_db / 80.0).clip(-1.0, 1.0)  # -80dB = -1, 0dB = 0
    return mel_db.T.astype(np.float32)  # (n_frames, n_mels)


def time_to_frame(time_sec: float) -> int:
    """Wandelt Zeit in Sekunden in Frame-Index um."""
    return int(time_sec * config.SAMPLE_RATE / config.HOP_LENGTH)


def frame_to_time(frame_idx: int) -> float:
    """Wandelt Frame-Index in Zeit in Sekunden um."""
    return frame_idx * config.HOP_LENGTH / config.SAMPLE_RATE


def n_frames_for_duration(duration_sec: float) -> int:
    """Wie viele Frames hat ein Audio von N Sekunden Länge?"""
    return int(duration_sec * config.SAMPLE_RATE / config.HOP_LENGTH)


class RollingMelBuffer:
    """
    Rolling Buffer für Live-Inferenz.
    Hält die letzten CONTEXT_FRAMES als Mel-Spektrogramm bereit.

    Nutzung:
        buf = RollingMelBuffer()
        buf.push_samples(new_audio_chunk)   # beim sounddevice callback
        window = buf.get_window()           # (CONTEXT_FRAMES, N_MELS)
    """

    def __init__(self):
        self._sample_buffer = np.zeros(
            config.N_FFT + config.HOP_LENGTH * config.CONTEXT_FRAMES,
            dtype=np.float32
        )
        self._mel_buffer = np.zeros(
            (config.CONTEXT_FRAMES, config.N_MELS),
            dtype=np.float32
        )
        self._frame_count = 0

    def push_samples(self, samples: np.ndarray):
        """
        Fügt neue Audio-Samples hinzu (ein HOP_LENGTH-Chunk).
        Berechnet den neuen Mel-Frame und schiebt ihn in den Buffer.
        """
        # Schiebe Sample-Buffer
        n = len(samples)
        self._sample_buffer = np.roll(self._sample_buffer, -n)
        self._sample_buffer[-n:] = samples

        # Berechne neuen Mel-Frame aus dem letzten N_FFT-Fenster
        window = self._sample_buffer[-(config.N_FFT):]
        spectrum = np.abs(librosa.stft(
            window,
            n_fft=config.N_FFT,
            hop_length=config.N_FFT,  # kein Hop, ein Frame
            center=False,
        )[:, 0]) ** 2

        mel_frame = librosa.feature.melspectrogram(
            S=spectrum[:, np.newaxis],  # (freq_bins, 1) — librosa erwartet (freq, frames)
            sr=config.SAMPLE_RATE,
            n_fft=config.N_FFT,        # explizit: verhindert n_fft=0 Inferenz-Bug
            n_mels=config.N_MELS,
            fmin=config.F_MIN,
            fmax=config.F_MAX,
        )[:, 0]
        mel_db = librosa.power_to_db(mel_frame[np.newaxis], ref=1.0)[0]
        mel_db = (mel_db / 80.0).clip(-1.0, 1.0)

        # Schiebe Mel-Buffer
        self._mel_buffer = np.roll(self._mel_buffer, -1, axis=0)
        self._mel_buffer[-1] = mel_db
        self._frame_count += 1

    def get_window(self) -> np.ndarray:
        """Gibt das aktuelle Kontext-Fenster zurück: (CONTEXT_FRAMES, N_MELS)"""
        return self._mel_buffer.copy()

    @property
    def is_ready(self) -> bool:
        """True wenn genug Frames für sinnvolle Inferenz vorhanden sind."""
        return self._frame_count >= config.CONTEXT_FRAMES
