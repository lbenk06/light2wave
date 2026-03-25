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
from utils.rekordbox_parser import parse_library
from utils.audio_features import load_audio, extract_mel
from utils.label_utils import compute_beat_labels, compute_phase_labels, phase_idx_to_name


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

    # ── Tracks laden ─────────────────────────────────────────────────────────
    print("\n[Parsing] Lese Rekordbox Datenbank...")
    print("[Info] Phasen-Labels werden aus Audio via Librosa berechnet (BREAK/BUILDUP/DROP)")
    max_tracks = 20 if test_mode else None
    tracks = parse_library(
        max_tracks=max_tracks,
        verbose=True,
    )

    if not tracks:
        print("\n[ERROR] Keine Tracks gefunden!")
        print("  → Prüfe ob Rekordbox auf diesem PC installiert ist")
        print("  → DB-Pfad: C:/Users/legol/AppData/Roaming/Pioneer/rekordbox/master.db")
        return

    # ── Verarbeitung ─────────────────────────────────────────────────────────
    print(f"\n[Build] Verarbeite {len(tracks)} Tracks...")
    print(f"[Build] Cache-Ordner: {config.CACHE_DIR}")

    stats = {
        'processed': 0,
        'skipped_cache': 0,
        'skipped_error': 0,
        'total_frames': 0,
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

            # Beat-Labels aus PQT2 Beat-Grid
            sin_phase, cos_phase, beat_in_bar = compute_beat_labels(track.beat_times, n_frames)

            # Phasen-Labels aus Librosa Audio-Analyse
            phase_labels = compute_phase_labels(y, track.beat_times, n_frames)

            # Speichere als komprimiertes numpy
            np.savez_compressed(
                cache_path,
                mel=mel.astype(np.float16),
                beat_phase_sin=sin_phase,
                beat_phase_cos=cos_phase,
                beat_in_bar=beat_in_bar.astype(np.uint8),
                phase_type=phase_labels.astype(np.uint8),  # 0=BREAK, 1=BUILDUP, 2=DROP
                bpm=np.float32(track.bpm),
            )

            stats['processed'] += 1
            stats['total_frames'] += n_frames

        except Exception as e:
            tqdm.write(f"[WARN] {track.name[:40]}: {e}")
            stats['skipped_error'] += 1

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  BUILD ABGESCHLOSSEN")
    print("=" * 60)
    print(f"  Verarbeitet:          {stats['processed']}")
    print(f"  Bereits gecacht:      {stats['skipped_cache']}")
    print(f"  Fehler:               {stats['skipped_error']}")
    print(f"  Gesamt Frames:        {stats['total_frames']:,}")
    print(f"  Ungefähre Datenmenge: {stats['processed'] * 2:.0f} MB")
    print(f"\n  Cache unter: {config.CACHE_DIR}")
    print("  -> Jetzt trainer.py starten!")


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
        phrase_type = data['phase_type']
        print(f"\n  {fname}:")
        print(f"    Mel-Shape:     {mel.shape}")
        print(f"    BPM:           {float(data['bpm']):.1f}")
        from collections import Counter
        c = Counter(int(x) for x in phrase_type)
        total = len(phrase_type)
        dist = {['BREAK','BUILDUP','DROP'][k]: f"{v/total*100:.0f}%" for k,v in sorted(c.items())}
        print(f"    Phasen-Verteilung: {dist}")


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
