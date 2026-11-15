"""Avvio: `python -m eyegaze` (GUI) oppure con opzioni da riga di comando."""
from __future__ import annotations

import argparse
import os
import queue
import sys
import time

from . import __version__, config as cfgmod, i18n
from .i18n import tr


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="breakfromaeye", description=tr("BreakFromAeye: se distogli lo sguardo dal PC parte il video (tablet Android e/o PC)."))
    p.add_argument("--config", type=str, default=str(cfgmod.CONFIG_PATH), help=tr("percorso di config.json"))
    p.add_argument("--dry-run", action="store_true", help=tr("mostra i comandi previsti senza inviarli"))
    p.add_argument("--headless", action="store_true", help=tr("senza finestra (stampa lo stato nel terminale)"))
    p.add_argument("--simulate", nargs="?", const="demo", metavar="SCENARIO", help=tr("esegue uno scenario finto in dry-run, senza webcam né tablet"))
    p.add_argument("--list-devices", action="store_true", help=tr("elenca i dispositivi ADB e termina"))
    p.add_argument("--check-camera", action="store_true", help=tr("prova la webcam (nessun fotogramma salvato) e termina"))
    p.add_argument("--calibrate", action="store_true", help=tr("avvia subito la calibrazione"))
    p.add_argument("--selftest", action="store_true", help=tr("controlla che le librerie, il modello e adb siano utilizzabili"))
    p.add_argument("--setup", action="store_true", help=tr("scarica i file mancanti (modello, adb) chiedendo conferma"))
    p.add_argument("--minimized", action="store_true", help=tr("parte nascosto nell'area di notifica"))
    p.add_argument("--version", action="version", version=__version__)
    return p.parse_args(argv)


def cmd_list_devices(cfg) -> int:
    from .adb import AdbClient, AdbError
    c = AdbClient(cfg["outputs"]["tablet"]["adb_path"])
    if not c.locate():
        print(tr("adb non trovato. Esegui setup.bat (o «breakfromaeye --setup») oppure indica il percorso in config.json (outputs.tablet.adb_path)."))
        return 1
    try:
        devs = c.devices()
    except AdbError as exc:
        print(tr('Errore ADB: {exc}', exc=exc))
        return 1
    print(tr('adb: {adb}', adb=c.adb))
    for d in devs:
        print(f"  {d.serial:28} {d.state:12} {d.model}")
    if not devs:
        print(tr("  nessun dispositivo. Abilita il debug wireless sul tablet e usa «Abbina…» nell'app (vedi README)."))
    return 0


def cmd_check_camera(cfg) -> int:
    from .capture import FrameSource
    src = FrameSource(cfg["camera"])
    ok = 0
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < 3:
        r = src.next()
        if r.kind != "camera_fail":
            ok += 1
        last = r
        time.sleep(0.03)
    src.close()
    if ok:
        print(tr('Webcam {v} OK ({ok} frame in 3 s, nessun fotogramma salvato).', v=cfg['camera']['index'], ok=ok))
        return 0
    print(tr('Webcam {v} NON utilizzabile: {v2}', v=cfg['camera']['index'], v2=last.detail if last else tr('nessuna risposta')))
    return 1


def cmd_headless(cfg) -> int:
    from .engine import Engine
    eng = Engine(cfg)
    if eng.model is None:
        print(tr("Nessuna calibrazione: avvia prima l'app con la finestra (o --calibrate)."))
        return 1
    eng.start()
    print(tr("In esecuzione (Ctrl+C per uscire).") + (tr("  [dry-run]") if cfg["dry_run"] else ""))
    last = None
    try:
        while True:
            s = eng.snapshot()
            line = f"{s['label']}" + (f" · {s['message']}" if s["message"] else "")
            if line != last:
                print(time.strftime("%H:%M:%S"), line)
                last = line
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        eng.stop()
    return 0


def cmd_selftest() -> int:
    """Verifica dell'installazione (usata anche per provare l'eseguibile creato da PyInstaller)."""
    results: list[tuple[str, bool, str]] = []

    def check(name, fn):
        try:
            results.append((name, True, str(fn() or "")))
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))

    def detector():
        import numpy as np
        from .capture import FaceDetector
        d = FaceDetector()
        r = d.detect(np.zeros((480, 640, 3), np.uint8))
        d.close()
        return tr('modello caricato; frame vuoto -> {r}', r=r)

    def media_session():
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager  # noqa: F401
        return "ok"

    def tray():
        from . import tray as t
        assert t.AVAILABLE, tr("pystray/Pillow non disponibili")
        return "ok"

    def tk():
        import tkinter, tkinter.ttk  # noqa: F401,E401
        return "ok"

    def qr():
        from .qrpair import qr_image
        return f"QR {qr_image('WIFI:T:ADB;S:x;P:y;;').size[0]} px"

    def languages():
        previous = i18n.current()
        try:
            i18n.set_language("en")
            ok = i18n.tr("Guardi il PC") == "Looking at the PC"
        finally:
            i18n.set_language(previous)
        assert ok, "English translations not available"
        return "it/en"

    def adb():
        from .adb import find_adb
        p = find_adb()
        assert p, tr("adb non trovato")
        return p

    for name, fn in ((tr("rilevatore MediaPipe"), detector), (tr("controlli multimediali Windows"), media_session),
                     (tr("icona area di notifica"), tray), (tr("Tkinter"), tk), (tr("codice QR"), qr), ("languages", languages), ("adb", adb)):
        check(name, fn)
    print(tr('BreakFromAeye {version__} · dati in {ROOT}', version__=__version__, ROOT=cfgmod.ROOT))
    for name, ok, info in results:
        print(f"[{'OK' if ok else 'ERRORE'}] {name}: {info}")
    return 0 if all(ok for _, ok, _ in results) else 1


def cmd_gui(cfg, calibrate: bool, session_dry_run: bool = False, minimized: bool = False) -> int:
    from .monitors import set_dpi_aware
    set_dpi_aware()
    from . import single
    show_cb: dict = {"fn": None}
    if not single.acquire(lambda: show_cb["fn"] and show_cb["fn"]()):
        print(tr("BreakFromAeye è già in esecuzione: ho riaperto la finestra esistente."))
        return 0
    from .engine import Engine
    from .gui import App
    q: "queue.Queue[str]" = queue.Queue()
    eng = Engine(cfg, printer=lambda m: (print(m), q.put(m)))
    eng.start()
    app = App(eng, q, session_dry_run, start_hidden=minimized or cfg["ui"]["start_minimized"])
    show_cb["fn"] = app.request_show
    if calibrate:
        app.root.after(500, app.calibrate)
    app.run()
    return 0


def _ensure_streams() -> None:
    """Con pythonw (nessuna finestra di comando) stdout/stderr non esistono: li invio a eyegaze.log."""
    if sys.stdout is None or sys.stderr is None:
        try:
            log = open(cfgmod.ROOT / "eyegaze.log", "a", encoding="utf-8", buffering=1)
        except OSError:
            log = open(os.devnull, "w")
        if sys.stdout is None:
            sys.stdout = log
        if sys.stderr is None:
            sys.stderr = log


def _fatal(exc: BaseException) -> None:
    import traceback
    traceback.print_exc()
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("BreakFromAeye", tr('Errore imprevisto:\n{name__}: {exc}\n\nDettagli in eyegaze.log', name__=type(exc).__name__, exc=exc))
        r.destroy()
    except Exception:
        pass


def main(argv=None) -> int:
    _ensure_streams()
    i18n.set_language("auto")                      # testi dell'aiuto nella lingua di Windows
    a = parse_args(argv)
    from pathlib import Path
    cfg = cfgmod.load(Path(a.config))
    i18n.set_language(cfg["ui"]["language"])
    if a.dry_run:
        cfg["dry_run"] = True
    if a.selftest:
        return cmd_selftest()
    if a.setup:
        from .assets import cli_setup
        return cli_setup()
    if a.simulate:
        from .simulate import SCENARIOS, run
        if a.simulate not in SCENARIOS:
            print(tr('Scenario sconosciuto. Disponibili: {join}', join=', '.join(SCENARIOS)))
            return 2
        print("\n".join(run(a.simulate, cfg)))
        return 0
    if a.list_devices:
        return cmd_list_devices(cfg)
    if a.check_camera:
        return cmd_check_camera(cfg)
    if a.headless:
        return cmd_headless(cfg)
    try:
        return cmd_gui(cfg, a.calibrate, a.dry_run, a.minimized)
    except Exception as exc:
        _fatal(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
