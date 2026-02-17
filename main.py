from nicegui import ui, app
from gui.app import create_app
from gui.state import state
from dmx.output import DMXOutput


#1. App erstellen
create_app()

app.add_static_files('/static', 'gui/static')


#2. DMX Output starten
state.dmx_interface=DMXOutput(state.engine)


#3. Server starten

ui.run(
    host='0.0.0.0',
    port=8081,
)





 