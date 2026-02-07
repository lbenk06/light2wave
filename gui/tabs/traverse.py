from nicegui import ui
from gui.state import state

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
        'position: relative; width: 1200px; height: 600px; margin: auto; background: #111;'
    ) as stage:

        # Hintergrundbild
        ui.image('/static/traverse.png').style(
            'width: 100%; height: 100%; object-fit: contain;'
        )

        fixture_elements = {}

        # Funktion: Fixture-Kreise + Labels zeichnen
        def redraw_fixtures():
            for el in fixture_elements.values():
                el.delete()
            fixture_elements.clear()

            for fixture in state.engine.fixtures:
                r, g, b = fixture.get_color()

                # Kreis + Klick zum Löschen
                def on_fixture_click(f=fixture):
                    if ui.confirm(f'Soll {f.id} gelöscht werden?'):
                        state.engine.fixtures.remove(f)
                        redraw_fixtures()

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
                ''').on('click', on_fixture_click)

                # Label unter Kreis: Name + Adresse
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

            # Nächste freie Adresse, falls nicht manuell angegeben
            if placing_address is None:
                placing_address = state.engine.next_free_address(state.engine.get_profile(placing_profile))

            # Name vergeben
            if not placing_name:
                placing_name = f'{placing_profile}_{len(state.engine.fixtures)+1}'

            # Fixture erstellen
            fixture = state.engine.create_fixture(
                profile_id=placing_profile,
                x=x,
                y=y,
                fixture_id=placing_name,
                address=placing_address
            )

            # Reset für nächsten Add-Vorgang
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

        # Button zum Hinzufügen
        def start_placing():
            global placing_profile, placing_name, placing_address
            placing_profile = profile_select.value
            placing_name = name_input.value.strip() or None
            placing_address = int(address_input.value)

        ui.button('Gerät hinzufügen', on_click=start_placing)

        # Projekt speichern
        def save_current_project():
            from projects.projects_io import save_project
            save_project(state.engine, 'projects/my_show.json')
        ui.button('Projekt speichern', on_click=save_current_project)

        # Projekt löschen
        def delete_project():
            if ui.confirm('Gesamtes Projekt löschen?'):
                state.engine.fixtures.clear()
                redraw_fixtures()
        ui.button('Projekt löschen', on_click=delete_project)

    # =============================
    # Live-Farbupdate
    # =============================
    def update_colors():
        for fixture, el in fixture_elements.items():
            r, g, b = fixture.get_color()
            el.style(f'background-color: rgb({r},{g},{b});')

    ui.timer(1 / 20, update_colors)
