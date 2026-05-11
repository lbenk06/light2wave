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
from audio.audio_live import (
    live_audio_state, get_input_devices, start_listening, stop_listening,
    set_mode as live_set_mode, set_manual_bpm as live_set_manual_bpm,
    mark_downbeat as live_mark_downbeat, set_input_gain as live_set_input_gain,
)

# pro dj link (pioneer cdj netzwerk) importieren
from audio.prolink_source import (
    start_prolink, stop_prolink, is_running as prolink_running, backend_label,
)

# magic auto modus
from engine.magic_auto import magic_auto_state, on_beat as magic_on_beat, on_transient as magic_on_transient, apply as magic_apply, EFFECT_OPTIONS

# sunset groove (Freiluftfrequenz / outdoor chill)
from engine.sunset_groove import (
    sunset_state,
    on_beat as sunset_on_beat,
    tick     as sunset_tick,
    reset    as sunset_reset,
)

# virtual light dj
from engine.light_dj import (
    VirtualLightDJ, PHASE_PALETTE, PALETTE_AUTO,
    get_all_palettes, save_custom_palette,
)
_vldj = VirtualLightDJ()

# lokaler state für die gui-steuerung
play_settings = {
    "source_mode": "MP3",  # mp3 oder live
    "mode": "Scene Sync",  # 'Scene Sync', 'Custom Timeline'
    "selected_bank": None,
    "current_scene_idx": 0,
    "flash_automatik":        True,        # flash automatik overlay
    "flash_drop_mode":        "interval",  # "interval" | "on_enter"
    "flash_drop_interval":    1,           # alle N Beats im Drop
    "flash_buildup_mode":     "off",       # "off" | "interval" | "on_enter"
    "flash_buildup_interval": 4,
    "flash_break_mode":       "off",       # "off" | "interval" | "on_enter"
    "flash_break_interval":   8,
    "_flash_drop_count":      0,
    "_flash_buildup_count":   0,
    "_flash_break_count":     0,
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
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('AUDIO QUELLE').classes('console-label')
            prolink_status_chip = ui.label('ProLink: offline') \
                .classes('text-[10px] font-mono text-gray-500 px-2 py-0.5 rounded') \
                .style('background:#0a0a14; border:1px solid #1a1a2a;')

        def _on_source_change(e):
            # Beim Wechsel WEG vom ProLink-Modus: Listener stoppen → Netzwerk-Last + Threads frei
            if e.value != 'PROLINK' and prolink_running():
                stop_prolink()
            # Beim Wechsel WEG vom LIVE-Modus: Mic-Stream + ML stoppen
            if e.value != 'LIVE' and live_audio_state.get('is_listening'):
                stop_listening()

        ui.radio(['MP3', 'LIVE', 'PROLINK'], value='MP3').bind_value(play_settings, 'source_mode') \
            .props('inline dark color=cyan').on_value_change(_on_source_change)

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
                ui.label('1. Live Input (Soundkarte/USB)').classes('text-xl font-bold text-gray-200 mb-3')

                # ═════════ SIGNAL ═════════════════════════════════════════
                ui.label('SIGNAL').classes('text-[10px] tracking-widest text-cyan-400 font-bold mb-1')

                with ui.row().classes('w-full items-center gap-2 mb-3'):
                    devices = get_input_devices()
                    device_dropdown = ui.select(
                        devices, label='Audio Eingang',
                        value=list(devices.keys())[0] if devices else None
                    ).props('dark color=cyan standout dense').classes('flex-grow')

                    def refresh_devices():
                        new_devices = get_input_devices()
                        device_dropdown.options = new_devices
                        if new_devices and device_dropdown.value not in new_devices:
                            device_dropdown.value = list(new_devices.keys())[0]
                        device_dropdown.update()
                        ui.notify('Geraeteliste aktualisiert', color='green')

                    ui.button(icon='refresh', on_click=refresh_devices) \
                        .props('color=cyan outline').classes('h-10 w-10')

                # Eingangs-Pegel (vol_meter) — bleibt, audio_ticker fuellt ihn
                ui.label('Eingangs-Pegel').classes('text-xs text-gray-400 mb-1')
                vol_meter = ui.linear_progress(value=0.0) \
                    .props('color=cyan track-color=gray-800 size=10px').classes('w-full mb-3 rounded')

                # Beat-Pulse statt veraltete Beat-Erkennung — vu_meter-Variable
                # bleibt damit audio_ticker (Zeile ~1044) keinen NameError wirft;
                # wird von _beat_pulse_tick() ueberschrieben.
                vu_meter = ui.linear_progress(value=0.0) \
                    .props('color=red track-color=transparent size=2px').classes('hidden')

                with ui.row().classes('w-full items-center gap-2 mb-3'):
                    ui.label('Input Gain').classes('text-xs text-gray-400 w-20')
                    gain_slider = ui.slider(min=0.0, max=8.0, step=0.1, value=1.0) \
                        .props('dark color=cyan label-always').classes('flex-grow')
                gain_slider.on_value_change(lambda e: live_set_input_gain(e.value))

                ui.separator().classes('my-2')

                # ═════════ TEMPO ══════════════════════════════════════════
                ui.label('TEMPO').classes('text-[10px] tracking-widest text-cyan-400 font-bold mb-1')

                with ui.row().classes('w-full items-center gap-2 mb-2'):
                    ui.label('Tracking:').classes('text-xs text-gray-400 w-20')
                    mode_toggle = ui.toggle(['AUTO', 'MANUAL'], value='AUTO') \
                        .props('dark color=cyan no-caps dense')
                mode_toggle.on_value_change(lambda e: live_set_mode(e.value))

                # MANUAL-Block: nur BPM-Input + TAP sichtbar in MANUAL.
                # Beat-1-Button ist UNTEN immer sichtbar (auch in AUTO als Resync).
                with ui.row().bind_visibility_from(mode_toggle, 'value',
                              lambda v: v == 'MANUAL') \
                        .classes('w-full items-end gap-2 mb-2'):
                    bpm_input = ui.number(label='Manuelle BPM', value=124.0,
                                          min=60, max=200, step=0.5) \
                        .props('dark color=orange dense outlined').classes('w-32')
                    bpm_input.on_value_change(
                        lambda e: live_set_manual_bpm(float(e.value or 120.0)))

                    _tap_state = {'taps': []}

                    def on_tap():
                        now = time.time()
                        _tap_state['taps'] = [t for t in _tap_state['taps']
                                              if now - t < 3.0] + [now]
                        if len(_tap_state['taps']) >= 2:
                            intervals = [b - a for a, b in
                                         zip(_tap_state['taps'][:-1], _tap_state['taps'][1:])]
                            avg = sum(intervals) / len(intervals)
                            if avg > 0:
                                bpm = round(60.0 / avg, 1)
                                bpm_input.value = bpm
                                live_set_manual_bpm(bpm)

                    ui.button('TAP', on_click=on_tap) \
                        .props('color=orange outline').classes('h-10 flex-grow')

                # Beat-1-Button immer sichtbar — funktioniert in beiden Modi
                with ui.row().classes('w-full items-center gap-2 mb-3'):
                    ui.button('Beat 1 ▶  (Leertaste)', on_click=live_mark_downbeat) \
                        .props('color=orange push').classes('h-10 flex-grow')

                # Status-Chips: BPM-LOCK / BAR-LOCK + grosse BPM-Anzeige
                with ui.row().classes('w-full items-center gap-2 mb-2'):
                    bpm_big = ui.label('--.- BPM').classes(
                        'text-2xl font-mono font-bold text-cyan-400'
                    )
                    # Beat-Pulse-Dot - flasht bei jedem Beat
                    beat_dot = ui.label('●').classes(
                        'text-3xl text-gray-700 ml-2 transition-colors duration-75'
                    )
                    ui.element('div').classes('flex-grow')   # Spacer
                    bpm_lock_chip = ui.label('BPM ?').classes(
                        'px-2 py-1 rounded text-[10px] font-bold bg-gray-700 text-gray-400'
                    )
                    bar_lock_chip = ui.label('BAR ?').classes(
                        'px-2 py-1 rounded text-[10px] font-bold bg-gray-700 text-gray-400'
                    )

                ui.separator().classes('my-2')

                # ═════════ OUTPUT ═════════════════════════════════════════
                ui.label('OUTPUT').classes('text-[10px] tracking-widest text-cyan-400 font-bold mb-1')

                with ui.row().classes('w-full items-center gap-2 mb-2'):
                    ui.label('Phrase:').classes('text-xs text-gray-400 w-20')
                    phrase_badge = ui.label('—').classes(
                        'px-3 py-1 rounded text-sm font-bold bg-gray-700 text-gray-300'
                    )

                status_live = ui.label('Status: Getrennt').classes('text-gray-400 text-sm mb-3')

                # Spacebar-Handler (global, mit Ignore-Filter)
                def on_global_key(e):
                    if not getattr(e.action, 'keydown', False):
                        return
                    key_name = (e.key.name or '').lower()
                    if key_name not in (' ', 'space'):
                        return
                    if not live_audio_state.get('is_listening'):
                        return
                    live_mark_downbeat()
                try:
                    ui.keyboard(on_key=on_global_key, active=True,
                                ignore=['input', 'select', 'textarea'])
                except Exception:
                    ui.keyboard(on_key=on_global_key, active=True)

                # Live-Update-Ticker: Lock-Chips, BPM, Phrase, Beat-Pulse
                _PHRASE_COLORS = {
                    'BREAK':   'bg-blue-700 text-white',
                    'BUILDUP': 'bg-orange-600 text-white',
                    'DROP':    'bg-red-700 text-white',
                    'WAITING': 'bg-gray-700 text-gray-300',
                }
                _live_ui_state = {
                    'last_beat_in_phr': -1,
                    'pulse_decay': 0.0,
                }

                def _live_status_tick():
                    if not live_audio_state.get('is_listening'):
                        return

                    bpm = live_audio_state.get('bpm', 0.0)
                    bpm_big.text = f"{bpm:.1f} BPM"

                    bpm_lock = live_audio_state.get('bpm_locked', False)
                    bar_lock = live_audio_state.get('bar_locked', False)
                    bpm_lock_chip.text = 'BPM LOCK' if bpm_lock else 'BPM ?'
                    bpm_lock_chip.classes(
                        replace='px-2 py-1 rounded text-[10px] font-bold ' +
                        ('bg-green-700 text-white' if bpm_lock else 'bg-gray-700 text-gray-400')
                    )
                    bar_lock_chip.text = 'BAR LOCK' if bar_lock else 'BAR ?'
                    bar_lock_chip.classes(
                        replace='px-2 py-1 rounded text-[10px] font-bold ' +
                        ('bg-green-700 text-white' if bar_lock else 'bg-gray-700 text-gray-400')
                    )

                    ph = live_audio_state.get('phase', 'WAITING')
                    cls = _PHRASE_COLORS.get(ph, 'bg-gray-700 text-gray-300')
                    phrase_badge.text = f"{ph}  ({live_audio_state.get('tempo_status', '')})"
                    phrase_badge.classes(replace='px-3 py-1 rounded text-sm font-bold ' + cls)

                ui.timer(0.20, _live_status_tick)

                def _beat_pulse_tick():
                    # Detektiert Beat-Wechsel anhand beat_in_phrase (ohne flag zu loeschen)
                    cnt = live_audio_state.get('beat_in_phrase', -1)
                    if cnt != _live_ui_state['last_beat_in_phr']:
                        _live_ui_state['last_beat_in_phr'] = cnt
                        _live_ui_state['pulse_decay'] = 1.0
                    p = _live_ui_state['pulse_decay']
                    _live_ui_state['pulse_decay'] = max(0.0, p * 0.55)
                    # Farbskala: rot (Beat 1), orange (2-3-4), gedimmt mit Decay
                    bib = live_audio_state.get('beat_in_bar', 0)
                    if p > 0.5:
                        col = 'text-red-500' if bib == 0 else 'text-orange-400'
                    elif p > 0.15:
                        col = 'text-red-700' if bib == 0 else 'text-orange-700'
                    else:
                        col = 'text-gray-700'
                    beat_dot.classes(replace=f'text-3xl {col} ml-2 transition-colors duration-75')
                ui.timer(0.05, _beat_pulse_tick)

                def toggle_live():
                    if not live_audio_state["is_listening"]:
                        if device_dropdown.value is None:
                            ui.notify('Bitte erst ein Geraet waehlen', color='red')
                            return
                        success, msg = start_listening(device_dropdown.value)
                        if success:
                            btn_live.props('color=red').set_text('TRENNEN')
                            status_live.set_text('Status: Verbunden')
                            status_live.classes('text-green-400', remove='text-gray-400')
                        else:
                            ui.notify(f'Fehler: {msg}', color='red')
                    else:
                        stop_listening()
                        btn_live.props('color=green').set_text('VERBINDEN')
                        status_live.set_text('Status: Getrennt')
                        status_live.classes('text-gray-400', remove='text-green-400')
                        vol_meter.value = 0.0
                        vu_meter.value  = 0.0

                btn_live = ui.button('VERBINDEN', on_click=toggle_live) \
                    .classes('w-full h-12 text-lg font-bold').props('color=green push')

            # ── PRO DJ LINK ──────────────────────────────────────────────
            with ui.column().bind_visibility_from(play_settings, 'source_mode', lambda m: m == 'PROLINK').classes('w-full'):
                ui.label('1. Pro DJ Link (Pioneer CDJ Netzwerk)').classes('text-xl font-bold text-gray-200 mb-2')
                ui.label('Rechner muss im selben LAN wie die CDJs sein. Beats kommen vom Master-Player.') \
                    .classes('text-[11px] text-gray-500 mb-3')

                with ui.column().classes('w-full bg-gray-800 p-3 rounded border border-purple-900 gap-1 mb-3'):
                    pl_status   = ui.label('Status: Getrennt').classes('text-gray-400 text-sm font-mono')
                    pl_backend  = ui.label('Backend: --').classes('text-[10px] text-gray-500')
                    pl_master   = ui.label('Master Player: --').classes('text-purple-300 text-xs font-mono')
                    pl_track    = ui.label('Track: --').classes('text-gray-200 text-xs font-mono truncate')
                    pl_bpm_lbl  = ui.label('BPM: --').classes('text-purple-400 text-lg font-bold')

                def toggle_prolink():
                    if not live_audio_state.get('prolink_active'):
                        ok, msg = start_prolink()
                        if ok:
                            pl_btn.props('color=red').set_text('TRENNEN')
                            ui.notify('Pro DJ Link gestartet', color='green')
                        else:
                            ui.notify(f'Verbindung fehlgeschlagen: {msg}', color='red')
                    else:
                        stop_prolink()
                        pl_btn.props('color=green').set_text('VERBINDEN')

                pl_btn = ui.button('VERBINDEN', on_click=toggle_prolink) \
                    .classes('w-full h-12 text-lg font-bold').props('color=green push')

                # ── WAVEFORM CANVAS (statisch + dynamischer Playhead) ────
                ui.label('Waveform').classes('text-xs text-gray-400 mt-4 mb-1')
                wf_container = ui.element('div') \
                    .classes('w-full rounded border border-purple-900') \
                    .style('position:relative; height:90px; overflow:hidden; '
                           'background:linear-gradient(to bottom,#0a0a14,#0f0f1a);')
                with wf_container:
                    # statisches SVG — wird NUR bei Track-Wechsel neu gebaut
                    wf_svg_html = ui.html('', sanitize=False) \
                        .style('position:absolute; inset:0; width:100%; height:100%; '
                               'pointer-events:none;')
                    # Fallback (zeigt sich wenn kein Track)
                    wf_fallback = ui.label('NO TRACK LOADED / OFFLINE') \
                        .classes('text-gray-600 text-[11px] font-mono tracking-widest') \
                        .style('position:absolute; top:50%; left:50%; '
                               'transform:translate(-50%,-50%); pointer-events:none;')
                    # Playhead — separater leichter Layer, NUR diese Style-Property aendert sich
                    wf_playhead = ui.element('div') \
                        .style('position:absolute; top:0; bottom:0; width:2px; left:0%; '
                               'background:#fff; box-shadow:0 0 8px rgba(255,255,255,0.7); '
                               'display:none; pointer-events:none;')

                # Time-Display unter der Waveform
                with ui.row().classes('w-full justify-between mt-1'):
                    wf_time_lbl = ui.label('00:00').classes('text-[10px] text-gray-500 font-mono')
                    wf_len_lbl  = ui.label('--:--').classes('text-[10px] text-gray-500 font-mono')

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
            ui.radio(['Scene Sync', 'Custom Timeline', 'Magic Auto', 'Virtual DJ', 'Sunset Groove'], value='Scene Sync').bind_value(play_settings, 'mode').props('inline dark color=cyan').classes('mb-2')
            
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

                    ui.label('Abklingen').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'fade').props('dark color=purple label-always').tooltip('0 = Blinder-Flash sofort weg, 1 = langes Nachleuchten')

                    ui.label('Strobe').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'strobe_amount').props('dark color=white label-always')

                # --- BEAT BLINDER ---
                ui.label('BEAT BLINDER').classes('text-xs text-gray-400 font-bold mt-2')
                with ui.column().classes('w-full bg-gray-900 p-2 rounded border border-orange-900 gap-2'):
                    with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-0'):
                        ui.label('Stärke').classes('text-gray-300 text-xs self-center')
                        ui.slider(min=0, max=1, step=0.01).bind_value(magic_auto_state, 'blinder_strength').props('dark color=orange label-always')

                        ui.label('Alle N Beats').classes('text-gray-300 text-xs self-center')
                        ui.select(
                            options={1: 'jeden Beat', 2: '2 Beats', 4: '4 Beats', 8: '8 Beats'},
                            value=1,
                        ).bind_value(magic_auto_state, 'blinder_every') \
                         .props('dark standout dense color=orange')

                    ui.label('Aktiv in Phase:').classes('text-gray-400 text-[10px] mt-1')
                    with ui.row().classes('gap-3'):
                        def _make_phase_cb(ph, label, color):
                            def toggle(e, p=ph):
                                phases = list(magic_auto_state.get('blinder_phases', []))
                                if e.value and p not in phases:
                                    phases.append(p)
                                elif not e.value and p in phases:
                                    phases.remove(p)
                                magic_auto_state['blinder_phases'] = phases
                            ui.checkbox(label, value=ph in magic_auto_state.get('blinder_phases', ['DROP']),
                                        on_change=toggle).props(f'dense color={color}').classes('text-xs')
                        _make_phase_cb('DROP',    'DROP',    'red')
                        _make_phase_cb('BUILDUP', 'BUILDUP', 'orange')
                        _make_phase_cb('BREAK',   'BREAK',   'blue')

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

                # --- LASER AUTOMATIK ---
                ui.label('LASER AUTOMATIK').classes('text-xs text-gray-400 font-bold mt-2')
                with ui.column().classes('w-full bg-gray-900 p-2 rounded border border-red-900 gap-1'):
                    ui.checkbox('Laser-Automation aktiv', value=True) \
                        .bind_value(magic_auto_state, 'laser_auto').classes('text-red-300 text-xs font-bold')

                    with ui.column().classes('w-full gap-1').bind_visibility_from(magic_auto_state, 'laser_auto'):
                        ui.checkbox('Zufälliges Muster (on beat / on drop)', value=True) \
                            .bind_value(magic_auto_state, 'laser_random_pattern').classes('text-gray-200 text-xs')
                        ui.checkbox('Farbe an Palette koppeln', value=True) \
                            .bind_value(magic_auto_state, 'laser_color_sync').classes('text-gray-200 text-xs')
                        ui.checkbox('Speed + Zoom nach Phase', value=True) \
                            .bind_value(magic_auto_state, 'laser_speed_react').classes('text-gray-200 text-xs')

                        with ui.row().classes('w-full items-center gap-2 mt-1'):
                            ui.label('DMX Modus:').classes('text-gray-400 text-xs whitespace-nowrap')
                            ui.radio(
                                options={"dynamic": "Dynamisch (animiert)", "static": "Statisch DMX"},
                                value="dynamic",
                            ).bind_value(magic_auto_state, 'laser_dmx_mode') \
                             .props('inline dark color=red').classes('text-xs')

                        with ui.row().classes('w-full items-center gap-2 mt-1') \
                                .bind_visibility_from(magic_auto_state, 'laser_random_pattern'):
                            ui.label('Muster-Wechsel:').classes('text-gray-400 text-xs whitespace-nowrap')
                            ui.select(
                                options={0.5: '½ Beat', 1: '1 Beat', 2: '2 Beats', 4: '4 Beats', 8: '8 Beats'},
                                value=2,
                            ).bind_value(magic_auto_state, 'laser_pattern_beats') \
                             .props('dark standout dense color=red').classes('w-32')

                # --- BLINDER KONFIGURATION ---
                ui.label('BLINDER GERÄTE').classes('text-xs text-gray-400 font-bold mt-2')
                with ui.column().classes('w-full bg-gray-900 p-2 rounded border border-orange-900 gap-2'):
                    ui.label('Welche Geräte als Blinder (leer = alle):') \
                        .classes('text-orange-300 text-[10px]')

                    fixture_ids = [f.id for f in state.engine.fixtures]
                    blinder_select = ui.select(
                        options=fixture_ids,
                        multiple=True,
                        value=magic_auto_state.get("blinder_fixture_ids", []),
                        label='Blinder Geräte',
                    ).props('dark standout dense color=orange use-chips').classes('w-full')

                    def on_blinder_fixtures_change(e):
                        magic_auto_state["blinder_fixture_ids"] = list(e.value or [])
                    blinder_select.on_value_change(on_blinder_fixtures_change)

                    ui.label('Blinder-Farbe:').classes('text-orange-300 text-[10px]')
                    ui.radio(
                        options={"white": "Weiss (voll)", "palette": "Palettenfarbe"},
                        value=magic_auto_state.get("blinder_color", "white"),
                    ).bind_value(magic_auto_state, "blinder_color") \
                     .props('inline dark color=orange').classes('text-xs')

                # --- INTELLIGENTE AUTOMATIK ---
                ui.label('INTELLIGENTE AUTOMATIK').classes('text-xs text-gray-400 font-bold mt-2')
                with ui.column().classes('w-full bg-gray-900 p-2 rounded border border-cyan-900 gap-0'):
                    ui.checkbox('Synth-Blinder (Hochton-Spike → Flash im Buildup/Drop)', value=True) \
                        .bind_value(magic_auto_state, 'synth_blinder').classes('text-cyan-300 text-xs') \
                        .tooltip('Erkennt Synth-/Hi-Hat-Einsetzen (1-8 kHz) und löst einen Blinder aus')
                    ui.checkbox('Smart Flash (nur bei Drop-Übergang oder hoher Energie)', value=True) \
                        .bind_value(magic_auto_state, 'smart_flash').classes('text-cyan-300 text-xs') \
                        .tooltip('Ersetzt zufällige Flash-Automatik durch musik-intelligentes Timing')
                    ui.checkbox('Energy Brightness (Lautstärke steuert Helligkeit)', value=True) \
                        .bind_value(magic_auto_state, 'energy_brightness').classes('text-cyan-300 text-xs') \
                        .tooltip('Break = dunkel, Buildup = mittel, Drop = voll hell')
                    ui.checkbox('Drop Instant (sofortiger Vollblinder beim ersten Drop-Beat)', value=True) \
                        .bind_value(magic_auto_state, 'drop_instant').classes('text-cyan-300 text-xs') \
                        .tooltip('Zündet beim ersten Beat nach Phasenwechsel zu DROP einen vollen Blinder')

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

            # --- VIRTUAL LIGHT DIRECTOR ---
            with ui.column().classes('w-full bg-gray-800 p-3 rounded border border-purple-900 gap-3') \
                    .bind_visibility_from(play_settings, 'mode', lambda m: m == 'Virtual DJ'):

                # Header
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label('VIRTUAL LIGHT DIRECTOR').classes('text-sm font-black tracking-widest text-purple-400')
                    vldj_switch = ui.switch('Aktiv', value=True).props('color=purple')
                    vldj_switch.on_value_change(lambda e: setattr(_vldj, 'is_active', e.value))

                # A. LIVE TELEMETRIE
                ui.label('LIVE TELEMETRIE').classes('text-xs text-gray-400 font-bold')
                with ui.column().classes('w-full bg-gray-900 p-2 rounded border border-purple-800 gap-2'):
                    with ui.row().classes('w-full gap-3 items-center'):
                        vldj_phase_badge = ui.label('WAITING') \
                            .classes('lcd-display text-xs font-black tracking-widest phase-wait px-2 py-1') \
                            .style('border-radius:2px; border:1px solid #1a1a2a;')
                        vldj_palette_lbl = ui.label('EIS').classes('text-purple-300 text-xs font-mono')
                    with ui.row().classes('w-full items-center gap-2'):
                        ui.label('Energie').classes('text-[10px] text-gray-500 w-12 whitespace-nowrap')
                        vldj_energy_bar = ui.linear_progress(value=0.0) \
                            .props('color=purple track-color=gray-800 size=8px').classes('flex-grow')
                        vldj_beat_dot = ui.element('div').style(
                            'width:12px;height:12px;border-radius:50%;'
                            'background:#333;border:1px solid #555;flex-shrink:0;'
                        )

                # B. LD CONTROLS
                ui.label('LD CONTROLS').classes('text-xs text-gray-400 font-bold mt-1')
                with ui.column().classes('w-full bg-gray-900 p-2 rounded border border-gray-700 gap-2'):
                    _pal_options = [PALETTE_AUTO] + list(get_all_palettes().keys())
                    vldj_palette_sel = ui.select(
                        options=_pal_options,
                        value=PALETTE_AUTO,
                        label='Palette (alle Phasen)'
                    ).props('dark standout dense color=purple').classes('w-full')

                    def _on_palette_sel(e):
                        _vldj.set_palette(None if e.value == PALETTE_AUTO else e.value)
                    vldj_palette_sel.on_value_change(_on_palette_sel)

                    with ui.row().classes('w-full items-center gap-2 mt-1'):
                        ui.label('Aggressivität').classes('text-gray-300 text-xs whitespace-nowrap')
                        aggr_sl = ui.slider(min=0.0, max=1.0, step=0.01, value=0.5) \
                            .props('dark color=purple label-always').classes('flex-grow')
                        aggr_sl.on_value_change(lambda e: _vldj.set_aggressiveness(e.value))
                    ui.label('0 = sanft / 0.5 = Standard / 1 = hart') \
                        .classes('text-[10px] text-gray-600 italic')

                # C. CUSTOM PALETTE CREATOR
                ui.label('PALETTE ERSTELLEN').classes('text-xs text-gray-400 font-bold mt-1')
                with ui.column().classes('w-full bg-gray-900 p-2 rounded border border-gray-700 gap-2'):
                    cp_name = ui.input('Palettenname', value='Meine Palette') \
                        .props('dark dense color=purple').classes('w-full')
                    cp_color_inputs = []
                    with ui.grid(columns=4).classes('w-full gap-1'):
                        for _ci, _hex in enumerate(['#ff1a00', '#00aaff', '#cc00ff', '#ffffff']):
                            with ui.column().classes('items-center gap-0'):
                                ui.label(f'F{_ci + 1}').classes('text-[9px] text-gray-500')
                                _inp = ui.color_input(value=_hex).classes('w-full')
                                cp_color_inputs.append(_inp)

                    def _save_palette():
                        name = cp_name.value.strip()
                        if not name:
                            ui.notify('Bitte Namen eingeben!', color='red')
                            return
                        colors = []
                        for ci in cp_color_inputs:
                            hex_s = ci.value.lstrip('#')
                            try:
                                r = int(hex_s[0:2], 16) / 255.0
                                g = int(hex_s[2:4], 16) / 255.0
                                b = int(hex_s[4:6], 16) / 255.0
                            except Exception:
                                r = g = b = 1.0
                            colors.append((r, g, b))
                        try:
                            save_custom_palette(name, colors)
                            new_opts = [PALETTE_AUTO] + list(get_all_palettes().keys())
                            vldj_palette_sel.options = new_opts
                            vldj_palette_sel.set_value(name)
                            vldj_palette_sel.update()
                            ui.notify(f'"{name}" gespeichert!', color='green')
                        except Exception as ex:
                            ui.notify(str(ex), color='red')

                    ui.button('PALETTE SPEICHERN', on_click=_save_palette) \
                        .props('color=purple push dense').classes('w-full font-bold text-xs')

                # D. PANIC BUTTONS
                ui.label('PANIC').classes('text-xs text-gray-400 font-bold mt-1')
                with ui.row().classes('w-full gap-2'):
                    def _panic_blackout():
                        _vldj.blackout(state.engine)
                        _vldj.is_active = False
                        vldj_switch.set_value(False)

                    def _panic_white():
                        _vldj.white_flash(state.engine)

                    ui.button('BLACKOUT', on_click=_panic_blackout) \
                        .props('push').classes(
                            'flex-grow h-14 text-base font-black tracking-widest text-red-400'
                        ).style('background:#1a0000; border:2px solid #cc0000;')
                    ui.button('WHITE FLASH', on_click=_panic_white) \
                        .props('push').classes(
                            'flex-grow h-14 text-base font-black tracking-widest text-gray-900'
                        ).style('background:#ffffff;')

                # Live-Telemetrie (20 Hz)
                def _update_vldj_status():
                    if play_settings['mode'] != 'Virtual DJ':
                        return
                    if play_settings['source_mode'] == 'LIVE':
                        ph = live_audio_state.get('phase', 'WAITING')
                        en = live_audio_state.get('energy_level', 0.0)
                    elif play_settings['source_mode'] == 'PROLINK':
                        ph = live_audio_state.get('phase') or 'DROP'
                        en = {'BREAK': 0.2, 'BUILDUP': 0.6, 'DROP': 1.0}.get(ph, 0.7)
                    else:
                        ph = audio_state.get('last_state') or 'WAITING'
                        en = {'BREAK': 0.2, 'BUILDUP': 0.6, 'DROP': 1.0}.get(ph, 0.0)

                    vldj_energy_bar.value = en
                    vldj_phase_badge.set_text(ph)
                    if ph == 'DROP':
                        vldj_phase_badge.classes('phase-drop', remove='phase-buildup phase-break phase-wait')
                    elif ph == 'BUILDUP':
                        vldj_phase_badge.classes('phase-buildup', remove='phase-drop phase-break phase-wait')
                    else:
                        vldj_phase_badge.classes('phase-break phase-wait', remove='phase-drop phase-buildup')

                    pal = _vldj._palette_override or PHASE_PALETTE.get(ph, 'eis')
                    vldj_palette_lbl.set_text(pal.upper())

                    d = int(min(_vldj._dim_env * 255, 255))
                    vldj_beat_dot.style(
                        f'width:12px;height:12px;border-radius:50%;'
                        f'background:rgb({d},{d // 4},{d // 2});border:1px solid #555;flex-shrink:0;'
                    )

                ui.timer(0.05, _update_vldj_status)

            # ── SUNSET GROOVE (Outdoor Chill - Freiluftfrequenz) ────────
            with ui.column().classes('w-full bg-gray-800 p-3 rounded mb-4 border border-orange-900 gap-3') \
                    .bind_visibility_from(play_settings, 'mode', lambda m: m == 'Sunset Groove'):
                ui.label('SUNSET GROOVE - Outdoor Chill').classes('text-sm font-bold text-orange-400')
                ui.label('Ruhiges warmes Atmen, nur EIN Blinder beim Drop-Eintritt. '
                         'Kein Strobe, kein Effekt-Wechsel.') \
                    .classes('text-[10px] text-gray-500 leading-tight')

                # Mini-Palette-Vorschau
                with ui.row().classes('w-full items-center gap-1 mt-1'):
                    ui.label('Palette:').classes('text-xs text-gray-400 w-16')
                    from engine.sunset_groove import SUNSET_PALETTE
                    for (pr, pg, pb, pw) in SUNSET_PALETTE:
                        mix_r = int(min(255, pr * 255 + pw * 128))
                        mix_g = int(min(255, pg * 255 + pw * 128))
                        mix_b = int(min(255, pb * 255 + pw * 128))
                        ui.element('div').style(
                            f'width:24px;height:14px;border-radius:3px;'
                            f'background:rgb({mix_r},{mix_g},{mix_b});'
                            f'border:1px solid #444;flex-shrink:0;'
                        )

                with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-1 mt-2'):
                    ui.label('Helligkeit').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0.2, max=1.0, step=0.05) \
                        .bind_value(sunset_state, 'brightness') \
                        .props('dark color=orange label-always')

                    ui.label('Blinder-Staerke').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0.0, max=1.0, step=0.05) \
                        .bind_value(sunset_state, 'blinder_strength') \
                        .props('dark color=orange label-always') \
                        .tooltip('0 = kein Blinder, 1 = voller weisser Pulse beim DROP-Eintritt')

                    ui.label('Farb-Zyklus').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=8, max=64, step=4) \
                        .bind_value(sunset_state, 'color_cycle_beats') \
                        .props('dark color=orange label-always') \
                        .tooltip('Beats pro Farb-Schritt - hoeher = traeger')

                    ui.label('Atem-Tempo').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0.15, max=1.2, step=0.05) \
                        .bind_value(sunset_state, 'breath_speed') \
                        .props('dark color=orange label-always')

                    ui.label('Atem-Tiefe').classes('text-gray-300 text-xs self-center')
                    ui.slider(min=0.0, max=0.5, step=0.05) \
                        .bind_value(sunset_state, 'breath_depth') \
                        .props('dark color=orange label-always') \
                        .tooltip('0 = konstantes Licht, 0.5 = stark atmend')

                ui.checkbox('Laser an (langsames rotes Pattern)', value=True) \
                    .bind_value(sunset_state, 'laser_on') \
                    .classes('text-orange-300 text-xs mt-1')

            # overlay flash- automatik
            ui.separator().classes('bg-gray-700 my-2')
            with ui.column().classes('w-full gap-2 mb-4').bind_visibility_from(play_settings, 'mode', lambda m: m not in ('Magic Auto', 'Virtual DJ', 'Sunset Groove')):
                ui.checkbox('Flash Automatik zuschalten', value=True) \
                    .bind_value(play_settings, 'flash_automatik') \
                    .classes('text-yellow-400 font-bold')

                with ui.column().classes('w-full bg-gray-800 p-2 rounded border border-yellow-900 gap-3') \
                        .bind_visibility_from(play_settings, 'flash_automatik'):

                    interval_opts = {1: '1 Beat', 2: '2 Beats', 4: '4 Beats', 8: '8 Beats', 16: '16 Beats'}
                    mode_opts     = {'off': 'Aus', 'on_enter': 'Bei Eintritt', 'interval': 'Intervall'}

                    for ph_label, ph_color, mode_key, iv_key, iv_color in [
                        ('DROP',    'text-red-400',    'flash_drop_mode',    'flash_drop_interval',    'red'),
                        ('BUILDUP', 'text-orange-400', 'flash_buildup_mode', 'flash_buildup_interval', 'orange'),
                        ('BREAK',   'text-blue-400',   'flash_break_mode',   'flash_break_interval',   'blue'),
                    ]:
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label(ph_label).classes(f'{ph_color} font-black text-xs w-16')
                            ui.select(
                                options=mode_opts,
                                value=play_settings.get(mode_key, 'off'),
                            ).bind_value(play_settings, mode_key) \
                             .props(f'dark standout dense color={iv_color}').classes('w-28')

                            iv_row = ui.row().classes('items-center gap-1')
                            with iv_row:
                                ui.select(
                                    options=interval_opts,
                                    value=play_settings.get(iv_key, 1),
                                ).bind_value(play_settings, iv_key) \
                                 .props(f'dark standout dense color={iv_color}').classes('w-28') \
                                 .bind_visibility_from(play_settings, mode_key, lambda v: v == 'interval')

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

                # Magic Auto läuft immer durch — Flash-Guard nur für Scene/Timeline
                if play_settings["mode"] == "Magic Auto":
                    magic_on_beat(phase)
                    return

                # Sunset Groove - eigener on_beat (zaehlt Farb-Zyklus + Drop-Pulse)
                if play_settings["mode"] == "Sunset Groove":
                    sunset_on_beat(phase)
                    return

                # Virtual DJ — beat_in_bar 0-basiert übergeben
                if play_settings["mode"] == "Virtual DJ":
                    if not _vldj.is_active:
                        return
                    if play_settings["source_mode"] == "LIVE" and live_audio_state.get("ml_active"):
                        ml_bar = live_audio_state.get("beat_in_bar", 0)
                    else:
                        ml_bar = (beat_in_bar - 1) % 16  # 1-4 → 0-3
                    energy = live_audio_state.get("energy_level", 0.5) \
                             if play_settings["source_mode"] == "LIVE" \
                             else {"BREAK": 0.2, "BUILDUP": 0.6, "DROP": 1.0}.get(phase or "DROP", 0.5)
                    _vldj.trigger_beat(ml_bar, phase or "DROP", energy)
                    return

                # Wenn ein Flash/Blinder gerade aktiv ist, Scene-Sync überspringen
                # damit der Blinder nicht durch eine neue Szene überschrieben wird
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

                # flash automatik overlay
                if play_settings["flash_automatik"] and play_settings["mode"] != "Magic Auto":
                    flash_events = [e for e in state.events if e.type == "flash"]
                    if flash_events:
                        prev_phase    = play_settings.get("_prev_flash_phase", "")
                        phase_entered = (phase != prev_phase)

                        def _check_flash(phase_key, interval_key, count_key):
                            mode = play_settings.get(phase_key, "off")
                            if mode == "off":
                                return False
                            if mode == "on_enter":
                                return phase_entered
                            # interval
                            if phase_entered:
                                play_settings[count_key] = 0
                            play_settings[count_key] = play_settings.get(count_key, 0) + 1
                            iv = max(1, int(play_settings.get(interval_key, 1)))
                            return play_settings[count_key] % iv == 0

                        if phase == "DROP":
                            should_flash = _check_flash("flash_drop_mode", "flash_drop_interval", "_flash_drop_count")
                        elif phase == "BUILDUP":
                            should_flash = _check_flash("flash_buildup_mode", "flash_buildup_interval", "_flash_buildup_count")
                        else:
                            should_flash = _check_flash("flash_break_mode", "flash_break_interval", "_flash_break_count")

                        if should_flash:
                            for e in flash_events:
                                if e.active: e.stop(state.engine)
                            random_flash = random.choice(flash_events)
                            random_flash.start(state.engine)
                        play_settings["_prev_flash_phase"] = phase

            # ticker und lichttrigger (100 mal pro sekunde)
            def audio_ticker():
                if not play_settings["is_active"]:
                    return
                if play_settings["source_mode"] == "MP3":
                    elapsed_time = get_current_time()
                    if elapsed_time == 0.0: return
                    # Energy Level aus Phase ableiten (MP3: kein echter RMS)
                    _mp3_energy = {"BREAK": 0.2, "BUILDUP": 0.6, "DROP": 1.0}.get(
                        audio_state.get("last_state", "DROP"), 0.5)
                    magic_auto_state["_energy_level"] = _mp3_energy
                    
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

                elif play_settings["source_mode"] == "PROLINK":
                    if not live_audio_state.get("prolink_active"):
                        return

                    # ProLink liefert keine Phase — User-gesetzt oder Default DROP
                    pl_phase = live_audio_state.get("phase") or "DROP"
                    if not pl_phase or pl_phase == "WAITING":
                        pl_phase = "DROP"
                        live_audio_state["phase"] = pl_phase

                    # Energy-Level fuer Magic Auto / VLDJ aus Phase ableiten
                    magic_auto_state["_energy_level"] = {
                        "BREAK": 0.2, "BUILDUP": 0.6, "DROP": 1.0
                    }.get(pl_phase, 0.7)

                    lbl_state.set_text(pl_phase)
                    if pl_phase == "DROP":
                        lbl_state.classes('phase-drop', remove='phase-buildup phase-break phase-wait')
                    elif pl_phase == "BUILDUP":
                        lbl_state.classes('phase-buildup', remove='phase-drop phase-break phase-wait')
                    else:
                        lbl_state.classes('phase-break', remove='phase-drop phase-buildup phase-wait')

                    # Beat aus dem Pioneer-Netzwerk
                    if live_audio_state["beat_triggered"]:
                        live_audio_state["beat_triggered"] = False
                        beat_in_bar = live_audio_state["beat_index"] + 1
                        bpm = live_audio_state.get("bpm_prolink", 0.0)
                        lbl_beat.set_text(f"PROLINK   |   {beat_in_bar}/4   {bpm:.1f} BPM")
                        if beat_in_bar == 1:
                            lbl_beat.classes('text-purple-400 font-bold', remove='text-gray-300')
                        else:
                            lbl_beat.classes('text-gray-300', remove='text-purple-400 font-bold')
                        trigger_lights(beat_in_bar, pl_phase)

                elif play_settings["source_mode"] == "LIVE":
                    if not live_audio_state["is_listening"]: return

                    # Energy Level an Magic Auto weitergeben
                    magic_auto_state["_energy_level"] = live_audio_state.get("energy_level", 0.5)

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

                    # Transient-Trigger weiterleiten
                    if live_audio_state.get("transient_triggered"):
                        live_audio_state["transient_triggered"] = False
                        if play_settings["is_active"]:
                            if play_settings["mode"] == "Magic Auto":
                                magic_on_transient(live_phase)
                            elif play_settings["mode"] == "Virtual DJ":
                                _vldj.trigger_transient()

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
                """Kontinuierlicher 100 Hz Update fuer Magic Auto."""
                if not play_settings["is_active"]:
                    return
                if play_settings["mode"] != "Magic Auto":
                    return
                if play_settings["source_mode"] == "MP3":
                    if not audio_state.get("is_playing", False):
                        return
                    phase = audio_state.get("last_state", "DROP")
                elif play_settings["source_mode"] == "PROLINK":
                    if not live_audio_state.get("prolink_active"):
                        return
                    phase = live_audio_state.get("phase") or "DROP"
                else:
                    if not live_audio_state["is_listening"]:
                        return
                    phase = live_audio_state.get("phase", "DROP")
                magic_apply(state.engine, phase)

            import time as _time
            _vldj_last_t = [0.0]

            def vldj_ticker():
                """Kontinuierlicher 100 Hz Update fuer Virtual DJ."""
                if not play_settings["is_active"]:
                    return
                if play_settings["mode"] != "Virtual DJ":
                    return
                if play_settings["source_mode"] == "MP3":
                    if not audio_state.get("is_playing", False):
                        return
                    phase  = audio_state.get("last_state") or "BREAK"
                    energy = {"BREAK": 0.2, "BUILDUP": 0.6, "DROP": 1.0}.get(phase, 0.5)
                elif play_settings["source_mode"] == "PROLINK":
                    if not live_audio_state.get("prolink_active"):
                        return
                    phase  = live_audio_state.get("phase") or "DROP"
                    energy = {"BREAK": 0.2, "BUILDUP": 0.6, "DROP": 1.0}.get(phase, 0.7)
                else:
                    if not live_audio_state["is_listening"]:
                        return
                    phase  = live_audio_state.get("phase", "BREAK")
                    energy = live_audio_state.get("energy_level", 0.5)

                now = _time.time()
                dt  = min(now - _vldj_last_t[0], 0.05) if _vldj_last_t[0] > 0 else 0.01
                _vldj_last_t[0] = now
                _vldj.tick(state.engine, dt, phase, energy)

            _sunset_last_t = [0.0]

            def sunset_ticker():
                """100 Hz Update fuer Sunset Groove."""
                if not play_settings["is_active"]:
                    return
                if play_settings["mode"] != "Sunset Groove":
                    return
                if play_settings["source_mode"] == "MP3":
                    if not audio_state.get("is_playing", False):
                        return
                    phase = audio_state.get("last_state") or "BREAK"
                    energy = {"BREAK": 0.2, "BUILDUP": 0.6, "DROP": 1.0}.get(phase, 0.5)
                elif play_settings["source_mode"] == "PROLINK":
                    if not live_audio_state.get("prolink_active"):
                        return
                    phase  = live_audio_state.get("phase") or "BREAK"
                    energy = {"BREAK": 0.2, "BUILDUP": 0.6, "DROP": 1.0}.get(phase, 0.7)
                else:
                    if not live_audio_state["is_listening"]:
                        return
                    phase  = live_audio_state.get("phase", "BREAK")
                    energy = live_audio_state.get("energy_level", 0.5)

                now = _time.time()
                dt  = min(now - _sunset_last_t[0], 0.05) if _sunset_last_t[0] > 0 else 0.01
                _sunset_last_t[0] = now
                sunset_tick(state.engine, dt, phase, energy)

            # Reset des Sunset-State beim Mode-Wechsel WEG von Sunset
            _last_mode_for_sunset = [play_settings.get("mode")]

            def _sunset_mode_watch():
                cur = play_settings.get("mode")
                if cur != _last_mode_for_sunset[0]:
                    if _last_mode_for_sunset[0] == "Sunset Groove":
                        sunset_reset()
                    _last_mode_for_sunset[0] = cur

            ui.timer(0.01, audio_ticker)
            ui.timer(0.01, magic_auto_ticker)
            ui.timer(0.01, vldj_ticker)
            ui.timer(0.01, sunset_ticker)
            ui.timer(0.50, _sunset_mode_watch)

            # ── PRO DJ LINK: Status-Chip + Waveform + Playhead ──────────
            _wf_state = {"track_id": object()}   # sentinel ungleich "None"

            def _format_mmss(sec: float) -> str:
                if sec <= 0: return "--:--"
                m = int(sec // 60); s = int(sec % 60)
                return f"{m:02d}:{s:02d}"

            def prolink_status_ticker():
                """2 Hz — billig: Status-Chip + Track-Labels."""
                active = bool(live_audio_state.get('prolink_active'))
                if active:
                    backend = backend_label()
                    prolink_status_chip.set_text(f"ProLink: {backend}")
                    prolink_status_chip.style(
                        'background:#0a1a14; border:1px solid #00ff8855; '
                        'color:#7fffaa; padding:2px 8px; border-radius:2px;'
                    )
                else:
                    prolink_status_chip.set_text('ProLink: offline')
                    prolink_status_chip.style(
                        'background:#0a0a14; border:1px solid #1a1a2a; '
                        'color:#666; padding:2px 8px; border-radius:2px;'
                    )

                # Detail-Panel nur updaten wenn sichtbar
                if play_settings['source_mode'] != 'PROLINK':
                    return
                pl_status.set_text(f"Status: {live_audio_state.get('prolink_status','Getrennt')}")
                pl_backend.set_text(f"Backend: {backend_label()}")
                mp = live_audio_state.get('prolink_master_player')
                pl_master.set_text(f"Master Player: {mp if mp else '--'}")
                title  = live_audio_state.get('track_title') or ''
                artist = live_audio_state.get('track_artist') or ''
                track_str = (f"{artist} — {title}" if (artist and title)
                             else (title or artist or '--'))
                pl_track.set_text(f"Track: {track_str}")
                bpm = live_audio_state.get('bpm_prolink', 0.0)
                pl_bpm_lbl.set_text(f"BPM: {bpm:.1f}" if bpm > 0 else "BPM: --")
                wf_len_lbl.set_text(_format_mmss(live_audio_state.get('track_length', 0.0)))

            def waveform_rebuild_ticker():
                """0.3 Hz Polling — rebuild SVG NUR wenn Track-ID sich aendert."""
                if play_settings['source_mode'] != 'PROLINK':
                    return
                tid = live_audio_state.get('track_id')
                if tid == _wf_state['track_id']:
                    return
                _wf_state['track_id'] = tid

                wf = live_audio_state.get('waveform_data')
                if wf is None or len(wf) == 0:
                    wf_svg_html.set_content('')
                    wf_fallback.style('position:absolute; top:50%; left:50%; '
                                      'transform:translate(-50%,-50%); '
                                      'pointer-events:none; display:block;')
                    wf_playhead.style('position:absolute; top:0; bottom:0; '
                                      'width:2px; left:0%; background:#fff; '
                                      'box-shadow:0 0 8px rgba(255,255,255,0.7); '
                                      'display:none; pointer-events:none;')
                    return

                wf_fallback.style('display:none;')
                wf_playhead.style('position:absolute; top:0; bottom:0; '
                                  'width:2px; left:0%; background:#fff; '
                                  'box-shadow:0 0 8px rgba(255,255,255,0.7); '
                                  'display:block; pointer-events:none;')

                # SVG bauen — Hoehe 0..31 → 0..100, vertikal zentriert
                n = len(wf)
                bar_w = 1000.0 / n
                rects = []
                for i, byte in enumerate(wf):
                    h = (int(byte) & 0x1f) / 31.0      # nur untere 5 Bit = Hoehe
                    bar_h = max(1.0, h * 95.0)
                    y = (100.0 - bar_h) / 2.0
                    x = i * bar_w
                    rects.append(
                        f'<rect x="{x:.2f}" y="{y:.2f}" '
                        f'width="{bar_w:.2f}" height="{bar_h:.2f}" '
                        f'fill="#a855f7"/>'
                    )
                svg = (
                    '<svg width="100%" height="100%" '
                    'preserveAspectRatio="none" viewBox="0 0 1000 100" '
                    'xmlns="http://www.w3.org/2000/svg">'
                    + ''.join(rects) + '</svg>'
                )
                wf_svg_html.set_content(svg)

            def playhead_ticker():
                """~30 Hz — bewegt nur den 2px-Playhead-Layer (sehr leicht)."""
                if play_settings['source_mode'] != 'PROLINK':
                    return
                length = live_audio_state.get('track_length', 0.0)
                pos    = live_audio_state.get('current_time', 0.0)
                if length <= 0 or live_audio_state.get('waveform_data') is None:
                    return
                pct = max(0.0, min(100.0, (pos / length) * 100.0))
                wf_playhead.style(
                    f'position:absolute; top:0; bottom:0; width:2px; '
                    f'left:{pct:.2f}%; background:#fff; '
                    f'box-shadow:0 0 8px rgba(255,255,255,0.7); '
                    f'display:block; pointer-events:none;'
                )
                wf_time_lbl.set_text(_format_mmss(pos))

            ui.timer(0.5, prolink_status_ticker)
            ui.timer(0.3, waveform_rebuild_ticker)
            ui.timer(1/30, playhead_ticker)