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
from cadagent.compliant.allowables import DIRECTIONS, PRINTED        # noqa: E402

VECTORS = ROOT / "tests" / "fixtures" / "formula-vectors.json"
DATA = ROOT / "src" / "cadagent" / "webkit" / "formulas-data.js"
# Every function the browser port has, by its Python name (the JS name is the camelCase of it).
PORTED = ("snap_root_strain", "snap_deflection_force", "snap_arm", "cantilever_shape", "cantilever_strain_profile",
          "cantilever_thickness_profile")
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

    def add(name, *args):
        out.append({"py": name, "js": camel(name), "args": list(args), "expected": jsonable(getattr(fx, name)(*args))})

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
    return ("/* Generated by tools/formula_vectors.py from cadagent.compliant.allowables: do not edit by hand.\n"
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
