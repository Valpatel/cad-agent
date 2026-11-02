"""The torsion-bar snap and the screw in a printed boss (#161): cadagent.formulas.torsion_snap_bar and screw_boss, the
functions under them, and cadagent.mechanical.bosses, against derivations written out here (the Saint-Venant series,
thread statics, the equilibrium of half a ring) and the published guides' rules."""
import math
import re
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from cadagent import formulas as fx
from cadagent.mechanical import bosses
from cadagent.mechanical.compliant import snapfit
from cadagent.mechanical.compliant.allowables import PRINTED

ROOT = Path(__file__).resolve().parents[1]
MM = 1e-3


# ----------------------------------------------------------------------------- the torsion bar

def _series(aspect, terms=200):
    """Derivation: the Saint-Venant stress function of a rectangle with half-sides a = aspect (long) and b = 1, as a
    series in the short direction (Timoshenko and Goodier, Theory of Elasticity, the rectangular bar in torsion). At
    a unit twist rate and G = 1, the shear stress (= strain) at the middle of the long sides,
    2 b [1 - 8 / pi^2 sum 1 / (n^2 cosh(n pi a / 2b))], and of the short sides, 16 b / pi^2 sum (-1)^((n - 1)/2)
    tanh(n pi a / 2b) / n^2, n odd."""
    a, b, odd = aspect, 1.0, range(1, 2 * terms, 2)
    long = 2 * b * (1 - 8 / math.pi ** 2 * sum(1 / (n * n * math.cosh(min(n * math.pi * a / (2 * b), 700))) for n in odd))
    short = 16 * b / math.pi ** 2 * sum((-1) ** ((n - 1) // 2) * math.tanh(n * math.pi * a / (2 * b)) / (n * n) for n in odd)
    return long, short


@pytest.mark.parametrize("aspect", [1, 1.136, 1.5, 2, 3, 4, 6, 10, 50])
def test_peak_shear_strain_against_the_series(aspect):
    # Roark's polynomial for the peak stress is furthest from the series at aspect 1.136, 0.75 % low (scanned from 1
    # to 50 in steps of 0.001); the page says "within 0.8 %".
    long, _ = _series(aspect)
    got = fx.torsion_shear_strain_rect(1.0, 1.0, 2 * aspect, 2.0)
    assert got == pytest.approx(long, rel=0.008)
    assert fx.torsion_shear_strain_rect(1.0, 1.0, 2.0, 2 * aspect) == got                  # either order


def test_peak_shear_strain_is_the_stress_over_g_and_the_thin_strip_limit():
    # Derivation: gamma = tau / G, with the torque that twists the bar through theta: T = K G theta / L.
    L, w, t, theta, G = 15 * MM, 4 * MM, 1.2 * MM, math.radians(8), 0.99e9
    T = fx.torsion_bar_stiffness(L, G, fx.torsion_constant_rect(w, t)) * theta
    assert fx.torsion_shear_strain_rect(theta, L, w, t) == pytest.approx(fx.torsion_shear_stress_rect(T, w, t) / G,
                                                                         rel=1e-12)
    # A thin strip (width 40 times the thickness): gamma -> theta t / L.
    assert fx.torsion_shear_strain_rect(theta, L, 40 * MM, 1 * MM) == pytest.approx(theta * 1 * MM / L, rel=0.002)


def test_a_flat_bar_still_shears_its_layers_at_three_quarters_of_the_peak():
    # docs/compliant.md: lying flat, the bar's short sides (the layers' edges) shear at 74 to 100 % of the peak, so the
    # check takes the allowable across the layers. The series: 1 for a square, 0.795 at 2:1, 0.7425 for a thin strip.
    # (the short-side series alternates and falls as 1 / n^2, so 2000 terms leave it within 1e-7)
    ratios = {a: _series(a, terms=2000)[1] / _series(a, terms=2000)[0] for a in (1, 2, 10, 50)}
    assert ratios[1] == pytest.approx(1.0, abs=1e-6)
    assert ratios[2] == pytest.approx(0.795, abs=5e-4)
    assert ratios[10] == pytest.approx(0.7425, abs=5e-4) and ratios[50] == pytest.approx(ratios[10], abs=1e-6)
    assert all(0.74 < r <= 1 + 1e-9 for r in ratios.values())
    assert "74 to 100 %" in (ROOT / "docs" / "compliant.md").read_text()


def test_torsion_snap_bar_from_first_principles():
    L, w, t, theta, E, eps, lever = 15 * MM, 4 * MM, 1.2 * MM, math.radians(8), 2.68e9, 0.0095, 10 * MM
    one = fx.torsion_snap_bar(L, w, t, theta, E, eps, lever)
    two = fx.torsion_snap_bar(L, w, t, theta, E, eps, lever, bars=2)
    G = E / (2 * 1.35)
    K = fx.torsion_constant_rect(w, t)
    assert one["shear_modulus"] == pytest.approx(G, rel=1e-12)
    assert one["torque"] == pytest.approx(K * G * theta / L, rel=1e-12)              # T = K G theta / L
    assert one["force"] * lever == pytest.approx(one["torque"], rel=1e-12)
    assert one["travel"] == pytest.approx(lever * math.sin(theta), rel=1e-12)
    # two bars: the same twist and strain, twice the torque (the guide's factor 2, Fig. 21)
    assert two["shear_strain"] == one["shear_strain"] and two["torque"] == pytest.approx(2 * one["torque"], rel=1e-12)
    # the guide's allowable shear strain is (1 + nu) eps, as snapfit.torsion_snap takes it
    assert one["allowable_shear_strain"] == pytest.approx(1.35 * eps, rel=1e-12)
    assert snapfit.torsion_snap(10, 1.5, eps, 2000, 8)["shear_strain"] == one["allowable_shear_strain"]
    # at the permissible twist the strain is the allowable, exactly
    edge = fx.torsion_snap_bar(L, w, t, one["permissible_twist"], E, eps, lever)
    assert edge["ratio"] == pytest.approx(1.0, rel=1e-12)
    assert one["passes"] == (one["ratio"] <= 1) and one["ratio"] == pytest.approx(0.8628, abs=1e-4)
    rest = fx.torsion_snap_bar(L, w, t, 0.0, E, eps, lever)
    assert rest["shear_strain"] == 0 and rest["force"] == 0 and rest["stiffness"] == one["stiffness"]


def test_torsion_snap_bar_matches_the_guides_round_bar_where_both_apply():
    # A thin strip of the same shear strain and length twists by gamma L / t; the guide's round bar by gamma L / r.
    # Both come from gamma = theta (outer fibre distance) / L: check the rectangle against that at the permissible twist.
    strip = fx.torsion_snap_bar(10 * MM, 40 * MM, 1 * MM, 0.1, 2000e6, 0.02, 8 * MM)
    gamma = snapfit.torsion_allowable_shear(0.02)
    assert strip["permissible_twist"] == pytest.approx(gamma * 10 / 1, rel=0.002)
    round_bar = snapfit.torsion_snap(bar_length=10, bar_radius=1.0, strain=0.02, secant_mpa=2000, lever_mm=8)
    assert math.radians(round_bar["twist_deg"]) == pytest.approx(gamma * 10 / 1.0, rel=1e-12)


def test_the_trapeze_effect_and_when_the_closed_form_stops_holding():
    # Derivation: twisted at theta' = theta / L, a fibre at y across the long side b runs as a helix and stretches by
    # (theta' y)^2 / 2. With no net axial force the strain is eps(y) = theta'^2 (y^2 - b^2 / 12) / 2, and each fibre's
    # pull, leaning at theta' y, has a moment about the axis: dT = E eps(y) (theta' y) y t dy. Integrated here.
    L, b, t, theta, E = 30 * MM, 12 * MM, 0.6 * MM, math.radians(30), 3.0e9
    rate, n = theta / L, 20000
    ys = [-b / 2 + b * (i + 0.5) / n for i in range(n)]
    eps = [rate * rate * (y * y - b * b / 12) / 2 for y in ys]
    assert abs(sum(eps)) * b / n < 1e-12                                                    # no net axial force
    torque = sum(E * e * rate * y * y * t for e, y in zip(eps, ys)) * b / n
    assert torque == pytest.approx(E * t * b ** 5 * rate ** 3 / 360, rel=1e-6)              # the trapeze term
    r = fx.torsion_snap_bar(L, b, t, theta, E, 0.02, 10 * MM)
    assert r["trapeze_ratio"] == pytest.approx(torque / (r["stiffness"] * theta), rel=1e-6)
    assert r["edge_axial_strain"] == pytest.approx(rate * rate * (b * b / 4 - b * b / 12) / 2, rel=1e-12)
    # the compliant page's example: 41 % more torque and 0.37 % along the edges, flagged
    assert not r["small_twist"] and round(100 * r["trapeze_ratio"]) == 41 and f"{100 * r['edge_axial_strain']:.2f}" == "0.37"
    page = (ROOT / "docs" / "compliant.md").read_text()
    assert "at 30° gains 41 %, with 0.37 % strain along its edges" in page
    # either way round the section, and the page's default bar is far inside the closed form's reach
    assert fx.torsion_snap_bar(L, t, b, theta, E, 0.02, 10 * MM)["trapeze_ratio"] == r["trapeze_ratio"]
    default = fx.torsion_snap_bar(15 * MM, 4 * MM, 1.2 * MM, math.radians(8), 2.68e9, 0.0095, 10 * MM, 2)
    assert default["small_twist"] and default["trapeze_ratio"] < 1e-3
    # a square bar barely warps its edges out of line: the term stays small at the same twist rate
    assert fx.torsion_snap_bar(L, 2 * MM, 2 * MM, theta, E, 0.02, 10 * MM)["small_twist"]
    assert fx.SMALL_TWIST_TRAPEZE == 0.1


@pytest.mark.parametrize("bad", [dict(length=0), dict(width=-1e-3), dict(thickness=math.nan), dict(twist=-0.1),
                                 dict(twist=math.inf), dict(modulus=0), dict(allowable_strain=0), dict(lever=0),
                                 dict(bars=3), dict(bars=True), dict(bars=1.5), dict(poisson=0.5), dict(length=True)])
def test_torsion_snap_bar_refuses_what_it_cannot_compute(bad):
    args = dict(length=15 * MM, width=4 * MM, thickness=1.2 * MM, twist=0.1, modulus=2.6e9, allowable_strain=0.01,
                lever=10 * MM, bars=1, poisson=0.35)
    with pytest.raises(ValueError):
        fx.torsion_snap_bar(**{**args, **bad})


# ----------------------------------------------------------------------------- the screw in a boss

def test_radial_pressure_is_the_flanks_push():
    # Derivation: a flank inclined at alpha (half the flank angle) carries the axial load F on its normal force N:
    # N cos alpha = F, so its radial part is N sin alpha = F tan alpha, spread over the crest cylinder pi d Le.
    F, d, Le = 400.0, 3 * MM, 6 * MM
    for flank in (60, 30):
        p = fx.thread_radial_pressure(F, d, Le, math.radians(flank))
        assert p * math.pi * d * Le == pytest.approx(F * math.tan(math.radians(flank / 2)), rel=1e-12)
    assert fx.thread_radial_pressure(F, d, Le) == fx.thread_radial_pressure(F, d, Le, math.radians(60))
    # a 30 degree flank pushes out less than half as hard as an ISO 60 degree one (tan 15 / tan 30 = 0.46)
    assert fx.thread_radial_pressure(F, d, Le, math.radians(30)) / fx.thread_radial_pressure(F, d, Le) == \
        pytest.approx(math.tan(math.radians(15)) / math.tan(math.radians(30)), rel=1e-12)


def test_hoop_stress_balances_the_pressure_on_half_the_ring():
    # Derivation: cut the ring along a diameter. The pressure on the half bore pushes p d per unit length; the hoop
    # stress across the two cut walls carries it: 2 * integral of sigma_t(r) dr from ri to ro = p d. Lame's
    # distribution sigma_t(r) = p ri^2 / (ro^2 - ri^2) (1 + ro^2 / r^2) peaks at the bore, where the function reads it.
    p, d, D = 3e6, 3 * MM, 6 * MM
    ri, ro = d / 2, D / 2

    def sigma(r):
        return p * ri ** 2 / (ro ** 2 - ri ** 2) * (1 + ro ** 2 / r ** 2)

    n = 20000
    h = (ro - ri) / n
    integral = h * (sigma(ri) / 2 + sum(sigma(ri + i * h) for i in range(1, n)) + sigma(ro) / 2)
    assert 2 * integral == pytest.approx(p * d, rel=1e-7)
    assert fx.boss_hoop_stress(p, d, D) == pytest.approx(sigma(ri), rel=1e-12)
    assert fx.boss_hoop_stress(p, d, D) / p == pytest.approx(5 / 3, rel=1e-12)          # 1.67 at D = 2 d
    assert fx.boss_hoop_stress(p, d, 1.25 * d) / p == pytest.approx(4.556, abs=1e-3)    # 4.6 at D = 1.25 d
    # a thin wall: sigma -> p r / t
    assert fx.boss_hoop_stress(p, 100 * MM, 100.2 * MM) == pytest.approx(p * 50 / 0.1, rel=0.002)
    for bad in [(-1, d, D), (p, 0, D), (p, d, d), (p, d, math.nan)]:
        with pytest.raises(ValueError):
            fx.boss_hoop_stress(*bad)


def test_nut_factor_flank_angle_defaults_to_the_iso_thread():
    for args in [(3 * MM, 0.5 * MM, 0.15, 0.15), (8 * MM, 1.25 * MM, 0.1, 0.2)]:
        assert fx.nut_factor(*args) == fx.nut_factor(*args, math.radians(60))
        # a narrower flank wedges less: a smaller K at the same friction
        assert fx.nut_factor(*args, math.radians(30)) < fx.nut_factor(*args)


@pytest.mark.parametrize("bad", [60.0, 30.0, 0.0, -0.5, math.pi / 2, 2.0, np.float32(60.0), Decimal("60")])
def test_nut_factor_refuses_a_flank_angle_outside_0_to_90_degrees(bad):
    # 60 passed as degrees used to give K = 0.59 instead of 0.20 (about 3 x) without complaint
    with pytest.raises(ValueError, match="radians"):
        fx.nut_factor(3 * MM, 0.5 * MM, 0.15, 0.15, bad)
    # just inside the range still computes
    assert fx.nut_factor(3 * MM, 0.5 * MM, 0.15, 0.15, math.pi / 2 - 1e-9) > 0


@pytest.mark.parametrize("bad, says", [(math.nan, "finite"), (math.inf, "finite"), (True, "real number"),
                                       ("1.047", "real number"), (None, "real number")])
def test_nut_factor_says_a_flank_angle_that_is_not_a_number_is_not_one(bad, says):
    with pytest.raises(ValueError, match=says) as err:
        fx.nut_factor(3 * MM, 0.5 * MM, 0.15, 0.15, bad)
    assert "between 0 and pi/2" not in str(err.value)          # not reported as out of range


def test_the_screw_formulas_take_numpy_scalars_and_decimals_as_their_float_values():
    d, P, f = 3 * MM, 0.5 * MM, 0.15
    k = fx.nut_factor(d, P, f, f, math.radians(60))
    for angle in (np.float32(math.radians(60)), np.float64(math.radians(60)), Decimal(repr(math.radians(60)))):
        assert fx.nut_factor(d, P, f, f, angle) == pytest.approx(k, rel=1e-6)
    assert fx.nut_factor(Decimal("0.003"), np.float64(P), np.float32(f), Decimal("0.15")) == pytest.approx(k, rel=1e-6)
    p_r = fx.thread_radial_pressure(1000.0, d, 6 * MM)
    assert fx.thread_radial_pressure(np.int64(1000), Decimal("0.003"), np.float32(6 * MM)) == pytest.approx(p_r, rel=1e-6)
    hoop = fx.boss_hoop_stress(10e6, d, 2 * d)
    assert fx.boss_hoop_stress(Decimal("1E+7"), np.float64(d), np.float32(2 * d)) == pytest.approx(hoop, rel=1e-6)
    for drive in (None, 0.1):
        r = fx.screw_boss(d, 1.12 * MM, 6 * MM, 6 * MM, 0.3, 15.5e6, 35e6, friction_high=0.5, drive_torque=drive)
        q = fx.screw_boss(Decimal("0.003"), np.float64(1.12 * MM), 6 * MM, np.float32(6 * MM), Decimal("0.3"),
                          np.int64(15_500_000), 35e6, friction_high=Decimal("0.5"),
                          drive_torque=None if drive is None else Decimal("0.1"))
        # every number in the result, banded or not, is the float call's, and a Python float or a bool
        for key, v in r.items():
            pairs = v.items() if isinstance(v, dict) else [(None, v)]
            for sub, x in pairs:
                y = q[key] if sub is None else q[key][sub]
                if isinstance(x, bool) or x is None:
                    assert y == x, (key, sub)
                else:
                    assert type(y) is float and y == pytest.approx(x, rel=1e-6), (key, sub)


def test_screw_boss_is_its_parts_and_covestros_window():
    d, P, Le, D, T, tau, hoop = 3 * MM, 1.12 * MM, 6 * MM, 6 * MM, 0.3, 15.5e6, 35e6
    r = fx.screw_boss(d, P, Le, D, T, tau, hoop)
    k_lo = fx.nut_factor(d, P, 0.2, 0.2, math.radians(30))
    k_hi = fx.nut_factor(d, P, 0.5, 0.5, math.radians(30))
    assert r["nut_factor"] == {"low": k_lo, "high": k_hi}
    assert r["preload"]["high"] * k_lo * d == pytest.approx(T, rel=1e-12)              # T = K F d, no drive torque
    # the drive torque makes no clamp: unmeasured, the low end takes the most the window allows, T / 1.2
    assert r["preload"]["low"] * k_hi * d == pytest.approx(T - T / 1.2, rel=1e-12)
    assert r["drive_torque"] is None
    assert r["strip_force"] == fx.thread_strip_force(d, P, Le, tau)                     # 0.875 pi d Le tau
    assert r["strip_force"] == pytest.approx(0.875 * math.pi * d * Le * tau, rel=1e-12)
    assert r["strip_torque"]["low"] == pytest.approx(k_lo * r["strip_force"] * d, rel=1e-12)
    # the margin is the strip torque over the applied torque, and (with no drive torque) the strip force over the clamp
    assert r["margin"]["low"] == pytest.approx(r["strip_force"] / r["preload"]["high"], rel=1e-12)
    # Covestro: tighten to at most half the stripping torque (taken at the low end of the band), and at least 1.2 x
    # the drive torque, so this tightening torque allows a measured drive torque of up to T / 1.2
    assert r["torque_ceiling"] == pytest.approx(0.5 * r["strip_torque"]["low"], rel=1e-12)
    assert r["drive_torque_limit"] == pytest.approx(T / 1.2, rel=1e-12)
    assert r["torque_ok"] == (r["margin"]["low"] >= 2)
    assert r["hoop_stress"] == pytest.approx(
        fx.boss_hoop_stress(fx.thread_radial_pressure(r["preload"]["high"], d, Le, math.radians(30)), d, D), rel=1e-12)
    assert r["outside_ok"] and r["engagement_ok"] and r["passes"]
    # thinner than 2 d, shorter than 2 d, or tightened past the ceiling: each fails on its own
    assert not fx.screw_boss(d, P, Le, 5.9 * MM, T, tau, hoop)["outside_ok"]
    assert not fx.screw_boss(d, P, 5.9 * MM, D, T, tau, hoop)["engagement_ok"]
    over = fx.screw_boss(d, P, Le, D, 0.4, tau, hoop)
    assert not over["torque_ok"] and not over["passes"] and over["outside_ok"]
    # exactly 2 d survives the rounding of d and D, whichever millimetre values make it
    for dd in (2.2, 2.5, 3.5, 4.5):
        assert fx.screw_boss(dd * MM, P, 2 * dd * MM, 2 * dd * MM, 0.1, tau, hoop)["outside_ok"]


def test_screw_boss_takes_off_a_measured_drive_torque():
    # The drive torque forms the thread and makes no clamp: the clamp is (T - drive) / K d, the thread strips at the
    # drive torque plus K F d, and Covestro's window runs from 1.2 x the drive torque to half that stripping torque.
    d, P, Le, D, tau, hoop, f = 3 * MM, 1.12 * MM, 6 * MM, 6 * MM, 15.5e6, 35e6, (0.2, 0.65, math.radians(30))
    none = fx.screw_boss(d, P, Le, D, 0.3, tau, hoop, *f)
    zero = fx.screw_boss(d, P, Le, D, 0.3, tau, hoop, *f, drive_torque=0.0)
    most = fx.screw_boss(d, P, Le, D, 0.3, tau, hoop, *f, drive_torque=0.3 / 1.2)
    # unmeasured, the clamp band spans no drive torque (the high end) to the most the window allows (the low end)
    assert none["preload"] == {"low": most["preload"]["low"], "high": zero["preload"]["high"]}
    assert none["strip_torque"] == zero["strip_torque"] and none["hoop_stress"] == zero["hoop_stress"]
    r = fx.screw_boss(d, P, Le, D, 0.3, tau, hoop, *f, drive_torque=0.2)
    k_lo, k_hi = r["nut_factor"]["low"], r["nut_factor"]["high"]
    assert r["preload"]["high"] * k_lo * d == pytest.approx(0.1, rel=1e-12)
    assert r["preload"]["low"] * k_hi * d == pytest.approx(0.1, rel=1e-12)
    assert r["strip_torque"]["low"] == pytest.approx(0.2 + k_lo * r["strip_force"] * d, rel=1e-12)
    assert r["torque_ceiling"] == pytest.approx(0.5 * r["strip_torque"]["low"], rel=1e-12)
    assert r["hoop_stress"] < none["hoop_stress"] and r["torque_ok"] and r["passes"]
    # under 1.2 x the drive torque the screw may not seat: the torque check fails though the ceiling is above it
    low = fx.screw_boss(d, P, Le, D, 0.3, tau, hoop, *f, drive_torque=0.3)
    assert not low["torque_ok"] and low["torque_ceiling"] > 0.3 and low["preload"] == {"low": 0.0, "high": 0.0}
    # the printed boss passes it through
    pb = bosses.printed_boss("pla-bambu-basic", "30", 6, 6, 0.3, drive_torque_nm=0.2)
    assert pb["inputs"]["drive_torque_nm"] == 0.2 and pb["preload"] == r["preload"]


@pytest.mark.parametrize("bad", [dict(diameter=0), dict(torque=0), dict(shear_strength=-1), dict(friction_low=-0.1),
                                 dict(friction_high=0.1), dict(outside_diameter=3 * MM), dict(engagement=math.inf),
                                 dict(drive_torque=-0.1), dict(drive_torque=math.nan), dict(drive_torque="0.1")])
def test_screw_boss_refuses_what_it_cannot_compute(bad):
    args = dict(diameter=3 * MM, pitch=1.12 * MM, engagement=6 * MM, outside_diameter=6 * MM, torque=0.3,
                shear_strength=15.5e6, hoop_strength=35e6, friction_low=0.2, friction_high=0.5)
    with pytest.raises(ValueError):
        fx.screw_boss(**{**args, **bad})


# ----------------------------------------------------------------------------- printed bosses

def test_printed_strength_is_the_cautious_edition():
    for key, m in PRINTED.items():
        along, across = m.strength("along"), m.strength("across")
        assert across <= along, key
        assert along == min(s.uts_mpa[0] for s in m.sheets), key
        assert across == min(min(s.uts_mpa) for s in m.sheets), key
    # Bambu PETG-CF: V3.0 (35 / 29 MPa) governs over V2.0 (59 / 38)
    cf = PRINTED["petg-cf-bambu"]
    assert (cf.strength("along"), cf.strength("across")) == (35, 29) and cf.strength_sheet("across").edition == "V3.0"


def test_printed_boss_picks_its_numbers_and_says_where_from():
    r = bosses.printed_boss("pla-bambu-basic", "30", 6, 6, 0.3)
    assert r["material"]["shear_strength"] == 0.5 * 31e6                    # half the lowest UTS across the layers
    assert r["material"]["hoop_strength"] == 35e6                           # upright: along the perimeters
    lying = bosses.printed_boss("pla-bambu-basic", "30", 6, 6, 0.3, axis="lying")
    assert lying["material"]["hoop_strength"] == 31e6 and lying["hoop_ratio"] > r["hoop_ratio"]
    assert r["friction"]["band"] == [0.2, 0.65] and r["screw"]["diameter_mm"] == 3.0
    same = fx.screw_boss(3 * MM, 1.12 * MM, 6 * MM, 6 * MM, 0.3, 15.5e6, 35e6, 0.2, 0.65)
    assert {k: r[k] for k in same} == same
    assert r["passes"] and not bosses.printed_boss("pla-bambu-basic", "30", 6, 6, 0.4)["torque_ok"]
    assert any("not a rating" in lim for lim in r["limits"])
    for bad in [("pla", "30", 6, 6, 0.3), ("pla-bambu-basic", "M3", 6, 6, 0.3)]:
        with pytest.raises(ValueError):
            bosses.printed_boss(*bad)
    with pytest.raises(ValueError):
        bosses.printed_boss("pla-bambu-basic", "30", 6, 6, 0.3, axis="z")


def test_the_delta_pt_table_and_the_docstring_example():
    sizes = list(bosses.DELTA_PT.values())
    assert all(b["diameter_mm"] > a["diameter_mm"] and b["pitch_mm"] > a["pitch_mm"] for a, b in zip(sizes, sizes[1:]))
    # the DELTA PT pitch is about a third of the diameter (0.35 to 0.39 d), against 0.15 to 0.2 d for ISO coarse
    assert all(0.34 < s["pitch_mm"] / s["diameter_mm"] < 0.4 for s in sizes)
    r = bosses.printed_boss("pla-bambu-basic", "30", 6, 6, 0.3)
    doc = bosses.__doc__
    assert f"clamp {r['preload']['low']:.0f}-{r['preload']['high']:.0f} N" in doc
    assert f"strips at {r['strip_force']:.0f} N ({r['strip_torque']['low']:.2f}-{r['strip_torque']['high']:.2f} N m)" in doc
    assert f"at most {r['torque_ceiling']:.2f} N m" in doc


def test_formulas_page_lists_the_new_sources():
    page = (ROOT / "docs" / "formulas.md").read_text()
    for name in ("torsion_shear_strain_rect", "torsion_snap_bar", "thread_radial_pressure", "boss_hoop_stress",
                 "screw_boss"):
        assert f"`{name}`" in page
    assert re.search(r"Bulten", page) and "Self-tapping screws for thermoplastics" in page


# ----------------------------------------------------------------------------- the pages' explorers

def _demo(page, tag):
    """The explorer on a page: its attributes and its still's alt text (tools/*-still.mjs check the JS side)."""
    found = re.search(rf"^<{tag}\b([^>]*)>([\s\S]*?)</{tag}>", (ROOT / "docs" / page).read_text(), re.M)
    assert found, f"no <{tag}> on docs/{page}"
    return dict(re.findall(r'([a-z-]+)="([^"]*)"', found.group(1))), re.search(r'alt="([^"]*)"', found.group(2)).group(1)


def test_the_torsion_explorer_on_the_snap_page_quotes_the_python():
    attrs, alt = _demo("compliant.md", "cad-torsion-snap")
    m = PRINTED[attrs["material"]]
    r = fx.torsion_snap_bar(float(attrs["length"]) * MM, float(attrs["width"]) * MM, float(attrs["thickness"]) * MM,
                            math.radians(float(attrs["twist"])), m.secant_upper_bound("along") * 1e6,
                            m.allowable("across", "repeated" in attrs), float(attrs["lever"]) * MM, int(attrs["bars"]))
    assert f"peak shear strain {100 * r['shear_strain']:.2f} %" in alt
    assert f"{100 * r['ratio']:.0f} % of the {100 * r['allowable_shear_strain']:.2f} % allowed across the layers" in alt
    assert ("a pass" if r["passes"] else "a fail") in alt and f"{r['force']:.2f} N at the lever" in alt
    text = (ROOT / "docs" / "compliant.md").read_text()
    assert f"uses {100 * r['ratio']:.0f} % of its allowable, and it fails past {math.degrees(r['permissible_twist']):.1f}°" in text


def test_the_boss_explorer_on_its_page_quotes_the_python():
    attrs, alt = _demo("screw-bosses.md", "cad-printed-boss")
    r = bosses.printed_boss(attrs["material"], attrs["size"], float(attrs["outside"]), float(attrs["engagement"]),
                            float(attrs["torque"]), attrs["axis"])
    assert f"clamp {r['preload']['low']:.0f} to {r['preload']['high']:.0f} N" in alt
    assert f"the thread strips at {r['strip_force']:.0f} N, at {r['strip_torque']['low']:.2f} to {r['strip_torque']['high']:.2f} N·m over the drive torque" in alt
    assert r["drive_torque"] is None and "makes no clamp" in alt
    measured = bosses.printed_boss(attrs["material"], attrs["size"], float(attrs["outside"]), float(attrs["engagement"]),
                                   float(attrs["torque"]), attrs["axis"], drive_torque_nm=0.2)
    text = (ROOT / "docs" / "screw-bosses.md").read_text()
    assert f"measured: {measured['preload']['low']:.0f} to {measured['preload']['high']:.0f} N" in text
    assert f"at most {r['torque_ceiling']:.2f} N·m" in alt and f"below {r['drive_torque_limit']:.2f} N·m" in alt
    assert f"hoop stress {r['hoop_stress'] / 1e6:.2f} MPa, {100 * r['hoop_ratio']:.0f} %" in alt
    assert ("a pass" if r["passes"] else "a fail") in alt
    # the page's "try these" numbers
    at = dict(attrs, outside=float(attrs["outside"]), engagement=float(attrs["engagement"]), torque=float(attrs["torque"]))
    run = lambda **k: bosses.printed_boss(**{"material": at["material"], "size": at["size"], "outside_mm": at["outside"],  # noqa: E731
                                            "engagement_mm": at["engagement"], "torque_nm": at["torque"], "axis": at["axis"], **k})
    assert not run(torque_nm=0.4)["torque_ok"]
    short = run(engagement_mm=3)
    assert f"strips at half the force ({short['strip_force']:.0f} N)" in text and f"falls to {short['torque_ceiling']:.2f} N·m" in text
    hf, copa = run(material="petg-bambu-hf"), run(material="copa-polymaker-dry")
    assert f"strips at {hf['strip_force']:.0f} N" in text and not hf["torque_ok"]
    assert f"CoPA strips at {copa['strip_force']:.0f} N and takes up to {copa['torque_ceiling']:.2f} N·m" in text
    thin = run(outside_mm=4)
    assert not thin["outside_ok"] and thin["hoop_ok"] and f"hoop stress is only {100 * thin['hoop_ratio']:.0f} %" in text
