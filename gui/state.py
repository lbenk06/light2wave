from engine.light_engine import LightEngine
from projects.projects_io import load_project, load_fixtures_from_json
from engine.events import load_events_from_json

class AppState:
    def __init__(self):
        self.engine = LightEngine()
        self.project = None
        self.current_scene=None
        self.universe=[0]*512

    def load_project(self, path):
        self.project = load_project(path)
        load_fixtures_from_json(self.project["fixtures"], self.engine)

    def render(self):
        self.universe=self.engine.render()
        return self.universe
    
    def load_events(self):
        self.events=load_events_from_json("events_default.json")
    
state=AppState()