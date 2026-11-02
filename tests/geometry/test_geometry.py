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
