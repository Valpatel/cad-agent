"""Gate bench: a small generic mechanism with declared intent, and the plan's seeded defects (§6).

The mechanism (millimetres, Z up, everything placed in assembly coordinates):

* ``base``: a 160 x 80 x 4 plate, the grounded part, with a 8 mm boss that carries the bracket;
* ``hopper``: an open box (2.4 mm walls and floor) on the base, with four corner posts holding
  heat-set ``insert_0..3``; its void is declared as the cavity ``hopper_cavity``;
* ``ball_0..7``: loose 10 mm balls inside the hopper (declared ``contains``, free);
* ``board``: a sensor board standing in the hopper against the -Y wall;
* ``lid`` on the hopper, held by ``screw_0..3`` (M3 x 8 envelopes) into the inserts;
* ``bracket``: an L bracket on the base boss;
* ``hinge_block``, ``pin``, ``arm`` and ``stop``: an arm on a pin (revolute joint about Y),
  resting on the stop at 0 deg and declared to lift to 40 deg;
* ``frame``: a post and an overhead beam that the arm clears at 40 deg and would hit near 45 deg.

``build(seed=None)`` returns a ``Bench``: the ``Assembly`` (``cadagent.gates``), the cavity solids,
the declarations as plain data (interfaces, intended overlaps, free and grounded parts, contains,
joints, fasteners, assembly steps, decisions, per-part minimum walls), and the parameters.

Registry hook: until the dossier registry (plan T13) exists, ``dossier_items(bench)`` returns
the same declarations in one dict, the plan's §3.4 ``dossier_items()`` migration path, so the
registry can adopt this fixture by importing that function instead of the bench changing shape.

Seeds (``SEEDS``) each inject one defect; ``tests/test_gate_bench.py`` runs them per gate.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import cadquery as cq

from cadagent.fasteners import insert_envelope, socket_head_envelope
from cadagent.gates import Assembly

PARAMS: Dict[str, Any] = {
    "wall": 2.4,
    "hopper": {"x": 10.0, "y": 15.0, "size": 50.0, "height": 40.0},
    "post": 10.0,
    "insert": {"od": 4.0, "id": 2.5, "length": 5.0, "hole_depth": 6.0},
    "screw": {"d": 3.0, "length": 8.0, "head_d": 5.5, "head_h": 3.0, "pitch": 0.5, "min_threads": 3},
    "lid": {"t": 3.0, "hole_d": 3.4},
    "ball": {"r": 5.0, "x": [29.0, 41.0], "y": [34.0, 46.0]},
    "bracket_lift": 0.0,
    "boss": True,
    "flap_range_deg": [0.0, 40.0],
    "gusset": False,
    "thin_wall": None,
    "ball_offset": None,
    "assembly_order": ["base", "hopper", "inserts", "board", "balls", "lid", "screws", "bracket", "hinge_block",
                       "stop", "arm", "pin", "frame"],
    "drop_alternatives": False,
}

SEEDS: Dict[str, Dict[str, Any]] = {
    "ball_through_wall": {"gate": "containment", "task": "T5", "parts": ["ball_7"],
                          "what": "ball_7 pushed 5 mm into the +Y wall (2.6 mm out of the far side)",
                          "params": {"ball_offset": ["ball_7", [0.0, 16.6, 0.0]]}},
    "bracket_floats": {"gate": "connectivity", "task": "T4", "parts": ["bracket"],
                       "what": "the base boss that carries the bracket is deleted, so the bracket floats",
                       "params": {"boss": False}},
    "bracket_hovers": {"gate": "connectivity", "task": "T4", "parts": ["bracket"],
                       "what": "the bracket is lifted 0.5 mm off the boss (interface I-bracket unrealised)",
                       "params": {"bracket_lift": 0.5}},
    "screw_too_long": {"gate": "fasteners", "task": "T6", "parts": ["screw_0"],
                       "what": "screw_0 lengthened 4 mm: its tip runs 3 mm past the insert hole into the post",
                       "params": {"screw_lengths": {"screw_0": 12.0}}},
    "screw_too_short": {"gate": "fasteners", "task": "T6", "parts": ["screw_1"],
                        "what": "screw_1 shortened to 4 mm: 1.0 mm of thread in the insert, under 3 threads",
                        "params": {"screw_lengths": {"screw_1": 4.0}}},
    "gusset_over_screw": {"gate": "fasteners", "task": "T6", "parts": ["screw_0", "gusset"],
                          "what": "a gusset on the lid overhangs screw_0's head, blocking the hex key",
                          "params": {"gusset": True}},
    "flap_hits_frame": {"gate": "motion", "task": "T7", "parts": ["arm", "frame"],
                        "what": "the arm's stop is raised to 60 deg; the arm hits the frame beam near 45 deg",
                        "params": {"flap_range_deg": [0.0, 60.0]}},
    "thin_wall": {"gate": "wall", "task": "T8", "parts": ["hopper"],
                  "what": "the hopper's +X wall thinned from 2.4 to 0.8 mm",
                  "params": {"thin_wall": 0.8}},
    "lid_before_board": {"gate": "assembly", "task": "T9", "parts": ["board", "lid"],
                         "what": "assembly steps reordered: the lid goes on before the board goes in",
                         "params": {"assembly_order": ["base", "hopper", "inserts", "lid", "balls", "board", "screws",
                                                       "bracket", "hinge_block", "stop", "arm", "pin", "frame"]}},
    "decision_without_alternatives": {"gate": "dossier-lint", "task": "T2", "parts": ["hopper"],
                                      "what": "decision D1 loses its rejected alternatives",
                                      "params": {"drop_alternatives": True}},
}

PIVOT = (105.0, 20.0)          # arm pivot (x, z); the axis runs along Y
LIFT_AXIS = (0.0, -1.0, 0.0)   # a positive angle about this axis lifts the arm's free end


@dataclass
class Bench:
    assembly: Assembly
    cavities: Dict[str, Any]
    declarations: Dict[str, Any]
    params: Dict[str, Any]
    seed: Optional[str] = None
    print_parts: Dict[str, float] = field(default_factory=dict)   # printed part -> declared minimum wall (mm)

    def shape(self, name: str):
        return self.assembly.shape(name)


def _box(x0, y0, z0, x1, y1, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _cyl_y(cx, cz, r, y0, y1):
    return cq.Solid.makeCylinder(r, y1 - y0, cq.Vector(cx, y0, cz), cq.Vector(0, 1, 0))


def _post_centres(p):
    h, post, w = p["hopper"], p["post"], p["wall"]
    lo_x, hi_x = h["x"] + w + post / 2, h["x"] + h["size"] - w - post / 2
    lo_y, hi_y = h["y"] + w + post / 2, h["y"] + h["size"] - w - post / 2
    return [(lo_x, lo_y), (hi_x, lo_y), (lo_x, hi_y), (hi_x, hi_y)]


def _hopper(p):
    h, w, post = p["hopper"], p["wall"], p["post"]
    x0, y0, z0 = h["x"], h["y"], 4.0
    x1, y1, top = x0 + h["size"], y0 + h["size"], z0 + h["height"]
    shell = _box(x0, y0, z0, x1, y1, top).cut(_box(x0 + w, y0 + w, z0 + w, x1 - w, y1 - w, top))
    for cx, cy in _post_centres(p):
        shell = shell.fuse(_box(cx - post / 2, cy - post / 2, z0 + w, cx + post / 2, cy + post / 2, top))
        ins = p["insert"]
        shell = shell.cut(cq.Solid.makeCylinder(ins["od"] / 2, ins["hole_depth"], cq.Vector(cx, cy, top - ins["hole_depth"])))
    if p["thin_wall"] is not None:
        shell = shell.cut(_box(x1 - w + p["thin_wall"], y0 - 1, z0 - 1, x1 + 1, y1 + 1, top + 1))
    cavity = _box(x0 + w, y0 + w, z0 + w, x1 - w, y1 - w, top)
    for cx, cy in _post_centres(p):
        cavity = cavity.cut(_box(cx - post / 2, cy - post / 2, z0 + w, cx + post / 2, cy + post / 2, top))
    return shell.clean(), cavity.clean(), top


def build(seed: Optional[str] = None, params: Optional[Dict[str, Any]] = None) -> Bench:
    """Build the clean bench, or the bench with one seeded defect from ``SEEDS``."""
    p = copy.deepcopy(PARAMS)
    if seed is not None:
        if seed not in SEEDS:
            raise KeyError(f"unknown seed {seed!r}; seeds: {sorted(SEEDS)}")
        p.update(copy.deepcopy(SEEDS[seed]["params"]))
    p.update(copy.deepcopy(params or {}))
    asm = Assembly()

    base = _box(0, 0, 0, 160, 80, 4)
    if p["boss"]:
        base = base.fuse(cq.Solid.makeCylinder(4, 3, cq.Vector(90, 20, 4))).clean()
    asm.add("base", base, group="frame")

    hopper, cavity, top = _hopper(p)
    asm.add("hopper", hopper, group="store")
    lid_t = p["lid"]["t"]
    lid = _box(p["hopper"]["x"], p["hopper"]["y"], top, p["hopper"]["x"] + p["hopper"]["size"],
               p["hopper"]["y"] + p["hopper"]["size"], top + lid_t)
    for cx, cy in _post_centres(p):
        lid = lid.cut(cq.Solid.makeCylinder(p["lid"]["hole_d"] / 2, lid_t, cq.Vector(cx, cy, top)))
    asm.add("lid", lid.clean(), group="store")

    ins, sc = p["insert"], p["screw"]
    lengths = p.get("screw_lengths", {})
    for i, (cx, cy) in enumerate(_post_centres(p)):
        asm.add(f"insert_{i}", insert_envelope(ins["od"], ins["id"], ins["length"]), (cx, cy, top), group="store")
        length = lengths.get(f"screw_{i}", sc["length"])
        asm.add(f"screw_{i}", socket_head_envelope(sc["d"], length, sc["head_d"], sc["head_h"]),
                (cx, cy, top + lid_t), group="store")

    b = p["ball"]
    floor_z = 4.0 + p["wall"]
    centres = [(x, y, floor_z + b["r"] + layer * 2 * b["r"]) for layer in (0, 1) for x in b["x"] for y in b["y"]]
    for i, c in enumerate(centres):
        if p["ball_offset"] and p["ball_offset"][0] == f"ball_{i}":
            c = tuple(v + d for v, d in zip(c, p["ball_offset"][1]))
        asm.add(f"ball_{i}", cq.Solid.makeSphere(b["r"], cq.Vector(*c), angleDegrees1=-90), group="store")

    w = p["wall"]
    asm.add("board", _box(24, p["hopper"]["y"] + w, floor_z, 46, p["hopper"]["y"] + w + 1.6, floor_z + 20),
            group="store")

    lift = p["bracket_lift"]
    bracket = _box(82, 15, 7, 98, 25, 10).fuse(_box(95, 15, 10, 98, 25, 30)).clean()
    asm.add("bracket", bracket, (0, 0, lift), group="bracket")

    px, pz = PIVOT
    block = _box(99, 30, 4, 111, 40, 26).cut(_cyl_y(px, pz, 2.5, 30, 40))
    asm.add("hinge_block", block.clean(), group="arm")
    asm.add("pin", _cyl_y(px, pz, 2.5, 28, 46), group="arm")
    arm = _box(100, 40, 14, 150, 44, 26).cut(_cyl_y(px, pz, 2.5, 40, 44))
    asm.add("arm", arm.clean(), body="arm", group="arm")
    asm.add("stop", _box(140, 38, 4, 150, 46, 14), group="arm")
    frame = _box(152, 36, 4, 156, 48, 60).fuse(_box(112, 36, 56, 156, 48, 60)).clean()
    asm.add("frame", frame, group="frame")

    if p["gusset"]:
        cx, cy = _post_centres(p)[0]
        g = _box(cx + 5, cy - 4, top + lid_t, cx + 12, cy + 4, top + lid_t + 9)
        g = g.fuse(_box(cx - 5, cy - 4, top + lid_t + 6, cx + 12, cy + 4, top + lid_t + 9)).clean()
        asm.add("gusset", g, group="store")

    decl = _declarations(p, top, lid_t)
    prints = {n: w for n in ("base", "hopper", "lid", "bracket", "hinge_block", "arm", "stop", "frame")}
    if p["gusset"]:
        prints["gusset"] = w
    return Bench(asm, {"hopper_cavity": cavity}, decl, p, seed, prints)


def _declarations(p, top, lid_t) -> Dict[str, Any]:
    sc, ins = p["screw"], p["insert"]
    lengths = p.get("screw_lengths", {})
    interfaces = [
        {"id": "I-hopper", "parts": ["base", "hopper"], "kind": "seat"},
        {"id": "I-lid", "parts": ["hopper", "lid"], "kind": "seat"},
        {"id": "I-board", "parts": ["hopper", "board"], "kind": "seat"},
        {"id": "I-bracket", "parts": ["base", "bracket"], "kind": "seat", "datum": "boss top, Z=7"},
        {"id": "I-block", "parts": ["base", "hinge_block"], "kind": "seat"},
        {"id": "I-pin-block", "parts": ["hinge_block", "pin"], "kind": "bearing"},
        {"id": "I-pin-arm", "parts": ["pin", "arm"], "kind": "revolute", "joint": "J-arm"},
        {"id": "I-arm-block", "parts": ["hinge_block", "arm"], "kind": "thrust face"},
        {"id": "I-stop", "parts": ["base", "stop"], "kind": "seat"},
        {"id": "I-arm-stop", "parts": ["arm", "stop"], "kind": "rest at 0 deg"},
        {"id": "I-frame", "parts": ["base", "frame"], "kind": "seat"},
    ]
    fasteners, overlaps = [], []
    for i in range(4):
        interfaces += [{"id": f"I-insert-{i}", "parts": ["hopper", f"insert_{i}"], "kind": "heat-set bore"},
                       {"id": f"I-seat-{i}", "parts": ["lid", f"screw_{i}"], "kind": "head seat"},
                       {"id": f"I-thread-{i}", "parts": [f"screw_{i}", f"insert_{i}"], "kind": "thread"},
                       {"id": f"I-cap-{i}", "parts": ["lid", f"insert_{i}"], "kind": "flush insert face"}]
        overlaps.append({"parts": [f"screw_{i}", f"insert_{i}"], "reason": "thread envelope: the screw's "
                         "nominal diameter overlaps the insert's minor diameter by design"})
        fasteners.append({"id": f"F{i}", "screw": f"screw_{i}", "clamps": "lid", "into": f"insert_{i}",
                          "axis": [0, 0, -1], "head_seat_z": top + lid_t, "length": lengths.get(f"screw_{i}", sc["length"]),
                          "thread_top_z": top, "thread_length": ins["length"], "hole_bottom_z": top - ins["hole_depth"],
                          "min_engagement_mm": sc["pitch"] * sc["min_threads"],
                          "tool": {"kind": "hex key", "size": 2.5, "envelope_d": 6.0, "length": 60.0}})
    if p["gusset"]:
        interfaces.append({"id": "I-gusset", "parts": ["lid", "gusset"], "kind": "seat"})
    steps_parts = {"base": ["base"], "hopper": ["hopper"], "inserts": [f"insert_{i}" for i in range(4)],
                   "board": ["board"], "balls": [f"ball_{i}" for i in range(8)], "lid": ["lid"],
                   "screws": [f"screw_{i}" for i in range(4)], "bracket": ["bracket"], "hinge_block": ["hinge_block"],
                   "stop": ["stop"], "arm": ["arm"], "pin": ["pin"], "frame": ["frame"]}
    direction = {"pin": "-Y"}
    steps = [{"step": n + 1, "fit": steps_parts[k], "direction": direction.get(k, "-Z"),
              **({"tool": "hex key 2.5", "fasteners": [f"F{i}" for i in range(4)]} if k == "screws" else {})}
             for n, k in enumerate(p["assembly_order"])]
    if p["gusset"]:
        steps.insert(6, {"step": 6.5, "fit": ["gusset"], "direction": "-Z"})
    decisions = [
        {"id": "D1", "scope": "part", "part": "hopper", "decision": "Square hopper with corner posts for the lid screws",
         "why": "posts give the inserts 3 mm of wall without thickening the 2.4 mm shell",
         "alternatives": [{"option": "screw bosses outside the wall", "rejected": "widens the footprint"},
                          {"option": "snap-fit lid", "rejected": "the lid must stay on when the arm shakes the bench"}]},
        {"id": "D2", "scope": "section", "section": "arm", "decision": "Arm rests on a fixed stop at 0 deg",
         "why": "a hard stop gives a repeatable zero without a sensor",
         "alternatives": [{"option": "spring return", "rejected": "adds a part and a fatigue mode"}]},
    ]
    if p["drop_alternatives"]:
        decisions[0]["alternatives"] = []
    lo, hi = p["flap_range_deg"]
    return {
        "grounded": ["base"],
        "interfaces": interfaces,
        "intended_overlaps": overlaps,
        "free_parts": [f"ball_{i}" for i in range(8)],
        "contains": [{"container": "hopper", "cavity": "hopper_cavity", "what": [f"ball_{i}" for i in range(8)],
                      "count": 8, "free": True}],
        "joints": [{"id": "J-arm", "kind": "revolute", "body": "arm", "parts": ["arm", "pin"],
                    "axis_point": [PIVOT[0], 0.0, PIVOT[1]], "axis_dir": list(LIFT_AXIS), "range_deg": [lo, hi],
                    "intended_contacts": [["arm", "pin"], ["arm", "hinge_block"], ["arm", "stop"]]}],
        "fasteners": fasteners,
        "assembly": steps,
        "decisions": decisions,
        "wall_mm": {"default": p["wall"]},
    }


def arm_pose(bench: Bench, degrees: float) -> Assembly:
    """The bench with the arm body rotated ``degrees`` about the pivot (positive lifts its free end)."""
    px, pz = PIVOT
    rot = cq.Location(cq.Vector(px, 0, pz)) * cq.Location(cq.Vector(0, 0, 0), cq.Vector(*LIFT_AXIS), degrees) \
        * cq.Location(cq.Vector(-px, 0, -pz))
    return bench.assembly.posed("arm", rot)


def dossier_items(bench: Bench) -> Dict[str, Any]:
    """The registry hook (plan §3.4): every declaration plus the shapes, as one plain dict."""
    return {"parts": {n: bench.assembly[n].shape for n in bench.assembly},
            "cavities": dict(bench.cavities),
            "print_parts": dict(bench.print_parts),
            **copy.deepcopy(bench.declarations)}


def arm_end_clearance_deg(bench: Bench) -> float:
    """Angle at which the arm's top far corner reaches the frame beam (analytic, for the tests)."""
    r, h = 45.0, 6.0
    beam = 56.0 - PIVOT[1]
    # solve r sin(t) + h cos(t) = beam
    return math.degrees(math.asin(beam / math.hypot(r, h)) - math.atan2(h, r))
