"""Gyropup's authored turret order -> the featured build guide (#811): committed bytes, geometry and the converter.

The committed example is checked against its receipt, and its neutral pose against geometry that holds across the
scene's moving groups (bearing races are concentric, each flywheel sits on its motor's axis). The converter itself
runs on a small synthetic Gyropup checkout in a temporary Git repository, so these tests need no Gyropup checkout.
Each check is shown to fail on a planted fault.
"""
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "docs/examples/build-guide/gyropup_turret.py"
BUNDLE = ROOT / "software/cadagent/webkit/assembly/examples/gyropup-turret"
SPEC = importlib.util.spec_from_file_location("gyropup_turret_guide", SOURCE)
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


def centre(bounds):
    return [(bounds[i] + bounds[i + 3]) / 2 for i in range(3)]


# Pairs whose members sit in different moving groups of the scene, so a wrong group translation separates them.
CONCENTRIC = [("pan_bearing", "pan_bearing_inner", 3),          # base / pan: the pan bearing's races
              ("tilt_bearing", "tilt_bearing_inner", 3),        # pan / tilt: the tilt bearing's races
              ("flywheel", "flywheel_motor_l", 2),              # wheel_l / tilt: hub on its motor's axis (x, y)
              ("flywheel_m", "flywheel_motor_r", 2),            # wheel_r / tilt
              ("slip_ring", "slip_ring_rotor", 2)]              # base / pan: the slip ring's rotor on its axis


def misaligned(bounds):
    return [f"{a}/{b}" for a, b, axes in CONCENTRIC
            if max(abs(p - q) for p, q in zip(centre(bounds[a])[:axes], centre(bounds[b])[:axes])) > 0.1]


def test_committed_example_matches_its_receipt():
    assert converter.check(BUNDLE) == []
    receipt = json.loads((BUNDLE / "receipt.json").read_bytes())
    assert receipt["project"] == "Valpatel/gyropup" and receipt["license"] == "MIT"
    assert len(receipt["revision"]) == 40 and receipt["steps"] >= 5
    assert "no vendor source CAD" in receipt["method"]
    assert all(len(h) == 64 for h in receipt["sources"].values())
    assert (BUNDLE / "LICENSE.txt").read_bytes().startswith(b"MIT License")
    guide = json.loads((BUNDLE / "guide.json").read_bytes())
    assert guide["snapshot"]["status"] == "wip" and guide["snapshot"]["source_commit"] == receipt["revision"]
    for phrase in ("Example sequence", "work-in-progress", "not a verified build procedure", "CAD step order does not prove"):
        assert phrase in guide["source"]["qualification"]
    # Every folder stays within the repository's growth limit of 20 files (README.md not counted).
    for folder in [BUNDLE, *[p for p in BUNDLE.iterdir() if p.is_dir()]]:
        assert len([p for p in folder.iterdir() if p.is_file() and p.name != "README.md"]) <= 20, folder


def test_committed_example_check_catches_a_planted_byte(tmp_path):
    copy = tmp_path / "bundle"
    shutil.copytree(BUNDLE, copy)
    mesh = copy / "base/pan_base.stl"
    data = bytearray(mesh.read_bytes())
    data[100] ^= 1
    mesh.write_bytes(bytes(data))
    (copy / "base/stray.stl").write_bytes(b"x")
    problems = converter.check(copy)
    assert "base/pan_base.stl: does not match its receipt" in problems
    assert "view.json: base/pan_base.stl does not match its hash" in problems
    assert "base/stray.stl: not in the receipt" in problems


def test_neutral_pose_keeps_parts_of_different_groups_together():
    view = json.loads((BUNDLE / "view.json").read_bytes())
    bounds = {p["name"]: p["bounds_mm"] for p in view["parts"]}
    assert misaligned(bounds) == []
    # The mounting face is z = 0: the pan base stands on it.
    assert abs(bounds["pan_base"][2]) < 0.01
    # Planted control: leave the tilt group in its own frame (no tilt pivot) and the tilt bearing's races part.
    planted = dict(bounds)
    planted["tilt_bearing_inner"] = [v - (140 if i % 3 == 2 else 0) for i, v in enumerate(bounds["tilt_bearing_inner"])]
    assert misaligned(planted) == ["tilt_bearing/tilt_bearing_inner"]


# ------------------------------------------------------------------------------------- converter on a synthetic repo

def stl(origin, size=(2.0, 2.0, 2.0)):
    """A two-triangle binary STL with a recognisable header."""
    x, y, z = origin
    tris = [((x, y, z), (x + size[0], y, z), (x, y + size[1], z + size[2])),
            ((x, y, z), (x, y + size[1], z), (x + size[0], y, z + size[2]))]
    out = bytearray(b"gyropup turret_box".ljust(80) + struct.pack("<I", len(tris)))
    for tri in tris:
        out += struct.pack("<3f", 0, 0, 1) + b"".join(struct.pack("<3f", *v) for v in tri) + b"\0\0"
    return bytes(out)


STAGES = (("one", "One", "the first steps", 1, 3), ("two", "Two", "the rest", 4, 5))


def make_repo(path: Path, rows=None):
    pivots = {"pan": [0, 0, 145.0], "tilt": [0, 0, 140.0], "pinion": [-52.65, 0, 145.0], "dial": [-48.0, 0, 0],
              "wheel_l": [25.0, 25.81, 0], "wheel_r": [25.0, -25.81, 0], "flap": [-87.0, 0, 91.0]}
    names = [("base_part", "base", (0, 0, 145)), ("pan_part", "pan", (0, 0, 0)), ("tilt_part", "tilt", (0, 0, 0)),
             ("wheel_part", "wheel_l", (0, 0, 0)), ("pinion_part", "pinion", (-52.65, 0, 145)),
             ("unused", "base", (5, 5, 150)), ("box_part", "j501", (0, 0, 0))]
    parts = []
    (path / "hardware/exports/sim/turret_box").mkdir(parents=True)
    (path / "hardware/cad/turret").mkdir(parents=True)
    for name, group, origin in names:
        data = stl(origin)
        (path / f"hardware/exports/sim/turret_box/{name}.stl").write_bytes(data)
        parts.append({"name": name, "part": name, "group": group, "file": f"{name}.stl", "color": "#336699",
                      "title": name.replace("_", " "), "sha256": hashlib.sha256(data).hexdigest()})
    (path / "hardware/exports/sim/turret_box/manifest.json").write_text(json.dumps({"pivots": pivots, "parts": parts}))
    rows = rows or [(f"Step {k}", [name], {name: 10} if k == 1 else ({name: (0, -5, 0)} if k == 2 else {}),
                     (0.6, -1.0, 0.7), f"Instruction {k}.")
                    for k, name in enumerate(["base_part", "pan_part", "tilt_part", "wheel_part", "pinion_part"], 1)]
    (path / "hardware/cad/turret/turret_assembly.py").write_text(
        "import nothing_here  # never imported by the converter\nSTEPS = " + repr(rows) + "\n")
    (path / "LICENSE").write_text("MIT License\n\nCopyright (c) test\n")
    git = lambda *a: subprocess.run(["git", "-C", str(path), *a], check=True, capture_output=True)
    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "synthetic")


@pytest.fixture
def small(monkeypatch):
    monkeypatch.setattr(converter, "STAGES", STAGES)


def test_converter_translates_each_group_and_leaves_out_unused_parts(tmp_path, small):
    make_repo(tmp_path / "repo")
    out = tmp_path / "out"
    out.mkdir()
    receipt = converter.convert(tmp_path / "repo", out)
    view = json.loads((out / "view.json").read_bytes())
    lows = {p["name"]: [round(v, 3) for v in p["bounds_mm"][:3]] for p in view["parts"]}
    assert lows["base_part"] == [0.0, 0.0, 0.0]                  # box frame, less the pan pivot
    assert lows["pan_part"] == [0.0, 0.0, 0.0]                   # already relative to the pan pivot
    assert lows["tilt_part"] == [0.0, 0.0, 140.0]                # plus the tilt pivot
    assert lows["wheel_part"] == [25.0, 25.81, 140.0]            # plus tilt and its own pivot
    assert lows["pinion_part"] == [-52.65, 0.0, 0.0]             # box frame, like the base
    assert "box_part" not in lows and receipt["excluded"]["parts"] == ["unused"]
    guide = json.loads((out / "guide.json").read_bytes())
    assert guide["steps"][0]["offsets_mm"] == {"base_part": [0.0, 0.0, 10.0]}       # a number lifts along +z
    assert guide["steps"][1]["offsets_mm"] == {"pan_part": [0.0, -5.0, 0.0]}        # a vector is kept
    assert guide["steps"][1]["parts"] == ["base_part", "pan_part"] and guide["steps"][1]["requires"] == ["step-01"]
    assert [s["subassembly"] for s in guide["steps"]] == ["one", "one", "one", "two", "two"]
    assert sorted(receipt["artifacts"]) == sorted(["LICENSE.txt", "guide.json", "view.json", "one/README.md", "two/README.md",
        "one/base_part.stl", "one/pan_part.stl", "one/tilt_part.stl", "two/wheel_part.stl", "two/pinion_part.stl"])
    # Triangles and normals unchanged: header, count and the first normal are the source's; only vertices move.
    source = (tmp_path / "repo/hardware/exports/sim/turret_box/tilt_part.stl").read_bytes()
    mesh = (out / "one/tilt_part.stl").read_bytes()
    assert mesh[:96] == source[:96] and len(mesh) == len(source) and mesh != source


def test_converter_refuses_unknown_or_repeated_parts(tmp_path, small):
    row = lambda k, name: (f"Step {k}", [name], {}, (1, 0, 0), "Text.")
    make_repo(tmp_path / "a", [row(1, "base_part"), row(2, "pan_part"), row(3, "ghost"), row(4, "tilt_part"), row(5, "wheel_part")])
    with pytest.raises(ValueError, match="does not have"):
        converter.convert(tmp_path / "a", tmp_path / "a-out")
    make_repo(tmp_path / "b", [row(1, "base_part"), row(2, "pan_part"), row(3, "pan_part"), row(4, "tilt_part"), row(5, "wheel_part")])
    with pytest.raises(ValueError, match="added by two steps"):
        converter.convert(tmp_path / "b", tmp_path / "b-out")
    make_repo(tmp_path / "c", [row(1, "base_part"), row(2, "pan_part")])
    with pytest.raises(ValueError, match="expected 5 steps"):
        converter.convert(tmp_path / "c", tmp_path / "c-out")


def test_converter_refuses_a_dirty_checkout(tmp_path, small):
    make_repo(tmp_path / "repo")
    (tmp_path / "repo/hardware/exports/sim/turret_box/base_part.stl").write_bytes(b"edited")
    with pytest.raises(SystemExit, match="uncommitted"):
        converter.convert(tmp_path / "repo", tmp_path / "out")
