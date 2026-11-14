"""Motion-range interference gate (T7).

The first half runs the gate's core (``run_motion``) on a box world with no CAD kernel: the rules
for sampling, chains, intended contacts, witnesses and density, in core CI. The second half runs
``motion_gate`` on CadQuery solids (skipped without the ``cad`` extra): the plan's flap that clears
at 0 deg and hits a wall, a stop contact at the range end, the pair cache, containment per pose, and a
parallelogram lift whose upper arm and cradle follow its lower arm (driven joints, issue #581). The last section is
repeating poses (#724): a shaft and a lugged wheel measured from their solids, and the wheels that only look symmetric.
"""

from __future__ import annotations

import math

import pytest

from cadagent.review.gates import Relation
from cadagent.review.gates.cache import matrix_key
from cadagent.review.gates.motion import (IDENTITY, Closure, Follow, Joint, World, _phase, box_distance, moved_box,
                                          resolve_follows, rotation, run_motion, translation)


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
    out = {"kind": "slider", "moving": moving, "fixed": fixed, "axis": {"origin": [0, 0, 0], "direction": direction},
           "range": list(rng) if rng is not None else None, "unit": "mm", **kw}
    return out


def finding(v, prefix):
    hits = [f for f in v["findings"] if f["id"].startswith(prefix)]
    assert hits, f"no finding {prefix!r}: {[f['id'] for f in v['findings']]}"
    return hits[0]


# a carriage on a rail (the fixed part), a wall at x = 40
RAIL = {"rail": (0, 0, -2, 100, 10, 0), "carriage": (0, 0, 0, 10, 10, 10), "wall": (40, 0, 0, 45, 10, 20)}


# ----------------------------------------------------------------------------- transforms and joints

def test_rotation_is_right_handed_about_an_offset_axis():
    m = rotation((1, 0, 0), (0, 0, 1), 90)
    from cadagent.review.gates.motion import _apply
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

def test_joint_ranges_must_match_the_kind():
    ax = ((0, 0, 0), (0, 0, 1))
    with pytest.raises(ValueError, match="needs a range in mm"):
        Joint.coerce("C", {"kind": "cylindrical", "moving": "a", "fixed": "b", "axis": ax, "range_deg": [0, 9]})
    with pytest.raises(ValueError, match="needs a range in deg"):
        Joint.coerce("R", {"kind": "revolute", "moving": "a", "fixed": "b", "axis": ax, "range": [0, 9], "unit": "mm"})
    # an explicit range_mm wins over a unit-less range, which a slider reads in mm
    j = Joint.coerce("S", {"kind": "slider", "moving": "a", "fixed": "b", "axis": ax, "range": [0, 9],
                           "range_mm": [0, 3]})
    assert (j.dofs[0].lo, j.dofs[0].hi) == (0, 3)
    still = Joint.coerce("Z", {"kind": "slider", "moving": "a", "fixed": "b", "axis": ax, "range_mm": [2, 2]})
    assert still.dofs[0].samples == 1 and still.dofs[0].values() == [2.0] and still.dofs[0].step() == 0




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
    assert v["groups"][0]["min_clearance_mm"] == 0 and v["groups"][0]["at"]["pair"] == ["carriage", "wall"]
    still = run_motion(BoxWorld(RAIL), {"J": slider("carriage", "rail", (5, 5))})
    assert [f["id"] for f in still["findings"]] == ["range:J:mm"] and still["groups"][0]["poses"] == 1
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
    ev = f["evidence"]
    assert ev["first_pose"] == "X=30mm,Z=20mm" and ev["last_clear_pose"] == "X=20mm,Z=20mm"    # a grid neighbour
    assert ev["onset"]["joint"] == "X" and ev["onset"]["clear"] <= 20 < ev["onset"]["hit"] < 20.1
    assert ev["onset"]["others"] == "Z=20mm"
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


def test_a_parents_travel_per_step_counts_what_its_child_carries_out():
    """The turret's step moves the arm's tip furthest when the arm is slid out: the radius is taken over the
    sampled poses, not the home pose (review of #52)."""
    boxes = {"base": (-20, -20, -2, 20, 20, 0), "turret": (-4, -4, 0, 4, 4, 4), "arm": (4, -2, 0, 14, 2, 4)}
    joints = {"T": {"kind": "revolute", "moving": "turret", "fixed": "base", "axis": ((0, 0, 0), (0, 0, 1)),
                    "range": [0, 90], "unit": "deg", "samples": 4},
              "A": slider("arm", "turret", (0, 50), samples=3)}
    (g,) = run_motion(BoxWorld(boxes), joints)["groups"]
    turn = g["density"][0]
    assert turn["max_radius_mm"] == pytest.approx(math.hypot(64, 2), abs=1e-3)
    assert turn["max_travel_per_step_mm"] == pytest.approx(math.radians(30) * math.hypot(64, 2), abs=1e-3)


def test_a_collision_below_home_gets_its_clear_neighbour_and_onset():
    boxes = {"rail": (-60, 0, -2, 60, 10, 0), "carriage": (0, 0, 0, 10, 10, 10), "wall": (-25, 0, 0, -20, 10, 20)}
    v = run_motion(BoxWorld(boxes), {"J": slider("carriage", "rail", (-30, 30), samples=13)})
    ev = finding(v, "collision:carriage|wall")["evidence"]
    assert ev["first_pose"] == "J=-25mm" and ev["last_clear_pose"] == "J=-20mm"   # moving out from home at 0
    assert ev["point_a"] is not None and -20 + 1e-9 >= ev["onset"]["clear"] > ev["onset"]["hit"] > -20.1


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
    three = run_motion(BoxWorld(CHAIN), {**CHAIN_JOINTS, "Y": slider("beam", "rail", (0, 1))},
                       samples={"X": 30, "Z": 30, "Y": 30}, combine=[["X", "Y"]], max_poses=1000)
    assert three["groups"][0]["poses"] == 1000                  # 10 per axis: 1000 ** (1/3) is not rounded down to 9


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


# ----------------------------------------------------------------------------- driven (mimic) joints

# two carriages nose to tail on one rail, 2 mm apart, and a wall 23 mm ahead of the front one
TRAIN = {"rail": (0, 0, -2, 100, 10, 0), "rear": (0, 0, 0, 10, 10, 10), "front": (12, 0, 0, 22, 10, 10),
         "wall": (45, 0, 0, 50, 10, 20)}


def test_a_follow_law_is_read_from_every_spelling_and_composed_down_to_the_sampled_joint():
    assert Follow.coerce(None) is None
    assert Follow.coerce("A") == Follow("A", 1.0, 0.0) == Follow.coerce(("A",)) == Follow.coerce({"joint": "A"})
    assert Follow.coerce(("A", -1)) == Follow("A", -1.0, 0.0)
    assert Follow.coerce(["A", 2, 5]) == Follow("A", 2.0, 5.0) == Follow.coerce(Follow("A", 2, 5).to_dict())
    assert Follow("A", 2, 5).of(10) == 25
    for bad in (("A", 0), ("A", 1, 2, 3), ("A", "x"), ("", 1), (3, 1), ("A", True), ("A", float("nan")),
                {"joint": "A", "ratio": 2}, {"multiplier": 2}, 7):
        with pytest.raises(ValueError):
            Follow.coerce(bad)
    # C = 2 B + 1 and B = -3 A + 10, so C = -6 A + 21; a slider may follow a revolute joint and the reverse
    laws, errors = resolve_follows({"A": {"kind": "revolute"}, "B": {"kind": "slider", "follows": ("A", -3, 10)},
                                    "C": {"follows": ("B", 2, 1)}, "D": {"kind": "fixed"}})
    assert errors == {} and laws == {"B": Follow("A", -3.0, 10.0), "C": Follow("A", -6.0, 21.0)}


def test_the_ways_a_joint_cannot_follow_are_each_named():
    _, errors = resolve_follows({
        "A": {"kind": "revolute"}, "cyl": {"kind": "cylindrical"}, "ball": {"kind": "ball"},
        "self": {"follows": "self"}, "lost": {"follows": "nowhere"}, "zero": {"follows": ("A", 0)},
        "on-cyl": {"follows": "cyl"}, "cyl-follows": {"kind": "cylindrical", "follows": "A"},
        "ball-follows": {"kind": "ball", "follows": "A"}, "after-lost": {"follows": "lost"},
        "x": {"follows": "y"}, "y": {"follows": "z"}, "z": {"follows": "x"}, "tail": {"follows": "x"}})
    assert errors["self"] == "it follows itself"
    assert errors["lost"] == "it follows 'nowhere', which is not a declared joint"
    assert "multiplier 0" in errors["zero"]
    assert errors["on-cyl"].startswith("it follows cyl, a cylindrical joint")
    assert errors["cyl-follows"].startswith("a cylindrical joint cannot follow another")
    assert errors["ball-follows"].startswith("a ball joint cannot follow another")
    assert errors["after-lost"] == "it follows lost, which cannot follow: " + errors["lost"]
    assert errors["x"] == "joints x -> y -> z -> x follow each other in a loop"
    assert all("follow each other in a loop" in errors[k] for k in ("y", "z", "tail"))
    assert sorted(errors) == sorted(["self", "lost", "zero", "on-cyl", "cyl-follows", "ball-follows", "after-lost",
                                     "x", "y", "z", "tail"])


def test_independent_joints_of_one_linkage_collide_falsely_and_a_follower_takes_the_real_path():
    """The front carriage is coupled to the rear one (a drawbar). Sampled as two free joints the rear one drives
    into the front one at rest; with the front following the rear they move as one and nothing is hit."""
    free = run_motion(BoxWorld(TRAIN), {"J-rear": slider("rear", "rail", (0, 20)),
                                        "J-front": slider("front", "rail", (0, 20))})
    assert not free["pass"]
    assert finding(free, "collision:front|rear")["evidence"]["first_pose"] .startswith("J-rear=3.636")
    world = BoxWorld(TRAIN)
    v = run_motion(world, {"J-rear": slider("rear", "rail", (0, 20)),
                           "J-front": {**slider("front", "rail", (0, 20)), "follows": "J-rear"}})
    assert v["pass"] and v["findings"] == [], v["findings"]
    assert [g["id"] for g in v["groups"]] == ["J-front+J-rear"]                # one group, one sampled axis
    g = v["groups"][0]
    assert g["poses"] == 12 and [d["joint"] for d in g["density"]] == ["J-rear"]
    assert v["stats"] == {**v["stats"], "joints": 2, "driven_joints": 1, "poses": 12}
    # the verdict says which joint was driven, by what, over which values, and that the ratio is a declaration
    row = v["driven"]["J-front"]
    assert row == g["driven"][0]
    assert (row["joint"], row["follows"], row["driver"], row["multiplier"], row["offset"], row["range"],
            row["declared_range"]) == ("J-front", "J-rear", "J-rear", 1.0, 0.0, [0.0, 20.0], [0.0, 20.0])
    assert row["law"] == "J-front = 1 × J-rear"
    check = next(c for c in v["checks"] if c["id"] == "follows:J-front")
    assert check["status"] == "pass" and "inside its declared range 0..20 mm" in check["message"]
    assert check["message"].endswith("The ratio is declared, not solved")
    assert "driven, not sampled: J-front = 1 × J-rear" in next(c for c in v["checks"]
                                                               if c["id"] == "motion:J-front+J-rear")["message"]
    assert g["density"][0]["drives"] == [{"joint": "J-front", "axis": "slide", "unit": "mm", "range": [0.0, 20.0],
                                          "step": pytest.approx(20 / 11, abs=1e-6),
                                          "max_travel_per_step_mm": pytest.approx(20 / 11, abs=1e-3)}]
    # the two move side by side, so no point travels further per step than either does alone
    assert g["density"][0]["max_travel_per_step_mm"] == pytest.approx(20 / 11, abs=1e-3)
    assert v["not_checked"] == ["loop closure of J-front = 1 × J-rear: the ratio is declared, not solved, and no "
                                "closes point measures it"]
    assert any("loop closure is not solved" in a for a in v["assumptions"])
    # the two are still checked against each other: they keep their 2 mm (boxes apart, so no kernel query)
    assert g["unmeasured_at"]["pair"] == ["front", "rear"] and g["unmeasured_gap_at_least_mm"] == 2.0
    assert set(world.calls) == {("front", "rail"), ("rail", "rear")}


def test_a_real_collision_on_the_coupled_path_is_found_with_its_onset():
    v = run_motion(BoxWorld(TRAIN), {"J-rear": slider("rear", "rail", (0, 30)),
                                     "J-front": {**slider("front", "rail", None), "follows": "J-rear"}})
    assert not v["pass"]
    assert [f["id"] for f in v["findings"] if f["id"].startswith("collision:")] == ["collision:front|wall"]
    onset = finding(v, "collision:front|wall")["evidence"]["onset"]
    assert onset["joint"] == "J-rear" and onset["clear"] <= 23 <= onset["hit"]       # the driver's value at the hit
    assert v["driven"]["J-front"]["declared_range"] is None
    assert "it declares no range of its own" in next(c for c in v["checks"] if c["id"] == "follows:J-front")["message"]


def test_a_follower_takes_multiplier_times_driver_plus_offset_about_its_own_axis():
    """The lift rises 2 mm for each mm the wedge slides, from 3 mm up: a roof 30 mm above it is met at wedge = 13.5."""
    boxes = {"bed": (0, 0, -2, 100, 10, 0), "wedge": (0, 0, 0, 10, 10, 5), "lift": (60, 0, 0, 70, 10, 5),
             "roof": (60, 0, 35, 70, 10, 40)}
    joints = {"J-wedge": slider("wedge", "bed", (0, 12)),
              "J-lift": {**slider("lift", "bed", (0, 30), direction=(0, 0, 1)), "follows": ("J-wedge", 2, 3)}}
    ok = run_motion(BoxWorld(boxes), joints)
    assert ok["pass"], ok["findings"]
    assert ok["driven"]["J-lift"]["range"] == [3.0, 27.0] and ok["driven"]["J-lift"]["law"] == "J-lift = 2 × J-wedge + 3 mm"
    assert ok["groups"][0]["unmeasured_gap_at_least_mm"] == pytest.approx(3.0)     # 35 - (5 + 27), at the range end
    joints["J-wedge"] = slider("wedge", "bed", (0, 20))
    bad = run_motion(BoxWorld(boxes), joints)
    onset = finding(bad, "collision:lift|roof")["evidence"]["onset"]
    assert onset["clear"] <= 13.5 <= onset["hit"]
    # and the follower now leaves the range it declares: 2 × 20 + 3 = 43 mm against 0..30
    f = finding(bad, "follows:J-lift")
    assert f["status"] == "fail" and "3..43 mm" in f["message"] and "outside its declared range 0..30 mm" in f["message"]
    assert f["evidence"]["range"] == [3.0, 43.0] and f["evidence"]["declared_range"] == [0.0, 30.0]


def test_a_follower_that_rides_on_its_driver_and_one_combined_with_a_free_joint():
    """A two-stage telescope: stage 2 rides on stage 1 and extends as far again, so it travels twice as far."""
    boxes = {"base": (0, 0, -2, 100, 10, 0), "s1": (0, 0, 0, 30, 10, 5), "s2": (0, 0, 5, 30, 10, 10),
             "post": (75, 0, 5, 80, 10, 30), "gate": (90, 0, 5, 95, 10, 30)}
    joints = {"J1": slider("s1", "base", (0, 20)), "J2": {**slider("s2", "s1", None), "follows": "J1"}}
    ok = run_motion(BoxWorld(boxes), joints)
    assert ok["pass"] and ok["groups"][0]["joints"] == ["J1", "J2"] and ok["groups"][0]["poses"] == 12
    assert ok["groups"][0]["unmeasured_gap_at_least_mm"] == pytest.approx(5.0)     # 75 - (30 + 2 × 20)
    d = ok["groups"][0]["density"][0]                   # stage 2 rides on stage 1: its travel adds to its carrier's
    assert d["max_travel_per_step_mm"] == pytest.approx(2 * 20 / 11, abs=1e-3)
    bad = run_motion(BoxWorld(boxes), {**joints, "J1": slider("s1", "base", (0, 25))})
    onset = finding(bad, "collision:post|s2")["evidence"]["onset"]
    assert onset["clear"] <= 22.5 <= onset["hit"]                                  # 30 + 2 x = 75
    # combined with a free joint, the follower is still computed in every pose of the grid, not sampled
    boxes2 = {k: v for k, v in boxes.items() if k != "post"}
    joints2 = {**joints, "J-gate": slider("gate", "base", (-30, 0))}
    v = run_motion(BoxWorld(boxes2), joints2, combine=[["J1", "J-gate"]])
    g = v["groups"][0]
    assert g["id"] == "J-gate+J1+J2" and g["poses"] == 144 and [d["joint"] for d in g["density"]] == ["J-gate", "J1"]
    f = finding(v, "collision:gate|s2")                 # the gate slid back 30 meets stage 2 at 30 + 2 x = 60
    assert f["evidence"]["first_pose"].startswith("J-gate=")
    assert "combination:" not in " ".join(c["id"] for c in v["checks"])


def test_a_step_cap_counts_the_followers_faster_travel():
    joints = {"J1": slider("rear", "rail", (0, 6)),
              "J2": {**slider("front", "rail", None), "follows": ("J1", 3)}}
    v = run_motion(BoxWorld({k: b for k, b in TRAIN.items() if k != "wall"}), joints, default_samples=3, max_step_mm=2)
    d = v["groups"][0]["density"][0]
    assert d["samples"] == 10 and d["drives"][0]["step"] == pytest.approx(2.0)      # 18 mm of follower travel / 2


def test_a_joint_that_cannot_be_driven_fails_the_gate_and_takes_its_followers_with_it():
    base = {"J-rear": slider("rear", "rail", (0, 5))}
    v = run_motion(BoxWorld(TRAIN), {**base, "J-front": {**slider("front", "rail", None), "follows": "J-nowhere"}})
    f = finding(v, "joint:J-front")
    assert not v["pass"] and f["message"] == ("joint J-front cannot be driven: it follows 'J-nowhere', which is not "
                                              "a declared joint")
    assert v["driven"] == {} and v["stats"]["joints"] == 1                 # the driver alone is still sampled
    loop = run_motion(BoxWorld(TRAIN), {"J-rear": {**slider("rear", "rail", None), "follows": "J-front"},
                                        "J-front": {**slider("front", "rail", None), "follows": "J-rear"}})
    assert finding(loop, "joint:J-front")["message"].endswith("joints J-front -> J-rear -> J-front follow each "
                                                              "other in a loop")
    assert finding(loop, "joint:J-rear") and loop["stats"]["joints"] == 0
    cyl = {"kind": "cylindrical", "moving": "front", "fixed": "rail", "axis": ((0, 0, 0), (1, 0, 0)),
           "range": [0, 10], "unit": "deg", "range_mm": [0, 5], "follows": "J-rear"}
    assert "a cylindrical joint cannot follow another" in finding(run_motion(BoxWorld(TRAIN), {**base, "J-front": cyl}),
                                                                 "joint:J-front")["message"]
    # the driver names a part that is not there: it cannot be posed, so neither can what follows it
    gone = run_motion(BoxWorld(TRAIN), {"J-rear": slider("ghost", "rail", (0, 5)),
                                        "J-front": {**slider("front", "rail", None), "follows": "J-rear"}})
    assert finding(gone, "joint:J-front")["message"] == "joint J-front follows joint J-rear, which cannot be posed"
    # a follower's range must be in its own unit
    wrong = {**slider("front", "rail", None), "range": [0, 5], "unit": "deg", "follows": "J-rear"}
    assert "it needs mm or none" in finding(run_motion(BoxWorld(TRAIN), {**base, "J-front": wrong}),
                                            "joint:J-front")["message"]


def test_a_closes_point_measures_whether_the_declared_ratio_keeps_the_loop_together():
    """A drawbar pins the two carriages at (11, 5, 5). At ratio 1 the pin stays one point; at 0.5 its two copies
    drift 10 mm apart by the end of a 20 mm stroke."""
    def joints(ratio, **closes):
        pin = {"parts": ("front", "rear"), "at": (11, 5, 5), **closes}
        return {"J-rear": slider("rear", "rail", (0, 20)),
                "J-front": {**slider("front", "rail", None), "follows": ("J-rear", ratio), "closes": [pin]}}
    ok = run_motion(BoxWorld(TRAIN), joints(1))
    assert ok["pass"] and ok["not_checked"] == []
    row = ok["groups"][0]["closures"][0]
    assert row["id"] == "closure:J-front:front|rear" and row["status"] == "pass" and row["max_apart_mm"] == 0.0
    bad = run_motion(BoxWorld(TRAIN), joints(0.5))
    f = finding(bad, "closure:J-front:front|rear")
    assert f["status"] == "fail" and f["evidence"]["max_apart_mm"] == pytest.approx(10.0)
    assert f["evidence"]["worst_pose"] == "J-rear=20mm" and "do not keep the loop closed" in f["message"]
    assert run_motion(BoxWorld(TRAIN), joints(0.5, tol_mm=12))["groups"][0]["closures"][0]["status"] == "pass"
    lost = run_motion(BoxWorld(TRAIN), joints(1, parts=("front", "ghost")))
    assert "ghost is not in the assembly" in finding(lost, "closure:J-front:front|ghost")["message"]
    assert Closure.coerce_all({"parts": ["a", "b"], "at": [1, 2, 3]}) == [Closure(("a", "b"), (1.0, 2.0, 3.0), 0.1)]
    for wrong in ({"parts": ("a", "a"), "at": (0, 0, 0)}, {"parts": ("a", "b"), "at": (0, 0)},
                  {"parts": ("a", "b"), "at": (0, 0, 0), "tol_mm": 0}, {"parts": ("a", "b")},
                  {"parts": ("a", "b"), "at": (0, 0, 0), "slack": 1}):
        with pytest.raises(ValueError):
            Closure.coerce_all(wrong)


def test_a_closes_point_is_measured_wherever_its_parts_move_and_refused_when_it_can_measure_nothing():
    """Review of #582: the point is carried by its parts, not by the joint that happens to state it."""
    boxes = {**TRAIN, "gate": (90, 0, 0, 95, 10, 20), "hook": (22, 0, 0, 24, 10, 5), "badge": (0, 0, 10, 4, 4, 12)}
    bodies = {"hook": "front"}                                    # the hook is fastened to the front carriage
    pin = {"parts": ("front", "rear"), "at": (11, 5, 5)}
    train = {"J-rear": slider("rear", "rail", (0, 20)),
             "J-front": {**slider("front", "rail", None), "follows": ("J-rear", 0.5)}}
    # stated on a free joint of another group, and on a fixed joint: still measured in the group that moves it
    for holder in ({"J-gate": {**slider("gate", "rail", (0, 3)), "closes": pin}},
                   {"J-badge": {"kind": "fixed", "moving": "badge", "fixed": "rear",
                                "axis": ((0, 0, 0), (0, 0, 1)), "closes": [pin]}}):
        v = run_motion(BoxWorld(boxes, bodies), {**train, **holder})
        jid = next(iter(holder))
        f = finding(v, f"closure:{jid}:front|rear")
        assert f["status"] == "fail" and f["evidence"]["max_apart_mm"] == pytest.approx(10.0)
        assert f["evidence"]["group"] == "J-front+J-rear" and v["closures"][0]["worst_pose"] == "J-rear=20mm"
        assert v["not_checked"] == [] or all("loop closure" not in n for n in v["not_checked"])
    # two parts of one body, and two parts nothing moves: neither measures anything, and neither hides the ratio
    one_body = run_motion(BoxWorld(boxes, bodies), {**train, "J-front": {
        **train["J-front"], "closes": {"parts": ("front", "hook"), "at": (22, 5, 2)}}})
    assert "both are in one body (front)" in finding(one_body, "closure:J-front:front|hook")["message"]
    still = run_motion(BoxWorld(boxes, bodies), {**train, "J-front": {
        **train["J-front"], "closes": {"parts": ("rail", "wall"), "at": (45, 5, 0)}}})
    assert "no sampled joint moves either part" in finding(still, "closure:J-front:rail|wall")["message"]
    for v in (one_body, still):
        assert not v["pass"] and v["not_checked"] == ["loop closure of J-front = 0.5 × J-rear: the ratio is declared, "
                                                      "not solved, and no closes point measures it"]
    # a driven joint that carries both parts moves them together: the point says nothing about its ratio
    stack = {"base": (0, 0, -2, 100, 10, 0), "sled": (0, 0, 0, 40, 10, 2), "p": (0, 0, 2, 10, 10, 6),
             "q": (12, 0, 2, 22, 10, 6), "lead": (60, 0, 0, 70, 10, 5)}
    v = run_motion(BoxWorld(stack), {
        "A": slider("lead", "base", (0, 10)), "D": {**slider("sled", "base", None), "follows": ("A", 0.37)},
        "P": slider("p", "sled", (0, 1), direction=(0, 0, 1)),
        "Q": {**slider("q", "sled", None, direction=(0, 0, 1)), "follows": "P",
              "closes": {"parts": ("p", "q"), "at": (11, 5, 4)}}})
    assert v["closures"][0]["status"] == "pass"
    assert v["not_checked"] == ["loop closure of D = 0.37 × A: the ratio is declared, not solved, and no closes "
                                "point measures it"]                    # Q's ratio is measured, D's is not
    # a part with instances in several bodies has no one place for the point
    multi = {**TRAIN, "bolt#0": (2, 2, 10, 4, 4, 12), "bolt#1": (14, 2, 10, 16, 4, 12)}
    v = run_motion(BoxWorld(multi, {"bolt#0": "rear", "bolt#1": "front"}), {**train, "J-front": {
        **train["J-front"], "closes": {"parts": ("bolt", "rail"), "at": (3, 3, 10)}}})
    assert "bolt has instances in several bodies (front, rear)" in finding(v, "closure:J-front:bolt|rail")["message"]
    with pytest.raises(ValueError):
        Closure.coerce_all({"parts": "ab", "at": (0, 0, 0)})


def test_samples_on_a_driven_joint_are_ignored_with_a_warning():
    joints = {"J-rear": slider("rear", "rail", (0, 5)),
              "J-front": {**slider("front", "rail", None), "follows": "J-rear", "samples": 40}}
    v = run_motion(BoxWorld(TRAIN), joints)
    assert v["pass"] and v["groups"][0]["poses"] == 12
    assert finding(v, "samples:J-front")["status"] == "warn"
    joints["J-front"].pop("samples")
    assert finding(run_motion(BoxWorld(TRAIN), joints, samples={"J-front": 40}), "samples:J-front")


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
    from cadagent.review.gates import Assembly
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
    from cadagent.review.gates.motion import motion_gate
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
    from cadagent.review.gates import Assembly
    from cadagent.review.gates.motion import motion_gate
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
    from cadagent.review.gates import PairCache
    from cadagent.review.gates.motion import motion_gate
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
    from cadagent.review.gates import Assembly
    from cadagent.review.gates.motion import motion_gate
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
    path = Path(__file__).resolve().parents[1] / "fixtures" / "gate_bench" / "build.py"
    if "gate_bench_build" not in sys.modules:
        spec = importlib.util.spec_from_file_location("gate_bench_build", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["gate_bench_build"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["gate_bench_build"]


def test_bench_seed_7_onset_brackets_the_analytic_contact_angle():
    from cadagent.review.gates.motion import motion_gate
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
    from cadagent.review.gates.motion import motion_from_build
    gb = _bench()
    bench = gb.build()
    gates = SimpleNamespace(motion_samples=5, intended_overlaps=[], ignore_pairs=[], touch_tol_mm=0.01)
    v = motion_from_build(bench.result, SimpleNamespace(gates=gates, parts={}), bench.declarations)
    assert v["pass"] and v["findings"] == [], v["findings"]
    assert v["groups"][0]["density"][0]["samples"] == 5 and v["limits"]["default_samples"] == 5
    assert v["not_checked"] == ["contains ball in hopper_cavity: not moved by I-pin-arm"]
    assert len(v["exclusions"]) == 4                     # the screws' thread envelopes, carried from the extras


# ----------------------------------------------------------------------------- a parallelogram lift (driven joints)

def _lift(stop: bool = True):
    """A parallelogram lift in the XZ plane, pivots along Y. Two 100 mm arms pivot on a tower at (0, 0) and
    (0, 50); a cradle is pinned to their far ends at (100, 0) and (100, 50), so it rises without tilting. The
    tower plate, the arms and the cradle plate lie in three layers 1 mm apart; the cradle carries a tine in the
    arms' layer, 7 mm beyond their ends. A stop on the tower hangs over the arms at z = 112."""
    cq = _cq()
    from cadagent.review.gates import Assembly
    asm = Assembly()
    asm.add("tower", cq.Solid.makeBox(20, 10, 70, cq.Vector(-10, -10, -10)))
    asm.add("lower_arm", cq.Solid.makeBox(110, 5, 10, cq.Vector(-5, 1, -5)))
    asm.add("upper_arm", cq.Solid.makeBox(110, 5, 10, cq.Vector(-5, 1, 45)))
    asm.add("cradle", cq.Solid.makeBox(35, 5, 70, cq.Vector(90, 7, -10)).fuse(
        cq.Solid.makeBox(13, 6, 70, cq.Vector(112, 1, -10))))
    if stop:
        asm.add("stop", cq.Solid.makeBox(50, 5, 10, cq.Vector(40, 1, 112)))
    return asm


def _lift_joints(top: float, coupled: bool, cradle: float = -1, **on_cradle):
    up = (0, -1, 0)                                         # positive angles raise the +X end
    upper = {"follows": "I-lower"} if coupled else {}
    carried = {"follows": ("I-lower", cradle), **on_cradle} if coupled else {}
    return {"I-lower": {"kind": "revolute", "parts": ("lower_arm", "tower"), "axis": ((0, 0, 0), up),
                        "range_deg": (0, top)},
            "I-upper": {"kind": "revolute", "parts": ("upper_arm", "tower"), "axis": ((0, 0, 50), up),
                        "range_deg": (0, top), **upper},
            "I-cradle": {"kind": "revolute", "parts": ("cradle", "lower_arm"), "axis": ((100, 0, 0), up),
                         "range_deg": (-top, 0), **carried}}


def test_a_parallelogram_collides_falsely_as_free_joints_and_is_clear_as_one_degree_of_freedom():
    from cadagent.review.gates.motion import motion_gate
    free = motion_gate(_lift(), _lift_joints(30, coupled=False), default_samples=5)
    hits = sorted(f["id"] for f in free["findings"] if f["id"].startswith("collision:"))
    assert not free["pass"] and "collision:lower_arm|upper_arm" in hits and "collision:cradle|upper_arm" in hits
    assert any(c["id"].startswith("combination:") for c in free["checks"])     # and it cannot say how they combine
    pin = {"parts": ("cradle", "upper_arm"), "at": (100, 0, 50)}
    v = motion_gate(_lift(), _lift_joints(30, coupled=True, closes=pin), default_samples=5)
    assert v["pass"] and v["findings"] == [], v["findings"]
    g, = v["groups"]
    assert g["joints"] == ["I-lower", "I-upper", "I-cradle"] and g["poses"] == 5
    assert [d["joint"] for d in g["density"]] == ["I-lower"]
    assert [(d["joint"], d["driver"], d["multiplier"], d["range"]) for d in g["driven"]] == [
        ("I-upper", "I-lower", 1.0, [0.0, 30.0]), ("I-cradle", "I-lower", -1.0, [-30.0, 0.0])]
    assert g["closures"][0]["status"] == "pass" and g["closures"][0]["max_apart_mm"] < 1e-6
    # the cradle rose without tilting: nothing comes nearer than the 1 mm between the layers
    assert g["min_clearance_mm"] == pytest.approx(1.0, abs=1e-6)
    assert v["not_checked"] == []


def test_a_real_collision_along_the_coupled_path_is_still_found():
    """Raised to 45 deg, the upper arm's top far corner (105 mm along, 5 mm above its pivot line) runs into the
    stop above it where 50 + 105 sin(a) + 5 cos(a) = 112, between 33 and 34 deg."""
    from cadagent.review.gates.motion import motion_gate
    v = motion_gate(_lift(), _lift_joints(45, coupled=True), default_samples=10)
    hits = sorted(f["id"] for f in v["findings"] if f["id"].startswith("collision:"))
    assert not v["pass"] and "collision:stop|upper_arm" in hits
    assert "collision:lower_arm|upper_arm" not in hits and "collision:cradle|upper_arm" not in hits
    f = finding(v, "collision:stop|upper_arm")
    onset = f["evidence"]["onset"]
    hit = next(a / 100 for a in range(0, 4500) if 50 + 105 * math.sin(math.radians(a / 100))
               + 5 * math.cos(math.radians(a / 100)) >= 112)
    assert 33 < hit < 34 and onset["joint"] == "I-lower"
    assert onset["clear"] - 0.1 <= hit <= onset["hit"] + 0.1, (onset, hit)


def test_a_closes_point_on_the_axis_of_the_only_joint_between_its_parts_is_refused():
    """The cradle's own pivot on the lower arm stays one point whatever the cradle's ratio: it measures nothing."""
    from cadagent.review.gates.motion import motion_gate
    for at in ((100, 0, 0), (100, 5, 0)):
        pivot = {"parts": ("cradle", "lower_arm"), "at": at}
        v = motion_gate(_lift(stop=False), _lift_joints(20, coupled=True, cradle=3, closes=pivot), default_samples=3)
        f = finding(v, "closure:I-cradle:cradle|lower_arm")
        assert f["status"] == "fail" and "lies on the axis of I-cradle, the only joint between the two" in f["message"]
        assert any(n.startswith("loop closure of I-cradle = 3 × I-lower") for n in v["not_checked"])


def test_a_wrong_ratio_pulls_the_closing_pin_apart():
    """The cradle declared to turn with the lower arm, not against it: the pin it shares with the upper arm, which
    the declaration never solved, is pulled apart, and the closes point says by how much."""
    from cadagent.review.gates.motion import motion_gate
    pin = {"parts": ("cradle", "upper_arm"), "at": (100, 0, 50)}
    v = motion_gate(_lift(stop=False), _lift_joints(20, coupled=True, cradle=1, closes=pin), default_samples=5)
    f = finding(v, "closure:I-cradle:cradle|upper_arm")
    # the pin on the cradle is 50 mm from the lower pivot and turned 40 deg from where the upper arm holds it
    assert f["status"] == "fail" and f["evidence"]["max_apart_mm"] == pytest.approx(
        2 * 50 * math.sin(math.radians(20)), abs=1e-3)
    assert finding(v, "follows:I-cradle")["status"] == "fail"           # and 0..20 deg leaves its declared -20..0


def test_containment_keeps_other_groups_follower_home_offset():
    cq = _cq()
    from cadagent.review.gates import Assembly
    from cadagent.review.gates.containment import containment_gate
    from cadagent.review.gates.motion import motion_gate
    asm = Assembly()
    asm.add("base", cq.Solid.makeBox(1, 1, 1, cq.Vector(-20, 0, 0)))
    asm.add("driver", cq.Solid.makeBox(1, 1, 1, cq.Vector(-10, 0, 0)))
    cavity = cq.Solid.makeBox(4, 4, 4, cq.Vector(9, -1, -1))
    asm.add("container", cq.Solid.makeBox(6, 6, 6, cq.Vector(8, -2, -2)).cut(cavity))
    asm.add_cavity("void", cavity, part="container")
    asm.add("follower", cq.Solid.makeBox(.5, .5, .5))
    joints = {"C": slider("container", "base", (0, 1)),
              "D": slider("driver", "base", (0, 1)),
              "F": {**slider("follower", "base", None), "follows": ("D", 1, 10)}}
    decls = [{"container": "container", "cavity": "void", "what": "follower", "count": 1}]
    # Independent assembly-frame oracle: explicitly translate both bodies at all four endpoint combinations.
    def tx(x):
        return [[1, 0, 0, x], [0, 1, 0, 0], [0, 0, 1, 0]]
    poses = {f"C{c}D{d}": {"container": tx(c), "follower": tx(10+d)}
             for c in (0, 1) for d in (0, 1)}
    oracle = containment_gate(asm, decls, poses=poses, support="off")
    assert oracle["pass"], oracle["findings"]
    wrong = containment_gate(asm, decls, poses={"missing-offset": {"container": tx(1)}}, support="off")
    assert not wrong["pass"]                       # dropping F's offset is observable, not a vacuous fixture
    v = motion_gate(asm, joints, default_samples=2, contains=decls,
                    containment_options={"support": "off"})
    checks = [c for c in v["checks"] if c["id"].startswith("containment@C/") and c["id"].endswith(":inside")]
    assert len(checks) == 2 and all(c["status"] == "pass" for c in checks), checks


# ----------------------------------------------------------------------------- repeating poses (#724)
#
# A body that a turn about its joint axis leaves unchanged. First the rule on a recording world with no CAD kernel:
# which joints may be shortened, how parts of one body combine, and that the kernel is asked at the equivalent pose.
# Then real solids: a shaft, a lugged wheel, and the wheels that only look symmetric, where a collision at one angle
# of the turn must still be found.

class Sym:
    def __init__(self, order):
        self.order = order

    def to_dict(self):
        return {"order": self.order, "difference_mm3": 0.0005, "boundary_mm": 0.002}


class TurnWorld(World):
    """Every part is a box around the origin (so every pair passes the broad phase) and every pair is apart.
    ``orders`` is each part's symmetry (absent: none); ``posed`` records the transform each relate was asked
    at per body, and ``asked`` the parts whose symmetry was measured."""

    def __init__(self, names, orders=None, bodies=None):
        self.names = list(names)
        self.orders = dict(orders or {})
        self.bodies = dict(bodies or {})
        self.posed = {}
        self.asked = []
        self.relations = 0

    def body(self, key):
        return self.bodies.get(key, key)

    def box(self, key):
        return (-5, -5, -5, 5, 5, 5)

    def relate(self, mats, a, b):
        self.relations += 1
        for body, m in mats.items():
            self.posed.setdefault(body, set()).add(matrix_key(m))
        return Relation(a, b, "apart", gap_mm=0.5, witness={"point_a": [0, 0, 0], "point_b": [0, 0, 0.5]})

    def symmetry(self, key, origin, direction):
        self.asked.append(key)
        return Sym(self.orders[key]) if key in self.orders else None


def turn(moving, fixed, rng=(-180, 180), origin=(0, 0, 0), **kw):
    return {"kind": "revolute", "moving": moving, "fixed": fixed, "axis": {"origin": origin, "direction": (0, 0, 1)},
            "range": list(rng) if rng is not None else None, "unit": "deg", **kw}


def group(v, gid):
    return next(g for g in v["groups"] if g["id"] == gid)


def test_a_phase_is_the_angle_inside_the_first_period():
    assert _phase(75.0, 30.0) == 15.0 and _phase(-30.0, 30.0) == 0.0 and _phase(-10.0, 30.0) == 20.0
    assert _phase(360 / 7 * 3, 360 / 7) == 0.0 and _phase(29.9999999999, 30.0) == 0.0     # float noise at a wrap
    assert _phase(123.4, None) == 0.0                                                    # any angle is the same pose


def test_a_body_of_revolution_is_queried_at_one_pose_and_the_verdict_says_so():
    w = TurnWorld(["frame", "shaft"], {"shaft": 0})
    v = run_motion(w, {"J": turn("shaft", "frame")}, max_step_deg=2)
    assert v["pass"] and v["stats"]["poses"] == 181 and v["stats"]["symmetric_joints"] == 1
    assert w.posed["shaft"] == {matrix_key(IDENTITY)}            # the pose the model was built in
    row = group(v, "J")["density"][0]
    assert row["samples"] == 181 and row["range"] == [-180, 180]                # the sampling itself is unchanged
    assert row["symmetry"]["kind"] == "revolution" and row["symmetry"]["distinct_poses"] == 1
    assert row["symmetry"]["parts"]["shaft"]["difference_mm3"] == 0.0005
    msg = next(c for c in v["checks"] if c["id"] == "motion:J")["message"]
    assert "measures as a body of revolution about the joint axis" in msg
    assert "0.0005 mm3" in msg and "0.002 mm" in msg and "its 181 samples are one pose, queried once" in msg


def test_an_n_fold_body_is_queried_over_one_period():
    w = TurnWorld(["frame", "wheel"], {"wheel": 12})
    v = run_motion(w, {"J": turn("wheel", "frame")}, max_step_deg=2)
    want = {matrix_key(rotation((0, 0, 0), (0, 0, 1), a)) for a in range(0, 30, 2)}
    assert w.posed["wheel"] == want                                             # 0, 2 .. 28 deg: one period
    sym = group(v, "J")["density"][0]["symmetry"]
    assert sym["kind"] == "periodic" and sym["period_deg"] == 30 and sym["distinct_poses"] == 15
    msg = next(c for c in v["checks"] if c["id"] == "motion:J")["message"]
    assert "repeating every 30 deg about the joint axis" in msg
    assert "its 181 samples are 15 distinct poses of one period, each queried once" in msg


def test_samples_that_do_not_divide_the_period_keep_every_distinct_phase():
    """13 samples over a turn are 30 deg apart: on a 7-fold part no two of them are the same pose but the two ends,
    so nothing is dropped. The shortcut only merges poses that are the same."""
    w = TurnWorld(["frame", "wheel"], {"wheel": 7})
    v = run_motion(w, {"J": turn("wheel", "frame")}, default_samples=13)
    assert len(w.posed["wheel"]) == 12 == group(v, "J")["density"][0]["symmetry"]["distinct_poses"]


def test_every_part_of_the_body_has_to_repeat_and_the_period_is_the_one_they_share():
    def distinct(orders):
        w = TurnWorld(["frame", "hub", "rim"], orders, {"hub": "rotor", "rim": "rotor"})
        v = run_motion(w, {"J": turn("hub", "frame")}, max_step_deg=5)
        return len(w.posed["rotor"]), v["stats"]["symmetric_joints"], group(v, "J")["density"][0].get("symmetry")

    assert distinct({"hub": 0, "rim": 0})[0] == 1
    n, joints, sym = distinct({"hub": 0, "rim": 12})                 # a round hub in a 12-lug rim: 30 deg
    assert n == 6 and sym["period_deg"] == 30
    n, joints, sym = distinct({"hub": 8, "rim": 12})                 # 45 and 30 deg repeat together every 90
    assert n == 18 and sym["period_deg"] == 90 and sym["order"] == 4
    assert distinct({"hub": 3, "rim": 2}) == (72, 0, None)           # 120 and 180 deg share only the full turn
    assert distinct({"hub": 0}) == (72, 0, None)                     # the rim is not symmetric: every sample
    assert distinct({}) == (72, 0, None)


def test_a_joint_that_carries_another_is_never_shortened_and_its_leaf_is():
    """The turret carries the arm joint: turning the turret moves the arm's axis, so every turret sample is its own
    pose even if the turret part were round. The arm's own round tool is still one pose per turret pose."""
    w = TurnWorld(["frame", "turret", "tool"], {"turret": 0, "tool": 0})
    joints = {"T": turn("turret", "frame", (0, 90)), "A": turn("tool", "turret", (0, 90), origin=(20, 0, 0))}
    v = run_motion(w, joints, default_samples=4)
    assert "turret" not in w.asked and "tool" in w.asked
    assert v["stats"]["poses"] == 16 and v["stats"]["symmetric_joints"] == 1
    assert len(w.posed["turret"]) == 4 and len(w.posed["tool"]) == 4       # the tool: carried by T, not turned by A
    rows = {r["joint"]: r for r in group(v, "T+A")["density"]}
    assert "symmetry" not in rows["T"] and rows["A"]["symmetry"]["distinct_poses"] == 1


def test_a_follower_and_its_driver_are_each_judged_on_their_own_body():
    joints = {"A": turn("gear_a", "frame", (0, 360)),
              "B": turn("gear_b", "frame", None, origin=(30, 0, 0), follows=("A", -2.0))}
    w = TurnWorld(["frame", "gear_a", "gear_b"], {"gear_b": 0})          # the driven gear is round, the driver is not
    v = run_motion(w, joints, default_samples=13)
    assert len(w.posed["gear_a"]) == 12 and len(w.posed["gear_b"]) == 1
    assert v["stats"]["symmetric_joints"] == 1
    drives = group(v, "A+B")["density"][0]["drives"][0]
    assert drives["joint"] == "B" and drives["symmetry"]["distinct_poses"] == 1 and drives["symmetry"]["samples"] == 13
    assert "B's moving body (1 part) measures as a body of revolution" in \
        next(c for c in v["checks"] if c["id"] == "motion:A+B")["message"]
    w = TurnWorld(["frame", "gear_a", "gear_b"], {"gear_a": 0})          # the other way round
    run_motion(w, joints, default_samples=13)
    assert len(w.posed["gear_a"]) == 1 and len(w.posed["gear_b"]) == 6    # B still takes -2 x A's real value


def test_a_closes_point_on_a_round_body_is_still_measured_at_the_sampled_angle():
    """The kernel is asked about the round crank at one pose, but a point it carries still moves with the turn."""
    w = TurnWorld(["frame", "crank"], {"crank": 0})
    joints = {"J": turn("crank", "frame", (0, 90), closes={"parts": ("crank", "frame"), "at": (10, 0, 0)})}
    v = run_motion(w, joints, default_samples=4)
    closure = v["closures"][0]
    assert closure["status"] == "fail" and closure["max_apart_mm"] == pytest.approx(10 * math.sqrt(2), abs=1e-5)
    assert closure["worst_pose"] == "J=90deg" and len(w.posed["crank"]) == 1


def test_sliders_and_cylindrical_joints_are_not_measured_and_symmetry_can_be_turned_off():
    w = TurnWorld(["frame", "rod", "plunger"], {"rod": 0, "plunger": 0})
    joints = {"S": {"kind": "slider", "moving": "rod", "fixed": "frame", "axis": ((0, 0, 0), (0, 0, 1)),
                    "range": [0, 5], "unit": "mm"},
              "C": {"kind": "cylindrical", "moving": "plunger", "fixed": "frame", "axis": ((0, 0, 0), (0, 0, 1)),
                    "range_deg": [0, 90], "range_mm": [0, 5]}}
    v = run_motion(w, joints, default_samples=3)
    assert w.asked == [] and v["stats"]["symmetric_joints"] == 0 and v["limits"]["symmetry"] is True
    w = TurnWorld(["frame", "shaft"], {"shaft": 0})
    v = run_motion(w, {"J": turn("shaft", "frame")}, default_samples=13, symmetry=False)
    assert w.asked == [] and len(w.posed["shaft"]) == 12 and v["limits"]["symmetry"] is False
    assert "symmetry" not in group(v, "J")["density"][0]
    assert "revolution" not in next(c for c in v["checks"] if c["id"] == "motion:J")["message"]


def test_the_gates_command_accepts_the_option():
    from cadagent.review.gates.run import options_allowed
    assert "symmetry" in options_allowed("motion")


# ----------------------------------------------------------------------------- repeating poses on CadQuery solids

SHAFT_AXIS = ((-50, 0, 0), (0, 0, 1))
WHEEL_AXIS = ((50, 0, 0), (0, 0, 1))


def _shaft(cq):
    """A shaft with a gear drawn as a chamfered disc: a body of revolution about z."""
    body = cq.Workplane("XY").circle(5.0).extrude(40).translate((0, 0, -10))
    return body.union(cq.Workplane("XY").circle(25).extrude(8).translate((0, 0, 2)).edges().chamfer(1))


def _wheel(cq, lugs=12, missing=0, long_lug=False):
    """A hub with ``lugs`` places for a lug reaching 26 mm; ``missing`` leaves the last ones empty, and ``long_lug``
    makes the first reach 29 mm."""
    body = cq.Workplane("XY").circle(5.0).extrude(40).translate((0, 0, -10))
    body = body.union(cq.Workplane("XY").circle(20).extrude(8).translate((0, 0, 2)))
    for i in range(lugs - missing):
        length = 11 if long_lug and i == 0 else 8
        lug = cq.Workplane("XY").box(length, 4, 8, centered=(False, True, False)).translate((18, 0, 2))
        body = body.union(lug.rotate((0, 0, 0), (0, 0, 1), 360 / lugs * i))
    return body


def _machine(cq, wheel, peg_radius=None, peg_deg=200.0):
    """A plate with two bores, the shaft and the wheel in them, a guard 0.5 mm from each, and an optional peg
    ``peg_radius`` from the wheel axis at ``peg_deg``."""
    from cadagent.review.gates import Assembly
    plate = cq.Workplane("XY").box(200, 80, 10, centered=(True, True, False)).translate((0, 0, -10))
    for x in (-50, 50):
        plate = plate.cut(cq.Workplane("XY").circle(5.0).extrude(10).translate((x, 0, -10)))
    asm = Assembly()
    asm.add("housing", plate.val())
    asm.add("shaft", _shaft(cq).translate((-50, 0, 0)).val())
    asm.add("wheel", wheel.translate((50, 0, 0)).val())
    guard = cq.Workplane("XY").box(4, 30, 12, centered=(False, True, False))
    asm.add("guard", guard.translate((-50 - 25.5 - 4, 0, 0)).val())
    asm.add("fender", guard.translate((50 + 29.5, 0, 0)).val())
    if peg_radius is not None:
        t = math.radians(peg_deg)
        asm.add("peg", cq.Workplane("XY").circle(1).extrude(12)
                .translate((50 + peg_radius * math.cos(t), peg_radius * math.sin(t), 0)).val())
    joints = {"shaft": {"kind": "revolute", "moving": "shaft", "fixed": "housing", "axis": SHAFT_AXIS,
                        "range": [-180, 180], "unit": "deg"},
              "wheel": {"kind": "revolute", "moving": "wheel", "fixed": "housing", "axis": WHEEL_AXIS,
                        "range": [-180, 180], "unit": "deg"}}
    return asm, joints


def test_symmetry_is_measured_from_the_solid():
    cq = _cq()
    from cadagent.review.gates.symmetry import Symmetry, rotational_symmetry
    z = ((0, 0, 0), (0, 0, 1))
    shaft = rotational_symmetry(_shaft(cq).val(), *z)
    assert shaft.order == 0 and shaft.period_deg == 0 and len(shaft.angles_deg) == 3
    assert shaft.difference_mm3 <= shaft.limit_mm3 and shaft.boundary_mm <= shaft.limit_mm == 0.01
    wheel = rotational_symmetry(_wheel(cq).val(), *z)
    assert wheel.order == 12 and wheel.period_deg == 30 and wheel.points > 100
    assert rotational_symmetry(_wheel(cq, lugs=7).val(), *z).order == 7
    assert rotational_symmetry(cq.Workplane("XY").box(10, 12, 5).val(), *z).order == 2
    assert rotational_symmetry(cq.Solid.makeSphere(10), *z).order == 0
    # the same solids about another axis, or moved off the axis, are not symmetric
    assert rotational_symmetry(_shaft(cq).val(), (0, 0, 0), (1, 0, 0)) is None
    assert rotational_symmetry(_shaft(cq).translate((0.5, 0, 0)).val(), *z) is None
    assert Symmetry.from_dict(wheel.to_dict()) == wheel


def test_solids_that_only_look_symmetric_are_not():
    cq = _cq()
    from cadagent.review.gates.symmetry import rotational_symmetry
    z = ((0, 0, 0), (0, 0, 1))
    disc = cq.Workplane("XY").circle(20).extrude(5)
    assert rotational_symmetry(_wheel(cq, missing=1).val(), *z) is None                  # one lug missing
    assert rotational_symmetry(_wheel(cq, long_lug=True).val(), *z) is None              # one lug 3 mm longer
    hole = disc.cut(cq.Workplane("XY").circle(1).extrude(5).translate((10, 0, 0)))
    assert rotational_symmetry(hole.val(), *z) is None                                   # an off-axis hole
    keyway = cq.Workplane("XY").circle(5).extrude(30).cut(
        cq.Workplane("XY").box(2, 2, 30, centered=(True, True, False)).translate((5, 0, 0)))
    assert rotational_symmetry(keyway.val(), *z) is None                                 # a shaft with a keyway
    # two opposite flats: a half turn, not a body of revolution (its corners stay on the cylinder at any angle)
    flats = cq.Workplane("XY").circle(5).extrude(30).cut(cq.Workplane("XY").box(12, 2, 30, centered=(True, True, False)))
    assert rotational_symmetry(flats.val(), *z).order == 2
    # two opposite nicks of 0.05 mm: 0.00025 mm3, far inside the volume allowance, balanced on the axis. Only the
    # boundary points see that it is a half turn and not a body of revolution
    nick = cq.Workplane("XY").box(0.05, 0.05, 0.05)
    nicked = disc.cut(nick.translate((20, 0, 2.5))).cut(nick.translate((-20, 0, 2.5)))
    assert rotational_symmetry(nicked.val(), *z).order == 2


def test_a_shaft_is_queried_once_and_a_lugged_wheel_over_one_period():
    cq = _cq()
    from cadagent.review.gates.motion import motion_gate
    asm, joints = _machine(cq, _wheel(cq))
    full = motion_gate(asm, joints, max_step_deg=10, symmetry=False)
    v = motion_gate(asm, joints, max_step_deg=10)
    assert full["pass"] and v["pass"], v["findings"]
    assert full["stats"]["poses"] == v["stats"]["poses"] == 74 and v["stats"]["symmetric_joints"] == 2
    # each joint's body meets two parts (its bore and its guard). Without the shortcut every pose that passes the
    # broad phase is a kernel query (36 distinct poses per joint); with it, one pose of the shaft and three
    # (0, 10, 20 deg) of the wheel
    assert full["stats"]["pair_queries"] == v["stats"]["pair_queries"]            # the broad phase is unchanged
    assert full["stats"]["kernel_queries"] >= 130 and full["stats"]["symmetry_queries"] == 0
    assert v["stats"]["kernel_queries"] == 2 * 1 + 2 * 3 and v["stats"]["symmetry_queries"] == 2
    shaft, wheel = (group(v, g)["density"][0]["symmetry"] for g in ("shaft", "wheel"))
    assert shaft["kind"] == "revolution" and shaft["distinct_poses"] == 1 and shaft["samples"] == 37
    assert wheel["period_deg"] == 30 and wheel["distinct_poses"] == 3
    assert group(v, "wheel")["min_clearance_mm"] == pytest.approx(group(full, "wheel")["min_clearance_mm"], abs=1e-6)
    msg = next(c for c in v["checks"] if c["id"] == "motion:shaft")["message"]
    assert "measures as a body of revolution about the joint axis" in msg and "queried once" in msg
    assert any("measure as unchanged by a rotation" in a for a in v["assumptions"])


def test_a_collision_at_one_angle_of_the_turn_is_found_on_a_wheel_that_only_looks_symmetric():
    """Eleven lugs reach 26 mm and one reaches 29 mm. A peg 28 mm out at 200 deg clears the eleven and is hit only
    when the long lug comes round to it. Sampling one 30 deg period would never turn the long lug that far: the
    wheel must not be taken for a 12-fold part."""
    cq = _cq()
    from cadagent.review.gates.motion import motion_gate
    asm, joints = _machine(cq, _wheel(cq, long_lug=True), peg_radius=28.0)
    v = motion_gate(asm, {"wheel": joints["wheel"]}, max_step_deg=10)
    assert not v["pass"] and v["stats"]["symmetric_joints"] == 0
    assert "symmetry" not in group(v, "wheel")["density"][0]
    hit = next(c for c in v["checks"] if c["id"] == "collision:peg|wheel")
    assert hit["evidence"]["first_pose"] == "wheel=-160deg" and hit["evidence"]["colliding_poses"] == 1
    assert v["stats"]["kernel_queries"] >= 36                    # every distinct pose of the turn was queried
    # the control: with twelve equal lugs the same peg is clear at every angle, and one period is enough to say so
    asm, joints = _machine(cq, _wheel(cq), peg_radius=28.0)
    ok = motion_gate(asm, {"wheel": joints["wheel"]}, max_step_deg=10)
    assert ok["pass"] and group(ok, "wheel")["density"][0]["symmetry"]["distinct_poses"] == 3


def test_a_missing_lug_is_sampled_over_the_full_turn():
    cq = _cq()
    from cadagent.review.gates.motion import motion_gate
    asm, joints = _machine(cq, _wheel(cq, missing=1))
    v = motion_gate(asm, {"wheel": joints["wheel"]}, max_step_deg=10)
    assert v["pass"] and v["stats"]["symmetric_joints"] == 0 and v["stats"]["kernel_queries"] >= 60
    assert "repeating" not in next(c for c in v["checks"] if c["id"] == "motion:wheel")["message"]


def test_a_collision_on_a_symmetric_wheel_reads_the_same_with_and_without_the_shortcut():
    """A peg in the lugs' path is hit by every lug. The shortcut asks the kernel about one period only, and every
    sampled pose still gets its answer: the same poses collide and the same one is reported first."""
    cq = _cq()
    from cadagent.review.gates.motion import motion_gate
    asm, joints = _machine(cq, _wheel(cq), peg_radius=25.0)
    joints = {"wheel": joints["wheel"]}
    full = motion_gate(asm, joints, max_step_deg=10, symmetry=False)
    v = motion_gate(asm, joints, max_step_deg=10)
    a, b = (next(c for c in x["checks"] if c["id"] == "collision:peg|wheel")["evidence"] for x in (full, v))
    assert a["colliding_poses"] == b["colliding_poses"] > 3
    assert a["first_pose"] == b["first_pose"] and a["worst_pose"] == b["worst_pose"]
    assert a["overlap_mm3"] == pytest.approx(b["overlap_mm3"], abs=1e-3)
    assert a["onset"]["clear"] == pytest.approx(b["onset"]["clear"]) and a["onset"]["hit"] == pytest.approx(b["onset"]["hit"])
    assert v["stats"]["kernel_queries"] < full["stats"]["kernel_queries"] / 4


def test_the_measurement_is_kept_in_the_pair_cache(tmp_path):
    cq = _cq()
    from cadagent.review.gates import PairCache
    from cadagent.review.gates.motion import motion_gate
    asm, joints = _machine(cq, _wheel(cq))
    cold = motion_gate(asm, joints, cache=PairCache(tmp_path))
    warm = motion_gate(asm, joints, cache=PairCache(tmp_path))
    assert cold["stats"]["symmetry_queries"] == 2 and warm["stats"]["symmetry_queries"] == 0
    assert warm["stats"]["kernel_queries"] == 0 and warm["stats"]["symmetric_joints"] == 2
    strip = lambda x: {k: x[k] for k in ("checks", "groups", "pass")}          # noqa: E731
    assert strip(cold) == strip(warm)
