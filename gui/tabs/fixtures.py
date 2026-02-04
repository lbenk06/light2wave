from nicegui import ui
from gui.state import state



def create():
    ui.label('Geräte').classes('text-h4')

    for fixture in state.engine.fixtures:
        with ui.card():
            ui.label(fixture.id)
            for role in fixture.roles:
                ui.slider(min=0, max=1, step=0.01,
                          value=fixture.get(role),
                          on_change=lambda e, f=fixture, r=role: f.set(r, e.value)).props('label')