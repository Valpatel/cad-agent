#!/usr/bin/env python3
"""Regenerate the animated concept figures (docs/img/motion/*.svg) from the code and fixtures they illustrate.

    PYTHONPATH=src python3 tools/motion_figures.py            # write the SVGs
    PYTHONPATH=src python3 tools/motion_figures.py --check    # exit 1 if a committed SVG differs (tests run this)

Nothing is keyframed by eye. Each figure draws one fixture or worked example from this repo:

* where the real code runs without CadQuery, the figure runs it:
  - the assembly-sequence core (``run_sequence``) on the subassembly fixture, and its insertion sweep
    (``sweep_pair``) on the box world of the assembly gate's tests;
  - the motion-trace validator (``validate_motion_trace``) on its tests' analytic shaft and renderer;
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


def box_world(boxes: dict):
    """A ``SequenceWorld`` of axis-aligned boxes (x0, y0, z0, x1, y1, z1) whose relations are exact, as
    tests/test_gate_assembly.py's ``BoxWorld``. ``queries`` records each exact query: (key, shift, other, relation)."""
    from cadagent.review.gates.assembly import SequenceWorld
    from cadagent.review.gates.relations import Relation, Tolerances

    class Boxes(SequenceWorld):
        def __init__(self, tol=Tolerances()):
            self.boxes, self.tol, self.names, self.queries = dict(boxes), tol, list(boxes), []

        def box(self, key):
            return self.boxes[key]

        def relate_at(self, key, shift, other):
            a = [c + shift[i % 3] for i, c in enumerate(self.boxes[key])]
            b = self.boxes[other]
            span = [min(a[i + 3], b[i + 3]) - max(a[i], b[i]) for i in range(3)]
            if all(x > 0 for x in span) and math.prod(span) > self.tol.overlap_mm3:
                lo = [max(a[i], b[i]) for i in range(3)]
                rel = Relation(key, other, "overlapping", gap_mm=0.0, overlap_mm3=math.prod(span),
                               witness={"overlap_centroid": [lo[i] + span[i] / 2 for i in range(3)]})
            else:
                g = math.sqrt(sum(max(0.0, -x) ** 2 for x in span))
                rel = Relation(key, other, "touching" if g <= self.tol.touch_mm else "apart", gap_mm=g,
                               witness={"point_a": [0, 0, 0], "point_b": [0, 0, 0]})
            self.queries.append((key, tuple(shift), other, rel))
            return rel

        def tool(self, spec, i, tool_name, decl, present, step, later=()):
            return {"tool": tool_name, "step": step["order"], "present": list(present), "blocked": [], "clear": True}
    return Boxes()


def subassembly_numbers() -> dict:
    from cadagent.review.gates.assembly import AccessOptions, run_sequence
    from cadagent.review.gates.fasteners import FastenerSpec

    specs = {k: FastenerSpec(k, f["clamps"], f["into"], axes=f["axes"], tool="hex", head_h_mm=.2)
             for k, f in SUB_FASTENERS.items()}
    world = box_world(SUB_BOXES)
    res = run_sequence(world, [dict(s) for s in SUB_STEPS], specs, subassemblies=json.loads(json.dumps(SUB_MODULE)),
                       tools={"hex": {"envelope_d": .2, "length": 10}}, service_after=SUB_SERVICE)
    checks = {c.id: c for c in res["checks"]}
    inner = res["subassemblies"]["electronics"]
    inner_step_2 = next(c for c in inner["checks"] if c["id"] == "step:2:insert")["message"]
    return {"result": res, "queries": [(q[0], q[2]) for q in world.queries], "margin_mm": AccessOptions().margin_mm,
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
        wall = f'fill="{PALE}" stroke="{INK}" stroke-width="1.5"'
        g.append(f'<path d="{path(v.rect(WALL[0], SLAB[1], WALL[1], h["window"][1]))}" {wall}/>')
        g.append(f'<path d="{path(v.rect(WALL[0], h["window"][3], WALL[1], SLAB[3]))}" {wall}/>')
        g.append(text(*v(WALL[1] + 0.7, v1 - 2.6), "wall", 10, MUTED))
        fx = v(RJ45["face_w"], 0)[0]
        g.append(f'<path d="M{num(fx)} {num(v(0, RJ45["face"][1])[1])}V{num(v(0, RJ45["face"][3])[1])}" '
                 f'stroke="{GREEN}" stroke-width="3"/>')
        # the plug and its cable, one group, so they fade as one. The cable comes first: the boot hides the round end
        # that the check's balls give it inside the boot. It is drawn along its bend by its dash offset.
        sx, sy = v(*p["start"][2:0:-1])
        ex, ey = v(p["end"][2], p["end"][1])
        arc = f'M{num(sx)} {num(sy)}A{num(rc * k)} {num(rc * k)} 0 0 {1 if name == "-v" else 0} {num(ex)} {num(ey)}'
        dash = f'fill="none" stroke-linecap="round" stroke-dasharray="{num(length)} {num(length)}" class="cb"'
        g += ['<g class="pl">', f'<path d="{arc}" stroke="{INK}" stroke-width="{num(od * k + 2.4)}" {dash}/>',
              f'<path d="{arc}" stroke="#c9d6cc" stroke-width="{num(od * k)}" {dash}/>']
        if not row["clear"]:
            body.append(f'<clipPath id="s{n}"><path d="{path(v.rect(w0, v0, w1, shelf_top))}"/></clipPath>')
            g.append(f'<path d="{arc}" stroke="{ORANGE}" stroke-width="{num(od * k)}" {dash} '
                     f'clip-path="url(#s{n})"/>')
        g += [f'<path d="{path(v.rect(boot["w"][0], boot["v"][0], boot["w"][1], boot["v"][1]))}" fill="{PALE}" '
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
        short_rows = ([(f"{fmt(-row['clearance_mm'], 2)} mm into shelf", ORANGE), ("fail", ORANGE)] if not clear else
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


# ----------------------------------------------------------------------------- 7. motion trace: captures against the CAD

# tests/test_motion_trace.py, contract(): the analytic shaft. The yaw joint turns the housing about Z through
# (10, 20, 30); the spin joint rides on it and turns the rotor about X through (40, 20, 30); the base stands still.
# MT_OFFSET is its 'offset-pivot' defect: the renderer spins the rotor about a pivot 48 mm off the shaft, in +Y.
MT_CONTRACT = {"schema_version": 1, "length_unit": "mm", "frame": "assembly-home",
               "reference": "synthetic analytic shaft: yaw datum (10,20,30), rotor datum (40,20,30)",
               "joints": {"yaw": {"parent": None, "pivot": [10, 20, 30], "axis": [0, 0, 1], "range_deg": [-90, 90]},
                          "spin": {"parent": "yaw", "pivot": [40, 20, 30], "axis": [1, 0, 0], "range_deg": [0, 360]}},
               "components": {
                   "rotor": {"joint": "spin", "points": [[40, 20, 30], [41, 20, 30], [40, 22, 30], [40, 20, 33]]},
                   "housing": {"joint": "yaw", "points": [[35, 20, 30], [35, 25, 30], [35, 20, 35], [45, 20, 30]]},
                   "base": {"joint": None, "points": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]}}}
MT_OFFSET = 48.0


def mt_render(angles: dict, offset: float = 0.0) -> dict:
    """The test's independent renderer (``observation()``): the points it draws for each component at ``angles``.
    It spins the rotor about the shaft, moved ``offset`` mm in +Y (its 'offset-pivot' defect at 48), then turns
    the rotor and housing about the yaw axis. It reads no matrix from the validator."""
    (yx, yy, _), (_, sy, sz) = MT_CONTRACT["joints"]["yaw"]["pivot"], MT_CONTRACT["joints"]["spin"]["pivot"]
    out = {}
    for name, comp in MT_CONTRACT["components"].items():
        pts = []
        for x, y, z in comp["points"]:
            if name == "rotor":
                a, py = math.radians(angles["spin"]), sy + offset
                y, z = py + (y - py) * math.cos(a) - (z - sz) * math.sin(a), sz + (y - py) * math.sin(a) + (z - sz) * math.cos(a)
            if comp["joint"] is not None:
                a, cx, cy = math.radians(angles["yaw"]), x - yx, y - yy
                x, y = yx + cx * math.cos(a) - cy * math.sin(a), yy + cx * math.sin(a) + cy * math.cos(a)
            pts.append([x, y, z])
        out[name] = pts
    return out


def motion_trace_numbers() -> dict:
    """``validate_motion_trace`` on the required poses as two renderers capture them: as built (A) and with the
    rotor's pivot 48 mm off (B); each sample alone too (its coverage fails, its landmark errors are the validator's),
    and A without the nested pose. The reference points are the validator's own: each joint's matrix applied to the
    home landmarks."""
    from cadagent.mechanical import motion_trace as mt
    c = json.loads(json.dumps(MT_CONTRACT))
    poses = mt.required_poses(c)
    joints, comps, order = mt._contract(c)

    def reference(p):
        mats = mt._matrices(joints, order, p)
        return {n: mt._apply(mats[comp["joint"]], comp["points"]).tolist() for n, comp in comps.items()}

    def trace(offset, keep=lambda p: True):
        return {"schema_version": 1, "length_unit": "mm", "frame": "assembly-home",
                "capture_source": "independent analytic test renderer",
                "samples": [{"id": str(i), "angles_deg": p, "components": mt_render(p, offset)}
                            for i, p in enumerate(poses) if keep(p)]}
    out = {"poses": poses, "reference": [reference(p) for p in poses], "tolerance_mm": inspect.signature(
        mt.validate_motion_trace).parameters["tolerance_mm"].default}
    for key, offset in (("A", 0.0), ("B", MT_OFFSET)):
        t = trace(offset)
        out[key] = {"report": mt.validate_motion_trace(c, t), "points": [s["components"] for s in t["samples"]],
                    "per_pose_mm": [max(r["max_error_mm"] for r in mt.validate_motion_trace(
                        c, dict(t, samples=[s]))["components"].values()) for s in t["samples"]]}
    nested = [i for i, p in enumerate(poses) if all(p.values())]
    out["nested"] = nested
    out["without_nested"] = mt.validate_motion_trace(c, trace(0.0, lambda p: not all(p.values())))
    return out


class Ortho:
    """An orthographic view of the home frame (SVG x right, y down): looking down at ``el`` degrees from the +X side,
    so the shaft (X) runs down the page, Y across it and Z up, ``k`` units per mm, (0, 0, 0) at (ox, oy)."""

    def __init__(self, el: float, k: float, ox: float = 0.0, oy: float = 0.0):
        self.s, self.c, self.k, self.ox, self.oy = math.sin(math.radians(el)), math.cos(math.radians(el)), k, ox, oy

    def __call__(self, p):
        return self.ox + self.k * p[1], self.oy + self.k * (self.s * p[0] - self.c * p[2])


def motion_trace_svg() -> str:
    h = motion_trace_numbers()
    poses, n, tol = h["poses"], len(h["poses"]), h["tolerance_mm"]
    bad = h["B"]["report"]["components"]["rotor"]
    still, nest = int(bad["worst_sample"]), h["nested"][0]          # the still frame: renderer B's worst sample
    yaw, spin = MT_CONTRACT["joints"]["yaw"], MT_CONTRACT["joints"]["spin"]
    px, py, pz = yaw["pivot"]
    turn = [p["yaw"] for p in poses]
    an = Anim(15.0)
    T = [0.75 + 1.2 * i for i in range(n)]                          # each pose is reached at T[i], after a move
    end, move, k, el, top = 14.1, 0.3, 4.2, 64, 84                  # (whole percentages of the 15 s loop)
    # the window: every landmark, drawn and expected, at every pose but B's nested one, which runs off the bottom
    pts = [Ortho(el, k)(q) for i in range(n) for key in ("A", "B") for comp in h[key]["points"][i].values() for q in comp
           if not (key == "B" and i == nest)]
    x0, x1, y0, y1 = (f(p[j] for p in pts) for j in (0, 1) for f in (min, max))
    v = Ortho(el, k, 340 - (x0 + x1) / 2, top + 14 - y0)
    bottom = top + 14 + (y1 - y0) + 12
    P = v((px, py, pz))

    def timeline(selector, values, decl, timing="ease-in-out", rest=None):
        """``selector`` takes ``values[i]`` at pose i, moving over the ``move`` before T[i]. Its own style, the still
        frame, is ``rest`` if given, else its value at the still pose."""
        if len(set(values)) == 1:
            return
        frames = [(0, values[0])]
        for i, val in enumerate(values):
            frames += [(max(T[i] - move, 0), values[i - 1] if i else val), (T[i], val)]
        frames += [(end, values[-1]), (end + 0.6, values[0]), (an.period, values[0])]
        # a keyframe between two with its own value changes nothing
        frames = [f for j, f in enumerate(frames) if j in (0, len(frames) - 1) or not
                  frames[j - 1][1] == f[1] == frames[j + 1][1]]
        an.add(selector, frames, decl, timing)
        if rest is not None or decl(values[still]) != decl(0 if not isinstance(values[0], tuple) else (0, 0)):
            an.css.append(f"{selector}{{{decl(values[still] if rest is None else rest)}}}")
    # the yaw, as a turn of everything it carries about its axis: drawn in the yaw's own frame (u across, w down the
    # shaft, from the pivot, unforeshortened), foreshortened by sin(el) and set on the page at the pivot's height
    timeline(".yw", [-t for t in turn], lambda d: f"transform:rotate({num(d)}deg)")

    def frame(z):
        return f'matrix(1 0 0 {num(v.s, 4)} {num(P[0])} {num(P[1] - v.c * k * (z - pz))})'

    def uw(q):
        return k * (q[1] - py), k * (q[0] - px)
    layers = {"r": {}, "a": {}, "b": {}}

    def mark(key, ident, where, carried, r):
        """One landmark: ``where`` its point at each pose. A carried one is turned back by the pose's yaw into the
        yaw's frame, where it moves only as the spin moves it; its height, which the yaw does not change, moves
        outside the turn."""
        if not carried:
            x, y = v(where[still])
            layers[key].setdefault(None, []).append(f'<circle cx="{num(x)}" cy="{num(y)}" r="{r}"/>')
            return
        q = [(*rotate(p[:2], -t, (px, py)), p[2]) for p, t in zip(where, turn)]
        u0, w0 = uw(q[still])
        moves = [(round(uw(p)[0] - u0, 1) + 0.0, round(uw(p)[1] - w0, 1) + 0.0) for p in q]
        lift = [round(-v.c * k * (p[2] - q[still][2]), 1) + 0.0 for p in q]
        own = f' id="{ident}"' if len(set(moves)) > 1 else ""
        circle = f'<circle{own} cx="{num(u0)}" cy="{num(w0)}" r="{r}"/>'
        timeline(f"#{ident}", moves, lambda d: f"transform:translate({num(d[0])}px,{num(d[1])}px)")
        outer = f"z{ident}" if len(set(lift)) > 1 else None
        timeline(f"#z{ident}", lift, lambda d: f"transform:translateY({num(d)}px)")
        layers[key].setdefault((outer, frame(q[still][2])), []).append(circle)
    for name, comp in MT_CONTRACT["components"].items():
        for j in range(len(comp["points"])):
            for key, src, r in (("r", h["reference"], 4.6), ("a", h["A"]["points"], 2.6), ("b", h["B"]["points"], 1.7)):
                mark(key, f"{key}{name[0]}{j}", [s_[name][j] for s_ in src], comp["joint"] is not None, r)

    def draw(groups):
        out = []
        for key, circles in groups.items():
            if key is None:
                out += circles
                continue
            outer, mat = key
            g = f'<g transform="{mat}"><g class="yw">{"".join(circles)}</g></g>'
            out.append(f'<g id="{outer}">{g}</g>' if outer else g)
        return "".join(out)

    body = [text(20, 28, "Motion trace: what a renderer draws, against the CAD, at every required pose", 15, INK,
                 weight="700"),
            text(20, 46, "the analytic shaft of tests/test_motion_trace.py through validate_motion_trace, with two "
                         "renderers capturing the same poses", 11, MUTED),
            ntext(20, 38, "Motion trace", 28, weight="700"),
            f'<clipPath id="sc"><rect x="20" y="{top - 24}" width="640" height="{num(bottom - top + 24)}"/></clipPath>',
            f'<rect x="20" y="{top - 24}" width="640" height="{num(bottom - top + 24)}" rx="8" fill="none" '
            f'stroke="{LINE}"/>']
    legend = [(f'<circle cx="0" cy="-4" r="4.6" fill="none" stroke="{GREEN}" stroke-width="1.4"/>',
               "where the CAD puts a landmark"),
              (f'<circle cx="0" cy="-4" r="2.6" fill="{INK}"/>', "where renderer A drew it"),
              (f'<circle cx="0" cy="-4" r="1.7" fill="{ORANGE}"/>', f"renderer B: its spin pivot {fmt(MT_OFFSET, 0)} mm "
                                                                     "off the shaft")]
    lx = 34
    for mk, s_ in legend:
        body.append(f'<g class="w" transform="translate({num(lx)} {top - 4})">{mk}{text(9, 0, s_, 11, MUTED)}</g>')
        lx += 22 + 5.9 * len(s_)
    body.append('<g clip-path="url(#sc)">')
    # the arc the housing's far end sweeps over the yaw's range, and the yaw axis
    far = MT_CONTRACT["components"]["housing"]["points"][3]
    R = k * math.dist(far[:2], (px, py))
    body.append(f'<path d="M{num(P[0] - R)} {num(P[1])}A{num(R)} {num(R * v.s)} 0 0 0 {num(P[0] + R)} {num(P[1])}" '
                f'fill="none" stroke="{LINE}" stroke-width="2"/>')
    body.append(f'<path d="M{num(P[0] - 7)} {num(P[1])}h14M{num(P[0])} {num(P[1] - 7 - v.c * k * 8)}v{num(14 + v.c * k * 8)}" '
                f'stroke="{MUTED}"/>')
    body.append(text(P[0] + 9, P[1] - 6, "yaw axis", 10, MUTED))
    # in the yaw's frame: the housing joined up through its landmarks at the pivot's height, on its arm, and the shaft
    hp = [uw(q) for q in MT_CONTRACT["components"]["housing"]["points"] if q[2] == pz]
    s0, s1 = uw((spin["pivot"][0] - 9, py)), uw((spin["pivot"][0] + 9, py))
    body.append(f'<g transform="{frame(pz)}"><g class="yw" fill="none">'
                f'<path d="M0 0L{num(hp[0][0])} {num(hp[0][1])}" stroke="{LINE}" stroke-width="3"/>'
                f'<path d="{path(hp)}" fill="{PALE}" stroke="{GREEN}"/>'
                f'<path d="M{num(s0[0])} {num(s0[1])}V{num(s1[1])}" stroke="{INK}" stroke-dasharray="7 2 1.5 2"/></g></g>')
    # B's pivot, and the circle it puts the rotor on (across the shaft: seen from this angle, an ellipse)
    bp = (spin["pivot"][0], spin["pivot"][1] + MT_OFFSET, spin["pivot"][2])
    c = v(bp)
    l0, l1 = v((bp[0] - 9, bp[1], bp[2])), v((bp[0] + 9, bp[1], bp[2]))
    spins = [i for i, p in enumerate(poses) if p["spin"] and not p["yaw"]]
    body.append(f'<g id="bp" opacity="0"><g fill="none" stroke="{ORANGE}"><ellipse cx="{num(c[0])}" cy="{num(c[1])}" '
                f'rx="{num(MT_OFFSET * k)}" ry="{num(MT_OFFSET * k * v.c)}" stroke-dasharray="4 4"/>'
                f'<path d="M{num(l0[0])} {num(l0[1])}V{num(l1[1])}" stroke-width="1.5" stroke-dasharray="7 2 1.5 2"/></g>'
                + text(l0[0] + 6, l0[1] + 8, f"B's spin pivot, {fmt(MT_OFFSET, 0)} mm off the shaft", 10, ORANGE)
                + ntext(l0[0] + 8, l0[1] + 16, "B's pivot", 24, ORANGE) + "</g>")
    timeline("#bp", [1 if i in spins else 0 for i in range(n)], lambda o: f"opacity:{o}", "linear")
    # names, while the yaw is home
    hx, hy = v(MT_CONTRACT["components"]["housing"]["points"][1])
    rx, ry = v(spin["pivot"])
    body.append(f'<g id="nm">{text(hx + 9, hy + 4, "housing (on the yaw)", 10, MUTED)}'
                f'{text(rx - 16, ry + 4, "rotor (spins on the housing)", 10, MUTED, "end")}</g>')
    timeline("#nm", [0 if t else 1 for t in turn], lambda o: f"opacity:{o}", "linear")
    bx, by = v(MT_CONTRACT["components"]["base"]["points"][0])
    body.append(text(bx + 10, by + 4, "base", 10, MUTED))
    body += [f'<g fill="none" stroke="{GREEN}" stroke-width="1.4">{draw(layers["r"])}</g>',
             f'<g fill="{INK}">{draw(layers["a"])}</g>', f'<g fill="{ORANGE}">{draw(layers["b"])}</g>']
    # B's rotor at the nested pose is off the bottom of the window
    nb = v(h["B"]["points"][nest]["rotor"][0])
    off = fmt(h["B"]["per_pose_mm"][nest], 1)
    note = text(max(nb[0] - 12, 30), bottom - 8, f"↓ B draws the rotor {off} mm off, below this view", 11, ORANGE,
                weight="700", halo=True)
    body.append(f'<g id="nb" opacity="0">{note}</g>')
    timeline("#nb", [1 if i == nest else 0 for i in range(n)], lambda o: f"opacity:{o}", "linear")
    body.append("</g>")

    # the required poses as a table, the current one lit, each renderer's worst landmark shown once it is reached
    ty, cw, cx0 = bottom + 26, 52.0, 140.0
    xs = [cx0 + cw * i + cw / 2 for i in range(n)]
    rows = [("yaw, °", [fmt(p["yaw"], 0) for p in poses]), ("spin, °", [fmt(p["spin"], 0) for p in poses]),
            ("A: worst, mm", [fmt(e, 1) for e in h["A"]["per_pose_mm"]]),
            ("B: worst, mm", [fmt(e, 1) for e in h["B"]["per_pose_mm"]])]
    body.append(f'<rect class="w cur" x="{num(cx0 + 1)}" y="{num(ty - 13)}" width="{num(cw - 2)}" height="83" rx="4" '
                f'fill="{PEACH}"/>')
    timeline(".cur", [cw * i for i in range(n)], lambda d: f"transform:translateX({num(d)}px)")
    body.append(text(20, ty, f"the {n} required poses", 12, INK, weight="600"))
    body.append(text(xs[nest], ty, "nested", 11, INK, "middle", "700"))
    for j, (label, vals) in enumerate(rows):
        y = ty + 18 + 16 * j
        body.append(text(20, y, label, 11, ORANGE if j == 3 else MUTED))
        cells = "".join(f'<tspan x="{num(xs[i])}"' + (f' fill="{ORANGE}" font-weight="700"' if j == 3 and
                        h["B"]["per_pose_mm"][i] > tol else "") + f">{escape(s_)}</tspan>" for i, s_ in enumerate(vals))
        body.append(f'<text y="{num(y)}" font-size="11" text-anchor="middle">{cells}</text>')
    # the errors are covered until their pose is reached: a cover over the two rows, shrinking to the right
    right = cx0 + cw * n
    an.css.append(f".cov{{transform-origin:{num(right)}px 0;transform-box:view-box}}")
    timeline(".cov", [(n - 1 - i) / n for i in range(n)], lambda f: f"transform:scaleX({num(f, 3)})", "steps(1,end)",
             rest=0)
    body.append(f'<rect class="w cov" x="{num(cx0)}" y="{num(ty + 38)}" width="{num(cw * n)}" height="33" fill="{BG}"/>')
    lines = [(INK, f"A: pass. At all {n} poses, every landmark is within {fmt(tol, 2)} mm of where the CAD puts it."),
             (ORANGE, f"B: fail (rendered-landmarks). Its rotor is {fmt(bad['max_error_mm'], 1)} mm off at spin "
                      f"{fmt(poses[still]['spin'], 0)}°, and its pivot {fmt(bad['max_anchor_error_mm'], 1)} mm off."),
             (MUTED, "Without the nested pose, A fails too (pose-coverage): yaw "
                     f"{fmt(poses[nest]['yaw'], 0)}° with spin {fmt(poses[nest]['spin'], 0)}° is missing.")]
    vy = ty + 104
    for i, (colour, s_) in enumerate(lines):
        body.append(f'<g id="v{i}">{text(20, vy + 19 * i, s_, 12, colour, weight="600" if i < 2 else None)}</g>')
        an.show(f"#v{i}", T[-1] + 0.45 + 0.3 * i, end)
    for i, (s_, colour) in enumerate([(f"{n} poses, 1 nested", INK), ("A: pass", INK),
                                      (f"B: fail, {fmt(bad['max_error_mm'], 0)} mm off", ORANGE)]):
        body.append(ntext(20, ty + 16 + 36 * i, s_, 26, colour, weight="700" if i else None))
    label = (f"The analytic shaft from the motion-trace tests at its {n} required poses: the yaw turns the housing, the "
             "spin turns the rotor on it, and one nested pose has both turned. Rings mark where the CAD puts each "
             "landmark. Renderer A's points sit in them at every pose, and it passes. Renderer B spins the rotor about "
             f"a pivot {fmt(MT_OFFSET, 0)} mm off the shaft, so its rotor is up to {fmt(bad['max_error_mm'], 0)} mm "
             "off, and it fails.")
    return svg(680, int(vy + 19 * 2 + 20), label, body, an)


# ----------------------------------------------------------------------------- 8. assembly: one insertion, swept

# tests/test_gate_assembly.py: BOXES (a base, a block on it, a card standing against the block's side, a cover over
# both), the card moved 3 mm off the block (the clearance test's ``near``), and the clearance test's diagonal
# approach past a block, which it also runs with max_step_mm = 5. Boxes (x0, y0, z0, x1, y1, z1), mm.
GATE_BOXES = {"base": (0, 0, 0, 100, 100, 5), "block": (10, 10, 5, 30, 30, 25), "card": (30, 10, 5, 32, 30, 20),
              "cover": (0, 0, 25, 40, 40, 30)}
GATE_NEAR_CARD = (33, 10, 5, 35, 30, 20)
GATE_DIAGONAL = {"part": (0, 0, 0, 10, 10, 10), "block": (-30, 0, 5, -20, 10, 15)}
GATE_DIAGONAL_DIRECTION, GATE_DIAGONAL_STEP_MM = (1, 0, -1), 5.0


def sweep_watch(boxes: dict, key: str, direction, other: str, **options) -> dict:
    """``sweep_pair`` on a box world, watched. A spy on its ``box_distance`` sees the swept box (the first call)
    and each position it steps to on the line (``s``, from the part's shift); the world records its exact queries:
    the seat first, then the positions within reach, then the bisection. Nothing in the gate is replaced."""
    from unittest import mock
    from cadagent.review.gates import assembly as ga
    world, real, boxes_seen = box_world(boxes), ga.box_distance, []

    def spy(a, b):
        g = real(a, b)
        boxes_seen.append((tuple(a), g))
        return g
    d = ga.direction_vector(direction)
    back = tuple(-c for c in d)
    with mock.patch.object(ga, "box_distance", spy):
        res = ga.sweep_pair(world, key, d, other, options=ga.AccessOptions(**options))
    pb = boxes[key]
    exact = {tuple(round(c, 9) for c in q[1]): q[3] for q in world.queries}
    visits = []
    for box, g in boxes_seen[1:]:
        shift = tuple(box[i] - pb[i] for i in range(3))
        rel = exact.get(tuple(round(c, 9) for c in shift))
        visits.append({"s": sum(a * b for a, b in zip(shift, back)), "box_gap": g, "exact": rel is not None,
                       "gap": rel.gap_mm if rel is not None and not rel.interferes else (None if rel else g),
                       "overlap_mm3": rel.overlap_mm3 if rel is not None and rel.interferes else None})
    seat = world.queries[0][3] if world.queries and not any(world.queries[0][1]) else None
    n_loop = sum(v["exact"] for v in visits)
    bisect = [(sum(a * b for a, b in zip(q[1], back)), q[3].interferes) for q in world.queries[(seat is not None) + n_loop:]]
    return {"result": res, "swept": boxes_seen[0][0], "swept_gap": boxes_seen[0][1], "visits": visits,
            "seat_gap": seat.gap_mm if seat is not None else None, "bisect": bisect, "direction": d, "back": back,
            "queries": len(world.queries)}


def sweep_numbers() -> dict:
    """The three pairs the figure draws, and what the gate reads from them. For the sampled pair, the bound between
    each two neighbouring positions h apart, (g1 + g2 - h) / 2, whose least is the gate's ``gap_lower_bound_mm``;
    and the exact gap all along the line, which the gate does not compute, to show the bound holds."""
    from cadagent.review.gates.assembly import AccessOptions
    from cadagent.review.gates.relations import Tolerances
    near = sweep_watch(dict(GATE_BOXES, card=GATE_NEAR_CARD), "card", "-Z", "block")
    blocked = sweep_watch(GATE_BOXES, "card", "-Z", "cover")
    diag = sweep_watch(GATE_DIAGONAL, "part", GATE_DIAGONAL_DIRECTION, "block", max_step_mm=GATE_DIAGONAL_STEP_MM)
    line = [(v["s"], v["gap"]) for v in diag["visits"]] + [(0.0, diag["seat_gap"])]
    bounds = [(s1, s2, g1, g2, max(0.0, (g1 + g2 - (s1 - s2)) / 2)) for (s1, g1), (s2, g2) in zip(line, line[1:])]
    world, travel = box_world(GATE_DIAGONAL), diag["visits"][0]["s"]

    def gap(s):
        return world.relate_at("part", tuple(s * c for c in diag["back"]), "block").gap_mm
    # the gap between convex parts is convex in the shift, so a ternary search finds the closest approach
    lo, hi = 0.0, travel
    for _ in range(200):
        a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        lo, hi = (lo, b) if gap(a) < gap(b) else (a, hi)
    closest = ((lo + hi) / 2, gap((lo + hi) / 2))
    true = sorted([(s, gap(s)) for s in (travel * i / 24 for i in range(25))] + [closest], reverse=True)
    return {"near": near, "blocked": blocked, "diagonal": diag, "line": line, "bounds": bounds, "true": true,
            "closest": closest, "touch_mm": Tolerances().touch_mm, "options": AccessOptions()}


def _closest(a, b):
    """The closest points of two disjoint boxes, in X and Z (their Y spans overlap in every pair drawn here)."""
    pa, pb = [], []
    for i in (0, 2):
        if a[i + 3] < b[i]:
            pa.append(a[i + 3]), pb.append(b[i])
        elif b[i + 3] < a[i]:
            pa.append(a[i]), pb.append(b[i + 3])
        else:
            m = (max(a[i], b[i]) + min(a[i + 3], b[i + 3])) / 2
            pa.append(m), pb.append(m)
    return pa, pb


def sweep_svg() -> str:
    h = sweep_numbers()
    near, blk, dg = h["near"], h["blocked"], h["diagonal"]
    an = Anim(16.0)
    end = 15.0
    body = [text(20, 28, "Assembly gate: one part moved in along a straight line, against one other part", 15, INK,
                 weight="700"),
            text(20, 46, "sweep_pair on the box world of tests/test_gate_assembly.py, seen from the side. s: how far "
                         "the part is from its seat", 11, MUTED),
            ntext(20, 38, "Insertion sweep", 28, weight="700")]
    solid = f'fill="{PALE}" stroke="{GREEN}"'

    def moved(box, s, back):
        return tuple(box[i] + s * back[i % 3] for i in range(6))

    def rect(v, box, attrs):
        (a, b), (c, d) = v(box[0], box[5]), v(box[3], box[2])
        return f'<rect x="{num(a)}" y="{num(b)}" width="{num(c - a)}" height="{num(d - b)}" {attrs}/>'

    def panel(ox, y, title, short, sub):
        body.extend([text(ox, y, title, 13, INK, weight="600"), ntext(ox, y + 6, short, 26, weight="700"),
                     text(ox, y + 16, sub, 11, MUTED)])

    def lines(ident, ox, y, rows, t0):
        body.append(f'<g id="{ident}">' + "".join(text(ox, y + 16 * i, s_, 12 if bold else 11, colour, weight="600" if bold
                                                       else None) for i, (s_, colour, bold) in enumerate(rows)) + "</g>")
        an.show(f"#{ident}", t0, end)

    def steps(selector, offsets, times, decl):
        """``selector`` moves to ``offsets[i]`` over the 0.3 s before ``times[i]``, holds the last, and returns."""
        frames = [(0, offsets[0])]
        for i, o in enumerate(offsets):
            frames += [(times[i] - 0.3, offsets[max(i - 1, 0)]), (times[i], o)]
        an.add(selector, frames + [(end, offsets[-1]), (end + 0.4, offsets[0]), (an.period, offsets[0])], decl)
        an.css.append(f"{selector}{{{decl(offsets[-1])}}}")

    # 1. the near card: the box it sweeps from its start to its seat stays 3 mm from the block's: no query
    y = 72
    v = View(5, 42.5, 3.0, 24, y + 24)
    card, block = GATE_NEAR_CARD, GATE_BOXES["block"]
    travel = near["result"]["travel_mm"]
    start, sw = moved(card, travel, (0, 0, 1)), near["swept"]
    panel(20, y, "1 · Far: the swept box is enough", "Far", "the card, 3 mm off the block, in along −Z")
    an.css.append(f".sw{{transform-origin:0 {num(v(0, sw[5])[1])}px;transform-box:view-box}}")
    an.add(".sw", [(0, 0), (0.4, 0), (1.6, 1), (end, 1), (end + 0.4, 0), (an.period, 0)],
           lambda f: f"transform:scaleY({num(f, 3)})")
    (tx, ty0), (_, ty1) = v(38, card[2]), v(38, start[2])
    body += [rect(v, block, solid), text(*v(20, 13), "block", 11, MUTED, "middle"),
             rect(v, sw, f'class="sw" fill="{PEACH}" stroke="{ORANGE}" stroke-dasharray="4 3"'),
             rect(v, card, f'fill="{BG}" stroke="{INK}" stroke-width="1.5"'),
             rect(v, start, f'fill="none" stroke="{INK}" stroke-dasharray="3 2"'),
             f'<path d="M{num(tx)} {num(ty0)}V{num(ty1)}m-3 5l3 -5 3 5" fill="none" stroke="{MUTED}"/>',
             text(tx + 5, ty1 + 6, "start", 10, MUTED), text(tx + 5, ty0, "seat", 10, MUTED),
             text(tx + 5, (ty0 + ty1) / 2 + 4, f"travel {fmt(travel, 0)}", 10, MUTED)]
    (gx0, gy), (gx1, _) = v(block[3], 9), v(sw[0], 9)
    body.append(f'<g id="d1"><path d="M{num(gx0)} {num(gy)}H{num(gx1)}M{num(gx0)} {num(gy - 4)}v8M{num(gx1)} {num(gy - 4)}v8" '
                f'stroke="{ORANGE}"/>{text(gx0 - 3, gy + 4, fmt(near["swept_gap"], 2), 10, ORANGE, "end", "700")}</g>')
    an.show("#d1", 1.7, end)
    lines("l1", 20, 240, [(f"it starts 1 mm past the block: travel {fmt(travel, 0)} mm", MUTED, False),
                    (f"its swept box stays {fmt(near['swept_gap'], 2)} mm from the block's", INK, False),
                    (f"clear, ≥ {fmt(near['result']['gap_lower_bound_mm'], 2)} mm, with "
                     f"{near['result']['samples']} queries", INK, True)], 1.9)
    body.append(ntext(20, 252, f"clear, {near['result']['samples']} queries", 24))

    # 2. the card into the cover fitted first: exact samples, the hit, and the first contact bisected
    ox = 352
    v = View(12, 47, 2.6, ox + 4, y + 30)
    card, cover = GATE_BOXES["card"], GATE_BOXES["cover"]
    panel(ox, y, "2 · Blocked: the contact bisected", "Blocked", "the card, with the cover fitted first")
    hits = blk["visits"]
    t3 = [3.4 + 0.7 * i for i in range(len(hits) + 1)]
    hit = moved(card, hits[-1]["s"], (0, 0, 1))
    body += [rect(v, (12, 0, cover[2], cover[3], 0, cover[5]), solid), text(*v(20, 26.3), "cover", 10, MUTED, "middle"),
             rect(v, card, f'fill="none" stroke="{INK}" stroke-dasharray="3 2"'), text(*v(31, -0.5), "seat", 10, MUTED, "middle")]
    steps(".cd", [v(0, vis["s"])[1] - v(0, 0)[1] for vis in hits], t3[1:], lambda o: f"transform:translateY({num(o)}px)")
    body.append(rect(v, card, f'class="cd" fill="{BG}" stroke="{INK}" stroke-width="1.5"'))
    shared = rect(v, (hit[0], 0, hit[2], hit[3], 0, cover[5]), f'fill="{ORANGE}"')
    body.append(f'<g id="ov">{shared}</g>')
    an.show("#ov", t3[-1], end)
    said = [f"seat first: gap {fmt(blk['seat_gap'], 2)}"] + [
        f"s {fmt(vis['s'], 0)}: " + (f"{fmt(vis['overlap_mm3'], 0)} mm³ shared, a hit" if vis["overlap_mm3"] else
                                    "touching" if vis["gap"] <= h["touch_mm"] else f"gap {fmt(vis['gap'], 2)}")
        for vis in hits]
    lx = ox + 100
    for i, s_ in enumerate(said):
        body.append(text(lx, y + 40 + 16 * i, s_, 11, ORANGE if i == len(hits) else INK, extra=f' id="q{i}"'))
        an.show(f"#q{i}", t3[i], end)
    # the bracket [last clear, first hit], halved refine_steps times towards the contact; s falls to the right
    s_hit, s_clear = hits[-1]["s"], hits[-2]["s"]
    widths, lo, hi = [], s_hit, s_clear
    for mid, inside in blk["bisect"]:
        lo, hi = (mid, hi) if inside else (lo, mid)
        widths.append((hi - lo) / (s_clear - s_hit))
    bx0, bx1, by = lx, lx + 150, y + 136
    tb = t3[-1] + 0.5
    an.css.append(f".br{{transform-origin:{num(bx0)}px 0;transform-box:view-box;transform:scaleX({num(widths[-1], 4)})}}")
    an.add(".br", [(0, 1), (tb, 1)] + [(tb + 0.12 * (j + 1), w) for j, w in enumerate(widths)]
           + [(end, widths[-1]), (end + 0.4, 1), (an.period, 1)], lambda w: f"transform:scaleX({num(w, 4)})", "steps(1,end)")
    body.append(f'<g id="bb" class="w">{text(bx0, by - 12, f"[{fmt(s_clear, 0)}, {fmt(s_hit, 0)}] halved {len(widths)} times", 11, INK)}'
                f'<path d="M{bx0} {by}H{bx1}" stroke="{LINE}" stroke-width="8"/>'
                f'<rect class="br" x="{bx0}" y="{by - 4}" width="{bx1 - bx0}" height="8" fill="{ORANGE}"/>'
                f'<path d="M{bx0} {by - 7}v14" stroke="{INK}" stroke-width="1.5"/>'
                + text(bx0, by + 17, f"s {fmt(s_clear, 0)}", 10, MUTED, "middle") + text(bx1, by + 17, fmt(s_hit, 0), 10, MUTED, "middle")
                + "</g>")
    an.show("#bb", tb - 0.3, end)
    first = blk["result"]["first_contact_mm"]
    lines("l2", ox, 240, [("its swept box meets the cover's, so it is sampled", MUTED, False),
                    (f"first contact between s {fmt(first[1], 4)} and {fmt(first[0], 4)}", INK, False),
                    (f"blocked {fmt(first[0], 2)} mm before its seat, {blk['result']['samples']} queries", ORANGE, True)],
          tb + 0.12 * len(widths) + 0.3)
    body.append(ntext(ox, 252, f"hits {fmt(first[0], 0)} mm out", 24, ORANGE, weight="700"))

    # 3. the diagonal approach: steps of the gap, exact samples within max_step_mm, the bound between neighbours
    y = 298
    v = View(-31.5, 39.5, 3.0, 24, y + 30)
    part, other = GATE_DIAGONAL["part"], GATE_DIAGONAL["block"]
    panel(20, y, "3 · Near: sampled, with a bound between samples", "Near",
          f"a part past a block's corner, in along (1, 0, −1); max_step_mm = {fmt(GATE_DIAGONAL_STEP_MM, 0)}")
    visits = dg["visits"]
    t2 = [8.6 + 0.7 * i for i in range(len(visits) + 2)]       # the seat (queried first), the visits, the seat again
    ghosts, dots, vees = [], [], []
    for i, vis in enumerate(visits):
        box = moved(part, vis["s"], dg["back"])
        pa, pb = _closest(box, other)
        (ax, ay), (bx, by) = v(*pa), v(*pb)
        dash = "" if vis["exact"] else ' stroke-dasharray="3 2"'
        ghosts.append(f'<g id="p{i}">' + rect(v, box, f'fill="none" stroke="{GREEN}"{dash}')
                      + f'<path d="M{num(ax)} {num(ay)}L{num(bx)} {num(by)}" stroke="{ORANGE if vis["exact"] else GREEN}" '
                        f'stroke-width="1.5"{dash}/></g>')
        an.show(f"#p{i}", t2[i + 1], end)
    body += [rect(v, other, solid), text(*v(-25, 1.4), "block", 10, MUTED, "middle"), *ghosts,
             rect(v, part, f'fill="none" stroke="{INK}" stroke-dasharray="3 2"'), text(*v(5, -3.6), "seat", 10, MUTED, "middle")]
    sx, sy = v(part[0], part[5])
    pos = [moved(part, vis["s"], dg["back"]) for vis in visits] + [part]
    steps(".mv", [(v(b[0], b[5])[0] - sx, v(b[0], b[5])[1] - sy) for b in pos], t2[1:],
          lambda o: f"transform:translate({num(o[0])}px,{num(o[1])}px)")
    body.append(rect(v, part, f'class="mv" fill="none" stroke="{INK}" stroke-width="2"'))
    # the gap along the way: each position's gap, the bound between neighbours (the V under each pair), and the
    # exact gap all along, which the gate never computes (dashed), staying between the bound and the least sample
    s_max, px0, px1, base, ky = visits[0]["s"], 196, 640, y + 150, 5.4
    kx = (px1 - px0) / s_max
    P = lambda s_, g: (px0 + (s_max - s_) * kx, base - g * ky)      # noqa: E731
    pt = lambda s_, g: f"{num(P(s_, g)[0])} {num(P(s_, g)[1])}"     # noqa: E731
    order = [len(visits)] + list(range(len(visits)))                # h["line"] runs start to seat; the seat came first
    for j, i in enumerate(order):
        s_, g = h["line"][i]
        exact = i == len(visits) or visits[i]["exact"]
        x_, y_ = P(s_, g)
        c = INK if exact else GREEN
        dot = f'<circle cx="{num(x_)}" cy="{num(y_)}" r="2.8"' + ("" if exact else f' fill="{BG}" stroke="{GREEN}"') + "/>"
        label = text(x_, y_ - 7, fmt(g, 2) + (" seat" if i == len(visits) else ""), 10, c,
                     "end" if x_ > px1 - 20 else "middle", extra=' class="h"')
        dots.append(f'<g id="g{i}">{dot}{label}</g>')
        an.show(f"#g{i}", t2[0] if j == 0 else t2[i + 1], end)
        if i:       # the bound between this position and the one before; the seat's last, once the loop is done
            s1, s2, g1, g2, b = h["bounds"][i - 1]
            vees.append(f'<path id="v{i}" d="M{pt(s1, g1)}L{pt((s1 + s2 + g2 - g1) / 2, b)}L{pt(s2, g2)}"/>')
            an.show(f"#v{i}", t2[i + 1], end)
    body += [f'<g fill="none" stroke="{GREEN}">{"".join(vees)}</g>', *dots]
    low = min(h["bounds"], key=lambda r: r[4])
    lb = P((low[0] + low[1] + low[3] - low[2]) / 2, low[4])
    an.css.append(f".h{{font-weight:700;stroke:{BG};stroke-width:3px;paint-order:stroke}}")
    (hx0, _), (hx1, _) = P(low[0], 0), P(low[1], 0)
    cx_, cy_ = P(low[0] + 2, 17)
    body.append(f'<g id="lb"><circle cx="{num(lb[0])}" cy="{num(lb[1])}" r="3.4" fill="{ORANGE}"/>'
                f'<path class="w" d="M{num(lb[0])} {num(lb[1] - 5)}L{num(cx_ + 30)} {num(cy_ + 4)}" stroke="{ORANGE}"/>'
                + text(cx_, cy_, f"≥ ({fmt(low[2], 2)} + {fmt(low[3], 2)} − {fmt(low[0] - low[1], 0)}) / 2 = {fmt(low[4], 2)}",
                       11, ORANGE, extra=' class="h"')
                + f'<path class="w" d="M{num(hx0)} {base + 5}v4H{num(hx1)}v-4" fill="none" stroke="{MUTED}"/>'
                + text((hx0 + hx1) / 2, base + 19, f"h {fmt(low[0] - low[1], 0)}", 10, MUTED, "middle") + "</g>")
    an.show("#lb", t2[-1] + 0.4, end)
    curve = " ".join(pt(s_, g) for s_, g in h["true"])
    cs, cg = h["closest"]
    body.append(f'<g id="ex"><path d="M{curve}" fill="none" stroke="{MUTED}" stroke-dasharray="2 2"/>'
                + text(P(cs - 3.4, 0)[0], base - 4, f"exact, least {fmt(cg, 2)}", 10, MUTED) + "</g>")
    an.show("#ex", t2[-1] + 0.8, end)
    body.append(f'<path d="M{px0} {base}H{px1}" stroke="{MUTED}"/>'
                + text(px0, base + 19, f"s {fmt(s_max, 1)}", 10, MUTED, "middle") + text(px1, base + 19, "0", 10, MUTED, "middle")
                + text(px0 - 8, y + 34, "gap, mm", 10, MUTED))
    lines("l3", 20, y + 192, [("A step is the gap, and at least max_step_mm. After the first sample, a box gap ≥ max_step_mm "
                         "stands in for the query (○).", MUTED, False),
                        ("A move of h changes the gap by at most h, so between two samples it stays ≥ (g1 + g2 − h) / 2. "
                         "Dashed: exact.", MUTED, False),
                        (f"clear: the closest approach lies between {fmt(dg['result']['gap_lower_bound_mm'], 2)} and "
                         f"{fmt(dg['result']['min_gap_mm'], 2)} mm; {dg['result']['samples']} queries", INK, True)],
          t2[-1] + 1.0)
    body.append(ntext(20, y + 204, f"≥ {fmt(low[4], 2)} mm between samples", 24, ORANGE, weight="700"))
    label = (f"Three pairs from the assembly gate's box-world tests, each part moved in along a straight line. A card 3 mm "
             f"off a block: the box it sweeps stays {fmt(near['swept_gap'], 0)} mm from the block's, so it is clear with "
             f"no kernel query. A card into a cover fitted first: it hits, and the first contact is bisected to "
             f"{fmt(first[0], 2)} mm before its seat. A part passing a block's corner: sampled near it, and between "
             f"samples h apart the gap is at least (g1 + g2 - h) / 2, here {fmt(low[4], 2)} mm.")
    return svg(680, y + 242, label, body, an)


FIGURES = {"hinge-sweep.svg": hinge_svg, "rib-in-counterbore.svg": counterbore_svg,
           "connector-window.svg": connector_svg, "cable-bend.svg": cable_svg, "module-insertion.svg": subassembly_svg,
           "search-front.svg": search_svg, "motion-trace.svg": motion_trace_svg, "insertion-sweep.svg": sweep_svg}


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
