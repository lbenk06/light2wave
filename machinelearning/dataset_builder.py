"""
Dataset Builder — einmalig ausführen bevor das Training startet.

Was dieser Script macht:
  1. Liest alle Tracks aus der Rekordbox XML
  2. Extrahiert Mel-Spektrogramme + Labels (Beat-Phase, Beat-in-Bar, Phrasentyp)
  3. Speichert alles als komprimierte .npz Dateien im Cache-Ordner

Danach lädt trainer.py die gecachten Features → viel schneller als on-the-fly.

Aufruf:
  python dataset_builder.py

Optionale Argumente:
  --test         Nur 20 Tracks verarbeiten (zum Testen)
  --resume       Überspringt bereits gecachte Tracks
  --usb D:/      USB-Stick Laufwerksbuchstabe (Standard aus config.py)
"""
import os
import sys
import argparse
import numpy as np
from tqdm import tqdm

import config
from utils.rekordbox_parser import parse_library, scan_phrases_from_stick
from utils.audio_features import load_audio, extract_mel
from utils.label_utils import compute_labels, label_summary


def build_cache(
    test_mode: bool = False,
    resume: bool = True,
    usb_drive: str = None,
):
    os.makedirs(config.CACHE_DIR, exist_ok=True)

    # ── Stick-Check ──────────────────────────────────────────────────────────
    if usb_drive:
        config.USB_DRIVE = usb_drive

    print("=" * 60)
    print("  LIGHT2WAVE — Dataset Builder")
    print("=" * 60)

    pioneer_folder = os.path.join(config.USB_DRIVE, "PIONEER")
    if os.path.exists(pioneer_folder):
        print(f"\n[Stick] {config.USB_DRIVE} erkannt — scanne Phrasen...")
        scan_phrases_from_stick(config.USB_DRIVE)
    else:
        print(f"\n[Stick] WARN: Kein PIONEER-Ordner auf {config.USB_DRIVE} gefunden.")
        print("         Phrasen-Daten werden nicht geladen.")

    # ── Tracks laden ─────────────────────────────────────────────────────────
    print("\n[Parsing] Lese Rekordbox XML...")
    max_tracks = 20 if test_mode else None
    tracks = parse_library(
        xml_path=config.XML_PATH,
        require_audio=True,
        max_tracks=max_tracks,
        verbose=True,
    )

    if not tracks:
        print("\n[ERROR] Keine Tracks gefunden!")
        print("  → Prüfe config.py: MAC_PATH_PREFIX und WINDOWS_PATH_PREFIX")
        print("  → Stelle sicher dass die Audio-Dateien erreichbar sind")
        return

    # ── Verarbeitung ─────────────────────────────────────────────────────────
    print(f"\n[Build] Verarbeite {len(tracks)} Tracks...")
    print(f"[Build] Cache-Ordner: {config.CACHE_DIR}")

    stats = {
        'processed': 0,
        'skipped_cache': 0,
        'skipped_error': 0,
        'total_frames': 0,
        'with_phrases': 0,
    }

    for track in tqdm(tracks, desc="Feature-Extraktion"):
        cache_path = os.path.join(config.CACHE_DIR, f"track_{track.track_id}.npz")

        # Resume: bereits gecachte Tracks überspringen
        if resume and os.path.exists(cache_path):
            stats['skipped_cache'] += 1
            continue

        try:
            # Lade Audio
            y = load_audio(track.audio_path)

            # Mel-Spektrogramm
            mel = extract_mel(y)  # (n_frames, N_MELS)
            n_frames = len(mel)

            # Labels
            sin_phase, cos_phase, beat_in_bar, phrase_type = compute_labels(track, n_frames)

            # Speichere als komprimiertes numpy
            np.savez_compressed(
                cache_path,
                mel=mel.astype(np.float16),          # Halbiert Speicher
                beat_phase_sin=sin_phase,
                beat_phase_cos=cos_phase,
                beat_in_bar=beat_in_bar.astype(np.uint8),
                phrase_type=phrase_type.astype(np.uint8),
                bpm=np.float32(track.bpm),
                has_phrases=np.bool_(track.has_phrases),
            )

            stats['processed'] += 1
            stats['total_frames'] += n_frames
            if track.has_phrases:
                stats['with_phrases'] += 1

        except Exception as e:
            tqdm.write(f"[WARN] {track.name[:40]}: {e}")
            stats['skipped_error'] += 1

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  BUILD ABGESCHLOSSEN")
    print("=" * 60)
    print(f"  Verarbeitet:          {stats['processed']}")
    print(f"  Davon mit Phrasen:    {stats['with_phrases']}")
    print(f"  Bereits gecacht:      {stats['skipped_cache']}")
    print(f"  Fehler:               {stats['skipped_error']}")
    print(f"  Gesamt Frames:        {stats['total_frames']:,}")
    print(f"  Ungefähre Datenmenge: {stats['processed'] * 2:.0f} MB")
    print(f"\n  Cache unter: {config.CACHE_DIR}")
    print("  → Jetzt trainer.py starten!")


def verify_cache(n_samples: int = 5):
    """Schneller Sanity-Check: Lädt ein paar gecachte Files und gibt Infos aus."""
    cache_files = [f for f in os.listdir(config.CACHE_DIR) if f.endswith('.npz')]
    if not cache_files:
        print("[Verify] Kein Cache gefunden. Erst dataset_builder.py ausführen.")
        return

    print(f"[Verify] {len(cache_files)} gecachte Tracks gefunden")

    for fname in cache_files[:n_samples]:
        data = np.load(os.path.join(config.CACHE_DIR, fname))
        mel = data['mel']
        phrase_type = data['phrase_type']
        print(f"\n  {fname}:")
        print(f"    Mel-Shape:     {mel.shape}")
        print(f"    BPM:           {float(data['bpm']):.1f}")
        print(f"    Hat Phrasen:   {bool(data['has_phrases'])}")
        print(f"    Label-Verteilung: {label_summary(phrase_type)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Light2Wave Dataset Builder")
    parser.add_argument("--test", action="store_true", help="Nur 20 Tracks (Test-Modus)")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Gecachte Tracks überspringen (Standard: an)")
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--verify", action="store_true", help="Cache prüfen und exit")
    parser.add_argument("--usb", type=str, default=None,
                        help="USB Laufwerksbuchstabe, z.B. E:/")
    args = parser.parse_args()

    if args.verify:
        verify_cache()
    else:
        build_cache(
            test_mode=args.test,
            resume=args.resume,
            usb_drive=args.usb,
        )
