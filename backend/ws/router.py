"""
WebSocket endpoint — single /ws connection for all real-time data.
Also handles incoming commands from the client.
"""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.ws.hub import hub

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                await _handle_command(msg)
            except Exception:
                pass
    except WebSocketDisconnect:
        hub.disconnect(ws)


async def _handle_command(msg: dict):
    """Handle incoming WS commands from the React frontend."""
    cmd = msg.get("type")

    if cmd == "set_master":
        from backend.state import app_state
        app_state.engine.master_dimmer = max(0.0, min(1.0, float(msg["value"])))

    elif cmd == "set_parked_color":
        from backend.state import app_state
        idx = int(msg["fixture_idx"])
        role = msg["role"]
        value = float(msg["value"])
        app_state.engine.set_parked_color(idx, **{role: value})

    elif cmd == "set_magic_auto":
        from engine.magic_auto import magic_auto_state
        key = msg.get("key")
        if key and key in magic_auto_state:
            magic_auto_state[key] = msg["value"]

    elif cmd == "trigger_event":
        from backend.state import app_state
        name = msg.get("name")
        ev = next((e for e in app_state.events if e.name == name), None)
        if ev:
            ev.trigger(app_state.engine)

    elif cmd == "flash_event":
        from backend.state import app_state
        for e in app_state.events:
            if e.type == "flash" and e.active:
                e.stop(app_state.engine)
        name = msg.get("name")
        ev = next((e for e in app_state.events if e.name == name), None)
        if ev:
            ev.start(app_state.engine)
