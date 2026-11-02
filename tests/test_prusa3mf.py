"""PrusaSlicer project 3MFs (cadagent.manufacturing.prusa3mf): volumes on their tools, the wipe tower's place, plates,
byte stability and the read-back. Hand-built boxes (numpy only), except the PrusaSlicer run (where installed)."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from cadagent.manufacturing import plates as P
from cadagent.manufacturing import prusa3mf as M

BED = (250.0, 210.0, 200.0)
FACES = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                  [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])


def box(x0, y0, z0, x1, y1, z1):
    v = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=float)
    return v, FACES.copy()


def cube_with_cap():
    """A 30 mm cube on tool 1 with a 4 mm cap on tool 2, away from the origin (the writer centres it)."""
    return [(box(40, 40, 5, 70, 70, 15), "body", 1), (box(40, 40, 15, 70, 70, 19), "cap", 2)]


def members(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


# ---------------------------------------------------------------------------------------------------------------
# write_project

def test_volumes_on_their_tools(tmp_path):
    path = tmp_path / "cube.3mf"
    r = M.write_project(path, [("cube", cube_with_cap(), (10, -5))], BED, wipe_tower=(150, 140))
    assert r["ok"] and r["extruders"] == [1, 2]
    (obj,) = r["objects"]
    assert obj["position"] == [135.0, 100.0] and obj["bounds_xy"] == [120.0, 85.0, 150.0, 115.0]
    assert [(v["name"], v["extruder"], v["triangles"], v["volume_mm3"]) for v in obj["volumes"]] == \
        [("body", 1, 12, 9000.0), ("cap", 2, 12, 3600.0)]
    files = members(path)
    assert sorted(files) == ["3D/3dmodel.model", "Metadata/Prusa_Slicer_wipe_tower_information.xml",
                             "Metadata/Slic3r_PE_model.config", "[Content_Types].xml", "_rels/.rels"]
    cfg = ET.fromstring(files[M.MODEL_CONFIG])
    vols = cfg.findall("object/volume")
    assert [(v.get("firstid"), v.get("lastid")) for v in vols] == [("0", "11"), ("12", "23")]
    assert [{m.get("key"): m.get("value") for m in v}["extruder"] for v in vols] == ["1", "2"]
    tower = ET.fromstring(files[M.WIPE_TOWER_INFO])
    assert tower.attrib == {"bed_idx": "0", "position_x": "150", "position_y": "140", "rotation_deg": "0"}
    back = M.read_project(path)
    v = back["objects"][0]["volumes"][0]["vertices"]
    assert v[:, 2].min() == 0 and abs(v[:, 0].min() + 15) < 1e-9     # lowest point on z=0, outline centred


def test_wipe_tower_default_and_off(tmp_path):
    two, one = cube_with_cap(), [(box(0, 0, 0, 10, 10, 10), "pin", 3)]
    M.write_project(tmp_path / "a.3mf", [("cube", two, (0, 0))], BED)
    tower = ET.fromstring(members(tmp_path / "a.3mf")[M.WIPE_TOWER_INFO])
    assert (float(tower.get("position_x")), float(tower.get("position_y"))) == M.DEFAULT_WIPE_TOWER[:2]
    M.write_project(tmp_path / "b.3mf", [("cube", two, (0, 0))], BED, wipe_tower=False)
    M.write_project(tmp_path / "c.3mf", [("pin", one, (0, 0))], BED)        # one tool: no tower
    for name in ("b.3mf", "c.3mf"):
        assert M.WIPE_TOWER_INFO not in members(tmp_path / name)
    r = M.write_project(tmp_path / "d.3mf", [("cube", two, (0, 0))], BED, wipe_tower=(200, 20, 90))
    assert r["wipe_tower"] == {"x": 200.0, "y": 20.0, "rotation_deg": 90.0}


def test_byte_reproducible(tmp_path, monkeypatch):
    objs = [("cube", cube_with_cap(), (0, 0)), ("pin", [(box(0, 0, 0, 8, 8, 20), "pin", 2)], (60, 0, 30))]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = M.write_project(tmp_path / "a" / "p.3mf", objs, BED)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    b = M.write_project(tmp_path / "b" / "p.3mf", objs, BED)
    assert a["sha256"] == b["sha256"]
    assert (tmp_path / "a" / "p.3mf").read_bytes() == (tmp_path / "b" / "p.3mf").read_bytes()


def test_turned_object_reads_back(tmp_path):
    r = M.write_project(tmp_path / "t.3mf", [("bar", [(box(0, 0, 0, 100, 10, 5), "bar", 1)], (0, 0, 30))], BED)
    x0, y0, x1, y1 = r["objects"][0]["bounds_xy"]
    c, s = P.rotation(30)
    assert abs((x1 - x0) - (100 * c + 10 * s)) < 1e-3 and abs((y1 - y0) - (100 * s + 10 * c)) < 1e-3


def test_open_mesh_is_refused_and_removed(tmp_path):
    v, f = box(0, 0, 0, 10, 10, 10)
    path = tmp_path / "open.3mf"
    with pytest.raises(M.Prusa3mfError, match="read-back mismatch"):
        M.write_project(path, [("open", [((v, f[:-1]), "open", 1)], (0, 0))], BED)
    assert not path.exists()


@pytest.mark.parametrize("objects, match", [
    ([], "at least one object"),
    ([("x", [], (0, 0))], "at least one volume"),
    ([("x", [(box(0, 0, 0, 1, 1, 1), "a", 0)], (0, 0))], "extruder"),
    ([("x", [(box(0, 0, 0, 1, 1, 1), "a", 1.0)], (0, 0))], "extruder"),
    ([("x", [(box(0, 0, 0, 40, 40, 1), "a", 1)], (110, 0))], "outside"),
    ([("x", [(box(0, 0, 0, 10, 10, 250), "a", 1)], (0, 0))], "tall"),
    ([("x", [(box(0, 0, 0, 1, 1, 1), "a", 1)], (0,))], "place"),
])
def test_bad_input(tmp_path, objects, match):
    with pytest.raises(M.Prusa3mfError, match=match):
        M.write_project(tmp_path / "x.3mf", objects, BED)
    assert not (tmp_path / "x.3mf").exists()


def test_trimesh_like_meshes(tmp_path):
    class Mesh:
        def __init__(self, v, f):
            self.vertices, self.faces = v, f
    r = M.write_project(tmp_path / "m.3mf", [("m", [(Mesh(*box(0, 0, 0, 5, 5, 5)), "m", 1)], (0, 0))], BED)
    assert r["objects"][0]["volumes"][0]["volume_mm3"] == 125.0


# ---------------------------------------------------------------------------------------------------------------
# write_plates

def plate_parts():
    return {"cube": cube_with_cap(), "bar": [(box(0, 0, 0, 240, 10, 5), "bar", 1)],
            "pin": [(box(0, 0, 0, 8, 8, 20), "pin", 2)]}


def as_layout(result):
    return [P.Plate(p["plate"], p["group"], [P.Placement(c["part"], c["copy"], c["x"], c["y"], c["width"],
                                                         c["depth"], c["angle"]) for c in p["copies"]])
            for p in result["plates"]]


def test_plates_by_tools(tmp_path):
    (tmp_path / "plate-07-old.3mf").write_bytes(b"stale")
    (tmp_path / "keep.3mf").write_bytes(b"not ours")
    r = M.write_plates(tmp_path, plate_parts(), BED, quantities={"cube": 3, "pin": 10})
    names = [Path(p["file"]).name for p in r["plates"]]
    assert names == ["plate-01-t1-t2.3mf", "plate-02-t1.3mf", "plate-03-t2.3mf"]
    assert sorted(p.name for p in tmp_path.glob("*.3mf")) == sorted(names + ["keep.3mf"])
    assert [p["wipe_tower"] is not None for p in r["plates"]] == [True, False, False]
    assert all(p["report"]["ok"] for p in r["plates"])
    tower = M.tower_keep_out(M.DEFAULT_WIPE_TOWER)
    layout = as_layout(r)
    assert not P.check_plates(layout[:1], BED, P.DEFAULT_GAP_MM, P.DEFAULT_MARGIN_MM, keep_out=[tower])
    assert not P.check_plates(layout, BED, P.DEFAULT_GAP_MM, P.DEFAULT_MARGIN_MM,
                              quantities={"cube": 3, "bar": 1, "pin": 10},
                              groups={"cube": "T1+T2", "bar": "T1", "pin": "T2"})
    # each object is written where the layout put it
    for p in r["plates"]:
        for c, o in zip(p["copies"], p["report"]["objects"]):
            assert np.allclose(o["bounds_xy"], [c["x"], c["y"], c["x"] + c["width"], c["y"] + c["depth"]], atol=1e-3)
    again = M.write_plates(tmp_path / "again", plate_parts(), BED, quantities={"cube": 3, "pin": 10})
    assert [p["sha256"] for p in again["plates"]] == [p["sha256"] for p in r["plates"]]


def test_plates_custom_groups_and_turns(tmp_path):
    parts = {"long": [(box(0, 0, 0, 260, 10, 5), "long", 1)], "pin": [(box(0, 0, 0, 8, 8, 20), "pin", 2)]}
    r = M.write_plates(tmp_path, parts, BED, groups={"long": "PLA", "pin": "PLA"}, stem="set")
    (plate,) = r["plates"]
    assert Path(plate["file"]).name == "set-01-pla.3mf" and plate["wipe_tower"] is not None
    assert [c["angle"] for c in plate["copies"] if c["part"] == "long"][0] not in (0, 90, 180, 270)
    with pytest.raises(M.Prusa3mfError, match="no volumes"):
        M.write_plates(tmp_path, parts, BED, quantities={"nothing": 1})
    with pytest.raises(M.Prusa3mfError, match="footprint"):
        M.write_plates(tmp_path, {"huge": [(box(0, 0, 0, 400, 400, 5), "huge", 1)]}, BED)


# ---------------------------------------------------------------------------------------------------------------
# PrusaSlicer itself

def prusa_slicer():
    """The command that runs PrusaSlicer, or None: on PATH, else the Flathub app."""
    exe = shutil.which("prusa-slicer") or shutil.which("PrusaSlicer")
    if exe:
        return [exe]
    flatpak = shutil.which("flatpak")
    if flatpak and subprocess.run([flatpak, "info", "com.prusa3d.PrusaSlicer"], capture_output=True).returncode == 0:
        return [flatpak, "run", "--command=prusa-slicer", "com.prusa3d.PrusaSlicer"]
    return None


# A two-tool printer from PrusaSlicer's defaults: the options a wipe tower needs, nothing from a vendor profile.
TWO_TOOLS = ["--bed-shape", "0x0,250x0,250x210,0x210", "--max-print-height", "200", "--nozzle-diameter", "0.4,0.4",
             "--temperature", "210,210", "--first-layer-temperature", "210,210", "--wipe-tower",
             "--use-relative-e-distances", "--layer-gcode", "G92 E0", "--gcode-flavor", "marlin2"]


@pytest.fixture
def slicer_dir():
    cmd = prusa_slicer()
    if cmd is None:
        pytest.skip("PrusaSlicer is not installed")
    # the Flathub sandbox cannot read /tmp: work beside the tests
    d = Path(tempfile.mkdtemp(prefix=".prusa3mf-", dir=Path(__file__).resolve().parent))
    try:
        yield cmd, d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def slice_gcode(cmd, path: Path) -> str:
    out = path.with_suffix(".gcode")
    run = subprocess.run(cmd + ["--export-gcode", *TWO_TOOLS, "--output", str(out), str(path)],
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stdout + run.stderr
    return out.read_text()


MOVE = re.compile(r"^G1 (?=.*X(-?[\d.]+))(?=.*Y(-?[\d.]+)).*E", re.M)


def walk(gcode: str):
    """(feature, tool, z, x, y) of every extruding XY move, after the priming lines."""
    tool, z, feature, out = 0, 0.0, "", []
    body = gcode.split("; CP PRIMING END", 1)[-1]
    for line in body.splitlines():
        if re.fullmatch(r"T\d+", line):
            tool = int(line[1:])
        elif line.startswith(";Z:"):
            z = float(line[3:])
        elif line.startswith(";TYPE:"):
            feature = line[6:]
        elif line.startswith("G1 ") and " E" in line and "X" in line and "Y" in line:
            x = float(re.search(r"X(-?[\d.]+)", line).group(1))
            y = float(re.search(r"Y(-?[\d.]+)", line).group(1))
            out.append((feature, tool, z, x, y))
    return out


def test_prusaslicer_slices_volumes_on_tools_with_tower_in_place(slicer_dir):
    cmd, d = slicer_dir
    path = d / "cube.3mf"
    r = M.write_project(path, [("cube", cube_with_cap(), (0, 0))], BED, wipe_tower=(150, 140))
    moves = walk(slice_gcode(cmd, path))
    part = [m for m in moves if m[0] in ("Perimeter", "External perimeter", "Solid infill", "Internal infill",
                                         "Top solid infill")]
    assert part and {t for f, t, z, x, y in part if z <= 10} == {0} and {t for f, t, z, x, y in part if z > 10.2} == {1}
    x0, y0, x1, y1 = r["objects"][0]["bounds_xy"]
    assert x0 - 0.5 < min(m[3] for m in part) and max(m[3] for m in part) < x1 + 0.5
    assert y0 - 0.5 < min(m[4] for m in part) and max(m[4] for m in part) < y1 + 0.5
    tower = [m for m in moves if m[0] == "Wipe tower"]
    assert tower, "no wipe tower printed"
    assert abs(min(m[3] for m in tower) - 150) < 2 and abs(min(m[4] for m in tower) - 140) < 2


def test_prusaslicer_slices_a_plate(slicer_dir):
    cmd, d = slicer_dir
    r = M.write_plates(d, plate_parts(), BED, quantities={"cube": 2})
    first = r["plates"][0]
    assert first["group"] == "T1+T2"
    moves = walk(slice_gcode(cmd, Path(first["file"])))
    tower = [m for m in moves if m[0] == "Wipe tower"]
    tx, ty, _ = M.DEFAULT_WIPE_TOWER
    assert tower and abs(min(m[3] for m in tower) - tx) < 2 and abs(min(m[4] for m in tower) - ty) < 2
    assert {m[1] for m in moves if m[0] == "External perimeter"} == {0, 1}
