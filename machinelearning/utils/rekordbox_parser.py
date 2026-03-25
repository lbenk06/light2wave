"""
Rekordbox-Daten-Parser für die ML-Pipeline.

Liest aus zwei Quellen:
  1. pyrekordbox DB  → alle 6500 Songs (Titel, BPM, Audio-Pfad, ANLZ-Pfad)
  2. .DAT / .EXT     → PQT2 Beat-Grid (exakte Beat-Positionen in Samples)

Phasen-Labels kommen NICHT von Pioneer (PVB2 verschlüsselt),
sondern werden in label_utils.py aus dem Audio berechnet.
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

try:
    from pyrekordbox.db6 import Rekordbox6Database
    from pyrekordbox.anlz import AnlzFile
    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    print("[WARN] pyrekordbox nicht installiert: pip install pyrekordbox")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

# Pfad zur lokalen Rekordbox PC-Datenbank
RB_DB_PATH = "C:/Users/legol/AppData/Roaming/Pioneer/rekordbox/master.db"
# Lokale ANLZ-Dateien (Beat-Grid etc.)
RB_ANLZ_ROOT = "C:/Users/legol/AppData/Roaming/Pioneer/rekordbox/share/PIONEER/USBANLZ"
# Audio-Dateien auf dem CDJ USB Stick
STICK_CONTENTS = "D:/Contents"
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.aif', '.aiff', '.m4a'}


@dataclass
class TrackData:
    track_id: str
    name: str
    artist: str
    audio_path: str
    bpm: float
    duration: float        # Sekunden
    beat_times: np.ndarray  # Beat-Zeiten in Sekunden aus PQT2, shape (n_beats,)
    sample_rate: int = 44100

    @property
    def audio_exists(self) -> bool:
        return os.path.isfile(self.audio_path)


def _load_beat_times_from_pqt2(anlz_dat_path: str, sample_rate: int = 44100) -> Optional[np.ndarray]:
    """
    Liest Beat-Zeiten aus dem PQT2 Tag einer .DAT Datei.
    PQT2 enthält für jeden Beat: Sample-Position + BPM.
    Gibt Beat-Zeiten in Sekunden zurück.
    """
    if not PYREKORDBOX_AVAILABLE or not os.path.isfile(anlz_dat_path):
        return None
    try:
        anlz = AnlzFile.parse_file(anlz_dat_path)
        pqt2 = next((t for t in anlz.tags if type(t).__name__ == 'PQT2AnlzTag'), None)
        if pqt2 is None or not hasattr(pqt2, 'beats') or len(pqt2.beats) == 0:
            return None
        # beats ist eine Liste von Einträgen mit .sample_time (Sample-Position)
        beat_samples = np.array([b.sample_time for b in pqt2.beats], dtype=np.float64)
        beat_times = beat_samples / sample_rate
        return beat_times.astype(np.float32)
    except Exception:
        return None


def _bpm_to_beat_times(bpm: float, duration: float) -> np.ndarray:
    """Fallback: Berechnet Beat-Zeiten aus konstantem BPM."""
    if bpm <= 0:
        return np.array([])
    interval = 60.0 / bpm
    return np.arange(0.0, duration, interval, dtype=np.float32)


def build_stick_index(contents_root: str = STICK_CONTENTS, verbose: bool = True) -> dict:
    """
    Scannt D:/Contents/ und baut einen Dateiname→Pfad Index.
    Key: Dateiname lowercase (ohne Pfad), Value: voller Pfad auf dem Stick.
    Dauert ~5 Sekunden für 2861 Dateien.
    """
    if not os.path.exists(contents_root):
        if verbose:
            print(f"[Parser] Stick nicht gefunden: {contents_root}")
        return {}

    index = {}
    for root, dirs, files in os.walk(contents_root):
        for f in files:
            if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS and not f.startswith('._'):
                index[f.lower()] = os.path.join(root, f)

    if verbose:
        print(f"[Parser] Stick-Index: {len(index)} Audio-Dateien auf D:/Contents/")
    return index


def _resolve_anlz_path(analysis_data_path: str) -> Optional[str]:
    """
    Wandelt den relativen ANLZ-Pfad aus der DB in einen absoluten Windows-Pfad um.
    DB speichert z.B.: /PIONEER/USBANLZ/dc1/fa3c4-..../ANLZ0000.DAT
    Lokal liegt es unter: C:/Users/.../share/PIONEER/USBANLZ/...
    """
    if not analysis_data_path:
        return None
    # Entferne führenden /
    rel = analysis_data_path.lstrip('/')
    full = os.path.join(RB_ANLZ_ROOT, rel.split('USBANLZ/', 1)[-1])
    return full if os.path.isfile(full) else None


# ─── HAUPT-FUNKTION ───────────────────────────────────────────────────────────

def parse_library(
    min_bpm: float = 60.0,
    max_bpm: float = 220.0,
    min_duration: float = 60.0,
    max_tracks: Optional[int] = None,
    verbose: bool = True,
) -> List[TrackData]:
    """
    Liest alle Tracks aus der Rekordbox PC-Datenbank.
    Für jeden Track wird das PQT2 Beat-Grid aus der lokalen ANLZ-Datei geladen.

    Returns:
        Liste von TrackData Objekten mit audio_path + beat_times
    """
    if not PYREKORDBOX_AVAILABLE:
        print("[ERROR] pyrekordbox fehlt. pip install pyrekordbox")
        return []

    if not os.path.exists(RB_DB_PATH):
        print(f"[ERROR] Rekordbox DB nicht gefunden: {RB_DB_PATH}")
        return []

    if verbose:
        print(f"[Parser] Öffne Rekordbox DB...")

    db = Rekordbox6Database(RB_DB_PATH)
    all_songs = list(db.get_content())

    if verbose:
        print(f"[Parser] {len(all_songs)} Songs in Datenbank")

    # Stick-Index aufbauen (Dateiname → Pfad)
    stick_index = build_stick_index(verbose=verbose)

    tracks = []
    skipped_bpm = skipped_audio = skipped_short = 0

    for song in all_songs:
        if max_tracks and len(tracks) >= max_tracks:
            break

        bpm      = float(song.BPM or 0) / 100.0  # DB speichert BPM × 100
        duration = float(song.Length or 0)
        sr       = int(song.SampleRate or 44100)

        # Filter
        if bpm < min_bpm or bpm > max_bpm:
            skipped_bpm += 1
            continue
        if duration < min_duration:
            skipped_short += 1
            continue

        # Audio-Pfad: erst lokalen Pfad, dann Stick-Matching
        audio_path = song.FolderPath or ""
        if not os.path.isfile(audio_path):
            # Dateiname aus DB-Pfad extrahieren und auf Stick suchen
            fname = os.path.basename(audio_path).lower()
            audio_path = stick_index.get(fname, "")

        if not audio_path or not os.path.isfile(audio_path):
            skipped_audio += 1
            continue

        # Beat-Grid aus PQT2
        anlz_path = _resolve_anlz_path(song.AnalysisDataPath)
        beat_times = _load_beat_times_from_pqt2(anlz_path, sr) if anlz_path else None

        if beat_times is None or len(beat_times) < 4:
            # Fallback: aus BPM berechnen
            beat_times = _bpm_to_beat_times(bpm, duration)

        if len(beat_times) < 4:
            skipped_bpm += 1
            continue

        tracks.append(TrackData(
            track_id=str(song.ID),
            name=str(song.Title or ""),
            artist=str(song.ArtistName or ""),
            audio_path=audio_path,
            bpm=bpm,
            duration=duration,
            beat_times=beat_times,
            sample_rate=sr,
        ))

        if verbose and len(tracks) % 500 == 0:
            print(f"[Parser] {len(tracks)} Tracks geladen...")

    if verbose:
        pqt2_count = sum(1 for t in tracks if len(t.beat_times) > 10)
        print(f"\n[Parser] Ergebnis:")
        print(f"  Verwendbare Tracks:      {len(tracks)}")
        print(f"  Davon mit PQT2 Grid:     {pqt2_count}")
        print(f"  Übersprungen (BPM/Beat): {skipped_bpm}")
        print(f"  Übersprungen (zu kurz):  {skipped_short}")
        print(f"  Übersprungen (kein Audio): {skipped_audio}")

    return tracks
