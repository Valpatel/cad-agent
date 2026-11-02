#!/usr/bin/env python3
"""Draw docs/img/joints/*.svg from cadagent.mechanical.printed_joints and cadagent.manufacturing.fit_coupons.

    python3 tools/printed_joint_figures.py            # write the SVGs
    python3 tools/printed_joint_figures.py --check    # exit 1 if a committed SVG differs (tests/test_printed_joints.py)

Pure Python, so the page shows exactly what the checks computed on the worked examples below (generic parts, not
any one project's). Colours: the categorical slots and status steps of the site's chart palette, each with a label,
so no meaning rests on colour alone.
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cadagent.manufacturing import fit_coupons as fc          # noqa: E402  (this checkout's package)
from cadagent.mechanical import printed_joints as pj          # noqa: E402

OUT = ROOT / "docs" / "img" / "joints"
# The worked examples the page quotes: a 5 mm pin through a 6 mm PETG eye at 900 N; a 16 mm PLA boss, 20 mm tall,
# with an M5 rod at 3 N m; the coupon for a 5 mm pin in a sliding fit.
EYE = dict(material="petg-bambu-basic", load_n=900, pin_mm=5, thickness_mm=6, edge_mm=10, width_mm=16)
EYE_BUSHING_MM = 8
EYE_VARIANTS = (("printed flat, bare", {}), ("printed flat, bushed", {"bushing_mm": EYE_BUSHING_MM}),
                ("on its side, bare", {"pin_axis": (0, 1, 0)}),
                ("on its side, bushed", {"pin_axis": (0, 1, 0), "bushing_mm": EYE_BUSHING_MM}))
BOSS = dict(material="pla-bambu-basic", height_mm=20, section=pj.tube(16, 5.5))
BOLT = pj.through_bolt(5, 0.8, torque_nm=3)
COUPON = fc.Fit("pivot pin", 5.0, "slide")
MODES = ("bearing", "shear-out", "net tension")
STYLE = ("<style>text{font:13px system-ui,sans-serif;fill:#1d1d1b}.muted{fill:#5c5b56;font-size:11px}"
         ".axis{stroke:#9b9a93;stroke-width:1;fill:none}.grid{stroke:#e2e1dc;stroke-width:1}"
         ".s1{fill:#2a78d6;stroke:#2a78d6}.s2{fill:#eb6834;stroke:#eb6834}.s3{fill:#1baf7a;stroke:#1baf7a}"
         ".part{fill:#eef1e4;stroke:#173d3c;stroke-width:1.5}.hole{fill:#fcfcfb;stroke:#173d3c;stroke-width:1.5}"
         ".bg{fill:#fcfcfb}"
         "@media (prefers-color-scheme:dark){text{fill:#f0efec}.muted{fill:#c3c2b7}.axis{stroke:#8a897f}"
         ".grid{stroke:#383835}.s1{fill:#3987e5;stroke:#3987e5}.s2{fill:#d95926;stroke:#d95926}"
         ".s3{fill:#199e70;stroke:#199e70}.part{fill:#2a3330;stroke:#c3c2b7}.hole{fill:#1a1a19;stroke:#c3c2b7}"
         ".bg{fill:#1a1a19}}</style>")
VERDICT_MARK = {"pass": "pass", "warn": "warn ▲", "fail": "fail ✕"}


def _svg(width: int, height: int, label: str, body: list) -> str:
    return "\n".join([f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
                      f'height="{height}" role="img" aria-label="{escape(label)}">', STYLE,
                      f'<rect class="bg" width="{width}" height="{height}"/>', *body, "</svg>"]) + "\n"


def eye_figure() -> str:
    """Left: the eye along its pin, the three sections marked. Right: each section's safety factor in four builds."""
    e, w, D, Db = EYE["edge_mm"], EYE["width_mm"], EYE["pin_mm"], EYE_BUSHING_MM
    s, ox, oy = 8.0, 110.0, 150.0                                   # px per mm, the hole's centre
    body = [f'<path class="part" d="M{ox - 2.2 * w * s / 2:.1f},{oy - w * s / 2:.1f} H{ox + (e - w / 2) * s:.1f} '
            f'A{w * s / 2:.1f},{w * s / 2:.1f} 0 0 1 {ox + (e - w / 2) * s:.1f},{oy + w * s / 2:.1f} '
            f'H{ox - 2.2 * w * s / 2:.1f} Z"/>',
            f'<circle class="hole" cx="{ox}" cy="{oy}" r="{Db * s / 2:.1f}" stroke-dasharray="4 3"/>',
            f'<circle class="hole" cx="{ox}" cy="{oy}" r="{D * s / 2:.1f}"/>',
            # bearing: the hole's front half; shear-out: two planes to the end; net tension: across beside the hole
            f'<path class="s1" style="fill:none" stroke-width="4" d="M{ox},{oy - D * s / 2:.1f} A{D * s / 2:.1f},'
            f'{D * s / 2:.1f} 0 0 1 {ox},{oy + D * s / 2:.1f}"><title>bearing on the hole</title></path>']
    for sign in (-1, 1):
        y = oy + sign * D * s / 2
        body.append(f'<line class="s2" stroke-width="3" stroke-dasharray="6 3" x1="{ox:.1f}" y1="{y:.1f}" '
                    f'x2="{ox + (e - 0.4) * s:.1f}" y2="{y:.1f}"><title>shear-out plane</title></line>')
        y0, y1 = oy + sign * D * s / 2, oy + sign * w * s / 2
        body.append(f'<line class="s3" stroke-width="4" x1="{ox:.1f}" y1="{y0:.1f}" x2="{ox:.1f}" y2="{y1:.1f}">'
                    '<title>net section</title></line>')
    body += [f'<line class="axis" x1="{ox}" y1="{oy}" x2="{ox + 40}" y2="{oy}" marker-end="url(#a)"/>',
             '<defs><marker id="a" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" '
             'orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#9b9a93"/></marker></defs>',
             f'<text x="20" y="{oy - w * s / 2 - 10:.0f}" class="muted">the pin pulls {EYE["load_n"]} N towards the '
             'end (arrow)</text>',
             f'<text x="20" y="{oy + w * s / 2 + 26:.0f}" class="muted">pin {D:g} mm · dashed: {Db:g} mm bushing</text>',
             f'<text x="20" y="{oy + w * s / 2 + 42:.0f}" class="muted">e {e:g} mm · w {w:g} mm · t '
             f'{EYE["thickness_mm"]:g} mm · PETG</text>',
             '<text x="20" y="30">The eye, along its pin</text>']
    # the bars
    x0, x1, top, fmax = 420.0, 700.0, 50.0, 4.5
    px = (x1 - x0) / fmax
    body += ['<text x="290" y="30">Safety factor of each section (strength over stress)</text>',
             f'<text x="{x0}" y="316" class="muted">dashed: fails below 1, passes from {pj.SAFETY:g}</text>']
    for f in (1.0, pj.SAFETY):
        xx = x0 + f * px
        body.append(f'<line class="grid" x1="{xx:.1f}" y1="{top - 6:.0f}" x2="{xx:.1f}" y2="300" '
                    'style="stroke:#9b9a93;stroke-dasharray:3 3"/>')
        body.append(f'<text x="{xx:.1f}" y="{top - 9:.0f}" text-anchor="middle" class="muted">{f:g}</text>')
    y = top
    for title, kw in EYE_VARIANTS:
        r = pj.pin_eye(**EYE, **kw)
        by = {row["check"]: row for row in r["rows"]}
        body.append(f'<text x="{x0 - 8:.0f}" y="{y + 12:.0f}" text-anchor="end">{escape(title)}</text>')
        for i, mode in enumerate(MODES):
            factor = by[mode]["limit"]["factor"]
            length = min(factor, fmax) * px
            yy = y + i * 15
            body.append(f'<rect class="s{i + 1}" x="{x0}" y="{yy:.0f}" width="{length:.1f}" height="11" rx="2">'
                        f'<title>{escape(title)}: {mode} factor {factor:.2f} ({by[mode]["verdict"]})</title></rect>')
            body.append(f'<text x="{x0 + length + 4:.1f}" y="{yy + 10:.0f}" class="muted">{factor:.2f} '
                        f'{VERDICT_MARK[by[mode]["verdict"]]}</text>')
        y += 64
    lx = 20
    for i, mode in enumerate(MODES):
        body.append(f'<rect class="s{i + 1}" x="{lx}" y="330" width="12" height="12" rx="2"/>'
                    f'<text x="{lx + 17}" y="340">{mode}</text>')
        lx += 120
    return _svg(760, 352, "Safety factors of a pin eye's bearing, shear-out and net section, printed flat or on its "
                "side, bare or with a bushing", body)


def peel_figure() -> str:
    """The root's layer stress against the side load: no bolt, the rod's preload kept, the rod's most preload."""
    sec = BOSS["section"]
    m = pj.PRINTED[BOSS["material"]]
    s_z, s_xy = m.strength("across") / pj.SAFETY, m.strength("along") / pj.SAFETY
    kept, high = pj.RETAINED * BOLT["preload_n"]["low"], BOLT["preload_n"]["high"]
    loads = [10.0 * i for i in range(0, 21)]
    # each point is root_peel's own: its states' mean (clamp and axial) and bending stresses at that side load (the
    # check needs a load above 0, so the first point is taken at 1 mN)
    states = [pj.root_peel(BOSS["material"], max(p, 1e-3), BOSS["height_mm"], sec, bolt=BOLT)["states"] for p in loads]
    series = (("no rod: tension side", "s2", [s["no bolt"]["mean_mpa"] + s["no bolt"]["bending_mpa"] for s in states]),
              (f"rod kept at {kept:.0f} N: tension side", "s1",
               [s["kept"]["mean_mpa"] + s["kept"]["bending_mpa"] for s in states]),
              (f"rod at its most, {high:.0f} N: compression side", "s3",
               [s["tightened"]["mean_mpa"] - s["tightened"]["bending_mpa"] for s in states]))
    x0, x1, y0, y1, vmin, vmax = 60.0, 480.0, 40.0, 300.0, -40.0, 20.0

    def X(p):
        return x0 + (x1 - x0) * p / loads[-1]

    def Y(v):
        return y0 + (y1 - y0) * (vmax - v) / (vmax - vmin)

    body = ['<text x="20" y="24">Layer stress at the root of an upright boss (MPa), against the side load (N)</text>']
    for v in range(-40, 21, 10):
        body.append(f'<line class="grid" x1="{x0}" y1="{Y(v):.1f}" x2="{x1}" y2="{Y(v):.1f}"/>'
                    f'<text x="{x0 - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="muted">{v}</text>')
    for p in range(0, 201, 50):
        body.append(f'<text x="{X(p):.1f}" y="{y1 + 16:.0f}" text-anchor="middle" class="muted">{p}</text>')
    body += [f'<line class="axis" x1="{x0}" y1="{Y(0):.1f}" x2="{x1}" y2="{Y(0):.1f}" style="stroke-width:1.5"/>',
             f'<text x="{x1 - 4}" y="{Y(0) + 14:.1f}" text-anchor="end" class="muted">0: the seam just closed</text>',
             f'<line class="axis" x1="{x0}" y1="{Y(s_z):.1f}" x2="{x1}" y2="{Y(s_z):.1f}" stroke-dasharray="5 3"/>',
             f'<text x="{x1 - 4}" y="{Y(s_z) - 5:.1f}" text-anchor="end" class="muted">+{s_z:.1f}: across-layer '
             f'strength / {pj.SAFETY:g}</text>',
             f'<line class="axis" x1="{x0}" y1="{Y(-s_xy):.1f}" x2="{x1}" y2="{Y(-s_xy):.1f}" stroke-dasharray="5 3"/>',
             f'<text x="{x1 - 4}" y="{Y(-s_xy) + 14:.1f}" text-anchor="end" class="muted">−{s_xy:.1f}: in-plane '
             f'strength / {pj.SAFETY:g} (squeeze)</text>']
    for name, cls, vals in series:
        pts = " ".join(f"{X(p):.1f},{Y(v):.1f}" for p, v in zip(loads, vals))
        body.append(f'<polyline class="{cls}" fill="none" stroke-width="2" points="{pts}">'
                    f'<title>{escape(name)}: {vals[-1]:.1f} MPa at {loads[-1]:.0f} N</title></polyline>')
        body.append(f'<circle class="{cls}" cx="{X(loads[-1]):.1f}" cy="{Y(vals[-1]):.1f}" r="4"/>')
        body.append(f'<text x="{X(loads[-1]) + 10:.1f}" y="{Y(vals[-1]) + 4:.1f}">{escape(name)}</text>')
    r = pj.root_peel(BOSS["material"], 100, BOSS["height_mm"], sec, bolt=BOLT)
    lo, hi = r["advice"]["torque_window_nm"]
    body.append(f'<text x="20" y="{y1 + 40:.0f}" class="muted">PLA, a 16 mm boss on a 5.5 mm bore, loaded 20 mm up; '
                f'an M5 rod at 3 N·m ({BOLT["preload_n"]["low"]:.0f}–{high:.0f} N), {pj.RETAINED:g} of it kept.</text>')
    body.append(f'<text x="20" y="{y1 + 58:.0f}" class="muted">At 100 N: {VERDICT_MARK[r["verdict"]]} (factor '
                f'{r["margin"]:.2f}). Staying closed wants {lo:.2f} N·m or more; sparing the squeezed side, at most '
                f'{hi:.2f} N·m.</text>')
    return _svg(800, int(y1 + 72), "Root layer stress of an upright printed boss with and without a through-rod's "
                "preload", body)


def coupon_figure() -> str:
    """The coupon for a 5 mm pin in a sliding fit, from above, each hole with its CAD diameter."""
    lay = fc.layout(COUPON)
    w, h = lay["size_mm"]
    s, ox, oy = 14.0, 30.0, 40.0
    n = fc.NOTCH_MM
    body = [f'<text x="20" y="24">Fit coupon: {escape(COUPON.name)}, {COUPON.nominal_mm:g} mm, {COUPON.kind} '
            f'(CAD {COUPON.centre_mm:g} ± {COUPON.step_mm * (COUPON.count // 2):g} mm)</text>',
            f'<path class="part" d="M{ox + n * s:.1f},{oy + h * s:.1f} H{ox + w * s:.1f} V{oy:.1f} H{ox:.1f} '
            f'V{oy + (h - n) * s:.1f} Z"/>']
    for i, ((x, y), d) in enumerate(zip(lay["centres_mm"], lay["diameters_mm"]), start=1):
        cx, cy = ox + x * s, oy + (h - y) * s
        body.append(f'<circle class="hole" cx="{cx:.1f}" cy="{cy:.1f}" r="{d * s / 2:.1f}"><title>hole {i}: '
                    f'{d:.2f} mm in CAD</title></circle>')
        body.append(f'<text x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" style="font-size:11px">{d:.2f}'
                    '</text>')
    tx = ox + w * s + 24
    lines = [f"hole 1 by the notched corner; sizes rise along each row",
             f"nominal {COUPON.nominal_mm:g} + slide {COUPON.allowance:g} + undersize {COUPON.undersize_mm:g} mm",
             f"{COUPON.count} holes, {COUPON.step_mm:g} mm apart, {lay['thickness_mm']:g} mm thick",
             "print it like the part, try the real pin,",
             "note which hole fits: from_coupon() gives the offset"]
    for k, line in enumerate(lines):
        body.append(f'<text x="{tx:.0f}" y="{oy + 18 + 20 * k:.0f}" class="muted">{escape(line)}</text>')
    return _svg(int(tx + 310), int(oy + h * s + 20), f"Fit coupon for a {COUPON.nominal_mm:g} mm pin: nine holes "
                "from 5.30 to 5.70 mm", body)


FIGURES = {"eye.svg": eye_figure, "peel.svg": peel_figure, "coupon.svg": coupon_figure}


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    stale = []
    for name, draw in FIGURES.items():
        path, svg = OUT / name, draw()
        if check:
            if not path.exists() or path.read_text() != svg:
                stale.append(str(path.relative_to(ROOT)))
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_text(svg)
    if stale:
        print("out of date (run python3 tools/printed_joint_figures.py):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
