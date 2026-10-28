"""Motion-range interference gate (T7).

The first half runs the gate's core (``run_motion``) on a box world with no CAD kernel: the rules
for sampling, chains, intended contacts, witnesses and density, in core CI. The second half runs
``motion_gate`` on CadQuery solids (skipped without the ``cad`` extra): the plan's flap that clears
at 0 deg and hits a wall, a stop contact at the range end, the pair cache, and containment per pose.
"""

from __future__ import annotations

import math

import pytest

from cadagent.gates import Relation
from cadagent.gates.motion import (IDENTITY, Joint, World, box_distance, moved_box, rotation, run_motion,
                                   translation)


# ----------------------------------------------------------------------------- a kernel-free world

class BoxWorld(World):
    """Parts are axis-aligned boxes; a relation is decided on the moved boxes (exact for slides and
    quarter turns). ``calls`` records every (a, b) the gate asked about."""

    def __init__(self, boxes, bodies=None, unknown=()):
        self.boxes = dict(boxes)
        self.names = list(boxes)
        self.bodies = dict(bodies or {})
        self.unknown = {frozenset(p) for p in unknown}
        self.calls = []

    def body(self, key):
        return self.bodies.get(key, key)

    def box(self, key):
        return self.boxes[key]

    def relate(self, mats, a, b):
        self.calls.append((a, b))
        if frozenset((a, b)) in self.unknown:
            return Relation(a, b, "unknown", error="test")
        ba = moved_box(self.boxes[a], mats.get(self.body(a), IDENTITY))
        bb = moved_box(self.boxes[b], mats.get(self.body(b), IDENTITY))
        sides = [min(ba[i + 3], bb[i + 3]) - max(ba[i], bb[i]) for i in range(3)]
        if all(s > 0 for s in sides) and math.prod(sides) > 0.001:
            vol = math.prod(sides)
            c = [(max(ba[i], bb[i]) + min(ba[i + 3], bb[i + 3])) / 2 for i in range(3)]
            return Relation(a, b, "overlapping", gap_mm=0.0, overlap_mm3=round(vol, 6),
                            witness={"overlap_centroid": c})
        gap = box_distance(ba, bb)
        pa = [min(max(ba[i], bb[i]), ba[i + 3]) for i in range(3)]
        pb = [min(max(bb[i], ba[i]), bb[i + 3]) for i in range(3)]
        state = "touching" if gap <= 0.01 else "apart"
        return Relation(a, b, state, gap_mm=round(gap, 6), witness={"point_a": pa, "point_b": pb})


def slider(moving, fixed, rng, direction=(1, 0, 0), **kw):
    return {"kind": "slider", "moving": moving, "fixed": fixed, "axis": {"origin": [0, 0, 0], "direction": direction},
            "range": list(rng), "unit": "mm", **kw}


def finding(v, prefix):
    hits = [f for f in v["findings"] if f["id"].startswith(prefix)]
    assert hits, f"no finding {prefix!r}: {[f['id'] for f in v['findings']]}"
    return hits[0]


# a carriage on a rail (the fixed part), a wall at x = 40
RAIL = {"rail": (0, 0, -2, 100, 10, 0), "carriage": (0, 0, 0, 10, 10, 10), "wall": (40, 0, 0, 45, 10, 20)}


# ----------------------------------------------------------------------------- transforms and joints

def test_rotation_is_right_handed_about_an_offset_axis():
    m = rotation((1, 0, 0), (0, 0, 1), 90)
    from cadagent.gates.motion import _apply
    assert _apply(m, (2, 0, 0)) == pytest.approx((1, 1, 0))
    assert _apply(translation((0, 0, 2), 5), (1, 1, 1)) == pytest.approx((1, 1, 6))
    assert moved_box((0, 0, 0, 2, 1, 1), rotation((0, 0, 0), (0, 0, 1), 90)) == pytest.approx((-1, 0, 0, 0, 2, 1))


def test_joint_from_the_build_record_and_the_registry_spelling():
    class Axis:
        origin, direction = (105.0, 0.0, 20.0), (0.0, -1.0, 0.0)
    j = Joint.coerce("I9", {"kind": "revolute", "moving": "arm", "fixed": "pin", "axis": Axis(), "range": [0, 40],
                            "unit": "deg", "samples": None})
    assert (j.moving, j.fixed, len(j.dofs)) == ("arm", "pin", 1)
    d = j.dofs[0]
    assert (d.kind, d.samples, d.values()[0], d.values()[-1]) == ("rotate", 12, 0, 40)
    assert d.step() == pytest.approx(40 / 11)
    reg = Joint.coerce("S", {"kind": "slider", "parts": ("a", "b"), "axis": ((0, 0, 0), (0, 0, 1)),
                             "range_mm": (5, -5), "samples": 3})
    assert reg.dofs[0].values() == [-5, 0, 5] and reg.dofs[0].home == 0
    cyl = Joint.coerce("C", {"kind": "cylindrical", "moving": "a", "fixed": "b", "axis": ((0, 0, 0), (0, 0, 1)),
                             "range": [0, 90], "unit": "deg", "range_mm": [0, 10]}, default_samples=4)
    assert [x.kind for x in cyl.dofs] == ["rotate", "slide"] and [x.samples for x in cyl.dofs] == [4, 4]
    fine = Joint.coerce("F", {"kind": "revolute", "moving": "a", "fixed": "b", "axis": ((0, 0, 0), (0, 0, 1)),
                              "range": [0, 90], "unit": "deg"}, max_step_deg=2)
    assert fine.dofs[0].samples == 46 and fine.dofs[0].step() == pytest.approx(2.0)
    with pytest.raises(ValueError):
        Joint.coerce("X", {"kind": "revolute", "moving": "a", "fixed": "b", "range": [0, 9], "unit": "deg"})


# ----------------------------------------------------------------------------- the core on boxes

def test_a_slider_that_reaches_a_wall_fails_with_the_first_pose_and_the_onset():
    w = BoxWorld(RAIL)
    v = run_motion(w, {"J": slider("carriage", "rail", (0, 50), samples=11)})
    assert v["pass"] is False
    f = finding(v, "collision:carriage|wall")
    ev = f["evidence"]
    assert f["parts"] == ["carriage", "wall"]
    assert ev["first_pose"] == "J=35mm" and ev["last_clear_pose"] == "J=30mm"     # 5 mm samples; contact at 30 mm
    assert ev["overlap_mm3"] == pytest.approx(500) and ev["colliding_poses"] == 2      # 35 and 40 mm: through it
    assert ev["last_clear_gap_mm"] == 0 and ev["point_a"] is not None            # touching at 30 mm
    onset = ev["onset"]
    assert onset["clear"] <= 30 + 1e-9 < onset["hit"]
    assert onset["hit"] - onset["clear"] == pytest.approx(5 / 256, abs=1e-5)
    (g,) = v["groups"]
    assert g["density"][0]["step"] == 5 and g["density"][0]["max_travel_per_step_mm"] == 5
    assert v["limits"]["default_samples"] == 12 and v["stats"]["poses"] == 11


def test_short_of_the_wall_passes_and_reports_the_smallest_clearance():
    v = run_motion(BoxWorld(RAIL), {"J": slider("carriage", "rail", (0, 29.5))})
    assert v["pass"] and v["findings"] == []
    (g,) = v["groups"]
    assert g["min_clearance_mm"] == pytest.approx(0.5) and g["at"]["pose"] == "J=29.5mm"
    assert g["intended_contacts_touching"]["carriage|rail"]["poses"] == 12      # the joint's own pair, on the rail


def test_an_intended_stop_may_touch_at_the_range_end_but_not_overlap():
    joint = slider("carriage", "rail", (0, 30), intended_contacts=[("carriage", "wall")])
    v = run_motion(BoxWorld(RAIL), {"J": joint})
    assert v["pass"] and v["findings"] == []
    assert v["groups"][0]["intended_contacts_touching"]["carriage|wall"] == {"poses": 1, "first": "J=30mm",
                                                                           "last": "J=30mm"}
    over = run_motion(BoxWorld(RAIL), {"J": {**joint, "range": [0, 31]}})
    f = finding(over, "collision:carriage|wall")
    assert f["evidence"]["intended_contact"] is True and "an intended contact" in f["message"]
    assert f["evidence"]["overlap_mm3"] == pytest.approx(100)


def test_an_undeclared_touch_warns_and_fails_when_strict():
    v = run_motion(BoxWorld(RAIL), {"J": slider("carriage", "rail", (0, 30))})
    assert v["pass"] and [f["id"] for f in v["findings"]] == ["contact:carriage|wall"]
    assert finding(v, "contact:")["status"] == "warn"
    strict = run_motion(BoxWorld(RAIL), {"J": slider("carriage", "rail", (0, 30))}, strict_contacts=True)
    assert strict["pass"] is False


def test_static_pairs_and_same_body_pairs_are_never_queried():
    boxes = {**RAIL, "pad": (0, 0, 10, 10, 10, 12), "other": (60, 0, 0, 70, 10, 10)}
    w = BoxWorld(boxes, bodies={"pad": "carriage"})              # the pad rides on the carriage
    run_motion(w, {"J": slider("carriage", "rail", (0, 20))})
    asked = {frozenset(c) for c in w.calls}
    assert frozenset(("rail", "wall")) not in asked and frozenset(("carriage", "pad")) not in asked
    assert asked <= {frozenset(("carriage", x)) for x in boxes} | {frozenset(("pad", x)) for x in boxes}
    assert not any("other" in c for c in w.calls)                 # its box never comes near


def test_an_unknown_relation_fails():
    v = run_motion(BoxWorld(RAIL, unknown=[("carriage", "rail")]), {"J": slider("carriage", "rail", (0, 10))})
    assert v["pass"] is False and finding(v, "relation:carriage|rail")["status"] == "fail"


CHAIN = {"rail": (0, 0, -2, 100, 10, 0), "carriage": (0, 0, 0, 10, 10, 10), "lift": (0, 0, 10, 10, 10, 20),
         "beam": (30, 0, 35, 60, 10, 40)}
CHAIN_JOINTS = {"X": slider("carriage", "rail", (0, 40), samples=5),
                "Z": slider("lift", "carriage", (0, 20), direction=(0, 0, 1), samples=5)}


def test_a_chain_is_sampled_on_a_grid_and_the_child_rides_on_its_parent():
    """The beam is reached only with the carriage out (x > 20) and the lift up (z > 15): one joint at a time
    with the other at home never meets it."""
    v = run_motion(BoxWorld(CHAIN), CHAIN_JOINTS)
    (g,) = v["groups"]
    assert g["id"] == "X+Z" and g["poses"] == 25 and g["joints"] == ["X", "Z"]
    f = finding(v, "collision:beam|lift")
    assert f["evidence"]["first_pose"] == "X=30mm,Z=20mm" and "onset" not in f["evidence"]
    assert f["evidence"]["colliding_poses"] == 2
    alone = run_motion(BoxWorld(CHAIN), {"X": CHAIN_JOINTS["X"]})
    assert alone["pass"], "the beam is out of reach with the lift down"
    # the parent's travel per step is measured on the parent and the child it carries
    assert [d["joint"] for d in g["density"]] == ["X", "Z"]


def test_a_child_axis_is_carried_by_its_parent():
    """A turret turns 90 deg about Z; an arm on it slides along the turret's +X. At 90 deg the arm's slide points
    along world +Y and reaches the post; sliding along world +X (the wrong composition) would miss it."""
    boxes = {"base": (-20, -20, -2, 20, 20, 0), "turret": (-4, -4, 0, 4, 4, 4), "arm": (4, -2, 0, 14, 2, 4),
             "post": (-5, 30, 0, 5, 35, 4)}
    joints = {"T": {"kind": "revolute", "moving": "turret", "fixed": "base", "axis": ((0, 0, 0), (0, 0, 1)),
                    "range": [0, 90], "unit": "deg", "samples": 2},
              "A": slider("arm", "turret", (0, 20), samples=3)}
    v = run_motion(BoxWorld(boxes), joints)
    f = finding(v, "collision:arm|post")
    assert f["evidence"]["first_pose"] == "T=90deg,A=20mm"
    assert v["groups"][0]["id"] == "T+A"


def test_independent_joints_whose_sweeps_meet_warn_until_combined():
    boxes = {"base": (0, 0, -2, 100, 10, 0), "a": (0, 0, 0, 10, 10, 10), "b": (50, 0, 0, 60, 10, 10)}
    joints = {"A": slider("a", "base", (0, 25), samples=6), "B": slider("b", "base", (-25, 0), samples=6)}
    v = run_motion(BoxWorld(boxes), joints)
    assert v["pass"] and [f["id"] for f in v["findings"]] == ["combination:A+B"]
    assert v["not_checked"] == ["A with B: combined poses (sampled separately)"]
    both = run_motion(BoxWorld(boxes), joints, combine=[["A", "B"]])
    assert both["groups"][0]["id"] == "A+B" and both["groups"][0]["poses"] == 36
    assert finding(both, "collision:a|b")["evidence"]["first_pose"] == "A=20mm,B=-25mm"


def test_a_grid_over_max_poses_is_coarsened_evenly_and_says_so():
    v = run_motion(BoxWorld(CHAIN), CHAIN_JOINTS, samples={"X": 30, "Z": 30}, max_poses=100)
    (g,) = v["groups"]
    assert g["poses"] == 100 and g["coarsened"] is True
    assert [d["samples"] for d in g["density"]] == [10, 10]
    assert [d["declared_samples"] for d in g["density"]] == [30, 30]
    assert finding(v, "density:X+Z")["status"] == "warn"


def test_joint_declaration_problems():
    w = BoxWorld(RAIL, bodies={"rail": "carriage"})
    v = run_motion(w, {"J": slider("carriage", "rail", (0, 10)), "M": slider("ghost", "rail", (0, 1)),
                       "P": {"kind": "planar", "moving": "wall", "fixed": "rail"},
                       "F": {"kind": "fixed", "moving": "wall", "fixed": "rail"}})
    ids = {f["id"]: f for f in v["findings"]}
    assert "in the moving body" in ids["joint:J"]["message"]
    assert "'ghost' is not in the assembly" in ids["joint:M"]["message"]
    assert ids["joint:P"]["status"] == "warn" and "joint:F" not in ids
    assert v["pass"] is False


def test_joints_that_carry_each_other_in_a_loop_fail_with_what_rides_on_them():
    boxes = {"base": (0, 0, -2, 90, 10, 0), "a": (0, 0, 0, 10, 10, 10), "b": (20, 0, 0, 30, 10, 10),
             "c": (40, 0, 0, 50, 10, 10)}
    v = run_motion(BoxWorld(boxes), {"J1": slider("a", "b", (0, 1)), "J2": slider("b", "a", (0, 1)),
                                     "J3": slider("c", "a", (0, 1))})
    ids = {f["id"]: f["message"] for f in v["findings"]}
    assert "in a loop" in ids["joint:J1"] and "rides on joint J1" in ids["joint:J3"]
    assert v["pass"] is False


def test_intended_overlaps_and_ignored_pairs():
    joint = {"J": slider("carriage", "rail", (0, 50))}
    ok = run_motion(BoxWorld(RAIL), joint, intended_overlaps=[{"parts": ["carriage", "wall"], "reason": "a brush"}])
    assert ok["pass"] and ok["exclusions"][0]["reason"] == "a brush"
    w = BoxWorld(RAIL)
    ign = run_motion(w, joint, ignore_pairs=[("carriage", "wall")])
    assert ign["pass"] and ("carriage", "wall") not in w.calls
    with pytest.raises(ValueError):
        run_motion(BoxWorld(RAIL), joint, intended_overlaps=[{"parts": ["carriage"], "reason": "x"}])


def test_verdict_is_deterministic_apart_from_the_timing():
    a = run_motion(BoxWorld(RAIL), {"J": slider("carriage", "rail", (0, 50))})
    b = run_motion(BoxWorld(RAIL), {"J": slider("carriage", "rail", (0, 50))})
    a["stats"].pop("seconds"), b["stats"].pop("seconds")
    assert a == b and a["physical_fit_verified"] is False and a["assumptions"]


# ----------------------------------------------------------------------------- on CadQuery solids

def _cq():
    return pytest.importorskip("cadquery")


def revolute(rng, **kw):
    return {"kind": "revolute", "moving": "flap", "fixed": "pin", "axis": ((0, 0, 4), (0, -1, 0)), "range": list(rng),
            "unit": "deg", **kw}


@pytest.fixture
def flap_wall():
    """The flap at 0 deg rests on the stop; a wall above it whose underside at z = 30 the flap's top far corner
    meets at the angle ``hit``."""
    cq = _cq()
    from cadagent.gates import Assembly
    asm = Assembly()
    asm.add("base", cq.Solid.makeBox(60, 20, 2, cq.Vector(-10, -5, -2)))
    asm.add("pin", cq.Solid.makeCylinder(1.5, 20, cq.Vector(0, -5, 4), cq.Vector(0, 1, 0)))
    flap = cq.Solid.makeBox(40, 10, 4, cq.Vector(-2, 0, 2)).cut(
        cq.Solid.makeCylinder(1.5, 10, cq.Vector(0, 0, 4), cq.Vector(0, 1, 0)))
    asm.add("flap", flap)
    asm.add("stop", cq.Solid.makeBox(6, 10, 2, cq.Vector(30, 0, 0)))
    asm.add("wall", cq.Solid.makeBox(40, 10, 4, cq.Vector(0, 0, 30)))
    r, h = 38.0, 2.0                       # the far top corner: 38 mm out, 2 mm above the pivot
    hit = math.degrees(math.asin(26.0 / math.hypot(r, h)) - math.atan2(h, r))
    return asm, hit


def test_flap_clears_at_0_and_hits_the_wall_on_its_way_to_60(flap_wall):
    from cadagent.gates.motion import motion_gate
    asm, hit = flap_wall
    assert 40 < hit < 50
    ok = motion_gate(asm, {"I1": revolute((0, 40), intended_contacts=[("flap", "stop")])})
    assert ok["pass"] and ok["findings"] == [], ok["findings"]
    g = ok["groups"][0]
    assert g["intended_contacts_touching"]["flap|stop"]["first"] == "I1=0deg"
    assert g["density"][0]["max_radius_mm"] == pytest.approx(math.hypot(38, 2), abs=0.5)
    bad = motion_gate(asm, {"I1": revolute((0, 60), intended_contacts=[("flap", "stop")])})
    f = finding(bad, "collision:flap|wall")
    onset = f["evidence"]["onset"]
    assert onset["clear"] - 0.05 <= hit <= onset["hit"] + 0.05, (onset, hit)
    assert f["evidence"]["overlap_mm3"] > 0 and len(f["evidence"]["point_a"]) == 3
    assert bad["stats"]["kernel_queries"] > 0


def test_stop_contact_at_the_range_end_passes_and_driving_past_it_fails():
    """A flap hinged at the origin swings down (positive about +Y) and lands flat on a stop face at 90 deg."""
    cq = _cq()
    from cadagent.gates import Assembly
    from cadagent.gates.motion import motion_gate
    asm = Assembly()
    asm.add("post", cq.Solid.makeBox(4, 6, 4, cq.Vector(-2, -6, -2)))        # the hinge, beside the flap
    asm.add("flap", cq.Solid.makeBox(20, 10, 2, cq.Vector(0, 0, 0)))
    asm.add("stop", cq.Solid.makeBox(4, 10, 20, cq.Vector(-4, 0, -24)))      # its face x = 0 meets the flap at 90
    joint = {"kind": "revolute", "moving": "flap", "fixed": "post", "axis": ((0, 0, 0), (0, 1, 0)),
             "intended_contacts": [("flap", "stop")], "unit": "deg"}
    ok = motion_gate(asm, {"H": {**joint, "range": [0, 90]}}, default_samples=7)
    assert ok["pass"] and ok["findings"] == [], ok["findings"]
    assert ok["groups"][0]["intended_contacts_touching"]["flap|stop"] == {"poses": 1, "first": "H=90deg",
                                                                        "last": "H=90deg"}
    over = motion_gate(asm, {"H": {**joint, "range": [0, 95]}}, default_samples=7)
    f = finding(over, "collision:flap|stop")
    assert f["evidence"]["intended_contact"] is True and f["evidence"]["first_pose"] == "H=95deg"


def test_the_pair_cache_makes_a_rerun_free(tmp_path, flap_wall):
    from cadagent.gates import PairCache
    from cadagent.gates.motion import motion_gate
    asm, _ = flap_wall
    joints = {"I1": revolute((0, 60), intended_contacts=[("flap", "stop")])}
    cold = motion_gate(asm, joints, cache=PairCache(tmp_path))
    warm = motion_gate(asm, joints, cache=PairCache(tmp_path))
    assert cold["stats"]["kernel_queries"] > 0 and cold["stats"]["cache_hits"] == 0
    assert warm["stats"]["kernel_queries"] == 0 and warm["stats"]["cache_hits"] == cold["stats"]["kernel_queries"]
    strip = lambda v: {k: v[k] for k in ("checks", "groups", "pass")}          # noqa: E731
    assert strip(cold) == strip(warm)


def test_containment_is_checked_per_pose_when_a_joint_moves_the_container(tmp_path):
    """A cup on a slider carries its cavity away from a ball that stays where it was modelled."""
    cq = _cq()
    from cadagent.gates import Assembly
    from cadagent.gates.motion import motion_gate
    asm = Assembly()
    asm.add("rail", cq.Solid.makeBox(80, 20, 2, cq.Vector(-10, -10, -2)))
    cup = cq.Solid.makeBox(20, 20, 12, cq.Vector(-10, -10, 0)).cut(cq.Solid.makeBox(16, 16, 10, cq.Vector(-8, -8, 2)))
    asm.add("cup", cup)
    asm.add_cavity("cup_void", cq.Solid.makeBox(16, 16, 10, cq.Vector(-8, -8, 2)), part="cup")
    asm.add("ball", cq.Solid.makeSphere(3, cq.Vector(0, 0, 5), angleDegrees1=-90))
    joints = {"S": {"kind": "slider", "moving": "cup", "fixed": "rail", "axis": ((0, 0, 0), (1, 0, 0)),
                    "range": [0, 30], "unit": "mm", "samples": 4}}
    v = motion_gate(asm, joints, ignore_pairs=[("cup", "ball")],
                    contains=[{"container": "cup", "cavity": "cup_void", "what": "ball", "count": 1}],
                    containment_options={"support": "off"}, out=tmp_path / "motion.json")
    inside = [f for f in v["findings"] if f["id"].startswith("containment@S/") and f["id"].endswith("ball:inside")]
    assert {f["id"].split("/")[1] for f in inside} == {"S=10mm", "S=20mm", "S=30mm"}, v["findings"]
    assert v["pass"] is False and (tmp_path / "motion.json").exists()
    home = [c for c in v["checks"] if c["id"].startswith("containment@S/S=0mm/")]
    assert home and all(c["status"] == "pass" for c in home)


# ----------------------------------------------------------------------------- the gate bench (seed 7)

def _bench():
    _cq()
    import importlib.util
    import sys
    from pathlib import Path
    path = Path(__file__).resolve().parent / "fixtures" / "gate_bench" / "build.py"
    if "gate_bench_build" not in sys.modules:
        spec = importlib.util.spec_from_file_location("gate_bench_build", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["gate_bench_build"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["gate_bench_build"]


def test_bench_seed_7_onset_brackets_the_analytic_contact_angle():
    from cadagent.gates.motion import motion_gate
    gb = _bench()
    clean = motion_gate(gb.build().assembly)
    assert clean["pass"] and clean["findings"] == []
    (g,) = clean["groups"]
    assert g["density"][0]["samples"] == 12 and g["density"][0]["step"] == pytest.approx(40 / 11, abs=1e-6)
    assert g["intended_contacts_touching"]["arm|stop"]["first"] == "I-pin-arm=0deg"    # resting on its stop
    assert g["at"]["pair"] == ["arm", "frame"] and g["min_clearance_mm"] > 1.5
    v = motion_gate(gb.build("flap_hits_frame").assembly)
    (f,) = [x for x in v["findings"] if x["id"].startswith("collision:")]
    assert f["parts"] == ["arm", "frame"]
    onset, hit = f["evidence"]["onset"], gb.arm_frame_contact_deg()
    # the onset is where shared volume first exceeds overlap_mm3: just past the corner's first touch (a 0.001 mm3
    # wedge of a corner 45 mm out is about 0.02 deg deep)
    assert hit <= onset["hit"] and onset["clear"] - hit < 0.05 and onset["hit"] - onset["clear"] < 0.025, (onset, hit)
    assert f["evidence"]["last_clear_gap_mm"] > 0 and f["evidence"]["overlap_mm3"] > 0


def test_motion_from_build_reads_the_dossier_gates_and_lists_unmoved_contents():
    from types import SimpleNamespace
    from cadagent.gates.motion import motion_from_build
    gb = _bench()
    bench = gb.build()
    gates = SimpleNamespace(motion_samples=5, intended_overlaps=[], ignore_pairs=[], touch_tol_mm=0.01)
    v = motion_from_build(bench.result, SimpleNamespace(gates=gates, parts={}), bench.declarations)
    assert v["pass"] and v["findings"] == [], v["findings"]
    assert v["groups"][0]["density"][0]["samples"] == 5 and v["limits"]["default_samples"] == 5
    assert v["not_checked"] == ["contains ball in hopper_cavity: not moved by I-pin-arm"]
    assert len(v["exclusions"]) == 4                     # the screws' thread envelopes, carried from the extras
