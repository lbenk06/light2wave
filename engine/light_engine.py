import profile
from engine.universe import Universe
from fixtures.fixture import Fixture
from fixtures.profiles import ALL_PROFILES


class LightEngine:
    def __init__(self):
        self.universe = Universe()
        self.fixtures = []
        self.profiles = ALL_PROFILES

    def add_fixture(self, fixture):
        self.fixtures.append(fixture)

    def render(self):
        self.universe.clear()
        for fixture in self.fixtures:
            fixture.render(self.universe.channels)
        return self.universe.channels

    def create_fixture(self, profile_id, x, y):
        """Erstellt ein neues Fixture an gegebener Position"""
        # Holt das Profil
        profile = self.get_profile(profile_id)

        # Berechne Startadresse (einfach sequenziell)
        address = self.next_free_address(profile)

        # Fixture erzeugen
        fixture = Fixture(
            fixture_id=f'Fixture {len(self.fixtures)+1}',
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
        # Annahme: self.profiles existiert
        return self.profiles[profile_id]

    def next_free_address(self, profile):
        """Berechnet die nächste freie DMX-Adresse"""
        used = sum(len(f.profile["channels"]) for f in self.fixtures)
        return used + 1  # +1 weil DMX 1-basiert
