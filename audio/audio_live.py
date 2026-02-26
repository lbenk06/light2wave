import numpy as np

# Hier kommt später die Live-Mikrofon/Desktop-Audio Analyse rein.
# Wir werden hier pyaudio nutzen, um in Echtzeit auf Transienten (Kick-Drums) zu lauschen.

live_audio_state = {
    "is_listening": False,
    "current_level": 0.0,
    "threshold": 50.0
}

def start_listening():
    pass

def stop_listening():
    pass