"""Geometry helpers on real cadquery solids."""

from __future__ import annotations

import pytest

cq = pytest.importorskip("cadquery")
trimesh = pytest.importorskip("trimesh")

from cadagent import geometry  # noqa: E402

def box(x, y, z, at=(0, 0, 0)):
    return cq.Workplane().box(x, y, z, centered=False).val().translate(at)

def test_solid_report_of_a_box():
    r = geometry.solid_report(box(10, 20, 30))
    assert r["cad_valid"] is True and r["solid_count"] == 1
    assert r["volume_cm3"] == pytest.approx(6.0)
    assert r["size_mm"] == pytest.approx([10, 20, 30])

def test_pairwise_intersections_measure_overlap_and_honour_skip_pairs():
    shapes = {"a": box(10, 10, 10), "b": box(10, 10, 10, at=(5, 0, 0)), "c": box(5, 5, 5, at=(50, 0, 0))}
    rows = {tuple(r["parts"]): r["intersection_mm3"] for r in geometry.pairwise_intersections(shapes)}
    assert rows[("a", "b")] == pytest.approx(500.0)
    assert rows[("a", "c")] == pytest.approx(0.0) and rows[("b", "c")] == pytest.approx(0.0)
    skipped = geometry.pairwise_intersections(shapes, skip_pairs=[("b", "a")])
    assert [r["parts"] for r in skipped] == [["a", "c"], ["b", "c"]]

def test_min_gap_between_separated_and_touching_boxes():
    assert geometry.min_gap(box(10, 10, 10), box(10, 10, 10, at=(15, 0, 0))) == pytest.approx(5.0)
    assert geometry.min_gap(box(10, 10, 10), box(10, 10, 10, at=(10, 0, 0))) == pytest.approx(0.0)

def test_export_print_stl_rotates_flattens_and_is_watertight(tmp_path):
    out = tmp_path / "part.stl"
    r = geometry.export_print_stl(box(10, 20, 30, at=(40, -7, 3)), out, rotation=((1, 0, 0), 90))
    assert r["watertight"] is True and r["cad_valid"] is True and r["solid_count"] == 1
    assert r["print_bounds_mm"] == pytest.approx([10, 30, 20])
    mesh = trimesh.load_mesh(out)
    assert mesh.is_watertight
    assert mesh.bounds[0] == pytest.approx([0, 0, 0], abs=1e-6)
    assert mesh.volume == pytest.approx(6000.0, rel=1e-6)

def test_downward_area_ignores_the_bed_and_finds_an_overhang(tmp_path):
    plain = tmp_path / "plain.stl"
    geometry.export_print_stl(box(20, 20, 10), plain)
    assert geometry.downward_area(plain)["downward_area_mm2"] == pytest.approx(0.0)

    tee = box(4, 4, 10, at=(8, 8, 0)).fuse(box(20, 20, 2, at=(0, 0, 10)))
    t_path = tmp_path / "tee.stl"
    geometry.export_print_stl(tee, t_path)
    r = geometry.downward_area(t_path)
    assert r["downward_area_mm2"] == pytest.approx(20 * 20 - 4 * 4)
    assert r["large_face_centers_mm"]

def test_within_bed():
    assert geometry.within_bed([200, 100, 50], [256, 256, 256])
    assert not geometry.within_bed([257, 100, 50], [256, 256, 256])
    assert geometry.within_bed([200, 100, 900], [256, 256])

# --- robust_union / robust_cut (#249) -------------------------------------------------------------------------------

def swept_tube(shift):
    """A tube swept along an arc; a few shifted by ``shift`` = 1 µm steps are nearly coincident solids."""
    path = cq.Workplane("XZ").spline([(0, 0), (5, 5 + shift), (10, 0)])
    return cq.Workplane("XY").circle(3).sweep(path).val().translate((shift, 0, 0))

class _Invalid:
    """Stands in for the invalid shape OCCT can return from a boolean."""
    wrapped = box(1, 1, 1).wrapped

    def clean(self):
        return self

    def isValid(self):
        return False

def test_robust_union_survives_a_multi_fuse_of_nearly_coincident_solids():
    tubes = [swept_tube(i * 1e-6) for i in range(3)]
    report = []
    out = geometry.robust_union(*tubes, report=report)
    assert out.isValid() and len(out.Solids()) == 1
    assert out.Volume() == pytest.approx(tubes[0].Volume(), rel=1e-4)
    plain = tubes[0].fuse(*tubes[1:]).clean()
    if plain.Volume() < 1.0:                              # OCCT 7.9 returns an empty, *valid* compound here
        assert plain.isValid()
        assert [r["fallback"] for r in report] == ["sequential"] and report[0]["reason"] == "no solids"

def test_robust_union_falls_back_to_one_at_a_time_when_the_multi_fuse_is_invalid(monkeypatch):
    real_fuse = cq.Shape.fuse

    def fuse(self, *others, **kw):
        return _Invalid() if len(others) > 1 else real_fuse(self, *others, **kw)

    monkeypatch.setattr(cq.Shape, "fuse", fuse)
    boxes = [box(10, 10, 10, at=(i * 5, 0, 0)) for i in range(4)]
    report = []
    out = geometry.robust_union(*boxes, None, report=report)
    assert out.isValid() and out.Volume() == pytest.approx(25 * 10 * 10)
    assert report == [{"op": "union", "fallback": "sequential", "shapes": 4, "reason": "invalid shape"}]

def test_robust_union_raises_rather_than_return_an_invalid_shape(monkeypatch):
    monkeypatch.setattr(cq.Shape, "fuse", lambda self, *others, **kw: _Invalid())
    with pytest.raises(geometry.GeometryError, match="one at a time"):
        geometry.robust_union(box(1, 1, 1), box(1, 1, 1, at=(0.5, 0, 0)), box(1, 1, 1, at=(1, 0, 0)))

def test_robust_union_and_cut_refuse_an_invalid_input():
    with pytest.raises(geometry.GeometryError, match="union argument 1"):
        geometry.robust_union(box(1, 1, 1), _Invalid())
    with pytest.raises(geometry.GeometryError, match="cut tool 0"):
        geometry.robust_cut(box(1, 1, 1), _Invalid())

def test_robust_cut_plain_path_reports_nothing():
    report = []
    out = geometry.robust_cut(box(10, 10, 10), box(2, 2, 20, at=(1, 1, -5)), box(2, 2, 20, at=(6, 6, -5)),
                              report=report)
    assert out.Volume() == pytest.approx(1000 - 2 * 40) and report == []
    assert geometry.robust_cut(box(1, 1, 1)).Volume() == pytest.approx(1.0)

def test_robust_cut_nudges_a_tool_whose_cut_raises(monkeypatch):
    real_cut = cq.Shape.cut
    pin = box(2, 2, 20, at=(4, 4, -5))

    def cut(self, *tools, **kw):
        if any(t.BoundingBox().xmin == pytest.approx(4.0, abs=1e-9) for t in tools):
            raise ValueError("Null TopoDS_Shape object")  # what OCCT raised where a cone met a pin hole
        return real_cut(self, *tools, **kw)

    monkeypatch.setattr(cq.Shape, "cut", cut)
    report = []
    out = geometry.robust_cut(box(10, 10, 10), pin, box(1, 1, 20, at=(0, 0, -5)), report=report)
    assert out.isValid() and out.Volume() == pytest.approx(1000 - 40 - 10)
    assert report[0]["fallback"] == "one_at_a_time" and "Null TopoDS_Shape" in report[0]["reason"]
    assert report[1] == {"op": "cut", "tool": 0, "nudge_mm": [0.01, 0.0, 0.0],
                         "reason": "raised ValueError: Null TopoDS_Shape object"}
    assert len(report) == 2                               # the second tool needed no nudge

def test_robust_cut_raises_when_every_nudge_fails(monkeypatch):
    def cut(self, *tools, **kw):
        raise ValueError("Null TopoDS_Shape object")

    monkeypatch.setattr(cq.Shape, "cut", cut)
    with pytest.raises(geometry.GeometryError, match="every nudge"):
        geometry.robust_cut(box(10, 10, 10), box(2, 2, 20, at=(4, 4, -5)))

def test_robust_cut_rejects_a_result_that_gained_volume(monkeypatch):
    monkeypatch.setattr(cq.Shape, "cut", lambda self, *tools, **kw: box(20, 20, 20))
    with pytest.raises(geometry.GeometryError, match="volume"):
        geometry.robust_cut(box(10, 10, 10), box(2, 2, 20, at=(4, 4, -5)), nudges=[(0.01, 0, 0)])

# --- the 1 µm weld in export_print_stl (#249) ----------------------------------------------------------------------

def split_cube(gap_mm, drop_face=False):
    """A 10 mm cube mesh whose corner vertex 0 is split in two, ``gap_mm`` apart; optionally with a face missing."""
    np = pytest.importorskip("numpy")
    cube = trimesh.creation.box(extents=(10, 10, 10))
    vertices = np.vstack([cube.vertices, cube.vertices[0] + (gap_mm, 0, 0)])
    faces = np.array(cube.faces)
    users = np.flatnonzero((faces == 0).any(axis=1))
    for f in users[: len(users) // 2]:                    # half the corner's faces use the copy
        faces[f][faces[f] == 0] = len(vertices) - 1
    if drop_face:
        faces = faces[np.flatnonzero(~(faces == 3).any(axis=1))[1:]]
    return trimesh.Trimesh(vertices, faces, process=False)

def write_mesh_instead(monkeypatch, mesh):
    monkeypatch.setattr(cq.exporters, "export", lambda shape, path, **kw: mesh.export(path))

def test_export_print_stl_welds_a_sub_micron_split_vertex(monkeypatch, tmp_path):
    mesh = split_cube(0.0004)
    out = tmp_path / "split.stl"
    mesh.export(out)
    assert not trimesh.load_mesh(out).is_watertight      # the split survives the STL round trip
    write_mesh_instead(monkeypatch, mesh)
    r = geometry.export_print_stl(box(10, 10, 10), out)
    assert r["watertight"] is True and r["vertices_welded"] == 1
    assert r["mesh_volume_mm3"] == pytest.approx(1000.0, abs=0.05)  # the weld moves one corner by 0.4 µm
    assert r["mesh_volume_before_weld_mm3"] == pytest.approx(r["mesh_volume_mm3"], abs=0.05)
    assert trimesh.load_mesh(out).is_watertight          # the rewritten STL is welded too

def test_export_print_stl_still_rejects_a_real_hole(monkeypatch, tmp_path):
    write_mesh_instead(monkeypatch, split_cube(0.0004, drop_face=True))
    with pytest.raises(geometry.GeometryError, match="non-watertight"):
        geometry.export_print_stl(box(10, 10, 10), tmp_path / "open.stl")
    write_mesh_instead(monkeypatch, split_cube(0.01))     # a 10 µm split is a gap, not a tessellation artefact
    with pytest.raises(geometry.GeometryError, match="non-watertight"):
        geometry.export_print_stl(box(10, 10, 10), tmp_path / "gap.stl")
    write_mesh_instead(monkeypatch, split_cube(0.0004))
    with pytest.raises(geometry.GeometryError, match="non-watertight"):
        geometry.export_print_stl(box(10, 10, 10), tmp_path / "off.stl", weld_mm=0)

def test_export_print_stl_of_a_clean_part_welds_nothing(tmp_path):
    r = geometry.export_print_stl(box(10, 20, 30), tmp_path / "plain.stl")
    assert r["vertices_welded"] == 0 and r["mesh_volume_mm3"] == pytest.approx(6000.0, rel=1e-6)
