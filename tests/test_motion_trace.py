"""An independent analytic fixture exercises actual observed points, never oracle predictions."""
from copy import deepcopy
import json
import math

import pytest

from cadagent.cli import main
from cadagent.mechanical.motion_trace import required_poses, validate_motion_trace


def contract():
    # Offset axes expose origin errors. Housing follows yaw, rotor follows yaw + spin.
    return {"schema_version": 1, "length_unit": "mm", "frame": "assembly-home",
            "reference": "synthetic analytic shaft: yaw datum (10,20,30), rotor datum (40,20,30)",
            "joints": {"yaw": {"parent": None, "pivot": [10, 20, 30], "axis": [0, 0, 1], "range_deg": [-90, 90]},
                       "spin": {"parent": "yaw", "pivot": [40, 20, 30], "axis": [1, 0, 0], "range_deg": [0, 360]}},
            "components": {
                "rotor": {"joint": "spin", "points": [[40, 20, 30], [41, 20, 30], [40, 22, 30], [40, 20, 33]]},
                "housing": {"joint": "yaw", "points": [[35, 20, 30], [35, 25, 30], [35, 20, 35], [45, 20, 30]]},
                "base": {"joint": None, "points": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]}}}


def observation(c, angles, defect=None):
    out = {}
    for name, comp in c["components"].items():
        out[name] = []
        for x, y, z in comp["points"]:
            if name == "rotor" or (name == "housing" and defect == "housing-spins"):
                a = math.radians(angles["spin"])
                if defect == "wrong-sign":
                    a = -a
                pivot_y = 20 + (48 if defect == "offset-pivot" else 0)
                cy, cz = y - pivot_y, z - 30
                if defect == "wrong-axis":  # rotate about Z instead of X
                    cx, cy = x - 40, y - 20
                    x, y = 40 + cx * math.cos(a) - cy * math.sin(a), 20 + cx * math.sin(a) + cy * math.cos(a)
                else:
                    y, z = pivot_y + cy * math.cos(a) - cz * math.sin(a), 30 + cy * math.sin(a) + cz * math.cos(a)
            if name != "base" and not (name == "rotor" and defect == "lost-parent"):
                a = math.radians(angles["yaw"])
                cx, cy = x - 10, y - 20
                x, y = 10 + cx * math.cos(a) - cy * math.sin(a), 20 + cx * math.sin(a) + cy * math.cos(a)
            p = [x, y, z]
            if defect == "metres-labelled-mm":
                p = [v / 1000 for v in p]
            if defect == "mirrored-frame":
                p[2] *= -1
            if defect == "deformed" and name == "rotor":
                p[0] *= 1.1
            out[name].append(p)
    return out


def trace(c, defect=None):
    return {"schema_version": 1, "length_unit": "mm", "frame": "assembly-home",
            "capture_source": "independent analytic test renderer",
            "samples": [{"id": str(i), "angles_deg": pose, "components": observation(c, pose, defect)}
                        for i, pose in enumerate(required_poses(c))]}


def test_independent_analytic_motion_and_nested_ownership_pass():
    c = contract()
    report = validate_motion_trace(c, trace(c))
    assert report["status"] == "pass"
    assert report["components"]["rotor"]["max_error_mm"] < 1e-12
    assert report["components"]["rotor"]["max_anchor_error_mm"] < 1e-10
    assert report["components"]["rotor"]["max_radius_error_mm"] < 1e-12
    assert report["coverage"]["spin"]["max_gap_deg"] == 90
    assert len(report["contract_sha256"]) == len(report["trace_sha256"]) == 64


@pytest.mark.parametrize("defect", ["offset-pivot", "wrong-axis", "wrong-sign", "lost-parent", "housing-spins",
                                   "metres-labelled-mm", "mirrored-frame", "deformed"])
def test_bad_rendered_transforms_fail(defect):
    c = contract()
    report = validate_motion_trace(c, trace(c, defect))
    assert report["status"] == "fail"
    assert any(f["check"] == "rendered-landmarks" for f in report["failures"])
    if defect == "offset-pivot":
        rotor = report["components"]["rotor"]
        assert rotor["max_error_mm"] == pytest.approx(96)
        assert rotor["max_anchor_error_mm"] == pytest.approx(96)
        assert rotor["max_radius_error_mm"] == pytest.approx(96)
    if defect == "housing-spins":
        assert {f["component"] for f in report["failures"]} == {"housing"}


def test_home_only_and_full_turn_alias_cannot_pass():
    c = contract()
    t = trace(c)
    t["samples"] = [s for s in t["samples"] if s["angles_deg"]["spin"] in (0, 360) and not s["angles_deg"]["yaw"]]
    report = validate_motion_trace(c, t)
    assert report["status"] == "fail"
    assert report["failures"][0]["check"] == "pose-coverage"


def test_nested_pose_is_required_even_if_individual_sweeps_pass():
    c = contract()
    t = trace(c)
    t["samples"] = [s for s in t["samples"] if not all(s["angles_deg"].values())]
    assert validate_motion_trace(c, t)["status"] == "fail"


def test_tolerance_is_stated_and_observations_are_not_mutated():
    c = contract()
    t = trace(c)
    t["samples"][0]["components"]["base"][0][0] += .02
    original = deepcopy(t)
    assert validate_motion_trace(c, t)["status"] == "fail"
    assert validate_motion_trace(c, t, tolerance_mm=.03)["status"] == "pass"
    assert t == original


@pytest.mark.parametrize("mutation,match", [
    (lambda c: c.update(length_unit="m"), "convert captures"),
    (lambda c: c.update(frame="world"), "convert captures"),
    (lambda c: c.update(reference=""), "reference"),
    (lambda c: c["joints"]["spin"].update(parent="missing"), "unknown parent"),
    (lambda c: c["joints"]["yaw"].update(parent="spin"), "cycle"),
    (lambda c: c["joints"]["spin"].update(axis=[0, 0, 0]), "nonzero"),
    (lambda c: c["joints"]["spin"].update(axis=[0, math.nan, 0]), "finite"),
    (lambda c: c["joints"]["spin"].update(range_deg=[10, 360]), "include home"),
    (lambda c: c["joints"]["spin"].update(range_deg=[0, 0]), "nonzero"),
    (lambda c: c["components"]["rotor"].update(joint="absent"), "unknown owning"),
    (lambda c: c["components"]["rotor"].update(points=[[0, 0, 0]] * 4), "affinely independent"),
    (lambda c: c["components"]["rotor"].update(points=[[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]]), "coplanar"),
    (lambda c: c["components"].pop("rotor"), "no captured components"),
])
def test_bad_reference_is_rejected(mutation, match):
    c = contract()
    mutation(c)
    with pytest.raises(ValueError, match=match):
        required_poses(c)


@pytest.mark.parametrize("mutation,match", [
    (lambda t: t.update(samples=[]), "nonempty list"),
    (lambda t: t.update(length_unit="m"), "convert captures"),
    (lambda t: t["samples"].append(t["samples"][0]), "unique"),
    (lambda t: t["samples"][0]["angles_deg"].pop("yaw"), "every joint"),
    (lambda t: t["samples"][0]["angles_deg"].update(spin=361), "outside reference"),
    (lambda t: t["samples"][0]["components"].pop("housing"), "every component"),
    (lambda t: t["samples"][0]["components"].update(extra=[[0, 0, 0]] * 4), "every component"),
    (lambda t: t["samples"][0]["components"]["rotor"].append([0, 0, 0]), "count differs"),
    (lambda t: t["samples"][0]["components"]["rotor"][0].__setitem__(0, math.inf), "finite"),
])
def test_bad_capture_is_rejected(mutation, match):
    c = contract()
    t = trace(c)
    mutation(t)
    with pytest.raises(ValueError, match=match):
        validate_motion_trace(c, t)


@pytest.mark.parametrize("tolerance", [0, -1, math.nan, True])
def test_invalid_tolerance(tolerance):
    c = contract()
    with pytest.raises(ValueError):
        validate_motion_trace(c, trace(c), tolerance_mm=tolerance)


def test_cli_poses_report_failure_and_schema_exit_codes(tmp_path, capsys):
    c = contract()
    cp, tp, out = (tmp_path / p for p in ("contract.json", "trace.json", "report.json"))
    cp.write_text(json.dumps(c))
    assert main(["motion-trace", str(cp), "--poses-only"]) == 0
    assert json.loads(capsys.readouterr().out) == required_poses(c)
    tp.write_text(json.dumps(trace(c)))
    assert main(["motion-trace", str(cp), str(tp), "--output", str(out)]) == 0
    assert json.loads(out.read_text())["status"] == "pass"
    tp.write_text(json.dumps(trace(c, "offset-pivot")))
    assert main(["motion-trace", str(cp), str(tp), "--output", str(out)]) == 1
    assert json.loads(out.read_text())["status"] == "fail"
    tp.write_text('{"broken":')
    assert main(["motion-trace", str(cp), str(tp)]) == 2
    assert main(["motion-trace", str(cp)]) == 2


def test_multi_turn_range_cannot_alias_every_sample_to_home():
    c = contract()
    c["joints"]["spin"]["range_deg"] = [0, 1440]
    poses = required_poses(c)
    assert any(p["spin"] == 90 for p in poses)
    assert validate_motion_trace(c, trace(c, "wrong-sign"))["status"] == "fail"


@pytest.mark.parametrize("location,key", [("joints", "parent"), ("components", "joint")])
def test_ownership_must_be_explicit(location, key):
    c = contract()
    next(iter(c[location].values())).pop(key)
    with pytest.raises(ValueError, match="declare"):
        required_poses(c)


def test_unbounded_rotations_fail_before_allocating_capture_poses():
    c = contract()
    c["joints"]["spin"]["range_deg"] = [0, 1e12]
    with pytest.raises(ValueError, match="bounded cycles"):
        required_poses(c)


def test_installed_copy_retains_the_capture_protocol(tmp_path):
    from pathlib import Path
    from cadagent.agentkit import install
    root = Path(__file__).resolve().parents[1]
    result = install(tmp_path, root, ("codex",), copy=True)
    assert not result["conflicts"]
    skill = tmp_path / ".codex/skills/cad-motion-validation"
    assert (skill / "references/trace-protocol.md").read_text() == (root / "skills/cad-motion-validation/references/trace-protocol.md").read_text()


# ----------------------------------------------------------------------------- closed loops (#187)
# A five-bar leg in the x-y plane: hips 40 mm apart, cranks 30 mm hanging at -120 and -60 degrees, shins 45 mm meeting
# at the foot pin below. hip_b turns about -z (its axis is flipped), the knees sit 5 mm deeper and the pin 10 mm, so
# the loop is solved in its plane whatever the joints' depths and directions. A toe rides on the left shin.

def _leg_home():
    A, B = (-20.0, 0.0), (20.0, 0.0)
    c1 = (A[0] + 30 * math.cos(math.radians(-120)), 30 * math.sin(math.radians(-120)))
    c2 = (B[0] + 30 * math.cos(math.radians(-60)), 30 * math.sin(math.radians(-60)))
    foot = (0.0, c1[1] - math.sqrt(45 ** 2 - 35 ** 2))
    return A, B, c1, c2, foot


def _box(cx, cy, z):
    return [[cx, cy, z], [cx + 2, cy, z], [cx, cy + 2, z], [cx, cy, z + 2]]


def leg_contract():
    A, B, c1, c2, foot = _leg_home()
    mid = lambda p, q: ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)        # noqa: E731
    return {"schema_version": 1, "length_unit": "mm", "frame": "assembly-home",
            "reference": "synthetic five-bar leg: hips (-20,0) and (20,0), cranks 30, shins 45",
            "joints": {"hip_a": {"parent": None, "pivot": [*A, 0], "axis": [0, 0, 1], "range_deg": [-60, 60]},
                       "knee_c": {"parent": "hip_a", "pivot": [*c1, 5], "axis": [0, 0, 1], "range_deg": [-180, 180]},
                       "hip_b": {"parent": None, "pivot": [*B, 0], "axis": [0, 0, -1], "range_deg": [-60, 60]},
                       "knee_d": {"parent": "hip_b", "pivot": [*c2, 5], "axis": [0, 0, 1], "range_deg": [-180, 180]},
                       "toe": {"parent": "knee_c", "pivot": [*foot, 10], "axis": [0, 0, 1], "range_deg": [-30, 30]}},
            "components": {"frame": {"joint": None, "points": _box(0, 10, 0)},
                           "crank_a": {"joint": "hip_a", "points": _box(*mid(A, c1), 0)},
                           "shin_c": {"joint": "knee_c", "points": _box(*mid(c1, foot), 5)},
                           "crank_b": {"joint": "hip_b", "points": _box(*mid(B, c2), 0)},
                           "shin_d": {"joint": "knee_d", "points": _box(*mid(c2, foot), 5)},
                           "toe": {"joint": "toe", "points": _box(foot[0], foot[1] - 5, 10)}},
            "loops": {"leg": {"closes": ["knee_c", "knee_d"], "pin": [*foot, 10], "inputs": ["hip_a", "hip_b"]}}}


def _turn(p, about, rad):
    x, y = p[0] - about[0], p[1] - about[1]
    return (about[0] + x * math.cos(rad) - y * math.sin(rad), about[1] + x * math.sin(rad) + y * math.cos(rad))


def leg_render(inputs, defect=None):
    """An independent renderer: it solves the leg itself (two circles of 45 about the knees, the foot below them) and
    returns the angles it posed and every component's points. ``defect``: 'serial' leaves the knees at home as a serial
    chain would, 'other-branch' takes the foot above the knees."""
    A, B, c1, c2, foot = _leg_home()
    ha, hb = math.radians(inputs["hip_a"]), -math.radians(inputs["hip_b"])     # hip_b turns about -z
    k1, k2 = _turn(c1, A, ha), _turn(c2, B, hb)
    dx, dy = k2[0] - k1[0], k2[1] - k1[1]
    s = math.hypot(dx, dy)
    h = math.sqrt(max(45 ** 2 - (s / 2) ** 2, 0.0))          # out of reach it draws the shins in line
    below = (k1[0] + dx / 2 + h * dy / s, k1[1] + dy / 2 - h * dx / s)
    above = (k1[0] + dx / 2 - h * dy / s, k1[1] + dy / 2 + h * dx / s)
    p = below if below[1] < above[1] else above
    if defect == "other-branch":
        p = above if p is below else below
    turn_c = math.atan2(p[1] - k1[1], p[0] - k1[0]) - math.atan2(foot[1] - c1[1], foot[0] - c1[0])
    turn_d = math.atan2(p[1] - k2[1], p[0] - k2[0]) - math.atan2(foot[1] - c2[1], foot[0] - c2[0])
    if defect == "serial":
        turn_c, turn_d = ha, hb
    angles = {"hip_a": inputs["hip_a"], "hip_b": inputs["hip_b"],
              "knee_c": math.degrees(math.remainder(turn_c - ha, 2 * math.pi)),
              "knee_d": math.degrees(math.remainder(turn_d - hb, 2 * math.pi)), "toe": inputs.get("toe", 0.0)}
    c = leg_contract()

    def move(points, steps):
        out = []
        for x, y, z in points:
            q = (x, y)
            for about, rad in steps:
                q = _turn(q, about, rad)
            out.append([q[0], q[1], z])
        return out

    # each body: its own turn about its pivot, then its parent's, outwards in
    shin_c = [(c1, turn_c - ha), (A, ha)]
    comps = {"frame": c["components"]["frame"]["points"],
             "crank_a": move(c["components"]["crank_a"]["points"], [(A, ha)]),
             "shin_c": move(c["components"]["shin_c"]["points"], shin_c),
             "crank_b": move(c["components"]["crank_b"]["points"], [(B, hb)]),
             "shin_d": move(c["components"]["shin_d"]["points"], [(c2, turn_d - hb), (B, hb)]),
             "toe": move(c["components"]["toe"]["points"], [(foot, math.radians(angles["toe"]))] + shin_c)}
    return angles, comps


def leg_trace(defect=None, extra=()):
    c = leg_contract()
    samples = []
    for i, pose in enumerate(list(required_poses(c)) + list(extra)):
        angles, comps = leg_render(pose, defect)
        samples.append({"id": str(i), "angles_deg": angles, "components": comps})
    return {"schema_version": 1, "length_unit": "mm", "frame": "assembly-home",
            "capture_source": "independent analytic five-bar renderer", "samples": samples}


def test_a_five_bar_leg_samples_its_inputs_and_solves_its_knees():
    c = leg_contract()
    poses = required_poses(c)
    hips = {(p["hip_a"], p["hip_b"]) for p in poses}
    # every hip sample against every other, except where the shins cannot reach: both cranks out at -60 put the knees
    # 100 mm apart, more than the shins' 90
    assert (-60, -60) not in hips and (60, 60) in hips and (0, 0) in hips
    assert 15 < len(hips) < 25
    for p in poses:
        angles, _ = leg_render(p)
        assert p["knee_c"] == pytest.approx(angles["knee_c"], abs=1e-9)
        assert p["knee_d"] == pytest.approx(angles["knee_d"], abs=1e-9)
    # the toe is exercised with the leg away from home, not with one knee turned alone
    toe = [p for p in poses if p["toe"] and p["hip_a"]]
    assert toe and all(abs(leg_render(p)[0]["knee_c"] - p["knee_c"]) < 1e-9 for p in toe)


def test_an_independent_loop_renderer_passes():
    report = validate_motion_trace(leg_contract(), leg_trace())
    assert report["status"] == "pass", report["failures"]
    row = report["loops"]["leg"]
    assert row["kind"] == "five-bar" and row["max_pose_error_mm"] < 1e-9 and not row["unreachable_samples"]
    assert row["links_mm"] == [pytest.approx({"crank": 30, "link": 45}), pytest.approx({"crank": 30, "link": 45})]
    assert report["components"]["shin_d"]["max_error_mm"] < 1e-9


@pytest.mark.parametrize("defect", ["serial", "other-branch"])
def test_a_renderer_that_breaks_the_loop_fails(defect):
    # Its landmarks agree with the angles it reports, so only the loop check sees that the leg came apart ('serial')
    # or assembled the other way ('other-branch').
    report = validate_motion_trace(leg_contract(), leg_trace(defect))
    assert report["status"] == "fail"
    assert [f["check"] for f in report["failures"]] == ["loop-pose"]
    assert report["failures"][0]["max_pose_error_mm"] > 10


def test_a_sample_whose_inputs_cannot_close_fails():
    report = validate_motion_trace(leg_contract(), leg_trace(extra=[{"hip_a": -60, "hip_b": -60}]))
    assert report["status"] == "fail"
    assert report["loops"]["leg"]["unreachable_samples"] == [str(len(required_poses(leg_contract())))]


def test_a_four_bar_driven_from_either_end():
    # Norton's Example 4-1 (40, 120, 80, 100 mm) at 40 degrees, as a tree from the crank (crank, coupler, rocker) and
    # from the rocker (rocker, coupler, crank): either way the rocker's angles are cadagent.formulas'.
    from cadagent import formulas as fx
    t3, t4 = fx.fourbar_angles(40, 120, 80, 100, math.radians(40))
    B = (40 * math.cos(math.radians(40)), 40 * math.sin(math.radians(40)))
    C = (100 + 80 * math.cos(t4), 80 * math.sin(t4))
    pts = lambda x, y: _box(x, y, 0)                                    # noqa: E731
    base = {"schema_version": 1, "length_unit": "mm", "frame": "assembly-home", "reference": "Norton Example 4-1"}
    crank = dict(base, joints={
        "crank": {"parent": None, "pivot": [0, 0, 0], "axis": [0, 0, 1], "range_deg": [-180, 180]},
        "coupler": {"parent": "crank", "pivot": [*B, 0], "axis": [0, 0, 1], "range_deg": [-180, 180]},
        "rocker": {"parent": None, "pivot": [100, 0, 0], "axis": [0, 0, 1], "range_deg": [-180, 180]}},
        components={"a": {"joint": "coupler", "points": pts(60, 70)}, "b": {"joint": "rocker", "points": pts(110, 30)},
                    "c": {"joint": "crank", "points": pts(10, 10)}},
        loops={"x": {"closes": ["coupler", "rocker"], "pin": [*C, 0], "inputs": ["crank"]}})
    poses = required_poses(crank)
    assert sorted(p["crank"] for p in poses) == [-180, -90, 0, 90, 180]        # home, and every 90 degrees
    for p in poses:
        want = fx.fourbar_angles(40, 120, 80, 100, math.radians(40 + p["crank"]))[1]
        assert math.remainder(math.radians(p["rocker"]) - (want - t4), 2 * math.pi) == pytest.approx(0, abs=1e-12)
    rocker = dict(base, joints={
        "rocker": {"parent": None, "pivot": [100, 0, 0], "axis": [0, 0, 1], "range_deg": [-20, 20]},
        "coupler": {"parent": "rocker", "pivot": [*C, 0], "axis": [0, 0, 1], "range_deg": [-180, 180]},
        "crank": {"parent": None, "pivot": [0, 0, 0], "axis": [0, 0, 1], "range_deg": [-180, 180]}},
        components=crank["components"],
        loops={"x": {"closes": ["coupler", "crank"], "pin": [*B, 0], "inputs": ["rocker"]}})
    for p in required_poses(rocker):
        # the crank pin is a from the crank pivot and b from the coupler's pivot, the rocker's tip
        t = math.radians(p["rocker"])
        tip = _turn(C, (100, 0), t)
        pin = _turn(B, (0, 0), math.radians(p["crank"]))
        assert math.dist(pin, tip) == pytest.approx(120, abs=1e-9)


@pytest.mark.parametrize("mutation,match", [
    (lambda c: c["loops"]["leg"].update(closes=["knee_c", "knee_c"]), "two different joints"),
    (lambda c: c["loops"]["leg"].update(inputs=["hip_a"]), "first joint of each two-joint chain"),
    (lambda c: c["loops"]["leg"].update(closes=["knee_c", "toe"]), "carries the other"),
    (lambda c: c["joints"]["knee_d"].update(axis=[0, 1, 0]), "not parallel"),
    (lambda c: c["loops"].update(again={"closes": ["knee_c", "knee_d"], "pin": [0, 0, 0],
                                        "inputs": ["hip_a", "hip_b"]}), "one loop per joint"),
    (lambda c: c["joints"]["knee_c"].update(range_deg=[-5, 5]), "outside its range"),
    (lambda c: c["joints"]["hip_b"].update(parent="knee_d"), "cycle at .*declare the closed loop under loops"),
])
def test_bad_loops_are_rejected(mutation, match):
    c = leg_contract()
    mutation(c)
    with pytest.raises(ValueError, match=match):
        required_poses(c)


def test_a_loop_at_a_lock_at_home_is_rejected():
    c = leg_contract()
    A, B, c1, c2, foot = _leg_home()
    c["loops"]["leg"]["pin"] = [0.0, c1[1], 10]                     # the pin between the knees: shins in one line
    with pytest.raises(ValueError, match="in one line"):
        required_poses(c)
