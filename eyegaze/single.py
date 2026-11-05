"""Una sola istanza: se il programma è già attivo (magari nascosto nell'area di notifica) lo riporta in primo piano."""
from __future__ import annotations

import socket
import sys
import threading
from typing import Callable

PORT = 47831          # solo localhost
MUTEX_NAME = "BreakFromAeyeMutex"
_mutex = None


def _hold_mutex() -> None:
    """Mutex con nome di Windows: l'installer lo usa (AppMutex) per sapere se il programma è in esecuzione."""
    global _mutex
    if sys.platform == "win32":
        try:
            import ctypes
            _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        except Exception:
            _mutex = None


def acquire(on_show: Callable[[], None], port: int = PORT) -> bool:
    """True = questa è l'unica istanza. False = ne esisteva già una, che è stata avvisata di mostrarsi."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        srv.bind(("127.0.0.1", port))
    except OSError:
        srv.close()
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.5) as c:
                c.sendall(b"show")
        except OSError:
            pass
        return False
    srv.listen(2)
    _hold_mutex()

    def loop() -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                try:
                    if conn.recv(16) == b"show":
                        on_show()
                except OSError:
                    pass

    threading.Thread(target=loop, daemon=True, name="single-instance").start()
    return True
