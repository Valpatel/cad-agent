#!/usr/bin/env python3
"""Regenerate the linkage figures (docs/img/linkages/*.svg) from cadagent.mechanical.linkages.

    PYTHONPATH=src python3 tools/linkage_figures.py            # write the SVGs
    PYTHONPATH=src python3 tools/linkage_figures.py --check    # exit 1 if a committed SVG differs (tests run this)

Nothing is drawn by eye. ``fivebar.svg`` sweeps a five-bar leg's tip round a stride with ``sweep_fivebar_tip`` and
animates the links through the poses it solves. Beside it is the map of the two crank angles from
``fivebar_workspace``, shaded by transmission angle. On the map are the stride's own path and a symmetric crank sweep
(``sweep_fivebar``) that runs into a lock, where the bisected event is marked. The SVG animates with CSS only, so it
runs in an ``<img>`` under the site's Content-Security-Policy and on GitHub. Under ``prefers-reduced-motion`` it holds
the first pose. Light and dark colours come from ``cadagent.publish.anim.svg``'s theme.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cadagent.mechanical import linkages as L                       # noqa: E402
from cadagent.publish.anim import svg as S                           # noqa: E402

OUT = ROOT / "docs" / "img" / "linkages"
U = S.UNITS_PER_PX
num = S.num

# The figure's five-bar, in mm: cranks a, links b, ground d; the stride (an ellipse inside the reach) and the
# symmetric sweep that locks.
A1 = A2 = 100.0
B1 = B2 = 120.0
D = 80.0
STRIDE = {"centre": (40.0, 150.0), "radii": (50.0, 22.0), "start_deg": 180.0, "samples": 48}
SYMMETRIC = [(90.0 + i, 90.0 - i) for i in range(61)]
MAP = {"theta1": (0.0, 180.0), "theta2": (0.0, 180.0), "samples": (37, 37)}
BINS = [(0, 20, "m0"), (20, 40, "m1"), (40, 60, "m2"), (60, 90.0001, "m3")]       # transmission angle, degrees
PERIOD = 7.2

# The map's ramp, one hue light to dark (more is better: further from a lock), with a dark set of the same steps
THEME = S.Theme(light={**S.THEME.light, "m0": "#eef0e6", "m1": "#cddbd2", "m2": "#9cbdb0", "m3": "#5f9384"},
                dark={**S.THEME.dark, "m0": "#1b2725", "m1": "#27403a", "m2": "#356358", "m3": "#4f907f"})


def solve():
    """The sweeps and the map the figure draws, and the numbers its label quotes."""
    path = L.ellipse_path(STRIDE["centre"], STRIDE["radii"], STRIDE["start_deg"], STRIDE["samples"])
    stride = L.sweep_fivebar_tip(A1, B1, A2, B2, D, path)
    sym = L.sweep_fivebar(A1, B1, A2, B2, D, SYMMETRIC)
    grid = L.fivebar_workspace(A1, B1, A2, B2, D, MAP["theta1"], MAP["theta2"], samples=MAP["samples"], cells=True)
    lock = next(e for e in sym["events"] if e["kind"] == "lock")
    return stride, sym, grid, lock


def fivebar_svg() -> str:
    stride, sym, grid, lock = solve()
    if stride["status"] != "pass":
        raise SystemExit(f"the figure's stride no longer passes: {stride['problems']}")
    steps = [s for s in stride["steps"][:-1]]                     # the last point is the first again
    home = steps[0]
    W, H = 680, 366
    body, css = [], []
    an = S.Timeline(PERIOD)

    def text(x, y, s, size=12, fill="ink", anchor=None, weight=None):
        a = f' text-anchor="{anchor}"' if anchor else ""
        w = f' font-weight="{weight}"' if weight else ""
        return (f'<text x="{num(x * U)}" y="{num(y * U)}" font-size="{size * U}" style="fill:var(--{fill})"{a}{w}>'
                f'{escape(s)}</text>')

    # ---- left: the linkage in its plane (mm, y up) to px
    lx0, ly0, lw, lh = 16, 40, 318, 246
    win = (-125.0, -32.0, 205.0, 238.0)                                 # x0, y0, x1, y1 in mm
    sc = min(lw / (win[2] - win[0]), lh / (win[3] - win[1]))

    def P(x, y):
        return (lx0 + (x - win[0]) * sc) * U, (ly0 + (win[3] - y) * sc) * U

    body.append(text(lx0, 22, "The leg: its tip round a stride", 13, weight="700"))
    body.append(f'<clipPath id="lp"><rect x="{num(lx0 * U)}" y="{num(ly0 * U)}" width="{num(lw * U)}" '
                f'height="{num(lh * U)}"/></clipPath>')
    body.append(f'<rect x="{num(lx0 * U)}" y="{num(ly0 * U)}" width="{num(lw * U)}" height="{num(lh * U)}" '
                f'rx="{8 * U}" style="fill:var(--panel)"/>')
    # the reach: each arm's outer circle (crank and link stretched in line), dashed, clipped to the panel
    reach = []
    for r in stride["reach"]:
        cx, cy = P(*r["pivot"])
        reach.append(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r["outer"] * sc * U)}"/>')
        reach.append(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r["inner"] * sc * U)}"/>')
    body.append(f'<g clip-path="url(#lp)" style="fill:none;stroke:var(--muted);stroke-width:{1.2 * U};'
                f'stroke-dasharray:{5 * U} {4 * U}">{"".join(reach)}</g>')
    # the stride, dotted
    pts = " ".join(f"{num(x)},{num(y)}" for x, y in (P(s["tip"]["x"], s["tip"]["y"]) for s in steps))
    body.append(f'<polygon points="{pts}" style="fill:none;stroke:var(--trace);stroke-width:{1.6 * U};'
                f'stroke-dasharray:{1.5 * U} {3 * U};stroke-linecap:round"/>')
    # ground
    (ax, ay), (bx, by) = P(0, 0), P(D, 0)
    hatch = "".join(f"M{num(ax + k * 9 * U - 6 * U)} {num(ay + 12 * U)}l{6 * U} {-7 * U}"
                    for k in range(int((bx - ax) / (9 * U)) + 2))
    body.append(f'<path d="M{num(ax - 10 * U)} {num(ay + 5 * U)}H{num(bx + 10 * U)}{hatch}" '
                f'style="fill:none;stroke:var(--muted);stroke-width:{1.2 * U}"/>')
    # the other assembly on the same cranks, dash-dot: the tip on the far side of the knees
    other = L.sweep_fivebar(A1, B1, A2, B2, D, [(s["angles_deg"]["theta1"], s["angles_deg"]["theta2"]) for s in steps],
                            mode=-home["assembly"], track="hold")["steps"]
    if not all(o["reachable"] and o["branch"] == -home["assembly"] for o in other):
        raise SystemExit("the other assembly does not follow the stride")
    q = P(*other[0]["pins"]["P"])
    # the links, posed at the first step and turned through the rest by CSS
    pins = home["pins"]
    c1h, c2h, ph = P(*pins["C1"]), P(*pins["C2"]), P(*pins["P"])
    line = lambda p, q, w: (f'<line x1="{num(p[0])}" y1="{num(p[1])}" x2="{num(q[0])}" y2="{num(q[1])}" '  # noqa: E731
                            f'style="stroke:var(--ink);stroke-width:{w * U};stroke-linecap:round"/>')
    ghost = lambda p, q: (f'<line x1="{num(p[0])}" y1="{num(p[1])}" x2="{num(q[0])}" y2="{num(q[1])}" '  # noqa: E731
                          f'style="stroke:var(--muted);stroke-width:{1.4 * U};'
                          f'stroke-dasharray:{7 * U} {3 * U} {1.5 * U} {3 * U}"/>')
    dot = lambda p, r, fill: f'<circle cx="{num(p[0])}" cy="{num(p[1])}" r="{r * U}" style="fill:var(--{fill})"/>'  # noqa: E731
    pin = lambda p: dot(p, 3.2, "bg") + f'<circle cx="{num(p[0])}" cy="{num(p[1])}" r="{3.2 * U}" ' \
        f'style="fill:none;stroke:var(--ink);stroke-width:{1.4 * U}"/>'                               # noqa: E731
    body.append(f'<g class="k1"><g class="o1">{ghost(c1h, q)}</g>{line((ax, ay), c1h, 5)}<g class="d1">'
                f'{line(c1h, ph, 3.4)}{pin(c1h)}{dot(ph, 5, "accent")}</g>{pin((ax, ay))}</g>')
    body.append(f'<g class="k2"><g class="o2">{ghost(c2h, q)}</g>{line((bx, by), c2h, 5)}<g class="d2">'
                f'{line(c2h, ph, 3.4)}{pin(c2h)}{pin(ph)}</g>{pin((bx, by))}</g>')
    body.append(text(ax / U - 24, ay / U + 18, "A", 12, "muted", "middle"))
    body.append(text(bx / U + 24, by / U + 18, "B", 12, "muted", "middle"))
    css.append(f".k1,.k2,.d1,.d2,.o1,.o2,.md{{transform-box:view-box}}"
               f".k1{{transform-origin:{num(ax)}px {num(ay)}px}}.k2{{transform-origin:{num(bx)}px {num(by)}px}}"
               f".d1,.o1{{transform-origin:{num(c1h[0])}px {num(c1h[1])}px}}"
               f".d2,.o2{{transform-origin:{num(c2h[0])}px {num(c2h[1])}px}}")

    def turns(poses, key_crank, key_link):
        """Per step: the crank's turn, and the link's turn relative to it, as SVG rotations (y down: clockwise)."""
        out = []
        c0, l0 = poses[0]["angles_deg"][key_crank], poses[0]["angles_deg"][key_link]
        for s in poses:
            dc = math.remainder(s["angles_deg"][key_crank] - c0, 360)
            dl = math.remainder(s["angles_deg"][key_link] - l0, 360)
            out.append((-dc, -(dl - dc)))
        return out

    dt = PERIOD / len(steps)
    rotate = lambda v: f"transform:rotate({num(v, 2)}deg)"                          # noqa: E731
    for crank, link, sel in (("theta1", "phi1", "1"), ("theta2", "phi2", "2")):
        for poses, group in ((steps, "d"), (other, "o")):
            tr = turns(poses, crank, link)
            if group == "d":
                an.add(f".k{sel}", [(i * dt, v[0]) for i, v in enumerate(tr)] + [(PERIOD, 0.0)], rotate, "linear")
            an.add(f".{group}{sel}", [(i * dt, v[1]) for i, v in enumerate(tr)] + [(PERIOD, 0.0)], rotate, "linear")
    sm = stride["summary"]
    # the left panel's key: line samples, then the sweep's numbers
    ky = ly0 + lh + 18
    keys = [("trace", f"{1.5 * U} {3 * U}", "stride"), ("muted", f"{5 * U} {4 * U}", "reach edge"),
            ("muted", f"{7 * U} {3 * U} {1.5 * U} {3 * U}", "other assembly")]
    x = lx0
    for colour, dash, label in keys:
        body.append(f'<line x1="{num(x * U)}" y1="{num((ky - 4) * U)}" x2="{num((x + 20) * U)}" y2="{num((ky - 4) * U)}" '
                    f'style="stroke:var(--{colour});stroke-width:{1.6 * U};stroke-dasharray:{dash}"/>')
        body.append(text(x + 25, ky, label, 11, "muted"))
        x += 25 + 6.2 * len(label) + 14
    body.append(text(lx0, ky + 18, f"lowest transmission angle {sm['min_transmission_deg']:.1f}°, arms "
                     f"{min(sm['in_line_margin_deg'].values()):.1f}° from in line: a pass", 11, "muted"))

    # ---- right: the map of the two crank angles
    mx0, my0, ms = 404, 40, 214
    (a0, a1), (b0, b1) = MAP["theta1"], MAP["theta2"]
    n1, n2 = MAP["samples"]

    def M(t1d, t2d):
        return (mx0 + (t1d - a0) / (a1 - a0) * ms) * U, (my0 + (b1 - t2d) / (b1 - b0) * ms) * U

    body.append(text(mx0 - 40, 22, "The cranks: where the links close", 13, weight="700"))
    cw, ch = ms / (n1 - 1) * U, ms / (n2 - 1) * U
    cells = {k: [] for _, _, k in BINS}
    for c in grid["cells"]:
        if not c["reachable"]:
            continue
        key = next(k for lo, hi, k in BINS if lo <= c["transmission_deg"] < hi)
        x, y = M(c["theta1"], c["theta2"])
        cells[key].append(f"M{num(x - cw / 2)} {num(y - ch / 2)}h{num(cw)}v{num(ch)}h{num(-cw)}z")
    for key, ds in cells.items():
        body.append(f'<path d="{"".join(ds)}" style="fill:var(--{key})"/>')
    body.append(f'<rect x="{num(M(a0, b1)[0] - cw / 2)}" y="{num(M(a0, b1)[1] - ch / 2)}" width="{num(ms * U + cw)}" '
                f'height="{num(ms * U + ch)}" style="fill:none;stroke:var(--line);stroke-width:{1 * U}"/>')
    for v in (0, 90, 180):
        x, y = M(v, b0)
        body.append(text(x / U, y / U + 18, f"{v}°", 11, "muted", "middle"))
        x, y = M(a0, v)
        body.append(text(x / U - 8, y / U + 4, f"{v}°", 11, "muted", "end"))
    x, y = M((a0 + a1) / 2, b0)
    body.append(text(x / U, y / U + 34, "θ1 (crank at A)", 11, "muted", "middle"))
    x, y = M(a1, b1)
    body.append(text(x / U + 8, y / U + 4, "θ2", 11, "muted"))
    body.append(text(x / U + 8, y / U + 18, "(at B)", 11, "muted"))
    # the symmetric sweep, to its lock
    p0, p1 = M(*SYMMETRIC[0]), M(lock["at_deg"]["theta1"], lock["at_deg"]["theta2"])
    body.append(f'<line x1="{num(p0[0])}" y1="{num(p0[1])}" x2="{num(p1[0])}" y2="{num(p1[1])}" '
                f'style="stroke:var(--accent);stroke-width:{2 * U};stroke-linecap:round"/>')
    body.append(f'<path d="M{num(p1[0] - 5 * U)} {num(p1[1] - 5 * U)}l{10 * U} {10 * U}m0 {-10 * U}l{-10 * U} {10 * U}" '
                f'style="stroke:var(--accent);stroke-width:{2.4 * U}"/>')
    body.append(text(p1[0] / U - 8, p1[1] / U + 18, f"lock, θ1 {lock['at_deg']['theta1']:.1f}°", 11, "ink",
                     "end"))
    # the stride's path, and a dot that follows the leg
    sp = [M(s["angles_deg"]["theta1"], s["angles_deg"]["theta2"]) for s in steps]
    body.append(f'<polygon points="{" ".join(f"{num(x)},{num(y)}" for x, y in sp)}" '
                f'style="fill:none;stroke:var(--trace);stroke-width:{1.6 * U}"/>')
    body.append(f'<circle class="md" cx="{num(sp[0][0])}" cy="{num(sp[0][1])}" r="{4.5 * U}" '
                f'style="fill:var(--accent);stroke:var(--bg);stroke-width:{1.5 * U}"/>')
    frames = [(i * dt, (x - sp[0][0], y - sp[0][1])) for i, (x, y) in enumerate(sp)] + [(PERIOD, (0.0, 0.0))]
    an.add(".md", frames, lambda v: f"transform:translate({num(v[0])}px,{num(v[1])}px)", "linear")
    x, y = max(sp, key=lambda q: q[0])
    body.append(text(x / U + 8, y / U + 4, "stride", 11, "ink"))
    # legend: the transmission angle bands
    lgx, lgy = mx0 - 40, my0 + ms + 46
    body.append(text(lgx, lgy + 9, "transmission angle:", 11, "muted"))
    x, lgy = lgx, lgy + 16
    for lo, hi, key in BINS:
        body.append(f'<rect x="{num(x * U)}" y="{num(lgy * U)}" width="{16 * U}" height="{11 * U}" rx="{2 * U}" '
                    f'style="fill:var(--{key});stroke:var(--line);stroke-width:{0.6 * U}"/>')
        body.append(text(x + 19, lgy + 9, f"{lo}–{int(hi)}°", 11, "muted"))
        x += 64
    body.append(text(lgx, lgy + 27, "Blank: the links cannot close. Under 40° a drive may bind.", 11, "muted"))

    label = (f"A five-bar leg (cranks {A1:g} mm, links {B1:g} mm, ground {D:g} mm) moves its tip round a stride "
             f"inside its reach, solved by sweep_fivebar_tip: its lowest transmission angle is "
             f"{sm['min_transmission_deg']:.1f}° and its arms stay {min(sm['in_line_margin_deg'].values()):.1f}° from "
             f"in line. Beside it, the map of the two crank angles shaded by transmission angle, with the stride's "
             f"path; turning both cranks symmetrically from 90° locks at θ1 = {lock['at_deg']['theta1']:.1f}°, where "
             f"the links stretch into one line.")
    desc = (f"{grid['reachable']} of {grid['cells_total']} crank-angle samples close. Generated by "
            "tools/linkage_figures.py from cadagent.mechanical.linkages.")
    return S.document(W, H, label, desc, "".join(css) + an.stylesheet(), body, theme=THEME)


FIGURES = {"fivebar.svg": fivebar_svg}


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
        print("out of date with their sources (run PYTHONPATH=src python3 tools/linkage_figures.py):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
