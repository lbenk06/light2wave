from engine.light_engine import LightEngine
from projects.projects_io import load_project, load_fixtures_from_json, load_banks_from_json
from engine.events import load_events_from_json

class AppState:
    def __init__(self):
        self.engine = LightEngine()
        self.project = None
        self.current_scene=None
        self.universe=[0]*512

        self.load_project("projects/my_show.json")
        self.load_events()

    def load_project(self, path):
        self.project = load_project(path)
        
        if self.project:
            load_fixtures_from_json(self.project.get("fixtures", []), self.engine)
            load_banks_from_json(self.project.get("banks", []), self.engine)
        else:
            print("f Projekt konnte nicht geladen werden")

    def render(self):
        self.universe=self.engine.render()
        return self.universe
    
    def load_events(self):
        try:
            self.events=load_events_from_json("events_default.json")
            print(f"{len(self.events)} Events geladen.")
        except Exception as e:
            print(f"Warnung: Events konnten nicht geladen werden: {e}")
            self.events={}

state=AppState()