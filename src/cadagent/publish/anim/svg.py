"""The parts every animated README figure shares: numbers, compact paths, a CSS keyframe timeline, themes, the
document wrapper and the rules a figure must pass to be embedded as an ``<img>`` on GitHub.

Figures animate with CSS only: no script and no SMIL. Under ``prefers-reduced-motion`` every animation stops, and
each element shows its own style, so the base style of every animated element is the figure's final frame. Colours
are CSS custom properties with a light and a dark set, chosen by ``prefers-color-scheme`` inside the SVG, and the
figure paints its own background. A mismatch between GitHub's theme and the browser's is therefore never
unreadable.

Coordinates are written in *units* of ``1 / UNITS_PER_PX`` CSS pixels and rounded to whole units, so path data is
short integers. Paths are relative after their first point. Deltas are taken between rounded points, so rounding
never drifts.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

UNITS_PER_PX = 2           # viewBox units per CSS pixel at the figure's natural width: 0.5 px resolution
BUDGET_BYTES = 250_000     # GitHub README figures: at most this many bytes per SVG
REDUCED_MOTION = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
FONT = "system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


# ----------------------------------------------------------------------------------------------------- numbers

def num(v: float, digits: int = 1) -> str:
    """A compact number: no trailing zeros, no leading zero before the point, no "-0"."""
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{v:.0f}"
    if s in ("-0", "", "-"):
        return "0"
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s


def attr(s: str) -> str:
    return escape(s, {'"': "&quot;"})


def _join(values: Sequence[str]) -> str:
    """Numbers separated as tightly as SVG path grammar allows: a minus sign or a leading point ends a number."""
    out, prev = "", None
    for v in values:
        if prev is not None and not v.startswith("-") and not (v.startswith(".") and "." in prev.lstrip("-")):
            out += " "
        out += v
        prev = v
    return out


# ----------------------------------------------------------------------------------------------------- paths

@dataclass
class PathBuilder:
    """Builds one compact ``d`` from segments in units (floats). Lines and elliptical arcs; consecutive segments that
    share an end point continue the subpath. ``radius_digits`` keeps small arcs round."""
    parts: List[str] = field(default_factory=list)
    at: Optional[Tuple[int, int]] = None
    start: Optional[Tuple[int, int]] = None

    @staticmethod
    def q(p) -> Tuple[int, int]:
        return int(round(p[0])), int(round(p[1]))

    def move(self, p) -> None:
        p = self.q(p)
        if self.at == p:
            return
        if self.at is None:
            self.parts.append("M" + _join([str(p[0]), str(p[1])]))
        else:
            self.parts.append("m" + _join([str(p[0] - self.at[0]), str(p[1] - self.at[1])]))
        self.at = self.start = p

    def line(self, p0, p1) -> None:
        self.move(p0)
        p = self.q(p1)
        if p == self.at:
            return
        dx, dy = p[0] - self.at[0], p[1] - self.at[1]
        prev = self.parts[-1] if self.parts else ""
        if prev[:1] == "l":                       # repeated command letters may be dropped
            self.parts[-1] = prev + ("" if str(dx).startswith("-") else " ") + _join([str(dx), str(dy)])
        else:
            self.parts.append("l" + _join([str(dx), str(dy)]))
        self.at = p

    def polyline(self, pts) -> None:
        pts = [self.q(p) for p in pts]
        if len(pts) < 2:
            return
        self.move(pts[0])
        for p in pts[1:]:
            self.line(self.at, p)

    def arc(self, p0, p1, rx: float, ry: float, rot_deg: float, large: bool, sweep: bool) -> None:
        self.move(p0)
        p = self.q(p1)
        if p == self.at:
            return
        rd = 1 if min(rx, ry) < 40 else 0
        self.parts.append("a" + _join([num(rx, rd), num(ry, rd), str(int(round(rot_deg)) % 180),
                                       "1" if large else "0", "1" if sweep else "0",
                                       str(p[0] - self.at[0]), str(p[1] - self.at[1])]))
        self.at = p

    def close(self) -> None:
        if self.parts:
            self.parts.append("z")
            self.at = self.start

    def d(self) -> str:
        return "".join(self.parts)


def arc_points(p0, p1, rx: float, ry: float, rot_deg: float, large: bool, sweep: bool,
               n: int) -> List[Tuple[float, float]]:
    """``n + 1`` points along an SVG elliptical arc from ``p0`` to ``p1``, ends included (the SVG spec's
    endpoint-to-centre conversion, appendix B.2.4; radii too small to reach are scaled up as browsers do)."""
    (x0, y0), (x1, y1) = p0, p1
    if (x0, y0) == (x1, y1) or rx == 0 or ry == 0:
        return [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1)]
    phi = math.radians(rot_deg)
    c, s = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x0 - x1) / 2, (y0 - y1) / 2
    xp, yp = c * dx2 + s * dy2, -s * dx2 + c * dy2
    rx, ry = abs(rx), abs(ry)
    lam = xp * xp / (rx * rx) + yp * yp / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    den = rx * rx * yp * yp + ry * ry * xp * xp
    coef = math.sqrt(max(0.0, num / den)) * (-1 if bool(large) == bool(sweep) else 1)
    cxp, cyp = coef * rx * yp / ry, -coef * ry * xp / rx
    cx, cy = c * cxp - s * cyp + (x0 + x1) / 2, s * cxp + c * cyp + (y0 + y1) / 2
    ux, uy = (xp - cxp) / rx, (yp - cyp) / ry
    vx, vy = (-xp - cxp) / rx, (-yp - cyp) / ry
    t1 = math.atan2(uy, ux)
    dt = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    if sweep and dt < 0:
        dt += 2 * math.pi
    elif not sweep and dt > 0:
        dt -= 2 * math.pi
    out = []
    for i in range(n + 1):
        t = t1 + dt * i / n
        out.append((cx + rx * math.cos(t) * c - ry * math.sin(t) * s, cy + rx * math.cos(t) * s + ry * math.sin(t) * c))
    out[0], out[-1] = (x0, y0), (x1, y1)
    return out


def polygon_d(loops: Iterable[Sequence[Tuple[float, float]]]) -> str:
    """Closed loops (outer boundaries and holes) as one ``d``, for ``fill-rule:evenodd``."""
    b = PathBuilder()
    for loop in loops:
        if len(loop) >= 3:
            b.at = None if not b.parts else b.at
            b.polyline(list(loop))
            b.close()
    return b.d()


def segments_d(segments: Iterable[Sequence]) -> str:
    """Drawn edges as one ``d``. A segment is ``["L", x0, y0, x1, y1]``, ``["P", x0, y0, x1, y1, ...]`` or
    ``["A", x0, y0, x1, y1, rx, ry, rot, large, sweep]`` in units."""
    b = PathBuilder()
    for s in segments:
        kind = s[0]
        if kind == "L":
            b.line(s[1:3], s[3:5])
        elif kind == "P":
            pts = list(zip(s[1::2], s[2::2]))
            if b.at != b.q(pts[0]):
                b.move(pts[0])
            b.polyline(pts)
        elif kind == "A":
            b.arc(s[1:3], s[3:5], s[5], s[6], s[7], bool(s[8]), bool(s[9]))
        else:
            raise ValueError(f"unknown segment {kind!r}")
    return b.d()


# ----------------------------------------------------------------------------------------------------- timeline

class Timeline:
    """CSS keyframes for one figure. Times are seconds in one loop of ``period``; every animation runs the whole
    loop, so they stay in step. Identical keyframe bodies are written once. A keyframe list may stop short of the
    loop's end: the element then returns to its own (still-frame) style, as CSS does for a missing 100 % frame."""

    def __init__(self, period: float):
        self.period = period
        self.keyframes: Dict[str, str] = {}
        self.anims: Dict[str, List[Tuple[str, str]]] = {}      # selector -> [(keyframes name, timing)]
        self.css: List[str] = []

    def pct(self, t: float) -> str:
        return num(100 * t / self.period, 2) + "%"

    def add(self, selector: str, frames: Sequence[Tuple[float, object]], decl: Callable[[object], str],
            timing: str = "ease-in-out") -> None:
        """Animate ``selector`` through ``frames`` [(t, value)], ``decl(value)`` giving the declarations."""
        groups: Dict[str, List[str]] = {}
        last = -1.0
        for t, v in frames:
            if not (0 <= t <= self.period + 1e-9) or t < last - 1e-9:
                raise ValueError(f"{selector}: keyframe time {t} out of order or outside 0..{self.period}")
            last = t
            groups.setdefault(decl(v), []).append(self.pct(min(t, self.period)))
        body = "".join(f"{','.join(p)}{{{d}}}" for d, p in groups.items())
        name = self.keyframes.setdefault(body, _name(len(self.keyframes)))
        self.anims.setdefault(selector, []).append((name, timing))

    def opacity(self, selector: str, points: Sequence[Tuple[float, float]], timing: str = "linear") -> None:
        self.add(selector, points, lambda o: f"opacity:{num(o, 2)}", timing)

    def window(self, selector: str, on: float, off: float, fade: float = 0.3, end: float = 1.0) -> None:
        """Hidden, shown from ``on`` (fading in over ``fade``) until ``off``, then at ``end`` opacity until the loop
        ends. With ``end`` 1 the element stays: its still frame is shown."""
        pts = [(0, 0), (on, 0), (on + fade, 1), (off, 1)]
        if off + fade <= self.period:
            pts.append((off + fade, end))
        self.opacity(selector, pts + [(self.period, end)])

    def stylesheet(self) -> str:
        """Keyframes, then one ``animation`` list per element (selectors with the same list share a rule: a second
        rule for one element would replace the first, not add to it)."""
        out = [f"@keyframes {name}{{{body}}}" for body, name in self.keyframes.items()] + self.css
        by_list: Dict[str, List[str]] = {}
        for selector, anims in self.anims.items():
            decl = ",".join(f"{name} {num(self.period, 2)}s {timing} infinite" for name, timing in anims)
            by_list.setdefault(decl, []).append(selector)
        for decl, selectors in by_list.items():
            out.append(f"{','.join(selectors)}{{animation:{decl}}}")
        return "".join(out) + REDUCED_MOTION


def _name(i: int) -> str:
    """Short keyframe names: a..z, then a0, a1, ..."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    return letters[i] if i < 26 else letters[i // 26 - 1] + str(i % 26)


# ----------------------------------------------------------------------------------------------------- themes

@dataclass(frozen=True)
class Theme:
    """Named colours as CSS custom properties, one set per colour scheme."""
    light: Mapping[str, str]
    dark: Mapping[str, str]

    def css(self) -> str:
        if set(self.light) != set(self.dark):
            raise ValueError("the light and dark themes must name the same colours")
        decl = lambda m: ";".join(f"--{k}:{v}" for k, v in m.items())
        return f"svg{{{decl(self.light)}}}@media (prefers-color-scheme:dark){{svg{{{decl(self.dark)}}}}}"


# cad-agent's palette (the site's), with a dark set of the same roles
THEME = Theme(
    light={"bg": "#fffdf5", "panel": "#f4f1e6", "ink": "#173d3c", "muted": "#526863", "line": "#d8e0d3",
           "edge": "#173d3c", "fill": "#fffdf5", "accent": "#bd3a12", "good": "#2f7d5b", "soft": "#ffe1cc",
           "link": "#e7a93a", "metal": "#c7cdc8", "dark": "#3a4744", "trace": "#2b7bb9"},
    dark={"bg": "#0f1716", "panel": "#16211f", "ink": "#e8efe9", "muted": "#9db0aa", "line": "#2a3a37",
          "edge": "#d5e2dc", "fill": "#13201e", "accent": "#ff7a45", "good": "#5cc8a0", "soft": "#4a2a1c",
          "link": "#f2b84e", "metal": "#4c5a57", "dark": "#26302e", "trace": "#6cb4ff"},
)


# ----------------------------------------------------------------------------------------------------- document

def document(width_px: int, height_px: int, title: str, description: str, css: str, body: Sequence[str],
             theme: Theme = THEME) -> str:
    """The SVG: sized at its natural width in CSS pixels, a viewBox in units, labelled for assistive technology
    (``role="img"``, ``aria-label``, ``<title>`` and ``<desc>``), with the theme's colours and its own background."""
    w, h = width_px * UNITS_PER_PX, height_px * UNITS_PER_PX
    return "".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{width_px}" height="{height_px}" '
        f'role="img" aria-label="{attr(title)}" font-family="{attr(FONT)}">',
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>",
        f"<style>{theme.css()}{css}</style>",
        f'<rect width="{w}" height="{h}" rx="{12 * UNITS_PER_PX}" style="fill:var(--bg)"/>',
        *body, "</svg>\n"])


# ----------------------------------------------------------------------------------------------------- rules

_EXTERNAL = re.compile(r"""(?:href|src)\s*=\s*["'](?!#)""", re.I)
_URL = re.compile(r"""url\(\s*["']?(?!#)""", re.I)


def problems(svg: str, budget: Optional[int] = None) -> List[str]:
    """Why ``svg`` is not safe to embed as a GitHub README ``<img>``: an empty list when it is. ``budget`` is the
    size limit in bytes (default ``BUDGET_BYTES``). Elements are compared by local name in any namespace, and the
    CSS rules are read from the ``<style>`` elements and ``style`` attributes."""
    budget = BUDGET_BYTES if budget is None else budget
    out = []
    size = len(svg.encode("utf-8"))
    if size > budget:
        out.append(f"{size} bytes, over the {budget} byte budget")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        return out + [f"not well-formed XML: {e}"]
    local = lambda tag: tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        out.append(f"root element is {root.tag}, not svg")
    tags = {local(el.tag) for el in root.iter()}
    for bad in ("script", "foreignObject", "iframe", "image", "use", "a"):
        if bad in tags:
            out.append(f"contains <{bad}>")
    if tags & {"animate", "animateTransform", "animateMotion", "animateColor", "set", "discard"}:
        out.append("SMIL animation (use CSS, which reduced motion can stop)")
    for el in root.iter():
        for k in el.attrib:
            if local(k).lower().startswith("on"):
                out.append(f"event handler attribute {local(k)} on <{local(el.tag)}>")
    if _EXTERNAL.search(svg):
        out.append("an href or src that is not a same-document #fragment")
    if _URL.search(svg) or "@import" in svg:
        out.append("a url() or @import that is not a same-document #fragment")
    css = "".join(el.text or "" for el in root.iter() if local(el.tag) == "style")
    inline = "".join(el.get("style", "") for el in root.iter())
    if "\\" in css + inline:
        out.append("a backslash in CSS (an escape could hide a url() or @import)")
    if root.get("role") != "img" or not root.get("aria-label"):
        out.append('no role="img" with an aria-label on the root')
    title = next((el for el in root if local(el.tag) == "title"), None)
    if title is None or not (title.text or "").strip():
        out.append("no <title>")
    if REDUCED_MOTION not in css:
        out.append("no prefers-reduced-motion rule in a <style> that stops every animation")
    if "@keyframes" not in css:
        out.append("no CSS animation")
    return out
