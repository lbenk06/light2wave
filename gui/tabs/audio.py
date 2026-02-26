from nicegui import ui
import os
import random
import asyncio
import tkinter as tk
from tkinter import filedialog
from gui.state import state

# ausgelagertes preanalyse audio file importieren
from audio.audio_file import audio_state, analyze_audio_background, toggle_playback, get_current_time

# live audio file importieren
from audio.audio_live import live_audio_state, get_input_devices, start_listening, stop_listening

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
    "last_active_item": None  # merkt sich den einen effekt, der gerade läuft
}

def create():
    ui.label('SOUND TO LIGHT & SHOWS').classes('text-h4 text-white mb-4')

    # audio quellen auswahl
    with ui.row().classes('w-full items-center mb-6 bg-gray-800 p-2 rounded border border-gray-600'):
        ui.label('Audio Quelle:').classes('text-lg font-bold text-gray-300 mr-4')
        ui.radio(['MP3', 'LIVE'], value='MP3').bind_value(play_settings, 'source_mode').props('inline dark color=cyan')

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
        with ui.card().classes('w-6/12 bg-gray-900 border border-gray-700 p-6'):
            ui.label('2. Show Steuerung').classes('text-xl font-bold text-gray-200 mb-4')
            
            lbl_state = ui.label("Phase: WARTEN").classes("text-2xl font-black text-blue-400 mb-2")
            lbl_beat = ui.label("Beat: -- | Takt: --").classes("text-lg text-gray-300 mb-4")
            
            # hauptmodus
            ui.label('Live-Modus (Basis-Licht):').classes('text-sm text-gray-400 font-bold mt-2')
            ui.radio(['Scene Sync', 'Custom Timeline'], value='Scene Sync').bind_value(play_settings, 'mode').props('inline dark color=cyan').classes('mb-2')
            
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

            # overlay flash- automatik
            ui.separator().classes('bg-gray-700 my-2')
            ui.checkbox('⚡ Flash Automatik zuschalten (Magic Mode)', value=True).bind_value(play_settings, 'flash_automatik').classes('mb-4 text-yellow-400 font-bold')

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

                # flash automatik overlay
                if play_settings["flash_automatik"]:
                    flash_events = [e for e in state.events if e.type == "flash"]
                    if flash_events:
                        if phase == "DROP" or beat_in_bar == 1:
                            for e in flash_events:
                                if e.active: e.stop(state.engine)
                            random_flash = random.choice(flash_events)
                            random_flash.start(state.engine)

            # ticker und lichttrigger (100 mal pro sekunde)
            def audio_ticker():
                if play_settings["source_mode"] == "MP3":
                    elapsed_time = get_current_time()
                    if elapsed_time == 0.0: return
                    
                    # 1.beat erkennung mp3
                    b_idx = audio_state["current_beat_idx"]
                    if b_idx < len(audio_state["beat_times"]) and elapsed_time >= audio_state["beat_times"][b_idx]:
                        beat_in_bar = ((b_idx + audio_state["beat_offset"]) % 4) + 1
                        lbl_beat.set_text(f"Beat total: {b_idx + 1}   |   Takt: {beat_in_bar} / 4")
                        
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
                            lbl_state.set_text(f"Phase: {current_state}")
                            if current_state == "DROP": 
                                lbl_state.classes('text-red-500', remove='text-orange-400 text-blue-400')
                            elif current_state == "BUILDUP": 
                                lbl_state.classes('text-orange-400', remove='text-red-500 text-blue-400')
                            else: 
                                lbl_state.classes('text-blue-400', remove='text-red-500 text-orange-400')
                                
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
                    
                    lbl_state.set_text(f"Phase: {live_phase} (Live)")
                    if live_phase == "DROP": 
                        lbl_state.classes('text-red-500', remove='text-orange-400 text-blue-400')
                    elif live_phase == "BUILDUP": 
                        lbl_state.classes('text-orange-400', remove='text-red-500 text-blue-400')
                    else: 
                        lbl_state.classes('text-blue-400', remove='text-red-500 text-orange-400')

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

            ui.timer(0.01, audio_ticker)