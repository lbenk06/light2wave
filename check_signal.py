"""Kurzer Signal-Check: misst 3 Sekunden Audio und zeigt Peak-Pegel."""
import sounddevice as sd
import numpy as np
import sys

def check(device_id, duration=3):
    dev = sd.query_devices(device_id)
    sr  = int(dev['default_samplerate'])
    ch  = min(2, dev['max_input_channels'])
    print(f"\nGeraet [{device_id}]: {dev['name']}")
    print(f"Rate: {sr} Hz | Kanaele: {ch}")
    print(f"Spiel jetzt {duration} Sekunden Musik ab ...\n")

    data = sd.rec(int(duration * sr), samplerate=sr, channels=ch,
                  device=device_id, dtype='float32')
    sd.wait()

    peak = float(np.max(np.abs(data)))
    rms  = float(np.sqrt(np.mean(data**2)))
    bar  = int(peak * 40)
    print(f"Peak:  {'█' * bar}{'░' * (40-bar)}  {peak:.4f}")
    print(f"RMS:   {rms:.4f}")

    if peak < 0.001:
        print("\n⚠  Kein Signal erkannt — moegliche Ursachen:")
        print("   1. Windows Eingangspegel auf 0 (Systemsteuerung > Sound > Aufnahme)")
        print("   2. Falscher USB-Kanal am Mischpult (USB Send nicht aktiviert)")
        print("   3. Treiber fehlt (ASIO/proprietaer)")
    elif peak < 0.01:
        print("\n⚠  Sehr leises Signal — Eingangspegel in Windows hochdrehen")
    else:
        print("\n✓  Signal vorhanden! App-Problem, kein Hardware-Problem.")

if __name__ == "__main__":
    device_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    check(device_id)
