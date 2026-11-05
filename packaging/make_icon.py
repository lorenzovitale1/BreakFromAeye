"""Rigenera assets/icon.ico e assets/icon.png:  python packaging/make_icon.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eyegaze.icon import draw_icon  # noqa: E402

out = ROOT / "assets"
out.mkdir(exist_ok=True)
draw_icon(256).save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
draw_icon(512).save(out / "icon.png")
print("scritti", out / "icon.ico", out / "icon.png")
