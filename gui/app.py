from nicegui import ui
from gui.state import state
from gui.tabs import live, audio, fixtures, traverse, scenes, dmx, event
import base64
from pathlib import Path

def _logo_base64():
    path = Path(__file__).parent / "static" / "logolbveranstaltungstechnik.png"
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

_LOGO_B64 = _logo_base64()


def create_app():
    # --- Globales Theme ---
    ui.dark_mode().enable()
    ui.colors(
        primary='#06b6d4',    # Cyan
        secondary='#8b5cf6',  # Violet
        positive='#10b981',
        negative='#ef4444',
        warning='#f59e0b',
        info='#38bdf8',
    )
    ui.add_head_html("""
    <style>
        /* ============================================
           LIGHT2WAVE — CONSOLE THEME
           ============================================ */

        /* Base */
        body, .q-page { background-color: #0d0d0f !important; }
        .nicegui-content { background-color: #0d0d0f !important; padding: 0 !important; }

        /* Monospace system stack */
        .font-mono, code, .value-display {
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
        }

        /* Scrollbar */
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: #0d0d0f; }
        ::-webkit-scrollbar-thumb { background: #2a2a35; border-radius: 2px; }
        ::-webkit-scrollbar-thumb:hover { background: #3a3a48; }

        /* ---- BUTTONS ---- */
        .q-btn { border-radius: 2px !important; font-weight: 700 !important; letter-spacing: 0.07em !important; }
        .q-btn--push {
            box-shadow: 0 2px 0 rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.06) !important;
        }
        .q-btn--push:active {
            box-shadow: 0 0 0 rgba(0,0,0,0.7), inset 0 2px 4px rgba(0,0,0,0.5) !important;
            transform: translateY(1px) !important;
        }

        /* ---- SLIDERS — FADER STYLE ---- */
        .q-slider__track-container--h { height: 3px !important; border-radius: 1px !important; }
        .q-slider__track { border-radius: 1px !important; }
        .q-slider__thumb {
            width: 10px !important;
            border-radius: 1px !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            box-shadow: 0 1px 5px rgba(0,0,0,0.6) !important;
        }
        /* Vertical master fader */
        .q-slider--v .q-slider__track-container--v { width: 4px !important; }
        .q-slider--v .q-slider__thumb {
            width: 30px !important; height: 8px !important; border-radius: 1px !important;
        }

        /* ---- CARDS ---- */
        .q-card { border-radius: 3px !important; box-shadow: none !important; }

        /* ---- TABS ---- */
        .q-tab { border-radius: 0 !important; min-height: 40px !important; padding: 0 14px !important; font-size: 11px !important; letter-spacing: 0.1em !important; }
        .q-tab--active .q-tab__label { color: #06b6d4 !important; font-weight: 800 !important; letter-spacing: 0.1em !important; }
        .q-tab--active .q-icon       { color: #06b6d4 !important; }
        .q-tab__indicator            { background: #06b6d4 !important; height: 2px !important; }
        .q-tab:hover .q-tab__label   { color: #a5f3fc; }
        .q-tab:hover .q-icon         { color: #a5f3fc; }
        .q-tab-panels { background: transparent !important; }
        .q-tab-panel  { padding: 14px !important; }

        /* ---- INPUTS ---- */
        .q-field__control { border-radius: 2px !important; }

        /* ---- SEPARATORS ---- */
        .q-separator--horizontal { background: #1a1a22 !important; }

        /* ---- TOOLTIPS ---- */
        .q-tooltip {
            background: #1c1c24 !important; border: 1px solid #2a2a38 !important;
            font-size: 10px !important; letter-spacing: 0.05em !important; color: #99aabc !important;
            border-radius: 2px !important;
        }

        /* ---- DIALOGS ---- */
        .q-dialog__backdrop { background: rgba(0,0,0,0.88) !important; }
        .q-card.q-dialog-plugin { background: #141418 !important; border: 1px solid #252535 !important; }

        /* ---- NOTIFICATIONS ---- */
        .q-notification { border-radius: 2px !important; font-size: 11px !important; font-weight: 700 !important; letter-spacing: 0.05em !important; }

        /* ============================================
           CUSTOM CONSOLE CLASSES
           ============================================ */

        /* Section label — like GrandMA category headers */
        .console-label {
            font-size: 9px !important;
            font-weight: 900 !important;
            letter-spacing: 0.25em !important;
            text-transform: uppercase !important;
            color: #38404f !important;
            padding-bottom: 5px !important;
            border-bottom: 1px solid #1a1a24 !important;
            display: block !important;
        }

        /* LCD-style value display */
        .lcd-display {
            font-family: 'Consolas', 'Monaco', monospace !important;
            background: #050710 !important;
            border: 1px solid #16162a !important;
            color: #00d4ff !important;
            padding: 3px 10px !important;
            border-radius: 2px !important;
            letter-spacing: 0.12em !important;
            text-align: right !important;
        }

        /* LED dot indicator */
        .led { width: 7px; height: 7px; border-radius: 50%; display: inline-block; border: 1px solid #222; }
        .led-green { background: #00ff41; box-shadow: 0 0 6px #00ff41; border-color: #00aa2a; }
        .led-red   { background: #ff3030; box-shadow: 0 0 6px #ff3030; border-color: #aa1010; }
        .led-amber { background: #ffaa00; box-shadow: 0 0 6px #ffaa00; border-color: #aa7000; }
        .led-cyan  { background: #00d4ff; box-shadow: 0 0 6px #00d4ff; border-color: #0088aa; }
        .led-off   { background: #181820; }

        /* Executor button (scene/event trigger) */
        .exec-btn {
            background: #111116 !important;
            border: 1px solid #22222e !important;
            border-radius: 2px !important;
            cursor: pointer !important;
            transition: background 0.07s, border-color 0.07s !important;
            position: relative !important;
            overflow: hidden !important;
        }
        .exec-btn:hover { background: #18181f !important; border-color: #303040 !important; }
        .exec-btn:active { background: #0a0a12 !important; transform: translateY(1px); }
        .exec-btn.exec-active {
            border-color: #00c832 !important;
            background: #051208 !important;
            box-shadow: inset 0 0 10px rgba(0,200,50,0.12) !important;
        }
        .exec-btn.exec-flash {
            border-color: #e0e0e0 !important;
            background: #dde !important;
        }

        /* Phase badges */
        .phase-break   { color: #38bdf8 !important; border-color: #0e4a6e !important; background: #020d14 !important; }
        .phase-buildup { color: #fbbf24 !important; border-color: #6e4a0e !important; background: #140f06 !important; }
        .phase-drop    { color: #f87171 !important; border-color: #6e0e0e !important; background: #14060a !important; }
        .phase-wait    { color: #6b7280 !important; border-color: #2a2a38 !important; background: #0d0d12 !important; }
    </style>
    """)
    ui.page_title('Light2Wave')

    # --- Branding-Leiste ---
    with ui.row().classes('w-full items-center px-6 py-2 gap-3').style(
        'background: linear-gradient(90deg, #0f172a 0%, #111827 100%); '
        'border-bottom: 1px solid #1e293b; min-height: 44px;'
    ):
        ui.icon('bolt', size='xs').classes('text-cyan-400')
        ui.label('LIGHT').classes('text-white font-black tracking-widest text-lg leading-none')
        ui.label('2WAVE').classes('text-cyan-400 font-black tracking-widest text-lg leading-none').style('margin-left: -6px;')
        with ui.element('div').style('width: 1px; height: 16px; background: #334155; margin: 0 8px;'):
            pass
        ui.label('Professional Light Control System').classes('text-gray-500 text-xs tracking-widest')
        ui.element('div').style('flex: 1;')
        ui.element('img') \
            .props(f'src="data:image/png;base64,{_LOGO_B64}"') \
            .style('height:56px; width:auto; border-radius:3px;')

    # --- Tab-Leiste ---
    with ui.tabs().classes('w-full bg-gray-900 px-4').props(
        'dense indicator-color=cyan active-color=cyan align=left'
    ) as tabs:
        tab_live     = ui.tab('LIVE',     icon='dashboard')
        tab_audio    = ui.tab('AUDIO IN', icon='graphic_eq')
        tab_fixtures = ui.tab('GERÄTE',   icon='lightbulb')
        tab_traverse = ui.tab('TRAVERSE', icon='grid_view')
        tab_event    = ui.tab('EVENTS',   icon='bolt')
        tab_scenes   = ui.tab('SZENEN',   icon='layers')
        tab_dmx      = ui.tab('DMX',      icon='cable')

    ui.separator().classes('bg-gray-800')

    # --- Tab-Inhalte ---
    with ui.tab_panels(tabs, value=tab_live).classes('w-full').style('background-color: #0a0d14;'):
        with ui.tab_panel(tab_live):
            live.create()
        with ui.tab_panel(tab_audio):
            audio.create()
        with ui.tab_panel(tab_fixtures):
            fixtures.create()
        with ui.tab_panel(tab_traverse):
            traverse.create()
        with ui.tab_panel(tab_event):
            event.create()
        with ui.tab_panel(tab_scenes):
            scenes.create()
        with ui.tab_panel(tab_dmx):
            dmx.create()

    ui.timer(1 / 40, state.render)
