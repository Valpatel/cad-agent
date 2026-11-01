#!/usr/bin/env python3
"""Regenerate the layer check's two figures in docs/img/fea/.

    PYTHONPATH=src python3 tools/fea_layer_figure.py      # needs cadquery, gmsh, scikit-fem, matplotlib, PIL (~30 s)

layer-check.svg: a printed bar's safety factor against its layers, by print tilt. A PETG-CF bar, 10 x 10 x 100 mm,
clamped at one end and pulled with 1000 N at the other (10 MPa). The lines are
cadagent.simulation.fea.layer_utilisation() on that uniaxial stress, by hand; the dots are Study.layer_check() on the
solved bar, over its middle half (where the stress is uniform), at tilts of the layer normal from the load. The SVG
carries its own light background, like the research charts, and a <title> on every dot for a hover readout.

layer-criteria.png: one solved PETG-CF L bracket, printed as modelled (layer normal z), drawn by Study.render(field=)
under the two bond criteria. The upright (4 mm thick, 20 wide, 30 tall, an R2 fillet at its root) is pushed back
with 27 N at its top edge, so its root fillet pulls across the layers while they carry shear. The combined criterion
fails a band along the fillet; the maximum-stress one passes it.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "img" / "fea" / "layer-check.svg"
OUT_CRITERIA = ROOT / "docs" / "img" / "fea" / "layer-criteria.png"
INK, MUTED, LINE, BG = "#173d3c", "#526863", "#d8e0d3", "#fffdf5"
BOND, BULK = "#bd3a12", "#2f6f9f"                   # validated as a pair (dataviz validator, light surface)
FONT = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif"
L, B, F, KEY = 100.0, 10.0, 1000.0, "petg_cf"
TILTS = range(0, 91, 15)


def solve():
    """(sigma, S_xy, S_z, [(tilt, layer_check), ...]) for the bar."""
    import cadquery as cq
    import numpy as np

    from cadagent.simulation.fea import MATERIALS, Study, plane_at
    st = Study(cq.Workplane("XY").box(L, B, B).translate((L / 2, 0, 0)), MATERIALS[KEY], mesh_mm=4.0, name="bar")
    st.fix(plane_at(0, 0.0)).force(plane_at(0, L), (F, 0, 0))
    st.solve()
    c = st.points[st.tets].mean(axis=1)
    mid = (c[:, 0] > L / 4) & (c[:, 0] < 3 * L / 4)
    checks = [(t, st.layer_check((math.cos(math.radians(t)), 0, math.sin(math.radians(t))), judge=mid)) for t in TILTS]
    xy, z = MATERIALS[KEY].layer_strengths_mpa
    return F / B ** 2, xy, z, checks, int(np.count_nonzero(mid))


def svg(sigma, xy, z, checks, judged) -> str:
    import numpy as np

    from cadagent.simulation.fea import layer_utilisation
    w, h, x0, x1, y0, y1, top_sf = 680, 400, 64, 650, 78, 318, 4.0
    X = lambda t: x0 + (x1 - x0) * t / 90
    Y = lambda sf: y1 - (y1 - y0) * min(sf, top_sf * 1.05) / top_sf
    tilt = np.linspace(0, 90, 361)
    sig = np.zeros((len(tilt), 3, 3))
    sig[:, 0, 0] = sigma
    normals = np.stack([np.cos(np.radians(tilt)), 0 * tilt, np.sin(np.radians(tilt))], axis=1)
    bond = np.array([float(layer_utilisation(sig[i], normals[i], xy, z)[0]) for i in range(len(tilt))])
    sf_bond = np.where(bond > 0, sigma / np.maximum(bond * sigma, 1e-12), np.inf)
    sf_bulk = xy / sigma
    worst = int(np.argmax(bond))
    cross = float(tilt[np.argmax((tilt > tilt[worst]) & (sf_bond >= sf_bulk))])
    path = lambda pts: "M" + " L".join(f"{X(t):.1f},{Y(s):.1f}" for t, s in pts)
    gov = [(t, min(b, sf_bulk)) for t, b in zip(tilt, sf_bond)]
    title = f"A {B:g} mm PETG-CF bar pulled at {sigma:g} MPa: its safety factor against the layers, by print tilt"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           f'aria-label="{escape(title, {chr(34): "&quot;"})}" font-family="{FONT}">',
           f'<rect width="{w}" height="{h}" rx="14" fill="{BG}" stroke="{LINE}"/>',
           f'<text x="18" y="30" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>',
           f'<defs><clipPath id="plot"><rect x="{x0}" y="{y0 - 4}" width="{x1 - x0}" height="{y1 - y0 + 4}"/></clipPath></defs>']
    lx = 18
    for name, colour, dash in ((f"bond: across the layers, against S_z = {z:g} MPa", BOND, ""),
                               (f"bulk: von Mises, against S_xy = {xy:.1f} MPa", BULK, "")):
        out.append(f'<line x1="{lx}" y1="50" x2="{lx + 16}" y2="50" stroke="{colour}" stroke-width="2.5"/>')
        out.append(f'<text x="{lx + 21}" y="54" font-size="12" fill="{MUTED}">{escape(name)}</text>')
        lx += 36 + 6.2 * len(name)
    for sf in range(int(top_sf) + 1):                                    # grid and y axis
        out.append(f'<line x1="{x0}" y1="{Y(sf):.1f}" x2="{x1}" y2="{Y(sf):.1f}" stroke="{LINE}"/>')
        out.append(f'<text x="{x0 - 8}" y="{Y(sf) + 4:.1f}" font-size="11" fill="{MUTED}" text-anchor="end">{sf}</text>')
    out.append(f'<text x="18" y="{(y0 + y1) / 2:.0f}" font-size="11" fill="{MUTED}" text-anchor="middle" '
               f'transform="rotate(-90 18 {(y0 + y1) / 2:.0f})">safety factor</text>')
    for t in range(0, 91, 15):                                           # x axis
        out.append(f'<text x="{X(t):.1f}" y="{y1 + 17}" font-size="11" fill="{MUTED}" text-anchor="middle">{t}°</text>')
    out.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{y1 + 36}" font-size="11" fill="{MUTED}" text-anchor="middle">tilt of '
               'the layer normal from the load (0°: the load crosses the layers; 90°: it runs along them)</text>')
    iso = z / sigma                                                      # the isotropic study at the Z strength
    out.append(f'<line x1="{x0}" y1="{Y(iso):.1f}" x2="{x1}" y2="{Y(iso):.1f}" stroke="{MUTED}" stroke-dasharray="5 4"/>')
    out.append(f'<text x="{X(78):.1f}" y="{Y(iso) + 15:.1f}" font-size="11" fill="{MUTED}" text-anchor="middle">'
               f'isotropic study at S_z everywhere: {iso:.2f}</text>')
    out.append(f'<g clip-path="url(#plot)">')
    out.append(f'<path d="{path(gov)}" fill="none" stroke="{INK}" stroke-opacity="0.16" stroke-width="9" '
               'stroke-linejoin="round"/>')
    out.append(f'<path d="{path([(t, sf_bulk) for t in tilt])}" fill="none" stroke="{BULK}" stroke-width="2"/>')
    out.append(f'<path d="{path([(t, s) for t, s in zip(tilt, sf_bond) if np.isfinite(s)])}" fill="none" '
               f'stroke="{BOND}" stroke-width="2"/>')
    out.append('</g>')
    def by_hand(t):
        b, u = layer_utilisation(sig[0], (math.cos(math.radians(t)), 0, math.sin(math.radians(t))), xy, z)
        return 1 / max(float(b), float(u))

    for t, lc in checks:                                                 # the solved bar
        sf = lc.safety_factor
        tip = (f"{t}°: Study.layer_check() safety factor {sf:.3f}, governed by {lc.governed_by} "
               f"(by hand {by_hand(t):.3f})")
        out.append(f'<circle cx="{X(t):.1f}" cy="{Y(sf):.1f}" r="5" fill="{BG}" stroke="{INK}" stroke-width="2">'
                   f'<title>{escape(tip)}</title></circle>')
    s30 = float(sf_bond[worst])
    out.append(f'<text x="{X(tilt[worst]):.1f}" y="{Y(s30) + 22:.1f}" font-size="11" fill="{INK}" text-anchor="middle">'
               f'worst tilt {tilt[worst]:.0f}°: {s30:.2f}</text>')
    out.append(f'<line x1="{X(cross):.1f}" y1="{Y(sf_bulk) - 6:.1f}" x2="{X(cross):.1f}" y2="{Y(sf_bulk) - 26:.1f}" '
               f'stroke="{MUTED}"/>')
    out.append(f'<text x="{X(cross) - 5:.1f}" y="{Y(sf_bulk) - 16:.1f}" font-size="11" fill="{INK}" text-anchor="end">'
               f'past {cross:.0f}° the bulk governs</text>')
    out.append(f'<text x="{x0 - 4}" y="{Y(0.55):.1f}" font-size="11" fill="{MUTED}">'
               f'shaded: the governing check · dots: Study.layer_check() on the solved bar (4 mm P2 mesh, '
               f'middle half: {judged} elements)</text>')
    out.append(f'<text x="{x0 - 4}" y="{Y(0.28):.1f}" font-size="11" fill="{MUTED}">'
               'lines: the same check by hand · interlayer shear allowable assumed S_z / √3 (no data sheet gives '
               'one)</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


# the bracket of layer-criteria.png: base on the bed, an upright wall built up in Z, an R2 fillet at the wall's root
BRACKET = {"base": (40.0, 20.0, 4.0), "wall": (4.0, 30.0), "fillet": 2.0, "push_n": 27.0, "mesh_mm": 2.5,
           "fillet_mesh_mm": 0.6}


def bracket():
    """The solved bracket and its two layer checks, {criterion: LayerCheck}."""
    import cadquery as cq

    from cadagent.simulation.fea import MATERIALS, Study, plane_at
    (bl, bw, bt), (wt, wh), r = BRACKET["base"], BRACKET["wall"], BRACKET["fillet"]
    part = (cq.Workplane("XY").box(bl, bw, bt, centered=(False, True, False))
            .union(cq.Workplane("XY").box(wt, bw, wh, centered=(False, True, False)))
            .edges(cq.selectors.BoxSelector((wt - 0.1, -bw, bt - 0.1), (wt + 0.1, bw, bt + 0.1))).fillet(r))
    fine = [((wt + 0.3 * r, y, bt + 0.3 * r), r + 2, BRACKET["fillet_mesh_mm"]) for y in (-6, 0, 6)]
    st = Study(part, MATERIALS[KEY], mesh_mm=BRACKET["mesh_mm"], name="L bracket", refine=fine)
    st.fix(plane_at(0, bl)).force(plane_at(2, wh), (-BRACKET["push_n"], 0, 0))      # bolted at the base's far end
    st.solve()
    return st, {c: st.layer_check((0, 0, 1), criterion=c) for c in ("combined", "max-stress")}


def criteria_png(st, checks, out: Path) -> None:
    """Study.render(field=) under each criterion, on one fixed scale (0 to 1, black past it), side by side."""
    import tempfile

    import numpy as np
    from PIL import Image

    panels = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, lc in checks.items():
            s = lc.stats["utilisation"]
            past = (f"{s['over_1']} elements past 1 ({s['over_1_volume_mm3']:.2g} mm³)" if s["over_1"]
                    else "nothing past 1")
            title = f"{name}: SF {lc.safety_factor:.2f}, p99 {s['p99']:.2f}, {past}"
            png = st.render(Path(tmp) / f"{name}.png", view=(22, 35), vmax=1.0, field=lc, title=title)
            img = Image.open(png).convert("RGB")
            ink = np.argwhere((np.asarray(img).astype(int).sum(axis=2) < 735))   # trim the white margin
            (y0, x0), (y1, x1) = ink.min(axis=0), ink.max(axis=0)
            panels.append(img.crop((max(x0 - 8, 0), max(y0 - 8, 0), x1 + 8, y1 + 8)))
    w, h = sum(p.width for p in panels) + 16 * (len(panels) - 1), max(p.height for p in panels)
    sheet = Image.new("RGB", (w, h), "white")
    x = 0
    for p in panels:
        sheet.paste(p, (x, 0))
        x += p.width + 16
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("P", palette=Image.ADAPTIVE, colors=256).save(out, optimize=True)


def main() -> None:
    sigma, xy, z, checks, judged = solve()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg(sigma, xy, z, checks, judged), encoding="utf-8")
    for t, lc in checks:
        print(f"{t:3d} deg  SF {lc.safety_factor:.3f}  {lc.governed_by}")
    print(OUT.relative_to(ROOT))
    st, by_criterion = bracket()
    criteria_png(st, by_criterion, OUT_CRITERIA)
    for name, lc in by_criterion.items():
        w, s = lc.worst, lc.stats["utilisation"]
        print(f"bracket {name:10}  SF {lc.safety_factor:.3f}  {lc.governed_by:8}  p99 {s['p99']:.3f}  "
              f"past 1: {s['over_1']} elements, {s['over_1_volume_mm3']:.3g} mm3  worst at {w['corner_mm']} "
              f"(sigma_n {w['sigma_n_mpa']}, tau_n {w['tau_n_mpa']} MPa; {w['resolution']['where']}, "
              f"{w['resolution']['elements_across']} elements across)")
    print(OUT_CRITERIA.relative_to(ROOT))


if __name__ == "__main__":
    main()
