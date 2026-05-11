import json
from fixtures.fixture import Fixture
from fixtures.profiles import ALL_PROFILES

def save_project(engine, filename, events=None, dmx_port=None):
    """
    Speichert das gesamte Projekt inkl. Traverses, Fixtures, Szenen, Events und DMX-Port.

    events / dmx_port werden bewusst beibehalten wenn sie nicht uebergeben werden —
    sonst loescht jeder Teil-Save (Fixture verschoben, Szene gespeichert, ...) die
    Events und den DMX-Port aus der Datei.
    """
    # Bestehende Werte aus Datei laden — werden nur ueberschrieben wenn explizit gesetzt
    existing_events = []
    existing_dmx_port = ""
    import os
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as fh:
                existing = json.load(fh)
            existing_events   = existing.get("events", [])
            existing_dmx_port = existing.get("dmx_port", "")
        except Exception:
            pass

    if events is not None:
        events_payload = [e.data for e in events]
    else:
        events_payload = existing_events

    if dmx_port is not None:
        dmx_port_payload = dmx_port
    else:
        dmx_port_payload = existing_dmx_port

    project_dict = {
        "traverses": [
            {"name": t.name, "x1": t.x1, "y1": t.y1, "x2": t.x2, "y2": t.y2, "snap_distance": t.snap_distance}
            for t in engine.traverses
        ],
        "fixtures": [],
        "banks": getattr(engine, "banks", []),
        "events": events_payload,
        "dmx_port": dmx_port_payload,
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
            x=float(f_data.get("x", 0.0)),
            y=float(f_data.get("y", 0.0))
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


def load_banks_from_json(bank_list_data, engine):
    """Lädt die Banks und Szenen aus der JSON"""
    if bank_list_data is None:
        bank_list_data = []
    engine.banks = bank_list_data
    print(f"{len(engine.banks)} Banks erfolgreich geladen.")


def load_events_from_project(event_list_data):
    """Erstellt Event-Objekte aus den im Projekt gespeicherten Rohdaten."""
    from engine.events import Event
    if not event_list_data:
        return []
    return [Event(e["name"], e) for e in event_list_data]


def list_projects(folder="projects"):
    """Gibt alle .json Projektdateien im projects-Ordner zurück (ohne user_profiles.json)."""
    import os
    if not os.path.exists(folder):
        return []
    return sorted([
        f for f in os.listdir(folder)
        if f.endswith(".json") and f != "user_profiles.json"
    ])