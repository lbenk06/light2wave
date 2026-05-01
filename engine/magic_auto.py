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
    "blinder_strength": 0.6,
    "blinder_every":    1,      # Blinder alle N Beats (1=jeden, 2=jeden 2., 4=jeden 4.)
    "blinder_phases":   ["DROP"],  # in welchen Phasen der Blinder feuert
    "fade":             0.65,   # 0 = harter Schnitt, 1 = langsames Abklingen (Blinder-Decay)
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

    # Intelligente Automatik-Toggles
    "synth_blinder":     True,   # Transient/Synth-Spike → Blinder-Flash
    "smart_flash":       True,   # Flash nur bei Drop-Übergang / hoher Energie
    "energy_brightness": True,   # Lautstärke beeinflusst Helligkeit
    "drop_instant":      True,   # Sofort voller Blinder beim ersten Drop-Beat

    # Blinder-Konfiguration
    "blinder_fixture_ids": [],   # leere Liste = alle Fixtures; sonst nur die gewählten
    "blinder_color":       "white",  # "white" | "palette" (aktuelle Palettenfarbe behalten)

    # Laser-Automatik
    "laser_auto":             True,    # Laser-Automation ein/aus
    "laser_random_pattern":   True,    # Muster wechseln on beat
    "laser_pattern_beats":    2,       # Muster-Wechsel-Intervall in Beats (0.5, 1, 2, 4, 8)
    "laser_color_sync":       True,    # Farbe an Palette koppeln
    "laser_speed_react":      True,    # Geschwindigkeit/Zoom reagiert auf Phase
    "laser_dmx_mode":         "dynamic",  # "static" | "dynamic"

    # Laser interner State
    "_laser_pattern":         100,     # aktueller Pattern-DMX-Wert (0-255)
    "_laser_beat_count":      0,
    "_laser_last_change":     0.0,     # Zeitstempel letzter Muster-Wechsel (für sub-beat Timing)

    # Interner State (kein UI-Binding)
    "_energy_level":      0.5,   # wird von audio_ticker aktualisiert
    "_prev_effect":       "none",
    "_effect_start":      0.0,
    "_prev_effect_start": 0.0,
    "_transition_start":  -1.0,
    "_transition_dur":    0.6,
    "_blinder_level":     0.0,
    "_blinder_beat_sub":  0,    # Zähler für blinder_every
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


def _palette_to_laser_color(r, g, b):
    """Mappt aktuelle RGB-Palettenfarbe auf nächsten Laser-Farbkanal-DMX-Wert."""
    # Dominante Farbe bestimmen
    if r >= g and r >= b and r > 0.3:
        if g > 0.4:   return 126  # Gelb (R+G)
        if b > 0.4:   return 198  # Magenta (R+B)
        return 18                  # Rot
    if g >= r and g >= b and g > 0.3:
        if b > 0.4:   return 162  # Cyan (G+B)
        return 54                  # Gruen
    if b >= r and b >= g and b > 0.3:
        return 90                  # Blau
    return 236                     # Weiss/Mix (Fallback)


def _apply_laser_fixtures(engine, phase, s, palette_r, palette_g, palette_b):
    """Wendet Laser-Automatik auf alle Fixtures mit laser_mode Kanal an."""
    if not s.get("laser_auto", True):
        return

    # Sub-Beat (0.5) Timing: alle ~0.3s (ca. halber Beat bei 120 BPM) Muster wechseln
    beat_interval = s.get("laser_pattern_beats", 2)
    if beat_interval == 0.5 and s.get("laser_random_pattern", True):
        now = time.time()
        last = s.get("_laser_last_change", 0.0)
        if (now - last) >= 0.3:   # ~120 BPM halber Beat
            s["_laser_pattern"]     = random.randint(0, 31) * 8 + 4
            s["_laser_last_change"] = now

    dmx_mode_val = 225 if s.get("laser_dmx_mode", "dynamic") == "dynamic" else 175

    # Phase → Speed / Zoom DMX-Werte
    if s.get("laser_speed_react", True):
        speed_map = {"BREAK": 30,  "BUILDUP": 140, "DROP": 210, "WAITING": 20}
        zoom_map  = {"BREAK": 40,  "BUILDUP": 130, "DROP": 200, "WAITING": 40}
        scan_speed = speed_map.get(phase, 140)
        zoom_val   = zoom_map.get(phase, 130)
    else:
        scan_speed = 128
        zoom_val   = 128

    color_val = (
        _palette_to_laser_color(palette_r, palette_g, palette_b)
        if s.get("laser_color_sync", True)
        else 128
    )

    pattern_val = int(s.get("_laser_pattern", 100))

    for fixture in engine.fixtures:
        if not fixture.has("laser_mode"):
            continue
        fixture.set("laser_mode",   dmx_mode_val / 255.0)
        fixture.set("pattern",      pattern_val  / 255.0)
        fixture.set("laser_color",  color_val    / 255.0)
        if fixture.has("speed"):       fixture.set("speed",       scan_speed / 255.0)
        if fixture.has("laser_speed"): fixture.set("laser_speed", scan_speed / 255.0)
        if fixture.has("zoom"):        fixture.set("zoom",        zoom_val   / 255.0)


def on_transient(phase="DROP"):
    """Wird bei erkanntem Synth/Transient-Spike aufgerufen (1-8 kHz)."""
    s = magic_auto_state
    if not s.get("synth_blinder", True):
        return
    if phase in ("BUILDUP", "DROP"):
        s["_blinder_level"] = min(1.0, s["blinder_strength"] * 0.65)


def on_beat(phase="DROP"):
    """Wird bei jedem erkannten Beat aufgerufen."""
    s = magic_auto_state

    # Blinder: nur in erlaubten Phasen und alle N Beats
    blinder_phases = s.get("blinder_phases", ["DROP"])
    if phase in blinder_phases:
        s["_blinder_beat_sub"] = s.get("_blinder_beat_sub", 0) + 1
        every = max(1, int(s.get("blinder_every", 1)))
        fire_blinder = (s["_blinder_beat_sub"] % every == 0)
    else:
        s["_blinder_beat_sub"] = 0
        fire_blinder = False

    # Drop Instant überschreibt: erster Beat beim Drop-Eintritt immer voll
    if s.get("drop_instant", True) and phase == "DROP" and s["_last_phase"] != "DROP":
        s["_blinder_level"] = 1.0
    elif fire_blinder:
        s["_blinder_level"] = min(1.0, s["blinder_strength"])
    # else: kein neuer Blinder — bestehender klingt ab

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

    # Laser Muster-Wechsel (vor _last_phase Update, damit drop_entrance korrekt)
    if s.get("laser_auto", True) and s.get("laser_random_pattern", True):
        beat_interval = s.get("laser_pattern_beats", 2)
        drop_entrance = (phase == "DROP" and s["_last_phase"] != "DROP")
        if drop_entrance:
            # Bei Drop-Eintritt sofort neues Muster
            s["_laser_pattern"]     = random.randint(0, 31) * 8 + 4
            s["_laser_beat_count"]  = 0
            s["_laser_last_change"] = time.time()
        elif beat_interval >= 1:
            # Ganzzahl-Beats: per Beat-Zähler
            s["_laser_beat_count"] = s.get("_laser_beat_count", 0) + 1
            if s["_laser_beat_count"] >= int(beat_interval):
                s["_laser_pattern"]     = random.randint(0, 31) * 8 + 4
                s["_laser_beat_count"]  = 0
                s["_laser_last_change"] = time.time()
        # 0.5-Beat Timing wird in _apply_laser_fixtures via Zeit-Check ausgelöst

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

    # Energy Brightness: Lautstärke skaliert die Helligkeit (0.3 – 1.0 Bereich)
    if s.get("energy_brightness", True):
        energy_mult = 0.3 + 0.7 * max(0.0, min(1.0, s.get("_energy_level", 0.5)))
        base_dim    = base_dim * energy_mult

    blinder_level    = s["_blinder_level"]
    blinder_ids      = s.get("blinder_fixture_ids", [])
    blinder_color    = s.get("blinder_color", "white")
    use_blinder_subs = len(blinder_ids) > 0  # True: nur gewählte Fixtures als Blinder

    for fixture in engine.fixtures:
        # Laser-Fixtures werden separat von _apply_laser_fixtures gesteuert
        if fixture.has("laser_mode") and s.get("laser_auto", True):
            continue

        is_blinder_fixture = (fixture.id in blinder_ids) if use_blinder_subs else True

        if is_blinder_fixture and blinder_level > 0.01:
            # Blinder-Modus: dieses Fixture übernehmen
            if blinder_color == "white":
                bl_r, bl_g, bl_b, bl_w = 0.0, 0.0, 0.0, 1.0
                # Falls kein White-Kanal: volles RGB-Weiß
                if not fixture.has("white"):
                    bl_r, bl_g, bl_b = 1.0, 1.0, 1.0
            else:
                bl_r, bl_g, bl_b, bl_w = r, g, b, w

            if fixture.has("dimmer"):
                fixture.set("dimmer", blinder_level)
                if fixture.has("red"):   fixture.set("red",   bl_r)
                if fixture.has("green"): fixture.set("green", bl_g)
                if fixture.has("blue"):  fixture.set("blue",  bl_b)
                if fixture.has("white"): fixture.set("white", bl_w)
            else:
                if fixture.has("red"):   fixture.set("red",   bl_r * blinder_level)
                if fixture.has("green"): fixture.set("green", bl_g * blinder_level)
                if fixture.has("blue"):  fixture.set("blue",  bl_b * blinder_level)
                if fixture.has("white"): fixture.set("white", bl_w * blinder_level)

            if fixture.has("strobe"): fixture.set("strobe", 0.0)
            continue

        # Normaler Effekt-Modus
        cur_val  = cur_func(fixture, cur_t, speed=effect_speed, width=5.0) if cur_func else 1.0
        prev_val = prev_func(fixture, prev_t, speed=effect_speed, width=5.0) if prev_func else 1.0

        if blend < 1.0:
            gen_val = prev_val * (1.0 - blend) + cur_val * blend
        else:
            gen_val = cur_val

        # Wenn dedizierte Blinder-Fixtures gewählt: andere Fixtures KEIN Blinder-Overlay
        extra_dim = blinder_level if not use_blinder_subs else 0.0
        dimmer    = min(1.0, base_dim * gen_val + extra_dim)

        if fixture.has("dimmer"):
            fixture.set("dimmer", dimmer)
            if fixture.has("red"):   fixture.set("red",   r)
            if fixture.has("green"): fixture.set("green", g)
            if fixture.has("blue"):  fixture.set("blue",  b)
            if fixture.has("white"): fixture.set("white", w)
        else:
            if fixture.has("red"):   fixture.set("red",   r * dimmer)
            if fixture.has("green"): fixture.set("green", g * dimmer)
            if fixture.has("blue"):  fixture.set("blue",  b * dimmer)
            if fixture.has("white"): fixture.set("white", w * dimmer)

        if fixture.has("strobe"):
            fixture.set("strobe", s["strobe_amount"])

    # Laser-Automatik (separate Fixtures mit laser_mode Kanal)
    _apply_laser_fixtures(engine, phase, s, r, g, b)
