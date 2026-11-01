#!/usr/bin/env python3
"""Golden test vectors for the browser port of cadagent.formulas, and the demos' material, fan and screw tables, from
the Python.

    python3 tools/formula_vectors.py            # write tests/fixtures/formula-vectors.json and webkit/formulas-data.js
    python3 tools/formula_vectors.py --check    # exit 1 if either committed file differs (the tests run this)

The Python is the source: ``tests/webkit-formulas.test.mjs`` runs ``src/cadagent/webkit/formulas.js`` on the same
vectors, so the browser can never compute a different number from the one agents get. Stdlib only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cadagent import formulas as fx                                  # noqa: E402  (this checkout's package)
from cadagent.mechanical.compliant.allowables import DIRECTIONS, PRINTED        # noqa: E402
from cadagent.thermal.fans import FANS                                            # noqa: E402
from cadagent.mechanical import bosses                                            # noqa: E402

VECTORS = ROOT / "tests" / "fixtures" / "formula-vectors.json"
DATA = ROOT / "src" / "cadagent" / "webkit" / "formulas-data.js"
# Every function the browser port has, by its Python name (the JS name is the camelCase of it).
PORTED = ("snap_root_strain", "snap_deflection_force", "snap_arm", "cantilever_shape", "cantilever_strain_profile",
          "cantilever_thickness_profile", "grashof", "fourbar_angles", "transmission_angle", "fourbar_input_limits",
          "fan_curve_line", "system_coefficient", "fans_in_series", "fans_in_parallel", "fan_stall_flow",
          "fan_operating_point", "torsion_constant_rect", "torsion_shear_stress_rect", "torsion_shear_strain_rect",
          "torsion_bar_stiffness", "torsion_snap_bar", "nut_factor", "preload_from_torque", "torque_for_preload",
          "thread_shear_areas", "thread_strip_force", "thread_radial_pressure", "boss_hoop_stress", "screw_boss")
TOLERANCE = {"rel": 1e-12, "abs": 1e-15}


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(w.title() for w in rest)


def jsonable(value):
    """Results as the JS returns them: dict keys in camelCase, tuples as lists."""
    if isinstance(value, dict):
        return {camel(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def cases():
    out = []

    def add(name, *args, **extra):
        out.append({"py": name, "js": camel(name), "args": list(args), "expected": jsonable(getattr(fx, name)(*args)),
                    **extra})

    def refuse(name, *args):
        """An input the Python refuses with ValueError: the port must refuse it too (with RangeError)."""
        try:
            getattr(fx, name)(*args)
        except ValueError:
            out.append({"py": name, "js": camel(name), "args": list(args), "raises": "ValueError"})
            return
        raise SystemExit(f"{name}{tuple(args)} no longer raises ValueError: change the refusal cases")

    xis = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
    for design in fx.DESIGNS:
        for xi in xis:
            add("cantilever_shape", xi, design)
            add("cantilever_strain_profile", xi, design)
            add("cantilever_thickness_profile", xi, design)
    mm = 1e-3
    arms = [(19 * mm, 3.28 * mm, 9.5 * mm, 2.4 * mm, 1815e6, 0.04, 2),      # Covestro Example I (PC, tapered)
            (12 * mm, 3.28 * mm, 9.5 * mm, 2.4 * mm, 1815e6, 0.04, 2),      # the same hook on a 12 mm arm
            (14 * mm, 1.6 * mm, 6 * mm, 0.5 * mm, 2703e6, 0.012, 1),        # docs/compliant.md's lid latch
            (40 * mm, 0.6 * mm, 2 * mm, 0.1 * mm, 724e6, 0.02, 1),
            (5 * mm, 4 * mm, 20 * mm, 5 * mm, 8637e6, 0.008, 3)]            # far outside small deflection
    for length, thickness, width, deflection, modulus, allowable, design in arms:
        add("snap_root_strain", length, thickness, deflection, design)
        strain = fx.snap_root_strain(length, thickness, deflection, design)
        add("snap_deflection_force", length, width, thickness, strain, modulus)
        add("snap_arm", length, thickness, width, deflection, modulus, allowable, design)
    for key, m in PRINTED.items():                    # each demo material at the demo's default geometry
        for direction in DIRECTIONS:
            add("snap_arm", 20 * mm, 1.6 * mm, 6 * mm, 1.5 * mm, m.secant_upper_bound(direction) * 1e6,
                m.allowable(direction), 1)
    for design in fx.DESIGNS:                         # an arm at rest: no strain or force, the same stiffness
        add("snap_arm", 20 * mm, 1.6 * mm, 6 * mm, 0.0, 2703e6, 0.02, design)
    fourbar_cases(add)
    fan_cases(add, refuse)
    torsion_cases(add, refuse)
    boss_cases(add, refuse)
    # What the Python refuses: xi outside 0..1, and a design that is not 1, 2 or 3 (including a string, a fraction
    # and an inherited key of a JS object).
    for xi in (-0.1, 1.2):
        refuse("cantilever_shape", xi, 1)
        refuse("cantilever_strain_profile", xi, 2)
    for bad in (0, 4, 2.5, "2", "toString"):
        refuse("cantilever_shape", 0.5, bad)
        refuse("cantilever_strain_profile", 0.5, bad)
        refuse("cantilever_thickness_profile", 0.5, bad)
        refuse("snap_root_strain", 20 * mm, 1.6 * mm, 1.5 * mm, bad)
        refuse("snap_arm", 20 * mm, 1.6 * mm, 6 * mm, 1.5 * mm, 2703e6, 0.02, bad)
    return out


# Four-bars (a crank, b coupler, c rocker, d ground): each Grashof inversion, a triple rocker, change points
# (parallelograms, a kite, a + b = c + d in lengths binary cannot hold), a near-degenerate one and links that never close.
FOURBARS = [(40, 120, 80, 100),            # Norton's Example 4-1, a crank-rocker (the demo's default)
            (80, 100, 120, 40),            # double crank
            (80, 100, 40, 120),            # rocker-crank: two input ranges
            (80, 40, 120, 100),            # double rocker: two input ranges
            (100, 80, 70, 60),             # triple rocker: one range, through 0
            (60, 30, 50, 70),
            (0.05, 0.02, 0.06, 0.04),
            (5, 2, 5, 2), (0.03, 0.07, 0.03, 0.07), (3, 3, 4, 4), (0.02, 0.05, 0.03, 0.04),     # change points
            (1, 1, 1 - 2.2e-6, 1 + 2e-6),  # open by 2e-7 at 0 degrees: a folded limit near 0
            (1, 1, 1, 10)]                 # one link longer than the other three: closes nowhere


# Where the two assemblies meet (an input limit, or 0 and 180 degrees on a change-point linkage) the angles are a double
# root: one ulp of difference in cos theta2 between two maths libraries moves them by about its square root (1e-8), so
# the port must agree there to 1e-7, not 1e-12. Beside it (1e-9 to 1e-6 rad away) the error grows only by a few
# thousand, so 1e-10 is enough. Whether the links close at all must still agree exactly. Measured on these vectors:
# Chrome and WebKit match the Python bit for bit, and Node 20 differs by at most 1.2e-12 (one ulp in Math.cos).
DOUBLE_ROOT = {"rel": 1e-7, "abs": 1e-7, "why": "where the branches meet: a double root"}
NEAR_DOUBLE_ROOT = {"rel": 1e-10, "abs": 1e-10, "why": "within 1e-6 rad of where the branches meet: near a double root"}


def fourbar_cases(add):
    """Both branches every 15 degrees, the change points and just beside them, and each input limit with points
    1e-7 rad either side (the open side closes nowhere, the inside on both branches). Output angles are compared
    as angles (pi and -pi are one position)."""
    import math
    for links in FOURBARS:
        add("grashof", *links)
        add("fourbar_input_limits", *links)
        angles = [math.radians(deg) for deg in range(-180, 181, 15)]
        angles += [0.0, math.pi, -math.pi, 1e-9, -1e-9, math.pi - 1e-9]
        lim = fx.fourbar_input_limits(*links)
        meet = [e for e in (lim["folded"], lim["stretched"]) if e is not None]
        for edge in meet:
            angles += [edge, -edge, edge - 1e-7, edge + 1e-7]
        if fx.grashof(*links)["kind"] == "change-point":
            meet += [0.0, math.pi]
        for t2 in angles:
            gap = min((abs(abs(t2) - m) for m in meet), default=1.0)
            near = {"tolerance": DOUBLE_ROOT} if gap == 0 else {"tolerance": NEAR_DOUBLE_ROOT} if gap < 1e-6 else {}
            for crossed in (False, True):
                add("fourbar_angles", *links, t2, crossed, angles=True, **near)
            add("transmission_angle", *links, t2, angles=True, **near)


# The fan-curve explorer's system slider: the pressure the enclosure needs at this flow (m^3/s), 100 m^3/h.
FAN_REFERENCE_FLOW = 100 / 3600
# A synthetic axial curve with a deep stall dip, which a linear (laminar) system crosses three times (unstable).
DIP = [(0.0, 20.0), (0.004, 8.0), (0.005, 14.0), (0.010, 6.0), (0.012, 0.0)]


def fan_cases(add, refuse):
    """Hand-solved straight-line fans (one, two in series, two in parallel), the stall-dip curve with its three
    crossings, systems exactly through a datasheet point (a root on a breakpoint), the datasheet's own published
    system curves, and the explorer's slider across its range, for every datasheet fan, one to four fans, both ways."""
    line = fx.fan_curve_line(40.0, 0.02)
    add("fan_curve_line", 40.0, 0.02)
    add("fan_curve_line", 15.2, 38.9 / 3600)
    for k in (4e5, 1.5e5, 1e4):                       # k qf^2 / p0 = 4 (restrictive), 1.5 (series = parallel), 0.1
        add("fan_operating_point", line, k)
        for n in (2, 3):
            add("fan_operating_point", fx.fans_in_series(line, n), k)
            add("fan_operating_point", fx.fans_in_parallel(line, n), k)
    add("fan_stall_flow", line)
    add("fan_stall_flow", DIP)
    add("fan_stall_flow", [(0.0, 5.0), (1.0, 6.0)])                          # a curve that only rises
    add("fan_stall_flow", [(0.0, 9.0), (1.0, 7.0), (2.0, 8.0), (3.0, 8.0), (4.0, 8.0), (5.0, 0.0)])   # a flat top
    add("fan_stall_flow", [(0.0, 9.0), (1.0, 9.0), (2.0, 4.0)])            # flat at shut-off: no rise, no stall
    add("fan_operating_point", DIP, 0.0, 2500.0)                             # three crossings: unstable
    add("fan_operating_point", DIP, 5.3e5)                                   # a quadratic system crosses it three times
    add("fan_operating_point", DIP, 3e5, 500.0)
    add("fan_operating_point", DIP, 1e6)
    for n in (2, 3):
        add("fans_in_series", DIP, n)
        add("fans_in_parallel", DIP, n)
    add("system_coefficient", 12.0, FAN_REFERENCE_FLOW)
    add("system_coefficient", 0.0, 0.01)
    # the datasheet's three published system curves (Pa per (m3/h)^2, read from the same chart), in SI
    published = [k * 3600 ** 2 for k in (0.00030214, 0.00075427, 0.0015352)]
    for fan in FANS.values():
        curve = fan.curve()
        add("fan_stall_flow", curve)
        for n in (1, 2, 3, 4):
            add("fans_in_series", curve, n)
            add("fans_in_parallel", curve, n)
        for k in published:
            add("fan_operating_point", curve, k)
        for q, p in curve[1:-1]:                     # through a marked point exactly: a root on a breakpoint
            add("fan_operating_point", curve, fx.system_coefficient(p, q))
        for dp in (2, 5, 8, 12, 16, 20, 25, 30, 40, 50, 65, 80):
            k = fx.system_coefficient(dp, FAN_REFERENCE_FLOW)
            for n in (1, 2, 3, 4):
                add("fan_operating_point", fx.fans_in_series(curve, n), k)
                add("fan_operating_point", fx.fans_in_parallel(curve, n), k)
    # What the Python refuses: too few points, flow not increasing, no loss, a negative loss, a curve the system never
    # crosses, a count that is not a whole number of at least 1, and a system point without a flow.
    refuse("fan_operating_point", [(0.0, 10.0)], 1e6)
    refuse("fan_operating_point", [(0.0, 10.0), (0.0, 5.0), (0.01, 0.0)], 1e6)
    refuse("fan_operating_point", [(0.01, 10.0), (0.0, 0.0)], 1e6)
    refuse("fan_operating_point", line, 0.0, 0.0)
    refuse("fan_operating_point", line, -1e5)
    refuse("fan_operating_point", line, 1e5, -10.0)
    refuse("fan_operating_point", [(0.0, 10.0), (0.01, 9.0)], 1.0)
    for bad in (0, -1, 2.5, True, "2"):
        refuse("fans_in_series", line, bad)
        refuse("fans_in_parallel", line, bad)
    refuse("fan_stall_flow", [(0.0, 1.0)])
    refuse("fans_in_series", [(0.0, 10.0)], 2)
    refuse("system_coefficient", 10.0, 0.0)
    refuse("system_coefficient", -1.0, 0.01)
    refuse("fan_curve_line", 0.0, 0.01)
    refuse("fan_curve_line", 10.0, -0.01)


def torsion_cases(add, refuse):
    """Rectangles from a square to a thin strip, either way round; the torsion-snap explorer's default and each demo
    material at it, one bar and two, at rest, at the permissible twist and far past it."""
    import math
    mm = 1e-3
    for w, t in [(2, 2), (3, 2), (4, 1.2), (6, 1), (20, 0.8), (1.2, 4), (10, 0.5)]:
        add("torsion_constant_rect", w * mm, t * mm)
        add("torsion_shear_stress_rect", 0.02, w * mm, t * mm)
        for twist in (0.0, 0.05, math.radians(8), math.radians(30)):
            add("torsion_shear_strain_rect", twist, 15 * mm, w * mm, t * mm)
    for L, G in [(15 * mm, 9.9e8), (8 * mm, 2.7e8), (30 * mm, 3.2e9)]:
        add("torsion_bar_stiffness", L, G, fx.torsion_constant_rect(4 * mm, 1.2 * mm))
    for key, m in PRINTED.items():                    # each demo material at the demo's default bar
        for bars in (1, 2):
            for repeated in (False, True):
                add("torsion_snap_bar", 15 * mm, 4 * mm, 1.2 * mm, math.radians(8), m.secant_upper_bound("along") * 1e6,
                    m.allowable("across", repeated), 10 * mm, bars)
    for twist in (0.0, math.radians(2), math.radians(20), math.radians(45)):
        for w, t in [(4, 1.2), (2, 2), (12, 0.8)]:
            add("torsion_snap_bar", 15 * mm, w * mm, t * mm, twist, 2.68e9, 0.0095, 10 * mm, 1)
    add("torsion_snap_bar", 15 * mm, 4 * mm, 1.2 * mm, 0.1, 2.68e9, 0.0095, 10 * mm, 2, 0.4)
    good = [15 * mm, 4 * mm, 1.2 * mm, 0.1, 2.68e9, 0.0095, 10 * mm, 1]
    for i, bad in [(0, 0.0), (1, -1 * mm), (3, -0.1), (4, 0.0), (5, 0.0), (6, 0.0), (7, 3), (7, 1.5), (7, True),
                   (0, "15"), (3, None)]:
        refuse("torsion_snap_bar", *good[:i], bad, *good[i + 1:])
    refuse("torsion_snap_bar", *good, 0.5)


def boss_cases(add, refuse):
    """The flank's push and the Lame wall alone; the screw-boss explorer's default; every DELTA PT size the explorer
    offers in every demo material, upright and lying, across its boss, engagement and torque sliders; and refusals."""
    import math
    mm = 1e-3
    for d, P, mu in [(3 * mm, 0.5 * mm, 0.15), (3 * mm, 1.12 * mm, 0.2), (4 * mm, 1.46 * mm, 0.65), (8 * mm, 1.25 * mm, 0.1)]:
        add("nut_factor", d, P, mu, mu)
        add("nut_factor", d, P, mu, mu, math.radians(30))
        add("nut_factor", d, P, mu, 0.0, math.radians(40))
    for T, d, K in [(0.5, 3 * mm, 0.2), (0.3, 3 * mm, 0.2675), (2.0, 8 * mm, 0.18)]:
        add("preload_from_torque", T, d, K)
        add("torque_for_preload", 400.0, d, K)
    add("preload_from_torque", 0.5, 3 * mm)
    add("torque_for_preload", 400.0, 3 * mm)
    for d, P, Le in [(3 * mm, 0.5 * mm, 6 * mm), (3 * mm, 1.12 * mm, 6 * mm), (5 * mm, 1.8 * mm, 12 * mm)]:
        add("thread_shear_areas", d, P, Le)
        add("thread_strip_force", d, P, Le, 15.5e6)
        add("thread_strip_force", d, P, Le, 15.5e6, "external")
    for F, d, Le in [(400.0, 3 * mm, 6 * mm), (0.0, 3 * mm, 6 * mm), (1500.0, 5 * mm, 9 * mm)]:
        add("thread_radial_pressure", F, d, Le)
        add("thread_radial_pressure", F, d, Le, math.radians(30))
    for p, d, D in [(3e6, 3 * mm, 6 * mm), (3e6, 3 * mm, 3.75 * mm), (0.0, 3 * mm, 6 * mm), (1e6, 4 * mm, 4.1 * mm)]:
        add("boss_hoop_stress", p, d, D)
    add("screw_boss", 3 * mm, 1.12 * mm, 6 * mm, 6 * mm, 0.3, 15.5e6, 35e6)
    add("screw_boss", 3 * mm, 1.12 * mm, 6 * mm, 6 * mm, 0.3, 15.5e6, 35e6, 0.2, 0.65)
    for key, m in PRINTED.items():
        shear = bosses.SHEAR_FROM_TENSILE * m.strength("across") * 1e6
        for size in BOSS_SIZES:
            s = bosses.DELTA_PT[size]
            d, P = s["diameter_mm"] * mm, s["pitch_mm"] * mm
            for axis, direction in bosses.AXES.items():
                hoop = m.strength(direction) * 1e6
                for k_out, k_len, torque in [(2.0, 2.0, 0.3), (1.5, 1.5, 0.2), (2.5, 3.0, 0.8), (1.3, 2.4, 0.05)]:
                    add("screw_boss", d, P, k_len * d, k_out * d, torque, shear, hoop, *bosses.FRICTION_BAND)
    for dd in (2.2, 2.5, 3.5, 4.5):                   # exactly 2 d, from millimetres
        add("screw_boss", dd * mm, 1.12 * mm, 2 * dd * mm, 2 * dd * mm, 0.1, 15.5e6, 35e6)
    good = [3 * mm, 1.12 * mm, 6 * mm, 6 * mm, 0.3, 15.5e6, 35e6, 0.2, 0.65]
    for i, bad in [(0, 0.0), (1, -1 * mm), (2, -6 * mm), (3, 3 * mm), (3, 2 * mm), (4, 0.0), (5, -1.0), (6, 0.0),
                   (7, -0.1), (8, 0.1), (4, "0.3")]:
        refuse("screw_boss", *good[:i], bad, *good[i + 1:])
    refuse("thread_radial_pressure", -1.0, 3 * mm, 6 * mm)
    refuse("thread_radial_pressure", 400.0, 0.0, 6 * mm)
    refuse("thread_radial_pressure", 400.0, 3 * mm, 6 * mm, 0.0)
    refuse("boss_hoop_stress", 1e6, 3 * mm, 3 * mm)
    refuse("boss_hoop_stress", -1.0, 3 * mm, 6 * mm)
    refuse("thread_strip_force", 3 * mm, 0.5 * mm, 6 * mm, 1e7, "both")


# The screw-boss explorer's screw sizes (DELTA PT 20 to 50: 2 to 5 mm).
BOSS_SIZES = ("20", "25", "30", "35", "40", "50")


def screws():
    """The explorer's screws: DELTA PT sizes in SI, with the friction band, the boss guide and their sources."""
    return {"source": bosses.DELTA_PT_SOURCE, "friction": list(bosses.FRICTION_BAND),
            "frictionSource": bosses.FRICTION_SOURCE, "shearFromTensile": bosses.SHEAR_FROM_TENSILE,
            "sizes": [{"key": k, "diameter": bosses.DELTA_PT[k]["diameter_mm"] * 1e-3,
                       "pitch": bosses.DELTA_PT[k]["pitch_mm"] * 1e-3} for k in BOSS_SIZES]}


def fans():
    """The explorer's fans: each datasheet curve in SI (m^3/s, Pa), with its name, voltage, speed and source."""
    return [{"key": f.key, "name": f.name, "voltage": f.voltage, "speed": f.speed, "density": f.density,
             "source": f.source, "curve": [list(pt) for pt in f.curve()]} for f in FANS.values()]

def materials():
    """The demo's materials: printed filaments with their modulus and allowable strain by print direction."""
    rows = []
    for key, m in PRINTED.items():
        rows.append({"key": key, "name": m.name, "condition": m.condition, "source": m.source,
                     "modulus": {d: m.secant_upper_bound(d) * 1e6 for d in DIRECTIONS},
                     "strength": {d: m.strength(d) * 1e6 for d in DIRECTIONS},
                     "allowable": {d: {"single": m.allowable(d), "repeated": m.allowable(d, repeated=True)}
                                   for d in DIRECTIONS}})
    return rows


def vectors_text() -> str:
    names = {c["py"] for c in cases()}
    missing = set(PORTED) - names
    if missing:
        raise SystemExit(f"no vectors for ported functions: {sorted(missing)}")
    head = {"generated_by": "tools/formula_vectors.py", "source": "cadagent.formulas (Python) is the reference",
            "tolerance": TOLERANCE, "ported": [camel(n) for n in PORTED]}
    lines = [f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}," for k, v in head.items()]
    rows = ",\n".join("  " + json.dumps(c, ensure_ascii=False) for c in cases())     # one case per line
    return "{\n" + "\n".join(lines) + '\n "cases": [\n' + rows + "\n ]\n}\n"


def data_text() -> str:
    body = json.dumps(materials(), indent=1, ensure_ascii=False)
    fan_rows = ",\n".join(" " + json.dumps(f, ensure_ascii=False) for f in fans())
    return ("/* Generated by tools/formula_vectors.py from cadagent.mechanical.compliant.allowables,\n"
            " * cadagent.thermal.fans and cadagent.mechanical.bosses: do not edit by hand.\n"
            " * MATERIALS: printed filaments for the kit's demos: the highest datasheet tensile modulus (Pa), the lowest\n"
            " * tensile strength (Pa) and the allowable snap-fit strain (fraction) by print direction, single joining\n"
            " * and repeated (x0.6). Each is derived from the datasheets named in `source` and is a hypothesis until a\n"
            " * printed coupon is measured.\n"
            " * FANS: fan curves read from the datasheet named in `source`, in SI ([flow m^3/s, pressure Pa]), at the\n"
            " * air density `density` (kg/m^3) and the voltage `voltage` (V), on the maker's test rig.\n"
            " * SCREWS: DELTA PT thread-forming screw sizes in SI (m), the steel-on-plastic friction band and the\n"
            " * shear strength as a fraction of the tensile one, with their sources. */\n"
            f"export const MATERIALS = {body};\n"
            f"export const FANS = [\n{fan_rows}\n];\n"
            f"export const SCREWS = {json.dumps(screws(), indent=1, ensure_ascii=False)};\n")


def main(argv) -> int:
    files = {VECTORS: vectors_text(), DATA: data_text()}
    if "--check" in argv:
        stale = [str(p.relative_to(ROOT)) for p, text in files.items() if not p.exists() or p.read_text() != text]
        if stale:
            print("out of date (run python3 tools/formula_vectors.py): " + ", ".join(stale))
            return 1
        print(f"formula vectors and demo materials are current ({len(cases())} cases)")
        return 0
    for p, text in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
