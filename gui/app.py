from nicegui import ui

from gui.tabs import (
    live,
    audio,
    fixtures,
    traverse,
    scenes,
    dmx,
)

def create_app():
    ui.page_title('Wave2Light')

    with ui.tabs().classes('w-full') as tabs:
        tab_live = ui.tab('LIVE')
        tab_audio = ui.tab('Audio In')
        tab_fixtures = ui.tab('Geräte')
        tab_traverse = ui.tab('Traverse')
        tab_scenes = ui.tab('Szenen')
        tab_dmx = ui.tab('DMX')

    with ui.tab_panels(tabs, value=tab_audio).classes('w-full'):
            
        with ui.tab_panel(tab_live):
            live.create()
       
        with ui.tab_panel(tab_audio):
            audio.create()

        with ui.tab_panel(tab_fixtures):
            fixtures.create()

        with ui.tab_panel(tab_traverse):
            traverse.create()

        with ui.tab_panel(tab_scenes):
            scenes.create()

        with ui.tab_panel(tab_dmx):
            dmx.create()
