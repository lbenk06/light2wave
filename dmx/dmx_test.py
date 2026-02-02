#test skript für dmx enttec pro controller

from DMXEnttecPro import Controller
import tkinter as tk
import time
import threading
import random

#dmx setup
dmx = Controller("COM5")
START_CHANNEL = 1
STROBO = 0

FADE_SPEED = 0.04  

#farben zum testen
BASE_COLORS = [
    (0, 0, 0, 255),   
    (255, 0, 0, 200),
    (200, 0, 0, 255),
    (0, 255, 0, 255),   
    (0, 0, 255, 255),   
]

def set_fluter(r, g, b, w, dimmer):
    dmx.set_channel(START_CHANNEL + 0, r)
    dmx.set_channel(START_CHANNEL + 1, g)
    dmx.set_channel(START_CHANNEL + 2, b)
    dmx.set_channel(START_CHANNEL + 3, w)
    dmx.set_channel(START_CHANNEL + 5, STROBO)
    dmx.set_channel(START_CHANNEL + 7, dimmer)
    dmx.submit()

#Ui zur darstellung der lampenfarbe
root = tk.Tk()
root.title("LED Fluter Monitor")
root.geometry("200x200")

canvas = tk.Canvas(root, width=200, height=200)
canvas.pack()

circle = canvas.create_oval(50, 50, 150, 150, fill="#000000")

def rgb_to_hex(r, g, b, w=0):
    # Mische Weiß dazu für UI-Darstellung
    r = min(255, r + w)
    g = min(255, g + w)
    b = min(255, b + w)
    return f"#{r:02x}{g:02x}{b:02x}"

# --- DMX Thread ---
def dmx_loop():
    while True:
        # zufällige Farbe (überwiegend Rot + Weiß)
        color = random.choices(BASE_COLORS, weights=[40, 20, 20, 10, 10])[0]
        r, g, b, w = color

        # Aufblenden
        for d in range(0, 256, 5):
            set_fluter(r, g, b, w, d)
            hex_color = rgb_to_hex(r, g, b, w)
            canvas.itemconfig(circle, fill=hex_color)
            time.sleep(FADE_SPEED)

        # Abblenden
        for d in range(255, -1, -5):
            set_fluter(r, g, b, w, d)
            hex_color = rgb_to_hex(r, g, b, w)
            canvas.itemconfig(circle, fill=hex_color)
            time.sleep(FADE_SPEED)

# DMX Thread starten
threading.Thread(target=dmx_loop, daemon=True).start()

root.mainloop()
