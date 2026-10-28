"""Time the gate relation table on a synthetic assembly (the plan's 100-part acceptance figure).

    PYTHONPATH=src python tools/gate_timing.py [--parts 100] [--cache DIR] [--json] [--motion SAMPLES]

Builds ``parts`` simple solids (boxes, cylinders, spheres) in rows of ten: within a row,
neighbours touch, overlap, sit inside one another or hover 0.5 mm apart, by row; rows are
20 mm apart so only in-row neighbours are broad-phase candidates. Prints the table's stats
(broad and narrow phase seconds, candidates, kernel queries, cache hits). Run it twice with
the same ``--cache`` to see the warm figure: the second run must make no kernel query.
``tests/test_gate_relations.py`` imports ``synthetic_assembly`` from here and asserts the
cold run is under 5 s.

``--motion SAMPLES`` times the motion gate instead, on the same assembly with three joints (``motion_joints``):
a lift that clears its 0.5 mm neighbours, a slide that runs into the next row and a turn that swings a cube into
its neighbours (so the verdict has collisions to witness), each sampled ``SAMPLES`` times (one joint at a time, so
``3 x SAMPLES`` poses).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROW_KINDS = ("touching", "overlapping", "apart", "contains", "touching")


def synthetic_assembly(parts: int = 100):
    """``(Assembly, expected)``: the synthetic assembly and ``{(a, b): state}`` for in-row neighbours."""
    import cadquery as cq
    from cadagent.gates import Assembly

    asm, expected = Assembly(), {}
    for i in range(parts):
        row, col = divmod(i, 10)
        kind = ROW_KINDS[row % len(ROW_KINDS)]
        y = row * 20.0
        name = f"r{row}c{col}"
        shape_kind = ("box", "cylinder", "sphere")[col % 3] if kind != "contains" else ("box" if col % 2 == 0 else "ball")
        if kind == "touching":       # 10 mm cubes and cylinders, 10 mm pitch: faces meet
            x = col * 10.0
            shape = (cq.Solid.makeBox(10, 10, 10) if shape_kind != "cylinder"
                     else cq.Solid.makeBox(10, 10, 10).fuse(cq.Solid.makeCylinder(3, 12, cq.Vector(5, 5, 0))))
        elif kind == "overlapping":  # 10 mm parts at 9 mm pitch
            x = col * 9.0
            shape = {"box": cq.Solid.makeBox(10, 10, 10),
                     "cylinder": cq.Solid.makeCylinder(5, 10, cq.Vector(5, 5, 0)),
                     "sphere": cq.Solid.makeSphere(5, cq.Vector(5, 5, 5), angleDegrees1=-90)}[shape_kind]
        elif kind == "apart":        # 0.5 mm gaps: inside the broad-phase margin, so measured exactly
            x = col * 10.5
            shape = cq.Solid.makeBox(10, 10, 10)
        else:                        # a 12 mm box then a 3 mm ball inside it, alternating
            x = (col // 2) * 13.0
            shape = (cq.Solid.makeBox(12, 12, 12) if shape_kind == "box"
                     else cq.Solid.makeSphere(1.5, cq.Vector(6, 6, 6), angleDegrees1=-90))
        asm.add(name, shape, (x, y, 0.0))
        if col > 0:
            prev = f"r{row}c{col - 1}"
            if kind == "contains":
                expected[(prev, name)] = "contains" if col % 2 == 1 else "apart"
            else:
                expected[(prev, name)] = kind
    return asm, expected


def motion_joints(samples: int = 20):
    """Three joints on the synthetic assembly's "apart" rows (10 mm cubes, 0.5 mm gaps): a lift along +Z
    (clears), a slide along +Y towards the next row, and a turn about a cube's own Z axis (hits its
    neighbours after a few degrees)."""
    return {"lift": {"kind": "slider", "moving": "r2c3", "fixed": "r2c2", "axis": ((0, 0, 0), (0, 0, 1)),
                     "range": [0, 30], "unit": "mm", "samples": samples},
            "slide": {"kind": "slider", "moving": "r7c5", "fixed": "r7c4", "axis": ((0, 0, 0), (0, 1, 0)),
                      "range": [0, 15], "unit": "mm", "samples": samples},
            "turn": {"kind": "revolute", "moving": "r2c7", "fixed": "r2c6", "axis": ((78.5, 45.0, 5.0), (0, 0, 1)),
                     "range": [0, 90], "unit": "deg", "samples": samples}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--parts", type=int, default=100)
    ap.add_argument("--cache", help="pair cache directory (default: none)")
    ap.add_argument("--json", action="store_true", help="print the stats as JSON only")
    ap.add_argument("--motion", type=int, metavar="SAMPLES", help="time the motion gate, SAMPLES per joint")
    args = ap.parse_args(argv)
    from cadagent.gates import PairCache, relation_table

    t0 = time.perf_counter()
    asm, _ = synthetic_assembly(args.parts)
    build_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    if args.motion:
        from cadagent.gates.motion import motion_gate
        v = motion_gate(asm, motion_joints(args.motion), cache=PairCache(args.cache) if args.cache else None)
        stats = dict(v["stats"], parts=len(asm), build_s=round(build_s, 3),
                     motion_total_s=round(time.perf_counter() - t1, 3),
                     findings=[f["id"] for f in v["findings"]])
        print(json.dumps(stats) if args.json else json.dumps(stats, indent=2))
        return 0
    table = relation_table(asm, cache=PairCache(args.cache) if args.cache else None)
    stats = dict(table.stats, build_s=round(build_s, 3), relations_total_s=round(time.perf_counter() - t1, 3))
    print(json.dumps(stats) if args.json else json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
