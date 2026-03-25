from nicegui import ui
from gui.state import state
from projects.projects_io import save_project


def create():

    if not hasattr(state.engine, 'banks'):
        state.engine.banks = []

    current_bank_index = 0 if state.engine.banks else -1

    refs = {
        "bank_tabs": None,
        "scene_grid": None,
    }

    # ── Logik-Funktionen (unverändert) ──────────────────────────────

    def refresh_ui():
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
        save_project(state.engine, "projects/my_show.json")
        current_bank_index = len(state.engine.banks) - 1
        inp_bank_name.value = ""
        refresh_ui()
        ui.notify(f"Bank '{new_bank['name']}' erstellt")

    def delete_current_bank():
        nonlocal current_bank_index
        if current_bank_index == -1: return
        deleted_name = state.engine.banks[current_bank_index]["name"]
        state.engine.banks.pop(current_bank_index)
        save_project(state.engine, "projects/my_show.json")
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
        scene_data = {}
        for fixture in state.engine.fixtures:
            scene_data[fixture.id] = fixture.values.copy()
        new_scene = {
            "name": inp_scene_name.value,
            "data": scene_data,
            "color": inp_scene_color.value
        }
        state.engine.banks[current_bank_index]["scenes"].append(new_scene)
        save_project(state.engine, "projects/my_show.json")
        inp_scene_name.value = ""
        refs["scene_grid"].clear()
        draw_playback_area()
        ui.notify("Szene gespeichert!", color="green")

    def load_scene(scene):
        data = scene["data"]
        for fixture in state.engine.fixtures:
            if fixture.id in data:
                saved_values = data[fixture.id]
                if isinstance(saved_values, dict):
                    for role, val in saved_values.items():
                        fixture.set(role, val)
                elif isinstance(saved_values, (list, tuple)):
                    if hasattr(fixture, 'set_color'):
                        fixture.set_color(saved_values[0], saved_values[1], saved_values[2])

    def delete_scene(scene):
        if current_bank_index == -1: return
        bank = state.engine.banks[current_bank_index]
        if scene in bank["scenes"]:
            bank["scenes"].remove(scene)
            save_project(state.engine, "projects/my_show.json")
            refs["scene_grid"].clear()
            draw_playback_area()
            ui.notify("Szene gelöscht", color="red")

    # ── PROGRAMMER-PANEL ────────────────────────────────────────────
    with ui.element('div').classes('w-full mb-3 border border-[#1e1e28] bg-[#0f0f14] rounded-sm p-3'):
        ui.label('PROGRAMMER').classes('console-label mb-3')

        with ui.row().classes('w-full items-center gap-2 flex-wrap'):
            # Bank erstellen
            inp_bank_name = ui.input() \
                .props('dense dark standout placeholder="Bank Name" color=cyan') \
                .classes('font-mono text-xs').style('max-width:150px;')
            ui.button('+ BANK', on_click=add_bank) \
                .props('dense flat color=cyan') \
                .classes('text-[10px] font-black tracking-widest')
            ui.button('DEL BANK', on_click=delete_current_bank) \
                .props('dense flat color=red') \
                .classes('text-[10px] font-black tracking-widest')

            # Vertikaler Trenner
            ui.element('div').style('width:1px; height:24px; background:#1e1e28; margin:0 6px;')

            # Szene speichern
            inp_scene_name = ui.input() \
                .props('dense dark standout placeholder="Szenen Name" color=cyan') \
                .classes('font-mono text-xs').style('max-width:160px;')
            inp_scene_color = ui.color_input(value='#333333') \
                .props('dense dark').classes('w-20')
            ui.button('SAVE', on_click=save_scene, icon='save') \
                .props('dense push color=green') \
                .classes('text-[10px] font-black tracking-widest')

        # Bank-Tabs
        ui.element('div').style('height:1px; background:#1a1a24; margin:10px 0 6px;')
        refs["bank_tabs"] = ui.tabs() \
            .classes('') \
            .props('dense active-color=cyan indicator-color=cyan align=left')
        refs["bank_tabs"].on_value_change(select_bank)

    # ── PLAYBACK-GRID ────────────────────────────────────────────────
    with ui.row().classes('items-center gap-2 mb-2'):
        ui.label('PLAYBACK').classes('console-label').style('border:none; padding:0;')
        ui.element('div').style('flex:1; height:1px; background:#1a1a24;')

    refs["scene_grid"] = ui.element('div').classes('flex flex-wrap gap-1')

    # ── Zeichenfunktionen ─────────────────────────────────────────────

    def draw_programming_area():
        with refs["bank_tabs"]:
            if not state.engine.banks:
                ui.tab(name=-1, label='KEINE BANKS')
                return
            for i, bank in enumerate(state.engine.banks):
                ui.tab(name=i, label=bank["name"].upper())
            if current_bank_index != -1:
                refs["bank_tabs"].value = current_bank_index

    def _scene_color(scene):
        c = scene.get("color", "#333333")
        if c and c != "#333333":
            return c
        if scene.get("data"):
            vals = list(scene["data"].values())[0]
            if isinstance(vals, dict):
                dim = vals.get("dimmer", 1.0)
                r = int(vals.get("red",   0) * dim * 255)
                g = int(vals.get("green", 0) * dim * 255)
                b = int(vals.get("blue",  0) * dim * 255)
                if r + g + b > 0:
                    return f"rgb({r},{g},{b})"
        return "#2a2a38"

    def draw_playback_area():
        refs["scene_grid"].clear()

        with refs["scene_grid"]:
            if current_bank_index == -1 or not state.engine.banks:
                ui.label('— Keine Bank ausgewählt —') \
                    .classes('text-[10px] font-mono text-[#28283a] tracking-widest uppercase p-6')
                return

            bank = state.engine.banks[current_bank_index]

            if not bank["scenes"]:
                ui.label(f'— {bank["name"]} ist leer —') \
                    .classes('text-[10px] font-mono text-[#28283a] tracking-widest uppercase p-6')
                return

            for i, scene in enumerate(bank["scenes"]):
                color = _scene_color(scene)

                # Exec-Button (GrandMA Stil)
                with ui.element('div').classes('exec-btn group').style('width:100px; height:72px; display:flex; flex-direction:column;') \
                        .on('click', lambda _, s=scene: load_scene(s)):

                    # Farbstreifen oben
                    ui.element('div').style(f'height:3px; background:{color}; width:100%; flex-shrink:0;')

                    # Inhalt
                    with ui.element('div').style('flex:1; padding:5px 6px; display:flex; flex-direction:column; justify-content:space-between; overflow:hidden;'):
                        # Szenenname
                        ui.label(scene["name"]) \
                            .classes('text-[10px] font-bold text-gray-300 leading-tight') \
                            .style('word-break:break-word; overflow:hidden; max-height:32px;') \
                            .tooltip(scene["name"])

                        # Fußzeile: Nummer + Löschen
                        with ui.element('div').style('display:flex; justify-content:space-between; align-items:center;'):
                            ui.label(f'{(i + 1):02d}') \
                                .classes('font-mono text-[8px] text-[#2a2a3c]')

                            ui.button(icon='close') \
                                .props('flat round dense') \
                                .classes('text-[#2a2a3c] hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity') \
                                .style('width:14px; height:14px; font-size:8px;') \
                                .on('click.stop', lambda _, s=scene: delete_scene(s))

    # Initialer Aufruf
    refresh_ui()
