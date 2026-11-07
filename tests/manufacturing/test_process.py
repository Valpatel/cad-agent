"""cadagent.manufacturing.process: every profile loads, every value carries a source id that resolves in the reference
registry (#118), unverified rows say so, and the numbers are the cited sources' (#99)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from cadagent.manufacturing import process as pp
from cadagent.mechanical.compliant.allowables import PRINTED

ROOT = Path(__file__).resolve().parents[2]
RAW = yaml.safe_load((ROOT / "docs" / "research" / "process-profiles.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def profiles():
    return pp.load()


def test_default_data_uses_the_moved_source_and_never_a_stale_old_copy(tmp_path, monkeypatch):
    content = pp.DATA.read_bytes()
    current, stale = tmp_path / "docs/research/process-profiles.yaml", tmp_path / "research/process-profiles.yaml"
    for path in (current, stale):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    monkeypatch.setattr(pp, "ROOT", tmp_path)
    monkeypatch.setattr(pp, "DATA", current)
    monkeypatch.delenv(pp.ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    assert pp.load().path == current
    current.unlink()
    with pytest.raises(pp.ProfileDataError, match="no process-profile data") as error:
        pp.load()
    assert str(current) in str(error.value) and stale.exists()


def test_every_process_loads_with_its_rules(profiles):
    assert sorted(p.process for p in profiles) == sorted(RAW["processes"])
    assert sum(len(p.rules) for p in profiles) == len(RAW["rules"])
    for p in profiles:
        assert p.rules and p.title == RAW["processes"][p.process]
        assert all(r.process == p.process for r in p.rules)


def test_every_value_has_a_source_that_resolves(profiles):
    """Rules, shop rows, formulas and material factors: each names a source id, and the id is in the reference
    registry (or is one of the data file's datasets)."""
    for p in profiles:
        for r in p.rules:
            assert r.source and r.source in p.sources and p.sources[r.source].resolved, r.id
        for m in p.materials.values():
            if isinstance(m, pp.FdmMaterial):
                for q, f in m.factors.items():
                    assert f.source == m.source and f.citation.startswith(("Bambu Lab", "Polymaker")), (m.key, q)
                    assert "https://" in f.citation, (m.key, q)
                    assert p.source(f.source).resolved, (m.key, q)
            else:
                for s in m.stocks:
                    assert p.sources[s.source].resolved and p.sources[s.source].url.startswith("https://"), s.sku
        for f in p.formulas.values():
            assert p.sources[f["source"]].resolved, f["id"]


def test_every_rule_evaluates_with_its_variables(profiles):
    env = dict(T=1.5, R=1.5, wall=2.5, D=4.0, L=50.0, depth=12.0, width=6.0, H=8.0, nozzle=0.4, rib=1.5,
               texture=0.05, area=36.0, die=16.0, BA=2.5, E=6.9, hole=5.4, grip=3.2, track=0.42, facets=12)
    for r in profiles.rules():
        lim = r.limit(**{k: env[k] for k in r.variables})
        assert lim.rule == r.id and lim.source == r.source and lim.verified == r.verified
        assert any(v is not None for v in (lim.min, lim.max, lim.value))
        assert all(math.isfinite(v) for v in (lim.min, lim.max, lim.value) if v is not None)


def test_a_missing_variable_is_named():
    with pytest.raises(pp.ProfileDataError, match="give T"):
        pp.profile("sheet-metal").rule("sm-flange-min-protolabs").limit()


def unverified_profile_path(tmp_path):
    """Plant an unverified source in a real profile; do not retain bad production data just to test the guard."""
    data = yaml.safe_load(pp.DATA.read_text(encoding="utf-8"))
    data["sources"] = yaml.safe_load(pp.REGISTRY.read_text(encoding="utf-8"))["sources"]
    candidate = next(r for r in data["rules"] if r["id"] == "sls-clearance-jlc3dp")
    candidate["status"] = "u"
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_unverified_rows_are_marked_and_refused_for_enforcement(tmp_path):
    sls = pp.profile("sls", unverified_profile_path(tmp_path))
    u = sls.rule("sls-clearance-jlc3dp")
    assert not u.verified and u.flag == "(u)"
    lim = u.limit()
    assert not lim.verified and lim.text.endswith("(u)") and lim.cite().endswith("(u)")
    assert [r.id for r in sls.unverified()] == ["sls-clearance-jlc3dp"]
    with pytest.raises(pp.ProfileDataError, match=r"\(u\)"):
        sls.verified_rule("sls-clearance-jlc3dp")
    ok = pp.profile("fdm").verified_rule("fdm-wall-min-hubs").limit()
    assert ok.verified and "(u)" not in ok.text
    assert {r.id for r in pp.load().rules() if not r.verified} == \
        {r["id"] for r in RAW["rules"] if r["status"] == "u"}


def test_specimen_labels_are_not_a_manufacturing_limit():
    """EOS slides 10–11 use different wall ranges and show incomplete openings, not a combined minimum."""
    assert "sls-gap-vs-wall-eos" not in {r.id for r in pp.profile("sls").rules}


@pytest.mark.parametrize("rule_id, env, want", [
    # Protolabs Network, "How to design parts for FDM 3D printing" / geometry limits table: 0.8 mm minimum FDM wall
    ("fdm-wall-min-hubs", {}, {"min": 0.8}),
    # Xometry Europe: three nozzle diameters; a 0.4 mm nozzle gives 1.2 mm
    ("fdm-wall-min-nozzle-xometry-eu", {"nozzle": 0.4}, {"min": 1.2}),
    # Protolabs Network desktop FDM: +/-0.5 % with a lower limit of +/-0.5 mm; at 200 mm, 1.0 mm
    ("fdm-tolerance-desktop-hubs", {"L": 200.0}, {"value": 1.0}),
    ("fdm-tolerance-desktop-hubs", {"L": 50.0}, {"value": 0.5}),
    # Century Tywood's shop rule, minimum flange 3.5 (T + R): T 1.6, R 0.889 gives 8.7115 mm
    ("sm-flange-min-century", {"T": 1.6, "R": 0.889}, {"min": 8.7115}),
    # Paulsen, hole to bend at least 2.5 T + R
    ("sm-hole-to-bend-min-paulsen", {"T": 2.0, "R": 2.0}, {"min": 7.0}),
    # Protolabs hole to edge: 1/16 in (1.574 mm) up to 0.036 in (0.914 mm) stock, else 1/8 in (3.175 mm)
    ("sm-hole-to-edge-protolabs", {"T": 0.9}, {"min": 1.574}),
    ("sm-hole-to-edge-protolabs", {"T": 1.0}, {"min": 3.175}),
])
def test_golden_rule_values(rule_id, env, want):
    process = next(r["process"] for r in RAW["rules"] if r["id"] == rule_id)
    lim = pp.profile(process).rule(rule_id).limit(**env)
    for k, v in want.items():
        assert getattr(lim, k) == pytest.approx(v), (rule_id, k)


def test_tolerances_are_listed_by_source():
    tol = {l.rule: l.value for l in pp.profile("fdm").tolerance(100.0)}
    assert tol["fdm-tolerance-desktop-hubs"] == pytest.approx(0.5)
    assert tol["fdm-tolerance-industrial-hubs"] == pytest.approx(0.2)
    assert tol["fdm-tolerance-xometry-us"] == pytest.approx(0.127)       # +/-0.005 in


def test_fdm_materials_cover_the_issue_families_and_every_allowables_entry():
    fdm = pp.profile("fdm")
    assert set(fdm.materials) == set(PRINTED)
    for family in ("petg", "pla", "asa", "pa-cf"):
        assert fdm.family(family), family


@pytest.mark.parametrize("key, quantity, want", [
    # Bambu PETG Basic: V3.0 strength 35 / 51 MPa (0.686); strain V2.0 5.7 / 11.2 % (0.509) is below V3.0's 5.2 / 9.5
    ("petg-bambu-basic", "strength", 35 / 51),
    ("petg-bambu-basic", "strain", 5.7 / 11.2),
    # Bambu PLA Basic V3.0 strength 31 / 35 and V2.0 35 / 39: V3.0 is lower (0.886)
    ("pla-bambu-basic", "strength", 31 / 35),
    # Polymaker PolyLite ASA V6.0: strain 1.65 / 6.7 %
    ("asa-polymaker", "strain", 1.65 / 6.7),
    # Polymaker Fiberon PA6-CF20 dry V1.1: modulus 3759.5 / 8636.5 MPa
    ("pa6-cf20-polymaker-dry", "modulus", 3759.5 / 8636.5),
])
def test_fdm_layer_factors_are_the_data_sheets(key, quantity, want):
    f = pp.profile("fdm").material(key).factor(quantity)
    assert f.value == pytest.approx(want, abs=5e-5) and f.verified and f.flag == ""


def test_fdm_factors_sit_inside_the_profiles_range():
    """The per-material factors and the profile's own range rows (fdm-orientation-z-*-ratio-tds) agree for the
    families that range covers (PLA, PETG, ASA, CoPA)."""
    fdm = pp.profile("fdm")
    rng = {q: fdm.rule(f"fdm-orientation-z-{q}-ratio-tds").limit() for q in ("strength", "strain")}
    for m in fdm.materials.values():
        if m.family in ("pla", "petg", "asa", "pa"):
            for q, lim in rng.items():
                v = m.factor(q).value
                assert lim.min - 0.005 <= v <= lim.max + 0.005, (m.key, q, v)


def test_sheet_metal_profiles_read_the_shop_table():
    sheet = pp.profile("sheet-metal")
    assert set(sheet.materials) == {"5052", "mild-steel", "g90", "304", "316"}
    alu, steel = sheet.material("5052"), sheet.material("mild-steel")
    assert len(alu.stocks) == 4 and len(steel.stocks) == 6
    # SendCutSend's specs: ALU-063, 0.063 in 5052, R 0.035 in, K 0.42, flange 0.303 in, relief 0.118 in
    s = alu.stock(1.6)
    assert (s.sku, s.R, s.K, s.min_flange, s.relief_depth) == ("ALU-063", 0.889, 0.42, 7.696, 2.997)
    assert s.R == pytest.approx(round(0.035 * 25.4, 3)) and s.min_flange == pytest.approx(round(0.303 * 25.4, 3))
    assert steel.stock(1.88).sku == "CRS-074" and steel.stock(1.95) is None and alu.stock(2.0) is None
    assert alu.hardness == "soft" and steel.hardness == "medium"
    for m in (alu, steel):
        for rid in m.excludes:
            sheet.rule(rid)


def test_missing_data_says_where_it_should_be(tmp_path, monkeypatch):
    with pytest.raises(pp.ProfileDataError, match="process-profiles.yaml"):
        pp.load(tmp_path / "nope.yaml")
    monkeypatch.setenv(pp.ENV, str(tmp_path / "nope.yaml"))
    with pytest.raises(pp.ProfileDataError, match=pp.ENV):
        pp.load()


def test_an_unknown_process_material_or_rule_is_refused():
    with pytest.raises(pp.ProfileDataError, match="no process"):
        pp.profile("waterjet")
    with pytest.raises(pp.ProfileDataError, match="no material"):
        pp.profile("fdm").material("nylon-x")
    with pytest.raises(pp.ProfileDataError, match="no rule"):
        pp.profile("fdm").rule("fdm-nope")


def test_registry_ids_resolve_once_the_registry_is_beside_the_data(tmp_path):
    """The ids resolve through the docs/research/references.yaml (#118) beside the data file: a copy with none beside it
    loads but resolves nothing, and a registry put beside it is read with no code change."""
    data = tmp_path / "process-profiles.yaml"
    data.write_text((ROOT / "docs" / "research" / "process-profiles.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    assert not pp.load(data)["fdm"].source("bambu-petg-basic-tds").resolved
    (tmp_path / "references.yaml").write_text(yaml.safe_dump({"sources": [
        {"id": "bambu-petg-basic-tds", "title": "PETG Basic Technical Data Sheet", "org": "Bambu Lab",
         "url": "https://store.bblcdn.com/"}]}), encoding="utf-8")
    fdm = pp.load(data)["fdm"]
    assert fdm.source("bambu-petg-basic-tds").resolved and fdm.source("bambu-petg-basic-tds").org == "Bambu Lab"
    assert not fdm.source("bambu-asa-tds").resolved


def test_shop_rules_load_only_when_the_shop_is_asked_for():
    """SendCutSend's own limits (#283) stay out of the generic answers, so the rules remain supplier-neutral."""
    sheet = pp.profile("sheet-metal")
    generic = sheet.limits(compare="sm-clinch-to-bend", E=6.35, BA=2.45)
    assert [l.rule for l in generic] == ["sm-clinch-to-bend-pem"]
    shop = sheet.limits(compare="sm-clinch-to-bend", shop="sendcutsend", E=6.35, BA=2.45)
    got = {l.rule: l.min for l in shop}
    # Both on the bend centre line: SendCutSend's BA/2 + N, and PEM's C/L-to-edge from the bend's outside (+ BA/2)
    assert got == {"sm-clinch-to-bend-pem": pytest.approx(7.575), "sm-clinch-to-bend-sendcutsend": pytest.approx(7.575)}
    with pytest.raises(pp.ProfileDataError, match="no shop 'sendcutsnd'"):
        sheet.limits(compare="sm-clinch-to-bend", shop="sendcutsnd", E=6.35, BA=2.45)
    with pytest.raises(pp.ProfileDataError, match="no shop"):
        sheet.rules_for(shop="sendcutsnd")
    assert {r.id for r in sheet.rules_for(compare="sm-hole-min")} == {"sm-hole-min-protolabs", "sm-hole-min-davis"}
    assert "sm-hole-min-laser-sendcutsend" in {r.id for r in sheet.rules_for(compare="sm-hole-min", shop="*")}


def test_a_shop_carries_its_rules_and_tables():
    shop = pp.load().shop("sendcutsend")
    assert shop.name == "SendCutSend" and all(r.shop == "sendcutsend" for r in shop.rules) and len(shop.rules) >= 10
    assert set(shop.tables) == {"sendcutsend-5052-and-mild-steel", "sendcutsend-stainless-and-galvanised",
                                "sendcutsend-cut-and-hardware-limits"}
    # ALU-063 in its specs: hardware C/L to edge 0.382 in, to a bend line 0.425 in, between the same part 0.589 in
    row = shop.table("sendcutsend-cut-and-hardware-limits").row("ALU-063")
    assert (row["hw_cl_edge"], row["hw_cl_bend"], row["hw_cl_same"]) == (9.703, 10.795, 14.961)
    assert row["hb_min"] == 60 and "hardware" in row["services"]
    with pytest.raises(pp.ProfileDataError):
        pp.load().shop("protocase")
    with pytest.raises(pp.ProfileDataError):
        shop.table("sendcutsend-5052-and-mild-steel").row("ALU-999")


def test_only_bend_tables_become_stock(tmp_path):
    """The cutting and hardware table has no R or K, so it is not read as bend tooling; the stainless and galvanised
    rows are (their materials wait for SHEET_MATERIALS entries)."""
    sheet = pp.profile("sheet-metal")
    assert {s.sku for s in sheet.material("5052").stocks} == {"ALU-040", "ALU-063", "ALU-090", "ALU-125"}


def test_a_rule_naming_an_unlisted_shop_is_refused(tmp_path):
    raw = dict(RAW)
    raw["rules"] = RAW["rules"] + [dict(RAW["rules"][0], id="fdm-x-nowhere", shop="nowhere")]
    path = tmp_path / "process-profiles.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(pp.ProfileDataError, match="nowhere"):
        pp.load(path)


def test_sqrt_and_cos_take_one_argument_and_refuse_a_negative_root():
    """The hole rules (#323): the arc floor and the faceted circle, evaluated from the data file."""
    assert pp.evaluate("sqrt(D*D + track*track)", {"D": 3.0, "track": 4.0}) == 5.0
    assert pp.evaluate("D / cos(pi / facets)", {"D": 1.0, "facets": 3}) == pytest.approx(2.0)
    assert pp.names_in("sqrt(D*D + track*track)") == ("D", "track")
    for bad in ("sqrt(D - 5)", "sqrt(D, D)", "cos()"):
        with pytest.raises(ValueError):
            pp.evaluate(bad, {"D": 1.0})
