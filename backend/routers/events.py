"""
Events router — list, trigger, start, stop, stop-all, CRUD.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/events", tags=["events"])


class EventCreate(BaseModel):
    name:      str
    type:      str = "dynamic"   # static | dynamic | flash | stop_all
    generator: str | None = None
    target_role: str = "dimmer"
    speed:     float = 1.0
    width:     float = 5.0
    roles:     dict = {}


@router.get("")
def list_events():
    from backend.state import app_state
    return [
        {"name": e.name, "type": e.type, "active": e.active, "data": e.data}
        for e in app_state.events
    ]


@router.post("/{name}/trigger")
def trigger_event(name: str):
    from backend.state import app_state
    ev = next((e for e in app_state.events if e.name == name), None)
    if not ev:
        raise HTTPException(404, f"Event '{name}' not found")
    ev.trigger(app_state.engine)
    return {"name": name, "active": ev.active}


@router.post("/{name}/start")
def start_event(name: str):
    from backend.state import app_state
    ev = next((e for e in app_state.events if e.name == name), None)
    if not ev:
        raise HTTPException(404, f"Event '{name}' not found")
    ev.start(app_state.engine)
    return {"name": name, "active": True}


@router.post("/{name}/stop")
def stop_event(name: str):
    from backend.state import app_state
    ev = next((e for e in app_state.events if e.name == name), None)
    if not ev:
        raise HTTPException(404, f"Event '{name}' not found")
    ev.stop(app_state.engine)
    return {"name": name, "active": False}


@router.post("/{name}/flash")
def flash_event(name: str):
    """Stop any running flash events and fire this one."""
    from backend.state import app_state
    # stop all active flash events
    for e in app_state.events:
        if e.type == "flash" and e.active:
            e.stop(app_state.engine)
    ev = next((e for e in app_state.events if e.name == name), None)
    if not ev:
        raise HTTPException(404, f"Event '{name}' not found")
    ev.start(app_state.engine)
    return {"name": name, "active": True}


@router.post("/stop_all")
def stop_all():
    from backend.state import app_state
    engine = app_state.engine
    for ev in engine.active_overlays[:]:
        ev.stop(engine)
    for f in engine.fixtures:
        for role in ["dimmer", "red", "green", "blue", "white", "strobe"]:
            if f.has(role):
                f.set(role, 0)
    return {"stopped": "all"}


@router.delete("/{name}")
def delete_event(name: str):
    from backend.state import app_state
    ev = next((e for e in app_state.events if e.name == name), None)
    if not ev:
        raise HTTPException(404, f"Event '{name}' not found")
    if ev.active:
        ev.stop(app_state.engine)
    app_state.events.remove(ev)
    return {"deleted": name}


@router.post("/save")
def save_events():
    """Persist current events list to events_default.json."""
    import json, os
    from backend.state import app_state
    path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "events_default.json")
    data = [e.data | {"name": e.name} for e in app_state.events]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return {"saved": len(data)}
