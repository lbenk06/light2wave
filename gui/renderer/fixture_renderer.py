from nicegui import ui


def draw_fixtures(parent_layer, fixtures, elements_dict, on_mouse_down=None, scale=1.0):
    """
    Zeichnet Fixtures in das übergebene Layer.
    Speichert UI-Referenzen in elements_dict.
    """

    parent_layer.clear()

    elements_dict.clear()

    with parent_layer:
        for fixture in fixtures:

            r, g, b = fixture.get_color()

            #  Darstellung je nach Profil
            style = get_fixture_style(fixture, r, g, b, scale=scale)

            with ui.element('div').style(style) as el:
                if on_mouse_down:
                    el.on('mousedown', lambda e, f=fixture: on_mouse_down(f))

                ui.tooltip(f"{fixture.id} (Addr: {fixture.address})")

                if scale > 0.8:  # Nur Label anzeigen wenn genug Platz ist
                    ui.label(f'{fixture.id}--{fixture.address}').style('''
                        position: absolute;
                        top: 26px;
                        left: 50%;
                        transform: translateX(-50%);
                        font-size: 10px;
                        color: black;
                        pointer-events: none;
                        text-align: center;
                        white-space: pre;
                        background-color: white;
                        padding: 0px 2px;
                        border-radius: 4px;
                        box-shadow: 0 1px 4px rgba(0,0,0,0.3);
                    ''')

            elements_dict[fixture] = el


def get_fixture_style(fixture, r, g, b, scale=1.0):
    """
    Gibt CSS-Style abhängig vom profile_id zurück.
    """

    base_style = f'''
        position: absolute;
        left: {fixture.x * scale}px;
        top: {fixture.y * scale}px;
        width: {24 * scale}px;
        height: {24 * scale}px;
        background-color: rgb({r},{g},{b});
        border: 2px solid white;
        box-shadow: 0 0 5px rgba(0,0,0,0.5);
        cursor: pointer;
        z-index: 1100;
        transform: translate(-50%, -50%);
        pointer-events: auto;
    '''

    if fixture.profile_id == "moving_head_9ch":
        # eckig
        return base_style + "border-radius: 4px;"

    elif fixture.profile_id == "led_fluter_8ch":
        # rund
        return base_style + "border-radius: 50%;"

    else:
        # fallback
        return base_style + "border-radius: 50%;"