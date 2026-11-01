"""The FEA material table pinned to the data sheets it cites (#125).

Each sheet below is written out as read on 2026-10-31, with its edition and where it was read, independently of
``cadagent.simulation.fea``. A change to a value in ``MATERIALS`` fails here until the sheet is read again and this file
updated with it. Only the inputs are pinned: CAD and simulation do not prove that a part fits or holds.

The rules the printed rows follow:
* E is the lowest modulus any sheet read for the material gives in the row's print direction (tensile, ISO 527, or
  bending, ISO 178; every edition read), so that an isotropic study errs towards more deflection, not less;
* the strength is at or below the lowest tensile strength in that direction;
* the density is the sheet's;
* the humid PA6-CF rows are the dry sheet values x0.6 (moisture) x0.8 (print), on modulus and strength alike.
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
    factor: float = 1.0                   # x0.6 humid x0.8 print for the PA6-CF rows
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
HUMID_PRINT = 0.6 * 0.8

PRINTED: Dict[str, Row] = {
    "pla": Row("bambu-pla-basic-tds", "V3.0", "Z", (PLA_V3, PLA_V2), 0.35, 2060, 25),
    # Two formulations sold as one product, tested two ways (V2.0 annealed, V3.0 not said to be). A spool does not say
    # which it is, so the lower modulus of the two (V2.0's) is used; the #94 coupon should record its formulation.
    "petg": Row("bambu-petg-basic-tds", "V2.0", "Z", (PETG_V2, PETG_V3), 0.38, 1120, 20),
    "petg_cf": Row("bambu-petg-cf-tds", "V3.0", "Z", (PETGCF_V3, PETGCF_V2), 0.36, 1340, 22),
    # the Z bending modulus (1820) is below the Z tensile (2180) on this sheet only
    "pa_cf": Row("bambu-paht-cf-tds", "V3.0", "Z", (PAHTCF_V3,), 0.35, 1820, 40),
    "pa6_cf_xy": Row("bambu-pa6-cf-tds", "V3.0", "X-Y", (PA6CF_V3,), 0.35, 4430 * HUMID_PRINT, 102 * HUMID_PRINT,
                     factor=HUMID_PRINT),
    "pa6_cf_z": Row("bambu-pa6-cf-tds", "V3.0", "Z", (PA6CF_V3,), 0.35, 2170 * HUMID_PRINT, 48 * HUMID_PRINT,
                    factor=HUMID_PRINT),
    "tpu95": Row("bambu-tpu-95a-hf-tds", "V1.0", "Z", (TPU_V1,), 0.45, 7.4, 8,
                 others={"Polymaker PolyFlex TPU95 TDS V5.4, Young's modulus X-Y (ISO 37)": 33.6}),
}

# Not tied to a sheet in the reference registry: typical handbook values, pinned so a change is deliberate.
# Protolabs' CNC material data sheet for aluminium 6061-T651/T6 (2026, read 2026-10-31) gives yield 276 MPa,
# E 10.0 Msi and 2.70 g/cm3. Its 7075-T651/T6 sheet gives only specification ranges (yield 434-476 MPa for T6 sheet,
# 372-462 MPa for T651 plate), below the typical 503 MPa used: a follow-up, not part of #125.
# (E MPa, nu, strength MPa, density g/cm3)
OTHER = {
    "al6061": (68900, 0.33, 276, 2.70),
    "al7075": (71700, 0.33, 503, 2.81),
    "steel": (200000, 0.29, 250, 7.85),
    "cf_tube": (64000, 0.3, 650, 1.55),
}


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
    lowest = min(s.uts_mpa[_axis(row.direction)] for s in row.sheets) * row.factor
    assert m.strength_mpa <= lowest + 1e-9


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


@pytest.mark.parametrize("key", sorted(OTHER))
def test_other_materials_are_pinned(key):
    m = MATERIALS[key]
    assert (m.E_mpa, m.nu, m.strength_mpa, m.density_g_cm3) == OTHER[key]
    assert m.direction == ""


def test_al6061_matches_the_protolabs_sheet():
    m = MATERIALS["al6061"]
    assert m.E_mpa == pytest.approx(10.0e6 * 6.894757e-3, rel=1e-3)     # 10.0 Msi
    assert m.strength_mpa == 276 and m.density_g_cm3 == 2.70


def test_sources_are_in_the_reference_registry():
    """Once the registry (#118, PR #119) is on this branch, every printed source must be an id in it."""
    yaml = pytest.importorskip("yaml")
    reg = ROOT / "research" / "references.yaml"
    if not reg.exists():
        pytest.skip("research/references.yaml is not on this branch yet (#119)")
    data = yaml.safe_load(reg.read_text())
    ids = set()

    def walk(x):
        if isinstance(x, dict):
            if "id" in x:
                ids.add(x["id"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    missing = sorted({r.source for r in PRINTED.values()} - ids)
    assert not missing, f"sources missing from research/references.yaml: {missing}"


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
    assert "in the layer plane (X-Y)" in xy and "x0.48" in xy and "E 2126.4 MPa" in xy and "strength 48.96 MPa" in xy
    assert "twice too stiff" in xy                    # the humid E rests on a strength ratio, and says so
    assert "x0.48" in _isotropic_basis(MATERIALS["pa6_cf_z"])


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
