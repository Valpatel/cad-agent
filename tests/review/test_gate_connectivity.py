"""Connectivity and floating-parts gate (plan §4.2, T4).

The analysis is pure Python on given relations, so most rules are tested in core CI with hand-made
``Relation`` rows; the plan's geometric tests run on real solids when cadquery is installed.
"""

from __future__ import annotations

import json

import pytest

from cadagent.review.gates import Relation, Tolerances, verdict
from cadagent.review.gates.connectivity import (ASSUMPTIONS, Declarations, Node, analyse, connectivity_gate, owner,
                                                to_dot, write_dot)

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
    assert isl["nearest"]["neighbour_grounded"] is True
    assert "nearest grounded part beam at 3.000 mm" in f["message"], f["message"]


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
    assert "holds arm on post (apart, gap 0.200 mm)" in joint["message"], joint["message"]
    groups = {g["group"]: g for g in v["graph"]["groups"]}
    assert groups["body:arm"]["grounded"] and groups["body:arm"]["via_joints"] == ["J"]
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
    assert "needs <= 0.2 mm (declared clearance)" in failing(v)["joint:J"]["message"]


def test_a_moving_body_hanging_on_a_floating_part_is_not_grounded():
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "pin"}}
    v = run(FRAME + ["pin", "arm"], FRAME_RELS + [apart("pin", "post", 1.5), touch("arm", "pin")],
            grounded=["base"], joints=joints, interfaces=FRAME_IFACES)
    f = failing(v)
    assert f["connect:static"]["parts"] == ["pin"] and "does not reach ground" in f["joint:J"]["message"]
    assert f["connect:body:arm"]["parts"] == ["arm"] and "which does not reach ground" in f["connect:body:arm"]["message"]
    assert f["connect:static"]["evidence"]["islands"][0]["nearest"]["gap_mm"] == 1.5


def test_parts_of_a_moving_body_must_reach_its_joint_part():
    nodes = FRAME + [Node("arm", body="arm"), Node("cap", body="arm"), Node("tip", body="arm")]
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    rels = FRAME_RELS + [touch("arm", "post"), touch("arm", "cap"), apart("tip", "beam", 0.0001), touch("tip", "beam")]
    v = run(nodes, rels, grounded=["base"], joints=joints, interfaces=FRAME_IFACES + [
        {"id": "c", "between": ["arm", "cap"]}, {"id": "t", "between": ["tip", "beam"]}])
    f = failing(v)["connect:body:arm"]
    assert f["parts"] == ["tip"] and "touches beam only across bodies" in f["message"]


def test_a_static_part_held_only_by_a_moving_body_floats():
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    v = run(FRAME + ["arm", "cap"], FRAME_RELS + [touch("arm", "post"), touch("arm", "cap")], grounded=["base"],
            joints=joints, interfaces=FRAME_IFACES + [{"id": "c", "between": ["arm", "cap"]}])
    f = failing(v)["connect:static"]
    assert f["parts"] == ["cap"] and "touches arm only across bodies" in f["message"]
    # a fixed joint to the arm puts the cap into the arm's body (derived, whatever its label)
    joints["F"] = {"kind": "fixed", "moving": "cap", "fixed": "arm"}
    ok = run(FRAME + ["arm", "cap"], FRAME_RELS + [touch("arm", "post"), touch("arm", "cap")], grounded=["base"],
             joints=joints, interfaces=FRAME_IFACES)
    assert ok["pass"] and ok["findings"] == [], ok["findings"]
    assert {n["id"]: n["group"] for n in ok["graph"]["nodes"]}["cap"] == "body:arm"


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


def test_a_fastener_without_a_solid_joins_its_parts_only_when_its_axis_is_measured():
    kw = dict(grounded=["base"], interfaces=FRAME_IFACES, fasteners={"m3": {"clamps": "lid", "into": "beam"}})
    v = run(FRAME + ["lid"], FRAME_RELS, **kw)               # nothing measured: not a connection
    f = {x["id"]: x for x in v["findings"]}
    assert f["fastener:m3"]["status"] == "warn" and f["connect:static"]["parts"] == ["lid"]
    assert v["not_checked"][0]["fastener"] == "m3"
    nodes = {k: Node(k) for k in FRAME + ["lid"]}
    an = analyse(nodes, FRAME_RELS, Declarations(**kw), fastener_reach={"m3": {"ok": True, "axes": []}})
    assert not [c for c in an.checks if c.status != "pass"]
    e = next(e for e in an.extra["graph"]["edges"] if e["kind"] == "fastener")
    assert e["rigid"] and e["measured"] == "axis reaches both"
    an = analyse(nodes, FRAME_RELS, Declarations(**kw), fastener_reach={"m3": {"ok": False, "reason": "misses lid"}})
    assert {c.id for c in an.checks if c.status == "fail"} == {"fastener:m3", "connect:static"}


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
    assert nodes["box"]["floating"] and not nodes["base"]["floating"] and nodes["arm"]["group"] == "body:arm"


def test_declarations_from_a_geometry_record_and_dossier_without_a_kernel():
    class Result:
        geometry = {"parts": {"base": {"grounded": True}, "ball": {"free": True, "free_reason": "loose"},
                              "lid": {}},
                    "fasteners": {"screw_0": {"clamps": "lid", "into": "base"}}}
        joints = {"J": {"kind": "revolute", "moving": "lid", "fixed": "base"}}

    from cadagent.review.dossier.model import (Containment, Dossier, FreePart, GateConfig, Interface, PairExemption,
                                               PartCard)
    d = Dossier(file="project.yaml", gates=GateConfig(grounded=["stand"], free_parts=[FreePart("dust", "lint")],
                                                      intended_overlaps=[PairExemption(("a", "b"), "insert")],
                                                      strict_interfaces=True, touch_tol_mm=0.02),
                interfaces={"I1": Interface("I1", between=["base", "lid"], kind="fastened", clearance=0.1)},
                parts={"hopper": PartCard("hopper", contains=[Containment("pellet", 40, "hopper_void", True)])})
    decl = Declarations.from_build(Result(), d, {"interfaces": [{"id": "X", "parts": ["lid", "ball"]}]})
    assert decl.grounded == ["base", "stand"] and decl.free["ball"] == "loose" and decl.free["dust"] == "lint"
    assert "hopper_void" in decl.free["pellet"]
    assert decl.fasteners == {"screw_0": {"clamps": "lid", "into": "base", "axes": [], "length_mm": None}}
    assert decl.joints["J"]["moving"] == "lid"
    assert [i["id"] for i in decl.interfaces] == ["I1", "X"] and decl.interfaces[0]["clearance"] == 0.1
    assert decl.strict_interfaces and decl.touch_mm == 0.02
    assert decl.intended_overlaps == [{"parts": ["a", "b"], "reason": "insert"}]
    assert decl.contains[0] == {"what": "pellet", "cavity": "hopper_void", "container": "hopper", "free": True,
                                "count": 40}
    three = run(FRAME, FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES + [
        {"id": "T", "between": ["base", "post", "beam"]}])
    assert "names 3 parties" in failing(three)["interface:T"]["message"]


# ----------------------------------------------------------------------------- on real solids (plan §4.2)

def box(x, y, z, at=(0, 0, 0)):
    return cq.Solid.makeBox(x, y, z, cq.Vector(*at))


def frame_assembly(extra=None):
    from cadagent.review.gates import Assembly
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
    asm = frame_assembly({"arm": (box(30, 5, 5, (64.5, 10, 20)), {})})     # 0.5 mm from the right post
    asm.joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "right"}}
    v = connectivity_gate(asm, Declarations(grounded=["base"], interfaces=FRAME3D))
    assert v["pass"] and v["findings"] == [], v["findings"]
    assert {n["id"]: n["group"] for n in v["graph"]["nodes"]}["arm"] == "body:arm"
    j = next(c for c in v["checks"] if c["id"] == "joint:J")
    assert "gap 0.500 mm" in j["message"]
    far = frame_assembly({"arm": (box(30, 5, 5, (50, 50, 20)), {})})       # 18 mm away: the joint does not hold
    far.joints = asm.joints
    v = connectivity_gate(far, Declarations(grounded=["base"], interfaces=FRAME3D))
    assert "18.028 mm from right, needs <= 1 mm" in {f["id"]: f for f in v["findings"]}["joint:J"]["message"]


@needs_cad
def test_real_item_hanging_in_a_declared_cavity_is_held():
    from cadagent.review.gates import Assembly
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


# ----------------------------------------------------------------------------- regressions from the PR review

def test_review_1_a_fixed_joint_needs_contact_or_a_declared_clearance():
    joints = {"F1": {"kind": "fixed", "moving": "bracket", "fixed": "post"}}
    far = run(FRAME + ["bracket"], FRAME_RELS + [apart("bracket", "post", 35.0)], grounded=["base"], joints=joints,
              interfaces=FRAME_IFACES)
    f = failing(far)
    assert f["connect:static"]["parts"] == ["bracket"]
    assert "bracket is 35.000 mm from post, needs contact or a declared clearance" in f["joint:F1"]["message"]
    held = run(FRAME + ["bracket"], FRAME_RELS + [touch("bracket", "post")], grounded=["base"], joints=joints,
               interfaces=FRAME_IFACES)
    assert held["pass"] and held["findings"] == [], held["findings"]
    spaced = run(FRAME + ["bracket"], FRAME_RELS + [apart("bracket", "post", 0.3)], grounded=["base"], joints=joints,
                 interfaces=FRAME_IFACES + [{"id": "F1", "between": ["bracket", "post"], "clearance": 0.5}])
    assert spaced["pass"] and spaced["findings"] == [], spaced["findings"]


def test_review_1_a_moving_joint_holds_only_within_max_joint_gap_mm_or_its_clearance():
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    kw = dict(grounded=["base"], joints=joints, interfaces=FRAME_IFACES)
    far = run(FRAME + ["arm"], FRAME_RELS + [apart("arm", "post", 40.0)], **kw)
    f = failing(far)
    assert "needs <= 1 mm (max_joint_gap_mm)" in f["joint:J"]["message"]
    assert f["connect:body:arm"]["parts"] == ["arm"] and "joint J does not hold arm" in f["connect:body:arm"]["message"]
    assert run(FRAME + ["arm"], FRAME_RELS + [apart("arm", "post", 40.0)], max_joint_gap_mm=50.0, **kw)["pass"]
    unmeasured = run(FRAME + ["arm"], FRAME_RELS, **kw)
    assert "arm is unmeasured from post" in failing(unmeasured)["joint:J"]["message"]


def test_review_3_a_free_part_holds_nothing_up():
    v = run(FRAME + ["ball", "bracket"], FRAME_RELS + [touch("ball", "post"), touch("ball", "bracket")],
            grounded=["base"], free={"ball": "loose"}, interfaces=FRAME_IFACES)
    f = failing(v)["connect:static"]
    assert f["parts"] == ["bracket"] and "touches only free part(s) ball, which hold nothing up" in f["message"]
    assert {e["a"] + "|" + e["b"]: e["rigid"] for e in v["graph"]["edges"]}["ball|post"] is False
    assert v["exclusions"] == [{"parts": ["ball"], "reason": "loose", "kind": "allowed free"}]


def test_review_4_ground_is_parts_only_and_every_joint_instance_is_checked():
    sec = run(FRAME + [Node("bracket", section="S1"), Node("frame", section="S1")], FRAME_RELS + [touch("frame", "base")],
              grounded=["S1"], interfaces=FRAME_IFACES)
    assert "grounded ['S1'] are sections" in failing(sec)["ground"]["message"]
    wheels = [Node("wheel#0", body="wheel"), Node("wheel#1", body="wheel")]
    v = run(FRAME + wheels, FRAME_RELS + [touch("wheel#0", "post"), apart("wheel#1", "post", 80.0)], grounded=["base"],
            joints={"J": {"kind": "revolute", "moving": "wheel", "fixed": "post"}}, interfaces=FRAME_IFACES)
    f = failing(v)
    assert f["connect:body:wheel"]["parts"] == ["wheel#1"]
    assert "wheel#1 is 80.000 mm from post" in f["joint:J"]["message"]
    feet = run(FRAME + ["foot#0", "foot#1"], FRAME_RELS + [touch("foot#0", "base")], grounded=["base", "foot"],
               interfaces=FRAME_IFACES + [{"id": "Ft", "between": ["base", "foot"]}])
    assert feet["pass"] and [x["id"] for x in feet["findings"]] == ["ground:foot"]
    assert "each is taken as ground" in feet["findings"][0]["message"]


def test_review_5_a_bracket_bolted_to_a_moving_arm_moves_with_it():
    joints = {"J1": {"kind": "revolute", "moving": "arm", "fixed": "post"}}
    nodes = FRAME + [Node("arm", body="arm"), Node("screw_0", kind="fastener", body="arm"), "bracket"]
    rels = FRAME_RELS + [touch("arm", "post"), touch("screw_0", "bracket"), touch("screw_0", "arm"),
                         touch("bracket", "arm")]
    v = run(nodes, rels, grounded=["base"], joints=joints, interfaces=FRAME_IFACES + [
        {"id": "B", "between": ["bracket", "arm"]}], fasteners={"screw_0": {"clamps": "bracket", "into": "arm"}})
    assert v["pass"] and v["findings"] == [], v["findings"]
    groups = {n["id"]: n["group"] for n in v["graph"]["nodes"]}
    assert groups["bracket"] == groups["screw_0"] == "body:arm"
    # a chain of fixed joints, in any order, joins the body
    chain = {"J1": joints["J1"], "a": {"kind": "fixed", "moving": "y", "fixed": "x"},
             "b": {"kind": "fixed", "moving": "x", "fixed": "arm"}}
    v = run(FRAME + ["arm", "x", "y"], FRAME_RELS + [touch("arm", "post"), touch("x", "arm"), touch("y", "x")],
            grounded=["base"], joints=chain, interfaces=FRAME_IFACES)
    assert v["pass"] and {n["id"]: n["group"] for n in v["graph"]["nodes"]}["y"] == "body:arm", v["findings"]
    # bolting the moving arm to ground is a finding
    bad = run(FRAME + ["arm"], FRAME_RELS + [touch("arm", "post"), touch("arm", "base")], grounded=["base"],
              joints={**joints, "W": {"kind": "fixed", "moving": "arm", "fixed": "base"}}, interfaces=FRAME_IFACES)
    assert "fixed joint W joins arm to base, a grounded part" in failing(bad)["bodies:arm"]["message"]


def test_from_build_bodies_are_the_transitive_closure():
    from cadagent.review.gates.relations import moving_bodies
    joints = {"J": {"kind": "revolute", "moving": "arm", "fixed": "pin"}, "a": {"kind": "fixed", "moving": "y",
                                                                                "fixed": "x"},
              "b": {"kind": "fixed", "moving": "x", "fixed": "arm"}}
    fasteners = {"s": {"clamps": "bracket", "into": "arm"}, "t": {"clamps": "pin", "into": "block"}}
    assert moving_bodies(joints, fasteners, ["base"]) == {"arm": "arm", "x": "arm", "y": "arm", "s": "arm",
                                                          "bracket": "arm"}


def test_review_6_duplicate_interfaces_merge_or_warn():
    same = run(FRAME, FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES + FRAME_IFACES)
    assert same["pass"] and same["findings"] == []
    diff = run(FRAME, FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES + [
        {"id": "I1", "between": ["base", "post"], "clearance": 0.3}])
    assert diff["pass"] and [x["id"] for x in diff["findings"]] == ["duplicate:interface:I1"]


def test_review_7_ignored_pairs_are_dropped_from_the_graph():
    rels = FRAME_RELS + [touch("base", "beam")]
    v = run(FRAME, rels, grounded=["base"], interfaces=FRAME_IFACES,
            ignore_pairs=[{"parts": ["base", "beam"], "reason": "variants"}])
    assert v["pass"] and v["findings"] == [], v["findings"]


def test_review_8_minor_items():
    # a body named "static" stays a moving body
    v = run(FRAME + [Node("arm", body="static")], FRAME_RELS + [apart("arm", "post", 0.2)], grounded=["base"],
            joints={"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}}, interfaces=FRAME_IFACES)
    assert v["pass"] and {n["id"]: n["group"] for n in v["graph"]["nodes"]}["arm"] == "body:static", v["findings"]
    # a mechanism interface on other parts than its joint
    v = run(FRAME + ["arm"], FRAME_RELS + [apart("arm", "post", 0.2)], grounded=["base"],
            joints={"J": {"kind": "revolute", "moving": "arm", "fixed": "post"}},
            interfaces=FRAME_IFACES + [{"id": "J", "between": ["beam", "base"], "kind": "revolute"}])
    assert "but joint J joins arm and post" in failing(v)["interface:J"]["message"]
    # non-geometric interfaces are listed as not checked
    v = run(FRAME, FRAME_RELS, grounded=["base"], interfaces=FRAME_IFACES + [
        {"id": "E", "between": ["base", "beam"], "kind": "electrical"}])
    assert v["not_checked"] == [{"interface": "E", "kind": "electrical", "reason": "not geometric"}]


@needs_cad
def test_review_real_false_passes_now_fail():
    """The reviewer's three real-solid repros: each must fail."""
    from cadagent.review.gates import Assembly

    def asm_with(parts, joints=None):
        a = Assembly()
        a.add("base", cq.Workplane().box(100, 100, 10).val())
        for name, loc in parts:
            a.add(name, cq.Workplane().box(10, 10, 10).val(), loc)
        a.joints = joints or {}
        return a

    a = asm_with([("bracket", (0, 0, 45))], {"F1": {"kind": "fixed", "moving": "bracket", "fixed": "base"}})
    v = connectivity_gate(a, Declarations(grounded=["base"]))
    assert not v["pass"] and "35.000 mm from base" in {f["id"]: f for f in v["findings"]}["joint:F1"]["message"]

    a = asm_with([("shelf", (0, 0, 70))])
    v = connectivity_gate(a, Declarations(grounded=["base"], fasteners={"m3": {"clamps": "shelf", "into": "base"}}))
    assert not v["pass"] and {f["id"] for f in v["findings"]} >= {"fastener:m3", "connect:static"}
    # with an axis and a length the reach is measured: 70 mm down from the shelf top reaches the base
    m3 = {"clamps": "shelf", "into": "base", "axes": [((0, 0, 75), (0, 0, -1))]}
    ok = connectivity_gate(a, Declarations(grounded=["base"], fasteners={"m3": {**m3, "length_mm": 72}}))
    assert ok["pass"], ok["findings"]
    short = connectivity_gate(a, Declarations(grounded=["base"], fasteners={"m3": {**m3, "length_mm": 20}}))
    assert "does not reach both" in {f["id"]: f for f in short["findings"]}["fastener:m3"]["message"]

    a = asm_with([("ball", (40, 0, 10)), ("shelf", (40, 0, 20))])
    v = connectivity_gate(a, Declarations(grounded=["base"], free={"ball": "loose spare"}))
    assert not v["pass"] and {f["id"]: f for f in v["findings"]}["connect:static"]["parts"] == ["shelf"]


@needs_cad
def test_review_7_a_table_passed_in_is_not_changed():
    from cadagent.review.gates import relation_table
    asm = frame_assembly({"box": (box(10, 10, 10, (40, 10, 20)), {})})
    table = relation_table(asm)
    before = dict(table.relations)
    v = connectivity_gate(asm, Declarations(grounded=["base"], interfaces=FRAME3D, touch_mm=0.5), table=table)
    assert table.relations == before
    assert v["floating"][0]["nearest"]["gap_mm"] == pytest.approx(15.0)       # measured outside the table
    assert "tolerances" in {f["id"] for f in v["findings"]}


@needs_cad
def test_review_8_contains_without_a_container_takes_the_cavity_part():
    from cadagent.review.gates import Assembly
    asm = Assembly()
    asm.add("base", box(40, 40, 5))
    asm.add("cup", box(30, 30, 30, (5, 5, 5)).cut(box(26, 26, 28, (7, 7, 7))))
    asm.add_cavity("cup_void", box(26, 26, 28, (7, 7, 7)), part="cup")
    asm.add("ball", cq.Solid.makeSphere(4, cq.Vector(20, 20, 11), angleDegrees1=-90))   # resting on the floor
    v = connectivity_gate(asm, Declarations(grounded=["base"], interfaces=[{"id": "I", "between": ["base", "cup"]}],
                                            contains=[{"what": "ball", "cavity": "cup_void"}]))
    assert v["pass"] and v["findings"] == [], v["findings"]


def test_review_8_contains_coverage_uses_the_contained_pairs_and_the_witness_says_if_it_is_grounded():
    inside = Relation("ball", "cav", "contains", contained="a_in_b")
    nodes = {k: Node(k) for k in FRAME + ["ball"]}
    an = analyse(nodes, FRAME_RELS + [touch("ball", "base")], Declarations(
        grounded=["base"], interfaces=FRAME_IFACES, contains=[{"what": "ball", "cavity": "cav"}]),
        contained=[("ball", "base", "cav", inside)])
    assert not [c for c in an.checks if c.status != "pass"]
    v = run(FRAME + ["ball", "bracket"], FRAME_RELS + [touch("ball", "bracket")], grounded=["base"],
            free={"ball": "loose"}, interfaces=FRAME_IFACES)
    assert "nearest ungrounded part ball at 0.000 mm" in failing(v)["connect:static"]["message"]
