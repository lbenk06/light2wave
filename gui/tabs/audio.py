from nicegui import ui
import os
import random
import asyncio
import tkinter as tk
from tkinter import filedialog
from gui.state import state

# Ausgelagertes Preanalyse audio file importieren
from audio.audio_file import audio_state, analyze_audio_background, toggle_playback, get_current_time

# Lokaler State für die GUI-Steuerung
play_settings = {
    "mode": "Scene Sync",  # 'Scene Sync', 'Custom Timeline'
    "selected_bank": None,
    "current_scene_idx": 0,
    "flash_automatik": True  # flash automatik als zusätzlich auswählbares overlay
}

def create():
    ui.label('SOUND TO LIGHT & SHOWS').classes('text-h4 text-white mb-6')

    with ui.row().classes('w-full gap-8 items-start'):
        
        # links: datei- auswahl und analyse
        with ui.card().classes('w-5/12 bg-gray-900 border border-gray-700 p-6'):
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

            # overlay flash- automatik
            ui.separator().classes('bg-gray-700 my-2')
            ui.checkbox('⚡ Flash Automatik zuschalten (Magic Mode)', value=True).bind_value(play_settings, 'flash_automatik').classes('mb-4 text-yellow-400 font-bold')

            # takt korrektur
            with ui.row().classes('gap-4 mb-6'):
                def shift_backward(): audio_state["beat_offset"] = (audio_state["beat_offset"] - 1) % 4
                def shift_forward(): audio_state["beat_offset"] = (audio_state["beat_offset"] + 1) % 4
                
                ui.button('< Takt verschieben', on_click=shift_backward).props('outline color=info')
                ui.button('Takt verschieben >', on_click=shift_forward).props('outline color=info')

            def ui_toggle_playback():
                toggle_playback()
                if audio_state["is_playing"]:
                    play_btn.props('color=red').set_text('STOP')
                else:
                    play_btn.props('color=green').set_text('PLAY')
                    lbl_state.set_text("Phase: GESTOPPT")
                    lbl_beat.set_text("Beat: -- | Takt: --")

            play_btn = ui.button('PLAY', on_click=ui_toggle_playback).props('color=green push').classes('w-full h-16 text-xl font-bold tracking-widest')
            play_btn.disable()

            # ticker und lichttrigger (100 mal pro sekunde)
            def audio_ticker():
                elapsed_time = get_current_time()
                if elapsed_time == 0.0: return
                
                # 1.beat erkennung
                b_idx = audio_state["current_beat_idx"]
                if b_idx < len(audio_state["beat_times"]) and elapsed_time >= audio_state["beat_times"][b_idx]:
                    beat_in_bar = ((b_idx + audio_state["beat_offset"]) % 4) + 1
                    lbl_beat.set_text(f"Beat total: {b_idx + 1}   |   Takt: {beat_in_bar} / 4")
                    
                    if beat_in_bar == 1: 
                        lbl_beat.classes('text-purple-400 font-bold', remove='text-gray-300')
                    else: 
                        lbl_beat.classes('text-gray-300', remove='text-purple-400 font-bold')
                        
                    # schicht 1: basis licht (szenen sync)
                    if play_settings["mode"] == "Scene Sync" and play_settings["selected_bank"]:
                        selected_bank = next((b for b in state.engine.banks if b["name"] == play_settings["selected_bank"]), None)
                        
                        if selected_bank and selected_bank["scenes"]:
                            # bei jedem beat eine szene weiter springen
                            play_settings["current_scene_idx"] = (play_settings["current_scene_idx"] + 1) % len(selected_bank["scenes"])
                            scene_to_load = selected_bank["scenes"][play_settings["current_scene_idx"]]
                            
                            data = scene_to_load.get("data", {})
                            for f in state.engine.fixtures:
                                if f.id in data:
                                    for k, v in data[f.id].items():
                                        f.set(k, v)
                                        
                    # schicht 2: flash automatik (overlay)
                    if play_settings["flash_automatik"]:
                        flash_events = [e for e in state.events if e.type == "flash"]
                        if flash_events:
                            # flashes und blinder nur beim drop bzw. 1. beat im takt auslösen
                            if audio_state["last_state"] == "DROP" or beat_in_bar == 1:
                                for e in flash_events:
                                    if e.active: e.stop(state.engine)
                                random_flash = random.choice(flash_events)
                                random_flash.start(state.engine)
                                
                    audio_state["current_beat_idx"] += 1

                # 2.struktur erkennung (Drop, Buildup, Break)
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

            # timer für die ui und lichttrigger
            ui.timer(0.01, audio_ticker)