"""cadagent.formulas.gears: spur and straight bevel geometry, tooth forces and Lewis bending.

Each test says what it stands on: a published value (Shigley's Examples 13-1, 13-8 and 14-1 and its tables, Boston
Gear's Table I, Khurmi and Gupta's Sections 30.6 to 30.8) or a derivation written out here (the path of contact from
the tip circles, slices of a tapered bevel tooth, the statics of the tooth forces).

Where they were read: Shigley's examples, equations and Table 14-2 in the publisher's lecture slides for the 9th
edition (Chapters 13, 14 and 15), not in the book; Boston Gear's own PDF; Khurmi and Gupta's 14th edition as a scan.
docs/research/references.yaml records each reading.
"""
import math

import pytest

from cadagent import formulas as fx
from cadagent.formulas import gears

INCH = 0.0254
LBF = 4.4482216152605            # N
PSI = LBF / INCH ** 2            # Pa
FT_PER_MIN = 0.3048 / 60         # m/s
HP = 550 * 0.3048 * LBF          # W
DEG20, DEG14_5 = math.radians(20.0), math.radians(14.5)

GEAR_FORMULAS = ("module_from_diametral_pitch", "diametral_pitch_from_module", "gear_pitch_diameter",
                 "gear_centre_distance", "gear_tip_diameter", "gear_root_diameter", "gear_base_diameter",
                 "gear_contact_ratio", "gear_min_teeth", "gear_max_mate_teeth", "bevel_pitch_angles",
                 "bevel_cone_distance", "bevel_mean_radius", "bevel_face_width_limits", "bevel_virtual_teeth",
                 "gear_tangential_force", "spur_gear_forces", "bevel_gear_forces", "lewis_form_factor",
                 "gear_velocity_factor", "lewis_bending_stress", "bevel_cone_factor", "lewis_bevel_bending_stress",
                 "spur_tooth_bending", "bevel_tooth_bending")


# ----------------------------------------------------------------------------- the registry

def test_every_gear_formula_is_registered_and_states_what_lewis_leaves_out():
    assert {n for n, f in fx.REGISTRY.items() if f.module == "cadagent.formulas.gears"} == set(GEAR_FORMULAS)
    for name in ("lewis_bending_stress", "lewis_bevel_bending_stress", "spur_tooth_bending", "bevel_tooth_bending"):
        limits = " ".join(fx.REGISTRY[name].limits)
        for words in ("static or low-speed first check", "AGMA", "pitting", "fatigue", "printed plastic",
                      "no agreed allowable"):
            assert words in limits, f"{name}: the limits do not say {words!r}"
    for name in ("bevel_pitch_angles", "bevel_cone_distance", "bevel_gear_forces", "bevel_tooth_bending"):
        assert "90 degrees" in " ".join(fx.REGISTRY[name].limits), name
    assert "LARGE-END" in fx.REGISTRY["lewis_bevel_bending_stress"].units["force"]
    assert "VIRTUAL" in fx.REGISTRY["lewis_bevel_bending_stress"].units["form_factor"]


# ----------------------------------------------------------------------------- geometry: spur gears

def test_module_and_diametral_pitch_convert_both_ways():
    assert fx.module_from_diametral_pitch(8) == pytest.approx(3.175e-3)          # 25.4 mm / 8
    assert fx.diametral_pitch_from_module(2e-3) == pytest.approx(12.7)
    for p in (2, 5, 8, 20, 48):
        assert fx.diametral_pitch_from_module(fx.module_from_diametral_pitch(p)) == pytest.approx(p)


def test_shigley_example_13_1_pitch_diameters_centre_distance_and_base_circles():
    """Example 13-1: a 16-tooth pinion and a 40-tooth gear, diametral pitch 2, pressure angle 20 degrees. The book
    gives p = 1.57 in, dP = 8 in, dG = 20 in, C = 14 in, rb = 3.76 in (pinion) and 9.40 in (gear)."""
    m = fx.module_from_diametral_pitch(2)
    assert math.pi * m / INCH == pytest.approx(1.57, abs=0.005)
    assert fx.gear_pitch_diameter(m, 16) / INCH == pytest.approx(8)
    assert fx.gear_pitch_diameter(m, 40) / INCH == pytest.approx(20)
    assert fx.gear_centre_distance(m, 16, 40) / INCH == pytest.approx(14)
    assert fx.gear_base_diameter(m, 16, DEG20) / 2 / INCH == pytest.approx(3.76, abs=0.005)
    assert fx.gear_base_diameter(m, 40, DEG20) / 2 / INCH == pytest.approx(9.40, abs=0.005)


def test_tip_and_root_diameters_of_full_depth_teeth():
    """Shigley's Table 13-1: addendum 1 m, dedendum 1.25 m. A 2 mm module, 20 teeth: 40 mm pitch, 44 mm tip, 35 mm
    root; the whole depth is 2.25 modules."""
    assert fx.gear_tip_diameter(2e-3, 20) == pytest.approx(0.044)
    assert fx.gear_root_diameter(2e-3, 20) == pytest.approx(0.035)
    assert (fx.gear_tip_diameter(2e-3, 20) - fx.gear_root_diameter(2e-3, 20)) / 2 == pytest.approx(2.25 * 2e-3)
    assert fx.gear_tip_diameter(2e-3, 20, addendum=0.8) == pytest.approx(0.0432)        # stub teeth
    assert fx.gear_root_diameter(2e-3, 20, dedendum=1.35) == pytest.approx(0.0346)      # teeth to be ground
    with pytest.raises(ValueError, match="no root circle"):
        fx.gear_root_diameter(2e-3, 3, dedendum=1.5)


def _path_of_contact(m, n1, n2, phi):
    """The path of contact by construction, not by the closed form: the pinion's centre at the origin, the gear's
    at (0, C), the pitch point between them, and the line of action through it at the pressure angle. Contact
    starts where the line meets the gear's tip circle and ends where it meets the pinion's."""
    r1, r2 = m * n1 / 2, m * n2 / 2
    pitch_point, direction = (0.0, r1), (math.cos(phi), math.sin(phi))

    def reach(centre, radius):          # the positive distance along +-direction from the pitch point to a circle
        ox, oy = pitch_point[0] - centre[0], pitch_point[1] - centre[1]
        out = []
        for sign in (1, -1):
            dx, dy = sign * direction[0], sign * direction[1]
            b, c = ox * dx + oy * dy, ox * ox + oy * oy - radius * radius
            out.append(-b + math.sqrt(b * b - c))
        return out
    # the pinion's tip circle is met on the side where the line of action leaves the pinion's base circle; the
    # gear's on the other side: of each circle's two crossings, the shorter reach is that side
    return min(reach((0.0, 0.0), r1 + m)) + min(reach((0.0, r1 + r2), r2 + m))


@pytest.mark.parametrize("n1, n2, phi", [(16, 40, DEG20), (18, 18, DEG20), (20, 100, DEG20), (32, 48, DEG14_5),
                                         (17, 300, math.radians(25))])
def test_contact_ratio_against_the_path_of_contact_constructed_from_the_tip_circles(n1, n2, phi):
    m = 2e-3
    expected = _path_of_contact(m, n1, n2, phi) / (math.pi * m * math.cos(phi))
    assert fx.gear_contact_ratio(m, n1, n2, phi) == pytest.approx(expected, rel=1e-12)
    assert fx.gear_contact_ratio(5 * m, n1, n2, phi) == pytest.approx(expected, rel=1e-12)   # scale-free
    assert fx.gear_contact_ratio(m, n2, n1, phi) == pytest.approx(expected, rel=1e-12)       # symmetric


def test_contact_ratio_of_shigleys_example_gears_by_hand():
    """The 16 and 40 tooth gears of Example 13-1 (P = 2, 20 degrees), worked by hand in inches: tip radii 4.5 and
    10.5, base radii 3.759 and 9.397, C sin(phi) = 4.788, so Lab = 2.474 + 4.685 - 4.788 = 2.371 in; the base pitch
    is 1.5708 cos 20 = 1.476 in, and mc = 1.61. Above Shigley's least of 1.2."""
    mc = fx.gear_contact_ratio(fx.module_from_diametral_pitch(2), 16, 40, DEG20)
    assert mc == pytest.approx(2.371 / 1.476, rel=1e-3) and mc > fx.MIN_CONTACT_RATIO == 1.2
    # a higher pressure angle shortens the path of contact; more teeth lengthen it
    assert fx.gear_contact_ratio(1e-3, 16, 40, math.radians(25)) < mc < fx.gear_contact_ratio(1e-3, 16, 40, DEG14_5)
    assert fx.gear_contact_ratio(1e-3, 30, 80, DEG20) > mc


def test_least_tooth_counts_without_interference_as_shigley_gives_them():
    """Shigley, 'Interference', at 20 degrees full depth: a pinion of 13 teeth runs with an equal gear (Eq. 13-10);
    the least pinion for a rack is 2 / sin^2(20 deg) = 17.1, so 18 (Eq. 13-13)."""
    assert fx.gear_min_teeth(DEG20, ratio=1) == {"bound": pytest.approx(12.323, abs=1e-3), "teeth": 13}
    assert fx.gear_min_teeth(DEG20) == {"bound": pytest.approx(17.097, abs=1e-3), "teeth": 18}
    assert fx.gear_min_teeth(DEG20, ratio=math.inf)["bound"] == pytest.approx(2 / math.sin(DEG20) ** 2)
    # Eq. (13-10), the one-to-one form, written out: 2k / (3 sin^2) (1 + sqrt(1 + 3 sin^2))
    s2 = math.sin(DEG20) ** 2
    assert fx.gear_min_teeth(DEG20, ratio=1)["bound"] == pytest.approx(2 / (3 * s2) * (1 + math.sqrt(1 + 3 * s2)))
    # the bound rises with the ratio toward the rack's, and falls with the pressure angle and with stub teeth
    bounds = [fx.gear_min_teeth(DEG20, ratio=r)["bound"] for r in (1, 2, 4, 10, 100, 1e6, math.inf)]
    assert bounds == sorted(bounds) and bounds[-2] == pytest.approx(bounds[-1], rel=1e-5)
    assert fx.gear_min_teeth(DEG14_5)["teeth"] == 32 and fx.gear_min_teeth(math.radians(25))["teeth"] == 12
    assert fx.gear_min_teeth(DEG20, addendum=0.8)["teeth"] == 14


def test_largest_mate_as_shigleys_table_gives_it():
    """Shigley's table of Eq. (13-12) at 20 degrees: pinions of 13, 14, 15, 16 and 17 teeth run free of
    interference with gears up to 16.45, 26.12, 45.49, 101.07 and 1309.86 teeth: 16, 26, 45, 101 and 1309."""
    for n, bound, whole in ((13, 16.45, 16), (14, 26.12, 26), (15, 45.49, 45), (16, 101.07, 101),
                            (17, 1309.86, 1309)):
        got = fx.gear_max_mate_teeth(n, DEG20)
        assert got["bound"] == pytest.approx(bound, abs=0.005) and got["teeth"] == whole
        # the two equations agree: with that mate's ratio, the least pinion is this one
        assert fx.gear_min_teeth(DEG20, ratio=got["bound"] / n)["bound"] == pytest.approx(n, rel=1e-9)
    assert fx.gear_max_mate_teeth(18, DEG20) == {"bound": math.inf, "teeth": None}     # 18 runs with a rack
    with pytest.raises(ValueError, match="the least is 13"):
        fx.gear_max_mate_teeth(12, DEG20)


# ----------------------------------------------------------------------------- geometry: straight bevel gears

def test_bevel_pitch_angles_of_shigley_example_13_8():
    """Example 13-8: a 15-tooth pinion and a 45-tooth gear: gamma = atan(3/9) = 18.4 deg, Gamma = 71.6 deg."""
    a = fx.bevel_pitch_angles(15, 45)
    assert math.degrees(a["pinion"]) == pytest.approx(18.4, abs=0.05)
    assert math.degrees(a["gear"]) == pytest.approx(71.6, abs=0.05)
    assert a["pinion"] + a["gear"] == pytest.approx(math.pi / 2)
    mitre = fx.bevel_pitch_angles(20, 20)
    assert mitre["pinion"] == mitre["gear"] == pytest.approx(math.pi / 4)


def test_cone_distance_from_either_gear_and_the_mean_radius_of_example_13_8():
    """Khurmi's L = sqrt((DG/2)^2 + (DP/2)^2) is Shigley's A0 = dP / (2 sin gamma) = dG / (2 sin Gamma) (Eq. 15-25).

    Example 13-8's figure: P = 5 teeth/in, 15 and 45 teeth, so the pitch radii are 1.5 and 4.5 in; it dimensions
    the average pitch radii as 1.293 in (pinion) and 3.88 in (gear). Those fix the face width the figure does not
    print: (L - b/2) / L = 1.293 / 1.5 gives b = 1.31 in, and the same b must return the gear's 3.88 in."""
    m = fx.module_from_diametral_pitch(5)
    cone = fx.bevel_cone_distance(m, 15, 45)
    a = fx.bevel_pitch_angles(15, 45)
    assert cone == pytest.approx(math.hypot(1.5, 4.5) * INCH)
    assert cone == pytest.approx(fx.gear_pitch_diameter(m, 15) / (2 * math.sin(a["pinion"])))
    assert cone == pytest.approx(fx.gear_pitch_diameter(m, 45) / (2 * math.sin(a["gear"])))
    face = 2 * cone * (1 - 1.293 / 1.5)
    assert face / INCH == pytest.approx(1.31, abs=0.005)
    assert fx.bevel_mean_radius(fx.gear_pitch_diameter(m, 15), face, cone) / INCH == pytest.approx(1.293)
    assert fx.bevel_mean_radius(fx.gear_pitch_diameter(m, 45), face, cone) / INCH == pytest.approx(3.88, abs=0.005)
    # the same radius from the cone's geometry: half the face back along the cone, d/2 - (b/2) sin(gamma)
    assert fx.bevel_mean_radius(fx.gear_pitch_diameter(m, 15), face, cone) == pytest.approx(
        fx.gear_pitch_diameter(m, 15) / 2 - face / 2 * math.sin(a["pinion"]))


def test_bevel_face_width_limits():
    """Shigley Eq. (15-24): F = min(0.3 A0, 10 / Pd); Khurmi: L / b not above 3. A 2 mm module, 18 and 36 teeth:
    L = 40.25 mm, a third is 13.4 mm, ten modules are 20 mm; a mitre pair of 60 teeth is limited by the modules."""
    limits = fx.bevel_face_width_limits(fx.bevel_cone_distance(2e-3, 18, 36), 2e-3)
    assert limits == {"third_of_cone": pytest.approx(0.0134164), "ten_modules": pytest.approx(0.020),
                      "maximum": pytest.approx(0.0134164)}
    long_cone = fx.bevel_face_width_limits(fx.bevel_cone_distance(2e-3, 60, 60), 2e-3)
    assert long_cone["maximum"] == long_cone["ten_modules"] == pytest.approx(0.020)
    assert long_cone["third_of_cone"] == pytest.approx(0.02 * math.sqrt(2)) and long_cone["third_of_cone"] > 0.020


def test_virtual_teeth_are_the_teeth_of_the_developed_back_cone():
    """Shigley Eq. (13-15): N' = 2 pi rb / p with rb the back-cone radius; Khurmi: TE = T sec(theta). The back cone
    is square to the pitch cone at the large end, so its radius is (d / 2) / cos(gamma)."""
    m, n = 2e-3, 18
    gamma = fx.bevel_pitch_angles(18, 36)["pinion"]
    back_cone_radius = (m * n / 2) / math.cos(gamma)
    assert fx.bevel_virtual_teeth(n, gamma) == pytest.approx(2 * math.pi * back_cone_radius / (math.pi * m))
    assert fx.bevel_virtual_teeth(20, math.pi / 4) == pytest.approx(20 * math.sqrt(2))         # a mitre gear
    # for shafts at 90 degrees the pair's virtual counts are N sqrt(1 + (N / N_mate)^2): the gear's grows fast
    assert fx.bevel_virtual_teeth(36, fx.bevel_pitch_angles(36, 18)["pinion"]) == pytest.approx(36 * math.sqrt(5))


# ----------------------------------------------------------------------------- tooth forces

def test_force_times_radius_returns_the_torque():
    for torque, radius in ((2.0, 0.018), (150.0, 0.11), (0.03, 0.004)):
        assert fx.gear_tangential_force(torque, radius) * radius == pytest.approx(torque)
    assert fx.gear_tangential_force(-2.0, 0.018) == fx.gear_tangential_force(2.0, 0.018)     # a magnitude
    spur = fx.spur_gear_forces(2.0, 0.036, DEG20)
    assert spur["tangential"] * 0.018 == pytest.approx(2.0)
    assert spur["radial"] == pytest.approx(spur["tangential"] * math.tan(DEG20))
    assert math.hypot(spur["tangential"], spur["radial"]) == pytest.approx(spur["normal"])
    bevel = fx.bevel_tooth_bending(torque=2.0, module=2e-3, teeth=18, mate_teeth=36, face_width=0.012)
    assert bevel["force_mean"] * bevel["mean_radius"] == pytest.approx(2.0)
    assert bevel["force_large_end"] * bevel["pitch_diameter"] / 2 == pytest.approx(2.0)
    assert bevel["force_mean"] > bevel["force_large_end"]              # the same torque at a smaller radius


def test_shigley_example_13_8_bevel_gear_forces():
    """Example 13-8: the pinion turns at 600 rev/min and transmits 5 hp; 20 degree teeth; the pinion's average pitch
    radius is 1.293 in and the gear's 3.88 in. The book: V = 406 ft/min, Wt = 406 lbf, and on the gear (pitch
    angle 71.6 degrees) Wr = 46.6 lbf and Wa = 140 lbf."""
    pinion_torque = 5 * HP / (600 * 2 * math.pi / 60)
    a = fx.bevel_pitch_angles(15, 45)
    pinion = fx.bevel_gear_forces(pinion_torque, 1.293 * INCH, a["pinion"], DEG20)
    assert pinion["tangential"] / LBF == pytest.approx(406, abs=0.5)
    gear = fx.bevel_gear_forces(pinion_torque * 3, 3 * 1.293 * INCH, a["gear"], DEG20)   # ratio 3: torque, radius
    assert gear["tangential"] / LBF == pytest.approx(406, abs=0.5)
    # the book rounds the pitch angle to 71.6 degrees (it is 71.565) and the load to 406 lbf (406.2) before it
    # resolves them, which moves its radial force by 0.3 %: unrounded it is 46.75 lbf
    assert gear["radial"] / LBF == pytest.approx(46.6, rel=4e-3)
    assert gear["axial"] / LBF == pytest.approx(140, abs=0.5)
    as_printed = fx.bevel_gear_forces(406 * LBF * 3.88 * INCH, 3.88 * INCH, math.radians(71.6), DEG20)
    assert as_printed["radial"] / LBF == pytest.approx(46.6, abs=0.05)
    assert as_printed["axial"] / LBF == pytest.approx(140, abs=0.5)
    # on shafts at 90 degrees each gear's axial force is the other's radial force
    assert pinion["axial"] == pytest.approx(gear["radial"]) and pinion["radial"] == pytest.approx(gear["axial"])


def test_bevel_forces_are_the_normal_force_resolved():
    """Statics, written out: the tooth's normal force lies in the plane square to the pitch cone's element, at the
    pressure angle from the tangent; its in-plane part Wt tan(phi) is square to the cone's surface, so it splits by
    the pitch angle into a radial part (cos) and an axial part (sin)."""
    f = fx.bevel_gear_forces(10.0, 0.02, math.radians(30), DEG20)
    assert math.sqrt(f["tangential"] ** 2 + f["radial"] ** 2 + f["axial"] ** 2) == pytest.approx(f["normal"])
    assert math.hypot(f["radial"], f["axial"]) == pytest.approx(f["tangential"] * math.tan(DEG20))
    assert f["axial"] / f["radial"] == pytest.approx(math.tan(math.radians(30)))
    # a pitch angle near 0 is a spur gear: no axial force, the spur radial force
    flat = fx.bevel_gear_forces(10.0, 0.02, 1e-9, DEG20)
    spur = fx.spur_gear_forces(10.0, 0.04, DEG20)
    assert flat["axial"] == pytest.approx(0, abs=1e-6) and flat["radial"] == pytest.approx(spur["radial"])


# ----------------------------------------------------------------------------- the Lewis form factor

def test_lewis_form_factors_as_shigley_table_14_2_prints_them():
    """Shigley's Table 14-2 (20 degrees, full depth), spot values read from the table."""
    for teeth, y in ((12, 0.245), (13, 0.261), (16, 0.296), (17, 0.303), (20, 0.322), (26, 0.346), (30, 0.359),
                     (50, 0.409), (100, 0.447), (300, 0.472), (400, 0.480), (math.inf, 0.485)):
        assert fx.lewis_form_factor(teeth) == fx.lewis_form_factor(teeth, DEG20, "shigley") == y
    assert len(fx.LEWIS_FORM_FACTORS["shigley"][20.0]) == 26


def test_lewis_form_factors_as_boston_gear_table_i_prints_them():
    """Boston Gear's Table I, both columns, spot values read from the catalogue page."""
    for teeth, y145, y20 in ((10, 0.176, 0.201), (12, 0.210, 0.245), (15, 0.245, 0.289), (20, 0.283, 0.320),
                             (30, 0.318, 0.358), (40, 0.336, 0.389), (60, 0.355, 0.421), (100, 0.368, 0.446),
                             (300, 0.382, 0.471), (math.inf, 0.390, 0.484)):
        assert fx.lewis_form_factor(teeth, DEG14_5) == fx.lewis_form_factor(teeth, DEG14_5, "boston") == y145
        assert fx.lewis_form_factor(teeth, DEG20, "boston") == y20
    assert all(len(rows) == 35 for rows in fx.LEWIS_FORM_FACTORS["boston"].values())


def test_every_form_factor_table_rises_with_the_tooth_count_and_the_two_20_degree_tables_agree():
    for name, columns in fx.LEWIS_FORM_FACTORS.items():
        for angle, rows in columns.items():
            counts, ys = [n for n, _ in rows], [y for _, y in rows]
            assert counts == sorted(counts) and ys == sorted(ys) and len(set(counts)) == len(counts), (name, angle)
            assert math.isinf(counts[-1]) and all(0.15 < y < 0.5 for y in ys), (name, angle)
    shigley = dict(fx.LEWIS_FORM_FACTORS["shigley"][20.0])
    boston = dict(fx.LEWIS_FORM_FACTORS["boston"][20.0])
    common = set(shigley) & set(boston)
    assert len(common) >= 20
    assert max(abs(shigley[n] - boston[n]) for n in common) <= 0.003 + 1e-12
    # a 20 degree tooth is thicker at the root than a 14.5 degree one, at every tooth count
    assert all(y20 > y145 for (_, y145), (_, y20) in zip(fx.LEWIS_FORM_FACTORS["boston"][14.5],
                                                         fx.LEWIS_FORM_FACTORS["boston"][20.0]))


def test_form_factor_interpolates_linearly_in_one_over_the_tooth_count():
    """Between rows, by hand: 23 teeth lies between 22 (0.331) and 24 (0.337) at (1/22 - 1/23) / (1/22 - 1/24) =
    0.5217 of the way, so Y = 0.3341. Past the last finite row the rack row is at 1/N = 0: 800 teeth is half way
    from 400 (0.480) to the rack (0.485)."""
    assert fx.lewis_form_factor(23) == pytest.approx(0.331 + 0.006 * (1 / 22 - 1 / 23) / (1 / 22 - 1 / 24))
    assert fx.lewis_form_factor(23) == pytest.approx(0.3341, abs=5e-5)
    assert fx.lewis_form_factor(800) == pytest.approx(0.4825)
    assert fx.lewis_form_factor(20.1246) == pytest.approx(0.3228, abs=5e-5)       # a bevel's virtual tooth number
    # monotonic and continuous across every row
    counts = [12 + 0.25 * i for i in range(2000)]
    ys = [fx.lewis_form_factor(n) for n in counts]
    assert all(b >= a for a, b in zip(ys, ys[1:])) and max(b - a for a, b in zip(ys, ys[1:])) < 0.005


def test_form_factor_refuses_what_the_tables_do_not_hold():
    with pytest.raises(ValueError, match="starts at 12 teeth"):
        fx.lewis_form_factor(11)
    assert fx.lewis_form_factor(11, DEG20, "boston") == 0.226
    with pytest.raises(ValueError, match="starts at 10 teeth"):
        fx.lewis_form_factor(9, DEG14_5)
    with pytest.raises(ValueError, match="14.5 and 20 degrees only"):
        fx.lewis_form_factor(20, math.radians(25))
    with pytest.raises(ValueError, match="radians"):
        fx.lewis_form_factor(20, 20)                                  # degrees passed by mistake
    with pytest.raises(ValueError, match="no column for 14.5 degrees"):
        fx.lewis_form_factor(20, DEG14_5, "shigley")
    with pytest.raises(ValueError, match="table must be one of"):
        fx.lewis_form_factor(20, DEG20, "agma")
    for bad in (0, -5, math.nan, True, "20", None):
        with pytest.raises(ValueError):
            fx.lewis_form_factor(bad)


# ----------------------------------------------------------------------------- Lewis bending

def test_velocity_factors_in_si_match_the_us_customary_forms():
    """Shigley gives each factor twice: Eqs. (14-4a), (14-4b), (14-5a), (14-5b) with V in ft/min and (14-6a) to
    (14-6d) with V in m/s. The SI constants are the others converted and rounded, so the two agree within 0.2 %."""
    for v_ft_min in (0, 100, 628, 1500, 4000):
        v = v_ft_min * FT_PER_MIN
        assert fx.gear_velocity_factor(v, "cast") == pytest.approx((600 + v_ft_min) / 600, rel=2e-3)
        assert fx.gear_velocity_factor(v, "cut") == pytest.approx((1200 + v_ft_min) / 1200, rel=2e-3)
        assert fx.gear_velocity_factor(v, "hobbed") == pytest.approx((50 + math.sqrt(v_ft_min)) / 50, rel=2e-3)
        assert fx.gear_velocity_factor(v, "ground") == pytest.approx(math.sqrt((78 + math.sqrt(v_ft_min)) / 78),
                                                                      rel=2e-3)
    assert all(fx.gear_velocity_factor(0, p) == 1 for p in fx.VELOCITY_PROFILES)
    assert (fx.gear_velocity_factor(5, "cast") > fx.gear_velocity_factor(5, "cut")
            > fx.gear_velocity_factor(5, "hobbed") > fx.gear_velocity_factor(5, "ground") > 1)
    assert fx.gear_velocity_factor(3.0) == fx.gear_velocity_factor(3.0, "cut")
    # Boston Gear derates the load by 600 / (600 + V): the reciprocal of the cast form
    assert 1 / fx.gear_velocity_factor(1500 * FT_PER_MIN, "cast") == pytest.approx(600 / 2100, rel=2e-3)


def test_shigley_example_14_1_lewis_rating_of_a_stock_spur_gear():
    """Example 14-1: diametral pitch 8, face 1.5 in, 16 teeth, 20 degrees full depth, AISI 1020 as rolled, a design
    factor of 3 on the 30 kpsi yield: 10 kpsi allowed, at 1200 rev/min. The book: d = 2 in, V = 628 ft/min,
    Kv = 1.52 (cut or milled), Y = 0.296, Wt = 365 lbf, 6.95 hp."""
    m = fx.module_from_diametral_pitch(8)
    d = fx.gear_pitch_diameter(m, 16)
    assert d / INCH == pytest.approx(2)
    speed = math.pi * d * 1200 / 60
    assert speed / FT_PER_MIN == pytest.approx(628, abs=0.5)
    kv = fx.gear_velocity_factor(speed, "cut")
    assert kv == pytest.approx(1.52, abs=0.005)
    y = fx.lewis_form_factor(16)
    assert y == 0.296
    # the book's load gives back the allowable stress, within its three-figure rounding
    stress = fx.lewis_bending_stress(365 * LBF, 1.5 * INCH, m, y, velocity_factor=1.52)
    assert stress / PSI == pytest.approx(10_000, rel=2e-3)
    # and the other way: the load at 10 kpsi, then the power
    load = 10_000 * PSI * 1.5 * INCH * m * y / kv
    assert load / LBF == pytest.approx(365, abs=1.0)
    assert load * speed / HP == pytest.approx(6.95, abs=0.03)
    # the same through the torque: spur_tooth_bending at the torque that load makes
    whole = fx.spur_tooth_bending(load * d / 2, m, 16, 1.5 * INCH, DEG20, velocity_factor=kv)
    assert whole["stress"] / PSI == pytest.approx(10_000) and whole["force"] == pytest.approx(load)
    assert whole["form_factor"] == 0.296 and whole["pitch_diameter"] == pytest.approx(d)


def test_lewis_equation_is_the_cantilever_it_models():
    """The equation written out: sigma = F / (b m Y). Doubling the face or the module halves the stress; the stress
    is linear in the force and in Kv; a 2 mm module, 12 mm face, Y = 0.309 tooth under 111.1 N is at 14.98 MPa."""
    assert fx.lewis_bending_stress(1000 / 9, 0.012, 2e-3, 0.309) == pytest.approx(14.98e6, rel=1e-3)
    base = fx.lewis_bending_stress(100, 0.01, 2e-3, 0.3)
    assert base == pytest.approx(100 / (0.01 * 2e-3 * 0.3))
    assert fx.lewis_bending_stress(100, 0.02, 2e-3, 0.3) == pytest.approx(base / 2)
    assert fx.lewis_bending_stress(100, 0.01, 4e-3, 0.3) == pytest.approx(base / 2)
    assert fx.lewis_bending_stress(300, 0.01, 2e-3, 0.3, velocity_factor=1.5) == pytest.approx(4.5 * base)
    assert fx.lewis_bending_stress(-100, 0.01, 2e-3, 0.3) == base


def _bevel_capacity_by_slices(stress, module, form_factor, cone, face, slices=20000):
    """A straight bevel tooth as thin spur slices, each at the same root stress. At a distance x from the apex the
    tooth is the large end scaled by x / L: module m x / L, pitch radius R x / L, the same tooth form. A slice dx
    carries dF = stress * (m x / L) * Y * dx by the Lewis equation and gives the torque dF * R x / L. Returns the
    total torque over R: the force at the large-end pitch radius that the tooth carries."""
    dx = face / slices
    return sum(stress * module * ((cone - face + (i + 0.5) * dx) / cone) ** 2 * form_factor * dx
               for i in range(slices))


@pytest.mark.parametrize("face_over_cone", [0.05, 0.2, 0.3, 1 / 3])
def test_bevel_cone_factor_against_slices_of_the_tapered_tooth(face_over_cone):
    """Khurmi's bevel factor (L - b) / L is the sliced tooth's 1 - b/L + b^2 / (3 L^2) without its last term, so it
    reads a little low: by 5.3 % at the limiting face of a third of the cone distance, less on a shorter face."""
    stress, m, y, cone = 50e6, 2e-3, 0.32, 0.040
    face = face_over_cone * cone
    sliced = _bevel_capacity_by_slices(stress, m, y, cone, face)
    exact = stress * m * y * face * (1 - face_over_cone + face_over_cone ** 2 / 3)
    assert sliced == pytest.approx(exact, rel=1e-8)
    lewis = stress * m * y * face * fx.bevel_cone_factor(face, cone)       # the force the formula allows
    assert lewis < sliced
    assert 1 - lewis / sliced == pytest.approx((face_over_cone ** 2 / 3) / (1 - face_over_cone
                                                                             + face_over_cone ** 2 / 3))
    assert 1 - lewis / sliced <= 0.0527
    # the stress function is that force turned round
    assert fx.lewis_bevel_bending_stress(lewis, face, m, y, cone) == pytest.approx(stress)


def test_bevel_lewis_stress_reduces_to_the_spur_result_as_the_face_goes_to_zero():
    """A vanishing face is one slice of the large end: a spur tooth of the virtual tooth number. The ratio of the
    bevel stress to the spur stress is L / (L - b), which tends to 1."""
    m, y, cone, force_per_width = 2e-3, 0.3228, 0.04025, 9000.0
    ratios = []
    for face in (0.012, 0.004, 1e-3, 1e-4, 1e-6, 1e-9):
        force = force_per_width * face
        bevel = fx.lewis_bevel_bending_stress(force, face, m, y, cone)
        spur = fx.lewis_bending_stress(force, face, m, y)
        assert bevel / spur == pytest.approx(cone / (cone - face))
        ratios.append(bevel / spur)
    assert ratios == sorted(ratios, reverse=True) and ratios[-1] == pytest.approx(1, abs=1e-7)
    # and a bevel pinion driving a very large gear is nearly a cylinder: its virtual teeth tend to its own
    assert fx.bevel_virtual_teeth(18, fx.bevel_pitch_angles(18, 18000)["pinion"]) == pytest.approx(18, rel=1e-6)


def test_bevel_tooth_bending_by_hand():
    """A 2 mm module pinion of 18 teeth on a 36-tooth gear, 12 mm face, 20 degree teeth, 2 N m on the pinion.

    d = 36 mm; gamma = atan(18/36) = 26.565 deg; L = sqrt(18^2 + 36^2) = 40.249 mm; N' = 18 / cos(gamma) = 20.125,
    Y' = 0.3228 (Table 14-2, between 20 and 21 teeth); the Lewis force is 2 / 0.018 = 111.1 N at the large end;
    the cone factor is (40.249 - 12) / 40.249 = 0.7019; the stress is 111.1 / (0.012 x 0.002 x 0.3228 x 0.7019) =
    20.4 MPa. The mean radius is 18 (40.249 - 6) / 40.249 = 15.317 mm, where the force on the bearings is
    2 / 0.015317 = 130.6 N."""
    r = fx.bevel_tooth_bending(torque=2.0, module=2e-3, teeth=18, mate_teeth=36, face_width=0.012)
    assert r["pitch_diameter"] == pytest.approx(0.036)
    assert math.degrees(r["pitch_angle"]) == pytest.approx(26.565, abs=1e-3)
    assert r["cone_distance"] == pytest.approx(0.040249, abs=1e-6)
    assert r["virtual_teeth"] == pytest.approx(20.125, abs=1e-3)
    assert r["form_factor"] == pytest.approx(0.3228, abs=5e-5)
    assert r["force_large_end"] == pytest.approx(111.1, abs=0.05)
    assert r["cone_factor"] == pytest.approx(0.7019, abs=5e-5)
    assert r["stress"] == pytest.approx(20.4e6, rel=2e-3)
    assert r["stress"] == pytest.approx(111.111 / (0.012 * 0.002 * 0.3228 * 0.7019), rel=1e-3)
    assert r["mean_radius"] == pytest.approx(0.015317, abs=1e-6)
    assert r["force_mean"] == pytest.approx(130.6, abs=0.05)
    assert r["radial"] == pytest.approx(130.576 * math.tan(DEG20) * math.cos(r["pitch_angle"]), rel=1e-4)
    assert r["axial"] == pytest.approx(130.576 * math.tan(DEG20) * math.sin(r["pitch_angle"]), rel=1e-4)
    assert r["face_width_limit"] == pytest.approx(0.040249 / 3, abs=1e-6) and r["face_width_ok"] is True
    assert r["velocity_factor"] == 1.0
    # the same from the parts
    assert r["stress"] == pytest.approx(fx.lewis_bevel_bending_stress(
        r["force_large_end"], 0.012, 2e-3, fx.lewis_form_factor(r["virtual_teeth"]), r["cone_distance"]))


def test_the_two_usual_bevel_mistakes_give_other_numbers():
    """What the composite function is for. The stress is not the spur equation at the large end without the cone
    factor (30 % low here), and not the mean-radius force put through the bevel equation (18 % high)."""
    r = fx.bevel_tooth_bending(torque=2.0, module=2e-3, teeth=18, mate_teeth=36, face_width=0.012)
    no_cone_factor = fx.lewis_bending_stress(r["force_large_end"], 0.012, 2e-3, r["form_factor"])
    assert no_cone_factor / r["stress"] == pytest.approx(r["cone_factor"]) and no_cone_factor < 0.71 * r["stress"]
    mean_force = fx.lewis_bevel_bending_stress(r["force_mean"], 0.012, 2e-3, r["form_factor"], r["cone_distance"])
    assert mean_force / r["stress"] == pytest.approx(0.018 / r["mean_radius"]) and mean_force > 1.17 * r["stress"]
    # the gear of the pair: twice the torque on twice the radius, so the same Lewis force, a larger virtual tooth
    # number and a lower stress
    gear = fx.bevel_tooth_bending(torque=4.0, module=2e-3, teeth=36, mate_teeth=18, face_width=0.012)
    assert gear["force_large_end"] == pytest.approx(r["force_large_end"])
    assert gear["cone_distance"] == pytest.approx(r["cone_distance"])
    assert gear["virtual_teeth"] == pytest.approx(36 * math.sqrt(5)) and gear["stress"] < r["stress"]
    assert gear["pitch_angle"] + r["pitch_angle"] == pytest.approx(math.pi / 2)
    assert gear["axial"] == pytest.approx(r["radial"]) and gear["radial"] == pytest.approx(r["axial"])


def test_bevel_tooth_bending_flags_a_face_past_the_recommended_limit_and_takes_the_other_table():
    wide = fx.bevel_tooth_bending(torque=2.0, module=2e-3, teeth=18, mate_teeth=36, face_width=0.016)
    assert wide["face_width_ok"] is False and wide["face_width_limit"] == pytest.approx(0.0134164)
    at_limit = fx.bevel_tooth_bending(torque=2.0, module=2e-3, teeth=18, mate_teeth=36,
                                      face_width=wide["face_width_limit"])
    assert at_limit["face_width_ok"] is True and at_limit["cone_factor"] == pytest.approx(2 / 3)
    old = fx.bevel_tooth_bending(torque=2.0, module=2e-3, teeth=18, mate_teeth=36, face_width=0.012,
                                 pressure_angle=DEG14_5, velocity_factor=1.3)
    assert old["form_factor"] == pytest.approx(fx.lewis_form_factor(old["virtual_teeth"], DEG14_5, "boston"))
    assert 0.283 < old["form_factor"] < 0.292                              # between 20 and 22 teeth at 14.5 deg
    boston = fx.bevel_tooth_bending(torque=2.0, module=2e-3, teeth=18, mate_teeth=36, face_width=0.012,
                                    table="boston")
    assert boston["form_factor"] == pytest.approx(fx.lewis_form_factor(boston["virtual_teeth"], DEG20, "boston"))
    with pytest.raises(ValueError, match="starts at 12 teeth"):           # 10 teeth on 40: 10.3 virtual teeth
        fx.bevel_tooth_bending(torque=1.0, module=2e-3, teeth=10, mate_teeth=40, face_width=0.01)


# ----------------------------------------------------------------------------- arguments

@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf, True, "2", None])
def test_lengths_forces_and_factors_must_be_finite_positive_numbers(bad):
    with pytest.raises(ValueError):
        fx.module_from_diametral_pitch(bad)
    with pytest.raises(ValueError):
        fx.gear_pitch_diameter(bad, 20)
    with pytest.raises(ValueError):
        fx.gear_tangential_force(1.0, bad)
    with pytest.raises(ValueError):
        fx.lewis_bending_stress(100, bad, 2e-3, 0.3)
    with pytest.raises(ValueError):
        fx.lewis_bending_stress(100, 0.01, 2e-3, bad)
    with pytest.raises(ValueError):
        fx.bevel_face_width_limits(bad, 2e-3)
    with pytest.raises(ValueError):
        fx.spur_tooth_bending(1.0, 2e-3, 20, bad)


@pytest.mark.parametrize("bad", [2, 0, -20, 20.5, math.inf, math.nan, True, "20", None])
def test_tooth_counts_must_be_whole_numbers(bad):
    with pytest.raises(ValueError, match="teeth"):
        fx.gear_pitch_diameter(2e-3, bad)
    with pytest.raises(ValueError, match="teeth"):
        fx.gear_centre_distance(2e-3, 20, bad)
    with pytest.raises(ValueError, match="teeth"):
        fx.bevel_pitch_angles(bad, 20)
    with pytest.raises(ValueError, match="teeth"):
        fx.bevel_tooth_bending(1.0, 2e-3, 20, bad, 0.01)
    assert fx.gear_pitch_diameter(2e-3, 20.0) == pytest.approx(0.040)       # a whole number as a float is fine


def test_angles_are_radians_and_the_rest_of_the_arguments_are_checked():
    for fn in (lambda a: fx.gear_base_diameter(2e-3, 20, a), lambda a: fx.gear_contact_ratio(2e-3, 20, 40, a),
               lambda a: fx.gear_min_teeth(a), lambda a: fx.spur_gear_forces(1.0, 0.04, a),
               lambda a: fx.bevel_gear_forces(1.0, 0.02, 0.5, a)):
        for bad in (20, 14.5, 0, -0.3, math.pi / 4, math.nan, True, "0.35"):
            with pytest.raises(ValueError, match="pressure_angle"):
                fn(bad)
    for bad in (0, -0.1, math.pi / 2, 45, math.nan, None):
        with pytest.raises(ValueError, match="pitch_angle"):
            fx.bevel_virtual_teeth(20, bad)
        with pytest.raises(ValueError, match="pitch_angle"):
            fx.bevel_gear_forces(1.0, 0.02, bad)
    for bad in (0.5, 0, -1, math.nan, "inf", True):
        with pytest.raises(ValueError, match="ratio"):
            fx.gear_min_teeth(DEG20, ratio=bad)
    for bad in (0.9, 0, -1, math.nan, math.inf, "1"):
        with pytest.raises(ValueError, match="velocity_factor"):
            fx.lewis_bending_stress(100, 0.01, 2e-3, 0.3, velocity_factor=bad)
        with pytest.raises(ValueError, match="velocity_factor"):
            fx.bevel_tooth_bending(1.0, 2e-3, 20, 40, 0.01, velocity_factor=bad)
    for bad in (-1, math.nan, math.inf, "3", True):
        with pytest.raises(ValueError, match="speed"):
            fx.gear_velocity_factor(bad)
    with pytest.raises(ValueError, match="profile must be one of"):
        fx.gear_velocity_factor(3.0, "moulded")
    for face in (0.04, 0.05):                                              # at or past the apex
        with pytest.raises(ValueError, match="less than the cone distance"):
            fx.bevel_cone_factor(face, 0.04)
        with pytest.raises(ValueError, match="less than the cone distance"):
            fx.bevel_mean_radius(0.036, face, 0.04)
        with pytest.raises(ValueError, match="less than the cone distance"):
            fx.lewis_bevel_bending_stress(100, face, 2e-3, 0.3, 0.04)
    for bad in (math.nan, math.inf, "2", None, True):
        with pytest.raises(ValueError, match="torque"):
            fx.spur_gear_forces(bad, 0.04)
        with pytest.raises(ValueError, match="force"):
            fx.lewis_bending_stress(bad, 0.01, 2e-3, 0.3)


def test_module_constants_are_the_standard_full_depth_proportions():
    assert (gears.ADDENDUM, gears.DEDENDUM) == (1.0, 1.25)
    assert gears.PRESSURE_ANGLE == pytest.approx(math.radians(20))
    assert set(fx.VELOCITY_PROFILES) == {"cast", "cut", "hobbed", "ground"}
