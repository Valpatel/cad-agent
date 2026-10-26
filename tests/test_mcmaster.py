"""cadagent.mcmaster without the network: page parsing, and normalise() on synthetic CadQuery parts placed in odd
frames (each kind's convention)."""

from __future__ import annotations

import json

import pytest

from cadagent import mcmaster as mc

cq = pytest.importorskip("cadquery")


def _step(tmp_path, name, shape):
    p = tmp_path / f"{name}.step"
    cq.exporters.export(shape if isinstance(shape, cq.Workplane) else cq.Workplane(obj=shape), str(p), exportType="STEP")
    return p


def _odd_frame(wp):
    """Lay a part built on +Z along X instead, rotated about its axis and moved off the origin."""
    return wp.rotate((0, 0, 0), (0, 0, 1), 17).rotate((0, 0, 0), (0, 1, 0), 90).translate((40.0, -12.0, 7.5))


# ----------------------------------------------------------------------------------- page data

def test_price_and_pack():
    assert mc.parse_price("$10.91 each") == (10.91, 1)
    assert mc.parse_price(" $13.96 per pack of 100 ") == (13.96, 100)
    assert mc.parse_price("$1,233.64 each") == (1233.64, 1)
    assert mc.parse_price("") == (None, None)


def test_spec_rows_group_and_parse():
    rows = [("For Shaft Diameter", "12 mm", False), ("Width Tolerance", "-0.12 mm to 0 mm", False),
            ("Dynamic Radial Load Capacity", "1,100 lb.", False), ("Temperature Range", "", False),
            ("Minimum", "-20° F", True), ("Max.", "230° F", True), ("Material", "Steel", False),
            ("Thread Size", "M5 × 0.8 mm", False), ("Length", "3/4\"", False), ("Weight", "0.05 lb.", False)]
    raw, parsed = mc.parse_specs(rows)
    assert raw["Temperature Range Minimum"] == "-20° F" and "Temperature Range" not in raw
    assert parsed["For Shaft Diameter"] == {"value": 12.0, "unit": "mm"}
    assert parsed["Width Tolerance"] == {"min": -0.12, "max": 0.0, "unit": "mm"}
    assert parsed["Dynamic Radial Load Capacity"]["unit"] == "N"
    assert parsed["Dynamic Radial Load Capacity"]["value"] == pytest.approx(4893.04, abs=0.01)
    assert parsed["Temperature Range Max."]["value"] == pytest.approx(110.0)
    assert parsed["Thread Size"]["thread"] == "M5x0.8"
    assert parsed["Length"]["value"] == pytest.approx(19.05)
    assert parsed["Weight"] == {"value": pytest.approx(22.68, abs=0.01), "unit": "g"}
    assert "Material" not in parsed


def test_catalog_entry_prefers_listed_weight_and_keeps_extra_fields(tmp_path):
    page = {"pn": "1234A5", "description": "Thing", "url": mc.product_url("1234a5"), "price_usd": 2.5, "pack_qty": 10,
            "listed_weight_g": 3.2, "specs": {"raw": {"Material": "Brass", "Length": "8 mm"},
                                              "parsed": {"Length": {"value": 8.0, "unit": "mm"}}}}
    info = {"mass_g_est": 9.9, "density_g_cm3": 8.5, "frame": mc.FRAMES["pin"], "kind": "pin", "bbox_mm": {}}
    e = mc.catalog_entry(page, info, cad="x/1234A5.norm.step")
    assert e["mass_g"] == 3.2 and e["mass_basis"] == "McMaster listed weight"
    assert e["dims_mm"]["length"] == 8.0 and e["material"] == "Brass"
    cat = tmp_path / "hardware.json"
    cat.write_text(json.dumps({"source": "s", "items": {"pin": {"used_for": "keep me", "qty": 4}}}))
    mc.update_catalog(cat, "pin", e)
    item = json.loads(cat.read_text())["items"]["pin"]
    assert item["used_for"] == "keep me" and item["qty"] == 4 and item["mcmaster"] == "1234A5"
    page.pop("listed_weight_g")
    assert "estimate" in mc.catalog_entry(page, info)["mass_basis"]


def test_write_source(tmp_path):
    p = mc.write_source(tmp_path / "91290A242", "91290A242", "M5 x 20 SHCS", when="2026-01-02")
    t = p.read_text()
    assert "https://www.mcmaster.com/91290A242/" in t and "2026-01-02" in t and "not redistributed" in t


# ----------------------------------------------------------------------------------- normalise

def test_bearing_ring_lands_on_z0_centred(tmp_path):
    ring = cq.Workplane("XY").circle(14).circle(6).extrude(8)
    p = _step(tmp_path, "ring", _odd_frame(ring))
    out, info = mc.normalise(p, "bearing", density=7.85)
    assert out.name == "ring.norm.step" and out.exists()
    b = info["bbox_mm"]
    assert b["min"][2] == pytest.approx(0, abs=1e-3) and b["max"][2] == pytest.approx(8, abs=1e-3)
    assert b["min"][0] == pytest.approx(-14, abs=1e-3) and b["max"][1] == pytest.approx(14, abs=1e-3)
    assert abs(abs(info["axis_found"][0]) - 1) < 1e-6           # it lay along X
    vol = 3.14159265 * (14 ** 2 - 6 ** 2) * 8
    assert info["volume_mm3"] == pytest.approx(vol, rel=1e-3)
    assert info["mass_g_est"] == pytest.approx(vol * 7.85 / 1000, rel=1e-3)


def _screw(head_d=8.5, head_h=5.0, d=5.0, length=20.0):
    return (cq.Workplane("XY").circle(head_d / 2).extrude(head_h)
            .faces(">Z").workplane().polygon(6, 4.0).cutBlind(-2.5)
            .union(cq.Workplane("XY").circle(d / 2).extrude(-length)))


@pytest.mark.parametrize("flip", [False, True])
def test_screw_head_up_underside_at_z0(tmp_path, flip):
    s = _screw()
    if flip:                                                     # head first towards -X
        s = s.rotate((0, 0, 0), (0, 1, 0), 180)
    p = _step(tmp_path, "screw", _odd_frame(s))
    _, info = mc.normalise(p, "screw")
    b = info["bbox_mm"]
    assert b["max"][2] == pytest.approx(5.0, abs=1e-3)           # head on +z, 5 tall
    assert b["min"][2] == pytest.approx(-20.0, abs=1e-3)         # shank 20 long towards -z
    assert b["max"][0] == pytest.approx(4.25, abs=1e-3)
    assert info["head_d"] == pytest.approx(8.5, abs=1e-3)


def test_shoulder_screw(tmp_path):
    s = (cq.Workplane("XY").circle(9).extrude(9)
         .union(cq.Workplane("XY").circle(6).extrude(-30))
         .union(cq.Workplane("XY").workplane(offset=-30).circle(5).extrude(-16)))
    p = _step(tmp_path, "shoulder", _odd_frame(s))
    _, info = mc.normalise(p, "shoulder_screw")
    b = info["bbox_mm"]
    assert b["max"][2] == pytest.approx(9, abs=1e-3) and b["min"][2] == pytest.approx(-46, abs=1e-3)


def test_rod_end_ball_at_origin_bore_y_shank_minus_z(tmp_path):
    # built with the ball at (0,0,0), bore along Z and the shank along +X (housing and shank 36 long)
    housing = cq.Workplane("XY").circle(11).extrude(9).translate((0, 0, -4.5))
    ball = cq.Workplane("XY").sphere(7).intersect(cq.Workplane("XY").box(20, 20, 12)).cut(
        cq.Workplane("XY").circle(3).extrude(20).translate((0, 0, -10)))
    shank = cq.Workplane("YZ").circle(5.0).extrude(36 - 9).translate((9, 0, 0))
    body = housing.cut(cq.Workplane("XY").sphere(7)).union(shank).union(ball)
    moved = body.rotate((0, 0, 0), (1, 1, 0), 33).translate((5, 6, 7))
    p = _step(tmp_path, "rodend", moved)
    _, info = mc.normalise(p, "rod_end")
    b = info["bbox_mm"]
    assert info["ball_d"] == pytest.approx(14, abs=1e-3)
    assert b["min"][2] == pytest.approx(-36, abs=1e-2)           # the shank's end, 36 from the ball centre
    assert b["max"][2] == pytest.approx(11, abs=1e-2)            # the housing's far side
    assert b["max"][1] == pytest.approx(6, abs=1e-2)             # ball width 12 along the bore (Y)
    assert b["max"][0] == pytest.approx(11, abs=1e-2)


def test_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        mc.normalise(tmp_path / "x.step", "sprocket")


def test_fetch_without_playwright_says_how_to_install(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_pw(name, *a, **k):
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_pw)
    with pytest.raises(mc.MissingDependency, match="pip install playwright"):
        mc._playwright()


def test_update_catalog_list_layout(tmp_path):
    cat = tmp_path / "parts.json"
    cat.write_text(json.dumps([{"id": "a", "notes": "keep"}, {"id": "b"}]))
    mc.update_catalog(cat, "a", {"mcmaster": "1A1", "notes": None})
    mc.update_catalog(cat, "c", {"mcmaster": "3C3"})
    items = json.loads(cat.read_text())
    assert [i["id"] for i in items] == ["a", "b", "c"]
    assert items[0] == {"id": "a", "notes": "keep", "mcmaster": "1A1"}


def test_screw_with_a_stepped_head_underside(tmp_path):
    # some imported screw models: a slightly smaller bearing-face step (1.1 mm) under the full head diameter
    s = (cq.Workplane("XY").circle(4.25).extrude(3.9)
         .union(cq.Workplane("XY").workplane(offset=-1.1).circle(4.15).extrude(1.1))
         .union(cq.Workplane("XY").workplane(offset=-1.1).circle(2.5).extrude(-22)))
    p = _step(tmp_path, "stepped", _odd_frame(s))
    _, info = mc.normalise(p, "screw")
    b = info["bbox_mm"]
    assert b["max"][2] == pytest.approx(5.0, abs=1e-3) and b["min"][2] == pytest.approx(-22.0, abs=1e-3)


def test_material_of_falls_back_to_finished_material():
    assert mc.material_of({"Finished Material": "Zinc-Plated Steel", "Insert Material": "Nylon"}) == "Zinc-Plated Steel"
    assert mc.density_for(mc.material_of({"Material": "18-8 Stainless Steel"})) == 8.0
