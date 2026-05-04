"""
VirtualLightDJ — autonome Licht-State-Machine.

Nimmt ML-Predictions (Phase, Beat, Energie) und schreibt smooth
DMX-Werte auf Fixtures. Alle künstlerischen Parameter stehen im
PARAMETER-Block am Anfang dieser Datei.

Schnittstelle:
    vldj = VirtualLightDJ()
    vldj.trigger_beat(beat_in_bar, phase, energy)   # bei jedem Beat
    vldj.trigger_transient()                         # bei Synth-Spike
    vldj.tick(engine, dt, phase, energy)             # 100 Hz Loop

Custom Paletten:
    save_custom_palette(name, colors)               # [(r,g,b), ...]
    load_custom_palettes()                          # lädt vldj_palettes.json
    get_all_palettes()                              # built-in + custom
"""

import json
import math
import os

# ══════════════════════════════════════════════════════════════════════
#  PARAMETER — hier tweaken
# ══════════════════════════════════════════════════════════════════════

# Farbpaletten: (R, G, B) Tupel, je 0.0–1.0
PALETTES: dict[str, list] = {
    "eis":       [(0.00, 0.70, 1.00), (0.10, 0.20, 1.00),
                  (0.60, 0.90, 1.00), (0.00, 0.40, 0.80)],
    "cyberpunk": [(0.00, 1.00, 1.00), (1.00, 0.00, 1.00),
                  (0.00, 0.50, 1.00), (1.00, 0.00, 0.50)],
    "fire":      [(1.00, 0.05, 0.00), (1.00, 0.35, 0.00),
                  (1.00, 0.55, 0.05), (0.90, 0.00, 0.00)],
    "neon":      [(0.00, 1.00, 0.20), (1.00, 0.90, 0.00),
                  (0.70, 0.00, 1.00), (0.00, 0.80, 1.00)],
}

# Welche Palette in welcher Phase (Fallback wenn kein Override)
PHASE_PALETTE: dict[str, str] = {
    "WAITING": "eis",
    "BREAK":   "eis",
    "BUILDUP": "cyberpunk",
    "DROP":    "fire",
}

# Abkling-Rate des Dimmer-Envelopes (pro Sekunde, exponentiell).
# Wird mit dem Aggressivitäts-Faktor skaliert (0.5 default = 1.0×).
DECAY: dict[str, float] = {
    "WAITING": 0.4,
    "BREAK":   0.7,
    "BUILDUP": 2.5,
    "DROP":    13.0,
}

BREAK_CAP        = 0.38   # max. Dimmer-Helligkeit im Break
BUILDUP_FLOOR    = 0.42   # min. Helligkeit im Buildup

DROP_DOWNBEAT_FLIP    = True
TRANSIENT_STRENGTH    = 0.82
TRANSIENT_DECAY       = 20.0
COLOR_FADE_RATE       = 3.5
BLINDER_TRANSIENT_MIX = 1.0
WASH_TRANSIENT_MIX    = 0.25

# ══════════════════════════════════════════════════════════════════════
#  CUSTOM PALETTEN — Persistenz
# ══════════════════════════════════════════════════════════════════════

CUSTOM_PALETTES_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'projects', 'vldj_palettes.json'
)
CUSTOM_PALETTES: dict[str, list] = {}

PALETTE_AUTO = "— Auto (Phase) —"


def load_custom_palettes() -> None:
    global CUSTOM_PALETTES
    if not os.path.exists(CUSTOM_PALETTES_PATH):
        return
    try:
        with open(CUSTOM_PALETTES_PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        CUSTOM_PALETTES = {k: [tuple(c) for c in v] for k, v in raw.items()}
        print(f"[light_dj] {len(CUSTOM_PALETTES)} custom palette(s) geladen")
    except Exception as e:
        print(f"[light_dj] Palette laden fehlgeschlagen: {e}")


def save_custom_palette(name: str, colors: list) -> None:
    """colors = list of (r, g, b) tuples with values 0.0–1.0. Minimum 2 colors."""
    if len(colors) < 2:
        raise ValueError("Mindestens 2 Farben benötigt")
    CUSTOM_PALETTES[name] = [tuple(c) for c in colors]
    _write_palettes_file()


def delete_custom_palette(name: str) -> None:
    if name in CUSTOM_PALETTES:
        del CUSTOM_PALETTES[name]
        _write_palettes_file()


def get_all_palettes() -> dict:
    """Merged dict: built-in first, then custom (custom can override)."""
    return {**PALETTES, **CUSTOM_PALETTES}


def _write_palettes_file() -> None:
    try:
        with open(CUSTOM_PALETTES_PATH, 'w', encoding='utf-8') as f:
            json.dump(
                {k: [list(c) for c in v] for k, v in CUSTOM_PALETTES.items()},
                f, indent=2, ensure_ascii=False
            )
    except Exception as e:
        print(f"[light_dj] Palette speichern fehlgeschlagen: {e}")


# Laden beim Import
load_custom_palettes()


# ══════════════════════════════════════════════════════════════════════


class VirtualLightDJ:
    """
    Autonome Licht-State-Machine.
    Trennt Beat-Trigger sauber von der kontinuierlichen Envelope-Logik.
    """

    def __init__(self):
        self._phase      = "WAITING"
        self._prev_phase = "WAITING"

        # Dimmer-Envelope: wird bei Beat-Hits gesetzt, klingt exponentiell ab
        self._dim_env       = 0.0
        # Transient-Envelope: weißer Kurz-Flash bei Synth-Spikes
        self._transient_env = 0.0

        # Farb-Interpolation
        self._palette_name = "eis"
        self._color_idx    = 0
        self._tgt_r = self._tgt_g = self._tgt_b = 0.5
        self._cur_r = self._cur_g = self._cur_b = 0.0

        # Steuerung
        self.is_active        = True     # on/off aus der UI
        self.aggressiveness   = 0.5      # 0=sanft, 0.5=standard, 1=hart
        self._palette_override: str | None = None   # None = Phase-Automatik

    # ── Öffentliche API ───────────────────────────────────────────────

    def set_palette(self, name: str | None) -> None:
        """Setzt eine globale Palette für alle Phasen. None = Phase-Automatik."""
        self._palette_override = name

    def set_aggressiveness(self, value: float) -> None:
        """0.0 = sehr sanft, 0.5 = Standard, 1.0 = sehr hart."""
        self.aggressiveness = max(0.0, min(1.0, value))

    def trigger_beat(self, beat_in_bar: int, phase: str, energy: float):
        """
        Einmal bei jedem erkannten Beat aufrufen.

        beat_in_bar : 0-15 (ML) oder 0-3 (Kick-Fallback)
        phase       : "BREAK" / "BUILDUP" / "DROP"
        energy      : 0.0–1.0 (Langzeit-RMS-Verhältnis)
        """
        palette = self._get_palette(phase)
        bar_pos = beat_in_bar % 4

        if phase == "DROP":
            if bar_pos == 0:
                self._dim_env = 1.0
                if DROP_DOWNBEAT_FLIP:
                    opp = (self._color_idx + max(1, len(palette) // 2)) % len(palette)
                    self._tgt_r, self._tgt_g, self._tgt_b = palette[opp]
                else:
                    self._tgt_r, self._tgt_g, self._tgt_b = palette[self._color_idx % len(palette)]
            else:
                hit_strength = 0.5 + 0.4 * energy
                self._dim_env = max(self._dim_env, hit_strength)
                self._tgt_r, self._tgt_g, self._tgt_b = palette[bar_pos % len(palette)]
            self._color_idx = (self._color_idx + 1) % len(palette)

        elif phase == "BUILDUP":
            target = BUILDUP_FLOOR + (1.0 - BUILDUP_FLOOR) * energy
            self._dim_env = max(self._dim_env, target)
            self._color_idx = (self._color_idx + 1) % len(palette)
            self._tgt_r, self._tgt_g, self._tgt_b = palette[self._color_idx]

        else:  # BREAK / WAITING
            if bar_pos == 0:
                self._dim_env = max(self._dim_env, 0.22)
                self._color_idx = (self._color_idx + 1) % len(palette)
                self._tgt_r, self._tgt_g, self._tgt_b = palette[self._color_idx]

    def trigger_transient(self):
        """Synth-Spike erkannt → weißer Kurz-Flash."""
        self._transient_env = TRANSIENT_STRENGTH

    def tick(self, engine, dt: float, phase: str, energy: float):
        """
        Kontinuierlicher 100-Hz-Update.

        engine : LightEngine-Instanz
        dt     : Sekunden seit letztem Aufruf (≈0.01)
        phase  : aktuelle Phase
        energy : 0.0–1.0
        """
        if not self.is_active:
            return

        if phase != self._phase:
            self._prev_phase = self._phase
            self._phase      = phase
            self._on_phase_change(phase)

        # Decay skaliert mit Aggressivität: 0.5 default → 1.0×
        decay_mult = self.aggressiveness * 2.0
        base_decay = DECAY.get(phase, 2.0) * decay_mult
        if phase == "BUILDUP":
            base_decay *= (1.0 + energy * 1.8)

        self._dim_env       = max(0.0, self._dim_env       - dt * base_decay)
        self._transient_env = max(0.0, self._transient_env - dt * TRANSIENT_DECAY)

        alpha = min(1.0, COLOR_FADE_RATE * dt)
        self._cur_r += (self._tgt_r - self._cur_r) * alpha
        self._cur_g += (self._tgt_g - self._cur_g) * alpha
        self._cur_b += (self._tgt_b - self._cur_b) * alpha

        self._apply(engine, phase, energy)

    def blackout(self, engine) -> None:
        """Sofortiger Blackout — setzt alle Fixture-Kanäle auf 0."""
        self._dim_env       = 0.0
        self._transient_env = 0.0
        self._cur_r = self._cur_g = self._cur_b = 0.0
        self._tgt_r = self._tgt_g = self._tgt_b = 0.0
        for fixture in engine.fixtures:
            for role in ('dimmer', 'red', 'green', 'blue', 'white', 'strobe'):
                if fixture.has(role):
                    fixture.set(role, 0.0)

    def white_flash(self, engine) -> None:
        """Sofortiger Weiss-Flash — alle Fixtures auf volle Helligkeit."""
        self._transient_env = 1.0
        self._dim_env       = 1.0
        for fixture in engine.fixtures:
            if fixture.has('laser_mode'):
                continue
            if fixture.has('dimmer'):
                fixture.set('dimmer', 1.0)
            if fixture.has('white'):
                fixture.set('white', 1.0)
            if fixture.has('red'):   fixture.set('red',   1.0)
            if fixture.has('green'): fixture.set('green', 1.0)
            if fixture.has('blue'):  fixture.set('blue',  1.0)
            if fixture.has('strobe'):
                fixture.set('strobe', 0.0)

    # ── Interne Methoden ──────────────────────────────────────────────

    def _get_palette(self, phase: str) -> list:
        all_pal = get_all_palettes()
        if self._palette_override is not None:
            return all_pal.get(self._palette_override, PALETTES['eis'])
        palette_name = PHASE_PALETTE.get(phase, 'eis')
        return all_pal.get(palette_name, PALETTES['eis'])

    def _on_phase_change(self, phase: str):
        palette = self._get_palette(phase)
        self._color_idx = 0
        self._tgt_r, self._tgt_g, self._tgt_b = palette[0]
        if phase == "DROP":
            self._dim_env = 1.0

    def _apply(self, engine, phase: str, energy: float):
        r, g, b = self._cur_r, self._cur_g, self._cur_b
        t_add   = self._transient_env

        dim = self._dim_env
        if phase == "BREAK":
            dim = min(dim, BREAK_CAP)
        elif phase == "BUILDUP":
            dim = max(dim, BUILDUP_FLOOR * energy)

        for fixture in engine.fixtures:
            if fixture.has("laser_mode"):
                continue

            if fixture.has("white"):
                blinder = min(1.0, dim + t_add * BLINDER_TRANSIENT_MIX)
                if fixture.has("dimmer"):
                    fixture.set("dimmer", blinder)
                    if fixture.has("red"):   fixture.set("red",   0.0)
                    if fixture.has("green"): fixture.set("green", 0.0)
                    if fixture.has("blue"):  fixture.set("blue",  0.0)
                    fixture.set("white", 1.0)
                else:
                    fixture.set("white", blinder)
                if fixture.has("strobe"):
                    fixture.set("strobe", 0.0)
                continue

            eff_dim = min(1.0, dim + t_add * WASH_TRANSIENT_MIX)
            if fixture.has("dimmer"):
                fixture.set("dimmer", eff_dim)
                if fixture.has("red"):   fixture.set("red",   r)
                if fixture.has("green"): fixture.set("green", g)
                if fixture.has("blue"):  fixture.set("blue",  b)
            else:
                if fixture.has("red"):   fixture.set("red",   r * eff_dim)
                if fixture.has("green"): fixture.set("green", g * eff_dim)
                if fixture.has("blue"):  fixture.set("blue",  b * eff_dim)

            if fixture.has("strobe"):
                fixture.set("strobe", min(1.0, t_add * 0.85))
