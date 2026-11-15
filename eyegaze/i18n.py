"""Traduzioni (italiano / inglese).

La chiave di ogni traduzione è il testo italiano (lingua di partenza): `tr("Guardi il PC")` restituisce l'italiano, oppure l'inglese
se la lingua attiva è "en" e in `locale_en.EN` esiste la voce. Per i testi con variabili si usano segnaposto con nome:
`tr("Trovati {n} dispositivi", n=3)`. Una voce mancante ricade sull'italiano; il test `tests/test_i18n.py` verifica che non ne manchi nessuna."""
from __future__ import annotations

import locale
import sys

LANGS = ("it", "en")
_current = "it"


def detect_system_language() -> str:
    """Lingua dell'interfaccia di Windows (italiano → "it", qualsiasi altra → "en")."""
    try:
        if sys.platform == "win32":
            import ctypes
            return "it" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x10 else "en"   # 0x10 = LANG_ITALIAN
        return "it" if (locale.getlocale()[0] or "").lower().startswith("it") else "en"
    except Exception:
        return "en"


def resolve(setting: str) -> str:
    return setting if setting in LANGS else detect_system_language()


def set_language(setting: str) -> str:
    """Imposta la lingua attiva: "it", "en" oppure "auto" (= lingua di Windows). Ritorna quella effettiva."""
    global _current
    _current = resolve(setting)
    return _current


def current() -> str:
    return _current


def tr(msg: str, **kw) -> str:
    s = msg
    if _current == "en":
        from .locale_en import EN
        s = EN.get(msg, msg)
    return s.format(**kw) if kw else s
