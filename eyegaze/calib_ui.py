"""Calibrazione a 9 punti a tutto schermo (sull'area scelta: un monitor o tutti)."""
from __future__ import annotations

import math
import time
import tkinter as tk
from typing import Callable

from .calibration import calibration_grid
from .engine import Engine
from .monitors import Rect, calibration_rect


class CalibrationWindow:
    def __init__(self, root: tk.Tk, engine: Engine, on_done: Callable[[bool, str], None]):
        self.engine, self.on_done = engine, on_done
        cfg = engine.cfg["calibration"]
        self.settle, self.sample = cfg["settle_seconds"], cfg["sample_seconds"]
        fallback = Rect(0, 0, root.winfo_screenwidth(), root.winfo_screenheight(), True)
        self.rect = calibration_rect(cfg["monitor"], fallback)
        self.points = calibration_grid()
        self.samples: list = []
        self.idx = -1
        self.phase = "intro"
        self.t0 = time.monotonic()

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry(f"{self.rect.w}x{self.rect.h}+{self.rect.x}+{self.rect.y}")
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#0b0e14")
        self.cv = tk.Canvas(self.win, bg="#0b0e14", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.win.bind("<Escape>", lambda e: self.finish(False, "Calibrazione annullata."))
        self.win.focus_force()
        engine.begin_calibration()
        self.tick()

    def pos(self, p):
        return self.rect.w * p[0], self.rect.h * p[1]

    def tick(self):
        if not self.win.winfo_exists():
            return
        now = time.monotonic() - self.t0
        cv = self.cv
        cv.delete("all")
        w, h = self.rect.w, self.rect.h
        if self.phase == "intro":
            cv.create_text(w / 2, h / 2 - 40, text="Calibrazione", fill="#e6edf3", font=("Segoe UI", 28, "bold"))
            cv.create_text(w / 2, h / 2 + 20, fill="#9aa7b4", font=("Segoe UI", 15), justify="center",
                           text="Siediti nella posizione abituale e tieni la testa naturale.\n"
                                "Segui il punto con lo SGUARDO: guardalo finché non si sposta.\n\n"
                                "Esc per annullare")
            if now > 3.5:
                self.next_point()
        else:
            x, y = self.pos(self.points[self.idx])
            r = 16 + 5 * math.sin(now * 6)
            sampling = self.phase == "sample"
            color = "#3fb950" if sampling else "#f0b429"
            cv.create_oval(x - r - 12, y - r - 12, x + r + 12, y + r + 12, outline=color, width=2)
            cv.create_oval(x - 7, y - 7, x + 7, y + 7, fill=color, outline="")
            cv.create_text(w / 2, 40, fill="#9aa7b4", font=("Segoe UI", 13),
                           text=f"Punto {self.idx + 1} di {len(self.points)}   ·   Esc per annullare")
            if self.phase == "settle" and now >= self.settle:
                self.phase, self.t0 = "sample", time.monotonic()
                self.engine.calib_collect(True)
            elif sampling and now >= self.sample:
                vecs = self.engine.calib_collect(False)
                self.samples.append((self.points[self.idx], vecs))
                self.next_point()
        if self.win.winfo_exists():
            self.win.after(33, self.tick)

    def next_point(self):
        self.idx += 1
        if self.idx >= len(self.points):
            self.complete()
            return
        self.phase, self.t0 = "settle", time.monotonic()

    def complete(self):
        area = {"x": self.rect.x, "y": self.rect.y, "w": self.rect.w, "h": self.rect.h,
                "monitor": self.engine.cfg["calibration"]["monitor"]}
        try:
            model = self.engine.finish_calibration(self.samples, area)
        except ValueError as exc:
            self.finish(False, str(exc))
            return
        q = "buona" if model.rmse < 0.12 else "media" if model.rmse < 0.22 else "scarsa"
        msg = f"Calibrazione completata (qualità {q}, errore {model.rmse:.2f})."
        if model.rmse >= 0.22:
            msg += " Riprova stando più fermo e con buona luce frontale."
        self.finish(True, msg, already_finished=True)

    def finish(self, ok: bool, msg: str, already_finished: bool = False):
        if not already_finished:
            self.engine.cancel_calibration()
        if self.win.winfo_exists():
            self.win.destroy()
        self.on_done(ok, msg)
