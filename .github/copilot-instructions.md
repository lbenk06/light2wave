<!-- Copilot instructions for Light2Wave - concise, actionable guidance for AI coding agents -->
# Light2Wave — Copilot Instructions

Purpose: help AI agents be immediately productive in the Light2Wave repository by describing architecture, conventions, workflows, and concrete examples.

- **Project entry:** `main.py` launches a NiceGUI app and calls `create_app()` in `gui/app.py`. Run locally with `python main.py` (default port 8081).
- **UI pattern:** each tab under `gui/tabs/` exposes a `create()` function. `gui/app.py` composes tabs; to add a tab, create `gui/tabs/<name>.py` with `def create():` and import it from `gui/app.py`.
- **Engine responsibility:** `engine/light_engine.py` is intended to coordinate audio input → scene logic → DMX output. Currently empty; place orchestration, scheduling, and update loops here.
- **Fixture model:** see `fixtures/fixture.py` — `Fixture(profile, address)` stores normalized 0.0–1.0 role values, `render(universe)` writes 0–255 bytes starting at `address-1`. Channel definitions live in `fixtures/profiles.py` (each channel has a `role` key used by scenes and engine).
- **DMX backends:** `dmx/` contains hardware integration stubs: `dmx_enttec.py` (hardware), `dmx_mock.py` (simulator). `dmx/dmx_test.py` demonstrates using `DMXEnttecPro.Controller` with a COM port — useful for hardware testing.
- **Scenes:** scene implementations live in `scenes/` (e.g., `dark.py`, `wash.py`, `impact.py`). They should compute target `Fixture.set(role, value)` updates based on engine inputs.
- **Conventions & patterns:**
  - All UI elements use NiceGUI and are created imperatively inside `create()` functions.
  - Data flow: audio input → `engine/light_engine.py` (analysis) → scene selection/parameters → modify `Fixture` objects → call `Fixture.render(universe)` → push to DMX backend.
  - Channel roles (strings like `dimmer`, `red`, `pan`) are the canonical keys across profiles, scenes, and fixtures.
- **Developer workflows:**
  - Run the app: `python main.py` (ensure `requirements.txt` installed in venv).
  - Hardware DMX test: run `python dmx/dmx_test.py` and adjust COM port.
  - Quick UI dev: edit `gui/tabs/*` and refresh the NiceGUI page.
- **Testing & debugging tips:**
  - Use `dmx_mock.py` while developing to capture `universe` arrays instead of sending live DMX.
  - Inspect `Fixture.render()` behavior by creating a small script that creates a `Fixture` and prints the `universe` array after `render()`.
- **Files to read when making changes:** `main.py`, `gui/app.py`, `engine/light_engine.py`, `fixtures/fixture.py`, `fixtures/profiles.py`, `dmx/dmx_test.py`, `scenes/`.

Example snippets

- Add a new tab: create `gui/tabs/mytab.py` with

```python
from nicegui import ui

def create():
    ui.label('My Tab').classes('text-h4')
```

- Create a simple DMX universe test:

```python
from fixtures.fixture import Fixture
from fixtures.profiles import LED_PAR_6CH

f = Fixture('par1', LED_PAR_6CH, 1)
f.set('red', 1.0)
u = [0]*512
f.render(u)
print(u[:6])
```

What to avoid / notes

- Do not assume the engine exists yet — `engine/light_engine.py` is the intended orchestration point and may be empty.
- Hardware code may require OS-specific serial ports (see `dmx/dmx_test.py` on COM ports for Windows).

If anything here is unclear or you'd like additional examples (e.g., scene templates, a mock DMX backend, or a small engine skeleton), tell me which part to expand and I'll iterate.
