from nicegui import ui
from gui.state import state
import serial.tools.list_ports

def create():
    # Helper: Ports finden
    def get_ports():
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports] if ports else ["Keine Ports"]

    ui.label('DMX HARDWARE').classes('text-h4 mb-4 text-white')

    with ui.card().classes('w-full bg-gray-900 border border-gray-700 p-6'):
        ui.label('Verbindung').classes('text-xl font-bold text-gray-300 mb-2')
        
        with ui.row().classes('items-center gap-4'):
            # Port Auswahl
            port_select = ui.select(get_ports(), label='COM Port', value=get_ports()[0]) \
                .props('dark standout color=cyan') \
                .classes('w-48')

            # Status Indikator
            status_led = ui.element('div').style('width: 20px; height: 20px; border-radius: 50%; background-color: #ff0000; transition: all 0.3s;')

            def handle_connect():
                # Wir rufen jetzt unseren neuen Manager auf!
                if state.dmx_interface.controller:
                    # Wenn schon verbunden -> Trennen
                    state.dmx_interface.disconnect()
                    ui.notify("Getrennt", color='warning')
                    status_led.style('background-color: #ff0000; box-shadow: none;')
                    connect_btn.text = "VERBINDEN"
                    connect_btn.props('color=green icon=link')
                else:
                    # Verbinden
                    success = state.dmx_interface.connect(port_select.value)
                    if success:
                        ui.notify(f"Verbunden mit {port_select.value}!", color='positive')
                        status_led.style('background-color: #00ff00; box-shadow: 0 0 15px #00ff00;')
                        connect_btn.text = "TRENNEN"
                        connect_btn.props('color=red icon=link_off')
                    else:
                        ui.notify("Fehler beim Verbinden!", color='negative')

            connect_btn = ui.button('VERBINDEN', on_click=handle_connect) \
                .props('push color=green icon=link')
            
            # Refresh Button
            ui.button(on_click=lambda: port_select.set_options(get_ports())).props('flat round icon=refresh color=grey')

    # MONITOR (Nur zur Anzeige)-->plotten die ersten 32 kanale als quadrate
    ui.label('Output Monitor').classes('text-lg font-bold mt-8 text-gray-400')
    
    # 16 Kanäle Anzeige
    monitor_labels = []
    with ui.grid(columns=16).classes('w-full gap-1'):
        for i in range(32): # Zeigen wir mal 32 an
            lbl = ui.label("0").classes("bg-gray-800 text-center text-xs text-white p-1 rounded font-mono")
            monitor_labels.append(lbl)

    def update_monitor():
        # Holt sich die Daten direkt aus der Engine zur Anzeige
        data = state.engine.render() 
        for i in range(32):
            if i < len(data):
                val = int(data[i])
                monitor_labels[i].text = str(val)
                # Färben wenn > 0
                bg = "#00aa00" if val > 0 else "#1f2937" # Grün oder Dunkelgrau
                monitor_labels[i].style(f'background-color: {bg}')

    ui.timer(0.2, update_monitor)