"""Gyropup's recorded snapshot -> the replay example: committed bytes, kinematics and the converter's own checks.

The committed example is checked against its receipt and against geometry the recorded joints must satisfy (the
five-bar loop closes). The converter itself runs on a small synthetic snapshot in a temporary Git repository, so
these tests need neither a Gyropup checkout nor MuJoCo.
"""
import hashlib
import importlib.util
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/examples/robot-replay/gyropup.py"
BUNDLE = ROOT / "software/cadagent/webkit/simulation/examples/gyropup-v2"
SPEC = importlib.util.spec_from_file_location("gyropup_replay_example", SOURCE)
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


def rotate(q, v):
    return converter.rotate(tuple(q), tuple(v))


def test_committed_example_matches_its_receipt():
    assert converter.check(BUNDLE) == []
    receipt = json.loads((BUNDLE / "receipt.json").read_bytes())
    assert receipt["project"] == "Valpatel/gyropup" and receipt["license"] == "MIT"
    assert len(receipt["revision"]) == 40
    assert "historical demo" in receipt["snapshot"]["statement"]
    assert receipt["snapshot"]["physical_test"] is False
    assert all(len(h) == 64 for h in receipt["sources"].values())
    assert (BUNDLE / "LICENSE.txt").read_bytes().startswith(b"MIT License")
    index = json.loads((BUNDLE / "index.json").read_bytes())
    assert [s["id"] for s in index["scenarios"]] == list(converter.SCENARIOS)
    for scenario in index["scenarios"]:
        assert scenario["summary"]["verdict"]["label"] in ("pass", "fail")
        assert scenario["summary"]["metrics"][0]["label"] == "Peak motor torque"
        assert "% of its peak-torque limit" in scenario["summary"]["metrics"][0]["value"]
        assert "not a cad-agent verification" in scenario["summary"]["note"]


@pytest.mark.parametrize("scenario", converter.SCENARIOS)
def test_recorded_joints_close_each_five_bar_loop(scenario):
    """Independent of the converter's own arithmetic: the front lower link's far end meets the wheel axle in every
    frame, and the links keep their lengths. A wrong sign or joint order opens the loop by centimetres."""
    recording = json.loads((BUNDLE / f"{scenario}.json").read_bytes())
    ids = [b["id"] for b in recording["bodies"]]
    worst = 0.0
    lengths = set()
    for frame in recording["frames"]:
        pose = dict(zip(ids, frame["poses"]))
        for side in "lr":
            lower_f, lower_r, wheel = pose[f"lower_f_{side}"], pose[f"lower_r_{side}"], pose[f"wheel_{side}"]
            l2 = math.dist(lower_r["position"], wheel["position"])
            lengths.add(round(l2, 4))
            tip = [p + d for p, d in zip(lower_f["position"], rotate(lower_f["quaternion"], (l2, 0, 0)))]
            worst = max(worst, math.dist(tip, wheel["position"]))
            # The snapshot records joint angles to 1e-4 rad: 15 µm at the end of a 150 mm link.
            for end in "fr":
                assert math.dist(pose[f"upper_{end}_{side}"]["position"], pose[f"lower_{end}_{side}"]["position"]) == pytest.approx(0.15, abs=1e-4)
    assert worst < 5e-4, f"{scenario}: five-bar loop open by {worst * 1000:.2f} mm"
    assert lengths == {0.25}


def test_wheels_rest_on_floor_and_scenery():
    """The push run stays on flat floor: each wheel centre sits one tyre radius up (the tyre compresses slightly)."""
    recording = json.loads((BUNDLE / "push.json").read_bytes())
    ids = [b["id"] for b in recording["bodies"]]
    heights = [frame["poses"][ids.index(f"wheel_{side}")]["position"][2] for frame in recording["frames"] for side in "lr"]
    assert 0.080 < min(heights) and max(heights) < 0.0870
    kerb = json.loads((BUNDLE / "kerb_drop.json").read_bytes())
    assert kerb["scenery"][0]["shape"] == "box" and kerb["scenery"][0]["size"][2] == pytest.approx(0.05)
    assert kerb["view"]["follow"] == "base" and recording["view"]["follow"] == "base"      # the push: 0.37 m from its start (0.65 m end to end)
    # A run that stays on its spot is framed whole (#809): the landing's base moves 9 mm across the floor.
    assert "follow" not in json.loads((BUNDLE / "landing.json").read_bytes())["view"]
    receipt = json.loads((BUNDLE / "receipt.json").read_bytes())
    assert f"more than {converter.FOLLOW_TRAVEL_M} m" in receipt["view"]


def test_committed_figures_are_the_snapshots_own():
    """Every figure the viewer shows is the summary's value under the receipt's stated rule (#809): the landing's
    recorded 0.04° lean reads 0.04°, not 0.0°."""
    index = json.loads((BUNDLE / "index.json").read_bytes())
    receipt = json.loads((BUNDLE / "receipt.json").read_bytes())
    assert "max_theta_deg to two decimals" in receipt["figures"] and "fore-aft (pitch)" in receipt["figures"] and "shows no lean" in receipt["figures"]
    shown = {s["id"]: {m["label"]: m["value"] for m in s["summary"]["metrics"]} for s in index["scenarios"]}
    assert {k: v["Largest fore-aft lean"] for k, v in shown.items()} == {"kerb_drop": "8.32°", "side_kerb": "8.45°", "push": "7.35°", "landing": "0.04°"}
    assert shown["landing"]["Peak motor torque"] == "42.0 N·m, rear-right leg motor: 35% of its peak-torque limit"


# ---------------------------------------------------------------------------------------- a synthetic snapshot

def stl(*triangles):
    return b"\0" * 80 + struct.pack("<I", len(triangles)) + b"".join(
        struct.pack("<12fH", 0, 0, 0, *[c for v in t for c in v], 0) for t in triangles)


TETRA = stl(((0, 0, 0), (10, 0, 0), (0, 10, 0)), ((0, 0, 0), (0, 10, 0), (0, 0, 10)),
            ((0, 0, 0), (0, 0, 10), (10, 0, 0)), ((10, 0, 0), (0, 0, 10), (0, 10, 0)))


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": "/dev/null", "HOME": str(repo)})


@pytest.fixture
def snapshot(tmp_path):
    repo = tmp_path / "gyropup"
    snap = repo / converter.SNAPSHOT
    (snap / "rig").mkdir(parents=True)
    part = lambda name, colour="#f5b82e": {"file": f"{name}.stl", "name": name, "color": colour, "opacity": 1.0}
    manifest = {"units": "mm", "body": [part("frame", "#5f6670"), {**part("shell", "#9fb4c7"), "opacity": 0.35}],
                "links": {"upper": [part("upper")], "front": [part("front")], "wheel_link": [part("wheel_link")],
                          "wheel": [part("tyre", "#1b1d21")]},
                "turret": {"pan": [part("pan", "#4a5058")], "tilt": [part("tilt", "#4a5058")],
                           "pan_mm": [-50, 0, 200], "tilt_mm": [-50, 0, 330], "muzzle_mm": [140, 0, 320]},
                "fivebar": {"D_mm": 150.0, "l1_mm": 150.0, "l2_mm": 250.0, "y_off_mm": 82.3,
                            "ref": {"phi1": -0.888, "phi2": -2.2536, "af": -2.3166, "aw": -0.825}}}
    (snap / "rig/manifest.json").write_text(json.dumps(manifest))
    for name in ("frame", "shell", "upper", "front", "wheel_link", "tyre", "pan", "tilt"):
        (snap / f"rig/{name}.stl").write_bytes(TETRA)
    layout = {"root": 0, "motor_f_l": 7, "knee_f_l": 8, "motor_r_l": 9, "knee_r_l": 10, "wheel_l": 11,
              "motor_f_r": 12, "knee_f_r": 13, "motor_r_r": 14, "knee_r_r": 15, "wheel_r": 16, "turret_pan": 17, "turret_tilt": 18}
    motors = {"motor_f_l": {"peak_torque_nm": 10.0, "of_peak": 0.1, "of_rated": 0.3},
              "wheel_r": {"peak_torque_nm": 6.0, "of_peak": 0.42, "of_rated": 1.2}}
    summary = {"name": "Synthetic", "passed": 4, "total": 4, "physical_test": False, "estimates": [], "scenarios": {}}
    for k, name in enumerate(converter.SCENARIOS):
        # The kerb drives 1.5 m; the plank run 0.3 m, between the follow threshold and the old 1 m rule (#809).
        frames = [[0.5 * i * (k == 0) + 0.1 * i * (k == 1), 0, 0.37, 1, 0, 0, 0] + [0.01 * i] * 12 for i in range(4)]
        run = {"scenario": name, "title": f"Synthetic {name}", "pass": True, "reasons": [], "max_theta_deg": 2.5,
               "motors": motors, "qpos_layout": layout, "events": [{"t": 0.05, "type": "push"}] if name == "push" else [],
               "props": [{"name": "kerb", "type": 6, "size": [1, 1, 0.025], "pos": [0, 0, 0.025], "quat": [1, 0, 0, 0],
                          "rgba": [0.6, 0.6, 0.62, 1]}] if name == "kerb_drop" else [],
               "seconds": 0.1, "frames": {"fps": 30, "qpos": frames}}
        (snap / f"{name}.json").write_text(json.dumps(run))
        summary["scenarios"][name] = {k2: run[k2] for k2 in ("title", "pass", "reasons", "max_theta_deg", "motors")}
    (snap / "summary.json").write_text(json.dumps(summary))
    (repo / "hardware/exports/sim/README.md").write_text("A snapshot generated by the tools on 2026-10-25.\nA historical demo.\n")
    (repo / "LICENSE").write_text("MIT License\n\nCopyright (c) synthetic\n")
    (repo / "software/simulation").mkdir(parents=True)
    (repo / converter.TIMESTEP_SOURCE).write_text('MJCF = """<option timestep="0.001" gravity="0 0 -9.81"/>"""\n')
    (repo / converter.SAMPLING_SOURCE).write_text(f"FPS = 30\n{converter.SAMPLING_RULE}\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "snapshot")
    return repo


def test_converter_writes_a_checked_deterministic_example(snapshot, tmp_path):
    out, again = tmp_path / "out", tmp_path / "again"
    out.mkdir()
    again.mkdir()
    receipt = converter.convert(snapshot, out)
    converter.convert(snapshot, again)
    for name in (*receipt["artifacts"], "receipt.json"):
        assert (out / name).read_bytes() == (again / name).read_bytes(), name
    assert converter.check(out, snapshot) == []
    assert receipt["sources"][f"{converter.SNAPSHOT}/push.json"] == hashlib.sha256((snapshot / converter.SNAPSHOT / "push.json").read_bytes()).hexdigest()
    index = json.loads((out / "index.json").read_bytes())
    push = next(s for s in index["scenarios"] if s["id"] == "push")["summary"]
    assert push["verdict"] == {"pass": True, "label": "pass"}
    assert push["metrics"][0]["value"] == "6.0 N·m, right wheel motor: 42% of its peak-torque limit"
    # Frames are stamped at the solver's true interval: one every round(1 / (30 x 0.001)) = 33 steps of 1 ms.
    assert [f["time_s"] for f in json.loads((out / "push.json").read_bytes())["frames"]] == [0, 0.033, 0.066, 0.099]
    assert push["metrics"][2] == {"label": "Events", "value": "push at 0.1 s"}
    model = json.loads((out / "robot.json").read_bytes())
    names = [p["name"] for p in model["parts"]]
    assert len(names) == len(set(names)), "a mesh shared by two bodies is packed once"
    recording = json.loads((out / "kerb_drop.json").read_bytes())
    assert {g["part"] for b in recording["bodies"] for g in b["geometry"]} <= set(names)
    assert any(g.get("opacity") == 0.35 for g in recording["bodies"][0]["geometry"])
    assert recording["scenery"][0]["size"] == [2, 2, 0.05]
    assert recording["view"]["follow"] == "base"                    # it drives 1.5 m
    assert json.loads((out / "side_kerb.json").read_bytes())["view"]["follow"] == "base"   # 0.3 m: above 0.1 m, below 1 m
    assert "follow" not in json.loads((out / "push.json").read_bytes())["view"]
    assert "mujoco" not in sys.modules


def test_check_rejects_a_tampered_recording_and_a_changed_source(snapshot, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    converter.convert(snapshot, out)
    original = (out / "push.json").read_bytes()
    (out / "push.json").write_bytes(original[:-2] + b" " + original[-2:])     # one byte more, the same JSON
    problems = converter.check(out)
    assert "push.json: does not match its receipt" in problems
    assert "index.json: push.json hash differs" in problems
    assert converter.main(["--check", "--out", str(out)]) == 1
    (out / "push.json").write_bytes(original)
    assert converter.main(["--check", "--out", str(out)]) == 0
    run = json.loads((snapshot / converter.SNAPSHOT / "landing.json").read_bytes())
    run["frames"]["qpos"][1][2] = 0.30
    (snapshot / converter.SNAPSHOT / "landing.json").write_text(json.dumps(run))
    git(snapshot, "commit", "-q", "-am", "a different landing")
    problems = converter.check(out, snapshot)
    assert any(p.startswith("landing.json: differs from a fresh conversion") for p in problems)


def test_converter_refuses_uncommitted_snapshot_changes(snapshot, tmp_path):
    (snapshot / converter.SNAPSHOT / "summary.json").write_text("{}")
    with pytest.raises(ValueError, match="uncommitted"):
        converter.convert(snapshot, tmp_path)


def test_mesh_names_cannot_leave_the_rig_folder(snapshot, tmp_path):
    path = snapshot / converter.SNAPSHOT / "rig/manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["body"][0]["file"] = "../summary.json"
    path.write_text(json.dumps(manifest))
    git(snapshot, "commit", "-q", "-am", "a path outside rig/")
    with pytest.raises(ValueError, match="not a plain STL name"):
        converter.convert(snapshot, tmp_path)


def test_card_capture_is_bound_to_the_viewer_that_made_it():
    """The cards' animation and still were captured from these exact viewer, example and capture-script bytes."""
    record = json.loads((BUNDLE / "card.json").read_bytes())
    for path, expected in record["sources"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, f"{path}: recapture the cards"
    assert hashlib.sha256((BUNDLE / record["file"]).read_bytes()).hexdigest() == record["sha256"]
    assert hashlib.sha256((BUNDLE / record["still"]["file"]).read_bytes()).hexdigest() == record["still"]["sha256"]
    assert record["scenario"] in converter.SCENARIOS and record["frames"] >= 30
    assert (BUNDLE / record["file"]).stat().st_size < 400_000


def test_frame_interval_and_motor_names_are_confirmed_not_guessed(snapshot, tmp_path):
    """The interval comes from Gyropup's own timestep and sampling rule, and every motor needs a known name: without
    either, the conversion stops instead of stamping a nominal rate or showing a raw key."""
    path = snapshot / converter.SAMPLING_SOURCE
    path.write_text("FPS = 30\nframe_every = 1\n")
    git(snapshot, "commit", "-q", "-am", "another sampling rule")
    with pytest.raises(ValueError, match="cannot confirm the frame interval"):
        converter.convert(snapshot, tmp_path)
    path.write_text(f"FPS = 30\n{converter.SAMPLING_RULE}\n")
    run_path = snapshot / converter.SNAPSHOT / "landing.json"
    run = json.loads(run_path.read_bytes())
    run["seconds"] = 0.2
    run_path.write_text(json.dumps(run))
    git(snapshot, "commit", "-q", "-am", "frames that do not fit the run")
    with pytest.raises(ValueError, match="do not fit"):
        converter.convert(snapshot, tmp_path)
    run["seconds"] = 0.1
    run_path.write_text(json.dumps(run))
    summary_path = snapshot / converter.SNAPSHOT / "summary.json"
    summary = json.loads(summary_path.read_bytes())
    summary["scenarios"]["push"]["motors"] = {"motor_x": {"peak_torque_nm": 1.0, "of_peak": 0.9, "of_rated": 2.0}}
    summary_path.write_text(json.dumps(summary))
    git(snapshot, "commit", "-q", "-am", "an unknown motor")
    with pytest.raises(ValueError, match="not a known Gyropup actuator key"):
        converter.convert(snapshot, tmp_path)


def test_lean_is_shown_as_recorded_or_not_at_all(snapshot, tmp_path):
    """The lean is the summary's own number to its recorded two decimals; a run without one shows no lean, and a value
    that is not an angle stops the conversion (#809). Nothing is invented or rounded to zero."""
    assert converter.lean_text({"max_theta_deg": 0.04}) == "0.04°"
    assert converter.lean_text({"max_theta_deg": 8.45}) == "8.45°"
    assert converter.lean_text({}) is None and converter.lean_text({"max_theta_deg": None}) is None
    path = snapshot / converter.SNAPSHOT / "summary.json"
    summary = json.loads(path.read_bytes())
    del summary["scenarios"]["landing"]["max_theta_deg"]
    summary["scenarios"]["push"]["max_theta_deg"] = 0.04
    path.write_text(json.dumps(summary))
    git(snapshot, "commit", "-q", "-am", "a run without a lean")
    out = tmp_path / "out"
    out.mkdir()
    converter.convert(snapshot, out)
    metrics = {s["id"]: s["summary"]["metrics"] for s in json.loads((out / "index.json").read_bytes())["scenarios"]}
    assert [m["label"] for m in metrics["landing"]] == ["Peak motor torque"]
    assert {"label": "Largest fore-aft lean", "value": "0.04°"} in metrics["push"]
    summary["scenarios"]["push"]["max_theta_deg"] = "7°"
    path.write_text(json.dumps(summary))
    git(snapshot, "commit", "-q", "-am", "a lean that is not a number")
    with pytest.raises(ValueError, match="not a recorded angle"):
        converter.convert(snapshot, tmp_path / "out")


def test_converter_refuses_a_missing_timestep_line(snapshot, tmp_path):
    """Without the MJCF timestep line the frame interval cannot be confirmed, so the conversion stops instead of
    stamping the nominal 30 fps (#809). Planted control: restoring the line converts."""
    path = snapshot / converter.TIMESTEP_SOURCE
    original = path.read_text()
    path.write_text('MJCF = """<option gravity="0 0 -9.81"/>"""\n')
    git(snapshot, "commit", "-q", "-am", "no timestep line")
    with pytest.raises(ValueError, match="cannot confirm the frame interval"):
        converter.convert(snapshot, tmp_path)
    path.write_text(original)
    git(snapshot, "commit", "-q", "-am", "the timestep line again")
    assert converter.convert(snapshot, tmp_path)["artifacts"]
