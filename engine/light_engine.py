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
        Berechnet die nächste freie DMX-Adresse.
        Summe aller belegten Kanäle + 1.
        """
        used = sum(len(f.profile["channels"]) for f in self.fixtures)
        return used + 1  # DMX ist 1-basiert
