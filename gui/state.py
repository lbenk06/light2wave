import os
from engine.light_engine import LightEngine
from engine.traverse_snap import Traverse
from projects.projects_io import (
    load_project, load_fixtures_from_json, load_banks_from_json,
    load_events_from_project, save_project
)
from engine.events import load_events_from_json

DEFAULT_PROJECT = "projects/my_show.json"


class AppState:
    def __init__(self):
        self.engine = LightEngine()
        self.project = None
        self.current_project_path = DEFAULT_PROJECT
        self.current_scene = None
        self.universe = [0] * 512
        self.events = []
        self.dmx_port = ""

        # Try loading existing project, fall back to defaults
        if os.path.exists(DEFAULT_PROJECT):
            self._load_full(DEFAULT_PROJECT)
        else:
            self._load_default_events()

    # ── Public API ────────────────────────────────────────────

    def load_project_file(self, path: str):
        """Lädt ein komplettes Projekt (Traverses, Fixtures, Szenen, Events)."""
        self._load_full(path)
        self.current_project_path = path

    def save_current_project(self):
        """Speichert das aktuelle Projekt in die aktuelle Datei."""
        self._do_save(self.current_project_path)

    def save_project_as(self, path: str):
        """Speichert unter neuem Pfad und wechselt darauf."""
        self._do_save(path)
        self.current_project_path = path

    def new_project(self, name: str):
        """Leert die Engine und legt ein neues Projekt an."""
        path = f"projects/{name}.json"
        self.engine.fixtures.clear()
        self.engine.traverses.clear()
        self.engine.banks = []
        self.engine.active_overlays = []
        self._load_default_events()
        self.current_project_path = path
        self._do_save(path)

    def render(self):
        self.universe = self.engine.render()
        return self.universe

    @property
    def project_name(self) -> str:
        return os.path.splitext(os.path.basename(self.current_project_path))[0]

    # ── Internal helpers ──────────────────────────────────────

    def _load_full(self, path: str):
        data = load_project(path)
        if data is None:
            print(f"Projekt nicht gefunden: {path}")
            return

        self.project = data

        # Traverses
        self.engine.traverses.clear()
        for td in data.get("traverses", []):
            t = Traverse(
                x1=td["x1"], y1=td["y1"],
                x2=td["x2"], y2=td["y2"],
                snap_distance=td.get("snap_distance", 40),
                name=td["name"]
            )
            self.engine.traverses.append(t)

        # Fixtures, Banks
        load_fixtures_from_json(data.get("fixtures", []), self.engine)
        load_banks_from_json(data.get("banks", []), self.engine)

        # Events — aus Projekt wenn vorhanden, sonst aus Default-Datei
        if data.get("events"):
            self.events = load_events_from_project(data["events"])
            print(f"{len(self.events)} Events aus Projekt geladen.")
        else:
            self._load_default_events()

        # DMX Port
        self.dmx_port = data.get("dmx_port", "")

    def _load_default_events(self):
        try:
            self.events = load_events_from_json("events_default.json")
            print(f"{len(self.events)} Events geladen.")
        except Exception as e:
            print(f"Warnung: Events konnten nicht geladen werden: {e}")
            self.events = []

    def _do_save(self, path: str):
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else "projects", exist_ok=True)
        save_project(
            engine=self.engine,
            filename=path,
            events=self.events,
            dmx_port=self.dmx_port,
        )
        print(f"Projekt gespeichert: {path}")


state = AppState()
