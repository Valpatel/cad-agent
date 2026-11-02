"""cadagent.formulas.rivets against published values: MIL-HDBK-5J's tables and the worked examples of Abbud's
lecture notes on riveted joints [ref:mil-hdbk-5j] [ref:abbud-riveted-joints]."""
import math

import pytest

from cadagent import formulas as fx

IN, LBF, PSI = 0.0254, 4.4482216152605, 6894.757293168


def test_single_shear_of_a_5056_rivet_matches_mil_hdbk_5j_table_8_1_2b():
    # Table 8.1.2(b): 5056 rivet (B), Fsu 28 ksi, 1/8 in (hole 0.1285 in): 363 lb, as the table rounds it.
    p = fx.rivet_shear_force(0.1285 * IN, 28_000 * PSI)
    assert p / LBF == pytest.approx(363, abs=0.5)
    assert fx.rivet_shear_force(0.1285 * IN, 28_000 * PSI, rivets=3, planes=2) == pytest.approx(6 * p, rel=1e-12)


def test_unit_bearing_matches_mil_hdbk_5j_table_8_1_2_1a():
    # Table 8.1.2.1(a), Fbr 100 ksi: 1/8 in rivet, t 0.040 in -> 514 lb; t 0.063 -> 810 lb; 3/16 in (0.191), t 0.063 -> 1203 lb.
    assert fx.bearing_force(0.1285 * IN, 0.040 * IN, 100_000 * PSI) / LBF == pytest.approx(514, abs=0.5)
    assert fx.bearing_force(0.1285 * IN, 0.063 * IN, 100_000 * PSI) / LBF == pytest.approx(810, abs=0.5)
    assert fx.bearing_force(0.191 * IN, 0.063 * IN, 100_000 * PSI) / LBF == pytest.approx(1203, abs=0.5)


MM, MPA = 1e-3, 1e6


def test_abbud_problem_2_single_riveted_lap():
    # t 6 mm, d 20 mm, p 50 mm; sigma_t 120, tau 90, sigma_c 180 MPa: Pt 21 600, Ps 28 278, Pc 21 600, P 36 000 N, 60 %.
    j = fx.lap_joint(20 * MM, 6 * MM, 50 * MM, 120 * MPA, 90 * MPA, 180 * MPA)
    assert j["tearing_n"] == pytest.approx(21_600, rel=1e-12)
    assert j["bearing_n"] == pytest.approx(21_600, rel=1e-12)
    # The notes take the rivet's area as 314.2 mm^2 (pi / 4 x 20^2 = 314.16), hence 28 278 rather than 28 274.
    assert j["shear_n"] == pytest.approx(28_278, rel=2e-4)
    assert j["solid_n"] == pytest.approx(36_000, rel=1e-12)
    assert j["strength_n"] == pytest.approx(21_600, rel=1e-12)
    assert j["efficiency"] == pytest.approx(0.60, rel=1e-12)


def test_abbud_problem_2_double_riveted_lap():
    # Two rivets per pitch, p 65 mm: Pt 32 400, Ps 56 556, Pc 43 200, P 46 800 N; tearing governs; 69.2 %.
    j = fx.lap_joint(20 * MM, 6 * MM, 65 * MM, 120 * MPA, 90 * MPA, 180 * MPA, rivets=2)
    assert (j["tearing_n"], j["bearing_n"], j["solid_n"]) == pytest.approx((32_400, 43_200, 46_800), rel=1e-12)
    assert j["shear_n"] == pytest.approx(56_556, rel=2e-4)
    assert j["mode"] == "tearing"
    assert j["efficiency"] == pytest.approx(0.692, abs=5e-4)


def test_a_bought_rivets_rating_replaces_its_alloys_shear():
    j = fx.lap_joint(3.264 * MM, 1.6 * MM, 9.525 * MM, 214 * MPA, None, 448 * MPA, rivet_shear=689.5)
    assert j["shear_n"] == 689.5 and j["mode"] == "shear"
    assert j["efficiency"] == pytest.approx(689.5 / (9.525 * MM * 1.6 * MM * 214 * MPA), rel=1e-12)
    with pytest.raises(ValueError, match="shear_strength"):
        fx.lap_joint(3.264 * MM, 1.6 * MM, 9.525 * MM, 214 * MPA, None, 448 * MPA)


@pytest.mark.parametrize("call", [
    lambda: fx.tearing_force(3 * MM, 3 * MM, 1 * MM, 1e8),           # pitch no larger than the hole
    lambda: fx.rivet_shear_force(-1, 1e8),
    lambda: fx.rivet_shear_force(1e-3, 1e8, rivets=0),
    lambda: fx.rivet_shear_force(1e-3, 1e8, planes=True),
    lambda: fx.bearing_force(1e-3, math.nan, 1e8),
    lambda: fx.solid_sheet_force(1e-3, 1e-3, math.inf),
])
def test_bad_inputs_are_refused(call):
    with pytest.raises(ValueError):
        call()
