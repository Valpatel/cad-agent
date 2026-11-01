#!/usr/bin/env python3
"""Regenerate the animated concept figures (docs/img/motion/*.svg) from the code and fixtures they illustrate.

    PYTHONPATH=src python3 tools/motion_figures.py            # write the SVGs
    PYTHONPATH=src python3 tools/motion_figures.py --check    # exit 1 if a committed SVG differs (tests run this)

Nothing is keyframed by eye. Each figure draws one fixture or worked example from this repo:

* where the real code runs without CadQuery, the figure runs it:
  - the assembly-sequence core (``run_sequence``) on the subassembly fixture;
  - the connector windows and margins (``cadagent.mechanical.connectors``);
  - the worked example's seeded search (``run_search``);
* where the real check needs the kernel, a 2D model of the same fixture stands in:
  - the motion gate's sampled poses, collision and bisected onset;
  - the hole check's probe volumes.

``tests/test_motion_figures.py`` runs ``--check`` and compares these fixtures with the tests' own copies. Where
CadQuery is installed, it also checks the 2D numbers against the real motion gate, hole check and connector sweep.

The SVGs animate with CSS only, with no script, so they run in an ``<img>`` under the site's Content-Security-Policy
and on GitHub. They carry their own light background. Under ``prefers-reduced-motion`` each one holds a still frame
that shows the result. They need cadagent's core dependencies (numpy, pyyaml): run them from a checkout with
``PYTHONPATH=src``, or with cadagent installed.
"""
from __future__ import annotations

import inspect
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "img" / "motion"

BG, INK, PALE, GREEN, PEACH, ORANGE = "#fffdf5", "#173d3c", "#eef1e4", "#6f8a80", "#ffe1cc", "#bd3a12"
MUTED, LINE = "#526863", "#d8e0d3"
FONT = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif"


# ----------------------------------------------------------------------------- drawing helpers

def num(v: float, digits: int = 1) -> str:
    """A compact number for coordinates: no trailing zeros, no "-0"."""
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{v:.0f}"
    return "0" if s in ("-0", "") else s


def fmt(v: float, digits: int = 1) -> str:
    """A number for a label: fixed decimals and a real minus sign."""
    return f"{v:.{digits}f}".replace("-", "−")


def attr(s: str) -> str:
    return escape(s, {'"': "&quot;"})


def path(points) -> str:
    return "M" + " ".join(f"{num(x)} {num(y)}" for x, y in points) + "Z"


def text(x, y, s, size=12, fill=INK, anchor=None, weight=None, extra="", halo=False) -> str:
    """A label. Size 12 and ink are the figure's defaults (set on the root), and muted 10 and 11 px labels have
    classes (``svg`` defines them), so none of these is repeated on every label."""
    if fill == MUTED and size in (10, 11):
        z, f = f' class="m{size}"', ""
    else:
        z = "" if size == 12 else f' font-size="{num(size)}"'
        f = "" if fill == INK else f' fill="{fill}"'
    a = f' text-anchor="{anchor}"' if anchor else ""
    w = f' font-weight="{weight}"' if weight else ""
    h = f' stroke="{BG}" stroke-width="3" paint-order="stroke"' if halo else ""
    return f'<text x="{num(x)}" y="{num(y)}"{z}{f}{a}{w}{h}{extra}>{escape(s)}</text>'


NARROW_PX = 400            # an <img> this wide or narrower shows the narrow labels (the SVG's own media query)
NARROW_MIN_SIZE = 23       # user units: at least 11 CSS px on a 360 px phone, whose docs column is 324 px wide


def ntext(x, y, s, size=24, fill=INK, anchor=None, weight=None, halo=False) -> str:
    """A label for the narrow layout only: shown, instead of every other label, when the figure is drawn
    ``NARROW_PX`` wide or less, where the 680-unit figure is scaled to about half and its small labels can't be read."""
    assert size >= NARROW_MIN_SIZE, s
    return text(x, y, s, size, fill, anchor, weight, ' class="n"', halo)


class View:
    """World (x right, z up, mm) to SVG user units (y down): ``k`` units per mm, world (x0, z_top) at (ox, oy)."""

    def __init__(self, x0: float, z_top: float, k: float, ox: float, oy: float):
        self.x0, self.z_top, self.k, self.ox, self.oy = x0, z_top, k, ox, oy

    def __call__(self, x: float, z: float):
        return self.ox + (x - self.x0) * self.k, self.oy + (self.z_top - z) * self.k

    def rect(self, x0, z0, x1, z1):
        return [self(x0, z0), self(x1, z0), self(x1, z1), self(x0, z1)]

    def poly(self, pts):
        return [self(x, z) for x, z in pts]


class Anim:
    """CSS keyframes for one figure. Times are seconds in one loop of ``period``, and every animation runs the whole
    loop, so they stay in step. A keyframe list may stop short of the loop's end: the element then returns to its
    own (still-frame) style, as CSS does for a missing 100 % keyframe. Identical keyframes are written once."""

    def __init__(self, period: float):
        self.period, self.keyframes, self.rules, self.css = period, {}, {}, []

    def pct(self, t: float) -> str:
        return num(100 * t / self.period, 1) + "%"

    def add(self, selector: str, frames, decl, timing: str = "ease-in-out", name_only: bool = False) -> None:
        """Animate ``selector`` through ``frames`` [(t, value)], ``decl(value)`` giving the CSS declarations.
        ``name_only`` sets just the animation's name, for elements whose duration and timing a shared rule sets."""
        groups: dict = {}
        for t, v in frames:
            assert 0 <= t <= self.period + 1e-9, (selector, t)
            groups.setdefault(decl(v), []).append(self.pct(t))
        body = "".join(f"{','.join(p)}{{{d}}}" for d, p in groups.items())
        name = self.keyframes.setdefault(body, f"k{len(self.keyframes)}")
        self.rules.setdefault((name, None if name_only else timing), []).append(selector)

    def show(self, selector: str, on: float, off: float, d: float = 0.3) -> None:
        """Hidden, then shown from ``on`` to ``off`` (fading over ``d``), then hidden to the loop's end."""
        frames = [(0, 0), (on, 0), (on + d, 1), (off, 1), (min(off + d, self.period), 0), (self.period, 0)]
        self.add(selector, frames, lambda o: f"opacity:{num(o, 2)}", "linear")

    def stylesheet(self) -> str:
        out = [f"@keyframes {name}{{{body}}}" for body, name in self.keyframes.items()] + self.css
        for (name, timing), selectors in self.rules.items():
            rule = f"animation-name:{name}" if timing is None else \
                f"animation:{name} {num(self.period, 2)}s {timing} infinite"
            out.append(f"{','.join(selectors)}{{{rule}}}")
        return "".join(out) + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"


def svg(w: int, h: int, label: str, body: list, anim: Anim) -> str:
    """The figure: a sized, labelled SVG with its own background. Under reduced motion every animation stops, and
    each element shows its own style: the still frame. Drawn ``NARROW_PX`` wide or less (a media query inside an
    SVG follows the ``<img>``'s own width), every label hides except the large ``ntext`` ones, and so does any
    element of class ``w``. They hide with ``visibility``, not ``display``: WebKit lays an SVG image out at more
    than one size, and re-laying the text out each time stalled a smooth scroll past the figure by about 150 ms."""
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
        f'aria-label="{attr(label)}" font-family="{FONT}" font-size="12" fill="{INK}">',
        f"<style>.m10,.m11{{fill:{MUTED}}}.m10{{font-size:10px}}.m11{{font-size:11px}}.n{{visibility:hidden}}"
        f"@media (max-width:{NARROW_PX}px){{text:not(.n),.w{{visibility:hidden}}.n{{visibility:visible}}}}"
        f"{anim.stylesheet()}</style>",
        f'<rect width="{w}" height="{h}" rx="14" fill="{BG}" stroke="{LINE}"/>',
        *body, "</svg>"]) + "\n"


# ----------------------------------------------------------------------------- 2D geometry

def rotate(p, deg, c):
    """``p`` turned ``deg`` counter-clockwise (x right, z up) about ``c``."""
    a = math.radians(deg)
    x, z = p[0] - c[0], p[1] - c[1]
    return c[0] + x * math.cos(a) - z * math.sin(a), c[1] + x * math.sin(a) + z * math.cos(a)


def clip(poly, box):
    """Sutherland-Hodgman: ``poly`` clipped to the axis-aligned ``box`` (x0, z0, x1, z1)."""
    x0, z0, x1, z1 = box
    edges = [(lambda p: p[0] >= x0, 0, x0), (lambda p: p[0] <= x1, 0, x1),
             (lambda p: p[1] >= z0, 1, z0), (lambda p: p[1] <= z1, 1, z1)]
    out = list(poly)
    for inside, axis, v in edges:
        pts, out = out, []
        for i, p in enumerate(pts):
            q = pts[i - 1]
            if inside(p) != inside(q):
                t = (v - q[axis]) / (p[axis] - q[axis])
                out.append((q[0] + t * (p[0] - q[0]), q[1] + t * (p[1] - q[1])))
            if inside(p):
                out.append(p)
        if not out:
            return []
    return out


def area(poly) -> float:
    return abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(poly, poly[1:] + poly[:1]))) / 2


def gap(a, b) -> float:
    """The distance between two convex polygons that do not overlap."""
    def to_segment(p, q, r):
        dx, dz = r[0] - q[0], r[1] - q[1]
        t = max(0.0, min(1.0, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dz) / (dx * dx + dz * dz)))
        return math.hypot(p[0] - q[0] - t * dx, p[1] - q[1] - t * dz)
    return min(to_segment(p, s[i - 1], s[i]) for u, s in ((a, b), (b, a)) for p in u for i in range(len(s)))


# ----------------------------------------------------------------------------- 1. motion gate: hinge sweep

# The gate bench (tests/fixtures/gate_bench/build.py), in the XZ plane, in millimetres. The arm spans Y 40..44 and
# the frame Y 36..48, so a section of the arm and the beam is exact, and their shared area times the arm's 4 mm is
# the shared volume. tests/test_motion_figures.py checks these numbers against the built bench and its verdict.
BENCH = {"pivot": (105.0, 20.0), "pin_r": 2.5, "arm": (100.0, 14.0, 150.0, 26.0), "arm_thickness": 4.0,
         "hinge_block": (99.0, 4.0, 111.0, 26.0), "stop": (140.0, 4.0, 150.0, 14.0),
         "post": (152.0, 4.0, 156.0, 60.0), "beam": (112.0, 56.0, 156.0, 60.0), "base": (0.0, 0.0, 160.0, 4.0),
         "seed": "flap_hits_frame", "range_deg": (0.0, 60.0), "default_range_deg": (0.0, 40.0)}


def arm_at(deg: float, b=BENCH):
    x0, z0, x1, z1 = b["arm"]
    return [rotate(p, deg, b["pivot"]) for p in ((x0, z0), (x1, z0), (x1, z1), (x0, z1))]


def hinge_numbers(b=BENCH) -> dict:
    """The motion gate's rules (cadagent.review.gates.motion) on the 2D model: the samples, the colliding poses, the
    last clear one and the onset bisected between them."""
    from cadagent.review.gates.motion import DEFAULT_SAMPLES, motion_gate
    from cadagent.review.gates.relations import Tolerances
    refine = inspect.signature(motion_gate).parameters["refine_steps"].default
    limit = Tolerances().overlap_mm3
    lo, hi = b["range_deg"]
    n = DEFAULT_SAMPLES
    samples = [lo + i * (hi - lo) / (n - 1) for i in range(n)]
    vol = lambda d: area(clip(arm_at(d, b), b["beam"])) * b["arm_thickness"]
    hits = [d for d in samples if vol(d) > limit]
    first = hits[0]
    last_clear = samples[samples.index(first) - 1]
    a, z, brackets = last_clear, first, [(last_clear, first)]
    for _ in range(refine):
        m = (a + z) / 2
        a, z = (a, m) if vol(m) > limit else (m, z)
        brackets.append((a, z))
    worst = max(hits, key=vol)
    bx0, bz0, bx1, bz1 = b["beam"]
    beam = [(bx0, bz0), (bx1, bz0), (bx1, bz1), (bx0, bz1)]
    corners = [(x, zz) for x in b["arm"][0::2] for zz in b["arm"][1::2]]
    radius = max(math.dist(p, b["pivot"]) for p in corners)
    step = (hi - lo) / (n - 1)
    return {"samples": samples, "hits": hits, "first": first, "first_mm3": vol(first), "last_clear": last_clear,
            "last_clear_gap_mm": gap(arm_at(last_clear, b), beam), "brackets": brackets, "onset": brackets[-1],
            "refine_steps": refine, "worst": worst, "worst_mm3": vol(worst), "step_deg": step,
            "max_radius_mm": radius, "max_travel_per_step_mm": math.radians(step) * radius, "overlap_mm3": limit}


def hinge_svg() -> str:
    b, h = BENCH, hinge_numbers()
    v = View(92, 64, 4.2, 20, 58)
    an = Anim(15.0)
    # timeline: through every sample, back to the last clear one, one pose per bisection, hold, home
    move, hold, t = 0.25, 0.35, 0.6
    frames, arrive = [(0, 0.0), (t, 0.0)], []
    for d in h["samples"]:
        t += move
        frames.append((t, d))
        arrive.append(t)
        t += hold
        frames.append((t, d))
    t += 0.45
    frames += [(t, h["last_clear"]), (t + 0.35, h["last_clear"])]
    back = t
    t += 0.35
    rows = [t]
    for (lo_, hi_), (plo, phi) in zip(h["brackets"][1:], h["brackets"]):
        tried = hi_ if hi_ != phi else lo_                  # the pose this bisection tried
        t += 0.2
        frames.append((t, tried))
        rows.append(t)
        t += 0.28
        frames.append((t, tried))
    still = frames[-1][1]
    done, end = t, 13.9
    frames += [(end, still), (end + 0.8, 0.0), (an.period, 0.0)]

    body = [text(20, 30, "Motion gate: the arm swept through its sampled poses", 15, INK, weight="700"),
            text(20, 47, f"gate bench, seed {b['seed']}: the joint's range raised from {fmt(b['default_range_deg'][1], 0)}° "
                         f"to {fmt(b['range_deg'][1], 0)}°; up to {fmt(h['max_travel_per_step_mm'], 2)} mm of travel "
                         "between samples", 11, MUTED),
            ntext(20, 40, "Motion gate sweep", 28, weight="700")]
    # the parts: base (cut away at the left: it starts at x = 0), hinge block (behind the arm), stop, frame
    bx0, bz0, bx1, bz1 = b["base"]
    cut = v.x0                                           # the drawing's left edge: a break line
    zig = [(cut + dx, bz1 - i * (bz1 - bz0) / 4) for i, dx in enumerate((0, 0.7, -0.7, 0.7))]
    body.append(f'<path d="{path(v.poly([(cut, bz0), (bx1, bz0), (bx1, bz1)] + zig))}" fill="{PALE}" stroke="{GREEN}"/>')
    body.append(f'<path d="{path(v.rect(*b["hinge_block"]))}" fill="{PALE}" stroke="{GREEN}" stroke-dasharray="3 2"/>')
    body.append(f'<path d="{path(v.rect(*b["stop"]))}" fill="{PALE}" stroke="{GREEN}"/>')
    px, pz = b["post"][0::2], b["post"][1::2]
    bx, bz = b["beam"][0::2], b["beam"][1::2]
    frame = [(px[0], pz[0]), (px[1], pz[0]), (px[1], pz[1]), (bx[0], bz[1]), (bx[0], bz[0]), (px[0], bz[0])]
    body.append(f'<path d="{path(v.poly(frame))}" fill="{PALE}" stroke="{INK}" stroke-width="1.5"/>')
    # one outline per sampled pose, kept as the sweep passes it
    for i, d in enumerate(h["samples"]):
        colour = ORANGE if d in h["hits"] else GREEN
        body.append(f'<path id="g{i}" d="{path(v.poly(arm_at(d)))}" fill="none" stroke="{colour}" stroke-opacity=".75"/>')
    # the arm, turned about the pin
    cx, cy = v(*b["pivot"])
    an.css.append(f".arm{{transform-origin:{num(cx)}px {num(cy)}px;transform-box:view-box;"
                  f"transform:rotate({num(-still, 2)}deg)}}")
    an.add(".arm", frames, lambda d: f"transform:rotate({num(-d, 2)}deg)")
    body.append(f'<path class="arm" d="{path(v.poly(arm_at(0)))}" fill="{BG}" stroke="{INK}" stroke-width="2" '
                f'stroke-linejoin="round"/>')
    # what each colliding pose shares with the beam
    for i, d in enumerate(h["samples"]):
        if d in h["hits"]:
            body.append(f'<path id="o{i}" d="{path(v.poly(clip(arm_at(d), b["beam"])))}" fill="{ORANGE}"/>')
    body.append(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(b["pin_r"] * v.k)}" fill="{INK}"/>')
    body.append(text(*v(134, 61.2), "frame beam", 11, MUTED, "middle"))
    body.append(text(*v(145, 8.1), "stop", 11, MUTED, "middle"))

    # right: the samples on an angle scale with a cursor that follows the arm, then the bisection's brackets
    x_of = lambda d: 344 + d * 306 / (b["range_deg"][1] - b["range_deg"][0])
    body.append(text(334, 92, f"{len(h['samples'])} samples, {fmt(b['range_deg'][0], 0)}–{fmt(b['range_deg'][1], 0)}°, "
                              f"{fmt(h['step_deg'], 2)}° apart", 12, INK, weight="600"))
    body.append(ntext(334, 90, f"{len(h['samples'])} poses, {fmt(b['range_deg'][0], 0)}–{fmt(b['range_deg'][1], 0)}°"))
    body.append(f'<path d="M{num(x_of(0))} 118H{num(x_of(60))}" stroke="{LINE}" stroke-width="3"/>')
    for d in range(0, 61, 15):
        body.append(text(x_of(d), 138, f"{d}°", 10, MUTED, "middle"))
    for i, d in enumerate(h["samples"]):
        body.append(f'<circle id="d{i}" cx="{num(x_of(d))}" cy="118" r="4.5" fill="{ORANGE if d in h["hits"] else GREEN}"/>')
        an.show(f"#g{i},#d{i}" + (f",#o{i}" if d in h["hits"] else ""), arrive[i], end)
    an.css.append(f".cur{{transform:translateX({num(x_of(still) - x_of(0))}px)}}")
    an.add(".cur", frames, lambda d: f"transform:translateX({num(x_of(d) - x_of(0))}px)")
    body.append(f'<path class="cur" d="M{num(x_of(0))} 110l-4.5 -7h9z" fill="{INK}"/>')

    lo0, hi0 = h["brackets"][0]
    z_of = lambda d: 344 + (d - lo0) * 306 / (hi0 - lo0)
    body.append(text(334, 166, f"onset bisected {h['refine_steps']} times", 12, INK, weight="600"))
    body.append(ntext(334, 166, f"{h['refine_steps']} bisections"))
    for j, (lo_, hi_) in enumerate(h["brackets"]):
        body.append(f'<rect id="r{j}" x="{num(z_of(lo_))}" y="{176 + 7 * j}" width="{num(max(z_of(hi_) - z_of(lo_), 1.2))}" '
                    f'height="5" rx="1" fill="{ORANGE if j == len(h["brackets"]) - 1 else GREEN}"/>')
        an.show(f"#r{j}", rows[j], end)
    y = 176 + 7 * len(h["brackets"]) + 12
    body.append(text(344, y, f"{fmt(lo0, 2)}° clear", 10, MUTED))
    body.append(text(650, y, f"{fmt(hi0, 2)}° hit", 10, MUTED, "end"))
    lines = [(arrive[h["samples"].index(h["first"])], ORANGE,
              f"collision:arm|frame from {fmt(h['first'], 2)}°, {fmt(h['first_mm3'], 1)} mm³ shared"),
             (back, INK, f"last clear {fmt(h['last_clear'], 2)}°, gap {fmt(h['last_clear_gap_mm'], 2)} mm"),
             (done, INK, f"onset between {fmt(h['onset'][0], 2)}° and {fmt(h['onset'][1], 2)}°"),
             (arrive[h["samples"].index(h["worst"])], MUTED,
              f"worst {fmt(h['worst'], 0)}°: {fmt(h['worst_mm3'], 1)} mm³; {len(h['hits'])} of {len(h['samples'])} poses hit")]
    short = [f"hits from {fmt(h['first'], 2)}°", f"last clear {fmt(h['last_clear'], 2)}°",
             f"onset {fmt(h['onset'][0], 2)}–{fmt(h['onset'][1], 2)}°"]
    for i, (on, colour, s) in enumerate(lines):
        narrow = ntext(334, 272 + 32 * i, short[i], fill=colour) if i < len(short) else ""
        body.append(f'<g id="t{i}">{text(334, y + 26 + 19 * i, s, 12, colour)}{narrow}</g>')
        an.show(f"#t{i}", on, end)
    label = (f"The gate bench arm swept from 0 to {fmt(b['range_deg'][1], 0)} degrees in {len(h['samples'])} sampled "
             f"poses. It collides with the frame beam from {fmt(h['first'], 2)} degrees, and the onset is bisected to "
             f"between {fmt(h['onset'][0], 2)} and {fmt(h['onset'][1], 2)} degrees.")
    return svg(680, 350, label, body, an)


# ----------------------------------------------------------------------------- 2. holes: a rib in a counterbore

# tests/test_holes.py, plate_with_counterbore: a 40 x 40 x 10 plate, a D3.4 clearance hole with a D6.4 x 4
# counterbore, and a 2 mm rib (X -22..0, Y -1..1, Z 0..14) that runs to the hole's centre. Drawn as the section
# through the hole's axis (Y = 0).
CBORE = {"plate": (-20.0, 0.0, 20.0, 10.0), "hole_r": 1.7, "cbore_r": 3.2, "cbore_depth": 4.0,
         "rib": (-22.0, -1.0, 0.0, 0.0, 1.0, 14.0)}


def _inside(rib, r, z0, z1, tol):
    """Volume of the box ``rib`` inside a probe cylinder of radius ``r - tol`` about Z, over ``z0 + tol .. z1 - tol``
    (cadagent.mechanical.holes.probe for a bore), by Simpson's rule across Y; the X extent is exact."""
    x0, y0, zr0, x1, y1, zr1 = rib
    rp, a, b = r - tol, z0 + tol, z1 - tol
    height = max(0.0, min(b, zr1) - max(a, zr0))
    lo, hi = max(y0, -rp), min(y1, rp)
    if height <= 0 or hi <= lo:
        return 0.0
    n = 2000

    def width(y):
        half = math.sqrt(max(rp * rp - y * y, 0.0))
        return max(0.0, min(x1, half) - max(x0, -half))
    s = width(lo) + width(hi) + sum((4 if i % 2 else 2) * width(lo + i * (hi - lo) / n) for i in range(1, n))
    return s * (hi - lo) / n / 3 * height


def counterbore_numbers(c=CBORE) -> dict:
    from cadagent.mechanical.holes import MIN_VOLUME_MM3, TOL_MM
    top = c["plate"][3]
    floor = top - c["cbore_depth"]
    rib_top = c["rib"][5]
    # rib after the holes: each bore's wall is the plate's, from its floor to the plate's top
    after = {"D6.4": _inside(c["rib"], c["cbore_r"], floor, top, TOL_MM),
             "D3.4": _inside(c["rib"], c["hole_r"], 0.0, floor, TOL_MM)}
    return {"after": after, "last": {"D6.4": 0.0, "D3.4": 0.0}, "tol_mm": TOL_MM, "min_volume_mm3": MIN_VOLUME_MM3,
            "floor": floor, "top": top, "rib_top": rib_top,
            # cut last, the counterbore also cuts the rib, so its wall (and its probe) runs up to the rib's top
            "probe_after": {"D6.4": (floor, top), "D3.4": (0.0, floor)},
            "probe_last": {"D6.4": (floor, rib_top), "D3.4": (0.0, floor)}}


def hatch(pid: str, base: str, line: str, gap: float = 7.0) -> str:
    """Section lining: a ``<pattern>`` of 45° lines on a solid base, used as ``fill="url(#pid)"``."""
    return (f'<pattern id="{pid}" width="{num(gap)}" height="{num(gap)}" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(45)"><rect width="{num(gap)}" height="{num(gap)}" fill="{base}"/>'
            f'<path d="M{num(gap / 2)} 0V{num(gap)}" stroke="{line}" stroke-width="1.4"/></pattern>')


def counterbore_svg() -> str:
    c, h = CBORE, counterbore_numbers()
    an = Anim(12.0)
    r1, r2, fl, top, rt = c["hole_r"], c["cbore_r"], h["floor"], h["top"], h["rib_top"]
    rx0, rx1 = c["rib"][0], c["rib"][3]
    px0, _, px1, _ = c["plate"]
    tol = h["tol_mm"]
    # the section window (mm): the plate and the rib run on past its sides, so their cut-off ends are drawn as edges
    X0, X1, Z0, Z1, k, oy = -7.0, 9.0, -2.4, 14.6, 15.0, 66
    window = (X0, Z0, X1, Z1)
    bore = [(-r1, 0), (r1, 0), (r1, fl), (r2, fl), (r2, top), (-r2, top), (-r2, fl), (-r1, fl)]
    shape = {
        "plate": [(px0, 0), (px1, 0), (px1, top), (px0, top)],
        "rib": [(rx0, 0), (rx1, 0), (rx1, rt), (rx0, rt)],
        "union": [(rx0, 0), (px1, 0), (px1, top), (rx1, top), (rx1, rt), (rx0, rt)],
        # holes cut first: the plate either side of them; the rib then refills the part of them left of the axis
        "after": [[(px0, 0), (-r1, 0), (-r1, fl), (-r2, fl), (-r2, top), (px0, top)],
                  [(r1, 0), (px1, 0), (px1, top), (r2, top), (r2, fl), (r1, fl)]],
        "refilled": [(rx1, 0), (-r1, 0), (-r1, fl), (-r2, fl), (-r2, top), (rx1, top)],
        # holes cut last: they also cut the rib, so the counterbore runs up through it to the rib's top
        "last": [[(rx0, 0), (-r1, 0), (-r1, fl), (-r2, fl), (-r2, rt), (rx0, rt)],
                 [(r1, 0), (px1, 0), (px1, top), (r2, top), (r2, fl), (r1, fl)]],
        "cutter_after": bore,
        "cutter_last": bore[:5] + [(rx1, top), (rx1, rt), (-r2, rt)] + bore[6:],
    }
    end, gone = 10.6, 11.0                           # the result holds to ``end``; both panels have faded by ``gone``
    steps_at = [(0.3, 2.6), (2.6, 4.9), (4.9, end)]
    t_probe = steps_at[2][0] + 0.2
    solid = f'fill="url(#hs)" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"'
    body = [f"<defs>{hatch('hs', GREEN, '#9ab0a4')}{hatch('hr', ORANGE, '#dc6d43')}</defs>",
            text(20, 28, "A rib added after the holes refills them: section through the screw hole", 15, INK, weight="700")]
    panels = [(30, "Holes cut, then the rib unioned", "Rib after holes", "after",
               ["1 · cut the hole and counterbore", "2 · union the rib: it runs to the hole's centre"],
               ["1 · cut holes", "2 · add rib"]),
              (370, "The rib unioned, then the holes cut last", "Holes cut last", "last",
               ["1 · union the rib", "2 · cut the hole and counterbore last"], ["1 · add rib", "2 · cut holes"])]
    an.add(".pg", [(0, 0), (0.3, 1), (end, 1), (gone, 0), (an.period, 0)], lambda o: f"opacity:{o}", "linear")
    for n, (ox, title, short, case, steps, short_steps) in enumerate(panels):
        v = View(X0, Z1, k, ox, oy)
        poly = lambda pts: path(v.poly(clip(pts, window)))
        t_cut, t_rib = (0.6, 2.8) if case == "after" else (2.8, 0.6)
        swap = t_cut + 0.45                          # under the opaque cutter, the uncut solid becomes the cut one
        t_holes = t_cut + 0.8                        # the cutter fades: the holes are there from now on
        seat = t_rib + 1.0
        off = (Z1 + 0.6) * k                         # the rib starts above the window, out of sight
        g = [f'<g class="pg">', text(ox, 54, title, 13, INK, weight="600"), ntext(ox, 50, short, 26, weight="700"),
             f'<clipPath id="c{n}"><rect x="{ox}" y="{oy}" width="{num((X1 - X0) * k)}" '
             f'height="{num((Z1 - Z0) * k)}"/></clipPath><g clip-path="url(#c{n})">']
        # the solid before the cut (the plate, and in the right panel the rib unioned onto it), then after it
        plate_until = swap if case == "after" else seat
        g.append(f'<path id="a{n}" d="{poly(shape["plate"])}" {solid} opacity="0"/>')
        an.add(f"#a{n}", [(0, 1), (plate_until, 1), (plate_until + 0.05, 0), (an.period, 0)],
               lambda o: f"opacity:{o}", "linear")
        if case == "last":
            # the rib slides down onto the plate; seated, the two are one solid with one outline, until the cut
            g.append(f'<path id="r{n}" d="{poly(shape["rib"])}" {solid} opacity="0"/>')
            an.add(f"#r{n}", [(0, (off, 1)), (t_rib, (off, 1)), (seat, (0, 1)), (seat + 0.05, (0, 0)),
                              (an.period, (0, 0))], lambda s: f"transform:translateY({num(-s[0])}px);opacity:{s[1]}")
            g.append(f'<path id="u{n}" d="{poly(shape["union"])}" {solid} opacity="0"/>')
            an.add(f"#u{n}", [(0, 0), (seat, 0), (seat + 0.05, 1), (swap, 1), (swap + 0.05, 0), (an.period, 0)],
                   lambda o: f"opacity:{o}", "linear")
        g.append(f'<path id="b{n}" d="{"".join(poly(p) for p in shape[case])}" {solid}/>')
        an.add(f"#b{n}", [(0, 0), (swap, 0), (swap + 0.05, 1), (an.period, 1)], lambda o: f"opacity:{o}", "linear")
        # what the hole check probes: each bore, its radius and length less the tolerance. Drawn under the rib and
        # its refill, it shades the void it probes, and what refills the bore covers it
        probes = "".join(path(v.rect(-(r - tol), z0 + tol, r - tol, z1 - tol)) for name, r in (("D6.4", r2), ("D3.4", r1))
                         for z0, z1 in [h["probe_" + case][name]])
        g.append(f'<path id="p{n}" d="{probes}" fill="{INK}" fill-opacity=".16"/>')
        an.show(f"#p{n}", t_probe, end)
        if case == "after":
            # the rib slides down onto the plate, opaque, and fills the half of each hole left of the axis
            g.append(f'<path id="r{n}" d="{poly(shape["rib"])}" {solid}/>')
            an.add(f"#r{n}", [(0, off), (t_rib, off), (seat, 0), (gone, 0), (gone + 0.05, off), (an.period, off)],
                   lambda d: f"transform:translateY({num(-d)}px)")
            walls = path(v.poly([(-r2, top), (-r2, fl), (-r1, fl), (-r1, 0)]))[:-1]
            g.append(f'<g id="f"><path d="{poly(shape["refilled"])}" fill="url(#hr)" stroke="{ORANGE}" stroke-width="1.6"/>'
                     f'<path d="{walls}" fill="none" stroke="{BG}" stroke-width="1.6" stroke-dasharray="5 3"/></g>')
            an.add("#f", [(0, 0), (seat, 0), (seat + 0.3, 1), (t_probe + 0.4, 1), (t_probe + 0.9, 0.55),
                          (t_probe + 1.4, 1), (t_probe + 1.9, 0.55), (t_probe + 2.4, 1), (an.period, 1)],
                   lambda o: f"opacity:{o}")
        # the hole's centreline, from the cut on
        cx, cz0 = v(0, -1.1)
        g.append(f'<path id="cl{n}" d="M{num(cx)} {num(cz0)}V{num(v(0, top + 1.2)[1])}" stroke="{INK}" stroke-width="1" '
                 f'stroke-dasharray="10 3 2 3"/>')
        # the cutter: shown over the uncut solid, held while the solid changes under it, then gone
        g.append(f'<path id="x{n}" d="{poly(shape["cutter_" + case])}" fill="{PEACH}" stroke="{ORANGE}" stroke-width="2" '
                 f'opacity="0"/>')
        an.add(f"#x{n}", [(0, 0), (t_cut, 0), (t_cut + 0.2, 1), (t_holes - 0.1, 1), (t_holes + 0.3, 0), (an.period, 0)],
               lambda o: f"opacity:{o}", "linear")
        g.append("</g>")
        an.show(f"#cl{n}", t_holes, an.period - 0.3)
        # the holes' names, outside the section, with leaders into the void; shown once the holes exist
        lx = 2.3
        g.append(f'<g id="l{n}">{text(*v(1.3, 12.5), "counterbore D6.4 × 4", 11, INK)}'
                 f'{text(*v(-1.6, -2.0), "clearance hole D3.4", 11, INK)}<g class="w" stroke="{INK}" fill="{INK}">'
                 f'<path d="M{num(v(lx, 11.8)[0])} {num(v(lx, 11.8)[1])}V{num(v(lx, 8.0)[1])}"/>'
                 f'<circle cx="{num(v(lx, 8.0)[0])}" cy="{num(v(lx, 8.0)[1])}" r="2.2"/>'
                 f'<path d="M{num(v(0.9, -1.1)[0])} {num(v(0.9, -1.1)[1])}V{num(v(0.9, 3.0)[1])}"/>'
                 f'<circle cx="{num(v(0.9, 3.0)[0])}" cy="{num(v(0.9, 3.0)[1])}" r="2.2"/></g></g>')
        an.show(f"#l{n}", t_holes, end)
        g.append(f'<g id="rl{n}">{text(*v(-4.6, 12.0), "rib", 12, BG, "middle", "700")}</g>')
        an.show(f"#rl{n}", seat, end)
        # the build order, the current step lit, and the hole check's findings once it has run
        y0 = oy + (Z1 - Z0) * k + 22
        steps = steps + ["3 · cad-agent holes probes each bore (shaded)"]
        short_steps = short_steps + ["3 · probe"]
        for j, (s, (t0, t1)) in enumerate(zip(steps, steps_at)):
            hidden = "" if j == 2 else ' opacity="0"'
            g.append(f'<rect id="h{n}{j}" class="w" x="{ox - 6}" y="{num(y0 + 19 * j - 13)}" width="300" height="18" rx="4" '
                     f'fill="{PEACH}"{hidden}/>')
            g.append(text(ox, y0 + 19 * j, s, 12, INK))
            g.append(f'<g id="ns{n}{j}"{hidden}>{ntext(ox, y0 + 30, short_steps[j])}</g>')
            an.show(f"#h{n}{j},#ns{n}{j}", t0, t1, 0.2)
        found = h[case]
        bad = [name for name, vol in found.items() if vol > h["min_volume_mm3"]]
        names = {"D6.4": "D6.4 counterbore", "D3.4": "D3.4 hole"}
        rows = [(f"{names[b]}: {fmt(vol, 1) + ' mm³ of rib' if vol else 'nothing'} inside", ORANGE if vol else INK)
                for b, vol in found.items()]
        rows.append((f"fail: over {fmt(h['min_volume_mm3'], 2)} mm³ in {len(bad)} bores", ORANGE) if bad else ("pass", INK))
        verdict = ntext(ox, y0 + 76, f"fail: rib in {len(bad)} bores" if bad else "pass: bores clear", 26,
                        ORANGE if bad else INK, weight="700")
        g.append(f'<g id="w{n}" opacity="0">{text(ox, y0 + 66, "the hole check has not run yet", 12, MUTED)}</g>')
        an.show(f"#w{n}", 0.3, t_probe + 0.2)
        for j, (s, colour) in enumerate(rows):
            last = j == len(rows) - 1
            g.append(f'<g id="v{n}{j}">{text(ox, y0 + 66 + 19 * j, s, 12, colour, weight="700" if last else None)}'
                     f'{verdict if last else ""}</g>')
            an.show(f"#v{n}{j}", t_probe + 0.5 + 0.3 * j, end)
        body += g + ["</g>"]
    label = ("Section through a screw hole in two build orders. When the rib is unioned after the clearance hole and "
             "counterbore are cut, it refills both, and the hole check finds "
             f"{fmt(h['after']['D6.4'], 1)} and {fmt(h['after']['D3.4'], 1)} cubic millimetres of rib inside them. "
             "When the holes are cut last, both are clear.")
    return svg(680, 460, label, body, an)


# ----------------------------------------------------------------------------- 3. connectors: plug through window

# tests/test_connectors.py: an RJ45 jack whose face is at w = 2, a 3 mm wall at w 3.5..6.5 (cut from a slab spanning
# u, v -20..40), and the bounding-box-style window that test uses as the bad case.
RJ45 = {"face": [0.0, 0.5, 16.0, 14.0], "face_w": 2.0, "centre_on": "receptacle", "clearance": 0.5,
        "plugs": [{"family": "rj45", "cavity": [2.0, 3.0, 14.0, 13.0]}]}
WALL = (3.5, 6.5)
SLAB = (-20.0, -20.0, 40.0, 40.0)
BBOX_WINDOW = [-0.5, -3.0, 16.5, 14.0]


def _box_volume(a, b) -> float:
    return math.prod(max(0.0, min(a[i + 3], b[i + 3]) - max(a[i], b[i])) for i in range(3))


def connector_numbers() -> dict:
    """The window, margins and insertion-sweep interference with the wall. The window and margins come from
    cadagent.mechanical.connectors. The sweep extends each plug segment to the plug's far end (connectors.envelope), and
    its shared volume with the box segments is exact."""
    from cadagent.mechanical import connectors as cn
    segs = cn.mate_segments(RJ45)
    far = max(s["w"][1] for s in segs)
    good = cn.window(RJ45, WALL)
    slab = (SLAB[0], SLAB[1], WALL[0], SLAB[2], SLAB[3], WALL[1])

    def hits(win):
        hole = (win[0], win[1], WALL[0] - 1, win[2], win[3], WALL[1] + 1)
        total = 0.0
        for s in segs:
            box = (s["u"][0], s["v"][0], s["w"][0], s["u"][1], s["v"][1], far)
            cut = tuple(max(p, q) for p, q in zip(box[:3], hole[:3])) + tuple(min(p, q) for p, q in zip(box[3:], hole[3:]))
            total += _box_volume(box, slab) - _box_volume(cut, slab)
        return total
    return {"segments": segs, "far": far, "good": good, "bad": BBOX_WINDOW,
            "passing": [s["what"] for s in cn.passing_segments(RJ45, WALL)],
            "margins": {"bad": cn.window_margins(RJ45, BBOX_WINDOW, WALL), "good": cn.window_margins(RJ45, good, WALL)},
            "interference_mm3": {"bad": hits(BBOX_WINDOW), "good": hits(good)}, "clearance": RJ45["clearance"]}


def connector_svg() -> str:
    h = connector_numbers()
    an = Anim(9.0)
    body = [text(20, 28, "Connector window: the mated plug swept in along its mating axis", 15, INK, weight="700"),
            ntext(20, 32, "Connector window sweep", 28, weight="700")]
    plug_body, boot = h["segments"]
    start, t_in, t_mated, end = 24.0, 0.8, 4.8, 7.8
    speed = start / (t_mated - t_in)
    t_at = lambda off: t_in + (start - off) / speed                # when the plug's offset along w is ``off``
    frames = [(0, (start, 0)), (0.3, (start, 1)), (t_in, (start, 1)), (t_mated, (0, 1)), (end, (0, 1)),
              (end + 0.4, (0, 0)), (end + 0.45, (start, 0)), (an.period, (start, 0))]
    k, w0, w1, v0, v1 = 8.6, -1.0, 25.0, -5.0, 19.0
    panels = [(34, "Window from the jack's bounding box", "From jack's box", "bad"),
              (374, "Window from the mated plug", "From mated plug", "good")]
    for n, (ox, title, short, case) in enumerate(panels):
        v = View(w0, v1, k, ox, 82)
        win = h[case]
        bottom = 82 + (v1 - v0) * k
        body.append(f'<clipPath id="c{n}"><rect x="{ox}" y="82" width="{num((w1 - w0) * k)}" '
                    f'height="{num((v1 - v0) * k)}"/></clipPath>')
        body.append(text(ox, 54, title, 13, INK, weight="600"))
        body.append(ntext(ox, 70, short, 24, weight="700"))
        body.append(text(ox, 72, f"window v {fmt(win[1])} to {fmt(win[3])} mm; the latch reaches "
                                 f"{fmt(plug_body['v'][1])}", 11, MUTED))
        g = [f'<g clip-path="url(#c{n})">']
        fx, fy0 = v(RJ45["face_w"], RJ45["face"][1])
        g.append(f'<path d="M{num(fx)} {num(fy0)}V{num(v(0, RJ45["face"][3])[1])}" stroke="{GREEN}" stroke-width="3"/>')
        g.append(text(fx - 7, fy0 - 8, "jack face", 10, MUTED, extra=f' transform="rotate(-90 {num(fx - 7)} {num(fy0 - 8)})"'))
        mid = (plug_body["v"][0] + plug_body["v"][1]) / 2
        g += [f'<g class="plug{n}">',
              f'<path d="{path(v.rect(boot["w"][0], boot["v"][0], boot["w"][1], boot["v"][1]))}" fill="{PALE}" '
              f'stroke="{GREEN}"/>',
              text(*v((boot["w"][0] + w1) / 2, mid - 0.5), "cable boot", 10, MUTED, "middle"),
              f'<path d="{path(v.rect(plug_body["w"][0], plug_body["v"][0], plug_body["w"][1], plug_body["v"][1]))}" '
              f'fill="{BG}" stroke="{INK}" stroke-width="1.5"/>',
              text(*v((plug_body["w"][0] + plug_body["w"][1]) / 2, mid + 0.6), "plug", 10, MUTED, "middle"),
              text(*v((plug_body["w"][0] + plug_body["w"][1]) / 2, mid - 1.0), "+ latch", 10, MUTED, "middle"), "</g>"]
        an.add(f".plug{n}", frames, lambda s: f"transform:translateX({num(s[0] * k)}px);opacity:{s[1]}", "linear")
        wall = f'fill="{PALE}" stroke="{INK}" stroke-width="1.5"'
        g.append(f'<path d="{path(v.rect(WALL[0], SLAB[1], WALL[1], win[1]))}" {wall}/>')
        g.append(f'<path d="{path(v.rect(WALL[0], win[3], WALL[1], SLAB[3]))}" {wall}/>')
        g.append(text(*v(WALL[1] + 0.7, v1 - 1.6), "wall", 10, MUTED))
        if h["interference_mm3"][case] > 0:
            band = v.rect(WALL[0], win[3], WALL[1], plug_body["v"][1])
            g.append(f'<path class="band" d="{path(band)}" fill="{ORANGE}"/>')
            # the swept latch fills the wall from its outer face inwards as the plug's front passes through it
            rx = num(v(WALL[1], 0)[0])
            front_in, front_out = WALL[1] - plug_body["w"][0], WALL[0] - plug_body["w"][0]
            an.css.append(f".band{{transform-origin:{rx}px 0;transform-box:view-box}}")
            an.add(".band", [(0, 0), (t_at(front_in), 0), (t_at(front_out), 1), (end, 1), (end + 0.4, 0),
                             (an.period, 0)], lambda s: f"transform:scaleX({s})", "linear")
        else:
            gx0, gx1 = v(WALL[0] - 0.8, 0)[0], v(WALL[1] + 0.8, 0)[0]
            for vv in (plug_body["v"][1], win[3]):
                g.append(f'<path d="M{num(gx0)} {num(v(0, vv)[1])}H{num(gx1)}" stroke="{ORANGE}"/>')
            g.append(text(*v(WALL[1] + 0.9, win[3] + 0.4), fmt(win[3] - plug_body["v"][1]), 10, ORANGE))
        g.append("</g>")
        body += g
        body.append(text(ox, bottom + 15, "← inside", 10, MUTED))
        body.append(text(ox + (w1 - w0) * k, bottom + 15, "outside →", 10, MUTED, "end"))
        m = h["margins"][case]
        vol = h["interference_mm3"][case]
        rows = ([(f"the sweep shares {fmt(vol, 2)} mm³ with the wall", ORANGE),
                 (f"top margin {fmt(m['margins_mm']['top'], 2)} mm: fail", ORANGE)] if vol > 0 else
                [("the sweep shares 0 mm³ with the wall", INK),
                 (f"smallest margin {fmt(m['min_margin_mm'], 2)} mm, clearance {fmt(h['clearance'], 1)}: pass", INK)])
        short_rows = ([(f"{fmt(vol, 1)} mm³ in wall", ORANGE), ("fail", ORANGE)] if vol > 0 else
                      [(f"clears by {fmt(m['min_margin_mm'], 1)} mm", INK), ("pass", INK)])
        for j, (s, colour) in enumerate(rows):
            narrow = ntext(ox, bottom + 30 + 30 * j, short_rows[j][0], 24 if j == 0 else 26, short_rows[j][1],
                           weight="700" if j else None)
            body.append(f'<g id="v{n}{j}">{text(ox, bottom + 38 + 18 * j, s, 12, colour, weight="600" if j else None)}'
                        f'{narrow}</g>')
            an.show(f"#v{n}{j}", t_mated + 0.2 + 0.3 * j, end, 0.3)
    label = ("An RJ45 plug pushed in along its mating axis through two panel windows. Through a window sized from the "
             f"jack's bounding box, the latch sweeps {fmt(h['interference_mm3']['bad'], 2)} cubic millimetres of wall. "
             f"Through the window derived from the mated plug, it clears with the {fmt(h['clearance'], 1)} mm clearance.")
    return svg(680, 360, label, body, an)


# ----------------------------------------------------------------------------- 4. assembly: a rigid module

# tests/test_gate_subassembly.py, fixture(): boxes (x0, y0, z0, x1, y1, z1), the fasteners, the module and the
# parent steps, run through the real kernel-free core (run_sequence) on exact box relations.
SUB_BOXES = {"base": (-1, 0, 0, 0, 3, 3), "carrier": (2, 0, 0, 3, 3, 3), "board": (1, 0, 0, 2, 3, 3),
             "board_screw": (.8, -.15, .75, 2.5, .35, 1.25), "retainer": (-.5, 1.9, 1.9, 3.2, 2.1, 2.1),
             "bumper": (4, 0, 0, 5, 3, 3)}
SUB_FASTENERS = {"board_screw": {"clamps": "board", "into": "carrier", "axes": [((1, .1, 1), (1, 0, 0))]},
                 "retainer": {"clamps": "carrier", "into": "base", "axes": [((3, 2, 2), (-1, 0, 0))]}}
SUB_MODULE = {"electronics": {"members": ["carrier", "board", "board_screw"], "steps": [
    {"order": 1, "fit": "carrier", "direction": "-Z"},
    {"order": 2, "fit": "board", "onto": "carrier", "direction": "+X", "fasteners": ["board_screw"]}]}}
SUB_STEPS = [{"order": 1, "fit": "base", "direction": "-Z"},
             {"order": 2, "fit": "electronics", "onto": "base", "direction": "-X", "fasteners": ["retainer"]},
             {"order": 3, "fit": "bumper", "onto": "base", "direction": "-Z"}]
SUB_SERVICE = {"electronics": ["bumper", "retainer"]}


def subassembly_numbers() -> dict:
    from cadagent.review.gates.assembly import AccessOptions, SequenceWorld, run_sequence
    from cadagent.review.gates.fasteners import FastenerSpec
    from cadagent.review.gates.relations import Relation, Tolerances

    class Boxes(SequenceWorld):
        """Exact relations of boxes (as tests/test_gate_assembly.py's BoxWorld), recording the exact queries."""

        def __init__(self, boxes, tol=Tolerances()):
            self.boxes, self.tol, self.names, self.queries = dict(boxes), tol, list(boxes), []

        def box(self, key):
            return self.boxes[key]

        def relate_at(self, key, shift, other):
            self.queries.append((key, other))
            a = [c + shift[i % 3] for i, c in enumerate(self.boxes[key])]
            b = self.boxes[other]
            span = [min(a[i + 3], b[i + 3]) - max(a[i], b[i]) for i in range(3)]
            if all(x > 0 for x in span) and math.prod(span) > self.tol.overlap_mm3:
                return Relation(key, other, "overlapping", gap_mm=0.0, overlap_mm3=math.prod(span))
            g = math.sqrt(sum(max(0.0, -x) ** 2 for x in span))
            return Relation(key, other, "touching" if g <= self.tol.touch_mm else "apart", gap_mm=g,
                            witness={"point_a": [0, 0, 0], "point_b": [0, 0, 0]})

        def tool(self, spec, i, tool_name, decl, present, step, later=()):
            return {"tool": tool_name, "step": step["order"], "present": list(present), "blocked": [], "clear": True}

    specs = {k: FastenerSpec(k, f["clamps"], f["into"], axes=f["axes"], tool="hex", head_h_mm=.2)
             for k, f in SUB_FASTENERS.items()}
    world = Boxes(SUB_BOXES)
    res = run_sequence(world, [dict(s) for s in SUB_STEPS], specs, subassemblies=json.loads(json.dumps(SUB_MODULE)),
                       tools={"hex": {"envelope_d": .2, "length": 10}}, service_after=SUB_SERVICE)
    checks = {c.id: c for c in res["checks"]}
    inner = res["subassemblies"]["electronics"]
    inner_step_2 = next(c for c in inner["checks"] if c["id"] == "step:2:insert")["message"]
    return {"result": res, "queries": world.queries, "margin_mm": AccessOptions().margin_mm,
            "failed": [i for i, c in checks.items() if c.status == "fail"],
            "qualified": checks["subassembly:electronics:qualified"].status, "bench_step_2": inner_step_2,
            "steps": res["steps"], "service": res["service_after"]["electronics"]}


def subassembly_svg() -> str:
    h = subassembly_numbers()
    an = Anim(15.0)
    k, v = 50.0, View(-1.7, 4.3, 50.0, 24, 74)
    steps = {s["order"]: s for s in h["steps"]}
    svc = h["service"]
    margin = h["margin_mm"]
    end = 13.9
    # timeline (s): bench 0.6..4.9, parent 5.2..9.6, service 10.6..end
    T = {"carrier": (0.6, 1.4), "board": (1.6, 2.5), "board_screw": (2.7, 3.4), "qualified": 3.6, "bench_out": (4.4, 4.9),
         "base": (5.2, 6.0), "module": (6.3, 7.5), "retainer": (7.8, 8.5), "bumper": (8.8, 9.6),
         "removed": (10.4, 10.8), "withdraw": (11.2, 12.4)}
    body = [text(20, 28, "A rigid module: its bench sequence first, then one parent step", 15, INK, weight="700"),
            text(20, 46, "the tests/test_gate_subassembly.py fixture through the assembly gate's own core (run_sequence)",
                 11, MUTED),
            ntext(20, 38, "A rigid module", 28, weight="700")]

    def rect(key, fill, stroke, w=1.5, dash=""):
        x0, _, z0, x1, _, z1 = SUB_BOXES[key]
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<path d="{path(v.rect(x0, z0, x1, z1))}" fill="{fill}" stroke="{stroke}" stroke-width="{w}"{d}/>'

    def name(key):
        x0, _, _, x1, _, z1 = SUB_BOXES[key]
        return text(*v((x0 + x1) / 2, z1 + 0.25), key, 11, MUTED, "middle")

    def slide(selector, dx, dz, t0, t1, away=None):
        """In from (dx, dz) mm to its seat over t0..t1, fading in; ``away`` = (t0, t1, dx) moves it off and out."""
        f = [(0, (dx, dz, 0)), (max(t0 - 0.3, 0), (dx, dz, 0)), (t0, (dx, dz, 1)), (t1, (0, 0, 1))]
        if away:
            f += [(away[0], (0, 0, 1)), (away[1], (away[2], 0, 1)), (away[1] + 0.3, (away[2], 0, 0))]
        else:
            f += [(end, (0, 0, 1)), (end + 0.4, (0, 0, 0))]
        f.append((an.period, (dx, dz, 0)))
        an.add(selector, f, lambda s: f"transform:translate({num(s[0] * k)}px,{num(-s[1] * k)}px);opacity:{s[2]}")

    # the bench: the members only, in the module's own frame
    out = (*T["bench_out"], 0)
    body.append(f'<g class="bc">{rect("carrier", BG, INK)}{name("carrier")}</g>'
                f'<g class="bb">{rect("board", BG, INK)}{name("board")}</g><g class="bs">{rect("board_screw", INK, INK, 1)}</g>')
    slide(".bc", 0, margin, *T["carrier"], out)
    slide(".bb", -margin, 0, *T["board"], out)
    slide(".bs", -margin, 0, *T["board_screw"], out)
    an.css.append(".bc,.bb,.bs{opacity:0}")
    # the parent: base, the module as one body, its retainer, the bumper; then the conditional withdrawal
    body.append(f'<g class="pb">{rect("base", PALE, GREEN)}{name("base")}</g>')
    slide(".pb", 0, margin, *T["base"])
    gx0, gz0 = v(0.62, -0.18)
    gx1, gz1 = v(3.18, 3.18)
    body.append(f'<g class="pm">{rect("carrier", BG, INK)}{rect("board", BG, INK)}{rect("board_screw", INK, INK, 1)}'
                f'{name("carrier")}{name("board")}'
                f'<rect x="{num(gx0)}" y="{num(gz1)}" width="{num(gx1 - gx0)}" height="{num(gz0 - gz1)}" rx="6" '
                f'fill="none" stroke="{ORANGE}" stroke-width="1.5" stroke-dasharray="5 4"/>'
                + text(*v(1.9, -0.55), "electronics: one rigid body", 11, ORANGE, "middle") + "</g>")
    slide(".pm", margin, 0, *T["module"], (*T["withdraw"], margin))
    body.append(f'<g class="pr">{rect("retainer", GREEN, INK, 1)}</g>')
    slide(".pr", margin, 0, *T["retainer"], (*T["removed"], 0))
    body.append(f'<g class="pu">{rect("bumper", PALE, GREEN)}{name("bumper")}</g>')
    slide(".pu", 0, margin, *T["bumper"], (*T["removed"], 0))
    # in the service step the assumed-removed parts are outlines only: the withdrawal is checked without them
    body.append(f'<g id="gone" opacity="0">{rect("bumper", "none", ORANGE, 1.5, "4 3")}'
                f'{rect("retainer", "none", ORANGE, 1.2, "3 2")}{name("bumper")}</g>')
    an.show("#gone", T["removed"][0], end)
    phases = [("On the bench: the module's members only", "1 · on the bench", 0.4, T["bench_out"][1]),
              ("In the parent: the module moves as one body", "2 · in the parent", T["base"][0], T["removed"][0]),
              ("Service: withdrawn with bumper and retainer assumed out", "3 · service", T["removed"][0], end)]
    for i, (s, short, t0, t1) in enumerate(phases):
        hidden = "" if i == 1 else ' opacity="0"'
        body.append(f'<g id="ph{i}"{hidden}>{text(24, 76, s, 12, INK, weight="600")}'
                    f'{ntext(24, 86, short, 26, weight="700")}</g>')
        an.show(f"#ph{i}", t0, t1)
    # the right column: the steps as the gate reports them, lit in turn
    rows = [("Bench: the members only", None, None, 0),
            ("1  carrier along −Z", *T["carrier"], 0),
            (f"2  board along +X, {h['bench_step_2'].split(', ')[-1]}", T["board"][0], T["board_screw"][1], 0),
            (f"module qualified: {h['qualified']}", T["qualified"], T["bench_out"][1], 1),
            ("Parent: the module is one part", None, None, 0),
            ("1  base along −Z", *T["base"], 0),
            ("2  electronics along −X, retainer", T["module"][0], T["retainer"][1], 0),
            (f"clear by at least {fmt(steps[2]['clearance_at_least_mm'], 1)} mm", T["module"][0], T["retainer"][1], 1),
            ("3  bumper along −Z", *T["bumper"], 0),
            ("Service: withdrawal (conditional)", None, None, 0),
            (f"{' and '.join(svc['assumed_removed'])} assumed removed", T["removed"][0], end - 0.4, 1),
            (f"withdraws along +X: {svc['status']}", T["withdraw"][0], end - 0.4, 1),
            ("removing those two is not verified", T["withdraw"][1], end - 0.4, 1)]
    y = 72
    for i, (s, t0, t1, indent) in enumerate(rows):
        if t0 is None:
            y += 8 if i else 0
            body.append(text(434, y, s, 12, INK, weight="700"))
        else:
            body.append(f'<rect id="h{i}" class="w" x="428" y="{y - 13}" width="238" height="18" rx="4" fill="{PEACH}" '
                        'opacity="0"/>')
            an.show(f"#h{i}", t0, t1, 0.2)
            body.append(text(434 + 16 * indent, y, s, 11.5, INK))
        y += 19
    # the narrow layout: the gate's three findings, large, each from the moment it is established
    findings = [(f"bench: {h['qualified']}", INK, T["qualified"]),
                (f"fitted, ≥ {fmt(steps[2]['clearance_at_least_mm'], 1)} mm", INK, T["retainer"][1]),
                (f"withdraws: {svc['status']}", ORANGE, T["withdraw"][1]),
                (f"if {len(svc['assumed_removed'])} parts out", ORANGE, T["withdraw"][1])]
    for i, (s, colour, t0) in enumerate(findings):
        body.append(f'<g id="nf{i}">{ntext(434, 132 + 40 * i + (0 if i < 3 else -8), s, fill=colour)}</g>')
        an.show(f"#nf{i}", t0, end)
    label = ("A preassembled module, a carrier and a board with its screw, is first checked on its own bench sequence. "
             "It then goes into the parent as one rigid body along minus X, and the retainer and bumper follow. "
             "With the bumper and retainer assumed removed, the module withdraws along plus X.")
    return svg(680, 352, label, body, an)


# ----------------------------------------------------------------------------- 5. explore: the search's trials

EXAMPLE = ROOT / "examples" / "explore-two-wheel"


def search_numbers() -> dict:
    """Runs the worked example's configured search (``cad-agent optimise``: seeded random trials) in a scratch copy,
    and ranks the trials seen so far after each one, as the leaderboard does."""
    from cadagent.simulation.explore.catalogue import load_configured
    from cadagent.simulation.explore.compare import rank
    from cadagent.simulation.explore.config import explore_config
    from cadagent.simulation.explore.evaluate import load_evaluator
    from cadagent.simulation.explore.optimise import run_search, search_config
    from cadagent.project import load_project
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / EXAMPLE.name
        shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("exports", "*.png"))
        project = load_project(root)
        cfg = explore_config(project.root, project.explore, project.title)
        catalogue, _ = load_configured(cfg)
        evaluator = load_evaluator(cfg.evaluator, project.root, project.python)
        sc = search_config(cfg, catalogue)
        summary = run_search(cfg, catalogue, evaluator, progress=lambda s: None)
        lines = (cfg.out / "search" / "trials.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    seen, fronts = [], []
    for r in records:
        if not r.get("duplicate_of"):
            seen.append(dict(r["evaluation"], trial=r["trial"]))
        fronts.append(sorted(e["trial"] for e in rank(seen, cfg.objectives) if e["pareto"]))
    return {"records": records, "fronts": fronts, "objectives": [(o.metric, o.goal) for o in cfg.objectives],
            "sampler": sc.sampler, "seed": sc.seed, "summary": summary}


def search_svg() -> str:
    h = search_numbers()
    recs, fronts = h["records"], h["fronts"]
    value = lambda r, m: r["evaluation"]["metrics"][m]["value"]
    an = Anim(14.0)
    x0, x1, y0, y1 = 74, 652, 282, 76              # plot box: cost along x, mass up y
    unique = [r for r in recs if not r.get("duplicate_of")]
    by_trial = {r["trial"]: r for r in unique}
    costs = [value(r, "cost_usd") for r in unique]
    masses = [value(r, "mass_kg") for r in unique]
    c_lo, c_hi = math.floor(min(costs) / 250) * 250, math.ceil(max(costs) / 250) * 250
    m_lo, m_hi = math.floor(min(masses)), math.ceil(max(masses))
    X = lambda c: x0 + (c - c_lo) * (x1 - x0) / (c_hi - c_lo)
    Y = lambda m: y0 - (m - m_lo) * (y0 - y1) / (m_hi - m_lo)
    arrive = {r["trial"]: 0.6 + i * 0.16 for i, r in enumerate(recs)}
    last_arrival = max(arrive.values())
    end = 12.9
    feasible = {r["trial"] for r in unique if r["evaluation"].get("verdict") in ("ok", "warn")}
    body = [text(20, 28, "Search: the worked example's trials arriving, and the Pareto front they form", 15, INK, weight="700"),
            text(20, 46, f"examples/explore-two-wheel, cad-agent optimise: {len(recs)} {h['sampler']} trials, seed "
                         f"{h['seed']}; illustrative parts and prices", 11, MUTED),
            ntext(20, 40, f"Search: {len(recs)} trials", 28, weight="700"),
            ntext(x0 + 8, y1 + 26, "↑ mass", fill=MUTED), ntext(x1, y0 + 34, "cost →", fill=MUTED, anchor="end")]
    for c in range(math.ceil(c_lo / 500) * 500, int(c_hi) + 1, 500):
        body.append(f'<path d="M{num(X(c))} {y1}V{y0}" stroke="{LINE}"/>')
        body.append(text(X(c), y0 + 16, f"{c:,}", 10, MUTED, "middle"))
    for m in range(int(m_lo), int(m_hi) + 1, 2):
        body.append(f'<path d="M{x0} {num(Y(m))}H{x1}" stroke="{LINE}"/>')
        body.append(text(x0 - 6, Y(m) + 3.5, str(m), 10, MUTED, "end"))
    body.append(text((x0 + x1) / 2, y0 + 32, "cost (USD, estimate)", 11, MUTED, "middle"))
    body.append(text(24, (y0 + y1) / 2, "mass (kg)", 11, MUTED, "middle",
                     extra=f' transform="rotate(-90 24 {num((y0 + y1) / 2)})"'))
    # every evaluated trial appears when it arrives; the group fades at the loop's end
    layers = {True: [], False: []}
    for r in unique:
        t = r["trial"]
        layers[t in feasible].append(f'<circle id="p{t}" cx="{num(X(value(r, "cost_usd")))}" '
                                     f'cy="{num(Y(value(r, "mass_kg")))}" r="{4.5 if t in feasible else 4}"/>')
        a = arrive[t]
        an.add(f"#p{t}", [(0, 0), (a, 0), (a + 0.15, 1)], lambda o: f"opacity:{o}", name_only=True)
    an.css.append(f".pts circle{{animation:{num(an.period)}s linear infinite}}")
    body.append(f'<g class="pts"><g fill="{BG}" stroke="{GREEN}" stroke-width="1.4">{"".join(layers[False])}</g>'
                f'<g fill="{INK}">{"".join(layers[True])}</g></g>')
    an.add(".pts", [(0, 1), (end, 1), (end + 0.5, 0), (an.period - 0.05, 0), (an.period, 1)],
           lambda o: f"opacity:{o}", "linear")
    # a repeat of an earlier combination is not evaluated again: the earlier point pulses
    reps = []
    for r in recs:
        if r.get("duplicate_of"):
            d = by_trial[r["duplicate_of"]]
            reps.append(f'<circle cx="{num(X(value(d, "cost_usd")))}" cy="{num(Y(value(d, "mass_kg")))}" r="9" '
                        f'style="animation-delay:{num(arrive[r["trial"]], 2)}s"/>')
    body.append(f'<g class="rep" fill="none" stroke="{MUTED}" stroke-width="1.2">{"".join(reps)}</g>')
    an.css.append("@keyframes rep{0%{opacity:.9;transform:scale(.45)}5%{opacity:0;transform:scale(1)}100%{opacity:0}}"
                  f".rep circle{{opacity:0;transform-box:fill-box;transform-origin:center;"
                  f"animation:rep {num(an.period)}s ease-out infinite}}")
    # the front as it stood after each trial: each member marked with what it is best at among the feasible trials.
    # The front is over three objectives and the plot shows two, so no line joins the members: one can be on the
    # front for runtime alone, beside a cheaper and lighter design
    changes = [(i, f) for i, f in enumerate(fronts) if i == 0 or f != fronts[i - 1]]
    at = lambda j: arrive[recs[changes[j][0]]["trial"]] + 0.1 if j < len(changes) else end
    spans = [(at(j), at(j + 1), f) for j, (_, f) in enumerate(changes)]
    names = {"cost_usd": "cost", "mass_kg": "mass", "runtime_min": "runtime"}
    best = {m: (min if goal == "min" else max)(value(by_trial[t], m) for t in feasible) for m, goal in h["objectives"]}

    def best_at(t):
        won = [m for m, _ in h["objectives"] if value(by_trial[t], m) == best[m]]
        return " and ".join(names.get(m, m) for m in won) or "a trade-off"
    for t in sorted({t for f in fronts for t in f}):
        member = [(on, off) for on, off, f in spans if t in f]
        if any(a[1] != b[0] for a, b in zip(member, member[1:])):
            raise ValueError(f"trial {t} left the front and came back: the figure draws one stretch per trial")
        r = by_trial[t]
        cx, cy = X(value(r, "cost_usd")), Y(value(r, "mass_kg"))
        won = best_at(t)
        detail = (f", {fmt(value(r, 'runtime_min'), 0)} min" if "runtime" in won else "")
        body.append(f'<g id="ff{t}"><circle cx="{num(cx)}" cy="{num(cy)}" r="7" fill="{ORANGE}" stroke="{BG}" stroke-width="2"/>'
                    + text(cx + 11, cy - 9, f"trial {t}: best {won}{detail}", 11, ORANGE, weight="600", halo=True)
                    + ntext(cx + 12, cy + 8, f"{t}: best {won}", fill=ORANGE, weight="700", halo=True) + "</g>")
        an.show(f"#ff{t}", member[0][0], member[-1][1])
    # progress, legend and the run's summary
    an.css.append(".bar{transform-box:fill-box;transform-origin:left}")
    an.add(".bar", [(0, 0), (arrive[recs[0]["trial"]], 0), (last_arrival, 1), (end, 1), (end + 0.5, 0), (an.period, 0)],
           lambda s: f"transform:scaleX({num(s, 3)})", "linear")
    body.append(f'<rect x="{x0}" y="58" width="{x1 - x0}" height="4" rx="2" fill="{LINE}"/>'
                f'<rect class="bar" x="{x0}" y="58" width="{x1 - x0}" height="4" rx="2" fill="{GREEN}"/>')
    ly = 340
    legend = [(f'<circle cx="0" cy="0" r="4" fill="{BG}" stroke="{GREEN}" stroke-width="1.4"/>', "infeasible"),
              (f'<circle cx="0" cy="0" r="4.5" fill="{INK}"/>', "feasible, dominated"),
              (f'<circle cx="0" cy="0" r="6" fill="{ORANGE}"/>', "front over cost, mass, runtime"),
              (f'<circle cx="0" cy="0" r="6" fill="none" stroke="{MUTED}" stroke-width="1.2"/>', "a repeat")]
    lx = x0
    for mark, s in legend:
        body.append(f'<g class="w" transform="translate({lx} {ly})">{mark}{text(10, 4, s, 11, MUTED)}</g>')
        lx += 26 + 6.1 * len(s)
    n_rep = len(recs) - len(unique)
    summary = (f"{len(recs)} trials ({len(unique)} evaluated, {n_rep} repeats), {len(feasible)} feasible, "
               f"{len(fronts[-1])} on the front")
    body.append(f'<g id="sum">{text(x1, ly + 22, summary, 12, INK, "end", "600")}'
                f'{ntext(x1, ly + 14, f"{len(feasible)} feasible, {len(fronts[-1])} on the front", anchor="end", weight="700")}</g>')
    an.show("#sum", last_arrival + 0.2, end)
    label = (f"The worked example's {len(recs)} seeded random trials plotted by cost and mass as they arrive. "
             f"{len(feasible)} are feasible and {len(fronts[-1])} form the Pareto front over cost, mass and runtime: "
             + " and ".join(f"trial {t}" for t in fronts[-1]) + ".")
    return svg(680, 376, label, body, an)


# ----------------------------------------------------------------------------- 6. connectors: the cable behind the plug

# tests/test_connectors.py: the same RJ45 port and wall, a Cat6 patch cord (Belden's data sheet: 6.1 mm, minimum bend
# radius 25 mm) and the shelf the enclosure stands on. The figure runs the real check: the obstacles are boxes in the
# panel frame, which cable_bend measures without a CAD kernel.
CAT6 = {"od": 6.1, "min_bend_radius": {"mm": 25.0},
        "basis": "Belden CAT6+ UTP PVC patch cord, technical data rev 0.202 (2025-02-07): nominal diameter 6.1 mm, "
                 "min bend radius (overall cable) 25 mm"}
SHELF = {"u": [-60.0, 80.0], "v": [-30.0, -20.0], "w": [-40.0, 120.0]}


def cable_numbers() -> dict:
    """``cable_bend`` on the port of the connector figure, with the window derived from the plug cut in the wall."""
    from cadagent.mechanical import connectors as cn
    mate = dict(RJ45, cable=CAT6)
    u0, v0, u1, v1 = cn.window(RJ45, WALL)
    su0, sv0, su1, sv1 = SLAB
    wall = [{"u": [su0, su1], "v": [sv0, v0], "w": list(WALL)}, {"u": [su0, su1], "v": [v1, sv1], "w": list(WALL)},
            {"u": [su0, u0], "v": [v0, v1], "w": list(WALL)}, {"u": [u1, su1], "v": [v0, v1], "w": list(WALL)}]
    result = cn.cable_bend(mate, {"wall": wall, "shelf": SHELF})
    spec = cn.cable_spec(mate)
    rows = {r["direction"]: r for r in result["directions"]}
    paths = {name: cn.bend_path(result["exit"], rows[name]["uv"], spec["centreline_radius_mm"], spec["turn_deg"])
             for name in ("-v", "+v")}
    return {"mate": mate, "segments": cn.mate_segments(mate), "window": [u0, v0, u1, v1], "result": result,
            "rows": rows, "paths": paths, "spec": spec}


def cable_svg() -> str:
    h = cable_numbers()
    res, spec, rows = h["result"], h["spec"], h["rows"]
    od, rc, radius = spec["od"], spec["centreline_radius_mm"], spec["radius_mm"]
    reach = res["reach_mm"]["beside"]
    ue, ve, we = res["exit"]
    plug_body, boot = h["segments"]
    shelf_top = SHELF["v"][1]
    an = Anim(10.0)
    body = [text(20, 28, "Cable bend: the cable behind the plug turned at its minimum radius", 15, INK, weight="700"),
            ntext(20, 32, "Cable bend radius", 28, weight="700")]
    k, w0, w1, v0, v1, oy = 3.8, -2.0, 76.0, -26.0, 43.0, 86
    t_seat, t_grow, t_grown, end = 1.4, 1.8, 4.6, 9.0
    length = rc * math.radians(spec["turn_deg"]) * k + 1          # the arc on the page, and a little more
    an.add(".pl", [(0, (10, 0)), (0.3, (10, 1)), (t_seat, (0, 1)), (end, (0, 1)), (end + 0.4, (0, 0)),
                   (an.period, (10, 0))], lambda s: f"transform:translateX({num(s[0] * k)}px);opacity:{s[1]}")
    an.add(".cb", [(0, length), (t_grow, length), (t_grown, 0), (end + 0.4, 0), (end + 0.45, length),
                   (an.period, length)], lambda s: f"stroke-dashoffset:{num(s)}", "linear")
    panels = [(34, "-v", "Turned down, towards the shelf", "Turned down",
               f"needs {fmt(reach, 1)} mm below its axis; the shelf is {fmt(ve - shelf_top, 2)} below"),
              (366, "+v", "Turned up", "Turned up", f"needs {fmt(reach, 1)} mm above its axis; nothing is there")]
    for n, (ox, name, title, short, sub) in enumerate(panels):
        v = View(w0, v1, k, ox, oy)
        row, p = rows[name], h["paths"][name]
        width, height = (w1 - w0) * k, (v1 - v0) * k
        body.append(f'<clipPath id="c{n}"><rect x="{ox}" y="{oy}" width="{num(width)}" height="{num(height)}"/></clipPath>')
        body.append(text(ox, 56, title, 13, INK, weight="600"))
        body.append(ntext(ox, 68, short, 24, weight="700"))
        body.append(text(ox, 74, sub, 11, MUTED))
        g = [f'<g clip-path="url(#c{n})">']
        g.append(f'<path d="{path(v.rect(w0, v0, w1, shelf_top))}" fill="{PALE}" stroke="{INK}" stroke-width="1.5"/>')
        g.append(text(*v(w0 + 1.2, shelf_top - 4.6), "shelf", 10, MUTED))
        # the cable: drawn first, so the boot hides the round end that the check's balls give it inside the boot
        sx, sy = v(*p["start"][2:0:-1])
        ex, ey = v(p["end"][2], p["end"][1])
        arc = f'M{num(sx)} {num(sy)}A{num(rc * k)} {num(rc * k)} 0 0 {1 if name == "-v" else 0} {num(ex)} {num(ey)}'
        dash = f'fill="none" stroke-linecap="round" stroke-dasharray="{num(length)} {num(length)}" class="cb"'
        g.append(f'<path d="{arc}" stroke="{INK}" stroke-width="{num(od * k + 2.4)}" {dash}/>')
        g.append(f'<path d="{arc}" stroke="#c9d6cc" stroke-width="{num(od * k)}" {dash}/>')
        if not row["clear"]:
            body.append(f'<clipPath id="s{n}"><path d="{path(v.rect(w0, v0, w1, shelf_top))}"/></clipPath>')
            g.append(f'<path d="{arc}" stroke="{ORANGE}" stroke-width="{num(od * k)}" {dash} '
                     f'clip-path="url(#s{n})"/>')
        wall = f'fill="{PALE}" stroke="{INK}" stroke-width="1.5"'
        g.append(f'<path d="{path(v.rect(WALL[0], SLAB[1], WALL[1], h["window"][1]))}" {wall}/>')
        g.append(f'<path d="{path(v.rect(WALL[0], h["window"][3], WALL[1], SLAB[3]))}" {wall}/>')
        g.append(text(*v(WALL[1] + 0.7, v1 - 2.6), "wall", 10, MUTED))
        fx = v(RJ45["face_w"], 0)[0]
        g.append(f'<path d="M{num(fx)} {num(v(0, RJ45["face"][1])[1])}V{num(v(0, RJ45["face"][3])[1])}" '
                 f'stroke="{GREEN}" stroke-width="3"/>')
        g += ['<g class="pl">',
              f'<path d="{path(v.rect(boot["w"][0], boot["v"][0], boot["w"][1], boot["v"][1]))}" fill="{PALE}" '
              f'stroke="{GREEN}"/>',
              text(*v((boot["w"][0] + boot["w"][1]) / 2, ve - 1.2), "boot", 10, MUTED, "middle"),
              f'<path d="{path(v.rect(plug_body["w"][0], plug_body["v"][0], plug_body["w"][1], plug_body["v"][1]))}" '
              f'fill="{BG}" stroke="{INK}" stroke-width="1.5"/>', "</g>"]
        # the bend's centre and its inside radius, which the data sheet states
        cx, cy = v(p["centre"][2], p["centre"][1])
        s = -p["direction"][1]                                    # from the centre, the arc lies against the turn
        at = lambda f, deg: v(p["centre"][2] + f * radius * math.cos(math.radians(deg)),          # noqa: E731
                              p["centre"][1] + s * f * radius * math.sin(math.radians(deg)))
        ix, iy = at(1, 45)
        mx, my = at(0.5, 45)
        lx, ly = mx - 6, my + (6 if s < 0 else -2) * 1.0
        g.append(f'<g id="r{n}"><path d="M{num(cx - 4)} {num(cy)}h8M{num(cx)} {num(cy - 4)}v8M{num(cx)} {num(cy)}'
                 f'L{num(ix)} {num(iy)}" stroke="{INK}" stroke-width="1.2"/>'
                 f'{text(lx, ly + 4, f"R {fmt(radius, 0)} inside", 10, MUTED, "end")}</g>')
        an.show(f"#r{n}", t_grown + 0.2, end)
        if not row["clear"]:
            depth = -row["clearance_mm"]
            g.append(f'<g id="d{n}">{text(*v(p["end"][2] - 4.4, shelf_top + 1.4), f"{fmt(depth, 2)} mm in", 10, ORANGE, "end")}</g>')
            an.show(f"#d{n}", t_grown, end)
        else:
            # its nearest part: the shelf, under the cable where it leaves the boot (tests check this is the gap)
            x, ya = v(we, ve - od / 2)
            yb = v(we, shelf_top)[1]
            g.append(f'<g id="d{n}"><path d="M{num(x)} {num(ya)}V{num(yb)}M{num(x - 4)} {num(ya)}h8M{num(x - 4)} '
                     f'{num(yb)}h8" stroke="{ORANGE}"/>'
                     f'{text(x + 4, (ya + yb) / 2 + 4, fmt(row["clearance_mm"], 1), 10, ORANGE)}</g>')
            an.show(f"#d{n}", t_grown, end)
        g.append("</g>")
        body += g
        bottom = oy + height
        clear = row["clear"]
        sign = lambda d: d.replace("-", "−")                     # noqa: E731
        others = [sign(d) for d in res["works"] if d != res["direction"]]
        rows_text = ([(f"turned {short.split()[1]} ({sign(name)}): {fmt(-row['clearance_mm'], 2)} mm into the "
                       f"{row['nearest']}", ORANGE), ("fail: this way it does not fit", ORANGE)] if not clear else
                     [(f"turned {short.split()[1]} ({sign(name)}): clear, {fmt(row['clearance_mm'], 1)} mm from the "
                       f"{row['nearest']}", INK),
                      (f"{res['status']}: turn {sign(res['direction'])}"
                       + (f" ({' and '.join(others)} clear too)" if others else ""), INK)])
        short_rows = ([(f"{fmt(-row['clearance_mm'], 1)} mm into shelf", ORANGE), ("fail", ORANGE)] if not clear else
                      [("clear", INK), (res["status"], INK)])
        for j, (line, colour) in enumerate(rows_text):
            narrow = ntext(ox, bottom + 30 + 30 * j, short_rows[j][0], 24 if j == 0 else 26, short_rows[j][1],
                           weight="700" if j else None)
            body.append(f'<g id="v{n}{j}">{text(ox, bottom + 22 + 18 * j, line, 12, colour, weight="600" if j else None)}'
                        f'{narrow}</g>')
            an.show(f"#v{n}{j}", t_grown + 0.4 + 0.3 * j, end)
    down, up = rows["-v"], rows["+v"]
    label = (f"An RJ45 plug seated in its jack, and its Cat6 cable, {fmt(od, 1)} mm across, leaving the boot and turning "
             f"at its {fmt(radius, 0)} mm minimum bend radius. Turned down, it needs {fmt(reach, 1)} mm below its axis "
             f"and the shelf is {fmt(ve - shelf_top, 2)} mm below, so it runs {fmt(-down['clearance_mm'], 2)} mm into "
             f"the shelf. Turned up, it clears; the nearest part is the shelf, {fmt(up['clearance_mm'], 1)} mm away. "
             f"The check passes, turning {res['direction']}.")
    return svg(680, oy + int(round((v1 - v0) * k)) + 66, label, body, an)


FIGURES = {"hinge-sweep.svg": hinge_svg, "rib-in-counterbore.svg": counterbore_svg,
           "connector-window.svg": connector_svg, "cable-bend.svg": cable_svg, "module-insertion.svg": subassembly_svg,
           "search-front.svg": search_svg}


def main(argv: list) -> int:
    stale = []
    for name, make in FIGURES.items():
        content, target = make(), OUT / name
        if "--check" in argv:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                stale.append(name)
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    if stale:
        print("out of date with their sources (run PYTHONPATH=src python3 tools/motion_figures.py):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
