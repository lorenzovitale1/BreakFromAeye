"""Abbinamento del tablet con codice QR (Debug wireless → "Abbina dispositivo con codice QR").

Come funziona (lo stesso meccanismo di Android Studio): il PC genera un nome e una password casuali e li mostra in un QR
`WIFI:T:ADB;S:<nome>;P:<password>;;`. Inquadrandolo, il tablet pubblica in rete (mDNS) un servizio di abbinamento con quel nome.
Il PC lo trova con `adb mdns services` e completa `adb pair <ip:porta> <password>`; poi collega il dispositivo.
La password vale solo per questa sessione e non viene mai scritta nei log o nei messaggi d'errore."""
from __future__ import annotations

import secrets
import string
import threading
import time
from typing import Callable, Optional

from .adb import AdbClient, AdbError
from .i18n import tr

_LOWER = string.ascii_lowercase + string.digits
_ALNUM = string.ascii_letters + string.digits


def new_credentials() -> tuple[str, str]:
    """(nome del servizio, password): casuali e non riutilizzabili."""
    return "bfa-" + "".join(secrets.choice(_LOWER) for _ in range(8)), "".join(secrets.choice(_ALNUM) for _ in range(12))


def qr_payload(name: str, password: str) -> str:
    return f"WIFI:T:ADB;S:{name};P:{password};;"


def qr_image(payload: str, box_size: int = 8):
    """Immagine PIL del QR (nero su bianco, margine incluso: si legge bene anche su interfaccia scura)."""
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=3)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").get_image().convert("RGB")


class QrPairing:
    def __init__(self, client: AdbClient, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.client, self._sleep, self._clock = client, sleep, clock
        self.name, self._password = new_credentials()

    @property
    def payload(self) -> str:
        return qr_payload(self.name, self._password)

    def run(self, cancel: threading.Event, on_status: Callable[[str], None] = lambda s: None,
            timeout: float = 120.0, connect_wait: float = 20.0) -> str:
        """Attende il tablet, abbina e collega. Ritorna un messaggio di esito; solleva AdbError se non riesce o se annullato."""
        if not self.client.mdns_ok():
            on_status(tr("Preparo la ricerca dei dispositivi in rete…"))
            self.client.enable_openscreen_mdns()
            if not self.client.mdns_ok():
                raise AdbError(tr("adb non riesce a cercare dispositivi in rete (mDNS non disponibile): usa «Abbina…» con il codice a 6 cifre."))
        on_status(tr("In attesa che il tablet inquadri il codice…"))
        deadline = self._clock() + timeout
        svc = None
        while svc is None:
            if cancel.is_set():
                raise AdbError("annullato")
            if self._clock() > deadline:
                raise AdbError(tr("tempo scaduto: il tablet non ha inquadrato il codice (stessa rete Wi-Fi del PC?)."))
            svc = next((s for s in self.client.mdns_services() if s.kind == "pairing" and s.name.lower() == self.name.lower()), None)
            if svc is None:
                self._sleep(1.0)
        on_status(tr("Tablet trovato: abbinamento in corso…"))
        self.client.pair(svc.hostport, self._password)
        on_status(tr("Abbinato. Connessione al tablet…"))
        host = svc.hostport.rsplit(":", 1)[0]
        end = self._clock() + connect_wait
        while self._clock() < end and not cancel.is_set():
            ready = [d for d in self.client.devices() if d.ready]
            match = next((d for d in ready if host in d.serial or "_adb-tls-connect" in d.serial), None)
            if match:
                return tr('Abbinato e connesso: {label}', label=match.label)
            conn = next((s for s in self.client.mdns_services() if s.kind == "connect" and s.hostport.rsplit(":", 1)[0] == host), None)
            if conn:
                try:
                    self.client.connect(conn.hostport)
                except AdbError:
                    pass
            self._sleep(1.0)
        return tr("Abbinamento riuscito. Premi «Aggiorna» e scegli il tablet; se non compare, usa «Connetti IP…».")
