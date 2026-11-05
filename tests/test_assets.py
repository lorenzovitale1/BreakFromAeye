import hashlib
import zipfile

import pytest

from eyegaze import assets, config as cfgmod


def test_download_verifies_sha_and_moves_file(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"hello model")
    dest = tmp_path / "out" / "m.task"
    good = hashlib.sha256(b"hello model").hexdigest()
    assert assets.download(src.as_uri(), dest, good).read_bytes() == b"hello model"
    dest.unlink()
    with pytest.raises(RuntimeError):
        assets.download(src.as_uri(), dest, "0" * 64)
    assert not dest.exists() and not list(dest.parent.glob("*.part"))     # nessun file corrotto lasciato


def test_pinned_hash_matches_local_model_if_present():
    if cfgmod.MODEL_PATH.exists():
        assert hashlib.sha256(cfgmod.MODEL_PATH.read_bytes()).hexdigest() == assets.MODEL_SHA256


def test_install_adb_rejects_path_traversal(tmp_path, monkeypatch):
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("../evil.txt", "x")
    monkeypatch.setattr(assets, "ADB_DIR", tmp_path / "tools")
    monkeypatch.setattr(assets, "ADB_URL", zpath.as_uri())
    monkeypatch.setattr(assets.sys, "platform", "win32")
    with pytest.raises(RuntimeError):
        assets.install_adb()
    assert not (tmp_path / "evil.txt").exists()


def test_install_adb_extracts_adb(tmp_path, monkeypatch):
    zpath = tmp_path / "pt.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("platform-tools/adb.exe", "binary")
    monkeypatch.setattr(assets, "ADB_DIR", tmp_path / "tools")
    monkeypatch.setattr(assets, "ADB_URL", zpath.as_uri())
    monkeypatch.setattr(assets.sys, "platform", "win32")
    assert assets.install_adb().read_bytes() == b"binary"


def test_data_dir_is_portable_in_checkout():
    assert cfgmod.PORTABLE and cfgmod.ROOT == cfgmod.PKG_ROOT
