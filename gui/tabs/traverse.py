from nicegui import ui
from gui.state import state
from projects.projects_io import save_project, load_project, load_fixtures_from_json
from engine.traverse1 import Traverse 
from nicegui import run
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

    # Snap-on für Geräte
    ghost_fixture = {
        "el": None,
        "x": 0,
        "y": 0,
    }

    placing_state.update({
        "hover_snap": None
    })

    snap_points_ui = []
    snap_layer = None

    if not state.engine.traverses:
        state.engine.traverses.append(
            Traverse(
                x1=200, y1=200,
                x2=1000, y2=200,
                snap_distance=60,
                name="Front-Traverse"
            )
        )


# Funktionen
################################################################################################

    def redraw_fixtures():
        """Löscht den Layer und zeichnet alle Lampen neu."""
        layer = container_refs["layer"]
        if layer is None: 
            return

        layer.clear()  # Layer beibehalten, nur Kinder löschen
        container_refs["elements"].clear()

        with layer:
            for fixture in state.engine.fixtures:
                r, g, b = fixture.get_color()

                # Direktes Fixture-Div, kein extra div für Klick
                def make_click_handler(f):
                    #return lambda e: confirm_delete_fixture(f)
                    return lambda e: confirm_delete_fixture(f, e.client)
                
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
                    z-index: 1100;
                    transform: translate(-50%, -50%);
                    pointer-events: auto;
                ''').on('click', make_click_handler(fixture)) as el:

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

    def confirm_delete_fixture(fixture, client):
        with ui.dialog() as dialog, ui.card():
            ui.label(f"'{fixture.id}' löschen?")
            with ui.row():
                def do_delete():
                    for t in state.engine.traverses:
                        for sp in t.snap_points:
                            if sp.get("fixture") == fixture:
                                sp["occupied"] = False
                                sp["fixture"] = None
                    
                    state.engine.fixtures.remove(fixture)
                    redraw_fixtures()
                    save_project(state.engine, "projects/my_show.json")
                    dialog.close()

                ui.button('Löschen', on_click=do_delete).props('color=red')
                ui.button('Abbrechen', on_click=dialog.close).props('flat')

        dialog.open()


    def handle_stage_click(e):
        if placing_state["mode"] != "placing":
            return

        snap = placing_state["hover_snap"]
        if not snap:
            ui.notify("Kein Snap-Point getroffen", color="orange")
            return

        traverse, sp_id = snap
        sp = traverse.snap_points[sp_id]

        try:
            new_fix = state.engine.create_fixture(
                profile_id=placing_state["profile"],
                x=sp["x"],
                y=sp["y"],
                fixture_id=placing_state["name"],
                address=placing_state["address"]
            )

            new_fix.traverse = traverse
            new_fix.snap_point = sp_id

            sp["occupied"] = True
            sp["fixture"] = new_fix

            # Cleanup
            ghost_fixture["el"].delete()
            ghost_fixture["el"] = None

            placing_state["mode"] = "idle"
            stage_container.style('cursor: default;')

            redraw_fixtures()
            save_project(state.engine, "projects/my_show.json")
            ui.notify(f"{new_fix.id} platziert", color="green")

        except Exception as err:
            ui.notify(str(err), color="red")

        draw_snap_points(show=False)


    def start_placing():
        if not sel_prof.value:
            return

        placing_state.update({
            "mode": "placing",
            "profile": sel_prof.value,
            "address": int(inp_addr.value),
            "name": inp_name.value or None,
            "hover_snap": None
        })

        # Ghost erzeugen
        with stage_container:
            ghost_fixture["el"] = ui.element('div').style('''
                position: absolute;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                background: rgba(255,255,255,0.4);
                border: 2px dashed cyan;
                transform: translate(-50%, -50%);
                pointer-events: none;
                z-index: 50;
            ''')

        stage_container.style('cursor: crosshair;')
        ui.notify("Fixture am Mauszeiger - auf Snap klicken")

        draw_snap_points(show=True)


    def handle_mouse_move(e):
        if placing_state["mode"] != "placing":
            return
        if not ghost_fixture["el"]:
            return

        # STAGE-lokale Koordinaten (NiceGUI korrekt)
        x = int(e.args.get("offsetX", 0))
        y = int(e.args.get("offsetY", 0))


        # Snap suchen
        snap = find_nearest_snap(x, y)
        placing_state["hover_snap"] = snap

        # Snap-UI reset
        for el in snap_points_ui:
            el.style('transform: translate(-50%, -50%) scale(1); background: cyan;')

        if snap:
            t, sp_id = snap
            sp = t.snap_points[sp_id]

            update_ghost(sp["x"], sp["y"], snapped=True)

            # Sicherer Zugriff auf das UI-Element
            snap_points_ui[sp_id].style(
                'transform: translate(-50%, -50%) scale(1.8); background: lime;'
            )

        else:
            update_ghost(x, y, snapped=False)




    def update_ghost(x: int, y: int, snapped: bool = False):
        if not ghost_fixture["el"]:
            return

        color = "lime" if snapped else "cyan"

        ghost_fixture["el"].style(
            f'''
            left: {x}px;
            top: {y}px;
            border-color: {color};
            '''
        )

    SNAP_RADIUS = 18
    def find_nearest_snap(x, y):
        best = None
        best_dist = SNAP_RADIUS

        for t in state.engine.traverses:
            for i, sp in enumerate(t.snap_points):
                if sp["occupied"]:
                    continue
                d = ((sp["x"]-x)**2 + (sp["y"]-y)**2) ** 0.5
                if d < best_dist:
                    best = (t, i)
                    best_dist = d

        return best
    
    def draw_snap_points(show=False):
        snap_layer.clear()
        snap_points_ui.clear()

        if not show:
            return

        with mouse_layer:
            for t in state.engine.traverses:
                for sp in t.snap_points:
                    el = ui.element('div').style(f'''
                        position: absolute;
                        left: {sp["x"]}px;
                        top: {sp["y"]}px;
                        width: 8px;
                        height: 8px;
                        border-radius: 50%;
                        background: {'red' if sp["occupied"] else 'cyan'};
                        transform: translate(-50%, -50%);
                        pointer-events: none;
                    ''')
                    snap_points_ui.append(el)

        

    # Projekt IO
    def do_save():
        if not os.path.exists('projects'): os.makedirs('projects')
        save_project(state.engine, "projects/my_show.json")
        ui.notify("Gespeichert", color="green")

    def do_load():
        data = load_project("projects/my_show.json")
        if data:
            fixtures_list=data.get("fixtures", [])
            load_fixtures_from_json(fixtures_list, state.engine)
            
            #banken und szenen laden:
            state.engine.banks=data.get("banks", [])            
            
            redraw_fixtures()
            ui.notify("Geladen", color="green")
        else:
            ui.notify("Fehler beim Laden (Projektdatei nicht gefunden)", color="red")

    def do_clear():
        # Dialog für alles löschen
        with ui.dialog() as d, ui.card():
            ui.label("Alles löschen?")
            with ui.row():
                def confirm(): #def confirm():
                    state.engine.fixtures.clear()
                    redraw_fixtures()
                    save_project(state.engine, "projects/my_show.json")
                    d.close()

                ui.button("JA", on_click=confirm).props('color=red')
                ui.button("Nein", on_click=d.close).props('flat')
        d.open()


# UI AUFBAU
################################################################################################

    with ui.element('div').style(
        'position: relative; width: 1200px; height: 800px; overflow: hidden;  background: #111;' # border: 1px solid #333;
    ) as stage_container:
        
        # Hintergrundbild (fängt Klicks ab)
        ui.image('/static/traverse.png') \
            .style('position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; pointer-events: none;') # object-fit: contain;
        
        # Snap Overlay (unsichtbar, aber fängt Mausbewegung ab)
        snap_layer = ui.element('div').style(
            'position:absolute; inset:0; z-index:10; pointer-events: none;'
        )

        # Fixture Layer (darüberliegend)
        # pointer-events: none, damit Klicks aufs Bild durchgehen (außer auf Lampen)
        container_refs["layer"] = ui.element('div').style(
            'position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: auto;'
        )

        mouse_layer = ui.element('div').style(
            'position: absolute; inset: 0; z-index: 1000; cursor: crosshair; background: transparent;' #pointer-events: none;
        )

        mouse_layer.on('mousemove', handle_mouse_move)
        mouse_layer.on('click', handle_stage_click)


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
        ui.button('Platzieren', on_click=start_placing, icon='add_location').props('color=primary')

        ui.separator().props('vertical')



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
