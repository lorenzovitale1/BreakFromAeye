"""Download dei file esterni (modello MediaPipe, Android platform-tools). Mai automatico: l'utente deve acconsentire."""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from .config import MODEL_PATH, ROOT, find_model

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
ADB_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
ADB_DIR = ROOT / "tools"


def download(url: str, dest: Path, sha256: Optional[str] = None, timeout: float = 30.0) -> Path:
    """Scarica in un file temporaneo, verifica l'impronta SHA-256 (se nota) e solo allora lo sposta a destinazione."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".part")
    h = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=timeout) as resp:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                h.update(chunk)
                out.write(chunk)
        if sha256 and h.hexdigest() != sha256:
            raise RuntimeError("file scaricato non valido (impronta SHA-256 diversa): download annullato")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return dest


def ensure_model() -> Path:
    if find_model().exists():
        return find_model()
    return download(MODEL_URL, MODEL_PATH, MODEL_SHA256)


def adb_path() -> Path:
    return ADB_DIR / "platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb")


def install_adb() -> Path:
    """Scarica gli Android platform-tools ufficiali (Google) in <dati>/tools/platform-tools."""
    if sys.platform != "win32":
        raise RuntimeError("Download automatico di adb disponibile solo su Windows: installa 'adb' con il tuo gestore di pacchetti.")
    target = adb_path()
    if target.exists():
        return target
    zip_path = ADB_DIR / "platform-tools.zip"
    download(ADB_URL, zip_path, timeout=60.0)
    try:
        base = ADB_DIR.resolve()
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():                          # niente path traversal
                if not (base / name).resolve().is_relative_to(base):
                    raise RuntimeError("archivio adb non valido")
            z.extractall(ADB_DIR)
    finally:
        zip_path.unlink(missing_ok=True)
    if not target.exists():
        raise RuntimeError("adb non trovato nell'archivio scaricato")
    return target


def cli_setup(ask: Callable[[str], bool] = lambda q: input(q + " [s/N] ").strip().lower() in ("s", "si", "y", "yes")) -> int:
    """`python -m eyegaze --setup`: scarica i file mancanti chiedendo conferma per ciascuno."""
    rc = 0
    if find_model().exists():
        print("Modello di rilevamento: già presente.")
    elif ask("Scaricare il modello MediaPipe face_landmarker.task (~4 MB, storage.googleapis.com)?"):
        try:
            print("Scaricato:", ensure_model())
        except Exception as exc:
            print(f"Errore download modello: {exc}")
            rc = 1
    else:
        print("Modello non scaricato: senza di esso il rilevamento non funziona.")
    from .adb import find_adb
    if find_adb():
        print("adb: già disponibile.")
    elif sys.platform == "win32" and ask("Scaricare Android platform-tools (adb, ~8 MB, dl.google.com) per controllare il tablet?"):
        try:
            print("Installato:", install_adb())
        except Exception as exc:
            print(f"Errore download adb: {exc}")
            rc = 1
    return rc
