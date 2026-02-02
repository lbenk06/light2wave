from nicegui import ui
from gui.app import create_app

create_app()
ui.run(title='Wave2Light', port=8081)  # port anpassen falls 8080 blockiert ist