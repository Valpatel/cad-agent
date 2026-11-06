"""Text as outlines, so a figure looks the same on every system without a web font (GitHub's ``<img>`` loads none).

The glyphs come from a TrueType file read with fontTools (a CadQuery dependency). The default is DejaVu Sans Bold,
whose licence (Bitstream Vera, with DejaVu's changes in the public domain) allows embedding its outlines. The
outlines are made once, when a scene is extracted, and stored in the scene, so rendering needs no font.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence, Tuple

DEJAVU_BOLD = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
               "/Library/Fonts/DejaVuSans-Bold.ttf")
DEJAVU = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
          "/Library/Fonts/DejaVuSans.ttf")


def find_font(candidates: Sequence[str]) -> Path:
    for c in candidates:
        if Path(c).exists():
            return Path(c)
    raise FileNotFoundError(f"none of these fonts is installed: {', '.join(candidates)}")


def outline(text: str, font: Path, size: float, tracking: float = 0.0) -> Dict[str, object]:
    """``text`` set at ``size`` (drawing units per em) as polygons: {"loops": [[(x, y), ...]], "width": advance}.
    Origin at the left end of the baseline, y down. Curves are flattened to within 1 % of the em."""
    from fontTools.pens.basePen import BasePen
    from fontTools.ttLib import TTFont

    f = TTFont(str(font))
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    upm = f["head"].unitsPerEm
    k = size / upm
    step = 0.01 * upm

    class Flatten(BasePen):
        def __init__(self, glyphs, dx):
            super().__init__(glyphs)
            self.dx, self.loops, self.cur = dx, [], []

        def _pt(self, p):
            return (self.dx + p[0] * k, -p[1] * k)

        def _moveTo(self, p):
            self.cur = [self._pt(p)]

        def _lineTo(self, p):
            self.cur.append(self._pt(p))

        def _curveToOne(self, p1, p2, p3):
            p0 = self._getCurrentPoint()
            n = max(2, int(max(abs(p3[0] - p0[0]), abs(p3[1] - p0[1])) / step / 2) + 2)
            for i in range(1, n + 1):
                t = i / n
                a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                self.cur.append(self._pt((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                                          a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])))

        def _qCurveToOne(self, p1, p2):
            p0 = self._getCurrentPoint()
            n = max(2, int(max(abs(p2[0] - p0[0]), abs(p2[1] - p0[1])) / step / 2) + 2)
            for i in range(1, n + 1):
                t = i / n
                a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
                self.cur.append(self._pt((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1])))

        def _closePath(self):
            if len(self.cur) >= 3:
                self.loops.append(self.cur)
            self.cur = []

        _endPath = _closePath

    loops: List[List[Tuple[float, float]]] = []
    x = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            raise ValueError(f"{font.name} has no glyph for {ch!r}")
        pen = Flatten(gs, x)
        gs[name].draw(pen)
        loops += pen.loops
        x += gs[name].width * k + tracking * size
    return {"loops": loops, "width": x - tracking * size}
