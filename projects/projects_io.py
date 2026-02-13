import json
from fixtures.fixture import Fixture
from fixtures.profiles import ALL_PROFILES

def save_project(engine, filename):
    """
    Speichert das Projekt. 
    Wichtig: Wir speichern nur die ID des Profils, nicht das ganze Dictionary.
    """
    project_dict = {
        "traverses": [
            {"name": t.name, "x1": t.x1, "y1": t.y1, "x2": t.x2, "y2": t.y2, "snap_distance": t.snap_distance}
            for t in engine.traverses
        ],
        "fixtures": [],
        "banks":getattr(engine, "banks", [])  # Falls es noch keine gibt leer
    }

    for f in engine.fixtures:
        # Wir nutzen die profile_id, die wir im Fixture hinterlegt haben
        # oder holen sie aus dem Profile-Dict
        pid = getattr(f, "profile_id", f.profile.get("profile_id"))

        traverse_name = f.traverse.name if f.traverse else None
        snap_point_index = f.snap_point if f.snap_point is not None else None

        project_dict["fixtures"].append({
            "id": f.id,
            "profile": pid,  # Hier speichern wir z.B. "led_par_6ch"
            "x": f.x,
            "y": f.y,
            "address": f.address,
            "values": f.values,
            "traverse": traverse_name,
            "snap_point_index": snap_point_index
            
        })

    try:
        with open(filename, 'w') as f:
            json.dump(project_dict, f, indent=4)
        print(f"Projekt erfolgreich gespeichert: {filename}")
    except Exception as e:
        print(f"Fehler beim Speichern: {e}")


def load_project(filename):
    """
    Lädt nur die JSON-Daten, erstellt noch keine Objekte.
    """
    try:
        with open(filename, 'r') as f:
            project_dict = json.load(f)
        return project_dict
    except FileNotFoundError:
        print(f"Datei nicht gefunden: {filename}")
        return None
    except json.JSONDecodeError:
        print(f"Datei beschädigt: {filename}")
        return None


def load_fixtures_from_json(fixture_list_data, engine):
    """
    Erstellt Fixture-Objekte aus den geladenen Daten.
    WICHTIG: Nutzt engine.profiles statt ALL_PROFILES!
    """
    if isinstance(engine.fixtures, list):
        engine.fixtures.clear()

    count = 0
    for f_data in fixture_list_data:
        profile_id = f_data["profile"]
        profile_dict = engine.profiles.get(profile_id)
        if not profile_dict:
            print(f"Profil '{profile_id}' nicht gefunden! Gerät {f_data['id']} wird übersprungen.")
            continue

        # Fixture erstellen
        fixture = Fixture(
            fixture_id=f_data["id"],
            profile=profile_dict,
            address=f_data["address"],
            x=int(f_data.get("x", 0)),
            y=int(f_data.get("y", 0))
        )        

        if "values" in f_data:
            fixture.values = f_data["values"]

        # Traverses korrekt zuweisen
        traverse_name = f_data.get("traverse")
        snap_index = f_data.get("snap_point_index")

        if traverse_name is not None and snap_index is not None:
            t = next((tr for tr in engine.traverses if tr.name == traverse_name), None)
            if t and snap_index < len(t.snap_points):
                fixture.traverse = t
                fixture.snap_point = snap_index
                t.snap_points[snap_index]["occupied"] = True
                t.snap_points[snap_index]["fixture"] = fixture


        engine.add_fixture(fixture)
        count += 1
    
    print(f"{count} Geräte erfolgreich geladen.")