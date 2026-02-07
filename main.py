from nicegui import ui, app
from gui.app import create_app

create_app()


app.add_static_files('/static', 'gui/static')

ui.run(
    host='0.0.0.0',
    port=8081,
)





 