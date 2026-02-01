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

ALL_PROFILES={
    "led_par_6ch": LED_PAR_6CH,
    "led_fluter_8ch": LED_FLUTER_8CH,
    "moving_head_9ch": MOVING_HEAD_9CH,
}