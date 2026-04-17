"""
Audio router — file analysis, playback, live input, play_settings, magic_auto.
"""
import os
import shutil
import tempfile
import asyncio

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter(prefix="/api/audio", tags=["audio"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "projects", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Devices ───────────────────────────────────────────────────────────────────

@router.get("/devices")
def get_devices():
    from audio.audio_live import get_input_devices
    return get_input_devices()


# ── Live Input ────────────────────────────────────────────────────────────────

class LiveStartBody(BaseModel):
    device_id: int


@router.post("/live/start")
def live_start(body: LiveStartBody):
    from audio.audio_live import start_listening
    ok, msg = start_listening(body.device_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"listening": True, "message": msg}


@router.post("/live/stop")
def live_stop():
    from audio.audio_live import stop_listening
    stop_listening()
    return {"listening": False}


@router.get("/live/state")
def live_state():
    from audio.audio_live import live_audio_state
    return live_audio_state


# ── File Analysis ─────────────────────────────────────────────────────────────

@router.post("/file/upload")
async def upload_file(file: UploadFile = File(...)):
    """Receive audio file, save to uploads/, trigger background analysis."""
    dest = os.path.join(UPLOAD_DIR, file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    from audio.audio_file import analyze_audio_background, audio_state

    result: dict = {"done": False}

    def on_success():
        result["done"] = True

    def on_error(err):
        result["error"] = err

    analyze_audio_background(dest, on_success, on_error)
    return {"status": "analyzing", "file": file.filename}


@router.get("/file/state")
def file_state():
    from audio.audio_file import audio_state
    return {
        "is_playing":       audio_state.get("is_playing", False),
        "bpm":              audio_state.get("bpm", 0.0),
        "file_path":        audio_state.get("file_path", ""),
        "last_state":       audio_state.get("last_state", "BREAK"),
        "current_beat_idx": audio_state.get("current_beat_idx", 0),
    }


@router.post("/file/play")
def file_play():
    from audio.audio_file import toggle_playback, audio_state
    toggle_playback()
    return {"is_playing": audio_state.get("is_playing", False)}


@router.post("/file/stop")
def file_stop():
    from audio.audio_file import toggle_playback, audio_state
    if audio_state.get("is_playing", False):
        toggle_playback()
    return {"is_playing": False}


@router.post("/beat_offset")
def beat_offset(delta: int):
    from audio.audio_file import audio_state
    audio_state["beat_offset"] = (audio_state.get("beat_offset", 0) + delta) % 4
    return {"beat_offset": audio_state["beat_offset"]}


# ── Play Settings ─────────────────────────────────────────────────────────────

class PlaySettingsBody(BaseModel):
    source_mode:      str | None = None
    mode:             str | None = None
    selected_bank:    str | None = None
    flash_automatik:  bool | None = None
    is_active:        bool | None = None
    custom_timeline:  dict | None = None


@router.post("/play_settings")
def update_play_settings(body: PlaySettingsBody):
    from backend.state import play_settings
    data = body.model_dump(exclude_none=True)
    play_settings.update(data)
    return play_settings


@router.get("/play_settings")
def get_play_settings():
    from backend.state import play_settings
    return play_settings


# ── Magic Auto ────────────────────────────────────────────────────────────────

@router.post("/magic_auto")
def update_magic_auto(body: dict):
    from engine.magic_auto import magic_auto_state
    for k, v in body.items():
        if k in magic_auto_state:
            magic_auto_state[k] = v
    return {k: v for k, v in magic_auto_state.items() if not callable(v)}


@router.get("/magic_auto")
def get_magic_auto():
    from engine.magic_auto import magic_auto_state
    return {k: v for k, v in magic_auto_state.items() if not callable(v)}
