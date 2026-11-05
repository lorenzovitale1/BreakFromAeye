"""Simulazione senza hardware: sequenze di sguardo finte -> comandi previsti (dry-run). Tempo simulato, istantaneo."""
from __future__ import annotations

import time

import numpy as np

from . import config as cfgmod
from .calibration import calibration_grid, fit_model
from .capture import FrameResult
from .engine import Engine, build_outputs
from .features import FaceFeatures

FPS = 15
SCREEN_CENTER = (0.5, 0.5)
TABLET_DOWN = (0.5, 2.2)        # guarda molto sotto lo schermo


def synthetic_model():
    pts = []
    for (tx, ty) in calibration_grid():
        pts.append(((tx, ty), [np.array([(tx - 0.5) * 20, (ty - 0.5) * 12, 0.0, 0.0]) for _ in range(10)]))
    return fit_model(pts)


def face(x, y, blink=0.0):
    return FrameResult("face", FaceFeatures((x - 0.5) * 20, (y - 0.5) * 12, 0, 0, 0.3, 0.3, blink))


SCENARIOS: dict[str, list[tuple[str, FrameResult, float]]] = {
    "demo": [
        ("stabilizzazione: guardo il PC", face(*SCREEN_CENTER), 4),
        ("leggo agli angoli dello schermo", face(0.03, 0.03), 3),
        ("leggo nell'angolo opposto", face(0.97, 0.97), 3),
        ("ammiccamento", face(*SCREEN_CENTER, blink=0.9), 0.4),
        ("occhiata rapida al tablet (0,8 s)", face(*TABLET_DOWN), 0.8),
        ("torno sullo schermo", face(*SCREEN_CENTER), 3),
        ("guardo il tablet (4 s)  -> atteso PLAY", face(*TABLET_DOWN), 4),
        ("torno al PC (3 s)       -> atteso PAUSA", face(*SCREEN_CENTER), 3),
        ("volto fuori inquadratura (3 s) -> atteso PLAY", FrameResult("no_face"), 3),
        ("torno al PC             -> atteso PAUSA", face(*SCREEN_CENTER), 3),
        ("webcam scollegata (10 s) -> nessun comando", FrameResult("camera_fail", detail="webcam scollegata"), 10),
        ("webcam torna, guardo il PC", face(*SCREEN_CENTER), 4),
    ],
}


def run(name: str = "demo", cfg: dict | None = None) -> list[str]:
    cfg = cfg or cfgmod.load()
    cfg = {**cfg, "dry_run": True}
    cfg["detection"] = {**cfg["detection"], "smoothing": 0.0}
    lines: list[str] = []
    clock = {"t": 0.0}
    eng = Engine(cfg, source=type("S", (), {"close": lambda s: None})(), outputs=build_outputs(cfg, lambda m: None),
                 model=synthetic_model(), clock=lambda: clock["t"], printer=lines.append)
    eng._setup()
    for desc, res, secs in SCENARIOS[name]:
        lines.append(f"--- t={clock['t']:5.1f}s  {desc}")
        for _ in range(round(secs * FPS)):
            eng.step(res, clock["t"])
            clock["t"] += 1 / FPS
        time.sleep(0.15)                       # lascia lavorare i thread delle uscite
    eng._teardown()
    return lines
