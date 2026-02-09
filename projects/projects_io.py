import json
from fixtures.fixture import Fixture
from fixtures.profiles import ALL_PROFILES

def save_project(engine, filename):
    """
    Speichert das Projekt. 
    Wichtig: Wir speichern nur die ID des Profils, nicht das ganze Dictionary.
    """
    project_dict = {
        "fixtures": []
    }

    for f in engine.fixtures:
        # Wir nutzen die profile_id, die wir im Fixture hinterlegt haben
        # oder holen sie aus dem Profile-Dict
        pid = getattr(f, "profile_id", f.profile.get("profile_id"))

        project_dict["fixtures"].append({
            "id": f.id,
            "profile": pid,  # Hier speichern wir z.B. "led_par_6ch"
            "x": f.x,
            "y": f.y,
            "address": f.address,
            "values": f.values
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
        
        # --- HIER WAR DER FEHLER ---
        # Wir suchen jetzt in engine.profiles (da sind Standard UND User Profile drin)
        if profile_id in engine.profiles:
            profile_dict = engine.profiles[profile_id]
        else:
            # Fallback: Vielleicht ist es doch ein Standard-Profil, das noch nicht geladen wurde?
            # Aber eigentlich sollte engine.profiles alles haben.
            print(f"ACHTUNG: Profil '{profile_id}' nicht in der Engine gefunden! Gerät {f_data['id']} wird übersprungen.")
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

        engine.add_fixture(fixture)
        count += 1
    
    print(f"{count} Geräte erfolgreich geladen.")