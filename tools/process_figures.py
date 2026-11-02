#!/usr/bin/env python3
"""Draw docs/process-checks.md's figures (docs/img/process/*.svg) from the code that makes the numbers.

    python3 tools/process_figures.py            # write the SVGs
    python3 tools/process_figures.py --check    # exit 1 if a committed SVG differs (tests/manufacturing/test_process_figures.py)

Each figure is computed by the module it shows, on worked examples, never typed in:

* dfm-wall.svg: ``cadagent.manufacturing.dfm.check`` on a 0.9 mm FDM wall with a 0.4 mm nozzle, a row per source;
* layer-factors.svg: ``cadagent.manufacturing.process`` FDM materials, across-the-layers factors from the data sheets;
* sheet-flange.svg: ``cadagent.manufacturing.sheet_metal.bend`` per stock in the shop's table, the shop's shortest
  flange against the generic rules at the shop's own radius.

Stdlib only besides cad-agent; the SVGs carry their own light background so they read the same on the site and on
GitHub in dark mode.
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cadagent.manufacturing import dfm, process, sheet_metal  # noqa: E402

OUT = ROOT / "docs" / "img" / "process"
INK, MUTED, LINE, BG = "#173d3c", "#526863", "#d8e0d3", "#fffdf5"
COLOUR = {"pass": "#6f8a80", "warn": "#c98a16", "fail": "#bd3a12", "info": "#9aa9a4"}
FONT = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif"
W, LABEL_W, PAD = 720, 300, 18
WALL = 0.9
SHORT = {"5052": "5052", "mild-steel": "mild steel"}
NOZZLE = 0.4


def fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _frame(title: str, subtitle: str, h: int) -> list[str]:
    q = {chr(34): "&quot;"}
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" role="img" '
            f'aria-label="{escape(title, q)}" font-family="{FONT}">',
            f'<rect width="{W}" height="{h}" rx="14" fill="{BG}" stroke="{LINE}"/>',
            f'<text x="{PAD}" y="30" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>',
            f'<text x="{PAD}" y="50" font-size="12" fill="{MUTED}">{escape(subtitle)}</text>']


def _axis(out: list[str], x, ticks: list[float], top: float, bottom: float, unit: str) -> None:
    for t in ticks:
        out.append(f'<line x1="{x(t):.1f}" y1="{top}" x2="{x(t):.1f}" y2="{bottom}" stroke="{LINE}"/>')
        out.append(f'<text x="{x(t):.1f}" y="{bottom + 15}" font-size="11" fill="{MUTED}" text-anchor="middle">'
                   f'{fmt(t)}</text>')
    out.append(f'<text x="{W - PAD - 26}" y="{bottom + 30}" font-size="11" fill="{MUTED}" text-anchor="end">'
               f'{escape(unit)}</text>')


def _legend(out: list[str], y: float, items: list[tuple[str, str]]) -> None:
    x = PAD
    for colour, text in items:
        out.append(f'<rect x="{x}" y="{y - 9}" width="12" height="12" rx="3" fill="{colour}"/>')
        out.append(f'<text x="{x + 17}" y="{y + 1}" font-size="11" fill="{INK}">{escape(text)}</text>')
        x += 24 + 6.4 * len(text)


def dfm_wall() -> str:
    r = dfm.check("fdm", [dfm.Feature("wall", "wall", WALL)], nozzle_mm=NOZZLE)["features"][0]
    rows = sorted(r["rules"], key=lambda x: (x.get("max") or x.get("min") or 0))
    row_h, top = 26, 84
    h = top + row_h * len(rows) + 82
    vmax = 2.0
    plot_w = W - LABEL_W - PAD - 30
    x = lambda v: LABEL_W + plot_w * min(v, vmax) / vmax
    out = _frame(f"A {fmt(WALL)} mm FDM wall, checked against every source: {r['verdict']}",
                 f"cadagent.manufacturing.dfm.check, nozzle {fmt(NOZZLE)} mm: {r['detail'].split(',')[0].split(';')[0]}", h)
    bottom = top + row_h * len(rows)
    _axis(out, x, [0, 0.5, 1.0, 1.5, 2.0], top - 8, bottom, "minimum wall, mm")
    out.append(f'<line x1="{x(WALL):.1f}" y1="{top - 14}" x2="{x(WALL):.1f}" y2="{bottom}" stroke="{INK}" '
               f'stroke-width="2" stroke-dasharray="5 3"/>')
    out.append(f'<text x="{x(WALL) + 5:.1f}" y="{top - 16}" font-size="11" font-weight="700" fill="{INK}">'
               f'the wall, {fmt(WALL)} mm</text>')
    for i, row in enumerate(rows):
        cy = top + row_h * i + row_h / 2
        c = COLOUR[row["verdict"]]
        out.append(f'<text x="{LABEL_W - 10}" y="{cy + 4:.1f}" font-size="12" fill="{INK}" text-anchor="end">'
                   f'{escape(row["rule"])}</text>')
        lo, hi = row.get("min"), row.get("max")
        if lo is not None and hi is not None and hi > lo:
            out.append(f'<rect x="{x(lo):.1f}" y="{cy - 5:.1f}" width="{x(hi) - x(lo):.1f}" height="10" rx="5" '
                       f'fill="{c}"/>')
            text, tx = f"{fmt(lo)}–{fmt(hi)} · {row['verdict']}", x(hi) + 8
        else:
            out.append(f'<circle cx="{x(lo):.1f}" cy="{cy:.1f}" r="6" fill="{c}"/>')
            text, tx = f"≥ {fmt(lo)} · {row['verdict']}", x(lo) + 10
        out.append(f'<text x="{tx:.1f}" y="{cy + 4:.1f}" font-size="11" fill="{INK}">{escape(text)}</text>')
    _legend(out, h - 28, [(COLOUR["pass"], "meets the rule"), (COLOUR["warn"], "inside its range"),
                          (COLOUR["fail"], "below it")])
    out.append(f'<text x="{PAD}" y="{h - 8}" font-size="10.5" fill="{MUTED}">A bar: one limit somewhere in the range '
               'by the source\'s own conditions. Rules are research/process-profiles.yaml\'s, by id.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def layer_factors() -> str:
    fdm = process.profile("fdm")
    mats = sorted(fdm.materials.values(), key=lambda m: (m.family, m.key))
    row_h, top = 30, 86
    h = top + row_h * len(mats) + 70
    plot_w = W - LABEL_W - PAD - 40
    x = lambda v: LABEL_W + plot_w * v
    rng = {q: fdm.rule(f"fdm-orientation-z-{q}-ratio-tds").limit() for q in ("strength", "strain")}
    out = _frame("Across the layers, a print keeps less strain than strength",
                 "cadagent.manufacturing.process: Z / XY from each filament's data sheet, the cautious edition", h)
    bottom = top + row_h * len(mats)
    _axis(out, x, [0, 0.25, 0.5, 0.75, 1.0], top - 8, bottom, "across the layers / in the layer plane")
    for i, m in enumerate(mats):
        y0 = top + row_h * i
        out.append(f'<text x="{LABEL_W - 10}" y="{y0 + row_h / 2 + 4:.1f}" font-size="12" fill="{INK}" '
                   f'text-anchor="end">{escape(m.name)}</text>')
        for j, (q, c) in enumerate((("strength", COLOUR["pass"]), ("strain", COLOUR["fail"]))):
            v = m.factor(q).value
            yy = y0 + 5 + j * 11
            out.append(f'<rect x="{LABEL_W}" y="{yy:.1f}" width="{x(v) - LABEL_W:.1f}" height="9" rx="2" fill="{c}"/>')
            out.append(f'<text x="{x(v) + 5:.1f}" y="{yy + 8:.1f}" font-size="10" fill="{INK}">{v:.2f}</text>')
    _legend(out, h - 34, [(COLOUR["pass"], "tensile strength"), (COLOUR["fail"], "strain to failure")])
    s, e = rng["strength"], rng["strain"]
    out.append(f'<text x="{PAD}" y="{h - 12}" font-size="10.5" fill="{MUTED}">'
               f'{escape(f"The profile range over PLA, PETG, ASA and CoPA sheets: strength {s.text}, strain {e.text} (fdm-orientation-z-*-ratio-tds).")}'
               '</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def sheet_flange() -> str:
    sheet = process.profile("sheet-metal")
    rows = []
    for key in ("5052", "mild-steel"):
        mat = sheet.material(key)
        for st in mat.stocks:
            shop = sheet_metal.bend(key, st.T)
            generic = sheet_metal.bend(key, st.T, radius_mm=st.R, k=st.K, shop=False)["min_flange_mm"]["all"]
            mins = [g["min"] for g in generic]
            rows.append((f"{st.sku} · {SHORT[key]} {fmt(st.T)} mm, R {fmt(st.R)}",
                         shop["min_flange_mm"]["value"], min(mins), max(mins), shop["k"]["value"],
                         shop["deduction_mm"]))
    row_h, top = 24, 86
    h = top + row_h * len(rows) + 70
    vmax = 16.0
    plot_w = W - LABEL_W - PAD - 110
    x = lambda v: LABEL_W + plot_w * min(v, vmax) / vmax
    out = _frame("Shortest flange: the shop's tooling first, the generic rules beside it",
                 "cadagent.manufacturing.sheet_metal.bend per stock in the shop's table; generic rules at its radius", h)
    bottom = top + row_h * len(rows)
    _axis(out, x, [0, 4, 8, 12, 16], top - 8, bottom, "flange, mm")
    out.append(f'<text x="{W - PAD}" y="{top - 14}" font-size="10.5" fill="{MUTED}" text-anchor="end">K · BD at 90°</text>')
    for i, (name, shop, lo, hi, k, bd) in enumerate(rows):
        cy = top + row_h * i + row_h / 2
        out.append(f'<text x="{LABEL_W - 10}" y="{cy + 4:.1f}" font-size="11.5" fill="{INK}" text-anchor="end">'
                   f'{escape(name)}</text>')
        out.append(f'<rect x="{x(lo):.1f}" y="{cy - 4:.1f}" width="{x(hi) - x(lo):.1f}" height="8" rx="4" '
                   f'fill="{COLOUR["info"]}" fill-opacity="0.55"/>')
        out.append(f'<circle cx="{x(shop):.1f}" cy="{cy:.1f}" r="5.5" fill="{COLOUR["fail"]}"/>')
        out.append(f'<text x="{W - PAD}" y="{cy + 4:.1f}" font-size="11" fill="{INK}" text-anchor="end">'
                   f'{k:.2f} · {bd:.2f} mm</text>')
    _legend(out, h - 34, [(COLOUR["fail"], "the shop's shortest flange (decides)"),
                          (COLOUR["info"], "generic rules: 2T + R, 4T, 3.5 (T + R)")])
    out.append(f'<text x="{PAD}" y="{h - 12}" font-size="10.5" fill="{MUTED}">Shop table: sendcutsend-specs, read '
               f'{escape(sheet.material("5052").stocks[0].verified_on)}. BD: bend deduction, the length a 90° bend takes '
               'off the outside dimensions.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


FIGURES = {"dfm-wall.svg": dfm_wall, "layer-factors.svg": layer_factors, "sheet-flange.svg": sheet_flange}


def main(argv: list[str]) -> int:
    stale = []
    for name, make in FIGURES.items():
        text, path = make(), OUT / name
        if "--check" in argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            OUT.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if stale:
        print("out of date with the code (run python3 tools/process_figures.py):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
