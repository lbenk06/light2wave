import json
from fixtures.fixture import Fixture
from fixtures.profiles import ALL_PROFILES


def save_project(engine, filename):
    """
    Speichert das aktuelle Projekt inkl. aller Fixtures, Positionen,
    Startadressen, Namen und aktuellen Kanalwerten.
    """
    project_dict = {
        "fixtures": []
    }

    for f in engine.fixtures:
        project_dict["fixtures"].append({
            "id": f.id,
            "profile": f.profile["profile_id"],
            "x": f.x,
            "y": f.y,
            "address": f.address,
            "values": f.values
        })

    with open(filename, 'w') as f:
        json.dump(project_dict, f, indent=4)
    print(f"Projekt gespeichert: {filename}")


def load_project(filename):
    """
    Lädt ein Projekt aus JSON-Datei und gibt das Dictionary zurück.
    """
    with open(filename, 'r') as f:
        project_dict = json.load(f)

    print(f"Projekt geladen: {filename}")
    return project_dict


def load_fixtures_from_json(fixture_list, engine):
    """
    Lädt die Fixtures aus einem JSON-Projekt in die Engine.
    Stellt Position, Startadresse, Werte und Profil wieder her.
    """
    for f in fixture_list:
        profile = ALL_PROFILES[f["profile"]]

        fixture = Fixture(
            fixture_id=f["id"],
            profile=profile,
            address=f["address"],
            x=f.get("x", 0),
            y=f.get("y", 0)
        )

        # Werte wiederherstellen (Dimmer/Farbe)
        if "values" in f:
            for role, val in f["values"].items():
                fixture.set(role, val)

        engine.add_fixture(fixture)


def apply_scene(scene_dict, fixtures):
    """
    Wendet die Werte einer Szene auf alle Fixtures an.
    """
    for fixture in fixtures:
        if fixture.id in scene_dict:
            for role, value in scene_dict[fixture.id].items():
                fixture.set(role, value)
