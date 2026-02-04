import json
from pathlib import Path

BASE_DIR=Path(__file__).resolve().parent.parent
DATA_DIR=BASE_DIR/"data"


class Event:

    def __init__(self, name, roles):
        self.name=name
        self.roles=roles

    def trigger(self, engine):
        for fixture in engine.fixtures:
            for role, value in self.roles.items():
                if fixture.has(role):
                    fixture.set(role, value)

def load_events_from_json(filename: str):
    path=DATA_DIR/filename

    with open(path, "r") as f:
        data=json.load(f)
    
    return [Event(e["name"], e["roles"]) for e in data]