import math
import time
import random

#Bühnengröße später dynamisch anpassbar machen

STAGE_WIDTH=1200.0
STAGE_HEIGHT=800.0


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


def gen_flash_decay(fixture, t, speed=1.0, width=5.0):
    """
    speed: Steuert das Aufblenden (Attack). Höher = schneller hell.
    width: Steuert das Ausblenden (Decay). Höher = schneller dunkel.
    """
    # 1. Attack-Phase (Aufblenden)
    # Wir berechnen die Dauer: Bei Speed 1.0 dauert es 0.1s, bei Speed 10.0 nur 0.01s.
    attack_duration = 0.1 / max(0.1, speed)
    
    if t < attack_duration:
        # Lineares Aufblenden von 0.0 auf 1.0
        return t / attack_duration
    
    # 2. Decay-Phase (Ausblenden/Nachleuchten)
    decay_time = t - attack_duration
    
    # Die Formel für das Ausglühen. 'width' steuert hier die Steilheit der Kurve.
    # val = e^(-zeit * steilheit)
    val = math.exp(-decay_time * width)
    
    return max(0.0, val)


def gen_vertical_wave(fixture, t, speed=1.0, width=5.0):
    """Welle von OBEN nach UNTEN. Sehr cool für die Säulen der Traverse."""
    norm_y = normalize(fixture.y, STAGE_HEIGHT)
    phase = norm_y * width
    return (math.sin(t * speed - phase) + 1) / 2

def gen_hard_chase(fixture, t, speed=1.0, width=5.0):
    """Wie linear_wave, aber ohne weiches Faden (Rechteck-Welle). Macht harte Ein/Aus Steps."""
    norm_x = normalize(fixture.x, STAGE_WIDTH)
    phase = norm_x * width
    val = math.sin(t * speed - phase)
    # Hard Cut: Wenn über 0, dann 100% an, sonst aus.
    return 1.0 if val > 0 else 0.0

def gen_scanner(fixture, t, speed=1.0, width=3.0):
    """Knight Rider / Cylon Scan. Ein Balken pendelt von links nach rechts und zurück."""
    # Oszillator der zwischen 0.0 und 1.0 pendelt
    scanner_pos = (math.sin(t * speed) + 1) / 2
    norm_x = normalize(fixture.x, STAGE_WIDTH)
    
    # Abstand der Lampe zum Scanner berechnen
    dist = abs(norm_x - scanner_pos)
    # Je kleiner width, desto breiter der Balken. Je größer width, desto schmaler.
    val = max(0.0, 1.0 - (dist * width))
    return val

def gen_breathing(fixture, t, speed=1.0, width=0.0):
    """Globaler Breathing Effekt. Alle Lampen faden exakt gleichzeitig weich ein und aus."""
    # Keine x/y Verschiebung (Phase), dadurch sind alle absolut synchron.
    return (math.sin(t * speed) + 1) / 2

def gen_heartbeat(fixture, t, speed=1.0, width=0.0):
    """Doppel-Pulsieren wie ein Herzschlag. Alle Lampen gleichzeitig."""
    # Taktzyklus auf 0.0 bis 1.0 normieren
    cycle = (t * speed) % 1.0
    
    # Erster kurzer Schlag
    if cycle < 0.15: 
        return math.sin(cycle * math.pi / 0.15)
    # Zweiter kurzer Schlag
    elif 0.3 < cycle < 0.45: 
        return math.sin((cycle - 0.3) * math.pi / 0.15)
    
    return 0.0

def gen_plasma(fixture, t, speed=1.0, width=5.0):
    """Organisches 2D-Fließen (ähnlich wie eine Lavalampe oder Wasser)."""
    nx = normalize(fixture.x, STAGE_WIDTH)
    ny = normalize(fixture.y, STAGE_HEIGHT)
    
    # Überlagerung von 3 verschiedenen Sinus-Wellen
    v1 = math.sin(nx * width + t * speed)
    v2 = math.sin(ny * width + t * speed * 1.3)
    v3 = math.sin((nx + ny) * width - t * speed * 0.8)
    
    # Durchschnitt bilden und auf 0-1 mappen
    return (v1 + v2 + v3 + 3) / 6

def gen_global_strobe(fixture, t, speed=10.0, width=0.5):
    """Hartes, synchrones Strobo. 'width' bestimmt wie lange das Licht im Takt AN ist (Duty Cycle)."""
    # Speed sollte hier hoch sein (z.B. 10.0 oder 20.0)
    cycle = (t * speed) % 1.0
    # Wenn width z.B. 0.5 ist, ist die Lampe 50% der Zeit an und 50% aus.
    return 1.0 if cycle < width else 0.0

def gen_flicker(fixture, t, speed=1.0, width=0.0):
    """Simuliert TV-Flimmern oder Feuer. Echtes, hochfrequentes Rauschen."""
    # Seed generieren, der sich ganz schnell ändert, aber für jede Lampe anders ist
    seed = fixture.x * 12.3 + fixture.y * 45.6 + int(t * speed * 15)
    random.seed(seed)
    # Gibt einen harten, zufälligen Wert zwischen 0.3 und 1.0 zurück
    return random.uniform(0.3, 1.0) if random.random() > 0.5 else 0.0

# --- MAPPING ---
# Diese Namen benutzt du in der JSON (events_default.json) unter "generator"

GENERATOR_MAP = {
    "linear_wave": gen_linear_wave,  # Links -> Rechts
    "center_sym": gen_center_sym,    # Mitte <-> Außen
    "gate_pulse": gen_gate_pulse,    # Oben-Mitte -> Überall hin
    "radar": gen_radar,              # Drehend
    "sparkle": gen_random_sparkle,    # Funkeln
    "flash_decay": gen_flash_decay,   # Blinder Hit

    "vertical_wave": gen_vertical_wave, # Oben -> Unten
    "hard_chase": gen_hard_chase,       # Linear, aber hartes Ein/Aus
    "scanner": gen_scanner,             # Pendeln wie Knight Rider
    "breathing": gen_breathing,         # Alle Lampen gleichzeitig weich ein/aus
    "heartbeat": gen_heartbeat,         # Alle Lampen gleichzeitig Doppel-Pulsieren
    "plasma": gen_plasma,               # Organisches 2D-Fließen
    "strobe": gen_global_strobe,        # Hartes, synchrones Strobo
    "flicker": gen_flicker,             # Echtes, hochfrequentes Rauschen
}