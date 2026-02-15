"""
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
"""

from nicegui import ui
from gui.state import state
import math

def create():
    # Container für Referenzen (damit der Timer Zugriff auf die Elemente hat)
    refs = {
        "event_buttons": {},
        "fixture_elements": {} # Speichert: fixture_obj -> ui.element
    }

    #funktionen

    def handle_event_click(event):
        event.trigger(state.engine)
        update_button_styles()

    def update_button_styles():
        """Färbt aktive Event-Buttons"""
        for name, btn in refs["event_buttons"].items():
            event = next((e for e in state.events if e.name == name), None)
            if event:

                if "BLINDER" in name.upper() or "FLASH" in name.upper():
                    btn.props('color=white text-color=black push')
                    continue

                if event.active:
                    btn.props('color=red push')
                    btn.classes('shadow-lg shadow-red-500/50')
                else:
                    btn.props('color=grey-9 outline')
                    btn.classes('remove-shadow')

    def update_visuals():
        """Wird 10x pro Sekunde aufgerufen: Aktualisiert Lampenfarben"""
        for fix, el in refs["fixture_elements"].items():
            #Farbe aus der Engine holen (0-255)
            r, g, b = fix.get_color()
            
            #Helligkeit simulieren (Schatten leuchtet wenn an)
            box_shadow = f"0 0 {10 + (r+g+b)/10}px rgb({r},{g},{b})" if (r+g+b) > 0 else "none"
            
            el.style(f'background-color: rgb({r},{g},{b}); box-shadow: {box_shadow};')

    #ui layout

    with ui.column().classes('w-full h-full p-4 gap-4'):
        
        #OBERER BEREICH: HEADER & FLASH (blinder)
        with ui.row().classes('w-full justify-between items-center'):
            ui.label('LIVE DASHBOARD').classes('text-2xl font-bold tracking-wider text-gray-200')
            
            # Flash Button suchen
            blinder_event = next((e for e in state.events if "BLINDER" in e.name.upper() or "FLASH" in e.name.upper()), None)
            if blinder_event:
                btn = ui.button('BLINDER', on_click=lambda _, e=blinder_event: handle_event_click(e)) \
                    .classes('text-xl font-black w-48 h-12') \
                    .props('color=white text-color=black push')
                refs["event_buttons"][blinder_event.name] = btn

        ui.separator().classes('bg-gray-700')

        # HAUPTBEREICH: BÜHNE (Links) & EVENTS (Rechts)
        with ui.row().classes('w-full items-start gap-4'):

            #1. VISUALISIERUNG (BÜHNE)
            # Wir skalieren die Bühne etwas runter, damit sie gut reinpasst (scale-75 oder feste Größe)
            with ui.card().classes('w-2/3 bg-black border border-gray-800 relative overflow-hidden').style('height: 600px;'):
                
                #Container, der alles zentriert und skaliert
                #aktuell noch statisch, könnte aber später interaktiv werden (Zoom, Pan)
                with ui.element('div').style('position: relative; width: 1200px; height: 800px; transform: scale(0.7); transform-origin: top left;'):
                    
                    # A) TRAVERSEN ZEICHNEN (Statisch)
                    svg_content = ""
                    for t in state.engine.traverses:
                        # Einfache Linien für die Traversen
                        svg_content += f'<line x1="{t.x1}" y1="{t.y1}" x2="{t.x2}" y2="{t.y2}" stroke="#444" stroke-width="10" />'
                        # Endpunkte
                        svg_content += f'<circle cx="{t.x1}" cy="{t.y1}" r="6" fill="#666" />'
                        svg_content += f'<circle cx="{t.x2}" cy="{t.y2}" r="6" fill="#666" />'

                    ui.html(f'''
                        <svg width="100%" height="100%" style="position:absolute; top:0; left:0; pointer-events:none;">
                            {svg_content}
                        </svg>
                    ''',sanitize=False)

                    # B) LAMPEN ZEICHNEN (Einmalig erstellen)
                    for fixture in state.engine.fixtures:
                        # Wir erstellen einen DIV für jede Lampe
                        with ui.element('div').style(f'''
                            position: absolute;
                            left: {fixture.x}px;
                            top: {fixture.y}px;
                            width: 20px; height: 20px;
                            border-radius: 50%;
                            background-color: black;
                            border: 2px solid #333;
                            transform: translate(-50%, -50%);
                            transition: background-color 0.1s;
                        ''') as el:
                            ui.tooltip(f"{fixture.id} (Addr: {fixture.address})")
                        
                        # Referenz speichern für Updates
                        refs["fixture_elements"][fixture] = el


            # --- 2. EVENTS & SZENEN (Rechts) ---
            with ui.column().classes('w-1/3 gap-4'):
                
                # Szenen/Banken Auswahl
                with ui.card().classes('w-full bg-gray-900 border border-gray-700 p-2'):
                    ui.label("SZENEN-STEUERUNG").classes("text-xs font-bold text-gray-500 mb-2")
                    
                    #Bankenauswahl
                    if state.engine.banks:
                        bank_names = [bank["name"] for bank in state.engine.banks]

                        with ui.row().classes('w-full items-center mb-4'):
                            ui.label('Bank:').classes('text-gray-200 mr-2')
                            #dropdown zum bank wählen
                            bank_select=ui.select(bank_names, value=bank_names[0]).props('dark standout label-color=white color=white').classes('flex-grow')

                        #container für szenen
                        scene_container=ui.row().classes('gap-2 wrap w-full')

                        def refresh_scenes():
                            """zeigt szenen der aktuell gewählten bank"""
                            scene_container.clear()
                            selected_bank=next((b for b in state.engine.banks if b["name"] == bank_select.value), None)

                            if selected_bank:
                                with scene_container:
                                    for scene in selected_bank["scenes"]:
                                        def load_scene(s=scene):
                                            data=s.get("data", {})
                                            for f in state.engine.fixtures:
                                                if f.id in data:
                                                    for k, v in data[f.id].items():
                                                        f.set(k, v)
                                            ui.notify(f"Szene '{scene['name']}' geladen", color='cyan')
                                        
                                        ui.button(scene["name"], on_click=load_scene).props('outline color=cyan').classes('min-w-[80px]')

                        bank_select.on_value_change(refresh_scenes)


                        #initial einmal aufrufen
                        refresh_scenes()



                ui.label('EFFEKTE').classes('text-xl text-purple-400 font-bold mt-2')
                
                with ui.column().classes('w-full gap-2'):
                    for event in state.events:
                        if "BLINDER" in event.name.upper(): continue # Den haben wir schon oben

                        btn = ui.button(event.name, on_click=lambda _, e=event: handle_event_click(e)) \
                            .classes('w-full text-lg font-bold') \
                            .props('color=grey-9 outline')
                        
                        refs["event_buttons"][event.name] = btn

    # Initiale Styles setzen
    update_button_styles()


    #10fps
    ui.timer(0.1, update_visuals)