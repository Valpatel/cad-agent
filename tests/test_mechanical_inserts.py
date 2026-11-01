"""cadagent.mechanical.inserts: the insert data and their sources, the hole and boss rules, the calibration against
published tests, and the joint check (#230)."""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

from cadagent import formulas as fx
from cadagent.mechanical import inserts as I

ROOT = Path(__file__).resolve().parents[1]
MM = 1e-3


# ----------------------------------------------------------------------------- the data and where it came from

def test_every_insert_names_its_source_and_the_day_it_was_read():
    for key, ins in I.INSERTS.items():
        assert ins.key == key and ins.thread.startswith("M") and ins.hole_mm and ins.length_mm > 0
        assert re.search(r"20\d\d-\d\d-\d\d", ins.source), key
        assert "McMaster-Carr" in ins.source or "bd_warehouse" in ins.source, key
    # the rows McMaster would not show this session are named, not guessed
    assert "M2.5" in I.MISSING and "M6" in I.MISSING and "93365A" in I.MISSING
    assert not any(i.thread in ("M2.5", "M6") for i in I.INSERTS.values())


def test_every_rule_names_a_document_with_a_date_or_an_edition():
    for key, ref in I.SRC.items():
        assert re.search(r"\b(19|20)\d\d\b|\d\d/\d\d", ref), key
    # each fitted test points at one of them
    for t in I.TESTS:
        assert any(t.source.startswith(ref[:40]) for ref in I.SRC.values()), t.key


def test_unknown_inserts_materials_and_axes_are_refused():
    with pytest.raises(ValueError):
        I.insert("mcmaster-94459A999")
    with pytest.raises(ValueError):
        I.family("pla-unknown")
    with pytest.raises(ValueError):
        I.hole_design(I.insert("mcmaster-94459A140"), axis="sideways")
    with pytest.raises(ValueError):
        I.capacity(I.insert("mcmaster-94459A140"), "pla-bambu-basic", axis="diagonal")


# ----------------------------------------------------------------------------- the hole and the boss

def test_hole_is_the_makers_plus_the_printed_allowance_and_deep_enough():
    h = I.hole_design(I.insert("mcmaster-94459A140"))
    # McMaster 4.0 mm + 0.2 mm (CNC Kitchen 2026); deepest of 6.5 (McMaster), 5.7 + 1 (ruthex), 5.7 + 2 x 0.5 (SPIROL)
    assert h["diameter_mm"] == 4.2 and h["depth_mm"] == pytest.approx(6.7)
    assert h["depth_rules_mm"] == {"maker's least material thickness": 6.5, "L + 1 mm (ruthex, CNC Kitchen)": 6.7,
                                   "L + 2 pitches (SPIROL)": 6.7}
    assert h["taper_deg"] == 0.0 and h["taper_max_deg"] == 1.0 and h["chamfer"] == "none"
    # golden: 42.13 - pi/4 (4.0^2 - 2.35^2) 5.7 = -4.775 mm^3 (room in the knurl's valleys); pocket pi/4 4^2 1.0
    assert h["displaced_mm3"] == pytest.approx(-4.775, abs=1e-3)
    assert h["overflow_mm3"] == pytest.approx(math.pi * 4.0, abs=1e-3)
    m8 = I.hole_design(I.insert("mcmaster-94459A778"))
    assert m8["depth_mm"] == pytest.approx(12.7 + 2 * 1.25)              # SPIROL's two pitches win at M8
    assert "displaced_mm3" not in m8                                      # no maker CAD measured: not guessed
    assert I.hole_design(I.insert("mcmaster-94459A140"), through=True)["depth_mm"] == 5.7
    assert any("teardrop" in w for w in I.hole_design(I.insert("mcmaster-94459A140"), "lying")["why"])


def test_boss_follows_the_makers_walls_and_knurl_multiples():
    b = I.boss_design(I.insert("mcmaster-94459A140"))
    # least: max(4.0 + 2 x 1.6, 1.5 x 4.72) = 7.2; full: 2 x 4.72 = 9.44
    assert b["least_outside_mm"] == pytest.approx(7.2) and b["outside_mm"] == pytest.approx(9.44)
    assert b["perimeters"] >= 3                                            # at least the metric size (SPIROL)
    m8 = I.boss_design(I.insert("mcmaster-94459A778"))
    assert m8["least_outside_mm"] == pytest.approx(9.6 + 2 * 4.5)
    assert "not read" in m8["knurl_basis"]


# ----------------------------------------------------------------------------- the calibration

def test_calibration_reproduces_the_published_tests():
    cal = I.calibration()
    rows = {r["key"]: r for r in cal["rows"]}
    area = math.pi * 4.6 * 5.7                                             # mm^2, ruthex / CNC Kitchen M3 x 5.7
    # Laszlo 2026, 1.28 mm wall, cross-zag: 1353.6 N -> q = 16.43 MPa; PolyLite PLA's tau 40.5 / 2 -> c = 0.8115
    assert rows["laszlo-2026-1.28-cross-zag"]["q_mpa"] == pytest.approx(1353.6 / area, abs=1e-3)
    assert rows["laszlo-2026-1.28-cross-zag"]["c"] == pytest.approx(0.8115, abs=1e-4)
    # SPIROL 04/26, Figure 10 (read off the bars): INS 19 long M6 (8.76 x 12.70 mm) in printed PLA, 4380 N ->
    # q = 12.53 MPa, c = 0.619, the lowest; CNC Kitchen 2019 the highest. PETG: SPIROL's INS 19, 3790 N -> 0.507
    m6 = math.pi * 8.76 * 12.70
    assert rows["spirol-3dp-pla-ins19"]["c"] == pytest.approx(0.6189, abs=1e-4)
    assert cal["pull"]["pla"]["low"] == pytest.approx(4380.0 / m6 / 20.25, rel=1e-9)
    assert cal["pull"]["pla"]["high"] == pytest.approx(181 * 9.80665 / area / 20.25, rel=1e-9)   # CNC Kitchen 2019
    assert cal["pull"]["petg"]["low"] == pytest.approx(3790.0 / m6 / 21.4, rel=1e-9)            # 0.507
    assert rows["cnck-2020"]["c"] == pytest.approx(119 * 9.80665 / area / 21.4, abs=1e-4)       # 0.662
    assert cal["pull"]["pla"]["cells"] == 13 and cal["pull"]["petg"]["cells"] == 3
    assert cal["pull"]["pooled"]["low"] == cal["pull"]["petg"]["low"]
    # the printed PC and glass-filled PA6 have no sheet in the table: they give r, not c
    assert "c" not in rows["spirol-3dp-pa6-gf30-ins19"] and "spirol-3dp-pc-ins19" not in cal["pull"]["pooled"]["tests"]
    # torque over pull, r = 2 T / (F D): CNC Kitchen 2020 PETG 2 x 3 / (1167 N x 4.6 mm) = 1.118; SPIROL's printed
    # 30 % glass-filled PA6, INS 19 long M6, 2 x 17.3 / (6020 N x 8.76 mm) = 0.656 is the lowest; PEM M8 in ABS 1.410
    # the highest; the 2019 bound (the screw broke first) is shown only
    assert cal["torque_ratio"]["printed"][0] == pytest.approx(1.1177, abs=1e-4)
    assert cal["torque_ratio"]["low"] == pytest.approx(2 * 17.3 * 1e3 / (6020.0 * 8.76), rel=1e-9)
    assert cal["torque_ratio"]["high"] == pytest.approx(2 * 26.0 * 1e3 / (3566.0 * 10.34), rel=1e-9)
    # SPIROL's nylon table is read in its primary units: 325 lb and 28 in-lb for the M3 INS 19 long
    assert rows["spirol-ins19-m3"]["pull_n"] == pytest.approx(1445.7, abs=0.1)
    assert rows["spirol-ins19-m3"]["torque_nm"] == pytest.approx(3.164, abs=1e-3)
    assert "cnck-2019" not in cal["torque_ratio"]["tests"] and rows["cnck-2019"]["torque_at_least"]
    # the moulded tests carry no c: no printed datasheet applies to them
    assert all("c" not in r for r in cal["rows"] if not r["printed"])


def test_capacity_is_the_shear_model_with_the_fitted_band():
    ins = I.insert("mcmaster-94459A140")
    cap = I.capacity(ins, "pla-bambu-basic")
    c = I.calibration()["pull"]["pla"]
    tau = 0.5 * 31e6                                                       # Bambu PLA Basic, across the layers
    assert cap["shear_strength_pa"] == tau
    assert cap["pull_out"]["low"] == pytest.approx(c["low"] * tau * math.pi * 4.72e-3 * 5.7e-3, rel=1e-12)
    assert cap["pull_out"]["low"] == pytest.approx(810.8, abs=0.1)         # golden: 0.6189 x 15.5 x pi 4.72 x 5.7
    r = I.calibration()["torque_ratio"]
    assert cap["torque_out"]["low"] == pytest.approx(
        fx.insert_shear_torque(4.72e-3, 5.7e-3, tau, c["low"] * r["low"]), rel=1e-12)
    assert cap["pull_out"]["low"] < cap["pull_out"]["mid"] < cap["pull_out"]["high"]
    assert cap["aged_share"] == (0.26, 0.55)
    # every published PLA result lies at or above the model's low end for its own stand-in material
    for t in I.TESTS:
        if t.family == "pla" and t.printed:
            low = fx.insert_shear_force(t.outer_mm * MM, t.length_mm * MM, I.shear_strength(t.stand_in), c["low"])
            assert t.pull_n >= low * (1 - 1e-9), t.key
    # a family with no printed test takes the lowest fit and says so
    asa = I.capacity(ins, "asa-bambu")
    assert asa["calibrated_on"] == "pooled" and asa["c"]["low"] == I.calibration()["pull"]["petg"]["low"]


def test_install_notes_cover_every_family():
    for key in I.PRINTED:
        n = I.install_notes(key)
        assert "degC" in n["temperature"] and "flush" in n["how"]


# ----------------------------------------------------------------------------- the joint check

def _rows(r):
    return {c["check"]: c for c in r["checks"]}


def test_a_flush_insert_with_a_washer_passes_at_the_torque_it_recommends():
    r = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, head_mm=7.0, clearance_mm=3.4,
                      clamped={"thickness_mm": 4.0})
    rows = _rows(r)
    assert r["clamp"]["path"] == "through-insert"
    assert {k: v["verdict"] for k, v in rows.items() if k != "preload kept"} == {
        "hole diameter": "pass", "hole depth": "pass", "melt volume": "pass", "boss wall": "pass",
        "clamp path": "pass", "tightening torque": "pass", "insert thread": "pass", "head bearing": "pass",
        "insert face": "pass"}
    # the plastic under the washer caps the preload at 78.06 MPa / 2 on pi/4 (7^2 - 3.4^2); the insert's end, round
    # the same hole, at brass's 124 MPa, is lower and sets the torque at the least nut factor
    area = math.pi / 4 * (7.0 ** 2 - 3.4 ** 2) * MM ** 2
    ring = math.pi / 4 * (I.INSERTS["mcmaster-94459A140"].outer_mm ** 2 - 3.4 ** 2) * MM ** 2
    k_lo = r["torque"]["nut_factor"]["low"]
    assert r["torque"]["preload_caps_n"]["head_bearing"] == pytest.approx(78.06e6 / 2 * area, rel=1e-9)
    assert r["torque"]["governed_by"] == "insert_face"
    assert r["torque"]["allowed_nm"] == pytest.approx(k_lo * 3e-3 * 124e6 * ring, rel=1e-9)
    assert rows["head bearing"]["value"] < 78.06 / 2 and rows["insert face"]["value"] == pytest.approx(124.0, abs=0.1)
    # without a limiter the plastic in the clamp relaxes: a warning, with the measured figures in it
    assert rows["preload kept"]["verdict"] == "warn" and "Amza" in rows["preload kept"]["detail"]
    assert r["verdict"] == "warn"


def test_a_recessed_insert_jacks_out_and_its_torque_falls_accordingly():
    flush = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, clamped={"material": "metal"})
    sunk = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, recess_mm=0.05,
                         clamped={"material": "metal"})
    assert flush["clamp"]["path"] == "through-insert" and sunk["clamp"]["path"] == "jack-out"
    assert sunk["torque"]["governed_by"] == "jack_out"
    assert sunk["torque"]["allowed_nm"] < flush["torque"]["allowed_nm"] / 3
    assert _rows(sunk)["clamp path"]["verdict"] == "warn" and "flush" in _rows(sunk)["clamp path"]["detail"]
    # proud by up to 0.13 mm still counts as flush; more warns
    assert _rows(I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, recess_mm=-0.1,
                               clamped={"material": "metal"}))["clamp path"]["verdict"] == "pass"
    assert _rows(I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, recess_mm=-0.3,
                               clamped={"material": "metal"}))["clamp path"]["verdict"] == "warn"


def test_overtightening_warns_inside_the_margin_and_fails_past_it():
    base = dict(insert="mcmaster-94459A775", material="pla-bambu-basic", boss_outside_mm=15.0,
                clamped={"material": "metal"})
    allowed = I.check_joint(**base)["torque"]["allowed_nm"]
    assert _rows(I.check_joint(**base, torque_nm=allowed))["tightening torque"]["verdict"] == "pass"
    assert _rows(I.check_joint(**base, torque_nm=1.5 * allowed))["tightening torque"]["verdict"] == "warn"
    assert _rows(I.check_joint(**base, torque_nm=2.5 * allowed))["tightening torque"]["verdict"] == "fail"
    assert I.check_joint(**base, torque_nm=2.5 * allowed)["verdict"] == "fail"


def test_thin_bosses_lying_inserts_and_uncalibrated_families_are_flagged():
    thin = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=7.0, clamped={"material": "metal"})
    assert _rows(thin)["boss wall"]["verdict"] == "fail" and thin["verdict"] == "fail"
    mid = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=8.0, clamped={"material": "metal"})
    assert _rows(mid)["boss wall"]["verdict"] == "warn"
    edge = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=12.0, edge_mm=1.0,
                         clamped={"material": "metal"})
    assert _rows(edge)["boss wall"]["verdict"] == "fail"                    # the least plastic to a free face
    lying = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", "lying", boss_outside_mm=9.5,
                          clamped={"material": "metal"})
    assert _rows(lying)["insert axis"]["verdict"] == "warn"
    asa = I.check_joint("mcmaster-94459A140", "asa-bambu", boss_outside_mm=9.5, clamped={"material": "metal"})
    assert _rows(asa)["calibration"]["verdict"] == "warn"
    nolen = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", clamped={"material": "metal"})
    assert _rows(nolen)["boss wall"]["verdict"] == "warn"                   # not given: say so, never assume it


def test_service_loads_are_held_to_the_low_end_over_the_margin():
    base = dict(insert="mcmaster-94459A140", material="pla-bambu-basic", boss_outside_mm=9.5,
                clamped={"material": "metal"})
    low = I.capacity(I.insert("mcmaster-94459A140"), "pla-bambu-basic")
    ok = I.check_joint(**base, pull_n=0.4 * low["pull_out"]["low"], turn_nm=0.4 * low["torque_out"]["low"])
    assert _rows(ok)["pull-out"]["verdict"] == "pass" and _rows(ok)["torque-out"]["verdict"] == "pass"
    near = I.check_joint(**base, pull_n=0.8 * low["pull_out"]["low"], push_n=0.8 * low["push_out"]["low"])
    assert _rows(near)["pull-out"]["verdict"] == "warn" and _rows(near)["push-out"]["verdict"] == "warn"
    over = I.check_joint(**base, pull_n=1.2 * low["pull_out"]["low"])
    assert _rows(over)["pull-out"]["verdict"] == "fail"


def test_a_far_side_insert_bears_on_its_shoulder():
    r = I.check_joint("mcmaster-94459A775", "pla-bambu-basic", installed_from="far side", recess_mm=3.0,
                      boss_outside_mm=15.0, clamped={"material": "metal"})
    assert r["clamp"]["path"] == "seat" and r["torque"]["governed_by"] == "shoulder"
    # the shoulder is the same plastic sheared on the knurl's cylinder, at the family's low c (0.6189)
    plug = fx.insert_shear_force(7.11e-3, 3e-3, 15.5e6, I.calibration()["pull"]["pla"]["low"])
    assert plug == pytest.approx(1038.6 * 0.6189, abs=0.1)                 # pi 7.11 x 3 mm x 15.5 MPa x c
    assert r["torque"]["preload_caps_n"]["shoulder"] == pytest.approx(plug / 2)
    assert _rows(r)["shoulder"]["verdict"] == "pass"


def test_a_limiter_is_checked_against_the_makers_rules():
    base = dict(insert="mcmaster-94459A775", material="petg-bambu-basic", boss_outside_mm=15.0,
                limiter_key="spirol-cl6000-m5")
    r = I.check_joint(**base, clamped={"thickness_mm": 6.1, "tolerance_mm": 0.05, "outside_mm": 18.0},
                      limiter_length_mm=6.0)
    rows = _rows(r)
    # the limiter abuts the insert: its end on the ring from its 6.15 mm bore to the insert's 7.11 mm knurl
    face = math.pi / 4 * (7.11 ** 2 - 6.15 ** 2)
    assert r["torque"]["governed_by"] == "insert_face"
    assert r["torque"]["preload_caps_n"]["insert_face"] == pytest.approx(124e6 * face * MM ** 2, rel=1e-9)
    assert rows["insert face"]["verdict"] == "pass" and rows["head over limiter"]["verdict"] == "pass"
    assert rows["limiter rating"]["verdict"] == "pass" and rows["limiter boss"]["verdict"] == "pass"
    # the stack: 6.1 +/- 0.05 plastic, 6.0 +0/-0.15 limiter -> squeezed (6.15 - 5.85) / 6.15 = 4.9 %, under 5 % but past
    # the printed plastic's strength over its modulus: it yields
    assert rows["limiter length"]["verdict"] == "warn" and "4.9 %" in rows["limiter length"]["detail"]
    # and the insert's face caps the preload below what it takes to squeeze the plastic: the limiter never seats
    assert rows["seating force"]["verdict"] == "fail" and "never reaches" in rows["seating force"]["detail"]
    proud = I.check_joint(**base, clamped={"thickness_mm": 6.0, "tolerance_mm": 0.05}, limiter_length_mm=6.0)
    assert "proud" in _rows(proud)["limiter length"]["detail"]
    with pytest.raises(ValueError):
        I.check_joint(**base)                                               # no plastic thickness to check against
    with pytest.raises(ValueError):
        I.check_joint(**{**base, "limiter_key": "spirol-cl6000-m3"}, clamped={"thickness_mm": 6.0})


def test_a_limiter_in_a_recessed_insert_fails_to_abut_it():
    r = I.check_joint("mcmaster-94459A775", "pla-bambu-basic", boss_outside_mm=15.0, recess_mm=0.5,
                      limiter_key="spirol-cl8000-m5", clamped={"thickness_mm": 5.1, "tolerance_mm": 0.05},
                      limiter_length_mm=5.0)
    assert _rows(r)["limiter on insert"]["verdict"] == "fail"


def test_the_screw_tip_bottoming_in_a_blind_hole_fails():
    base = dict(insert="mcmaster-94459A775", material="petg-bambu-basic", boss_outside_mm=15.0, hole_depth_mm=9.5,
                clamped={"material": "metal"})
    tip = {d: _rows(I.check_joint(**base, screw_depth_mm=d))["screw tip"] for d in (7.0, 9.0, 11.5)}
    assert [tip[d]["verdict"] for d in (7.0, 9.0, 11.5)] == ["pass", "warn", "fail"]
    assert "2.00 mm past the hole's floor" in tip[11.5]["detail"] and "jacks the insert out" in tip[11.5]["detail"]
    assert "7.00 of the insert's 7.9 mm" in tip[7.0]["detail"]
    through = I.check_joint(**{**base, "through": True}, screw_depth_mm=20.0)
    assert _rows(through)["screw tip"]["verdict"] == "pass"
    # a hole no deeper than the insert cannot seat it
    assert _rows(I.check_joint(**{**base, "hole_depth_mm": 7.9}))["hole depth"]["verdict"] == "fail"
    with pytest.raises(ValueError):
        I.check_joint(**base, screw_depth_mm=0.0)


def test_the_inserts_own_thread_caps_the_torque_over_the_length_engaged():
    r = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, clamped={"material": "metal"},
                      screw_depth_mm=3.0)
    # the ISO 68 internal area over 3 mm of M3, at brass's softest shear yield (0.577 x 124 MPa), over the margin
    strip = 0.875 * math.pi * 3.0 * 3.0 * MM ** 2 * 0.577 * 124e6
    assert _rows(r)["insert thread"]["limit"] == pytest.approx(strip / 2, abs=0.1)
    assert r["torque"]["preload_caps_n"]["insert_thread"] == pytest.approx(strip / 2, rel=1e-9)
    assert r["torque"]["governed_by"] == "insert_thread"
    assert r["torque"]["allowed_nm"] == pytest.approx(r["torque"]["nut_factor"]["low"] * 3e-3 * strip / 2, rel=1e-9)
    # all of the thread engaged when the tip is not given: more thread, a higher ceiling
    full = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", boss_outside_mm=9.5, clamped={"material": "metal"})
    assert full["torque"]["preload_caps_n"]["insert_thread"] == pytest.approx(strip / 2 * 5.7 / 3.0, rel=1e-9)


def test_a_clamped_hole_as_wide_as_the_insert_jacks_it_out():
    narrow = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", clamped={"material": "metal"}, clearance_mm=3.4)
    wide = I.check_joint("mcmaster-94459A140", "pla-bambu-basic", clamped={"material": "metal"}, clearance_mm=5.0)
    assert narrow["clamp"]["path"] == "through-insert" and wide["clamp"]["path"] == "jack-out"
    assert "as wide as the insert" in wide["clamp"]["why"]
    assert wide["torque"]["allowed_nm"] < narrow["torque"]["allowed_nm"] / 2


# ----------------------------------------------------------------------------- a screw into metal, plastic clamped

def test_check_clamp_holds_the_plastic_under_the_head_to_its_bearing_strength():
    r = I.check_clamp("M4", "pa6-cf20-polymaker-wet", 15.6, head_mm=7.0, clearance_mm=4.5)
    rows = _rows(r)
    area = math.pi / 4 * (7.0 ** 2 - 4.5 ** 2) * MM ** 2
    k_lo = fx.nut_factor(4e-3, 0.7e-3, 0.08, 0.20)
    strength = I.bearing_strength("pa6-cf20-polymaker-wet")
    assert r["torque"]["governed_by"] == "head_bearing"
    assert r["torque"]["allowed_nm"] == pytest.approx(k_lo * 4e-3 * strength / 2 * area, rel=1e-9)
    assert rows["head bearing"]["verdict"] == "pass"
    assert rows["head bearing"]["value"] == pytest.approx(strength / 2e6, abs=0.01)
    assert rows["preload kept"]["verdict"] == "warn"
    over = I.check_clamp("M6", "pa6-cf20-polymaker-wet", 26.0, head_mm=10.0, clearance_mm=6.6, torque_nm=8.0)
    assert over["verdict"] == "fail" and _rows(over)["head bearing"]["verdict"] == "fail"


def test_check_clamp_takes_your_own_limiter_and_the_cone_sets_its_seating_force():
    base = dict(thread="M10", material="pa6-cf20-polymaker-wet", thickness_mm=40.0, tolerance_mm=0.1, head_mm=20.0,
                clearance_mm=12.0, torque_nm=20.0, limiter={"outside_mm": 18.0, "bore_mm": 12.0})
    flush = _rows(I.check_clamp(**base, limiter_length_mm=40.0))
    assert flush["limiter length"]["verdict"] == "warn" and "proud" in flush["limiter length"]["detail"]
    assert flush["limiter wall"]["verdict"] == "warn"                      # no yield given: reported, not judged
    sunk = I.check_clamp(**base, limiter_length_mm=39.8)
    rows = _rows(sunk)
    # 40.1 mm of plastic at most, the sleeve 39.8 +0/-0.05: the head squeezes the plastic 0.35 mm before it lands
    E = I.PRINTED["pa6-cf20-polymaker-wet"].secant_upper_bound("across") * 1e6
    cone = fx.frustum_stiffness(E, 40.1 * MM, 20.0 * MM, 18.0 * MM)      # one cone: the far face on metal
    column = E * math.pi / 4 * (20.0 ** 2 - 18.0 ** 2) * MM ** 2 / (40.1 * MM)
    assert cone > 4 * column                                              # a narrow ring on thick plastic
    assert rows["seating force"]["value"] == pytest.approx(cone * 0.35 * MM, abs=0.05)
    assert rows["seating force"]["verdict"] == "warn" and "MPa" in rows["seating force"]["detail"]
    strong = _rows(I.check_clamp(**{**base, "limiter": {"outside_mm": 18.0, "bore_mm": 12.0, "yield_pa": 640e6}},
                                 limiter_length_mm=39.8))
    assert strong["limiter wall"]["verdict"] == "pass"
    for bad in (dict(thread="M7"), dict(thread="5"), dict(thickness_mm=0.05), dict(limiter_key="spirol-cl6000-m5"),
                dict(limiter={"outside_mm": 12.0, "bore_mm": 12.0}), dict(limiter={"outside_mm": 18.0,
                                                                                    "bore_mm": 12.0,
                                                                                    "material": "titanium"})):
        with pytest.raises(ValueError):
            I.check_clamp(**{**base, **bad})


def test_check_spec_runs_insert_and_clamp_joints_together():
    spec = {"defaults": {"material": "pla-bambu-basic", "boss_outside_mm": 9.5},
            "joints": [{"name": "a", "insert": "mcmaster-94459A140", "clamped": {"material": "metal"}},
                       {"name": "b", "thread": "M5", "thickness_mm": 5.0}]}
    r = I.check_spec(spec)
    assert [j["name"] for j in r["joints"]] == ["a", "b"] and r["joints"][1]["thread"] == "M5"
    for joint in ({"insert": "mcmaster-94459A140", "thread": "M3", "material": "pla-bambu-basic"},
                  {"material": "pla-bambu-basic"}, {"thread": "M5", "thickness_mm": 5.0, "insert_axis": 1}):
        with pytest.raises(ValueError):
            I.check_spec({"defaults": {"material": "pla-bambu-basic"}, "joints": [joint]})


def test_the_check_refuses_what_it_cannot_judge():
    for bad in (dict(insert="nope"), dict(material="steel"), dict(axis="sideways"), dict(screw_class="14.9"),
                dict(pull_n=-1.0), dict(torque_nm=0.0), dict(margin=0.5), dict(recess_mm=math.nan),
                dict(installed_from="far side")):
        with pytest.raises(ValueError):
            I.check_joint(**{"insert": "mcmaster-94459A140", "material": "pla-bambu-basic", **bad})


def test_check_spec_runs_every_joint_with_its_defaults():
    spec = {"defaults": {"material": "pla-bambu-basic", "clamped": {"material": "metal"}},
            "joints": [{"name": "a", "insert": "mcmaster-94459A140", "boss_outside_mm": 9.5},
                       {"name": "b", "insert": "mcmaster-94459A775", "boss_outside_mm": 7.0}]}
    r = I.check_spec(spec)
    assert [j["name"] for j in r["joints"]] == ["a", "b"] and r["verdict"] == "fail"
    json.dumps(r, allow_nan=False, default=str)
    for bad in ({}, {"joints": []}, {"joints": [1]}, {"joints": [{"insert": "mcmaster-94459A140",
                                                                  "material": "pla-bambu-basic", "colour": 1}]}):
        with pytest.raises(ValueError):
            I.check_spec(bad)


def test_every_insert_and_material_checks_without_error():
    for key in I.INSERTS:
        for mat in I.PRINTED:
            for axis in I.AXES:
                r = I.check_joint(key, mat, axis, boss_outside_mm=I.boss_design(I.insert(key))["outside_mm"],
                                  clamped={"material": "metal"})
                assert r["verdict"] in ("pass", "warn", "fail")
                assert r["torque"]["allowed_nm"] > 0 and r["capacity"]["pull_out"]["low"] > 0


def test_cli_checks_a_spec_file_and_exits_1_only_on_a_fail(tmp_path):
    spec = tmp_path / "joints.yaml"
    spec.write_text("defaults: {material: pla-bambu-basic, clamped: {material: metal}}\n"
                    "joints:\n  - {name: lid, insert: mcmaster-94459A140, boss_outside_mm: 9.5}\n")
    out = tmp_path / "out.json"
    run = [sys.executable, "-m", "cadagent.cli", "inserts", str(spec), "--output", str(out)]
    env = {"PYTHONPATH": str(ROOT / "src")}
    import os
    r = subprocess.run(run, capture_output=True, text=True, env={**os.environ, **env})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "lid" in r.stdout and json.loads(out.read_text())["joints"][0]["name"] == "lid"
    spec.write_text("joints:\n  - {insert: mcmaster-94459A140, material: pla-bambu-basic, boss_outside_mm: 6,"
                    " clamped: {material: metal}}\n")
    assert subprocess.run(run, capture_output=True, text=True, env={**os.environ, **env}).returncode == 1
    spec.write_text("joints:\n  - {name: hub, thread: M5, material: pla-bambu-basic, thickness_mm: 5}\n")
    r = subprocess.run(run, capture_output=True, text=True, env={**os.environ, **env})
    assert r.returncode == 0 and "M5 clamping" in r.stdout, r.stdout + r.stderr
    spec.write_text("joints: []\n")
    assert subprocess.run(run, capture_output=True, text=True, env={**os.environ, **env}).returncode == 2


# every row the preload loads must pass at the torque the check recommends: each one is a torque ceiling

LOADED = ("tightening torque", "insert thread", "pull-out", "shoulder", "head bearing", "insert face", "limiter end",
          "limiter rating", "limiter wall")


def _loaded_rows_pass(r):
    bad = {c["check"]: (c["verdict"], c["detail"][:120]) for c in r["checks"]
           if c["check"] in LOADED and c["verdict"] != "pass" and c["value"] is not None}     # not "not checked"
    assert not bad, (r["name"], r["torque"]["governed_by"], bad)


@pytest.mark.parametrize("key", sorted(I.INSERTS))
@pytest.mark.parametrize("material", ["pla-bambu-basic", "petg-bambu-basic", "copa-polymaker-wet"])
def test_the_recommended_torque_passes_every_row_it_loads_into_an_insert(key, material):
    ins = I.insert(key)
    lim = I.limiter_for(ins)
    cap = I.capacity(ins, material)
    pull = 0.3 * cap["pull_out"]["low"] / I.MARGIN
    # a separating load the 2 mm shoulder in front of a far-side insert can carry on its own
    plug = fx.insert_shear_force(I._knurl(ins)[0] * MM, 2.0 * MM, cap["shear_strength_pa"], cap["c"]["low"])
    joints = [dict(clamped={"material": "metal"}), dict(clamped={"thickness_mm": 4.0}),
              dict(recess_mm=0.2, clamped={"material": "metal"}, pull_n=pull),
              dict(installed_from="far side", recess_mm=2.0, clamped={"material": "metal"},
                   pull_n=0.3 * plug / I.MARGIN),
              dict(clamped={"material": "metal"}, pull_n=pull, screw_class="8.8")]
    if lim:
        joints += [dict(limiter_key=lim["key"], limiter_length_mm=5.0, clamped={"thickness_mm": 5.0}, pull_n=pull),
                   dict(limiter_key=lim["key"].replace("cl6000", "cl8000"), limiter_length_mm=5.0,
                        clamped={"thickness_mm": 5.0}, installed_from="far side", recess_mm=2.0)]
    for j in joints:
        _loaded_rows_pass(I.check_joint(key, material, boss_outside_mm=4 * ins.diameter_mm + 4, **j))


@pytest.mark.parametrize("thread", ["M3", "M4", "M5", "M6", "M8"])
@pytest.mark.parametrize("screw_class", ["8.8", "10.9", "12.9"])
def test_the_recommended_torque_passes_every_row_it_loads_clamping_plastic(thread, screw_class):
    d = float(thread[1:])
    for lim in ({}, {"limiter_key": f"spirol-cl6000-{thread.lower()}"}, {"limiter_key": f"spirol-cl8000-{thread.lower()}"},
                {"limiter": {"outside_mm": 2.0 * d, "bore_mm": d + 0.4, "yield_pa": 300e6}}):
        r = I.check_clamp(thread, "petg-bambu-basic", 6.0, head_mm=2.0 * d + 2.0, clearance_mm=d + 0.5,
                          screw_class=screw_class, limiter_length_mm=6.0 if lim else None, **lim)
        _loaded_rows_pass(r)
        assert r["torque"]["preload_caps_n"]["screw"] == pytest.approx(0.75 * r["proof_load_n"])


def test_a_catalogue_limiter_caps_the_preload_at_its_rating():
    # SPIROL rates CL6000 for class 10.9: at most 75 % of a 10.9 screw's proof load, whatever class goes through it
    r = I.check_clamp("M5", "petg-polymaker", 5.0, tolerance_mm=0.05, outside_mm=18.0,
                      limiter_key="spirol-cl6000-m5", limiter_length_mm=5.0)
    rated = 0.75 * fx.proof_load(5e-3, 0.8e-3, 830e6)
    assert r["torque"]["governed_by"] == "limiter_rating"
    assert r["torque"]["preload_caps_n"]["limiter_rating"] == pytest.approx(rated, rel=1e-12)
    assert _rows(r)["limiter rating"]["verdict"] == "pass"


def test_a_far_side_insert_has_no_floor_in_front_of_the_screw_and_its_limiter_lands_on_plastic():
    base = dict(insert="mcmaster-94459A775", material="pla-bambu-basic", installed_from="far side", recess_mm=3.0,
                boss_outside_mm=15.0)
    tip = _rows(I.check_joint(**base, clamped={"material": "metal"}, screw_depth_mm=8.0))["screw tip"]
    assert tip["verdict"] == "pass" and "far side" in tip["detail"]
    r = I.check_joint(**base, limiter_key="spirol-cl6000-m5", limiter_length_mm=5.0, clamped={"thickness_mm": 5.0})
    rows = _rows(r)
    assert "limiter on insert" not in rows and "insert face" not in rows
    assert rows["limiter end"]["verdict"] == "pass" and "limiter_end" in r["torque"]["preload_caps_n"]
    # the limiter's whole end lands on the shoulder: its body round the wider of its bore and the shoulder's hole
    lim = I.limiter("spirol-cl6000-m5")
    end = math.pi / 4 * (lim.body_mm ** 2 - max(lim.bore_mm, 5.5) ** 2) * MM ** 2
    assert r["torque"]["preload_caps_n"]["limiter_end"] == pytest.approx(I.bearing_strength("pla-bambu-basic") / 2
                                                                         * end, rel=1e-9)
    # the shoulder's plastic stays in the clamp path, so the joint relaxes as one with no limiter
    assert rows["preload kept"]["verdict"] == "warn" and "shoulder" in rows["preload kept"]["detail"]


def test_the_hole_band_is_the_makers_plus_the_printed_allowance():
    base = dict(insert="mcmaster-94459A140", material="pla-bambu-basic", boss_outside_mm=9.5,
                clamped={"material": "metal"})
    assert _rows(I.check_joint(**base, hole_mm=4.25))["hole diameter"]["verdict"] == "pass"
    at_maker = _rows(I.check_joint(**base, hole_mm=4.0))["hole diameter"]
    assert at_maker["verdict"] == "warn" and "0.25 mm small" in at_maker["detail"]
    assert at_maker["limit"] == [4.2, 4.3]


def test_the_squeeze_counts_the_limiters_own_deflection_and_states_assumed_tolerances():
    r = I.check_clamp("M5", "petg-bambu-basic", 6.2, outside_mm=18.0, limiter_key="spirol-cl6000-m5",
                      limiter_length_mm=6.0)
    detail = _rows(r)["limiter length"]["detail"]
    assert "um included" in detail and "assumed, with no source" in detail
    lim = I.limiter("spirol-cl6000-m5")
    d_c = r["torque"]["preload_n"]["high"] * 6.0e-3 / (math.pi / 4 * (lim.body_mm ** 2 - lim.bore_mm ** 2) * MM ** 2
                                                       * lim.modulus_pa)
    squeeze = (6.3 - (6.0 - 0.15) + d_c / MM) / 6.3                   # SPIROL formulas 1 and 2
    assert f"{squeeze * 100:.1f} %" in detail
    # the strain at which printed PETG reaches its measured compressive strength, not its tensile
    E = I.PRINTED["petg-bambu-basic"].secant_upper_bound("across") * 1e6
    assert f"{65.94e6 / E * 100:.1f} %" in detail


# ----------------------------------------------------------------------------- the coupons

def test_coupon_plan_covers_every_insert_both_axes_and_both_clamps():
    plan = I.coupon_plan()
    # no clamp cell tests a joint the check fails; a limiter cell's limiter stands proud, so it keeps the preload
    for c in plan["cells"]:
        if c["test"] == "clamp":
            assert c["check"]["verdict"] != "fail", c["id"]
            if c["limiter"]:
                assert c["predicted"]["preload_kept"]["low"] == 1.0 and c["plate_mm"] < 4.85, c["id"]
    ids = [c["id"] for c in plan["cells"]]
    assert len(ids) == len(set(ids))
    for key, ins in I.INSERTS.items():
        for axis in I.AXES:
            tests = {c["test"] for c in plan["cells"] if c["insert"] == key and c["axis"] == axis}
            assert tests == {"pull", "torque", "clamp"}, (key, axis)
    m3 = [c for c in plan["cells"] if c["insert"] == "mcmaster-94459A140" and c["test"] == "clamp"]
    assert {c["limiter"] for c in m3} == {None, "spirol-cl6000-m3"}
    assert all(c["count"] == I.PLAN_COUNT for c in plan["cells"])
    json.dumps(plan, allow_nan=False, default=str)


def test_coupon_blocks_are_cad_with_the_designed_hole():
    pytest.importorskip("cadquery")
    ins = I.insert("mcmaster-94459A140")
    up, lying = I.coupon_block(ins, "upright"), I.coupon_block(ins, "lying")
    side = I.coupon_side(ins)
    hole = I.hole_design(ins)
    for solid in (up, lying):
        assert solid.isValid()
        vol = side * side * (hole["depth_mm"] + 3.0) - math.pi / 4 * hole["diameter_mm"] ** 2 * hole["depth_mm"]
        assert solid.Volume() == pytest.approx(vol, rel=1e-3)
    assert up.BoundingBox().zlen == pytest.approx(hole["depth_mm"] + 3.0)
    assert lying.BoundingBox().zlen == pytest.approx(side) and lying.BoundingBox().zmin == pytest.approx(0.0)
    plate = I.clamp_plate(I.CLAMP_PLATE_MM, I.limiter_for(ins)["hole_mm"])
    assert plate.isValid() and plate.BoundingBox().zlen == pytest.approx(I.CLAMP_PLATE_MM)



def test_the_insert_face_is_held_to_brass_yield_under_a_clamped_part_as_under_a_limiter():
    m3 = dict(insert="mcmaster-94459A140", material="pla-bambu-basic", boss_outside_mm=9.5)
    flush = I.check_joint(**m3, clamped={"material": "metal"})
    knurl = I.INSERTS["mcmaster-94459A140"].outer_mm
    ring = math.pi / 4 * (knurl ** 2 - 3.4 ** 2) * MM ** 2             # round the ISO 273 medium hole
    assert flush["torque"]["governed_by"] == "insert_face"
    assert flush["torque"]["preload_caps_n"]["insert_face"] == pytest.approx(124e6 * ring, rel=1e-9)
    face = _rows(flush)["insert face"]
    assert face["verdict"] == "pass" and face["value"] <= 124.0 and "8.42 mm^2" in face["detail"]
    # over the softest temper's yield it warns, up to the hardest's, then fails
    hard = _rows(I.check_joint(**m3, clamped={"material": "metal"}, torque_nm=0.9))["insert face"]
    assert hard["verdict"] == "warn" and 124.0 < hard["value"] <= 310.0
    # recessed, the clamped part never reaches the brass: no face row
    assert "insert face" not in _rows(I.check_joint(**m3, recess_mm=0.2, clamped={"material": "metal"}))
    # a limiter on the insert is held to the same 124 MPa on its own ring
    with_lim = I.check_joint("mcmaster-94459A775", "pla-bambu-basic", boss_outside_mm=15.0, clamped={"thickness_mm": 6.0},
                             limiter_key="spirol-cl6000-m5", limiter_length_mm=6.0)
    assert _rows(with_lim)["insert face"]["limit"] == 124.0


def test_a_far_side_insert_is_pressed_onto_its_shoulder_and_its_melt_goes_back_to_the_far_face():
    base = dict(insert="mcmaster-94459A140", material="pla-bambu-basic", installed_from="far side", recess_mm=3.0,
                boss_outside_mm=9.5, clamped={"material": "metal"})
    rows = _rows(I.check_joint(**base))
    assert rows["hole depth"]["verdict"] == "pass" and rows["hole depth"]["limit"] == 5.7
    assert rows["melt volume"]["value"] is None and "far face" in rows["melt volume"]["detail"]
    deep = _rows(I.check_joint(**base, hole_depth_mm=6.7))["hole depth"]
    assert deep["verdict"] == "warn" and "1.00 mm deeper" in deep["detail"] and "jack-out" in deep["detail"]


def test_an_insert_larger_than_any_fitted_is_flagged_and_its_confidence_is_low():
    big = I.check_joint("mcmaster-94459A778", "pla-bambu-basic", boss_outside_mm=30.0, clamped={"material": "metal"})
    row = _rows(big)["calibration size"]
    assert row["verdict"] == "warn" and row["limit"] == [8.76, 12.7] and "14.0 at M8" in row["detail"]
    assert big["capacity"]["confidence"].startswith("low")
    m5 = I.check_joint("mcmaster-94459A775", "pla-bambu-basic", boss_outside_mm=15.0, clamped={"material": "metal"})
    assert "calibration size" not in _rows(m5) and m5["capacity"]["confidence"].startswith("medium")


def test_the_preload_kept_level_is_a_named_assumption():
    r = I.check_clamp("M10", "pa6-cf20-polymaker-wet", 40.0, head_mm=20.0, clearance_mm=12.0, torque_nm=20.0,
                      limiter={"outside_mm": 18.0, "bore_mm": 12.0}, limiter_length_mm=39.8)
    kept = _rows(r)["preload kept"]
    assert kept["limit"] == I.PRELOAD_KEPT_PASS and "assumed level" in kept["detail"]
