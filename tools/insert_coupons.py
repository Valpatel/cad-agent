#!/usr/bin/env python3
"""The insert coupons of the test plan (cadagent.mechanical.inserts.coupon_plan), as CAD to print.

    PYTHONPATH=src python3 tools/insert_coupons.py --out exports/insert-coupons   # STEP + STL per coupon, plan.json
    PYTHONPATH=src python3 tools/insert_coupons.py --figure                       # docs/img/inserts/coupons.svg
    PYTHONPATH=src python3 tools/insert_coupons.py --figure --check               # exit 1 if the figure is stale

Each insert gets a block printed upright (the insert's axis along the build direction) and one printed lying (its
axis in the layer plane); the same block is pulled out and turned out. The clamp coupons add a printed plate with a
hole for a compression limiter or for the screw alone. Every solid is in its print orientation: +Z is the build
direction, so the STL goes on the bed as it is. The figure is CadQuery's own projection of the solids (its SVG
export), recoloured for light and dark: what is drawn is the CAD, not a sketch of it. Needs CadQuery.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from cadagent.mechanical import inserts as I                          # noqa: E402
from cadagent.publish.anim import svg as S                            # noqa: E402

FIGURE = ROOT / "docs" / "img" / "inserts" / "coupons.svg"
PROJECTION = (1.0, -1.6, 1.1)


def coupons():
    """(name, solid) for every coupon: each insert upright and lying, then each insert's clamp plates."""
    out = []
    for key, ins in I.INSERTS.items():
        for axis in I.AXES:
            out.append((f"{ins.thread}x{ins.length_mm:g}-{axis}", I.coupon_block(ins, axis)))
        lim = I.limiter_for(ins)
        if lim is not None:
            out.append((f"{ins.thread}x{ins.length_mm:g}-plate-limiter",
                        I.clamp_plate(lim["length_mm"], lim["hole_mm"])))
        out.append((f"{ins.thread}x{ins.length_mm:g}-plate-plastic",
                    I.clamp_plate(I.CLAMP_PLATE_MM, ins.diameter_mm + 0.4)))
    return out


def write(out_dir: Path) -> None:
    import cadquery as cq
    from cadagent.geometry import export_step
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, solid in coupons():
        export_step(solid, out_dir / f"{name}.step", name=name)
        cq.exporters.export(cq.Workplane().add(solid), str(out_dir / f"{name}.stl"), tolerance=0.02,
                            angularTolerance=0.1)
    (out_dir / "plan.json").write_text(json.dumps(I.coupon_plan(), indent=1, default=str) + "\n")
    print(f"wrote {len(coupons())} coupons and plan.json to {out_dir}")


def figure() -> str:
    """The upright and lying coupons of three inserts (M3, M5, M8), side by side, as CadQuery projects them."""
    import cadquery as cq
    keys = ["mcmaster-94459A140", "mcmaster-94459A775", "mcmaster-94459A778"]
    solids, x = [], 0.0
    labels = []
    for key in keys:
        ins = I.insert(key)
        for axis in I.AXES:
            s = I.coupon_block(ins, axis)
            bb = s.BoundingBox()
            solids.append(s.translate(cq.Vector(x - bb.xmin, 0, 0)))
            labels.append((x + bb.xlen / 2, f"{ins.thread} {axis}"))
            x += bb.xlen + 8.0
    raw = cq.exporters.getSVG(cq.Compound.makeCompound(solids),
                              opts={"width": 820, "height": 230, "marginLeft": 20, "marginTop": 20,
                                    "projectionDir": PROJECTION, "showHidden": False, "showAxes": False,
                                    "strokeWidth": 0.25})
    transform = re.search(r'<g transform="([^"]+)"', raw).group(1)
    visible = raw.split("<!-- solid lines -->", 1)[1]
    paths = re.findall(r'<path d="([^"]+)"', visible)
    w, h = 860, 300
    U = S.UNITS_PER_PX
    body = [f'<g transform="scale({U}) translate(10 20)"><g transform="{transform}" class="cad">']
    body += [f'<path d="{d}"/>' for d in paths]
    body.append("</g></g>")
    css = (".cad{fill:none;stroke:var(--edge);stroke-width:.25;stroke-linejoin:round}"
           f"text{{fill:var(--ink);font-size:{12 * U}px}}")
    body.append(f'<text x="{20 * U}" y="{(h - 16) * U}">CadQuery\'s projection of the coupon solids '
                f'(cadagent.mechanical.inserts.coupon_block), each in its print orientation: upright then lying, '
                f'for M3, M5 and M8</text>')
    title = ("Insert test coupons as CAD: for each insert a block printed upright (the insert's axis along the build "
             "direction) and one printed lying (its axis in the layer plane), each with the maker's hole; M3, M5 "
             "and M8 shown")
    return S.document(w, h, title, title, css, body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, help="write every coupon's STEP and STL and the plan here")
    ap.add_argument("--figure", action="store_true", help="write docs/img/inserts/coupons.svg")
    ap.add_argument("--check", action="store_true", help="with --figure: exit 1 if the committed figure differs")
    a = ap.parse_args()
    if a.out:
        write(a.out)
    if a.figure:
        svg = figure()
        if a.check:
            if not FIGURE.exists() or FIGURE.read_text() != svg:
                print(f"stale: {FIGURE.relative_to(ROOT)} (run tools/insert_coupons.py --figure)")
                return 1
        else:
            FIGURE.parent.mkdir(parents=True, exist_ok=True)
            FIGURE.write_text(svg)
            print(f"wrote {FIGURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
