"""cadagent.manufacturing.fit_coupons: the sizes follow the process profile, the sheet matches the coupon, and the
coupon is one watertight solid with every hole at its size."""
from __future__ import annotations

import csv
import io
import math
from pathlib import Path

import pytest
import yaml

from cadagent.manufacturing import fit_coupons as fc

ROOT = Path(__file__).resolve().parents[2]


def _rule(rule_id):
    data = yaml.safe_load((ROOT / "docs" / "research" / "process-profiles.yaml").read_text())
    return next(r for r in data["rules"] if r["id"] == rule_id)


def test_numbers_stay_in_step_with_the_process_profile():
    assert fc.UNDERSIZE_MM == _rule("fdm-hole-undersize-cnckitchen")["value"]
    slide = _rule("fdm-clearance-sliding-xometry-eu")
    assert slide["min"] <= fc.ALLOWANCE_MM["slide"] <= slide["max"]
    assert fc.ALLOWANCE_MM["free"] == _rule("fdm-clearance-moving-prusa")["min"]
    insert = _rule("fdm-insert-hole-cad-offset-cnckitchen")
    assert insert["min"] <= fc.ALLOWANCE_MM["insert"] + fc.UNDERSIZE_MM <= insert["max"]
    for kind, source in fc.ALLOWANCE_SOURCE.items():
        for rule_id in [w.strip("();,") for w in source.split() if w.strip("();,").startswith("fdm-")]:
            _rule(rule_id)                                                  # every cited row exists


def test_insert_sweep_centres_on_the_hole_inserts_draws():
    """The coupon's middle hole is the hole ``inserts.hole_design`` draws the part with (#290): CNC Kitchen's 4.2 mm
    in CAD for its 4.0 mm M3 hole, 0.2 mm over the maker's, not the maker's hole plus the 0.25 mm undersize."""
    from cadagent.mechanical import inserts
    for key, ins in inserts.INSERTS.items():
        fit = fc.Fit(key, ins.hole_mm, "insert")
        drawn = inserts.hole_design(ins)["diameter_mm"]
        assert fit.centre_mm == pytest.approx(drawn), key
        assert fit.diameters()[fit.count // 2] == pytest.approx(drawn), key
    m3 = fc.Fit("M3 insert", inserts.INSERTS["mcmaster-94459A140"].hole_mm, "insert")
    assert m3.centre_mm == pytest.approx(4.2)
    # read back, the middle hole means the printer printed as CNC Kitchen's did: the profile's undersize
    assert fc.from_coupon(m3, 4.2)["printer_offset_mm"] == pytest.approx(fc.UNDERSIZE_MM)


def test_sweep_is_centred_on_nominal_plus_allowance_plus_undersize():
    fit = fc.Fit("pivot pin", 5.0, "slide")
    assert fit.centre_mm == pytest.approx(5.5)
    assert fit.diameters() == [5.3, 5.35, 5.4, 5.45, 5.5, 5.55, 5.6, 5.65, 5.7]
    assert fc.Fit("seat", 8, "press", count=3, step_mm=0.1).diameters() == [8.15, 8.25, 8.35]
    assert fc.Fit("own", 3, allowance_mm=-0.1, undersize_mm=0.3, count=1).diameters() == [3.2]


@pytest.mark.parametrize("bad", [dict(kind="snug"), dict(axis="sideways"), dict(count=4), dict(nominal_mm=0),
                                 dict(nominal_mm=0.1, allowance_mm=-1.0), dict(depth_mm=-1)])
def test_fit_refuses(bad):
    with pytest.raises(ValueError):
        fc.Fit(**({"name": "f", "nominal_mm": 5.0} | bad))


def test_layout_spaces_holes_with_a_wall_between_them():
    lay = fc.layout(fc.Fit("bearing", 22.0, "press", depth_mm=7, count=5))
    ds, cs = lay["diameters_mm"], lay["centres_mm"]
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            gap = math.dist(cs[i], cs[j]) - (ds[i] + ds[j]) / 2
            assert gap >= lay["wall_mm"] - 1e-9 - (max(ds) - min(ds))
    w, h = lay["size_mm"]
    for (x, y), d in zip(cs, ds):
        assert x - d / 2 >= lay["wall_mm"] / 2 - 1e-9 and y - d / 2 >= lay["wall_mm"] / 2 - 1e-9
        assert x + d / 2 <= w and y + d / 2 <= h
    standing = fc.layout(fc.Fit("bearing", 22.0, "press", axis="horizontal", count=5))
    assert len({y for _, y in standing["centres_mm"]}) == 1                 # one row, so it stands low


def test_a_press_fit_coupon_takes_the_parts_own_wall():
    default = fc.layout(fc.Fit("bushing seat", 8.0, "press"))
    assert default["wall_mm"] == pytest.approx(0.25 * 8.45)                # max(2, a quarter of the largest hole)
    own = fc.layout(fc.Fit("bushing seat", 8.0, "press", wall_mm=4.0))
    assert own["wall_mm"] == 4.0 and own["size_mm"][0] > default["size_mm"][0]
    xs = sorted({x for x, _ in own["centres_mm"]})
    assert xs[1] - xs[0] == pytest.approx(max(own["diameters_mm"]) + 4.0)  # the wall between the largest holes
    with pytest.raises(ValueError):
        fc.Fit("bushing seat", 8.0, "press", wall_mm=0.5)


def test_sheet_has_a_row_per_hole_with_blanks_to_fill():
    fits = [fc.Fit("pivot pin", 5.0, "slide"), fc.Fit("seat", 8.0, "press", count=3)]
    table = list(csv.DictReader(io.StringIO(fc.sheet(fits))))
    assert len(table) == 12 and table[0]["coupon"] == "pivot-pin" and table[4]["offset_mm"] == "+0.000"
    assert all(r["measured_mm"] == "" and r["fit"] == "" for r in table)
    assert [r["cad_mm"] for r in table[9:]] == ["8.200", "8.250", "8.300"]


def test_reading_a_coupon_back():
    fit = fc.Fit("pivot pin", 5.0, "slide")
    got = fc.from_coupon(fit, 5.45, measured_mm=5.2)
    assert got == {"fit": "pivot pin", "cad_mm": 5.45, "printer_offset_mm": 0.2, "printed_under_cad_mm": 0.25}
    with pytest.raises(ValueError):
        fc.from_coupon(fit, 5.42)


def test_coupon_solid_has_every_hole_and_writes_print_files(tmp_path):
    cq = pytest.importorskip("cadquery")
    pytest.importorskip("trimesh")
    fit = fc.Fit("bushing seat", 8.0, "press", depth_mm=6, count=5)
    solid = fc.coupon(fit)
    assert solid.isValid() and len(solid.Solids()) == 1
    lay = fc.layout(fit)
    w, h = lay["size_mm"]
    hole_area = sum(math.pi * d * d / 4 for d in lay["diameters_mm"]) + fc.NOTCH_MM ** 2 / 2
    assert solid.Volume() == pytest.approx((w * h - hole_area) * 6, rel=1e-6)
    circles = {round(e.radius() * 2, 4) for e in solid.Edges() if e.geomType() == "CIRCLE"}
    assert circles == set(lay["diameters_mm"])
    out = fc.write([fit, fc.Fit("608 bearing", 22.0, "press", depth_mm=7, axis="horizontal", count=3)], tmp_path)
    for slug, files in out["coupons"].items():
        assert Path(files["step"]).exists() and files["stl_report"]["watertight"]
    standing = out["coupons"]["608-bearing"]["stl_report"]["print_bounds_mm"]
    assert standing[1] == pytest.approx(7.0, abs=1e-3)                      # printed on edge: thickness in Y
    assert (tmp_path / "fit-coupons.csv").read_text() == fc.sheet([fit, fc.Fit("608 bearing", 22.0, "press",
                                                                                depth_mm=7, axis="horizontal",
                                                                                count=3)])
    with pytest.raises(ValueError):
        fc.write([fit, fit], tmp_path)
    assert cq  # imported for the skip


def test_specimen_stamp_rejects_nonallocated_formats_before_cad():
    fit = fc.Fit("fixture", 5.0)
    for value in ("short", "abcdef0123", "../../part", "ABCDEF01234", None):
        with pytest.raises(ValueError, match="allocated ten"):
            fc.labelled_coupon(fit, value)


def test_labelled_coupon_real_geometry_preserves_fit_envelope_and_actual_engraving(tmp_path):
    cq = pytest.importorskip("cadquery")
    from cadagent.geometry import export_print_stl, export_step
    import cadquery.importers
    fit = fc.Fit("pin", 5.0, "slide", count=3)
    original = fc.coupon(fit)
    labelled, proof = fc.labelled_coupon(fit, "ABCDEF0123")
    w, h = fc.layout(fit)["size_mm"]
    envelope = cq.Workplane("XY").box(w, h, fit.depth, centered=False).val()
    inside = labelled.intersect(envelope)
    assert original.cut(inside).Volume() < 1e-7
    assert inside.cut(original).Volume() < 1e-7
    assert labelled.isValid() and len(labelled.Solids()) == 1
    # Independent volume accounting rejects a no-op engraver rather than trusting proof flags.
    x0, x1, y0, y1, z0, z1 = proof["tab_bounds_mm"]
    tab = (cq.Workplane("XY").box(x1-x0, y1-y0, z1-z0, centered=False)
           .translate((x0, y0, z0)).val())
    unmarked = original.fuse(tab)
    removed = unmarked.cut(labelled)
    assert removed.Volume() > 1.0
    assert removed.Volume() == pytest.approx(proof["removed_mm3"], abs=1e-7)
    assert removed.BoundingBox().ymin >= h + 0.5
    assert "ABCDEF0123" in proof["svg"] and proof["physical_legibility_verified"] is False
    step = export_step(labelled, tmp_path / "ABCDEF0123.step")
    back = cadquery.importers.importStep(str(step)).val()
    assert back.Volume() == pytest.approx(labelled.Volume(), rel=1e-7)
    mesh = export_print_stl(labelled, tmp_path / "ABCDEF0123.stl")
    assert mesh["watertight"]
