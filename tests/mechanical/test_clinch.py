"""cadagent.mechanical.clinch: PEM's cited parts, and the placement check against the sm-clinch-* rules (#283)."""
import math

import pytest

from cadagent.mechanical import clinch as cl

IN, LBF = 25.4, 4.4482216152605


def _check(result, name):
    return next(c for c in result["checks"] if c["check"] == name)


def test_the_parts_match_pems_bulletins():
    m3 = cl.PARTS["S-M3-1"]                                       # Bulletin CL: CL-4, CL-13
    assert (m3.hole_mm, m3.min_sheet_mm, m3.edge_mm, m3.pushout_n, m3.torque_out_nm) == (4.22, 1.0, 4.8, (400, 550),
                                                                                       (1.13, 1.7))
    assert cl.PARTS["CLS-M3-1"].material == "300 stainless" and cl.PARTS["S-M3-1"].material == "hardened steel"
    assert "SS-M5-1" in cl.PARTS and "S-M5-1" not in cl.PARTS    # M5 and #10 are the SS and CLSS types
    quarter = cl.PARTS["S-0420-1"]                                # inch rows converted: 0.344 in hole, 0.34 in E
    assert math.isclose(quarter.hole_mm, 0.344 * IN, abs_tol=1e-4) and math.isclose(quarter.edge_mm, 0.34 * IN, abs_tol=1e-4)
    assert math.isclose(quarter.pushout_n[0], 360 * LBF, abs_tol=0.05)
    assert cl.PARTS["FH-M4"].pull_through_n == (4448, 5650)       # Bulletin FH, FH-29
    assert cl.PARTS["SO-M3"].screw_torque_nm == 0.55               # Bulletin SO, SO-12
    assert len(cl.PARTS) == 28
    for p in cl.PARTS.values():
        assert p.source in cl.SRC and p.material in cl.CLASSES


def test_sendcutsends_worked_example_is_pems_rule():
    """SendCutSend's PEM guide: a 1/4-20 nut in 0.063 in 5052 sits 0.340 in from the edge and 0.512 in from the next
    one, which is PEM's E + hole/2 = 0.34 + 0.344 / 2 (HB-12)."""
    r = cl.check_placement("S-0420-1", "5052-h32", 0.063 * IN, edge_mm=0.340 * IN,
                           neighbours=[("S-0420-1", 0.512 * IN)])
    assert r["verdict"] == "pass"
    assert _check(r, "edge")["limit"] == f"at least {0.34 * IN:.3f} mm"
    assert _check(r, "spacing to S-0420-1")["limit"] == f"at least {0.512 * IN:.3f} mm"
    closer = cl.check_placement("S-0420-1", "5052-h32", 0.063 * IN, neighbours=[("S-0420-1", 0.50 * IN)])
    assert closer["verdict"] == "fail"


def test_spacing_takes_the_larger_of_the_two_ways_round():
    # an M3 nut beside an M6 nut: 4.8 + 8.75/2 = 9.175 against 8.6 + 4.22/2 = 10.71
    r = cl.check_placement("S-M3-1", "5052-h32", 1.6, neighbours=[("S-M6-1", 10.0)])
    c = _check(r, "spacing to S-M6-1")
    assert (c["verdict"], c["limit"]) == ("fail", "at least 10.710 mm")


def test_the_bend_distance_is_ba_over_two_plus_e():
    """1.6 mm 5052 on SendCutSend's tooling: R 0.889 mm, K 0.42, so BA = pi (0.889 + 0.42 x 1.6) / 2 = 2.4520 mm, and
    an M3 nut needs 2.4520 / 2 + 4.8 = 6.026 mm from the bend centre line."""
    ba = math.pi * (0.889 + 0.42 * 1.6) / 2
    r = cl.check_placement("S-M3-1", "5052-h32", 1.6, to_bend_mm=6.1)
    assert _check(r, "bend")["verdict"] == "pass"
    assert _check(r, "bend")["limit"].startswith(f"at least {ba / 2 + 4.8:.3f} mm")
    assert cl.check_placement("S-M3-1", "5052-h32", 1.6, to_bend_mm=5.9)["verdict"] == "fail"
    given = cl.check_placement("S-M3-1", "6061-t6", 1.6, to_bend_mm=6.0, bend_allowance_mm=3.0)
    assert _check(given, "bend")["verdict"] == "fail" and "6.300" in _check(given, "bend")["limit"]
    with pytest.raises(ValueError, match="bend_allowance_mm"):
        cl.check_placement("S-M3-1", "6061-t6", 1.6, to_bend_mm=6.0)


def test_hardness_follows_the_part_material():
    assert _check(cl.check_placement("S-M3-1", "6061-t6", 1.6), "hardness")["verdict"] == "pass"     # 55 <= 80
    cls_crs = _check(cl.check_placement("CLS-M3-1", "cold-rolled-steel", 1.5), "hardness")
    assert cls_crs["verdict"] == "warn" and "certificate" in cls_crs["detail"]                       # 40-75 vs 70
    assert _check(cl.check_placement("CLS-M3-1", "cold-rolled-steel", 1.5, sheet_hrb=60), "hardness")["verdict"] == "pass"
    assert _check(cl.check_placement("CLS-M3-1", "cold-rolled-steel", 1.5, sheet_hrb=72), "hardness")["verdict"] == "fail"
    for part in ("CLS-M3-1", "S-M3-1", "FH-M3", "SO-M3"):         # only hardened-stainless types go into stainless
        c = _check(cl.check_placement(part, "304-annealed", 1.5), "hardness")
        assert c["verdict"] == "fail" and "SP" in c["limit"]


def test_thickness_and_hole():
    assert cl.check_placement("S-M6-1", "5052-h32", 1.2)["verdict"] == "fail"                         # needs 1.4 mm
    ok = cl.check_placement("S-M3-1", "5052-h32", 1.6, hole_mm=4.25)
    assert _check(ok, "hole")["verdict"] == "pass" and _check(ok, "hole")["limit"] == "4.220-4.300 mm"
    assert _check(cl.check_placement("S-M3-1", "5052-h32", 1.6, hole_mm=4.31), "hole")["verdict"] == "fail"
    assert _check(cl.check_placement("S-M3-1", "5052-h32", 1.6, hole_mm=4.20), "hole")["verdict"] == "fail"


def test_loads_use_the_matching_test_sheet():
    al = cl.check_placement("S-M3-1", "5052-h32", 1.6, pushout_n=300, factor=1.5)   # 300 x 1.5 = 450 > 400
    assert _check(al, "push-out")["verdict"] == "fail"
    steel = cl.check_placement("S-M3-1", "cold-rolled-steel", 1.6, pushout_n=300, factor=1.5)        # 450 <= 550
    assert _check(steel, "push-out")["verdict"] == "pass"
    so = cl.check_placement("SO-M3", "5052-h32", 1.6, torque_nm=0.6)                # the screw torque limit, 0.55
    assert _check(so, "torque")["verdict"] == "fail"
    nut = cl.check_placement("S-M3-1", "5052-h32", 1.6, pull_n=100)                 # a nut has no pull-through rating
    assert _check(nut, "pull-through")["verdict"] == "fail" and "no pull-through" in _check(nut, "pull-through")["detail"]


def test_notes_and_limits():
    thick = cl.check_placement("S-M6-1", "cold-rolled-steel", 2.5)
    assert any("punch side" in n for n in thick["notes"])
    assert not any("punch side" in n for n in cl.check_placement("S-M3-1", "5052-h32", 1.6)["notes"])
    assert any("not allowables" in x for x in thick["limits"])


def test_parts_for_lists_what_clinches_cheapest_first():
    keys = [p["key"] for p in cl.parts_for("M3", "5052-h32", 1.6)]
    assert keys[:2] == ["S-M3-1", "CLS-M3-1"] and "FH-M3" in keys
    assert "CLS-M3-1" not in [p["key"] for p in cl.parts_for("M3", "cold-rolled-steel", 1.6)]       # 75 > 70
    assert cl.parts_for("M3", "304-annealed", 1.6) == []
    assert [p["key"] for p in cl.parts_for("M6", "5052-h32", 1.2)] == []                             # too thin
    assert [p["key"] for p in cl.parts_for("M4", "5052-h32", 1.6, kind="standoff")] == ["BSO-M4", "SO-M4"]


def test_bad_input_is_named():
    with pytest.raises(ValueError, match="unknown part"):
        cl.check_placement("S-M7-1", "5052-h32", 1.6)
    with pytest.raises(ValueError, match="unknown sheet"):
        cl.check_placement("S-M3-1", "brass", 1.6)
    with pytest.raises(ValueError, match="thickness_mm"):
        cl.check_placement("S-M3-1", "5052-h32", -1)
    with pytest.raises(ValueError, match="kind"):
        cl.parts_for("M3", "5052-h32", 1.6, kind="rivet")
