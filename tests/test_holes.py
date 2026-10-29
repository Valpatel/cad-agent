import json

import pytest

cq = pytest.importorskip("cadquery")

from cadagent import holes
from cadagent.cli import main
from cadagent.project import CadConfigError


def plate_with_counterbore(rib_after_holes: bool):
    """A 40 x 40 x 10 plate, a D3.4 clearance hole with a D6.4 x 4 counterbore, and a 2 mm rib on top running to the
    hole's centre (like a stiffening rib that ends on a screw)."""
    plate = cq.Workplane("XY").box(40, 40, 10, centered=(True, True, False))
    rib = cq.Workplane("XY").box(22, 2, 14, centered=False).translate((-22, -1, 0))
    holes_ = (cq.Workplane("XY").circle(1.7).extrude(20).translate((0, 0, -5))
              .union(cq.Workplane("XY").circle(3.2).extrude(10).translate((0, 0, 6))))
    if rib_after_holes:                      # the bug: the rib refills part of the counterbore
        return plate.cut(holes_).union(rib).val()
    return plate.union(rib).cut(holes_).val()


def test_rib_added_after_the_holes_is_found():
    r = holes.check_shape(plate_with_counterbore(rib_after_holes=True))
    assert not r["pass"]
    f = r["findings"][0]
    assert f["diameter_mm"] == pytest.approx(6.4) and f["intrusion_mm3"] > 5
    assert f["intrusion_centre_mm"][0] < 0                 # the rib comes in from -x


def test_holes_cut_last_pass():
    r = holes.check_shape(plate_with_counterbore(rib_after_holes=False))
    assert r["pass"] and r["holes"] == 2 and not r["findings"]


def test_fillets_slot_ends_and_bosses_are_not_holes():
    box = cq.Workplane("XY").box(40, 40, 20, centered=(True, True, False))
    pocket = cq.Workplane("XY").rect(20, 20).extrude(15).translate((0, 0, 5)).edges("|Z").fillet(3)
    slot = cq.Workplane("YZ").slot2D(12, 4).extrude(50).translate((-25, 10, 12))
    boss = cq.Workplane("XY").circle(4).extrude(10).translate((0, 0, 20))
    shape = box.cut(pocket).cut(slot).union(boss).union(cq.Workplane("XY").box(2, 30, 3).translate((0, 0, 8))).val()
    r = holes.check_shape(shape)
    assert r["pass"] and r["holes"] == 0, r


def test_coaxial_holes_in_opposite_walls_stay_separate():
    shell = cq.Workplane("XY").box(100, 30, 30).faces(">Z").shell(-3)        # open box, walls 3 mm
    bored = shell.cut(cq.Workplane("YZ").circle(2).extrude(120).translate((-60, 0, 0)))
    shape = bored.union(cq.Workplane("XY").box(4, 30, 20).translate((0, 0, 0))).val()   # a web across the middle
    r = holes.check_shape(shape)
    assert r["pass"] and r["holes"] >= 2, r


def test_d_flat_is_reported_with_a_hint_and_can_be_excepted():
    d_hole = cq.Workplane("XY").circle(3.3).extrude(10).cut(cq.Workplane("XY").box(10, 10, 10, centered=(False, True, False)).translate((2.8, 0, 0)))
    shape = cq.Workplane("XY").box(20, 20, 4, centered=(True, True, False)).cut(d_hole.translate((0, 0, -3))).val()
    r = holes.check_shape(shape)
    assert not r["pass"] and "D-flat" in r["findings"][0]["hint"]
    r = holes.check_shape(shape, exceptions=[{"at": [0, 0, 2], "diameter_mm": 6.6, "reason": "anti-rotation flat"}])
    assert r["pass"] and r["excepted"][0]["reason"] == "anti-rotation flat"


def project(tmp_path, shape, extra=""):
    root = tmp_path / "proj"
    (root / "exports").mkdir(parents=True)
    cq.exporters.export(cq.Workplane().add(shape), str(root / "exports/plate.step"))
    (root / "exports/geometry-checks.json").write_text(json.dumps({"plate": {"cad_valid": True}}))
    (root / "cad-agent.yaml").write_text("cad:\n  name: p\n  title: P\n" + extra)
    return root


def test_cli_and_report_rows(tmp_path):
    from cadagent.project import load_project
    from cadagent.report import holes_feature

    root = project(tmp_path, plate_with_counterbore(True))
    assert main(["holes", "--project", str(root)]) == 1
    data = json.loads((root / "exports/hole-checks.json").read_text())
    assert not data["pass"] and data["parts"]["plate"]["sha256"]
    rows = holes_feature(load_project(root))["checks"]
    assert rows[0]["status"] == "fail" and "material inside" in rows[0]["message"]
    cq.exporters.export(cq.Workplane().add(plate_with_counterbore(False)), str(root / "exports/plate.step"))
    assert "stale" in holes_feature(load_project(root))["checks"][0]["message"]      # STEP changed since the check
    assert main(["holes", "--project", str(root)]) == 0
    assert holes_feature(load_project(root))["checks"][0]["status"] == "pass"


def test_not_run_fails_and_skip_needs_a_reason(tmp_path):
    from cadagent.project import load_project
    from cadagent.report import holes_feature

    root = project(tmp_path, plate_with_counterbore(False))
    assert holes_feature(load_project(root))["checks"][0]["status"] == "fail"
    root2 = project(tmp_path / "b", plate_with_counterbore(True), "  holes:\n    skip: {plate: ''}\n")
    with pytest.raises(CadConfigError):
        holes.config(load_project(root2))


def test_stepped_bore_with_a_ledge_passes_and_a_blocking_rib_fails():
    block = cq.Workplane("XY").box(20, 20, 30, centered=(True, True, False))
    stepped = (cq.Workplane("XY").circle(3.3).extrude(26).translate((0, 0, 4))          # bore from the top to z 4
               .union(cq.Workplane("XY").circle(1.7).extrude(40).translate((0, 0, -5)))  # screw hole through the ledge
               .union(cq.Workplane("XY").circle(3.3).extrude(3).translate((0, 0, -1))))  # counterbore under the ledge
    assert holes.check_shape(block.cut(stepped).val())["pass"]
    plate = cq.Workplane("XY").box(30, 30, 10, centered=(True, True, False)).cut(
        cq.Workplane("XY").circle(1.7).extrude(20).translate((0, 0, -5)))
    rib = cq.Workplane("XY").box(30, 8, 3).translate((0, 0, 5))                            # wider than the hole
    r = holes.check_shape(plate.union(rib).val())
    assert not r["pass"] and r["findings"][0]["diameter_mm"] == pytest.approx(3.4)
