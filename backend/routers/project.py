"""
Project router — save/load show file, DMX port management.
"""
import serial.tools.list_ports
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/project", tags=["project"])

PROJECT_FILE = "projects/my_show.json"


@router.post("/save")
def save_project():
    from backend.state import app_state
    from projects.projects_io import save_project as _save
    _save(app_state.engine, PROJECT_FILE)
    return {"saved": PROJECT_FILE}


@router.post("/load")
def load_project():
    from backend.state import app_state
    app_state.load_project(PROJECT_FILE)
    return {"loaded": PROJECT_FILE}


# ── DMX ───────────────────────────────────────────────────────────────────────

@router.get("/dmx/ports")
def list_dmx_ports():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return {"ports": ports}


class DmxConnectBody(BaseModel):
    port: str


@router.post("/dmx/connect")
def dmx_connect(body: DmxConnectBody):
    from backend.state import app_state
    if app_state.dmx_interface is None:
        raise HTTPException(500, "DMX output not initialized")
    ok = app_state.dmx_interface.connect(body.port)
    if not ok:
        raise HTTPException(400, f"Failed to connect to {body.port}")
    return {"connected": True, "port": body.port}


@router.post("/dmx/disconnect")
def dmx_disconnect():
    from backend.state import app_state
    if app_state.dmx_interface:
        app_state.dmx_interface.disconnect()
    return {"connected": False}


@router.get("/dmx/status")
def dmx_status():
    from backend.state import app_state
    connected = (
        app_state.dmx_interface is not None
        and app_state.dmx_interface.controller is not None
    )
    return {"connected": connected}


@router.get("/dmx/universe")
def dmx_universe():
    from backend.state import app_state
    return {"channels": list(app_state.universe)}
