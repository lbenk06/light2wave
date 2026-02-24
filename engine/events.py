import json
import time
from pathlib import Path
from engine.generators import GENERATOR_MAP

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

class Event:
    def __init__(self, name, data):
        self.name = name
        self.data = data
        
        self.type = data.get("type", "static")
        
        self.active = False
        self.start_time = 0

    def trigger(self, engine):
        """Schaltet das Event AN oder AUS (Toggle)"""
        if self.type=="stop_all":
            #alle laufenden Effekte stoppen
            for event in engine.active_overlays[:]:
                event.stop(engine)

            #blackout (alle lampen ausschalten)
            for fixture in engine.fixtures:
                if fixture.has("dimmer"):
                    fixture.set("dimmer", 0)
                #farben auch aus
                if fixture.has("red"): fixture.set("red", 0)
                if fixture.has("green"): fixture.set("green", 0)
                if fixture.has("blue"): fixture.set("blue", 0)
                if fixture.has("white"): fixture.set("white", 0)
                if fixture.has("strobe"): fixture.set("strobe", 0)
            return
        
        #blinderfall kein toggle
        if self.type=="flash":
            if self.active:
                self.stop(engine)
            self.start(engine)
            return
        

        #Normalfall (toggle)
        
        if self.active:
            self.stop(engine)
        else:
            self.start(engine)

    def start(self, engine):
        """Fügt das Event zur aktiven Liste der Engine hinzu"""
        if self not in engine.active_overlays:
            engine.active_overlays.append(self)
        
        self.active = True
        self.start_time = time.time()
        print(f"Event gestartet: {self.name}")

    def stop(self, engine):
        """Entfernt das Event aus der Engine"""
        if self in engine.active_overlays:
            engine.active_overlays.remove(self)
        
        self.active = False
        print(f"Event gestoppt: {self.name}")

    def update(self, engine):
        """
        Wird von der Engine in jedem Frame aufgerufen.
        Berechnet die neuen Werte für die Lampen.
        """
        if not self.active: return
        
        t = time.time() - self.start_time
        
        #statisch
        if self.type == "static":
            # Wir holen die Rollen aus 'roles' im data-Dictionary
            roles = self.data.get("roles", {})
            for fixture in engine.fixtures:
                for role, val in roles.items():
                    if fixture.has(role):
                        fixture.set(role, val)
        
        #dynamisch
        elif self.type == "dynamic" or self.type=="flash":
            
            params = self.data.get("params", {})
            gen_name = params.get("generator")

            #falls das event mit festen farben definiert ist, diese verwenden
            roles=self.data.get("roles", {})
            color_keys=["red", "green", "blue", "white"]

            #versucht das event eigene farben zu setzen?
            event_has_color=any(c in roles for c in color_keys)

            for fixture in engine.fixtures:
                #alte farben auswaschen
                #wenn das event eine farbe vorhibt, setzen wir sicherheitshalber erst alle farben auf 0
                if event_has_color:
                    for c in color_keys:
                        if fixture.has(c) and c != params.get("target_role"):
                            fixture.set(c, 0.0)
                #neue werte aus dem event setzen            
                for role, val in roles.items():
                    if fixture.has(role) and role!=params.get("target_role"):
                        fixture.set(role, val)
            
            
            
            
            # Generator Funktion aus der Map holen
            func = GENERATOR_MAP.get(gen_name)

            if func:
                target_role = params.get("target_role", "dimmer")
                speed = params.get("speed", 1.0)
                width = params.get("width", 5.0)

                # Nur Lampen holen, die diese Eigenschaft haben
                target_fixtures = [f for f in engine.fixtures if f.has(target_role)]

                max_val=0.0

                for fixture in target_fixtures:
                    # Hier übergeben wir das fixture-Objekt für x/y Koordinaten
                    val = func(fixture, t, speed=speed, width=width)
                    fixture.set(target_role, val)

                    if val>max_val:
                        max_val=val

                #auto stopp wenn der flash effekt durch ist (kein weiß clash mehr-->engine wieder frei für andere events)
                attack_duration = 0.1 / max(0.1, speed)
                if self.type=="flash" and t > attack_duration and max_val<0.01:
                    self.stop(engine)


def load_events_from_json(filename: str):
    path = DATA_DIR / filename
    try:
        with open(path, "r") as f:
            data = json.load(f)
        
        return [Event(e["name"], e) for e in data]
        
    except Exception as e:
        print(f"Fehler beim Laden der Events: {e}")
        return []