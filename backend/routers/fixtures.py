"""
Fixtures router — list fixtures, profiles, add/remove, place on traverse.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/fixtures", tags=["fixtures"])


@router.get("")
def list_fixtures():
    from backend.state import app_state
    engine = app_state.engine
    result = []
    for idx, f in enumerate(engine.fixtures):
        result.append({
            "idx":       idx,
            "id":        f.id,
            "profile_id": f.profile_id,
            "address":   f.address,
            "x":         f.x,
            "y":         f.y,
            "traverse":  f.traverse.name if f.traverse else None,
            "snap_point": f.snap_point,
            "values":    f.values,
            "parked":    idx in engine.parked_fixtures,
            "channels":  [ch["role"] for ch in f.profile["channels"]],
        })
    return result


@router.get("/profiles")
def list_profiles():
    from backend.state import app_state
    return list(app_state.engine.profiles.keys())


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str):
    from backend.state import app_state
    p = app_state.engine.profiles.get(profile_id)
    if not p:
        raise HTTPException(404, f"Profile '{profile_id}' not found")
    return p


class PlaceFixtureBody(BaseModel):
    profile_id:     str
    traverse_name:  str
    snap_index:     int
    address:        int | None = None
    fixture_id:     str | None = None


@router.post("/place")
def place_fixture(body: PlaceFixtureBody):
    from backend.state import app_state
    engine = app_state.engine

    traverse = next((t for t in engine.traverses if t.name == body.traverse_name), None)
    if not traverse:
        raise HTTPException(404, f"Traverse '{body.traverse_name}' not found")
    if body.snap_index >= len(traverse.snap_points):
        raise HTTPException(400, "snap_index out of range")
    snap = traverse.snap_points[body.snap_index]
    if snap["occupied"]:
        raise HTTPException(400, "Snap point already occupied")

    fixture = engine.create_fixture(
        profile_id=body.profile_id,
        x=snap["x"],
        y=snap["y"],
        fixture_id=body.fixture_id,
        address=body.address,
    )
    fixture.traverse = traverse
    fixture.snap_point = body.snap_index
    snap["occupied"] = True
    snap["fixture"] = fixture

    return {"id": fixture.id, "address": fixture.address}


@router.delete("/{fixture_id}")
def delete_fixture(fixture_id: str):
    from backend.state import app_state
    engine = app_state.engine
    fix = next((f for f in engine.fixtures if f.id == fixture_id), None)
    if not fix:
        raise HTTPException(404, "Fixture not found")

    # Free snap point
    if fix.traverse and fix.snap_point is not None:
        sp = fix.traverse.snap_points[fix.snap_point]
        sp["occupied"] = False
        sp["fixture"] = None

    engine.fixtures.remove(fix)
    return {"deleted": fixture_id}


class SetChannelBody(BaseModel):
    role:  str
    value: float   # 0.0 – 1.0


@router.post("/{fixture_idx}/channel")
def set_fixture_channel(fixture_idx: int, body: SetChannelBody):
    from backend.state import app_state
    engine = app_state.engine
    if fixture_idx < 0 or fixture_idx >= len(engine.fixtures):
        raise HTTPException(400, "fixture_idx out of range")
    engine.fixtures[fixture_idx].set(body.role, max(0.0, min(1.0, body.value)))
    return {"ok": True}


class CreateProfileBody(BaseModel):
    name:     str
    channels: list[dict]   # [{"role": "dimmer"}, ...]


@router.post("/profiles")
def create_profile(body: CreateProfileBody):
    import json, os
    from backend.state import app_state
    profile_id = body.name.lower().replace(" ", "_")
    if profile_id in app_state.engine.profiles:
        raise HTTPException(400, f"Profile '{profile_id}' already exists")
    profile = {
        "profile_id": profile_id,
        "name":       body.name,
        "channels":   [{"name": ch["role"].capitalize(), "role": ch["role"]} for ch in body.channels],
    }
    app_state.engine.profiles[profile_id] = profile
    # Persist to disk
    os.makedirs("projects", exist_ok=True)
    path = "projects/user_profiles.json"
    data = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            pass
    data[profile_id] = profile
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    return profile


@router.get("/profiles_full")
def list_profiles_full():
    from backend.state import app_state
    return list(app_state.engine.profiles.values())


class MoveFixtureBody(BaseModel):
    traverse_name: str
    snap_index:    int


@router.post("/{fixture_id}/move")
def move_fixture(fixture_id: str, body: MoveFixtureBody):
    from backend.state import app_state
    engine = app_state.engine
    fix = next((f for f in engine.fixtures if f.id == fixture_id), None)
    if not fix:
        raise HTTPException(404, "Fixture not found")

    # Free old snap point
    if fix.traverse and fix.snap_point is not None:
        old_sp = fix.traverse.snap_points[fix.snap_point]
        old_sp["occupied"] = False
        old_sp["fixture"] = None

    traverse = next((t for t in engine.traverses if t.name == body.traverse_name), None)
    if not traverse:
        raise HTTPException(404, f"Traverse '{body.traverse_name}' not found")

    snap = traverse.snap_points[body.snap_index]
    if snap["occupied"] and snap["fixture"] is not fix:
        raise HTTPException(400, "Target snap point already occupied")

    fix.traverse = traverse
    fix.snap_point = body.snap_index
    fix.x = snap["x"]
    fix.y = snap["y"]
    snap["occupied"] = True
    snap["fixture"] = fix

    return {"id": fix.id, "x": fix.x, "y": fix.y}
