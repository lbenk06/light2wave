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