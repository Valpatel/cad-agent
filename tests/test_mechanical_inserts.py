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
    assert cal["pull"]["pla"]["low"] == pytest.approx(1353.6 / area / 20.25, rel=1e-9)
    assert cal["pull"]["pla"]["high"] == pytest.approx(181 * 9.80665 / area / 20.25, rel=1e-9)   # CNC Kitchen 2019
    assert cal["pull"]["petg"]["low"] == pytest.approx(119 * 9.80665 / area / 21.4, rel=1e-9)   # 0.662
    assert cal["pull"]["pla"]["cells"] == 11 and cal["pull"]["pooled"]["low"] == cal["pull"]["petg"]["low"]
    # torque over pull, r = 2 T / (F D): CNC Kitchen 2020 PETG 2 x 3 / (1167 N x 4.6 mm) = 1.118; SPIROL's M3 in
    # nylon 0.874 is the lowest; PEM M8 in ABS 1.410 the highest; the 2019 bound (the screw broke first) is shown only
    assert cal["torque_ratio"]["printed"] == [pytest.approx(1.1177, abs=1e-4)]
    assert cal["torque_ratio"]["low"] == pytest.approx(2 * 3.0 * 1e3 / (1445.0 * 4.75), rel=1e-9)
    assert cal["torque_ratio"]["high"] == pytest.approx(2 * 26.0 * 1e3 / (3566.0 * 10.34), rel=1e-9)
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
    assert cap["pull_out"]["low"] == pytest.approx(1063.1, abs=0.1)        # golden
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
        "clamp path": "pass", "tightening torque": "pass", "head bearing": "pass"}
    # the plastic under the washer sets the torque: 78.06 MPa / 2 on pi/4 (7^2 - 3.4^2), at the least nut factor
    area = math.pi / 4 * (7.0 ** 2 - 3.4 ** 2) * MM ** 2
    k_lo = r["torque"]["nut_factor"]["low"]
    assert r["torque"]["governed_by"] == "head_bearing"
    assert r["torque"]["allowed_nm"] == pytest.approx(k_lo * 3e-3 * 78.06e6 / 2 * area, rel=1e-9)
    assert rows["head bearing"]["value"] == pytest.approx(78.06 / 2, abs=0.01)
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
    plug = fx.insert_shear_force(7.11e-3, 3e-3, 15.5e6, 1.0)               # pi 7.11 x 3 mm x 15.5 MPa = 1038.6 N
    assert plug == pytest.approx(1038.6, abs=0.1)
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
    spec.write_text("joints: []\n")
    assert subprocess.run(run, capture_output=True, text=True, env={**os.environ, **env}).returncode == 2


# ----------------------------------------------------------------------------- the coupons

def test_coupon_plan_covers_every_insert_both_axes_and_both_clamps():
    plan = I.coupon_plan()
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
