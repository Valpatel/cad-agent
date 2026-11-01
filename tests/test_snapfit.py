"""The calculator against the worked examples of the Covestro snap-fit design guide, plus the check rows."""
import math

import pytest

from cadagent.mechanical.compliant import snapfit as sf


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
                               max_mating_n=80)
    assert good["pass"], good["rows"]
    assert good["self_locking"] and good["separation_force_n"] is None
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
        {"name": "example-I", "length_mm": 19, "design": 2, "undercut_mm": 2.4, "material": "pc", "process": "moulding",
         "section": {"rect": {"width_mm": 9.5, "thickness_mm": 3.28}}, "lead_deg": 30, "return_deg": 90,
         "root_radius_mm": 1.0},
        {"name": "printed-clip", "length_mm": 15, "design": 1, "undercut_mm": 1.0, "process": "fdm",
         "material": {"name": "PETG (datasheet)", "strain": 0.03, "source": "test value"},
         "section": {"rect": {"width_mm": 6, "thickness_mm": 1.6}}, "root_radius_mm": 0.8},
    ]}
    p = tmp_path / "snaps.json"
    p.write_text(_json.dumps(spec))
    out = tmp_path / "result.json"
    assert main(["snapfit", str(p), "--output", str(out)]) == 1
    res = _json.loads(out.read_text())
    assert res["snaps"][0]["pass"] and res["snaps"][0]["mating_force_n"] == pytest.approx(58.5, abs=0.5)
    assert "Infinity" not in out.read_text() and res["snaps"][0]["self_locking"]
    assert not res["snaps"][1]["pass"]
    assert res["snaps"][1]["rows"][0]["check"] == "process derating"
    text = capsys.readouterr().out
    assert "PASS  example-I" in text and "FAIL  printed-clip" in text
    spec["snaps"][1].update(orientation="along", process_factor=0.8,
                            process_source="coupon C-12, 2026-11-01")
    p.write_text(_json.dumps(spec))
    assert main(["snapfit", str(p)]) == 0


# --------------------------------------------------------------------------- printed (datasheet) allowables

from cadagent.mechanical.compliant import allowables as al


@pytest.mark.parametrize("name, along, across", [
    # research/compliant-mechanisms.md section 6, single joining, to its rounding
    ("pla-polymaker", 0.011, 0.009), ("pla-bambu-basic", 0.0095, 0.0095), ("pla-bambu-matte", 0.0107, 0.0092),
    ("petg-polymaker", 0.017, 0.016), ("petg-bambu-basic", 0.0128, 0.0096), ("petg-bambu-hf", 0.013, 0.010),
    ("petg-cf-bambu", 0.0100, 0.0100), ("asa-polymaker", 0.013, 0.008), ("asa-bambu", 0.0106, 0.0102),
    ("copa-polymaker-dry", 0.020, 0.0065), ("copa-polymaker-wet", 0.033, 0.0085),
    ("pa6-cf20-polymaker-dry", 0.008, 0.008),           # capped at moulded glass-filled PA66 (0.89 % derived)
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
    sheet = al.Sheet("m", "test sheet", "V1", "2026-10-31", "p. 1", "https://example.org", (100, 100), (50, 50),
                     (100, 100))
    capped = al.PrintedMaterial("x", (sheet,), moulded_cap=0.04)
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
    assert along["material"]["secant_basis"].startswith("datasheet tensile modulus")
    assert "upper bound" in [x for x in _printed_snap(material="copa-polymaker-dry", orientation="along",
                                                       undercut_mm=0.5, max_mating_n=50)["rows"]
                             if x["check"] == "mating force"][0]["detail"]
    assert along["deflection_force_n"] > across["deflection_force_n"]     # Z modulus is lower


def test_printed_snap_without_orientation_fails_and_assumes_across():
    r = _printed_snap()
    assert not r["pass"] and r["rows"][0]["check"] == "print orientation"
    assert r["material"]["orientation"] == "across"
    with pytest.raises(ValueError):
        _printed_snap(orientation="along", process="sla")


def test_docs_page_example_runs_and_table_matches_the_code():
    # docs/compliant.md is a living page: its YAML example and printed-allowables table are checked here
    import re
    from pathlib import Path
    import yaml
    doc = (Path(__file__).resolve().parents[1] / "docs" / "compliant.md").read_text()
    result = sf.check_spec(yaml.safe_load(re.search(r"```yaml\n(.*?)```", doc, re.S).group(1)))
    assert result["pass"] and [s["name"] for s in result["snaps"]] == ["lid-latch", "example-I"]
    rows = re.findall(r"`([a-z0-9-]+)` \| ([\d.]+) % \| ([\d.]+) %", doc)
    assert {name for name, _, _ in rows} == set(al.PRINTED)
    for name, along, across in rows:
        assert al.PRINTED[name].allowable("along") * 100 == pytest.approx(float(along), abs=0.06), name
        assert al.PRINTED[name].allowable("across") * 100 == pytest.approx(float(across), abs=0.06), name


# --------------------------------------------------------------------------- review of #105: nothing passes unchecked

def _snap(**kw):
    s = {"name": "s", "material": "pc", "process": "moulding", "length_mm": 19, "undercut_mm": 2.4, "design": 2,
         "section": {"rect": {"width_mm": 9.5, "thickness_mm": 3.28}}, "lead_deg": 30, "return_deg": 45,
         "root_radius_mm": 1.0}
    s.update(kw)
    return sf.check_spec_entry(s)


@pytest.mark.parametrize("kw, missing", [
    ({"material": "pc-blend"}, "secant_mpa"),                                     # no secant modulus in the guide
    ({"material": "petg-polymaker", "process": "fdm", "orientation": "along", "undercut_mm": 0.3}, "friction"),
    ({"lead_deg": None}, "lead_deg"),
])
def test_a_declared_force_limit_that_cannot_be_computed_fails(kw, missing):
    r = _snap(max_mating_n=1, **kw)
    row = [x for x in r["rows"] if x["check"] == "mating force"][0]
    assert not r["pass"] and not row["pass"] and missing in row["detail"]


def test_self_locking_retention_fails_closed():
    r = _snap(return_deg=90, min_retention_n=10)
    row = [x for x in r["rows"] if x["check"] == "retention force"][0]
    assert not row["pass"] and "self-locking" in row["detail"]
    assert _snap(return_deg=30, min_retention_n=10)["pass"]


@pytest.mark.parametrize("kw", [
    {"material": {"name": "x", "strain": 3, "source": "typo: meant 3 %"}},
    {"process_factor": 5}, {"share": 0}, {"undercut_mm": -1}, {"design": 4}, {"lead_deg": 95},
    {"length_mm": "long"}, {"repeated": "yes"}, {"process": "casting"},
    {"section": {"rect": {"width_mm": 0, "thickness_mm": 2}}},
])
def test_out_of_range_inputs_are_errors_that_name_the_field(kw):
    with pytest.raises(ValueError, match="snap 's'"):
        _snap(**kw)


def test_process_must_be_stated_and_layered_processes_need_derating():
    r = _snap(process=None)
    assert not r["pass"] and r["rows"][0]["check"] == "process"
    for proc in ("FDM ", "sls", "mjf", "sla"):
        r = _snap(process=proc)
        assert not r["pass"] and r["rows"][0]["check"] == "process derating", proc
    ok = _snap(process="mjf", orientation="along", process_factor=0.5, process_source="coupon M-3")
    assert ok["material"]["allowable"] == pytest.approx(0.02)


def test_secant_modulus_is_interpolated_at_the_root_strain():
    assert sf.secant_at({0.02: 1815.0, 0.005: 2200.0}, 0.0042) == 2200.0
    assert sf.secant_at({0.02: 1815.0, 0.005: 2200.0}, 0.0125) == pytest.approx(2007.5)
    r = _snap(undercut_mm=0.5)                                    # 0.42 % root strain
    assert r["material"]["secant_mpa"] == 2200.0 and "held" in r["material"]["secant_basis"]


def test_missing_root_radius_fails():
    r = _snap(root_radius_mm=None)
    assert not r["pass"] and [x for x in r["rows"] if x["check"] == "root radius"][0]["value"] is None


def test_large_deflection_is_warned():
    assert _snap()["warnings"]                                    # Example I: y/l = 0.13
    assert not _snap(undercut_mm=1.0)["warnings"]


def test_ring_section_concave_fibre_beyond_180_degrees():
    import numpy as np
    for arc in (120.0, 200.0, 300.0, 360.0):
        sec = sf.ring_section(10.0, 12.0, arc, tension="concave")
        th = math.radians(arc) / 2
        n_r, n_a = 400, 4000                                      # midpoint rule
        r, a = np.meshgrid(10 + (np.arange(n_r) + 0.5) * 2 / n_r, -th + (np.arange(n_a) + 0.5) * 2 * th / n_a)
        y, w = r * np.cos(a), r                                   # polar area element r dr da
        ybar = (y * w).sum() / w.sum()
        assert sec.dims["ybar"] == pytest.approx(ybar, abs=1e-3)
        y_min = min(10 * math.cos(th), 12 * math.cos(min(th, math.pi)))   # exact extreme fibre
        assert sec.c == pytest.approx(ybar - y_min, abs=1e-3), arc
        assert y.min() >= y_min - 1e-9 and y.min() == pytest.approx(y_min, abs=0.01)
        assert sec.inertia == pytest.approx((((y - ybar) ** 2) * w).sum() / w.sum() * sec.area, rel=1e-3)


def test_torsion_force_and_deflection_from_first_principles():
    t = sf.torsion_snap(bar_length=10, bar_radius=1.5, strain=0.04, secant_mpa=2000, lever_mm=8, bars=2)
    phi = math.radians(t["twist_deg"])
    torque = (2000 / 2.7) * (math.pi * 1.5 ** 4 / 2) * phi / 10   # T = G Ip phi / L per bar
    assert t["force_n"] == pytest.approx(2 * torque / 8)
    assert t["deflection_mm"] == pytest.approx(8 * math.sin(phi))


def test_annular_shaft_factor():
    q = 1.2
    expect = 0.62 * math.sqrt((q - 1) / (q + 1)) / ((q * q + 1) / (q * q - 1) - 0.35)
    assert sf.annular_factor_shaft(12.0, 10.0) == pytest.approx(expect)
    assert sf.annular_factor_shaft(12.0, 10.0) > sf.annular_factor_hub(12.0, 10.0)   # the -nu term


def test_bad_yaml_is_exit_2(tmp_path):
    from cadagent.cli import main
    p = tmp_path / "s.yaml"
    p.write_text("snaps: [ {name: a, length_mm: 3")
    assert main(["snapfit", str(p)]) == 2
    p.write_text("snaps:\n  - name: a\n")
    assert main(["snapfit", str(p)]) == 2


def test_docs_ranges_match_the_datasheets():
    # the living page's stated across/along ranges for PLA, PETG, ASA and CoPA come from the PRINTED rows
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1] / "docs" / "compliant.md").read_text()
    rows = [v.sheets[0] for k, v in al.PRINTED.items() if not k.startswith("pa6-cf")]     # the current editions
    strength = [s.uts_mpa[1] / s.uts_mpa[0] for s in rows]
    elong = [s.break_pct[1] / s.break_pct[0] for s in rows]
    stated = f"{round(min(strength) * 100)}–{round(max(strength) * 100)} % of the in-plane strength but only " \
             f"{round(min(elong) * 100)}–{round(max(elong) * 100)} % of the elongation"
    assert " ".join(doc.split()).count(stated) == 1, stated


def test_docs_direction_costs_match_the_code():
    from pathlib import Path
    doc = " ".join((Path(__file__).resolve().parents[1] / "docs" / "compliant.md").read_text().split())
    ratio = {k: v.allowable("across") / v.allowable("along") for k, v in al.PRINTED.items()}
    pct = lambda keys: sorted(round(ratio[k] * 100) for k in keys)
    pla_petg = pct(k for k in ratio if k.startswith(("pla", "petg")))
    copa = pct(k for k in ratio if k.startswith("copa"))
    assert f"{pla_petg[0]}–{pla_petg[-1]} % of the in-plane value for PLA and PETG" in doc
    assert f"{round(ratio['asa-bambu'] * 100)} % for Bambu ASA, {round(ratio['asa-polymaker'] * 100)} % for Polymaker ASA" in doc
    assert f"{copa[0]}–{copa[-1]} % for CoPA" in doc


def test_self_locking_lead_fails_and_json_stays_valid(tmp_path):
    import json as _json
    from cadagent.cli import main
    r = _snap(lead_deg=70, friction=0.6)
    assert not r["pass"] and r["mating_self_locking"] and "mating_force_n" not in r
    spec = tmp_path / "s.json"
    spec.write_text(_json.dumps({"snaps": [{"name": "s", "material": "pc", "process": "moulding", "length_mm": 19,
                                            "undercut_mm": 2.4, "design": 2, "lead_deg": 70, "root_radius_mm": 1,
                                            "section": {"rect": {"width_mm": 9.5, "thickness_mm": 3.28}}}]}))
    out = tmp_path / "r.json"
    assert main(["snapfit", str(spec), "--output", str(out)]) == 1
    assert _json.loads(out.read_text())["snaps"][0]["mating_self_locking"]


def test_secant_basis_says_when_it_is_held_not_interpolated():
    assert "held" in _snap(undercut_mm=0.3)["material"]["secant_basis"]          # below 0.5 %
    assert "interpolated" in _snap(undercut_mm=1.5)["material"]["secant_basis"]  # 1.25 %


# ----------------------------------------------------------------------------- along the insertion (#165)

def _example_I_engagement(**kw):
    """The guide's Example I hook (PC, l 19, h 3.28, b 9.5, design 2, 2.4 mm undercut, 30 deg lead, mu 0.6,
    Es 1,815 MPa) along its insertion."""
    args = dict(length=19, section=sf.rect_section(9.5, 3.28), undercut=2.4, lead_deg=30, design=2,
                secant_mpa=1815, friction=0.6)
    args.update(kw)
    return sf.engagement(**args)


def test_engagement_peaks_at_the_guides_example_I_numbers():
    """At the top of the lead the curve is the guide's own Example I result: about 2 % root strain, P 32.5 N and
    W 58.5 N, the same as check_cantilever gives for that arm."""
    e = _example_I_engagement(land_mm=1.5)
    top = e["points"][1]
    assert top["deflection_mm"] == pytest.approx(2.4)
    assert top["strain"] == pytest.approx(0.02, abs=2e-4)
    assert top["deflection_force_n"] == pytest.approx(32.5, abs=0.2)
    assert top["mating_force_n"] == pytest.approx(58.5, abs=0.4)
    c = sf.check_cantilever(length=19, section=sf.rect_section(9.5, 3.28), undercut=2.4, design=2, strain_allow=0.04,
                            secant_mpa=1815, friction=0.6, lead_deg=30, root_radius=1.0)
    assert top["strain"] == c["strain"] and top["mating_force_n"] == c["mating_force_n"]
    assert top["deflection_force_n"] == c["deflection_force_n"] and e["peak"] == {
        k: top[k] for k in ("deflection_mm", "strain", "deflection_force_n", "mating_force_n")}


def test_engagement_rides_the_lead_then_the_land_then_drops():
    e = _example_I_engagement(land_mm=1.5)
    lead = 2.4 / math.tan(math.radians(30))
    assert e["lead_travel_mm"] == pytest.approx(lead)
    assert [p["phase"] for p in e["points"]] == ["lead", "lead", "land", "land", "released"]
    assert [p["travel_mm"] for p in e["points"]] == pytest.approx([0, lead, lead, lead + 1.5, lead + 1.5])
    assert [p["deflection_mm"] for p in e["points"]] == pytest.approx([0, 2.4, 2.4, 2.4, 0])
    start, top, land0, land1, released = e["points"]
    assert start["strain"] == start["deflection_force_n"] == start["mating_force_n"] == 0
    # on the land only friction resists: the same formula at 0 deg, mu * P
    assert land0["mating_force_n"] == land1["mating_force_n"] == pytest.approx(0.6 * top["deflection_force_n"])
    assert sf.mating_force(top["deflection_force_n"], 0.6, 0) == pytest.approx(land0["mating_force_n"])
    assert released["strain"] == released["mating_force_n"] == 0
    # without a land the hook drops straight off the top of the lead
    assert [p["phase"] for p in _example_I_engagement()["points"]] == ["lead", "lead", "released"]


def test_engagement_is_linear_in_the_travel_on_the_lead():
    """Halfway up the lead, every quantity is half its peak: the points returned are exact with straight lines
    between them, which is what lets the figure animate them with linear keyframes."""
    e = _example_I_engagement()
    top = e["points"][1]
    half = sf.root_strain(sf.rect_section(9.5, 3.28), 19, 1.2, 2)
    assert half == pytest.approx(top["strain"] / 2)
    p_half = sf.deflection_force(sf.rect_section(9.5, 3.28), 19, half, 1815)
    assert sf.mating_force(p_half, 0.6, 30) == pytest.approx(top["mating_force_n"] / 2)
    assert sf.travel_at_strain(e, top["strain"] / 2) == pytest.approx(e["lead_travel_mm"] / 2)
    assert sf.travel_at_strain(e, top["strain"]) == pytest.approx(e["lead_travel_mm"])
    assert sf.travel_at_strain(e, top["strain"] * 1.01) is None and sf.travel_at_strain(e, 0) is None


def test_engagement_without_friction_or_modulus_gives_no_force_and_a_self_locking_lead_none():
    e = _example_I_engagement(friction=None)
    assert all(p["mating_force_n"] is None for p in e["points"]) and e["points"][1]["deflection_force_n"] > 0
    e = _example_I_engagement(secant_mpa=None)
    assert all(p["deflection_force_n"] is None and p["mating_force_n"] is None for p in e["points"])
    locked = _example_I_engagement(lead_deg=60, land_mm=1.0)          # 0.6 tan 60 > 1
    assert locked["mating_self_locking"] and locked["points"][1]["mating_force_n"] is None
    assert locked["points"][2]["mating_force_n"] == pytest.approx(0.6 * locked["points"][2]["deflection_force_n"])
    assert not _example_I_engagement()["mating_self_locking"]
    assert "self_locking" not in locked          # check_cantilever's self_locking is the return face holding


def test_engagement_shares_the_lift_and_refuses_nonsense():
    full, half = _example_I_engagement(), _example_I_engagement(share=0.5)
    assert half["points"][1]["deflection_mm"] == pytest.approx(1.2)
    assert half["points"][1]["strain"] == pytest.approx(full["points"][1]["strain"] / 2)
    assert half["lead_travel_mm"] == full["lead_travel_mm"]           # the edge still rides the whole undercut
    for bad in ({"lead_deg": 0}, {"lead_deg": 90}, {"land_mm": -1}, {"share": 0}, {"undercut": 0}, {"design": 4}):
        with pytest.raises(ValueError):
            _example_I_engagement(**bad)


def test_a_checked_snap_names_the_friction_it_used():
    """check_spec_entry's material says which mu the forces used and where it came from: the guide's family value
    for the plastic on itself (the default) or against steel, a given one, or none."""
    base = {"material": "copa-polymaker-dry", "orientation": "along", "length_mm": 15, "undercut_mm": 1.3,
            "section": {"rect": {"width_mm": 6, "thickness_mm": 1.6}}, "root_radius_mm": 1.0, "lead_deg": 30}
    assert sf.check_spec_entry(base)["material"]["friction"] == pytest.approx(0.35 * 1.5)   # PA, same material
    assert sf.check_spec_entry({**base, "friction": 0.4})["material"]["friction"] == 0.4
    assert sf.check_spec_entry({**base, "material": "petg-cf-bambu"})["material"]["friction"] is None
    assert sf.check_spec_entry({**base, "material": "pc", "process": "moulding"})["material"]["friction"] == \
        pytest.approx(0.6)
    basis = lambda **k: sf.check_spec_entry({**base, **k})["material"]["friction_basis"]
    assert (basis(), basis(friction=0.4), basis(same_material=False)) == ("same material", "given", "against steel")
    assert sf.check_spec_entry({**base, "same_material": False})["material"]["friction"] == pytest.approx(0.35)
    assert basis(material="petg-cf-bambu") is None and basis(material="petg-cf-bambu", friction=0.3) == "given"
    assert basis(material="pc", process="moulding") == "same material"
