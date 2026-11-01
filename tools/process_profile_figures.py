#!/usr/bin/env python3
"""Draw the process-profile charts (docs/img/research/process-*.svg) from research/process-profiles.yaml.

    python3 tools/process_profile_figures.py            # write the SVGs
    python3 tools/process_profile_figures.py --check    # exit 1 if a committed SVG differs from the data (tests run this)

The YAML is the source: a chart can never disagree with the rules it shows. Each chart takes the rules that share a
`compare` key, so a rule added to the file appears in its chart on the next run. Stdlib and PyYAML only; the SVGs carry
their own light background so they read the same on the site and on GitHub in dark mode.

`evaluate()` is the one place a rule's expression ("2*T + R", "max(0.005*L, 0.5)", "1.574 if T <= 0.914 else 3.175")
is turned into a number; the tests use it to check every expression in the file.
"""
from __future__ import annotations

import ast
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research" / "process-profiles.yaml"
OUT = ROOT / "docs" / "img" / "research"
INK, MUTED, LINE, BG, GREEN, ORANGE = "#173d3c", "#526863", "#d8e0d3", "#fffdf5", "#6f8a80", "#bd3a12"
FONT = "system-ui,-apple-system,Segoe UI,Roboto,sans-serif"

# ----------------------------------------------------------------------------- expressions

_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b}
_CMP = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b}
_FUN = {"min": min, "max": max}


def evaluate(expr: float | int | str, env: dict[str, float]) -> float:
    """A rule's min/max/value as a number. Numbers pass through; a string may use the names in ``env``, numbers,
    + - * / ( ), unary minus, min(), max(), pi, and one ``a if <comparison> else b`` (not nested, not two). Anything
    else raises ValueError, as does dividing by zero, so a typo in the data file fails the tests instead of being
    skipped and a caller needs to catch only ValueError."""
    if isinstance(expr, bool):
        raise ValueError(f"{expr!r} is not a number")
    if isinstance(expr, (int, float)):
        return float(expr)
    names = dict(env, pi=math.pi)

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise ValueError(f"{expr!r}: unknown name {node.id!r}")
            return float(names[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUN and node.args \
                and not node.keywords:
            return _FUN[node.func.id](ev(a) for a in node.args)
        if isinstance(node, ast.IfExp) and isinstance(node.test, ast.Compare) and len(node.test.ops) == 1 \
                and type(node.test.ops[0]) in _CMP:
            test = _CMP[type(node.test.ops[0])](ev(node.test.left), ev(node.test.comparators[0]))
            return ev(node.body) if test else ev(node.orelse)
        raise ValueError(f"{expr!r}: {type(node).__name__} is not allowed in a rule expression")

    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"{expr!r}: {e.msg}") from None
    if sum(isinstance(n, ast.IfExp) for n in ast.walk(tree)) > 1:
        raise ValueError(f"{expr!r}: only one `a if <comparison> else b` is allowed")
    try:
        return ev(tree)
    except ZeroDivisionError:
        raise ValueError(f"{expr!r}: division by zero at {env}") from None


# ----------------------------------------------------------------------------- data

def load() -> dict:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


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

def ranges_svg(title: str, subtitle: str, groups: list[tuple[str, list[tuple[str, float | None, float | None, str]]]],
               vmax: float, ticks: list[float], unit: str, note: str) -> str:
    """One row per rule, grouped. A row is (label, low, high, colour): low and high equal is one value (a dot); both set
    is a range (a bar); high None is "at least low" (a dot with a fading tail to the right); low None is "at most
    high" (a tail from zero to a dot)."""
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
        for name, lo, hi, colour in rows:
            cy = y + row_h / 2
            out.append(f'<text x="{label_w - 10}" y="{cy + 4:.1f}" font-size="12" fill="{INK}" text-anchor="end">'
                       f'{escape(name)}</text>')
            if lo is not None and hi is not None and hi > lo:
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


def _row(rule: dict, sources: dict, env: dict, colour: str = GREEN):
    lo = evaluate(rule["min"], env) if "min" in rule else None
    hi = evaluate(rule["max"], env) if "max" in rule else None
    if "value" in rule:
        lo = hi = evaluate(rule["value"], env)
    return label(rule, sources), lo, hi, colour


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
    vmax = math.ceil(max(v for _, rows in groups for _, lo, hi, _ in rows for v in (lo, hi) if v is not None) * 2) / 2
    if any(lo == vmax and hi is None for _, rows in groups for _, lo, hi, _ in rows):
        vmax += 0.5  # room for the tail of a floor that sits at the top of the scale
    ticks = [i * 0.5 for i in range(int(vmax / 0.5) + 1)]
    n = sum(len(r) for _, r in groups)
    return ranges_svg("Minimum wall thickness: what each source recommends",
                      f"{n} rules from research/process-profiles.yaml (compare: min-wall). A bar is a range; ≥ is a floor.",
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
        rows = [_row(r, sources, SHEET) for r in data["rules"] if r.get("compare") == key and r.get("status") == "read"]
        if key in SHOP_COLUMNS:
            v = near[cols.index(SHOP_COLUMNS[key])]
            rows.append((f"{credit(sources[shop['source']])} tooling · {near[0]}", v, v, ORANGE))
        groups.append((title, rows))
    vmax = math.ceil(max(v for _, rows in groups for _, lo, hi, _ in rows for v in (lo, hi) if v is not None) / 2) * 2
    ticks = [float(i) for i in range(0, int(vmax) + 1, 2)]
    t_near, r_near = near[cols.index("T")], near[cols.index("R")]
    return ranges_svg(f"Sheet metal: the same rule from different sources, at T = {SHEET['T']} mm, R = {SHEET['R']} mm",
                      "Generic rules evaluated from research/process-profiles.yaml; orange is one shop's real tooling.",
                      groups, vmax, ticks, "mm",
                      f"Shop row: SendCutSend's specs file, {near[1]} {near[0]} (T {t_near:.2f}, R {r_near:.2f} mm). "
                      "Read 2026-10-31.")


FIGURES = {"process-min-wall.svg": min_wall, "process-sheet-metal.svg": sheet_metal}


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
        print("out of date with research/process-profiles.yaml (run python3 tools/process_profile_figures.py):",
              ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
