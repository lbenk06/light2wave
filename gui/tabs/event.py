from nicegui import ui
from gui.state import state
import json
import time
from pathlib import Path
from engine.generators import GENERATOR_MAP
from engine.events import Event

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
EVENTS_FILE = DATA_DIR / "events_default.json"

_TARGET_ROLES = ["dimmer", "red", "green", "blue", "white"]

_TYPE_LABELS = {
    "dynamic":  "Dynamisch (Welle / Chase)",
    "flash":    "Flash (Blinder-Hit)",
    "static":   "Statisch (feste Farbe)",
    "stop_all": "Stop All (Blackout)",
}

# Per-Generator Metadaten: Labels, Hints, Slider-Maxima
_GEN_META: dict[str, dict] = {
    "linear_wave":   {"name": "Welle Links → Rechts",
                      "speed_lbl": "Tempo",          "speed_hint": "Wie schnell die Welle von links nach rechts läuft",
                      "width_lbl": "Wellendichte",   "width_hint": "Höher = engere, schneller wechselnde Wellen"},
    "center_sym":    {"name": "Symmetrisch (Mitte → Außen)",
                      "speed_lbl": "Tempo",          "speed_hint": "Ausbreitungsgeschwindigkeit von der Bühnenmitte",
                      "width_lbl": "Wellendichte",   "width_hint": "Höher = mehr Wellen gleichzeitig sichtbar"},
    "gate_pulse":    {"name": "Explosion (Traverse-Mitte)",
                      "speed_lbl": "Ausbreitungs-Tempo", "speed_hint": "Wie schnell der Impuls von der Mitte nach außen läuft",
                      "width_lbl": "Wellenbreite",   "width_hint": "Breite des leuchtenden Pulses"},
    "vertical_wave": {"name": "Welle Oben → Unten",
                      "speed_lbl": "Tempo",          "speed_hint": "Wie schnell die Welle die Säulen herunterläuft",
                      "width_lbl": "Wellendichte",   "width_hint": "Höher = mehr Wellen auf den Säulen"},
    "radar":         {"name": "Radar / Rotationsstrahl",
                      "speed_lbl": "Rotationstempo", "speed_hint": "Wie schnell sich der Strahl dreht (Runden/Sekunde)",
                      "width_lbl": "Strahlschärfe",  "width_hint": "Höher = schmälerer, schärferer Lichtstrahl"},
    "scanner":       {"name": "Scanner (Knight Rider)",
                      "speed_lbl": "Pendelgeschwindigkeit", "speed_hint": "Wie schnell der Balken von links nach rechts pendelt",
                      "width_lbl": "Strahlbreite",   "width_hint": "Niedriger = breiterer Schein, höher = schmaler Spot"},
    "hard_chase":    {"name": "Harter Chase (kein Fade)",
                      "speed_lbl": "Tempo",          "speed_hint": "Geschwindigkeit des Chasers",
                      "width_lbl": "Wellendichte",   "width_hint": "Wie viele Lampen gleichzeitig leuchten"},
    "plasma":        {"name": "Plasma / Lavalampe",
                      "speed_lbl": "Fließtempo",     "speed_hint": "Wie schnell die organischen Formen fließen",
                      "width_lbl": "Komplexität",    "width_hint": "Höher = chaotischere, kleinteiligere Muster"},
    "breathing":     {"name": "Breathing (alle synchron)",
                      "speed_lbl": "Atemtempo",      "speed_hint": "Wie schnell alle Lampen gemeinsam ein- und ausblenden",
                      "width_lbl": "—",              "width_hint": "Nicht verwendet"},
    "heartbeat":     {"name": "Herzschlag (Doppelpuls)",
                      "speed_lbl": "BPM / Tempo",   "speed_hint": "Wie schnell der Doppelschlag pulsiert",
                      "width_lbl": "—",              "width_hint": "Nicht verwendet"},
    "sparkle":       {"name": "Funkeln / Glitzer",
                      "speed_lbl": "Funkelrate",     "speed_hint": "Wie schnell und häufig einzelne Lampen aufblitzen",
                      "width_lbl": "—",              "width_hint": "Nicht verwendet"},
    "flicker":       {"name": "Flackern / Feuer",
                      "speed_lbl": "Flackerrate",    "speed_hint": "Intensität und Geschwindigkeit des Flackerns",
                      "width_lbl": "—",              "width_hint": "Nicht verwendet"},
    "strobe":        {"name": "Strobo (synchron)",
                      "speed_lbl": "Blitze / Sekunde", "speed_hint": "Stroboskop-Frequenz (z.B. 10 = 10 Blitze/s, 1–30 sinnvoll)",
                      "width_lbl": "Einschaltzeit (Duty Cycle)", "width_hint": "0.1 = kurzer Blitz · 0.5 = 50% an · max 1.0",
                      "width_max": 1.0},
    "flash_decay":   {"name": "Flash Envelope",
                      "speed_lbl": "Aufglühzeit",    "speed_hint": "intern",
                      "width_lbl": "Abglühzeit",     "width_hint": "intern"},
}

# ── Preview-Fixtures (simulierte Traverse-Positionen auf Bühnenkoordinaten) ──
class _MockFixture:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
    def has(self, _): return True
    def set(self, *_): pass

_PREV_FIXTURES = [
    # Obere Traverse-Bar (8 Fixtures, x 100–1100, y 200)
    _MockFixture(100, 200), _MockFixture(243, 200), _MockFixture(386, 200),
    _MockFixture(529, 200), _MockFixture(671, 200), _MockFixture(814, 200),
    _MockFixture(957, 200), _MockFixture(1100, 200),
    # Linke Säule (x=100, y 350/550/750)
    _MockFixture(100, 350), _MockFixture(100, 550), _MockFixture(100, 750),
    # Rechte Säule (x=1100, y 350/550/750)
    _MockFixture(1100, 350), _MockFixture(1100, 550), _MockFixture(1100, 750),
]

# Canvas-Positionen für die Zeichnung (400×180 px)
_PREV_POS = json.dumps([
    [38,28],[90,28],[140,28],[190,28],[240,28],[292,28],[342,28],[378,28],
    [22,72],[22,118],[22,162],
    [378,72],[378,118],[378,162],
])

# Statisches JS-Snippet für die Traverse-Zeichenfunktion (einmal definiert)
_CANVAS_JS = r"""
window._evDraw = function(vals, r, g, b) {
    var c = document.getElementById('ev-prev-canvas');
    if (!c) return;
    var ctx = c.getContext('2d');
    ctx.fillStyle = '#07070f';
    ctx.fillRect(0, 0, c.width, c.height);

    // Traverse-Struktur
    ctx.strokeStyle = '#1c1c2e';
    ctx.lineWidth = 5;
    ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(22,28); ctx.lineTo(378,28); ctx.stroke();
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(22,28); ctx.lineTo(22,168); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(378,28); ctx.lineTo(378,168); ctx.stroke();

    var POS = """ + _PREV_POS + r""";
    for (var i = 0; i < vals.length && i < POS.length; i++) {
        var v = vals[i];
        var px = POS[i][0], py = POS[i][1];
        var rv = Math.round(r * v), gv = Math.round(g * v), bv = Math.round(b * v);

        // Glow-Halo
        if (v > 0.02) {
            var grad = ctx.createRadialGradient(px, py, 0, px, py, 22);
            grad.addColorStop(0, 'rgba(' + rv + ',' + gv + ',' + bv + ',' + (v * 0.9) + ')');
            grad.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = grad;
            ctx.beginPath(); ctx.arc(px, py, 22, 0, Math.PI * 2); ctx.fill();
        }

        // Kern-Punkt
        ctx.fillStyle = 'rgb(' + rv + ',' + gv + ',' + bv + ')';
        ctx.beginPath(); ctx.arc(px, py, 5, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = v > 0.08 ? '#777' : '#252535';
        ctx.lineWidth = 1;
        ctx.stroke();
    }
};
"""


def create():
    ui.label('EVENT EDITOR').classes('console-label mb-4')

    form = {
        "name":        "",
        "type":        "dynamic",
        "generator":   "linear_wave",
        "target_role": "dimmer",
        "speed":       2.0,
        "width":       5.0,
        "attack":      8.0,
        "decay":       5.0,
        "roles": {"red": 1.0, "green": 0.0, "blue": 0.0, "white": 0.0},
    }

    # ── Vorschau-Dialog ────────────────────────────────────────────────
    def open_preview():
        if form["type"] == "flash":
            gen_name, speed, width, loop = "flash_decay", form["attack"], form["decay"], 3.0
        else:
            gen_name, speed, width, loop = form["generator"], form["speed"], form["width"], None

        gen_func = GENERATOR_MAP.get(gen_name)
        if not gen_func:
            ui.notify("Kein Generator gewählt", color="red")
            return

        r = int(form["roles"].get("red", 0.0) * 255)
        g = int(form["roles"].get("green", 0.0) * 255)
        b = int(form["roles"].get("blue", 0.0) * 255)
        if r == 0 and g == 0 and b == 0:
            r = g = b = 220

        start_t = [time.time()]
        active = [True]
        meta = _GEN_META.get(gen_name, {})

        with ui.dialog().props('persistent') as dlg, \
                ui.card().classes('bg-[#07070f] border border-gray-700 p-4 gap-2 min-w-[440px]'):

            with ui.row().classes('w-full items-center justify-between mb-1'):
                ui.label(f'TRAVERSE VORSCHAU').classes('text-xs text-gray-400 font-bold tracking-widest')
                ui.label(meta.get("name", gen_name)).classes('text-purple-300 text-xs font-mono')

            ui.html(
                '<canvas id="ev-prev-canvas" width="400" height="180" '
                'style="background:#07070f;border:1px solid #1a1a2e;border-radius:4px;display:block;">'
                '</canvas>'
            )

            with ui.row().classes('w-full justify-center gap-6 mt-1'):
                slbl = meta.get("speed_lbl", "Speed")
                wlbl = meta.get("width_lbl", "Width")
                ui.label(f'{slbl}: {speed}').classes('text-[11px] text-gray-500 font-mono')
                if wlbl != "—":
                    ui.label(f'{wlbl}: {width}').classes('text-[11px] text-gray-500 font-mono')
                if loop:
                    ui.label('(Flash — wiederholt alle 3s)').classes('text-[11px] text-yellow-700 italic')

            def _close():
                active[0] = False
                prev_timer.cancel()
                dlg.close()

            ui.button('SCHLIESSEN', on_click=_close, icon='close') \
                .props('outline color=grey dense').classes('w-full mt-2 text-xs')

            # JS-Zeichenfunktion definieren
            ui.run_javascript(_CANVAS_JS)

            def _update():
                if not active[0]:
                    return
                t = time.time() - start_t[0]
                if loop:
                    t = t % loop

                vals = []
                for fx in _PREV_FIXTURES:
                    try:
                        v = float(gen_func(fx, t, speed=speed, width=width))
                        vals.append(round(min(1.0, max(0.0, v)), 3))
                    except Exception:
                        vals.append(0.0)

                ui.run_javascript(
                    f'window._evDraw && window._evDraw({json.dumps(vals)},{r},{g},{b})'
                )

            prev_timer = ui.timer(1 / 30, _update)

        dlg.open()

    # ── Formular-Karte ─────────────────────────────────────────────────
    with ui.card().classes('w-full bg-gray-900 border border-gray-700 p-5 mb-6'):
        ui.label('NEUES EVENT').classes('text-xs text-gray-400 font-bold tracking-widest mb-3')

        with ui.row().classes('w-full gap-6 items-start'):

            # Linke Spalte: Name, Typ, Farbe
            with ui.column().classes('flex-1 gap-3 min-w-[210px]'):
                ui.input(label='Name').bind_value(form, 'name') \
                    .props('dark color=cyan dense').classes('w-full')

                ui.select(options=_TYPE_LABELS, value='dynamic', label='Typ') \
                    .bind_value(form, 'type') \
                    .props('dark color=cyan standout dense').classes('w-full')

                ui.separator().classes('bg-gray-700 my-1')
                ui.label('FARBE').classes('text-[10px] text-gray-500 font-bold')
                with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-1'):
                    for _ch, _col in [('red','red'),('green','green'),('blue','blue'),('white','grey')]:
                        ui.label(_ch.capitalize()).classes(f'text-{_col}-400 text-xs self-center')
                        ui.slider(min=0, max=1, step=0.01) \
                            .bind_value(form['roles'], _ch) \
                            .props(f'dark color={_col} label-always dense')
                ui.label('Leer = Geräte-Farbe bleibt erhalten') \
                    .classes('text-[10px] text-gray-600 italic mt-1')

            # Rechte Spalte: Typ-spezifisch
            with ui.column().classes('flex-1 gap-2 min-w-[210px]'):

                # ── DYNAMISCH ─────────────────────────────────────────
                with ui.column().classes('w-full gap-2') \
                        .bind_visibility_from(form, 'type', lambda t: t == 'dynamic'):
                    ui.label('DYNAMISCHER EFFEKT').classes('text-[10px] text-purple-400 font-bold')

                    gen_sel = ui.select(options=list(GENERATOR_MAP.keys()), label='Muster') \
                        .bind_value(form, 'generator') \
                        .props('dark color=purple standout dense').classes('w-full')

                    ui.select(options=_TARGET_ROLES, label='Ziel-Kanal') \
                        .bind_value(form, 'target_role') \
                        .props('dark color=teal standout dense').classes('w-full') \
                        .tooltip('Welcher DMX-Kanal wird vom Generator gesteuert?')

                    lbl_speed = ui.label('Tempo').classes('text-gray-300 text-xs mt-1')
                    hint_speed = ui.label('').classes('text-[10px] text-gray-600 italic -mt-1')
                    ui.slider(min=0.1, max=15.0, step=0.1) \
                        .bind_value(form, 'speed') \
                        .props('dark color=purple label-always')

                    lbl_width = ui.label('Breite / Phase').classes('text-gray-300 text-xs mt-1')
                    hint_width = ui.label('').classes('text-[10px] text-gray-600 italic -mt-1')
                    width_sl = ui.slider(min=0.1, max=15.0, step=0.1) \
                        .bind_value(form, 'width') \
                        .props('dark color=purple label-always')

                    def _update_gen_labels(e=None):
                        m = _GEN_META.get(form["generator"], {})
                        lbl_speed.set_text(m.get("speed_lbl", "Geschwindigkeit"))
                        hint_speed.set_text(m.get("speed_hint", ""))
                        wlbl = m.get("width_lbl", "Breite / Phase")
                        lbl_width.set_text(wlbl)
                        hint_width.set_text(m.get("width_hint", ""))
                        wmax = m.get("width_max", 15.0)
                        width_sl.max = wmax
                        if form["width"] > wmax:
                            form["width"] = round(wmax * 0.5, 2)

                    gen_sel.on_value_change(_update_gen_labels)
                    _update_gen_labels()

                # ── FLASH ─────────────────────────────────────────────
                with ui.column().classes('w-full gap-2') \
                        .bind_visibility_from(form, 'type', lambda t: t == 'flash'):
                    ui.label('FLASH / BLINDER HIT').classes('text-[10px] text-yellow-400 font-bold')

                    with ui.column().classes('w-full gap-0'):
                        with ui.row().classes('w-full items-center justify-between'):
                            ui.label('Aufglühzeit').classes('text-yellow-300 text-xs font-bold')
                            ui.label('Langsam ← · → Sofort').classes('text-[10px] text-gray-500 italic')
                        ui.slider(min=0.5, max=15.0, step=0.5) \
                            .bind_value(form, 'attack') \
                            .props('dark color=yellow label-always').classes('w-full')
                        ui.label('Niedrig = weiches Aufblenden  ·  Hoch = sofortiger Blitz') \
                            .classes('text-[10px] text-gray-600 italic mb-2')

                    with ui.column().classes('w-full gap-0'):
                        with ui.row().classes('w-full items-center justify-between'):
                            ui.label('Abglühzeit').classes('text-orange-300 text-xs font-bold')
                            ui.label('Langer Schweif ← · → Kurzer Knall').classes('text-[10px] text-gray-500 italic')
                        ui.slider(min=0.5, max=20.0, step=0.5) \
                            .bind_value(form, 'decay') \
                            .props('dark color=orange label-always').classes('w-full')
                        ui.label('Niedrig = langer Nachschein  ·  Hoch = harter, kurzer Hit') \
                            .classes('text-[10px] text-gray-600 italic mb-2')

                    ui.select(options=_TARGET_ROLES, label='Ziel-Kanal') \
                        .bind_value(form, 'target_role') \
                        .props('dark color=teal standout dense').classes('w-full') \
                        .tooltip('Welcher DMX-Kanal wird geflasht?')

                # ── STATISCH ──────────────────────────────────────────
                with ui.column().classes('w-full gap-2') \
                        .bind_visibility_from(form, 'type', lambda t: t == 'static'):
                    ui.label('STATISCHES LICHT').classes('text-[10px] text-blue-400 font-bold')
                    ui.label(
                        'Farbe links einstellen.\n'
                        'Das Event hält diese Farbe bis es manuell gestoppt wird.'
                    ).classes('text-xs text-gray-500 whitespace-pre-line')

                # ── STOP ALL ──────────────────────────────────────────
                with ui.column().classes('w-full gap-2') \
                        .bind_visibility_from(form, 'type', lambda t: t == 'stop_all'):
                    ui.label('STOP ALL').classes('text-[10px] text-red-400 font-bold')
                    ui.label(
                        'Stoppt sofort alle laufenden Effekte\n'
                        'und setzt alle Lampen auf Schwarz.'
                    ).classes('text-xs text-gray-500 whitespace-pre-line')

        # Buttons
        ui.separator().classes('bg-gray-700 my-3')
        with ui.row().classes('w-full gap-3'):

            def _save_event():
                name = form["name"].strip()
                if not name:
                    ui.notify('Bitte einen Namen eingeben!', color='red')
                    return

                ev_type = form["type"]
                roles = {k: v for k, v in form["roles"].items() if v > 0}
                new_data: dict = {"name": name, "type": ev_type, "roles": roles}

                if ev_type == "dynamic":
                    new_data["params"] = {
                        "generator":   form["generator"],
                        "target_role": form["target_role"],
                        "speed":       float(form["speed"]),
                        "width":       float(form["width"]),
                    }
                elif ev_type == "flash":
                    new_data["params"] = {
                        "generator":   "flash_decay",
                        "target_role": form["target_role"],
                        "speed":       float(form["attack"]),
                        "width":       float(form["decay"]),
                    }

                try:
                    all_ev = []
                    if EVENTS_FILE.exists():
                        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                            all_ev = json.load(f)
                    idx = next((i for i, e in enumerate(all_ev) if e["name"] == name), None)
                    if idx is not None:
                        all_ev[idx] = new_data
                    else:
                        all_ev.append(new_data)
                    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
                        json.dump(all_ev, f, indent=4, ensure_ascii=False)
                except Exception as e:
                    ui.notify(f'Speicherfehler: {e}', color='red')
                    return

                new_ev = Event(name, new_data)
                sidx = next((i for i, e in enumerate(state.events) if e.name == name), None)
                if sidx is not None:
                    if state.events[sidx].active:
                        state.events[sidx].stop(state.engine)
                    state.events[sidx] = new_ev
                else:
                    state.events.append(new_ev)

                ui.notify(f'"{name}" gespeichert!', color='green')
                form["name"] = ""
                render_events()

            ui.button('VORSCHAU', on_click=open_preview, icon='visibility') \
                .props('outline color=purple') \
                .bind_visibility_from(form, 'type', lambda t: t in ('dynamic', 'flash'))

            ui.button('SPEICHERN', on_click=_save_event, icon='save') \
                .props('push color=green').classes('font-bold')

    # ── Event-Liste ───────────────────────────────────────────────────
    ui.label('GESPEICHERTE EVENTS').classes('console-label mb-3')
    events_container = ui.element('div').classes('w-full flex flex-wrap gap-3')

    def _delete_event(name):
        ev = next((e for e in state.events if e.name == name), None)
        if ev and ev.active:
            ev.stop(state.engine)
        state.events = [e for e in state.events if e.name != name]
        if EVENTS_FILE.exists():
            with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with open(EVENTS_FILE, "w", encoding="utf-8") as f:
                json.dump([e for e in data if e.get("name") != name], f, indent=4, ensure_ascii=False)
        ui.notify(f'"{name}" gelöscht', color='orange')
        render_events()

    def _edit_event(ev_obj: Event):
        form["name"] = ev_obj.name
        form["type"] = ev_obj.type
        for c in ["red", "green", "blue", "white"]:
            form["roles"][c] = ev_obj.data.get("roles", {}).get(c, 0.0)
        params = ev_obj.data.get("params", {})
        if params:
            form["generator"]   = params.get("generator", "linear_wave")
            form["target_role"] = params.get("target_role", "dimmer")
            form["speed"]       = params.get("speed", 2.0)
            form["width"]       = params.get("width", 5.0)
            form["attack"]      = params.get("speed", 8.0)
            form["decay"]       = params.get("width", 5.0)
        ui.notify(f'"{ev_obj.name}" in den Editor geladen', color='info')
        ui.run_javascript('window.scrollTo(0, 0)')

    def render_events():
        events_container.clear()
        with events_container:
            if not state.events:
                ui.label('Noch keine Events erstellt.').classes('text-gray-600 text-sm italic')
                return
            for ev in state.events:
                _make_event_card(ev)

    def _make_event_card(ev: Event):
        border = 'border-green-500' if ev.active else 'border-gray-700'
        with ui.card().classes(f'w-52 bg-gray-800 border {border} p-3 gap-1'):

            # Kopfzeile
            with ui.row().classes('w-full justify-between items-center'):
                with ui.row().classes('items-center gap-1 min-w-0'):
                    if ev.active:
                        ui.element('div').style(
                            'width:8px;height:8px;border-radius:50%;'
                            'background:#22c55e;box-shadow:0 0 6px #22c55e;flex-shrink:0;'
                        )
                    ui.label(ev.name).classes('font-bold text-gray-200 text-sm truncate').tooltip(ev.name)
                with ui.row().classes('gap-0 flex-shrink-0'):
                    ui.button(icon='edit', on_click=lambda ev=ev: _edit_event(ev)) \
                        .props('flat round dense color=info').tooltip('Bearbeiten')
                    async def _confirm_del(n=ev.name):
                        with ui.dialog() as dlg, ui.card():
                            ui.label(f'"{n}" wirklich löschen?').classes('font-bold')
                            with ui.row().classes('mt-2 gap-2'):
                                ui.button('Löschen', on_click=lambda: (_delete_event(n), dlg.close())) \
                                    .props('color=red push')
                                ui.button('Abbrechen', on_click=dlg.close).props('outline')
                        dlg.open()
                    ui.button(icon='delete', on_click=_confirm_del) \
                        .props('flat round dense color=red').tooltip('Löschen')

            # Typ-Badge
            _badge_col = {'dynamic': 'purple', 'flash': 'orange', 'static': 'blue', 'stop_all': 'red'}
            ui.badge(ev.type, color=_badge_col.get(ev.type, 'grey'))

            # Parameter
            if ev.type in ('dynamic', 'flash'):
                params = ev.data.get("params", {})
                gen  = params.get("generator", "-")
                tgt  = params.get("target_role", "dimmer")
                spd  = params.get("speed", "-")
                wid  = params.get("width", "-")
                meta = _GEN_META.get(gen, {})
                if ev.type == 'flash':
                    ui.label(f'Attack: {spd}').classes('text-xs text-yellow-400 font-mono')
                    ui.label(f'Decay:  {wid}').classes('text-xs text-orange-400 font-mono')
                    ui.label(f'Kanal: {tgt}').classes('text-xs text-gray-500 font-mono')
                else:
                    ui.label(meta.get("name", gen)).classes('text-xs text-purple-300 font-mono truncate').tooltip(gen)
                    ui.label(f'{meta.get("speed_lbl","Speed")}: {spd}').classes('text-xs text-gray-400 font-mono')
                    if meta.get("width_lbl") != "—":
                        ui.label(f'{meta.get("width_lbl","Width")}: {wid}').classes('text-xs text-gray-500 font-mono')
                    ui.label(f'Kanal: {tgt}').classes('text-xs text-gray-500 font-mono')
            elif ev.type == 'static':
                roles = ev.data.get("roles", {})
                if roles:
                    clr = '  '.join(f'{k[0].upper()}:{v:.1f}' for k, v in roles.items())
                    ui.label(clr).classes('text-xs text-blue-300 font-mono')

            # Test-Button (feuert das Event auf echter Hardware)
            def _fire(e=ev):
                e.trigger(state.engine)
                render_events()

            ui.button('FEUER', on_click=_fire, icon='bolt') \
                .props('push dense color=cyan').classes('w-full mt-1 text-xs font-black tracking-widest')

    render_events()
