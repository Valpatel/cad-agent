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
    # relief depth: Davis's T + R = 3.2 mm is the strictest generic; SendCutSend's T + R + 0.5 is its own (shop) rule
    assert b["relief_depth_mm"]["rule"] in {"sm-relief-depth-min-davis", "sm-relief-depth-min-century"}
    assert b["relief_depth_mm"]["value"] == pytest.approx(3.2)
    assert "sm-relief-depth-min-sendcutsend" not in {x["rule"] for x in b["relief_depth_mm"]["all"]}


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


def test_an_unverified_k_row_never_sets_a_flat_length(tmp_path):
    from cadagent.manufacturing import process as pp
    head, tail = pp.DATA.read_text(encoding="utf-8").split("  - id: sm-k-air-soft-r-le-t-hubs\n", 1)
    tail = tail.replace("    status: read\n", "    status: u\n", 1)
    data = tmp_path / "process-profiles.yaml"
    data.write_text(head + "  - id: sm-k-air-soft-r-le-t-hubs\n" + tail, encoding="utf-8")
    assert not pp.load(data)["sheet-metal"].rule("sm-k-air-soft-r-le-t-hubs").verified
    with pytest.raises(pp.ProfileDataError, match=r"\(u\)"):
        sm.bend("5052", 2.0, radius_mm=2.0, path=data)


# ----------------------------------------------------------------------------- more stock: galvanised and stainless

@pytest.mark.parametrize("material, t, sku, r, k", [
    ("304", 1.524, "SST-060", 1.778, 0.34),         # SendCutSend's specs rows (sendcutsend-specs)
    ("316", 3.175, "SST316-125", None, None),
    ("g90", 1.499, "G90-059", None, None),
])
def test_galvanised_and_stainless_read_the_shops_rows(material, t, sku, r, k):
    b = sm.bend(material, t)
    assert b["stock"] == sku and b["k"]["source"] == "sendcutsend-specs"
    if r is not None:
        assert b["radius_mm"]["value"] == r and b["k"]["value"] == k


def test_stainless_off_the_table_takes_the_hard_metal_k():
    b = sm.bend("304", 2.0)
    assert b["stock"] is None
    assert b["radius_mm"]["value"] == pytest.approx(2.0)                    # T: every generic rule left for hard metal
    assert b["k"]["rule"] == "sm-k-air-hard-r-le-t-hubs" and b["k"]["value"] == 0.4


def test_every_sendcutsend_rule_is_marked_as_its_shops():
    # a shop's rule must never leak into the generic checks a project without that shop runs
    from cadagent.manufacturing import process as pp
    prof = pp.profile("sheet-metal")
    loose = [r.id for r in prof.rules if r.id.endswith("-sendcutsend") and r.shop != "sendcutsend"]
    assert not loose
    assert all(not prof.rule(l.rule).shop for l in prof.limits(compare="sm-relief-width", T=1.6, R=1.6))


# ----------------------------------------------------------------------------- a hole near a bend, on each rule's datum

def test_feature_to_bend_by_datum():
    # ALU-063: T 1.6, R 0.889. Tangent datum: Hubs and Davis 2T = 3.2. No datum: DFMA 2T + R = 4.089,
    # Paulsen 2.5T + R = 4.889, Protolabs 4T = 6.4. Century 1.5 (T + R) = 3.7335 to the inside face, d + R tan 45
    r = sm.feature_to_bend("5052", 1.6, 3.0)
    rows = {x["rule"]: x for x in r["rules"]}
    assert r["verdict"] == "fail" and r["radius_mm"] == 0.889
    assert rows["sm-hole-to-bend-min-hubs"]["verdict"] == "fail" and rows["sm-hole-to-bend-min-hubs"]["min_mm"] == 3.2
    assert rows["sm-hole-to-bend-min-dfma"]["min_mm"] == pytest.approx(4.089)
    assert rows["sm-hole-to-bend-min-dfma"]["verdict"] == "warn"            # no datum stated: never a fail
    assert rows["sm-hole-to-bend-min-paulsen"]["min_mm"] == pytest.approx(4.889)
    assert rows["sm-feature-to-bend-protolabs"]["min_mm"] == pytest.approx(6.4)
    c = rows["sm-hole-to-bend-min-century"]
    assert c["distance_mm"] == pytest.approx(3.889) and c["min_mm"] == pytest.approx(3.7335) and c["verdict"] == "pass"
    assert sm.feature_to_bend("5052", 1.6, 3.2)["verdict"] == "warn"          # clears every stated datum
    assert sm.feature_to_bend("5052", 1.6, 6.4)["verdict"] == "pass"


def test_feature_to_bend_converts_the_inside_face_at_45_degrees():
    # T 2, R 2 at 45 deg: the inside face is R tan 22.5 = 0.828427 past the tangent; Century needs 1.5 (2 + 2) = 6
    ok = {x["rule"]: x for x in sm.feature_to_bend("mild-steel", 2.0, 5.2, 45.0, radius_mm=2.0)["rules"]}
    assert ok["sm-hole-to-bend-min-century"]["distance_mm"] == pytest.approx(5.2 + 2 * math.tan(math.radians(22.5)), abs=1e-4)
    assert ok["sm-hole-to-bend-min-century"]["verdict"] == "pass"
    assert sm.feature_to_bend("mild-steel", 2.0, 5.2, 45.0, radius_mm=2.0)["verdict"] == "warn"
    assert sm.feature_to_bend("mild-steel", 2.0, 5.1, 45.0, radius_mm=2.0)["verdict"] == "fail"


# ----------------------------------------------------------------------------- a bent part against the shop's limits

def _by(r):
    return {c["check"]: c for c in r["checks"]}


def test_check_bends_relief_width_generic_and_shop():
    # generic: Hubs and Paulsen T = 1.6 mm; SendCutSend's own T/2 = 0.8 mm only counts when the shop is named
    sc = dict(shop="sendcutsend")
    assert _by(sm.check_bends("5052", 1.6, [20, 20], relief_width_mm=1.6, **sc))["relief width"]["verdict"] == "pass"
    assert _by(sm.check_bends("5052", 1.6, [20, 20], relief_width_mm=0.9, **sc))["relief width"]["verdict"] == "warn"
    assert _by(sm.check_bends("5052", 1.6, [20, 20], relief_width_mm=0.9))["relief width"]["verdict"] == "fail"
    assert _by(sm.check_bends("5052", 1.6, [20, 20], relief_width_mm=0.7, **sc))["relief width"]["verdict"] == "fail"


def test_check_bends_flange_angle_box_and_channel():
    r = sm.check_bends("5052", 1.6, [7.0, 20], [90, 135], shop="sendcutsend")
    c = _by(r)
    assert r["verdict"] == "fail" and r["stock"] == "ALU-063"
    assert c["flange 1"]["verdict"] == "fail" and c["flange 2"]["verdict"] == "pass"   # ALU-063 shortest 7.696 mm
    assert c["angle 1"]["verdict"] == "pass" and c["angle 2"]["verdict"] == "fail"     # 130 deg at most
    assert "angle 1" not in _by(sm.check_bends("5052", 1.6, [20, 20]))                  # no shop, no shop limit
    box = dict(box=True, shop="sendcutsend")
    assert _by(sm.check_bends("5052", 1.6, [80] * 4, hardware=True, **box))["box flange"]["verdict"] == "fail"  # 76.2
    assert _by(sm.check_bends("5052", 1.6, [80] * 4, **box))["box flange"]["verdict"] == "pass"                 # 127
    ch = dict(shop="sendcutsend")
    assert _by(sm.check_bends("5052", 1.6, [20, 20], channel_base_mm=39.9, **ch))["channel base"]["verdict"] == "fail"
    assert _by(sm.check_bends("5052", 1.6, [20, 20], channel_base_mm=40.0, **ch))["channel base"]["verdict"] == "pass"


def test_check_bends_relief_depth_from_the_row_or_the_rules():
    # on the shop's row ALU-063 the depth is 2.997 mm
    assert _by(sm.check_bends("5052", 1.6, [20], relief_depth_mm=2.997))["relief depth"]["verdict"] == "pass"
    assert _by(sm.check_bends("5052", 1.6, [20], relief_depth_mm=2.9))["relief depth"]["verdict"] == "fail"
    # off the row (R 1.6): generic T + R = 3.2 mm; SendCutSend named adds its own T + R + 0.5 = 3.7 mm
    g = _by(sm.check_bends("5052", 1.6, [20], relief_depth_mm=3.5, radius_mm=1.6))["relief depth"]
    assert g["verdict"] == "pass"
    s = _by(sm.check_bends("5052", 1.6, [20], relief_depth_mm=3.5, radius_mm=1.6, shop="sendcutsend"))["relief depth"]
    assert s["verdict"] == "fail" and s["rule"] == "sm-relief-depth-min-sendcutsend"


def test_check_bends_refuses():
    with pytest.raises(ValueError):
        sm.check_bends("5052", 1.6, [20, 20], [90])
    with pytest.raises(ValueError):
        sm.check_bends("5052", 1.6, [])
    with pytest.raises(Exception):
        sm.check_bends("5052", 1.6, [20], shop="no-such-shop")


def test_feature_to_bend_gives_no_extra_credit_past_90_degrees():
    # T 2, R 6: Century needs 1.5 (2 + 6) = 12. At 120 deg R tan 60 = 10.39 would pass a hole 4 mm from the tangent;
    # capped at R it is 10 mm, a fail, as at 90 deg
    for a in (90.0, 120.0):
        c = {x["rule"]: x for x in sm.feature_to_bend("mild-steel", 2.0, 4.0, a, radius_mm=6.0)["rules"]}
        assert c["sm-hole-to-bend-min-century"]["distance_mm"] == pytest.approx(10.0)
        assert c["sm-hole-to-bend-min-century"]["verdict"] == "fail"


def test_a_flange_that_clears_only_the_shops_row_warns():
    # ALU-063's row: 7.696 mm; Century's 3.5 (T + R) = 3.5 x 2.489 = 8.7115 mm at the row's radius
    c = _by(sm.check_bends("5052", 1.6, [8.0]))["flange 1"]
    assert c["verdict"] == "warn" and c["rule"] == "sm-flange-min-century"
    assert c["limit"] == "at least 8.711 mm"
    # without the rows the radius is the generic T = 1.6 and Century needs 3.5 x 3.2 = 11.2 mm
    assert _by(sm.check_bends("5052", 1.6, [8.0], rows=False))["flange 1"]["verdict"] == "fail"


def test_the_shops_relief_rule_holds_on_its_own_row_too():
    # SST316-060: the feed's depth is 2.997 mm, the shop's own rule T + R + 0.5 = 1.524 + 1.778 + 0.5 = 3.802 mm
    c = _by(sm.check_bends("316", 1.524, [20], relief_depth_mm=3.0, shop="sendcutsend"))["relief depth"]
    assert c["verdict"] == "fail" and c["rule"] == "sm-relief-depth-min-sendcutsend"
    assert c["limit"] == "at least 3.802 mm"
    # no shop: 3.0 clears the row (2.997) but not the generic T + R = 3.302 (Davis, Century Tywood), so it warns
    assert _by(sm.check_bends("316", 1.524, [20], relief_depth_mm=3.0))["relief depth"]["verdict"] == "warn"


def test_the_shops_angle_range_and_hardware_on_acute_bends():
    sc = dict(shop="sendcutsend")
    assert _by(sm.check_bends("5052", 1.6, [20], 3.0, **sc))["angle 1"]["verdict"] == "fail"       # under 5 deg
    assert _by(sm.check_bends("5052", 1.6, [20], 120.0, **sc))["angle 1"]["verdict"] == "pass"
    assert _by(sm.check_bends("5052", 1.6, [20], 120.0, hardware=True, **sc))["angle 1"]["verdict"] == "fail"


def test_shop_only_inputs_without_a_shop_say_so():
    r = sm.check_bends("5052", 1.6, [20, 20], box=True, channel_base_mm=40)
    assert {c["check"] for c in r["checks"]} == {"flange 1", "flange 2"} and r["notes"]
    with pytest.raises(ValueError):
        sm.check_bends("5052", 1.6, [20, 20], channel_base_mm=-5)
