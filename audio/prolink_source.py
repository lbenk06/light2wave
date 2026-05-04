"""
Pro DJ Link Listener
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Verbindet sich als virtueller CDJ-Player ins Pioneer-Netzwerk
und schreibt Beats, Playhead und Waveform nach `live_audio_state`.

Architektur (Decoupling):
    - Backend schreibt NUR in live_audio_state.
    - Keine direkten GUI-/Engine-Aufrufe.

Zwei Backends:
    1. python-prodj-link (flesniak)
       → liefert Beats, Position (ms), Track-Metadata, Waveform
    2. Roher UDP-Listener auf Port 50001 (Fallback ohne Library)
       → liefert nur Beats + BPM (kein Waveform, keine Position)

Public API:
    start_prolink(interface_name=None) -> (ok: bool, msg: str)
    stop_prolink() -> None
    is_running() -> bool
"""
from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Optional

import numpy as np

from audio.audio_live import live_audio_state

# ── State-Erweiterung (idempotent, ueberschreibt nichts) ────────────────
_PROLINK_DEFAULTS = {
    "prolink_active":         False,
    "prolink_status":         "Getrennt",
    "prolink_master_player":  None,
    "prolink_player_count":   0,
    "track_loaded":           False,
    "track_id":               None,
    "track_title":            "",
    "track_artist":           "",
    "track_length":           0.0,    # Sekunden
    "current_time":           0.0,    # Sekunden — abgespielte Position
    "bpm_prolink":            0.0,
    "waveform_data":          None,   # np.ndarray uint8 — Hoehen 0..31
    "waveform_color":         None,   # Optional RGB
}
for _k, _v in _PROLINK_DEFAULTS.items():
    live_audio_state.setdefault(_k, _v)

# ── Pro DJ Link Konstanten ───────────────────────────────────────────────
_BEAT_PORT     = 50001
_HEADER        = b"Qspt1WmJOL"
_PKT_TYPE_BEAT = 0x28


# ════════════════════════════════════════════════════════════════════════
#  Backend 1 — python-prodj-link (High-Level)
# ════════════════════════════════════════════════════════════════════════

_prodj_lib_available = False
try:
    from prodj import ProDj as _ProDj   # type: ignore
    _prodj_lib_available = True
except Exception:
    _ProDj = None  # type: ignore


_prodj_instance = None
_position_thread: Optional[threading.Thread] = None
_stop_flag = threading.Event()


def _on_client_change(client_number: int) -> None:
    """python-prodj-link: Client-Status-Update (auch Beats kommen hier rein)."""
    if _prodj_instance is None:
        return
    try:
        client = _prodj_instance.cl.getClient(client_number)
    except Exception:
        return
    if client is None:
        return

    # Beat-Trigger — beat-in-bar 1..4 vom Master-CDJ
    new_beat = getattr(client, "beat", None)
    if new_beat is not None and 1 <= int(new_beat) <= 4:
        prev_idx = live_audio_state.get("beat_index", -1)
        new_idx  = (int(new_beat) - 1) % 4
        if new_idx != prev_idx:
            live_audio_state["beat_triggered"] = True
            live_audio_state["beat_index"]     = new_idx

    # BPM (master)
    bpm = getattr(client, "bpm", None)
    if bpm:
        try:
            live_audio_state["bpm_prolink"] = float(bpm)
        except Exception:
            pass

    # Position in ms → Sekunden
    pos = getattr(client, "position", None)
    if pos is not None:
        try:
            live_audio_state["current_time"] = float(pos) / 1000.0
        except Exception:
            pass

    # Master-Erkennung
    if getattr(client, "is_master", False):
        live_audio_state["prolink_master_player"] = client_number

    # Player-Count Update
    try:
        live_audio_state["prolink_player_count"] = len(_prodj_instance.cl.clients)
    except Exception:
        pass


def _on_metadata(client_number: int, slot: str, track_id: int, metadata: dict) -> None:
    """python-prodj-link: neue Track-Metadaten verfuegbar."""
    if _prodj_instance is None:
        return

    title  = metadata.get("title", "") if metadata else ""
    artist = metadata.get("artist", "") if metadata else ""
    length = float(metadata.get("duration", 0.0) or 0.0) if metadata else 0.0

    live_audio_state["track_id"]     = track_id
    live_audio_state["track_title"]  = title or ""
    live_audio_state["track_artist"] = artist or ""
    live_audio_state["track_length"] = length

    # Waveform anfragen (Preview = klein, schnell)
    try:
        wf_raw = _prodj_instance.data.get_preview_waveform(
            client_number, slot, track_id
        )
        if wf_raw:
            arr = np.frombuffer(wf_raw, dtype=np.uint8)
            live_audio_state["waveform_data"] = arr
            live_audio_state["track_loaded"]  = True
        else:
            live_audio_state["waveform_data"] = None
    except Exception as e:
        print(f"[prolink] Waveform-Fetch fehlgeschlagen: {e}")
        live_audio_state["waveform_data"] = None


def _start_high_level(interface_name: Optional[str]) -> bool:
    global _prodj_instance
    if not _prodj_lib_available or _ProDj is None:
        return False
    try:
        _prodj_instance = _ProDj()
        if interface_name and hasattr(_prodj_instance, "set_interface_name"):
            _prodj_instance.set_interface_name(interface_name)

        # Callbacks defensiv setzen — API variiert zwischen Versionen
        if hasattr(_prodj_instance, "set_client_change_callback"):
            _prodj_instance.set_client_change_callback(_on_client_change)
        if hasattr(_prodj_instance, "set_metadata_change_callback"):
            _prodj_instance.set_metadata_change_callback(_on_metadata)

        _prodj_instance.start()

        # Als virtueller CDJ #5 ankuendigen (1-4 sind echte Player)
        if hasattr(_prodj_instance, "vcdj_set_player_number"):
            _prodj_instance.vcdj_set_player_number(5)
        if hasattr(_prodj_instance, "vcdj_enable"):
            _prodj_instance.vcdj_enable()

        live_audio_state["prolink_active"] = True
        live_audio_state["prolink_status"] = "Verbunden (python-prodj-link)"
        print("[prolink] high-level backend gestartet")
        return True
    except Exception as e:
        print(f"[prolink] high-level start fehlgeschlagen: {e}")
        _prodj_instance = None
        return False


# ════════════════════════════════════════════════════════════════════════
#  Backend 2 — Minimaler UDP Beat-Listener (Fallback)
# ════════════════════════════════════════════════════════════════════════

_sock: Optional[socket.socket] = None
_udp_thread: Optional[threading.Thread] = None


def _udp_loop() -> None:
    """Minimal-Listener — extrahiert nur Beats und BPM aus Port 50001."""
    last_beat_t = 0.0
    while not _stop_flag.is_set():
        if _sock is None:
            break
        try:
            data, _addr = _sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            break
        except Exception as e:
            print(f"[prolink] socket error: {e}")
            break

        if len(data) < 96 or not data.startswith(_HEADER):
            continue
        if data[10] != _PKT_TYPE_BEAT:
            continue

        # Beat-Paket: BPM @ 0x5a (BE u16, BPM*100), beat-in-bar @ 0x5c
        try:
            bpm_raw     = struct.unpack(">H", data[0x5a:0x5c])[0]
            beat_in_bar = data[0x5c]
        except (struct.error, IndexError):
            continue

        if 0 < bpm_raw < 30000:
            live_audio_state["bpm_prolink"] = bpm_raw / 100.0

        if 1 <= beat_in_bar <= 4:
            now = time.time()
            if now - last_beat_t > 0.05:   # Entprellung max ~20 Beats/s
                last_beat_t = now
                live_audio_state["beat_triggered"] = True
                live_audio_state["beat_index"]     = (beat_in_bar - 1) % 4

        live_audio_state["prolink_status"] = "UDP-Fallback (Port 50001)"


def _start_udp_fallback() -> bool:
    global _sock, _udp_thread
    try:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _sock.settimeout(1.0)
        _sock.bind(("0.0.0.0", _BEAT_PORT))
        _stop_flag.clear()
        _udp_thread = threading.Thread(target=_udp_loop, daemon=True,
                                       name="prolink-udp")
        _udp_thread.start()
        live_audio_state["prolink_active"] = True
        live_audio_state["prolink_status"] = "UDP-Fallback aktiv (Port 50001)"
        print("[prolink] UDP-Fallback gestartet (Port 50001)")
        return True
    except Exception as e:
        live_audio_state["prolink_status"] = f"Fehler: {e}"
        print(f"[prolink] UDP-Bind fehlgeschlagen: {e}")
        if _sock is not None:
            try: _sock.close()
            except Exception: pass
            _sock = None
        return False


# ════════════════════════════════════════════════════════════════════════
#  Public API
# ════════════════════════════════════════════════════════════════════════

def start_prolink(interface_name: Optional[str] = None) -> tuple[bool, str]:
    """Startet die Pro-DJ-Link-Verbindung.
    Pausiert vorher den Mic-Stream (inkl. ML-Inferenz)."""
    if live_audio_state.get("prolink_active"):
        return True, "bereits aktiv"

    # ML / Mic-Stream pausieren — verhindert PyTorch-CPU-Last im PROLINK-Modus
    try:
        from audio.audio_live import stop_listening
        if live_audio_state.get("is_listening"):
            stop_listening()
            print("[prolink] Mic-Stream + ML pausiert")
    except Exception as e:
        print(f"[prolink] stop_listening warnung: {e}")

    if _start_high_level(interface_name):
        return True, live_audio_state["prolink_status"]
    if _start_udp_fallback():
        return True, live_audio_state["prolink_status"]
    return False, live_audio_state.get("prolink_status", "Fehler")


def stop_prolink() -> None:
    global _prodj_instance, _sock, _udp_thread
    _stop_flag.set()

    if _prodj_instance is not None:
        try:
            _prodj_instance.stop()
        except Exception:
            pass
        _prodj_instance = None

    if _sock is not None:
        try: _sock.close()
        except Exception: pass
        _sock = None

    if _udp_thread is not None:
        _udp_thread.join(timeout=1.5)
        _udp_thread = None

    live_audio_state["prolink_active"]        = False
    live_audio_state["prolink_status"]        = "Getrennt"
    live_audio_state["prolink_master_player"] = None
    live_audio_state["track_loaded"]          = False
    live_audio_state["waveform_data"]         = None
    live_audio_state["track_title"]           = ""
    live_audio_state["track_artist"]          = ""
    live_audio_state["track_length"]          = 0.0
    live_audio_state["current_time"]          = 0.0
    print("[prolink] gestoppt")


def is_running() -> bool:
    return bool(live_audio_state.get("prolink_active"))


def backend_label() -> str:
    """Gibt zurueck welches Backend aktiv ist (fuer UI-Hinweis)."""
    if not is_running():
        return "offline"
    return "high-level" if _prodj_instance is not None else "udp-fallback"
