"""Icona di BreakFromAeye: un occhio con un triangolo "play" nell'iride.

Disegnata in codice con Pillow (nessuna immagine esterna, nessun diritto di terzi). Serve per l'icona nell'area di notifica
(colore = stato) e, tramite packaging/make_icon.py, per assets/icon.ico e assets/icon.png."""
from __future__ import annotations

from PIL import Image, ImageDraw


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def draw_icon(size: int = 256, accent: str = "#4c8dff", background: bool = True) -> Image.Image:
    k = 4 if size < 512 else 2                      # supercampionamento per bordi lisci
    n = size * k
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r, g, b = _rgb(accent)
    if background:
        d.rounded_rectangle((0, 0, n - 1, n - 1), radius=int(n * 0.22), fill=(15, 20, 27, 255))
        d.rounded_rectangle((n * 0.035, n * 0.035, n * 0.965, n * 0.965), radius=int(n * 0.19),
                            outline=(r, g, b, 90), width=max(1, int(n * 0.012)))
    cx = cy = n / 2
    w, h = n * 0.40, n * 0.235
    xs = [i / 60 * 2 - 1 for i in range(61)]
    top = [(cx + w * x, cy - h * (1 - x * x) ** 0.8) for x in xs]
    bottom = [(cx + w * x, cy + h * (1 - x * x) ** 0.8) for x in reversed(xs)]
    lens = top + bottom                              # forma a mandorla dell'occhio
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).polygon(lens, fill=255)
    layer = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.polygon(lens, fill=(244, 247, 251, 255))      # sclera
    ri = h * 1.02
    ld.ellipse((cx - ri, cy - ri, cx + ri, cy + ri), fill=(int(r * .55), int(g * .55), int(b * .55), 255))   # bordo iride
    ri2 = ri * 0.86
    ld.ellipse((cx - ri2, cy - ri2, cx + ri2, cy + ri2), fill=(r, g, b, 255))                                # iride
    a = ri * 0.5
    ld.polygon([(cx - a * 0.6, cy - a), (cx - a * 0.6, cy + a), (cx + a, cy)], fill=(255, 255, 255, 255))   # play
    img.paste(layer, (0, 0), mask)                   # palpebre: l'iride resta dentro l'occhio
    d.line(lens + [lens[0]], fill=(r, g, b, 255), width=max(1, int(n * 0.02)), joint="curve")
    return img.resize((size, size), Image.LANCZOS)
