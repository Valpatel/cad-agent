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
