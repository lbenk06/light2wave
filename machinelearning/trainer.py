"""
Training-Loop für das Beat & Phrase Erkennungs-Modell.

Aufruf:
  python trainer.py

Strategie (Mini-Epoch):
  Statt alle 6000 Songs auf einmal zu laden, werden pro Iteration
  SONGS_PER_MINI_EPOCH zufällig ausgewählt und in RAM geladen.
  → Kein Out-of-Memory bei großen Libraries.

Checkpoints werden regelmäßig gespeichert.
TensorBoard-Logging wenn tensorboard installiert ist.
"""
import os
import sys
import random
import glob
import time
import argparse

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from torch.optim.lr_scheduler import OneCycleLR
from tqdm import tqdm

import config
from model import BeatPhraseModel, BeatPhraseLoss, create_model, load_model

# Optional TensorBoard
try:
    from torch.utils.tensorboard import SummaryWriter
    TENSORBOARD = True
except ImportError:
    TENSORBOARD = False


class CachedTrackDataset(Dataset):
    """
    PyTorch Dataset für gecachte .npz Track-Features.

    Jedes Sample ist ein zufälliges CONTEXT_FRAMES-Fenster
    aus einem der geladenen Tracks.
    """

    def __init__(self, npz_paths: list, samples_per_track: int = 200):
        """
        Args:
            npz_paths:         Liste von .npz Dateipfaden
            samples_per_track: Wie viele Fenster pro Track gesampelt werden
        """
        self.samples = []  # (mel_slice, labels)
        self._load_tracks(npz_paths, samples_per_track)

    def _load_tracks(self, paths: list, samples_per_track: int):
        ctx = config.CONTEXT_FRAMES

        for path in paths:
            try:
                data = np.load(path)
                mel = data['mel'].astype(np.float32)    # (n_frames, N_MELS)
                sin = data['beat_phase_sin']
                cos = data['beat_phase_cos']
                bar = data['beat_in_bar'].astype(np.int64)
                phrase = data['phase_type'].astype(np.int64)

                n_frames = len(mel)
                if n_frames < ctx + 1:
                    continue

                # Zufällige Fenster sampeln
                max_start = n_frames - ctx
                starts = np.random.randint(0, max_start, size=samples_per_track)

                for s in starts:
                    mel_window = mel[s:s + ctx].T  # (N_MELS, CONTEXT_FRAMES)
                    target_idx = s + ctx - 1       # Label für den letzten Frame (kausal)

                    self.samples.append((
                        mel_window,
                        sin[target_idx],
                        cos[target_idx],
                        bar[target_idx],
                        phrase[target_idx],
                    ))

            except Exception as e:
                pass

        # Mischen
        random.shuffle(self.samples)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        mel, sin, cos, bar, phrase = self.samples[idx]
        return (
            torch.from_numpy(mel),                     # (N_MELS, CONTEXT_FRAMES)
            torch.tensor(sin, dtype=torch.float32),    # scalar
            torch.tensor(cos, dtype=torch.float32),    # scalar
            torch.tensor(bar, dtype=torch.long),       # scalar
            torch.tensor(phrase, dtype=torch.long),    # scalar
        )


def collate_fn(batch):
    mel, sin, cos, bar, phrase = zip(*batch)
    return (
        torch.stack(mel),
        {
            'beat_phase_sin': torch.stack(sin),
            'beat_phase_cos': torch.stack(cos),
            'beat_in_bar':    torch.stack(bar),
            'phase_type':    torch.stack(phrase),
        }
    )


def evaluate(model, val_paths, loss_fn, device, n_eval_tracks=50):
    """Schnelle Validierung auf einer Teilmenge der Val-Tracks."""
    model.eval()
    val_subset = random.sample(val_paths, min(n_eval_tracks, len(val_paths)))
    dataset = CachedTrackDataset(val_subset, samples_per_track=50)
    if len(dataset) == 0:
        return {}

    loader = DataLoader(dataset, batch_size=config.BATCH_SIZE,
                        collate_fn=collate_fn, num_workers=0)

    total_losses = {}
    n_batches = 0
    with torch.no_grad():
        for mel, targets in loader:
            mel = mel.to(device)
            targets = {k: v.to(device) for k, v in targets.items()}
            outputs = model(mel)
            losses = loss_fn(outputs, targets)
            for k, v in losses.items():
                total_losses[k] = total_losses.get(k, 0.0) + (v.item() if hasattr(v, 'item') else v)
            n_batches += 1

    return {k: v / n_batches for k, v in total_losses.items()}


def train(resume: bool = False):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"[Train] Device: {device}")
    if device.type == 'cuda':
        print(f"[Train] GPU: {torch.cuda.get_device_name(0)}")

    # ── Daten laden ──────────────────────────────────────────────────────────
    all_npz = sorted(glob.glob(os.path.join(config.CACHE_DIR, "track_*.npz")))
    if not all_npz:
        print("[ERROR] Kein Cache gefunden. Erst dataset_builder.py ausführen!")
        sys.exit(1)

    print(f"[Train] {len(all_npz)} gecachte Tracks gefunden")

    # Train/Val Split
    random.seed(42)
    random.shuffle(all_npz)
    split = int(len(all_npz) * (1 - config.VALIDATION_SPLIT))
    train_paths = all_npz[:split]
    val_paths   = all_npz[split:]
    print(f"[Train] Train: {len(train_paths)} | Val: {len(val_paths)}")

    # ── Modell ────────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(config.MODEL_SAVE_PATH), exist_ok=True)

    start_epoch = 0
    best_val_loss = float('inf')

    if resume and os.path.exists(config.MODEL_SAVE_PATH):
        model = load_model(config.MODEL_SAVE_PATH)
        checkpoint = torch.load(config.MODEL_SAVE_PATH, map_location='cpu', weights_only=True)
        start_epoch = checkpoint.get('epoch', 0) + 1
        best_val_loss = checkpoint.get('val_loss', float('inf'))
        print(f"[Train] Resume ab Epoch {start_epoch}")
    else:
        model = create_model()

    model = model.to(device)
    loss_fn = BeatPhraseLoss().to(device)
    optimizer = AdamW(model.parameters(), lr=config.LEARNING_RATE, weight_decay=1e-4)

    # TensorBoard
    writer = None
    if TENSORBOARD:
        tb_dir = os.path.join(os.path.dirname(config.MODEL_SAVE_PATH), "runs")
        writer = SummaryWriter(tb_dir)
        print(f"[Train] TensorBoard: tensorboard --logdir {tb_dir}")

    # ── Training Loop ─────────────────────────────────────────────────────────
    global_step = 0

    for epoch in range(start_epoch, config.NUM_EPOCHS):
        model.train()
        epoch_start = time.time()

        # Mini-Epoch: zufällige Teilmenge der Tracks laden
        mini_train = random.sample(train_paths,
                                   min(config.SONGS_PER_MINI_EPOCH, len(train_paths)))

        dataset = CachedTrackDataset(mini_train, samples_per_track=150)
        if len(dataset) == 0:
            print(f"[WARN] Epoch {epoch}: Dataset leer!")
            continue

        loader = DataLoader(
            dataset,
            batch_size=config.BATCH_SIZE,
            shuffle=True,
            collate_fn=collate_fn,
            num_workers=config.NUM_WORKERS,
            pin_memory=(device.type == 'cuda'),
            drop_last=True,
        )

        # LR Scheduler (OneCycle pro Mini-Epoch)
        scheduler = OneCycleLR(
            optimizer,
            max_lr=config.LEARNING_RATE,
            steps_per_epoch=len(loader),
            epochs=1,
            pct_start=0.1,
        )

        # ── Mini-Epoch Loop ──────────────────────────────────────────────────
        running_losses = {}
        n_batches = 0

        progress = tqdm(loader, desc=f"Epoch {epoch+1}/{config.NUM_EPOCHS}", leave=False)
        for mel, targets in progress:
            mel = mel.to(device)
            targets = {k: v.to(device) for k, v in targets.items()}

            optimizer.zero_grad()
            outputs = model(mel)
            losses = loss_fn(outputs, targets)
            losses['loss'].backward()

            # Gradient Clipping (Stabilität)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()
            scheduler.step()

            for k, v in losses.items():
                val = v.item() if hasattr(v, 'item') else v
                running_losses[k] = running_losses.get(k, 0.0) + val
            n_batches += 1
            global_step += 1

            if n_batches % 50 == 0:
                avg_loss = running_losses.get('loss', 0) / n_batches
                progress.set_postfix({'loss': f"{avg_loss:.4f}"})

                if writer:
                    writer.add_scalar('train/loss', avg_loss, global_step)

        # ── Validierung ──────────────────────────────────────────────────────
        val_losses = evaluate(model, val_paths, loss_fn, device)
        val_loss = val_losses.get('loss', float('inf'))

        train_loss = running_losses.get('loss', 0) / max(n_batches, 1)
        epoch_time = time.time() - epoch_start

        print(
            f"Epoch {epoch+1:3d}/{config.NUM_EPOCHS} | "
            f"Train: {train_loss:.4f} | "
            f"Val: {val_loss:.4f} | "
            f"Phase: {val_losses.get('loss_phase', 0):.4f} | "
            f"Bar: {val_losses.get('loss_bar', 0):.4f} | "
            f"Phrase: {val_losses.get('loss_phrase', 0):.4f} | "
            f"{epoch_time:.0f}s"
        )

        if writer:
            writer.add_scalar('val/loss', val_loss, epoch)
            writer.add_scalar('val/loss_phase', val_losses.get('loss_phase', 0), epoch)
            writer.add_scalar('val/loss_phrase', val_losses.get('loss_phrase', 0), epoch)

        # ── Checkpoint ───────────────────────────────────────────────────────
        checkpoint = {
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'val_loss': val_loss,
            'train_loss': train_loss,
        }

        # Bestes Modell speichern
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(checkpoint, config.MODEL_SAVE_PATH)
            print(f"  [OK] Bestes Modell gespeichert (Val-Loss: {val_loss:.4f})")

        # Periodischer Checkpoint alle 10 Epochs
        if (epoch + 1) % 10 == 0:
            ckpt_path = config.MODEL_SAVE_PATH.replace('.pt', f'_epoch{epoch+1}.pt')
            torch.save(checkpoint, ckpt_path)

    if writer:
        writer.close()

    print(f"\n[Train] Fertig! Bestes Modell: {config.MODEL_SAVE_PATH}")
    print(f"[Train] Beste Val-Loss: {best_val_loss:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="Vom letzten Checkpoint weitermachen")
    args = parser.parse_args()
    train(resume=args.resume)
