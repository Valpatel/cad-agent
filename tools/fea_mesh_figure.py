#!/usr/bin/env python3
"""Regenerate docs/img/fea/corner-convergence.svg: the peak stress at an inside corner as refine= makes the mesh there
finer, for a sharp corner and for the same corner with an R1.5 fillet.

    PYTHONPATH=src python3 tools/fea_mesh_figure.py       # needs cadquery, gmsh and scikit-fem (about a minute)

A steel L-bracket (legs 20 mm, 4 mm thick, 2 mm wide), one leg clamped at its end and 100 N on the other's, meshed
at 2 mm, then refined round the inside corner (a 1.5 mm ball) to 1, 0.5, 0.25 and 0.125 mm. The dots are
Study.solve()'s design peak; the dashed line is Williams' (1952) rate for a sharp 270° corner, stress ~ r^(λ-1) with
sin(3πλ/2) = λ (λ = 0.5445), drawn through the 0.25 mm dot. It is a 2D rate: at the coarser meshes the peak sits
where the corner meets a side face, a 3D vertex with its own exponent, so the measured steps (x1.22 to x1.47, about
x1.34 on average) only come close to it. The SVG carries its own light background, like the other
FEA charts, and a <title> on every dot for a hover readout.
"""
from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "img" / "fea" / "corner-convergence.svg"
INK, MUTED, LINE, BG = "#173d3c", "#526863", "#d8e0d3", "#fffdf5"
SHARP, FILLET = "#bd3a12", "#2f6f9f"                # the pair the layer-check chart uses (validated, light surface)
FONT = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif"
MESH, SIZES, FILLET_R = 2.0, (None, 1.0, 0.5, 0.25, 0.125), 1.5


def williams_lambda() -> float:
    """The root of sin(3πλ/2) = λ in (0.3, 0.9): Williams' mode I eigenvalue for a 270° corner."""
    lo, hi = 0.3, 0.9
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if math.sin(1.5 * math.pi * mid) - mid > 0 else (lo, mid)
    return (lo + hi) / 2


def solve():
    """{fillet radius: [(size, peak MPa, peak record, tets), ...]} for the sharp and the filleted corner."""
    import cadquery as cq

    from cadagent.simulation.fea import Material, MeshWarning, Study, plane_at
    steel = Material("steel", 200000, 0.3, 250, 7.85)
    out = {}
    for r in (0.0, FILLET_R):
        s = cq.Workplane("XZ").polyline([(0, 0), (20, 0), (20, 4), (4, 4), (4, 20), (0, 20)]).close().extrude(-2)
        if r:
            s = s.edges("|Y").edges(cq.selectors.NearestToPointSelector((4, 1, 4))).fillet(r)
        corner = (4 + r * (1 - math.sqrt(0.5)), 1.0, 4 + r * (1 - math.sqrt(0.5)))
        rows = []
        for size in SIZES:
            st = Study(s, steel, mesh_mm=MESH, name="bracket", refine=[(corner, 1.5, size)] if size else None)
            st.fix(plane_at(0, 0.0)).force(plane_at(0, 20.0), (0, 0, -100.0))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", MeshWarning)
                res = st.solve()
            rows.append((size or MESH, res["von_mises_design_mpa"], res["mesh"]["peak"], res["mesh"]["tets"]))
        out[r] = rows
    return out


def svg(data) -> str:
    lam = williams_lambda()
    w, h, x0, x1, y0, y1 = 680, 400, 70, 640, 84, 312
    lo, hi = math.log2(MESH), math.log2(SIZES[-1])
    X = lambda size: x0 + (x1 - x0) * (math.log2(size) - lo) / (hi - lo)      # finer to the right
    top = 250 * math.ceil(max(v for rows in data.values() for _, v, _, _ in rows) * 1.08 / 250)
    Y = lambda mpa: y1 - (y1 - y0) * mpa / top
    title = f"Peak stress at an inside corner as refine= makes it finer: sharp, and an R{FILLET_R:g} fillet"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           f'aria-label="{escape(title, {chr(34): "&quot;"})}" font-family="{FONT}">',
           f'<rect width="{w}" height="{h}" rx="14" fill="{BG}" stroke="{LINE}"/>',
           f'<text x="18" y="30" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>']
    lx = 18
    for name, colour in (("sharp corner: never settles", SHARP), (f"R{FILLET_R:g} fillet: settles", FILLET),
                         (f"Williams 1952: stress ~ r^{lam - 1:.3f}", MUTED)):
        dash = ' stroke-dasharray="5 4"' if colour == MUTED else ""
        out.append(f'<line x1="{lx}" y1="54" x2="{lx + 16}" y2="54" stroke="{colour}" stroke-width="2.5"{dash}/>')
        out.append(f'<text x="{lx + 21}" y="58" font-size="12" fill="{MUTED}">{escape(name)}</text>')
        lx += 40 + 6.3 * len(name)
    for mpa in range(0, int(top) + 1, 250):                                   # grid and y axis
        out.append(f'<line x1="{x0}" y1="{Y(mpa):.1f}" x2="{x1}" y2="{Y(mpa):.1f}" stroke="{LINE}"/>')
        out.append(f'<text x="{x0 - 8}" y="{Y(mpa) + 4:.1f}" font-size="11" fill="{MUTED}" text-anchor="end">{mpa}</text>')
    out.append(f'<text x="18" y="{(y0 + y1) / 2:.0f}" font-size="11" fill="{MUTED}" text-anchor="middle" '
               f'transform="rotate(-90 18 {(y0 + y1) / 2:.0f})">design peak, von Mises (MPa)</text>')
    for size in (MESH,) + SIZES[1:]:                                          # x axis
        label = f"{size:g} mm" + (", no refine" if size == MESH else "")
        out.append(f'<text x="{X(size):.1f}" y="{y1 + 17}" font-size="11" fill="{MUTED}" text-anchor="middle">'
                   f'{escape(label)}</text>')
    out.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{y1 + 36}" font-size="11" fill="{MUTED}" text-anchor="middle">'
               f'element size at the corner (refine=, inside a {MESH:g} mm mesh; each step halves it)</text>')
    sharp = data[0.0]
    ref_size, ref = next((s, v) for s, v, _, _ in sharp if s == 0.25)
    pts = [(s, ref * (s / ref_size) ** (lam - 1)) for s in (1.0, 0.75, 0.5, 0.35, 0.25, 0.18, 0.125)]
    out.append('<path d="M' + " L".join(f"{X(s):.1f},{Y(v):.1f}" for s, v in pts) +
               f'" fill="none" stroke="{MUTED}" stroke-width="1.6" stroke-dasharray="5 4"/>')
    for r, colour in ((0.0, SHARP), (FILLET_R, FILLET)):
        rows = data[r]
        out.append('<path d="M' + " L".join(f"{X(s):.1f},{Y(v):.1f}" for s, v, _, _ in rows) +
                   f'" fill="none" stroke="{colour}" stroke-width="2"/>')
        for i, (s, v, peak, tets) in enumerate(rows):
            step = f", x{v / rows[i - 1][1]:.2f} on the step before" if i else ""
            tip = (f"{'sharp corner' if not r else f'R{r:g} fillet'}, {s:g} mm: {v:g} MPa{step}; {tets} tets, "
                   f"{peak['elements_across']} elements across the {peak['wall_mm']:g} mm wall"
                   + (f", {peak['element_mm']:g} mm elements on the R{peak['radius_mm']:g}" if peak.get('radius_mm') else "")
                   + f", at {peak['where']}")
            out.append(f'<circle cx="{X(s):.1f}" cy="{Y(v):.1f}" r="5" fill="{BG}" stroke="{colour}" stroke-width="2">'
                       f'<title>{escape(tip)}</title></circle>')
        last = rows[-1]
        out.append(f'<text x="{X(last[0]) - 10:.1f}" y="{Y(last[1]) + (-12 if not r else 20):.1f}" font-size="11" '
                   f'fill="{colour}" text-anchor="end">{last[1]:.0f} MPa</text>')
    f = [v for _, v, _, _ in data[FILLET_R]]
    out.append(f'<text x="{x0 + 8}" y="{Y(top * 0.08):.1f}" font-size="11" fill="{MUTED}">'
               f'the fillet stays within {100 * (max(f) / min(f) - 1):.1f} % across all five meshes; the sharp corner '
               f'grows about 2^{1 - lam:.3f} = {2 ** (1 - lam):.2f} x per halving</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    data = solve()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg(data), encoding="utf-8")
    for r, rows in data.items():
        print(f"fillet {r:g}: " + ", ".join(f"{s:g} mm {v:g} MPa ({t} tets)" for s, v, _, t in rows))
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
