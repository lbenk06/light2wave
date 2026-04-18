#grundprofile: ledpar mit 6 kanälen (stairville led flood panel), led_fluter (stairville hl230 rgbww), moving_head_wash:

LED_PAR_6CH={
    "profile_id":"led_par_6ch",
    "name":"LED PAR 6CH",
    "channels":[
        {"name":"Dimmer","role":"dimmer"},
        {"name":"Red","role":"red"},
        {"name":"Green","role":"green"},
        {"name":"Blue","role":"blue"},
        {"name":"Strobe","role":"strobe"},
        {"name":"Unused","role":"unused"},
    ]

}

LED_FLUTER_8CH={
    "profile_id":"led_fluter_8ch",
    "name":"LED Fluter 8CH",
    "channels":[
        {"name":"Red","role":"red"},
        {"name":"Green","role":"green"},
        {"name":"Blue","role":"blue"},
        {"name":"White","role":"white"},
        {"name":"Unused","role":"unused"},
        {"name":"Strobe","role":"strobe"},
        {"name":"Unused","role":"unused"},
        {"name":"Dimmer","role":"dimmer"},
        
    ]
}

MOVING_HEAD_9CH = {
    "profile_id": "moving_head_9ch",
    "name": "Moving Head 9CH",
    "channels": [
        {"name": "Dimmer", "role": "dimmer"},
        {"name": "Red", "role": "red"},
        {"name": "Green", "role": "green"},
        {"name": "Blue", "role": "blue"},
        {"name": "White", "role": "white"},
        {"name": "Pan", "role": "pan"},
        {"name": "Tilt", "role": "tilt"},
        {"name": "Strobe", "role": "strobe"},
        {"name": "Speed", "role": "speed"},
    ]
}


# Laserworld EL-230RGB MK2 — 9-Kanal DMX
# CH1: 0-49=Aus, 50-99=Sound, 100-149=Auto, 150-199=Statisch-DMX, 200-255=Dynamisch-DMX
# CH2: Musterauswahl (0-255)
# CH3: X-Position (1-10=Mitte, 11-255=Position)
# CH4: Y-Position (1-10=Mitte, 11-255=Position)
# CH5: Scan-Geschwindigkeit (0-255)
# CH6: Dynamik-Geschwindigkeit (0-255)
# CH7: Zoom / Größe (0-255)
# CH8: Farbe (0-255)
# CH9: Farb-Segment (0-255)
LASERWORLD_EL230_9CH = {
    "profile_id": "laserworld_el230_9ch",
    "name": "Laserworld EL-230RGB MK2 9CH",
    "channels": [
        {"name": "Modus",           "role": "laser_mode"},
        {"name": "Muster",          "role": "pattern"},
        {"name": "X-Position",      "role": "x_pos"},
        {"name": "Y-Position",      "role": "y_pos"},
        {"name": "Scan-Speed",      "role": "speed"},
        {"name": "Dynamik-Speed",   "role": "laser_speed"},
        {"name": "Zoom",            "role": "zoom"},
        {"name": "Farbe",           "role": "laser_color"},
        {"name": "Farb-Segment",    "role": "color_segment"},
    ],
    # DMX-Wertebereiche mit Beschreibung — (dmx_min, dmx_max, label)
    "hints": {
        "laser_mode": [
            (0,   49,  "LASER AUS"),
            (50,  99,  "Sound-Modus"),
            (100, 149, "Auto-Modus"),
            (150, 199, "Statisch DMX [aktiv]"),
            (200, 255, "Dynamisch DMX [aktiv]"),
        ],
        "x_pos": [
            (0,  10,  "Mitte (Zentrum)"),
            (11, 255, "X-Positionierung"),
        ],
        "y_pos": [
            (0,  10,  "Mitte (Zentrum)"),
            (11, 255, "Y-Positionierung"),
        ],
        "pattern":       [(0, 255, "Muster 0–255 → verschiedene Laser-Muster")],
        "speed":         [(0, 255, "Scan-Geschwindigkeit (0=langsam, 255=schnell)")],
        "laser_speed":   [(0, 255, "Dynamik-Speed (nur bei Dynamisch DMX aktiv)")],
        "zoom":          [(0, 255, "Zoom / Mustergröße (0=klein, 255=groß)")],
        "laser_color":   [(0, 255, "Farbe (0=Rot, ~85=Grün, ~170=Blau, 255=Weiß/Mix)")],
        "color_segment": [(0, 255, "Farb-Segment / Farbbereich-Aufteilung")],
    }
}

ALL_PROFILES = {
    "led_par_6ch":          LED_PAR_6CH,
    "led_fluter_8ch":       LED_FLUTER_8CH,
    "moving_head_9ch":      MOVING_HEAD_9CH,
    "laserworld_el230_9ch": LASERWORLD_EL230_9CH,
}