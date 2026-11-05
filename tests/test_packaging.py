"""Icona, ricerca del modello/adb inclusi nell'installer."""
import sys

from eyegaze import adb, config as cfgmod
from eyegaze.icon import draw_icon


def test_icon_sizes_and_accent():
    for size in (16, 64, 256):
        assert draw_icon(size).size == (size, size)
    a, b = draw_icon(64, "#3fb950"), draw_icon(64, "#f0b429")
    assert a.getpixel((32, 22)) != b.getpixel((32, 22))          # il colore (stato) cambia l'iride
    assert draw_icon(64).getpixel((0, 0))[3] == 0                 # angoli trasparenti (sfondo arrotondato)


def test_find_model_prefers_user_copy_then_bundle(tmp_path, monkeypatch):
    user, bundle = tmp_path / "user" / "m.task", tmp_path / "bundle"
    (bundle / "models").mkdir(parents=True)
    (bundle / "models" / "m.task").write_bytes(b"b")
    monkeypatch.setattr(cfgmod, "MODEL_PATH", user)
    monkeypatch.setattr(cfgmod, "BUNDLE_DIR", bundle)
    assert cfgmod.find_model() == bundle / "models" / "m.task"    # solo incluso nell'installer
    user.parent.mkdir()
    user.write_bytes(b"u")
    assert cfgmod.find_model() == user                            # scaricato dall'utente: ha la precedenza


def test_find_adb_looks_in_bundle(tmp_path, monkeypatch):
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    (tmp_path / "tools" / "platform-tools").mkdir(parents=True)
    (tmp_path / "tools" / "platform-tools" / exe).write_bytes(b"x")
    monkeypatch.setattr(adb, "ROOT", tmp_path / "nowhere")
    monkeypatch.setattr(adb, "BUNDLE_DIR", tmp_path)
    monkeypatch.setattr(adb.shutil, "which", lambda _n: None)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "none"))
    assert adb.find_adb() == str(tmp_path / "tools" / "platform-tools" / exe)
