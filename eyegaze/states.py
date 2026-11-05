"""Tipi condivisi: osservazioni per frame e stati stabili."""
from __future__ import annotations

from enum import Enum


class Obs(str, Enum):
    """Osservazione istantanea (un frame)."""
    AT = "at"                # sguardo sullo schermo
    AWAY = "away"            # sguardo altrove (o volto assente, se configurato)
    NONE = "none"            # nessuna informazione utile (ammiccamento, frame scartato)
    CAMERA_FAIL = "camera"   # webcam scollegata / bloccata / senza immagine


class GazeState(str, Enum):
    """Stato stabile mostrato all'utente."""
    LOOKING_AT_PC = "LOOKING_AT_PC"
    LOOKING_AWAY = "LOOKING_AWAY"
    UNKNOWN = "UNKNOWN"


STATE_LABELS = {
    GazeState.LOOKING_AT_PC: "Guardi il PC",
    GazeState.LOOKING_AWAY: "Guardi altrove",
    GazeState.UNKNOWN: "Sguardo incerto",
}

ACTIONS = ("play", "pause", "none")
ACTION_LABELS = {"play": "PLAY", "pause": "PAUSA", "none": "nessuno"}
