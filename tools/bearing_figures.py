#!/usr/bin/env python3
"""Draw docs/img/bearings/*.svg from cadagent.formulas.bearings and cadagent.mechanical.bearings.

    python3 tools/bearing_figures.py            # write the SVGs
    python3 tools/bearing_figures.py --check    # exit 1 if a committed SVG differs (tests/test_bearings.py runs this)

Pure Python, so the page shows exactly what the code computes on the catalogue bearings and the worked example below.
Colours: the categorical slots and the steps of the site's chart palette, each line labelled at its end, so no
meaning rests on colour alone; every mark has a <title> for its value on hover.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cadagent import formulas as fx                     # noqa: E402  (this checkout's package)
from cadagent.mechanical import bearings as mb          # noqa: E402

OUT = ROOT / "docs" / "img" / "bearings"
# The worked example the page quotes: a walking robot's knee, a sealed 6201 swinging +/-30 degrees once a second,
# 900 N for 60 % of each stride and 150 N for the rest, 2 000 h asked; a fall with the power cut puts 3 485 N on it.
KNEE = dict(oscillation={"amplitude_deg": 30, "cycles_per_min": 60},
            duty=[{"name": "stance", "radial_n": 900, "share": 0.6}, {"name": "swing", "radial_n": 150, "share": 0.4}],
            required_hours=2000, static=[{"name": "power cut", "radial_n": 3485}])
KNEE_GEOMETRY = {"balls": 7, "ball_mm": 5.953}            # assumed, not SKF's: see docs/bearings.md
LIFE_BEARINGS = ("skf-61804", "skf-6201", "skf-6301", "skf-nu-202-ecp")
STYLE = ("<style>text{font:13px system-ui,sans-serif;fill:#1d1d1b}.muted{fill:#5c5b56;font-size:11px}"
         ".axis{stroke:#9b9a93;stroke-width:1;fill:none}.grid{stroke:#e2e1dc;stroke-width:1}"
         ".s1{fill:#2a78d6;stroke:#2a78d6}.s2{fill:#eb6834;stroke:#eb6834}.s3{fill:#1baf7a;stroke:#1baf7a}"
         ".s4{fill:#eda100;stroke:#eda100}.bad{fill:#d1242f;stroke:#d1242f}.band{fill:#efeee9;stroke:none}"
         ".bg{fill:#fcfcfb}.ring{stroke:#fcfcfb}"
         "@media (prefers-color-scheme:dark){text{fill:#f0efec}.muted{fill:#c3c2b7}.axis{stroke:#8a897f}"
         ".grid{stroke:#383835}.s1{fill:#3987e5;stroke:#3987e5}.s2{fill:#d95926;stroke:#d95926}"
         ".s3{fill:#199e70;stroke:#199e70}.s4{fill:#c98500;stroke:#c98500}.band{fill:#262624}"
         ".bg{fill:#1a1a19}.ring{stroke:#1a1a19}.bad{fill:#e5484d;stroke:#e5484d}}"
         "</style>")
MARK = {"pass": "pass", "warn": "warn ▲", "fail": "fail ✕"}
VERDICT_CLASS = {"pass": "s3", "warn": "s4", "fail": "bad"}
# Rows whose value must stay below the limit; every other row with a limit must stay above it.
UPPER = {"axial load", "load range", "speed"}


def _svg(width: int, height: int, label: str, body: list) -> str:
    return "\n".join([f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
                      f'height="{height}" role="img" aria-label="{escape(label)}">', STYLE,
                      f'<rect class="bg" width="{width}" height="{height}"/>', *body, "</svg>"]) + "\n"


def _log(v: float, lo: float, hi: float, p0: float, p1: float) -> float:
    return p0 + (p1 - p0) * (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))


def _fmt(v: float) -> str:
    return f"{v:g}" if v < 1e4 else f"10^{round(math.log10(v))}" if abs(math.log10(v) % 1) < 1e-9 else f"{v:.0e}"


def life_figure() -> str:
    """L10 against the equivalent load on log-log axes: solid where the makers call the life robust (P up to 0.5 C,
    0.33 C for a roller), dashed beyond, ending at C0, where the raceways start to dent; the knee's load marked."""
    lo_p, hi_p, lo_l, hi_l = 50.0, 20000.0, 0.01, 1e6
    x0, x1, y0, y1 = 70.0, 560.0, 50.0, 330.0
    X = lambda p: _log(p, lo_p, hi_p, x0, x1)                                 # noqa: E731
    Y = lambda life: _log(life, lo_l, hi_l, y1, y0)                           # noqa: E731
    body = ['<text x="20" y="24">Basic rating life L10 (million revolutions) against the equivalent load P (N)</text>']
    for e in range(-2, 7):
        v = 10.0 ** e
        body.append(f'<line class="grid" x1="{x0}" y1="{Y(v):.1f}" x2="{x1}" y2="{Y(v):.1f}"/>'
                    f'<text x="{x0 - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="muted">'
                    f'{("10^" + str(e)) if abs(e) > 2 else f"{v:g}"}</text>')
    for p in (50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
        body.append(f'<line class="grid" x1="{X(p):.1f}" y1="{y0}" x2="{X(p):.1f}" y2="{y1}"/>'
                    f'<text x="{X(p):.1f}" y="{y1 + 16:.0f}" text-anchor="middle" class="muted">{p:g}</text>')
    labels = []
    for i, key in enumerate(LIFE_BEARINGS, start=1):
        b = mb.bearing(key)
        top = (0.33 if b.roller else 0.5) * b.dynamic_n
        end = min(b.static_n, hi_p) if not b.roller else min(b.dynamic_n, hi_p)
        ps = [lo_p * (end / lo_p) ** (k / 60) for k in range(61)]
        solid = [p for p in ps if p <= top] + [top]
        dashed = [top] + [p for p in ps if p > top]
        for pts, dash in ((solid, ""), (dashed, ' stroke-dasharray="5 4"')):
            pts = [p for p in pts if p <= end and fx.rating_life(b.dynamic_n, p, b.roller) <= hi_l]
            if len(pts) < 2:
                continue
            line = " ".join(f"{X(p):.1f},{Y(fx.rating_life(b.dynamic_n, p, b.roller)):.1f}" for p in pts)
            body.append(f'<polyline class="s{i}" style="fill:none" stroke-width="2"{dash} points="{line}"><title>'
                        f'{escape(b.maker + " " + b.designation)}: C {b.dynamic_n / 1e3:g} kN, C0 '
                        f'{b.static_n / 1e3:g} kN</title></polyline>')
        le = fx.rating_life(b.dynamic_n, end, b.roller)
        body.append(f'<line class="s{i}" stroke-width="2" x1="{X(end):.1f}" y1="{Y(le) - 6:.1f}" x2="{X(end):.1f}" '
                    f'y2="{Y(le) + 6:.1f}"><title>{escape(b.designation)}: '
                    f'{"C0" if not b.roller else "C"} = {end:.0f} N, L10 {le:.3g}</title></line>')
        lab = fx.rating_life(b.dynamic_n, lo_p, b.roller)
        labels.append((Y(min(lab, hi_l)), f"{b.designation}{' (roller)' if b.roller else ''}", i))
    # direct labels at the left edge, spread so they never overlap
    labels.sort()
    last = -1e9
    for y, text, i in labels:
        y = max(y, last + 15, y0 + 10)
        last = y
        body.append(f'<rect class="s{i}" x="{x1 + 14}" y="{y - 9:.1f}" width="10" height="10" rx="2"/>'
                    f'<text x="{x1 + 30}" y="{y:.1f}">{escape(text)}</text>')
    knee = mb.check_bearing("skf-6201-2rsh", **KNEE, internal=KNEE_GEOMETRY)
    pm, l10 = knee["life"]["equivalent_load_n"], knee["life"]["l10_million_rev"]
    body.append(f'<circle class="s2 ring" cx="{X(pm):.1f}" cy="{Y(l10):.1f}" r="5" stroke-width="2">'
                f'<title>the knee: P = {pm:.0f} N, L10 {l10:.0f} million revolutions</title></circle>'
                f'<line class="axis" x1="{X(pm):.1f}" y1="{Y(l10) + 6:.1f}" x2="{X(pm):.1f}" y2="{Y(0.3) - 14:.1f}"/>'
                f'<text x="{X(pm):.1f}" y="{Y(0.3):.1f}" text-anchor="middle">the knee\'s duty: P = {pm:.0f} N, '
                f'L10 {l10:.0f}</text>')
    body += [f'<text x="20" y="{y1 + 40:.0f}" class="muted">SKF catalogue ratings; L10 = (C / P)^3 for balls, '
             '^(10/3) for rollers (ISO 281). Solid up to 0.5 C (0.33 C for a roller),</text>',
             f'<text x="20" y="{y1 + 56:.0f}" class="muted">where SKF calls the life robust; dashed beyond. A ball '
             'bearing\'s line ends at its C0 (tick), where the raceways start to dent.</text>']
    return _svg(720, int(y1 + 70), "Basic rating life against load for four SKF bearings on log-log axes", body)


def table_figure() -> str:
    """e and Y of a deep-groove ball bearing against f0 Fa / C0, one panel each, for the three clearances."""
    lo, hi = 0.172, 6.89
    panels = (("e: Fa / Fr above it, the axial load counts", "e", 0.15, 0.6, 60.0),
              ("Y: the axial load's factor in P = X Fr + Y Fa", "y", 0.9, 2.4, 420.0))
    w, y0, y1 = 300.0, 50.0, 260.0
    body = []
    qs = [lo * (hi / lo) ** (k / 80) for k in range(81)]
    for title, key, vmin, vmax, x0 in panels:
        x1 = x0 + w
        X = lambda q, x0=x0, x1=x1: _log(q, lo, hi, x0, x1)                       # noqa: E731
        Y = lambda v, vmin=vmin, vmax=vmax: y1 - (y1 - y0) * (v - vmin) / (vmax - vmin)   # noqa: E731
        body.append(f'<text x="{x0 - 40:.0f}" y="28">{escape(title)}</text>')
        steps = [round(vmin + (vmax - vmin) * k / 6, 3) for k in range(7)]
        for v in steps:
            body.append(f'<line class="grid" x1="{x0}" y1="{Y(v):.1f}" x2="{x1}" y2="{Y(v):.1f}"/>'
                        f'<text x="{x0 - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="muted">{v:g}</text>')
        for q in (0.172, 0.345, 0.689, 1.38, 3.45, 6.89):
            body.append(f'<text x="{X(q):.1f}" y="{y1 + 16:.0f}" text-anchor="middle" class="muted">{q:g}</text>')
        body.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{y1 + 34:.0f}" text-anchor="middle" class="muted">'
                    'f0 Fa / C0 (log scale)</text>')
        for i, clearance in enumerate(fx.CLEARANCES, start=1):
            pts = " ".join(f"{X(q):.1f},{Y(fx.deep_groove_factors(q, clearance)[key]):.1f}" for q in qs)
            body.append(f'<polyline class="s{i}" style="fill:none" stroke-width="2" points="{pts}"><title>{clearance} '
                        f'clearance</title></polyline>')
            for row in fx.DEEP_GROOVE_TABLE[clearance]:
                v = row[1] if key == "e" else row[3]
                body.append(f'<circle class="s{i} ring" cx="{X(row[0]):.1f}" cy="{Y(v):.1f}" r="4" '
                            f'stroke-width="1.5"><title>{clearance}, f0 Fa / C0 = {row[0]:g}: {key} = {v:g}'
                            '</title></circle>')
    for i, (clearance, name) in enumerate(zip(fx.CLEARANCES, ("normal clearance", "C3", "C4")), start=1):
        body.append(f'<rect class="s{i}" x="{60 + 150 * (i - 1)}" y="{y1 + 52:.0f}" width="12" height="12" rx="2"/>'
                    f'<text x="{77 + 150 * (i - 1)}" y="{y1 + 62:.0f}">{name}</text>')
    body.append(f'<text x="740" y="{y1 + 62:.0f}" text-anchor="end" class="muted">dots: SKF Table 9; lines: the '
                'interpolation</text>')
    return _svg(760, int(y1 + 76), "The deep-groove ball bearing's e and Y against f0 Fa over C0 for normal, C3 and "
                "C4 clearance", body)


def knee_figure() -> str:
    """Left: the oscillation factor against the amplitude, Harris and Rumbarger, the small-swing region shaded and
    the knee's swing marked. Right: each check row of the knee for the 6201 and the 6301."""
    crit = fx.critical_amplitude(KNEE_GEOMETRY["balls"], KNEE_GEOMETRY["ball_mm"] / 22.0, "outer")
    lo, hi, fmin, fmax = 1.0, 180.0, 0.4, 100.0
    x0, x1, y0, y1 = 60.0, 360.0, 50.0, 280.0
    X = lambda a: _log(a, lo, hi, x0, x1)                                     # noqa: E731
    Y = lambda f: _log(f, fmin, fmax, y1, y0)                                 # noqa: E731
    body = ['<text x="20" y="24">Oscillations per revolution of equal fatigue</text>',
            f'<rect class="band" x="{x0}" y="{y0}" width="{X(10) - x0:.1f}" height="{y1 - y0}"/>',
            f'<text x="{x0 + 4}" y="{y1 - 36}" class="muted">below 10°: SKF</text>',
            f'<text x="{x0 + 4}" y="{y1 - 22}" class="muted">calls it invalid;</text>',
            f'<text x="{x0 + 4}" y="{y1 - 8}" class="muted">wear governs</text>']
    for f in (0.5, 1, 2, 5, 10, 20, 50, 100):
        body.append(f'<line class="grid" x1="{x0}" y1="{Y(f):.1f}" x2="{x1}" y2="{Y(f):.1f}"/>'
                    f'<text x="{x0 - 6}" y="{Y(f) + 4:.1f}" text-anchor="end" class="muted">{f:g}</text>')
    for a in (1, 2, 5, 10, 20, 30, 50, 90, 180):
        body.append(f'<text x="{X(a):.1f}" y="{y1 + 16:.0f}" text-anchor="middle" class="muted">{a}°</text>')
    body.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{y1 + 34:.0f}" text-anchor="middle" class="muted">amplitude θ, '
                'centre to one end (log scale)</text>')
    amps = [lo * (hi / lo) ** (k / 90) for k in range(91)]
    for cls, name, f in (("s1", "Harris, 90 / θ", fx.harris_factor),
                         ("s2", f"Rumbarger, 7 balls (θcrit {crit:.0f}°)", lambda a: fx.rumbarger_factor(a, crit))):
        pts = " ".join(f"{X(a):.1f},{Y(f(a)):.1f}" for a in amps)
        body.append(f'<polyline class="{cls}" style="fill:none" stroke-width="2" points="{pts}"><title>{escape(name)}'
                    '</title></polyline>')
    body += [f'<text x="{X(3.0):.1f}" y="{Y(fx.harris_factor(3.0)) - 10:.1f}">Harris, 90 / θ</text>',
             f'<text x="{X(2.2):.1f}" y="{Y(fx.rumbarger_factor(2.2, crit)) + 22:.1f}">Rumbarger: 7 balls, θcrit '
             f'{crit:.0f}° (dotted line)</text>',
             f'<line class="axis" x1="{X(crit):.1f}" y1="{y0}" x2="{X(crit):.1f}" y2="{y1}" stroke-dasharray="3 3"/>']
    a_k = fx.rumbarger_factor(30, crit)
    body.append(f'<circle class="s2 ring" cx="{X(30):.1f}" cy="{Y(a_k):.1f}" r="5" stroke-width="2"><title>the '
                f'knee: ±30°, {a_k:.2f} oscillations per revolution</title></circle>'
                f'<text x="{X(30) + 8:.1f}" y="{Y(a_k) + 20:.1f}">knee ±30°: {a_k:.2f}</text>')
    # right: the checks
    bx, by = 420.0, 50.0
    body.append(f'<text x="{bx}" y="24">The knee, checked (verdict per row; s0 and x / 2b)</text>')
    results = [("6201-2RSH", mb.check_bearing("skf-6201-2rsh", **KNEE, internal=KNEE_GEOMETRY)),
               ("6301-2RSH", mb.check_bearing("skf-6301-2rsh", **KNEE))]
    names = [r["check"] for r in results[0][1]["checks"]]
    body.append(f'<text x="{bx + 190}" y="{by + 4}" class="muted">6201-2RSH</text>'
                f'<text x="{bx + 290}" y="{by + 4}" class="muted">6301-2RSH</text>')
    for k, check in enumerate(names):
        y = by + 26 + 22 * k
        body.append(f'<text x="{bx}" y="{y:.0f}">{escape(check.replace("static safety: ", "s0, "))}</text>')
        for j, (_, res) in enumerate(results):
            row = next((r for r in res["checks"] if r["check"] == check), None)
            if row is None:
                continue
            val = row["value"]
            shown = check.startswith("static safety") or check == "contact travel"
            txt = f"{MARK[row['verdict']]}" + (f" {val:.2f}" if shown and isinstance(val, float) else "")
            weight = ' style="font-weight:700"' if row["verdict"] == "fail" else ""
            body.append(f'<text x="{bx + 190 + 100 * j}" y="{y:.0f}"{weight}>{escape(txt)}<title>'
                        f'{escape(row["detail"])}</title></text>')
    y = by + 26 + 22 * len(names) + 10
    life = results[0][1]["life"]
    body += [f'<text x="{bx}" y="{y:.0f}" class="muted">6201: L10 {life["life_million"]:.0f} million '
             f'oscillations, {life["hours"] / 1e3:.0f} thousand hours</text>',
             f'<text x="{bx}" y="{y + 16:.0f}" class="muted">at ±30°, 1 Hz, 900 N / 150 N; s0 in a 3 485 N power cut'
             '</text>',
             f'<text x="{bx}" y="{y + 32:.0f}" class="muted">6301 has no geometry given: its θcrit row warns</text>']
    return _svg(820, int(max(y1 + 50, y + 46)), "A knee bearing's oscillation factor against amplitude, and the "
                "knee's check rows for a 6201 and a 6301", body)


def page_example() -> dict:
    """The spec in docs/bearings.md's "Check a bearing" section, read from the page so the figure shows its output."""
    text = (ROOT / "docs" / "bearings.md").read_text()
    return yaml.safe_load(text.split("```yaml\n", 1)[1].split("```", 1)[0])


def margin_figure() -> str:
    """The page's example spec, checked: each row's margin to its limit (value over limit, or limit over value for a
    row that must stay below it) on a log axis, with 1 the limit; dots coloured and labelled by verdict."""
    result = mb.check_spec(page_example())
    lo, hi, x0, x1 = 0.2, 1000.0, 230.0, 630.0
    X = lambda m: _log(min(max(m, lo), hi), lo, hi, x0, x1)                   # noqa: E731
    body = ['<text x="20" y="24">The example above, checked: how far each row is from its limit</text>']
    y = 44.0
    for item in result["bearings"]:
        rows = [r for r in item["checks"] if r.get("limit") not in (None, 0) and isinstance(r.get("value"), float)]
        top = y + 30
        bottom = top + 22 * len(rows)
        body += [f'<text x="20" y="{y + 18:.0f}" style="font-weight:700">{escape(item["name"])}: '
                 f'{escape(item["bearing"]["designation"])}, {MARK[item["verdict"]]}</text>',
                 f'<rect class="band" x="{x0}" y="{top - 12:.0f}" width="{X(1) - x0:.1f}" '
                 f'height="{bottom - top + 6:.0f}"/>']
        for m in (1, 10, 100, 1000):
            body.append(f'<line class="grid" x1="{X(m):.1f}" y1="{top - 12:.0f}" x2="{X(m):.1f}" '
                        f'y2="{bottom - 6:.0f}"/>')
        body.append(f'<line class="axis" x1="{X(1):.1f}" y1="{top - 12:.0f}" x2="{X(1):.1f}" y2="{bottom - 6:.0f}" '
                    'stroke-width="2"/>')
        for k, row in enumerate(rows):
            ry = top + 22 * k
            m = row["limit"] / row["value"] if row["check"] in UPPER else row["value"] / row["limit"]
            label = row["check"].replace("static safety: ", "s0, ").replace(" (heaviest block)", "")
            mark = f' {MARK[row["verdict"]]}' if row["verdict"] != "pass" else ""
            shown = f"{m:.2g}" if m < 10 else f"{m:.0f}"
            body += [f'<text x="{x0 - 10}" y="{ry + 4:.0f}" text-anchor="end">{escape(label)}</text>',
                     f'<line class="grid" x1="{x0}" y1="{ry:.0f}" x2="{x1}" y2="{ry:.0f}" stroke-dasharray="2 4"/>',
                     f'<circle class="{VERDICT_CLASS[row["verdict"]]} ring" cx="{X(m):.1f}" cy="{ry:.0f}" r="6" '
                     f'stroke-width="2"><title>{escape(row["detail"])}</title></circle>',
                     f'<text x="{X(m) + 11:.1f}" y="{ry + 4:.0f}">{shown}×{mark}</text>']
        y = bottom + 4
    for m in (0.2, 1, 10, 100, 1000):
        body.append(f'<text x="{X(m):.1f}" y="{y + 12:.0f}" text-anchor="middle" class="muted">{m:g}</text>')
    body += [f'<text x="{x0}" y="{y + 30:.0f}" class="muted">margin: value / limit, or limit / value for the load '
             'range and speed (log scale)</text>',
             f'<text x="{x0}" y="{y + 46:.0f}" class="muted">shaded: past the limit</text>']
    return _svg(720, int(y + 60), "The docs example checked: each row's margin to its limit for the rope sheave and "
                "the knee; the knee's power-cut s0 is past its limit and the critical amplitude warns", body)


FIGURES = {"checks.svg": margin_figure, "life-load.svg": life_figure, "xy-table.svg": table_figure,
           "knee.svg": knee_figure}


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
        print("out of date (run python3 tools/bearing_figures.py):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
