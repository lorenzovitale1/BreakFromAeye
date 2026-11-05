"""Interfaccia Tkinter: stato, controllo uscite, calibrazione e editor delle impostazioni."""
from __future__ import annotations

import base64
import copy
import json
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Optional

from . import config as cfgmod
from . import APP_NAME, assets
from .adb import AdbError
from .calib_ui import CalibrationWindow
from .engine import Engine
from .calibration import keyboard_preset
from .monitors import monitor_options
from .tray import Tray
from .zone_ui import CornerWizard, ZoneEditDialog
from .outputs import AdbOutput, CommandResult
from .states import ACTION_LABELS, GazeState

C = dict(bg="#0f141b", card="#161d27", line="#243040", text="#e6edf3", muted="#8b98a8",
         accent="#4c8dff", ok="#3fb950", warn="#f0b429", bad="#f85149", idle="#6e7b8b")
STATE_COLOR = {GazeState.LOOKING_AT_PC: C["ok"], GazeState.LOOKING_AWAY: C["warn"], GazeState.UNKNOWN: C["idle"]}
F = "Segoe UI"
RESTART_PREFIXES = ("camera.", "show_preview")          # le uscite si ricostruiscono da sole, senza toccare la webcam
ACTION_UI = {"play": "PLAY", "pause": "PAUSA", "none": "nessuna azione"}


def setup_style(root: tk.Tk) -> None:
    s = ttk.Style(root)
    s.theme_use("clam")
    root.configure(bg=C["bg"])
    s.configure(".", background=C["bg"], foreground=C["text"], font=(F, 10), borderwidth=0, focuscolor=C["bg"])
    s.configure("Card.TFrame", background=C["card"])
    s.configure("TLabel", background=C["bg"], foreground=C["text"])
    s.configure("Card.TLabel", background=C["card"])
    s.configure("Muted.TLabel", foreground=C["muted"], font=(F, 9))
    s.configure("CardMuted.TLabel", background=C["card"], foreground=C["muted"], font=(F, 9))
    s.configure("H1.TLabel", font=(F, 16, "bold"))
    s.configure("H2.TLabel", background=C["card"], font=(F, 11, "bold"))
    s.configure("TButton", background=C["line"], foreground=C["text"], padding=(12, 6), relief="flat")
    s.map("TButton", background=[("active", "#2f3d52"), ("disabled", C["card"])], foreground=[("disabled", C["idle"])])
    s.configure("Accent.TButton", background=C["accent"], foreground="white", font=(F, 10, "bold"))
    s.map("Accent.TButton", background=[("active", "#6aa0ff")])
    s.configure("Danger.TButton", background="#3a1f24", foreground="#ff9a93")
    s.map("Danger.TButton", background=[("active", "#52262d")])
    s.configure("TNotebook", background=C["bg"], tabmargins=(0, 0, 0, 0), bordercolor=C["bg"], lightcolor=C["bg"], darkcolor=C["bg"])
    s.configure("TNotebook.Tab", background=C["bg"], foreground=C["muted"], padding=(18, 8), font=(F, 10, "bold"), bordercolor=C["bg"], lightcolor=C["bg"], darkcolor=C["bg"])
    s.map("TNotebook.Tab", foreground=[("selected", C["text"])], background=[("selected", C["bg"])])
    s.configure("TCheckbutton", background=C["card"], foreground=C["text"])
    s.map("TCheckbutton", background=[("active", C["card"])])
    s.configure("TCombobox", fieldbackground=C["line"], background=C["line"], foreground=C["text"], arrowcolor=C["text"])
    s.map("TCombobox", fieldbackground=[("readonly", C["line"])], foreground=[("readonly", C["text"])])
    s.configure("TEntry", fieldbackground=C["line"], foreground=C["text"], insertcolor=C["text"])
    s.configure("TSpinbox", fieldbackground=C["line"], foreground=C["text"], arrowcolor=C["text"])
    s.configure("Horizontal.TScale", background=C["card"], troughcolor=C["line"])
    s.configure("Horizontal.TProgressbar", background=C["accent"], troughcolor=C["line"], thickness=8)
    s.configure("Vertical.TScrollbar", background=C["line"], troughcolor=C["bg"], arrowcolor=C["muted"])
    s.configure("Mode.Toolbutton", background=C["line"], foreground=C["text"], padding=(14, 7), relief="flat", font=(F, 10, "bold"))
    s.map("Mode.Toolbutton", background=[("selected", C["accent"]), ("active", "#2f3d52")], foreground=[("selected", "white")])
    s.configure("Treeview", background=C["line"], fieldbackground=C["line"], foreground=C["text"], rowheight=26, borderwidth=0)
    s.map("Treeview", background=[("selected", C["accent"])])
    s.configure("Treeview.Heading", background=C["card"], foreground=C["muted"], font=(F, 9, "bold"), relief="flat")
    root.option_add("*TCombobox*Listbox.background", C["line"])
    root.option_add("*TCombobox*Listbox.foreground", C["text"])


def card(parent, title: str = "", **grid) -> ttk.Frame:
    f = ttk.Frame(parent, style="Card.TFrame", padding=14)
    if title:
        ttk.Label(f, text=title, style="H2.TLabel").pack(anchor="w", pady=(0, 8))
    return f


class App:
    def __init__(self, engine: Engine, log_queue: "queue.Queue[str]", session_dry_run: bool = False,
                 start_hidden: bool = False):
        self.engine = engine
        self.session_dry_run = session_dry_run   # --dry-run da riga di comando: vale solo per questa esecuzione, non va su config.json
        self.log_q = log_queue
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("900x800")
        self.root.minsize(860, 700)
        setup_style(self.root)
        self.vars: dict[str, tuple[tk.Variable, dict]] = {}
        self._photo = None
        self.ui_q: "queue.Queue[Callable[[], None]]" = queue.Queue()   # Tk non e thread-safe: i thread passano da qui
        self.visible = True
        self._notified_hidden = False
        self._calib_was_visible = True
        self._draw_mode = False
        self._draw_start = self._draw_cur = None
        self._zone_sig = None
        self._zgeom = (0.0, 0.0, 1.0, 1.0)
        post = self.ui_q.put
        self.tray = Tray({"show": lambda: post(self.show_window), "pause": lambda: post(self.toggle_pause),
                          "mode": lambda m: post(lambda: self.set_mode(m)), "calibrate": lambda: post(self.calibrate),
                          "quit": lambda: post(self.quit)}, self.current_mode, lambda: self.engine.paused)
        self.tray_ok = self.tray.start()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_button)
        self.root.after(100, self.refresh)
        if start_hidden and self.tray_ok:
            self.root.after(30, self.hide_window)
        self.root.after(700, self._startup_checks)

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=(18, 14, 18, 6))
        top.pack(fill="x")
        ttk.Label(top, text=f"👁  {APP_NAME}", style="H1.TLabel").pack(side="left")
        self.pill = tk.Label(top, text="", bg=C["bg"], fg=C["warn"], font=(F, 9, "bold"))
        self.pill.pack(side="left", padx=12)
        ttk.Button(top, text="Esci", style="Danger.TButton", command=self.quit).pack(side="right")
        ttk.Button(top, text="✕ Chiudi", command=self.on_close_button).pack(side="right", padx=8)
        ttk.Button(top, text="🎯 Ricalibra", command=self.calibrate).pack(side="right", padx=8)
        self.pause_btn = ttk.Button(top, text="⏸ Pausa", width=12, command=self.toggle_pause)
        self.pause_btn.pack(side="right")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        self.tab_state, self.tab_zones = ttk.Frame(nb, padding=8), ttk.Frame(nb, padding=8)
        self.tab_set, self.tab_log = ttk.Frame(nb), ttk.Frame(nb, padding=8)
        nb.add(self.tab_state, text="Stato")
        nb.add(self.tab_zones, text="Aree sicure")
        nb.add(self.tab_set, text="Impostazioni")
        nb.add(self.tab_log, text="Registro")
        self._build_state()
        self._build_zones()
        self._build_settings()
        self._build_log()

    def _build_state(self) -> None:
        t = self.tab_state
        t.columnconfigure(0, weight=1, uniform="c")
        t.columnconfigure(1, weight=1, uniform="c")
        bar = ttk.Frame(t, style="Card.TFrame", padding=(14, 10))
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(bar, text="Cosa controllare:", style="H2.TLabel").pack(side="left")
        self.mode_var = tk.StringVar(value=self.current_mode())
        for val, text in (("tablet", "📱 Tablet"), ("pc", "🖥 Video sul PC"), ("both", "📱 + 🖥 Entrambi")):
            ttk.Radiobutton(bar, text=text, value=val, variable=self.mode_var, style="Mode.Toolbutton",
                            command=lambda: self.set_mode(self.mode_var.get())).pack(side="left", padx=(10, 0))
        left = card(t)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 12))
        self.dot = tk.Canvas(left, width=96, height=96, bg=C["card"], highlightthickness=0)
        self.dot.pack(pady=(4, 0))
        self.dot_item = self.dot.create_oval(8, 8, 88, 88, fill=C["idle"], outline="")
        self.state_lbl = ttk.Label(left, text="…", style="Card.TLabel", font=(F, 20, "bold"))
        self.state_lbl.pack(pady=(6, 2))
        self.prog_lbl = ttk.Label(left, text=" ", style="CardMuted.TLabel")
        self.prog_lbl.pack()
        self.prog = ttk.Progressbar(left, maximum=1.0, length=240)
        self.prog.pack(pady=(4, 8))
        self.msg_lbl = ttk.Label(left, text="", style="CardMuted.TLabel", wraplength=320, justify="center")
        self.msg_lbl.pack(pady=(0, 6))
        ttk.Label(left, text="Area da monitorare (schermi)", style="CardMuted.TLabel").pack(pady=(4, 0))
        self.area_var = tk.StringVar()
        self.area_cb = ttk.Combobox(left, textvariable=self.area_var, state="readonly", width=36)
        self.area_cb.pack(pady=(2, 6))
        self.area_cb.bind("<<ComboboxSelected>>", self._area_chosen)
        self._sync_area_cb()
        ttk.Label(left, text="Mappa dello sguardo (rettangolo = schermo)", style="CardMuted.TLabel").pack()
        self.map = tk.Canvas(left, width=280, height=170, bg="#0b0e14", highlightthickness=1, highlightbackground=C["line"])
        self.map.pack(pady=4)
        self.preview_lbl = tk.Label(left, bg=C["card"])
        self.preview_lbl.pack()

        right = ttk.Frame(t)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        # --- tablet
        self.tab_card = card(right, "📱 Tablet Android")
        self.tab_card.pack(fill="x", pady=(0, 12))
        self.tab_status = ttk.Label(self.tab_card, text="", style="Card.TLabel", wraplength=330, justify="left")
        self.tab_status.pack(anchor="w")
        self.tab_last = ttk.Label(self.tab_card, text="", style="CardMuted.TLabel", wraplength=330, justify="left")
        self.tab_last.pack(anchor="w", pady=(2, 8))
        self.dev_var = tk.StringVar()
        self.dev_cb = ttk.Combobox(self.tab_card, textvariable=self.dev_var, state="readonly", values=[])
        self.dev_cb.pack(fill="x")
        self.dev_cb.bind("<<ComboboxSelected>>", self._device_chosen)
        self.devices: list = []
        r1 = ttk.Frame(self.tab_card, style="Card.TFrame")
        r1.pack(fill="x", pady=(8, 0))
        ttk.Button(r1, text="Aggiorna", command=self.refresh_devices).pack(side="left")
        ttk.Button(r1, text="Connetti IP…", command=self.connect_dialog).pack(side="left", padx=6)
        ttk.Button(r1, text="Abbina…", command=self.pair_dialog).pack(side="left")
        r2 = ttk.Frame(self.tab_card, style="Card.TFrame")
        r2.pack(fill="x", pady=(8, 0))
        ttk.Button(r2, text="▶ Test PLAY", command=lambda: self.test("tablet", "play")).pack(side="left")
        ttk.Button(r2, text="⏸ Test PAUSA", command=lambda: self.test("tablet", "pause")).pack(side="left", padx=6)
        # --- pc
        self.pc_card = card(right, "🖥  Video sul PC (YouTube…)")
        self.pc_card.pack(fill="x")
        self.pc_status = ttk.Label(self.pc_card, text="", style="Card.TLabel", wraplength=330, justify="left")
        self.pc_status.pack(anchor="w")
        self.pc_last = ttk.Label(self.pc_card, text="", style="CardMuted.TLabel", wraplength=330, justify="left")
        self.pc_last.pack(anchor="w", pady=(2, 8))
        r3 = ttk.Frame(self.pc_card, style="Card.TFrame")
        r3.pack(fill="x")
        ttk.Button(r3, text="▶ Test PLAY", command=lambda: self.test("pc_media", "play")).pack(side="left")
        ttk.Button(r3, text="⏸ Test PAUSA", command=lambda: self.test("pc_media", "pause")).pack(side="left", padx=6)
        self.test_lbl = ttk.Label(right, text="", style="Muted.TLabel", wraplength=360, justify="left")
        self.test_lbl.pack(anchor="w", pady=(10, 0))

    def _build_log(self) -> None:
        self.log = tk.Text(self.tab_log, bg=C["card"], fg=C["text"], relief="flat", state="disabled",
                           font=("Consolas", 10), wrap="word", padx=10, pady=8)
        self.log.pack(fill="both", expand=True)

    def _build_settings(self) -> None:
        outer = self.tab_set
        bar = ttk.Frame(outer, padding=(8, 8, 8, 4))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Salva e applica", style="Accent.TButton", command=self.save_settings).pack(side="left")
        ttk.Button(bar, text="Annulla modifiche", command=self.load_settings_into_form).pack(side="left", padx=8)
        ttk.Button(bar, text="Ripristina predefiniti", command=lambda: self.load_settings_into_form(cfgmod.DEFAULTS)).pack(side="left")
        self.set_msg = ttk.Label(bar, text="", style="Muted.TLabel")
        self.set_msg.pack(side="left", padx=12)

        cv = tk.Canvas(outer, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(cv)
        win = cv.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta / 120), "units") if str(self.root.focus_get()).find("combobox") < 0 else None)

        section, holder = None, None
        for meta in cfgmod.SETTINGS:
            if meta["section"] != section:
                section = meta["section"]
                holder = card(body, section)
                holder.pack(fill="x", padx=8, pady=6)
            self._setting_row(holder, meta)
        self.load_settings_into_form()

    def _setting_row(self, parent, meta: dict) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=5)
        row.columnconfigure(1, weight=1)
        t = meta["type"]
        ttk.Label(row, text=meta["label"], style="Card.TLabel", font=(F, 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(row, text=meta["help"], style="CardMuted.TLabel", wraplength=560, justify="left").grid(row=1, column=0, columnspan=3, sticky="w")
        if t == "float":
            var = tk.DoubleVar()
            vlabel = ttk.Label(row, text="", style="Card.TLabel", width=8, anchor="e")
            step = meta["step"]

            def on_change(_v=None, var=var, vlabel=vlabel, step=step, unit=meta.get("unit", "")):
                val = round(round(var.get() / step) * step, 4)
                var.set(val)
                vlabel.configure(text=f"{val:g} {unit}".strip())

            ttk.Scale(row, from_=meta["min"], to=meta["max"], variable=var, command=on_change).grid(row=0, column=1, sticky="ew", padx=12)
            vlabel.grid(row=0, column=2, sticky="e")
            var._cb = on_change  # type: ignore[attr-defined]
        elif meta.get("widget") == "monitor":
            var = tk.StringVar()
            self._monitor_cb = ttk.Combobox(row, textvariable=var, state="readonly", width=30,
                                            values=[lbl for _, lbl in monitor_options()])
            self._monitor_cb.grid(row=0, column=2, sticky="e")
        elif t == "int":
            var = tk.IntVar()
            ttk.Spinbox(row, from_=meta["min"], to=meta["max"], textvariable=var, width=8).grid(row=0, column=2, sticky="e")
        elif t == "bool":
            var = tk.BooleanVar()
            ttk.Checkbutton(row, variable=var, text="Attivo").grid(row=0, column=2, sticky="e")
        elif t == "choice":
            var = tk.StringVar()
            ttk.Combobox(row, textvariable=var, values=list(self._labels_for(meta).values()), state="readonly",
                         width=28 if meta.get("labels") else 16).grid(row=0, column=2, sticky="e")
        else:
            var = tk.StringVar()
            ttk.Entry(row, textvariable=var, width=26).grid(row=0, column=2, sticky="e")
        self.vars[meta["path"]] = (var, meta)

    # ------------------------------------------------------------ impostazioni
    def load_settings_into_form(self, cfg: Optional[dict] = None) -> None:
        cfg = cfg or self.engine.cfg
        for path, (var, meta) in self.vars.items():
            val = cfgmod.get_path(cfg, path)
            if meta.get("widget") == "monitor":
                val = self._monitor_label(val)
            elif meta["type"] == "choice":
                val = self._labels_for(meta).get(str(val), str(val))
            var.set(val if meta["type"] != "choice" else str(val))
            cb = getattr(var, "_cb", None)
            if cb:
                cb()
        self.set_msg.configure(text="")

    def collect_form(self) -> dict:
        cfg = copy.deepcopy(self.engine.cfg)
        for path, (var, meta) in self.vars.items():
            try:
                val: Any = var.get()
            except tk.TclError:
                continue
            if meta.get("widget") == "monitor":
                val = self._monitor_value(val)
            elif meta["type"] == "choice":
                val = {lab: k for k, lab in self._labels_for(meta).items()}.get(val, val)
            cfgmod.set_path(cfg, path, val)
        return cfgmod.validate(cfg)

    def save_settings(self) -> None:
        new = self.collect_form()
        old = self.engine.cfg
        changed = [p for p in self.vars if cfgmod.get_path(new, p) != cfgmod.get_path(old, p)]
        try:
            self._persist(new)
        except OSError as exc:
            messagebox.showerror("Salvataggio", f"Impossibile scrivere config.json:\n{exc}")
            return
        restart = any(p.startswith(RESTART_PREFIXES) for p in changed)
        self.engine.apply_config(new, restart)
        note = "Salvato e applicato." if changed else "Nessuna modifica."
        if "calibration.monitor" in changed and self.engine.model is None:
            note += " Area senza calibrazione: premi «Ricalibra»."
        self.set_msg.configure(text=note)
        self.load_settings_into_form()
        self._sync_area_cb()

    # ------------------------------------------------------------ area monitorata
    @staticmethod
    def _monitor_label(value) -> str:
        key = cfgmod.calibration_key(value)
        return next((lbl for v, lbl in monitor_options() if v == key), "Tutti i monitor" if key == "all" else str(value))

    @staticmethod
    def _monitor_value(label: str) -> str:
        return next((v for v, lbl in monitor_options() if lbl == label), "all")

    def _sync_area_cb(self) -> None:
        opts = monitor_options()
        self.area_cb.configure(values=[lbl for _, lbl in opts])
        self.area_var.set(self._monitor_label(self.engine.cfg["calibration"]["monitor"]))
        self.area_cb.state(["!disabled"] if len(opts) > 1 else ["disabled"])

    def _area_chosen(self, _e=None) -> None:
        value = self._monitor_value(self.area_var.get())
        cfg = copy.deepcopy(self.engine.cfg)
        cfgmod.set_path(cfg, "calibration.monitor", value)
        try:
            self._persist(cfg)
        except OSError as exc:
            messagebox.showerror("Salvataggio", f"Impossibile scrivere config.json:\n{exc}")
            return
        self.engine.apply_config(cfg, False)
        self.load_settings_into_form()
        if self.engine.model is None:
            if messagebox.askyesno("Calibrazione", "Per questa area non c'è ancora una calibrazione.\n\nAvviarla ora?"):
                self.calibrate()
        else:
            self.test_lbl.configure(text="Area cambiata: uso la calibrazione già salvata per questa area.")

    def _persist(self, cfg: dict) -> None:
        out = copy.deepcopy(cfg)
        if self.session_dry_run and out["dry_run"]:
            out["dry_run"] = False
        cfgmod.save(out)

    # ------------------------------------------------------------ azioni
    def toggle_pause(self) -> None:
        self.engine.set_paused(not self.engine.paused)

    def calibrate(self) -> None:
        if self.engine.snapshot()["calibrating"]:
            return
        self._calib_was_visible = self.visible
        self.root.withdraw()
        self.root.after(250, lambda: CalibrationWindow(self.root, self.engine, self._calib_done))

    def _calib_done(self, ok: bool, msg: str) -> None:
        if self._calib_was_visible:
            self.show_window()
        self.test_lbl.configure(text=msg)
        self.log_q.put(msg)
        if not ok:
            messagebox.showinfo("Calibrazione", msg)

    def _startup_checks(self) -> None:
        """All'avvio: modello mancante -> proponi il download; poi, se serve, la prima calibrazione."""
        if not self.visible:
            return
        if not cfgmod.find_model().exists():
            self._offer_model_download(then=self._offer_first_calibration)
        else:
            self._offer_first_calibration()

    def _offer_model_download(self, then: Callable[[], None]) -> None:
        if not messagebox.askyesno(
                "Modello di rilevamento",
                "Serve il modello del volto MediaPipe (face_landmarker.task, circa 4 MB, scaricato da storage.googleapis.com — Google).\n"
                "Si scarica una sola volta; le immagini della webcam restano sempre sul tuo PC.\n\nScaricarlo ora?"):
            then()
            return
        self.test_lbl.configure(text="Download del modello in corso…")

        def done(_res, err):
            if err:
                messagebox.showerror("Download", f"Download non riuscito:\n{err}")
            else:
                self.test_lbl.configure(text="Modello scaricato.")
                self.engine.restart()
            then()
        self.bg(assets.ensure_model, done)

    def _offer_adb_download(self) -> None:
        if not messagebox.askyesno(
                "adb non trovato",
                "Per controllare il tablet serve adb (Android platform-tools, circa 8 MB, scaricato da dl.google.com — Google).\n\nScaricarlo ora?"):
            return
        self.test_lbl.configure(text="Download di adb in corso…")

        def done(_res, err):
            if err:
                messagebox.showerror("Download", f"Download non riuscito:\n{err}")
                return
            out = self._tablet_out()
            if out:
                out.client.adb = None                  # forza una nuova ricerca
            self.engine.restart()
            self.test_lbl.configure(text="adb installato. Ora abbina il tablet con «Abbina…».")
        self.bg(assets.install_adb, done)

    def _offer_first_calibration(self) -> None:
        if self.engine.model is not None:
            return
        if not self.visible:
            return
        if messagebox.askyesno("Prima calibrazione",
                               "Per riconoscere quando guardi lo schermo serve una breve calibrazione (circa 30 secondi).\n\nAvviarla ora?"):
            self.calibrate()

    def _tablet_out(self) -> Optional[AdbOutput]:
        d = self.engine.dispatcher
        o = d.outputs.get("tablet") if d else None
        o = getattr(o, "inner", o)
        return o if isinstance(o, AdbOutput) else None

    def bg(self, fn: Callable[[], Any], done: Callable[[Any, Optional[Exception]], None]) -> None:
        def run():
            try:
                res, err = fn(), None
            except Exception as exc:
                res, err = None, exc
            self.ui_q.put(lambda: done(res, err))
        threading.Thread(target=run, daemon=True).start()

    def refresh_devices(self) -> None:
        out = self._tablet_out()
        if not out:
            self.test_lbl.configure(text="Abilita «Controlla il tablet» nelle Impostazioni.")
            return

        def done(devs, err):
            if err:
                self.test_lbl.configure(text=f"ADB: {err}")
                if "adb non trovato" in str(err):
                    self._offer_adb_download()
                return
            self.devices = devs
            self.dev_cb.configure(values=[f"{d.label} · {d.state}" for d in devs])
            if devs:
                cur = next((i for i, d in enumerate(devs) if d.serial == out.serial), 0 if len(devs) == 1 else -1)
                if cur >= 0:
                    self.dev_cb.current(cur)
                    out.select(devs[cur].serial)
            self.test_lbl.configure(text=f"{len(devs)} dispositivo/i trovato/i." if devs else "Nessun dispositivo: usa «Abbina…» / «Connetti IP…».")

        self.bg(out.client.devices, done)

    def _device_chosen(self, _e=None) -> None:
        i = self.dev_cb.current()
        out = self._tablet_out()
        if out and 0 <= i < len(self.devices):
            out.select(self.devices[i].serial)
            self.engine.cfg["outputs"]["tablet"]["serial"] = self.devices[i].serial
            try:
                self._persist(self.engine.cfg)
            except OSError:
                pass
            self.test_lbl.configure(text=f"Selezionato: {self.devices[i].label}")

    def _ask(self, title: str, fields: list[tuple[str, bool]], action: Callable[..., str]) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=C["bg"], padx=18, pady=16)
        dlg.transient(self.root)
        entries = []
        for label, secret in fields:
            ttk.Label(dlg, text=label).pack(anchor="w")
            e = ttk.Entry(dlg, width=34, show="•" if secret else "")
            e.pack(pady=(2, 10))
            entries.append(e)
        info = ttk.Label(dlg, text="", style="Muted.TLabel", wraplength=300)
        info.pack(anchor="w")

        def go():
            vals = [e.get().strip() for e in entries]
            info.configure(text="Attendi…")
            self.bg(lambda: action(*vals), lambda r, err: (info.configure(text=str(err) if err else r),
                                                           (dlg.after(900, dlg.destroy), self.refresh_devices()) if not err else None))
        ttk.Button(dlg, text="OK", style="Accent.TButton", command=go).pack(anchor="e", pady=(8, 0))
        entries[0].focus_set()

    def connect_dialog(self) -> None:
        out = self._tablet_out()
        if out:
            self._ask("Connetti via Wi-Fi", [("IP:porta di connessione (es. 192.168.1.50:41234)", False)],
                      lambda hp: (out.client.connect(hp), "Connesso")[1])

    def pair_dialog(self) -> None:
        out = self._tablet_out()
        if out:
            self._ask("Abbina tablet (Debug wireless)",
                      [("IP:porta di PAIRING (schermata «Abbina con codice»)", False), ("Codice di abbinamento", True)],
                      lambda hp, code: out.client.pair(hp, code))

    def test(self, name: str, action: str) -> None:
        d = self.engine.dispatcher
        if not d or name not in d.outputs:
            self.test_lbl.configure(text="Uscita disattivata: abilitala nelle Impostazioni.")
            return
        self.test_lbl.configure(text=f"Test {ACTION_LABELS[action]} in corso…")

        def job(out):
            if isinstance(out, AdbOutput):
                try:
                    msg = out.test_response(action)
                    res = CommandResult(time.time(), name, action, True, msg)
                except AdbError as exc:
                    res = CommandResult(time.time(), name, action, False, f"ADB: {exc}")
            else:
                res = out.send(action)
            self.engine._on_result(res)
            msg = ("DRY-RUN attivo: il comando NON è stato inviato. Chiudi e avvia con start.bat per inviarlo davvero."
                   if res.dry_run else res.message)
            self.ui_q.put(lambda: self.test_lbl.configure(text=msg))
        d.call(name, job)

    # ------------------------------------------------------------ finestra / area di notifica
    def close_action(self) -> str:
        return self.engine.cfg["ui"]["close_action"] if self.tray_ok else "quit"

    def on_close_button(self) -> None:
        if self.close_action() == "tray":
            self.hide_window()
        else:
            self.quit()

    def hide_window(self) -> None:
        self.root.withdraw()
        self.visible = False
        if not self._notified_hidden:
            self._notified_hidden = True
            self.tray.notify("Il programma continua a funzionare in background. Clic sull'icona per riaprire la finestra.")

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.visible = True

    def request_show(self) -> None:
        self.ui_q.put(self.show_window)             # chiamabile da altri thread (seconda istanza)

    def quit(self) -> None:
        try:
            self.tray.stop()
            self.engine.stop()
        finally:
            self.root.destroy()

    close = quit

    # ------------------------------------------------------------ cosa controllare (tablet / PC / entrambi)
    def current_mode(self) -> str:
        o = self.engine.cfg["outputs"]
        t, p = o["tablet"]["enabled"], o["pc_media"]["enabled"]
        return "both" if t and p else "tablet" if t else "pc" if p else "none"

    def set_mode(self, mode: str) -> None:
        cfg = copy.deepcopy(self.engine.cfg)
        cfg["outputs"]["tablet"]["enabled"] = mode in ("tablet", "both")
        cfg["outputs"]["pc_media"]["enabled"] = mode in ("pc", "both")
        try:
            self._persist(cfg)
        except OSError as exc:
            messagebox.showerror("Salvataggio", f"Impossibile scrivere config.json:\n{exc}")
        self.engine.apply_config(cfg, False)         # ricostruisce solo le uscite, la webcam non si ferma
        self.mode_var.set(self.current_mode())
        self.load_settings_into_form()

    @staticmethod
    def _labels_for(meta: dict) -> dict:
        lab = dict(meta.get("labels") or {})
        if not lab and all(str(c) in ACTION_UI for c in meta["choices"]):
            lab = dict(ACTION_UI)
        return {str(c): lab.get(str(c), str(c)) for c in meta["choices"]}

    # ------------------------------------------------------------ aree sicure
    def _build_zones(self) -> None:
        t = self.tab_zones
        t.columnconfigure(1, weight=1)
        left = card(t, "Aree sicure")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        ttk.Label(left, text="Guardare un'area sicura (per esempio la tastiera mentre scrivi) NON conta come «guardi altrove», "
                             "anche se è fuori dallo schermo.", style="CardMuted.TLabel", wraplength=300, justify="left").pack(anchor="w")
        self.zone_area_lbl = ttk.Label(left, text="", style="CardMuted.TLabel")
        self.zone_area_lbl.pack(anchor="w", pady=(6, 4))
        self.zone_tree = ttk.Treeview(left, columns=("name", "on"), show="headings", height=7, selectmode="browse")
        self.zone_tree.heading("name", text="Nome")
        self.zone_tree.heading("on", text="Stato")
        self.zone_tree.column("name", width=190)
        self.zone_tree.column("on", width=70, anchor="center")
        self.zone_tree.pack(fill="x")
        ttk.Button(left, text="＋ Guarda i 4 angoli…", style="Accent.TButton", command=self.zone_wizard).pack(fill="x", pady=(10, 4))
        ttk.Button(left, text="✏ Disegna sulla mappa", command=self.zone_draw_mode).pack(fill="x", pady=2)
        ttk.Button(left, text="＋ Tastiera (stima)", command=lambda: self._zone_add(keyboard_preset())).pack(fill="x", pady=2)
        r = ttk.Frame(left, style="Card.TFrame")
        r.pack(fill="x", pady=(8, 0))
        ttk.Button(r, text="Modifica…", command=self.zone_edit).pack(side="left")
        ttk.Button(r, text="On/Off", command=self.zone_toggle).pack(side="left", padx=6)
        ttk.Button(r, text="Elimina", command=self.zone_delete).pack(side="left")
        right = card(t, "Mappa dello sguardo")
        right.grid(row=0, column=1, sticky="nsew")
        self.zmap = tk.Canvas(right, width=440, height=320, bg="#0b0e14", highlightthickness=1, highlightbackground=C["line"])
        self.zmap.pack()
        self.zmap.bind("<ButtonPress-1>", self._z_press)
        self.zmap.bind("<B1-Motion>", self._z_drag)
        self.zmap.bind("<ButtonRelease-1>", self._z_release)
        self.zone_hint = ttk.Label(right, text="Blu = schermo · giallo = aree sicure · pallino = dove guardi ora.",
                                   style="CardMuted.TLabel", wraplength=430, justify="left")
        self.zone_hint.pack(anchor="w", pady=(8, 0))

    def _refresh_zone_list(self) -> None:
        zones = self.engine.current_zones()
        sig = json.dumps(zones, sort_keys=True) + self.engine.cfg["calibration"]["monitor"]
        if sig == self._zone_sig:
            return
        self._zone_sig = sig
        self.zone_tree.delete(*self.zone_tree.get_children())
        for i, z in enumerate(zones):
            self.zone_tree.insert("", "end", iid=str(i), values=(z["name"], "attiva" if z["enabled"] else "off"))
        self.zone_area_lbl.configure(text=f"Per l'area: {self._monitor_label(self.engine.cfg['calibration']['monitor'])}")

    def _save_zones(self, zones: list) -> None:
        cfg = copy.deepcopy(self.engine.cfg)
        cfg.setdefault("safe_zones", {})[cfgmod.calibration_key(cfg["calibration"]["monitor"])] = zones
        cfg = cfgmod.validate(cfg)
        try:
            self._persist(cfg)
        except OSError as exc:
            messagebox.showerror("Salvataggio", f"Impossibile scrivere config.json:\n{exc}")
        self.engine.apply_config(cfg, False)
        self._refresh_zone_list()

    def _zone_add(self, zone: dict) -> None:
        self._save_zones(list(self.engine.current_zones()) + [zone])

    def _selected_zone(self) -> Optional[int]:
        sel = self.zone_tree.selection()
        return int(sel[0]) if sel else None

    def zone_wizard(self) -> None:
        if self.engine.model is None:
            messagebox.showinfo("Aree sicure", "Prima calibra lo schermo (pulsante «Ricalibra»).")
            return
        n = len(self.engine.current_zones()) + 1
        CornerWizard(self.root, self.engine, lambda z: (self._zone_add(z) if z else None), f"Area sicura {n}")

    def zone_draw_mode(self) -> None:
        self._draw_mode = True
        self.zone_hint.configure(text="Trascina sulla mappa per disegnare il rettangolo dell'area sicura.")

    def zone_edit(self) -> None:
        i = self._selected_zone()
        zones = list(self.engine.current_zones())
        if i is None or i >= len(zones):
            return

        def done(z, i=i):
            zones[i] = z
            self._save_zones(zones)
        ZoneEditDialog(self.root, zones[i], done)

    def zone_toggle(self) -> None:
        i = self._selected_zone()
        zones = [dict(z) for z in self.engine.current_zones()]
        if i is not None and i < len(zones):
            zones[i]["enabled"] = not zones[i]["enabled"]
            self._save_zones(zones)
            self.zone_tree.selection_set(str(i))

    def zone_delete(self) -> None:
        i = self._selected_zone()
        zones = list(self.engine.current_zones())
        if i is not None and i < len(zones):
            del zones[i]
            self._save_zones(zones)

    def _zxy(self, e) -> tuple[float, float]:
        x0, y0, sw, sh = self._zgeom
        return (e.x - x0) / sw, (e.y - y0) / sh

    def _z_press(self, e) -> None:
        if self._draw_mode:
            self._draw_start = self._draw_cur = self._zxy(e)

    def _z_drag(self, e) -> None:
        if self._draw_start:
            self._draw_cur = self._zxy(e)

    def _z_release(self, e) -> None:
        if not self._draw_start:
            return
        (ax, ay), (bx, by) = self._draw_start, self._zxy(e)
        self._draw_start = self._draw_cur = None
        self._draw_mode = False
        self.zone_hint.configure(text="Blu = schermo · giallo = aree sicure · pallino = dove guardi ora.")
        if abs(bx - ax) < 0.03 or abs(by - ay) < 0.03:
            return
        zone = {"name": f"Area sicura {len(self.engine.current_zones()) + 1}", "enabled": True,
                "x0": min(ax, bx), "y0": min(ay, by), "x1": max(ax, bx), "y1": max(ay, by)}
        ZoneEditDialog(self.root, zone, self._zone_add, "Nuova area sicura")

    # ------------------------------------------------------------ aggiornamento periodico
    def refresh(self) -> None:
        s = self.engine.snapshot()
        col = STATE_COLOR[s["state"]]
        self.dot.itemconfigure(self.dot_item, fill=col)
        self.state_lbl.configure(text=s["label"], foreground=col)
        self.tray.update(col, s["label"] + (" · in pausa" if s["paused"] else "") + (" · DRY-RUN" if s["dry_run"] else ""),
                         (self.current_mode(), s["paused"]))
        if self.mode_var.get() != self.current_mode():
            self.mode_var.set(self.current_mode())
        self._refresh_zone_list()
        self.pill.configure(text=("DRY-RUN (nessun invio)" if s["dry_run"] else ""))
        self.pause_btn.configure(text="▶ Riprendi" if s["paused"] else "⏸ Pausa")
        if s["paused"]:
            self.prog_lbl.configure(text="Automazione in pausa")
            self.prog["value"] = 0
        elif s["progress_target"] is not None:
            what = "«guardi altrove»" if s["progress_target"] == GazeState.LOOKING_AWAY else "«guardi il PC»"
            self.prog_lbl.configure(text=f"Verso {what}…")
            self.prog["value"] = s["progress"]
        else:
            self.prog_lbl.configure(text=" ")
            self.prog["value"] = 0
        self.msg_lbl.configure(text=s["message"], foreground=C["bad"] if (not s["camera_ok"] or "mancante" in s["message"]) else C["muted"])
        self._draw_map(self.map, s, 280, 170, 130)
        self._draw_map(self.zmap, s, 440, 320, 200)
        for n, lbl, last in (("tablet", self.tab_status, self.tab_last), ("pc_media", self.pc_status, self.pc_last)):
            o = s["outputs"].get(n)
            if o is None:
                lbl.configure(text="⚪ Disattivato", foreground=C["idle"])
                last.configure(text="Abilitalo in Impostazioni.")
                continue
            ok = o.get("connected")
            name = o.get("model") or o.get("serial") or ""
            lbl.configure(text=("🟢 Connesso" if ok else "🔴 Scollegato") + (f" · {name}" if name and n == "tablet" else "")
                          + (f"\n{o['detail']}" if o.get("detail") else ""), foreground=C["ok"] if ok else C["bad"])
            r = o.get("last")
            if r is None:
                last.configure(text="Ultimo comando: nessuno")
            else:
                st = "dry-run" if r.dry_run else ("OK" if r.ok else "ERRORE")
                last.configure(text=f"Ultimo comando: {ACTION_LABELS.get(r.action, r.action)} · {st} · {time.strftime('%H:%M:%S', time.localtime(r.ts))}"
                               + ("" if r.ok else f"\n{r.message}"))
        self._preview(s)
        self._drain_log()
        try:
            while True:
                self.ui_q.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(100, self.refresh)

    def _draw_map(self, cv: tk.Canvas, s: dict, W: int, H: int, sw: int) -> None:
        cv.delete("all")
        sh = sw * 9 / 16
        x0, y0 = (W - sw) / 2, 16
        if cv is self.zmap:
            self._zgeom = (x0, y0, sw, sh)
        for z in s["zones"]:
            col = C["warn"] if z["enabled"] else C["idle"]
            cv.create_rectangle(x0 + z["x0"] * sw, y0 + z["y0"] * sh, x0 + z["x1"] * sw, y0 + z["y1"] * sh, outline=col,
                                width=3 if (s["safe_hit"] and z["enabled"]) else 1, dash=(5, 3))
            if cv is self.zmap:
                cv.create_text(x0 + z["x0"] * sw + 6, y0 + z["y0"] * sh + 6, text=z["name"], anchor="nw", fill=col, font=(F, 9))
        if cv is self.zmap and self._draw_start and self._draw_cur:
            (ax, ay), (bx, by) = self._draw_start, self._draw_cur
            cv.create_rectangle(x0 + ax * sw, y0 + ay * sh, x0 + bx * sw, y0 + by * sh, outline=C["ok"], width=2)
        m = s["margin"]
        cv.create_rectangle(x0 - m * sw, y0 - m * sh, x0 + sw * (1 + m), y0 + sh * (1 + m), outline=C["line"], dash=(3, 3))
        cv.create_rectangle(x0, y0, x0 + sw, y0 + sh, outline=C["accent"], width=2)
        g = s["gaze"]
        if g:
            gx = min(max(x0 + g[0] * sw, 4), W - 4)
            gy = min(max(y0 + g[1] * sh, 4), H - 4)
            cv.create_oval(gx - 6, gy - 6, gx + 6, gy + 6, fill=STATE_COLOR[s["state"]], outline="")

    def _preview(self, s: dict) -> None:
        if not self.engine.cfg["show_preview"] or s["preview"] is None:
            if self._photo is not None:
                self.preview_lbl.configure(image="")
                self._photo = None
            return
        import cv2
        ok, buf = cv2.imencode(".png", s["preview"])
        if ok:
            self._photo = tk.PhotoImage(data=base64.b64encode(buf.tobytes()))
            self.preview_lbl.configure(image=self._photo)

    def _drain_log(self) -> None:
        lines = []
        try:
            while True:
                lines.append(self.log_q.get_nowait())
        except queue.Empty:
            pass
        if lines:
            self.log.configure(state="normal")
            self.log.insert("end", "\n".join(lines) + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()
