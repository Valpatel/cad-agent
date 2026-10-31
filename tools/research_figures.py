#!/usr/bin/env python3
"""Regenerate the research pages' charts (docs/img/research/*.svg) from the tables on those pages.

    python3 tools/research_figures.py            # write the SVGs
    python3 tools/research_figures.py --check    # exit 1 if a committed SVG differs from its table (tests run this)

The tables are the source: a chart can never disagree with the page it illustrates. Stdlib only; the SVGs carry their
own light background so they read the same on the site and on GitHub in dark mode.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "research"
INK, MUTED, LINE, BG, GREEN, ORANGE = "#173d3c", "#526863", "#d8e0d3", "#fffdf5", "#6f8a80", "#bd3a12"
FONT = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif"


def table(md: str, heading: str) -> list[list[str]]:
    """The rows (cells, stripped) of the first Markdown table after ``heading``."""
    start = md.index(heading)
    rows, seen = [], False
    for line in md[start:].splitlines()[1:]:
        if line.startswith("|"):
            seen = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not set("".join(cells)) <= set("-: "):
                rows.append(cells)
        elif seen:
            break
    return rows[1:]                                   # without the header row


def number(cell: str) -> tuple[float, str] | None:
    m = re.match(r"^(≥|>)?\s*([0-9]+(?:\.[0-9]+)?)$", cell.replace(",", ""))
    return (float(m.group(2)), m.group(1) or "") if m else None


def bars_svg(title: str, rows: list[tuple[str, list[tuple[float, str]]]], series: list[tuple[str, str]],
             vmax: float, ticks: list[float], fmt, note: str) -> str:
    """Horizontal grouped bars: one group per row, one bar per series, the value printed at the bar's end."""
    w, label_w, pad = 680, 210, 18
    bar_h, gap, group_gap = 13, 3, 14
    group_h = len(series) * bar_h + (len(series) - 1) * gap
    top = 70
    h = top + len(rows) * (group_h + group_gap) + 44
    plot_w = w - label_w - pad - 56
    x = lambda v: label_w + plot_w * min(v, vmax) / vmax
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           f'aria-label="{escape(title, {chr(34): "&quot;"})}" font-family="{FONT}">',
           f'<rect width="{w}" height="{h}" rx="14" fill="{BG}" stroke="{LINE}"/>',
           f'<text x="{pad}" y="30" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>']
    lx = pad
    for name, colour in series:                      # legend
        out.append(f'<rect x="{lx}" y="42" width="12" height="12" rx="2" fill="{colour}"/>')
        out.append(f'<text x="{lx + 17}" y="52.5" font-size="12" fill="{MUTED}">{escape(name)}</text>')
        lx += 24 + 7 * len(name)
    bottom = top + len(rows) * (group_h + group_gap) - group_gap + 6
    for t in ticks:                                  # grid
        out.append(f'<line x1="{x(t):.1f}" y1="{top - 6}" x2="{x(t):.1f}" y2="{bottom}" stroke="{LINE}"/>')
        out.append(f'<text x="{x(t):.1f}" y="{bottom + 16}" font-size="11" fill="{MUTED}" text-anchor="middle">{fmt(t)}</text>')
    y = top
    for label, values in rows:
        out.append(f'<text x="{label_w - 10}" y="{y + group_h / 2 + 4:.1f}" font-size="12" fill="{INK}" '
                   f'text-anchor="end">{escape(label)}</text>')
        for (v, mark), (_, colour) in zip(values, series):
            out.append(f'<rect x="{label_w}" y="{y}" width="{x(v) - label_w:.1f}" height="{bar_h}" rx="2" fill="{colour}"/>')
            out.append(f'<text x="{x(v) + 5:.1f}" y="{y + bar_h - 2.5}" font-size="11" fill="{INK}">{escape(mark + fmt(v))}</text>')
            y += bar_h + gap
        y += group_gap - gap
    out.append(f'<text x="{pad}" y="{h - 12}" font-size="11" fill="{MUTED}">{escape(note)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def anisotropy() -> str:
    md = (ROOT / "research" / "compliant-mechanisms.md").read_text(encoding="utf-8")
    rows = []
    for cells in table(md, "## 5. FDM anisotropy"):
        strength, strain = number(cells[4]), number(cells[5])
        if strength and strain:
            rows.append((re.sub(r"\s*\([^)]*\)\s*$", "", cells[0]), [strength, strain]))
    return bars_svg("Pulled across the layers: what is left of the in-plane value (Z ÷ XY)", rows,
                    [("strength", GREEN), ("strain to failure", ORANGE)], 1.0, [0, 0.25, 0.5, 0.75, 1.0],
                    lambda v: f"{v:.2f}".rstrip("0").rstrip(".") if v in (0, 1) else f"{v:.2f}",
                    "Manufacturers' data sheets, 100 % infill (research/compliant-mechanisms.md §5). ≥: a lower bound.")


def stars(top: int = 12) -> str:
    md = (ROOT / "research" / "landscape.md").read_text(encoding="utf-8")
    verified = re.search(r"verified (\d{4}-\d{2}-\d{2})", md).group(1)
    rows = []
    for cells in table(md, "## 1. Capability matrix"):
        name = re.match(r"\[([^\]]+)\]", cells[0])
        count = number(cells[2].split("/")[0].strip())
        if name and count:
            rows.append((name.group(1), [count]))
    rows.sort(key=lambda r: -r[1][0][0])
    vmax = (int(rows[0][1][0][0]) // 5000 + 1) * 5000
    return bars_svg(f"GitHub stars, the {top} most-starred projects in the capability matrix", rows[:top],
                    [("stars", GREEN)], vmax, [i * vmax / 5 for i in range(6)], lambda v: f"{v:,.0f}",
                    f"Read from the matrix rows (research/landscape.md §1), verified {verified}. Stars measure attention, not fitness.")


FIGURES = {"fdm-anisotropy.svg": anisotropy, "landscape-stars.svg": stars}


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
        print("out of date with their tables (run python3 tools/research_figures.py):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
