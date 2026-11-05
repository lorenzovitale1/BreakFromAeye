"""Uscite: dove inviare PLAY/PAUSA (tablet via ADB, player del PC via Windows Media Session) + dispatcher."""
from __future__ import annotations

import asyncio
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .adb import (AdbClient, AdbError, KEY_PAUSE, KEY_PLAY, KEY_PLAY_PAUSE, STATE_PAUSED, STATE_PLAYING)


@dataclass
class CommandResult:
    ts: float
    output: str
    action: str          # play | pause
    ok: bool
    message: str = ""
    dry_run: bool = False


class Output:
    """Interfaccia comune. `send` è bloccante e viene chiamato solo dal thread del dispatcher."""
    name = "output"
    label = "Uscita"

    def send(self, action: str) -> CommandResult:  # pragma: no cover
        raise NotImplementedError

    def status(self) -> dict:
        return {"connected": False, "detail": ""}

    def refresh(self) -> None:
        """Aggiorna la cache di stato (connessione). Chiamato periodicamente dal thread del dispatcher."""

    def close(self) -> None:
        pass


class DryRunOutput(Output):
    """Registra il comando previsto senza inviarlo."""

    def __init__(self, inner: Output, printer: Callable[[str], None] = print):
        self.inner, self.name, self.label, self._print = inner, inner.name, inner.label, printer
        self.planned: list[str] = []

    def send(self, action: str) -> CommandResult:
        desc = self.inner.describe(action) if hasattr(self.inner, "describe") else action.upper()
        self.planned.append(desc)
        self._print(f"[dry-run] {self.label}: {desc}")
        return CommandResult(time.time(), self.name, action, True, f"(dry-run) {desc}", dry_run=True)

    def status(self) -> dict:
        s = dict(self.inner.status())
        s["detail"] = (s.get("detail", "") + " · dry-run").strip(" ·")
        return s

    def refresh(self) -> None:
        self.inner.refresh()


# ------------------------------------------------------------------ tablet
class AdbOutput(Output):
    name, label = "tablet", "Tablet Android"

    MAX_RETRIES = 2
    RECONNECT_MIN_INTERVAL = 5.0

    def __init__(self, cfg: dict, client: Optional[AdbClient] = None):
        self.cfg = cfg                       # sotto-dizionario outputs.tablet
        self.client = client or AdbClient(cfg.get("adb_path", ""))
        self.serial = cfg.get("serial", "")
        self._status = {"connected": False, "detail": "non verificato", "serial": self.serial, "model": ""}
        self._last_reconnect = -1e9

    def describe(self, action: str) -> str:
        code = KEY_PLAY if action == "play" else KEY_PAUSE
        s = self.serial or "<seriale da scegliere>"
        extra = " (via toggle_if_needed)" if self.cfg.get("method") == "toggle_if_needed" else ""
        return f"adb -s {s} shell input keyevent {code}{extra}"

    # selezione esplicita del dispositivo: mai inventare un seriale
    def select(self, serial: str) -> None:
        self.serial = serial
        self.cfg["serial"] = serial

    def _resolve(self) -> str:
        devs = self.client.devices()
        ready = [d for d in devs if d.ready]
        if self.serial:
            match = next((d for d in devs if d.serial == self.serial), None)
            if match and match.ready:
                self._status.update(connected=True, detail="connesso", serial=match.serial, model=match.model)
                return self.serial
            if match and not match.ready:
                raise AdbError(f"dispositivo {match.serial} in stato «{match.state}»")
            raise AdbError(f"dispositivo {self.serial} non trovato")
        if len(ready) == 1:                          # un solo dispositivo pronto: scelta non ambigua
            self.serial = ready[0].serial
            self._status.update(connected=True, detail="connesso", serial=self.serial, model=ready[0].model)
            return self.serial
        if not ready:
            raise AdbError("nessun dispositivo connesso")
        raise AdbError("più dispositivi connessi: selezionane uno")

    def refresh(self) -> None:
        try:
            self._resolve()
        except AdbError as exc:
            self._status.update(connected=False, detail=str(exc))

    def status(self) -> dict:
        return dict(self._status)

    def _try_reconnect(self) -> None:
        now = time.monotonic()
        if now - self._last_reconnect < self.RECONNECT_MIN_INTERVAL:
            return
        self._last_reconnect = now
        if self.serial and ":" in self.serial:         # dispositivo Wi-Fi: riprova la connessione
            try:
                self.client.connect(self.serial)
            except AdbError:
                pass

    def send(self, action: str) -> CommandResult:
        last_err = ""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                serial = self._resolve()
                self._do(serial, action)
                self._status.update(connected=True, detail="connesso")
                return CommandResult(time.time(), self.name, action, True, self.describe(action))
            except AdbError as exc:
                last_err = str(exc)
                self._status.update(connected=False, detail=last_err)
                if attempt < self.MAX_RETRIES:
                    self._try_reconnect()
                    time.sleep(0.4)
        return CommandResult(time.time(), self.name, action, False, f"ADB: {last_err}")

    def _do(self, serial: str, action: str) -> None:
        if self.cfg.get("method") == "toggle_if_needed":
            st = self.client.playback_state(serial)
            want = STATE_PLAYING if action == "play" else STATE_PAUSED
            if st == want:
                return                                  # già nello stato voluto
            if st is not None:
                self.client.keyevent(serial, KEY_PLAY_PAUSE)
                return
            # stato non leggibile: ripiega sui tasti espliciti
        self.client.keyevent(serial, KEY_PLAY if action == "play" else KEY_PAUSE)

    def test_response(self, action: str) -> str:
        """Invia il comando e riporta se il player sembra averlo recepito (best effort)."""
        serial = self._resolve()
        self.client.keyevent(serial, KEY_PLAY if action == "play" else KEY_PAUSE)
        time.sleep(1.0)
        st = self.client.playback_state(serial)
        want = STATE_PLAYING if action == "play" else STATE_PAUSED
        if st is None:
            return "Comando inviato. Stato del player non leggibile: verifica a vista sul tablet."
        return "Il player ha recepito il comando." if st == want else \
            "Comando inviato ma il player NON è cambiato: l'app potrebbe ignorare i tasti (prova il metodo toggle_if_needed)."


# ------------------------------------------------------------------ PC
class PcMediaOutput(Output):
    """Play/Pausa espliciti sul player del browser tramite Windows System Media Transport Controls."""
    name, label = "pc_media", "Video sul PC"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._status = {"connected": False, "detail": "non verificato"}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def describe(self, action: str) -> str:
        flt = self.cfg.get("app_filter") or "sessione multimediale corrente"
        return f"Windows Media Session ({flt}): {action.upper()}"

    def _run(self, coro):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(coro)

    async def _session(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
        mgr = await M.request_async()
        flt = (self.cfg.get("app_filter") or "").strip().lower()
        if flt:
            for s in mgr.get_sessions():
                if flt in (s.source_app_user_model_id or "").lower():
                    return s
            return None
        cur = mgr.get_current_session()
        if cur is not None:
            return cur
        sessions = list(mgr.get_sessions())
        return sessions[0] if sessions else None

    async def _act(self, action: str) -> str:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as PS
        s = await self._session()
        if s is None:
            return "nosession"
        st = s.get_playback_info().playback_status
        if action == "play":
            if st == PS.PLAYING:
                return "already"
            ok = await s.try_play_async()
        else:
            if st in (PS.PAUSED, PS.STOPPED):
                return "already"
            ok = await s.try_pause_async()
        return "ok" if ok else "refused"

    def refresh(self) -> None:
        if sys.platform != "win32":
            self._status.update(connected=False, detail="solo Windows")
            return
        try:
            s = self._run(self._session())
            if s is None:
                self._status.update(connected=False, detail="nessun video/audio attivo nel browser")
            else:
                self._status.update(connected=True, detail=f"sessione: {s.source_app_user_model_id}")
        except Exception as exc:          # winrt mancante o errore WinRT
            self._status.update(connected=False, detail=f"controlli multimediali non disponibili ({type(exc).__name__})")

    def status(self) -> dict:
        return dict(self._status)

    def send(self, action: str) -> CommandResult:
        try:
            res = self._run(self._act(action))
        except Exception as exc:
            res = "error"
            err = f"{type(exc).__name__}: {exc}"
        else:
            err = ""
        if res in ("ok", "already"):
            self._status.update(connected=True)
            return CommandResult(time.time(), self.name, action, True,
                                 self.describe(action) + (" (già nello stato)" if res == "already" else ""))
        if res in ("nosession", "refused", "error") and self.cfg.get("fallback_media_key") and sys.platform == "win32":
            self._media_key()
            return CommandResult(time.time(), self.name, action, True, "tasto multimediale Play/Pausa (toggle di riserva)")
        why = {"nosession": "nessuna sessione multimediale (avvia il video nel browser)",
               "refused": "il player ha rifiutato il comando"}.get(res, err)
        self._status.update(connected=False, detail=why)
        return CommandResult(time.time(), self.name, action, False, why)

    @staticmethod
    def _media_key() -> None:
        import ctypes
        VK_MEDIA_PLAY_PAUSE, KEYUP = 0xB3, 0x0002
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYUP, 0)


# ------------------------------------------------------------------ dispatcher
class Dispatcher:
    """Un thread per uscita; coda con solo l'ultima azione pendente (niente raffiche)."""

    def __init__(self, outputs: list[Output], on_result: Callable[[CommandResult], None], poll_seconds: float = 6.0):
        self.outputs = {o.name: o for o in outputs}
        self._on_result = on_result
        self._q: dict[str, "queue.Queue[Optional[str]]"] = {n: queue.Queue() for n in self.outputs}
        self._stop = threading.Event()
        self._poll = poll_seconds
        self._threads = [threading.Thread(target=self._worker, args=(n,), daemon=True, name=f"out-{n}")
                         for n in self.outputs]
        for t in self._threads:
            t.start()

    def submit(self, name: str, action: str) -> None:
        q = self._q[name]
        try:
            while True:                       # tieni solo l'azione più recente
                q.get_nowait()
        except queue.Empty:
            pass
        q.put(action)

    def call(self, name: str, fn: Callable[[Output], object]) -> None:
        """Esegue `fn(output)` nel thread dell'uscita (per test manuali e refresh)."""
        self._q[name].put(fn)  # type: ignore[arg-type]

    def _worker(self, name: str) -> None:
        out = self.outputs[name]
        q = self._q[name]
        try:
            out.refresh()
        except Exception:
            pass
        while not self._stop.is_set():
            try:
                item = q.get(timeout=self._poll)
            except queue.Empty:
                try:
                    out.refresh()
                except Exception:
                    pass
                continue
            if item is None:
                break
            try:
                if callable(item):
                    item(out)
                else:
                    self._on_result(out.send(item))
            except Exception as exc:
                self._on_result(CommandResult(time.time(), name, str(item), False, f"{type(exc).__name__}: {exc}"))

    def stop(self) -> None:
        self._stop.set()
        for q in self._q.values():
            q.put(None)
        for t in self._threads:
            t.join(timeout=2)
        for o in self.outputs.values():
            try:
                o.close()
            except Exception:
                pass
