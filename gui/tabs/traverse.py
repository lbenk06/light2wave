from nicegui import ui
from gui.state import state


def create():
    ui.label('Traverse').classes('text-h4')

    with ui.element('div').style('position: relative; width: 800px; height: 300px; margin: auto;') as stage:

        ui.image('/assets/traverse.png').style('position: absolute; top: 0; left: 0; width: 100%; height: 100%;')

        fixture_elements={}

        for fixture in state.engine.fixtures:
            r,g,b=fixture.get_color()

            el = ui.element('div').style(
                f'''
                position: absolute;
                left: {fixture.x}px;
                top: {fixture.y}px;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                background-color: rgb({r},{g},{b});
                border: 2px solid black;
                '''
            )

            fixture_elements[fixture]=el

    def update_colors():
        for fixture, el in fixture_elements.items():
            r,g,g=fixture.get_color()
            el.style(
                f'background-color: rgb({r},{g},{b});'
            )
    ui.timer(1 / 20, update_colors)  #20fps