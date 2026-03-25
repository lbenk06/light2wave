"""
Rekordbox-Daten-Parser für die ML-Pipeline.

Liest aus zwei Quellen:
  1. XML Export  → Beat-Grid (BPM + Beat-Zeiten) + Audio-Pfade
  2. .EXT Dateien → Phrasen-Typen (PPHR Tag) vom CDJ USB Stick

Gibt eine Liste von TrackData-Objekten zurück, jede mit:
  - audio_path:  Absoluter Pfad zur Audio-Datei
  - beat_times:  Beat-Zeiten in Sekunden (numpy array)
  - phrases:     Liste von (time_sec, phrase_kind) Tupeln
"""
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import unquote

import numpy as np

try:
    from pyrekordbox.anlz import AnlzFile
    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    print("[WARN] pyrekordbox nicht installiert. Nur XML-Daten verfügbar (keine Phrasen).")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


@dataclass
class PhraseInfo:
    beat_number: int       # Beat-Nummer im Track (ab 1)
    kind: int              # Pioneer Phrasen-Typ (1-9)
    time_sec: float = 0.0  # Berechnete Zeit in Sekunden


@dataclass
class TrackData:
    track_id: str
    name: str
    artist: str
    audio_path: str
    bpm: float
    duration: float        # Sekunden
    beat_times: np.ndarray  # Beat-Zeiten in Sekunden, shape (n_beats,)
    phrases: List[PhraseInfo] = field(default_factory=list)
    sample_rate: int = 44100

    @property
    def has_phrases(self) -> bool:
        return len(self.phrases) > 0

    @property
    def audio_exists(self) -> bool:
        return os.path.isfile(self.audio_path)


def _translate_path(xml_location: str) -> str:
    """
    Übersetzt den Mac-Pfad aus der XML in einen Windows-Pfad.

    XML enthält: file://localhost/Users/leobenk/Music/DJ/track.mp3
    Wir wollen: D:/Music/DJ/track.mp3 (oder wo auch immer die Files sind)
    """
    # URL-decode (Leerzeichen etc.)
    path = unquote(xml_location)

    # Entferne "file://localhost" Präfix
    if path.startswith("file://localhost"):
        path = path[len("file://localhost"):]
    elif path.startswith("file://"):
        path = path[len("file://"):]

    # Custom Map zuerst prüfen (spezifischere Regeln haben Vorrang)
    for mac_prefix, win_prefix in config.CUSTOM_PATH_MAP.items():
        if path.startswith(mac_prefix):
            return win_prefix + path[len(mac_prefix):]

    # Standard-Übersetzung: Mac /Users/leobenk/ → USB-Stick Laufwerk
    if path.startswith(config.MAC_PATH_PREFIX):
        remainder = path[len(config.MAC_PATH_PREFIX):]
        # Auf dem Stick liegt alles unter D:/ direkt, also:
        # /Users/leobenk/Music/... → D:/Music/...
        return os.path.join(config.WINDOWS_PATH_PREFIX, remainder).replace("\\", "/")

    # Falls der Pfad schon Windows-ähnlich ist (z.B. /C:/...)
    if len(path) > 2 and path[0] == '/' and path[2] == ':':
        return path[1:]  # Entferne führenden /

    return path


def _compute_beat_times(tempo_elements: List) -> np.ndarray:
    """
    Berechnet alle Beat-Zeiten aus den TEMPO-Elementen der XML.

    Rekordbox XML hat pro BPM-Sektion ein TEMPO-Element:
      <TEMPO Inizio="0.025" Bpm="128.00" Metro="4/4" Battito="1"/>

    Inizio   = Zeit des Beats bei Battito in Sekunden
    Bpm      = BPM ab diesem Punkt
    Battito  = Beat-Nummer innerhalb des Takts (1-4)
    """
    if not tempo_elements:
        return np.array([])

    beat_times = []
    sections = []

    for el in tempo_elements:
        sections.append({
            'start_time': float(el.get('Inizio', 0)),
            'bpm': float(el.get('Bpm', 120)),
            'battito': int(el.get('Battito', 1)),
        })

    # Sortiere nach Zeit
    sections.sort(key=lambda x: x['start_time'])

    for i, sec in enumerate(sections):
        beat_interval = 60.0 / sec['bpm']

        # Ende dieser Sektion = Beginn der nächsten (oder 2 Stunden als Max)
        end_time = sections[i + 1]['start_time'] if i + 1 < len(sections) else sec['start_time'] + 7200

        t = sec['start_time']
        while t < end_time - beat_interval * 0.5:
            beat_times.append(t)
            t += beat_interval

    return np.array(sorted(beat_times))


def _load_phrases_from_ext(ext_path: str, beat_times: np.ndarray) -> List[PhraseInfo]:
    """
    Liest Phrasen-Daten aus einer .EXT Datei (PPHR Tag).
    Berechnet die Zeit in Sekunden aus der Beat-Nummer und dem Beat-Grid.
    """
    if not PYREKORDBOX_AVAILABLE:
        return []

    phrases = []
    try:
        anlz = AnlzFile.parse_file(ext_path)
        phrases_tag = next(
            (tag for tag in anlz.tags if tag.fourcc == b'PPHR'),
            None
        )

        if phrases_tag is None or not hasattr(phrases_tag, 'phrases'):
            return []

        for p in phrases_tag.phrases:
            beat_num = p.beat_number
            kind = int(p.kind)

            # Beat-Nummer → Zeit in Sekunden (Beat-Grid ist 1-indexed)
            idx = beat_num - 1
            if 0 <= idx < len(beat_times):
                time_sec = float(beat_times[idx])
            elif len(beat_times) > 0:
                # Extrapoliere wenn nötig
                bpm_est = 60.0 / np.mean(np.diff(beat_times[-10:])) if len(beat_times) > 1 else 120
                time_sec = float(beat_times[-1]) + (idx - len(beat_times) + 1) * (60.0 / bpm_est)
            else:
                time_sec = 0.0

            phrases.append(PhraseInfo(
                beat_number=beat_num,
                kind=kind,
                time_sec=time_sec
            ))
    except Exception as e:
        pass  # Kaputte Datei → ignorieren

    return phrases


def _find_ext_file_for_track(audio_path: str) -> Optional[str]:
    """
    Versucht die .EXT Analyse-Datei für eine Audio-Datei zu finden.

    Strategie 1: pyrekordbox's eingebaute Pfadberechnung
    Strategie 2: Brute-Force Scan (langsam, nur als Fallback)
    """
    if not os.path.exists(config.ANLZ_ROOT):
        return None

    # Strategie 1: pyrekordbox Pfadberechnung (MD5-Hash des Pfads)
    try:
        from pyrekordbox.anlz import get_anlz_paths
        paths = get_anlz_paths(audio_path, config.ANLZ_ROOT)
        ext_path = paths.get('EXT') or paths.get('.EXT')
        if ext_path and os.path.exists(ext_path):
            return ext_path
    except Exception:
        pass

    # Strategie 2: Falls pyrekordbox's Funktion nicht funktioniert
    # (für zukünftige manuelle Hash-Berechnung)
    return None


# ─── HAUPT-FUNKTION ───────────────────────────────────────────────────────────

def parse_library(
    xml_path: str = config.XML_PATH,
    min_bpm: float = 60.0,
    max_bpm: float = 220.0,
    min_duration: float = 30.0,
    require_audio: bool = True,
    max_tracks: Optional[int] = None,
    verbose: bool = True,
) -> List[TrackData]:
    """
    Parst die Rekordbox XML und gibt alle verwendbaren Tracks zurück.

    Args:
        xml_path:       Pfad zum Rekordbox XML Export
        min_bpm:        Minimales BPM (filtert Samples/Acapellas heraus)
        max_bpm:        Maximales BPM
        min_duration:   Minimale Track-Dauer in Sekunden
        require_audio:  Nur Tracks zurückgeben deren Audio-Datei existiert
        max_tracks:     Limit für schnelle Tests (None = alle)
        verbose:        Fortschritt ausgeben

    Returns:
        Liste von TrackData Objekten
    """
    if verbose:
        print(f"[Parser] Lese XML: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    tracks = []
    skipped_no_bpm = 0
    skipped_no_audio = 0
    skipped_short = 0

    all_track_elements = root.findall('.//TRACK')
    if verbose:
        print(f"[Parser] {len(all_track_elements)} Tracks in XML gefunden")

    for i, track_el in enumerate(all_track_elements):
        if max_tracks and len(tracks) >= max_tracks:
            break

        # ── Basis-Metadaten ──
        track_id = track_el.get('TrackID', str(i))
        name = track_el.get('Name', 'Unknown')
        artist = track_el.get('Artist', '')
        location = track_el.get('Location', '')
        avg_bpm = float(track_el.get('AverageBpm', 0))
        duration = float(track_el.get('TotalTime', 0))
        sample_rate = int(track_el.get('SampleRate', 44100))

        # ── Filter ──
        if avg_bpm < min_bpm or avg_bpm > max_bpm:
            skipped_no_bpm += 1
            continue

        if duration < min_duration:
            skipped_short += 1
            continue

        # ── Pfad übersetzen ──
        audio_path = _translate_path(location)

        if require_audio and not os.path.isfile(audio_path):
            skipped_no_audio += 1
            continue

        # ── Beat-Grid aus TEMPO Tags ──
        tempo_elements = track_el.findall('TEMPO')
        beat_times = _compute_beat_times(tempo_elements)

        if len(beat_times) == 0:
            # Kein Beat-Grid → aus BPM und Dauer schätzen
            if avg_bpm > 0:
                beat_interval = 60.0 / avg_bpm
                beat_times = np.arange(0, duration, beat_interval)
            else:
                skipped_no_bpm += 1
                continue

        # ── Phrasen aus .EXT Datei ──
        phrases = []
        ext_path = _find_ext_file_for_track(audio_path)
        if ext_path:
            phrases = _load_phrases_from_ext(ext_path, beat_times)

        track = TrackData(
            track_id=track_id,
            name=name,
            artist=artist,
            audio_path=audio_path,
            bpm=avg_bpm,
            duration=duration,
            beat_times=beat_times,
            phrases=phrases,
            sample_rate=sample_rate,
        )
        tracks.append(track)

        if verbose and len(tracks) % 500 == 0:
            print(f"[Parser] {len(tracks)} Tracks geladen...")

    if verbose:
        with_phrases = sum(1 for t in tracks if t.has_phrases)
        print(f"\n[Parser] ✓ Ergebnis:")
        print(f"  Verwendbare Tracks:    {len(tracks)}")
        print(f"  Davon mit Phrasen:     {with_phrases}")
        print(f"  Übersprungen (kein BPM): {skipped_no_bpm}")
        print(f"  Übersprungen (zu kurz):  {skipped_short}")
        print(f"  Übersprungen (kein Audio): {skipped_no_audio}")

    return tracks


def scan_phrases_from_stick(usb_drive: str = config.USB_DRIVE, verbose: bool = True) -> int:
    """
    Scannt den USB Stick nach Phrase-Daten und gibt die Anzahl zurück.
    Nützlich um zu prüfen ob der Stick korrekt erkannt wird.
    """
    anlz_root = os.path.join(usb_drive, "PIONEER", "USBANLZ")
    if not os.path.exists(anlz_root):
        print(f"[Scan] PIONEER/USBANLZ nicht gefunden auf {usb_drive}")
        return 0

    count = 0
    phrases_count = 0

    for root_dir, dirs, files in os.walk(anlz_root):
        for f in files:
            if f.upper().endswith('.EXT'):
                count += 1
                if PYREKORDBOX_AVAILABLE:
                    try:
                        anlz = AnlzFile.parse_file(os.path.join(root_dir, f))
                        has_pphr = any(tag.fourcc == b'PPHR' for tag in anlz.tags)
                        if has_pphr:
                            phrases_count += 1
                    except Exception:
                        pass

    if verbose:
        print(f"[Scan] .EXT Dateien gefunden: {count}")
        print(f"[Scan] Davon mit Phrasen:     {phrases_count}")

    return phrases_count
