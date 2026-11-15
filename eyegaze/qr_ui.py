"""Finestra «Abbina con QR»: mostra il codice, attende il tablet, abbina e collega."""
from __future__ import annotations

import base64
import io
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .adb import AdbClient, AdbError
from .qrpair import QrPairing, qr_image

BG, FG, MUTED, OK, BAD = "#0f141b", "#e6edf3", "#8b98a8", "#3fb950", "#f85149"
F = "Segoe UI"
TIMEOUT = 120.0


class QrPairDialog:
    def __init__(self, root: tk.Tk, client: AdbClient, post: Callable[[Callable[[], None]], None],
                 on_success: Callable[[], None]):
        """`post(fn)` esegue `fn` nel thread della GUI (Tk non è thread-safe)."""
        self.client, self.post, self.on_success = client, post, on_success
        self.cancel = threading.Event()
        self.pairing = QrPairing(client)
        self.t0 = time.monotonic()
        self.finished = False

        self.win = tk.Toplevel(root)
        self.win.title("Abbina il tablet con codice QR")
        self.win.configure(bg=BG, padx=24, pady=18)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        tk.Label(self.win, bg=BG, fg=FG, font=(F, 14, "bold"), text="Abbina con codice QR").pack(anchor="w")
        tk.Label(self.win, bg=BG, fg=MUTED, font=(F, 10), justify="left", wraplength=360,
                 text="Sul tablet: Impostazioni → Opzioni sviluppatore → Debug wireless → «Abbina dispositivo con codice QR», "
                      "poi inquadra questo codice. Tablet e PC devono essere sulla stessa rete Wi-Fi.").pack(anchor="w", pady=(6, 10))
        buf = io.BytesIO()
        qr_image(self.pairing.payload).save(buf, format="PNG")
        self.photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        tk.Label(self.win, image=self.photo, bg="white", bd=0).pack(pady=(0, 10))
        self.status = tk.Label(self.win, bg=BG, fg=FG, font=(F, 10, "bold"), text="Avvio…", wraplength=360, justify="left")
        self.status.pack(anchor="w")
        self.bar = ttk.Progressbar(self.win, maximum=TIMEOUT, length=360)
        self.bar.pack(pady=(8, 10))
        self.btn = ttk.Button(self.win, text="Annulla", command=self.close)
        self.btn.pack(anchor="e")
        threading.Thread(target=self._work, daemon=True, name="qr-pairing").start()
        self._tick()

    def _set(self, text: str, color: str = FG) -> None:
        self.post(lambda: self.status.winfo_exists() and self.status.configure(text=text, fg=color))

    def _work(self) -> None:
        try:
            msg = self.pairing.run(self.cancel, self._set, TIMEOUT)
            self.finished = True
            self._set("✔ " + msg, OK)
            self.post(lambda: (self.on_success(), self.win.winfo_exists() and self.win.after(2500, self.close)))
        except AdbError as exc:
            self.finished = True
            if not self.cancel.is_set():
                self._set(f"✖ {exc}", BAD)
                self.post(lambda: self.btn.winfo_exists() and self.btn.configure(text="Chiudi"))
        except Exception as exc:       # errore imprevisto: mai bloccare la GUI
            self.finished = True
            self._set(f"✖ {type(exc).__name__}: {exc}", BAD)

    def _tick(self) -> None:
        if self.win.winfo_exists() and not self.finished:
            self.bar["value"] = time.monotonic() - self.t0
            self.win.after(500, self._tick)

    def close(self) -> None:
        self.cancel.set()
        if self.win.winfo_exists():
            self.win.destroy()
