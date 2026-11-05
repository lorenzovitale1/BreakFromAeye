"""Acquisizione webcam + rilevamento volto. Nessun fotogramma viene salvato o inviato in rete."""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .config import MODEL_PATH
from .features import FaceFeatures, extract_features


@dataclass
class FrameResult:
    kind: str                                   # "camera_fail" | "no_face" | "face"
    features: Optional[FaceFeatures] = None
    preview: Optional[np.ndarray] = None        # BGR ridotto, solo se richiesto
    detail: str = ""


class ModelMissing(RuntimeError):
    pass


class FaceDetector:
    """MediaPipe Face Landmarker (Tasks API): 478 landmark con iridi, blendshape, matrice di posa."""

    def __init__(self, model_path=MODEL_PATH):
        if not model_path.exists():
            raise ModelMissing(f"Modello mancante: {model_path.name}. Riapri l'app e accetta il download, oppure esegui «python -m eyegaze --setup».")
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        self._mp = mp
        opts = vision.FaceLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO, num_faces=1,
            min_face_detection_confidence=0.5, min_face_presence_confidence=0.5, min_tracking_confidence=0.5,
            output_face_blendshapes=True, output_facial_transformation_matrixes=True)
        self._lm = vision.FaceLandmarker.create_from_options(opts)
        self._last_ms = 0

    def detect(self, frame_bgr: np.ndarray) -> Optional[FaceFeatures]:
        import cv2
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        self._last_ms = max(self._last_ms + 1, int(time.monotonic() * 1000))   # timestamp strettamente crescente
        res = self._lm.detect_for_video(img, self._last_ms)
        if not res.face_landmarks:
            return None
        pts = np.array([[p.x, p.y, p.z] for p in res.face_landmarks[0]], dtype=float)
        if len(pts) < 478:
            return None
        matrix = res.facial_transformation_matrixes[0] if res.facial_transformation_matrixes else None
        bs = {c.category_name: c.score for c in res.face_blendshapes[0]} if res.face_blendshapes else None
        return extract_features(pts, w, h, matrix, bs)

    def close(self) -> None:
        try:
            self._lm.close()
        except Exception:
            pass


class FrameSource:
    """Webcam + detector, con diagnosi di guasto: scollegata, bloccata (frame identici) o buia (obiettivo coperto)."""

    READ_FAIL_S, FROZEN_S, DARK_S, REOPEN_S = 1.0, 2.5, 2.0, 3.0

    def __init__(self, camera_cfg: dict, want_preview: bool = False, detector: Optional[FaceDetector] = None):
        self.cfg = camera_cfg
        self.want_preview = want_preview
        self.detector = detector
        self._cap = None
        self._last_ok = time.monotonic()
        self._last_change = time.monotonic()
        self._dark_since: Optional[float] = None
        self._sig: Optional[bytes] = None
        self._last_open_try = -1e9

    def _open(self) -> None:
        import cv2
        self._last_open_try = time.monotonic()
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(int(self.cfg["index"]), backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg["width"])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg["height"])
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._cap = cap
            self._last_ok = self._last_change = time.monotonic()
        else:
            cap.release()
            self._cap = None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self.detector:
            self.detector.close()

    def next(self) -> FrameResult:
        import cv2
        now = time.monotonic()
        if self._cap is None:
            if now - self._last_open_try >= self.REOPEN_S:
                self._open()
            if self._cap is None:
                return FrameResult("camera_fail", detail="webcam non disponibile")
        ok, frame = self._cap.read()
        now = time.monotonic()
        if not ok or frame is None:
            if now - self._last_ok >= self.READ_FAIL_S:
                self._cap.release()
                self._cap = None
                return FrameResult("camera_fail", detail="webcam scollegata o errore di lettura")
            return FrameResult("no_data")
        self._last_ok = now

        small = cv2.resize(frame, (32, 24), interpolation=cv2.INTER_AREA)
        sig = small.tobytes()
        if sig != self._sig:
            self._sig, self._last_change = sig, now
        if now - self._last_change >= self.FROZEN_S:
            return FrameResult("camera_fail", detail="webcam bloccata (immagine ferma)")
        if float(small.mean()) < 4.0:
            self._dark_since = self._dark_since or now
            if now - self._dark_since >= self.DARK_S:
                return FrameResult("camera_fail", detail="immagine nera (obiettivo coperto?)")
        else:
            self._dark_since = None

        if self.detector is None:                    # modello mancante: mai interpretare l'assenza di rilevatore come «sguardo altrove»
            return FrameResult("no_data")
        feats = self.detector.detect(frame)
        prev = cv2.resize(frame, (240, 180)) if self.want_preview else None
        if feats is None:
            return FrameResult("no_face", preview=prev)
        return FrameResult("face", feats, prev)
