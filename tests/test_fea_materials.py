"""The FEA material table pinned to the data sheets it cites (#125).

Each sheet below is written out as read on 2026-10-31, with its edition and where it was read, independently of
``cadagent.simulation.fea``. A change to a value in ``MATERIALS`` fails here until the sheet is read again and this file
updated with it. Only the inputs are pinned: CAD and simulation do not prove that a part fits or holds.

The rules the printed rows follow:
* E is the lowest modulus any sheet read for the material gives in the row's print direction (tensile, ISO 527, or
  bending, ISO 178; every edition read), so that an isotropic study errs towards more deflection, not less;
* the strength is at or below the lowest tensile strength in that direction;
* the density is the sheet's;
* the humid PA6-CF rows are Bambu's dry sheet values x the wet / dry ratio of Polymaker's PA6-CF20 sheet (the modulus
  ratio on E, the strength ratio on the strength, per direction) x0.8 (print) (#157);
* the layer-check allowables (X-Y, Z) are the row's strength across the layers, and that times the lowest X-Y / Z
  tensile strength ratio of the editions read; the humid PA6-CF rows share one pair, their two strengths (#144).

The metals are pinned to MIL-HDBK-5J's design minimums (#157), the carbon tube as a typical value.
"""
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import pytest

from cadagent.simulation.fea import MATERIALS, Material, _isotropic_basis

ROOT = Path(__file__).resolve().parents[1]
BBL = "https://store.bblcdn.com/"
AX = "https://www.additive-x.com/shop/mpattachments/file/viewonline/id/{}/product_id/{}"


@dataclass(frozen=True)
class Sheet:
    """One edition of one data sheet: (X-Y, Z) values at 100 % infill. ``None`` where the sheet gives none."""
    edition: str
    read_at: str                          # where it was read on 2026-10-31
    tensile_mpa: Tuple[float, float]      # Young's modulus, ISO 527
    uts_mpa: Tuple[float, float]          # tensile strength, ISO 527
    density_g_cm3: float                  # ISO 1183
    bending_mpa: Optional[Tuple[float, float]] = None   # bending modulus, ISO 178
    annealed: bool = True                 # the sheet says its bars were annealed (and dried) before testing


@dataclass(frozen=True)
class Row:
    source: str                           # id in research/references.yaml (#118)
    edition_in_note: str                  # the edition the row says it uses
    direction: str                        # 'Z' or 'X-Y'
    sheets: Tuple[Sheet, ...]
    nu: float                             # not on any of these sheets: a typical value, pinned so it cannot drift
    E_mpa: float
    strength_mpa: float
    factor: float = 1.0                   # on E: humid x print for the PA6-CF rows
    strength_factor: float = 1.0          # on the strength: humid x print for the PA6-CF rows
    others: Dict[str, float] = field(default_factory=dict)   # other makers' sheets, for the record (not used)


PLA_V3 = Sheet("Bambu PLA Basic TDS V3.0",
               BBL + "s1/default/58b85d0f3db94878854a28fdb8a0006e/Bambu_PLA_Basic_Technical_Data_Sheet.pdf",
               (2580, 2060), (35, 31), 1.24, bending_mpa=(2750, 2370))
PLA_V2 = Sheet("Bambu PLA Basic TDS V2.0", AX.format(494, 2236), (2680, 2160), (39, 35), 1.24, bending_mpa=(2750, 2370))
PETG_V2 = Sheet("Bambu PETG Basic TDS V2.0", AX.format(580, 2330), (1460, 1120), (48, 39), 1.25,
                bending_mpa=(1790, 1580))
# V3.0 is a reformulated filament under the same name ("The all-new Bambu Lab PETG Basic ... The refined formula"),
# and its bars are not said to be annealed (it advises against annealing PETG Basic); V2.0's were, at 65 degC for 8 h
PETG_V3 = Sheet("Bambu PETG Basic TDS V3.0",
                BBL + "s1/default/cb94589bf7994fdcbfa833badefae9cd/Bambu_PETG_Basic_Technical_Data_Sheet.pdf",
                (2780, 2550), (51, 35), 1.25, bending_mpa=(1950, 1740), annealed=False)
PETGCF_V3 = Sheet("Bambu PETG-CF TDS V3.0", BBL + "626e4f424bf345ae965ad0ddfcaf2459.pdf", (2460, 1340), (35, 29), 1.25,
                  bending_mpa=(2910, 1560))
PETGCF_V2 = Sheet("Bambu PETG-CF TDS V2.0", AX.format(596, 2346), (2460, 1340), (59, 38), 1.25, bending_mpa=(2890, 1680))
PAHTCF_V3 = Sheet("Bambu PAHT-CF TDS V3.0 (dry)", BBL + "7166b20bc68f4c87b32c972b856eeb4b.pdf", (3860, 2180), (92, 47),
                  1.06, bending_mpa=(4230, 1820))
PA6CF_V3 = Sheet("Bambu PA6-CF TDS V3.0 (dry)", BBL + "b2abc59ac250492b979a52f1ce3e61b3.pdf", (4430, 2170), (102, 48),
                 1.09, bending_mpa=(5460, 2240))
TPU_V1 = Sheet("Bambu TPU 95A HF TDS V1.0", BBL + "58df32731eab4c90a7dac9b12e13ba88.pdf", (9.8, 7.4), (27.3, 22.3), 1.22)
# Polymaker Fiberon PA6-CF20 TDS V1.1 (PDF of 2024-12-08), p. 1: dry (annealed 100 degC / 16 h) and wet (then 48 h in
# water at 60 degC, 5.30 % moisture), (X-Y, Z). Not a row of its own: its wet / dry ratios make Bambu's PA6-CF humid.
PM_PA6CF20_DRY = Sheet("Polymaker Fiberon PA6-CF20 TDS V1.1 (dry)",
                       "https://cdn.shopify.com/s/files/1/0548/7299/7945/files/TDS_FIBERON_PA6-CF20_V1.1_EN.pdf",
                       (8636.5, 3759.5), (109.3, 54.0), 1.17, bending_mpa=(7037.6, 2975.3))
PM_PA6CF20_WET = Sheet("Polymaker Fiberon PA6-CF20 TDS V1.1 (wet)", PM_PA6CF20_DRY.read_at,
                       (2508.1, 1056.1), (54.7, 25.5), 1.17, bending_mpa=(2286.2, 801.1))
PRINT = 0.8


def humid(i: int, quantity: str) -> float:
    """Polymaker's wet / dry ratio for one axis (0 X-Y, 1 Z) of the tensile modulus or strength."""
    attr = {"E": "tensile_mpa", "strength": "uts_mpa"}[quantity]
    return getattr(PM_PA6CF20_WET, attr)[i] / getattr(PM_PA6CF20_DRY, attr)[i]



PRINTED: Dict[str, Row] = {
    "pla": Row("bambu-pla-basic-tds", "V3.0", "Z", (PLA_V3, PLA_V2), 0.35, 2060, 25),
    # Two formulations sold as one product, tested two ways (V2.0 annealed, V3.0 not said to be). A spool does not say
    # which it is, so the lower modulus of the two (V2.0's) is used; the #94 coupon should record its formulation.
    "petg": Row("bambu-petg-basic-tds", "V2.0", "Z", (PETG_V2, PETG_V3), 0.38, 1120, 20),
    "petg_cf": Row("bambu-petg-cf-tds", "V3.0", "Z", (PETGCF_V3, PETGCF_V2), 0.36, 1340, 22),
    # the Z bending modulus (1820) is below the Z tensile (2180) on this sheet only
    "pa_cf": Row("bambu-paht-cf-tds", "V3.0", "Z", (PAHTCF_V3,), 0.35, 1820, 40),
    "pa6_cf_xy": Row("bambu-pa6-cf-tds", "V3.0", "X-Y", (PA6CF_V3,), 0.35, 4430 * humid(0, "E") * PRINT,
                     102 * humid(0, "strength") * PRINT, factor=humid(0, "E") * PRINT,
                     strength_factor=humid(0, "strength") * PRINT),
    "pa6_cf_z": Row("bambu-pa6-cf-tds", "V3.0", "Z", (PA6CF_V3,), 0.35, 2170 * humid(1, "E") * PRINT,
                    48 * humid(1, "strength") * PRINT, factor=humid(1, "E") * PRINT,
                    strength_factor=humid(1, "strength") * PRINT),
    "tpu95": Row("bambu-tpu-95a-hf-tds", "V1.0", "Z", (TPU_V1,), 0.45, 7.4, 8,
                 others={"Polymaker PolyFlex TPU95 TDS V5.4, Young's modulus X-Y (ISO 37)": 33.6}),
}

# Metals (#157): MIL-HDBK-5J (31 January 2003), read on 2026-10-31 from
# https://everyspec.com/MIL-HDBK/MIL-HDBK-0001-0099/MIL_HDBK_5J_139/ . Design minimums in US units, as the handbook
# gives them: (table, page, E 10^3 ksi, mu, Fty ksi, the grain direction and basis of Fty, density lb/in3).
KSI, LB_IN3 = 6.894757, 27.679905
HANDBOOK = {
    # 6061-T6 sheet (A-basis Fty: 35 LT, 36 L) and T651 plate to 6.000 in (35 LT, A- then S-basis)
    "al6061": ("3.6.2.0(b1), (b2)", "3-264", 9.9, 0.33, 35, "LT, A/S", 0.098),
    # 7075-T6 sheet and T651 plate, 0.012-2.000 in: A-basis Fty (LT) 67, 68, 69, 67, 68, 67 by thickness band
    "al7075": ("3.7.6.0(b1)", "3-371", 10.3, 0.33, 67, "LT, A", 0.101),
    # AISI 1025 carbon steel, sheet, strip, plate, tubing and bar: S-basis
    "steel": ("2.2.1.0(b)", "2-8", 29.0, 0.32, 36, "L and LT, S", 0.284),
}
# The A-basis Fty (LT) of 7075-T651 plate by thickness band past 2.000 in: the row's note warns of these
THICK_7075 = {"2.001-2.500": 64, "2.501-3.000": 61, "3.001-3.500": 58, "3.501-4.000": 54}
# Common machining stock with lower minimums in the same handbook, which the notes name (A-basis Fty LT, ksi, by
# thickness band in inches): extruded 6061-T6/T6510/T6511 rod, bar and shapes, Table 3.6.2.0(g), p. 3-272; rolled or
# cold-finished 7075-T6/T651 bar and rod, Table 3.7.6.0(d), p. 3-380
EXTRUDED_6061 = ("3.6.2.0(g)", {"to 1.000": 33, "1.001-6.500": 28})
BAR_7075 = ("3.7.6.0(d)", {"to 2.000": 66, "2.001-3.000": 63, "3.001-4.000": 60})
# Protolabs' CNC material data sheets (2026, read 2026-10-31): 6061-T651/T6 typical yield 276 MPa (40 ksi),
# E 10.0 Msi, 2.70 Mg/m3; 7075 yield 434-476 MPa (T6 sheet) and 372-462 MPa (T651 plate to 101.6 mm) over thickness.
PROTOLABS = {"6061_typical_yield": 276, "6061_density": 2.70, "7075_sheet": (434, 476), "7075_plate": (372, 462)}
TYPICAL_BEFORE_157 = {"al6061": 276, "al7075": 503}
# Not from a sheet: a typical value, pinned so a change is deliberate. (E MPa, nu, strength MPa, density g/cm3)
TYPICAL = {"cf_tube": (64000, 0.3, 650, 1.55)}
OTHER = set(HANDBOOK) | set(TYPICAL)


def _axis(direction: str) -> int:
    return {"X-Y": 0, "Z": 1}[direction]


def test_every_material_is_pinned():
    assert set(MATERIALS) == set(PRINTED) | set(OTHER)


@pytest.mark.parametrize("key", sorted(PRINTED))
def test_printed_values_are_the_sheets(key):
    m, row = MATERIALS[key], PRINTED[key]
    assert m.source == row.source
    assert m.direction == row.direction
    assert row.edition_in_note in m.note
    assert m.E_mpa == pytest.approx(row.E_mpa, abs=1e-9)
    assert m.strength_mpa == pytest.approx(row.strength_mpa, abs=1e-9)
    assert m.nu == row.nu
    assert m.density_g_cm3 == row.sheets[0].density_g_cm3


@pytest.mark.parametrize("key", sorted(PRINTED))
def test_printed_modulus_is_the_lowest_any_sheet_gives_in_its_direction(key):
    m, row = MATERIALS[key], PRINTED[key]
    i = _axis(row.direction)
    moduli = [s.tensile_mpa[i] for s in row.sheets] + [s.bending_mpa[i] for s in row.sheets if s.bending_mpa]
    assert m.E_mpa == pytest.approx(min(moduli) * row.factor, abs=1e-9)
    # and never above the in-plane modulus (the stiffer direction) of any edition
    assert m.E_mpa <= min(s.tensile_mpa[0] for s in row.sheets) * row.factor


@pytest.mark.parametrize("key", sorted(PRINTED))
def test_printed_strength_is_at_or_below_the_sheets(key):
    m, row = MATERIALS[key], PRINTED[key]
    lowest = min(s.uts_mpa[_axis(row.direction)] for s in row.sheets) * row.strength_factor
    assert m.strength_mpa <= lowest + 1e-9


@pytest.mark.parametrize("key", sorted(PRINTED))
def test_layer_strengths_keep_the_rows_margin_in_both_directions(key):
    # Study.layer_check() defaults to these: bond against Z, von Mises against X-Y
    m, row = MATERIALS[key], PRINTED[key]
    xy, z = m.layer_strengths_mpa
    assert (xy, z)[_axis(row.direction)] == m.strength_mpa              # the row's own strength in its direction
    if key.startswith("pa6_cf"):
        assert (xy, z) == (MATERIALS["pa6_cf_xy"].strength_mpa, MATERIALS["pa6_cf_z"].strength_mpa)
        assert xy == pytest.approx(102 * humid(0, "strength") * PRINT) and z == pytest.approx(48 * humid(1, "strength") * PRINT)
    else:
        assert z == m.strength_mpa
        assert xy == pytest.approx(z * min(s.uts_mpa[0] / s.uts_mpa[1] for s in row.sheets), rel=1e-12)
    in_plane = PRINTED["pa6_cf_xy"].strength_factor if key.startswith("pa6_cf") else row.strength_factor
    assert z < xy <= min(s.uts_mpa[0] for s in row.sheets) * in_plane + 1e-9    # below the sheet in the layer plane


def test_isotropic_materials_have_no_layer_strengths():
    for key in OTHER:
        assert MATERIALS[key].layer_strengths_mpa is None, key


def test_the_default_printed_materials_are_for_the_weak_direction():
    # pa6_cf_xy is the one row for parts whose stress stays in the layers, and says so in its name
    for key, m in MATERIALS.items():
        if key in PRINTED and key != "pa6_cf_xy":
            assert m.direction == "Z", key
    assert "along the layers" in MATERIALS["pa6_cf_xy"].name


def test_the_moduli_reported_in_the_issue_are_gone():
    # #125: the values before the fix, all above the Z tensile modulus of the sheets they cited
    before = {"pla": 2700, "petg": 1800, "petg_cf": 2900, "pa_cf": 4500, "pa6_cf_xy": 3000, "pa6_cf_z": 2400,
              "tpu95": 30}
    for key, e in before.items():
        assert MATERIALS[key].E_mpa < e, key


@pytest.mark.parametrize("key", sorted(HANDBOOK))
def test_metals_are_the_handbook_minimums(key):
    m = MATERIALS[key]
    table, page, e_ksi, mu, fty, basis, rho = HANDBOOK[key]
    assert m.E_mpa == pytest.approx(e_ksi * 1e3 * KSI, abs=0.05)
    assert m.nu == mu
    assert m.strength_mpa == pytest.approx(fty * KSI, abs=0.05)
    assert m.source == "mil-hdbk-5j" and table in m.note and f"{fty} ksi" in m.note
    assert m.direction == ""
    if key != "al6061":                                   # 6061's density is Protolabs' 2.70 (the handbook: 2.71)
        assert m.density_g_cm3 == pytest.approx(rho * LB_IN3, abs=0.005)
    assert "minimum" in m.note and "typical" not in m.note.split(";")[0]


def test_6061_density_and_typical_yield_from_protolabs():
    m = MATERIALS["al6061"]
    assert m.density_g_cm3 == PROTOLABS["6061_density"]
    assert m.density_g_cm3 == pytest.approx(HANDBOOK["al6061"][-1] * LB_IN3, abs=0.015)
    assert f"typical yield is {PROTOLABS['6061_typical_yield']} MPa" in m.note


def test_metal_strengths_are_not_above_any_cited_minimum():
    # a safety factor against a typical value reads high (#157): 14 % for 6061, 9 % for 7075
    for key, typical in TYPICAL_BEFORE_157.items():
        assert MATERIALS[key].strength_mpa < typical
    assert TYPICAL_BEFORE_157["al6061"] / MATERIALS["al6061"].strength_mpa == pytest.approx(1.14, abs=0.005)
    assert TYPICAL_BEFORE_157["al7075"] / MATERIALS["al7075"].strength_mpa == pytest.approx(1.09, abs=0.005)
    # 7075: the thinnest plate band's minimum is the top of Protolabs' plate range; thicker plate is weaker, and the
    # note says so
    assert MATERIALS["al7075"].strength_mpa == pytest.approx(PROTOLABS["7075_plate"][1], abs=0.5)
    assert all(v < HANDBOOK["al7075"][4] for v in THICK_7075.values())
    assert f"{min(THICK_7075.values())} ksi" in MATERIALS["al7075"].note and "thicker plate is lower" in MATERIALS["al7075"].note


def test_metal_notes_name_the_weaker_stock_forms():
    # the solver knows neither the product form nor the grain direction, so the note says which stock is weaker
    for key, (table, bands) in (("al6061", EXTRUDED_6061), ("al7075", BAR_7075)):
        note = MATERIALS[key].note
        assert table in note, key
        assert all(v <= HANDBOOK[key][4] for v in bands.values()), key
        assert f"{max(bands.values())} ksi" in note and f"{min(bands.values())} ksi" in note, key
    assert "extruded rod, bar and shapes" in MATERIALS["al6061"].note
    assert "bar and rod" in MATERIALS["al7075"].note


def test_carbon_tube_is_labelled_typical():
    m = MATERIALS["cf_tube"]
    assert (m.E_mpa, m.nu, m.strength_mpa, m.density_g_cm3) == TYPICAL["cf_tube"]
    assert "typical" in m.note and "not a minimum" in m.note and m.direction == ""


def test_sources_are_in_the_reference_registry():
    """Every material's source is a read entry of the registry (#118), and the registry lists fea.py as relying on it."""
    from cadagent.review.references import load
    reg = load(ROOT / "research" / "references.yaml")
    for key, m in MATERIALS.items():
        if not m.source:
            assert "typical" in m.note, f"{key}: no source, and the note does not say its values are typical"
            continue
        ref = reg.resolve(m.source)
        assert ref.kind == "source", f"{key}: {m.source} is {ref.kind} in research/references.yaml, not a read source"
        assert "src/cadagent/simulation/fea.py" in ref["used_for"], m.source
    assert {r.source for r in PRINTED.values()} <= set(reg.entries)


@pytest.mark.parametrize("key", sorted(PRINTED))
def test_assumptions_say_which_modulus_and_strength(key):
    m = MATERIALS[key]
    line = _isotropic_basis(m)
    assert f"E {m.E_mpa:g} MPa" in line and f"strength {m.strength_mpa:g} MPa" in line
    assert m.note in line and "not isotropic" in line
    # the note itself must say what the modulus and the strength are taken from
    assert "modulus" in m.note and "strength" in m.note, key


def test_assumptions_name_the_print_direction_and_factors():
    assert "across the layers (Z)" in _isotropic_basis(MATERIALS["petg"])
    xy = _isotropic_basis(MATERIALS["pa6_cf_xy"])
    assert "in the layer plane (X-Y)" in xy and "x0.290 humid" in xy and "x0.500 humid" in xy and "x0.8 print" in xy
    assert f"E {MATERIALS['pa6_cf_xy'].E_mpa:g} MPa" in xy and "Polymaker PA6-CF20 V1.1 wet / dry" in xy
    z = _isotropic_basis(MATERIALS["pa6_cf_z"])
    assert "x0.281 humid" in z and "x0.472 humid" in z
    for key in ("pa6_cf_xy", "pa6_cf_z"):            # the factors the notes name are the ones applied, to 3 places
        i, row = _axis(PRINTED[key].direction), PRINTED[key]
        note = MATERIALS[key].note
        assert f"x{humid(i, 'E'):.3f} humid" in note and f"x{humid(i, 'strength'):.3f} humid" in note


def test_humid_pa6_cf_takes_the_saturated_modulus_ratio_not_a_strength_ratio():
    # #157: before, x0.6 (a strength-like ratio) on E made these rows about twice too stiff
    assert humid(0, "E") == pytest.approx(0.290, abs=5e-4) and humid(1, "E") == pytest.approx(0.281, abs=5e-4)
    assert humid(0, "strength") == pytest.approx(0.500, abs=5e-4) and humid(1, "strength") == pytest.approx(0.472, abs=5e-4)
    before = {"pa6_cf_xy": (4430 * 0.48, 102 * 0.48), "pa6_cf_z": (2170 * 0.48, 48 * 0.48)}
    for key, (e, s) in before.items():
        assert e / MATERIALS[key].E_mpa == pytest.approx(2.07 if key == "pa6_cf_xy" else 2.14, abs=0.01)
        assert MATERIALS[key].strength_mpa < s


def test_the_in_plane_recipe_keeps_the_assumptions_true():
    # the recipe in docs/toolkit.md and fea.py for a part whose bending stays in the layer plane
    import dataclasses
    m = dataclasses.replace(MATERIALS["petg_cf"], E_mpa=2460, direction="X-Y",
                            note="Bambu PETG-CF TDS V3.0: E is the X-Y tensile modulus; strength the Z allowable")
    line = _isotropic_basis(m)
    assert "E 2460 MPa, a modulus in the layer plane (X-Y)" in line
    assert "strength 22 MPa" in line and "strength the Z allowable" in line
    assert "Z tensile modulus" not in line
    recipe = "note='Bambu PETG-CF TDS V3.0: E is the X-Y tensile modulus; strength the Z allowable'"
    assert recipe in (ROOT / "docs" / "toolkit.md").read_text()
    assert recipe in Path(inspect.getsourcefile(Material)).read_text()          # fea.py, wherever it lives


def test_isotropic_materials_add_nothing_to_the_assumptions():
    assert _isotropic_basis(MATERIALS["steel"]) == ""
    assert _isotropic_basis(Material("steel", 200000, 0.3, 250, 7.85)) == ""   # the positional form still works


def test_topopt_default_modulus_is_pla_across_the_layers():
    from cadagent.simulation.topopt import TopOpt
    assert inspect.signature(TopOpt.__init__).parameters["E_mpa"].default == MATERIALS["pla"].E_mpa
