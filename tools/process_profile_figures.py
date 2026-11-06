#!/usr/bin/env python3
"""Draw the process-profile charts (docs/img/research/process-*.svg) and the sheet-metal diagrams
(docs/img/sheet-metal/*.svg) from docs/research/process-profiles.yaml (and docs/research/references.yaml, the sources it cites).

    python3 tools/process_profile_figures.py            # write the SVGs
    python3 tools/process_profile_figures.py --check    # exit 1 if a committed SVG differs from the data (tests run this)

The YAML is the source: a chart can never disagree with the rules it shows. Each chart takes the rules that share a
`compare` key, so a rule added to the file appears in its chart on the next run. Stdlib and PyYAML only; the SVGs carry
their own light background so they read the same on the site and on GitHub in dark mode.

`evaluate()` (from `cadagent.manufacturing.process`) is the one place a rule's expression ("2*T + R", "max(0.005*L, 0.5)", "1.574 if T <= 0.914 else 3.175")
is turned into a number; the tests use it to check every expression in the file.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "research" / "process-profiles.yaml"
REGISTRY = ROOT / "docs" / "research" / "references.yaml"
OUT = ROOT / "docs" / "img" / "research"
SHEET_OUT = ROOT / "docs" / "img" / "sheet-metal"
INK, MUTED, LINE, BG, GREEN, ORANGE = "#173d3c", "#526863", "#d8e0d3", "#fffdf5", "#6f8a80", "#bd3a12"
FONT = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif"

# ----------------------------------------------------------------------------- expressions

# The one evaluator lives in the package, which checks and calculators use too (#99).
sys.path.insert(0, str(ROOT / "src"))
from cadagent.manufacturing.process import evaluate  # noqa: E402
from cadagent.review import references  # noqa: E402

# ----------------------------------------------------------------------------- data

def load() -> dict:
    """The profiles, with ``sources``: the read entries of the reference registry (docs/research/references.yaml and its
    schema-2 shards, #118, #323) that the rules cite. A rule may cite only a read record, never a catalogued one."""
    data = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    data["sources"] = [ref.data for ref in references.load(REGISTRY).of_kind("source")]
    return data


def credit(source: dict) -> str:
    """How a chart names a source: the named person if there is one (surnames when there are two, "et al." beyond),
    else the organisation's short name, keeping a former name ("Protolabs Network (Hubs)")."""
    names = source.get("authors") or []
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0].split()[-1]} and {names[1].split()[-1]}"
    if names:
        return f"{names[0].split()[-1]} et al."
    org = source["org"]
    short = org.split(" (")[0].split(",")[0].strip()
    formerly = org.split("(formerly ", 1)[1].split(")")[0] if "(formerly " in org else ""
    return f"{short} ({formerly})" if formerly else short


def label(rule: dict, sources: dict) -> str:
    who = credit(sources[rule["source"]])
    return f"{who} · {rule['variant']}" if rule.get("variant") else who


# ----------------------------------------------------------------------------- drawing

Row = tuple[str, float | None, float | None, str, bool]


def ranges_svg(title: str, subtitle: str, groups: list[tuple[str, list[Row]]],
               vmax: float, ticks: list[float], unit: str, note: str) -> str:
    """One row per rule, grouped. A row is (label, low, high, colour, window): low and high equal is one value (a dot);
    both set is a range (a filled bar: one limit that varies between them), or with window set an allowed window (a
    dot at low on an open bar to high: at least low and at most high); high None is "at least low" (a dot with a fading tail to the right); low
    None is "at most high" (a tail from zero to a dot)."""
    w, label_w, pad, row_h, head_h = 680, 300, 18, 20, 24
    top = 78
    n_rows = sum(len(rows) for _, rows in groups)
    h = top + len(groups) * head_h + n_rows * row_h + 54
    plot_w = w - label_w - pad - 44
    x = lambda v: label_w + plot_w * min(v, vmax) / vmax
    fmt = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           f'aria-label="{escape(title, {chr(34): "&quot;"})}" font-family="{FONT}">',
           f'<rect width="{w}" height="{h}" rx="14" fill="{BG}" stroke="{LINE}"/>',
           f'<text x="{pad}" y="30" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>',
           f'<text x="{pad}" y="50" font-size="12" fill="{MUTED}">{escape(subtitle)}</text>']
    bottom = h - 46
    for t in ticks:
        out.append(f'<line x1="{x(t):.1f}" y1="{top - 8}" x2="{x(t):.1f}" y2="{bottom}" stroke="{LINE}"/>')
        out.append(f'<text x="{x(t):.1f}" y="{bottom + 15}" font-size="11" fill="{MUTED}" text-anchor="middle">'
                   f'{fmt(t)}</text>')
    out.append(f'<text x="{label_w + plot_w:.1f}" y="{bottom + 30}" font-size="11" fill="{MUTED}" '
               f'text-anchor="end">{escape(unit)}</text>')
    y = top
    for group, rows in groups:
        out.append(f'<text x="{pad}" y="{y + 15}" font-size="12.5" font-weight="700" fill="{INK}">{escape(group)}</text>')
        y += head_h
        for name, lo, hi, colour, window in rows:
            cy = y + row_h / 2
            out.append(f'<text x="{label_w - 10}" y="{cy + 4:.1f}" font-size="12" fill="{INK}" text-anchor="end">'
                       f'{escape(name)}</text>')
            if lo is not None and hi is not None and hi > lo and window:  # at least lo and at most hi
                out.append(f'<rect x="{x(lo):.1f}" y="{cy - 4:.1f}" width="{x(hi) - x(lo):.1f}" height="8" rx="4" '
                           f'fill="{BG}" stroke="{colour}" stroke-width="1.6"/>')
                out.append(f'<circle cx="{x(lo):.1f}" cy="{cy:.1f}" r="5" fill="{colour}"/>')
                text, tx = f"≥ {fmt(lo)}, ≤ {fmt(hi)}", x(hi) + 7
            elif lo is not None and hi is not None and hi > lo:     # one limit, somewhere in lo..hi
                out.append(f'<rect x="{x(lo):.1f}" y="{cy - 4:.1f}" width="{x(hi) - x(lo):.1f}" height="8" rx="4" '
                           f'fill="{colour}"/>')
                text, tx = f"{fmt(lo)}–{fmt(hi)}", x(hi) + 7
            elif hi is None:                                     # at least lo
                out.append(f'<rect x="{x(lo):.1f}" y="{cy - 1.5:.1f}" width="{min(48, label_w + plot_w - x(lo)):.1f}" '
                           f'height="3" rx="1.5" fill="{colour}" fill-opacity="0.35"/>')
                out.append(f'<circle cx="{x(lo):.1f}" cy="{cy:.1f}" r="5" fill="{colour}"/>')
                text, tx = f"≥ {fmt(lo)}", x(lo) - 9
            elif lo is None:                                     # at most hi
                out.append(f'<line x1="{label_w}" y1="{cy:.1f}" x2="{x(hi):.1f}" y2="{cy:.1f}" stroke="{colour}" '
                           f'stroke-width="2" stroke-dasharray="3 3"/>')
                out.append(f'<circle cx="{x(hi):.1f}" cy="{cy:.1f}" r="5" fill="{colour}"/>')
                text, tx = f"≤ {fmt(hi)}", x(hi) + 9
            else:                                                # one value
                out.append(f'<circle cx="{x(lo):.1f}" cy="{cy:.1f}" r="5" fill="{colour}"/>')
                text, tx = fmt(lo), x(lo) + 9
            anchor = "end" if hi is None and lo is not None else "start"
            if anchor == "end" and tx - 7 * len(text) < label_w:  # no room left of a low dot: write it after the tail
                anchor, tx = "start", x(lo) + min(48, label_w + plot_w - x(lo)) + 5
            out.append(f'<text x="{tx:.1f}" y="{cy + 4:.1f}" font-size="11" fill="{INK}" text-anchor="{anchor}">'
                       f'{escape(text)}</text>')
            y += row_h
    out.append(f'<text x="{pad}" y="{h - 12}" font-size="11" fill="{MUTED}">{escape(note)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _row(rule: dict, sources: dict, env: dict, colour: str = GREEN) -> Row:
    lo = evaluate(rule["min"], env) if "min" in rule else None
    hi = evaluate(rule["max"], env) if "max" in rule else None
    if "value" in rule:
        lo = hi = evaluate(rule["value"], env)
    return label(rule, sources), lo, hi, colour, bool(rule.get("window"))


# ----------------------------------------------------------------------------- the charts

PROCESS_TITLES = {"fdm": "FDM / FFF", "sla": "SLA and MSLA (resin)", "sls": "SLS (powder bed)", "mjf": "HP Multi Jet Fusion",
                  "injection-moulding": "Injection moulding", "cnc": "CNC machining", "sheet-metal": "Sheet metal"}


def min_wall() -> str:
    data = load()
    sources = {s["id"]: s for s in data["sources"]}
    rules = [r for r in data["rules"] if r.get("compare") == "min-wall" and r.get("status") == "read"]
    groups = []
    for process in PROCESS_TITLES:
        rows = [_row(r, sources, {}) for r in rules if r["process"] == process]
        if rows:
            groups.append((PROCESS_TITLES[process], rows))
    vmax = math.ceil(max(v for _, rows in groups for _, lo, hi, *_ in rows for v in (lo, hi) if v is not None) * 2) / 2
    if any(lo == vmax and hi is None for _, rows in groups for _, lo, hi, *_ in rows):
        vmax += 0.5  # room for the tail of a floor that sits at the top of the scale
    ticks = [i * 0.5 for i in range(int(vmax / 0.5) + 1)]
    n = sum(len(r) for _, r in groups)
    return ranges_svg("Minimum wall thickness: what each source recommends",
                      f"{n} rules (compare: min-wall). A bar: the minimum varies; open bar: an allowed window; ≥: a floor.",
                      groups, vmax, ticks, "mm",
                      "Each source's own wording and conditions are in the YAML file and on the page. Read 2026-10-31.")


SHEET = {"T": 1.5, "R": 1.5}
SHEET_GROUPS = [("sm-flange-min", "Minimum flange length"), ("sm-hole-to-bend", "Hole to bend (each source's own datum)"),
                ("sm-relief-depth", "Bend relief depth"), ("sm-relief-width", "Bend relief width")]
SHOP_COLUMNS = {"sm-flange-min": "min_flange_after_bend", "sm-relief-depth": "relief_depth"}


def sheet_metal() -> str:
    data = load()
    sources = {s["id"]: s for s in data["sources"]}
    shop = data["shop_tables"][0]
    cols = shop["columns"]
    near = min(shop["rows"], key=lambda r: abs(r[cols.index("T")] - SHEET["T"]) + 10 * (r[1] != "cold-rolled mild steel"))
    groups = []
    for key, title in SHEET_GROUPS:
        rows = [_row(r, sources, SHEET) for r in data["rules"]
                if r.get("compare") == key and r.get("status") == "read" and not r.get("shop")]
        if key in SHOP_COLUMNS:
            v = near[cols.index(SHOP_COLUMNS[key])]
            rows.append((f"{credit(sources[shop['source']])} tooling · {near[0]}", v, v, ORANGE, False))
        groups.append((title, rows))
    vmax = math.ceil(max(v for _, rows in groups for _, lo, hi, *_ in rows for v in (lo, hi) if v is not None) / 2) * 2
    ticks = [float(i) for i in range(0, int(vmax) + 1, 2)]
    t_near, r_near = near[cols.index("T")], near[cols.index("R")]
    return ranges_svg(f"Sheet metal: the same rule from different sources, at T = {SHEET['T']} mm, R = {SHEET['R']} mm",
                      "Generic rules evaluated from docs/research/process-profiles.yaml; orange is one shop's real tooling.",
                      groups, vmax, ticks, "mm",
                      f"Shop row: SendCutSend's specs file, {near[1]} {near[0]} (T {t_near:.2f}, R {r_near:.2f} mm). "
                      "Read 2026-10-31.")


SHORT = {"E. I. du Pont de Nemours and Company": "DuPont", "Covestro LLC": "Covestro", "PennEngineering": "PEM"}   # names too long for a row


def _span_row(rule: dict, sources: dict, envs: list[dict], prefix: str = "", per: str | None = None) -> Row:
    """A rule as one row, evaluated in each of ``envs``: a value that changes between them (a rule that steps with the
    feature's area, say) becomes the range it spans, drawn as a bar (the limit varies). With ``per``, each value is
    divided by that variable first, so a rule in proportion to it reads the same in every setting."""
    def scaled(env: dict) -> Row:
        name, lo, hi, colour, window = _row(rule, sources, env)
        k = env[per] if per else 1.0
        return name, None if lo is None else lo / k, None if hi is None else hi / k, colour, window
    rows = [scaled(env) for env in envs]
    name, _, _, colour, window = rows[0]
    los = [r[1] for r in rows if r[1] is not None]
    his = [r[2] for r in rows if r[2] is not None]
    lo = min(los) if los else None
    hi = max(his) if his else None
    if "value" in rule:
        lo, hi = min(r[1] for r in rows), max(r[2] for r in rows)
    for long, short in SHORT.items():
        name = name.replace(long, short)
    return (f"{prefix}{name}", lo, hi, colour, window)


def _scale(groups: list[tuple[str, list[Row]]], step: float) -> tuple[float, list[float]]:
    top = max(v for _, rows in groups for _, lo, hi, *_ in rows for v in (lo, hi) if v is not None)
    vmax = math.ceil(top / step) * step
    if any(lo == vmax and hi is None for _, rows in groups for _, lo, hi, *_ in rows):
        vmax += step  # room for the tail of a floor that sits at the top of the scale
    return vmax, [round(i * step, 6) for i in range(int(round(vmax / step)) + 1)]


def compared(title: str, subtitle: str, groups: list[tuple[str, str, str | None]], *, envs: list[dict] | None = None,
             unit: str, step: float, note: str, kinds: dict[str, str] | None = None, per: str | None = None,
             shop: str | None = None) -> str:
    """A chart of the rules that share a compare key: ``groups`` is (heading, compare key, process or None), the
    rules read from the YAML in file order and evaluated in ``envs`` (one or more variable settings). With ``kinds``
    (compare key -> a word), a group holds every key in it and each row says which ("hole · Xometry"). A shop's own
    rules (``shop:``) are left out unless ``shop`` names it, as cadagent.manufacturing.process does."""
    data = load()
    sources = {s["id"]: s for s in data["sources"]}
    envs = envs or [{}]
    out = []
    for heading, key, process in groups:
        keys = list(kinds) if key == "*" else [key]
        rows = [_span_row(r, sources, envs, f"{kinds[r['compare']]} · " if kinds else "", per)
                for k in keys for r in data["rules"]
                if r.get("compare") == k and r.get("status") == "read" and (process is None or r["process"] == process)
                and (not r.get("shop") or r.get("shop") == shop)]
        if rows:
            out.append((heading, rows))
    vmax, ticks = _scale(out, step)
    n = sum(len(rows) for _, rows in out)
    return ranges_svg(title, subtitle.format(n=n), out, vmax, ticks, unit, note)


READ = "Each source's own wording and conditions are in the YAML file and on the page. Read 2026-10-31."
BY_PROCESS = [(PROCESS_TITLES[p], p) for p in ("fdm", "sla", "sls", "mjf")]


def fits() -> str:
    return compared("Clearance between mating printed parts: what each source recommends",
                    "{n} rules (compare: clearance-fit). A bar: the gap grows with the mating area (10 to 30 mm²).",
                    [(t, "clearance-fit", p) for t, p in BY_PROCESS], envs=[{"area": 10.0}, {"area": 30.0}],
                    unit="mm", step=0.1, note=READ)


def holes_pins() -> str:
    return compared("Smallest hole and pin that print, by process",
                    "{n} rules (compare: min-hole, min-pin). ≥: a floor; a bar: the floor varies.",
                    [(t, "*", p) for t, p in BY_PROCESS], unit="mm", step=0.5, note=READ,
                    kinds={"min-hole": "hole", "min-pin": "pin"})


def overhangs() -> str:
    return compared("FDM: the steepest overhang printed without support, from vertical",
                    "{n} rules (compare: overhang-max), in degrees from vertical. ≤: a ceiling; a bar: it varies.",
                    [("FDM / FFF", "overhang-max", "fdm")], unit="degrees", step=15, note=READ)


def escape_holes() -> str:
    return compared("Drain and escape holes for hollow prints",
                    "{n} rules (compare: escape-hole): the smallest hole that lets resin or powder out.",
                    [(t, "escape-hole", p) for t, p in BY_PROCESS], unit="mm", step=2, note=READ)


def fine_detail() -> str:
    return compared("Embossed and engraved detail: the smallest that prints",
                    "{n} rules (compare: emboss-min, engrave-min), height or depth.",
                    [(t, "*", p) for t, p in BY_PROCESS], unit="mm", step=0.2, note=READ,
                    kinds={"emboss-min": "emboss", "engrave-min": "engrave"})


def moulding_wall() -> str:
    return compared("Injection moulding: recommended wall thickness",
                    "{n} rules (compare: im-wall). A bar: the range each source recommends for that resin.",
                    [("By resin", "im-wall", "injection-moulding")], unit="mm", step=0.5, note=READ)


def moulding_draft() -> str:
    return compared("Injection moulding: draft on faces in the line of draw",
                    "{n} rules (compare: im-draft), in degrees. ≥: a floor; a bar: it varies with resin or texture.",
                    [("By resin and finish", "im-draft", "injection-moulding")], unit="degrees", step=1, note=READ)


RIB = 0.6     # a rule given in rib thickness is drawn at a rib of 0.6 x wall, the most common ceiling


def moulding_corners() -> str:
    groups = [("Boss wall", "im-boss-wall", None), ("Inside corner radius", "im-corner", None)]
    return compared("Injection moulding: boss walls and inside corners as multiples of the wall",
                    "{n} rules as multiples of the wall. A bar: it varies (DuPont's boss wall steps down past 3.175 mm).", groups, envs=[{"wall": 1.0}, {"wall": 4.0}], unit="× wall",
                    step=0.5, note=READ, per="wall")


def moulding_ratios() -> str:
    groups = [("Rib thickness", "im-rib-thickness", None), ("Rib height", "im-rib-height", None),
              ("Fillet at the rib's base", "im-rib-fillet", None)]
    return compared("Injection moulding: ribs as multiples of the wall",
                    "{n} rules, at a nominal wall of 1 (so each reads as × wall); a rule given in rib thickness takes "
                    f"a rib of {RIB} × wall.", groups, envs=[{"wall": 1.0, "rib": RIB}], unit="× nominal wall",
                    step=0.5, note=READ)


def sheet_holes() -> str:
    env = dict(SHEET)
    groups = [("Smallest inside bend radius", "sm-bend-radius-min", None), ("Smallest hole", "sm-hole-min", None),
              ("Hole to the edge", "sm-hole-to-edge", None), ("Hole to hole", "sm-hole-spacing", None),
              ("Hem return", "sm-hem-return", None)]
    return compared(f"Sheet metal: holes, edges, bends and hems at T = {SHEET['T']} mm",
                    "{n} rules evaluated from docs/research/process-profiles.yaml at T = 1.5 mm. ≥: a floor; "
                    "a bar: it varies with the alloy.", groups, envs=[env], unit="mm", step=2, note=READ)


def cnc_depths() -> str:
    groups = [("End-mill depth of cut", "cnc-tool-reach", None), ("Cavity depth (× its width)", "cnc-cavity-depth", None),
              ("Hole depth", "cnc-hole-depth", None), ("Thread length", "cnc-thread-length", None)]
    return compared("CNC: how deep a tool, hole or thread can go, as multiples of its diameter",
                    "{n} rules, at a diameter (or cavity width) of 1, so each reads as × D. ≤: a ceiling.",
                    groups, envs=[{"D": 1.0, "width": 1.0}], unit="× diameter", step=5, note=READ)


POWDER_L = 25.0


def powder_tolerance() -> str:
    return compared(f"Powder bed: tolerance (±) on a {POWDER_L:g} mm dimension, by source",
                    "{n} rules (compare: tolerance) for SLS and MJF, each evaluated at L = 25 mm (inside every "
                    "rule's size band).", [(PROCESS_TITLES[p], "tolerance", p) for p in ("sls", "mjf")],
                    envs=[{"L": POWDER_L}], unit="± mm", step=0.1, note=READ)


FDM_L = 50.0


def fdm_tolerance() -> str:
    return compared(f"FDM: tolerance (±) on a {FDM_L:g} mm dimension, by source",
                    "{n} rules (compare: tolerance), each evaluated at L = 50 mm: a factor of four between them.",
                    [(PROCESS_TITLES["fdm"], "tolerance", "fdm")], envs=[{"L": FDM_L}], unit="± mm", step=0.1, note=READ)


def cnc_tolerance() -> str:
    return compared(f"Machined and moulded parts: default tolerance (±) on a {POWDER_L:g} mm dimension",
                    "{n} rules (compare: tolerance), each evaluated at L = 25 mm.",
                    [(PROCESS_TITLES[p], "tolerance", p) for p in ("cnc", "injection-moulding")],
                    envs=[{"L": POWDER_L}], unit="± mm", step=0.05, note=READ)


def resin_overhangs() -> str:
    groups = [("Unsupported overhang length", "overhang-length-max", "sla"), ("Bridge between supports", "bridge-max", "sla")]
    return compared("Resin: how far an overhang or a bridge may reach, by printer and service",
                    "{n} rules (compare: overhang-length-max, bridge-max). ≤: a ceiling.",
                    groups, unit="mm", step=5, note=READ)


def moulding_bosses() -> str:
    groups = [("Boss outside diameter", "im-boss-od", None), ("Depth of a blind cored hole", "im-hole-depth", None)]
    return compared("Injection moulding: bosses and cored holes as multiples of the hole diameter",
                    "{n} rules (compare: im-boss-od, im-hole-depth), at a hole diameter of 1, so each reads as × D.",
                    groups, envs=[{"D": 1.0}], unit="× D", step=0.5, note=READ)


BEND_COLUMNS = ("sku", "material", "T", "R", "K")


def _bend_tables(data: dict) -> list[dict]:
    return [t for t in data["shop_tables"] if set(BEND_COLUMNS) <= set(t["columns"])]


def sheet_shop() -> str:
    data = load()
    sources = {s["id"]: s for s in data["sources"]}
    tables = _bend_tables(data)
    groups = []
    for shop in tables:
        cols = shop["columns"]
        for material in dict.fromkeys(r[cols.index("material")] for r in shop["rows"]):
            rows = [(f"{r[0]} · T {r[cols.index('T')]:.2f} mm · K {r[cols.index('K')]:.2f}", r[cols.index("R")],
                     r[cols.index("R")], ORANGE, False) for r in shop["rows"] if r[cols.index("material")] == material]
            groups.append((material[0].upper() + material[1:], rows))
    vmax, ticks = _scale(groups, 0.5)
    who = credit(sources[tables[0]["source"]])
    dates = sorted({str(t["verified"]) for t in tables})
    return ranges_svg(f"Sheet metal: one shop's inside bend radius and K-factor, by sheet ({who})",
                      f"{sum(len(r) for _, r in groups)} rows of the shop's own tooling tables (shop_tables), not a "
                      "generic rule: R is not simply T.", groups, vmax, ticks, "R, mm",
                      f"Converted from inches (as_printed in the YAML). Read {' and '.join(dates)}.")


CORNER = {"D": 6.0, "depth": 12.0}


def cnc_corners() -> str:
    return compared(f"CNC: inside corner radius for a {CORNER['D']:g} mm end mill cutting {CORNER['depth']:g} mm deep",
                    "{n} rules (compare: cnc-corner-radius), evaluated at D = 6 mm and a pocket 12 mm deep. "
                    "≥: a floor; a bar: it varies.", [("Inside vertical corner", "cnc-corner-radius", None)],
                    envs=[CORNER], unit="mm", step=1, note=READ)


def cnc_walls() -> str:
    groups = [("Minimum wall", "min-wall", "cnc"), ("Smallest tool or cavity", "cnc-small-tool", None)]
    return compared("CNC: the thinnest wall and the smallest tool, by source",
                    "{n} rules (compare: min-wall, cnc-small-tool). ≥: a floor.", groups, unit="mm", step=0.5, note=READ)


# ----------------------------------------------------------------------------- sheet metal joining (#283)

READ_1101 = "Each source's own wording and conditions are in the YAML file and on the page. Read 2026-11-01."
RIVET = {"D": 3.175, "T": 1.6}          # a 1/8 in blind rivet in 1.6 mm sheet


def _limits_table(data: dict) -> dict:
    return next(t for t in data["shop_tables"] if t["id"] == "sendcutsend-cut-and-hardware-limits")


def sheet_hardware() -> str:
    """The shop's least hardware distances per stock: one bar per material across its thicknesses."""
    data = load()
    sources = {s["id"]: s for s in data["sources"]}
    table = _limits_table(data)
    cols = table["columns"]
    groups = []
    for col, title in (("hw_cl_edge", "Hardware hole centre to a cut edge"),
                       ("hw_cl_bend", "Hardware hole centre to a bend line"),
                       ("hw_cl_same", "Hardware hole centre to the next of the same part")):
        rows = []
        for material in dict.fromkeys(r[cols.index("material")] for r in table["rows"]):
            mine = [r for r in table["rows"] if r[cols.index("material")] == material and r[cols.index(col)] is not None]
            if not mine:
                continue
            vals = [r[cols.index(col)] for r in mine]
            ts = [r[cols.index("T")] for r in mine]
            rows.append((f"{material} · T {min(ts):.2f}–{max(ts):.2f} mm", min(vals), max(vals), ORANGE, False))
        groups.append((title, rows))
    vmax, ticks = _scale(groups, 2)
    who = credit(sources[table["source"]])
    return ranges_svg(f"Sheet metal: one shop's least distances for pressed-in hardware ({who})",
                      f"{len(table['rows'])} stocks it fits hardware to; a bar spans the stock's thicknesses. Each "
                      "part's catalogue value may be larger.", groups, vmax, ticks, "mm",
                      f"Its specs file (shop_tables), converted from inches. Read {table['verified']}.")


def clinch_hardness() -> str:
    return compared("Self-clinching fasteners: the hardest sheet each fastener material takes",
                    "{n} rules (compare: sm-clinch-sheet-hardness). The sheet must also be about 20 HRB softer than "
                    "the fastener.", [("Fastener material", "sm-clinch-sheet-hardness", None)], unit="HRB", step=10,
                    note=READ_1101)


def rivet_spacing() -> str:
    return compared("Blind rivets: edge distance and pitch, in rivet diameters, by source",
                    "{n} rules (compare: sm-rivet-edge, sm-rivet-pitch), divided by the rivet diameter D. "
                    "≥: a floor; a dot: a nominal value.",
                    [("Hole centre to the sheet edge", "sm-rivet-edge", None),
                     ("Centre to centre (pitch)", "sm-rivet-pitch", None)],
                    envs=[RIVET], unit="× D", step=1, note=READ_1101, per="D")


def _dim(x1: float, y1: float, x2: float, y2: float, text: str, colour: str = INK, side: int = -1) -> list[str]:
    """A dimension line with arrow heads and its value, offset to one side."""
    out = [f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{colour}" stroke-width="1.2" '
           'marker-start="url(#arr)" marker-end="url(#arr)"/>']
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if abs(y2 - y1) < 1:      # horizontal
        out.append(f'<text x="{mx:.1f}" y="{my + (14 if side > 0 else -5):.1f}" font-size="11" fill="{colour}" '
                   f'text-anchor="middle">{escape(text)}</text>')
    else:                     # vertical
        out.append(f'<text x="{mx + (6 if side > 0 else -6):.1f}" y="{my + 4:.1f}" font-size="11" fill="{colour}" '
                   f'text-anchor="{"start" if side > 0 else "end"}">{escape(text)}</text>')
    return out


def bent_plate() -> str:
    """A bent mounting plate with a clinch nut and a riveted strap, its limits read from the YAML for one stock."""
    data = load()
    sku = "ALU-063"
    bend = next(t for t in _bend_tables(data) if any(r[0] == sku for r in t["rows"]))
    b = dict(zip(bend["columns"], next(r for r in bend["rows"] if r[0] == sku)))
    lim_t = _limits_table(data)
    h = dict(zip(lim_t["columns"], next(r for r in lim_t["rows"] if r[0] == sku)))
    rules = {r["id"]: r for r in data["rules"]}
    D = RIVET["D"]
    edge = evaluate(rules["sm-rivet-edge-pop"]["min"], {"D": D})
    pitch = evaluate(rules["sm-rivet-pitch-faa"]["min"], {"D": D})
    hardness = rules["sm-clinch-sheet-hardness-steel-pem"]["max"]
    ba = evaluate(next(f for f in data["formulas"] if f["id"] == "sm-bend-allowance")["expr"].replace("pi", "3.141592653589793"),
                  {"R": b["R"], "K": b["K"], "T": b["T"], "A": 90.0})
    f1 = lambda v: f"{v:.1f}"
    w, hgt = 680, 400
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {hgt}" width="{w}" height="{hgt}" role="img" '
           f'aria-label="A bent mounting plate with a clinch nut and a riveted strap, and the distances each must keep" '
           f'font-family="{FONT}">',
           f'<defs><marker id="arr" viewBox="0 0 8 8" refX="4" refY="4" markerWidth="7" markerHeight="7" '
           f'orient="auto-start-reverse"><path d="M0 1 L7 4 L0 7 z" fill="{INK}"/></marker></defs>',
           f'<rect width="{w}" height="{hgt}" rx="14" fill="{BG}" stroke="{LINE}"/>',
           f'<text x="18" y="30" font-size="15" font-weight="700" fill="{INK}">A two-bend mounting plate: the distances '
           f'its hardware and rivets keep</text>',
           f'<text x="18" y="50" font-size="12" fill="{MUTED}">One shop\'s 1.6 mm 5052 ({sku}) and a 1/8 in (3.2 mm) '
           f'blind rivet. Not to scale.</text>']
    # --- side view: a channel (base and two flanges), at left
    x0, y0, base, fl, t = 60, 300, 210, 120, 7
    out.append(f'<text x="{x0}" y="84" font-size="12.5" font-weight="700" fill="{INK}">Side view</text>')
    path = (f"M{x0} {y0 - fl} L{x0} {y0} L{x0 + base} {y0} L{x0 + base} {y0 - fl} L{x0 + base - t} {y0 - fl} "
            f"L{x0 + base - t} {y0 - t} L{x0 + t} {y0 - t} L{x0 + t} {y0 - fl} Z")
    out.append(f'<path d="{path}" fill="{GREEN}" fill-opacity="0.35" stroke="{INK}" stroke-width="1.4" '
               'stroke-linejoin="round"/>')
    out += _dim(x0 - 14, y0 - fl, x0 - 14, y0, "")
    out.append(f'<text x="{x0 - 20}" y="{y0 - fl - 8}" font-size="11" fill="{INK}">flange ≥ {f1(b["min_flange_after_bend"])}</text>')
    out.append(f'<text x="{x0 + base / 2}" y="{y0 + 36}" font-size="11" fill="{INK}" text-anchor="middle">'
               f'inside radius R {b["R"]:.2f} mm · K {b["K"]:.2f}</text>')
    out.append(f'<text x="{x0 + base / 2}" y="{y0 + 20}" font-size="11" fill="{INK}" text-anchor="middle">'
               f'T {b["T"]:.2f} mm · bend allowance {ba:.2f} mm at 90°</text>')
    # a clinch nut in the base, a strap riveted to the right flange
    nx = x0 + 120
    out.append(f'<rect x="{nx - 9}" y="{y0 - t - 9}" width="18" height="9" fill="{ORANGE}"/>')
    out.append(f'<rect x="{nx - 5}" y="{y0 - t}" width="10" height="{t}" fill="{ORANGE}" fill-opacity="0.6"/>')
    out.append(f'<text x="{nx}" y="{y0 - t - 16}" font-size="11" fill="{ORANGE}" text-anchor="middle">clinch nut</text>')
    sx = x0 + base
    out.append(f'<rect x="{sx}" y="{y0 - fl + 10}" width="{t}" height="{fl - 40}" fill="{LINE}" stroke="{INK}"/>')
    for ry in (y0 - fl + 30, y0 - fl + 60):
        out.append(f'<rect x="{sx - t - 4}" y="{ry - 4}" width="{2 * t + 12}" height="8" rx="3" fill="{ORANGE}"/>')
    out.append(f'<text x="{sx + 14}" y="{y0 - fl + 34}" font-size="11" fill="{ORANGE}">riveted strap</text>')
    # --- plan view of the base, at right
    px, py, pw, ph = 350, 110, 290, 220
    out.append(f'<text x="{px}" y="84" font-size="12.5" font-weight="700" fill="{INK}">A face between two bends, from above</text>')
    out.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" fill="{GREEN}" fill-opacity="0.18" stroke="{INK}"/>')
    for bx in (px + 24, px + pw - 24):
        out.append(f'<line x1="{bx}" y1="{py}" x2="{bx}" y2="{py + ph}" stroke="{INK}" stroke-dasharray="6 4"/>')
    out.append(f'<text x="{px + 28}" y="{py + ph - 8}" font-size="10.5" fill="{MUTED}">bend line</text>')
    cx, cy = px + 100, py + ph - 62
    out.append(f'<circle cx="{cx}" cy="{cy}" r="8" fill="{BG}" stroke="{ORANGE}" stroke-width="2.4"/>')
    out += _dim(px + 24, cy, cx, cy, f"≥ {f1(h['hw_cl_bend'])} to bend", colour=ORANGE, side=-1)
    out += _dim(cx, cy, cx, py + ph, f"≥ {f1(h['hw_cl_edge'])} to edge", colour=ORANGE, side=1)
    for i in range(3):
        rx = px + 120 + i * 54
        out.append(f'<circle cx="{rx}" cy="{py + 34}" r="5" fill="{BG}" stroke="{INK}" stroke-width="2"/>')
    out += _dim(px + 120, py + 18, px + 174, py + 18, f"pitch ≥ {f1(pitch)} (3D)", side=-1)
    out += _dim(px + 100, py, px + 100, py + 34, f"edge ≥ {f1(edge)} (2D)", side=-1)
    out.append(f'<line x1="{px + 100}" y1="{py + 34}" x2="{px + 120}" y2="{py + 34}" stroke="{MUTED}" stroke-dasharray="2 2"/>')
    out.append(f'<text x="{px + 120}" y="{py + 56}" font-size="10.5" fill="{MUTED}">rivets of a lap joint along an edge</text>')
    notes = [f"Clinch nut: the shop's least distances for this stock (a part's own K or N may be larger); sheet at most "
             f"HRB {hardness} for steel nuts.",
             f"Rivets: edge ≥ 2D = {f1(edge)} mm (POP, FAA), pitch ≥ 3D = {f1(pitch)} mm (FAA). Bend relief {f1(b['relief_depth'])} mm deep "
             f"at the corners."]
    for i, n in enumerate(notes):
        out.append(f'<text x="18" y="{hgt - 34 + 16 * i}" font-size="11" fill="{MUTED}">{escape(n)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


SHEET_FIGURES = {"bent-plate.svg": bent_plate, "shop-hardware.svg": sheet_hardware,
                 "clinch-hardness.svg": clinch_hardness, "rivet-spacing.svg": rivet_spacing}

FIGURES = {"process-min-wall.svg": min_wall, "process-sheet-metal.svg": sheet_metal, "process-fits.svg": fits,
           "process-holes-pins.svg": holes_pins,
           "process-overhangs.svg": overhangs, "process-escape-holes.svg": escape_holes,
           "process-fine-detail.svg": fine_detail, "process-moulding-wall.svg": moulding_wall,
           "process-moulding-draft.svg": moulding_draft, "process-moulding-ratios.svg": moulding_ratios,
           "process-sheet-holes.svg": sheet_holes, "process-cnc-depths.svg": cnc_depths,
           "process-resin-overhangs.svg": resin_overhangs, "process-moulding-bosses.svg": moulding_bosses,
           "process-sheet-shop.svg": sheet_shop, "process-cnc-corners.svg": cnc_corners, "process-cnc-walls.svg": cnc_walls,
           "process-moulding-corners.svg": moulding_corners, "process-powder-tolerance.svg": powder_tolerance,
           "process-cnc-tolerance.svg": cnc_tolerance, "process-fdm-tolerance.svg": fdm_tolerance}


def main(argv: list[str]) -> int:
    stale = []
    for name, make, folder in [(n, m, OUT) for n, m in FIGURES.items()] + [(n, m, SHEET_OUT) for n, m in SHEET_FIGURES.items()]:
        text, path = make(), folder / name
        if "--check" in argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if stale:
        print("out of date with docs/research/process-profiles.yaml (run python3 tools/process_profile_figures.py):",
              ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
