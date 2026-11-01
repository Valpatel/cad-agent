"""cadagent.formulas against worked examples from the cited sources, or against derivations written out here.

Each test says which: a published value (with the source), or an independent derivation (numerical integration, the
direct stiffness method, a series solution, loop closure, thread geometry) that the closed form must match.
"""
import inspect
import itertools
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from cadagent import formulas as fx
from cadagent.thermal import heatsink
from cadagent.mechanical.compliant import snapfit

ROOT = Path(__file__).resolve().parents[1]
MM = 1e-3


# ----------------------------------------------------------------------------- the registry

def test_every_formula_states_its_units_limits_and_source():
    assert len(fx.REGISTRY) >= 30
    for name, f in fx.REGISTRY.items():
        fn = getattr(fx, name)
        params = set(inspect.signature(fn).parameters)
        assert params <= set(f.units), f"{name}: no unit for {sorted(params - set(f.units))}"
        assert f.limits and all(len(lim) > 10 for lim in f.limits), name
        assert any(f.source.startswith(s) for s in fx.SOURCES.values()), f"{name}: source is not in SOURCES"
        assert re.search(r"Section|Table|Eq\.|Chapter|profile|formula|area", f.source[len(f.source.split(",")[0]):]), \
            f"{name}: the citation does not say where in the source"
        assert f.summary and f.returns, name


def test_catalogue_is_plain_data_for_agents():
    import json
    cat = fx.catalogue()
    assert [c["name"] for c in cat] == sorted(fx.REGISTRY)
    json.dumps(cat)                                                        # serialisable as is
    assert {"name", "module", "summary", "units", "returns", "limits", "source"} <= set(cat[0])


def test_sources_are_cited_by_edition_not_quoted():
    for key, ref in fx.SOURCES.items():
        if key.startswith("iso"):
            assert re.search(r"ISO \d+-1:\d{4}", ref), key
        elif key in ("freudenstein", "gosselin", "goncalves"):                 # papers: a journal or proceedings, a year
            assert re.search(r"Transactions|Proceedings", ref) and re.search(r"\b(19|20)\d\d\b", ref), key
        elif key != "covestro":
            assert re.search(r"\d+(st|nd|rd|th) ed\.", ref) and re.search(r"\b(19|20)\d\d\b", ref), key


# ----------------------------------------------------------------------------- beams

def _beam_element(E, I, L):
    """Euler-Bernoulli beam element stiffness (deflection and rotation at each end): exact for end loads."""
    return E * I / L ** 3 * np.array([[12, 6 * L, -12, 6 * L], [6 * L, 4 * L * L, -6 * L, 2 * L * L],
                                      [-12, -6 * L, 12, -6 * L], [6 * L, 2 * L * L, -6 * L, 4 * L * L]])


@pytest.mark.parametrize("support,fixed", [
    ("cantilever", [0, 1]),                     # root clamped, load at the free end (node 2)
    ("guided", [0, 1, 5]),                      # root clamped, the loaded end slides without turning
    ("simply-supported", [0, 4]),               # pinned at both ends, load at the centre (node 1)
    ("fixed-fixed", [0, 1, 4, 5]),
])
def test_beam_stiffness_by_the_direct_stiffness_method(support, fixed):
    # Derivation: two exact beam elements, assembled and solved; the coefficient must be 3, 12, 48 or 192.
    E, I, L = 2.1e11, 3e-9, 0.25
    centre = support in ("simply-supported", "fixed-fixed")
    a = L / 2 if centre else L / 2                               # two elements either way
    K = np.zeros((6, 6))
    for e in range(2):
        K[2 * e:2 * e + 4, 2 * e:2 * e + 4] += _beam_element(E, I, a)
    load_dof = 2 if centre else 4
    free = [i for i in range(6) if i not in fixed]
    f = np.zeros(6)
    f[load_dof] = 1.0
    u = np.zeros(6)
    u[free] = np.linalg.solve(K[np.ix_(free, free)], f[free])
    assert fx.beam_stiffness(E, I, L, support) == pytest.approx(1.0 / u[load_dof], rel=1e-9)


def test_cantilever_tip_deflection_is_the_cantilever_stiffness():
    E, I, L, F = 2.0e9, fx.rect_second_moment(6 * MM, 1.6 * MM), 20 * MM, 1.5
    assert fx.rect_second_moment(6 * MM, 1.6 * MM) == pytest.approx(6e-3 * 1.6e-3 ** 3 / 12)
    assert fx.cantilever_tip_deflection(F, E, I, L) == pytest.approx(F / fx.beam_stiffness(E, I, L), rel=1e-12)
    with pytest.raises(ValueError):
        fx.beam_stiffness(E, I, L, "hinged")


def _numerical_shape(design, n=40000):
    """Derivation: integrate y'' = M / (E I(x)) twice from a clamped root (trapezoid rule) for an end load."""
    x = np.linspace(0.0, 1.0, n + 1)
    h = 1.0 - 0.5 * x if design == 2 else np.ones_like(x)
    b = 1.0 - 0.75 * x if design == 3 else np.ones_like(x)
    curvature = (1.0 - x) / (b * h ** 3)
    slope = np.concatenate([[0.0], np.cumsum((curvature[1:] + curvature[:-1]) / 2 * np.diff(x))])
    y = np.concatenate([[0.0], np.cumsum((slope[1:] + slope[:-1]) / 2 * np.diff(x))])
    return x, y


@pytest.mark.parametrize("design", [1, 2, 3])
def test_deflection_curves_match_numerical_integration(design):
    x, y = _numerical_shape(design)
    for i in range(0, len(x), 2000):
        assert fx.cantilever_shape(float(x[i]), design) == pytest.approx(y[i] / y[-1], abs=1e-8)
    assert fx.cantilever_shape(0.0, design) == 0.0 and fx.cantilever_shape(1.0, design) == pytest.approx(1.0)
    # the exact factor: y_tip = k eps_root L^2 / h, with eps_root = 6 F L / (E b h^2) and y'' scaled by 12 F L / E b h^3
    assert fx.cantilever_taper_factor(design) == pytest.approx(2.0 * y[-1], rel=1e-8)


def test_the_guides_table_1_factors_are_the_exact_integrals_rounded():
    # Covestro Table 1 prints 0.67, 1.09 and 0.86 (rectangle) and 1/3, 0.55, 0.43 (any section, y = k eps l^2 / c).
    exact = {d: fx.cantilever_taper_factor(d) for d in (1, 2, 3)}
    assert exact[1] == pytest.approx(2 / 3, rel=1e-12)
    for d in (1, 2, 3):
        assert round(exact[d], 2) == snapfit.DESIGN_K_RECT[d]
        assert snapfit.DESIGN_K[d] == pytest.approx(exact[d] / 2, abs=0.005)


@pytest.mark.parametrize("design", [1, 2, 3])
def test_strain_peaks_at_the_root_and_follows_M_c_over_I(design):
    xs = np.linspace(0, 1, 201)
    prof = [fx.cantilever_strain_profile(float(x), design) for x in xs]
    assert prof[0] == 1.0 and prof[-1] == 0.0 and max(prof) == 1.0
    # derivation: eps = M c / (E I) = 6 F (L - x) / (E b(x) h(x)^2)
    h = [fx.cantilever_thickness_profile(float(x), design) for x in xs]
    b = [1.0 - 0.75 * x if design == 3 else 1.0 for x in xs]
    for x, p, hh, bb in zip(xs, prof, h, b):
        assert p == pytest.approx((1.0 - x) / (bb * hh * hh), abs=1e-12)
    with pytest.raises(ValueError):
        fx.cantilever_shape(1.5, design)


def test_covestro_example_I_in_si_units():
    # Covestro guide, Example I: PC, l 19 mm, b 9.5 mm, h 3.28 mm (tapered, design 2), undercut 2.4 mm, Es 1,815 MPa
    # at the 2 % design strain; the guide's deflection force is 32.5 N (also reproduced in tests/test_snapfit.py).
    eps = fx.snap_root_strain(19 * MM, 3.28 * MM, 2.4 * MM, design=2)
    assert eps == pytest.approx(0.02, abs=0.0002)
    assert fx.snap_deflection_force(19 * MM, 9.5 * MM, 3.28 * MM, 0.02, 1815e6) == pytest.approx(32.5, abs=0.1)
    arm = fx.snap_arm(19 * MM, 3.28 * MM, 9.5 * MM, 2.4 * MM, 1815e6, 0.04, design=2)
    assert arm["passes"] and arm["ratio"] == pytest.approx(0.5, abs=0.01)     # the guide designs to half of 4 %
    assert not arm["small_deflection"]                                         # 2.4 / 19 = 0.13, as the guide warns
    assert arm["permissible_deflection"] == pytest.approx(2 * 2.4 * MM, rel=0.01)
    assert arm["stiffness"] == pytest.approx(arm["force"] / (2.4 * MM))
    # P / y is the same at any deflection, so an arm at rest reports the same stiffness, b h^3 Es / (6 k L^3)
    rest = fx.snap_arm(19 * MM, 3.28 * MM, 9.5 * MM, 0.0, 1815e6, 0.04, design=2)
    assert rest["strain"] == 0.0 and rest["force"] == 0.0 and rest["passes"]
    k = snapfit.DESIGN_K_RECT[2]
    assert rest["stiffness"] == pytest.approx(arm["stiffness"], rel=1e-12)
    assert rest["stiffness"] == pytest.approx(9.5 * MM * (3.28 * MM) ** 3 * 1815e6 / (6 * k * (19 * MM) ** 3), rel=1e-12)


def test_snap_arm_agrees_with_cad_agent_snapfit():
    sec = snapfit.rect_section(6.0, 1.6)                                     # snapfit in mm and MPa
    row = snapfit.check_cantilever(length=14, section=sec, undercut=0.5, strain_allow=0.012, secant_mpa=2703,
                                   root_radius=0.8)
    arm = fx.snap_arm(14 * MM, 1.6 * MM, 6 * MM, 0.5 * MM, 2703e6, 0.012)
    assert arm["strain"] == pytest.approx(row["strain"], rel=1e-12)
    assert arm["force"] == pytest.approx(row["deflection_force_n"], rel=1e-12)
    assert arm["passes"] == row["rows"][0]["pass"]


# ----------------------------------------------------------------------------- torsion

def _saint_venant_rect(w, t, terms=200):
    """Derivation: the exact series for a w x t rectangle, K = w t^3 / 3 [1 - 192 t / (pi^5 w) sum tanh(n pi w / 2t)
    / n^5, n odd] (Timoshenko and Goodier, Theory of Elasticity, the rectangular bar in torsion)."""
    s = sum(math.tanh(n * math.pi * w / (2 * t)) / n ** 5 for n in range(1, 2 * terms, 2))
    return w * t ** 3 / 3 * (1 - 192 * t / (math.pi ** 5 * w) * s)


@pytest.mark.parametrize("aspect,rel", [(1, 0.002), (1.145, 0.005), (1.5, 0.002), (2, 0.002), (3, 0.002), (4, 0.002),
                                        (6, 0.002), (10, 0.002), (50, 0.002)])
def test_rectangular_torsion_constant_against_the_series(aspect, rel):
    # Roark's polynomial is furthest from the series at aspect 1.145, 0.49 % low (scanned from 1 to 50); the limits
    # say "within 0.5 %".
    w, t = aspect * 2 * MM, 2 * MM
    assert fx.torsion_constant_rect(w, t) == pytest.approx(_saint_venant_rect(w, t), rel=rel)
    assert fx.torsion_constant_rect(t, w) == fx.torsion_constant_rect(w, t)          # either order


@pytest.mark.parametrize("aspect,alpha,beta", [(1.0, 0.208, 0.141), (1.5, 0.231, 0.196), (2.0, 0.246, 0.229),
                                               (3.0, 0.267, 0.263), (6.0, 0.299, 0.299), (10.0, 0.312, 0.312)])
def test_rectangular_torsion_against_the_tabulated_coefficients(aspect, alpha, beta):
    # Shigley, 10th ed., Section 3-12 (Torsion): tau_max = T / (alpha b c^2), theta = T l / (beta b c^3 G) for a
    # b x c rectangle; the table's three-figure coefficients.
    b, c, T = aspect * 1.0, 1.0, 1.0
    assert fx.torsion_shear_stress_rect(T, b, c) == pytest.approx(T / (alpha * b * c * c), rel=0.005)
    assert fx.torsion_constant_rect(b, c) == pytest.approx(beta * b * c ** 3, rel=0.006)


def test_round_torsion_bar_and_the_guides_torsion_snap():
    r, L, G = 1.5 * MM, 12 * MM, 0.8e9
    J = fx.torsion_constant_round(r)
    assert J == pytest.approx(math.pi * r ** 4 / 2)
    assert fx.torsion_constant_round(2 * MM, 1 * MM) == pytest.approx(math.pi * (16 - 1) * MM ** 4 / 2)
    T = 0.05
    theta = fx.torsion_bar_twist(T, L, G, J)
    assert fx.torsion_bar_stiffness(L, G, J) * theta == pytest.approx(T)
    assert fx.torsion_shear_stress_round(T, r) == pytest.approx(G * r * theta / L)      # tau = G gamma, gamma = r theta / L
    # The Covestro torsion snap (snapfit.torsion_snap, mm and MPa) is the same mechanics: two bars at shear strain gamma
    # carry the lever force P with P * lever = 2 K G gamma / r.
    snap = snapfit.torsion_snap(bar_length=12, bar_radius=1.5, strain=0.02, secant_mpa=2000, lever_mm=10)
    g = fx.shear_modulus(2000e6, snapfit.POISSON_PLASTICS)
    assert snap["shear_modulus_mpa"] * 1e6 == pytest.approx(g)
    twist = math.radians(snap["twist_deg"])
    assert snap["force_n"] * 10 * MM == pytest.approx(2 * fx.torsion_bar_stiffness(L, g, J) * twist, rel=1e-9)
    with pytest.raises(ValueError):
        fx.torsion_constant_round(1 * MM, 2 * MM)


# ----------------------------------------------------------------------------- springs

def test_spring_rate_from_the_wire_as_a_torsion_bar():
    # Derivation: the wire is a torsion bar of length pi D Na, twisted by F D / 2; the load point moves (D / 2) theta.
    d, D, Na, G, F = 1.0 * MM, 10 * MM, 8, 79.3e9, 5.0
    theta = fx.torsion_bar_twist(F * D / 2, math.pi * D * Na, G, fx.torsion_constant_round(d / 2))
    assert fx.spring_rate(d, D, Na, G) == pytest.approx(F / (D / 2 * theta), rel=1e-12)
    assert fx.spring_index(D, d) == 10


@pytest.mark.parametrize("C", [4, 6, 8, 10, 12])
def test_bergstrasser_and_wahl_agree_within_two_percent(C):
    # Cross-check against the Wahl factor (4C - 1) / (4C - 4) + 0.615 / C (Shigley 10th ed., Section 10-2, Eq. 10-4):
    # the two curvature corrections agree within 1.5 % over the recommended range, Bergstrasser's slightly lower.
    wahl = (4 * C - 1) / (4 * C - 4) + 0.615 / C
    assert fx.bergstrasser_factor(C) == pytest.approx(wahl, rel=0.015)
    assert fx.bergstrasser_factor(C) < wahl
    assert fx.bergstrasser_factor(C) > 1 + 0.5 / C                        # always above the direct-shear factor alone


def test_spring_stress_is_torsion_plus_curvature():
    d, D, F = 0.8 * MM, 6 * MM, 4.0
    plain = fx.torsion_shear_stress_round(F * D / 2, d / 2)              # 8 F D / pi d^3
    assert plain == pytest.approx(8 * F * D / (math.pi * d ** 3))
    assert fx.spring_shear_stress(F, d, D) == pytest.approx(fx.bergstrasser_factor(D / d) * plain)


# ----------------------------------------------------------------------------- screws

def test_preload_and_torque_are_inverses_with_the_default_nut_factor():
    assert fx.preload_from_torque(0.6, 3 * MM) == pytest.approx(0.6 / (0.2 * 3e-3))
    assert fx.torque_for_preload(fx.preload_from_torque(2.0, 5 * MM, 0.18), 5 * MM, 0.18) == pytest.approx(2.0)
    assert fx.NUT_FACTORS["unstated"] == fx.NUT_FACTORS["zinc-plated"] == 0.2


@pytest.mark.parametrize("d,p", [(3, 0.5), (4, 0.7), (5, 0.8), (6, 1.0), (8, 1.25), (10, 1.5), (16, 2.0), (20, 2.5)])
def test_nut_factor_from_friction_is_about_0_2(d, p):
    # Shigley 10th ed., Section 8-8: with thread and collar friction both 0.15, Eq. (8-26) gives K close to 0.20 for
    # any size, which is where T = 0.2 F d comes from.
    assert fx.nut_factor(d * MM, p * MM, 0.15, 0.15) == pytest.approx(0.20, abs=0.012)
    assert fx.nut_factor(d * MM, p * MM, 0.10, 0.10) < fx.nut_factor(d * MM, p * MM, 0.15, 0.15)


@pytest.mark.parametrize("d,p,area", [(3, 0.5, 5.03), (4, 0.7, 8.78), (5, 0.8, 14.2), (6, 1.0, 20.1), (8, 1.25, 36.6),
                                      (10, 1.5, 58.0), (12, 1.75, 84.3), (16, 2.0, 157.0)])
def test_tensile_stress_area_against_the_tabulated_values(d, p, area):
    # ISO 898-1 (and Shigley 10th ed., Table 8-1): tabulated nominal stress areas in mm^2, coarse pitch.
    assert fx.tensile_stress_area(d * MM, p * MM) * 1e6 == pytest.approx(area, rel=0.003)


def test_thread_shear_areas_from_the_basic_profile():
    # Derivation from the ISO 68-1 basic profile (H = 0.866025 p, 60 degree flanks): a tooth's width along the axis
    # at a diameter D is p/2 at the pitch diameter and changes by tan 30 per unit of radius. The screw's teeth shear
    # at the hole's minor diameter D1, the hole's teeth at the screw's major diameter d.
    d, p, Le = 4.0, 0.7, 6.0
    H = math.sqrt(3) / 2 * p
    d2, D1 = d - 0.75 * H, d - 1.25 * H

    def external_width(D):        # screw tooth width at diameter D
        return p / 2 + 2 * (d2 - D) / 2 * math.tan(math.radians(30))

    w_ext = external_width(D1)    # the screw's material at D1
    w_int = p - external_width(d)  # the hole's material at d
    assert w_ext == pytest.approx(0.75 * p, rel=1e-9) and w_int == pytest.approx(0.875 * p, rel=1e-9)
    areas = fx.thread_shear_areas(d * MM, p * MM, Le * MM)
    assert areas["external"] == pytest.approx(math.pi * D1 * Le * w_ext / p * MM ** 2, rel=1e-6)
    assert areas["internal"] == pytest.approx(math.pi * d * Le * w_int / p * MM ** 2, rel=1e-6)
    # a screw in plastic: the plastic's threads (internal) strip at the plastic's shear strength times its area
    assert fx.thread_strip_force(d * MM, p * MM, Le * MM, 30e6) == pytest.approx(areas["internal"] * 30e6)
    assert fx.thread_strip_force(d * MM, p * MM, Le * MM, 30e6, side="external") < \
        fx.thread_strip_force(d * MM, p * MM, Le * MM, 30e6)
    with pytest.raises(ValueError):
        fx.thread_strip_force(d * MM, p * MM, Le * MM, 30e6, side="both")


# ----------------------------------------------------------------------------- linkages

def _circle_solution(a, b, c, d, t2):
    """Derivation: the coupler-rocker joint is where a circle of radius b about the crank pin meets a circle of
    radius c about the output pivot (d, 0)."""
    A = np.array([a * math.cos(t2), a * math.sin(t2)])
    O4 = np.array([d, 0.0])
    dist = np.linalg.norm(O4 - A)
    if dist > b + c or dist < abs(b - c):
        return []
    x = (dist ** 2 + b * b - c * c) / (2 * dist)
    yy = math.sqrt(max(b * b - x * x, 0.0))
    e = (O4 - A) / dist
    n = np.array([-e[1], e[0]])
    out = []
    for sign in (1, -1):
        B = A + x * e + sign * yy * n
        out.append((math.atan2(*(B - A)[::-1]), math.atan2(*(B - O4)[::-1])))
    return out


@pytest.mark.parametrize("links", [(40, 120, 80, 100), (30, 70, 60, 80), (60, 90, 80, 30), (60, 90, 40, 100),
                                   (3, 3, 4, 4), (10, 10, 25, 25), (3, 3 * (1 + 1e-9), 4, 4)])   # two kites, a near-kite
def test_fourbar_positions_close_the_loop_and_match_the_circle_construction(links):
    a, b, c, d = links
    solved = 0
    for deg in range(0, 360, 7):
        t2 = math.radians(deg)
        both = [fx.fourbar_angles(a, b, c, d, t2, crossed=x) for x in (False, True)]
        circles = _circle_solution(a, b, c, d, t2)
        if not circles:
            assert both == [None, None]
            continue
        solved += 1
        for t3, t4 in both:
            z = a * complex(math.cos(t2), math.sin(t2)) + b * complex(math.cos(t3), math.sin(t3)) \
                - c * complex(math.cos(t4), math.sin(t4)) - d
            assert abs(z) < 1e-9 * d
        def ang(u, v):
            return abs(math.atan2(math.sin(u - v), math.cos(u - v)))
        for sol in both:          # each branch is one of the two circle intersections
            assert min(ang(sol[0], cs[0]) + ang(sol[1], cs[1]) for cs in circles) < 1e-9
        assert ang(both[0][1], both[1][1]) > 1e-6 or len({round(cs[1], 9) for cs in circles}) == 1
        mu = fx.transmission_angle(a, b, c, d, t2)
        between = ang(both[0][0], both[0][1])
        assert mu == pytest.approx(min(between, math.pi - between), abs=1e-9)
    assert solved


def _loop_error(a, b, c, d, t2, t3, t4):
    return abs(a * complex(math.cos(t2), math.sin(t2)) + b * complex(math.cos(t3), math.sin(t3))
               - c * complex(math.cos(t4), math.sin(t4)) - d)


def _coupler_side(a, b, c, d, t2, t4):
    """Which side of the diagonal from the crank pin A to the output pivot O4 the coupler-rocker pin B is on, as the
    sine of the angle from A->O4 to A->B: positive (left) on the open branch, negative on the crossed one, 0 where the
    two assemblies meet. None where A sits on O4, so the diagonal has no direction."""
    ax, ay = a * math.cos(t2), a * math.sin(t2)
    bx, by = d + c * math.cos(t4), c * math.sin(t4)
    e = math.hypot(d - ax, ay)
    if e < 1e-6 * max(a, b, c, d):
        return None
    return ((d - ax) * (by - ay) + ay * (bx - ax)) / (e * b)


@pytest.mark.parametrize("links", [(3, 3, 4, 4), (10, 10, 25, 25), (7, 7, 2, 2), (3 * MM, 3 * MM, 4 * MM, 4 * MM),
                                   (3, 3 * (1 + 1e-9), 4, 4), (3 * (1 - 1e-9), 3, 4, 4), (5, 5, 5, 5),
                                   # change points (S + L = P + Q) that turn fully: parallelograms (a = c, b = d) and a
                                   # crank-rocker with a + b = c + d; the lengths 0.03 and so on are not exact in binary
                                   (5, 2, 5, 2), (0.03, 0.07, 0.03, 0.07), (0.02, 0.05, 0.03, 0.04)])
def test_fourbar_kites_and_change_points_close_at_every_input_angle(links):
    # A kite (a = b, c = d) has A = 0 in the quadratic at every input angle: the root must not come from 0 / 0. At a
    # change point the two assemblies meet at 0 or 180 degrees, so the discriminant is 0 there and round-off can push it
    # below. Neither may hide a position that closes. Every 0.1 degree, both branches, and every 1e-9 rad for 5e-8 rad
    # either side of 0 and 180 degrees (where the coupler pin sits on the input pivot, or the links lie flat).
    a, b, c, d = links
    longest = max(links)
    assert fx.grashof(*links)["crank_rotates"]                             # the crank turns fully, so every angle closes
    angles = [math.radians(tenth / 10) for tenth in range(3600)]
    angles += [base + k * 1e-9 for base in (0.0, math.pi) for k in range(-50, 51)]
    for t2 in angles:
        both = [fx.fourbar_angles(a, b, c, d, t2, crossed=crossed) for crossed in (False, True)]
        for crossed, got in zip((False, True), both):
            assert got is not None, (t2, crossed)
            assert _loop_error(a, b, c, d, t2, *got) < 1e-12 * longest, (t2, crossed)
            # the branch asked for: open on the left of the diagonal, crossed on the right; where the two meet (the
            # pin on the diagonal, to round-off), both branches give that one position
            side = _coupler_side(a, b, c, d, t2, got[1])
            if side is None:                                              # crank pin on the output pivot
                continue
            if abs(side) > 1e-6:
                assert (side < 0) == crossed, (t2, crossed, side)
            else:
                assert _loop_error(a, b, c, d, t2, *both[0]) < 1e-12 * longest and \
                    abs(math.remainder(both[0][1] - both[1][1], 2 * math.pi)) < 1e-6, (t2, both)
        assert fx.transmission_angle(a, b, c, d, t2) is not None, t2
    t3, t4 = fx.fourbar_angles(3, 3, 4, 4, 0.0)
    assert abs(math.cos(t4) + 1) < 1e-15                                  # the rocker folds back onto the ground link


def test_fourbar_parallelogram_lies_flat_at_0_degrees():
    # a = c = 5, b = d = 2 with the crank along the ground: the rocker lies along it too and the coupler joins their
    # ends, one position for both branches, with the coupler in line with the rocker (mu = 0)
    for crossed in (False, True):
        assert fx.fourbar_angles(5, 2, 5, 2, 0.0, crossed=crossed) == (0.0, 0.0)
    assert fx.transmission_angle(5, 2, 5, 2, 0.0) == 0.0


@pytest.mark.parametrize("links", [(100, 80, 70, 60), (80, 40, 120, 100), (60, 30, 50, 70), (0.05, 0.02, 0.06, 0.04)])
def test_fourbar_closes_at_the_limits_of_the_input(links):
    # A crank that cannot turn fully stops where coupler and rocker line up: there the diagonal e from the crank pin
    # to the output pivot is b + c or |b - c|, the linkage closes in one position (both branches meet) and the
    # transmission angle is 0. Round-off at that angle used to return None for about half the branches.
    a, b, c, d = links
    longest = max(links)
    assert not fx.grashof(*links)["crank_rotates"]
    limits = [math.acos(cos) for span in (b + c, abs(b - c))
              for cos in [(a * a + d * d - span * span) / (2 * a * d)] if abs(cos) <= 1]
    assert limits
    for t0 in limits:
        for t2 in (t0, -t0):
            for crossed in (False, True):
                got = fx.fourbar_angles(a, b, c, d, t2, crossed=crossed)
                assert got is not None and _loop_error(a, b, c, d, t2, *got) < 1e-12 * longest, (t2, crossed)
            assert fx.transmission_angle(a, b, c, d, t2) == pytest.approx(0.0, abs=1e-6), t2
    # well past a limit the links still cannot close
    assert fx.fourbar_angles(a, b, c, d, limits[0] + 1e-3) is None or fx.fourbar_angles(a, b, c, d, limits[0] - 1e-3) is None


@pytest.mark.parametrize("links", [(100, 80, 70, 60), (80, 40, 120, 100), (60, 30, 50, 70), (0.05, 0.02, 0.06, 0.04)])
def test_fourbar_tolerance_is_tight_on_both_sides(links):
    # The other side of the closing test above: set the input so the diagonal e is just past b + c or |b - c|.
    # Open by 1e-9 of the longest link, ten thousand times the tolerance, the links cannot close: None. Inside by the
    # same amount, or open by a tenth of the tolerance, they close. A looser _CLOSE, or a tolerance on e squared that
    # grows with the links, lets the open loop through.
    a, b, c, d = links
    longest = max(links)
    checked = 0
    for span, outward in ((b + c, 1), (abs(b - c), -1)):
        for gap, closes in ((1e-9, False), (-1e-9, True), (1e-13, True)):
            e = span + outward * gap * longest
            cos = (a * a + d * d - e * e) / (2 * a * d)
            if abs(cos) > 1:
                continue
            t2 = math.acos(cos)
            for crossed in (False, True):
                got = fx.fourbar_angles(a, b, c, d, t2, crossed=crossed)
                assert (got is not None) == closes, (span, gap, crossed, got)
            assert (fx.transmission_angle(a, b, c, d, t2) is not None) == closes, (span, gap)
            checked += 1
    assert checked >= 3


def test_fourbar_an_open_loop_stays_open_across_a_short_diagonal():
    # At theta2 = 0 the diagonal is d - a = 2e-6 and |b - c| = 2.2e-6: open by 2e-7 of the longest link. A tolerance on
    # e squared lets this through, since it is a large tolerance on e when e is short (from the review of #146).
    for crossed in (False, True):
        assert fx.fourbar_angles(1, 1, 1 - 2.2e-6, 1 + 2e-6, 0.0, crossed=crossed) is None
    assert fx.transmission_angle(1, 1, 1 - 2.2e-6, 1 + 2e-6, 0.0) is None

def test_fourbar_norton_example_4_1():
    # Norton, Design of Machinery, Example 4-1: a = 40, b = 120, c = 80, d = 100 at theta2 = 40 degrees.
    open_, crossed = (fx.fourbar_angles(40, 120, 80, 100, math.radians(40), crossed=x) for x in (False, True))
    assert [math.degrees(v) for v in open_] == pytest.approx([20.298, 57.325], abs=5e-4)
    assert [math.degrees(v) for v in crossed] == pytest.approx([-60.978, -98.005], abs=5e-4)


def test_grashof_classes():
    # crank-rocker (S + L < P + Q, the crank shortest), the input turns fully: every angle closes
    assert fx.grashof(40, 120, 80, 100) == {"grashof": True, "kind": "grashof", "crank_rotates": True,
                                            "inversion": "crank-rocker"}
    assert all(fx.fourbar_angles(40, 120, 80, 100, math.radians(t)) for t in range(360))
    # a double rocker (Grashof, coupler shortest): the input cannot turn fully
    assert fx.grashof(80, 40, 120, 100)["crank_rotates"] is False
    assert any(fx.fourbar_angles(80, 40, 120, 100, math.radians(t)) is None for t in range(360))
    # non-Grashof (S + L > P + Q): no link turns fully
    assert fx.grashof(100, 80, 70, 60) == {"grashof": False, "kind": "non-grashof", "crank_rotates": False,
                                           "inversion": "triple-rocker"}
    assert any(fx.fourbar_angles(100, 80, 70, 60, math.radians(t)) is None for t in range(360))
    # parallelogram: S + L = P + Q, a change-point linkage
    assert fx.grashof(50, 100, 50, 100)["kind"] == "change-point"
    assert fx.grashof(50, 100, 50, 100)["inversion"] == "change-point"
    # the four Grashof inversions, by the shortest link (Norton, Chapter 2): the same four lengths each time
    for links, name in (((40, 120, 80, 100), "crank-rocker"), ((80, 100, 120, 40), "double-crank"),
                        ((80, 100, 40, 120), "rocker-crank"), ((80, 40, 120, 100), "double-rocker")):
        g = fx.grashof(*links)
        assert g["kind"] == "grashof" and g["inversion"] == name, links
        assert g["crank_rotates"] == (name in ("crank-rocker", "double-crank")), links


def _closes_between(limits, t2):
    """Whether the input angle t2 lies in the range fourbar_input_limits gives: folded <= |t2| <= stretched."""
    t = abs(math.remainder(t2, 2 * math.pi))
    lo = limits["folded"] if limits["folded"] is not None else 0.0
    hi = limits["stretched"] if limits["stretched"] is not None else math.pi
    return limits["closes"] and lo <= t <= hi


def test_fourbar_input_limits_are_where_the_links_stop_closing():
    # Every four-bar with whole-number links from 1 to 6 (and a millimetre copy of each, whose lengths binary cannot
    # hold): the input turns fully exactly when grashof says the crank rotates, and fourbar_angles closes exactly
    # inside the limits, every 3 degrees, away from the limits themselves.
    checked = limited = 0
    for a, b, c, d in itertools.product(range(1, 7), repeat=4):
        for scale in (1, MM):
            links = (a * scale, b * scale, c * scale, d * scale)
            lim = fx.fourbar_input_limits(*links)
            assert lim["full_turn"] == fx.grashof(*links)["crank_rotates"], links
            edges = [v for v in (lim["folded"], lim["stretched"]) if v is not None]
            limited += bool(edges)
            for deg in range(-180, 180, 3):
                t2 = math.radians(deg)
                if any(abs(abs(t2) - e) < 1e-6 for e in edges):
                    continue
                want = _closes_between(lim, t2)
                for crossed in (False, True):
                    assert (fx.fourbar_angles(*links, t2, crossed=crossed) is not None) == want, (links, deg, lim)
                assert (fx.transmission_angle(*links, t2) is not None) == want, (links, deg)
                checked += 1
    assert checked > 100_000 and limited > 500


# The branches meet at a limit to the square root of round-off (a double root), about 1e-8 rad. Across a diagonal of
# 2e-6 between links of 1 (the last case, folded near 0 degrees) the pin's place is that much less certain.
@pytest.mark.parametrize("links,meet", [((100, 80, 70, 60), 1e-7), ((80, 40, 120, 100), 1e-7), ((60, 30, 50, 70), 1e-7),
                                        ((0.05, 0.02, 0.06, 0.04), 1e-7), ((80, 100, 40, 120), 1e-7),
                                        ((1, 1, 1 - 2.2e-6, 1 + 2e-6), 1e-4)])
def test_fourbar_input_limits_lock_the_linkage(links, meet):
    # At each limit coupler and rocker lie in one line: the links close in one position (both branches meet), the
    # transmission angle is 0, and the circle construction's two intersections meet. 1e-7 rad further out, nothing
    # closes; 1e-7 rad inside, both branches do. The angle is the law of cosines' acos, in half angles.
    a, b, c, d = links
    lim = fx.fourbar_input_limits(*links)
    assert lim["closes"] and not lim["full_turn"]
    for name, span, outward in (("folded", abs(b - c), -1), ("stretched", b + c, 1)):
        t0 = lim[name]
        if t0 is None:
            continue
        assert 0 < t0 < math.pi
        assert t0 == pytest.approx(math.acos((a * a + d * d - span * span) / (2 * a * d)), abs=1e-7)
        for sign in (1, -1):
            t2 = sign * t0
            both = [fx.fourbar_angles(a, b, c, d, t2, crossed=x) for x in (False, True)]
            assert all(got is not None and _loop_error(a, b, c, d, t2, *got) < 1e-9 * max(links) for got in both)
            assert abs(math.remainder(both[0][1] - both[1][1], 2 * math.pi)) < meet
            assert fx.transmission_angle(a, b, c, d, t2) == pytest.approx(0.0, abs=meet)
            beyond, inside = sign * (t0 + outward * 1e-7), sign * (t0 - outward * 1e-7)
            assert all(fx.fourbar_angles(a, b, c, d, beyond, crossed=x) is None for x in (False, True)), (name, sign)
            assert not _circle_solution(a, b, c, d, beyond) and len(_circle_solution(a, b, c, d, inside)) == 2
            assert all(fx.fourbar_angles(a, b, c, d, inside, crossed=x) is not None for x in (False, True))


def test_fourbar_input_limits_of_the_inversions():
    # A crank-rocker and a double crank turn fully; a triple rocker stops on one side (its input swings through 0);
    # a double rocker and a rocker-crank stop on both, so the input has two mirror-image ranges; links that cannot
    # make a loop at all (one longer than the other three together) close nowhere.
    assert fx.fourbar_input_limits(40, 120, 80, 100) == {"closes": True, "full_turn": True, "folded": None,
                                                         "stretched": None}
    assert fx.fourbar_input_limits(80, 100, 120, 40)["full_turn"]
    tri = fx.fourbar_input_limits(100, 80, 70, 60)
    assert tri["folded"] is None and math.degrees(tri["stretched"]) == pytest.approx(137.874, abs=1e-3)
    dr = fx.fourbar_input_limits(80, 40, 120, 100)
    assert [round(math.degrees(dr[k]), 3) for k in ("folded", "stretched")] == [51.318, 125.100]
    assert fx.fourbar_input_limits(1, 1, 1, 10) == {"closes": False, "full_turn": False, "folded": None,
                                                    "stretched": None}
    # change points pass their in-line position without stopping: a parallelogram, and a + b = c + d
    for links in ((5, 2, 5, 2), (0.03, 0.07, 0.03, 0.07), (0.02, 0.05, 0.03, 0.04)):
        assert fx.fourbar_input_limits(*links)["full_turn"], links


# ----------------------------------------------------------------------------- heat and air

def test_layered_wall_with_films():
    # Derivation (Incropera Section 3.1.3): resistances in series, the same heat flow through each, so each layer's
    # temperature drop is q R. 2 mm PETG (k 0.2) and 1 mm aluminium (k 200) between films of 10 and 25 W/m2K.
    A = 0.01
    out = fx.wall_heat_flow([(2 * MM, 0.2), (1 * MM, 200.0)], A, t_hot=60.0, t_cold=25.0, h_hot=10.0, h_cold=25.0)
    rs = [1 / (10 * A), 2e-3 / (0.2 * A), 1e-3 / (200 * A), 1 / (25 * A)]
    assert out["resistance"] == pytest.approx(sum(rs))
    q = 35.0 / sum(rs)
    assert out["heat_flow"] == pytest.approx(q) and out["flux"] == pytest.approx(q / A)
    expected = [60 - q * rs[0], 60 - q * sum(rs[:2]), 60 - q * sum(rs[:3])]
    assert out["surfaces"] == pytest.approx(expected)
    bare = fx.wall_heat_flow([(2 * MM, 0.2)], A, 60.0, 25.0)            # faces held at the two temperatures
    assert bare["surfaces"] == pytest.approx([60.0, 25.0])
    assert bare["resistance"] == pytest.approx(fx.wall_resistance(2 * MM, 0.2, A))
    assert fx.film_resistance(10.0, A) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        fx.wall_heat_flow([], A, 60.0, 25.0)
    # h = 0 is an insulated face, not a face held at its temperature: refused, as is a negative film coefficient
    for films in ({"h_hot": 0.0}, {"h_cold": 0.0}, {"h_hot": -5.0}, {"h_cold": float("nan")}):
        with pytest.raises(ValueError, match="insulated"):
            fx.wall_heat_flow([(2 * MM, 0.2)], A, 60.0, 25.0, **films)


def test_fan_against_a_quadratic_system_is_the_quadratic_root():
    # Derivation: a straight fan line p = p0 (1 - Q / Qf) against k Q^2 has one positive root.
    p0, qf, k = 15.2, 38.9 / 3600, 2.0e6
    op = fx.fan_operating_point(fx.fan_curve_line(p0, qf), k)
    a, b, c = k, p0 / qf, -p0
    q = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    assert op["flow"] == pytest.approx(q, rel=1e-12) and op["pressure"] == pytest.approx(k * q * q, rel=1e-12)
    assert op["stable"] and len(op["intersections"]) == 1
    assert fx.system_coefficient(op["pressure"], op["flow"]) == pytest.approx(k)


def test_fan_operating_point_matches_the_heatsink_solver():
    # Reuse, not fork: cadagent.thermal.heatsink.operating_point (bisection on the same straight fan line) must find the same
    # point for a system that is purely quadratic.
    k = 3.0e6

    class Quadratic:
        def pressure_drop(self, q):
            return k * q * q

        def channel_velocity(self, q):
            return 0.0

    fan = heatsink.FanCurve(dp0_pa=15.2, q_free_m3h=38.9)
    ref = heatsink.operating_point(Quadratic(), fan)
    op = fx.fan_operating_point(fx.fan_curve_line(fan.dp0_pa, fan.q_free_m3h / 3600), k)
    assert op["flow"] == pytest.approx(ref["q_m3s"], rel=1e-9)
    assert op["pressure"] == pytest.approx(ref["dp_pa"], rel=1e-6)


def test_fan_curve_with_a_stall_dip_is_flagged_unstable():
    # An axial fan's curve sags in the middle: a flat system crosses it three times.
    curve = [(0.0, 20.0), (0.004, 8.0), (0.005, 14.0), (0.010, 6.0), (0.012, 0.0)]
    op = fx.fan_operating_point(curve, k=0.0, r=2500.0)                     # a linear (laminar) system
    assert len(op["intersections"]) == 3 and not op["stable"]
    assert op["flow"] == max(q for q, _ in op["intersections"])
    for q, p in op["intersections"]:
        assert p == pytest.approx(np.interp(q, *zip(*curve)), rel=1e-9) and p == pytest.approx(2500.0 * q)
    with pytest.raises(ValueError):
        fx.fan_operating_point([(0.0, 10.0)], 1e6)
    with pytest.raises(ValueError):
        fx.fan_operating_point([(0.0, 10.0), (0.01, 9.0)], 1.0)               # never crosses within the curve


# ----------------------------------------------------------------------------- the browser port and the docs

def test_golden_vectors_and_demo_materials_are_current():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "formula_vectors.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_docs_page_lists_every_formula_and_its_source():
    page = (ROOT / "docs" / "formulas.md").read_text()
    for name in fx.REGISTRY:
        assert f"`{name}`" in page, f"docs/formulas.md does not list {name}"
    for ref in ("Roark", "Shigley", "Covestro", "Norton", "Freudenstein", "Gosselin", "COBEM", "Incropera", "White",
                "ISO 68-1", "ISO 898-1"):
        assert ref in page



def test_the_demo_on_docs_compliant_starts_from_what_the_python_computes():
    # The page's <cad-cantilever> attributes, run through cadagent.formulas, give the root strain its still's alt text
    # quotes (tools/cantilever-still.mjs checks the same from the browser side), and the page's claim that the arm
    # passes flat and fails upright holds.
    from cadagent.mechanical.compliant.allowables import PRINTED
    page = (ROOT / "docs" / "compliant.md").read_text()
    tag = re.search(r"<cad-cantilever\b([^>]*)>([\s\S]*?)</cad-cantilever>", page)
    assert tag, "docs/compliant.md has no <cad-cantilever> demo"
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag.group(1)))
    m = PRINTED[attrs["material"]]
    args = [float(attrs[k]) * MM for k in ("length", "thickness", "width", "deflection")]

    def arm(direction):
        return fx.snap_arm(*args, m.secant_upper_bound(direction) * 1e6, m.allowable(direction), int(attrs["design"]))

    flat, upright = arm("along"), arm("across")
    assert attrs["direction"] == "along" and flat["passes"] and not upright["passes"]
    assert f"{flat['strain'] * 100:.2f} %" in tag.group(2) and f"{flat['force']:.2f} N" in tag.group(2)
    assert f"{round(flat['ratio'] * 100)} %" in page and f"{round(upright['ratio'] * 100)} %" in page
    assert 'src="img/compliant/cantilever-explorer.svg"' in tag.group(2)          # the still before the script loads


def test_the_fourbar_demo_and_its_pages_say_what_the_python_computes():
    # docs/linkages.md and docs/formulas.md show <cad-fourbar>: its attributes, run through cadagent.formulas, give the
    # class and the lowest transmission angle the still's alt text quotes (tools/fourbar-still.mjs checks the same from
    # the browser side), and the page's worked numbers (the limits of the linkages it suggests) are the Python's.
    def deg(rad):
        return f"{round(math.degrees(rad), 1):g}°"

    linkages = (ROOT / "docs" / "linkages.md").read_text()
    for page in (linkages, (ROOT / "docs" / "formulas.md").read_text()):
        tag = re.search(r"^<cad-fourbar\b([^>]*)>([\s\S]*?)</cad-fourbar>", page, re.M)
        assert tag, "no <cad-fourbar> demo"
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag.group(1)))
        links = [float(attrs[k]) for k in ("crank", "coupler", "rocker", "ground")]
        assert links == [40, 120, 80, 100] and fx.grashof(*links)["inversion"] == "crank-rocker"
        alt = tag.group(2)
        lowest = min(fx.transmission_angle(*links, math.radians(t)) for t in range(-180, 180))
        assert lowest == fx.transmission_angle(*links, 0.0)                            # lowest at 0 degrees
        assert f"{deg(lowest)} at 0°" in alt and "crank-rocker" in alt
        assert f"is {deg(fx.transmission_angle(*links, math.radians(float(attrs['angle']))))}" in alt.replace("°;", "°")
        assert 'src="img/formulas/fourbar-animator.svg"' in alt
    assert f"falls to {deg(fx.transmission_angle(40, 120, 80, 100, 0.0))} at" in linkages
    tri = fx.fourbar_input_limits(100, 80, 70, 60)
    assert fx.grashof(100, 80, 70, 60)["inversion"] == "triple-rocker" and f"±{deg(tri['stretched'])}" in linkages
    dr = fx.fourbar_input_limits(80, 40, 120, 100)
    assert fx.grashof(80, 40, 120, 100)["inversion"] == "double-rocker"
    assert f"locks at {deg(dr['folded'])} and at {deg(dr['stretched'])}" in linkages
    angles = fx.fourbar_angles(0.040, 0.120, 0.080, 0.100, math.radians(40))
    assert f"{deg(angles[0])} and {deg(angles[1])}" in linkages
