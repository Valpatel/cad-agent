"""cadagent.formulas.welds against published values, or against derivations written out here.

Each test says which. Published: ANSI/AISC 360-16 Section J2 and J4.2 [ref:aisc-360-16]; Shigley's Chapter 9 tables
and worked examples, read in the publisher's lecture slides for the 9th edition [ref:shigley-9e-welding-slides] and
checked against class notes on the 10th [ref:hijazi-shigley-ch9] (the book itself was not opened); and the Steel Tube
Institute's full-capacity fillet weld [ref:packer-2024-full-capacity-welds]. Derived: every unit property by
integrating along the line, the stresses by putting the applied loads back together from the weld's forces, and the
critical point by searching the whole weld.
"""
import math

import numpy as np
import pytest

from cadagent import formulas as fx

IN, LBF, PSI = 0.0254, 4.4482216152605, 6894.757293168
KIP, KSI = 1000 * LBF, 1000 * PSI
MM, MPA = 1e-3, 1e6


# ----------------------------------------------------------------------------- one fillet

def test_the_throat_is_the_shortest_distance_from_the_root_to_the_face():
    # Derivation: legs h on the two faces; the face joins (h, 0) and (0, h); its distance from the root (0, 0) is
    # h / sqrt(2). AISC 360-16 J2.2a defines the effective throat as that distance; Shigley rounds it to 0.707 h.
    leg = 6 * MM
    root_to_face = abs(0 + 0 - leg) / math.hypot(1, 1)
    assert fx.fillet_throat(leg) == pytest.approx(root_to_face, rel=1e-12)
    assert fx.fillet_throat(leg) / leg == pytest.approx(0.707, abs=5e-4)
    assert fx.fillet_throat_area(leg, 80 * MM) == pytest.approx(root_to_face * 80 * MM, rel=1e-12)
    assert fx.fillet_throat_stress(-12e3, leg, 80 * MM) == pytest.approx(12e3 / (root_to_face * 80 * MM), rel=1e-12)


def test_shigley_example_9_2_allowable_load_of_a_3_8_in_e70_fillet():
    # Shigley Example 9-2: a 3/8 in E70 fillet, 2 in long on both sides; its Table 9-6 gives 5.57 kip per inch of
    # weld, so F = 5.57 x 4 = 22.28 kip. That table's stress, 0.30 of the electrode's tensile strength, is AISC's
    # 0.60 FEXX over Omega = 2.00, so the ASD strength must reproduce it.
    weld = fx.weld_metal_strength(70 * KSI, "asd")
    assert weld["nominal"] == pytest.approx(0.60 * 70 * KSI) and weld["factor"] == 2.0
    assert weld["available"] == pytest.approx(0.30 * 70 * KSI, rel=1e-12)
    per_inch = weld["available"] * fx.fillet_throat(0.375 * IN)
    assert per_inch / (KIP / IN) == pytest.approx(5.57, abs=0.005)
    assert weld["available"] * fx.fillet_throat_area(0.375 * IN, 4 * IN) / KIP == pytest.approx(22.28, abs=0.02)
    # and the example's load, 16.5 kip on the two welds, is under it
    assert fx.fillet_throat_stress(16.5 * KIP, 0.375 * IN, 4 * IN) < weld["available"]


def test_aisc_table_j2_5_factors_for_a_fillet_weld():
    # AISC 360-16 Table J2.5, fillet welds, shear: Fnw = 0.60 FEXX, phi = 0.75, Omega = 2.00.
    lrfd, asd = fx.weld_metal_strength(483 * MPA), fx.weld_metal_strength(483 * MPA, "asd")
    assert (lrfd["method"], lrfd["factor"], asd["factor"]) == ("lrfd", 0.75, 2.0)
    assert lrfd["available"] == pytest.approx(0.75 * 0.60 * 483 * MPA, rel=1e-12)
    assert asd["available"] == pytest.approx(0.60 * 483 * MPA / 2.00, rel=1e-12)
    assert lrfd["available"] / asd["available"] == pytest.approx(1.5, rel=1e-12)      # phi times Omega


def test_steel_tube_institute_full_capacity_fillet_on_a_rectangular_tube():
    # Packer (Steel Tube Institute, 2024), design example: HSS wall Fy = 50 ksi, t = 0.349 in, E70. A fillet develops
    # the wall's design yield, 0.9 Fy t per unit length; with the directional factor 1.5 on a round tube the article
    # needs a throat of 0.332 in, a 0.47 in leg, and says a rectangular tube (no factor) would need a 3/4 in leg.
    fy, t, fexx = 50 * KSI, 0.349 * IN, 70 * KSI
    wall = 0.9 * fy * t
    available = fx.weld_metal_strength(fexx)["available"]                             # no directional increase

    def develops(leg):
        return available * fx.fillet_throat(leg) >= wall

    assert develops(0.75 * IN) and not develops(0.6875 * IN)                          # 3/4 in does, 11/16 in does not
    # the article's round-tube weld, a 0.332 in throat, carries the wall only with its factor of 1.5
    assert 1.5 * available * 0.332 * IN == pytest.approx(wall, rel=2e-3)
    assert fx.fillet_throat(0.47 * IN) / IN == pytest.approx(0.332, abs=1e-3)
    assert not develops(0.47 * IN)


# ----------------------------------------------------------------------------- minimum and maximum size

@pytest.mark.parametrize("thinner_in,least_in", [(1 / 8, 1 / 8), (1 / 4, 1 / 8), (0.26, 3 / 16), (1 / 2, 3 / 16),
                                                 (0.51, 1 / 4), (3 / 4, 1 / 4), (0.76, 5 / 16), (2, 5 / 16)])
def test_aisc_table_j2_4_minimum_fillet(thinner_in, least_in):
    # AISC 360-16 Table J2.4: to 1/4 in inclusive, 1/8 in; over 1/4 to 1/2, 3/16; over 1/2 to 3/4, 1/4; over 3/4,
    # 5/16 in. (Its SI column prints 3, 5, 6 and 8 mm at 6, 13 and 19 mm, each within 0.4 mm of these.)
    least = fx.fillet_size_limits(thinner_in * IN)["minimum"]
    assert least == pytest.approx(least_in * IN, rel=1e-12)
    assert least == pytest.approx({1 / 8: 3, 3 / 16: 5, 1 / 4: 6, 5 / 16: 8}[least_in] * MM, abs=0.4 * MM)


def test_aisc_j2_2b_maximum_fillet_along_an_edge():
    # J2.2b(b): along an edge under 1/4 in thick, no more than the thickness; from 1/4 in, the thickness less 1/16 in.
    assert fx.fillet_size_limits(3 * MM)["maximum"] is None                            # not along an edge
    thin = fx.fillet_size_limits(0.125 * IN, 0.125 * IN)                               # a lapped 1/8 in plate
    assert thin == {"minimum": pytest.approx(0.125 * IN), "maximum": pytest.approx(0.125 * IN), "conflict": False}
    # 1/4 in stock: least 1/8 in, largest 3/16 in. The table's SI column would ask for 5 mm and allow 4.35 mm.
    quarter = fx.fillet_size_limits(0.25 * IN, 0.25 * IN)
    assert quarter["minimum"] == pytest.approx(0.125 * IN) and quarter["maximum"] == pytest.approx(0.1875 * IN)
    assert quarter["conflict"] is False
    assert fx.fillet_size_limits(10 * MM, 8 * MM)["maximum"] == pytest.approx(8 * MM - IN / 16)
    # a thin edge beside thicker parts cannot meet both: a 0.3 in thinner part asks for 3/16 in, a 0.15 in edge
    # allows 0.15 in
    assert fx.fillet_size_limits(0.3 * IN, 0.15 * IN)["conflict"] is True


# ----------------------------------------------------------------------------- unit properties of a line

def _segments(group, n=2000, ends=False):
    """Derivation: the weld cut into short pieces, as midpoints (x, y) and lengths, built from the dimensions alone.
    With ``ends``, points from end to end of each weld instead (for a search, not a sum)."""
    if group["pattern"] == "circle":
        r = group["diameter"] / 2
        a = (np.arange(n) + 0.5) * 2 * np.pi / n
        return r * np.cos(a), r * np.sin(a), np.full(n, 2 * np.pi * r / n)
    u = np.linspace(-0.5, 0.5, n) if ends else (np.arange(n) + 0.5) / n - 0.5
    if group["pattern"] == "parallel":
        d, b = group["weld_length"], group["spacing"]
        x = np.concatenate([np.full(n, b / 2), np.full(n, -b / 2)])
        return x, np.concatenate([u * d, u * d]), np.full(2 * n, d / n)
    b, d = group["width"], group["depth"]
    x = np.concatenate([np.full(n, b / 2), np.full(n, -b / 2), u * b, u * b])
    y = np.concatenate([u * d, u * d, np.full(n, d / 2), np.full(n, -d / 2)])
    return x, y, np.concatenate([np.full(2 * n, d / n), np.full(2 * n, b / n)])


GROUPS = [fx.weld_line_parallel(60 * MM, 25 * MM), fx.weld_line_parallel(20 * MM, 90 * MM),
          fx.weld_line_box(50.8 * MM, 50.8 * MM), fx.weld_line_box(40 * MM, 100 * MM), fx.weld_line_circle(48.3 * MM)]


@pytest.mark.parametrize("group", GROUPS, ids=lambda g: g["pattern"])
def test_unit_properties_match_integration_along_the_line(group):
    # Derivation: length = sum dl, Iu about x = sum y^2 dl, about y = sum x^2 dl, Ju = sum r^2 dl (midpoint rule).
    x, y, dl = _segments(group)
    assert group["length"] == pytest.approx(dl.sum(), rel=1e-9)
    assert group["iu_x"] == pytest.approx((y * y * dl).sum(), rel=1e-6)
    assert group["iu_y"] == pytest.approx((x * x * dl).sum(), rel=1e-6)
    assert group["ju"] == pytest.approx(((x * x + y * y) * dl).sum(), rel=1e-6)
    assert (x * dl).sum() == pytest.approx(0, abs=1e-12) and (y * dl).sum() == pytest.approx(0, abs=1e-12)


def test_unit_properties_are_shigleys_tables_9_1_and_9_2():
    # The closed forms as Shigley's Tables 9-1 (torsion) and 9-2 (bending) print them, with b across and d along.
    b, d, r = 0.375, 2.0, 1.25
    two = fx.weld_line_parallel(d, b)
    assert two["ju"] == pytest.approx(d * (3 * b * b + d * d) / 6)                   # Table 9-1, weld 2
    assert two["iu_x"] == pytest.approx(d ** 3 / 6)                                  # Table 9-2, weld 2
    assert fx.weld_line_parallel(b, d)["iu_y"] == pytest.approx(b * d * d / 2)       # Table 9-2, weld 3, turned
    box = fx.weld_line_box(b, d)
    assert box["ju"] == pytest.approx((b + d) ** 3 / 6)                              # Table 9-1, weld 5
    assert box["iu_x"] == pytest.approx(d * d * (3 * b + d) / 6)                     # Table 9-2, weld 6
    assert box["length"] == pytest.approx(2 * (b + d))                               # A = 1.414 h (b + d)
    circle = fx.weld_line_circle(2 * r)
    assert circle["ju"] == pytest.approx(2 * math.pi * r ** 3)                       # Table 9-1, weld 6
    assert circle["iu_x"] == circle["iu_y"] == pytest.approx(math.pi * r ** 3)       # Table 9-2, weld 9
    assert circle["length"] == pytest.approx(2 * math.pi * r)                        # A = 1.414 pi h r


# ----------------------------------------------------------------------------- stress on the throat

def test_shigley_example_9_4_welded_cantilever():
    # Shigley Example 9-4: a 3/8 x 2 in bar welded with 3/8 in fillets down its two 2 in sides, 500 lbf at 6 in.
    # The book: A = 1.06 in^2, Iu = 1.33 in^3, I = 0.353 in^4, tau' = 0.472 kpsi, tau'' = 8.50 kpsi, tau = 8.51 kpsi.
    # It carries A and I to three figures (500 x 6 / 0.353 = 8.50; unrounded, 8.49), hence the 0.2 % tolerance.
    group = fx.weld_line_parallel(2 * IN, 0.375 * IN)
    s = fx.weld_group_stress(group, 0.375 * IN, shear_y=-500 * LBF, moment_x=500 * LBF * 6 * IN)
    assert s["throat_area"] / IN ** 2 == pytest.approx(1.06, abs=0.005)
    assert group["iu_x"] / IN ** 3 == pytest.approx(1.33, abs=0.005)
    assert s["throat"] * group["iu_x"] / IN ** 4 == pytest.approx(0.353, abs=0.001)
    assert s["primary"] / KSI == pytest.approx(0.472, rel=2e-3)
    assert s["secondary"] / KSI == pytest.approx(8.50, rel=2e-3)
    assert s["stress"] / KSI == pytest.approx(8.51, rel=2e-3)
    assert abs(s["point"][1]) == pytest.approx(1 * IN)                                 # at an end of a weld
    # part (c): the code's allowable for an E60 electrode is 18 kpsi in the book's Table 9-6, which AISC's 0.60 FEXX
    # over 2.00 reproduces; the weld is under it. (The book then scales by the 1.6 it reads into that allowable,
    # 0.577 x 50 / 18, to compare with part (a): 1.6 x 18 / 8.51 = 3.38.)
    allowable = fx.weld_metal_strength(60 * KSI, "asd")["available"]
    assert allowable / KSI == pytest.approx(18.0, rel=1e-12)
    assert s["stress"] < allowable
    assert 1.6 * allowable / s["stress"] == pytest.approx(3.38, abs=0.01)


def test_shigley_bending_of_two_welds_across_the_load():
    # Shigley's section on welded joints in bending (its Fig. 9-17): two welds of length b, d apart, top and bottom
    # of a bar: Iu = b d^2 / 2 and tau'' = 1.414 M / (b d h).
    b, d, h, moment = 30 * MM, 50 * MM, 5 * MM, 240.0
    s = fx.weld_group_stress(fx.weld_line_parallel(b, d), h, moment_y=moment)
    assert s["stress"] == pytest.approx(math.sqrt(2) * moment / (b * d * h), rel=1e-12)
    assert s["primary"] == 0.0 and s["secondary"] == s["stress"]


LOADS = [dict(shear_y=1500.0, moment_x=400.0), dict(torque=250.0), dict(axial=-3000.0),
         dict(shear_x=900.0, shear_y=-400.0, axial=1200.0, moment_x=-150.0, moment_y=220.0, torque=90.0),
         dict(shear_x=2000.0, torque=-60.0, moment_y=35.0),
         dict(axial=500.0, moment_x=-120.0, moment_y=-80.0),              # peaks at (+x, -y) alone
         dict(shear_x=-700.0, shear_y=-900.0, torque=150.0, moment_x=60.0, moment_y=45.0)]


def _line_forces(group, x, y, shear_x=0.0, shear_y=0.0, axial=0.0, moment_x=0.0, moment_y=0.0, torque=0.0):
    """Derivation, written apart from the module: force per unit length at each point, from statics."""
    length = group["length"]
    return (shear_x / length - torque * y / group["ju"], shear_y / length + torque * x / group["ju"],
            axial / length + moment_x * y / group["iu_x"] - moment_y * x / group["iu_y"])


@pytest.mark.parametrize("group", GROUPS, ids=lambda g: g["pattern"])
@pytest.mark.parametrize("loads", LOADS)
def test_the_welds_forces_add_back_up_to_the_applied_loads(group, loads):
    # Derivation: equilibrium. Summing the line's forces, and their moments r x f about the centroid, must return
    # each applied force and moment; this fixes the properties, the lever arms and every sign.
    x, y, dl = _segments(group)
    fx_, fy_, fz_ = _line_forces(group, x, y, **loads)
    got = {"shear_x": (fx_ * dl).sum(), "shear_y": (fy_ * dl).sum(), "axial": (fz_ * dl).sum(),
           "moment_x": (y * fz_ * dl).sum(), "moment_y": (-x * fz_ * dl).sum(),
           "torque": ((x * fy_ - y * fx_) * dl).sum()}
    scale = max(abs(v) for v in loads.values())
    for name, value in got.items():
        assert value == pytest.approx(loads.get(name, 0.0), rel=1e-5, abs=1e-6 * scale), name


@pytest.mark.parametrize("group", GROUPS, ids=lambda g: g["pattern"])
@pytest.mark.parametrize("loads", LOADS)
def test_the_critical_point_is_the_worst_point_of_the_whole_weld(group, loads):
    # Derivation: search every short piece of the weld for the largest resultant; the function must find at least
    # that (it looks at the corners of straight welds, and searches a circle).
    leg = 4 * MM
    x, y, _ = _segments(group, n=20001, ends=True)
    resultant = np.sqrt(sum(c * c for c in _line_forces(group, x, y, **loads)))
    s = fx.weld_group_stress(group, leg, **loads)
    assert s["force_per_length"] == pytest.approx(resultant.max(), rel=1e-6)
    assert s["force_per_length"] >= resultant.max() * (1 - 1e-9)
    assert s["stress"] == pytest.approx(resultant.max() / (leg / math.sqrt(2)), rel=1e-6)
    assert s["stress"] <= s["primary"] + s["secondary"] + 1e-6                         # a vector sum, never more
    px, py = s["point"]
    assert np.min(np.hypot(x - px, y - py)) < 1e-4                                     # and it is on the weld


def test_the_critical_corner_is_not_always_on_a_diagonal():
    # Derivation: a pull with bending about both axes. f_z = P / L + Mx y / Iu_x - My x / Iu_y is largest where
    # Mx y > 0 and My x < 0: with Mx < 0 and My < 0 that is the corner (+x, -y), and no other corner ties.
    b, d = 40 * MM, 100 * MM
    group = fx.weld_line_box(b, d)
    s = fx.weld_group_stress(group, 4 * MM, axial=500.0, moment_x=-120.0, moment_y=-80.0)
    assert s["point"] == [pytest.approx(b / 2), pytest.approx(-d / 2)]
    by_hand = 500.0 / group["length"] + 120.0 * (d / 2) / group["iu_x"] + 80.0 * (b / 2) / group["iu_y"]
    assert s["force_per_length"] == pytest.approx(by_hand, rel=1e-12)


def test_a_group_edited_by_hand_is_refused():
    # The group's properties must belong to its dimensions: a changed dimension, length or pattern is refused.
    group = fx.weld_line_box(0.2, 0.2)
    for change in ({"width": 0.05, "depth": 0.05}, {"length": 10.0}, {"iu_x": group["iu_x"] * 2}, {"ju": True},
                   {"pattern": "circle"}):
        with pytest.raises(ValueError):
            fx.weld_group_stress({**group, **change}, 4 * MM, shear_y=1000.0)
    assert fx.weld_group_stress(dict(group), 4 * MM, shear_y=1000.0)["stress"] > 0
    # only the pattern and its dimensions are needed
    bare = fx.weld_group_stress({"pattern": "box", "width": 0.2, "depth": 0.2}, 4 * MM, shear_y=1000.0)
    assert bare == fx.weld_group_stress(group, 4 * MM, shear_y=1000.0)


def test_a_round_boss_in_torsion_and_a_tube_in_bending_by_hand():
    # Derivation: a circle of radius r. Torque alone: T = (f)(r)(2 pi r), so f = T / (2 pi r^2), the same all round.
    # Bending alone: f = M c / Iu = M r / (pi r^3) = M / (pi r^2) at the extreme fibre. Axial: P / (2 pi r).
    r, leg = 20 * MM, 5 * MM
    throat = leg / math.sqrt(2)
    circle = fx.weld_line_circle(2 * r)
    assert fx.weld_group_stress(circle, leg, torque=80.0)["stress"] == pytest.approx(
        80.0 / (2 * math.pi * r * r) / throat, rel=1e-12)
    bend = fx.weld_group_stress(circle, leg, moment_x=80.0)
    assert bend["stress"] == pytest.approx(80.0 / (math.pi * r * r) / throat, rel=1e-9)
    assert bend["point"][1] == pytest.approx(r, rel=1e-9) or bend["point"][1] == pytest.approx(-r, rel=1e-9)
    assert fx.weld_group_stress(circle, leg, axial=900.0)["stress"] == pytest.approx(
        900.0 / (2 * math.pi * r) / throat, rel=1e-12)
    assert fx.weld_group_stress(circle, leg)["stress"] == 0.0


# ----------------------------------------------------------------------------- strength: weld metal and base metal apart

def test_base_metal_shear_is_aisc_j4_2_by_hand():
    # AISC 360-16 J4.2: yielding 0.60 Fy Agv with phi 1.00, Omega 1.50 (J4-3); rupture 0.60 Fu Anv with phi 0.75,
    # Omega 2.00 (J4-4). Per unit length of weld the area is the thickness. A36 plate, 6 mm: Fy 250, Fu 400 MPa.
    t, fy, fu = 6 * MM, 250 * MPA, 400 * MPA
    lrfd = fx.base_metal_shear_strength(t, fy, fu)
    assert lrfd["yielding"] == pytest.approx(1.00 * 0.60 * fy * t) and lrfd["rupture"] == pytest.approx(0.75 * 0.60 * fu * t)
    assert (lrfd["mode"], lrfd["available"]) == ("yielding", pytest.approx(900e3))     # 900 against 1080 N/mm
    asd = fx.base_metal_shear_strength(t, fy, fu, "asd")
    assert asd["yielding"] == pytest.approx(0.60 * fy * t / 1.50) and asd["rupture"] == pytest.approx(0.60 * fu * t / 2.00)
    assert asd["available"] == pytest.approx(600e3)
    # rupture governs when Fu is under 4/3 of Fy (LRFD: 0.75 Fu < Fy)
    assert fx.base_metal_shear_strength(t, 350 * MPA, 420 * MPA)["mode"] == "rupture"


def test_the_check_keeps_weld_metal_and_base_metal_apart():
    # Derivation: with one phi for both (rupture), the base metal matches the weld when 0.60 Fu t = 0.60 FEXX 0.707 w,
    # that is t = 0.707 w FEXX / Fu. A thinner wall makes the base metal govern, a thicker one the weld.
    leg, fexx, fu, fy = 5 * MM, 483 * MPA, 400 * MPA, 380 * MPA                        # Fy high enough that rupture governs
    balanced = leg / math.sqrt(2) * fexx / fu
    stress = 120 * MPA
    even = fx.fillet_weld_check(stress, leg, fexx, balanced, fy, fu)
    assert even["weld_ratio"] == pytest.approx(even["base_ratio"], rel=1e-12)
    assert even["weld_ratio"] == pytest.approx(stress / (0.75 * 0.60 * fexx), rel=1e-12)
    assert even["force_per_length"] == pytest.approx(stress * leg / math.sqrt(2), rel=1e-12)
    thin = fx.fillet_weld_check(stress, leg, fexx, balanced / 2, fy, fu)
    assert thin["governs"] == "base" and thin["base_ratio"] == pytest.approx(2 * thin["weld_ratio"], rel=1e-12)
    assert thin["weld_passes"] and thin["passes"] == thin["base_passes"]
    thick = fx.fillet_weld_check(stress, leg, fexx, balanced * 3, fy, fu)
    assert thick["governs"] == "weld" and thick["base_ratio"] < thick["weld_ratio"] < 1 and thick["passes"]
    # the thin wall fails on its base metal while its weld metal passes: one verdict would hide which
    over = fx.fillet_weld_check(0.9 * 0.75 * 0.60 * fexx, leg, fexx, balanced / 2, fy, fu)
    assert over["weld_passes"] and not over["base_passes"] and not over["passes"]


def test_asd_and_lrfd_are_reported_as_what_they_are():
    lrfd = fx.fillet_weld_check(100 * MPA, 4 * MM, 483 * MPA, 3 * MM, 315 * MPA, 400 * MPA, "lrfd")
    asd = fx.fillet_weld_check(100 * MPA, 4 * MM, 483 * MPA, 3 * MM, 315 * MPA, 400 * MPA, "asd")
    assert (lrfd["method"], asd["method"]) == ("lrfd", "asd") and set(fx.METHODS) == {"lrfd", "asd"}
    assert asd["weld_ratio"] == pytest.approx(1.5 * lrfd["weld_ratio"], rel=1e-12)     # 2.00 x 0.75
    assert asd["weld_available"] == pytest.approx(0.30 * 483 * MPA, rel=1e-12)
    # the base metal follows the method too. By hand, per metre: ASD yielding 0.60 (315) 3 / 1.50 = 378 kN and
    # rupture 0.60 (400) 3 / 2.00 = 360 kN; LRFD yielding 1.00 x 567 kN and rupture 0.75 x 720 = 540 kN.
    assert asd["base_available"] == pytest.approx(360e3, rel=1e-12)
    assert lrfd["base_available"] == pytest.approx(540e3, rel=1e-12)
    assert asd["base_ratio"] == pytest.approx(1.5 * lrfd["base_ratio"], rel=1e-12)


def test_the_limits_say_what_a_weld_calculation_does_not_cover():
    for name in ("weld_group_stress", "fillet_weld_check", "weld_metal_strength", "fillet_throat_stress"):
        limits = " ".join(fx.REGISTRY[name].limits)
        assert "static" in limits and "fatigue" in limits, name
        assert "hobbyist" in limits and "break test" in limits, name
    assert "heat-affected" in " ".join(fx.REGISTRY["fillet_weld_check"].limits)
    assert "burn" in " ".join(fx.REGISTRY["base_metal_shear_strength"].limits)
    group_limits = " ".join(fx.REGISTRY["weld_group_stress"].limits)
    assert "Section K5" in group_limits and "unconservative" in group_limits        # not for tube-to-tube joints
    assert "spread evenly" in group_limits                                           # the shear convention
    doc = __import__("cadagent.formulas.welds", fromlist=["x"]).__doc__
    for word in ("fatigue", "heat-affected", "residual stress", "burn-through", "hobbyist"):
        assert word in doc, word


@pytest.mark.parametrize("call", [
    lambda: fx.fillet_throat(0),
    lambda: fx.fillet_throat(True),
    lambda: fx.fillet_throat_area(3e-3, -1),
    lambda: fx.fillet_throat_stress(math.nan, 3e-3, 0.05),
    lambda: fx.fillet_size_limits(-1e-3),
    lambda: fx.fillet_size_limits(3e-3, 0),
    lambda: fx.weld_line_parallel(0.05, 0),
    lambda: fx.weld_line_box(math.inf, 0.05),
    lambda: fx.weld_line_circle(-0.05),
    lambda: fx.weld_group_stress({"pattern": "tee"}, 3e-3),
    lambda: fx.weld_group_stress("box", 3e-3),
    lambda: fx.weld_group_stress({"pattern": "box", "width": 0.05}, 3e-3),
    lambda: fx.weld_group_stress({"pattern": ["box"], "width": 0.05, "depth": 0.05}, 3e-3),
    lambda: fx.weld_group_stress(fx.weld_line_box(0.05, 0.05), 3e-3, shear_x=1e300, shear_y=1e300),
    lambda: fx.weld_metal_strength(483e6, ["lrfd"]),
    lambda: fx.weld_group_stress(fx.weld_line_box(0.05, 0.05), 3e-3, torque=math.inf),
    lambda: fx.weld_group_stress(fx.weld_line_box(0.05, 0.05), 0),
    lambda: fx.weld_metal_strength(483e6, "wsd"),
    lambda: fx.weld_metal_strength(0),
    lambda: fx.base_metal_shear_strength(3e-3, 250e6, 400e6, "LRFD"),
    lambda: fx.base_metal_shear_strength(0, 250e6, 400e6),
    lambda: fx.fillet_weld_check(-1.0, 3e-3, 483e6, 3e-3, 250e6, 400e6),
])
def test_bad_inputs_are_refused(call):
    with pytest.raises(ValueError):
        call()
