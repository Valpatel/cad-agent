"""Connectivity and floating-parts gate (plan §4.2, T4).

The analysis is pure Python on given relations, so most rules are tested in core CI with hand-made
``Relation`` rows; the plan's geometric tests run on real solids when cadquery is installed.
"""

from __future__ import annotations

import json

import pytest

from cadagent.gates import Relation, Tolerances, verdict
from cadagent.gates.connectivity import (ASSUMPTIONS, Declarations, Node, analyse, connectivity_gate, owner, to_dot,
                                         write_dot)

try:
    import cadquery as cq
except ImportError:  # core CI: the pure analysis still runs
    cq = None
needs_cad = pytest.mark.skipif(cq is None, reason="needs cadquery (the cad extra)")


# ----------------------------------------------------------------------------- pure analysis

def touch(a, b, area=10.0):
    return Relation(a, b, "touching", gap_mm=0.0, contact_area_mm2=area,
                    witness={"point_a": [0, 0, 0], "point_b": [0, 0, 0]})


def apart(a, b, gap):
    return Relation(a, b, "apart", gap_mm=gap, witness={"point_a": [0, 0, gap], "point_b": [0, 0, 0]})


def run(nodes, rels, **decl):
    nodes = {n.key: n for n in (x if isinstance(x, Node) else Node(x) for x in nodes)}
    an = analyse(nodes, rels, Declarations(**decl))
    return verdict("connectivity", an.checks, assumptions=ASSUMPTIONS, exclusions=an.exclusions, extra=an.extra)


FRAME = ["base", "post", "beam"]
FRAME_RELS = [touch("base", "post"), touch("post", "beam")]
FRAME_IFACES = [{"id": "I1", "between": ["base", "post"]}, {"id": "I2", "between": ["post", "beam"]}]


def failing(v):
    return {f["id"]: f for f in v["findings"] if f["status"] == "fail"}


def test_owner_strips_only_a_numeric_instance_suffix():
    assert owner("ball#3") == "ball" and owner("ball") == "ball" and owner("a#b") == "a#b"
    assert owner("m3:lid-base#0") == "m3:lid-base"


def test_a_frame_of_touching_parts_passes_with_no_finding():
    v = run(FRAME, FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES)
    assert v["pass"] and v["findings"] == [], v["findings"]
    assert {c["id"] for c in v["checks"]} == {"ground", "connect:static", "interface:I1", "interface:I2"}


def test_a_floating_part_fails_with_its_nearest_neighbour_and_gap():
    v = run(FRAME + ["box"], FRAME_RELS + [apart("box", "beam", 3.0), apart("box", "post", 7.0)],
            grounded=["base"], interfaces=FRAME_IFACES)
    f = failing(v)["connect:static"]
    assert f["parts"] == ["box"]
    (isl,) = v["floating"]
    assert isl["parts"] == ["box"] and isl["nearest"]["neighbour"] == "beam" and isl["nearest"]["gap_mm"] == 3.0
    assert isl["nearest"]["neighbour_anchored"] is True
    assert "nearest beam at 3.000 mm" in f["message"]


def test_marking_the_floating_part_free_passes_and_records_the_reason():
    v = run(FRAME + ["box"], FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES, free={"box": "loose spare"})
    assert v["pass"] and v["findings"] == []
    assert v["exclusions"] == [{"parts": ["box"], "reason": "loose spare", "kind": "allowed free"}]


def test_a_free_part_needs_a_reason():
    v = run(FRAME + ["box"], FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES, free={"box": ""})
    assert set(failing(v)) == {"free:box", "connect:static"}
    stale = run(FRAME, FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES, free={"ghost": "gone"})
    assert stale["pass"] and stale["findings"][0]["id"] == "free:ghost" and stale["status"] == "warn"


def test_an_island_of_two_touching_parts_is_one_finding():
    v = run(FRAME + ["a", "b"], FRAME_RELS + [touch("a", "b"), apart("b", "beam", 0.4)], grounded=["base"],
            interfaces=FRAME_IFACES + [{"id": "Iab", "between": ["a", "b"]}])
    (isl,) = v["floating"]
    assert isl["parts"] == ["a", "b"] and isl["nearest"]["part"] == "b" and isl["nearest"]["gap_mm"] == 0.4


def test_no_grounded_part_fails():
    v = run(FRAME, FRAME_RELS, interfaces=FRAME_IFACES)
    assert "ground" in failing(v) and "connect:static" not in {c["id"] for c in v["checks"]}
    v = run(FRAME, FRAME_RELS, grounded=["nowhere"], interfaces=FRAME_IFACES)
    assert "not in the assembly" in failing(v)["ground"]["message"]


def test_a_declared_interface_with_a_gap_fails_until_a_clearance_covers_it():
    rels = [touch("base", "post"), apart("post", "beam", 2.0), touch("base", "beam")]
    ifaces = [{"id": "I1", "between": ["base", "post"]}, {"id": "I2", "between": ["post", "beam"]},
              {"id": "I3", "between": ["base", "beam"]}]
    v = run(FRAME, rels, grounded=["base"], interfaces=ifaces)
    f = failing(v)["interface:I2"]
    assert f["parts"] == ["beam", "post"] and "apart by 2.000 mm" in f["message"]
    assert v["unrealised"][0]["id"] == "I2" and v["unrealised"][0]["gap_mm"] == 2.0
    ifaces[1]["clearance"] = 2.5
    ok = run(FRAME, rels, grounded=["base"], interfaces=ifaces)
    assert ok["pass"] and ok["findings"] == [], ok["findings"]
    ifaces[1]["clearance"] = 1.5
    assert "over the declared clearance 1.5 mm" in failing(run(FRAME, rels, grounded=["base"],
                                                               interfaces=ifaces))["interface:I2"]["message"]


def test_a_gap_interface_without_a_clearance_fails():
    v = run(FRAME, FRAME_RELS + [apart("base", "beam", 0.3)], grounded=["base"],
            interfaces=FRAME_IFACES + [{"id": "G", "between": ["base", "beam"], "kind": "gap"}])
    assert "needs a declared clearance" in failing(v)["interface:G"]["message"]


def test_a_revolute_joint_links_a_part_that_touches_nothing():
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    v = run(FRAME + ["arm"], FRAME_RELS + [apart("arm", "post", 0.2)], grounded=["base"], joints=joints,
            interfaces=FRAME_IFACES + [{"id": "J", "between": ["arm", "post"], "kind": "revolute"}])
    assert v["pass"] and v["findings"] == [], v["findings"]
    joint = next(c for c in v["checks"] if c["id"] == "joint:J")
    assert "arm (body arm) hangs on post" in joint["message"] and "gap 0.200 mm" in joint["message"]
    groups = {g["group"]: g for g in v["graph"]["groups"]}
    assert groups["arm"]["grounded"] and groups["arm"]["via_joint"] == "J"
    # without the joint the arm floats
    lone = run(FRAME + ["arm"], FRAME_RELS + [apart("arm", "post", 0.2)], grounded=["base"], interfaces=FRAME_IFACES)
    assert failing(lone)["connect:static"]["parts"] == ["arm"]


def test_a_mechanism_interface_needs_a_registered_joint():
    v = run(FRAME, FRAME_RELS, grounded=["base"],
            interfaces=FRAME_IFACES + [{"id": "J", "between": ["post", "beam"], "kind": "revolute"}])
    assert "has no registered joint" in failing(v)["interface:J"]["message"]


def test_a_joint_clearance_limits_the_joint_gap():
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    v = run(FRAME + ["arm"], FRAME_RELS + [apart("arm", "post", 0.6)], grounded=["base"], joints=joints,
            interfaces=FRAME_IFACES + [{"id": "J", "between": ["arm", "post"], "kind": "revolute",
                                        "clearance": 0.2}])
    assert "over the declared clearance 0.2 mm" in failing(v)["joint:J"]["message"]


def test_a_moving_body_hanging_on_a_floating_part_is_not_grounded():
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "pin"}}
    v = run(FRAME + ["pin", "arm"], FRAME_RELS + [apart("pin", "post", 1.5), touch("arm", "pin")],
            grounded=["base"], joints=joints, interfaces=FRAME_IFACES)
    f = failing(v)
    assert f["connect:static"]["parts"] == ["pin"] and "does not reach ground" in f["joint:J"]["message"]
    assert f["connect:static"]["evidence"]["islands"][0]["nearest"]["gap_mm"] == 1.5


def test_parts_of_a_moving_body_must_reach_its_joint_part():
    nodes = FRAME + [Node("arm", body="arm"), Node("cap", body="arm"), Node("tip", body="arm")]
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    rels = FRAME_RELS + [touch("arm", "post"), touch("arm", "cap"), apart("tip", "beam", 0.0001), touch("tip", "beam")]
    v = run(nodes, rels, grounded=["base"], joints=joints, interfaces=FRAME_IFACES + [
        {"id": "c", "between": ["arm", "cap"]}, {"id": "t", "between": ["tip", "beam"]}])
    f = failing(v)["connect:body:arm"]
    assert f["parts"] == ["tip"] and "touches only beam in another body" in f["message"]


def test_a_static_part_held_only_by_a_moving_body_floats():
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    v = run(FRAME + ["arm", "cap"], FRAME_RELS + [touch("arm", "post"), touch("arm", "cap")], grounded=["base"],
            joints=joints, interfaces=FRAME_IFACES + [{"id": "c", "between": ["arm", "cap"]}])
    f = failing(v)["connect:static"]
    assert f["parts"] == ["cap"] and "touches only arm" in f["message"]
    # a fixed joint to the arm with the body label fixes it
    nodes = FRAME + [Node("arm", body="arm"), Node("cap", body="arm")]
    joints["F"] = {"kind": "fixed", "moving": "cap", "fixed": "arm"}
    ok = run(nodes, FRAME_RELS + [touch("arm", "post")], grounded=["base"], joints=joints, interfaces=FRAME_IFACES)
    assert ok["pass"] and ok["findings"] == [], ok["findings"]
    # a fixed joint across bodies is a labelling error
    bad = run(FRAME + [Node("arm", body="arm"), "cap"], FRAME_RELS + [touch("arm", "post")], grounded=["base"],
              joints=joints, interfaces=FRAME_IFACES)
    assert "labelled as different bodies" in failing(bad)["joint:F"]["message"]


def test_an_undeclared_contact_warns_and_fails_when_strict():
    rels = FRAME_RELS + [touch("base", "beam", area=4.0)]
    v = run(FRAME, rels, grounded=["base"], interfaces=FRAME_IFACES)
    assert v["pass"] and v["status"] == "warn"
    (w,) = v["findings"]
    assert w["id"] == "contact:base|beam" and w["parts"] == ["base", "beam"] and v["undeclared_contacts"][0]["parts"]
    strict = run(FRAME, rels, grounded=["base"], interfaces=FRAME_IFACES, strict_interfaces=True)
    assert not strict["pass"] and "contact:base|beam" in failing(strict)


def test_contacts_declared_by_joints_fasteners_contains_overlaps_and_free_parts_are_not_reported():
    nodes = FRAME + ["arm", "lid", "screw", "ball#0", "ball#1", "nut"]
    rels = FRAME_RELS + [touch("arm", "post"), touch("arm", "base"), touch("lid", "beam"), touch("screw", "lid"),
                         touch("screw", "beam"), touch("ball#0", "beam"), touch("ball#0", "ball#1"),
                         touch("ball#1", "beam"), touch("nut", "base"), touch("nut", "ball#1")]
    v = run(nodes, rels, grounded=["base"], interfaces=FRAME_IFACES,
            joints={"J": {"kind": "revolute", "moving": "arm", "fixed": "post",
                          "intended_contacts": [["arm", "base"]]}},
            fasteners={"screw": {"clamps": "lid", "into": "beam"}},
            contains=[{"what": "ball", "container": "beam", "cavity": "c"}],
            intended_overlaps=[{"parts": ["nut", "base"], "reason": "press fit"}], free={"ball": "loose"})
    assert v["pass"] and v["findings"] == [], v["findings"]
    edges = {(e["a"], e["b"]): e for e in v["graph"]["edges"]}
    assert edges[("ball#1", "nut")]["declared_by"] == ["free part"]
    assert "fastener:screw" in edges[("beam", "lid")]["declared_by"]


def test_a_fastener_without_a_solid_joins_its_parts_on_its_declaration():
    v = run(FRAME + ["lid"], FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES,
            fasteners={"m3": {"clamps": "lid", "into": "beam"}})
    assert v["pass"] and v["findings"] == [], v["findings"]
    c = next(c for c in v["checks"] if c["id"] == "fastener:m3")
    assert "not measured" in c["message"]
    e = next(e for e in v["graph"]["edges"] if e["kind"] == "fastener")
    assert e["measured"] is False and e["rigid"]


def test_a_fastener_solid_must_touch_what_it_clamps_and_threads_into():
    v = run(FRAME + ["lid", "screw"], FRAME_RELS + [touch("lid", "beam"), touch("screw", "lid"),
                                                    apart("screw", "beam", 0.8)],
            grounded=["base"], interfaces=FRAME_IFACES + [{"id": "L", "between": ["lid", "beam"]}],
            fasteners={"screw": {"clamps": "lid", "into": "beam"}})
    f = failing(v)["fastener:screw"]
    assert "screw does not touch what it threads into (nearest beam at 0.800 mm)" in f["message"]


def test_contained_items_are_held_by_their_container_whether_or_not_they_touch():
    nodes = {k: Node(k) for k in FRAME + ["ball"]}
    decl = Declarations(grounded=["base"], interfaces=FRAME_IFACES, contains=[{"what": "ball", "container": "beam",
                                                                              "cavity": "beam_void"}])
    inside = Relation("ball", "beam_void", "contains", contained="a_in_b", wall_mm=1.0)
    an = analyse(nodes, FRAME_RELS, decl, contained=[("ball", "beam", "beam_void", inside)])
    assert not [c for c in an.checks if c.status != "pass"]
    an = analyse(nodes, FRAME_RELS, decl)
    assert [c.id for c in an.checks if c.status == "fail"] == ["connect:static"]


def test_an_unknown_relation_fails():
    rels = FRAME_RELS + [Relation("base", "beam", "unknown", error="volumes disagree")]
    v = run(FRAME, rels, grounded=["base"], interfaces=FRAME_IFACES)
    assert "volumes disagree" in failing(v)["relation:base|beam"]["message"]


def test_interfaces_between_sections_and_instances():
    nodes = [Node("base", section="S1"), Node("post", section="S1"), Node("ball#0", section="S2"),
             Node("ball#1", section="S2")]
    rels = [touch("base", "post"), touch("ball#1", "post"), touch("ball#0", "ball#1")]
    v = run(nodes, rels, grounded=["base"], interfaces=[{"id": "I", "parts": ["S1", "S2"]},
                                                        {"id": "P", "between": ["base", "post"]},
                                                        {"id": "B", "between": ["ball", "post"]},
                                                        {"id": "E", "between": ["S1", "S2"], "kind": "electrical"}],
            free={"ball": "loose"})
    assert v["pass"] and v["findings"] == [], v["findings"]
    assert "1 of 2 instance pairs" in next(c for c in v["checks"] if c["id"] == "interface:B")["message"]
    assert "interface:E" not in {c["id"] for c in v["checks"]}


def test_the_graph_and_dot_are_deterministic(tmp_path):
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    args = (FRAME + ["arm", "box"], FRAME_RELS + [touch("base", "beam"), apart("box", "beam", 3.0)])
    kw = dict(grounded=["base"], joints=joints, interfaces=FRAME_IFACES + [{"id": "X", "between": ["box", "beam"]}])
    v1, v2 = run(*args, **kw), run(*args, **kw)
    assert json.dumps(v1, sort_keys=True) == json.dumps(v2, sort_keys=True)
    dot = to_dot(v1)
    assert dot == to_dot(v1["graph"])
    assert dot.startswith("graph connectivity {") and '"base" [peripheries=2]' in dot
    assert '"box" [color=red, fontcolor=red]' in dot and 'label="J revolute"' in dot
    assert 'label="undeclared"' in dot and 'label="X unrealised 3.000 mm"' in dot
    p = write_dot(v1, tmp_path / "g" / "c.dot")
    assert p.read_text() == dot
    nodes = {n["id"]: n for n in v1["graph"]["nodes"]}
    assert nodes["box"]["floating"] and not nodes["base"]["floating"] and nodes["arm"]["group"] == "arm"


def test_declarations_from_a_geometry_record_and_dossier_without_a_kernel():
    class Result:
        geometry = {"parts": {"base": {"grounded": True}, "ball": {"free": True, "free_reason": "loose"},
                              "lid": {}},
                    "fasteners": {"screw_0": {"clamps": "lid", "into": "base"}}}
        joints = {"J": {"kind": "revolute", "moving": "lid", "fixed": "base"}}

    from cadagent.dossier.model import (Containment, Dossier, FreePart, GateConfig, Interface, PairExemption,
                                        PartCard)
    d = Dossier(file="project.yaml", gates=GateConfig(grounded=["stand"], free_parts=[FreePart("dust", "lint")],
                                                      intended_overlaps=[PairExemption(("a", "b"), "insert")],
                                                      strict_interfaces=True, touch_tol_mm=0.02),
                interfaces={"I1": Interface("I1", between=["base", "lid"], kind="fastened", clearance=0.1)},
                parts={"hopper": PartCard("hopper", contains=[Containment("pellet", 40, "hopper_void", True)])})
    decl = Declarations.from_build(Result(), d, {"interfaces": [{"id": "X", "parts": ["lid", "ball"]}]})
    assert decl.grounded == ["base", "stand"] and decl.free["ball"] == "loose" and decl.free["dust"] == "lint"
    assert "hopper_void" in decl.free["pellet"]
    assert decl.fasteners == {"screw_0": {"clamps": "lid", "into": "base"}} and decl.joints["J"]["moving"] == "lid"
    assert [i["id"] for i in decl.interfaces] == ["I1", "X"] and decl.interfaces[0]["clearance"] == 0.1
    assert decl.strict_interfaces and decl.touch_mm == 0.02
    assert decl.intended_overlaps == [{"parts": ["a", "b"], "reason": "insert"}]
    assert decl.contains[0] == {"what": "pellet", "cavity": "hopper_void", "container": "hopper", "free": True,
                                "count": 40}
    with pytest.raises(ValueError):
        Declarations(interfaces=[{"id": "bad", "between": ["only-one"]}])


# ----------------------------------------------------------------------------- on real solids (plan §4.2)

def box(x, y, z, at=(0, 0, 0)):
    return cq.Solid.makeBox(x, y, z, cq.Vector(*at))


def frame_assembly(extra=None):
    from cadagent.gates import Assembly
    asm = Assembly()
    asm.add("base", box(100, 40, 5))
    asm.add("left", box(5, 40, 50, (0, 0, 5)))
    asm.add("right", box(5, 40, 50, (95, 0, 5)))
    asm.add("top", box(100, 40, 5, (0, 0, 55)))
    for name, (shape, kw) in (extra or {}).items():
        asm.add(name, shape, **kw)
    return asm


FRAME3D = [{"id": "Ib", "between": ["base", "left"]}, {"id": "Ir", "between": ["base", "right"]},
           {"id": "It", "between": ["left", "top"]}, {"id": "Iu", "between": ["right", "top"]}]


@needs_cad
def test_real_frame_with_a_floating_box_fails_and_passes_once_free(tmp_path):
    asm = frame_assembly({"box": (box(10, 10, 10, (40, 10, 20)), {})})
    v = connectivity_gate(asm, Declarations(grounded=["base"], interfaces=FRAME3D), out=tmp_path / "c.json")
    assert not v["pass"]
    (isl,) = v["floating"]
    n = isl["nearest"]
    assert isl["parts"] == ["box"] and n["gap_mm"] == pytest.approx(15.0) and n["neighbour"] == "base"
    assert n["point_a"][2] == pytest.approx(20.0) and n["point_b"][2] == pytest.approx(5.0)
    assert json.loads((tmp_path / "c.json").read_text()) == v and (tmp_path / "c.dot").is_file()
    ok = connectivity_gate(asm, Declarations(grounded=["base"], interfaces=FRAME3D, free={"box": "spare, loose"}))
    assert ok["pass"] and ok["findings"] == [], ok["findings"]


@needs_cad
def test_real_interface_with_a_2_mm_gap_fails_then_passes_with_clearance_2_5():
    # the tab hangs on the right post; the shelf on the left post; the declared shelf/tab interface has a 2 mm gap
    asm2 = frame_assembly({"shelf": (box(20, 40, 3, (5, 0, 30)), {}), "tab": (box(68, 40, 3, (27, 0, 30)), {})})
    ifaces = FRAME3D + [{"id": "Is", "between": ["left", "shelf"]}, {"id": "It2", "between": ["tab", "right"]},
                        {"id": "Ig", "between": ["shelf", "tab"]}]
    v = connectivity_gate(asm2, Declarations(grounded=["base"], interfaces=ifaces))
    f = {x["id"]: x for x in v["findings"]}["interface:Ig"]
    assert "apart by 2.000 mm" in f["message"]       # 2 mm: beyond near_mm, measured exactly for the witness
    ifaces[-1]["clearance"] = 2.5
    assert [x["id"] for x in v["findings"]] == ["interface:Ig"]
    ok = connectivity_gate(asm2, Declarations(grounded=["base"], interfaces=ifaces))
    assert ok["pass"] and ok["findings"] == [], ok["findings"]


@needs_cad
def test_real_revolute_joint_links_a_part_that_touches_nothing():
    asm = frame_assembly({"arm": (box(30, 5, 5, (50, 50, 20)), {"body": "arm"})})
    asm.joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "right"}}
    v = connectivity_gate(asm, Declarations(grounded=["base"], interfaces=FRAME3D))
    assert v["pass"] and v["findings"] == [], v["findings"]
    assert {n["id"]: n["group"] for n in v["graph"]["nodes"]}["arm"] == "arm"


@needs_cad
def test_real_item_hanging_in_a_declared_cavity_is_held():
    from cadagent.gates import Assembly
    asm = Assembly()
    asm.add("base", box(40, 40, 5))
    cup = box(30, 30, 30, (5, 5, 5)).cut(box(26, 26, 28, (7, 7, 7)))
    asm.add("cup", cup)
    asm.add_cavity("cup_void", box(26, 26, 28, (7, 7, 7)), part="cup")
    asm.add("ball", cq.Solid.makeSphere(4, cq.Vector(20, 20, 20), angleDegrees1=-90))
    decl = dict(grounded=["base"], interfaces=[{"id": "I", "between": ["base", "cup"]}])
    v = connectivity_gate(asm, Declarations(**decl))
    assert {f["id"] for f in v["findings"]} == {"connect:static"}
    held = connectivity_gate(asm, Declarations(**decl, contains=[{"what": "ball", "cavity": "cup_void"}]))
    assert held["pass"] and held["findings"] == [], held["findings"]
    assert any(e["kind"] == "contained" and e["b"] == "cup" for e in held["graph"]["edges"])
    unreg = connectivity_gate(asm, Declarations(**decl, contains=[{"what": "ball", "cavity": "nope"}]))
    assert unreg["not_checked"][0]["cavity"] == "nope" and not unreg["pass"]


@needs_cad
def test_touch_tolerance_from_the_declarations_is_used():
    asm = frame_assembly({"pad": (box(10, 10, 2, (40, 10, 5.005)), {})})
    ifaces = FRAME3D + [{"id": "P", "between": ["base", "pad"]}]
    assert connectivity_gate(asm, Declarations(grounded=["base"], interfaces=ifaces))["pass"]
    v = connectivity_gate(asm, Declarations(grounded=["base"], interfaces=ifaces, touch_mm=0.001))
    assert not v["pass"] and v["limits"]["touch_mm"] == 0.001
    assert Tolerances().touch_mm == 0.01
