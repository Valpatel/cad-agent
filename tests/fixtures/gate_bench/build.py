"""Gate bench: a small generic mechanism declared through the dossier registry, and the plan's seeded defects (§6).

The mechanism (millimetres, Z up, everything in assembly coordinates):

* ``base``: a 160 x 80 x 4 plate, the grounded part, with an 8 mm boss that carries the bracket;
* ``hopper``: an open box (2.4 mm walls and floor, filleted outer corners) on the base, with four
  corner posts holding heat-set ``insert_0..3``; its void is the declared cavity ``hopper_cavity``;
* ``ball``: eight loose 10 mm balls in the hopper, one part with eight instances (``ball#0..7``), free;
* ``board``: a sensor board standing in the hopper against the -Y wall;
* ``lid`` on the hopper, held by four fasteners ``screw_0..3`` (M3 x 8 envelopes) into the inserts;
* ``bracket``: an L bracket on the base boss;
* ``hinge_block``, ``pin``, ``arm`` and ``stop`` (filleted): an arm on a pin, the revolute joint
  ``I-pin-arm`` about Y, resting on the stop at 0 deg and declared to lift to 40 deg;
* ``frame``: a post and an overhead beam that the arm clears at 40 deg and would hit near 45 deg.

``build(seed=None)`` declares everything on a fresh ``cadagent.dossier.Registry`` (parts, the cavity,
the joint, the fasteners with their placed shapes and stack numbers, the assembly steps), builds it
without writing files, and returns a ``Bench``: the ``BuildResult``, ``Assembly.from_build`` of it,
and the declarations that belong in the YAML dossier rather than the build script (interfaces,
intended overlaps, ``contains``, decisions, per-part minimum walls, tool envelopes) as plain data
until the bench grows a ``dossier/`` directory.

Seeds (``SEEDS``) each inject one defect; ``tests/test_gate_bench.py`` runs them per gate.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import cadquery as cq

from cadagent import dossier
from cadagent.fasteners import insert_envelope, socket_head_envelope
from cadagent.gates import Assembly

PARAMS: Dict[str, Any] = {
    "wall": 2.4,
    "hopper": {"x": 10.0, "y": 15.0, "size": 50.0, "height": 40.0, "corner_r": 3.0},
    "post": 10.0,
    "insert": {"od": 4.0, "id": 2.5, "length": 5.0, "hole_depth": 6.0},
    "screw": {"d": 3.0, "length": 8.0, "head_d": 5.5, "head_h": 3.0, "pitch": 0.5, "min_threads": 3},
    "screw_lengths": {},
    "lid": {"t": 3.0, "hole_d": 3.4},
    "ball": {"r": 5.0, "x": [29.0, 41.0], "y": [34.0, 46.0]},
    "bracket_lift": 0.0,
    "boss": True,
    "flap_range_deg": [0.0, 40.0],
    "gusset": False,
    "thin_wall": None,
    "ball_offset": None,
    "assembly_order": ["base", "hopper", "inserts", "board", "ball", "lid", "bracket", "hinge_block",
                       "stop", "arm", "pin", "frame"],
    "drop_alternatives": False,
}

SEEDS: Dict[str, Dict[str, Any]] = {
    "ball_through_wall": {"gate": "containment", "task": "T5", "parts": ["ball#7"],
                          "what": "ball#7 pushed 5 mm into the +Y wall (2.6 mm out of the far side)",
                          "params": {"ball_offset": [7, [0.0, 16.6, 0.0]]}},
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
                          "what": "a gusset fitted on the lid before its screws are driven overhangs screw_0's head, "
                                  "blocking the hex key",
                          "params": {"gusset": True}},
    "flap_hits_frame": {"gate": "motion", "task": "T7", "parts": ["arm", "frame"],
                        "what": "the arm's stop is raised to 60 deg; the arm hits the frame beam near 45 deg",
                        "params": {"flap_range_deg": [0.0, 60.0]}},
    "thin_wall": {"gate": "wall", "task": "T8", "parts": ["hopper"],
                  "what": "the hopper's +X wall thinned from 2.4 to 0.8 mm",
                  "params": {"thin_wall": 0.8}},
    "lid_before_board": {"gate": "assembly", "task": "T9", "parts": ["board", "lid"],
                         "what": "assembly steps reordered: the lid goes on before the board goes in",
                         "params": {"assembly_order": ["base", "hopper", "inserts", "lid", "ball", "board",
                                                       "bracket", "hinge_block", "stop", "arm", "pin", "frame"]}},
    "decision_without_alternatives": {"gate": "dossier-lint", "task": "T2", "parts": ["hopper"],
                                      "what": "decision D1 loses its rejected alternatives",
                                      "params": {"drop_alternatives": True}},
}

PIVOT = (105.0, 20.0)          # arm pivot (x, z); the axis runs along Y
LIFT_AXIS = (0.0, -1.0, 0.0)   # a positive angle about this axis lifts the arm's free end
PRINTED = ("base", "hopper", "lid", "bracket", "hinge_block", "arm", "stop", "frame")


@dataclass
class Bench:
    result: Any                                  # cadagent.dossier.BuildResult
    assembly: Assembly
    declarations: Dict[str, Any]
    params: Dict[str, Any]
    seed: Optional[str] = None
    print_parts: Dict[str, float] = field(default_factory=dict)   # printed part -> declared minimum wall (mm)

    def shape(self, name: str):
        """A part or cavity in assembly coordinates (``TopoDS_Shape``)."""
        return self.assembly.shape(name)

    @property
    def cavities(self) -> Dict[str, Any]:
        return {n: c.located for n, c in self.assembly.cavities.items()}


def _box(x0, y0, z0, x1, y1, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _cyl_y(cx, cz, r, y0, y1):
    return cq.Solid.makeCylinder(r, y1 - y0, cq.Vector(cx, y0, cz), cq.Vector(0, 1, 0))


def post_centres(p):
    h, post, w = p["hopper"], p["post"], p["wall"]
    lo_x, hi_x = h["x"] + w + post / 2, h["x"] + h["size"] - w - post / 2
    lo_y, hi_y = h["y"] + w + post / 2, h["y"] + h["size"] - w - post / 2
    return [(lo_x, lo_y), (hi_x, lo_y), (lo_x, hi_y), (hi_x, hi_y)]


def _hopper(p):
    h, w, post = p["hopper"], p["wall"], p["post"]
    x0, y0, z0 = h["x"], h["y"], 4.0
    x1, y1, top = x0 + h["size"], y0 + h["size"], z0 + h["height"]
    outer = cq.Workplane().add(_box(x0, y0, z0, x1, y1, top)).edges("|Z").fillet(h["corner_r"]).val()
    shell = outer.cut(_box(x0 + w, y0 + w, z0 + w, x1 - w, y1 - w, top))
    for cx, cy in post_centres(p):
        shell = shell.fuse(_box(cx - post / 2, cy - post / 2, z0 + w, cx + post / 2, cy + post / 2, top))
        ins = p["insert"]
        shell = shell.cut(cq.Solid.makeCylinder(ins["od"] / 2, ins["hole_depth"], cq.Vector(cx, cy, top - ins["hole_depth"])))
    if p["thin_wall"] is not None:
        shell = shell.cut(_box(x1 - w + p["thin_wall"], y0 - 1, z0 - 1, x1 + 1, y1 + 1, top + 1))
    cavity = _box(x0 + w, y0 + w, z0 + w, x1 - w, y1 - w, top)
    for cx, cy in post_centres(p):
        cavity = cavity.cut(_box(cx - post / 2, cy - post / 2, z0 + w, cx + post / 2, cy + post / 2, top))
    return shell.clean(), cavity.clean(), top


def register(reg, p: Dict[str, Any]) -> None:
    """Declare the bench on registry ``reg`` for parameters ``p`` (``PARAMS`` with a seed applied)."""
    base = _box(0, 0, 0, 160, 80, 4)
    if p["boss"]:
        base = base.fuse(cq.Solid.makeCylinder(4, 3, cq.Vector(90, 20, 4))).clean()
    reg.add_part("base", base, section="frame", grounded=True)

    hopper, cavity, top = _hopper(p)
    reg.add_part("hopper", hopper, section="store")
    reg.add_cavity("hopper", "hopper_cavity", cavity)
    h, lid_t = p["hopper"], p["lid"]["t"]
    lid = cq.Workplane().add(_box(h["x"], h["y"], top, h["x"] + h["size"], h["y"] + h["size"], top + lid_t)) \
        .edges("|Z").fillet(h["corner_r"]).val()
    for cx, cy in post_centres(p):
        lid = lid.cut(cq.Solid.makeCylinder(p["lid"]["hole_d"] / 2, lid_t, cq.Vector(cx, cy, top)))
    reg.add_part("lid", lid.clean(), section="store")

    ins, sc = p["insert"], p["screw"]
    for i, (cx, cy) in enumerate(post_centres(p)):
        reg.add_part(f"insert_{i}", insert_envelope(ins["od"], ins["id"], ins["length"]), section="store",
                     place=(cx, cy, top))
        length = p["screw_lengths"].get(f"screw_{i}", sc["length"])
        reg.fastener("m3_shcs", clamps="lid", into=f"insert_{i}", name=f"screw_{i}", via=f"I-thread-{i}",
                     at=[dossier.Axis((cx, cy, top + lid_t), (0, 0, -1))], tool="hex key 2.5",
                     length_mm=length, diameter_mm=sc["d"], thread_start_mm=lid_t, thread_depth_mm=ins["length"],
                     min_engagement_mm=sc["pitch"] * sc["min_threads"],
                     shape=socket_head_envelope(sc["d"], length, sc["head_d"], sc["head_h"]))

    b, w = p["ball"], p["wall"]
    floor_z = 4.0 + w
    centres = [[x, y, floor_z + b["r"] + layer * 2 * b["r"]] for layer in (0, 1) for x in b["x"] for y in b["y"]]
    if p["ball_offset"]:
        i, d = p["ball_offset"]
        centres[i] = [v + dv for v, dv in zip(centres[i], d)]
    reg.add_part("ball", [cq.Solid.makeSphere(b["r"], cq.Vector(*c), angleDegrees1=-90) for c in centres],
                 section="store", free=True, reason="loose balls in the hopper")
    reg.add_part("board", _box(24, h["y"] + w, floor_z, 46, h["y"] + w + 1.6, floor_z + 20), section="store")

    bracket = _box(82, 15, 7, 98, 25, 10).fuse(_box(95, 15, 10, 98, 25, 30)).clean()
    reg.add_part("bracket", bracket, section="bracket", place=(0, 0, p["bracket_lift"]))

    px, pz = PIVOT
    reg.add_part("hinge_block", _box(99, 30, 4, 111, 40, 26).cut(_cyl_y(px, pz, 2.5, 30, 40)).clean(), section="arm")
    reg.add_part("pin", _cyl_y(px, pz, 2.5, 28, 46), section="arm")
    reg.add_part("arm", _box(100, 40, 14, 150, 44, 26).cut(_cyl_y(px, pz, 2.5, 40, 44)).clean(), section="arm")
    stop = cq.Workplane().add(_box(140, 38, 4, 150, 46, 14)).edges("|Z").fillet(2).val()
    reg.add_part("stop", stop, section="arm")
    reg.add_part("frame", _box(152, 36, 4, 156, 48, 60).fuse(_box(112, 36, 56, 156, 48, 60)).clean(), section="frame")
    reg.joint("I-pin-arm", "revolute", parts=("arm", "pin"), axis=((px, 0.0, pz), LIFT_AXIS),
              range_deg=tuple(p["flap_range_deg"]), intended_contacts=[("arm", "pin"), ("arm", "hinge_block"),
                                                                       ("arm", "stop")])
    if p["gusset"]:
        cx, cy = post_centres(p)[0]
        g = _box(cx + 5, cy - 4, top + lid_t, cx + 12, cy + 4, top + lid_t + 9)
        g = g.fuse(_box(cx - 5, cy - 4, top + lid_t + 6, cx + 12, cy + 4, top + lid_t + 9)).clean()
        reg.add_part("gusset", g, section="store")

    onto = {"hopper": "base", "inserts": "hopper", "board": "hopper", "ball": "hopper", "lid": "hopper",
            "bracket": "base", "hinge_block": "base", "stop": "base", "arm": "hinge_block", "pin": "hinge_block",
            "frame": "base"}
    order = 1
    for item in p["assembly_order"]:
        for fit in ([f"insert_{i}" for i in range(4)] if item == "inserts" else [item]):
            extra = {"tool": "hex key 2.5", "fasteners": [f"screw_{i}" for i in range(4)]} if item == "lid" else {}
            if item == "lid" and p["gusset"]:     # seed 6: the gusset goes on the lid before the screws are driven
                reg.assembly.step(order, fit, onto.get(item), direction="-Z")
                order += 1
                fit = "gusset"
            reg.assembly.step(order, fit, "lid" if fit == "gusset" else onto.get(item),
                              direction="-Y" if item == "pin" else "-Z", **extra)
            order += 1


def _declarations(p) -> Dict[str, Any]:
    """What the bench's YAML dossier would hold: interfaces, intended overlaps, contains, decisions, requirements,
    walls, tools."""
    interfaces = [
        {"id": "I-hopper", "parts": ["base", "hopper"], "kind": "seat"},
        {"id": "I-lid", "parts": ["hopper", "lid"], "kind": "seat"},
        {"id": "I-board", "parts": ["hopper", "board"], "kind": "seat"},
        {"id": "I-bracket", "parts": ["base", "bracket"], "kind": "seat", "datum": "boss top, Z=7"},
        {"id": "I-block", "parts": ["base", "hinge_block"], "kind": "seat"},
        {"id": "I-pin-block", "parts": ["hinge_block", "pin"], "kind": "bearing"},
        {"id": "I-pin-arm", "parts": ["pin", "arm"], "kind": "revolute"},
        {"id": "I-arm-block", "parts": ["hinge_block", "arm"], "kind": "thrust face"},
        {"id": "I-stop", "parts": ["base", "stop"], "kind": "seat"},
        {"id": "I-arm-stop", "parts": ["arm", "stop"], "kind": "rest at 0 deg"},
        {"id": "I-frame", "parts": ["base", "frame"], "kind": "seat"},
    ]
    overlaps = []
    for i in range(4):
        interfaces += [{"id": f"I-insert-{i}", "parts": ["hopper", f"insert_{i}"], "kind": "heat-set bore"},
                       {"id": f"I-seat-{i}", "parts": ["lid", f"screw_{i}"], "kind": "head seat"},
                       {"id": f"I-thread-{i}", "parts": [f"screw_{i}", f"insert_{i}"], "kind": "thread"},
                       {"id": f"I-cap-{i}", "parts": ["lid", f"insert_{i}"], "kind": "flush insert face"}]
        overlaps.append({"parts": [f"screw_{i}", f"insert_{i}"], "reason": "thread envelope: the screw's "
                         "nominal diameter overlaps the insert's minor diameter by design"})
    if p["gusset"]:
        interfaces.append({"id": "I-gusset", "parts": ["lid", "gusset"], "kind": "seat"})
    decisions = [
        {"id": "D1", "scope": "part", "part": "hopper", "decision": "Square hopper with corner posts for the lid screws",
         "why": "posts give the inserts 3 mm of wall without thickening the 2.4 mm shell",
         "alternatives": [{"option": "screw bosses outside the wall", "rejected": "widens the footprint"},
                          {"option": "snap-fit lid", "rejected": "the lid must stay on when the arm shakes the bench"}]},
        {"id": "D2", "scope": "section", "section": "arm", "decision": "Arm rests on a fixed stop at 0 deg",
         "why": "a hard stop gives a repeatable zero without a sensor",
         "alternatives": [{"option": "spring return", "rejected": "adds a part and a fatigue mode"}]},
        {"id": "D3", "scope": "section", "section": "frame", "decision": "One flat base plate carries everything",
         "why": "a single grounded part gives every subassembly one datum",
         "alternatives": [{"option": "separate feet per subassembly", "rejected": "no common datum"}]},
        {"id": "D4", "scope": "section", "section": "bracket", "decision": "L bracket seated on a base boss",
         "why": "the boss sets the bracket height without shims",
         "alternatives": [{"option": "bracket screwed to the plate", "rejected": "adds two fasteners"}]},
    ]
    requirements = [
        {"id": "R1", "text": "Holds eight balls", "sections": ["store"], "checks": ["gate:containment"]},
        {"id": "R2", "text": "The arm lifts 40 deg without hitting anything", "sections": ["arm"],
         "checks": ["gate:motion"]},
        {"id": "R3", "text": "Every part is held", "sections": ["frame", "bracket"], "checks": ["gate:connectivity"]},
    ]
    if p["drop_alternatives"]:
        decisions[0]["alternatives"] = []
    return {"interfaces": interfaces, "intended_overlaps": overlaps,
            "contains": [{"container": "hopper", "cavity": "hopper_cavity", "what": "ball", "count": 8, "free": True}],
            "decisions": decisions, "requirements": requirements, "wall_mm": {"default": p["wall"]},
            "tools": {"hex key 2.5": {"envelope_d": 6.0, "length": 60.0}}}


def build(seed: Optional[str] = None, params: Optional[Dict[str, Any]] = None) -> Bench:
    """Build the clean bench, or the bench with one seeded defect from ``SEEDS``."""
    p = copy.deepcopy(PARAMS)
    if seed is not None:
        if seed not in SEEDS:
            raise KeyError(f"unknown seed {seed!r}; seeds: {sorted(SEEDS)}")
        p.update(copy.deepcopy(SEEDS[seed]["params"]))
    p.update(copy.deepcopy(params or {}))
    with dossier.use_registry() as reg:
        register(reg, p)
        result = reg.build({}, write=False)
    prints = {n: p["wall"] for n in PRINTED + (("gusset",) if p["gusset"] else ())}
    return Bench(result, Assembly.from_build(result), _declarations(p), p, seed, prints)


def arm_pose(bench: Bench, degrees: float) -> Assembly:
    """The bench with the arm body rotated ``degrees`` about the pivot (positive lifts its free end)."""
    px, pz = PIVOT
    rot = cq.Location(cq.Vector(px, 0, pz)) * cq.Location(cq.Vector(0, 0, 0), cq.Vector(*LIFT_AXIS), degrees) \
        * cq.Location(cq.Vector(-px, 0, -pz))
    return bench.assembly.posed(bench.assembly["arm"].body, rot)


def arm_frame_contact_deg() -> float:
    """Angle at which the arm's top far corner reaches the frame beam (analytic, for the tests)."""
    r, h = 45.0, 6.0
    beam = 56.0 - PIVOT[1]
    return math.degrees(math.asin(beam / math.hypot(r, h)) - math.atan2(h, r))
