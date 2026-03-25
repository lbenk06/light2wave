"""
Live Inferenz — verbindet das trainierte Modell mit light2wave.

Was passiert hier:
  1. sounddevice empfängt Audio vom Line-In / Mikrofon
  2. Jeder Block (512 Samples = ~23ms) → in den Rolling-Mel-Buffer
  3. Wenn Buffer voll (CONTEXT_FRAMES = ~3s): Modell-Inferenz
  4. Ergebnisse → BeatState Objekt → an light2wave übergeben

Latenz:
  Audio-Chunk:        ~23ms
  Feature-Extraktion: ~5ms
  Modell-Inferenz:    ~10ms
  ─────────────────────────
  Gesamt:             ~38ms  (unter 80ms Wahrnehmungsgrenze ✓)

Aufruf standalone:
  python live_inference.py

Integration in light2wave:
  from machinelearning.live_inference import BeatDetector, BeatState
  detector = BeatDetector(callback=my_callback)
  detector.start()
"""
import os
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(__file__))
import config
from model import load_model, BeatPhraseModel
from utils.audio_features import RollingMelBuffer
from utils.label_utils import decode_beat_phase, phrase_kind_to_name

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    print("[WARN] sounddevice nicht installiert. Live-Modus nicht verfügbar.")


@dataclass
class BeatState:
    """
    Aktueller Zustand des Beat/Phrase-Detektors.
    Wird bei jedem Inferenz-Schritt aktualisiert und an light2wave übergeben.
    """
    # Beat-Phase [0.0 – 1.0]: 0 = Beat, 0.5 = Zwischen-Beat
    beat_phase: float = 0.0

    # Beat-Position im 16er-Raster [0–15]: 0 = Downbeat
    beat_in_bar: int = 0

    # Phrasen-Typ (0–9)
    phrase_type: int = 0
    phrase_name: str = "unknown"

    # Konfidenz-Werte [0–1]
    beat_confidence: float = 0.0
    phrase_confidence: float = 0.0

    # Wurde gerade ein Beat erkannt? (True für einen Frame)
    is_beat: bool = False

    # Ist gerade der Downbeat? (Beat 0 im 16er-Raster)
    is_downbeat: bool = False

    # Latenz der letzten Inferenz in ms
    inference_ms: float = 0.0

    # Zeitstempel (Unix-Zeit)
    timestamp: float = field(default_factory=time.time)


class BeatDetector:
    """
    Haupt-Klasse für die Live Beat & Phrasen-Erkennung.

    Beispiel:
        def on_beat(state: BeatState):
            if state.is_beat:
                print(f"Beat! Phase: {state.beat_phase:.2f} | {state.phrase_name}")

        detector = BeatDetector(callback=on_beat)
        detector.start()
        # ... läuft im Hintergrund ...
        detector.stop()
    """

    def __init__(
        self,
        model_path: str = config.MODEL_SAVE_PATH,
        callback: Optional[Callable[[BeatState], None]] = None,
        device_name: Optional[str] = config.LIVE_DEVICE,
        beat_threshold: float = 0.15,  # Phasensprung-Schwelle für Beat-Detection
    ):
        self.callback = callback
        self.device_name = device_name
        self.beat_threshold = beat_threshold

        self._mel_buffer = RollingMelBuffer()
        self._state = BeatState()
        self._running = False
        self._stream = None
        self._last_beat_phase = 0.0
        self._inference_count = 0

        # Modell laden
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Kein trainiertes Modell gefunden: {model_path}\n"
                "Erst dataset_builder.py und dann trainer.py ausführen!"
            )

        self._device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self._model = load_model(model_path).to(self._device)
        self._model.eval()
        print(f"[Detector] Modell geladen ({self._device})")

    def _audio_callback(self, indata: np.ndarray, frames: int,
                        time_info, status):
        """sounddevice Callback — läuft in einem separaten Thread."""
        if status:
            pass  # Überläufe etc. ignorieren für Echtzeit

        # Mono sicherstellen
        samples = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        samples = samples.astype(np.float32)

        # Mel-Buffer befüllen
        self._mel_buffer.push_samples(samples)

        # Nur inferieren wenn Buffer voll
        if self._mel_buffer.is_ready:
            self._run_inference()

    def _run_inference(self):
        """Modell-Inferenz auf dem aktuellen Mel-Fenster."""
        t_start = time.perf_counter()

        window = self._mel_buffer.get_window()  # (CONTEXT_FRAMES, N_MELS)

        # (N_MELS, CONTEXT_FRAMES) → (1, N_MELS, CONTEXT_FRAMES)
        mel_tensor = torch.from_numpy(window.T).unsqueeze(0).to(self._device)

        with torch.no_grad():
            outputs = self._model(mel_tensor)

        # Beat-Phase dekodieren
        sin_val = outputs['beat_phase'][0, 0].item()
        cos_val = outputs['beat_phase'][0, 1].item()
        beat_phase = decode_beat_phase(sin_val, cos_val)

        # Beat-in-Bar: argmax
        bar_logits = outputs['beat_in_bar'][0]
        bar_probs = torch.softmax(bar_logits, dim=0)
        beat_in_bar = int(torch.argmax(bar_probs).item())
        beat_confidence = float(bar_probs.max().item())

        # Phrasen-Typ: argmax
        phrase_logits = outputs['phrase_type'][0]
        phrase_probs = torch.softmax(phrase_logits, dim=0)
        phrase_type = int(torch.argmax(phrase_probs).item())
        phrase_confidence = float(phrase_probs.max().item())

        # Beat-Detection: Phase springt von ~1.0 zurück auf ~0.0
        phase_delta = beat_phase - self._last_beat_phase
        is_beat = phase_delta < -self.beat_threshold  # Phasen-Reset
        self._last_beat_phase = beat_phase

        inference_ms = (time.perf_counter() - t_start) * 1000

        # State aktualisieren
        self._state = BeatState(
            beat_phase=beat_phase,
            beat_in_bar=beat_in_bar,
            phrase_type=phrase_type,
            phrase_name=phrase_kind_to_name(phrase_type),
            beat_confidence=beat_confidence,
            phrase_confidence=phrase_confidence,
            is_beat=is_beat,
            is_downbeat=(is_beat and beat_in_bar == 0),
            inference_ms=inference_ms,
            timestamp=time.time(),
        )

        self._inference_count += 1

        # Callback aufrufen
        if self.callback:
            self.callback(self._state)

    def start(self):
        """Startet die Live-Erkennung."""
        if not SOUNDDEVICE_AVAILABLE:
            raise RuntimeError("sounddevice nicht installiert: pip install sounddevice")

        self._running = True
        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            blocksize=config.LIVE_BLOCKSIZE,
            channels=config.LIVE_CHANNELS,
            dtype='float32',
            device=self.device_name,
            callback=self._audio_callback,
        )
        self._stream.start()
        print(f"[Detector] Live-Erkennung gestartet")
        print(f"[Detector] Audio-Gerät: {self._stream.device}")
        print(f"[Detector] Samplerate: {config.SAMPLE_RATE}Hz | "
              f"Block: {config.LIVE_BLOCKSIZE} samples (~{config.LIVE_BLOCKSIZE/config.SAMPLE_RATE*1000:.0f}ms)")

    def stop(self):
        """Stoppt die Live-Erkennung."""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        print(f"[Detector] Gestoppt nach {self._inference_count} Inferenzen")

    @property
    def state(self) -> BeatState:
        """Aktueller Zustand (thread-safe lesen)."""
        return self._state

    @staticmethod
    def list_devices():
        """Listet verfügbare Audio-Eingabegeräte auf."""
        if not SOUNDDEVICE_AVAILABLE:
            print("sounddevice nicht installiert")
            return
        print("\nVerfügbare Audio-Eingabegeräte:")
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                print(f"  [{i}] {d['name']}  (inputs: {d['max_input_channels']})")


# ─── STANDALONE DEMO ──────────────────────────────────────────────────────────

def _demo_callback(state: BeatState):
    """Einfacher Demo-Callback der den Zustand in der Konsole anzeigt."""
    bar_vis = "█" * (state.beat_in_bar + 1) + "░" * (16 - state.beat_in_bar - 1)
    beat_marker = "◉ BEAT" if state.is_beat else "     "
    down_marker = " ← DOWNBEAT" if state.is_downbeat else ""

    print(
        f"\r{bar_vis} | "
        f"Phase: {state.beat_phase:.2f} | "
        f"Beat {state.beat_in_bar+1:2d}/16 | "
        f"{state.phrase_name:8s} ({state.phrase_confidence:.0%}) | "
        f"{beat_marker}{down_marker} | "
        f"{state.inference_ms:.1f}ms",
        end="", flush=True
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Light2Wave Live Beat Detector")
    parser.add_argument("--list-devices", action="store_true", help="Audio-Geräte auflisten")
    parser.add_argument("--device", type=str, default=None,
                        help="Audio-Gerät Name oder Index")
    args = parser.parse_args()

    if args.list_devices:
        BeatDetector.list_devices()
        sys.exit(0)

    if not os.path.exists(config.MODEL_SAVE_PATH):
        print(f"[ERROR] Kein Modell gefunden: {config.MODEL_SAVE_PATH}")
        print("  1. python dataset_builder.py")
        print("  2. python trainer.py")
        sys.exit(1)

    print("Light2Wave — Live Beat & Phrase Detector")
    print("Drücke Ctrl+C zum Beenden\n")

    detector = BeatDetector(
        callback=_demo_callback,
        device_name=args.device,
    )
    detector.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n")
        detector.stop()
