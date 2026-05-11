"""
sunset_groove.py — ruhiger Outdoor-Mode fuer Freiluftfrequenz-Sets.

Setzt sehr weiches Licht (langsames Atmen aller Fixtures in einer warmen
Sonnenuntergangs-Palette), kein Strobe, keine Auto-Effekt-Wechsel. Die
einzige Aktion auf einen DROP ist ein einzelner kurzer Blinder-Pulse.

Wird ueber eine eigene Routine im audio_ticker getriggert (on_beat) und
durch einen eigenen 100 Hz Ticker continuiert (tick).
"""
import math


# Warme Sonnenuntergangs-Palette als (R, G, B, W) Tupel im 0..1 Bereich.
# Mischung aus tiefem Rot, Orange, Bernstein, warmen Weiss. Nichts kaltes.
SUNSET_PALETTE = [
    (1.00, 0.18, 0.00, 0.10),   # Tiefes Rot
    (1.00, 0.42, 0.08, 0.18),   # Sonnenuntergangs-Orange
    (1.00, 0.28, 0.00, 0.30),   # Warmes Rot + Glow
    (0.90, 0.55, 0.12, 0.35),   # Bernstein / Amber
    (1.00, 0.10, 0.00, 0.40),   # Rot mit warmem Weiss
    (0.65, 0.20, 0.00, 0.50),   # Sanftes Rotglow
]


sunset_state = {
    # User-Einstellungen
    "brightness":          0.85,  # 0..1 Master-Helligkeit
    "blinder_strength":    0.90,  # 0..1 Drop-Blinder-Pulse-Intensitaet
    "color_cycle_beats":   32,    # so viele Beats pro Farb-Schritt (sehr langsam)
    "laser_on":            True,  # Laser an/aus
    "breath_speed":        0.45,  # Atemfrequenz (Hz-ish)
    "breath_depth":        0.30,  # +/- Schwankung um Mittelpunkt 0.6

    # Interner State - nicht direkt vom User aendern
    "_palette_idx":        0,
    "_palette_progress":   0.0,   # 0..1 innerhalb des aktuellen Farb-Schritts
    "_blinder_level":      0.0,   # decayt mit der Zeit
    "_last_phase":         "BREAK",
    "_breath_t":           0.0,
}


def reset():
    """Beim Mode-Wechsel / Audio-Stop aufrufen."""
    s = sunset_state
    s["_palette_idx"]      = 0
    s["_palette_progress"] = 0.0
    s["_blinder_level"]    = 0.0
    s["_last_phase"]       = "BREAK"
    s["_breath_t"]         = 0.0


def on_beat(phase="BREAK"):
    """Wird bei jedem erkannten Beat aufgerufen (analog magic_auto.on_beat)."""
    s = sunset_state

    # Farbe schreitet pro Beat einen kleinen Schritt weiter (sehr langsam)
    step = 1.0 / max(1, s["color_cycle_beats"])
    s["_palette_progress"] += step
    if s["_palette_progress"] >= 1.0:
        s["_palette_progress"] -= 1.0
        s["_palette_idx"] = (s["_palette_idx"] + 1) % len(SUNSET_PALETTE)

    # Drop-Pulse: nur beim Uebergang in DROP einen kurzen Blinder
    if phase == "DROP" and s["_last_phase"] != "DROP":
        s["_blinder_level"] = max(s["_blinder_level"], s["blinder_strength"])

    s["_last_phase"] = phase


def tick(engine, dt, phase="BREAK", energy=0.5):
    """Kontinuierlicher Update (~100 Hz). Setzt Fixture-Werte basierend auf
    Palette + Atem + Drop-Pulse-Decay."""
    s = sunset_state

    # Atem fortschreiben
    s["_breath_t"] += dt

    # Drop-Blinder decay (Decay-Rate so dass nach ~0.6 s wieder unten)
    if s["_blinder_level"] > 0.0:
        s["_blinder_level"] = max(0.0, s["_blinder_level"] - dt * 1.8)

    # Smooth Farb-Interpolation zwischen aktuellem und naechstem Palette-Slot
    progress  = s["_palette_progress"]
    cur_color  = SUNSET_PALETTE[s["_palette_idx"]]
    next_color = SUNSET_PALETTE[(s["_palette_idx"] + 1) % len(SUNSET_PALETTE)]
    r = cur_color[0] * (1 - progress) + next_color[0] * progress
    g = cur_color[1] * (1 - progress) + next_color[1] * progress
    b = cur_color[2] * (1 - progress) + next_color[2] * progress
    w = cur_color[3] * (1 - progress) + next_color[3] * progress

    # Sehr langsames Atmen (Sinus um Mittelpunkt 0.6)
    breath = 0.60 + s["breath_depth"] * math.sin(s["_breath_t"] * s["breath_speed"])
    base_dim = s["brightness"] * breath

    # Sanfte Phase-Reaktion: DROP etwas heller, BREAK etwas dunkler.
    # Bewusst klein gehalten damit es ruhig wirkt.
    if phase == "DROP":
        base_dim *= 1.10
    elif phase == "BREAK":
        base_dim *= 0.75

    base_dim = max(0.0, min(1.0, base_dim))
    blinder  = s["_blinder_level"]

    for fixture in engine.fixtures:
        # Laser-Fixtures separat
        if fixture.has("laser_mode"):
            if s.get("laser_on", True):
                # Langsames warmes Pattern, niedrige Geschwindigkeit
                fixture.set("laser_mode",    175 / 255.0)
                fixture.set("pattern",        0.15)
                fixture.set("x_pos",          0.0)
                fixture.set("y_pos",          0.0)
                fixture.set("speed",          0.15)
                fixture.set("laser_speed",    0.0)
                fixture.set("zoom",           0.35)
                fixture.set("laser_color",    0.0)    # Rot
                fixture.set("color_segment",  0.0)
            else:
                fixture.set("laser_mode", 0.0)
            continue

        # RGBW-Fixtures: warme Farbe + Atem-Dimmer + ggf. Blinder-Overlay
        if fixture.has("dimmer"):
            if blinder > 0.01:
                # Blinder-Pulse: in Richtung Weiss mixen + Dimmer hoch
                br = r * (1 - blinder) + 1.0 * blinder
                bg = g * (1 - blinder) + 1.0 * blinder
                bb = b * (1 - blinder) + 1.0 * blinder
                bw = w * (1 - blinder) + 1.0 * blinder
                fixture.set("red",   br)
                fixture.set("green", bg)
                fixture.set("blue",  bb)
                if fixture.has("white"):
                    fixture.set("white", bw)
                fixture.set("dimmer", max(base_dim, blinder))
            else:
                fixture.set("red",   r)
                fixture.set("green", g)
                fixture.set("blue",  b)
                if fixture.has("white"):
                    fixture.set("white", w)
                fixture.set("dimmer", base_dim)

            if fixture.has("strobe"):
                fixture.set("strobe", 0.0)
