from nicegui import ui
from gui.state import state

def create():
    # Initialisieren
    if not hasattr(state.engine, 'banks'):
        state.engine.banks = []
    
    # Lokaler State für die aktuelle Bank (Index)
    current_bank_index = 0 if state.engine.banks else -1

    # Container-Referenzen
    refs = {
        "bank_tabs": None,      # Die Tabs oben
        "scene_grid": None,     # Die Buttons unten
    }

    # Logik Funktionen

    def refresh_ui():
        """Zeichnet alles neu"""
        refs["bank_tabs"].clear()
        refs["scene_grid"].clear()
        
        draw_programming_area()
        draw_playback_area()

    def add_bank():
        nonlocal current_bank_index 
        
        if not inp_bank_name.value:
            ui.notify("Bitte Bank-Namen eingeben", color="orange")
            return
        
        new_bank = {"name": inp_bank_name.value, "scenes": []}
        state.engine.banks.append(new_bank)
        current_bank_index = len(state.engine.banks) - 1
        
        inp_bank_name.value = ""
        refresh_ui()
        ui.notify(f"Bank '{new_bank['name']}' erstellt")

    def delete_current_bank():
        nonlocal current_bank_index 

        if current_bank_index == -1: return
        
        deleted_name = state.engine.banks[current_bank_index]["name"]
        state.engine.banks.pop(current_bank_index)
        current_bank_index = 0 if state.engine.banks else -1
        
        refresh_ui()
        ui.notify(f"Bank '{deleted_name}' gelöscht", color="red")

    def select_bank(e):
        nonlocal current_bank_index 
        current_bank_index = e.value 
        refs["scene_grid"].clear()
        draw_playback_area()

    def save_scene():
        if current_bank_index == -1:
            ui.notify("Erst eine Bank erstellen!", color="red")
            return
        if not inp_scene_name.value:
            ui.notify("Szenen-Namen eingeben!", color="orange")
            return

        # SNAPSHOT LOGIK
        scene_data = {}
        for fixture in state.engine.fixtures:
            # WICHTIG: .copy(), damit wir die Werte einfrieren!
            scene_data[fixture.id] = fixture.values.copy()

        new_scene = {
            "name": inp_scene_name.value,
            "data": scene_data
        }

        state.engine.banks[current_bank_index]["scenes"].append(new_scene)
        inp_scene_name.value = ""
        
        refs["scene_grid"].clear()
        draw_playback_area()
        ui.notify("Szene gespeichert!", color="green")

    def load_scene(scene):
        """Feuert die Szene ab"""
        data = scene["data"]
        for fixture in state.engine.fixtures:
            if fixture.id in data:
                saved_values = data[fixture.id]
                
                # Neues Format (Dictionary)
                if isinstance(saved_values, dict):
                    for role, val in saved_values.items():
                        fixture.set(role, val)
                
                # Fallback mit altem Format (RGB-Tupel) - wird in neuen Szenen nicht mehr gespeichert, aber alte Szenen bleiben so kompatibel
                elif isinstance(saved_values, (list, tuple)):
                    if hasattr(fixture, 'set_color'):
                        fixture.set_color(saved_values[0], saved_values[1], saved_values[2])

    def delete_scene(scene):
        if current_bank_index == -1: return
        bank = state.engine.banks[current_bank_index]
        
        if scene in bank["scenes"]:
            bank["scenes"].remove(scene)
            # UI neu zeichnen
            refs["scene_grid"].clear()
            draw_playback_area()
            ui.notify("Szene gelöscht", color="red")


    # UI Layout

    # oben Programmier Modus zum Banken erstellen und Szenen speichern
    with ui.card().classes('w-full mb-4 bg-gray-800 border border-gray-600'):
        ui.label('PROGRAMMIER MODUS').classes('text-xs font-bold text-gray-400 mb-2')
        
        with ui.row().classes('w-full gap-8 items-start'):
            
            # SPALTE A: Bank Verwaltung
            with ui.column().classes('gap-2'):
                ui.label('1. Banken').classes('font-bold text-white')
                with ui.row():
                    inp_bank_name = ui.input('Name').props('dense dark placeholder="Bank Name"')
                    ui.button(icon='add', on_click=add_bank).props('dense round color=green')
                
                ui.button('Bank löschen', on_click=delete_current_bank).props('flat dense color=red size=sm')

            # SPALTE B: Szenen Speichern
            with ui.column().classes('gap-2'):
                ui.label('2. Look speichern').classes('font-bold text-white')
                with ui.row():
                    inp_scene_name = ui.input('Name').props('dense dark placeholder="Szenen Name"')
                    ui.button('SPEICHERN', on_click=save_scene).props('dense color=blue icon=save')

        # Die Bank-Tabs
        ui.separator().classes('my-2 bg-gray-600')
        refs["bank_tabs"] = ui.tabs().classes('w-full text-left text-white').props('active-color=cyan indicator-color=cyan dense')
        refs["bank_tabs"].on_value_change(select_bank)


    # unten Live PLayback mit Szenen Auswahl
    ui.label('LIVE PLAYBACK').classes('text-xl font-bold mt-4 mb-2 text-white')
    refs["scene_grid"] = ui.row().classes('w-full gap-4 wrap')


    # Funktionen zum Zeichnen der Bereiche
    def draw_programming_area():
        with refs["bank_tabs"]:
            if not state.engine.banks:
                ui.tab(name=-1, label='Keine Banken')
                return

            for i, bank in enumerate(state.engine.banks):
                ui.tab(name=i, label=bank["name"])
            
            if current_bank_index != -1:
                refs["bank_tabs"].value = current_bank_index

    def draw_playback_area():
        with refs["scene_grid"]:
            if current_bank_index == -1 or not state.engine.banks:
                ui.label('Keine Bank ausgewählt.').classes('text-gray-500 italic')
                return

            bank = state.engine.banks[current_bank_index]
            
            if not bank["scenes"]:
                ui.label(f"Bank '{bank['name']}' ist leer.").classes('text-gray-500')
                return

            #Für jede Szene eine Karte zeichnen
            for scene in bank["scenes"]:
                
                #Karte erscheint in der Farbe der ersten Lampe der Szene (wenn vorhanden) als Vorschau, sonst grau
                preview_color = "#333"
                if scene["data"]:
                    vals = list(scene["data"].values())[0]
                    r, g, b = 0, 0, 0
                    if isinstance(vals, dict):
                        dim = vals.get("dimmer", 1.0)
                        r = int(vals.get("red", 0) * dim * 255)
                        g = int(vals.get("green", 0) * dim * 255)
                        b = int(vals.get("blue", 0) * dim * 255)
                    elif isinstance(vals, (list, tuple)):
                        r, g, b = vals[0], vals[1], vals[2]
                    preview_color = f"rgb({r}, {g}, {b})"

                #Szenenkarte mit Klickfunktionen
                with ui.card().classes('w-40 h-32 relative cursor-pointer hover:scale-105 transition-transform border border-gray-600 p-0 overflow-hidden'):
                    
                    #Szene laden beim Draufklicken (grosser Klickbereich)
                    with ui.element('div').classes('w-full h-full flex flex-col items-center justify-center p-2') \
                        .style(f'background: linear-gradient(to top, {preview_color} 0%, #222 100%);') \
                        .on('click', lambda _, s=scene: load_scene(s)):
                        
                        ui.icon('touch_app', size='md').classes('text-white opacity-50 mb-1')
                        ui.label(scene["name"]).classes('text-white font-bold text-center leading-tight shadow-black')

                    #Löschen Button der Szenen
                    with ui.button(icon='close') \
                        .props('round flat dense color=white size=xs') \
                        .style('position: absolute; top: 2px; right: 2px; opacity: 0.6; z-index: 10;') \
                        .classes('hover:bg-red-600 hover:opacity-100') \
                        .on('click.stop', lambda _, s=scene: delete_scene(s)): 
                        pass

    # Initialer Aufruf
    refresh_ui()