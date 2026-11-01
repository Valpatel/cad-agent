#!/usr/bin/env python3
"""Regenerate the research pages' charts (docs/img/research/*.svg) from the tables on those pages.

    python3 tools/research_figures.py            # write the SVGs
    python3 tools/research_figures.py --check    # exit 1 if a committed SVG differs from its table (tests run this)

The tables are the source: a chart can never disagree with the page it illustrates. Stdlib only; the SVGs carry their
own light background so they read the same on the site and on GitHub in dark mode.
"""
from __future__ import annotations

import math
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


GAP = re.compile(r"^(?:—(?:\s*\([^)]*\))?|n/a|no\b.*)$", re.I)     # "—", "— (why)", "n/a", "no Z data"


def number(cell: str, where: str) -> tuple[float, str] | None:
    """A table cell as (value, mark): a plain number, or one marked ``≥``/``>`` as a lower bound. An explicit gap
    (``—``, ``— (why)``, ``n/a``, ``no … data``) is None. Anything else is an error, so an edit to a table (a footnote, ``~``,
    ``32.3k``) can never drop a row from its chart while ``--check`` still passes."""
    text = cell.replace(",", "").strip()
    if GAP.match(text):
        return None
    m = re.match(r"^(≥|>)?\s*([0-9]+(?:\.[0-9]+)?)$", text)
    if not m:
        raise ValueError(f"{where}: {cell!r} is neither a number nor a gap (—); fix the table or the chart's reader")
    return float(m.group(2)), m.group(1) or ""


def bars_svg(title: str, rows: list[tuple[str, list[tuple[float, str] | None]]], series: list[tuple[str, str]],
             vmax: float, ticks: list[float], fmt, note: str, mark: tuple[float, str] | None = None) -> str:
    """Horizontal grouped bars: one group per row, one bar per series, the value printed at the bar's end; a missing
    value (None) gets "—" and no bar. ``mark`` (value, label) draws a dashed reference line across every group."""
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
    if mark:                                         # a reference value, labelled at the top of its line
        out.append(f'<line x1="{x(mark[0]):.1f}" y1="{top - 10}" x2="{x(mark[0]):.1f}" y2="{bottom}" stroke="{INK}" '
                   f'stroke-width="1.5" stroke-dasharray="5 4"/>')
        out.append(f'<text x="{x(mark[0]) - 4:.1f}" y="{top - 14}" font-size="11" fill="{INK}" '
                   f'text-anchor="end">{escape(mark[1])}</text>')
    y = top
    for label, values in rows:
        out.append(f'<text x="{label_w - 10}" y="{y + group_h / 2 + 4:.1f}" font-size="12" fill="{INK}" '
                   f'text-anchor="end">{escape(label)}</text>')
        for value, (_, colour) in zip(values, series):
            if value is None:                            # words, not a dash that could pass for a stub of a bar
                out.append(f'<text x="{label_w + 5}" y="{y + bar_h - 2.5}" font-size="11" font-style="italic" '
                           f'fill="{MUTED}">not known</text>')
            else:
                v, mark, *high = value                   # (value, mark) or a range (low, mark, high)
                out.append(f'<rect x="{label_w}" y="{y}" width="{x(v) - label_w:.1f}" height="{bar_h}" rx="2" fill="{colour}"/>')
                end, text = x(v), mark + fmt(v)
                if high:                                 # the rest of a range, paler: the low end is the safe reading
                    low, top = fmt(v), fmt(high[0])
                    unit = re.search(r"[^0-9.]*$", top).group()   # "2–4 %", not "2 %–4 %"
                    end, text = x(high[0]), f"{mark}{low.removesuffix(unit) if unit else low}–{top}"
                    out.append(f'<rect x="{x(v):.1f}" y="{y}" width="{end - x(v):.1f}" height="{bar_h}" rx="2" '
                               f'fill="{colour}" fill-opacity="0.35"/>')
                out.append(f'<text x="{end + 5:.1f}" y="{y + bar_h - 2.5}" font-size="11" fill="{INK}">{escape(text)}</text>')
            y += bar_h + gap
        y += group_gap - gap
    out.append(f'<text x="{pad}" y="{h - 12}" font-size="11" fill="{MUTED}">{escape(note)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def anisotropy() -> str:
    md = (ROOT / "research" / "compliant-mechanisms.md").read_text(encoding="utf-8")
    rows, unsheeted = [], []
    for cells in table(md, "## 5. FDM anisotropy"):
        where = f"compliant-mechanisms.md §5, {cells[0]}"
        values = [number(cells[4], where), number(cells[5], where)]
        label = re.sub(r"\s*\([^)]*\)\s*$", "", cells[0])
        if re.search(r"\((?:s|u)\b", cells[6]):         # read from a search snippet or unverified: not a data sheet
            unsheeted.append(label)
        elif any(values):                                # a row with no ratio at all (no Z data) has nothing to draw
            rows.append((label, values))
    marks = "".join(v[1] for _, vs in rows for v in vs if v)
    note = "Manufacturers' data sheets, 100 % infill (research/compliant-mechanisms.md §5)." + \
        (" ≥: a lower bound." if marks else "") + \
        (f" Not drawn (no data sheet): {', '.join(unsheeted)}." if unsheeted else "")
    return bars_svg("Pulled across the layers: what is left of the in-plane value (Z ÷ XY)", rows,
                    [("strength", GREEN), ("strain to failure", ORANGE)], 1.0, [0, 0.25, 0.5, 0.75, 1.0],
                    lambda v: f"{v:.2f}".rstrip("0").rstrip(".") if v in (0, 1) else f"{v:.2f}", note)


def stars(top: int = 12) -> str:
    md = (ROOT / "research" / "landscape.md").read_text(encoding="utf-8")
    verified = re.search(r"verified (\d{4}-\d{2}-\d{2})", md).group(1)
    rows = []
    for cells in table(md, "## 1. Capability matrix"):
        name = re.match(r"\[([^\]]+)\]", cells[0])
        if not name:
            raise ValueError(f"landscape.md §1: {cells[0]!r} does not start with a [project](link)")
        count = number(cells[2].split("/")[0], f"landscape.md §1, {name.group(1)}")
        if count:
            rows.append((name.group(1), [count]))
    rows.sort(key=lambda r: -r[1][0][0])
    rows = rows[:top]
    vmax = (int(rows[0][1][0][0]) // 5000 + 1) * 5000
    return bars_svg(f"GitHub stars, the {len(rows)} most-starred projects in the capability matrix", rows,
                    [("stars", GREEN)], vmax, [i * vmax / 5 for i in range(6)], lambda v: f"{v:,.0f}",
                    f"Read from the matrix rows (research/landscape.md §1), verified {verified}. Stars measure attention, not fitness.")


def percent(cell: str, where: str) -> tuple[float, str] | tuple[float, str, float]:
    """A strain cell in per cent: ``4 %``, a range ``0.8–1.2 %`` (low, "", high), or the first of ``a / b %`` (a
    single / repeat pair). Anything else is an error, as in ``number``."""
    text = cell.strip()
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)(?:\s*[–-]\s*([0-9]+(?:\.[0-9]+)?))?(?:\s*/\s*[0-9]+(?:\.[0-9]+)?)?\s*%$", text)
    if not m:
        raise ValueError(f"{where}: {cell!r} is not a strain in per cent; fix the table or the chart's reader")
    low = float(m.group(1))
    return (low, "", float(m.group(2))) if m.group(2) else (low, "")


def per_cent(v: float) -> str:
    return f"{v:g} %"


def moulded_strain() -> str:
    """§3: the moulded resins' allowable strain from the two guides that were read, used once and used often."""
    md = (ROOT / "research" / "compliant-mechanisms.md").read_text(encoding="utf-8")
    rows = []
    for anchor, guide in (("**Bayer Table 2**", "Bayer"), ("**DuPont Table 10.06**", "DuPont")):
        for cells in table(md, anchor):
            where = f"compliant-mechanisms.md §3, {guide}, {cells[0]}"
            rows.append((cells[0], [percent(cells[1], where), percent(cells[2], where)]))
    top = max(v[2] if len(v) == 3 else v[0] for _, vs in rows for v in vs)
    vmax = 5 * math.ceil(top / 5)
    return bars_svg("Moulded resins: the strain a snap arm may take, used once and used often", rows,
                    [("used once", GREEN), ("used often", ORANGE)], vmax, [i * 5 for i in range(vmax // 5 + 1)],
                    per_cent, "Bayer Table 2 (the first six rows) and DuPont Table 10.06 (research/compliant-mechanisms.md §3). "
                    "Pale: the top of a range.")


def printed_strain() -> str:
    """§6: the derived allowable strain for one assembly, along the layers (XY) and across them (Z), per data sheet."""
    md = (ROOT / "research" / "compliant-mechanisms.md").read_text(encoding="utf-8")
    rows, skipped = [], []
    for cells in table(md, "## 6. Printed allowable strain"):
        name, _, detail = cells[0].partition(" (")
        label = f"{name}, {re.split(r'[;,]', detail.rstrip(')'))[0]}" if detail else name
        if "does not govern" in cells[1]:               # TPU: sized for force and retention, not strain
            skipped.append(name)
            continue
        where = f"compliant-mechanisms.md §6, {cells[0]}"
        rows.append((label, [percent(cells[1], where), percent(cells[2], where)]))
    note = ("Derived from the data sheets by §6's rule; not yet checked by coupons." +
            (f" {', '.join(skipped)} not drawn: strain does not govern." if skipped else ""))
    top = max(v[0] for _, vs in rows for v in vs)
    steps = math.ceil(top / 0.5)                         # the axis ends on the half per cent at or above the largest
    return bars_svg("Printed snap arms: the strain allowed for one assembly, along and across the layers", rows,
                    [("along the layers (XY)", GREEN), ("across the layers (Z)", ORANGE)], steps * 0.5,
                    [i * 0.5 for i in range(steps + 1)], per_cent, note)


def celsius(cell: str, where: str) -> tuple[float, str]:
    """A temperature cell, ``60 °C``; anything else is an error."""
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*°C$", cell.strip())
    if not m:
        raise ValueError(f"{where}: {cell!r} is not a temperature in °C; fix the table or the chart's reader")
    return float(m.group(1)), ""


def thermal_limits() -> str:
    """§6: the printed materials' glass transition and heat deflection temperatures against the module's TTP limit."""
    md = (ROOT / "research" / "simulation-tools.md").read_text(encoding="utf-8")
    ttp = re.search(r"\*\*TTP \(datasheet\):\*\* operating range −25 to \*\*([0-9]+) °C max\*\*", md)
    if not ttp:
        raise ValueError("simulation-tools.md §6: the TTP's maximum is not where the chart reads it")
    rows = []
    for cells in table(md, "**Printed-material limits"):
        where = f"simulation-tools.md §6, {cells[0]}"
        rows.append((re.sub(r"\s*\([^)]*\)\s*$", "", cells[0]), [celsius(c, where) for c in cells[1:4]]))
    limit = float(ttp.group(1))
    return bars_svg("Printed materials soften below the module's thermal plate limit", rows,
                    [("glass transition (DSC)", GREEN), ("HDT at 0.45 MPa", ORANGE), ("HDT at 1.8 MPa", INK)],
                    100.0, [0, 20, 40, 60, 80, 100], lambda v: f"{v:g} °C",
                    "Bambu data sheets (research/simulation-tools.md §6). The plate is not the air at a wall: "
                    "a wall's own temperature decides.", mark=(limit, f"TTP max {limit:g} °C"))


FIGURES = {"fdm-anisotropy.svg": anisotropy, "landscape-stars.svg": stars, "thermal-limits.svg": thermal_limits,
           "moulded-strain.svg": moulded_strain, "printed-strain.svg": printed_strain}


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
