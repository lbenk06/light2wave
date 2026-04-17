"""
Central application state — shared between all routers, WebSocket hub,
and background tasks. Wraps the existing AppState singleton and adds
the audio/playback settings that previously lived in gui/tabs/audio.py.
"""
import sys
import os

# Make sure project root is on path so all existing modules can be imported
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gui.state import state as _app_state          # existing singleton
from audio.audio_live import live_audio_state
from audio.audio_file import audio_state
from engine.magic_auto import magic_auto_state

# Re-export the core singleton
app_state = _app_state

# play_settings moved here from gui/tabs/audio.py so all backend tasks can access it
play_settings: dict = {
    "source_mode":    "MP3",        # "MP3" | "LIVE"
    "mode":           "Scene Sync", # "Scene Sync" | "Custom Timeline" | "Magic Auto"
    "selected_bank":  None,
    "current_scene_idx": 0,
    "flash_automatik": True,
    "custom_timeline": {"BREAK": [], "BUILDUP": [], "DROP": []},
    "custom_step_idx": 0,
    "last_active_item": None,
    "is_active":      False,        # Audio mode on/off
}
