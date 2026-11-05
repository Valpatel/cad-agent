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

ROOT = Path(__file__).resolve().parents[2]
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
        "insert face": "pass", "clamped on insert": "pass"}
    # the plastic under the washer caps the preload at 78.06 MPa / 2 on pi/4 (7^2 - 3.4^2); the brass of the insert's
    # end, round the same hole, at 124 MPa on its ring; and the printed lid sitting on that ring, at 78.06 MPa / 2 on
    # it, is the lowest and sets the torque at the least nut factor
    area = math.pi / 4 * (7.0 ** 2 - 3.4 ** 2) * MM ** 2
    ring = math.pi / 4 * (I.INSERTS["mcmaster-94459A140"].outer_mm ** 2 - 3.4 ** 2) * MM ** 2
    k_lo = r["torque"]["nut_factor"]["low"]
    caps = r["torque"]["preload_caps_n"]
    assert caps["head_bearing"] == pytest.approx(78.06e6 / 2 * area, rel=1e-9)
    assert caps["insert_face"] == pytest.approx(124e6 * ring, rel=1e-9)
    assert r["torque"]["governed_by"] == "clamped_on_insert"
    assert r["torque"]["allowed_nm"] == pytest.approx(k_lo * 3e-3 * 78.06e6 / 2 * ring, rel=1e-9)
    assert rows["clamped on insert"]["value"] == pytest.approx(78.06 / 2, abs=0.05)
    assert rows["head bearing"]["value"] < 78.06 / 2 and rows["insert face"]["value"] < 124.0
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


def test_cad_allowance_matches_the_process_profile():
    """inserts and fit_coupons take the printed insert hole's allowance from the same row (#290)."""
    import yaml
    rules = yaml.safe_load((ROOT / "research" / "process-profiles.yaml").read_text())["rules"]
    row = next(r for r in rules if r["id"] == "fdm-insert-hole-cad-offset-cnckitchen")
    assert I.CAD_ALLOWANCE_MM == (row["min"], row["max"])


def test_spec_result_has_a_boolean_pass_a_checks_row_reads(tmp_path):
    """``pass`` is true unless a joint fails, so a ``cad: checks:`` row reads it with no wrapper (#292)."""
    from cadagent.project import load_project
    from cadagent.publish import report
    warn = I.check_spec({"joints": [{"insert": "mcmaster-94459A140", "material": "pla-bambu-basic",
                                     "boss_outside_mm": 8, "clamped": {"material": "metal"}}]})
    fail = I.check_spec({"joints": [{"insert": "mcmaster-94459A140", "material": "pla-bambu-basic",
                                     "boss_outside_mm": 6, "clamped": {"material": "metal"}}]})
    assert (warn["verdict"], warn["pass"]) == ("warn", True)
    assert (fail["verdict"], fail["pass"]) == ("fail", False)
    (tmp_path / "exports").mkdir()
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: lid\n  checks:\n"
                                             "    - {id: inserts, title: Inserts, file: exports/inserts.json}\n")
    for result, status in ((warn, "pass"), (fail, "fail")):
        (tmp_path / "exports" / "inserts.json").write_text(json.dumps(result, default=str))
        row = report.checks_feature(load_project(tmp_path), tmp_path)["checks"][0]
        assert row["status"] == status, row


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
          "limiter rating", "limiter wall", "clamped on insert", "clamped on washer")


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
    if ins.thread in ("M2", "M3", "M4", "M5", "M6"):          # the washer tables' sizes
        joints += [dict(clamped={"thickness_mm": 3.0}, insert_washer="iso7089", head_washer="iso7089"),
                   dict(clamped={"thickness_mm": 4.0}, insert_washer="iso7089", head="button"
                        if ins.thread != "M2" else "cheese", chamfer_mm=0.2)]
    if ins.thread in ("M3", "M4", "M5", "M6"):
        joints += [dict(clamped={"thickness_mm": 3.0}, insert_washer="iso7093", head_washer="iso7093")]
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
    r = I.check_joint(**base)
    rows = _rows(r)
    assert rows["hole depth"]["verdict"] == "pass" and rows["hole depth"]["limit"] == 5.7
    # the result's hole and install note say the same as the rows
    assert r["hole"]["depth_mm"] == 5.7 and "far face" in r["hole"]["why"][2]
    assert r["hole"]["overflow_mm3"] == 0.0
    assert "on to the shoulder" in r["install"]["how"] and "never below" not in r["install"]["how"]
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


def test_a_printed_part_clamped_on_a_flush_insert_bears_on_its_ring():
    lid = I.check_joint("mcmaster-94459A140", "petg-bambu-basic", boss_outside_mm=9.5, head_mm=7.0, clearance_mm=3.4,
                        clamped={"thickness_mm": 4.0})
    row = _rows(lid)["clamped on insert"]
    strength = I.bearing_strength("petg-bambu-basic") / 1e6
    assert row["verdict"] == "pass" and row["limit"] == pytest.approx(strength / 2, abs=0.05)
    # the torque the brass alone would allow crushes the lid into the ring
    over = _rows(I.check_joint("mcmaster-94459A140", "petg-bambu-basic", boss_outside_mm=9.5, head_mm=7.0,
                               clearance_mm=3.4, clamped={"thickness_mm": 4.0}, torque_nm=0.64))["clamped on insert"]
    assert over["verdict"] == "fail" and over["value"] > strength
    # a washer under the head does not help the ring; the row says which washer would
    assert "not under the head" in row["detail"] and "cautious side" in row["detail"]
    # clamping metal, nothing printed sits on the ring
    metal = I.check_joint("mcmaster-94459A140", "petg-bambu-basic", boss_outside_mm=9.5, clamped={"material": "metal"})
    assert "clamped on insert" not in _rows(metal)


# ----------------------------------------------------------------------------- heads, washers and the fix ladder (#292)

M3_LID = dict(insert="mcmaster-94459A140", material="pla-bambu-basic", boss_outside_mm=8,
              clamped={"thickness_mm": 3.0})


def test_the_issues_m3_lid_names_a_washer_with_its_torque():
    r = I.check_joint(**M3_LID)
    # as the issue found it: the lid on the insert's ring sets 0.20 N m
    assert r["torque"]["governed_by"] == "clamped_on_insert"
    assert r["torque"]["allowed_nm"] == pytest.approx(0.2006, abs=1e-4)
    fixes = r["fixes"]
    assert fixes["for"] == "clamped_on_insert" and fixes["preload_n"] == pytest.approx(328.6, abs=0.1)
    order = [o["fix"] for o in fixes["options"]]
    assert order == ["larger head", "washer", "large washer", "limiter", "limiter"]
    by = {}
    for o in fixes["options"]:
        by.setdefault(o["fix"], o)
    # no listed head bears wider than the socket head's 5.07 mm: the button head's dw is 5.00, and the cheese head's
    # 5.32 is its dk min standing in for a dw its standard does not give, so it is not compared
    assert not by["larger head"]["named"] and by["larger head"]["why"] == "no listed M3 head bears wider than 5.07 mm"
    # the fix: ISO 7089 washers, between the lid and the insert and then under the head, as each face governs
    w = fixes["fix"]
    assert w is by["washer"] and w["set"] == {"insert_washer": "iso7089", "head_washer": "iso7089"}
    assert w["governed_by"] == "clamped_on_washer" and w["named"]
    # its limit by hand: PLA's 78.06 MPa / 2 on the washer's bearing face (formulas test: 19.84 mm^2), and the torque
    # at the least nut factor with the head now on steel (thread 0.10, collar 0.08)
    face = fx.washer_bearing(4.72 * MM, 6.64 * MM, 0.45 * MM, 3.4 * MM, 2160e6, 2.9 * MM, 207e9, 78.06e6 / 2,
                             640e6 / 2)
    F = 78.06e6 / 2 * face["area"]
    assert w["preload_n"] == pytest.approx(F, rel=1e-9) and F == pytest.approx(774.3, abs=0.1)
    assert w["allowed_nm"] == pytest.approx(fx.nut_factor(3 * MM, 0.5 * MM, 0.10, 0.08) * 3 * MM * F, rel=1e-9)
    assert w["allowed_nm"] == pytest.approx(0.299, abs=1e-3) and w["gain"] == pytest.approx(2.36, abs=0.01)
    # the large washer lifts it further; the catalogue limiters lift the preload but fail their own rows
    assert by["large washer"]["named"] and by["large washer"]["preload_n"] > w["preload_n"]
    limiters = [o for o in fixes["options"] if o["fix"] == "limiter"]
    assert {o["set"]["limiter_key"] for o in limiters} == {"spirol-cl6000-m3", "spirol-cl8000-m3"}
    for o in limiters:
        assert not o["named"] and "seating force" in o["why"] and "limiter press fit" in o["why"]
    # every washer leaves the lid in the clamp path, so nothing here keeps the preload in metal
    assert fixes["lasting"] is None


def test_the_washer_fix_checked_directly_passes_every_row_it_loads():
    r = I.check_joint(**M3_LID, insert_washer="iso7089", head_washer="iso7089")
    rows = _rows(r)
    assert "clamped on insert" not in rows and rows["clamped on washer"]["verdict"] == "pass"
    assert "ISO 7089" in rows["clamped on washer"]["detail"] and "washer's hole" in rows["insert face"]["detail"]
    assert r["torque"]["friction"]["collar"] == list(I.COLLAR_ON_METAL)           # the head turns on the washer
    # the insert's brass now carries the washer round its hole at its largest (3.2 mm to H13: 3.38 mm), not the lid
    # round its 3.4 mm one
    assert r["torque"]["preload_caps_n"]["insert_face"] == pytest.approx(
        124e6 * math.pi / 4 * (4.72 ** 2 - 3.38 ** 2) * MM ** 2, rel=1e-9)
    _loaded_rows_pass(r)
    # the lid on the washer still sets it: the ladder's next step swaps both washers for large ones
    assert r["fixes"]["for"] == "clamped_on_washer" and r["fixes"]["fix"]["fix"] == "large washer"
    assert r["fixes"]["fix"]["set"] == {"head_washer": "iso7093", "insert_washer": "iso7093"}
    assert r["clamped_on_washer"]["washer"]["by"] == "bending"


def test_where_a_limiter_is_the_lasting_fix():
    # an M5 insert under a 3.8 +/- 0.05 mm PETG lid: the washers lift the cap, but the lid stays in the clamp and
    # relaxes; a 4 mm CL6000 stands proud of the lid at its least length, the head lands on metal and every row of
    # its own passes, so it is named, and it is the one that keeps the preload
    r = I.check_joint("mcmaster-94459A775", "petg-bambu-basic", boss_outside_mm=15,
                      clamped={"thickness_mm": 3.8, "tolerance_mm": 0.05, "outside_mm": 20})
    fixes = r["fixes"]
    assert fixes["fix"]["fix"] == "washer"
    lim = fixes["lasting"]
    assert lim["fix"] == "limiter" and lim["named"] and lim["set"]["limiter_length_mm"] == 4.0
    assert "standing proud" in lim["what"] and lim["preload_kept"] >= I.PRELOAD_KEPT_PASS
    washers = [o for o in fixes["options"] if o["fix"] in ("washer", "large washer")]
    assert all(o["named"] and o["preload_kept"] < I.PRELOAD_KEPT_PASS for o in washers)
    checked = I.check_joint("mcmaster-94459A775", "petg-bambu-basic", boss_outside_mm=15,
                            clamped={"thickness_mm": 3.8, "tolerance_mm": 0.05, "outside_mm": 20},
                            limiter_key=lim["set"]["limiter_key"], limiter_length_mm=4.0)
    assert {c["check"]: c["verdict"] for c in checked["checks"]}["seating force"] == "pass"
    assert not [c for c in checked["checks"] if c["verdict"] == "fail"]


def test_m3_heads_are_now_checked_and_a_chamfer_shrinks_the_face():
    r = I.check_joint(**M3_LID)
    head = _rows(r)["head bearing"]
    assert head["value"] is not None and "ISO 4762 socket head" in head["detail"]
    # the socket head's fillet (da 3.6 mm) is wider than the 3.4 mm hole: the row says to chamfer it
    assert "chamfer it to at least 3.6 mm" in head["detail"]
    caps = r["torque"]["preload_caps_n"]
    assert caps["head_bearing"] == pytest.approx(78.06e6 / 2 * fx.bearing_area(5.07 * MM, 3.4 * MM), rel=1e-9)
    chamfered = I.check_joint(**M3_LID, chamfer_mm=0.3)
    assert chamfered["torque"]["preload_caps_n"]["head_bearing"] == pytest.approx(
        78.06e6 / 2 * fx.bearing_area(5.07 * MM, 3.4 * MM, 0.3 * MM), rel=1e-9)
    assert "chamfer it" not in _rows(chamfered)["head bearing"]["detail"]
    # an under-chamfer narrows the lid's ring on the insert
    under = I.check_joint(**M3_LID, under_chamfer_mm=0.2)
    assert under["torque"]["preload_caps_n"]["clamped_on_insert"] == pytest.approx(
        78.06e6 / 2 * fx.bearing_area(4.72 * MM, 3.4 * MM, 0.2 * MM), rel=1e-9)


def test_check_clamp_names_a_larger_head_then_washers():
    r = I.check_clamp("M4", "pla-bambu-basic", 6.0)
    assert r["torque"]["governed_by"] == "head_bearing"
    opts = {o["fix"]: o for o in r["fixes"]["options"]}
    # ISO 7380-1's button head bears on 6.84 mm against the socket head's 6.53: the first fix
    assert r["fixes"]["fix"] is opts["larger head"] and opts["larger head"]["set"] == {"head": "button"}
    gain = (6.84 ** 2 - 4.5 ** 2) / (6.53 ** 2 - 4.5 ** 2)
    assert opts["larger head"]["gain"] == pytest.approx(gain, rel=1e-9)
    assert opts["washer"]["set"] == {"head_washer": "iso7089"} and opts["washer"]["named"]
    assert opts["large washer"]["preload_n"] > opts["washer"]["preload_n"] > opts["larger head"]["preload_n"]
    # a head given as head_mm that is wider than every listed head: no larger head
    wide = I.check_clamp("M4", "pla-bambu-basic", 6.0, head_mm=9.0, clearance_mm=4.5)
    assert {o["fix"]: o for o in wide["fixes"]["options"]}["larger head"]["why"].startswith("no listed M4 head")


def test_check_clamp_on_m3_names_no_larger_head():
    # the cheese head's dk min (5.32 mm) is not a bearing face: it is not set against the socket head's dw (5.07)
    r = I.check_clamp("M3", "pla-bambu-basic", 3.0)
    opts = {o["fix"]: o for o in r["fixes"]["options"]}
    assert not opts["larger head"]["named"] and r["fixes"]["fix"] is opts["washer"]


def test_a_larger_washer_already_fitted_is_kept():
    r = I.check_joint(**M3_LID, head_mm=9.0, head_washer="iso7093", insert_washer="iso7093")
    opts = {o["fix"]: o for o in r["fixes"]["options"]}
    assert "or a larger one, is fitted already" in opts["washer"]["why"] and "set" not in opts["washer"]
    assert "fitted already" in opts["large washer"]["why"]
    # a smaller one is swapped up
    up = I.check_joint(**M3_LID, insert_washer="iso7089")
    big = {o["fix"]: o for o in up["fixes"]["options"]}["large washer"]
    assert big["set"]["insert_washer"] == "iso7093" and big["named"]


def test_a_head_wider_than_its_washer_says_only_the_washer_bears():
    r = I.check_clamp("M3", "pla-bambu-basic", 3.0, head_mm=8.0, head_washer="iso7089")
    detail = _rows(r)["head bearing"]["detail"]
    assert "as wide as the washer or wider" in detail and "0.00 of its" not in detail
    assert r["head"]["on_plastic"]["area_mm2"] == pytest.approx(math.pi / 4 * (6.64 ** 2 - 3.4 ** 2), rel=1e-9)


def test_washers_and_heads_are_validated():
    with pytest.raises(ValueError, match="washer must be one of"):
        I.check_joint(**M3_LID, head_washer="din125")
    with pytest.raises(ValueError, match="lists no M2 washer"):
        I.check_joint("mcmaster-94459A120", "pla-bambu-basic", clamped={"thickness_mm": 3.0}, insert_washer="iso7093")
    with pytest.raises(ValueError, match="not both"):
        I.check_joint(**M3_LID, insert_washer="iso7089", limiter_key="spirol-cl6000-m3")
    with pytest.raises(ValueError, match="clamp path is jack-out"):
        I.check_joint(**M3_LID, insert_washer="iso7089", recess_mm=0.2)
    with pytest.raises(ValueError, match="thickness_mm"):
        I.check_joint("mcmaster-94459A140", "pla-bambu-basic", head_washer="iso7089")
    with pytest.raises(ValueError, match="head must be one of"):
        I.check_clamp("M4", "pla-bambu-basic", 6.0, head="hex")
    with pytest.raises(ValueError, match="nothing bears"):
        I.check_clamp("M4", "pla-bambu-basic", 6.0, chamfer_mm=1.1)


def test_the_cli_prints_the_fix(tmp_path):
    spec = tmp_path / "joints.yaml"
    spec.write_text("joints:\n  - {name: lid, insert: mcmaster-94459A140, material: pla-bambu-basic, "
                    "boss_outside_mm: 8, clamped: {thickness_mm: 3.0}}\n")
    import os
    r = subprocess.run([sys.executable, "-m", "cadagent.cli", "inserts", str(spec)], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tighten to at most 0.20 N m (clamped on insert)" in r.stdout
    assert ("fix: an ISO 7089 washer between the part and the insert and one under the head: at most 0.30 N m, "
            "774 N preload (clamped on washer)") in r.stdout
    assert "spirol-cl6000-m3" not in r.stdout                       # a limiter that fails is not named


# ----------------------------------------------------------------------------- the printed hole, by filament and nozzle
# (#323 phase 7). Golden vectors from the sources' numbers; each planted defect is a joint drawn with the old,
# filament-blind hole or a boss too thin for the nozzle, which the check must catch.
M3 = "mcmaster-94459A140"                    # McMaster's M3 x 5.7: the maker's hole 4.0 mm, CNC Kitchen's own size


def test_filler_increase_is_spirol_s_two_steps_interpolated():
    # SPIROL's white paper: +0.08 mm at 15 % filler or more, +0.15 mm at 35 % or more, interpolate between
    for pct, add in ((0, 0.0), (14.9, 0.0), (15, 0.08), (25, 0.115), (35, 0.15), (60, 0.15)):
        assert I.filler_increase(pct) == pytest.approx(add, abs=1e-12), pct
    for bad in (-1, 101, "20", True):
        with pytest.raises(ValueError):
            I.filler_increase(bad)


def test_the_hole_numbers_come_from_the_process_profile():
    import yaml
    rules = {r["id"]: r for r in yaml.safe_load((ROOT / "research" / "process-profiles.yaml").read_text())["rules"]}
    filler = rules["fdm-insert-hole-filler-spirol"]
    assert (filler["min"], filler["max"]) == (0.08, 0.15)
    assert rules["fdm-hole-undersize-cnckitchen-2019"]["value"] == 0.1
    assert I.perimeter_counts(I.insert(M3)) == {"lulzbot": rules["fdm-insert-wall-perimeters-lulzbot"]["min"],
                                                 "spirol": 3, "padt": [4, 6], "governs": "spirol", "least": 3}


def test_printed_hole_with_no_inputs_is_cnc_kitchen_s_4_2_mm():
    h = I.printed_hole(I.insert(M3))
    assert h["cad_mm"] == 4.2 and h["cad_band_mm"] == [4.2, 4.3]          # CNC Kitchen 2026: 4.0 + 0.2 to 0.3
    assert h["target_mm"] == pytest.approx(3.95) and h["undersize_mm"] == 0.25
    assert h["undersize_published_mm"] == [0.1, 0.25]                       # 2019 and 2026: the range is kept
    assert I.hole_design(I.insert(M3))["diameter_mm"] == 4.2 and "printed" not in I.hole_design(I.insert(M3))


def test_a_coupon_s_undersize_governs():
    h = I.printed_hole(I.insert(M3), "pla-bambu-basic", undersize_mm=0.1)   # CNC Kitchen 2019's printer
    assert h["cad_mm"] == 4.05 and h["cad_band_mm"] == [4.05, 4.15] and "coupon" in h["undersize_basis"]


def test_a_filled_filament_grows_the_hole_and_an_unknown_content_widens_the_band():
    known = I.printed_hole(I.insert(M3), "pa6-cf20-polymaker-dry", filler_pct=30)
    assert known["cad_mm"] == 4.333 and known["cad_band_mm"] == [4.333, 4.433]   # 4.0 + 0.1325 + 0.2 to 0.3
    unknown = I.printed_hole(I.insert(M3), "pa6-cf20-polymaker-dry")
    assert unknown["filled"] and unknown["cad_mm"] == 4.2 and unknown["cad_band_mm"] == [4.2, 4.45]
    assert I.printed_hole(I.insert(M3), "pla-bambu-basic")["cad_band_mm"] == [4.2, 4.3]


def test_the_nozzle_sets_a_floor_and_the_mesh_its_circle():
    # a wide track in a hole with no measured undersize: the RepRap arc balance is the floor
    h = I.printed_hole(I.insert(M3), "pla-bambu-basic", line_mm=0.8, undersize_mm=0.0)
    assert h["undersize_mm"] == pytest.approx(math.sqrt(3.95 ** 2 + 0.8 ** 2) - 3.95, abs=1e-4)     # 0.0802
    assert "arc floor" in h["undersize_basis"]
    # exact, not one step: the drawn hole prints, by the same balance, at the 3.95 mm wanted
    assert fx.arc_printed_diameter(h["cad_mm"] * 1e-3, 0.8e-3) / 1e-3 == pytest.approx(3.95, abs=1e-3)
    assert I.printed_hole(I.insert(M3), line_mm=0.42)["cad_mm"] == 4.2    # under the 0.25 mm: it does not bind
    coarse = I.printed_hole(I.insert(M3), facets=12)
    assert coarse["cad_mm"] == pytest.approx(4.2 / math.cos(math.pi / 12), abs=1e-3)   # 4.348: flats on 4.2
    assert coarse["facet_mm"] == pytest.approx(4.2 * (1 - math.cos(math.pi / 12)), abs=1e-4)
    assert coarse["polyhole"] == {"facets": 8, "diameter": pytest.approx(3.95 / math.cos(math.pi / 8), abs=1e-4)}
    assert any("EPFL" in w for w in I.printed_hole(I.insert(M3), "petg-bambu-basic")["why"])


def test_planted_defect_a_filled_joint_drawn_with_the_unfilled_hole():
    common = dict(boss_outside_mm=9.5, clamped={"material": "metal"})
    rows = lambda r: {c["check"]: c for c in r["checks"]}                    # noqa: E731
    bad = rows(I.check_joint(M3, "pa6-cf20-polymaker-dry", hole_mm=4.2, filler_pct=30, **common))
    assert bad["hole diameter"]["verdict"] == "warn" and bad["hole diameter"]["limit"] == [4.333, 4.433]
    good = rows(I.check_joint(M3, "pa6-cf20-polymaker-dry", filler_pct=30, **common))
    assert good["hole diameter"]["verdict"] == "pass" and good["printed hole"]["verdict"] == "pass"
    unknown = rows(I.check_joint(M3, "pa6-cf20-polymaker-dry", **common))
    assert unknown["printed hole"]["verdict"] == "warn" and "coupon" in unknown["printed hole"]["detail"]
    # the hole coupon in this filament settles it as well as the content does (#343 review)
    coupon = rows(I.check_joint(M3, "pa6-cf20-polymaker-dry", undersize_mm=0.15, **common))
    assert coupon["printed hole"]["verdict"] == "pass" and "your coupon" in coupon["printed hole"]["detail"]


def test_planted_defect_a_coarse_mesh_drawn_at_the_round_hole():
    rows = {c["check"]: c for c in I.check_joint(M3, "pla-bambu-basic", hole_mm=4.2, facets=12, boss_outside_mm=9.5,
                                                 clamped={"material": "metal"})["checks"]}
    assert rows["hole diameter"]["verdict"] == "warn"


def test_planted_defect_a_boss_too_thin_for_the_nozzle():
    def perimeters(outside, line):
        r = I.check_joint(M3, "pla-bambu-basic", boss_outside_mm=outside, line_mm=line, clamped={"material": "metal"})
        return next(c for c in r["checks"] if c["check"] == "boss perimeters")
    thin = perimeters(7.2, 0.8)              # (7.2 - 4.2) / 2 = 1.5 mm: one whole 0.8 mm line, SPIROL asks three
    assert thin["verdict"] == "warn" and thin["value"] == 1 and thin["limit"] == 3
    ok = perimeters(9.5, 0.42)               # 2.65 mm: six whole 0.42 mm lines
    assert ok["verdict"] == "pass" and ok["value"] == 6 and "gap fill" in ok["detail"]
    assert I.boss_design(I.insert(M3), 0.42)["solid_outside_mm"] == pytest.approx(4.2 + 2 * 7 * 0.42, abs=1e-9)


def test_defaults_add_no_rows_so_existing_results_stand():
    r = I.check_joint(M3, "pla-bambu-basic", boss_outside_mm=9.5, clamped={"material": "metal"})
    assert not {"printed hole", "boss perimeters"} & {c["check"] for c in r["checks"]}
