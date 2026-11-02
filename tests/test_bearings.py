"""Rolling bearings: cadagent.formulas.bearings against the makers' worked examples (tests/fixtures/bearing-vectors.json),
the exact Hertz contact against its closed forms and published approximations, and the check
(cadagent.mechanical.bearings.check_bearing) on the cases it must pass, warn and fail."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from cadagent import formulas as fx
from cadagent.formulas.bearings import _agm_elliptic
from cadagent.mechanical import bearings as mb

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests" / "fixtures" / "bearing-vectors.json").read_text())
KNEE = dict(oscillation={"amplitude_deg": 30, "cycles_per_min": 60},
            duty=[{"name": "stance", "radial_n": 900, "share": 0.6}, {"name": "swing", "radial_n": 150, "share": 0.4}],
            required_hours=2000, static=[{"name": "power cut", "radial_n": 3485}],
            internal={"balls": 7, "ball_mm": 5.953})


# ----------------------------------------------------------------------------- the golden vectors

def _run(vector):
    env = {}
    for step in vector["steps"]:
        args = {k: env[v[1:]] if isinstance(v, str) and v.startswith("$") else v for k, v in step["args"].items()}
        out = getattr(fx, step["fn"])(**args)
        if "key" in step:
            out = out[step["key"]]
        out = out * step.get("scale", 1.0) if isinstance(out, float) else out
        if "as" in step:
            env[step["as"]] = out
        yield step, out


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=[v["id"] for v in VECTORS["vectors"]])
def test_golden_vectors_from_the_makers_worked_examples(vector):
    checked = 0
    for step, out in _run(vector):
        if "expect" in step:
            expect = step["expect"]
            pairs = [(out[k], v) for k, v in expect.items()] if isinstance(expect, dict) else [(out, expect)]
            for got, want in pairs:
                assert got == pytest.approx(want, rel=step["rel"], abs=1e-12), (vector["id"], step["fn"], got, want)
            checked += 1
        if "at_least" in step:
            assert out >= step["at_least"], (vector["id"], out)
            checked += 1
    assert checked, f"{vector['id']} checks nothing"
    assert "p." in vector["source"] or "Table" in vector["source"], "a vector names its page"


def test_nsk_contact_constants_reproduce_nsks_worked_example():
    v = VECTORS["nsk_contact"]
    k1, k2, k3 = mb.NSK_CONTACT[v["size"]]
    root = v["radial_n"] ** (1 / 3)
    assert k1 * root == pytest.approx(v["p_max_mpa"], rel=v["rel"])
    assert k2 * root == pytest.approx(v["two_a_mm"], rel=v["rel"])
    assert k3 * root == pytest.approx(v["two_b_mm"], rel=v["rel"] * 2)       # printed to two digits
    b = mb.bearing({"designation": "6210", "kind": "deep-groove ball", "d_mm": 50, "outer_mm": 90, "width_mm": 20,
                    "dynamic_n": 35000, "static_n": 23200})
    w = mb.contact_width(b, v["radial_n"])
    assert w["width"] == pytest.approx(k3 * root * 1e-3) and "NSK" in w["basis"]


# ----------------------------------------------------------------------------- life, reliability, loads

def test_life_equation_and_its_inverse():
    for roller in (False, True):
        life = fx.rating_life(7280, 900, roller)
        assert life == pytest.approx((7280 / 900) ** (10 / 3 if roller else 3))
        assert fx.required_dynamic_rating(900, life, roller) == pytest.approx(7280)
    assert fx.life_hours(1.0, 1000) == pytest.approx(1e6 / 60e3)
    with pytest.raises(ValueError):
        fx.rating_life(7280, 0)


def test_reliability_factor_is_the_weibull_form_that_rounds_to_the_table():
    weibull = lambda r: 0.95 * (math.log(100 / r) / math.log(100 / 90)) ** (2 / 3) + 0.05   # noqa: E731
    for r, a1 in fx.RELIABILITY_TABLE.items():
        assert round(weibull(r), 2) == a1                       # the form behind the table, to its two decimals
    # between the rows it falls steadily, and at ISO 281's end, 99.95 %, it gives 0.077
    values = [fx.reliability_factor(r) for r in (90, 92.5, 95, 97.5, 99, 99.5, 99.9, 99.95)]
    assert values == sorted(values, reverse=True)
    assert fx.reliability_factor(99.95) == pytest.approx(0.077, abs=0.0005)
    for bad in (89.9, 99.96, 100, float("nan"), "99"):
        with pytest.raises(ValueError):
            fx.reliability_factor(bad)


def test_deep_groove_load_interpolates_and_ignores_a_small_axial_load():
    f = fx.deep_groove_factors(0.5 * (1.03 + 1.38))             # half-way between two rows
    assert f["e"] == pytest.approx(0.29) and f["y"] == pytest.approx(1.50) and not f["clamped"]
    assert fx.deep_groove_factors(0.05)["clamped"] and fx.deep_groove_factors(10)["clamped"]
    small = fx.deep_groove_load(1000, 100, 3100, 12)             # Fa / Fr = 0.1 < e: P = Fr
    assert small["load"] == 1000 and not small["axial_counts"]
    big = fx.deep_groove_load(500, 300, 3100, 12)
    assert big["axial_counts"] and big["load"] == pytest.approx(0.56 * 500 + big["y"] * 300)
    assert fx.deep_groove_load(0, 300, 3100, 12)["axial_counts"]    # pure axial
    # a larger clearance takes more of the axial load (higher e, lower Y at the same f0 Fa / C0)
    n, c3 = fx.deep_groove_factors(1.0), fx.deep_groove_factors(1.0, "c3")
    assert c3["e"] > n["e"] and c3["y"] < n["y"]
    with pytest.raises(ValueError):
        fx.deep_groove_factors(1.0, "c5")


def test_static_load_is_never_below_the_radial_load():
    assert fx.static_equivalent_load(1000, 0) == 1000          # 0.6 Fr < Fr
    assert fx.static_equivalent_load(1000, 1000) == pytest.approx(1100)
    assert fx.static_equivalent_load(0, 1000) == pytest.approx(500)
    assert fx.static_safety(3100, 3485) == pytest.approx(0.8895, abs=1e-4)


def test_iso76_rating_from_the_internal_geometry_matches_skfs_6201():
    # SKF's 6201: C0 3.1 kN, f0 12, so Z Dw^2 = 258 mm^2; 7 balls of 5.953 mm (15/64 in) give 248 mm^2, within 4 %
    zdw2 = fx.static_rating_iso76(12, 7, 5.953e-3) / 12
    assert zdw2 == pytest.approx(3100 / 12, rel=0.04)
    with pytest.raises(ValueError):
        fx.static_rating_iso76(12, 7.0, 5.953e-3)


# ----------------------------------------------------------------------------- duty cycles

def test_miner_and_the_cubic_mean_are_the_same_sum():
    loads, shares, c = [900.0, 150.0, 2000.0], [0.5, 0.45, 0.05], 7280
    for roller in (False, True):
        pm = fx.duty_cycle_load(loads, shares, roller)
        lives = [fx.rating_life(c, p, roller) for p in loads]
        assert fx.rating_life(c, pm, roller) == pytest.approx(fx.miner_life(lives, shares), rel=1e-12)
    assert fx.duty_cycle_load([700], [1.0]) == pytest.approx(700)
    with pytest.raises(ValueError):
        fx.duty_cycle_load([700, 800], [0.5, 0.4])


def test_revolution_shares_and_the_linear_mean():
    assert fx.revolution_fractions([0.5, 0.5], [500, 1500]) == pytest.approx([0.25, 0.75])
    # SKF's (Fmin + 2 Fmax) / 3 sits above the exact cubic mean of a steady ramp, by at most 9 %
    for lo in (0.0, 200.0, 500.0, 900.0):
        hi = 1000.0
        exact = ((hi ** 4 - lo ** 4) / (4 * (hi - lo))) ** (1 / 3)
        assert exact <= fx.varying_load_mean(lo, hi) <= 1.09 * exact
    with pytest.raises(ValueError):
        fx.varying_load_mean(2, 1)


# ----------------------------------------------------------------------------- oscillation

def test_oscillation_factors():
    crit = fx.critical_amplitude(7, 5.953 / 22, "outer")
    assert crit == pytest.approx(360 / (7 * (1 - 5.953 / 22)))
    assert fx.critical_amplitude(7, 5.953 / 22, "inner") < crit
    assert fx.rumbarger_factor(80, crit) == fx.harris_factor(80)          # above the critical amplitude
    below = fx.rumbarger_factor(30, crit)
    assert below == pytest.approx((30 / crit) ** 0.1 * 3)                  # ball: 1 - 1/e = 1 - 9/10
    assert fx.rumbarger_factor(30, crit, roller=True) == pytest.approx((30 / crit) ** (1 / 9) * 3)
    # the contact rolls the same arc on both raceways
    assert fx.rolling_travel(30, 0.022, 0.005953, "inner") == pytest.approx(fx.rolling_travel(30, 0.022, 0.005953,
                                                                                              "outer"))
    assert fx.rolling_travel(30, 0.022, 0.005953) == pytest.approx(math.radians(30) * 0.022 *
                                                                   (1 - (5.953 / 22) ** 2) / 4)
    for bad in ((0,), (-5,)):
        with pytest.raises(ValueError):
            fx.harris_factor(*bad)


# ----------------------------------------------------------------------------- Hertz

def test_elliptic_integrals():
    k, e = _agm_elliptic(0.5)
    assert k == pytest.approx(1.8540746773013719, rel=1e-13) and e == pytest.approx(1.3506438810476755, rel=1e-13)
    assert _agm_elliptic(0.0) == pytest.approx((math.pi / 2, math.pi / 2))


def test_hertz_circle_is_johnsons_closed_form():
    # a sphere of radius R on a flat: a^3 = 3 W R / (4 E*), E* = E / (2 (1 - nu^2)); p0 = 3 W / (2 pi a^2)
    w, r = 1000.0, 0.005
    c = fx.hertz_point_contact(w, r, r)
    e_star = 208e9 / (2 * (1 - 0.3 ** 2))
    a = (3 * w * r / (4 * e_star)) ** (1 / 3)
    assert c["a"] == pytest.approx(a, rel=1e-12) and c["b"] == pytest.approx(a, rel=1e-12)
    assert c["p_max"] == pytest.approx(3 * w / (2 * math.pi * a * a), rel=1e-12)


@pytest.mark.parametrize("ratio,tol", [(1.5, 0.03), (3, 0.03), (10, 0.03), (35, 0.03), (100, 0.07)])
def test_hertz_ellipse_against_hamrock_and_brewe(ratio, tol):
    # Brewe and Hamrock's curve fits for k and E: within 3 % of the exact solution up to Ry / Rx = 35 (a deep-groove
    # raceway's range), drifting to 6 % at 100
    c = fx.hertz_point_contact(500.0, 0.002, 0.002 * ratio)
    assert c["k"] == pytest.approx(1.0339 * ratio ** 0.6360, rel=tol)
    assert c["ellipticity_integral"] == pytest.approx(1.0003 + 0.5968 / ratio, rel=0.01)
    assert c["p_max"] == pytest.approx(1.5 * 500 / (math.pi * c["a"] * c["b"]))
    # the load scales the contact by its cube root
    d = fx.hertz_point_contact(4000.0, 0.002, 0.002 * ratio)
    assert d["b"] / c["b"] == pytest.approx(2.0) and d["p_max"] / c["p_max"] == pytest.approx(2.0)


def test_ball_raceway_contact_geometry():
    c = fx.ball_raceway_contact(500, 0.005953, 0.022, 0.52, "inner")
    o = fx.ball_raceway_contact(500, 0.005953, 0.022, 0.53, "outer")
    assert c["rx"] == pytest.approx(0.005953 / 2 * (1 - 5.953 / 22)) and o["rx"] > c["rx"]
    assert o["p_max"] < c["p_max"]                               # the outer contact is the gentler one
    with pytest.raises(ValueError):
        fx.ball_raceway_contact(500, 0.005953, 0.022, 0.5)


# ----------------------------------------------------------------------------- the catalogue

def test_every_catalogue_bearing_is_sourced_and_consistent():
    assert {"skf-6201", "skf-6301", "skf-61812", "skf-61800", "skf-61806"} <= set(mb.BEARINGS)
    for key, b in mb.BEARINGS.items():
        assert b.key == key and "https://" in b.source and "2026-11-01" in b.source, key
        assert 0 < b.d_mm < b.outer_mm and b.width_mm > 0 and b.dynamic_n > 0 and b.static_n > 0, key
        assert (b.reference_rpm is None) == (b.seals == "contact seals" or b.maker != "SKF"), key
        assert b.fatigue_limit_n < b.static_n * (0.15 if b.roller else 0.1), key   # Pu: a few % of C0
        if not b.roller:
            assert 10 <= b.f0 <= 17, key
            # ISO 76: C0 = f0 Z Dw^2, and a deep-groove bearing's balls fill about 0.3 of its section
            assert 0.15 < math.sqrt(b.static_n / b.f0 / 8) / (b.outer_mm - b.d_mm) < 0.6, key
    assert mb.bearing("skf-6201").size == "6201" and mb.bearing("skf-6201-2rsh").size == "6201"


def test_custom_bearings_and_refusals():
    b = mb.bearing({"designation": "X1", "kind": "deep-groove ball", "d_mm": 8, "outer_mm": 22, "width_mm": 7,
                    "dynamic_n": 3450, "static_n": 1370, "f0": 12})
    assert b.maker == "unknown" and not b.roller
    for bad in ({"designation": "X1"}, {"designation": "X1", "kind": "needle", "d_mm": 8, "outer_mm": 22,
                                        "width_mm": 7, "dynamic_n": 1, "static_n": 1}):
        with pytest.raises(ValueError):
            mb.bearing(bad)
    with pytest.raises(ValueError):
        mb.bearing("skf-9999")
    assert mb.s0_guideline(False) == 1.5 and mb.s0_guideline(True, "high", "infrequent", "yes") == 0.8
    with pytest.raises(ValueError):
        mb.s0_guideline(False, motion="infrequent", deformation="no")


# ----------------------------------------------------------------------------- the check

def rows(result):
    return {r["check"]: r for r in result["checks"]}


def test_the_knee_6201_lives_but_dents_in_a_power_cut_and_the_6301_does_not():
    r = mb.check_bearing("skf-6201-2rsh", **KNEE)
    by = rows(r)
    assert r["verdict"] == "fail" and r["motion"] == "oscillating"
    assert by["static safety: power cut"]["verdict"] == "fail"
    assert by["static safety: power cut"]["value"] == pytest.approx(3100 / 3485, abs=1e-3)
    assert by["rating life"]["verdict"] == "pass"
    assert by["critical amplitude"]["verdict"] == "warn"           # 30 < 70.5 degrees: Rumbarger
    assert r["life"]["oscillation_factor"] < r["life"]["harris_factor"]
    assert by["contact travel"]["verdict"] == "pass" and r["life"]["contact"]["x_over_2b"] > 10
    pm = fx.duty_cycle_load([900, 150], [0.6, 0.4])
    assert r["life"]["life_million"] == pytest.approx(fx.rating_life(7280, pm) * r["life"]["oscillation_factor"])
    assert r["life"]["hours"] == pytest.approx(r["life"]["life_million"] * 1e6 / 3600)
    s = mb.check_bearing("skf-6301-2rsh", **{**KNEE, "internal": None})
    assert rows(s)["static safety: power cut"]["verdict"] == "pass"
    assert rows(s)["critical amplitude"]["verdict"] == "warn"       # no geometry given: Harris, flagged


def test_the_rope_sheave_passes_every_row():
    r = mb.check_bearing("skf-6207-2rsh", radial_n=550, speed_rpm=2450, required_hours=43800)
    assert r["verdict"] == "pass", [c for c in r["checks"] if c["verdict"] != "pass"]
    assert r["life"]["hours"] == pytest.approx(804800, rel=5e-4)


def test_small_swings_warn_of_false_brinelling():
    r = mb.check_bearing("skf-6201", oscillation={"amplitude_deg": 1, "cycles_per_min": 600}, radial_n=500,
                         required_millions=100)
    by = rows(r)
    assert by["amplitude"]["verdict"] == "warn" and by["contact travel"]["verdict"] == "warn"
    assert by["contact travel"]["value"] < 1 and "NSK" in by["contact travel"]["detail"]


def test_fails_on_speed_axial_load_life_and_a_roller_pushed_sideways():
    assert rows(mb.check_bearing("skf-6201", radial_n=500, speed_rpm=40000))["speed"]["verdict"] == "fail"
    assert rows(mb.check_bearing("skf-6201", radial_n=500, speed_rpm=40000 * 0.8 / 0.64))["speed"]["verdict"] == "fail"
    assert rows(mb.check_bearing("skf-6201", radial_n=500, speed_rpm=26000))["speed"]["verdict"] == "warn"   # > 0.5 lim
    assert rows(mb.check_bearing("skf-6201", radial_n=500, axial_n=800, speed_rpm=100))["axial load"]["verdict"] == \
        "fail"                                                     # d 12 mm: 0.25 C0 = 775 N
    assert rows(mb.check_bearing("skf-6201", radial_n=500, axial_n=300, speed_rpm=3000, required_hours=10000,
                                 reliability=99))["rating life"]["verdict"] == "fail"
    nu = mb.check_bearing("skf-nu-202-ecp", radial_n=1000, axial_n=10, speed_rpm=1000)
    assert rows(nu)["axial load"]["verdict"] == "fail"
    light = mb.check_bearing("skf-6201", radial_n=40, speed_rpm=1000)
    assert rows(light)["minimum load"]["verdict"] == "warn"


def test_a_duty_cycle_by_time_at_two_speeds():
    r = mb.check_bearing("skf-6201", duty=[{"radial_n": 400, "share": 0.5, "speed_rpm": 500},
                                           {"radial_n": 800, "share": 0.5, "speed_rpm": 1500}], required_hours=5000)
    assert r["speed_rpm"] == pytest.approx(1000)
    assert [b["share"] for b in r["blocks"]] == pytest.approx([0.25, 0.75])
    pm = fx.duty_cycle_load([400, 800], [0.25, 0.75])
    assert r["life"]["hours"] == pytest.approx(fx.life_hours(fx.rating_life(7280, pm), 1000))
    with pytest.raises(ValueError):
        mb.check_bearing("skf-6201", speed_rpm=1000, duty=[{"radial_n": 400, "share": 1.0, "speed_rpm": 500}])
    with pytest.raises(ValueError):
        mb.check_bearing("skf-6201", speed_rpm=1000, duty=[{"radial_n": 400, "share": 0.5}])
    with pytest.raises(ValueError):
        mb.check_bearing("skf-6201", speed_rpm=1000, oscillation={"amplitude_deg": 10, "cycles_per_min": 1})
    with pytest.raises(ValueError):
        mb.check_bearing("skf-6201")


def test_check_spec_and_the_cli(tmp_path):
    spec = {"defaults": {"bearing": "skf-6201-2rsh", "oscillation": KNEE["oscillation"]},
            "bearings": [{"name": "knee", "duty": KNEE["duty"], "required_hours": 2000, "static": KNEE["static"]},
                         {"name": "knee, 6301", "bearing": "skf-6301-2rsh", "duty": KNEE["duty"],
                          "required_hours": 2000, "static": KNEE["static"]}]}
    out = mb.check_spec(spec)
    assert out["verdict"] == "fail" and [b["verdict"] for b in out["bearings"]] == ["fail", "warn"]
    with pytest.raises(ValueError):
        mb.check_spec({"bearings": [{"bearing": "skf-6201", "rpm": 3}]})
    f = tmp_path / "b.yaml"
    import yaml
    f.write_text(yaml.safe_dump(spec))
    run = lambda *a: subprocess.run([sys.executable, "-m", "cadagent.cli", "bearings", *a], capture_output=True,  # noqa
                                    text=True, cwd=tmp_path, env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""})
    r = run(str(f), "--output", str(tmp_path / "out.json"))
    assert r.returncode == 1, r.stderr
    assert "FAIL  knee" in r.stdout and "WARN  knee, 6301" in r.stdout
    assert json.loads((tmp_path / "out.json").read_text())["verdict"] == "fail"
    spec["bearings"] = spec["bearings"][1:]
    f.write_text(yaml.safe_dump(spec))
    assert run(str(f)).returncode == 0
    f.write_text("bearings: 3")
    assert run(str(f)).returncode == 2


def test_the_docs_example_says_what_the_check_computes():
    import re
    import yaml
    page = (ROOT / "docs" / "bearings.md").read_text()
    spec = yaml.safe_load(re.search(r"```yaml\n# bearings.yaml\n(.*?)```", page, re.S).group(1))
    out = mb.check_spec(spec)
    for b in out["bearings"]:
        life = b["life"]
        line = (f"{b['verdict'].upper():4}  {b['name']}: {b['motion']}, {life['life_million']:.3g} million "
                f"{life['unit']} ({life['hours']:,.0f} h), least s0 {min(s['s0'] for s in b['static']):.2f}")
        assert line in page, line
    knee = out["bearings"][1]
    assert f"s0 {rows(knee)['static safety: power cut']['value']:.2f}" in page
    assert f"{knee['life']['contact']['x_over_2b']:.1f} times its width" in page


def test_figures_are_current():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "bearing_figures.py"), "--check"], capture_output=True,
                       text=True)
    assert r.returncode == 0, r.stdout + r.stderr
