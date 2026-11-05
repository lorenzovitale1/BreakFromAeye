"""Avvio: `python -m eyegaze` (GUI) oppure con opzioni da riga di comando."""
from __future__ import annotations

import argparse
import os
import queue
import sys
import time

from . import __version__, config as cfgmod


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="eyegaze", description="Eye gaze -> Play/Pausa su tablet Android e/o video sul PC.")
    p.add_argument("--config", type=str, default=str(cfgmod.CONFIG_PATH), help="percorso di config.json")
    p.add_argument("--dry-run", action="store_true", help="mostra i comandi previsti senza inviarli")
    p.add_argument("--headless", action="store_true", help="senza finestra (stampa lo stato nel terminale)")
    p.add_argument("--simulate", nargs="?", const="demo", metavar="SCENARIO", help="esegue uno scenario finto in dry-run, senza webcam né tablet")
    p.add_argument("--list-devices", action="store_true", help="elenca i dispositivi ADB e termina")
    p.add_argument("--check-camera", action="store_true", help="prova la webcam (nessun fotogramma salvato) e termina")
    p.add_argument("--calibrate", action="store_true", help="avvia subito la calibrazione")
    p.add_argument("--setup", action="store_true", help="scarica i file mancanti (modello, adb) chiedendo conferma")
    p.add_argument("--minimized", action="store_true", help="parte nascosto nell'area di notifica")
    p.add_argument("--version", action="version", version=__version__)
    return p.parse_args(argv)


def cmd_list_devices(cfg) -> int:
    from .adb import AdbClient, AdbError
    c = AdbClient(cfg["outputs"]["tablet"]["adb_path"])
    if not c.locate():
        print("adb non trovato. Esegui setup.bat (o «eyegaze --setup») oppure indica il percorso in config.json (outputs.tablet.adb_path).")
        return 1
    try:
        devs = c.devices()
    except AdbError as exc:
        print(f"Errore ADB: {exc}")
        return 1
    print(f"adb: {c.adb}")
    for d in devs:
        print(f"  {d.serial:28} {d.state:12} {d.model}")
    if not devs:
        print("  nessun dispositivo. Abilita il debug wireless sul tablet e usa «Abbina…» nell'app (vedi README).")
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
        print(f"Webcam {cfg['camera']['index']} OK ({ok} frame in 3 s, nessun fotogramma salvato).")
        return 0
    print(f"Webcam {cfg['camera']['index']} NON utilizzabile: {last.detail if last else 'nessuna risposta'}")
    return 1


def cmd_headless(cfg) -> int:
    from .engine import Engine
    eng = Engine(cfg)
    if eng.model is None:
        print("Nessuna calibrazione: avvia prima l'app con la finestra (o --calibrate).")
        return 1
    eng.start()
    print("In esecuzione (Ctrl+C per uscire)." + ("  [dry-run]" if cfg["dry_run"] else ""))
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


def cmd_gui(cfg, calibrate: bool, session_dry_run: bool = False, minimized: bool = False) -> int:
    from .monitors import set_dpi_aware
    set_dpi_aware()
    from . import single
    show_cb: dict = {"fn": None}
    if not single.acquire(lambda: show_cb["fn"] and show_cb["fn"]()):
        print("Eye Gaze è già in esecuzione: ho riaperto la finestra esistente.")
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
        messagebox.showerror("Eye Gaze", f"Errore imprevisto:\n{type(exc).__name__}: {exc}\n\nDettagli in eyegaze.log")
        r.destroy()
    except Exception:
        pass


def main(argv=None) -> int:
    _ensure_streams()
    a = parse_args(argv)
    from pathlib import Path
    cfg = cfgmod.load(Path(a.config))
    if a.dry_run:
        cfg["dry_run"] = True
    if a.setup:
        from .assets import cli_setup
        return cli_setup()
    if a.simulate:
        from .simulate import SCENARIOS, run
        if a.simulate not in SCENARIOS:
            print(f"Scenario sconosciuto. Disponibili: {', '.join(SCENARIOS)}")
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
