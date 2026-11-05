"""Estrazione di feature dallo sguardo a partire dai landmark MediaPipe (478 punti con iridi).

Funzioni pure su array numpy: testabili senza webcam né MediaPipe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

# Indici landmark MediaPipe Face Mesh (con iridi)
R_OUTER, R_INNER, R_UP, R_LOW, R_IRIS = 33, 133, 159, 145, 468       # occhio destro del soggetto (sx in immagine)
L_INNER, L_OUTER, L_UP, L_LOW, L_IRIS = 362, 263, 386, 374, 473      # occhio sinistro del soggetto

# Scale fisse per portare le feature a ordini di grandezza simili (più stabile della z-score su pochi punti)
FEATURE_SCALES = np.array([10.0, 10.0, 0.10, 0.10])   # yaw°, pitch°, iride_h, iride_v
FEATURE_NAMES = ("yaw", "pitch", "iris_h", "iris_v")


@dataclass
class FaceFeatures:
    yaw: float        # gradi
    pitch: float      # gradi
    iris_h: float     # posizione orizzontale iride (media occhi), in larghezze d'occhio, + = verso destra in immagine
    iris_v: float     # posizione verticale iride, + = verso il basso
    ear_l: float      # apertura occhio sx (altezza/larghezza)
    ear_r: float
    blink: float      # 0..1 punteggio ammiccamento (da blendshape o EAR)

    def vector(self) -> np.ndarray:
        return np.array([self.yaw, self.pitch, self.iris_h, self.iris_v], dtype=float)


def head_angles(matrix: np.ndarray) -> tuple[float, float]:
    """Yaw/pitch (gradi) dalla matrice di trasformazione 4x4 del volto.

    Usa l'asse «avanti» del volto: monotono rispetto alla rotazione della testa,
    indipendente dal segno scelto (la calibrazione apprende la mappa)."""
    r = np.asarray(matrix, dtype=float)[:3, :3]
    f = r[:, 2] / (np.linalg.norm(r[:, 2]) or 1.0)
    yaw = math.degrees(math.atan2(f[0], f[2]))
    pitch = math.degrees(math.atan2(f[1], math.hypot(f[0], f[2])))
    return yaw, pitch


def _eye(lm: np.ndarray, left_pt: int, right_pt: int, up: int, low: int, iris: int) -> tuple[float, float, float]:
    """(h, v, ear) per un occhio; lm in pixel (x, y). `left_pt` è l'angolo a sinistra in immagine."""
    a, b = lm[left_pt, :2], lm[right_pt, :2]
    width = float(np.linalg.norm(b - a)) or 1e-6
    u = (b - a) / width
    v = np.array([-u[1], u[0]])                 # perpendicolare, + verso il basso
    rel = lm[iris, :2] - (a + b) / 2.0
    ear = float(np.linalg.norm(lm[up, :2] - lm[low, :2])) / width
    return float(rel @ u) / width, float(rel @ v) / width, ear


def extract_features(landmarks: np.ndarray, width: int, height: int, matrix: Optional[np.ndarray],
                     blendshapes: Optional[dict[str, float]] = None) -> FaceFeatures:
    """`landmarks`: array (N>=478, 3) normalizzato [0,1]. Corregge implicitamente il rollio (assi dell'occhio)."""
    lm = np.asarray(landmarks, dtype=float).copy()
    lm[:, 0] *= width
    lm[:, 1] *= height
    hr, vr, ear_r = _eye(lm, R_OUTER, R_INNER, R_UP, R_LOW, R_IRIS)
    hl, vl, ear_l = _eye(lm, L_INNER, L_OUTER, L_UP, L_LOW, L_IRIS)
    yaw, pitch = head_angles(matrix) if matrix is not None else (0.0, 0.0)
    if blendshapes and "eyeBlinkLeft" in blendshapes and "eyeBlinkRight" in blendshapes:
        blink = max(blendshapes["eyeBlinkLeft"], blendshapes["eyeBlinkRight"])
    else:
        # fallback EAR: occhio aperto ~0.25-0.35, chiuso < 0.12
        blink = float(np.clip(1.0 - min(ear_l, ear_r) / 0.25, 0.0, 1.0))
    return FaceFeatures(yaw, pitch, (hr + hl) / 2.0, (vr + vl) / 2.0, ear_l, ear_r, float(blink))
