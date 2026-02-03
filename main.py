#from nicegui import ui
#from gui.app import create_app

#create_app()
#ui.run(title='Wave2Light', port=8081)  # port anpassen falls 8080 blockiert ist

import time
from engine.light_engine import LightEngine
from projects.projects_io import load_project, load_fixtures_from_json, apply_scene

engine=LightEngine()

project=load_project("projects/my_show.json")
load_fixtures_from_json(project["fixtures"], engine)


scene_data=project["banks"][0]["scenes"][0]["values"]

try:
    while True:
        apply_scene(scene_data, engine.fixtures)
        universe=engine.render()
        print(f"UNiverse: {universe[:30]}")
        time.sleep(1/40)
except KeyboardInterrupt:
    print("Schleife beendet")

 