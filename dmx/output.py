import threading
import time
from DMXEnttecPro import Controller


class DMXOutput:

    def __init__(self, engine):
        self.engine=engine
        self.controller=None
        self.running=True
        self.thread=threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

        print("DMXOutput gestartet...")


    def connect(self, port):
        """Verbindet mit dem Interface"""
        try:
            if self.controller:
                self.controller.close() 
            
            self.controller=Controller(port)
            print(f"DMX-Interface an {port} verbunden.")
            return True
        
        except Exception as e:
            print(f"DMX Verbindungsfehler: {e}")
            self.controller=None
            return False
        
    def disconnect(self):
        """Trennt die Verbindung zum Interface"""
        if self.controller:
            self.controller.close()
            self.controller=None
            print("DMX-Interface getrennt.")


    def _loop(self):
        """Endlosschleife, die parallel zur UI läuft und DMX-Daten sendet"""
        while self.running:
            if self.controller:
                try:
                    #1. DMX-Daten aus der Engine rendern-->liefert die Liste mit 512 Werten

                    channels=self.engine.render()

                    #2. DMX-Daten an das Interface senden

                    #enttecpro dmx (kanal 1 bis n)
                    for i, val in enumerate(channels):
                        self.controller.set_channel(i+1, int(val))

                    #3. daten schicken
                    self.controller.submit()
                
                except Exception as e:
                    print(f"DMX Sende-Fehler: {e}")
                    self.controller=None #Verbindung trennen bei Fehler

            time.sleep(0.025) #40fps

            