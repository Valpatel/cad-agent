#!/usr/bin/env python3
"""Regenerate the inserts page's diagrams (docs/img/inserts/*.svg) from cadagent.mechanical.inserts.

    PYTHONPATH=src python3 tools/insert_figures.py            # write the SVGs
    PYTHONPATH=src python3 tools/insert_figures.py --check    # exit 1 if a committed SVG differs (tests run this)

Nothing is drawn by eye: every section is to scale from the module's own hole and boss design for one insert, and
every number on a figure is what the module computed. ``section.svg`` is a boss with a heat-set insert (hole, taper,
overflow pocket, wall, layers); ``clamp-paths.svg`` the three ways a screw's tension reaches the insert; ``limiters.svg``
a compression limiter proud, flush and short of the plastic it passes through; ``calibration.svg`` the published tests
against the shear model fitted to them. Static SVG with light and dark colours (``cadagent.publish.anim.svg``'s
theme), so it shows in an ``<img>`` under the site's Content-Security-Policy and on GitHub.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Sequence, Tuple
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cadagent.mechanical import inserts as I                          # noqa: E402
from cadagent.publish.anim import svg as S                            # noqa: E402

OUT = ROOT / "docs" / "img" / "inserts"
U = S.UNITS_PER_PX
THEME = S.Theme(light={**S.THEME.light, "brass": "#d3a93f", "brassedge": "#7a5a12", "plastic": "#e9e3cf",
                       "layer": "#cfc6a8", "melt": "#f2c9a8"},
                dark={**S.THEME.dark, "brass": "#b08a2a", "brassedge": "#f0cf7a", "plastic": "#2a3330",
                      "layer": "#3c4743", "melt": "#5a3a28"})
CSS = ("text{fill:var(--ink);font-size:" + str(13 * U) + "px}.small{font-size:" + str(11 * U) + "px;fill:var(--muted)}"
       ".big{font-size:" + str(15 * U) + "px;font-weight:600}.dim{stroke:var(--muted);stroke-width:" + str(U) +
       ";fill:none}.edge{stroke:var(--edge);stroke-width:" + str(1.2 * U) + ";stroke-linejoin:round}"
       ".plastic{fill:var(--plastic)}.layer{stroke:var(--layer);stroke-width:" + str(U) + "}"
       ".brass{fill:var(--brass);stroke:var(--brassedge);stroke-width:" + str(U) + "}"
       ".metal{fill:var(--metal);stroke:var(--edge);stroke-width:" + str(U) + "}"
       ".screw{fill:var(--dark);stroke:var(--edge);stroke-width:" + str(U) + "}"
       ".good{stroke:var(--good);fill:var(--good)}.bad{stroke:var(--accent);fill:var(--accent)}"
       ".arrow{stroke-width:" + str(2.4 * U) + ";stroke-linecap:round}.hole{fill:var(--bg)}"
       ".melt{fill:var(--melt)}.axis{stroke:var(--muted);stroke-width:" + str(U) + ";stroke-dasharray:"
       + f"{6 * U} {4 * U}" + "}")
PICK = "mcmaster-94459A140"
MATERIAL = "pla-bambu-basic"


def n(v: float) -> str:
    return S.num(v * U, 0) if abs(v * U - round(v * U)) < 1e-9 else S.num(v * U, 1)


def rect(x, y, w, h, cls) -> str:
    return f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}" class="{cls}"/>'


def line(x1, y1, x2, y2, cls) -> str:
    return f'<line x1="{n(x1)}" y1="{n(y1)}" x2="{n(x2)}" y2="{n(y2)}" class="{cls}"/>'


def poly(points: Sequence[Tuple[float, float]], cls) -> str:
    return f'<polygon points="{" ".join(f"{n(x)},{n(y)}" for x, y in points)}" class="{cls}"/>'


def text(x, y, s, cls="", anchor="start") -> str:
    c = f' class="{cls}"' if cls else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text x="{n(x)}" y="{n(y)}"{c}{a}>{escape(s)}</text>'


def arrow(x1, y1, x2, y2, cls) -> List[str]:
    """A line with a head at (x2, y2)."""
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    h = 7.0
    p1 = (x2 - h * math.cos(a - 0.45), y2 - h * math.sin(a - 0.45))
    p2 = (x2 - h * math.cos(a + 0.45), y2 - h * math.sin(a + 0.45))
    return [line(x1, y1, x2, y2, f"{cls} arrow"), poly([(x2, y2), p1, p2], cls)]


def knurl(x_in, x_out, y0, y1, pitch, outward) -> List[Tuple[float, float]]:
    """One wall of an insert in section: from the bore (x_in) to the knurl's crests (x_out), its outer edge a zigzag
    of the given pitch; ``outward`` +1 for the right wall, -1 for the left."""
    pts = [(x_in, y0)]
    y, crest = y0, True
    root = x_out - outward * 0.35 * pitch
    while y < y1 - 1e-9:
        pts.append((x_out if crest else root, y))
        y = min(y + pitch / 2, y1)
        crest = not crest
    pts += [(x_out if crest else root, y1), (x_in, y1)]
    return pts


def section(cx, top, k, ins, hole, boss, layers="upright", recess=0.0, show_dims=True) -> List[str]:
    """A boss with its insert in section, centred at cx, its top face at ``top``, k px per mm."""
    out: List[str] = []
    Rb, Rh = boss["outside_mm"] / 2 * k, hole["diameter_mm"] / 2 * k
    Rt = Rh                                                  # straight: the makers' holes do not taper
    depth, floor = hole["depth_mm"] * k, 2.5 * k
    Ro, Ri, L = (ins.outer_mm or ins.hole_mm) / 2 * k, (ins.cad_bore_mm or ins.diameter_mm * 0.8) / 2 * k, ins.length_mm * k
    out.append(rect(cx - Rb, top, 2 * Rb, depth + floor, "plastic"))
    step = 0.6 * k                                           # layers drawn every 0.6 mm (three 0.2 mm layers)
    if layers == "upright":
        y = top + step
        while y < top + depth + floor - 1:
            out.append(line(cx - Rb, y, cx + Rb, y, "layer"))
            y += step
    else:
        x = cx - Rb + step
        while x < cx + Rb - 1:
            out.append(line(x, top, x, top + depth + floor, "layer"))
            x += step
    out.append(poly([(cx - Rt, top), (cx + Rt, top), (cx + Rh, top + depth), (cx - Rh, top + depth)], "hole"))
    y0 = top + recess * k
    for side in (-1, 1):
        melt = [(cx + side * Rh, y0), (cx + side * (Ro + 0.25 * k), y0), (cx + side * (Ro + 0.25 * k), y0 + L),
                (cx + side * Rh, y0 + L)]
        out.append(poly(melt, "melt"))
        pts = knurl(cx + side * Ri, cx + side * Ro, y0, y0 + L, 0.9 * k, side)
        out.append(poly(pts, "brass"))
    out.append(poly([(cx - Rb, top), (cx - Rb, top + depth + floor), (cx + Rb, top + depth + floor),
                     (cx + Rb, top)], "edge") .replace('class="edge"', 'class="edge" fill="none"'))
    out.append(line(cx, top - 14, cx, top + depth + floor + 10, "axis"))
    return out


def figure_section() -> str:
    ins = I.insert(PICK)
    hole = I.hole_design(ins)
    boss = I.boss_design(ins)
    k = 30.0
    top, cx = 60.0, 290.0
    body = section(cx, top, k, ins, hole, boss)
    Rb, Rh = boss["outside_mm"] / 2 * k, hole["diameter_mm"] / 2 * k
    depth = hole["depth_mm"] * k
    L = ins.length_mm * k
    # dimensions: the hole's diameter above, the depth and the insert's length on the right, the wall at the left
    body += [line(cx - Rh, top - 24, cx + Rh, top - 24, "dim"), line(cx - Rh, top - 30, cx - Rh, top - 4, "dim"),
             line(cx + Rh, top - 30, cx + Rh, top - 4, "dim"),
             text(cx, top - 32, f"hole Ø{hole['diameter_mm']:.2f} mm in CAD (maker's {hole['maker_mm']:g})", "small",
                  "middle")]
    xr = cx + Rb + 18
    body += [line(xr, top, xr, top + depth, "dim"), line(xr - 4, top + depth, xr + 4, top + depth, "dim"),
             text(xr + 8, top + depth - 6, f"depth {hole['depth_mm']:.1f} mm", "small"),
             line(xr - 10, top, xr - 10, top + L, "dim"), line(xr - 14, top + L, xr - 6, top + L, "dim"),
             text(xr + 8, top + L / 2, f"insert {ins.length_mm:g} mm", "small")]
    pocket_y = top + (ins.length_mm + (hole["depth_mm"] - ins.length_mm) / 2) * k
    body.append(text(cx + Rb + 18, pocket_y + 30, f"pocket {hole['overflow_mm3']:.1f} mm³", "small"))
    xl = cx - Rb - 12
    body += [text(xl, top + depth * 0.55, f"wall {boss['wall_mm']:.2f} mm", "small", "end"),
             text(xl, top + depth * 0.55 + 16, f"boss Ø{boss['outside_mm']:.2f} mm", "small", "end"),
             text(xl, top + depth * 0.55 + 32, f"(least Ø{boss['least_outside_mm']:.2f})", "small", "end")]
    x2 = 600
    lines = [(f"{ins.thread} × {ins.length_mm:g} mm, {ins.maker} {ins.part}", "big"),
             (f"knurl Ø{ins.outer_mm:g} mm, brass, {ins.volume_mm3:g} mm³", ""),
             (f"hole Ø{hole['diameter_mm']:.2f} mm in CAD, straight, {hole['depth_mm']:.1f} mm deep", ""),
             (f"melt pushed aside {hole['displaced_mm3']:+.1f} mm³, pocket {hole['overflow_mm3']:.1f} mm³", ""),
             (f"wall at least {boss['least_wall_mm']:g} mm; {boss['perimeters']} perimeters, solid", ""),
             ("layers across the insert: printed upright (axis along Z)", ""),
             ("drawn to scale from cadagent.mechanical.inserts", "small")]
    y = top + 4
    for s, cls in lines:
        body.append(text(x2, y, s, cls))
        y += 26
    title = (f"Section of a printed boss with a {ins.thread} heat-set insert ({ins.maker} {ins.part}): hole "
             f"{hole['diameter_mm']:.2f} mm, {hole['depth_mm']:.1f} mm deep, wall {boss['wall_mm']:.1f} mm")
    return S.document(960, int(top + depth + 2.5 * k + 50), title, title + ". " + " ".join(hole["why"]), CSS, body,
                      THEME)


def _panel_title(x, y, title, verdict, good) -> List[str]:
    out = [text(x, y, title, "big", "middle")]
    for i, part in enumerate(verdict.split("; ")):
        out.append(text(x, y + 20 + 16 * i, part, "small", "middle"))
    return out


def figure_clamp_paths() -> str:
    """Three joints, side by side: the insert pulled into a shoulder (seat), flush so the clamped part bears on it
    (through-insert), and recessed so the screw jacks it out of the boss. Paths and words from insert_clamp_path."""
    k, w = 16.0, 290.0
    body: List[str] = []
    cases = [("seat", I.fx.insert_clamp_path(1.2e-3, 0.1e-3, "far side")),
             ("through-insert", I.fx.insert_clamp_path(0.0, 0.1e-3)),
             ("jack-out", I.fx.insert_clamp_path(0.6e-3, 0.1e-3))]
    titles = {"seat": "Seat: pulled into a shoulder", "through-insert": "Through the insert: flush",
              "jack-out": "Jack-out: recessed"}
    for i, (name, r) in enumerate(cases):
        cx = w / 2 + i * w
        good = r["path"] != "jack-out"
        body += _panel_title(cx, 30, titles[name], "the knurl carries " + ("the whole preload" if r["knurl_preload"]
                                                                          else "no preload"), good)
        top = 175.0
        Rb, Ro, Rh, Ri, L = 5.5 * k, 2.36 * k, 2.0 * k, 1.2 * k, 5.7 * k
        Rs = 1.6 * k                                           # the screw's clearance
        # the clamped part on top, the boss below it
        body.append(rect(cx - Rb, top - 3.0 * k, 2 * Rb, 3.0 * k, "metal"))
        body.append(rect(cx - Rs, top - 3.0 * k, 2 * Rs, 3.0 * k, "hole"))
        body.append(rect(cx - Rb, top, 2 * Rb, 9.0 * k, "plastic"))
        y = top + 0.6 * k
        while y < top + 9.0 * k - 1:
            body.append(line(cx - Rb, y, cx + Rb, y, "layer"))
            y += 0.6 * k
        if name == "seat":
            y0 = top + 1.2 * k                                 # behind a 1.2 mm shoulder, pressed in from below
            body.append(rect(cx - Rs, top, 2 * Rs, 1.2 * k, "hole"))
            body.append(rect(cx - Rh, y0, 2 * Rh, 9.0 * k - 1.2 * k, "hole"))
        else:
            y0 = top + (0.6 * k if name == "jack-out" else 0.0)
            body.append(rect(cx - Rh, top, 2 * Rh, 7.0 * k, "hole"))
        for side in (-1, 1):
            body.append(poly(knurl(cx + side * Ri, cx + side * Ro, y0, y0 + L, 0.9 * k, side), "brass"))
        # the screw: head above the clamped part, shank down into the insert
        body.append(rect(cx - 2.8 * k, top - 3.0 * k - 1.8 * k, 5.6 * k, 1.8 * k, "screw"))
        body.append(rect(cx - 1.5 * k, top - 3.0 * k, 3.0 * k, 3.0 * k + L * 0.9 + (y0 - top), "screw"))
        # the clamp: the screw pulls the insert up; where it reacts
        cls = "good" if good else "bad"
        body += arrow(cx, y0 + L * 0.55, cx, y0 + L * 0.15, cls)
        if name == "seat":
            for side in (-1, 1):
                body += arrow(cx + side * 1.9 * k, top + 1.9 * k, cx + side * 1.9 * k, top + 1.25 * k, "good")
            note = "the shoulder takes it in bearing"
        elif name == "through-insert":
            for side in (-1, 1):
                body += arrow(cx + side * 1.9 * k, top + 0.9 * k, cx + side * 1.9 * k, top + 0.1 * k, "good")
            note = "the clamped part bears on the insert"
        else:
            for side in (-1, 1):
                body += arrow(cx + side * (Ro + 0.6 * k), y0 + L * 0.8, cx + side * (Ro + 0.6 * k), y0 + L * 0.2, "bad")
            note = "the knurl shears the boss: it pulls out"
        body.append(text(cx, top + 9.0 * k + 26, note, "small", "middle"))
    title = ("Three clamp paths for a heat-set insert: pulled into a shoulder (the shoulder carries the clamp), flush "
             "(the clamped part bears on the insert) and recessed (the screw jacks the insert out of the boss: the knurl "
             "carries the whole preload)")
    return S.document(int(3 * w), 360, title, title, CSS, body, THEME)


def figure_limiters() -> str:
    """A compression limiter proud, flush and short of the plastic it passes through: SPIROL's rule is a limiter
    no longer than the plastic's least thickness, squeezing it a few per cent."""
    k, w = 16.0, 290.0
    body: List[str] = []
    for i, (name, standout) in enumerate((("proud", 0.15), ("flush", 0.0), ("short", -0.15))):
        cx = w / 2 + i * w
        top, t = 140.0, 6.0 * k
        Rb, Rl, Ri, Rw = 8.0 * k, 3.0 * k, 1.7 * k, 4.5 * k
        s = standout * k * 6                                    # standouts drawn 6 x so they show
        state = {"proud": "clamp through the metal; the plastic loose round it",
                 "flush": "clamp through the metal; the plastic just held",
                 "short": "the head squeezes the plastic first; a few % is the aim"}[name]
        body += _panel_title(cx, 30, f"{name.capitalize()}: {standout:+.2f} mm", state, name != "proud")
        body.append(rect(cx - Rb, top + t, 2 * Rb, 2.5 * k, "metal"))                        # the base
        body.append(rect(cx - Rb, top, 2 * Rb, t, "plastic"))                                 # the plastic part
        body.append(rect(cx - Rl, top - s, 2 * Rl, t + s, "metal"))                           # the limiter
        body.append(rect(cx - Ri, top - max(s, 0.0) - 1, 2 * Ri, t + max(s, 0.0) + 2, "hole"))
        head_y = top - max(s, 0.0)
        body.append(rect(cx - Rw, head_y - 1.0 * k, 2 * Rw, 1.0 * k, "metal"))                # the washer
        body.append(rect(cx - 2.8 * k, head_y - 1.0 * k - 2.0 * k, 5.6 * k, 2.0 * k, "metal"))  # the head
        body.append(rect(cx - 1.4 * k, head_y - 1.0 * k, 2.8 * k, t + 2.5 * k + max(s, 0.0) + 1.0 * k, "metal"))
        if name == "proud":
            body.append(text(cx, top + t + 2.5 * k + 22, f"plastic {standout:.2f} mm below the limiter", "small",
                             "middle"))
            body += arrow(cx - 2.2 * k, head_y + 0.2 * k, cx - 2.2 * k, top + t - 0.3 * k, "good")
        elif name == "flush":
            body += arrow(cx - 2.2 * k, head_y + 0.2 * k, cx - 2.2 * k, top + t - 0.3 * k, "good")
        else:
            body += arrow(cx - 3.8 * k, head_y + 0.2 * k, cx - 3.8 * k, top + t - 0.3 * k, "bad")
            body.append(text(cx, top + t + 2.5 * k + 22, f"limiter {-standout:.2f} mm short of the plastic", "small",
                             "middle"))
    title = ("A compression limiter proud, flush and short of the plastic it passes through: proud, the plastic is "
             "loose round it; flush, the clamp goes through the metal; short, the head squeezes the plastic a few per "
             "cent before it lands on the limiter (SPIROL: at most 5 %, which printed plastic may not take)")
    return S.document(int(3 * w), 330, title, title, CSS, body, THEME)


# One hue per host, in a fixed order, checked for colour-blind separation on the site's light and dark surfaces;
# a marker shape per host as well, and each series labelled where it sits, so colour never carries it alone.
HOSTS = (("pla", True, "printed PLA", "circle"), ("petg", True, "printed PETG", "square"),
         ("nylon", False, "moulded nylon 6/6 (SPIROL)", "diamond"), ("abs", False, "moulded ABS (PEM)", "triangle"),
         ("pc", False, "moulded, extruded PC", "cross"))
SERIES = S.Theme(light={**THEME.light, "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a", "s4": "#eda100",
                        "s5": "#e87ba4"},
                 dark={**THEME.dark, "s1": "#3987e5", "s2": "#d95926", "s3": "#199e70", "s4": "#c98500",
                       "s5": "#d55181"})


def marker(shape: str, x: float, y: float, cls: str) -> str:
    r = 5.0
    if shape == "circle":
        return f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(r)}" class="{cls}"/>'
    if shape == "square":
        return rect(x - r, y - r, 2 * r, 2 * r, cls)
    if shape == "diamond":
        return poly([(x, y - r * 1.3), (x + r * 1.3, y), (x, y + r * 1.3), (x - r * 1.3, y)], cls)
    if shape == "triangle":
        return poly([(x, y - r * 1.2), (x + r * 1.2, y + r), (x - r * 1.2, y + r)], cls)
    return poly([(x - r, y - 2), (x - 2, y - 2), (x - 2, y - r), (x + 2, y - r), (x + 2, y - 2), (x + r, y - 2),
                 (x + r, y + 2), (x + 2, y + 2), (x + 2, y + r), (x - 2, y + r), (x - 2, y + 2), (x - r, y + 2)], cls)


def figure_calibration() -> str:
    """The published pull-out results as the mean shear stress on the knurl's cylinder, q = F / (pi D L), against the
    knurl's diameter. If the shear model holds, each host's points lie level whatever the insert's size; the band is
    the fit, c tau, for the strongest PLA sheet the printed tests are compared with, and the dashed line what the
    check holds an insert to in Bambu PLA Basic."""
    cal = I.calibration()
    W, H = 860, 400
    x0, x1, y0, y1 = 90.0, 600.0, 340.0, 50.0                 # plot box, px
    dmin, dmax, qmax = 3.0, 11.0, 25.0
    X = lambda d: x0 + (d - dmin) / (dmax - dmin) * (x1 - x0)
    Y = lambda q: y0 - q / qmax * (y0 - y1)
    css = CSS + "".join(f".s{i + 1}{{fill:var(--s{i + 1});stroke:var(--bg);stroke-width:{2 * U}}}"
                        for i in range(len(HOSTS))) + f".grid{{stroke:var(--line);stroke-width:{U}}}" \
        f".band{{fill:var(--soft);opacity:.8}}.check{{stroke:var(--accent);stroke-width:{1.6 * U};" \
        f"stroke-dasharray:{6 * U} {4 * U}}}"
    body: List[str] = []
    for q in range(0, 26, 5):
        body += [line(x0, Y(q), x1, Y(q), "grid"), text(x0 - 10, Y(q) + 4, f"{q}", "small", "end")]
    for d in range(3, 12):
        body += [line(X(d), y0, X(d), y0 + 5, "dim"), text(X(d), y0 + 20, f"{d}", "small", "middle")]
    body += [text((x0 + x1) / 2, y0 + 42, "knurl diameter D (mm)", "small", "middle"),
             text(x0 - 60, y1 - 16, "q = F / (π D L), MPa", "small")]
    pla = cal["pull"]["pla"]
    tau = I.shear_strength("pla-polymaker") / 1e6
    body.append(rect(x0, Y(pla["high"] * tau), x1 - x0, Y(pla["low"] * tau) - Y(pla["high"] * tau), "band"))
    body.append(text(x1 - 6, Y(pla["high"] * tau) - 6,
                     f"fit: c {pla['low']:.2f}-{pla['high']:.2f} × τ {tau:.2f} MPa (PolyLite PLA)", "small", "end"))
    q_check = pla["low"] * I.shear_strength("pla-bambu-basic") / 1e6
    body += [line(x0, Y(q_check), x1, Y(q_check), "check"),
             text(X(4.9), Y(q_check) - 6, f"the check in Bambu PLA Basic: {q_check:.1f} MPa", "small")]
    rows = {r["key"]: r for r in cal["rows"]}
    for i, (fam, printed, label, shape) in enumerate(HOSTS):
        pts = [(t.outer_mm, rows[t.key]["q_mpa"]) for t in I.TESTS if t.family == fam and t.printed == printed]
        for x, q in pts:
            body.append(marker(shape, X(x), Y(q), f"s{i + 1}"))
        if printed:                                      # direct labels for the two printed series; the legend has all
            x, q = max(pts, key=lambda pt: pt[1])
            body.append(text(X(x) + 12, Y(q) + 4, label, "small"))
    # the legend, right of the plot: shape and hue, then how many results
    ly = y1 + 6
    for i, (fam, printed, label, shape) in enumerate(HOSTS):
        k = sum(1 for t in I.TESTS if t.family == fam and t.printed == printed)
        body += [marker(shape, 640, ly, f"s{i + 1}"), text(656, ly + 4, f"{label} ({k})", "small")]
        ly += 24
    body.append(text(640, ly + 14, "printed: Laszlo 2026, CNC Kitchen,", "small"))
    body.append(text(640, ly + 30, "SPIROL 04/26 (M6, chart)", "small"))
    body.append(text(640, ly + 46, "moulded: SPIROL, PEM SI", "small"))
    q_pla = {t.key: rows[t.key]["q_mpa"] for t in I.TESTS if t.family == "pla" and t.printed}
    m3 = [q for k, q in q_pla.items() if I.TESTS[[t.key for t in I.TESTS].index(k)].outer_mm < 5]
    m6 = [q for k, q in q_pla.items() if I.TESTS[[t.key for t in I.TESTS].index(k)].outer_mm > 8]
    title = (f"Published heat-set insert pull-out tests as shear stress on the knurl's cylinder against insert size: "
             f"printed PLA {min(m3):.1f}-{max(m3):.1f} MPa at M3 and {min(m6):.1f}-{max(m6):.1f} MPa at M6, so the "
             f"larger insert sits lower; the check holds Bambu PLA Basic to {q_check:.1f} MPa")
    return S.document(W, H, title, title, css, body, SERIES)


def main(check: bool = False) -> int:
    figures = {"section.svg": figure_section(), "clamp-paths.svg": figure_clamp_paths(),
               "limiters.svg": figure_limiters(), "calibration.svg": figure_calibration()}
    stale = []
    OUT.mkdir(parents=True, exist_ok=True)
    for name, svg in figures.items():
        path = OUT / name
        if check:
            if not path.exists() or path.read_text() != svg:
                stale.append(name)
        else:
            path.write_text(svg)
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("stale: " + ", ".join(stale) + " (run tools/insert_figures.py)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv[1:]))
