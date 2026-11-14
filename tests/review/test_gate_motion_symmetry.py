"""Repeating poses in the motion gate (#724): a body that a turn about its joint axis leaves unchanged.

The first half runs the rule on a recording world with no CAD kernel: which joints may be shortened, how
parts of one body combine, and that the kernel is asked at the equivalent pose. The second half measures
real solids (skipped without the ``cad`` extra): a shaft, a lugged wheel, and the wheels that only look
symmetric, where a collision at one angle of the turn must still be found.
"""

from __future__ import annotations

import math

import pytest

from cadagent.review.gates import Relation
from cadagent.review.gates.cache import matrix_key
from cadagent.review.gates.motion import IDENTITY, World, _phase, rotation, run_motion


# ----------------------------------------------------------------------------- a kernel-free world

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


# ----------------------------------------------------------------------------- on CadQuery solids

def _cq():
    return pytest.importorskip("cadquery")


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
