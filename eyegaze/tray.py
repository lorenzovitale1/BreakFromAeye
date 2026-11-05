"""Icona nell'area di notifica (la freccia ^ accanto all'orologio). Opzionale: richiede pystray + Pillow."""
from __future__ import annotations

from typing import Callable

try:
    import pystray
    from PIL import Image, ImageDraw
    AVAILABLE = True
except Exception:          # librerie mancanti: l'app funziona, ma senza icona (la X chiude il programma)
    AVAILABLE = False


def make_icon(color: str, size: int = 64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, size - 2, size - 2), fill="#0f141b", outline=color, width=4)
    d.ellipse((13, 21, size - 13, size - 21), fill="white")
    c, r = size / 2, 9
    d.ellipse((c - r, c - r, c + r, c + r), fill=color)
    return img


class Tray:
    """`handlers`: show, pause, mode(str), calibrate, quit. Vengono chiamati dal thread della tray:
    chi li fornisce deve passare il lavoro al thread della GUI."""

    def __init__(self, handlers: dict[str, Callable], get_mode: Callable[[], str], get_paused: Callable[[], bool]):
        self._h, self._mode, self._paused = handlers, get_mode, get_paused
        self._color = "#6e7b8b"
        self._last = None
        self.icon = None

    def start(self) -> bool:
        if not AVAILABLE:
            return False
        h = self._h
        radio = lambda label, key: pystray.MenuItem(                       # noqa: E731
            label, lambda icon, item: h["mode"](key), checked=lambda item: self._mode() == key, radio=True)
        menu = pystray.Menu(
            pystray.MenuItem("Apri finestra", lambda icon, item: h["show"](), default=True),
            pystray.MenuItem(lambda item: "Riprendi automazione" if self._paused() else "Pausa automazione",
                             lambda icon, item: h["pause"]()),
            pystray.MenuItem("Controlla", pystray.Menu(radio("Tablet", "tablet"), radio("Video sul PC", "pc"),
                                                       radio("Entrambi", "both"))),
            pystray.MenuItem("Ricalibra", lambda icon, item: h["calibrate"]()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Esci", lambda icon, item: h["quit"]()))
        try:
            self.icon = pystray.Icon("eyegaze", make_icon(self._color), "Eye Gaze → Play/Pausa", menu)
            self.icon.run_detached()
        except Exception:
            self.icon = None
            return False
        return True

    def update(self, color: str, tooltip: str, sig: tuple = ()) -> None:
        """Aggiorna icona/tooltip/menu solo se qualcosa è cambiato (`sig`: stato che influenza il menu)."""
        key = (color, tooltip, sig)
        if self.icon is None or key == self._last:
            return
        self._last = key
        try:
            if color != self._color:
                self._color = color
                self.icon.icon = make_icon(color)
            self.icon.title = tooltip[:120]
            self.icon.update_menu()
        except Exception:
            pass

    def notify(self, message: str, title: str = "Eye Gaze") -> None:
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
