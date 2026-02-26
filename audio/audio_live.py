import numpy as np
import sounddevice as sd
from scipy.signal import butter, lfilter
import time

# globaler state für das live modul
live_audio_state = {
    "is_listening": False,
    "beat_triggered": False,
    "beat_index": 0,
    "level": 0.0,
    "sensitivity": 3.5,
    "device_id": None,
    "phase": "WAITING", 
    "volume": 0.0
}

_stream = None
_kick_energy_history = np.zeros(20)
_last_kick_time = 0

# historien für die gesamtenergie-> um besser entscheiden zu können ob wirklich ein phasenwechsel vorliegt
_short_term_energy = np.zeros(10)  # ca. 0.5 sekunden
_long_term_energy = np.zeros(100)  # ca. 5 sekunden

def get_input_devices():
    devices = sd.query_devices()
    inputs = {}
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            inputs[i] = f"{i}: {d['name']}"
    return inputs

def bandpass(data, low=40, high=150, fs=48000):
    b, a = butter(4, [low / (fs / 2), high / (fs / 2)], btype='band')
    return lfilter(b, a, data)

def _audio_callback(indata, frames, time_info, status):
    global _kick_energy_history, _last_kick_time
    global _short_term_energy, _long_term_energy
    
    if not live_audio_state["is_listening"]:
        return

    # stereo in mono mischen
    mono = np.mean(indata, axis=1).astype(np.float32)

    # 1. echtzeit phasenerkennung
    # gesamt rms (lautstärke) berechnen
    overall_rms = np.sqrt(np.mean(mono**2))
    if np.isnan(overall_rms): overall_rms = 0.0
    
    _short_term_energy = np.roll(_short_term_energy, -1)
    _short_term_energy[-1] = overall_rms
    
    _long_term_energy = np.roll(_long_term_energy, -1)
    _long_term_energy[-1] = overall_rms
    
    short_avg = np.mean(_short_term_energy)
    long_avg = np.mean(_long_term_energy)
    
    # ratio muss einen wert haben
    ratio = 1.0 
    
    # regeln für die phase (buidlup, drop, break):
    if long_avg > 0:
        ratio = short_avg / long_avg
        
        # wenn die aktuelle lautstärke deutlich unter dem durchschnitt der letzten 5s liegt -> break
        if ratio < 0.8:
            live_audio_state["phase"] = "BREAK"
            
        # wenn die lautstärke über dem durchschnitt liegt und wir beats haben -> drop
        elif ratio > 1.2:
            live_audio_state["phase"] = "DROP"
            
        # wenn sie dazwischen liegt (oder leicht ansteigt) -> buildup
        else:
            # um ständiges flackern zu vermeiden sanftes wechseln
            if live_audio_state["phase"] == "BREAK":
                live_audio_state["phase"] = "BUILDUP"

    # 2. beat erkennung (kick drum)
    kick_band = bandpass(mono)
    energy = np.sum(kick_band ** 2)

    _kick_energy_history = np.roll(_kick_energy_history, -1)
    _kick_energy_history[-1] = energy

    threshold = np.mean(_kick_energy_history) * live_audio_state["sensitivity"]
    
    
    # 1. echten audio pegel senden
    live_audio_state["volume"] = min(overall_rms * 4.0, 1.0)
    # 2. beat wahrscheinlichkeit (reagiert auf den sensitivitätsslider)
    current_level = min(energy / (threshold if threshold > 0 else 1), 1.5) / 1.5
    live_audio_state["level"] = current_level
    
    now = time.time()  
    
    if energy > threshold and (now - _last_kick_time) > 0.25:
        _last_kick_time = now
        live_audio_state["beat_triggered"] = True
        live_audio_state["beat_index"] = (live_audio_state["beat_index"] + 1) % 4
        
        # wenn harter beat erkannt-> drop
        if ratio >= 0.9: 
            live_audio_state["phase"] = "DROP"

def start_listening(device_id):
    global _stream, _kick_energy_history, _short_term_energy, _long_term_energy
    if _stream is not None:
        stop_listening()
        
    try:
        dev_info = sd.query_devices(device_id)
        channels = min(2, dev_info['max_input_channels'])
        
        _kick_energy_history = np.zeros(20)
        _short_term_energy = np.zeros(10)
        _long_term_energy = np.zeros(100)
        
        live_audio_state["is_listening"] = True
        live_audio_state["device_id"] = device_id
        live_audio_state["phase"] = "WAITING"
        
        _stream = sd.InputStream(
            device=device_id,
            channels=channels,
            samplerate=48000,
            blocksize=2048,
            callback=_audio_callback
        )
        _stream.start()
        return True, "Gestartet"
    except Exception as e:
        live_audio_state["is_listening"] = False
        return False, str(e)

def stop_listening():
    global _stream
    live_audio_state["is_listening"] = False
    if _stream:
        _stream.stop()
        _stream.close()
        _stream = None