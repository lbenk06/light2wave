from nicegui import ui
from gui.state import state


def create():
    ui.label('Traverse').classes('text-h4')

    container=ui.row()

    def update():
        container.clear()
        for f in state.engine.fixtures:
            color=f.get_color()
            ui.label('⬤').style(f'color: rgb({color[0]},{color[1]},{color[2]}); font-size: 40px')
        
    ui.timer(0.1, update)