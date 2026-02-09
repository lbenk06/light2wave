from nicegui import ui
from gui.state import state
from projects.projects_io import save_project, load_project, load_fixtures_from_json
import os

def create():
    ui.label('Traverse').classes('text-h4')

    # Status Variablen
    placing_state = {
        "mode": "idle",
        "profile": None,
        "address": 1,
        "name": None
    }

    # Globale Referenzen für UI-Updates
    container_refs = {
        "layer": None,
        "elements": {} 
    }

    # ==========================================
    # FUNKTIONEN
    # ==========================================

    def redraw_fixtures():
        """Löscht den Layer und zeichnet alle Lampen neu."""
        layer = container_refs["layer"]
        if layer is None: return

        layer.clear()
        container_refs["elements"].clear()

        with layer:
            for fixture in state.engine.fixtures:
                r, g, b = fixture.get_color()
                
                # WICHTIG: Hier sind keine Kommentare mehr im Style-String!
                with ui.element('div').style(f'''
                    position: absolute;
                    left: {fixture.x}px;
                    top: {fixture.y}px;
                    width: 24px;
                    height: 24px;
                    border-radius: 50%;
                    background-color: rgb({r},{g},{b});
                    border: 2px solid white;
                    box-shadow: 0 0 5px rgba(0,0,0,0.5);
                    cursor: pointer;
                    z-index: 10;
                    transform: translate(-50%, -50%);
                    pointer-events: auto;
                ''') as el:
                    # Klick Event zum Löschen
                    ui.element('div').classes('w-full h-full').on('click', lambda e, f=fixture: confirm_delete_fixture(f))
                    
                    # Tooltip
                    ui.tooltip(f"{fixture.id} (Addr: {fixture.address})")
                    
                    # Text-Label
                    ui.label(f'{fixture.id}\n{fixture.address}').style('''
                        position: absolute;
                        top: 26px;
                        left: 50%;
                        transform: translateX(-50%);
                        font-size: 10px;
                        color: white;
                        text-shadow: 1px 1px 1px black;
                        pointer-events: none;
                        text-align: center;
                        white-space: nowrap;
                    ''')
                
                # Referenz speichern für Farb-Updates
                container_refs["elements"][fixture] = el

    def confirm_delete_fixture(fixture):
        """Löschen-Dialog für eine einzelne Lampe"""
        if placing_state["mode"] == "placing": return

        with ui.dialog() as dialog, ui.card():
            ui.label(f"'{fixture.id}' löschen?")
            with ui.row():
                def do_delete():
                    state.engine.fixtures.remove(fixture)
                    redraw_fixtures()
                    save_project(state.engine, "projects/my_show.json")
                    dialog.close()
                    ui.notify(f"{fixture.id} gelöscht")
                
                ui.button('Löschen', on_click=do_delete).props('color=red')
                ui.button('Abbrechen', on_click=dialog.close).props('flat')
        dialog.open()

    def handle_stage_click(e):
        """Klick auf das Bild zum Platzieren"""
        if placing_state["mode"] != "placing": return

        x = int(e.args.get('offsetX', 0))
        y = int(e.args.get('offsetY', 0))

        try:
            # Fixture erstellen
            new_fix = state.engine.create_fixture(
                profile_id=placing_state["profile"],
                x=x,
                y=y,
                fixture_id=placing_state["name"],
                address=placing_state["address"]
            )
            
            # Modus beenden
            placing_state["mode"] = "idle"
            stage_container.style('cursor: default;')
            
            redraw_fixtures()
            save_project(state.engine, "projects/my_show.json")
            ui.notify(f"Platziert: {new_fix.id}", color="green")
            
        except Exception as err:
            ui.notify(f"Fehler: {str(err)}", color="red")

    # ==========================================
    # UI AUFBAU
    # ==========================================

    with ui.element('div').style('position: relative; width: 100%; height: 800px; overflow: hidden; border: 1px solid #333;') as stage_container:
        
        # Hintergrundbild (fängt Klicks ab)
        ui.image('/static/traverse.png').style('width: 100%; height: 100%; object-fit: contain;').on('click', handle_stage_click)
        
        # Fixture Layer (darüberliegend)
        # pointer-events: none, damit Klicks aufs Bild durchgehen (außer auf Lampen)
        container_refs["layer"] = ui.element('div').style('position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none;')

    # Initiale Zeichnung
    redraw_fixtures()

    ui.separator().classes('my-4')

    # Steuerung
    with ui.row().classes('w-full items-end gap-4'):
        
        # Profil Auswahl mit Refresh-Logik
        with ui.row().classes('gap-1 items-end'):
            # Wir definieren das Select leer oder mit aktuellen Werten
            opts = {pid: p['name'] for pid, p in state.engine.profiles.items()}
            sel_prof = ui.select(opts, label="Profil").classes('w-40')
            if opts: sel_prof.value = list(opts.keys())[0]
            
            # Funktion zum Aktualisieren der Liste
            def refresh_profile_list():
                # Neue Liste aus der Engine holen
                new_opts = {pid: p['name'] for pid, p in state.engine.profiles.items()}
                sel_prof.options = new_opts
                sel_prof.update() # UI neu zeichnen
                ui.notify("Profil-Liste aktualisiert")

            # Kleiner Refresh Button daneben
            ui.button(on_click=refresh_profile_list, icon='refresh').props('flat dense round color=grey')

        # Adresse
        inp_addr = ui.number(label="Adresse", value=1, min=1, max=512, format="%.0f").classes('w-24')
        
        def update_addr_suggestion():
            if sel_prof.value:
                prof = state.engine.get_profile(sel_prof.value)
                inp_addr.value = state.engine.next_free_address(prof)
        sel_prof.on_value_change(update_addr_suggestion)

        # Name
        inp_name = ui.input(label="Name").classes('w-40')

        # Button Platzieren
        def start_placing():
            if not sel_prof.value: return
            placing_state.update({
                "mode": "placing",
                "profile": sel_prof.value,
                "address": int(inp_addr.value),
                "name": inp_name.value or None
            })
            stage_container.style('cursor: crosshair;')
            ui.notify("Klicke auf die Traverse!", color="blue")

        ui.button('Platzieren', on_click=start_placing, icon='add_location').props('color=primary')

        ui.separator().props('vertical')

        # Projekt IO
        def do_save():
            if not os.path.exists('projects'): os.makedirs('projects')
            save_project(state.engine, "projects/my_show.json")
            ui.notify("Gespeichert", color="green")

        def do_load():
            data = load_project("projects/my_show.json")
            if data:
                load_fixtures_from_json(data.get("fixtures", []), state.engine)
                redraw_fixtures()
                ui.notify("Geladen", color="green")

        def do_clear():
            # Dialog für alles löschen
            with ui.dialog() as d, ui.card():
                ui.label("Alles löschen?")
                with ui.row():
                    def confirm():
                        state.engine.fixtures.clear()
                        redraw_fixtures()
                        save_project(state.engine, "projects/my_show.json")
                        d.close()
                        ui.notify("Projekt geleert", color="orange")
                    ui.button("JA", on_click=confirm).props('color=red')
                    ui.button("Nein", on_click=d.close).props('flat')
            d.open()

        with ui.row():
            ui.button('Save', on_click=do_save, icon='save').props('flat')
            ui.button('Load', on_click=do_load, icon='folder_open').props('flat')
            ui.button('Clear', on_click=do_clear, icon='delete').props('color=red flat')

    # Live-Farben Update (Effizient)
    def update_colors():
        for fixture, el in container_refs["elements"].items():
            r, g, b = fixture.get_color()
            el.style(f'background-color: rgb({r},{g},{b});')

    ui.timer(0.1, update_colors)