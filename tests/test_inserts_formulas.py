"""Threaded inserts and compression limiters (#230): the closed forms in cadagent.formulas.inserts and .limiters,
each against a hand-worked golden vector and an independent derivation (the same-material press fit, a spring
chain solved directly, the torque split of Shigley's own equation)."""
import math

import pytest

from cadagent import formulas as fx

MM = 1e-3


# ----------------------------------------------------------------------------- the screw and the annulus

def test_proof_load_is_the_stress_area_times_the_class_proof_strength():
    # M3 x 0.5: As = pi/4 (3 - 0.9382 x 0.5)^2 = 5.0308 mm^2; class 12.9 proof strength 970 MPa -> 4880 N
    assert fx.proof_load(3 * MM, 0.5 * MM, 970e6) == pytest.approx(4879.9, abs=0.1)
    # M5 x 0.8: As = 14.18 mm^2 -> 13 755 N; M8 x 1.25: 36.6 mm^2 -> 35 503 N
    assert fx.proof_load(5 * MM, 0.8 * MM, 970e6) == pytest.approx(13755, rel=1e-3)
    assert fx.proof_load(8 * MM, 1.25 * MM, 970e6) == pytest.approx(35503, rel=1e-3)
    for bad in [(0, 0.5 * MM, 970e6), (3 * MM, 0.5 * MM, 0.0), (3 * MM, -1.0, 970e6)]:
        with pytest.raises(ValueError):
            fx.proof_load(*bad)


def test_annulus_stress_is_load_over_area():
    # 1000 N on a 6 mm head over a 3.2 mm hole: pi/4 (36 - 10.24) = 20.232 mm^2 -> 49.43 MPa
    assert fx.annulus_stress(1000.0, 6 * MM, 3.2 * MM) == pytest.approx(49.427e6, rel=1e-4)
    assert fx.annulus_stress(1000.0, 4 * MM, 0.0) == pytest.approx(1000.0 / (math.pi * 4e-6), rel=1e-12)
    assert fx.annulus_stress(0.0, 6 * MM, 3.2 * MM) == 0.0
    for bad in [(-1.0, 6 * MM, 3 * MM), (1.0, 3 * MM, 3 * MM), (1.0, 6 * MM, -1.0), (1.0, math.nan, 3 * MM)]:
        with pytest.raises(ValueError):
            fx.annulus_stress(*bad)


# ----------------------------------------------------------------------------- the limiter

def test_limiter_stack_stacks_the_tolerances_worst_case():
    r = fx.limiter_stack(5.0 * MM, 4.9 * MM, 0.05 * MM, 0.1 * MM)
    assert r["standout"]["nominal"] == pytest.approx(0.1 * MM)
    assert r["standout"]["low"] == pytest.approx(-0.05 * MM) and r["standout"]["high"] == pytest.approx(0.25 * MM)
    assert r["state"] == "either"
    assert fx.limiter_stack(5.2 * MM, 4.9 * MM, 0.05 * MM, 0.1 * MM)["state"] == "proud"
    assert fx.limiter_stack(4.7 * MM, 4.9 * MM, 0.05 * MM, 0.1 * MM)["state"] == "short"
    assert fx.limiter_stack(5 * MM, 5 * MM)["state"] == "either"          # exactly flush, no tolerance
    with pytest.raises(ValueError):
        fx.limiter_stack(5 * MM, 5 * MM, -0.1 * MM)


def test_a_short_limiter_loads_the_plastic_until_the_head_reaches_it():
    k = 2e7                                                               # N/m
    assert fx.limiter_plastic_load(0.0, k, 3000.0) == 0.0                # flush
    assert fx.limiter_plastic_load(-0.1 * MM, k, 3000.0) == 0.0          # proud
    assert fx.limiter_plastic_load(0.05 * MM, k, 3000.0) == pytest.approx(1000.0)
    assert fx.limiter_plastic_load(1.0 * MM, k, 3000.0) == 3000.0        # never reaches the limiter
    with pytest.raises(ValueError):
        fx.limiter_plastic_load(math.nan, k, 3000.0)


def test_press_fit_matches_the_same_material_closed_form():
    # one material: p = E delta / (2 R^3) (ro^2 - R^2)(R^2 - ri^2) / (ro^2 - ri^2), delta radial (Shigley 3-16)
    E, nu, d, D, di, dd = 2.5e9, 0.35, 5 * MM, 9 * MM, 3 * MM, 0.08 * MM
    R, ro, ri, delta = d / 2, D / 2, di / 2, dd / 2
    same = E * delta / (2 * R ** 3) * (ro ** 2 - R ** 2) * (R ** 2 - ri ** 2) / (ro ** 2 - ri ** 2)
    assert fx.press_fit_pressure(dd, d, D, E, nu, E, nu, di) == pytest.approx(same, rel=1e-12)
    # a rigid tube in plastic: only the hub term, p = delta / (R/E ((ro^2 + R^2)/(ro^2 - R^2) + nu))
    rigid = fx.press_fit_pressure(dd, d, D, E, nu, 1e30, 0.3, di)
    assert rigid == pytest.approx(delta / (R / E * ((ro ** 2 + R ** 2) / (ro ** 2 - R ** 2) + nu)), rel=1e-12)
    # golden: a steel tube (200 GPa, 0.29) of 5 x 3.2 mm in a 9 mm plastic boss (2.5 GPa, 0.35), 0.1 mm interference
    p = fx.press_fit_pressure(0.1 * MM, 5 * MM, 9 * MM, 2.5e9, 0.35, 200e9, 0.29, 3.2 * MM)
    assert p == pytest.approx(22.035e6, rel=1e-4)
    assert fx.press_fit_force(p, 5 * MM, 4 * MM, 0.3) == pytest.approx(0.3 * p * math.pi * 5 * MM * 4 * MM)
    assert fx.press_fit_pressure(0.0, d, D, E, nu, E, nu) == 0.0
    for bad in [dict(interference=-1e-5), dict(hub_outer_diameter=d), dict(shaft_inner_diameter=d),
                dict(hub_poisson=0.5), dict(shaft_modulus=0.0)]:
        args = dict(interference=dd, diameter=d, hub_outer_diameter=D, hub_modulus=E, hub_poisson=nu,
                    shaft_modulus=E, shaft_poisson=nu, shaft_inner_diameter=di)
        with pytest.raises(ValueError):
            fx.press_fit_pressure(**{**args, **bad})


def test_preload_retained_matches_a_spring_chain_solved_directly():
    # screw kb and plastic km in series at a fixed total stretch; the plastic's stiffness falls to r km
    kb, km, F0 = 4e7, 1e7, 2000.0
    total = F0 / kb + F0 / km
    for r in (0.0, 0.3, 0.6, 1.0):
        F = total / (1 / kb + 1 / (r * km)) if r > 0 else 0.0
        assert fx.preload_retained(r, km / kb) == pytest.approx(F / F0, abs=1e-12)
    assert fx.preload_retained(0.5, 0.0) == 0.5                            # a soft member passes its relaxation on
    assert fx.preload_retained(0.5, 1e9) == pytest.approx(1.0, abs=1e-8)   # a rigid one keeps it
    with pytest.raises(ValueError):
        fx.preload_retained(1.2, 0.25)


def test_a_limiter_keeps_its_own_share_and_the_plastic_relaxes():
    assert fx.preload_retained_limited(0.0, 3000.0, 0.4) == 1.0           # flush or proud: nothing in the plastic
    assert fx.preload_retained_limited(3000.0, 3000.0, 0.4) == pytest.approx(0.4)   # never reached the limiter
    assert fx.preload_retained_limited(1000.0, 3000.0, 0.4) == pytest.approx((2000 + 400) / 3000)
    with pytest.raises(ValueError):
        fx.preload_retained_limited(4000.0, 3000.0, 0.4)


# ----------------------------------------------------------------------------- the insert

def test_displaced_volume_is_a_volume_balance():
    # McMaster 94459A140 (M3 x 5.7): 42.13 mm^3 of brass over 5.74 mm, its CAD's bore 2.35 mm. In a 4.0 mm hole it
    # leaves 5.10 mm^3 of the knurl's valleys empty; in a 3.8 mm hole it pushes 1.93 mm^3 aside.
    V, db, L = 42.13e-9, 2.35 * MM, 5.74 * MM
    assert fx.insert_displaced_volume(V, 4.0 * MM, db, L) == pytest.approx(-5.1045e-9, abs=0.001e-9)
    assert fx.insert_displaced_volume(V, 3.8 * MM, db, L) == pytest.approx(1.9283e-9, abs=0.001e-9)
    with pytest.raises(ValueError):
        fx.insert_displaced_volume(V, 2.0 * MM, db, L)


def test_overflow_is_the_pocket_below_the_insert():
    # a 4.0 mm hole 6.5 mm deep under a 5.7 mm insert: pi/4 x 16 x 0.8 = 10.05 mm^3
    assert fx.overflow_volume(4 * MM, 6.5 * MM, 5.7 * MM) == pytest.approx(10.053e-9, rel=1e-4)
    assert fx.overflow_volume(4 * MM, 5.0 * MM, 5.7 * MM) == 0.0


def test_shear_force_and_torque_are_the_cylinder_times_c():
    D, L, tau, c = 4.72 * MM, 5.7 * MM, 15.5e6, 0.8
    area = math.pi * D * L
    assert fx.insert_shear_force(D, L, tau, c) == pytest.approx(c * tau * area, rel=1e-12)
    assert fx.insert_shear_torque(D, L, tau, c) == pytest.approx(c * tau * area * D / 2, rel=1e-12)
    # golden: 0.8 x 15.5 MPa x pi x 4.72 x 5.7 mm^2 = 1048.1 N; times 2.36 mm = 2.4735 N m
    assert fx.insert_shear_force(D, L, tau, c) == pytest.approx(1048.1, abs=0.1)
    assert fx.insert_shear_torque(D, L, tau, c) == pytest.approx(2.4735, abs=1e-4)
    for bad in [(0, L, tau, c), (D, L, tau, 0.0), (D, L, -tau, c)]:
        with pytest.raises(ValueError):
            fx.insert_shear_force(*bad)


@pytest.mark.parametrize("recess,tol,frm,path", [
    (0.3 * MM, 0.05 * MM, "joint face", "jack-out"),
    (0.0, 0.05 * MM, "joint face", "through-insert"),
    (0.04 * MM, 0.05 * MM, "joint face", "jack-out"),        # any recess jacks out: the tolerance is proud only
    (-0.04 * MM, 0.05 * MM, "joint face", "through-insert"),
    (-0.2 * MM, 0.05 * MM, "joint face", "through-insert"),
    (1.0 * MM, 0.0, "far side", "seat"),
])
def test_clamp_path_follows_where_the_insert_sits(recess, tol, frm, path):
    r = fx.insert_clamp_path(recess, tol, frm)
    assert r["path"] == path
    assert r["knurl_preload"] == (1.0 if path == "jack-out" else 0.0)
    assert r["why"] and r["instead"]


def test_clamp_path_refuses_what_it_cannot_place():
    with pytest.raises(ValueError):
        fx.insert_clamp_path(0.0, 0.0, "far side")         # no shoulder in front of it
    with pytest.raises(ValueError):
        fx.insert_clamp_path(0.1 * MM, 0.0, "sideways")
    with pytest.raises(ValueError):
        fx.insert_clamp_path(math.nan)


def test_insert_limited_torque_splits_the_torque_as_shigley_does():
    d, p = 3 * MM, 0.5 * MM
    Fp = fx.proof_load(d, p, 970e6)
    r = fx.insert_limited_torque(d, p, "through-insert", 800.0, 0.5, Fp, (0.15, 0.25), (0.15, 0.25))
    # the thread's share: K with no collar friction over K, at the most thread and least collar friction
    share = fx.nut_factor(d, p, 0.25, 0.0) / fx.nut_factor(d, p, 0.25, 0.15)
    assert r["thread_share"] == pytest.approx(share, rel=1e-12)
    # the same share from Shigley's thread-torque equation written out
    dm = d - 0.649519 * p
    lam, sec = p / (math.pi * dm), 1 / math.cos(math.radians(30))
    thread = dm / 2 * (lam + 0.25 * sec) / (1 - 0.25 * lam * sec)
    assert share == pytest.approx(thread / (thread + 0.15 * 0.625 * d), rel=1e-12)
    assert r["ceilings"]["torque_out"] == pytest.approx(0.5 / (2.0 * share))
    assert r["ceilings"]["screw"] == pytest.approx(fx.nut_factor(d, p, 0.15, 0.15) * Fp * d)
    assert "jack_out" not in r["ceilings"] and r["governed_by"] == "torque_out"
    lo, hi = r["preload"]["low"], r["preload"]["high"]
    assert lo < hi and hi == pytest.approx(r["torque"] / (r["nut_factor"]["low"] * d))


def test_jack_out_takes_the_preload_and_the_thread_torque_together():
    d, p, Fout, Tout = 3 * MM, 0.5 * MM, 800.0, 0.5
    Fp = fx.proof_load(d, p, 970e6)
    r = fx.insert_limited_torque(d, p, "jack-out", Fout, Tout, Fp, (0.15, 0.25), (0.15, 0.25))
    T, k_lo = r["torque"], r["nut_factor"]["low"]
    assert r["governed_by"] == "jack_out"
    # at that torque the linear interaction sits exactly on 1 / margin
    assert (T / (k_lo * d)) / Fout + T * r["thread_share"] / Tout == pytest.approx(0.5, rel=1e-12)
    seated = fx.insert_limited_torque(d, p, "seat", Fout, Tout, Fp, (0.15, 0.25), (0.15, 0.25))
    assert T < seated["torque"]
    # a weak screw governs
    assert fx.insert_limited_torque(d, p, "seat", Fout, 50.0, 10.0)["governed_by"] == "screw"


@pytest.mark.parametrize("bad", [dict(path="sideways"), dict(pull_out=0.0), dict(margin=0.5),
                                 dict(thread_friction=(0.3, 0.1)), dict(collar_friction=0.2),
                                 dict(flank_angle=60.0)])
def test_insert_limited_torque_refuses_what_it_cannot_compute(bad):
    args = dict(diameter=3 * MM, pitch=0.5 * MM, path="seat", pull_out=800.0, torque_out=0.5, proof_load=4880.0)
    with pytest.raises(ValueError):
        fx.insert_limited_torque(**{**args, **bad})
