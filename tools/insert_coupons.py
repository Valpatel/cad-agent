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
PROJECTION = (1.0, -1.0, 0.8)       # from above a front corner: +Z comes out up


def coupons():
    """(name, solid) for every coupon: each insert upright and lying, then each insert's clamp plates."""
    out = []
    for key, ins in I.INSERTS.items():
        for axis in I.AXES:
            out.append((f"{ins.thread}x{ins.length_mm:g}-{axis}", I.coupon_block(ins, axis)))
        lim = I.limiter_for(ins)
        if lim is not None:
            out.append((f"{ins.thread}x{ins.length_mm:g}-plate-limiter",
                        I.clamp_plate(lim["plate_mm"], lim["hole_mm"])))
        out.append((f"{ins.thread}x{ins.length_mm:g}-plate-plastic",
                    I.clamp_plate(I.CLAMP_PLATE_MM, I.CLEARANCE_MM[ins.thread])))
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


def _projected(solid):
    """One solid's visible edges as CadQuery projects them (its HLR, isometric): a list of path strings in model mm,
    y up, and their bounding box (x0, y0, x1, y1)."""
    import cadquery as cq
    raw = cq.exporters.getSVG(cq.Compound.makeCompound([solid]),
                              opts={"projectionDir": PROJECTION, "showHidden": False, "showAxes": False})
    visible = raw.split("<!-- solid lines -->", 1)[1]
    paths = re.findall(r'<path d="([^"]+)"', visible)
    nums = [float(v) for d in paths for v in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", d)]
    xs, ys = nums[0::2], nums[1::2]
    return paths, (min(xs), min(ys), max(xs), max(ys))


def _moved(d: str, dx: float, dy: float, k: float) -> str:
    """A path's points scaled by k and moved by (dx, dy). For this projection CadQuery's path y already runs down
    the picture, as SVG's does."""
    vals = iter(re.findall(r"[ML]|-?\d+(?:\.\d+)?(?:e-?\d+)?", d))
    out = []
    for tok in vals:
        if tok in "ML":
            out.append(tok)
            continue
        x, y = float(tok), float(next(vals))
        out.append(f"{S.num((dx + k * x) * S.UNITS_PER_PX, 1)},{S.num((dy + k * y) * S.UNITS_PER_PX, 1)}")
    return " ".join(out)


def figure() -> str:
    """The upright and lying coupons of three inserts (M3, M5, M8), side by side, each as CadQuery projects it."""
    keys = ["mcmaster-94459A140", "mcmaster-94459A775", "mcmaster-94459A778"]
    views = []
    for key in keys:
        ins = I.insert(key)
        for axis in I.AXES:
            views.append((f"{ins.thread} {axis}", *_projected(I.coupon_block(ins, axis))))
    w, h, gap, left, base = 880, 300, 24.0, 20.0, 220.0
    widest = sum(b[2] - b[0] for _, _, b in views)
    k = (w - 2 * left - gap * (len(views) - 1)) / widest           # one scale for all: sizes compare
    U = S.UNITS_PER_PX
    body, x = [], left
    for label, paths, (x0, y0, x1, y1) in views:
        dx, dy = x - k * x0, base - k * y1
        body += [f'<path class="cad" d="{_moved(d, dx, dy, k)}"/>' for d in paths]
        body.append(f'<text x="{S.num((x + k * (x1 - x0) / 2) * U, 1)}" y="{S.num((base + 26) * U, 1)}" '
                    f'text-anchor="middle">{label}</text>')
        x += k * (x1 - x0) + gap
    css = (f".cad{{fill:none;stroke:var(--edge);stroke-width:{1.1 * U};stroke-linejoin:round}}"
           f"text{{fill:var(--ink);font-size:{13 * U}px}}.small{{fill:var(--muted);font-size:{11 * U}px}}")
    body.append(f'<text class="small" x="{S.num(left * U, 0)}" y="{S.num((h - 18) * U, 0)}">CadQuery\'s projection of '
                f'the coupon solids (cadagent.mechanical.inserts.coupon_block), to one scale, each in its print '
                f'orientation</text>')
    title = ("Insert test coupons as CAD: for M3, M5 and M8, a block printed upright (the insert's axis along the "
             "build direction) and one printed lying (its axis in the layer plane), each with its designed hole")
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
