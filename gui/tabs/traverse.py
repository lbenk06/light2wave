from nicegui import ui
from gui.state import state
from projects.projects_io import save_project, load_project
import os

# Statusvariablen für das Platzieren eines neuen Fixtures
placing_profile = None
placing_name = None
placing_address = None

def create():
    global placing_profile, placing_name, placing_address

    ui.label('Traverse').classes('text-h4')

    # =============================
    # TRAVERSE-BEREICH
    # =============================
    with ui.element('div').style(
        'position: relative; width: 1200px; height: 800px; margin: auto; background: #111;'
    ) as stage:

        # Hintergrundbild (pointer-events none, damit Klicks durchgehen)
        ui.image('/static/traverse.png').style(
            'width: 100%; height: 100%; object-fit: contain; pointer-events: none;'
        )

        fixture_elements = {}

        # =============================
        # Fixture löschen
        # =============================
        def remove_fixture(fixture):
            if ui.confirm(f'Soll {fixture.id} gelöscht werden?'):
                state.engine.fixtures.remove(fixture)
                redraw_fixtures()

        # =============================
        # Fixtures zeichnen
        # =============================
        def redraw_fixtures():
            # alte Elemente löschen
            for el in fixture_elements.values():
                el.delete()
            fixture_elements.clear()

            for fixture in state.engine.fixtures:
                r, g, b = fixture.get_color()

                # Kreis
                el = ui.element('div').style(f'''
                    position: absolute;
                    left: {fixture.x}px;
                    top: {fixture.y}px;
                    width: 24px;
                    height: 24px;
                    border-radius: 50%;
                    background-color: rgb({r},{g},{b});
                    border: 2px solid black;
                    cursor: pointer;
                ''').on('click', lambda e, f=fixture: remove_fixture(f))

                # Name + Adresse unter Kreis
                ui.label(f'{fixture.id}\nAddr: {fixture.address}').style(f'''
                    position: absolute;
                    left: {fixture.x - 20}px;
                    top: {fixture.y + 28}px;
                    width: 80px;
                    text-align: center;
                    color: white;
                    font-size: 12px;
                ''')

                fixture_elements[fixture] = el

        redraw_fixtures()

        # =============================
        # Klick auf Traverse → Fixture platzieren
        # =============================
        def on_stage_click(e):
            global placing_profile, placing_name, placing_address
            if placing_profile is None:
                return

            x = int(e.args['offsetX'])
            y = int(e.args['offsetY'])

            # Name und Adresse setzen
            if not placing_name:
                placing_name = f'{placing_profile}_{len(state.engine.fixtures)+1}'
            if placing_address is None:
                placing_address = state.engine.next_free_address(
                    state.engine.get_profile(placing_profile)
                )

            # Fixture erstellen
            fixture = state.engine.create_fixture(
                profile_id=placing_profile,
                x=x,
                y=y,
                fixture_id=placing_name,
                address=placing_address
            )

            # Reset der Statusvariablen
            placing_profile = None
            placing_name = None
            placing_address = None

            redraw_fixtures()

        stage.on('click', on_stage_click)

    # =============================
    # Steuerung unter der Traverse
    # =============================
    ui.separator()
    with ui.row().classes('justify-center gap-4'):

        # Profil auswählen
        profile_select = ui.select(
            options=[(p["name"], pid) for pid, p in state.engine.profiles.items()],
            label='Profil auswählen'
        )

        # Startadresse automatisch auf nächste freie Adresse setzen
        next_address = state.engine.next_free_address(
            state.engine.get_profile(list(state.engine.profiles.keys())[0])
        )
        address_input = ui.number(
            label='Startadresse',
            value=next_address,
            min=1,
            max=512,
            step=1
        )

        # Name eingeben
        name_input = ui.input(label='Gerätename', value='')

        # Gerät platzieren starten
        def start_placing():
            global placing_profile, placing_name, placing_address
            placing_profile = profile_select.value
            placing_name = name_input.value.strip() or None
            placing_address = int(address_input.value)

        ui.button('Gerät hinzufügen', on_click=start_placing)

        # =============================
        # Projekt speichern
        # =============================
        def save_current_project():
            if not os.path.exists('projects'):
                os.makedirs('projects')

            save_project(state.engine, "projects/my_show.json")
            ui.notify("Projekt gespeichert", color="green")

        ui.button('Projekt speichern', on_click=save_current_project)

        # Projekt laden
        def load_current_project():
            try:
                project_data = load_project("projects/my_show.json")
                state.engine.fixtures.clear()
                from projects.projects_io import load_fixtures_from_json
                load_fixtures_from_json(project_data.get("fixtures", []), state.engine)
                redraw_fixtures()
                ui.notify("Projekt geladen", color="green")
            except FileNotFoundError:
                ui.notify("Keine gespeicherte Show gefunden", color="red")

        ui.button('Projekt laden', on_click=load_current_project)

        # Projekt löschen
        def delete_project():
            if ui.confirm("Gesamtes Projekt löschen?"):
                state.engine.fixtures.clear()
                redraw_fixtures()
                ui.notify("Projekt gelöscht", color="red")

        ui.button('Projekt löschen', on_click=delete_project)

    # =============================
    # Live-Farbupdate
    # =============================
    def update_colors():
        for fixture, el in fixture_elements.items():
            r, g, b = fixture.get_color()
            el.style(f'background-color: rgb({r},{g},{b});')

    ui.timer(1 / 20, update_colors)
