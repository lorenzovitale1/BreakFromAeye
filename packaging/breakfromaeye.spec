# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller --noconfirm --clean packaging/breakfromaeye.spec     (dalla cartella principale del progetto)
# Richiede: models/face_landmarker.task e tools/platform-tools (adb) già presenti: `python -m eyegaze --setup`.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent                      # noqa: F821  (SPECPATH è definito da PyInstaller)

datas, binaries, hiddenimports = [], [], []
d, b, h = collect_all("mediapipe")
datas += d
binaries += b
hiddenimports += h
hiddenimports += collect_submodules("winrt") + ["pystray._win32"]

model = ROOT / "models" / "face_landmarker.task"
adb_dir = ROOT / "tools" / "platform-tools"
assert model.exists(), "manca models/face_landmarker.task (esegui: python -m eyegaze --setup)"
assert (adb_dir / "adb.exe").exists(), "manca tools/platform-tools/adb.exe (esegui: python -m eyegaze --setup)"
datas += [(str(model), "models"), (str(adb_dir), "tools/platform-tools"), (str(ROOT / "assets" / "icon.ico"), "assets"),
          (str(ROOT / "LICENSE"), ".")]

a = Analysis(                                      # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tkinter.test"],
    noarchive=False,
)
pyz = PYZ(a.pure)                                  # noqa: F821
exe = EXE(                                         # noqa: F821
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="BreakFromAeye",
    console=False,                                 # nessuna finestra di comando
    icon=str(ROOT / "assets" / "icon.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="BreakFromAeye")   # noqa: F821
