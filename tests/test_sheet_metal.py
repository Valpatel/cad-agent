"""cadagent.manufacturing.sheet_metal: bend allowance and deduction by hand-worked vectors, K and the flange from the
shop's table first, then the generic rules, each with its source (#99)."""
from __future__ import annotations

import math

import pytest

from cadagent.manufacturing import sheet_metal as sm


def test_shop_stock_gives_its_radius_k_and_flange():
    # SendCutSend ALU-063: T 1.600, R 0.889, K 0.42, shortest flange 7.696, relief 2.997 mm (sendcutsend-specs)
    b = sm.bend("5052", 1.6)
    assert b["stock"] == "ALU-063"
    assert b["radius_mm"]["value"] == 0.889 and b["k"]["value"] == 0.42
    assert b["k"]["source"] == "sendcutsend-specs" and b["min_flange_mm"]["value"] == 7.696
    assert b["relief_depth_mm"]["value"] == 2.997
    # BA = pi (R + K T) A / 180 = pi (0.889 + 0.672) / 2 = 2.452013; OSSB = (R + T) tan 45 = 2.489; BD = 2.525987
    assert b["allowance_mm"] == pytest.approx(math.pi * 1.561 / 2, abs=1e-6)
    assert b["allowance_mm"] == pytest.approx(2.452013, abs=1e-6)
    assert b["setback_mm"] == pytest.approx(2.489, abs=1e-9)
    assert b["deduction_mm"] == pytest.approx(2.525987, abs=1e-6)
    assert b["formula"]["id"] == "sm-bend-allowance" and b["formula"]["source"] == "solidworks-k-factor"


@pytest.mark.parametrize("angle, ba, ossb", [
    # T 1, R 1, K 0.5: BA = pi * 1.5 * A / 180; OSSB = 2 tan(A / 2)
    (90.0, 2.356194, 2.0),
    (45.0, 1.178097, 0.828427),
    (120.0, 3.141593, 3.464102),
])
def test_bend_allowance_and_setback_by_hand(angle, ba, ossb):
    b = sm.bend("mild-steel", 1.0, angle, radius_mm=1.0, k=0.5)
    assert b["allowance_mm"] == pytest.approx(ba, abs=1e-6)
    assert b["setback_mm"] == pytest.approx(ossb, abs=1e-6)
    assert b["deduction_mm"] == pytest.approx(2 * ossb - ba, abs=1e-6)
    assert b["k"]["rule"] == "given" and b["radius_mm"]["rule"] == "given"


@pytest.mark.parametrize("material, r, t, rule, k", [
    # Protolabs Network's air-bending K table (hubs-sheet-metal)
    ("5052", 1.0, 2.0, "sm-k-air-soft-r-le-t-hubs", 0.33),
    ("5052", 4.0, 2.0, "sm-k-air-soft-r-t-3t-hubs", 0.40),
    ("mild-steel", 2.0, 2.0, "sm-k-air-medium-r-le-t-hubs", 0.38),
    ("mild-steel", 5.0, 2.0, "sm-k-air-medium-r-t-3t-hubs", 0.43),
    ("mild-steel", 7.0, 2.0, "sm-k-air-r-gt-3t-hubs", 0.50),
])
def test_without_a_shop_row_k_comes_from_the_generic_table(material, r, t, rule, k):
    b = sm.bend(material, t, radius_mm=r)
    assert b["stock"] is None and b["k"]["rule"] == rule and b["k"]["value"] == k
    assert b["k"]["source"] == "hubs-sheet-metal" and b["k"]["verified"]


def test_a_radius_other_than_the_shops_drops_its_k_and_flange():
    b = sm.bend("5052", 1.6, radius_mm=1.6)
    assert b["stock"] is None and b["k"]["rule"] == "sm-k-air-soft-r-le-t-hubs"
    # the strictest generic flange at T 1.6, R 1.6 is Century Tywood's 3.5 (T + R) = 11.2 mm; every one is listed
    f = b["min_flange_mm"]
    assert f["rule"] == "sm-flange-min-century" and f["value"] == pytest.approx(11.2)
    assert {x["rule"] for x in f["all"]} == {"sm-flange-min-protolabs", "sm-flange-min-davis",
                                             "sm-flange-min-century", "sm-flange-min-hubs"}
    # relief depth: SendCutSend T + R + 0.5 = 3.7 mm is the strictest generic
    assert b["relief_depth_mm"]["rule"] == "sm-relief-depth-min-sendcutsend"
    assert b["relief_depth_mm"]["value"] == pytest.approx(3.7)


def test_no_shop_and_no_radius_takes_the_generic_minimum_radius():
    b = sm.bend("mild-steel", 2.0, shop=False)
    assert b["radius_mm"]["value"] == pytest.approx(2.0)                    # T, every generic minimum-radius rule
    assert b["radius_mm"]["rule"] != "sm-bend-radius-min-davis-hard-al"     # 4-8 T is for 6061 and 2024


def test_flat_length_of_a_u_channel():
    # 20 + 30 + 20 outside, two 90 degree bends in SendCutSend's CRS-059 (1.499 mm, R 1.6, K 0.40)
    out = sm.flat_length([20, 30, 20], "mild-steel", 1.499)
    ba = math.pi * (1.6 + 0.40 * 1.499) / 2
    bd = 2 * (1.6 + 1.499) - ba
    assert out["flat_mm"] == pytest.approx(70 - 2 * bd, abs=1e-5)
    assert out["verdict"] == "pass"
    short = sm.flat_length([5, 30, 20], "mild-steel", 1.499)
    assert short["verdict"] == "fail" and short["short_legs"] == [0]          # under the shop's 7.849 mm flange


@pytest.mark.parametrize("args, kw", [((0.0,), {}), ((1.6, 180.0), {}), ((1.6, 90.0), {"k": 0.7}),
                                      ((1.6, 90.0), {"radius_mm": -1})])
def test_bend_refuses(args, kw):
    with pytest.raises(ValueError):
        sm.bend("5052", *args, **kw)


def test_flat_length_refuses_mismatched_angles():
    with pytest.raises(ValueError, match="angles"):
        sm.flat_length([10, 10, 10], "5052", 1.6, angles=[90])
