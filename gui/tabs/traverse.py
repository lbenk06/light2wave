from nicegui import ui
from gui.state import state
from projects.projects_io import save_project, load_project, load_fixtures_from_json
from engine.traverse_snap import Traverse 
from gui.renderer.traverse_renderer import draw_traverses
from gui.renderer.fixture_renderer import draw_fixtures
import os

def create():
    ui.label('Traverse').classes('text-h4')

    interaction_state = {"mode": "idle"}  # idle | placing | dragging

    # Status Variablen
    placing_state = {
        #"mode": "idle",
        "profile": None,
        "address": 1,
        "name": None,
        "hover_snap": None
    }

    drag_state = {
        "fixture": None,
        "origin_traverse": None,
        "origin_snap": None,
    }

    placing_state.update({
        "hover_snap": None
    })    

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

    snap_points_ui = {}
    snap_layer = None
    SNAP_RADIUS = 18

    if not state.engine.traverses:
        #state.engine.traverses.append(
        state.engine.traverses.extend([
            Traverse(
                x1=200, y1=200,
                x2=1000, y2=200,
                snap_distance=50,
                name="Front-Traverse"
            ),
            Traverse(
                x1=175, y1=175,
                x2=175, y2=575,
                snap_distance=50,
                name="Front-Left-Traverse"
            ),
            Traverse(
                x1=1025, y1=175,
                x2=1025, y2=575,
                snap_distance=50,
                name="Front-Right-Traverse"
            )
        ])
    

# Funktionen
################################################################################################
    
    def redraw_fixtures():
        if container_refs["layer"] is None:
            return

        draw_fixtures(
            parent_layer=container_refs["layer"],
            fixtures=state.engine.fixtures,
            elements_dict=container_refs["elements"],
            on_mouse_down=handle_mouse_down
        )

    def delete_fixture(fixture, client):
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

    def trash_bin(x, y):
        stage_width = 1200
        stage_height = 800
        size = 50
        margin = 20

        return (
            stage_width - margin -size <= x <= stage_width - margin and
            stage_height - margin -size <= y <= stage_height - margin
        )

    def handle_mouse_down(fixture):

        if interaction_state["mode"] == "placing":
            return

        if fixture.traverse is None or fixture.snap_point is None:
            ui.notify("Dieses Fixture ist noch keinem Traverse zugeordnet!", color="orange")
            return
        
        interaction_state["mode"] = "dragging"
        drag_state["fixture"] = fixture
        drag_state["origin_traverse"] = fixture.traverse
        drag_state["origin_snap"] = fixture.snap_point

        # alten Snap erstmal freigeben
        sp = fixture.traverse.snap_points[fixture.snap_point]
        sp["occupied"] = False
        sp["fixture"] = None

        # Fixtures halbtransparent machen
        el = container_refs["elements"].get(fixture)
        if el:
            el.style('opacity: 0.5;')

        draw_snap_points(show=True)
        create_ghost()

    def handle_mouse_up(e):

        if interaction_state["mode"] != "dragging":
            return

        fixture = drag_state["fixture"]
        x = int(e.args.get("offsetX", 0))
        y = int(e.args.get("offsetY", 0))

        if trash_bin(x, y):
            delete_fixture(fixture, e.client)
            interaction_state["mode"] = "idle"
            drag_state["fixture"] = None
            draw_snap_points(show=False)
            redraw_fixtures()
            return

        snap = placing_state["hover_snap"]

        if not snap:
            ui.notify("Kein Snap-Punkt", color="orange")
            return

        new_traverse, new_sp_id = snap
        new_sp = new_traverse.snap_points[new_sp_id]

        # Alten Snap freigeben
        old_traverse = fixture.traverse
        old_sp = old_traverse.snap_points[fixture.snap_point]
        old_sp["occupied"] = False
        old_sp["fixture"] = None

        # Neuen Snap belegen
        fixture.x = new_sp["x"]
        fixture.y = new_sp["y"]
        fixture.traverse = new_traverse
        fixture.snap_point = new_sp_id

        new_sp["occupied"] = True
        new_sp["fixture"] = fixture

        interaction_state["mode"] = "idle"
        drag_state["fixture"] = None

        # Fixtures wieder ganz sichtbar
        el = container_refs["elements"].get(fixture)
        if el:
            el.style('opacity: 1;')

        if ghost_fixture["el"]:
            ghost_fixture["el"].delete()
            ghost_fixture["el"] = None

        draw_snap_points(show=False)
        redraw_fixtures()
        save_project(state.engine, "projects/my_show.json")

    def handle_stage_click(e):
        if interaction_state["mode"] != "placing":
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

            interaction_state["mode"] = "idle"
            stage_container.style('cursor: default;')

            redraw_fixtures()
            save_project(state.engine, "projects/my_show.json")
            ui.notify(f"{new_fix.id} platziert", color="green")
            draw_snap_points(show=False)

        except Exception as err:
            ui.notify(str(err), color="red")

    def start_placing():
        if not sel_prof.value:
            return

        interaction_state["mode"] = "placing"

        placing_state.update({
            "profile": sel_prof.value,
            "address": int(inp_addr.value),
            "name": inp_name.value or None,
            "hover_snap": None
        })

        create_ghost()

        stage_container.style('cursor: crosshair;')
        ui.notify("Fixture am Mauszeiger - auf Snap klicken")

        draw_snap_points(show=True)

    def handle_mouse_move(e):

        # STAGE-lokale Koordinaten (NiceGUI korrekt)
        x = int(e.args.get("offsetX", 0))
        y = int(e.args.get("offsetY", 0))

        # Platzieren
        if interaction_state["mode"] == "placing":

            if not ghost_fixture["el"]:
                return

            # Snap suchen
            snap = find_nearest_snap(x, y)
            placing_state["hover_snap"] = snap

            # Snap-UI reset
            for el in snap_points_ui.values():
                el.style('transform: translate(-50%, -50%) scale(1); background: cyan;')

            if snap:
                t, sp_id = snap
                sp = t.snap_points[sp_id]
                snap_points_ui[(t, sp_id)].style(
                    'transform: translate(-50%, -50%) scale(1.8); background: lime;'
                )
                update_ghost(sp["x"], sp["y"], snapped=True)

            else:
                update_ghost(x, y, snapped=False)

        # Verschieben
        elif interaction_state["mode"] == "dragging":
            snap = find_nearest_snap(x, y)
            placing_state["hover_snap"] = snap

            # Highlight Logik wie beim placing
            for el in snap_points_ui.values():
                el.style('transform: translate(-50%, -50%) scale(1); background: cyan;')

            if snap:
                t, sp_id = snap
                sp = t.snap_points[sp_id]
                snap_points_ui[(t, sp_id)].style(
                    'transform: translate(-50%, -50%) scale(1.8); background: lime;'
                )                
                update_ghost(sp["x"], sp["y"], snapped=True)

            else:
                update_ghost(x, y, snapped=False)

            # Trash Hoverlook
            if trash_bin(x, y):
                trash_icon.style(
                    'transform: scale(1.4); '
                    'filter: brightness(1.3);'
                )
            else:
                trash_icon.style(
                    'transform: scale(1); '
                    'filter: brightness(1);'
                )

    def create_ghost():
        if ghost_fixture["el"]:
            ghost_fixture["el"].delete()

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

        with snap_layer:
            for t in state.engine.traverses:
                for i, sp in enumerate(t.snap_points):
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
                    snap_points_ui[(t, i)] = el


    # Projekt IO
    def do_save():
        if not os.path.exists('projects'): os.makedirs('projects')
        save_project(state.engine, "projects/my_show.json")
        ui.notify("Gespeichert", color="green")

    def do_load():
        data = load_project("projects/my_show.json")
        if not data:
            ui.notify("Fehler beim Laden (Projektdatei nicht gefunden)", color="red")
            return

        # Traverses zuerst wiederherstellen
        state.engine.traverses.clear()
        for td in data.get("traverses", []):
            t = Traverse(
                x1=td["x1"],
                y1=td["y1"],
                x2=td["x2"],
                y2=td["y2"],
                snap_distance=td.get("snap_distance", 40),
                name=td["name"]
            )
            state.engine.traverses.append(t)

        # Fixtures laden und Traverses verbinden
        fixtures_list = data.get("fixtures", [])
        load_fixtures_from_json(fixtures_list, state.engine)

        # Banken und Szenen laden
        state.engine.banks = data.get("banks", [])

        redraw_fixtures()
        draw_traverses(traverse_layer, state.engine.traverses)
        ui.notify("Geladen", color="green")

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
        'position: relative; width: 1200px; height: 800px; overflow: hidden;  background: #fff;' # border: 1px solid #333;
    ) as stage_container:
         
        traverse_layer = ui.element('div').style(
            'position: absolute; top:0; left:0; width: 1200px; height: 800px; z-index: 5; pointer-events: none;'
        )
        
        # Mülleimer UI (unten rechts)
        trash_icon = ui.image('/static/icons8-full-trash-100-s.png').style(
            'position: absolute; z-index: 15; bottom: 20px; right: 20px; '
            'width: 50px; height: 50px; pointer-events: none;'
            'pointer-events: none; '
            'transition: transform 0.15s ease, filter 0.15s ease'
        )
        
        # Snap Overlay (unsichtbar, aber fängt Mausbewegung ab)
        snap_layer = ui.element('div').style(
            'position:absolute; top:0; left:0; width:1200px; height:800px; z-index:10; pointer-events: none;'
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
        mouse_layer.on('mouseup', handle_mouse_up)
        mouse_layer.on('click', handle_stage_click)


    # Initiale Zeichnung
    redraw_fixtures()
    draw_traverses(traverse_layer, state.engine.traverses)


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
