"""cadagent.geometry.overhang_regions and `cad-agent overhangs`: downward faces past the limit, as connected regions."""
from __future__ import annotations

import json
import math

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from cadagent.geometry import overhang_regions  # noqa: E402


class Soup:
    """A trimesh-like triangle soup: every triangle has its own three vertices, as in an STL."""

    def __init__(self, triangles):
        tri = np.asarray(triangles, dtype=float).reshape(-1, 3, 3)
        self.vertices = tri.reshape(-1, 3)
        self.faces = np.arange(len(self.vertices)).reshape(-1, 3)


def ceiling(x, y, z, sx, sy):
    """A downward-facing rectangle (two triangles, normal -Z)."""
    a, b, c, d = (x, y, z), (x, y + sy, z), (x + sx, y + sy, z), (x + sx, y, z)
    return [(a, b, c), (a, c, d)]


def slope(deg, x=0.0, z=5.0, length=10.0, width=4.0):
    """A downward-facing rectangle rising at ``deg`` from horizontal along +X."""
    h = length * math.tan(math.radians(deg))
    a, b, c, d = (x, 0, z), (x, width, z), (x + length, width, z + h), (x + length, 0, z + h)
    return [(a, b, c), (a, c, d)]


BED = [((0, 0, 0), (1, 0, 0), (0, 1, 0))]          # an upward triangle at z=0: the lowest point, never flagged


def test_regions_are_grouped_sorted_and_located():
    mesh = Soup(BED + ceiling(0, 0, 20, 10, 10) + ceiling(30, 0, 5, 3, 3) + ceiling(50, 0, 0, 5, 5))
    r = overhang_regions(mesh)
    assert r["downward_area_mm2"] == pytest.approx(109.0)          # the square on the bed is left out
    assert [g["area_mm2"] for g in r["regions"]] == [100.0, 9.0]
    big = r["regions"][0]
    assert big["bounds_mm"] == [0.0, 0.0, 20.0, 10.0, 10.0, 20.0] and big["centre_mm"] == [5.0, 5.0, 20.0]
    assert (big["faces"], big["flattest_deg"], big["mean_slope_deg"]) == (2, 0.0, 0.0)
    assert r["angle"].startswith("slope from horizontal: 0 = flat ceiling")


def test_the_angle_is_the_slope_from_horizontal():
    mesh = Soup(BED + slope(30) + slope(45, x=20) + slope(60, x=40))
    r = overhang_regions(mesh)
    assert [g["flattest_deg"] for g in r["regions"]] == [30.0]     # 45° is at the limit (an STL chamfer), not past it
    assert r["regions"][0]["area_mm2"] == pytest.approx(10 / math.cos(math.radians(30)) * 4, abs=0.01)
    wide = overhang_regions(mesh, limit_deg=70)
    assert sorted(g["flattest_deg"] for g in wide["regions"]) == [30.0, 45.0, 60.0]
    assert overhang_regions(mesh, limit_deg=20)["regions"] == []
    for bad in (0, -5, 91):
        with pytest.raises(ValueError):
            overhang_regions(mesh, limit_deg=bad)


def test_shared_edges_join_regions_and_corners_do_not():
    # two 5 x 5 ceilings sharing an edge (vertices repeated, as in an STL): one region; a third touching a corner: its own
    mesh = Soup(BED + ceiling(0, 0, 10, 5, 5) + ceiling(5, 0, 10, 5, 5) + ceiling(10, 5, 10, 5, 5))
    assert [g["area_mm2"] for g in overhang_regions(mesh)["regions"]] == [50.0, 25.0]


def test_small_regions_are_counted_not_listed():
    mesh = Soup(BED + ceiling(0, 0, 10, 1, 1) + ceiling(5, 0, 10, 1.5, 2) + ceiling(10, 0, 10, 4, 4))
    r = overhang_regions(mesh, min_area=4)
    assert [g["area_mm2"] for g in r["regions"]] == [16.0]
    assert (r["small_regions"], r["small_area_mm2"]) == (2, 4.0)
    assert overhang_regions(Soup(BED))["regions"] == []
    with pytest.raises(ValueError, match="no triangles"):
        overhang_regions(Soup(np.zeros((0, 3, 3))))


def test_an_stl_path_and_the_bed_is_the_lowest_point(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    stem = trimesh.creation.box(extents=(4, 4, 10))
    stem.apply_translation((0, 0, 105))                 # the part sits at z=100, not on z=0
    plate = trimesh.creation.box(extents=(20, 20, 2))
    plate.apply_translation((0, 0, 111))
    path = tmp_path / "t.stl"
    trimesh.util.concatenate([stem, plate]).export(path)
    r = overhang_regions(path)
    assert [g["area_mm2"] for g in r["regions"]] == [400.0]   # the plate's underside; the stem's foot is on the bed
    assert r["regions"][0]["bounds_mm"][2] == r["regions"][0]["bounds_mm"][5] == 110.0


# ---------------------------------------------------------------------------------------------- cad-agent overhangs

def _project(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    from .test_report import make_project

    root = make_project(tmp_path)
    t = trimesh.util.concatenate([trimesh.creation.box(extents=(4, 4, 10)).apply_translation((0, 0, 5)),
                                  trimesh.creation.box(extents=(20, 20, 2)).apply_translation((0, 0, 11))])
    t.export(root / "exports" / "box.stl")
    trimesh.creation.box(extents=(10, 10, 10)).export(root / "exports" / "lid.stl")
    return root


def test_overhangs_command_writes_the_screen(tmp_path, capsys):
    from cadagent.cli import main

    root = _project(tmp_path)
    assert main(["overhangs", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "box" in out and "400.0 mm2" in out and "overhang-screen.json" in out
    data = json.loads((root / "exports" / "overhang-screen.json").read_text())
    assert (data["version"], data["limit_deg"], data["min_area_mm2"]) == (1, 45.0, 4.0)
    assert "not a slicer" in data["note"]
    assert data["parts"]["box"]["regions"][0]["area_mm2"] == 400.0 and data["parts"]["lid"]["regions"] == []
    assert len(data["parts"]["box"]["sha256"]) == 64

    # one part again, same settings: the other row stays; other settings: only that part
    data["parts"]["lid"]["marker"] = True
    (root / "exports" / "overhang-screen.json").write_text(json.dumps(data))
    assert main(["overhangs", "--project", str(root), "box"]) == 0
    assert json.loads((root / "exports" / "overhang-screen.json").read_text())["parts"]["lid"]["marker"] is True
    assert main(["overhangs", "--project", str(root), "box", "--limit", "30", "--min-area", "1"]) == 0
    data = json.loads((root / "exports" / "overhang-screen.json").read_text())
    assert set(data["parts"]) == {"box"} and data["limit_deg"] == 30.0
    # a row whose STL changed since is not kept by a run of another part
    assert main(["overhangs", "--project", str(root), "--limit", "30", "--min-area", "1"]) == 0
    trimesh = pytest.importorskip("trimesh")
    trimesh.creation.box(extents=(12, 12, 12)).export(root / "exports" / "lid.stl")
    assert main(["overhangs", "--project", str(root), "box", "--limit", "30", "--min-area", "1"]) == 0
    assert set(json.loads((root / "exports" / "overhang-screen.json").read_text())["parts"]) == {"box"}


def test_overhangs_command_fails_on_missing_or_unreadable_stls(tmp_path, capsys):
    from cadagent.cli import main

    root = _project(tmp_path)
    (root / "exports" / "lid.stl").unlink()
    assert main(["overhangs", "--project", str(root)]) == 1
    data = json.loads((root / "exports" / "overhang-screen.json").read_text())
    assert "not found" in data["parts"]["lid"]["error"] and data["parts"]["box"]["regions"]
    (root / "exports" / "lid.stl").write_text("x")
    assert main(["overhangs", "--project", str(root), "lid"]) == 1
    assert "no triangles" in json.loads((root / "exports" / "overhang-screen.json").read_text())["parts"]["lid"]["error"]
    capsys.readouterr()
    assert main(["overhangs", "--project", str(root), "nope"]) == 2
    assert "no such part" in capsys.readouterr().err
    assert main(["overhangs", "--project", str(root), "--limit", "0"]) == 2
