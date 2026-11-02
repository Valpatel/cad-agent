"""cadagent.manufacturing.dfm: features held against every verified source, the spread reported, (u) rows advisory
only, the shop's table first for sheet metal, and FDM layer direction (#99)."""
from __future__ import annotations

import pytest

from cadagent.manufacturing import dfm


def _one(process, feature, **kw):
    return dfm.check(process, [feature], **kw)["features"][0]


def test_an_fdm_wall_passes_warns_and_fails_against_the_sources():
    # Prusa 0.45, Protolabs Network 0.8, Xometry EU 0.75-1.0, Xometry EU 3 x nozzle (1.2), Xometry US 1.2-1.5 mm
    thick = _one("fdm", dfm.Feature("w", "wall", 1.5), nozzle_mm=0.4)
    assert thick["verdict"] == "pass" and thick["strictest"] == pytest.approx(1.5)
    assert {r["rule"] for r in thick["rules"]} == {"fdm-wall-min-hubs", "fdm-wall-min-prusa", "fdm-wall-min-xometry-eu",
                                                    "fdm-wall-min-nozzle-xometry-eu", "fdm-wall-min-xometry-us"}
    mid = _one("fdm", dfm.Feature("w", "wall", 0.9), nozzle_mm=0.4)
    assert mid["verdict"] == "warn" and "fdm-wall-min-xometry-us" in mid["detail"]
    assert _one("fdm", dfm.Feature("w", "wall", 0.4), nozzle_mm=0.4)["verdict"] == "fail"


def test_a_rule_needing_a_missing_number_is_skipped_not_guessed():
    f = _one("fdm", dfm.Feature("w", "wall", 1.5))
    assert [s["rule"] for s in f["skipped"]] == ["fdm-wall-min-nozzle-xometry-eu"]
    assert f["skipped"][0]["needs"] == ["nozzle"]


def test_upper_limits_bridge_and_overhang():
    assert _one("fdm", dfm.Feature("b", "bridge", 4.0))["verdict"] == "pass"
    assert _one("fdm", dfm.Feature("b", "bridge", 8.0))["verdict"] == "fail"       # Hubs and Xometry EU: 5 mm
    assert _one("fdm", dfm.Feature("o", "overhang", 40.0))["verdict"] == "pass"
    # 50 deg: beyond Hubs' and Xometry's 45, inside Prusa's 45-60, within Prusa's 75 with 360-degree cooling
    o = _one("fdm", dfm.Feature("o", "overhang", 50.0))
    assert o["verdict"] == "warn"
    assert {r["rule"]: r["verdict"] for r in o["rules"]}["fdm-overhang-max-prusa"] == "warn"
    assert _one("fdm", dfm.Feature("o", "overhang", 80.0))["verdict"] == "fail"
    assert _one("fdm", dfm.Feature("o", "overhang", 50.0), exclude=["fdm-overhang-max-prusa-360-cooling",
                                                                      "fdm-overhang-max-prusa"])["verdict"] == "fail"


def test_unverified_rows_are_advisory_and_never_decide():
    g = _one("sls", dfm.Feature("g", "gap", 0.1))
    assert [a["rule"] for a in g["advisory"]] == ["sls-gap-vs-wall-eos"]
    assert g["advisory"][0]["cite"].endswith("(u)") and not g["advisory"][0]["verified"]
    assert "sls-gap-vs-wall-eos" not in {r["rule"] for r in g["rules"]}
    assert "sls-gap-vs-wall-eos" not in g["detail"]


def test_a_flexing_arm_across_the_layers_warns_with_the_material_factors():
    arm = dfm.Feature("latch", "wall", 2.0, stress_dir=(0, 0, 1), flexes=True)
    f = _one("fdm", arm, material="petg-bambu-basic", nozzle_mm=0.4)
    lay = f["layers"]
    assert f["verdict"] == "warn" and lay["verdict"] == "warn" and lay["direction"] == "across the layers"
    assert lay["factors"]["strain"]["value"] == pytest.approx(5.7 / 11.2, abs=5e-5)
    assert lay["factors"]["strain"]["source"] == "bambu-petg-basic-tds"
    flat = _one("fdm", dfm.Feature("latch", "wall", 2.0, stress_dir=(1, 0, 0.1), flexes=True), nozzle_mm=0.4)
    assert flat["layers"]["direction"] == "along the layers" and flat["verdict"] == "pass"
    # no material: the profile's range over the data sheets, by rule id
    loaded = _one("fdm", dfm.Feature("boss", "wall", 2.0, stress_dir=(0, 0, 1)), nozzle_mm=0.4)
    assert loaded["verdict"] == "pass" and "fdm-orientation-z-strain-ratio-tds" in loaded["layers"]["detail"]
    # the build direction is the layer normal: printed on its side, a Z stress lies in the layers
    side = _one("fdm", arm, material="petg-bambu-basic", nozzle_mm=0.4, build=(1, 0, 0))
    assert side["layers"]["direction"] == "along the layers"


def test_sheet_metal_reads_the_shop_table_first():
    # SendCutSend ALU-063 (1.6 mm 5052): shortest flange 7.696 mm; the generic rules are shown beside it
    short = _one("sheet-metal", dfm.Feature("f", "flange", 7.0), material="5052", thickness_mm=1.6)
    assert short["verdict"] == "fail" and short["shop"]["min"] == pytest.approx(7.696)
    assert {r["rule"] for r in short["rules"]} == {"sm-flange-min-protolabs", "sm-flange-min-davis",
                                                    "sm-flange-min-century", "sm-flange-min-hubs"}
    assert _one("sheet-metal", dfm.Feature("f", "flange", 7.7), material="5052", thickness_mm=1.6)["verdict"] == "pass"
    r = _one("sheet-metal", dfm.Feature("r", "bend-radius", 0.889), material="5052", thickness_mm=1.6)
    assert r["verdict"] == "pass" and "ALU-063" in r["shop"]["rule"]
    # without the shop: generic flange rules at T 1.6, R 1.6: 4T 6.4, 3.5 (T + R) 11.2, 2T + R 4.8
    g = _one("sheet-metal", dfm.Feature("f", "flange", 7.0), material="5052", thickness_mm=1.6, radius_mm=1.6)
    assert g["shop"] is None and g["verdict"] == "warn" and g["strictest"] == pytest.approx(11.2)


def test_sheet_metal_excludes_rules_for_other_alloys():
    r = _one("sheet-metal", dfm.Feature("r", "bend-radius", 2.0), material="mild-steel", thickness_mm=2.0, shop=False,
             radius_mm=2.0)
    assert "sm-bend-radius-min-davis-hard-al" not in {x["rule"] for x in r["rules"]}
    assert r["verdict"] == "pass"
    with_all = _one("sheet-metal", dfm.Feature("r", "bend-radius", 2.0), thickness_mm=2.0, radius_mm=2.0)
    assert "sm-bend-radius-min-davis-hard-al" in {x["rule"] for x in with_all["rules"]}
    assert with_all["verdict"] == "warn"


def test_the_report_names_its_sources_and_limits():
    r = dfm.check("fdm", [dfm.Feature("w", "wall", 1.0)], nozzle_mm=0.4)
    assert "hubs-3dp-geometry-limits" in r["sources"] and r["limits"]
    assert any("(u)" in x for x in r["limits"])


@pytest.mark.parametrize("bad", [dict(kind="fillet"), dict(size=-1.0), dict(size=float("nan"))])
def test_feature_refuses(bad):
    with pytest.raises(ValueError):
        dfm.Feature(**({"name": "f", "kind": "wall", "size": 1.0} | bad))


def test_sheet_metal_needs_a_thickness():
    with pytest.raises(ValueError, match="thickness_mm"):
        dfm.check("sheet-metal", [dfm.Feature("f", "flange", 5.0)])
