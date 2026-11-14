"""The published replay is bound to actual native solver output, not target angles."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/examples/robot-replay/produce.py"
BUNDLE = ROOT / "software/cadagent/webkit/simulation/examples/two-link-arm"
SPEC = importlib.util.spec_from_file_location("robot_recording_example", SOURCE)
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)


def test_committed_recording_receipt_binds_every_source_and_artifact():
    receipt = json.loads((BUNDLE / "receipt.json").read_bytes())
    for path, expected in receipt["sources"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    for path, expected in receipt["artifacts"].items():
        assert hashlib.sha256((BUNDLE / path).read_bytes()).hexdigest() == expected, path
    assert receipt["configuration"] == json.loads(SOURCE.with_name("config.json").read_bytes())
    assert receipt["engine"] == {"name": "MuJoCo", "version": "3.3.7"}
    assert not any(receipt["observations"]["solver_warning_counts"])
    recording = json.loads((BUNDLE / "recording.json").read_bytes())
    assert len(recording["frames"]) == 501
    assert recording["frames"][0]["time_s"] == 0
    assert recording["frames"][-1]["time_s"] == 10
    capture = json.loads((BUNDLE / "preview.json").read_bytes())
    for path, expected in capture["sources"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    assert hashlib.sha256((BUNDLE / capture["artifact"]["path"]).read_bytes()).hexdigest() == capture["artifact"]["sha256"]


def test_actual_solver_recording_preserves_link_length_and_responds_to_mass(tmp_path):
    pytest.importorskip("mujoco")
    config = json.loads(SOURCE.with_name("config.json").read_bytes())
    config["duration_s"] = 1
    path = tmp_path / "config.json"
    path.write_bytes(producer.encoded(config))
    recording, receipt = producer.produce(path, tmp_path / "baseline")
    assert receipt["effective_settings"]["completed_steps"] == 500
    assert len(recording["frames"]) == 51
    assert receipt["observations"]["max_target_error_rad"][1] > .1
    assert receipt["observations"]["peak_applied_torque_nm"][1] <= config["torque_limit_nm"][1]
    for frame in recording["frames"]:
        base, upper, forearm = frame["poses"]
        assert base["position"] == [0, 0, 0]
        assert math.dist(upper["position"], forearm["position"]) == pytest.approx(config["link_lengths_m"][0], abs=1e-10)
        for body in frame["poses"]:
            assert all(math.isfinite(v) for v in body["position"] + body["quaternion"])
            assert math.hypot(*body["quaternion"]) == pytest.approx(1, abs=1e-10)
    assert recording["frames"][-1]["poses"][2]["quaternion"] != recording["frames"][0]["poses"][2]["quaternion"]
    config["link_masses_kg"] = [2.4, 1.4]
    path.write_bytes(producer.encoded(config))
    heavier, changed = producer.produce(path, tmp_path / "heavy")
    assert heavier["frames"][-1]["poses"] != recording["frames"][-1]["poses"], "displayed motion must respond to actual physics inputs"
    assert changed["artifacts"]["model.xml"] != receipt["artifacts"]["model.xml"]
    producer.produce(path, tmp_path / "heavy", check=True)
    (tmp_path / "heavy/recording.json").write_text("{}")
    with pytest.raises(ValueError, match="outputs differ"):
        producer.produce(path, tmp_path / "heavy", check=True)


@pytest.mark.parametrize("key,value", [("timestep_s", float("nan")), ("duration_s", 600),
    ("sample_hz", 49), ("link_masses_kg", [-1, .7]), ("joint_range_rad", [1, -1])])
def test_run_budget_and_physical_inputs_are_checked_before_native_solver(key, value):
    config = json.loads(SOURCE.with_name("config.json").read_bytes())
    config[key] = value
    with pytest.raises(ValueError):
        producer.validate_config(config)
