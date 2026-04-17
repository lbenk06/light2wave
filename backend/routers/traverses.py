"""
Traverses router.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/traverses", tags=["traverses"])


@router.get("")
def list_traverses():
    from backend.state import app_state
    result = []
    for t in app_state.engine.traverses:
        result.append({
            "name": t.name,
            "x1": t.x1, "y1": t.y1,
            "x2": t.x2, "y2": t.y2,
            "snap_distance": t.snap_distance,
            "snap_points": [
                {
                    "idx":      i,
                    "x":        sp["x"],
                    "y":        sp["y"],
                    "occupied": sp["occupied"],
                    "fixture_id": sp["fixture"].id if sp["fixture"] else None,
                }
                for i, sp in enumerate(t.snap_points)
            ],
        })
    return result


class TraverseCreate(BaseModel):
    name:          str
    x1:            float
    y1:            float
    x2:            float
    y2:            float
    snap_distance: float = 40.0


@router.post("")
def create_traverse(body: TraverseCreate):
    from backend.state import app_state
    from engine.traverse_snap import Traverse
    engine = app_state.engine
    if any(t.name == body.name for t in engine.traverses):
        raise HTTPException(400, f"Traverse '{body.name}' already exists")
    t = Traverse(
        x1=body.x1, y1=body.y1,
        x2=body.x2, y2=body.y2,
        snap_distance=body.snap_distance,
        name=body.name,
    )
    engine.traverses.append(t)
    return {"name": t.name, "snap_points": len(t.snap_points)}


@router.delete("/{name}")
def delete_traverse(name: str):
    from backend.state import app_state
    engine = app_state.engine
    t = next((tr for tr in engine.traverses if tr.name == name), None)
    if not t:
        raise HTTPException(404, f"Traverse '{name}' not found")
    # Remove fixtures on this traverse
    for sp in t.snap_points:
        if sp["fixture"]:
            engine.fixtures.remove(sp["fixture"])
    engine.traverses.remove(t)
    return {"deleted": name}
