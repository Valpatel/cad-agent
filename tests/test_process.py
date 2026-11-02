"""cadagent.manufacturing.process: every profile loads, every value carries a source id that resolves (or is a
registry id waiting on #118), unverified rows say so, and the numbers are the cited sources' (#99)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from cadagent.manufacturing import process as pp
from cadagent.mechanical.compliant.allowables import PRINTED

ROOT = Path(__file__).resolve().parents[1]
RAW = yaml.safe_load((ROOT / "research" / "process-profiles.yaml").read_text(encoding="utf-8"))
# Registry ids (#118) the FDM data sheets cite; research/references.yaml is not on the branch yet, so they do not resolve.
PENDING_REGISTRY = {source for _, source in pp.FDM_MATERIALS.values()}


@pytest.fixture(scope="module")
def profiles():
    return pp.load()


def test_every_process_loads_with_its_rules(profiles):
    assert sorted(p.process for p in profiles) == sorted(RAW["processes"])
    assert sum(len(p.rules) for p in profiles) == len(RAW["rules"])
    for p in profiles:
        assert p.rules and p.title == RAW["processes"][p.process]
        assert all(r.process == p.process for r in p.rules)


def test_every_value_has_a_source_that_resolves(profiles):
    """Rules, shop rows, formulas and material factors: each names a source id, and the id is in the data file (or
    one of its datasets), or is a registry id that waits on #118."""
    for p in profiles:
        for r in p.rules:
            assert r.source and r.source in p.sources and p.sources[r.source].resolved, r.id
        for m in p.materials.values():
            if isinstance(m, pp.FdmMaterial):
                for q, f in m.factors.items():
                    assert f.source == m.source and f.citation.startswith(("Bambu Lab", "Polymaker")), (m.key, q)
                    assert "https://" in f.citation, (m.key, q)
                    assert p.source(f.source).resolved or f.source in PENDING_REGISTRY, (m.key, q)
            else:
                for s in m.stocks:
                    assert p.sources[s.source].resolved and p.sources[s.source].url.startswith("https://"), s.sku
        for f in p.formulas.values():
            assert p.sources[f["source"]].resolved, f["id"]


def test_every_rule_evaluates_with_its_variables(profiles):
    env = dict(T=1.5, R=1.5, wall=2.5, D=4.0, L=50.0, depth=12.0, width=6.0, H=8.0, nozzle=0.4, rib=1.5,
               texture=0.05, area=36.0)
    for r in profiles.rules():
        lim = r.limit(**{k: env[k] for k in r.variables})
        assert lim.rule == r.id and lim.source == r.source and lim.verified == r.verified
        assert any(v is not None for v in (lim.min, lim.max, lim.value))
        assert all(math.isfinite(v) for v in (lim.min, lim.max, lim.value) if v is not None)


def test_a_missing_variable_is_named():
    with pytest.raises(pp.ProfileDataError, match="give T"):
        pp.profile("sheet-metal").rule("sm-flange-min-protolabs").limit()


def test_unverified_rows_are_marked_and_refused_for_enforcement():
    sls = pp.profile("sls")
    u = sls.rule("sls-gap-vs-wall-eos")
    assert not u.verified and u.flag == "(u)"
    lim = u.limit()
    assert not lim.verified and lim.text.endswith("(u)") and lim.cite().endswith("(u)")
    assert [r.id for r in sls.unverified()] == ["sls-gap-vs-wall-eos"]
    with pytest.raises(pp.ProfileDataError, match=r"\(u\)"):
        sls.verified_rule("sls-gap-vs-wall-eos")
    ok = pp.profile("fdm").verified_rule("fdm-wall-min-hubs").limit()
    assert ok.verified and "(u)" not in ok.text
    assert {r.id for r in pp.load().rules() if not r.verified} == \
        {r["id"] for r in RAW["rules"] if r["status"] == "u"}


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
    assert set(sheet.materials) == {"5052", "mild-steel"}
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
    """When research/references.yaml (#118) sits beside the data file, the data-sheet ids resolve with no code change."""
    data = tmp_path / "process-profiles.yaml"
    data.write_text((ROOT / "research" / "process-profiles.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    assert not pp.load(data)["fdm"].source("bambu-petg-basic-tds").resolved
    (tmp_path / "references.yaml").write_text(yaml.safe_dump({"sources": [
        {"id": "bambu-petg-basic-tds", "title": "PETG Basic Technical Data Sheet", "org": "Bambu Lab",
         "url": "https://store.bblcdn.com/"}]}), encoding="utf-8")
    fdm = pp.load(data)["fdm"]
    assert fdm.source("bambu-petg-basic-tds").resolved and fdm.source("bambu-petg-basic-tds").org == "Bambu Lab"
    assert not fdm.source("bambu-asa-tds").resolved
