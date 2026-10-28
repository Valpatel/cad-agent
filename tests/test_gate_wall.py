"""Minimum-wall gate: mesh rays and exact B-rep rays."""

from __future__ import annotations

import json

import pytest

cq = pytest.importorskip("cadquery")
trimesh = pytest.importorskip("trimesh")

from cadagent.gates import wall  # noqa: E402


def plate(t=2.4):
    return cq.Workplane().box(20, 20, t, centered=False).val()


def ribbed(t=0.8):
    base = cq.Workplane().box(40, 40, 5, centered=False)
    return base.union(cq.Workplane().box(t, 30, 15, centered=False).translate((20, 5, 5))).val()


@pytest.mark.parametrize("source", ["mesh", "shape", "both"])
def test_a_2_4_mm_plate_passes_at_2_4_and_fails_at_2_5(source):
    p = plate()
    kw = {"mesh": p, "shape": p} if source == "both" else {source: p}
    ok = wall.check_wall("plate", 2.4, **kw)
    assert ok.status == "pass", ok.message
    bad = wall.check_wall("plate", 2.5, **kw)
    assert bad.status == "fail" and "2.400 mm < 2.5 mm" in bad.message
    assert bad.evidence["witnesses"][0]["thickness_mm"] == pytest.approx(2.4, abs=1e-3)


@pytest.mark.parametrize("source", ["mesh", "shape"])
def test_a_0_8_mm_rib_is_found_with_a_witness_on_the_rib(source):
    c = wall.check_wall("ribbed", 2.4, **{source: ribbed()})
    assert c.status == "fail"
    w = c.evidence["witnesses"][0]
    assert w["thickness_mm"] == pytest.approx(0.8, abs=1e-3)
    assert 20 - 1e-6 <= w["point"][0] <= 20.8 + 1e-6 and 20 - 1e-6 <= w["exit_point"][0] <= 20.8 + 1e-6
    method = "mesh-ray" if source == "mesh" else "brep-ray"
    assert c.evidence[method]["thin_area_mm2"] > 0 and c.evidence[method]["min_mm"] == pytest.approx(0.8, abs=1e-3)


def test_brep_probe_samples_every_face_whatever_its_area():
    r = wall.brep_thickness(ribbed(), grid=2)
    assert r["faces"] == 11 and r["rays"] >= r["faces"] and r["misses"] == 0
    # a mesh sub-sampled to two rays almost surely misses the rib; the B-rep probe cannot
    assert (r["thickness"] < 0.81).sum() >= 2 * 4


def test_curved_wall_reads_within_the_chord_tolerance():
    tube = cq.Workplane().circle(10).circle(7.6).extrude(20).val()
    c = wall.check_wall("tube", 2.4, mesh=tube, shape=tube)
    assert c.status == "pass"
    assert c.evidence["brep-ray"]["min_mm"] == pytest.approx(2.4, abs=1e-6)
    assert 2.39 <= c.evidence["mesh-ray"]["min_mm"] <= 2.4 + 1e-6


def test_numpy_fallback_agrees_with_the_rtree_engine(monkeypatch):
    fast = wall.mesh_thickness(ribbed())
    real = wall.require

    def no_rtree(module, purpose):
        if module == "rtree":
            raise ImportError("rtree hidden for the test")
        return real(module, purpose)
    monkeypatch.setattr(wall, "require", no_rtree)
    slow = wall.mesh_thickness(ribbed())
    assert slow["engine"] == "numpy" and slow["thickness"] == pytest.approx(fast["thickness"], abs=1e-6)


def test_mesh_inputs_subsampling_and_an_open_mesh(tmp_path):
    stl = tmp_path / "plate.stl"
    cq.exporters.export(plate(), str(stl))
    assert wall.check_wall("plate", 2.4, mesh=stl).status == "pass"
    big = wall.mesh_thickness(cq.Workplane().sphere(10).val(), max_rays=50)
    assert big["rays"] == 50 and big["triangles"] > 50
    assert big["areas"].sum() == pytest.approx(4 * 3.14159265 * 100, rel=0.02)
    m = wall._as_mesh(plate())
    m.update_faces(list(range(len(m.faces) - 1)))           # drop a triangle: no longer closed
    c = wall.check_wall("open", 2.4, mesh=m)
    assert c.status == "fail" and "open" in c.message
    with pytest.raises(ValueError):
        wall.check_wall("nothing", 2.4)


def test_wall_gate_writes_one_verdict_with_per_part_thresholds(tmp_path):
    out = tmp_path / "gates" / "wall.json"
    v = wall.wall_gate({"plate": {"wall_mm": 2.4, "mesh": plate(), "shape": plate()},
                        "ribbed": {"wall_mm": 0.8, "shape": ribbed()},
                        "thin": {"wall_mm": 3.0, "shape": plate()}}, out=out)
    assert v["pass"] is False and v["counts"] == {"pass": 2, "warn": 0, "fail": 1}
    assert [f["id"] for f in v["findings"]] == ["wall:thin"]
    assert v["limits"]["parts"]["ribbed"] == {"wall_mm": 0.8} and v["physical_fit_verified"] is False
    assert any("not measured" in a for a in v["assumptions"])
    assert json.loads(out.read_text()) == v


# ----------------------------------------------------------------------------- review regressions (PR #27)

def funnel(t=2.4, angle=45.0, length=20.0, r0=10.0):
    """A conical wall of normal thickness ``t`` with square-cut ends (no knife edge)."""
    import math
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    p0 = (r0, 0.0)
    p1 = (r0 + length * c, length * s)
    n = (-s * t, c * t)
    pts = [p0, p1, (p1[0] + n[0], p1[1] + n[1]), (p0[0] + n[0], p0[1] + n[1])]
    return cq.Workplane("XZ").polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0)).val()


CURVED = {
    "filleted box": (lambda: cq.Workplane().box(30, 30, 20).edges().fillet(2).val(), 20.0),
    "ball": (lambda: cq.Solid.makeSphere(5, angleDegrees1=-90), 10.0),
    "conical wall": (funnel, 2.4),
    "shelled filleted box": (lambda: cq.Workplane().box(30, 30, 20).edges().fillet(4).shell(-2.4).val(), 2.4),
    "spherical shell": (lambda: cq.Solid.makeSphere(10, angleDegrees1=-90).cut(cq.Solid.makeSphere(7.6, angleDegrees1=-90)), 2.4),
}


@pytest.mark.parametrize("name", list(CURVED))
def test_curved_parts_pass_at_their_true_thickness(name):
    make, true_t = CURVED[name]
    s = make()
    m = wall._as_mesh(s)
    assert m.is_watertight, "the repaired tessellation must be closed"
    c = wall.check_wall(name, true_t, mesh=s, shape=s)
    assert c.status == "pass", c.message
    assert c.evidence["brep-ray"]["min_mm"] == pytest.approx(true_t, abs=1e-6)
    over = wall.check_wall(name, true_t + 0.1, mesh=s, shape=s)
    assert over.status == "fail" and over.evidence["witnesses"][0]["thickness_mm"] == pytest.approx(true_t, abs=1e-3)


@pytest.mark.parametrize("make", [lambda: cq.Workplane().box(30, 30, 20).edges().fillet(2).val(),
                                  lambda: cq.Solid.makeSphere(5, angleDegrees1=-90),
                                  lambda: cq.Solid.makeCone(10, 0, 20)])
def test_tessellations_with_poles_apexes_and_fillet_corners_are_closed_after_repair(make, tmp_path):
    s = make()
    verts, tris = s.tessellate(0.05, 0.2)
    raw = trimesh.Trimesh([(v.x, v.y, v.z) for v in verts], tris, process=True)
    assert not raw.is_watertight                                     # what the review found
    assert wall._as_mesh(s).is_watertight
    stl = tmp_path / "part.stl"
    cq.exporters.export(s, str(stl))
    assert wall._as_mesh(stl).is_watertight
    assert "open" not in wall.check_wall("p", 0.5, mesh=s).message


def test_a_cone_reads_thin_only_at_its_sharp_apex_and_rim():
    s = cq.Solid.makeCone(10, 0, 20)
    c = wall.check_wall("cone", 2.0, mesh=s, shape=s)
    assert c.status == "fail"
    for w in c.evidence["witnesses"]:                                # the apex, or the 63 deg base rim
        x, y, z = w["point"]
        assert z > 14 or (z < 1 and (x * x + y * y) ** 0.5 > 9), w


def test_mesh_chord_error_is_dismissed_by_the_brep_and_counted():
    shell = CURVED["spherical shell"][0]()
    mesh_only = wall.check_wall("shell", 2.4, mesh=shell)
    assert mesh_only.status == "fail"                                # a mesh alone reads it ~0.03 mm thin
    both = wall.check_wall("shell", 2.4, mesh=shell, shape=shell)
    assert both.status == "pass" and both.evidence["mesh-ray"]["dismissed_as_chord_error"] > 0
    assert wall.check_wall("shell", 2.4, mesh=shell, tol_mm=0.1).status == "pass"


def test_an_open_mesh_with_a_brep_is_a_warning_not_a_failure():
    p = plate()
    m = wall._as_mesh(p)
    m.update_faces(list(range(len(m.faces) - 1)))
    c = wall.check_wall("open", 2.4, mesh=m, shape=p)
    assert c.status == "warn" and "B-rep rays are the evidence" in c.message


def test_brep_sampling_scales_with_face_size_and_finds_an_eccentric_bore():
    tube = cq.Workplane().circle(10).extrude(20).cut(cq.Workplane().center(4.2, 0).circle(5).extrude(20)).val()
    c = wall.check_wall("tube", 1.0, shape=tube)
    assert c.status == "fail"
    assert c.evidence["brep-ray"]["min_mm"] < 0.9                      # true minimum 0.8 at +X
    assert c.evidence["witnesses"][0]["point"][0] > 8
    coarse = wall.brep_thickness(tube, grid=3, max_grid=3)
    assert coarse["thickness"].min() > c.evidence["brep-ray"]["min_mm"]
