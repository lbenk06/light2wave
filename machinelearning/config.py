"""
Zentrale Konfiguration für die ML-Pipeline.
Hier alle Pfade und Hyperparameter anpassen.
"""
import os

# ─── PFADE ────────────────────────────────────────────────────────────────────

# Pfad zum Rekordbox XML Export
XML_PATH = os.path.join(os.path.dirname(__file__), "rekordboxlib.xml")

# Laufwerksbuchstabe des CDJ USB Sticks
USB_DRIVE = "D:/"

# Ordner für den analysierten Phasen-Daten auf dem Stick
ANLZ_ROOT = os.path.join(USB_DRIVE, "PIONEER", "USBANLZ")

# Ordner für die Audio-Dateien auf dem Stick
CONTENTS_ROOT = os.path.join(USB_DRIVE, "Contents")

# Pfad-Übersetzung: Mac-Pfad-Präfix → Windows-Pfad auf dem Stick
# Die XML hat Pfade wie /Users/leobenk/Music/... (Mac)
# Auf dem Stick liegen die Files unter D:/Contents/...
MAC_PATH_PREFIX = "/Users/leobenk/"          # Präfix in der XML
WINDOWS_PATH_PREFIX = USB_DRIVE              # Ersatz auf dem Stick
# Beispiel: /Users/leobenk/Music/DJ/track.mp3
#        →  D:/Music/DJ/track.mp3
# Falls das nicht stimmt, kannst du hier genauer anpassen:
CUSTOM_PATH_MAP = {
    # "/Users/leobenk/Music/": "D:/Contents/",  # Beispiel
}

# Wo der fertige Dataset-Cache gespeichert wird
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", "cache")

# Wo das trainierte Modell gespeichert wird
MODEL_SAVE_PATH = os.path.join(os.path.dirname(__file__), "data", "beat_phrase_model.pt")

# ─── AUDIO FEATURE PARAMETER ──────────────────────────────────────────────────

SAMPLE_RATE = 22050          # Hz (Standard für Musikanalyse)
HOP_LENGTH = 512             # Samples pro Frame (~23ms bei 22050Hz)
N_FFT = 2048                 # FFT Fenstergröße
N_MELS = 128                 # Mel-Bänder
F_MIN = 20.0                 # Untere Frequenzgrenze (Hz)
F_MAX = 8000.0               # Obere Frequenzgrenze (Hz)

# Kontext-Fenster für das Modell (wie viele Frames es "sieht")
CONTEXT_FRAMES = 128         # ~3 Sekunden Kontext

# ─── MODELL PARAMETER ─────────────────────────────────────────────────────────

# Phrasen-Typen aus Pioneer PPHR Tag (kind → Name)
PHRASE_KINDS = {
    0:  "unknown",
    1:  "intro",
    2:  "up",        # aufbauend / Verse
    3:  "down",      # abbauend
    4:  "chorus",    # Höhepunkt
    5:  "outro",
    6:  "break",     # Fill-in / Break
    7:  "verse",     # Variante Verse
    8:  "bridge",
    9:  "peak",      # alternative Chorus-Variante
}
NUM_PHRASE_TYPES = len(PHRASE_KINDS)  # 10 Klassen
NUM_BEATS_IN_BAR = 16                 # 16-Beat Phrasen (typisch Electronic/House)

# ─── TRAINING PARAMETER ───────────────────────────────────────────────────────

BATCH_SIZE = 64
LEARNING_RATE = 3e-4
NUM_EPOCHS = 50
SONGS_PER_MINI_EPOCH = 200      # Wie viele Songs pro Mini-Epoch geladen werden
VALIDATION_SPLIT = 0.1          # 10% der Songs als Validierung
NUM_WORKERS = 4                 # DataLoader Worker (0 auf Windows falls Probleme)

# ─── LIVE INFERENZ PARAMETER ──────────────────────────────────────────────────

LIVE_DEVICE = None              # None = Standard-Eingabegerät, oder z.B. "Focusrite"
LIVE_CHANNELS = 1               # Mono
LIVE_BLOCKSIZE = HOP_LENGTH     # Ein Frame pro Callback (~23ms)
