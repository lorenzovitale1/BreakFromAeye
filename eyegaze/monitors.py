"""Geometria dei monitor (Windows) per la calibrazione, anche con secondo schermo."""
from __future__ import annotations

import sys
from typing import NamedTuple


class Rect(NamedTuple):
    x: int
    y: int
    w: int
    h: int
    primary: bool = False


def set_dpi_aware() -> None:
    """Coordinate Tk = pixel reali (altrimenti la calibrazione è scalata sugli schermi con zoom > 100%)."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def list_monitors() -> list[Rect]:
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    out: list[Rect] = []

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    def cb(hmon, hdc, rc, data):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r = mi.rcMonitor
        out.append(Rect(r.left, r.top, r.right - r.left, r.bottom - r.top, bool(mi.dwFlags & 1)))
        return True

    proto = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    ctypes.windll.user32.EnumDisplayMonitors(0, 0, proto(cb), 0)
    out.sort(key=lambda r: (not r.primary, r.x, r.y))      # principale per primo
    return out


def monitor_options() -> list[tuple[str, str]]:
    """[(valore per config, etichetta)] per la scelta dell'area da monitorare."""
    mons = list_monitors()
    if len(mons) < 2:
        return [("all", "Schermo")]
    prim = mons[0]
    opts = [("all", f"Tutti i monitor ({len(mons)})")]
    for i, m in enumerate(mons):
        if m.primary:
            where = "principale"
        else:
            where = ("a sinistra" if m.x < prim.x else "a destra" if m.x >= prim.x + prim.w
                     else "sopra" if m.y < prim.y else "sotto")
        opts.append((str(i), f"Monitor {i + 1} · {where} · {m.w}x{m.h}"))
    return opts


def calibration_rect(setting: str, fallback: Rect) -> Rect:
    """'all' = scrivania virtuale, 'primary' = monitor principale, oppure indice del monitor."""
    mons = list_monitors()
    if not mons:
        return fallback
    s = str(setting).strip().lower()
    if s == "primary":
        return mons[0]
    if s.isdigit() and int(s) < len(mons):
        return mons[int(s)]
    x0 = min(m.x for m in mons)
    y0 = min(m.y for m in mons)
    x1 = max(m.x + m.w for m in mons)
    y1 = max(m.y + m.h for m in mons)
    return Rect(x0, y0, x1 - x0, y1 - y0)
