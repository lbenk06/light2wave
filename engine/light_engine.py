from engine.universe import Universe
from fixtures.fixture import Fixture
from fixtures.profiles import ALL_PROFILES
import os
import json


class LightEngine:
    def __init__(self):
        self.universe = Universe()
        self.fixtures = []
        self.traverses = []
        self.profiles = ALL_PROFILES.copy()

        self.banks=[] #wird von projects_io geladen
        self.active_overlays=[] #laufende Events

        self.master_dimmer = 1.0  # 0.0 = Blackout, 1.0 = volle Helligkeit

        self.parked_fixtures: set = set()          # Indices der geparkten Fixtures
        self.parked_values: dict = {}              # fixture_idx -> liste von Kanalwerten

        self.load_user_profiles()

        #inteface
        self.dmx_controller=None


    def load_user_profiles(self):
        """Lädt eigene Profile aus der JSON-Datei"""
        filename = "projects/user_profiles.json"
        
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    custom_profiles = json.load(f)
                    # Wir fügen die Custom-Profile zu den Standard-Profilen hinzu
                    self.profiles.update(custom_profiles)
                    print(f"{len(custom_profiles)} eigene Profile geladen.")
            except Exception as e:
                print(f"Fehler beim Laden der User-Profile: {e}")

    def park_fixture(self, fixture_idx: int):
        """Friert Fixture ein — aktuelle Kanalwerte werden fixiert, Effekte ignoriert"""
        if fixture_idx >= len(self.fixtures):
            return
        fix = self.fixtures[fixture_idx]
        start = fix.address - 1
        n = len(fix.profile["channels"])
        self.parked_values[fixture_idx] = list(self.universe.channels[start:start + n])
        self.parked_fixtures.add(fixture_idx)

    def unpark_fixture(self, fixture_idx: int):
        """Gibt Fixture wieder frei — Effekte wirken wieder"""
        self.parked_fixtures.discard(fixture_idx)
        self.parked_values.pop(fixture_idx, None)

    def set_parked_color(self, fixture_idx: int, **role_values):
        """Setzt einzelne Kanalwerte für ein geparktes Fixture (z.B. red=1.0, white=0.5)"""
        if fixture_idx not in self.parked_fixtures:
            return
        fix = self.fixtures[fixture_idx]
        ch_roles = [ch["role"] for ch in fix.profile["channels"]]
        vals = list(self.parked_values.get(fixture_idx, [0] * len(ch_roles)))
        for role, val in role_values.items():
            if role in ch_roles:
                i = ch_roles.index(role)
                vals[i] = int(max(0.0, min(1.0, val)) * 255)
        self.parked_values[fixture_idx] = vals

    def add_fixture(self, fixture: Fixture):
        """Fügt ein Fixture zur Engine hinzu"""
        self.fixtures.append(fixture)

    def render(self):
        """Rendert alle Fixtures und Events ins Universe"""
        #1. Events
        for event in self.active_overlays[:]:
            event.update(self)

        #2. Fixtures
        self.universe.clear()
        for fixture in self.fixtures:
            fixture.render(self.universe.channels)

        #3. Geparkte Fixtures: überschreiben Effekte mit eingefrorenen Werten
        for idx in self.parked_fixtures:
            if idx < len(self.fixtures):
                fix = self.fixtures[idx]
                start = fix.address - 1
                values = self.parked_values.get(idx, [])
                for i, v in enumerate(values):
                    if start + i < 512:
                        self.universe.channels[start + i] = v

        #4. Master Dimmer: skaliert alle Kanalwerte am Ende
        if self.master_dimmer < 1.0:
            m = max(0.0, self.master_dimmer)
            for i in range(512):
                self.universe.channels[i] = int(self.universe.channels[i] * m)

        return self.universe.channels

    def create_fixture(self, profile_id, x=0, y=0, fixture_id=None, address=None):
        """
        Erstellt ein neues Fixture.
        Wenn fixture_id oder address None sind, werden automatisch generiert.
        """
        profile = self.get_profile(profile_id)

        # Adresse automatisch, falls nicht angegeben
        if address is None:
            address = self.next_free_address(profile)

        # Name automatisch, falls nicht angegeben
        if fixture_id is None:
            fixture_id = f'{profile_id}_{len(self.fixtures)+1}'

        # Fixture erstellen
        fixture = Fixture(
            fixture_id=fixture_id,
            profile=profile,
            address=address,
            x=x,
            y=y
        )

        # In Engine registrieren
        self.add_fixture(fixture)
        return fixture

    def get_profile(self, profile_id):
        """Holt ein Profil anhand der ID"""
        return self.profiles[profile_id]

    def next_free_address(self, profile):
        """
        Berechnet die nächste absolut sichere, freie DMX-Adresse.
        Sucht den höchsten belegten Kanal im gesamten Universum und setzt +1.
        """
        if not self.fixtures:
            return 1  # Wenn noch keine Lampen da sind, starte bei 1
            
        highest_occupied_channel = 0
        
        for f in self.fixtures:
            # Der letzte belegte Kanal dieser Lampe = Startadresse + Anzahl der Kanäle - 1
            last_channel = f.address + len(f.profile["channels"]) - 1
            
            if last_channel > highest_occupied_channel:
                highest_occupied_channel = last_channel
                
        return highest_occupied_channel + 1



    def connect_dmx(self, port):
        """Verbindet die Engine mit unserem Enttec Pro DMX INterface"""
        from DMXEnttecPro import DMXEnttecPro
        try:
            self.dmx_controller=Controller(port)
            print(f"DMX-Interface an {port} verbunden.")

        except Exception as e:
            print(f"DMX Fehler: {e}")
            return False