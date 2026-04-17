"""
WebSocket connection hub.
- Manages all active WS connections
- Provides broadcast() to push JSON to all clients
- Background tasks push state at fixed intervals
"""
import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionHub:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, msg_type: str, payload: Any):
        if not self._connections:
            return
        data = json.dumps({"type": msg_type, "payload": payload, "ts": time.time()})
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def connected_count(self) -> int:
        return len(self._connections)


hub = ConnectionHub()


# ── Background push tasks ─────────────────────────────────────────────────────

async def _fixture_push_loop():
    """Push fixture colors + active overlays at 10 Hz."""
    from backend.state import app_state
    while True:
        try:
            fixtures_payload = []
            for f in app_state.engine.fixtures:
                r, g, b = f.get_color()
                idx = app_state.engine.fixtures.index(f)
                fixtures_payload.append({
                    "id":     f.id,
                    "idx":    idx,
                    "r": r, "g": g, "b": b,
                    "parked": idx in app_state.engine.parked_fixtures,
                    "x": f.x, "y": f.y,
                    "address": f.address,
                    "traverse": f.traverse.name if f.traverse else None,
                    "snap_point": f.snap_point,
                    "values": f.values,
                })
            await hub.broadcast("fixture_colors", fixtures_payload)

            overlays = [e.name for e in app_state.engine.active_overlays]
            await hub.broadcast("active_overlays", overlays)
        except Exception:
            pass
        await asyncio.sleep(0.1)   # 10 Hz


async def _audio_push_loop():
    """Push audio state at 25 Hz."""
    from backend.state import live_audio_state, audio_state, play_settings, magic_auto_state
    while True:
        try:
            await hub.broadcast("audio_live", {
                "is_listening":   live_audio_state["is_listening"],
                "beat_triggered": live_audio_state["beat_triggered"],
                "beat_index":     live_audio_state["beat_index"],
                "level":          live_audio_state["level"],
                "phase":          live_audio_state["phase"],
                "volume":         live_audio_state["volume"],
                "ml_active":      live_audio_state.get("ml_active", False),
            })
            await hub.broadcast("audio_file", {
                "is_playing":      audio_state.get("is_playing", False),
                "bpm":             audio_state.get("bpm", 0.0),
                "last_state":      audio_state.get("last_state", "BREAK"),
                "current_beat_idx": audio_state.get("current_beat_idx", 0),
                "file_path":       audio_state.get("file_path", ""),
            })
            await hub.broadcast("play_settings", {
                "source_mode":    play_settings["source_mode"],
                "mode":           play_settings["mode"],
                "selected_bank":  play_settings["selected_bank"],
                "flash_automatik": play_settings["flash_automatik"],
                "is_active":      play_settings["is_active"],
                "custom_timeline": play_settings["custom_timeline"],
            })
        except Exception:
            pass
        await asyncio.sleep(0.04)   # 25 Hz


async def _magic_auto_push_loop():
    """Push magic auto state at 5 Hz (color preview)."""
    from backend.state import magic_auto_state
    while True:
        try:
            exportable = {k: v for k, v in magic_auto_state.items()
                          if not callable(v)}
            await hub.broadcast("magic_auto", exportable)
        except Exception:
            pass
        await asyncio.sleep(0.2)   # 5 Hz


async def _engine_meta_push_loop():
    """Push engine meta (master dimmer, events list) at 5 Hz."""
    from backend.state import app_state
    while True:
        try:
            await hub.broadcast("engine_meta", {
                "master_dimmer":   app_state.engine.master_dimmer,
                "parked_fixtures": list(app_state.engine.parked_fixtures),
            })
            events_payload = [
                {"name": e.name, "type": e.type, "active": e.active}
                for e in app_state.events
            ]
            await hub.broadcast("events_state", events_payload)
        except Exception:
            pass
        await asyncio.sleep(0.2)   # 5 Hz


async def _dmx_monitor_loop():
    """Push first 32 DMX channels at 5 Hz for DmxTab monitor."""
    from backend.state import app_state
    while True:
        try:
            await hub.broadcast("dmx_monitor", {
                "channels": list(app_state.universe[:32])
            })
        except Exception:
            pass
        await asyncio.sleep(0.2)


async def start_background_tasks():
    asyncio.create_task(_fixture_push_loop())
    asyncio.create_task(_audio_push_loop())
    asyncio.create_task(_magic_auto_push_loop())
    asyncio.create_task(_engine_meta_push_loop())
    asyncio.create_task(_dmx_monitor_loop())
