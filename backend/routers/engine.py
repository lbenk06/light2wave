"""
Engine router — master dimmer, park/unpark, fixture channel control.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/engine", tags=["engine"])


class MasterDimmerBody(BaseModel):
    value: float


class ParkedColorBody(BaseModel):
    red:    float | None = None
    green:  float | None = None
    blue:   float | None = None
    white:  float | None = None
    dimmer: float | None = None


class FixtureChannelBody(BaseModel):
    role:  str
    value: float


@router.get("/state")
def get_engine_state():
    from backend.state import app_state
    engine = app_state.engine
    return {
        "master_dimmer":   engine.master_dimmer,
        "parked_fixtures": list(engine.parked_fixtures),
        "active_overlays": [e.name for e in engine.active_overlays],
        "fixture_count":   len(engine.fixtures),
    }


@router.post("/master")
def set_master(body: MasterDimmerBody):
    from backend.state import app_state
    app_state.engine.master_dimmer = max(0.0, min(1.0, body.value))
    return {"master_dimmer": app_state.engine.master_dimmer}


@router.post("/blackout")
def blackout():
    from backend.state import app_state
    app_state.engine.master_dimmer = 0.0
    return {"master_dimmer": 0.0}


@router.post("/fixtures/{idx}/park")
def park_fixture(idx: int, body: ParkedColorBody | None = None):
    from backend.state import app_state
    engine = app_state.engine
    if idx >= len(engine.fixtures):
        raise HTTPException(404, "Fixture not found")
    engine.park_fixture(idx)
    engine.set_parked_color(idx, dimmer=1.0)
    if body:
        kw = {k: v for k, v in body.model_dump().items() if v is not None}
        if kw:
            engine.set_parked_color(idx, **kw)
    return {"parked": True, "idx": idx}


@router.delete("/fixtures/{idx}/park")
def unpark_fixture(idx: int):
    from backend.state import app_state
    app_state.engine.unpark_fixture(idx)
    return {"parked": False, "idx": idx}


@router.delete("/fixtures/park")
def unpark_all():
    from backend.state import app_state
    for i in list(app_state.engine.parked_fixtures):
        app_state.engine.unpark_fixture(i)
    return {"unparked": "all"}


@router.post("/fixtures/{idx}/color")
def set_parked_color(idx: int, body: ParkedColorBody):
    from backend.state import app_state
    engine = app_state.engine
    if idx not in engine.parked_fixtures:
        raise HTTPException(400, "Fixture not parked")
    kw = {k: v for k, v in body.model_dump().items() if v is not None}
    engine.set_parked_color(idx, **kw)
    return {"ok": True}


@router.post("/fixtures/{fixture_id}/channel")
def set_fixture_channel(fixture_id: str, body: FixtureChannelBody):
    from backend.state import app_state
    fix = next((f for f in app_state.engine.fixtures if f.id == fixture_id), None)
    if not fix:
        raise HTTPException(404, "Fixture not found")
    fix.set(body.role, body.value)
    return {"ok": True}
