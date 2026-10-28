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
    assert c.status == "fail" and "watertight" in c.message
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
