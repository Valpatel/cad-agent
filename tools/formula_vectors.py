#!/usr/bin/env python3
"""Golden test vectors for the browser port of cadagent.formulas, and the demo's material table, from the Python.

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

VECTORS = ROOT / "tests" / "fixtures" / "formula-vectors.json"
DATA = ROOT / "src" / "cadagent" / "webkit" / "formulas-data.js"
# Every function the browser port has, by its Python name (the JS name is the camelCase of it).
PORTED = ("snap_root_strain", "snap_deflection_force", "snap_arm", "cantilever_shape", "cantilever_strain_profile",
          "cantilever_thickness_profile", "grashof", "fourbar_angles", "transmission_angle", "fourbar_input_limits")
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


def materials():
    """The demo's materials: printed filaments with their modulus and allowable strain by print direction."""
    rows = []
    for key, m in PRINTED.items():
        rows.append({"key": key, "name": m.name, "condition": m.condition, "source": m.source,
                     "modulus": {d: m.secant_upper_bound(d) * 1e6 for d in DIRECTIONS},
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
    return ("/* Generated by tools/formula_vectors.py from cadagent.mechanical.compliant.allowables: do not edit by hand.\n"
            " * Printed filaments for the kit's demos: datasheet tensile modulus (Pa) and allowable snap-fit strain\n"
            " * (fraction) by print direction, single joining and repeated (x0.6). Each allowable is derived from the\n"
            " * datasheet named in `source` and is a hypothesis until a printed coupon is measured. */\n"
            f"export const MATERIALS = {body};\n")


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
