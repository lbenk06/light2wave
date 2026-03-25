from nicegui import ui
from gui.state import state
from gui.renderer.traverse_renderer import draw_traverses
from gui.renderer.fixture_renderer import draw_fixtures

def create():
    # Container für Referenzen (damit der Timer Zugriff auf die Elemente hat)
    refs = {
        "event_buttons": {},
        "fixture_elements": {},  # Speichert: fixture_obj -> ui.element
        "park_buttons": {},      # Speichert: fixture_idx -> ui.button
    }

    #funktionen

    def handle_event_click(event):
        event.trigger(state.engine)
        update_button_styles()


    def handle_flash_click(event):
        #1. alle laufenden Flash Events stoppen (überschreiben)
        for e in state.events:
            if e.type=="flash" and e.active:
                e.stop(state.engine)
            
        #2. neues event starten

        event.start(state.engine)
        update_button_styles()

    def update_button_styles():
        """Aktualisiert Executive-Button-Styles je nach aktivem Zustand"""
        for name, btn in refs["event_buttons"].items():
            event = next((e for e in state.events if e.name == name), None)
            if event:
                if "BLINDER" in name.upper() or "FLASH" in name.upper():
                    btn.classes('exec-flash', remove='exec-active exec-btn')
                    continue
                if event.active:
                    btn.classes('exec-btn exec-active', remove='exec-flash')
                else:
                    btn.classes('exec-btn', remove='exec-active exec-flash')

    def toggle_park(fixture_idx: int):
        """Park/Unpark eines Fixtures umschalten"""
        engine = state.engine
        if fixture_idx in engine.parked_fixtures:
            engine.unpark_fixture(fixture_idx)
        else:
            engine.park_fixture(fixture_idx)
            # Dimmer auf 1.0 setzen damit Farb-Sliders sofort wirken
            engine.set_parked_color(fixture_idx, dimmer=1.0)
        update_park_styles()

    def update_park_styles():
        """Aktualisiert PARK-Button-Farben und zeigt Farb-Controls"""
        for idx, btn in refs["park_buttons"].items():
            parked = idx in state.engine.parked_fixtures
            if parked:
                btn.classes('exec-btn exec-active', remove='exec-flash')
                btn.props('color=amber')
            else:
                btn.classes('exec-btn', remove='exec-active exec-flash')
                btn.props(remove='color')
            color_row = refs.get("park_color_rows", {}).get(idx)
            if color_row:
                color_row.style('display:block;' if parked else 'display:none;')

    def get_display_color(fix, idx):
        """Gibt Displayfarbe zurück — für geparkte Fixtures aus eingefrorenen Werten"""
        engine = state.engine
        if idx in engine.parked_fixtures:
            vals = engine.parked_values.get(idx, [])
            ch_roles = [ch["role"] for ch in fix.profile["channels"]]
            def gv(role):
                try:
                    i = ch_roles.index(role)
                    return vals[i] / 255.0 if i < len(vals) else 0.0
                except ValueError:
                    return 0.0
            dim = gv("dimmer") if "dimmer" in ch_roles else 1.0
            r = int(gv("red") * dim * 255)
            g = int(gv("green") * dim * 255)
            b = int(gv("blue") * dim * 255)
            if "white" in ch_roles:
                w = int(gv("white") * dim * 255)
                r, g, b = min(255, r + w), min(255, g + w), min(255, b + w)
            return (r, g, b)
        return fix.get_color()

    def update_visuals():
        """Wird 10x pro Sekunde aufgerufen: Aktualisiert Lampenfarben"""
        fixtures = state.engine.fixtures
        for fix, el in refs["fixture_elements"].items():
            try:
                idx = fixtures.index(fix)
                r, g, b = get_display_color(fix, idx)

                #Helligkeit simulieren (Schatten leuchtet wenn an)
                box_shadow = f"0 0 {10 + (r+g+b)/10}px rgb({r},{g},{b})" if (r+g+b) > 0 else "none"

                el.style(f'background-color: rgb({r},{g},{b}); box-shadow: {box_shadow};')
            except Exception:
                pass

        update_button_styles()
        update_park_styles()

    def on_refresh():
        ui.notify('Live Tab neu geladen', color='green')
        refresh_ui()

    # HAUPTCONTAINER FÜR DEN REFRESH
    main_container = ui.column().classes('w-full h-full p-4 gap-4')

    def refresh_ui():
        # Inhalt leeren
        main_container.clear()
        refs["event_buttons"].clear()
        refs["fixture_elements"].clear()
        refs["park_buttons"].clear()

        #ui layout neu aufbauen
        with main_container:
            
            #Oberer Bereich: Flash Buttons, Refresh
            with ui.row().classes('w-full justify-between items-center'):
                with ui.row().classes('items-center gap-4'):
                    ui.label('LIVE DASHBOARD').classes('text-2xl font-bold tracking-wider text-gray-200')
                    
                    # Refresh Button
                    ui.button(on_click=on_refresh, icon='refresh') \
                        .props('flat round color=grey') \
                        .tooltip('Kompletten Tab neu laden')

                with ui.row().classes('gap-2 items-center'):
                    flash_events=[e for e in state.events if e.type=="flash" or "BLINDER" in e.name.upper()]
                    for ev in flash_events:
                        btn = ui.button(ev.name.upper(), on_click=lambda _, e=ev: handle_flash_click(e) ) \
                            .classes('text-sm font-black px-6 h-12') \
                            .props('color=white text-color=black push')
                        
                        refs["event_buttons"][ev.name] = btn


            ui.separator().classes('bg-gray-700')

            with ui.row().classes('w-full items-start gap-4'):

                # --- MASTER FADER ---
                with ui.column().classes('items-center gap-2 py-2').style('min-width: 56px;'):
                    ui.label('MASTER').classes('text-xs font-black text-yellow-400 tracking-widest')
                    ui.slider(min=0.0, max=1.0, step=0.01, value=1.0) \
                        .bind_value(state.engine, 'master_dimmer') \
                        .props('vertical reverse color=yellow label-always') \
                        .style('height: 320px;')
                    ui.button(icon='highlight_off', on_click=lambda: setattr(state.engine, 'master_dimmer', 0.0)) \
                        .props('flat round color=red dense') \
                        .tooltip('Blackout')
                    ui.button(icon='light_mode', on_click=lambda: setattr(state.engine, 'master_dimmer', 1.0)) \
                        .props('flat round color=yellow dense') \
                        .tooltip('Volle Helligkeit')

                # Mitte: Stage + Szenen darunter
                with ui.column().classes('flex-1 gap-2'):
                    SCALE=0.5
                    windowwith=1200*SCALE
                    windowheight=800*SCALE
                    with ui.element('div').style(f'''
                        position: relative;
                        width: {windowwith}px;
                        height: {windowheight}px;
                        overflow: auto;
                        transform-origin: top left;
                    '''):
                        # Traverse
                        with ui.element('div').style('position: absolute; inset: 0; z-index: 10;') as traverse_layer:
                            draw_traverses(traverse_layer, state.engine.traverses, scale=SCALE)

                        # Fixtures
                        with ui.element('div').style('position: absolute; inset: 0; z-index: 20; ') as fixture_layer:
                            draw_fixtures(
                                parent_layer=fixture_layer,
                                fixtures=state.engine.fixtures,
                                elements_dict=refs["fixture_elements"],
                                on_mouse_down=None,
                                scale=SCALE
                            )

                    # Szenen/Banken Auswahl — direkt unter Stage
                    with ui.card().classes('w-full bg-gray-900 border border-gray-700 p-2'):
                        ui.label("SZENEN-STEUERUNG").classes("text-xs font-bold text-gray-500 mb-2")

                        if state.engine.banks:
                            bank_names = [bank["name"] for bank in state.engine.banks]

                            with ui.row().classes('w-full items-center mb-4'):
                                ui.label('Bank:').classes('text-gray-200 mr-2')
                                bank_select = ui.select(bank_names, value=bank_names[0]).props('dark standout label-color=white color=white').classes('flex-grow')

                            scene_container = ui.row().classes('gap-2 wrap w-full')

                            def refresh_scenes():
                                scene_container.clear()
                                selected_bank = next((b for b in state.engine.banks if b["name"] == bank_select.value), None)
                                if selected_bank:
                                    with scene_container:
                                        for scene in selected_bank["scenes"]:
                                            def load_scene(s=scene):
                                                data = s.get("data", {})
                                                for f in state.engine.fixtures:
                                                    if f.id in data:
                                                        for k, v in data[f.id].items():
                                                            f.set(k, v)
                                                ui.notify(f"Szene '{scene['name']}' geladen", color='cyan')
                                            ui.button(scene["name"], on_click=load_scene).props('outline color=cyan').classes('min-w-[80px]')

                            bank_select.on_value_change(refresh_scenes)
                            refresh_scenes()

                # Rechts: Effekte + Park
                with ui.column().classes('gap-2').style('min-width:220px; max-width:260px;'):
                    


                    ui.label('EFFEKTE').classes('console-label mb-2')

                    with ui.grid(columns=2).classes('w-full gap-1'):
                        for event in state.events:
                            if event.type=="flash" or event.type=="stop_all" or "BLINDER" in event.name.upper():
                                continue

                            btn = ui.button(event.name, on_click=lambda _, e=event: handle_event_click(e)) \
                                .classes('w-full exec-btn text-[10px] font-black tracking-widest uppercase') \
                                .props('flat') \
                                .style('height:40px; padding:0 6px;')

                            refs["event_buttons"][event.name] = btn

                    stop_event = next((e for e in state.events if e.type=="stop_all"), None)
                    if stop_event:
                        ui.element('div').style('height:1px; background:#1a1a24; margin:10px 0 6px;')
                        ui.button('■  STOP ALL', on_click=lambda _, e=stop_event: handle_event_click(e)) \
                            .classes('w-full font-black tracking-[0.15em]') \
                            .props('push color=red') \
                            .style('height:38px; font-size:11px; border-radius:2px;')

                    # --- PARK SEKTION ---
                    ui.element('div').style('height:1px; background:#1a1a24; margin:14px 0 8px;')
                    with ui.row().classes('w-full items-center justify-between mb-1'):
                        ui.label('FIXTURE PARK').classes('console-label')
                        def unpark_all():
                            for i in list(state.engine.parked_fixtures):
                                state.engine.unpark_fixture(i)
                            update_park_styles()

                        ui.button('ALLE FREI', on_click=unpark_all) \
                            .classes('exec-btn text-[9px]') \
                            .props('flat dense') \
                            .style('height:20px; padding:0 6px;')

                    refs["park_buttons"].clear()
                    refs["park_color_rows"] = {}
                    with ui.column().classes('w-full gap-1'):
                        for idx, fix in enumerate(state.engine.fixtures):
                            fix_roles = [ch["role"] for ch in fix.profile["channels"]]

                            with ui.row().classes('w-full items-center gap-1'):
                                ui.label(fix.id).classes('text-[10px] text-gray-300 font-mono flex-1')
                                ui.label(f'A{fix.address}').classes('text-[9px] text-gray-600 font-mono')
                                btn = ui.button('PARK', on_click=lambda _, i=idx: toggle_park(i)) \
                                    .classes('exec-btn text-[9px]') \
                                    .props('flat dense') \
                                    .style('height:22px; min-width:44px; padding:0 6px;')
                                refs["park_buttons"][idx] = btn

                            # Farb-Controls — nur sichtbar wenn geparkt
                            with ui.column().classes('w-full pl-2 gap-1').style('display:none;') as color_row:
                                # Preset-Buttons
                                PRESETS = [
                                    ('W',  dict(red=1.0, green=1.0, blue=1.0, white=1.0, dimmer=1.0)),
                                    ('R',  dict(red=1.0, green=0.0, blue=0.0, dimmer=1.0)),
                                    ('G',  dict(red=0.0, green=1.0, blue=0.0, dimmer=1.0)),
                                    ('B',  dict(red=0.0, green=0.0, blue=1.0, dimmer=1.0)),
                                    ('OFF',dict(red=0.0, green=0.0, blue=0.0, white=0.0, dimmer=0.0)),
                                ]
                                with ui.row().classes('gap-1'):
                                    for label_p, vals_p in PRESETS:
                                        ui.button(label_p, on_click=lambda _, i=idx, v=vals_p: (
                                            state.engine.set_parked_color(i, **v)
                                        )).classes('exec-btn text-[9px]') \
                                          .props('flat dense') \
                                          .style('height:20px; min-width:28px; padding:0 4px;')

                                # Dimmer-Slider
                                if 'dimmer' in fix_roles:
                                    with ui.row().classes('w-full items-center gap-2'):
                                        ui.label('DIM').classes('console-label w-6')
                                        ui.slider(min=0.0, max=1.0, step=0.01, value=1.0,
                                            on_change=lambda e, i=idx: state.engine.set_parked_color(i, dimmer=e.value)
                                        ).classes('flex-1').props('color=yellow dense')

                                # R/G/B/W Sliders je nach Profil
                                for role, color in [('red','red'), ('green','green'), ('blue','cyan'), ('white','white')]:
                                    if role in fix_roles:
                                        with ui.row().classes('w-full items-center gap-2'):
                                            ui.label(role[0].upper()).classes('console-label w-6')
                                            ui.slider(min=0.0, max=1.0, step=0.01, value=0.0,
                                                on_change=lambda e, i=idx, r=role: state.engine.set_parked_color(i, **{r: e.value})
                                            ).classes('flex-1').props(f'color={color} dense')

                            refs["park_color_rows"][idx] = color_row
                        


        # Initiale Styles setzen
        update_button_styles()

    # EINMALIG AUFRUFEN ZUM START
    refresh_ui()

    #10fps TIMER AUSSERHALB VON REFRESH_UI
    ui.timer(0.1, update_visuals)