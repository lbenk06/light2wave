import numpy as np
import librosa
import threading
import pygame

# pygame mixer initialisieren
pygame.mixer.init()

# globaler state für preanalyse file
audio_state = {
    "file_path": None,
    "beat_times": [],
    "frames_times": [],
    "structure": [],
    "bpm": 0,
    "is_playing": False,
    "current_beat_idx": 0,
    "current_frame_idx": 0,
    "last_state": None,
    "beat_offset": 0,
    "magic_mode": True
}

def analyze_audio_background(file_path, on_success, on_error):
    """Läuft im Hintergrund und ruft am Ende die Callbacks auf"""
    def task():
        try:
            y, sr = librosa.load(file_path)
            
            bpm, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            bpm_value = float(bpm[0]) if isinstance(bpm, np.ndarray) else float(bpm)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
            
            rms = librosa.feature.rms(y=y)[0]
            frames_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr).tolist()
            
            window_size = int(sr / 512 * 8) 
            rms_smoothed = np.convolve(rms, np.ones(window_size)/window_size, mode='same')
            mean_energy = np.mean(rms_smoothed)
            
            offset = int(sr / 512 * 4) 
            rms_trend = np.zeros_like(rms_smoothed)
            rms_trend[offset:] = rms_smoothed[offset:] - rms_smoothed[:-offset]
            
            structure = []
            for i in range(len(rms_smoothed)):
                if rms_smoothed[i] > mean_energy * 1.2: structure.append("DROP")
                elif rms_trend[i] > mean_energy * 0.1 and rms_smoothed[i] < mean_energy * 1.2: structure.append("BUILDUP")
                else: structure.append("BREAK")
                    
            cleaned_structure = []
            min_frames = int(sr / 512 * 1.5) 
            for i in range(len(structure)):
                if min_frames < i < len(structure) - min_frames:
                    umgebung = structure[i-10 : i+10]
                    cleaned_structure.append(max(set(umgebung), key=umgebung.count))
                else:
                    cleaned_structure.append(structure[i])
                    
            audio_state["beat_times"] = beat_times
            audio_state["frames_times"] = frames_times
            audio_state["structure"] = cleaned_structure
            audio_state["bpm"] = bpm_value
            audio_state["file_path"] = file_path
            
            pygame.mixer.music.load(file_path)
            on_success()
            
        except Exception as e:
            on_error(str(e))
            
    threading.Thread(target=task, daemon=True).start()

def toggle_playback():
    """Startet oder stoppt den Song"""
    if not audio_state["is_playing"]:
        audio_state["current_beat_idx"] = 0
        audio_state["current_frame_idx"] = 0
        audio_state["last_state"] = None
        pygame.mixer.music.play()
        audio_state["is_playing"] = True
    else:
        pygame.mixer.music.stop()
        audio_state["is_playing"] = False

def get_current_time():
    """Gibt die aktuelle Song Position in Sekunden zurück"""
    if not audio_state["is_playing"] or not pygame.mixer.music.get_busy():
        return 0.0
    return pygame.mixer.music.get_pos() / 1000.0