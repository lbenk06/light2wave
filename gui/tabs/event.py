from nicegui import ui
from gui.state import state
import json
from pathlib import Path
from engine.generators import GENERATOR_MAP
import sys
from engine.events import Event

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
EVENTS_FILE = DATA_DIR / "events_default.json"

def create():
    ui.label('EVENT EDITOR').classes('text-h4 text-white mb-6')

    # Editor für neue Events
    # Lokaler Speicher für die Formular-Eingaben
    form_data = {
        "name": "",
        "type": "dynamic",
        "generator": "linear_wave",
        "target_role": "dimmer",
        "speed": 2.0,
        "width": 5.0,
        "roles": {"red": 1.0, "green": 0.0, "blue": 0.0, "white": 0.0, "dimmer": 1.0}
    }

    with ui.card().classes('w-full max-w-4xl bg-gray-900 border border-gray-700 p-6 mb-8'):
        ui.label('Neues Event erstellen').classes('text-xl font-bold text-gray-200 mb-4')
        
        with ui.row().classes('w-full gap-8 items-start'):
            
            # Linke Spalte Grundeinstellungen und optional Farben (in welcher Farbe soll der Effekt leuchten wenn er aktiv ist? wenn keine angegeben wird, dann werden die über den geräte tab eingestellten verwendet)
            with ui.column().classes('w-5/12 gap-4'):
                ui.input(label='Event Name').bind_value(form_data, 'name').props('dark color=cyan').classes('w-full')
                
                ui.select(
                    options=['dynamic', 'static', 'flash', 'stop_all'],
                    label='Event Typ'
                ).bind_value(form_data, 'type').props('dark color=cyan').classes('w-full')

                ui.separator().classes('bg-gray-700')
                
                # fixe farben für den Effekt (optional)
                ui.label('Feste Farben (Optional)').classes('text-sm font-bold text-gray-400')
                ui.label('Wenn der Effekt immer eine bestimmte Farbe haben soll.').classes('text-xs text-gray-500 -mt-3')
                
                with ui.row().classes('gap-2'):
                    ui.number(label='R', min=0, max=1, step=0.1, format='%.1f').bind_value(form_data["roles"], 'red').props('dark color=red filled').classes('w-16')
                    ui.number(label='G', min=0, max=1, step=0.1, format='%.1f').bind_value(form_data["roles"], 'green').props('dark color=green filled').classes('w-16')
                    ui.number(label='B', min=0, max=1, step=0.1, format='%.1f').bind_value(form_data["roles"], 'blue').props('dark color=blue filled').classes('w-16')
                    ui.number(label='W', min=0, max=1, step=0.1, format='%.1f').bind_value(form_data["roles"], 'white').props('dark color=grey filled').classes('w-16')



            # Rechte Spalte: dynamische Parameter (für flash und dynamische events)
            with ui.column().classes('w-5/12 gap-4').bind_visibility_from(form_data, 'type', lambda t: t in ['dynamic', 'flash']):
                ui.label('Effekt Parameter').classes('text-sm font-bold text-gray-400')
                
                # Generator-Wahl
                ui.select(options=list(GENERATOR_MAP.keys()), label='Muster').bind_value(form_data, 'generator').props('dark color=purple')
                
                # Dynamische Labels je nach Typ
                with ui.column().classes('w-full'):
                    # Wenn Dynamic: Geschwindigkeit,  Wenn Flash: Aufblend-Zeit (Attack)
                    ui.label().bind_text_from(form_data, 'type', backward=lambda t: 'Aufblend-Tempo (Attack)' if t == 'flash' else 'Geschwindigkeit (Speed)').classes('text-xs text-gray-500')
                    ui.slider(min=0.1, max=15.0, step=0.1).bind_value(form_data, 'speed').props('dark color=purple label-always')

                    # Wenn Dynamic: Breite/Phase, Wenn Flash: Nachleucht-Dauer (Decay)
                    ui.label().bind_text_from(form_data, 'type', backward=lambda t: 'Nachleucht-Dauer (Decay)' if t == 'flash' else 'Breite / Phase (Width)').classes('text-xs text-gray-500')
                    ui.slider(min=0.1, max=15.0, step=0.1).bind_value(form_data, 'width').props('dark color=purple label-always')
                        

        
        # Speicher button
        ui.separator().classes('my-6 bg-gray-700')
        with ui.row().classes('w-full justify-end'):
            
            def save_event():
                name = form_data["name"].strip()
                if not name:
                    ui.notify('Bitte einen Namen eingeben!', color='red')
                    return
                
                # Datenstruktur aufbauen
                new_event_data = {
                    "name": name,
                    "type": form_data["type"],
                    "roles": {k: v for k, v in form_data["roles"].items() if v > 0} 
                }
                
                if form_data["type"] in ["dynamic", "flash"]:
                    new_event_data["params"] = {
                        "generator": form_data["generator"],
                        "target_role": form_data["target_role"],
                        "speed": float(form_data["speed"]),
                        "width": float(form_data["width"])
                    }
                
                # JSON Speichern
                try:
                    all_events = []
                    if EVENTS_FILE.exists():
                        with open(EVENTS_FILE, "r") as f:
                            all_events = json.load(f)
                        
                    #Überschreiben wenn Name schnon existier
                    existing_index=next((i for i, e in enumerate(all_events) if e["name"] == name), None)
                    if existing_index is not None:
                        all_events[existing_index]=new_event_data
                    else:
                        all_events.append(new_event_data)
                    
                    with open(EVENTS_FILE, "w") as f:
                        json.dump(all_events, f, indent=4)
                        
                except Exception as e:
                    ui.notify(f'Fehler beim Speichern: {e}', color='red')
                    return
                
                # Live in die Engine laden
                new_event_obj = Event(name, new_event_data)

                #Auch im live State überschreiben
                state_idx=next((i for i, e in enumerate(state.events) if e.name == name), None)
                if state_idx is not None:
                    #altes Event stoppen falls es aktiv ist
                    if state.events[state_idx].active:
                        state.events[state_idx].stop(state.engine)
                    state.events[state_idx]=new_event_obj
                else:
                    state.events.append(new_event_obj)

                
                ui.notify(f'Event "{name}" gespeichert!', color='green')
                form_data["name"] = ""
                render_existing_events()

            ui.button('EVENT SPEICHERN', on_click=save_event, icon='save').props('push color=green')


    # Hilfsfunktionen
    def delete_event(event_name):
        #aus der engine löschen
        event_to_remove=next((e for e in state.events if e.name == event_name), None)
        if event_to_remove and event_to_remove.active:
            event_to_remove.stop(state.engine)
        state.events= [e for e in state.events if e.name != event_name]

        #aus der json löschen
        if EVENTS_FILE.exists():
            with open(EVENTS_FILE, "r") as f:
                all_events=json.load(f)
            updated_events=[e for e in all_events if e.get("name") != event_name]
            with open(EVENTS_FILE, "w") as f:
                json.dump(updated_events, f, indent=4)
        
        ui.notify(f'Event "{event_name}" gelöscht!', color='orange')
        render_existing_events()

    def edit_event(ev_obj):
        form_data["name"] = ev_obj.name
        form_data["type"] = ev_obj.type

        #farben zurücksetzen und neu laden
        for c in ["red", "green", "blue", "white", "dimmer"]:
            form_data["roles"][c] = 0.0
        roles = ev_obj.data.get("roles", {})

        for color, val in roles.items():
            if color in form_data["roles"]:
                form_data["roles"][color] = val
        
        #params laden
        params=ev_obj.data.get("params", {})
        if params:
            form_data["generator"] = params.get("generator", "linear_wave")
            form_data["target_role"] = params.get("target_role", "dimmer")
            form_data["speed"] = params.get("speed", 1.0)
            form_data["width"] = params.get("width", 5.0)

        ui.notify(f'"{ev_obj.name}" in den Editor geladen', color='info')
        ui.run_javascript('window.scrollTo(0, 0)') # Scrollt nach oben zum Editor


    # liste der bestehenden events
    ui.label('Aktuelle Events').classes('text-xl font-bold text-gray-200 mb-4')
    
    events_container = ui.row().classes('w-full gap-4 wrap')

    def render_existing_events():
        events_container.clear()
        with events_container:
            for ev in state.events:
                with ui.card().classes('w-64 bg-gray-800 border border-gray-600 p-3'):
                    
                    # kopfzeile mit Name und Edit/Delete Buttons
                    with ui.row().classes('w-full justify-between items-center mb-2'):
                        ui.label(ev.name).classes('font-bold text-gray-200 truncate w-32').tooltip(ev.name)
                        
                        with ui.row().classes('gap-1'):
                            ui.button(icon='edit', on_click=lambda _, e=ev: edit_event(e)).props('flat round dense color=info').tooltip('Bearbeiten')
                            
                            # Löschen mit Sicherheitsabfrage
                            async def confirm_delete(e_name=ev.name):
                                with ui.dialog() as dialog, ui.card():
                                    ui.label(f'"{e_name}" wirklich löschen?')
                                    with ui.row():
                                        ui.button('Ja', on_click=lambda: (delete_event(e_name), dialog.close())).props('color=red')
                                        ui.button('Abbrechen', on_click=dialog.close).props('outline')
                                dialog.open()
                                
                            ui.button(icon='delete', on_click=confirm_delete).props('flat round dense color=red').tooltip('Löschen')

                    # Event Typ und Parameter anzeigen
                    color = 'purple' if ev.type == 'dynamic' else 'blue'
                    if ev.type == 'flash': color = 'white text-black'
                    if ev.type == 'stop_all': color = 'red'
                    ui.badge(ev.type, color=color)

                    if ev.type in ['dynamic', 'flash']:
                        gen = ev.data.get("params", {}).get("generator", "-")
                        ui.label(f'Gen: {gen}').classes('text-xs text-gray-400 font-mono mt-1')
                        
                        speed = ev.data.get("params", {}).get("speed", "-")
                        ui.label(f'Speed: {speed}').classes('text-xs text-gray-400 font-mono')
                        
                        tr = ev.data.get("params", {}).get("target_role", "-")
                        ui.label(f'Target: {tr}').classes('text-xs text-gray-500 font-mono')

    render_existing_events()