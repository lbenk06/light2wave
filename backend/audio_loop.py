"""
Audio-to-Light loop — extracted from gui/tabs/audio.py.
Runs as a 100 Hz asyncio background task.
Reads audio_state / live_audio_state and triggers engine changes.
"""
import asyncio
import random
import time

from audio.audio_file import audio_state, get_current_time
from audio.audio_live import live_audio_state
from engine.magic_auto import magic_auto_state, on_beat as magic_on_beat, apply as magic_apply


def trigger_lights(beat_in_bar: int, phase: str):
    """Apply beat-triggered lighting change based on current play_settings."""
    from backend.state import app_state, play_settings

    if not play_settings["is_active"]:
        return

    # Don't override a running flash/blinder
    if any(e.active for e in app_state.events if e.type == "flash"):
        return

    mode = play_settings["mode"]

    # ── Scene Sync ────────────────────────────────────────────────────────────
    if mode == "Scene Sync" and play_settings["selected_bank"]:
        bank = next(
            (b for b in app_state.engine.banks if b["name"] == play_settings["selected_bank"]),
            None
        )
        if bank and bank["scenes"]:
            play_settings["current_scene_idx"] = (
                play_settings["current_scene_idx"] + 1
            ) % len(bank["scenes"])
            scene = bank["scenes"][play_settings["current_scene_idx"]]
            data = scene.get("data", {})
            for f in app_state.engine.fixtures:
                if f.id in data:
                    for k, v in data[f.id].items():
                        f.set(k, v)

    # ── Custom Timeline ───────────────────────────────────────────────────────
    elif mode == "Custom Timeline":
        active_phase = phase or "DROP"
        selections = play_settings["custom_timeline"].get(active_phase, [])

        if not selections:
            last = play_settings.get("last_active_item")
            if last and last.startswith("Event: "):
                ev = next((e for e in app_state.events if e.name == last[7:]), None)
                if ev and ev.active:
                    ev.stop(app_state.engine)
            play_settings["last_active_item"] = None
        else:
            if beat_in_bar == 1:
                play_settings["custom_step_idx"] = (
                    play_settings["custom_step_idx"] + 1
                ) % len(selections)
            if play_settings["custom_step_idx"] >= len(selections):
                play_settings["custom_step_idx"] = 0

            active_item = selections[play_settings["custom_step_idx"]]

            if play_settings.get("last_active_item") != active_item:
                old = play_settings.get("last_active_item")
                if old and old.startswith("Event: "):
                    ev = next((e for e in app_state.events if e.name == old[7:]), None)
                    if ev and ev.active:
                        ev.stop(app_state.engine)
                play_settings["last_active_item"] = active_item

            if active_item.startswith("Event: "):
                ev = next((e for e in app_state.events if e.name == active_item[7:]), None)
                if ev:
                    if ev.type == "flash":
                        if ev.active:
                            ev.stop(app_state.engine)
                        ev.start(app_state.engine)
                    elif not ev.active:
                        ev.start(app_state.engine)
            elif active_item.startswith("Bank: "):
                bank_name = active_item[6:]
                bank = next((b for b in app_state.engine.banks if b["name"] == bank_name), None)
                if bank and bank["scenes"]:
                    play_settings["current_scene_idx"] = (
                        play_settings["current_scene_idx"] + 1
                    ) % len(bank["scenes"])
                    scene = bank["scenes"][play_settings["current_scene_idx"]]
                    data = scene.get("data", {})
                    for f in app_state.engine.fixtures:
                        if f.id in data:
                            for k, v in data[f.id].items():
                                f.set(k, v)

    # ── Magic Auto ────────────────────────────────────────────────────────────
    elif mode == "Magic Auto":
        magic_on_beat(phase)

    # ── Flash Automatik overlay ───────────────────────────────────────────────
    if play_settings["flash_automatik"] and mode != "Magic Auto":
        from backend.state import app_state as _s
        flash_events = [e for e in _s.events if e.type == "flash"]
        if flash_events and (phase == "DROP" or beat_in_bar == 1):
            for e in flash_events:
                if e.active:
                    e.stop(_s.engine)
            random.choice(flash_events).start(_s.engine)


async def audio_loop():
    """100 Hz audio-to-light ticker (equivalent to old ui.timer(0.01))."""
    from backend.state import play_settings

    while True:
        try:
            source = play_settings["source_mode"]

            if source == "MP3" and play_settings["is_active"]:
                elapsed = get_current_time()
                if elapsed > 0.0:
                    b_idx = audio_state["current_beat_idx"]
                    beats = audio_state.get("beat_times", [])
                    if b_idx < len(beats) and elapsed >= beats[b_idx]:
                        beat_in_bar = ((b_idx + audio_state.get("beat_offset", 0)) % 4) + 1
                        trigger_lights(beat_in_bar, audio_state.get("last_state", "DROP"))
                        audio_state["current_beat_idx"] += 1

                    # Structure detection
                    f_idx = audio_state.get("current_frame_idx", 0)
                    frames_times = audio_state.get("frames_times", [])
                    structure = audio_state.get("structure", [])
                    while f_idx < len(frames_times) and frames_times[f_idx] < elapsed:
                        f_idx += 1
                        audio_state["current_frame_idx"] = f_idx
                    if f_idx < len(structure):
                        current_state = structure[f_idx]
                        if current_state != audio_state.get("last_state"):
                            audio_state["last_state"] = current_state

            elif source == "LIVE" and play_settings["is_active"]:
                if live_audio_state["is_listening"] and live_audio_state["beat_triggered"]:
                    live_audio_state["beat_triggered"] = False
                    beat_in_bar = live_audio_state["beat_index"] + 1
                    trigger_lights(beat_in_bar, live_audio_state.get("phase", "DROP"))

            # Magic auto continuous apply (smooth fading)
            if play_settings["mode"] == "Magic Auto" and play_settings["is_active"]:
                from backend.state import app_state
                if source == "MP3":
                    phase = audio_state.get("last_state", "DROP")
                    if not audio_state.get("is_playing", False):
                        await asyncio.sleep(0.01)
                        continue
                else:
                    phase = live_audio_state.get("phase", "DROP")
                    if not live_audio_state["is_listening"]:
                        await asyncio.sleep(0.01)
                        continue
                magic_apply(app_state.engine, phase)

        except Exception:
            pass

        await asyncio.sleep(0.01)  # 100 Hz
