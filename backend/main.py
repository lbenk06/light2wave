"""
light2wave — FastAPI backend entry point.

Start with:
  uvicorn backend.main:app --host 0.0.0.0 --port 8081 --reload
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

# ── Import routers ────────────────────────────────────────────────────────────
from backend.routers.engine    import router as engine_router
from backend.routers.events    import router as events_router
from backend.routers.audio     import router as audio_router
from backend.routers.fixtures  import router as fixtures_router
from backend.routers.scenes    import router as scenes_router
from backend.routers.traverses import router as traverses_router
from backend.routers.project   import router as project_router
from backend.ws.router         import router as ws_router
from backend.ws.hub            import start_background_tasks
from backend.audio_loop        import audio_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    # State singleton initialises itself on import (loads project + events)
    from backend.state import app_state
    from dmx.output import DMXOutput

    # Start DMX output thread (40 Hz, daemon)
    app_state.dmx_interface = DMXOutput(app_state.engine)
    print("[light2wave] DMX output thread started")

    # Start WebSocket broadcast tasks (asyncio, non-blocking)
    await start_background_tasks()
    print("[light2wave] WebSocket broadcast tasks started")

    # Start audio-to-light loop (100 Hz asyncio task)
    asyncio.create_task(audio_loop())
    print("[light2wave] Audio loop started")

    print("[light2wave] Backend ready at http://0.0.0.0:8081")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    if app_state.dmx_interface:
        app_state.dmx_interface.running = False
    print("[light2wave] Shutdown complete")


app = FastAPI(title="light2wave", version="2.0.0", lifespan=lifespan)

# ── CORS (allow Vite dev server on :5173) ────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(engine_router)
app.include_router(events_router)
app.include_router(audio_router)
app.include_router(fixtures_router)
app.include_router(scenes_router)
app.include_router(traverses_router)
app.include_router(project_router)
app.include_router(ws_router)

# ── Serve React build (production) ───────────────────────────────────────────
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    print(f"[light2wave] Serving React build from {FRONTEND_DIST}")
