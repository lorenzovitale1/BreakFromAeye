"""Completezza delle traduzioni: ogni testo mostrato all'utente ha la versione inglese, con gli stessi segnaposto."""
import ast
import pathlib
import string

import pytest

from eyegaze import config, gui, i18n, simulate, states, zone_ui
from eyegaze.locale_en import EN

SRC = pathlib.Path(__file__).resolve().parent.parent / "eyegaze"


def used_keys():
    keys = set()
    for f in SRC.glob("*.py"):
        if f.name in ("locale_en.py", "i18n.py"):
            continue
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args and isinstance(n.args[0], ast.Constant):
                keys.add(n.args[0].value)
    for s in config.SETTINGS:
        keys.update(s[k] for k in ("section", "label", "help", "unit") if s.get(k))
        keys.update((s.get("labels") or {}).values())
    keys.update(states.STATE_LABELS.values())
    keys.update(states.ACTION_LABELS.values())
    keys.update(gui.ACTION_UI.values())
    keys.update(zone_ui.CORNERS)
    keys.update(d for d, _r, _s in simulate.SCENARIOS["demo"])
    return keys


def fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_text_has_an_english_translation():
    missing = sorted(k for k in used_keys() if k not in EN)
    assert not missing, "traduzioni inglesi mancanti:\n" + "\n".join(map(repr, missing))


def test_no_stale_translations():
    stale = sorted(set(EN) - used_keys())
    assert not stale, "voci inutilizzate in locale_en.py:\n" + "\n".join(map(repr, stale))


def test_placeholders_match_between_languages():
    for it, en in EN.items():
        assert fields(it) == fields(en), (it, en)
        if fields(it):
            kw = {f: 1 for f in fields(it)}
            en.format(**kw)


def test_no_untranslated_string_inside_tr_arguments():
    """Es. tr('Webcam {v}: {w}', w='nessuna risposta') lascerebbe 'nessuna risposta' sempre in italiano."""
    bad = []
    for f in SRC.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        wrapped = {id(n.args[0]) for n in ast.walk(tree)
                   if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args}     # tr annidati: già a posto
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr":
                for kw in n.keywords:
                    for c in ast.walk(kw.value):
                        if isinstance(c, ast.Constant) and isinstance(c.value, str) and len(c.value) > 3 and " " in c.value                                 and id(c) not in wrapped:
                            bad.append((f.name, n.lineno, c.value))
    assert not bad, bad


@pytest.fixture
def english():
    i18n.set_language("en")
    yield
    i18n.set_language("it")


def test_language_switch(english):
    assert i18n.tr("Guardi il PC") == "Looking at the PC"
    assert i18n.tr("Tutti i monitor ({n})", n=2) == "All monitors (2)"
    assert states.action_label("pause") == "PAUSE" and states.state_label(states.GazeState.LOOKING_AWAY) == "Looking away"
    assert i18n.tr("testo sconosciuto") == "testo sconosciuto"          # voce mancante: ricade sull'originale


def test_italian_is_the_default_and_auto_resolves():
    assert i18n.set_language("it") == "it" and i18n.tr("Guardi il PC") == "Guardi il PC"
    assert i18n.set_language("auto") in ("it", "en")
    i18n.set_language("it")


def test_settings_labels_translate(english):
    for s in config.SETTINGS:
        assert i18n.tr(s["label"]) != "" and i18n.tr(s["help"]) != ""
    lab = gui.App._labels_for({"choices": ["play", "pause", "none"]})
    assert lab == {"play": "PLAY", "pause": "PAUSE", "none": "no action"}
