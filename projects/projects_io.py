import json
from fixtures.fixture import Fixture
from fixtures.profiles import ALL_PROFILES


def save_project(project_dict, filename):
    with open(filename, 'w') as f:
        json.dump(project_dict, f, indent=4)
    print(f"Projekt gespeichert: {filename}")

def load_project(filename):
    with open(filename, 'r') as f:
        project_dict = json.load(f)

    print(f"Projekt geladen: {filename}")
    return project_dict

def load_fixtures_from_json(fixture_list, engine):
    for f in fixture_list:
        profile=ALL_PROFILES[f["profile"]]
        fixture=Fixture(f["id"],profile,address=f["address"])
        engine.add_fixture(fixture)

def apply_scene(scene_dict, fixtures):
    for fixture in fixtures:
        if fixture.id in scene_dict:
            for role, value in scene_dict[fixture.id].items():
                fixture.set(role, value)