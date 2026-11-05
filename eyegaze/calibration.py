"""Modello di sguardo: regressione ridge (feature -> punto sullo schermo) appresa dalla calibrazione."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .features import FEATURE_SCALES
from .config import CALIBRATION_PATH, calibration_key, calibration_path

MAX_YAW_DEG = 70.0   # oltre questa rotazione dal centro calibrato è sempre «altrove»


def calibration_grid(n: int = 3, lo: float = 0.08, hi: float = 0.92) -> list[tuple[float, float]]:
    """Punti (x, y) in frazioni dell'area calibrata: centro per primo, poi angoli e bordi."""
    mid = 0.5
    pts = [(mid, mid), (lo, lo), (hi, lo), (hi, hi), (lo, hi), (mid, lo), (hi, mid), (mid, hi), (lo, mid)]
    return pts


@dataclass
class GazeModel:
    weights: np.ndarray                  # (5, 2): bias + 4 feature
    center_yaw: float
    rmse: float                          # errore di adattamento, in frazione di schermo
    area: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)

    def predict(self, vec: np.ndarray) -> tuple[float, float]:
        x = np.concatenate([[1.0], np.asarray(vec, dtype=float) / FEATURE_SCALES])
        out = x @ self.weights
        return float(out[0]), float(out[1])

    # ---- classificazione con isteresi ----------------------------------
    @staticmethod
    def inside(x: float, y: float, margin: float) -> bool:
        return -margin <= x <= 1 + margin and -margin <= y <= 1 + margin

    def is_at_screen(self, x: float, y: float, yaw: float, was_at: bool, margin: float, hysteresis: float) -> bool:
        if abs(yaw - self.center_yaw) > MAX_YAW_DEG:
            return False
        m = margin + hysteresis if was_at else max(0.0, margin - hysteresis)
        return self.inside(x, y, m)

    # ---- persistenza ----------------------------------------------------
    def to_json(self) -> dict:
        return {"version": 1, "weights": self.weights.tolist(), "center_yaw": self.center_yaw,
                "rmse": self.rmse, "area": self.area, "created": self.created}

    @classmethod
    def from_json(cls, d: dict) -> "GazeModel":
        w = np.array(d["weights"], dtype=float)
        if w.shape != (5, 2):
            raise ValueError("calibrazione non valida")
        return cls(w, float(d["center_yaw"]), float(d.get("rmse", 0.0)), d.get("area", {}), float(d.get("created", 0)))

    def save(self, path: Path = CALIBRATION_PATH) -> None:
        path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")

    @classmethod
    def load_for(cls, setting) -> Optional["GazeModel"]:
        """Calibrazione salvata per l'area scelta (o, per compatibilita, il vecchio file unico se riguarda la stessa area)."""
        m = cls.load(calibration_path(setting))
        if m is None:
            old = cls.load(CALIBRATION_PATH)
            if old is not None and calibration_key(old.area.get("monitor", "all")) == calibration_key(setting):
                return old
        return m

    @classmethod
    def load(cls, path: Path = CALIBRATION_PATH) -> Optional["GazeModel"]:
        try:
            return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None


def fit_model(samples: list[tuple[tuple[float, float], list[np.ndarray]]], ridge: float = 0.3,
              area: Optional[dict] = None) -> GazeModel:
    """`samples`: per ogni punto bersaglio (x, y) l'elenco dei vettori feature raccolti.

    Per robustezza ogni punto è ridotto alla mediana dopo aver scartato gli outlier (MAD)."""
    xs, ys = [], []
    for (tx, ty), vecs in samples:
        if len(vecs) < 3:
            continue
        arr = np.array(vecs, dtype=float) / FEATURE_SCALES
        med = np.median(arr, axis=0)
        mad = np.median(np.abs(arr - med), axis=0) + 1e-6
        keep = np.all(np.abs(arr - med) <= 4.0 * 1.4826 * mad + 0.05, axis=1)
        good = arr[keep] if keep.sum() >= 3 else arr
        xs.append(np.concatenate([[1.0], np.median(good, axis=0)]))
        ys.append([tx, ty])
    if len(xs) < 5:
        raise ValueError("Troppo pochi punti validi: assicurati che il volto resti visibile durante la calibrazione.")
    X, Y = np.array(xs), np.array(ys)
    reg = ridge * np.eye(X.shape[1])
    reg[0, 0] = 0.0                                         # il bias non si penalizza
    W = np.linalg.solve(X.T @ X + reg, X.T @ Y)
    rmse = float(np.sqrt(np.mean((X @ W - Y) ** 2)))
    center_yaw = float(np.median([v[1] * FEATURE_SCALES[0] for v in xs]))   # yaw mediano dei punti
    return GazeModel(W, center_yaw, rmse, area or {})


def zone_from_points(points, pad: float = 0.08, name: str = "Area sicura") -> dict:
    """Area sicura = riquadro (5°-95° percentile dei punti guardati) + margine, nelle coordinate dello schermo (0..1 = schermo)."""
    arr = np.array(points, dtype=float).reshape(-1, 2)
    if len(arr) < 8:
        raise ValueError("Troppo pochi dati: tieni lo sguardo sull'area e il volto visibile.")
    lo, hi = np.percentile(arr, 5, axis=0), np.percentile(arr, 95, axis=0)
    return {"name": name, "enabled": True, "x0": float(lo[0] - pad), "y0": float(lo[1] - pad),
            "x1": float(hi[0] + pad), "y1": float(hi[1] + pad)}


def zone_from_corners(corners, pad: float = 0.03, name: str = "Area sicura") -> dict:
    """Area sicura dai 4 angoli guardati uno a uno: riquadro che li contiene (mediana dei punti di ogni angolo) + margine."""
    pts = []
    for samples in corners:
        arr = np.array(samples, dtype=float).reshape(-1, 2)
        if len(arr) < 5:
            raise ValueError("Troppo pochi dati su un angolo: tieni il volto visibile e lo sguardo fermo.")
        pts.append(np.median(arr, axis=0))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {"name": name, "enabled": True, "x0": float(min(xs) - pad), "y0": float(min(ys) - pad),
            "x1": float(max(xs) + pad), "y1": float(max(ys) + pad)}


def in_zone(z: dict, x: float, y: float, margin: float = 0.0) -> bool:
    return z["x0"] - margin <= x <= z["x1"] + margin and z["y0"] - margin <= y <= z["y1"] + margin


def keyboard_preset() -> dict:
    """Stima della zona sotto lo schermo (tastiera). Meglio registrarla guardandola davvero."""
    return {"name": "Tastiera (stima)", "enabled": True, "x0": 0.0, "y0": 1.15, "x1": 1.0, "y1": 1.9}
