"""Aree sicure: procedura guidata a 4 angoli (con bip, perché guardando fuori dallo schermo non si vedono i punti)
e finestra di modifica manuale."""
from __future__ import annotations

import math
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from .calibration import zone_from_corners
from .engine import Engine

BG, FG, MUTED, ACCENT, OK, WARN = "#0f141b", "#e6edf3", "#8b98a8", "#4c8dff", "#3fb950", "#f0b429"
F = "Segoe UI"
CORNERS = ["IN ALTO a SINISTRA", "IN ALTO a DESTRA", "IN BASSO a DESTRA", "IN BASSO a SINISTRA"]
FIRST_PREP, PREP, CAPTURE = 4.0, 3.0, 1.6      # secondi


def beep(root: tk.Misc, kind: str) -> None:
    """Segnale acustico (non bloccante): 'start' = un bip acuto, 'end' = due bip bassi."""
    try:
        import winsound
        seq = [(1400, 220)] if kind == "start" else [(700, 130), (700, 130)]
        threading.Thread(target=lambda: [winsound.Beep(f, d) for f, d in seq], daemon=True).start()
    except Exception:
        root.bell()


class CornerWizard:
    def __init__(self, root: tk.Tk, engine: Engine, on_done: Callable[[Optional[dict]], None], default_name: str):
        self.root, self.engine, self.on_done, self.default_name = root, engine, on_done, default_name
        self.win = tk.Toplevel(root)
        self.win.title("Nuova area sicura")
        self.win.configure(bg=BG, padx=24, pady=20)
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.cancel)
        self.title = tk.Label(self.win, bg=BG, fg=FG, font=(F, 15, "bold"), text="Nuova area sicura")
        self.title.pack(anchor="w")
        self.text = tk.Label(self.win, bg=BG, fg=MUTED, font=(F, 11), justify="left", wraplength=470)
        self.text.pack(anchor="w", pady=(8, 10))
        self.big = tk.Label(self.win, bg=BG, fg=ACCENT, font=(F, 40, "bold"), text="")
        self.big.pack()
        self.bar = ttk.Progressbar(self.win, maximum=1.0, length=470)
        self.bar.pack(pady=(6, 12))
        self.name_var = tk.StringVar(value=default_name)
        self.entry = ttk.Entry(self.win, textvariable=self.name_var, width=34)
        self.row = ttk.Frame(self.win)
        self.row.pack(fill="x")
        self.btn = ttk.Button(self.row, text="Inizia", style="Accent.TButton", command=self.start)
        self.btn.pack(side="right")
        self.cancel_btn = ttk.Button(self.row, text="Annulla", command=self.cancel)
        self.cancel_btn.pack(side="right", padx=8)
        self.corners: list[list] = []
        self.idx = 0
        self.phase, self.t0 = "intro", 0.0
        self.zone: Optional[dict] = None
        self.text.configure(text=("Guarda uno alla volta i 4 angoli dell'area che vuoi rendere sicura (per esempio la tastiera), "
                                  "nell'ordine: alto-sinistra, alto-destra, basso-destra, basso-sinistra.\n\n"
                                  "Per ogni angolo parte un conto alla rovescia. Al BIP ACUTO guarda quell'angolo e tieni fermo lo sguardo "
                                  "finché senti DUE BIP BASSI. Tieni il volto visibile alla webcam e la testa nella posizione abituale."))

    # ------------------------------------------------------------------
    def start(self) -> None:
        self.engine.begin_zone_capture()               # durante la registrazione nessun comando viene inviato
        self.btn.pack_forget()
        self.phase, self.t0, self.idx, self.corners = "prep", time.monotonic(), 0, []
        self.tick()

    def tick(self) -> None:
        if not self.win.winfo_exists():
            return
        el = time.monotonic() - self.t0
        if self.phase == "prep":
            dur = FIRST_PREP if self.idx == 0 else PREP
            left = max(0.0, dur - el)
            self.title.configure(text=f"Angolo {self.idx + 1} di 4")
            self.text.configure(text=f"Preparati a guardare l'angolo {CORNERS[self.idx]} dell'area.")
            self.big.configure(text=str(math.ceil(left)) if left > 0 else "•", fg=WARN)
            self.bar["value"] = el / dur
            if el >= dur:
                beep(self.root, "start")
                self.engine.zone_collect(True)
                self.phase, self.t0 = "capture", time.monotonic()
        elif self.phase == "capture":
            self.text.configure(text=f"Guarda ORA l'angolo {CORNERS[self.idx]} e tieni fermo lo sguardo…")
            self.big.configure(text="👁", fg=OK)
            self.bar["value"] = el / CAPTURE
            if el >= CAPTURE:
                self.corners.append(self.engine.zone_collect(False))
                beep(self.root, "end")
                self.idx += 1
                if self.idx >= 4:
                    self.finish()
                    return
                self.phase, self.t0 = "prep", time.monotonic()
        self.win.after(50, self.tick)

    def finish(self) -> None:
        self.engine.end_zone_capture()
        try:
            self.zone = zone_from_corners(self.corners, name=self.default_name)
        except ValueError as exc:
            self.phase = "error"
            self.title.configure(text="Non riuscito")
            self.text.configure(text=f"{exc}\n\nRiprova: dopo il bip acuto tieni lo sguardo sull'angolo e la testa ferma.")
            self.big.configure(text="")
            self.btn.configure(text="Riprova", command=self.restart)
            self.btn.pack(side="right")
            return
        self.phase = "name"
        z = self.zone
        self.title.configure(text="Area registrata")
        self.text.configure(text="Dai un nome all'area. Potrai modificarla o disattivarla in qualsiasi momento.")
        self.big.configure(text="✔", fg=OK)
        self.bar["value"] = 1.0
        self.entry.pack(before=self.row, pady=(0, 10))
        self.entry.focus_set()
        self.btn.configure(text="Salva", command=self.save)
        self.btn.pack(side="right")
        self.cancel_btn.configure(text="Scarta")

    def restart(self) -> None:
        self.btn.pack_forget()
        self.start()

    def save(self) -> None:
        if self.zone is not None:
            self.zone["name"] = (self.name_var.get().strip() or self.default_name)[:40]
        self.close(self.zone)

    def cancel(self) -> None:
        self.close(None)

    def close(self, zone: Optional[dict]) -> None:
        self.engine.end_zone_capture()
        if self.win.winfo_exists():
            self.win.destroy()
        self.on_done(zone)


class ZoneEditDialog:
    """Modifica manuale: nome e coordinate nel sistema dello schermo (0..1 = schermo; >1 = sotto/destra; <0 = sopra/sinistra)."""

    def __init__(self, root: tk.Tk, zone: Optional[dict], on_done: Callable[[dict], None], title: str = "Modifica area sicura"):
        self.on_done = on_done
        self.win = tk.Toplevel(root)
        self.win.title(title)
        self.win.configure(bg=BG, padx=20, pady=16)
        self.win.transient(root)
        z = zone or {"name": "Area sicura", "enabled": True, "x0": 0.0, "y0": 1.15, "x1": 1.0, "y1": 1.9}
        self.enabled = z.get("enabled", True)
        self.vars = {k: tk.StringVar(value=(z[k] if k == "name" else f"{z[k]:.2f}")) for k in ("name", "x0", "y0", "x1", "y1")}
        tk.Label(self.win, bg=BG, fg=MUTED, font=(F, 9), justify="left", wraplength=360,
                 text="Coordinate rispetto allo schermo calibrato: 0 = bordo sinistro/alto, 1 = bordo destro/basso. "
                      "Esempio tastiera: x da 0.1 a 0.9, y da 1.15 a 1.8 (sotto lo schermo).").pack(anchor="w", pady=(0, 10))
        grid = ttk.Frame(self.win)
        grid.pack(fill="x")
        for r, (key, label) in enumerate([("name", "Nome"), ("x0", "Sinistra (x min)"), ("x1", "Destra (x max)"),
                                          ("y0", "Alto (y min)"), ("y1", "Basso (y max)")]):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(grid, textvariable=self.vars[key], width=22).grid(row=r, column=1, padx=(12, 0), pady=3)
        self.err = tk.Label(self.win, bg=BG, fg="#f85149", font=(F, 9))
        self.err.pack(anchor="w", pady=(8, 0))
        row = ttk.Frame(self.win)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Salva", style="Accent.TButton", command=self.save).pack(side="right")
        ttk.Button(row, text="Annulla", command=self.win.destroy).pack(side="right", padx=8)

    def save(self) -> None:
        try:
            x0, x1 = sorted((float(self.vars["x0"].get().replace(",", ".")), float(self.vars["x1"].get().replace(",", "."))))
            y0, y1 = sorted((float(self.vars["y0"].get().replace(",", ".")), float(self.vars["y1"].get().replace(",", "."))))
        except ValueError:
            self.err.configure(text="Inserisci numeri (es. 0.25).")
            return
        if x1 - x0 < 0.02 or y1 - y0 < 0.02:
            self.err.configure(text="L'area è troppo piccola.")
            return
        zone = {"name": (self.vars["name"].get().strip() or "Area sicura")[:40], "enabled": self.enabled,
                "x0": x0, "y0": y0, "x1": x1, "y1": y1}
        self.win.destroy()
        self.on_done(zone)
