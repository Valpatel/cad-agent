"""Deterministic SVG figures for snap-fit results: the arm, its deflected shape, the undercut and the root strain.

Pure Python (no plotting library), so docs and the showcase (#104) draw exactly what the calculator computed. The
deflected curve is the end-loaded cantilever shape y(x) = y_tip * x^2 (3l - x) / (2 l^3), drawn for illustration;
the numbers in the labels come from the result, not from the drawing.
"""
from __future__ import annotations

import math
from typing import Any, Dict
from xml.sax.saxutils import escape


def _strain_colour(ratio: float) -> str:
    """Green under 80 % of allowable, amber to 100 %, red above."""
    if ratio <= 0.8:
        return "#2e9d5b"
    if ratio <= 1.0:
        return "#d39a1c"
    return "#c8372d"


def cantilever_svg(result: Dict[str, Any], length_mm: float, root_mm: float, design: int = 1,
                   lead_deg: float = 30.0, width_px: int = 640) -> str:
    """Side view of a cantilever snap from :func:`snapfit.check_cantilever` / ``check_spec_entry`` output: the arm as
    made (dashed) and fully deflected over the catch (filled, coloured by root strain against the allowable)."""
    L, t0 = float(length_mm), float(root_mm)
    tL = t0 / 2 if design == 2 else t0
    y_tip = float(result["deflection_mm"])
    u = y_tip                                                        # hook height = the undercut it rides over
    allow = float(result.get("material", {}).get("allowable") or result["rows"][0]["limit"])
    ratio = float(result["strain"]) / allow if allow else 0.0
    ramp = u / max(math.tan(math.radians(lead_deg)), 0.2)            # lead ramp length along the arm
    face_x = max(L - ramp, L * 0.6)

    def thick(x: float) -> float:
        return t0 + (tL - t0) * min(x, L) / L

    def defl(x: float) -> float:
        x = min(x, L)
        return -y_tip * x * x * (3 * L - x) / (2 * L ** 3)

    n = 24
    xs = [L * i / n for i in range(n + 1)]
    # y grows downwards; the top fibre is y = 0, the hook hangs below the arm's tip and the arm deflects upwards
    outline = [(x, 0.0) for x in xs] + [(L, thick(L)), (face_x, thick(face_x) + u), (face_x, thick(face_x))] + \
              [(x, thick(x)) for x in reversed(xs) if x < face_x]
    bent = [(x, y + defl(x)) for x, y in outline]
    pts = outline + bent
    xmin, xmax = -4.0, max(x for x, _ in pts) + 0.35 * L
    ymin, ymax = min(y for _, y in pts) - 1.5, max(y for _, y in pts) + 1.5
    plot_h = 260
    scale = min((width_px - 120) / (xmax - xmin), plot_h / (ymax - ymin))
    ox, oy = 60 - xmin * scale, 20 - ymin * scale

    def P(x: float, y: float) -> str:
        return f"{ox + x * scale:.1f},{oy + y * scale:.1f}"

    col = _strain_colour(ratio)
    name = escape(str(result.get("name", "snap")))
    h = int(20 + (ymax - ymin) * scale + 80)
    wall_top, wall_bot = oy + (ymin + 0.5) * scale, oy + (ymax - 0.5) * scale
    dim_x = ox + (L + 0.12 * L) * scale
    y0, y1 = oy + (thick(face_x) + u) * scale, oy + (thick(face_x) + u + defl(face_x)) * scale
    forces = (f' · P {result["deflection_force_n"]:.1f} N' if "deflection_force_n" in result else '') + \
             (f' · W {result["mating_force_n"]:.1f} N' if "mating_force_n" in result else '')
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} {h}" width="{width_px}" height="{h}" '
        f'role="img" aria-label="{name}: cantilever snap, root strain {result["strain"] * 100:.2f} percent">',
        '<style>text{font:13px system-ui,sans-serif;fill:#333}.dim{stroke:#555;stroke-width:1;fill:none}'
        '@media (prefers-color-scheme:dark){text{fill:#ddd}.dim{stroke:#aaa}}</style>',
        f'<rect x="{ox - 4 * scale:.1f}" y="{wall_top:.1f}" width="{4 * scale:.1f}" height="{wall_bot - wall_top:.1f}" '
        'fill="#9aa4ad" opacity="0.5"/>',
        f'<polygon points="{" ".join(P(x, y) for x, y in outline)}" fill="none" stroke="#888" stroke-dasharray="4 3"/>',
        f'<polygon points="{" ".join(P(x, y) for x, y in bent)}" fill="{col}" fill-opacity="0.25" stroke="{col}" '
        'stroke-width="2"/>',
        f'<circle cx="{ox:.1f}" cy="{oy:.1f}" r="5" fill="{col}"><title>root: peak strain</title></circle>',
        f'<line class="dim" x1="{dim_x:.1f}" y1="{y0:.1f}" x2="{dim_x:.1f}" y2="{y1:.1f}"/>',
        f'<line class="dim" x1="{ox + face_x * scale:.1f}" y1="{y0:.1f}" x2="{dim_x + 4:.1f}" y2="{y0:.1f}" '
        'stroke-dasharray="2 2"/>',
        f'<text x="{dim_x + 6:.1f}" y="{(y0 + y1) / 2 + 4:.1f}">y {y_tip:.2f} mm</text>',
        f'<text x="60" y="{h - 46}">{name} · design {design} · l {L:g} mm · h {t0:g} mm'
        + (f' → {tL:g} mm' if design == 2 else '') + f' · lead {lead_deg:g}°</text>',
        f'<text x="60" y="{h - 26}" style="fill:{col}">root strain {result["strain"] * 100:.2f} % of '
        f'{allow * 100:.2f} % allowed ({ratio * 100:.0f} %){forces}</text>',
        f'<text x="60" y="{h - 8}" style="font-size:11px;opacity:.75">{"PASS" if result["pass"] else "FAIL"} · '
        'dashed: as made · filled: deflected over the catch (shape illustrative, numbers computed)</text>',
        '</svg>',
    ]
    return "\n".join(lines) + "\n"
