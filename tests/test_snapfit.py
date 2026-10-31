"""The calculator against the worked examples of the Covestro snap-fit design guide, plus the check rows."""
import math

import pytest

from cadagent.compliant import snapfit as sf


def test_example_I_tapered_rectangular_hook():
    # Makrolon PC, l 19, b 9.5, undercut 2.4, 30 deg; design to half the 4 % permissible strain.
    eps = sf.MATERIALS["pc"].strain / 2
    h = sf.thickness_for(2.4, 19, eps, design=2)
    assert h == pytest.approx(3.28, abs=0.01)
    sec = sf.rect_section(9.5, 3.28)
    p = sf.deflection_force(sec, 19, eps, sf.MATERIALS["pc"].secant_mpa[0.02])
    assert p == pytest.approx(32.5, abs=0.1)
    mu = sf.MATERIALS["pc"].mu(same_material=True)
    assert mu == pytest.approx(0.6)
    assert (mu + math.tan(math.radians(30))) / (1 - mu * math.tan(math.radians(30))) == pytest.approx(1.8, abs=0.01)
    assert sf.mating_force(p, mu, 30) == pytest.approx(58.5, abs=0.3)


def test_example_II_ring_segment_hook():
    # Bayblend PC/ABS, frequent separation: 60 % of 2.5 %; l 25.4, r2 20, r1 17.5, 75 deg arc, design 2, convex in tension.
    eps = sf.MATERIALS["pc-abs"].allowable(repeated=True)
    assert eps == pytest.approx(0.015)
    sec = sf.ring_section(17.5, 20.0, 75.0, tension="convex")
    assert sec.c == pytest.approx(2.52, abs=0.02)            # the guide's c2
    y = sf.permissible_deflection(sec, 25.4, eps, design=2)
    assert y == pytest.approx(2.11, abs=0.02)


def test_rect_factors_match_general_section_factors():
    sec = sf.rect_section(5, 2)
    for d in (1, 2, 3):
        rect = sf.permissible_deflection(sec, 20, 0.02, design=d)
        general = sf.DESIGN_K[d] * 0.02 * 400 / 1.0
        assert rect == pytest.approx(general, rel=0.02)
    assert sf.root_strain(sec, 20, sf.permissible_deflection(sec, 20, 0.03, 2), 2) == pytest.approx(0.03)


def test_ring_section_degenerates_to_rectangle_for_a_thin_short_arc():
    r2, t, w = 1000.0, 2.0, 10.0
    sec = sf.ring_section(r2 - t, r2, math.degrees(w / (r2 - t / 2)))
    rect = sf.rect_section(w, t)
    assert sec.area == pytest.approx(rect.area, rel=1e-3)
    assert sec.inertia == pytest.approx(rect.inertia, rel=2e-2)
    assert sec.c == pytest.approx(1.0, abs=0.02)


def test_annular_example_lamp_cover():
    # Makrolon lamp: d 200, walls 2.5, undercut 2 x 1 mm shared equally, effective lead 30 deg, mu 0.6, Es 2,200.
    x = sf.annular_factor_hub(205.0, 200.0)
    assert x == pytest.approx(1.7e-3, rel=0.03)
    r = sf.annular_snap(2.0, 200.0, 2.5, 2200.0, 1.7e-3, friction=0.6, lead_deg=30, share=0.5)
    assert r["strain"] == pytest.approx(0.005)
    assert r["transverse_force_n"] == pytest.approx(748, abs=1)
    assert r["mating_force_n"] == pytest.approx(1346, rel=0.01)
    far = sf.annular_snap(2.0, 200.0, 2.5, 2200.0, 1.7e-3, friction=0.6, lead_deg=30, share=0.5,
                          distance_from_end=100)
    assert far["location_factor"] == 3.0


def test_torsion_bar_relations():
    t = sf.torsion_snap(bar_length=10, bar_radius=1.5, strain=0.04, secant_mpa=2000, lever_mm=8, bars=2)
    assert t["shear_strain"] == pytest.approx(1.35 * 0.04)
    assert t["twist_deg"] == pytest.approx(math.degrees(0.054 * 10 / 1.5))
    assert t["shear_modulus_mpa"] == pytest.approx(2000 / 2.7)


def test_self_locking_return_angle_is_inseparable():
    assert math.isinf(sf.mating_force(10, 0.6, 90))
    assert math.isinf(sf.mating_force(10, 0.6, 60))           # mu tan 60 > 1


def test_check_fails_over_strain_and_sharp_root_and_passes_good_design():
    pc = sf.MATERIALS["pc"]
    sec = sf.rect_section(9.5, 3.28)
    good = sf.check_cantilever(length=19, section=sec, undercut=2.4, design=2, strain_allow=pc.allowable(),
                               secant_mpa=1815, friction=0.6, lead_deg=30, return_deg=90, root_radius=1.0,
                               max_mating_n=80, min_retention_n=50)
    assert good["pass"], good["rows"]
    assert math.isinf(good["separation_force_n"])
    bad = sf.check_cantilever(length=10, section=sec, undercut=2.4, design=1,
                              strain_allow=pc.allowable(repeated=True, process_factor=0.5), root_radius=0.2)
    assert not bad["pass"]
    assert [r["check"] for r in bad["rows"] if not r["pass"]] == ["root strain", "root radius"]


def test_allowable_strain_rules():
    assert sf.allowable_strain_from_yield(0.06, "amorphous") == pytest.approx(0.042)
    assert sf.allowable_strain_from_yield(0.04, "filled") == pytest.approx(0.02)
    with pytest.raises(ValueError):
        sf.allowable_strain_from_yield(0.05, "rubber")


def test_spec_file_cli_and_fdm_needs_stated_layer_derating(tmp_path, capsys):
    import json as _json
    from cadagent.cli import main
    spec = {"snaps": [
        {"name": "example-I", "length_mm": 19, "design": 2, "undercut_mm": 2.4, "material": "pc",
         "section": {"rect": {"width_mm": 9.5, "thickness_mm": 3.28}}, "lead_deg": 30, "return_deg": 90,
         "root_radius_mm": 1.0},
        {"name": "printed-clip", "length_mm": 15, "design": 1, "undercut_mm": 1.0, "process": "fdm",
         "material": {"name": "PETG (datasheet)", "strain": 0.03, "source": "test value"},
         "section": {"rect": {"width_mm": 6, "thickness_mm": 1.6}}},
    ]}
    p = tmp_path / "snaps.json"
    p.write_text(_json.dumps(spec))
    out = tmp_path / "result.json"
    assert main(["snapfit", str(p), "--output", str(out)]) == 1
    res = _json.loads(out.read_text())
    assert res["snaps"][0]["pass"] and res["snaps"][0]["mating_force_n"] == pytest.approx(58.5, abs=0.5)
    assert not res["snaps"][1]["pass"]
    assert res["snaps"][1]["rows"][0]["check"] == "process derating"
    text = capsys.readouterr().out
    assert "PASS  example-I" in text and "FAIL  printed-clip" in text
    spec["snaps"][1].update(orientation="bending along layers (arm printed flat)", process_factor=0.8,
                            process_source="coupon C-12, 2026-11-01")
    p.write_text(_json.dumps(spec))
    assert main(["snapfit", str(p)]) == 0


# --------------------------------------------------------------------------- printed (datasheet) allowables

from cadagent.compliant import allowables as al


@pytest.mark.parametrize("name, along, across", [
    # research/compliant-mechanisms.md section 6, single joining, to its rounding
    ("pla-polymaker", 0.011, 0.009), ("pla-bambu-basic", 0.010, 0.010), ("petg-polymaker", 0.017, 0.016),
    ("petg-bambu-basic", 0.023, 0.023), ("petg-bambu-hf", 0.013, 0.010), ("asa-polymaker", 0.013, 0.008),
    ("asa-bambu", 0.015, 0.012), ("copa-polymaker-dry", 0.020, 0.0065), ("copa-polymaker-wet", 0.033, 0.0085),
    ("pa6-cf20-polymaker-dry", 0.009, 0.009),
])
def test_printed_allowables_match_the_derived_table(name, along, across):
    pm = al.PRINTED[name]
    assert pm.allowable("along") == pytest.approx(along, abs=0.0006)
    assert pm.allowable("across") == pytest.approx(across, abs=0.0006)
    assert pm.allowable("across", repeated=True) == pytest.approx(0.6 * pm.allowable("across"))
    assert pm.allowable("across") <= pm.allowable("along")


def test_printed_rule_and_cap():
    copa = al.PRINTED["copa-polymaker-dry"]
    d = copa.derivation("across")
    assert d["z"]["governed_by"] == "0.5 x elongation at break" and d["z"]["strain"] == pytest.approx(0.0065)
    assert d["xy"]["governed_by"] == "0.7 x UTS/E"
    assert d["status"].startswith("derived")
    capped = al.PrintedMaterial("x", "test", (100, 100), (50, 50), (100, 100), moulded_cap=0.04)
    assert capped.single("along") == 0.04                     # 0.7*0.5 = 35 % would exceed the moulded PA66 value
    with pytest.raises(ValueError):
        copa.allowable("z")


def test_dupont_rows_use_their_own_repeated_values():
    assert sf.MATERIALS["pom-delrin-100"].allowable() == 0.08
    assert sf.MATERIALS["pom-delrin-100"].allowable(repeated=True) == 0.02
    assert sf.MATERIALS["pc"].allowable(repeated=True) == pytest.approx(0.024)


def _printed_snap(**kw):
    s = {"name": "lid", "material": "petg-polymaker", "length_mm": 12, "undercut_mm": 0.6, "design": 1,
         "section": {"rect": {"width_mm": 6, "thickness_mm": 1.4}}, "lead_deg": 30, "return_deg": 45,
         "friction": 0.5, "root_radius_mm": 0.8}
    s.update(kw)
    return sf.check_spec_entry(s)


def test_printed_snap_direction_decides():
    # CoPA arm, 1.31 % root strain: fine with the arm lying in XY (2.0 %), fails built along Z (0.65 %)
    along = _printed_snap(material="copa-polymaker-dry", orientation="along", undercut_mm=0.9)
    across = _printed_snap(material="copa-polymaker-dry", orientation="across", undercut_mm=0.9)
    assert along["strain"] == pytest.approx(across["strain"]) == pytest.approx(0.01306, abs=1e-4)
    assert along["pass"] and not across["pass"] and across["rows"][0]["check"] == "root strain"
    assert along["material"]["secant_note"].startswith("datasheet tensile modulus")
    assert along["deflection_force_n"] > across["deflection_force_n"]     # Z modulus is lower


def test_printed_snap_without_orientation_fails_and_assumes_across():
    r = _printed_snap()
    assert not r["pass"] and r["rows"][0]["check"] == "print orientation"
    assert r["material"]["orientation"] == "across"
    with pytest.raises(ValueError):
        _printed_snap(orientation="along", process="sla")
