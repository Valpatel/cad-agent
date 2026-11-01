"""The printed snap-fit allowables pinned to the data-sheet editions they cite (#156).

Each sheet below is written out as read on 2026-10-31, with its maker, edition, PDF date, page and link, independently
of ``cadagent.mechanical.compliant.allowables``. A change to a value there fails here until the sheet is read again and
this file updated with it. The rule (lowest allowable; mating force from the highest modulus and retention from the
lowest, across the editions read) is checked on these transcriptions, so a wrong edition choice fails too. Only the
inputs are pinned: a printed coupon (#94) is what proves an allowable, not a data sheet.
"""
import re
from pathlib import Path

import pytest

from cadagent.mechanical.compliant import allowables as al

ROOT = Path(__file__).resolve().parents[1]
BBL = "https://store.bblcdn.com/"
AX = "https://www.additive-x.com/shop/mpattachments/file/viewonline/id/{}/product_id/{}"
PM = "https://cdn.shopify.com/s/files/1/0548/7299/7945/files/"

# (maker, edition, PDF date, page, url, E XY/Z MPa, UTS XY/Z MPa, elongation at break XY/Z %), current edition first
SHEETS = {
    "pla-bambu-basic": [
        ("Bambu Lab", "V3.0", "2025-04-25", "p. 2",
         BBL + "s1/default/58b85d0f3db94878854a28fdb8a0006e/Bambu_PLA_Basic_Technical_Data_Sheet.pdf",
         (2580, 2060), (35, 31), (12.2, 7.5)),
        ("Bambu Lab", "V2.0", "2023-03-11", "p. 2", AX.format(494, 2236), (2680, 2160), (39, 35), (12.2, 7.5))],
    "pla-bambu-matte": [
        ("Bambu Lab", "V3.0", "2025-04-25", "p. 2",
         BBL + "s7/default/5b061f2feeac4ba88f355a33248bbda7/Bambu_PLA_Matte_Technical_Data_Sheet.pdf",
         (1960, 1670), (30, 22), (14.8, 4.8)),
        ("Bambu Lab", "V2.0", "2023-05-10", "p. 2", AX.format(513, 2261), (1960, 1670), (32, 25), (32.8, 4.8))],
    "pla-polymaker": [
        ("Polymaker", "V5.4", "2024-04-29", "p. 4", PM + "PolyLite_PLA_TDS_EN_V5.4.pdf",
         (3426.9, 3064.9), (52.3, 40.5), (6.3, 1.8))],
    # two filaments sold as one product: V3.0 is "The all-new Bambu Lab PETG Basic ... The refined formula"
    "petg-bambu-basic": [
        ("Bambu Lab", "V3.0", "2026-01-25", "p. 2",
         BBL + "s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf",
         (2780, 2550), (51, 35), (9.5, 5.2)),
        ("Bambu Lab", "V2.0", "2023-06-26", "p. 2", AX.format(580, 2330), (1460, 1120), (48, 39), (11.2, 5.7))],
    "petg-bambu-hf": [
        ("Bambu Lab", "V1.0", "2024-07-18", "p. 2", BBL + "3a230e260a3a47c2b0db0156e07eef91.pdf",
         (1810, 1540), (34, 23), (8.6, 5.1))],
    "petg-cf-bambu": [
        ("Bambu Lab", "V3.0", "2023-08-29", "p. 2", BBL + "626e4f424bf345ae965ad0ddfcaf2459.pdf",
         (2460, 1340), (35, 29), (10.4, 4.7)),
        ("Bambu Lab", "V2.0", "2023-03-11", "p. 2", AX.format(596, 2346), (2460, 1340), (59, 38), (10.4, 4.7))],
    "petg-polymaker": [
        ("Polymaker", "V5.4", "2024-04-22", "p. 4", PM + "PolyLite_PETG_TDS_EN_V5.4.pdf",
         (2116.8, 1898.7), (50.8, 42.8), (8.4, 3.3))],
    "asa-bambu": [
        ("Bambu Lab", "V3.0", "2023-09-19", "p. 2", BBL + "ad7b08230c164e72856cffbe06bb7dc9.pdf",
         (2450, 2120), (37, 31), (9.2, 4.6)),
        ("Bambu Lab", "V2.0", "2023-07-26", "p. 2", AX.format(612, 2399), (2450, 2120), (52, 35), (9.2, 4.6))],
    "asa-polymaker": [   # V6.0 now served at the V5.4 address, with V5.4's mechanical values
        ("Polymaker", "V6.0", "2025-12-02", "p. 1", PM + "PolyLite_ASA_TDS_EN_V5.4.pdf",
         (2379, 1965), (43.8, 32), (6.7, 1.65))],
    "copa-polymaker-dry": [
        ("Polymaker", "V5.4", "2024-04-14", "p. 4", PM + "PolyMide_CoPA_TDS_V5.4.pdf",
         (2703, 2209), (78.0, 45.8), (12.7, 1.3))],
    "copa-polymaker-wet": [
        ("Polymaker", "V5.4", "2024-04-14", "p. 4", PM + "PolyMide_CoPA_TDS_V5.4.pdf",
         (724, 660), (34.3, 13.7), (13.2, 1.7))],
    "pa6-cf20-polymaker-dry": [
        ("Polymaker", "V1.1", "2024-12-08", "p. 1", PM + "TDS_FIBERON_PA6-CF20_V1.1_EN.pdf",
         (8636.5, 3759.5), (109.3, 54.0), (2.1, 1.9))],
    "pa6-cf20-polymaker-wet": [
        ("Polymaker", "V1.1", "2024-12-08", "p. 1", PM + "TDS_FIBERON_PA6-CF20_V1.1_EN.pdf",
         (2508.1, 1056.1), (54.7, 25.5), (7.0, 6.7))],
}
CAP = {"copa-polymaker-dry": 0.04, "copa-polymaker-wet": 0.06, "pa6-cf20-polymaker-dry": 0.008,
       "pa6-cf20-polymaker-wet": 0.015}


def _rule(e, uts, brk, axis):
    return min(0.7 * uts[axis] / e[axis], 0.5 * brk[axis] / 100)


def test_every_entry_is_pinned():
    assert set(al.PRINTED) == set(SHEETS)


@pytest.mark.parametrize("key", sorted(SHEETS))
def test_each_sheet_is_the_one_read(key):
    sheets = al.PRINTED[key].sheets
    assert len(sheets) == len(SHEETS[key])
    for s, (maker, edition, date, page, url, e, uts, brk) in zip(sheets, SHEETS[key]):
        assert (s.maker, s.edition, s.date, s.url, s.e_mpa, s.uts_mpa, s.break_pct) == \
            (maker, edition, date, url, e, uts, brk)
        assert s.where.startswith(page)
        assert s.edition in s.citation and s.url in s.citation and date in s.citation
        assert s.url in al.PRINTED[key].source


@pytest.mark.parametrize("key", sorted(SHEETS))
def test_allowable_is_the_lowest_and_the_force_moduli_the_cautious_edition(key):
    m, read = al.PRINTED[key], SHEETS[key]
    cap = CAP.get(key, 1.0)
    along = min(min(_rule(e, uts, brk, 0) for *_, e, uts, brk in read), cap)
    across = min(min(min(_rule(e, uts, brk, 0), _rule(e, uts, brk, 1)) for *_, e, uts, brk in read), cap)
    assert m.allowable("along") == pytest.approx(along, rel=1e-12)
    assert m.allowable("across") == pytest.approx(across, rel=1e-12)
    # mating force from the highest modulus, retention force from the lowest: each the cautious side
    assert m.secant_upper_bound("along") == max(e[0] for *_, e, _u, _b in read)
    assert m.secant_upper_bound("across") == max(e[1] for *_, e, _u, _b in read)
    assert m.retention_modulus("along") == min(e[0] for *_, e, _u, _b in read)
    assert m.retention_modulus("across") == min(e[1] for *_, e, _u, _b in read)


def test_the_current_maker_sheet_comes_first():
    # Bambu serves V3.0 for these from its store; the V2.0 copies are a reseller's and come second
    for key in ("pla-bambu-basic", "pla-bambu-matte", "petg-bambu-basic", "petg-cf-bambu", "asa-bambu"):
        first, *rest = al.PRINTED[key].sheets
        assert first.edition == "V3.0" and first.url.startswith(BBL), key
        assert [s.edition for s in rest] == ["V2.0"] and rest[0].url.startswith(AX.split("/shop")[0]), key
    for key, m in al.PRINTED.items():
        assert m.sheets[0].url.startswith((BBL, PM)), key


def test_the_sizes_worked_out_in_the_issue():
    # #156's comment: PETG-CF 1.68 % -> 1.00 %; PETG Basic 2.30 % -> 1.28 % along, 0.96 % across; PLA 1.02 % -> 0.95 %
    assert al.PRINTED["petg-cf-bambu"].allowable("along") == pytest.approx(0.0100, abs=5e-5)
    assert al.PRINTED["petg-cf-bambu"].allowable("across") == pytest.approx(0.0100, abs=5e-5)
    assert al.PRINTED["petg-bambu-basic"].allowable("along") == pytest.approx(0.0128, abs=5e-5)
    assert al.PRINTED["petg-bambu-basic"].allowable("across") == pytest.approx(0.0096, abs=5e-5)
    assert al.PRINTED["pla-bambu-basic"].allowable("along") == pytest.approx(0.0095, abs=5e-5)
    # and the V2.0 values they replace, from the V2.0 sheets alone
    v2 = lambda key: al.PrintedMaterial("v2", (al.PRINTED[key].sheets[1],))
    assert v2("petg-cf-bambu").allowable("across") == pytest.approx(0.0168, abs=5e-5)
    assert v2("petg-bambu-basic").allowable("across") == pytest.approx(0.0230, abs=5e-5)
    assert v2("pla-bambu-basic").allowable("across") == pytest.approx(0.0102, abs=5e-5)


def test_derivation_names_the_edition_behind_each_number():
    d = al.PRINTED["pla-bambu-basic"].derivation("across")
    assert d["xy"]["sheet"].endswith("V3.0") and d["z"]["sheet"].endswith("V3.0")
    # V2.0's modulus is higher: the mating-force bound; V3.0's is lower: the retention force
    assert d["modulus"]["mating"] == {"mpa": 2160, "sheet": "Bambu Lab PLA Basic Technical Data Sheet V2.0"}
    assert d["modulus"]["retention"] == {"mpa": 2060, "sheet": "Bambu Lab PLA Basic Technical Data Sheet V3.0"}
    assert d["editions"] == ["Bambu Lab PLA Basic Technical Data Sheet V3.0",
                             "Bambu Lab PLA Basic Technical Data Sheet V2.0"]
    petg = al.PRINTED["petg-bambu-basic"].derivation("along")
    assert petg["modulus"] == {"mating": {"mpa": 2780, "sheet": "Bambu Lab PETG Basic Technical Data Sheet V3.0"},
                               "retention": {"mpa": 1460, "sheet": "Bambu Lab PETG Basic Technical Data Sheet V2.0"}}
    assert "reformulated" in petg["note"] and "#94" in petg["note"]
    assert al.PRINTED["petg-bambu-basic"].sheets[0].formulation.startswith("the reformulated filament")


def test_mating_force_takes_the_stiffest_edition_and_retention_the_softest():
    # PR #197 review: a PETG Basic clip whose retention fails with the V2.0 filament must not pass on V3.0's modulus.
    # 14 mm arm, 6 x 1.2 mm, 0.5 mm undercut, along the layers: P = b h^2 E eps / (6 l) at the root strain.
    from cadagent.mechanical.compliant import snapfit as sf
    spec = {"name": "clip", "material": "petg-bambu-basic", "orientation": "along", "length_mm": 14,
            "undercut_mm": 0.5, "section": {"rect": {"width_mm": 6, "thickness_mm": 1.2}}, "friction": 0.4,
            "lead_deg": 30, "return_deg": 45, "root_radius_mm": 0.8, "min_retention_n": 2.5, "max_mating_n": 10}
    r = sf.check_spec_entry(spec)
    eps = 1.2 * 0.5 / (0.67 * 14 ** 2)                       # Bayer Table 1, design 1, as printed: y = 0.67 eps l^2 / h
    force = lambda e: 6 * 1.2 ** 2 * e * eps / (6 * 14)
    assert r["deflection_force_n"] == pytest.approx(force(2780), rel=1e-9)            # V3.0: mating
    assert r["retention_deflection_force_n"] == pytest.approx(force(1460), rel=1e-9)  # V2.0: retention
    assert r["separation_force_n"] == pytest.approx(sf.mating_force(force(1460), 0.4, 45), rel=1e-9)
    assert r["mating_force_n"] == pytest.approx(sf.mating_force(force(2780), 0.4, 30), rel=1e-9)
    row = {x["check"]: x for x in r["rows"]}
    assert r["separation_force_n"] == pytest.approx(1.6, abs=0.05) and not row["retention force"]["pass"]
    assert "lowest edition" in row["retention force"]["detail"]
    assert "highest edition" in row["mating force"]["detail"]
    assert r["material"]["secant_mpa"] == 2780 and r["material"]["retention_secant_mpa"] == 1460
    # a modulus the caller gives is used for both
    given = sf.check_spec_entry(dict(spec, secant_mpa=2000))
    assert given["material"]["retention_secant_mpa"] == 2000 and "retention_deflection_force_n" not in given
    # one edition: one modulus, as before
    one = sf.check_spec_entry(dict(spec, material="petg-polymaker"))
    assert one["material"]["secant_mpa"] == one["material"]["retention_secant_mpa"]
    assert "retention_deflection_force_n" not in one


def test_a_material_needs_a_sheet():
    with pytest.raises(ValueError, match="Sheet"):
        al.PrintedMaterial("x", ())


def _research_rows(heading):
    md = (ROOT / "research" / "compliant-mechanisms.md").read_text()
    lines = md[md.index(heading):].splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("|"))
    rows = lines[first + 2:next(i for i in range(first, len(lines)) if not lines[i].startswith("|"))]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows]


def _pair(cell):
    return tuple(float(x) for x in cell.split("/"))


@pytest.mark.parametrize("key", sorted(SHEETS))
def test_research_table_has_each_current_sheet(key):
    # research/compliant-mechanisms.md section 5 has a row for every current edition and for every sheet that is a
    # formulation of its own (both PETG Basic filaments); the other earlier editions are in its "Earlier editions"
    # paragraph, each value that differs from the current sheet under that filament's name
    md = (ROOT / "research" / "compliant-mechanisms.md").read_text()
    rows = _research_rows("## 5. FDM anisotropy")
    earlier = md[md.index("**Earlier editions.**"):].split("\n\n")[0].replace("\n", " ").split(";")
    current, *older = al.PRINTED[key].sheets

    def same(row, s):
        try:
            e, uts, brk = _pair(row[1]), _pair(row[2]), _pair(row[3])
        except ValueError:
            return False
        return (all(abs(a - b) <= 0.5 for a, b in zip(e, s.e_mpa)) and uts == s.uts_mpa and brk == s.break_pct)
    for s in [current] + [s for s in older if s.formulation]:
        match = [r for r in rows if same(r, s)]
        assert len(match) == 1, f"{key} {s.edition}: no single §5 row with {s.e_mpa}, {s.uts_mpa}, {s.break_pct}"
        name, cite = match[0][0], match[0][6]
        assert cite.startswith("[BBL-" if s.maker == "Bambu Lab" else "[PM-"), key
        if s.maker == "Bambu Lab":
            assert s.edition in name, key                     # the table says which edition each Bambu row is
    for s in (s for s in older if not s.formulation):
        filament = s.title.replace(" Technical Data Sheet", "")
        segment = next((x for x in earlier if f"{filament} " in x), "")
        assert segment, f"{key} {s.edition}: no {filament} in the Earlier editions paragraph"
        for new, old in ((current.e_mpa, s.e_mpa), (current.uts_mpa, s.uts_mpa), (current.break_pct, s.break_pct)):
            if new != old:
                assert f"{old[0]:g} / {old[1]:g}" in segment, f"{key} {s.edition}: {old} not under {filament}"


def test_research_allowable_table_follows_the_code():
    # section 6: the Bambu rows that changed in #156, to the table's rounding
    rows = {r[0]: r for r in _research_rows("## 6. Printed allowable strain")}
    expect = {"PLA Basic (Bambu V3.0": "pla-bambu-basic", "PLA Matte (Bambu V3.0": "pla-bambu-matte",
              "PETG Basic (Bambu V3.0": "petg-bambu-basic", "PETG-CF (Bambu V3.0": "petg-cf-bambu",
              "ASA (Bambu V3.0": "asa-bambu"}
    for prefix, key in expect.items():
        row = next(r for name, r in rows.items() if name.startswith(prefix))
        xy, z = (float(re.match(r"([\d.]+)", c).group(1)) / 100 for c in row[1:3])
        m = al.PRINTED[key]
        assert m.allowable("along") == pytest.approx(xy, abs=0.0006), key
        assert m.allowable("across") == pytest.approx(z, abs=0.0006), key
