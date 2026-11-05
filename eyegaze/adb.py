"""Client ADB minimale: individuazione, dispositivi, pairing/connessione Wi-Fi, tasti multimediali.

Il `runner` è iniettabile (tests con ADB finto). Codici di pairing e segreti non vengono mai registrati nei log.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import BUNDLE_DIR, ROOT

KEY_PLAY, KEY_PAUSE, KEY_PLAY_PAUSE = 126, 127, 85
STATE_PLAYING, STATE_PAUSED = 3, 2

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class AdbError(RuntimeError):
    pass


@dataclass(frozen=True)
class Device:
    serial: str
    state: str          # device | offline | unauthorized | ...
    model: str = ""

    @property
    def ready(self) -> bool:
        return self.state == "device"

    @property
    def label(self) -> str:
        return f"{self.model or 'Android'} ({self.serial})"


def _run_default(args, **kw):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    return subprocess.run(args, capture_output=True, text=True, creationflags=flags, **kw)


def find_adb(configured: str = "") -> Optional[str]:
    """Ordine: percorso in config -> tools/platform-tools -> PATH -> cartelle standard Windows/Android SDK."""
    cands: list[Path] = []
    if configured:
        cands.append(Path(configured))
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    cands.append(ROOT / "tools" / "platform-tools" / exe)
    cands.append(BUNDLE_DIR / "tools" / "platform-tools" / exe)      # incluso nell'installer
    on_path = shutil.which("adb")
    if on_path:
        cands.append(Path(on_path))
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(env):
            cands.append(Path(os.environ[env]) / "platform-tools" / exe)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cands.append(Path(local) / "Android" / "Sdk" / "platform-tools" / exe)
    for c in cands:
        if c.is_file():
            return str(c)
    return None


class AdbClient:
    def __init__(self, adb_path: str = "", runner: Runner = _run_default, timeout: float = 8.0):
        self._configured = adb_path
        self._run = runner
        self.timeout = timeout
        self.adb: Optional[str] = None

    def locate(self) -> Optional[str]:
        self.adb = find_adb(self._configured)
        return self.adb

    def _exec(self, *args: str, timeout: Optional[float] = None, secret: bool = False) -> str:
        if not self.adb and not self.locate():
            raise AdbError("adb non trovato: esegui setup.bat (o «breakfromaeye --setup») oppure indica il percorso in Impostazioni.")
        try:
            cp = self._run([self.adb, *args], timeout=timeout or self.timeout)
        except subprocess.TimeoutExpired:
            raise AdbError("adb non risponde (timeout).")
        except OSError as exc:
            raise AdbError(f"impossibile eseguire adb: {exc}")
        out = ((cp.stdout or "") + (cp.stderr or "")).strip()
        if cp.returncode != 0:
            shown = "operazione non riuscita" if secret else out[:200]
            raise AdbError(shown or f"adb codice {cp.returncode}")
        return out

    # ---- dispositivi ----------------------------------------------------
    def devices(self) -> list[Device]:
        out = self._exec("devices", "-l")
        res: list[Device] = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2 or line.startswith("*"):
                continue
            m = re.search(r"model:(\S+)", line)
            res.append(Device(parts[0], parts[1], m.group(1).replace("_", " ") if m else ""))
        return res

    def connect(self, hostport: str) -> str:
        out = self._exec("connect", hostport, timeout=12)
        if "connected" not in out.lower() or "cannot" in out.lower() or "failed" in out.lower():
            raise AdbError(out[:200] or "connessione non riuscita")
        return out

    def pair(self, hostport: str, code: str) -> str:
        """Il codice è l'argomento del comando ma non finisce mai in log o messaggi d'errore."""
        out = self._exec("pair", hostport, code, timeout=20, secret=True)
        if "successfully" not in out.lower():
            raise AdbError("abbinamento non riuscito: controlla porta di pairing e codice (scadono presto).")
        return "Abbinamento riuscito"

    def disconnect(self, hostport: str = "") -> None:
        try:
            self._exec("disconnect", *([hostport] if hostport else []))
        except AdbError:
            pass

    # ---- comandi ---------------------------------------------------------
    def keyevent(self, serial: str, code: int) -> None:
        self._exec("-s", serial, "shell", "input", "keyevent", str(code))

    def playback_state(self, serial: str) -> Optional[int]:
        """Stato PlaybackState della prima sessione multimediale attiva (3=play, 2=pausa) oppure None."""
        try:
            out = self._exec("-s", serial, "shell", "dumpsys", "media_session", timeout=10)
        except AdbError:
            return None
        for m in re.finditer(r"state=PlaybackState\s*\{state=(\d+)", out):
            st = int(m.group(1))
            if st in (STATE_PLAYING, STATE_PAUSED, 6):    # 6 = buffering (conta come in riproduzione)
                return STATE_PLAYING if st == 6 else st
        return None
