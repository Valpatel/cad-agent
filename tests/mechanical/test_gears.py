"""cadagent.mechanical.gears: the reference dimensions against closed forms written out here, and the solids
measured: tooth count, radii, tooth thickness, play in mesh and interference, not only that they build."""
import math
import time
import warnings

import pytest

from cadagent.mechanical import gears
from cadagent.mechanical.gears import (bevel_gear, bevel_gear_dimensions, external_ring_gear, gear_pair_dimensions,
                                       module_from_diametral_pitch, spur_gear, spur_gear_dimensions)


def inv(angle):
    return math.tan(angle) - angle


def involute_thickness(module, teeth, pressure_angle, radius, backlash=0.0, shift=0.0):
    """Arc tooth thickness of an involute tooth on the circle of ``radius`` (the textbook closed form)."""
    a = math.radians(pressure_angle)
    r = module * teeth / 2
    s = module * (math.pi / 2 + 2 * shift * math.tan(a)) - backlash
    return 2 * radius * (s / (2 * r) + inv(a) - inv(math.acos(r * math.cos(a) / radius)))


# ---- dimensions (no CAD kernel) ------------------------------------------------------------------------------------

def test_reference_dimensions_of_a_standard_gear():
    d = spur_gear_dimensions(2, 40)
    assert d['pitch_diameter_mm'] == pytest.approx(80)
    assert d['base_diameter_mm'] == pytest.approx(80 * math.cos(math.radians(20)))
    assert d['tip_diameter_mm'] == pytest.approx(84)
    assert d['root_diameter_mm'] == pytest.approx(75)             # 1.25 modules below the pitch circle
    assert d['tooth_thickness_mm'] == pytest.approx(math.pi)      # pi m / 2
    assert d['circular_pitch_mm'] == pytest.approx(2 * math.pi)
    assert d['tip_thickness_mm'] == pytest.approx(involute_thickness(2, 40, 20, 42))
    assert d['root_fillet_mm'] == pytest.approx(0.38 * 2, abs=1e-3)   # ISO 53's 0.38 m fills a 0.25 m clearance
    assert not d['undercut'] and spur_gear_dimensions(2, 60)['notes'] == []


def test_the_involute_starts_where_the_straight_side_of_the_cutter_ends():
    # The cutter's flank is straight to one module below the pitch line (the 0.25 m below that is its tip round).
    # A flank point at depth v touches the gear on the line of action, at radius sqrt(r^2 + (v / sin a)^2 - 2 r v).
    for teeth, angle in ((40, 20), (60, 14.5), (176, 20)):
        r, a = teeth, math.radians(angle)
        start = spur_gear_dimensions(2, teeth, pressure_angle=angle)['involute_start_diameter_mm'] / 2
        assert start == pytest.approx(math.sqrt(r * r + (2 / math.sin(a)) ** 2 - 2 * r * 2), abs=1e-9)


def test_backlash_and_profile_shift_change_the_tooth_thickness():
    a = math.radians(20)
    assert spur_gear_dimensions(3, 20, backlash=0.08)['tooth_thickness_mm'] == pytest.approx(1.5 * math.pi - 0.08)
    d = spur_gear_dimensions(3, 20, profile_shift=0.4)
    assert d['tooth_thickness_mm'] == pytest.approx(3 * (math.pi / 2 + 0.8 * math.tan(a)))
    assert d['tip_diameter_mm'] == pytest.approx(60 + 2 * 1.4 * 3)
    assert d['root_diameter_mm'] == pytest.approx(60 - 2 * 0.85 * 3)


def test_diametral_pitch_gives_the_module():
    assert module_from_diametral_pitch(12) == pytest.approx(25.4 / 12)
    assert spur_gear_dimensions(module_from_diametral_pitch(12), 16)['pitch_diameter_mm'] == pytest.approx(25.4 * 16 / 12)
    with pytest.raises(ValueError):
        module_from_diametral_pitch(0)


def test_a_14_5_degree_16_tooth_gear_reports_its_undercut():
    d = spur_gear_dimensions(module_from_diametral_pitch(12), 16, pressure_angle=14.5)
    assert d['undercut']
    assert d['min_teeth_without_undercut'] == 32                  # 2 / sin^2(14.5 deg) = 31.9
    assert d['involute_start_diameter_mm'] > d['base_diameter_mm']   # the bottom of the involute is cut away
    assert any('undercut' in note for note in d['notes'])
    assert not spur_gear_dimensions(2, 32, pressure_angle=14.5)['undercut']
    assert spur_gear_dimensions(2, 16, pressure_angle=20)['min_teeth_without_undercut'] == 18   # 2 / sin^2(20) = 17.1
    assert not spur_gear_dimensions(2, 18)['undercut'] and spur_gear_dimensions(2, 17)['undercut']
    # a positive profile shift pulls the cutter out: 16 teeth at 20 degrees need x >= 1 - 16 sin^2(20) / 2 = 0.064
    assert not spur_gear_dimensions(2, 16, profile_shift=0.07)['undercut']
    assert spur_gear_dimensions(2, 16, profile_shift=0.06)['undercut']


def test_a_base_circle_above_the_root_circle_is_noted():
    d = spur_gear_dimensions(2, 12)
    assert d['base_diameter_mm'] > d['root_diameter_mm']
    assert any('base circle' in note for note in d['notes'])
    assert spur_gear_dimensions(2, 60)['base_diameter_mm'] < spur_gear_dimensions(2, 60)['root_diameter_mm']


def test_pair_centre_distance_and_contact_ratio():
    p = gear_pair_dimensions(2, 18, 40)
    assert p['centre_distance_mm'] == pytest.approx(58)
    assert p['working_pressure_angle_deg'] == pytest.approx(20)
    assert p['ratio'] == pytest.approx(40 / 18)
    assert p['tip_clearance_mm'] == pytest.approx(0.5)
    a = math.radians(20)
    length = (math.sqrt(20 ** 2 - (18 * math.cos(a)) ** 2) + math.sqrt(42 ** 2 - (40 * math.cos(a)) ** 2)
              - 58 * math.sin(a))                                 # path of contact between the two tip circles
    assert p['contact_ratio'] == pytest.approx(length / (2 * math.pi * math.cos(a)))
    assert 1.5 < p['contact_ratio'] < 1.7
    assert not p['tip_past_involute'] and not p['contact_shortened']
    assert p['mesh_rotation_b_deg'] == pytest.approx(4.5)         # half a pitch of the 40-tooth gear
    assert gear_pair_dimensions(2, 18, 41)['mesh_rotation_b_deg'] == 0
    assert p['a']['teeth'] == 18 and p['b']['pitch_diameter_mm'] == pytest.approx(80)


def test_an_undercut_pinion_shortens_the_contact():
    p = gear_pair_dimensions(2, 16, 48, pressure_angle=14.5)
    assert p['a']['undercut'] and p['contact_shortened'] and not p['tip_past_involute']
    a = math.radians(14.5)
    full = (math.sqrt(18 ** 2 - (16 * math.cos(a)) ** 2) + math.sqrt(50 ** 2 - (48 * math.cos(a)) ** 2)
            - 64 * math.sin(a)) / (2 * math.pi * math.cos(a))
    assert p['contact_ratio'] < full


def test_profile_shift_moves_the_centre_distance_to_the_working_pressure_angle():
    p = gear_pair_dimensions(2, 16, 48, pressure_angle=14.5, profile_shift_a=0.5)
    a, w = math.radians(14.5), math.radians(p['working_pressure_angle_deg'])
    assert inv(w) == pytest.approx(inv(a) + 2 * math.tan(a) * 0.5 / 64)
    assert p['centre_distance_mm'] == pytest.approx(64 * math.cos(a) / math.cos(w))
    assert 64 < p['centre_distance_mm'] < 65                      # less than the 1 mm the shift alone would add
    assert p['tip_clearance_mm'] < 0.5 and p['backlash_mm'] is None
    balanced = gear_pair_dimensions(2, 16, 48, profile_shift_a=0.3, profile_shift_b=-0.3, backlash=0.04)
    assert balanced['centre_distance_mm'] == pytest.approx(64) and balanced['backlash_mm'] == pytest.approx(0.08)


def test_a_tip_that_works_inside_the_involute_is_flagged():
    # A nearly full root round ends the cutter's straight side 0.94 modules down, so the involute starts higher than
    # the tip of a large mate reaches: gear a's active profile must start at
    # sqrt(rb^2 + (a sin(alpha) - sqrt(ra_b^2 - rb_b^2))^2), inside its involute.
    p = gear_pair_dimensions(2, 30, 120, root_fillet=0.47)
    a = math.radians(20)
    active = math.hypot(30 * math.cos(a), 150 * math.sin(a) - math.sqrt(122 ** 2 - (120 * math.cos(a)) ** 2))
    assert active < p['a']['involute_start_diameter_mm'] / 2
    assert p['tip_past_involute'] and any('root fillet' in note for note in p['notes'])
    standard = gear_pair_dimensions(2, 30, 120)
    assert active > standard['a']['involute_start_diameter_mm'] / 2 and not standard['tip_past_involute']


@pytest.mark.parametrize('kwargs', [
    dict(module=0, teeth=20), dict(module=2, teeth=3), dict(module=2, teeth=20.5),
    dict(module=2, teeth=20, pressure_angle=45), dict(module=2, teeth=20, backlash=-0.1),
    dict(module=2, teeth=20, backlash=4), dict(module=2, teeth=20, root_fillet=0.9),
    dict(module=2, teeth=20, profile_shift=1.3), dict(module=2, teeth=20, clearance=0.6, pressure_angle=30),
])
def test_impossible_gears_are_refused(kwargs):
    with pytest.raises(ValueError):
        spur_gear_dimensions(**kwargs)


def test_bevel_reference_dimensions():
    d = bevel_gear_dimensions(2, 16, 32, 8)
    delta = math.atan(16 / 32)
    assert d['pitch_angle_deg'] == pytest.approx(math.degrees(delta))
    assert d['pitch_angle_deg'] + bevel_gear_dimensions(2, 32, 16, 8)['pitch_angle_deg'] == pytest.approx(90)
    assert d['cone_distance_mm'] == pytest.approx(math.hypot(16, 32))      # sqrt(r1^2 + r2^2)
    assert d['pitch_diameter_mm'] == pytest.approx(32)
    assert d['pitch_circle_z_mm'] == pytest.approx(32)                     # the mate's pitch radius
    assert d['tip_diameter_mm'] == pytest.approx(32 + 2 * 2 * math.cos(delta))
    assert d['virtual_teeth'] == pytest.approx(16 / math.cos(delta))       # Tredgold
    assert d['tooth_thickness_mm'] == pytest.approx(math.pi)
    assert d['tip_angle_deg'] == pytest.approx(math.degrees(delta + math.atan(2 / d['cone_distance_mm'])))
    assert d['root_angle_deg'] == pytest.approx(math.degrees(delta - math.atan(2.5 / d['cone_distance_mm'])))
    assert d['front_face_z_mm'] == pytest.approx(d['back_face_z_mm'] * (1 - 8 / d['cone_distance_mm']))
    assert bevel_gear_dimensions(2, 20, 20, 8)['pitch_angle_deg'] == pytest.approx(45)
    assert bevel_gear_dimensions(2, 12, 24, 6)['undercut']                 # 13.4 virtual teeth
    assert any('third' in note for note in bevel_gear_dimensions(2, 16, 32, 14)['notes'])
    for bad in (dict(face_width=40), dict(face_width=0), dict(teeth=16.5), dict(backing=40)):
        with pytest.raises(ValueError):
            bevel_gear_dimensions(**{**dict(module=2, teeth=16, mate_teeth=32, face_width=8), **bad})


# ---- solids --------------------------------------------------------------------------------------------------------

@pytest.fixture(scope='module')
def cq():
    return pytest.importorskip('cadquery')


def turned(cq, solid, degrees):
    return solid.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), degrees)


def common(a, b):
    return a.intersect(b).Volume()


def thickness_at(cq, solid, radius, teeth, width, half=0.02):
    """Arc tooth thickness on the circle of ``radius``, from the metal inside a thin tube there."""
    tube = cq.Solid.makeCylinder(radius + half, width).cut(cq.Solid.makeCylinder(radius - half, width))
    return common(solid, tube) / (teeth * 2 * half * width)


def test_spur_gear_is_one_valid_solid_with_the_right_teeth_and_radii(cq):
    teeth, width = 18, 6
    d = spur_gear_dimensions(2, teeth)
    gear = spur_gear(2, teeth, width, bore=8)
    assert gear.isValid() and len(gear.Solids()) == 1
    box = gear.BoundingBox()
    assert (box.zmin, box.zmax) == pytest.approx((0, width), abs=1e-6)
    assert box.xmax == pytest.approx(d['tip_diameter_mm'] / 2, abs=1e-4)      # tooth 0 lies on +X
    # tooth count: a turn of one tooth pitch maps the gear onto itself, half a pitch does not
    volume = gear.Volume()
    assert common(gear, turned(cq, gear, 360 / teeth)) == pytest.approx(volume, rel=1e-6)
    assert common(gear, turned(cq, gear, 180 / teeth)) < 0.9 * volume
    assert common(gear, turned(cq, gear, 360 / (teeth + 1))) < 0.99 * volume
    # root circle: a disc just inside it is all metal (less the bore), one just outside is not
    root = d['root_diameter_mm'] / 2

    def disc(radius):
        return math.pi * (radius ** 2 - 4 ** 2) * width
    assert common(gear, cq.Solid.makeCylinder(root - 0.001, width)) == pytest.approx(disc(root - 0.001), rel=1e-6)
    assert common(gear, cq.Solid.makeCylinder(root + 0.2, width)) < disc(root + 0.2) * 0.999
    # nothing outside the tip circle
    tip = d['tip_diameter_mm'] / 2
    assert common(gear, cq.Solid.makeCylinder(tip + 1e-4, width)) == pytest.approx(volume, rel=1e-9)
    assert common(gear, cq.Solid.makeCylinder(tip - 0.2, width)) < volume * 0.999


@pytest.mark.parametrize('teeth,angle,backlash,shift', [(20, 20, 0.1, 0.0), (32, 14.5, 0.06, 0.0),
                                                        (18, 20, 0.0, 0.3)])
def test_tooth_thickness_follows_the_involute(cq, teeth, angle, backlash, shift):
    module, width = 2, 4
    gear = spur_gear(module, teeth, width, pressure_angle=angle, backlash=backlash, profile_shift=shift)
    d = spur_gear_dimensions(module, teeth, pressure_angle=angle, backlash=backlash, profile_shift=shift)
    pitch = module * teeth / 2
    expected = module * (math.pi / 2 + 2 * shift * math.tan(math.radians(angle))) - backlash
    assert thickness_at(cq, gear, pitch, teeth, width) == pytest.approx(expected, abs=2e-3)
    low = d['involute_start_diameter_mm'] / 2 + 0.05
    for radius in (low, d['tip_diameter_mm'] / 2 - 0.05):
        assert thickness_at(cq, gear, radius, teeth, width) == pytest.approx(
            involute_thickness(module, teeth, angle, radius, backlash, shift), abs=2e-3)


def test_an_undercut_gear_is_drawn_undercut_and_warns(cq):
    module, teeth, width = 2, 16, 4
    with pytest.warns(UserWarning, match='undercut'):
        gear = spur_gear(module, teeth, width, pressure_angle=14.5)
    assert gear.isValid() and len(gear.Solids()) == 1
    d = spur_gear_dimensions(module, teeth, pressure_angle=14.5)
    base, start = d['base_diameter_mm'] / 2, d['involute_start_diameter_mm'] / 2
    # above the crossing the flank is the involute; between the base circle and the crossing metal is missing
    assert thickness_at(cq, gear, start + 0.05, teeth, width) == pytest.approx(
        involute_thickness(module, teeth, 14.5, start + 0.05), abs=2e-3)
    inside = (base + start) / 2
    assert thickness_at(cq, gear, inside, teeth, width, half=0.005) < involute_thickness(module, teeth, 14.5, inside) - 5e-4
    # the tooth is narrower at the neck than at the base circle: the mark of an undercut
    assert thickness_at(cq, gear, base - 0.6, teeth, width) < thickness_at(cq, gear, base, teeth, width)
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        spur_gear(module, 32, width, pressure_angle=14.5)          # 32 teeth: no warning


def test_a_gear_with_its_base_circle_above_the_root_builds(cq):
    with pytest.warns(UserWarning):
        gear = spur_gear(2, 10, 5)
    assert gear.isValid() and len(gear.Solids()) == 1
    d = spur_gear_dimensions(2, 10)
    assert d['base_diameter_mm'] > d['root_diameter_mm']
    assert common(gear, turned(cq, gear, 36)) == pytest.approx(gear.Volume(), rel=1e-6)
    sharp = spur_gear(2, 30, 5, root_fillet=0)                    # a sharp cutter corner: plain trochoid root
    full = spur_gear(2, 30, 5, root_fillet=0.47)                  # close to a full round: almost no root arc
    assert sharp.isValid() and full.isValid() and sharp.Volume() < spur_gear(2, 30, 5).Volume() < full.Volume()


def mesh(cq, pair, a, b, turn=0.0, nudge=0.0, shift=0.0):
    """Gear b placed against gear a (turned by ``turn`` degrees, b following), a nudged on or the centres moved."""
    ratio = pair['a']['teeth'] / pair['b']['teeth']
    placed = turned(cq, b, pair['mesh_rotation_b_deg'] - turn * ratio).translate(
        cq.Vector(pair['centre_distance_mm'] + shift, 0, 0))
    return common(turned(cq, a, turn + nudge), placed)


@pytest.mark.parametrize('teeth_a,teeth_b,angle,shift_a', [(18, 40, 20, 0.0), (16, 48, 14.5, 0.0), (16, 48, 14.5, 0.5)])
def test_a_pair_meshes_at_the_centre_distance_with_the_backlash_it_was_given(cq, teeth_a, teeth_b, angle, shift_a):
    module, backlash = 2, 0.05
    options = dict(pressure_angle=angle, backlash=backlash)
    pair = gear_pair_dimensions(module, teeth_a, teeth_b, profile_shift_a=shift_a, **options)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')                            # the undercut pinions say so; tested above
        a = spur_gear(module, teeth_a, 4, profile_shift=shift_a, **options)
        b = spur_gear(module, teeth_b, 4, **options)
    radius = module * teeth_a / 2
    free = math.degrees(backlash / radius)                         # each gear is thinned by the backlash allowance
    for step in range(2):                                          # two phases of one tooth pitch
        turn = step * 360 / teeth_a / 2 * 0.8
        assert mesh(cq, pair, a, b, turn) < 1e-6
        for side in (1, -1):                                       # a may turn either way by the play, and no more
            assert mesh(cq, pair, a, b, turn, nudge=side * 0.7 * free) < 1e-6
            assert mesh(cq, pair, a, b, turn, nudge=side * 1.3 * free) > 1e-4
    assert mesh(cq, pair, a, b, shift=-0.3) > 0.1                  # centres too close: the teeth collide
    assert mesh(cq, pair, a, b, turn=180 / teeth_a, shift=-0.3) > 0.1


def test_teeth_without_backlash_touch_without_overlap(cq):
    pair = gear_pair_dimensions(2, 18, 40)
    a, b = spur_gear(2, 18, 4), spur_gear(2, 40, 4)
    for turn in (0, 5, 10, 15):
        assert mesh(cq, pair, a, b, turn) < 1e-4
        assert mesh(cq, pair, a, b, turn, nudge=0.05) > 1e-3       # 0.016 mm at the pitch circle
        assert mesh(cq, pair, a, b, turn, nudge=-0.05) > 1e-3
    assert mesh(cq, pair, a, b, shift=-0.05) > 1e-3


def test_ring_gear_is_the_same_teeth_on_a_ring(cq):
    module, teeth, width, inner = 2, 40, 8, 60
    d = spur_gear_dimensions(module, teeth)
    ring = external_ring_gear(module, teeth, width, inner, backlash=0.05)
    assert ring.isValid() and len(ring.Solids()) == 1
    solid = spur_gear(module, teeth, width, backlash=0.05)
    assert ring.Volume() == pytest.approx(solid.Volume() - math.pi * 30 ** 2 * width, rel=1e-9)
    assert common(ring, cq.Solid.makeCylinder(29.999, width)) == pytest.approx(0, abs=1e-6)
    assert common(ring, turned(cq, ring, 9)) == pytest.approx(ring.Volume(), rel=1e-6)
    assert thickness_at(cq, ring, 40, teeth, width) == pytest.approx(math.pi - 0.05, abs=2e-3)
    assert d['root_diameter_mm'] == pytest.approx(75)
    with pytest.raises(ValueError, match='Rim'):
        external_ring_gear(module, teeth, width, 74)              # 0.5 mm of rim, under one module
    assert external_ring_gear(module, teeth, width, 74, min_rim=0.4).isValid()
    with pytest.raises(ValueError):
        spur_gear(module, teeth, width, bore=75)
    with pytest.raises(ValueError):
        spur_gear(module, teeth, 0)


def test_a_176_tooth_gear_builds_in_seconds(cq):
    start = time.perf_counter()
    gear = spur_gear(1.5, 176, 10, bore=200)
    elapsed = time.perf_counter() - start
    assert gear.isValid() and len(gear.Solids()) == 1
    assert elapsed < 20                                            # 0.2 to 0.8 s on a desktop; the bound is for slow CI
    assert gear.BoundingBox().xmax == pytest.approx(1.5 * 178 / 2, abs=1e-4)


# ---- straight bevel gears ------------------------------------------------------------------------------------------

def test_bevel_gear_is_one_valid_solid_with_the_right_cone(cq):
    module, teeth, mate, width = 2, 16, 32, 6
    d = bevel_gear_dimensions(module, teeth, mate, width, backlash=0.05)
    gear = bevel_gear(module, teeth, mate, width, backlash=0.05, bore=5)
    assert isinstance(gear, cq.Solid) and gear.isValid()
    volume = gear.Volume()
    assert common(gear, turned(cq, gear, 360 / teeth)) == pytest.approx(volume, rel=1e-5)
    assert common(gear, turned(cq, gear, 180 / teeth)) < 0.95 * volume
    box = gear.BoundingBox()
    assert box.xmax == pytest.approx(d['tip_diameter_mm'] / 2, abs=1e-3)      # the large-end tip circle
    assert box.zmax == pytest.approx(d['back_face_z_mm'], abs=1e-4)
    # Teeth taper to the apex: on the pitch cone, the tooth is as thick as its share of the cone distance.
    delta, cone = math.radians(d['pitch_angle_deg']), d['cone_distance_mm']
    for inset in (1.0, 5.0):
        along, side = cone - inset, 0.04
        r, z = along * math.sin(delta), along * math.cos(delta)
        ring = (cq.Workplane('XZ').polyline([(r - side, z - side), (r + side, z - side), (r + side, z + side),
                                             (r - side, z + side)]).close().revolve(360, (0, 0, 0), (0, 1, 0)).val())
        measured = common(gear, ring) / (teeth * (2 * side) ** 2)
        assert measured == pytest.approx((math.pi - 0.05) * along / cone, abs=3e-3)
    # The tip and root cones pass through the apex: metal ends at the tip angle and is solid inside the root angle.
    def cone_shell(angle_deg, z0, z1):
        t = math.tan(math.radians(angle_deg))
        return (cq.Workplane('XZ').polyline([(0, z0), (z0 * t, z0), (z1 * t, z1), (0, z1)]).close()
                .revolve(360, (0, 0, 0), (0, 1, 0)).val())
    z0, z1 = d['front_face_z_mm'] + 0.5, d['front_face_z_mm'] + 3
    inside = cone_shell(d['root_angle_deg'] - 0.01, z0, z1).cut(cq.Solid.makeCylinder(2.5, 50))
    assert common(gear, inside) == pytest.approx(inside.Volume(), rel=1e-6)
    outer = common(gear, cone_shell(d['tip_angle_deg'] + 0.01, z0, z1))
    slab = common(gear, cq.Solid.makeCylinder(60, z1 - z0, cq.Vector(0, 0, z0)))
    assert outer == pytest.approx(slab, rel=1e-9)
    assert common(gear, cone_shell(d['tip_angle_deg'] - 0.5, z0, z1)) < slab * 0.999


def bevel_mesh(cq, a, b, da, db, turn=0.0, nudge=0.0, push=0.0):
    """Gear a on +Z and gear b on +X with a common apex; b pushed toward the apex by ``push``."""
    ratio = da['teeth'] / db['teeth']
    placed = turned(cq, b, db['mesh_rotation_deg'] - turn * ratio).rotate(
        cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), 90).translate(cq.Vector(-push, 0, 0))
    return common(turned(cq, a, turn + nudge), placed)


@pytest.mark.parametrize('teeth_a,teeth_b,angle', [(16, 32, 20), (15, 30, 14.5)])
def test_a_bevel_pair_meshes_at_90_degrees_with_the_backlash_it_was_given(cq, teeth_a, teeth_b, angle):
    module, width, backlash = 2, 6, 0.05
    options = dict(pressure_angle=angle, backlash=backlash)
    da = bevel_gear_dimensions(module, teeth_a, teeth_b, width, **options)
    db = bevel_gear_dimensions(module, teeth_b, teeth_a, width, **options)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        a = bevel_gear(module, teeth_a, teeth_b, width, **options)
        b = bevel_gear(module, teeth_b, teeth_a, width, **options)
    free = math.degrees(backlash / (module * teeth_a / 2))
    assert bevel_mesh(cq, a, b, da, db) < 1e-6
    turn = 0.3 * 360 / teeth_a
    assert bevel_mesh(cq, a, b, da, db, turn) < 1e-6
    for side in (1, -1):                                           # a may turn either way by the play, and no more
        assert bevel_mesh(cq, a, b, da, db, turn, nudge=side * 0.6 * free) < 1e-6
        assert bevel_mesh(cq, a, b, da, db, turn, nudge=side * 1.4 * free) > 1e-4
    assert bevel_mesh(cq, a, b, da, db, push=0.3) > 0.1           # mounted too close to the apex: collision


def test_an_undercut_bevel_warns(cq):
    with pytest.warns(UserWarning, match='undercut'):
        gear = bevel_gear(2, 12, 24, 6)
    assert isinstance(gear, cq.Solid) and gear.isValid()
    with pytest.raises(ValueError):
        bevel_gear(2, 16, 32, 8, bore=40)


def test_public_names():
    assert set(gears.__all__) == {'module_from_diametral_pitch', 'spur_gear_dimensions', 'gear_pair_dimensions',
                                  'spur_gear', 'external_ring_gear', 'bevel_gear_dimensions', 'bevel_gear'}
