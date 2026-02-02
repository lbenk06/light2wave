from nicegui import ui

def create():
    ui.label('Geräte').classes('text-h4')

    fixtures = ["Moving Head", "LED Bar", "Strobe"]
    selected_label = ui.label("Keine Fixture gewählt")

    # Buttons dynamisch erstellen
    for f in fixtures:
        ui.button(f, on_click=lambda e, name=f: selected_label.set_text(f"Gewählt: {name}"))

    # Dropdown als Alternative
    select = ui.select(fixtures, value="Moving Head")
    select.on('change', lambda e: selected_label.set_text(f"Dropdown: {e.value}"))