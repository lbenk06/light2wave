"""
Beat & Phrase Erkennungs-Modell — Causal Temporal Convolutional Network (TCN)

Architektur:
  Input:  (batch, N_MELS, CONTEXT_FRAMES)  ← Mel-Spektrogramm Fenster
          kausal: Frame T hängt nur von Frames ≤T ab → live-fähig!

  TCN-Backbone:
    7 Blöcke mit exponentiell wachsender Dilation (1,2,4,8,16,32,64)
    Jeder Block: DilatedCausalConv → BatchNorm → ReLU → Residual

  Output-Köpfe:
    beat_phase   → 2 Werte (sin + cos der Phase)  Regression
    beat_in_bar  → 16 Klassen (Beat 1–16)          Klassifikation
    phrase_type  → 10 Klassen (Intro, Chorus, ...)  Klassifikation

Modell-Größe: ~500K Parameter → schnell auf CPU (<10ms Inferenz)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import config


class CausalConv1d(nn.Module):
    """
    Kausale 1D-Faltung: Output T hängt nur von Inputs ≤T ab.
    Erreicht durch linksseitiges Padding = (kernel-1) × dilation.
    """
    def __init__(self, in_channels: int, out_channels: int,
                 kernel_size: int, dilation: int = 1):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_channels, out_channels, kernel_size,
            dilation=dilation, padding=0
        )

    def forward(self, x):
        # x: (batch, channels, time)
        x = F.pad(x, (self.padding, 0))
        return self.conv(x)


class TCNBlock(nn.Module):
    """
    Ein TCN-Residual-Block:
      → DilatedCausalConv → BatchNorm → GELU
      → DilatedCausalConv → BatchNorm → GELU
      → Residual (mit 1x1-Conv falls Kanäle sich ändern)
    """
    def __init__(self, in_channels: int, out_channels: int,
                 kernel_size: int = 3, dilation: int = 1, dropout: float = 0.1):
        super().__init__()

        self.net = nn.Sequential(
            CausalConv1d(in_channels, out_channels, kernel_size, dilation),
            nn.BatchNorm1d(out_channels),
            nn.GELU(),
            nn.Dropout(dropout),
            CausalConv1d(out_channels, out_channels, kernel_size, dilation),
            nn.BatchNorm1d(out_channels),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        # 1x1 Projection falls In ≠ Out Kanäle
        self.shortcut = (
            nn.Conv1d(in_channels, out_channels, 1)
            if in_channels != out_channels
            else nn.Identity()
        )

    def forward(self, x):
        return self.net(x) + self.shortcut(x)


class BeatPhraseModel(nn.Module):
    """
    Multi-Task Modell für Beat-Phase und Phrasen-Erkennung.

    Input:  mel Spektrogramm  shape (batch, N_MELS, CONTEXT_FRAMES)
    Output: dict mit:
      'beat_phase'  → (batch, 2)   [sin, cos]
      'beat_in_bar' → (batch, 16)  Logits
      'phrase_type' → (batch, 10)  Logits
    """

    def __init__(
        self,
        n_mels: int = config.N_MELS,
        context_frames: int = config.CONTEXT_FRAMES,
        num_beats_in_bar: int = config.NUM_BEATS_IN_BAR,
        num_phrase_types: int = config.NUM_PHRASE_TYPES,
        channels: int = 64,
        n_blocks: int = 7,
        kernel_size: int = 3,
        dropout: float = 0.1,
    ):
        super().__init__()

        self.n_mels = n_mels
        self.context_frames = context_frames

        # ── Eingangs-Projektion: N_MELS → channels ──────────────────────────
        self.input_proj = nn.Sequential(
            nn.Conv1d(n_mels, channels, kernel_size=1),
            nn.BatchNorm1d(channels),
            nn.GELU(),
        )

        # ── TCN Backbone ─────────────────────────────────────────────────────
        # Dilations: 1, 2, 4, 8, 16, 32, 64 → receptive field = ~256 Frames
        tcn_blocks = []
        for i in range(n_blocks):
            dilation = 2 ** i
            in_ch = channels if i == 0 else channels * 2
            out_ch = channels * 2
            tcn_blocks.append(TCNBlock(in_ch, out_ch, kernel_size, dilation, dropout))
        self.tcn = nn.ModuleList(tcn_blocks)

        feature_dim = channels * 2  # nach letztem Block

        # ── Output-Köpfe ─────────────────────────────────────────────────────
        # Shared Feature → komprimiert auf 256 Dims
        self.shared_head = nn.Sequential(
            nn.Linear(feature_dim, 256),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        # Beat-Phase: sin + cos → Regression
        self.beat_phase_head = nn.Linear(256, 2)

        # Beat-in-Bar: Klassifikation 0-15
        self.beat_in_bar_head = nn.Linear(256, num_beats_in_bar)

        # Phrasen-Typ: Klassifikation 0-9
        self.phrase_type_head = nn.Linear(256, num_phrase_types)

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, nonlinearity='relu')
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, mel: torch.Tensor) -> dict:
        """
        Args:
            mel: (batch, N_MELS, CONTEXT_FRAMES)

        Returns:
            dict mit 'beat_phase', 'beat_in_bar', 'phrase_type'
        """
        # (batch, N_MELS, T) → (batch, channels, T)
        x = self.input_proj(mel)

        # TCN Backbone
        for block in self.tcn:
            x = block(x)

        # Letzten Frame nehmen (kausale Vorhersage für aktuellen Zeitpunkt)
        # x: (batch, feature_dim, T) → nimm [:, :, -1]
        x = x[:, :, -1]  # (batch, feature_dim)

        # Shared Head
        shared = self.shared_head(x)  # (batch, 256)

        # Outputs
        beat_phase = self.beat_phase_head(shared)      # (batch, 2) - keine Aktivierung!
        beat_in_bar = self.beat_in_bar_head(shared)    # (batch, 16) Logits
        phrase_type = self.phrase_type_head(shared)    # (batch, 10) Logits

        return {
            'beat_phase': beat_phase,     # sin/cos, normiert nach Loss
            'beat_in_bar': beat_in_bar,   # Logits → CrossEntropy
            'phrase_type': phrase_type,   # Logits → CrossEntropy
        }

    @property
    def n_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class BeatPhraseLoss(nn.Module):
    """
    Multi-Task Loss:
      L = w1 × CircularMSE(beat_phase) + w2 × CE(beat_in_bar) + w3 × CE(phrase_type)
    """
    def __init__(
        self,
        w_phase: float = 1.0,
        w_bar: float = 0.5,
        w_phrase: float = 1.0,
        phrase_weight_unknown: float = 0.2,  # "unknown" Klasse geringer gewichten
    ):
        super().__init__()
        self.w_phase  = w_phase
        self.w_bar    = w_bar
        self.w_phrase = w_phrase

        # Klassengewichte: "unknown" (Klasse 0) weniger gewichten
        phrase_weights = torch.ones(config.NUM_PHRASE_TYPES)
        phrase_weights[0] = phrase_weight_unknown
        self.register_buffer('phrase_weights', phrase_weights)

    def forward(self, outputs: dict, targets: dict) -> dict:
        """
        Args:
            outputs: dict von BeatPhraseModel.forward()
            targets: dict mit:
                'beat_phase_sin':  (batch,)
                'beat_phase_cos':  (batch,)
                'beat_in_bar':     (batch,) int64
                'phrase_type':     (batch,) int64
        Returns:
            dict mit 'loss' (gesamt) und Einzel-Losses für Logging
        """
        # Beat-Phase: MSE auf sin + cos separat (circular loss)
        pred_sin = outputs['beat_phase'][:, 0]
        pred_cos = outputs['beat_phase'][:, 1]
        loss_phase = F.mse_loss(pred_sin, targets['beat_phase_sin']) + \
                     F.mse_loss(pred_cos, targets['beat_phase_cos'])

        # Beat-in-Bar: Cross-Entropy
        loss_bar = F.cross_entropy(outputs['beat_in_bar'], targets['beat_in_bar'])

        # Phrasen-Typ: Cross-Entropy (mit Klassengewichten)
        loss_phrase = F.cross_entropy(
            outputs['phrase_type'],
            targets['phrase_type'],
            weight=self.phrase_weights,
        )

        total = (
            self.w_phase  * loss_phase +
            self.w_bar    * loss_bar   +
            self.w_phrase * loss_phrase
        )

        return {
            'loss':         total,
            'loss_phase':   loss_phase.item(),
            'loss_bar':     loss_bar.item(),
            'loss_phrase':  loss_phrase.item(),
        }


def create_model() -> BeatPhraseModel:
    """Erstellt ein neues Modell mit Standard-Hyperparametern aus config.py."""
    model = BeatPhraseModel()
    print(f"[Model] BeatPhraseModel erstellt: {model.n_parameters:,} Parameter")
    return model


def load_model(path: str = config.MODEL_SAVE_PATH) -> BeatPhraseModel:
    """Lädt ein trainiertes Modell vom Disk."""
    model = BeatPhraseModel()
    state = torch.load(path, map_location='cpu', weights_only=True)
    model.load_state_dict(state['model_state_dict'])
    model.eval()
    print(f"[Model] Modell geladen von {path}")
    print(f"[Model] Trainiert bis Epoch {state.get('epoch', '?')}, "
          f"Val-Loss: {state.get('val_loss', '?'):.4f}")
    return model


if __name__ == "__main__":
    # Schneller Architektur-Test
    model = create_model()
    batch = torch.randn(4, config.N_MELS, config.CONTEXT_FRAMES)
    out = model(batch)
    print(f"\nOutput shapes:")
    for k, v in out.items():
        print(f"  {k}: {v.shape}")

    loss_fn = BeatPhraseLoss()
    targets = {
        'beat_phase_sin': torch.randn(4),
        'beat_phase_cos': torch.randn(4),
        'beat_in_bar':    torch.randint(0, 16, (4,)),
        'phrase_type':    torch.randint(0, 10, (4,)),
    }
    losses = loss_fn(out, targets)
    print(f"\nLosses: {losses}")
