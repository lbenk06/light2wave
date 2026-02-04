from nicegui import ui
from gui.state import state

def create():
    ui.label('LIVE').classes('text-h4')


    with ui.row().classes('w-full'):
        #Bereich Traverse


        with ui.column().classes('w-2/3'):
            ui.label("Bühne")
            #Visualiesierung

        #rechter bereich mit den events
        with ui.column().classes('w-1/3'):
            ui.label("Events").classes("text-h5")

            for event in state.events:
                ui.button(
                    event.name,
                    on_click=lambda e=event: e.trigger(state.engine)
                ).classes("w-full")
