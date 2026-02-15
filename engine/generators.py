import math
import time
import random

#Bühnengröße später dynamisch anpassbar machen

STAGE_WIDTH=1200.0
STAGE_DEPTH=800.0


#Mitte der Front Traverse
CENTER_X=STAGE_WIDTH/2


#Höhe der Front Traverse
TOP_TRUSS_Y=200.0


#Hilfsfunktionen

def normalize(val, max_val):
    """Rechnet Pixel-Koordinaten in 0.0 bis 1.0 um."""
    if max_val == 0: return 0
    return val / max_val

def get_dist(x1, y1, x2, y2):
    """Abstand zwischen zwei Punkten (Pythagoras)."""
    return math.sqrt((x1-x2)**2 + (y1-y2)**2)

#generatoren

def gen_linear_wave(fixture, t, speed=1.0, width=5.0):
    """
    Klassische Welle von LINKS nach RECHTS.
    Gut für Farbverläufe über das ganze Rig.
    """
    # X-Position normieren (0.0 = Links, 1.0 = Rechts)
    norm_x = normalize(fixture.x, STAGE_WIDTH)
    
    # Phase verschiebt sich basierend auf X
    phase = norm_x * width
    
    # Sinus (-1 bis 1) auf (0 bis 1) mappen
    val = (math.sin(t * speed - phase) + 1) / 2
    return val


def gen_center_sym(fixture, t, speed=1.0, width=5.0):
    """
    Symmetrisch von der MITTE (X=600) nach außen.
    Links und Rechts machen das Gleiche (gespiegelt).
    """
    # Abstand zur Mitte berechnen (in Pixeln)
    dist_pixel = abs(fixture.x - CENTER_X)
    
    # Normieren auf halbe Bühnenbreite (600px)
    dist_norm = dist_pixel / (STAGE_WIDTH / 2)
    
    phase = dist_norm * width
    val = (math.sin(t * speed - phase) + 1) / 2
    return val


def gen_gate_pulse(fixture, t, speed=1.0, width=5.0):
    """
    EXPLOSION: Startet exakt in der Mitte der oberen Traverse (Punkt 600, 200).
    Läuft gleichzeitig nach links/rechts und die Säulen runter.
    PERFEKT für deine Tor-Traverse.
    """
    # Abstand zum "Herz" der Traverse berechnen
    dist_pixel = get_dist(fixture.x, fixture.y, CENTER_X, TOP_TRUSS_Y)
    
    # Normieren (Wir nehmen ca. 600px als maximalen Weg an)
    dist_norm = dist_pixel / 600.0
    
    # Welle erzeugen
    phase = dist_norm * width
    val = (math.sin(t * speed - phase) + 1) / 2
    return val


def gen_radar(fixture, t, speed=1.0, width=1.0):
    """
    Dreht sich wie ein Uhrzeiger um die Mitte (600, 400).
    """
    # Mitte der Bühne (nicht der Traverse) für Rotation
    cx, cy = STAGE_WIDTH / 2, STAGE_HEIGHT / 2
    
    dx = fixture.x - cx
    dy = fixture.y - cy
    
    # Winkel der Lampe (-PI bis +PI)
    angle = math.atan2(dy, dx)
    
    # Rotierender Sweep-Winkel
    sweep = (t * speed) % (2 * math.pi)
    # Mapping auf -PI bis +PI
    if sweep > math.pi: sweep -= 2*math.pi
    
    # Abstand im Winkel berechnen
    diff = abs(angle - sweep)
    # Korrektur beim Sprung von PI auf -PI
    if diff > math.pi: diff = 2*math.pi - diff
    
    # Helligkeit basierend auf Winkelabstand
    val = max(0, 1.0 - (diff * width))
    return val


def gen_random_sparkle(fixture, t, speed=1.0, width=0.0):
    """
    Zufälliges Funkeln / Strobo-Effekt.
    Jede Lampe hat ihren eigenen 'Random' basierend auf ihrer ID/Position.
    """
    # Wir nutzen x+y als "Seed", damit es deterministisch bleibt aber wild aussieht
    seed = fixture.x + fixture.y
    
    # Schneller Sinus mit unterschiedlichen Frequenzen
    val = (math.sin(t * speed * 5 + seed) + 1) / 2
    
    # Hard Cut für Strobo-Look (alles über 0.8 ist AN, rest AUS)
    if val > 0.8: return 1.0
    return 0.0


def gen_flash_decay(fixture, t, speed=1.0, width=0.0):
    """
    Simuliert einen Blinder-Schlag (Hit).
    - Attack: Geht extrem schnell an (0.05s).
    - Decay: Glüht langsam aus (exponentiell).
    """
    # 1. Attack Phase (0 bis 0.05 Sekunden) -> Schnell hochfahren
    attack_time = 0.05
    if t < attack_time:
        # Lineares Fade-In von 0 auf 1
        return t / attack_time
    
    # 2. Decay Phase (Ab 0.05 Sekunden) -> Langsam ausglühen
    decay_time = t - attack_time
    
    # Formel: e^(-t * speed)
    # Je kleiner 'speed', desto länger glüht es nach.
    val = math.exp(-decay_time * speed)
    
    # Nichts Negatives zurückgeben
    return max(0.0, val)


# --- MAPPING ---
# Diese Namen benutzt du in der JSON (events_default.json) unter "generator"

GENERATOR_MAP = {
    "linear_wave": gen_linear_wave,  # Links -> Rechts
    "center_sym": gen_center_sym,    # Mitte <-> Außen
    "gate_pulse": gen_gate_pulse,    # Oben-Mitte -> Überall hin
    "radar": gen_radar,              # Drehend
    "sparkle": gen_random_sparkle,    # Funkeln
    "flash_decay": gen_flash_decay   # Blinder Hit
}