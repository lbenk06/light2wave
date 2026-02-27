from nicegui import ui
from gui.state import state
import json 
import os

# Pfad zur Datei für eigene Profile
PROFILE_FILE = "projects/user_profiles.json"

def save_custom_profile_to_disk(new_profile_data):
    """Speichert ein neues Profil in die JSON-Datei im projects-Ordner."""
    # Sicherstellen, dass der projects Ordner existiert
    if not os.path.exists("projects"):
        os.makedirs("projects")

    data = {}
    
    # 1. Bestehende Datei laden
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {}

    # 2. Neues Profil hinzufügen
    data[new_profile_data["profile_id"]] = new_profile_data

    # 3. Speichern
    try:
        with open(PROFILE_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        ui.notify(f"Fehler beim Speichern: {e}", color="red")


def create():
    # OBERER BEREICH: LIVE STEUERUNG
    
    # Header Zeile: Titel links, Refresh-Button rechts
    with ui.row().classes('w-full items-center justify-between mb-4'):
        ui.label('Geräte Steuerung').classes('text-h4')
        
        # HIER IST DER REFRESH BUTTON
        # Er ruft update_ui() auf, um die Slider neu zu laden
        def do_refresh():
            update_ui()
            ui.notify("Geräte aktualisiert", position='top', color='green', timeout=1000)
            
        ui.button('Refresh', on_click=do_refresh, icon='refresh').props('flat')

    # Container für die Slider-Karten (wird durch update_ui befüllt)
    fixtures_container = ui.row().classes('w-full wrap gap-4 items-start')

    def update_ui():
        """Löscht die alten Slider und baut sie basierend auf state.engine.fixtures neu."""
        fixtures_container.clear()

        # Fall 1: Keine Geräte da
        if not state.engine.fixtures:
            with fixtures_container:
                ui.label('Keine Geräte vorhanden. Gehe zum "Traverse" Tab.').classes('text-grey italic')
            return

        # Fall 2: Geräte vorhanden -> Karten bauen
        with fixtures_container:
            for fixture in state.engine.fixtures:
                
                # Karte für ein Gerät
                with ui.card().classes('w-full sm:w-[48%] md:w-80 p-3'):
                    
                    # Kopfzeile Karte: Name und Adresse
                    with ui.row().classes('w-full justify-between items-center mb-1'):
                        ui.label(fixture.id).classes('text-md font-bold')
                        ui.badge(f'Adr: {fixture.address}', color='grey-8').props('rounded')

                    ui.separator().classes('mb-2')

                    # Slider für jeden Kanal
                    for channel in fixture.profile["channels"]:
                        role = channel["role"]
                        if role == "unused": continue

                        # Farben für Slider bestimmen
                        c_map = {
                            'red': 'red', 'green': 'green', 'blue': 'blue', 
                            'white': 'grey-4', 'dimmer': 'orange', 'strobe': 'grey'
                        }
                        slider_color = c_map.get(role, 'primary')

                        # Slider UI (Label + Slider 0-255)
                        with ui.column().classes('w-full gap-0 mb-1'):
                            ui.label(role).classes('text-xs text-grey-6 uppercase font-bold tracking-wider')
                            
                            current_val_255 = int(fixture.get(role) * 255)
                            
                            ui.slider(
                                min=0, max=255, step=1,
                                value=current_val_255,
                                # Umrechnung 0-255 zurück auf 0.0-1.0 für die Engine
                                on_change=lambda e, f=fixture, r=role: f.set(r, e.value / 255.0)
                            ).props(f'color={slider_color} label').classes('w-full')

    # Beim ersten Laden der Seite einmal ausführen
    update_ui()

    ui.separator().classes('my-8')

    # UNTERER BEREICH: PROFIL EDITOR
    
    # Lokaler State für den Editor
    editor_state = {
        "name": "",
        "channels": [{"role": "dimmer"}] 
    }
    
    # Container für die Kanal-Zeilen
    channels_container = ui.column().classes('w-full gap-2')

    def refresh_editor():
        """Zeichnet die Liste der Kanäle im Editor neu"""
        channels_container.clear()
        
        with channels_container:
            for i, ch in enumerate(editor_state["channels"]):
                with ui.row().classes('w-full items-center gap-2'):
                    ui.label(f"CH {i+1}").classes('font-bold text-grey w-12')
                    
                    # Auswahl der Rolle
                    ui.select(
                        options=['dimmer', 'red', 'green', 'blue', 'white', 'strobe', 'pan', 'tilt', 'speed', 'unused'],
                        value=ch['role'],
                        on_change=lambda e, idx=i: update_channel_role(idx, e.value)
                    ).classes('w-40')
                    
                    # Löschen Button
                    ui.button(on_click=lambda _, idx=i: remove_channel(idx), icon='delete').props('flat round color=red dense')

    def update_channel_role(index, new_role):
        editor_state["channels"][index]["role"] = new_role

    def add_channel():
        editor_state["channels"].append({"role": "unused"})
        refresh_editor()

    def remove_channel(index):
        if len(editor_state["channels"]) > 0:
            editor_state["channels"].pop(index)
            refresh_editor()

    def save_new_profile():
        name = name_input.value.strip()
        if not name:
            ui.notify("Bitte einen Namen eingeben!", color="red")
            return
        
        if not editor_state["channels"]:
            ui.notify("Das Profil braucht mindestens einen Kanal!", color="red")
            return

        # ID generieren
        profile_id = name.lower().replace(" ", "_")
        
        # Prüfen ob ID schon vergeben (im RAM)
        if profile_id in state.engine.profiles:
            ui.notify(f"Profil-ID '{profile_id}' existiert schon!", color="orange")
            return

        # Profil Objekt erstellen
        new_profile = {
            "profile_id": profile_id,
            "name": name,
            "channels": []
        }
        
        for ch in editor_state["channels"]:
            new_profile["channels"].append({
                "name": ch["role"].capitalize(),
                "role": ch["role"]
            })

        # 1. In die Engine speichern (RAM)
        state.engine.profiles[profile_id] = new_profile

        # 2. Auf die Festplatte speichern (JSON)
        save_custom_profile_to_disk(new_profile)
        
        ui.notify(f"Profil '{name}' gespeichert!", color="green")
        
        # Editor zurücksetzen
        editor_state["name"] = ""
        name_input.value = ""
        editor_state["channels"] = [{"role": "dimmer"}]
        refresh_editor()

    # -- UI Element (Aufklappbar) --
    with ui.expansion('Neues Profil erstellen', icon='library_add').classes('w-full bg-grey-1 p-4 rounded shadow-sm'):
        
        with ui.column().classes('w-full max-w-2xl'):
            ui.label("Eigene Gerätedefinition anlegen").classes('text-grey-6 mb-2')
            
            # Name Input
            name_input = ui.input(label="Profil Name (z.B. 'Mein LED Bar')").classes('w-full mb-4')
            
            ui.label("Kanalbelegung:").classes('text-lg')
            
            # Kanal Liste rendern
            refresh_editor() 
            
            # Buttons
            with ui.row().classes('mt-4'):
                ui.button('Kanal +', on_click=add_channel, icon='add').props('outline')
                ui.button('Speichern', on_click=save_new_profile, icon='save').props('color=green')