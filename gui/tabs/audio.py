from nicegui import ui
import os
import random
import asyncio
import time
import tkinter as tk
from tkinter import filedialog
from gui.state import state

# ausgelagertes preanalyse audio file importieren
from audio.audio_file import audio_state, analyze_audio_background, toggle_playback, get_current_time

# live audio file importieren
from audio.audio_live import live_audio_state, get_input_devices, start_listening, stop_listening

# magic auto modus
from engine.magic_auto import magic_auto_state, on_beat as magic_on_beat, apply as magic_apply, EFFECT_OPTIONS

# lokaler state für die gui-steuerung
play_settings = {
    "source_mode": "MP3",  # mp3 oder live
    "mode": "Scene Sync",  # 'Scene Sync', 'Custom Timeline'
    "selected_bank": None,
    "current_scene_idx": 0,
    "flash_automatik": True,  # flash automatik als zusätzlich auswählbares overlay
    "custom_timeline": {      # speichert die auswahl für die phasen (als listen für mehrfachauswahl)
        "BREAK": [],
        "BUILDUP": [],
        "DROP": []
    },
    "custom_step_idx": 0,     # zählt die schritte (beats) mit
    "last_active_item": None, # merkt sich den einen effekt, der gerade läuft
    "is_active": False,       # Audio-Modus an/aus (Live-Tab hat Prio wenn False)
}

def create():
    # Header
    with ui.row().classes('w-full items-center justify-between mb-3'):
        ui.label('SOUND TO LIGHT').classes('text-white font-black text-lg tracking-widest')

        def toggle_audio_mode():
            play_settings["is_active"] = not play_settings["is_active"]
            if play_settings["is_active"]:
                audio_toggle_btn.props('color=cyan').set_text('AUDIO MODE: AN')
            else:
                audio_toggle_btn.props('color=grey').set_text('AUDIO MODE: AUS')
                # Alle audio-gesteuerten Events stoppen wenn Audio-Modus aus
                from gui.state import state as _state
                for ev in _state.events:
                    if ev.active and ev.type != "flash":
                        ev.stop(_state.engine)

        audio_toggle_btn = ui.button('AUDIO MODE: AUS', on_click=toggle_audio_mode) \
            .props('color=grey push') \
            .classes('font-black tracking-widest h-10')

    # Audio-Quellschalter — Hardware-Button-Stil
    with ui.element('div').classes('w-full mb-4 border border-[#1e1e28] bg-[#0f0f14] rounded-sm p-3'):
        ui.label('AUDIO QUELLE').classes('console-label mb-3')
        ui.radio(['MP3', 'LIVE'], value='MP3').bind_value(play_settings, 'source_mode') \
            .props('inline dark color=cyan')

    with ui.row().classes('w-full gap-8 items-start'):
        
        # links: datei- auswahl und analyse oder live input
        with ui.card().classes('w-5/12 bg-gray-900 border border-gray-700 p-6'):
            
            # datei einfügen bereich
            with ui.column().bind_visibility_from(play_settings, 'source_mode', lambda m: m == 'MP3').classes('w-full'):
                ui.label('1. Pre-Analysis (MP3/WAV)').classes('text-xl font-bold text-gray-200 mb-4')
                
                status_label = ui.label('Warte auf Audio-Datei...').classes('text-gray-400 text-sm mb-4')
                bpm_label = ui.label('BPM: --').classes('text-lg font-bold text-purple-400 mb-4')
                
                def on_analyze_success():
                    filename = os.path.basename(audio_state['file_path'])
                    status_label.set_text(f"Bereit: {filename}")
                    status_label.classes('text-green-400', remove='text-yellow-400 text-gray-400 text-red-500')
                    bpm_label.set_text(f"BPM: {audio_state['bpm']:.1f}")
                    play_btn.enable()
                    ui.notify("Analyse abgeschlossen!", color="green")

                def on_analyze_error(err_msg):
                    status_label.set_text(f"Fehler: {err_msg}")
                    status_label.classes('text-red-500', remove='text-yellow-400 text-gray-400 text-green-400')
                    ui.notify("Fehler bei der Analyse", color="red")

                async def open_file_picker():
                    def dialog():
                        root = tk.Tk()
                        root.withdraw()
                        root.attributes('-topmost', True)
                        path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav *.ogg *.flac")])
                        root.destroy()
                        return path

                    file_path = await asyncio.to_thread(dialog)
                    
                    if file_path:
                        status_label.set_text("Analysiere... Bitte warten!")
                        status_label.classes('text-yellow-400', remove='text-gray-400 text-green-400 text-red-500')
                        play_btn.disable()
                        analyze_audio_background(file_path, on_analyze_success, on_analyze_error)

                ui.button('DATEI AUSWÄHLEN', on_click=open_file_picker, icon='folder').classes('w-full h-12 text-lg font-bold').props('color=cyan push')

            # live input
            with ui.column().bind_visibility_from(play_settings, 'source_mode', lambda m: m == 'LIVE').classes('w-full'):
                ui.label('1. Live Input (Soundkarte/USB)').classes('text-xl font-bold text-gray-200 mb-4')
                
                # reihe mit dropdown und refresh button (geräteliste-->nur inoputs)
                with ui.row().classes('w-full items-center gap-2 mb-4'):
                    devices = get_input_devices()
                    device_dropdown = ui.select(devices, label='Audio Eingang', value=list(devices.keys())[0] if devices else None).props('dark color=cyan standout').classes('flex-grow')
                    
                    def refresh_devices():
                        new_devices = get_input_devices()
                        device_dropdown.options = new_devices
                        # Falls das vorher gewählte Gerät weg ist, wähle das Erste
                        if new_devices and device_dropdown.value not in new_devices:
                            device_dropdown.value = list(new_devices.keys())[0]
                        device_dropdown.update()
                        ui.notify('Geräteliste aktualisiert!', color='green')
                        
                    ui.button(icon='refresh', on_click=refresh_devices).props('color=cyan outline').classes('h-14 w-14')
                
                
                # duales Vvu meter (lautstärke und beat erkennung)
                ui.label('Audio Signal (Roh-Pegel DJM):').classes('text-xs text-gray-400 mb-1')
                vol_meter = ui.linear_progress(value=0.0).props('color=blue track-color=gray-800 size=12px').classes('w-full mb-2 rounded')
                
                ui.label('Beat Erkennung (Schlägt rot an bei Trigger):').classes('text-xs text-gray-400 mb-1')
                vu_meter = ui.linear_progress(value=0.0).props('color=green track-color=gray-800 size=12px').classes('w-full mb-4 rounded')
                

                ui.label('Sensitivität (Schwelle)').classes('text-xs text-gray-400')
                ui.slider(min=1.0, max=8.0, step=0.1).bind_value(live_audio_state, 'sensitivity').props('dark color=purple label-always').classes('mb-4')
                
                status_live = ui.label('Status: Getrennt').classes('text-gray-400 text-sm mb-4')
                
                def toggle_live():
                    if not live_audio_state["is_listening"]:
                        if device_dropdown.value is None:
                            ui.notify('Bitte erst ein Gerät wählen!', color='red')
                            return
                        success, msg = start_listening(device_dropdown.value)
                        if success:
                            btn_live.props('color=red').set_text('TRENNEN')
                            status_live.set_text('Status: Verbunden (Höre zu...)').classes('text-green-400', remove='text-gray-400')
                        else:
                            ui.notify(f'Fehler: {msg}', color='red')
                    else:
                        stop_listening()
                        btn_live.props('color=green').set_text('VERBINDEN')
                        status_live.set_text('Status: Getrennt').classes('text-gray-400', remove='text-green-400')
                        vu_meter.value = 0.0 # balken zurücksetzen
                        vol_meter.value = 0.0

                btn_live = ui.button('VERBINDEN', on_click=toggle_live).classes('w-full h-12 text-lg font-bold').props('color=green push')

        # rechts: playback und moduswahl
        with ui.element('div').classes('w-6/12 border border-[#1e1e28] bg-[#0f0f14] rounded-sm p-4'):
            ui.label('SHOW STEUERUNG').classes('console-label mb-3')

            # LCD-Anzeigen: Phase + Beat
            with ui.row().classes('w-full gap-2 mb-4'):
                with ui.column().classes('gap-1'):
                    ui.label('PHASE').classes('console-label').style('border:none; padding:0;')
                    lbl_state = ui.label('WARTEN') \
                        .classes('lcd-display text-xl font-black tracking-widest phase-wait') \
                        .style('min-width:130px; border-radius:2px; padding:4px 10px; border:1px solid #1a1a2a;')

                with ui.column().classes('gap-1'):
                    ui.label('BEAT / TAKT').classes('console-label').style('border:none; padding:0;')
                    lbl_beat = ui.label('-- / --') \
                        .classes('lcd-display text-xl font-black tracking-widest') \
                        .style('min-width:110px; border-radius:2px; padding:4px 10px; border:1px solid #1a1a2a;')
            
            # hauptmodus
            ui.label('Live-Modus (Basis-Licht):').classes('text-sm text-gray-400 font-bold mt-2')
            ui.radio(['Scene Sync', 'Custom Timeline', 'Magic Auto'], value='Scene Sync').bind_value(play_settings, 'mode').props('inline dark color=cyan').classes('mb-2')
            
            # bank auswahl für szenen sync
            with ui.column().bind_visibility_from(play_settings, 'mode', lambda m: m == 'Scene Sync').classes('w-full bg-gray-800 p-3 rounded mb-4 border border-gray-600'):
                ui.label('Bank für den Beat-Chaser auswählen:').classes('text-xs text-gray-400')
                
                bank_names = [bank["name"] for bank in state.engine.banks] if state.engine.banks else []
                if bank_names:
                    if play_settings["selected_bank"] not in bank_names:
                        play_settings["selected_bank"] = bank_names[0]
                    ui.select(bank_names, label='Bank').bind_value(play_settings, 'selected_bank').props('dark color=cyan standout').classes('w-full')
                else:
                    ui.label('Keine Bänke gefunden! Erstelle erst eine im Live-Tab.').classes('text-red-400 text-sm font-bold')

            # custom timeline auswahl (mehrfachauswahl)
            with ui.column().bind_visibility_from(play_settings, 'mode', lambda m: m == 'Custom Timeline').classes('w-full bg-gray-800 p-3 rounded mb-4 border border-gray-600'):
                ui.label('Weise den Phasen Bänke und Effekte zu (Mehrfachauswahl möglich):').classes('text-xs text-gray-400 mb-2')
                
                combo_options = []
                if state.engine.banks:
                    for b in state.engine.banks: combo_options.append(f"Bank: {b['name']}")
                if state.events:
                    for e in state.events: 
                        if e.type != "stop_all": combo_options.append(f"Event: {e.name}")
                        
                with ui.row().classes('w-full items-center gap-2 mb-2'):
                    ui.label('BREAK').classes('w-16 text-blue-400 font-bold text-sm')
                    ui.select(combo_options, multiple=True, value=play_settings["custom_timeline"]["BREAK"]).bind_value(play_settings["custom_timeline"], "BREAK").props('dark color=cyan standout dense use-chips').classes('flex-grow')
                    
                with ui.row().classes('w-full items-center gap-2 mb-2'):
                    ui.label('BUILDUP').classes('w-16 text-orange-400 font-bold text-sm')
                    ui.select(combo_options, multiple=True, value=play_settings["custom_timeline"]["BUILDUP"]).bind_value(play_settings["custom_timeline"], "BUILDUP").props('dark color=cyan standout dense use-chips').classes('flex-grow')
                    
                with ui.row().classes('w-full items-center gap-2'):
                    ui.label('DROP').classes('w-16 text-red-500 font-bold text-sm')
                    ui.select(combo_options, multiple=True, value=play_settings["custom_timeline"]["DROP"]).bind_value(play_settings["custom_timeline"], "DROP").props('dark color=cyan standout dense use-chips').classes('flex-grow')

            # --- MAGIC AUTO MODUS ---
            with ui.column().bind_visibility_from(play_settings, 'mode', lambda m: m == 'Magic Auto').classes('w-full bg-gray-800 p-3 rounded mb-2 border border-yellow-700 gap-2'):
                ui.label('MAGIC AUTO - Light DJ').classes('text-sm font-bold text-yellow-400')

                # --- AUTOMATIK ---
                ui.label('AUTOMATIK').classes('text-xs text-gray-400 font-bold mt-1')
                with ui.column().classes('w-full bg-gray-900 p-2 rounded border border-gray-600 gap-1'):
                    ui.checkbox('Effekte automatisch wechseln (nach Phase)', value=True).bind_value(magic_auto_state, 'auto_effects').classes('text-gray-200 text-xs')

                    with ui.row().classes('w-full items-center gap-3').bind_visibility_from(magic_auto_state, 'auto_effects'):
                        ui.label('Wechsel alle').classes('text-gray-400 text-xs whitespace-nowrap')
                        ui.slider(min=1, max=32, step=1).bind_value(magic_auto_state, 'effect_change_beats').props('dark color=yellow label-always').classes('flex-grow')
                        ui.label('Beats').classes('text-gray-400 text-xs whitespace-nowrap')

                # --- FARBE ---
                ui.label('FARBE').classes('text-xs text-gray-400 font-bold mt-2')

                # Farbpaletten-Auswahl
                from engine.magic_auto import COLOR_PALETTES
                ui.select(
                    options=list(COLOR_PALETTES.keys()),
                    value='Club',
                    label='Palette'
                ).bind_value(magic_auto_state, 'color_palette').props('dark color=cyan standout dense').classes('w-full mb-1')

                # Farbvorschau-Box (zeigt Custom-Farbe oder Palette)
                color_preview = ui.element('div').style(
                    'width: 100%; height: 20px; border-radius: 6px; '
                    'background: rgb(51, 0, 255); border: 1px solid #555;'
                )

                # Custom-Slider (nur sichtbar wenn Palette = Custom)
                with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-0').bind_visibility_from(magic_auto_state, 'color_palette', lambda v: v == 'Custom'):
                    ui.label('Rot').classes('text-red-400 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'red').props('dark color=red label-always')

                    ui.label('Gruen').classes('text-green-400 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'green').props('dark color=green label-always')

                    ui.label('Blau').classes('text-blue-400 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'blue').props('dark color=blue label-always')

                    ui.label('Weiss').classes('text-gray-200 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'white').props('dark color=white label-always')

                # --- INTENSITAET ---
                ui.label('INTENSITAET').classes('text-xs text-gray-400 font-bold mt-2')
                with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-0'):
                    ui.label('Helligkeit').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'brightness').props('dark color=yellow label-always')

                    ui.label('Beat-Blinder').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'blinder_strength').props('dark color=orange label-always')

                    ui.label('Abklingen').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'fade').props('dark color=purple label-always').tooltip('0 = Blinder-Flash sofort weg, 1 = langes Nachleuchten')

                    ui.label('Strobe').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'strobe_amount').props('dark color=white label-always')

                # --- UEBERBLEND ---
                ui.label('UEBERBLEND').classes('text-xs text-gray-400 font-bold mt-2')
                with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-0'):
                    ui.label('Farb-Fade').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'color_fade').props('dark color=teal label-always').tooltip('0 = harter Farbwechsel, 1 = weiches Ineinanderfaden')

                # --- BLACKOUT ---
                ui.label('BLACKOUT').classes('text-xs text-gray-400 font-bold mt-2')
                with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-0'):
                    ui.label('Alle N Beats').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0, max=32, step=1).bind_value(magic_auto_state, 'blackout_interval').props('dark color=red label-always').tooltip('0 = nie, z.B. 8 = alle 8 Beats ein Blackout')

                    ui.label('Dauer (sek)').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0.05, max=2.0, step=0.05).bind_value(magic_auto_state, 'blackout_duration').props('dark color=red-4 label-always')

                # --- EFFEKT (manuell, nur wenn auto_effects=False) ---
                with ui.column().classes('w-full gap-1').bind_visibility_from(magic_auto_state, 'auto_effects', lambda v: not v):
                    ui.label('EFFEKT (manuell)').classes('text-xs text-gray-400 font-bold mt-2')
                    effect_select = ui.select(
                        options=list(EFFECT_OPTIONS.keys()),
                        value='Keiner'
                    ).props('dark color=cyan standout dense').classes('w-full')

                    def on_effect_change(e):
                        magic_auto_state['effect'] = EFFECT_OPTIONS.get(e.value, 'none')
                        magic_auto_state['_effect_start'] = time.time()

                    effect_select.on_value_change(on_effect_change)

                with ui.row().classes('w-full items-center gap-3 mt-1'):
                    ui.label('Max Geschw.').classes('text-gray-300 text-xs whitespace-nowrap')
                    ui.slider(min=0.1, max=5.0, step=0.1).bind_value(magic_auto_state, 'effect_speed').props('dark color=cyan label-always').classes('flex-grow')

                ui.separator().classes('bg-gray-600')
                ui.checkbox('Phasen-Reaktion (BREAK / BUILDUP / DROP)', value=True).bind_value(magic_auto_state, 'phase_react').classes('text-gray-300 text-xs')

                # Timer fuer Farbvorschau-Update
                def update_color_preview():
                    palette_name = magic_auto_state['color_palette']
                    if palette_name != 'Custom':
                        from engine.magic_auto import COLOR_PALETTES as CP
                        palette = CP.get(palette_name)
                        if palette:
                            cidx = magic_auto_state['_color_idx'] % len(palette)
                            pr, pg, pb, _ = palette[cidx]
                            r_v, g_v, b_v = int(pr * 255), int(pg * 255), int(pb * 255)
                        else:
                            r_v = g_v = b_v = 128
                    else:
                        r_v = int(magic_auto_state['red'] * 255)
                        g_v = int(magic_auto_state['green'] * 255)
                        b_v = int(magic_auto_state['blue'] * 255)
                    color_preview.style(
                        f'width: 100%; height: 20px; border-radius: 6px; '
                        f'background: rgb({r_v},{g_v},{b_v}); border: 1px solid #555;'
                    )

                ui.timer(0.1, update_color_preview)

            # overlay flash- automatik
            ui.separator().classes('bg-gray-700 my-2')
            ui.checkbox('Flash Automatik zuschalten (Magic Mode)', value=True).bind_value(play_settings, 'flash_automatik').bind_visibility_from(play_settings, 'mode', lambda m: m != 'Magic Auto').classes('mb-4 text-yellow-400 font-bold')

            # takt korrektur (nur bei mp3)
            with ui.row().classes('gap-4 mb-6').bind_visibility_from(play_settings, 'source_mode', lambda m: m == 'MP3'):
                def shift_backward(): audio_state["beat_offset"] = (audio_state["beat_offset"] - 1) % 4
                def shift_forward(): audio_state["beat_offset"] = (audio_state["beat_offset"] + 1) % 4
                
                ui.button('< Takt verschieben', on_click=shift_backward).props('outline color=info')
                ui.button('Takt verschieben >', on_click=shift_forward).props('outline color=info')

            def ui_toggle_playback():
                toggle_playback()
                if audio_state["is_playing"]:
                    play_btn.props('color=red').set_text('STOP MP3')
                else:
                    play_btn.props('color=green').set_text('PLAY MP3')
                    lbl_state.set_text("Phase: GESTOPPT")
                    lbl_beat.set_text("Beat: -- | Takt: --")

            play_btn = ui.button('PLAY MP3', on_click=ui_toggle_playback).props('color=green push').classes('w-full h-16 text-xl font-bold tracking-widest')
            play_btn.bind_visibility_from(play_settings, 'source_mode', lambda m: m == 'MP3')
            play_btn.disable()

            # licht trigger funktion (wird von mp3 und live modus geteilt)
            def trigger_lights(beat_in_bar, phase):
                if not play_settings["is_active"]:
                    return
                # Wenn ein Flash/Blinder gerade aktiv ist, Scene-Sync überspringen
                # damit der Blinder nicht durch eine neue Szene übersch rieben wird
                flash_running = any(e.active for e in state.events if e.type == "flash")
                if flash_running:
                    return
                
                # modus 1 scene sync (szenen wechseln auf den beat)
                if play_settings["mode"] == "Scene Sync" and play_settings["selected_bank"]:
                    selected_bank = next((b for b in state.engine.banks if b["name"] == play_settings["selected_bank"]), None)
                    
                    if selected_bank and selected_bank["scenes"]:
                        play_settings["current_scene_idx"] = (play_settings["current_scene_idx"] + 1) % len(selected_bank["scenes"])
                        scene_to_load = selected_bank["scenes"][play_settings["current_scene_idx"]]
                        
                        data = scene_to_load.get("data", {})
                        for f in state.engine.fixtures:
                            if f.id in data:
                                for k, v in data[f.id].items():
                                    f.set(k, v)
                                    
                # modus zwei custom timeline (wenn länger in einer phase wechseln wenn eingestellt mehrere events immer jedes bar auf den 1. beat)
                elif play_settings["mode"] == "Custom Timeline":
                    active_phase = phase if phase else "DROP"
                    current_selections = play_settings["custom_timeline"].get(active_phase, [])
                    
                    if not current_selections:
                        if play_settings.get("last_active_item") and play_settings["last_active_item"].startswith("Event: "):
                            ev_name = play_settings["last_active_item"].replace("Event: ", "")
                            old_ev = next((e for e in state.events if e.name == ev_name), None)
                            if old_ev and old_ev.active: old_ev.stop(state.engine)
                        play_settings["last_active_item"] = None
                    else:
                        # 1. nur auf den taktanfang 1.beat den nächsten effekt in der liste wählen
                        if beat_in_bar == 1:
                            play_settings["custom_step_idx"] = (play_settings["custom_step_idx"] + 1) % len(current_selections)
                        
                        if play_settings["custom_step_idx"] >= len(current_selections):
                            play_settings["custom_step_idx"] = 0
                            
                        active_item = current_selections[play_settings["custom_step_idx"]]
                        
                        # 2. alten effekt stoppen
                        if play_settings.get("last_active_item") != active_item:
                            old_item = play_settings.get("last_active_item")
                            if old_item and old_item.startswith("Event: "):
                                old_ev = next((e for e in state.events if e.name == old_item.replace("Event: ", "")), None)
                                if old_ev and old_ev.active:
                                    old_ev.stop(state.engine)
                            play_settings["last_active_item"] = active_item

                        # 3. aktives element für diesen takt steuern
                        if active_item.startswith("Event: "):
                            ev_name = active_item.replace("Event: ", "")
                            active_ev = next((e for e in state.events if e.name == ev_name), None)
                            if active_ev:
                                if active_ev.type == "flash":
                                    if active_ev.active: active_ev.stop(state.engine)
                                    active_ev.start(state.engine)
                                elif not active_ev.active:
                                    active_ev.start(state.engine)
                                    
                        elif active_item.startswith("Bank: "):
                            bank_name = active_item.replace("Bank: ", "")
                            selected_bank = next((b for b in state.engine.banks if b["name"] == bank_name), None)
                            if selected_bank and selected_bank["scenes"]:
                                play_settings["current_scene_idx"] = (play_settings["current_scene_idx"] + 1) % len(selected_bank["scenes"])
                                scene_to_load = selected_bank["scenes"][play_settings["current_scene_idx"]]
                                data = scene_to_load.get("data", {})
                                for f in state.engine.fixtures:
                                    if f.id in data:
                                        for k, v in data[f.id].items():
                                            f.set(k, v)

                # modus 3 magic auto (beat-trigger)
                elif play_settings["mode"] == "Magic Auto":
                    magic_on_beat(phase)

                # flash automatik overlay
                if play_settings["flash_automatik"] and play_settings["mode"] != "Magic Auto":
                    flash_events = [e for e in state.events if e.type == "flash"]
                    if flash_events:
                        if phase == "DROP" or beat_in_bar == 1:
                            for e in flash_events:
                                if e.active: e.stop(state.engine)
                            random_flash = random.choice(flash_events)
                            random_flash.start(state.engine)

            # ticker und lichttrigger (100 mal pro sekunde)
            def audio_ticker():
                if not play_settings["is_active"]:
                    return
                if play_settings["source_mode"] == "MP3":
                    elapsed_time = get_current_time()
                    if elapsed_time == 0.0: return
                    
                    # 1.beat erkennung mp3
                    b_idx = audio_state["current_beat_idx"]
                    if b_idx < len(audio_state["beat_times"]) and elapsed_time >= audio_state["beat_times"][b_idx]:
                        beat_in_bar = ((b_idx + audio_state["beat_offset"]) % 4) + 1
                        lbl_beat.set_text(f"{b_idx + 1:04d}  /{beat_in_bar}/4")
                        
                        if beat_in_bar == 1: 
                            lbl_beat.classes('text-purple-400 font-bold', remove='text-gray-300')
                        else: 
                            lbl_beat.classes('text-gray-300', remove='text-purple-400 font-bold')
                            
                        trigger_lights(beat_in_bar, audio_state["last_state"])
                        audio_state["current_beat_idx"] += 1

                    # 2.struktur erkennung mp3
                    f_idx = audio_state["current_frame_idx"]
                    while f_idx < len(audio_state["frames_times"]) and audio_state["frames_times"][f_idx] < elapsed_time:
                        f_idx += 1
                        audio_state["current_frame_idx"] = f_idx
                        
                    if f_idx < len(audio_state["structure"]):
                        current_state = audio_state["structure"][f_idx]
                        
                        if current_state != audio_state["last_state"]:
                            lbl_state.set_text(current_state)
                            if current_state == "DROP":
                                lbl_state.classes('phase-drop', remove='phase-buildup phase-break phase-wait')
                            elif current_state == "BUILDUP":
                                lbl_state.classes('phase-buildup', remove='phase-drop phase-break phase-wait')
                            else:
                                lbl_state.classes('phase-break', remove='phase-drop phase-buildup phase-wait')
                                
                            audio_state["last_state"] = current_state

                elif play_settings["source_mode"] == "LIVE":
                    if not live_audio_state["is_listening"]: return

                    # 1. gesamtlautstärke (blauer balken)
                    # vu meter updaten
                    vol_meter.value = live_audio_state.get("volume", 0.0)
                    
                    # 2. beat trigger (grün-rot)
                    # zeigt das verhältnis vom bass zur eingestellten schwelle (über sensitivitätsslider)
                    # erreicht der wert 1.0, blinkt der balken rot und das licht wird abgefeuert (bspw. neue szene)
                    beat_confidence = min(live_audio_state.get("level", 0.0), 1.0)
                    vu_meter.value = beat_confidence
                    
                    if beat_confidence > 0.8:
                        vu_meter.props('color=red track-color=gray-800 size=12px')
                    else:
                        vu_meter.props('color=green track-color=gray-800 size=12px')
                    

                    # phase kommt jetzt live aus der audio_live.py erkennung
                    live_phase = live_audio_state.get("phase", "DROP")
                    
                    lbl_state.set_text(live_phase)
                    if live_phase == "DROP":
                        lbl_state.classes('phase-drop', remove='phase-buildup phase-break phase-wait')
                    elif live_phase == "BUILDUP":
                        lbl_state.classes('phase-buildup', remove='phase-drop phase-break phase-wait')
                    else:
                        lbl_state.classes('phase-break', remove='phase-drop phase-buildup phase-wait')

                    # beat aus der live berechnung
                    if live_audio_state["beat_triggered"]:
                        live_audio_state["beat_triggered"] = False
                        beat_in_bar = live_audio_state["beat_index"] + 1

                        lbl_beat.set_text(f"LIVE Beat   |   Takt: {beat_in_bar} / 4")
                        if beat_in_bar == 1:
                            lbl_beat.classes('text-purple-400 font-bold', remove='text-gray-300')
                        else:
                            lbl_beat.classes('text-gray-300', remove='text-purple-400 font-bold')

                        # echte live phase an den trigger übergeben
                        trigger_lights(beat_in_bar, live_phase)

            def magic_auto_ticker():
                """Kontinuierlicher 100 Hz Update fuer Magic Auto (smooth fading, strobe, effekte)."""
                if not play_settings["is_active"]:
                    return
                if play_settings["mode"] != "Magic Auto":
                    return
                if play_settings["source_mode"] == "MP3":
                    if not audio_state.get("is_playing", False):
                        return
                    phase = audio_state.get("last_state", "DROP")
                else:
                    if not live_audio_state["is_listening"]:
                        return
                    phase = live_audio_state.get("phase", "DROP")
                magic_apply(state.engine, phase)

            ui.timer(0.01, audio_ticker)
            ui.timer(0.01, magic_auto_ticker)