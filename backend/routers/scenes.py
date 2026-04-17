"""
Scenes & Banks router.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


@router.get("/banks")
def list_banks():
    from backend.state import app_state
    return app_state.engine.banks


class BankCreate(BaseModel):
    name: str


@router.post("/banks")
def create_bank(body: BankCreate):
    from backend.state import app_state
    engine = app_state.engine
    if any(b["name"] == body.name for b in engine.banks):
        raise HTTPException(400, f"Bank '{body.name}' already exists")
    bank = {"name": body.name, "scenes": []}
    engine.banks.append(bank)
    return bank


@router.delete("/banks/{bank_name}")
def delete_bank(bank_name: str):
    from backend.state import app_state
    engine = app_state.engine
    bank = next((b for b in engine.banks if b["name"] == bank_name), None)
    if not bank:
        raise HTTPException(404, f"Bank '{bank_name}' not found")
    engine.banks.remove(bank)
    return {"deleted": bank_name}


class SceneCreate(BaseModel):
    name:  str
    color: str = "#ffffff"


@router.post("/banks/{bank_name}/scenes/capture")
def capture_scene(bank_name: str, body: SceneCreate):
    """Snapshot current fixture values as a new scene."""
    from backend.state import app_state
    engine = app_state.engine
    bank = next((b for b in engine.banks if b["name"] == bank_name), None)
    if not bank:
        raise HTTPException(404, f"Bank '{bank_name}' not found")

    data = {f.id: dict(f.values) for f in engine.fixtures}
    scene = {"name": body.name, "color": body.color, "data": data}
    bank["scenes"].append(scene)
    return scene


@router.post("/banks/{bank_name}/scenes/{scene_idx}/load")
def load_scene(bank_name: str, scene_idx: int):
    from backend.state import app_state
    engine = app_state.engine
    bank = next((b for b in engine.banks if b["name"] == bank_name), None)
    if not bank:
        raise HTTPException(404, f"Bank '{bank_name}' not found")
    if scene_idx >= len(bank["scenes"]):
        raise HTTPException(404, "Scene index out of range")

    scene = bank["scenes"][scene_idx]
    data = scene.get("data", {})
    for f in engine.fixtures:
        if f.id in data:
            for k, v in data[f.id].items():
                f.set(k, v)
    return {"loaded": scene["name"]}


@router.delete("/banks/{bank_name}/scenes/{scene_idx}")
def delete_scene(bank_name: str, scene_idx: int):
    from backend.state import app_state
    engine = app_state.engine
    bank = next((b for b in engine.banks if b["name"] == bank_name), None)
    if not bank:
        raise HTTPException(404, f"Bank '{bank_name}' not found")
    if scene_idx >= len(bank["scenes"]):
        raise HTTPException(404, "Scene index out of range")
    deleted = bank["scenes"].pop(scene_idx)
    return {"deleted": deleted["name"]}
