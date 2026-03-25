import time
import random
from engine.generators import GENERATOR_MAP

# Welche Effekte passen zu welcher Phase
PHASE_EFFECT_POOLS = {
    "BREAK":   ["breathing", "scanner", "vertical_wave", "flicker"],
    "BUILDUP": ["linear_wave", "center_sym", "radar", "plasma"],
    "DROP":    ["hard_chase", "gate_pulse", "sparkle", "center_sym", "radar"],
    "WAITING": ["breathing"],
}

# Vordefinierte Farbpaletten: liste von (r, g, b, w) Tupeln (0.0 - 1.0)
COLOR_PALETTES = {
    "Custom":  None,
    "Warm":    [(1.0, 0.15, 0.0, 0.0), (1.0, 0.4, 0.0, 0.0), (0.9, 0.05, 0.0, 0.0), (1.0, 0.6, 0.0, 0.0)],
    "Kalt":    [(0.0, 0.2,  1.0, 0.0), (0.1, 0.0,  1.0, 0.0), (0.0, 0.6,  1.0, 0.0), (0.3, 0.0,  0.8, 0.0)],
    "Club":    [(1.0, 0.0,  0.5, 0.0), (0.0, 0.0,  1.0, 0.0), (0.6, 0.0,  1.0, 0.0), (1.0, 0.0,  1.0, 0.0)],
    "Feuer":   [(1.0, 0.0,  0.0, 0.0), (1.0, 0.25, 0.0, 0.0), (1.0, 0.6,  0.0, 0.0), (0.9, 0.05, 0.0, 0.0)],
    "Eis":     [(0.0, 0.8,  1.0, 0.2), (0.0, 0.4,  1.0, 0.3), (0.2, 0.2,  1.0, 0.0), (0.0, 1.0,  0.9, 0.1)],
    "Weiss":   [(0.0, 0.0,  0.0, 1.0), (0.2, 0.2,  0.3, 0.6), (0.0, 0.0,  0.0, 1.0), (0.1, 0.1,  0.2, 0.7)],
    "Neon":    [(0.0, 1.0,  0.2, 0.0), (1.0, 0.9,  0.0, 0.0), (0.0, 0.8,  1.0, 0.0), (1.0, 0.0,  0.6, 0.0)],
}

# Effekt-Auswahl fuer manuellen Modus (Anzeigename -> Generator-Key)
EFFECT_OPTIONS = {
    "Keiner":           "none",
    "Atmen":            "breathing",
    "Links-Rechts":     "linear_wave",
    "Mitte-Aussen":     "center_sym",
    "Vertikale Welle":  "vertical_wave",
    "Plasma":           "plasma",
    "Radar":            "radar",
    "Harter Chase":     "hard_chase",
    "Scanner":          "scanner",
    "Funkeln":          "sparkle",
    "Flimmern":         "flicker",
}

magic_auto_state = {
    # Basis-Slider (immer aktiv)
    "brightness":       0.8,
    "red":              0.2,
    "green":            0.0,
    "blue":             1.0,
    "white":            0.0,
    "strobe_amount":    0.0,
    "blinder_strength": 0.9,
    "fade":             0.4,    # 0 = harter Schnitt, 1 = langsames Abklingen (Blinder-Decay)
    "color_fade":       0.0,    # 0 = harter Farbwechsel, 1 = weicher Ueberblend
    "phase_react":      True,
    "effect_speed":     2.0,    # max. Effektgeschwindigkeit

    # Blackout
    "blackout_interval": 0,     # alle N Beats ein Blackout (0 = nie)
    "blackout_duration": 0.3,   # wie lange der Blackout dauert (Sekunden)

    # Automatik-Optionen
    "auto_effects":         True,
    "effect_change_beats":  8,      # alle N Beats neuen Effekt waehlen
    "color_palette":        "Club", # "Custom" = Slider-Werte, sonst Palette

    # Manuell gewaehlter Effekt (nur aktiv wenn auto_effects=False)
    "effect": "none",

    # Interner State (kein UI-Binding)
    "_prev_effect":       "none",
    "_effect_start":      0.0,
    "_prev_effect_start": 0.0,
    "_transition_start":  -1.0,
    "_transition_dur":    0.6,
    "_blinder_level":     0.0,
    "_last_update":       0.0,
    "_beat_count":        0,
    "_color_idx":         0,
    "_last_phase":        "WAITING",
    "_blackout_active":   False,
    "_blackout_end_time": 0.0,
    # aktuelle Farbwerte fuer sanftes Faeden (Ueberblend)
    "_cur_r": 0.0, "_cur_g": 0.0, "_cur_b": 0.0, "_cur_w": 0.0,
}


def _pick_new_effect(phase):
    """Waehlt einen neuen Effekt aus dem Phasen-Pool und startet den Crossfade."""
    s = magic_auto_state
    pool = PHASE_EFFECT_POOLS.get(phase, PHASE_EFFECT_POOLS["DROP"])

    # Aktuellen Effekt vermeiden, damit immer etwas Neues kommt
    available = [e for e in pool if e != s["effect"]]
    if not available:
        available = pool

    new_effect = random.choice(available)

    # Crossfade starten
    now = time.time()
    s["_prev_effect"]       = s["effect"]
    s["_prev_effect_start"] = s["_effect_start"]
    s["effect"]             = new_effect
    s["_effect_start"]      = now
    s["_transition_start"]  = now


def on_beat(phase="DROP"):
    """Wird bei jedem erkannten Beat aufgerufen."""
    s = magic_auto_state

    # Blinder-Flash
    s["_blinder_level"] = min(1.0, s["blinder_strength"])

    s["_beat_count"] += 1

    # Blackout-Trigger
    interval = int(s["blackout_interval"])
    if interval > 0 and s["_beat_count"] % interval == 0:
        s["_blackout_active"]   = True
        s["_blackout_end_time"] = time.time() + max(0.05, s["blackout_duration"])

    # Automatischer Effektwechsel
    if s["auto_effects"]:
        change_interval = max(1, int(s["effect_change_beats"]))
        phase_changed   = phase != s["_last_phase"]

        # Wechseln wenn: Interval erreicht ODER Phase hat sich geaendert
        if s["_beat_count"] % change_interval == 0 or phase_changed:
            _pick_new_effect(phase)

    s["_last_phase"] = phase

    # Automatischer Farbwechsel aus Palette
    if s["color_palette"] != "Custom":
        palette = COLOR_PALETTES.get(s["color_palette"])
        if palette:
            s["_color_idx"] = (s["_color_idx"] + 1) % len(palette)


def apply(engine, phase="DROP"):
    """
    Kontinuierlicher Update - wird bei jedem Timer-Tick (~100 Hz) aufgerufen.
    Berechnet alle Fixture-Werte inkl. Crossfade zwischen Effekten.
    """
    s = magic_auto_state

    now = time.time()
    dt  = min(now - s["_last_update"] if s["_last_update"] > 0 else 0.01, 0.1)
    s["_last_update"] = now

    # --- Phasen-Multiplikator ---
    if s["phase_react"]:
        pm = {"BREAK": 0.15, "BUILDUP": 0.55, "DROP": 1.0, "WAITING": 0.15}.get(phase, 1.0)
    else:
        pm = 1.0

    # --- Effektgeschwindigkeit automatisch an Phase anpassen ---
    if s["auto_effects"] and s["phase_react"]:
        speed_mult = {"BREAK": 0.25, "BUILDUP": 0.65, "DROP": 1.0, "WAITING": 0.2}.get(phase, 1.0)
        effect_speed = s["effect_speed"] * speed_mult
    else:
        effect_speed = s["effect_speed"]

    # --- Blinder abklingen lassen ---
    decay_rate         = 0.3 + (1.0 - s["fade"]) * 19.7
    s["_blinder_level"] = max(0.0, s["_blinder_level"] - dt * decay_rate)

    # --- Effekt-Funktionen (mit Crossfade) ---
    cur_func  = GENERATOR_MAP.get(s["effect"])
    cur_t     = now - s["_effect_start"]

    prev_func = GENERATOR_MAP.get(s["_prev_effect"])
    prev_t    = now - s["_prev_effect_start"]

    trans_elapsed = now - s["_transition_start"] if s["_transition_start"] > 0 else s["_transition_dur"]
    blend         = min(1.0, trans_elapsed / s["_transition_dur"]) if s["_transition_dur"] > 0 else 1.0

    # --- Blackout: alles aus fuer die eingestellte Dauer ---
    if s["_blackout_active"]:
        if now < s["_blackout_end_time"]:
            for fixture in engine.fixtures:
                if fixture.has("dimmer"):
                    fixture.set("dimmer", 0.0)
                else:
                    for role in ["red", "green", "blue", "white"]:
                        if fixture.has(role): fixture.set(role, 0.0)
                if fixture.has("strobe"): fixture.set("strobe", 0.0)
            return  # nichts weiter tun
        else:
            s["_blackout_active"] = False

    # --- Zielfarbe: Palette oder Custom-Slider ---
    if s["color_palette"] != "Custom":
        palette = COLOR_PALETTES.get(s["color_palette"])
        if palette:
            target_r, target_g, target_b, target_w = palette[s["_color_idx"] % len(palette)]
        else:
            target_r, target_g, target_b, target_w = s["red"], s["green"], s["blue"], s["white"]
    else:
        target_r, target_g, target_b, target_w = s["red"], s["green"], s["blue"], s["white"]

    # --- Farbueberblend: hart (0) oder weich (1) ---
    cf = s["color_fade"]
    if cf > 0.0:
        # Interpolationsrate: cf=0.01 -> ~50/s (fast), cf=1.0 -> ~0.5/s (slow)
        rate = 0.5 + (1.0 - cf) * 49.5
        alpha = min(1.0, rate * dt)
        s["_cur_r"] += (target_r - s["_cur_r"]) * alpha
        s["_cur_g"] += (target_g - s["_cur_g"]) * alpha
        s["_cur_b"] += (target_b - s["_cur_b"]) * alpha
        s["_cur_w"] += (target_w - s["_cur_w"]) * alpha
    else:
        s["_cur_r"], s["_cur_g"], s["_cur_b"], s["_cur_w"] = target_r, target_g, target_b, target_w

    r, g, b, w = s["_cur_r"], s["_cur_g"], s["_cur_b"], s["_cur_w"]

    base_dim = s["brightness"] * pm
    blinder  = s["_blinder_level"]

    for fixture in engine.fixtures:
        # Generator-Wert mit Crossfade berechnen
        cur_val  = cur_func(fixture, cur_t, speed=effect_speed, width=5.0) if cur_func else 1.0
        prev_val = prev_func(fixture, prev_t, speed=effect_speed, width=5.0) if prev_func else 1.0

        if blend < 1.0:
            gen_val = prev_val * (1.0 - blend) + cur_val * blend
        else:
            gen_val = cur_val

        dimmer = min(1.0, base_dim * gen_val + blinder)

        # Dimmer-Kanal vorhanden: separat dimmen
        if fixture.has("dimmer"):
            fixture.set("dimmer", dimmer)
            if fixture.has("red"):   fixture.set("red",   r)
            if fixture.has("green"): fixture.set("green", g)
            if fixture.has("blue"):  fixture.set("blue",  b)
            if fixture.has("white"): fixture.set("white", w)
        else:
            # Kein Dimmer: Helligkeit direkt in RGB einrechnen
            if fixture.has("red"):   fixture.set("red",   r * dimmer)
            if fixture.has("green"): fixture.set("green", g * dimmer)
            if fixture.has("blue"):  fixture.set("blue",  b * dimmer)
            if fixture.has("white"): fixture.set("white", w * dimmer)

        # Hardware-Strobe
        if fixture.has("strobe"):
            fixture.set("strobe", s["strobe_amount"])
