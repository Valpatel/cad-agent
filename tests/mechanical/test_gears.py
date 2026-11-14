"""cadagent.mechanical.gears: the reference dimensions against closed forms written out here, and the solids
measured: tooth count, radii, tooth thickness, play in mesh and interference, not only that they build.

To keep the file quick, each gear is built once (``built``), a spur gear is measured on its flat end face (it is a
prism, which is checked), and a bevel pair's play is measured between the teeth near the mesh.
"""
import math
import warnings

import pytest

from cadagent.mechanical import gears
from cadagent.mechanical.gears import (bevel_gear, bevel_gear_dimensions, external_ring_gear, gear_pair_dimensions,
                                       spur_gear, spur_gear_dimensions)

NAN, INF = float('nan'), float('inf')


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


def test_an_inch_gear_is_its_diametral_pitch_as_a_module_in_mm():
    d = spur_gear_dimensions(25.4 / 12, 16)                       # 12 DP: the module is 25.4 / 12 mm
    assert d['pitch_diameter_mm'] == pytest.approx(25.4 * 16 / 12)    # 16 teeth / 12 per inch, in mm
    assert d['module_mm'] == pytest.approx(2.1167, abs=1e-4)


def test_a_14_5_degree_16_tooth_gear_reports_its_undercut():
    d = spur_gear_dimensions(25.4 / 12, 16, pressure_angle=14.5)
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


@pytest.mark.parametrize('value', [NAN, INF, -INF])
def test_nan_and_infinity_are_refused_by_name(value):
    # A comparison such as ``backlash < 0`` is false for NaN, so each number is checked for being finite first.
    for name in ('module', 'teeth', 'pressure_angle', 'backlash', 'clearance', 'root_fillet', 'profile_shift'):
        with pytest.raises(ValueError):
            spur_gear_dimensions(**{**dict(module=2, teeth=20), name: value})
    for name in ('module', 'teeth', 'mate_teeth', 'face_width', 'pressure_angle', 'backlash', 'clearance',
                 'root_fillet', 'backing'):
        with pytest.raises(ValueError):
            bevel_gear_dimensions(**{**dict(module=2, teeth=16, mate_teeth=32, face_width=8), name: value})
    with pytest.raises(ValueError, match='Profile shift must be a finite number'):
        gear_pair_dimensions(2, 18, 40, profile_shift_b=value)
    with pytest.raises(ValueError, match='Backlash allowance must be a finite number'):
        spur_gear_dimensions(2, 20, backlash=value)
    with pytest.raises(ValueError, match='Tooth count must be a whole number'):
        spur_gear_dimensions(2, value)                            # infinity used to raise OverflowError


def test_bad_sizes_are_refused_before_any_solid_is_made():
    # None of these reaches the CAD kernel: the checks come first.
    for bad in (dict(bore=NAN), dict(bore=-1), dict(face_width=NAN), dict(face_width=INF), dict(face_width=0),
                dict(chord_tolerance=NAN), dict(chord_tolerance=0)):
        with pytest.raises(ValueError):
            spur_gear(**{**dict(module=2, teeth=20, face_width=5), **bad})
    # A plain bore keeps one module of wall under the root circle (root diameter 35 mm, so 31 mm at most).
    with pytest.raises(ValueError, match='31.000 mm'):
        spur_gear(2, 20, 5, bore=35 - 1e-6)
    with pytest.raises(ValueError, match='wall of one module'):
        spur_gear(2, 20, 5, bore=31.01)
    for bad in (dict(inner_diameter=NAN), dict(inner_diameter=0), dict(min_rim=NAN), dict(min_rim=0),
                dict(inner_diameter=74)):                         # 0.5 mm of rim, under one module
        with pytest.raises(ValueError):
            external_ring_gear(**{**dict(module=2, teeth=40, face_width=8, inner_diameter=60), **bad})
    with pytest.raises(TypeError, match="external_ring_gear.*'bore'"):   # its hole is inner_diameter
        external_ring_gear(2, 40, 8, 60, bore=5)
    for bad in (dict(bore=NAN), dict(bore=40), dict(chord_tolerance=NAN), dict(face_width=NAN), dict(backing=NAN),
                dict(backing=-1)):
        with pytest.raises(ValueError):
            bevel_gear(**{**dict(module=2, teeth=16, mate_teeth=32, face_width=8), **bad})


def test_bevel_face_width_and_tooth_count_limits_are_named():
    cone = math.hypot(16, 32)                                     # module 2: half of 2 * sqrt(16^2 + 32^2)
    assert bevel_gear_dimensions(2, 16, 32, cone / 3 - 0.01)['notes'] == []
    assert any('third' in note for note in bevel_gear_dimensions(2, 16, 32, cone / 3 + 0.01)['notes'])
    assert bevel_gear_dimensions(2, 16, 32, 0.9 * cone - 0.01)['face_width_mm'] == pytest.approx(0.9 * cone - 0.01)
    for width in (0.9 * cone + 0.01, 0.999 * cone, cone, 40):
        with pytest.raises(ValueError, match='0.9 of the cone distance'):
            bevel_gear_dimensions(2, 16, 32, width)
    with pytest.raises(ValueError, match='4-tooth bevel gear with a 40-tooth mate'):
        bevel_gear_dimensions(2, 4, 40, 10)                       # no room for a back face under the root
    assert bevel_gear_dimensions(2, 4, 40, 10, backing=0)['teeth'] == 4


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


@pytest.fixture(scope='module')
def built(cq):
    """``built(name, *args, **kwargs)``: that gear and the warnings it raised, made once for the whole file."""
    cache = {}

    def build(name, *args, **kwargs):
        key = (name, args, tuple(sorted(kwargs.items())))
        if key not in cache:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                solid = getattr(gears, name)(*args, **kwargs)
            cache[key] = (solid, caught)
        return cache[key]
    return build


def turned(cq, shape, degrees, axis=(0, 0, 1)):
    return shape.rotate(cq.Vector(0, 0, 0), cq.Vector(*axis), degrees)


def common(a, b):
    """Volume that two solids share."""
    return a.intersect(b).Volume()


def shared(a, b):
    """Area that two faces in one plane share."""
    return a.intersect(b).Area()


def disc(cq, radius, hole=0.0, z=0.0):
    """A flat disc (a ring when ``hole`` is a radius) on the plane Z = z, about the Z axis."""
    centre, up = cq.Vector(0, 0, z), cq.Vector(0, 0, 1)
    inner = [cq.Wire.makeCircle(hole, centre, up)] if hole else []
    return cq.Face.makeFromWires(cq.Wire.makeCircle(radius, centre, up), inner)


def end_face(gear, width):
    """The Z = 0 face of a spur gear, after checking that the gear is the prism of that face."""
    face = gear.faces('<Z')
    box = gear.BoundingBox()
    assert (box.zmin, box.zmax) == pytest.approx((0, width), abs=1e-6)
    assert gear.faces('>Z').Area() == pytest.approx(face.Area(), rel=1e-9)
    assert gear.Volume() == pytest.approx(face.Area() * width, rel=2e-5)      # the kernel integrates the two apart
    return face


def thickness_at(cq, face, radius, teeth, half=0.02, z=0.0):
    """Arc tooth thickness on the circle of ``radius``, from the metal of a flat section inside a thin ring there."""
    return shared(face, disc(cq, radius + half, radius - half, z)) / (teeth * 2 * half)


def test_spur_gear_is_one_valid_solid_with_the_right_teeth_and_radii(cq, built):
    teeth, width = 18, 6
    d = spur_gear_dimensions(2, teeth)
    gear, _ = built('spur_gear', 2, teeth, width, bore=8)
    assert gear.isValid() and len(gear.Solids()) == 1
    assert gear.BoundingBox().xmax == pytest.approx(d['tip_diameter_mm'] / 2, abs=1e-4)   # tooth 0 lies on +X
    face = end_face(gear, width)
    # tooth count: a turn of one tooth pitch maps the gear onto itself, half a pitch does not
    area = face.Area()
    assert shared(face, turned(cq, face, 360 / teeth)) == pytest.approx(area, rel=1e-6)
    assert shared(face, turned(cq, face, 180 / teeth)) < 0.9 * area
    assert shared(face, turned(cq, face, 360 / (teeth + 1))) < 0.99 * area
    # root circle: a disc just inside it is all metal (less the bore), one just outside is not
    root = d['root_diameter_mm'] / 2

    def ring(radius):
        return math.pi * (radius ** 2 - 4 ** 2)
    assert shared(face, disc(cq, root - 0.001)) == pytest.approx(ring(root - 0.001), rel=1e-6)
    assert shared(face, disc(cq, root + 0.2)) < ring(root + 0.2) * 0.999
    # nothing outside the tip circle
    tip = d['tip_diameter_mm'] / 2
    assert shared(face, disc(cq, tip + 1e-4)) == pytest.approx(area, rel=1e-9)
    assert shared(face, disc(cq, tip - 0.2)) < area * 0.999


@pytest.mark.parametrize('teeth,angle,backlash,shift', [(20, 20, 0.1, 0.0), (32, 14.5, 0.06, 0.0),
                                                        (18, 20, 0.0, 0.3)])
def test_tooth_thickness_follows_the_involute(cq, built, teeth, angle, backlash, shift):
    module, width = 2, 4
    gear, _ = built('spur_gear', module, teeth, width, pressure_angle=angle, backlash=backlash, profile_shift=shift)
    face = end_face(gear, width)
    d = spur_gear_dimensions(module, teeth, pressure_angle=angle, backlash=backlash, profile_shift=shift)
    pitch = module * teeth / 2
    expected = module * (math.pi / 2 + 2 * shift * math.tan(math.radians(angle))) - backlash
    assert thickness_at(cq, face, pitch, teeth) == pytest.approx(expected, abs=2e-3)
    low = d['involute_start_diameter_mm'] / 2 + 0.05
    for radius in (low, d['tip_diameter_mm'] / 2 - 0.05):
        assert thickness_at(cq, face, radius, teeth) == pytest.approx(
            involute_thickness(module, teeth, angle, radius, backlash, shift), abs=2e-3)


def test_an_undercut_gear_is_drawn_undercut_and_warns(cq, built):
    module, teeth, width = 2, 16, 4
    with pytest.warns(UserWarning, match='undercut') as raised:
        gear = spur_gear(module, teeth, width, pressure_angle=14.5)
    assert raised[0].filename == __file__                          # the warning points at the caller
    assert gear.isValid() and len(gear.Solids()) == 1
    face = end_face(gear, width)
    d = spur_gear_dimensions(module, teeth, pressure_angle=14.5)
    base, start = d['base_diameter_mm'] / 2, d['involute_start_diameter_mm'] / 2
    # above the crossing the flank is the involute; between the base circle and the crossing metal is missing
    assert thickness_at(cq, face, start + 0.05, teeth) == pytest.approx(
        involute_thickness(module, teeth, 14.5, start + 0.05), abs=2e-3)
    inside = (base + start) / 2
    assert (thickness_at(cq, face, inside, teeth, half=0.005)
            < involute_thickness(module, teeth, 14.5, inside) - 5e-4)
    # the tooth is narrower at the neck than at the base circle: the mark of an undercut
    assert thickness_at(cq, face, base - 0.6, teeth) < thickness_at(cq, face, base, teeth)
    assert built('spur_gear', module, 32, width, pressure_angle=14.5)[1] == []   # 32 teeth: no warning
    with pytest.warns(UserWarning, match='undercut') as raised:    # a ring warns for its own caller too
        external_ring_gear(module, teeth, width, 20, pressure_angle=14.5)
    assert raised[0].filename == __file__


def test_a_gear_with_its_base_circle_above_the_root_builds(cq, built):
    gear, raised = built('spur_gear', 2, 10, 5)
    assert len(raised) == 1 and 'undercut' in str(raised[0].message)
    assert gear.isValid() and len(gear.Solids()) == 1
    d = spur_gear_dimensions(2, 10)
    assert d['base_diameter_mm'] > d['root_diameter_mm']
    face = end_face(gear, 5)
    assert shared(face, turned(cq, face, 36)) == pytest.approx(face.Area(), rel=1e-6)
    sharp = spur_gear(2, 30, 5, root_fillet=0)                    # a sharp cutter corner: plain trochoid root
    full = spur_gear(2, 30, 5, root_fillet=0.47)                  # close to a full round: almost no root arc
    assert sharp.isValid() and full.isValid() and sharp.Volume() < spur_gear(2, 30, 5).Volume() < full.Volume()


def test_a_chord_tolerance_that_cannot_be_met_is_refused(cq):
    with pytest.raises(ValueError, match='Chord tolerance 1e-09 mm is not reached'):
        spur_gear(2, 20, 5, chord_tolerance=1e-9)
    fine, coarse = spur_gear(2, 20, 5, chord_tolerance=1e-5), spur_gear(2, 20, 5, chord_tolerance=0.05)
    assert fine.isValid() and coarse.isValid()
    assert fine.Volume() == pytest.approx(spur_gear(2, 20, 5).Volume(), rel=1e-5)


def test_the_same_arguments_give_the_same_solid(cq, built):
    def corners(solid):
        return sorted((v.X, v.Y, v.Z) for v in solid.Vertices())
    for name, args, options in (('spur_gear', (2, 10, 5), {}), ('bevel_gear', WIDE_UNDERCUT_BEVEL, WIDE_OPTIONS)):
        first, _ = built(name, *args, **options)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')                        # both warn; tested elsewhere
            again = getattr(gears, name)(*args, **options)
        # The kernel's last bit varies from build to build, so the corners are compared to a nanometre.
        assert len(corners(again)) == len(corners(first))
        for one, other in zip(corners(again), corners(first)):
            assert one == pytest.approx(other, abs=1e-9)
        assert again.Volume() == pytest.approx(first.Volume(), rel=1e-12)
    assert spur_gear_dimensions(2, 10) == spur_gear_dimensions(2, 10)


# A 10-tooth mitre gear at 14.5 degrees: 14.1 virtual teeth where 32 avoid undercut, and a 5 mm face on a 14.14 mm
# cone (a third is 4.71 mm). One gear is both halves of its pair.
WIDE_UNDERCUT_BEVEL = (2, 10, 10, 5)
WIDE_OPTIONS = dict(pressure_angle=14.5, backlash=0.05)
PLAY_TOLERANCE = 1e-3                                              # mm, on a measured gap between flanks


def meshed(cq, pair, a, b, turn=0.0, nudge=0.0, shift=0.0):
    """End faces a and b in mesh: a turned by ``turn`` degrees and b following, a nudged on or the centres moved."""
    ratio = pair['a']['teeth'] / pair['b']['teeth']
    placed = turned(cq, b, pair['mesh_rotation_b_deg'] - turn * ratio).translate(
        cq.Vector(pair['centre_distance_mm'] + shift, 0, 0))
    return turned(cq, a, turn + nudge), placed


def flank_gap(cq, pair, a, b, **placing):
    """Smallest distance between the two meshed end faces, measured on the teeth near the line of centres.

    Only the metal within 9 mm of that line is kept (the teeth in mesh are within 5 mm of it): cutting metal away can
    only widen a gap, so a gap that equals the expected play was measured where the teeth are closest.
    """
    first, second = meshed(cq, pair, a, b, **placing)
    near = cq.Face.makePlane(20, 18, cq.Vector(pair['a']['pitch_diameter_mm'] / 2, 0, 0), cq.Vector(0, 0, 1))
    return first.intersect(near).distance(second.intersect(near))


@pytest.mark.parametrize('teeth_a,teeth_b,angle,shift_a', [(18, 40, 20, 0.0), (16, 48, 14.5, 0.0),
                                                           (16, 48, 14.5, 0.5)])
def test_a_pair_meshes_at_the_centre_distance_with_the_backlash_it_was_given(cq, built, teeth_a, teeth_b, angle,
                                                                             shift_a):
    module, width, backlash = 2, 4, 0.05
    options = dict(pressure_angle=angle, backlash=backlash)
    pair = gear_pair_dimensions(module, teeth_a, teeth_b, profile_shift_a=shift_a, **options)
    a = end_face(built('spur_gear', module, teeth_a, width, profile_shift=shift_a, **options)[0], width)
    b = end_face(built('spur_gear', module, teeth_b, width, **options)[0], width)
    pitch = 360 / teeth_a
    for step in range(12):                                         # no metal in common anywhere in one tooth pitch
        assert shared(*meshed(cq, pair, a, b, step * pitch / 12)) < 1e-9
    # Each tooth is thinned by the allowance along its pitch circle, so a flank stands backlash * cos(pressure
    # angle) off its mate, measured square to the flank, on both sides; and gear a turns by backlash / radius
    # either way before it touches.
    play = backlash * math.cos(math.radians(angle))
    free = math.degrees(backlash / (module * teeth_a / 2))
    for turn in (0.0, 0.4 * pitch):
        assert flank_gap(cq, pair, a, b, turn=turn) == pytest.approx(play, abs=PLAY_TOLERANCE)
        for side in (1, -1):
            assert flank_gap(cq, pair, a, b, turn=turn, nudge=side * 0.7 * free) == pytest.approx(
                0.3 * play, abs=PLAY_TOLERANCE)
            assert shared(*meshed(cq, pair, a, b, turn, nudge=side * 1.3 * free)) > 2.5e-5
    assert shared(*meshed(cq, pair, a, b, shift=-0.3)) > 0.025     # centres too close: the teeth collide
    assert shared(*meshed(cq, pair, a, b, turn=pitch / 2, shift=-0.3)) > 0.025


def test_teeth_without_backlash_touch_without_overlap(cq, built):
    pair = gear_pair_dimensions(2, 18, 40)
    a, b = end_face(built('spur_gear', 2, 18, 4)[0], 4), end_face(built('spur_gear', 2, 40, 4)[0], 4)
    for turn in (0, 5, 10, 15):
        assert shared(*meshed(cq, pair, a, b, turn)) < 2.5e-5 and flank_gap(cq, pair, a, b, turn=turn) < 1e-4
        assert shared(*meshed(cq, pair, a, b, turn, nudge=0.05)) > 2.5e-4     # 0.016 mm at the pitch circle
        assert shared(*meshed(cq, pair, a, b, turn, nudge=-0.05)) > 2.5e-4
    assert shared(*meshed(cq, pair, a, b, shift=-0.05)) > 2.5e-4


def test_ring_gear_is_the_same_teeth_on_a_ring(cq, built):
    module, teeth, width, inner = 2, 40, 8, 60
    d = spur_gear_dimensions(module, teeth)
    ring = external_ring_gear(module, teeth, width, inner, backlash=0.05)
    assert ring.isValid() and len(ring.Solids()) == 1
    solid, _ = built('spur_gear', module, teeth, width, backlash=0.05)
    assert ring.Volume() == pytest.approx(solid.Volume() - math.pi * 30 ** 2 * width, rel=1e-9)
    face = end_face(ring, width)
    assert shared(face, disc(cq, 29.999)) == pytest.approx(0, abs=1e-6)
    assert shared(face, turned(cq, face, 9)) == pytest.approx(face.Area(), rel=1e-6)
    assert thickness_at(cq, face, 40, teeth) == pytest.approx(math.pi - 0.05, abs=2e-3)
    assert d['root_diameter_mm'] == pytest.approx(75)
    thin = external_ring_gear(module, teeth, width, 74, min_rim=0.4)          # 0.5 mm of rim, when asked for
    assert thin.isValid() and len(thin.Solids()) == 1
    assert external_ring_gear(module, teeth, width, 71).isValid()             # exactly one module of rim


def test_a_176_tooth_ring_of_teeth_is_one_valid_solid(cq):
    gear = external_ring_gear(1.5, 176, 10, 200)
    assert gear.isValid() and len(gear.Solids()) == 1
    assert gear.BoundingBox().xmax == pytest.approx(1.5 * 178 / 2, abs=1e-4)
    assert len(gear.Faces()) == 176 * 6 + 3                        # five faces a tooth, a root each, bore and ends


# ---- straight bevel gears ------------------------------------------------------------------------------------------

def test_bevel_gear_is_one_valid_solid_with_the_right_cone(cq, built):
    module, teeth, mate, width = 2, 13, 14, 6
    d = bevel_gear_dimensions(module, teeth, mate, width, backlash=0.05)
    gear, raised = built('bevel_gear', module, teeth, mate, width, pressure_angle=20, backlash=0.05, bore=5)
    assert isinstance(gear, cq.Solid) and gear.isValid() and raised == []
    box = gear.BoundingBox()
    assert box.xmax == pytest.approx(d['tip_diameter_mm'] / 2, abs=1e-3)      # the large-end tip circle
    assert box.zmax == pytest.approx(d['back_face_z_mm'], abs=1e-4)
    delta, cone = math.radians(d['pitch_angle_deg']), d['cone_distance_mm']
    tip, root = math.radians(d['tip_angle_deg']), math.radians(d['root_angle_deg'])
    # Two flat sections square to the axis, between where the root cone leaves the front cone and where the tip
    # cone leaves the back cone, so each crosses the root, pitch and tip cones inside the face width.
    low = (cone - width) * math.cos(root) / math.cos(root - delta)
    high = cone * math.cos(tip) / math.cos(tip - delta)
    assert high - low > 1
    for z in (low + 0.25 * (high - low), low + 0.75 * (high - low)):
        along = z / math.cos(delta)                                # where the section crosses the pitch cone
        section = gear.intersect(disc(cq, 60, z=z))
        area = section.Area()
        # tooth count: a turn of one tooth pitch maps the section onto itself, half a pitch does not
        assert shared(section, turned(cq, section, 360 / teeth)) == pytest.approx(area, rel=1e-6)
        assert shared(section, turned(cq, section, 180 / teeth)) < 0.95 * area
        # teeth taper to the apex: on the pitch cone, the tooth is as thick as its share of the cone distance
        measured = thickness_at(cq, section, along * math.sin(delta), teeth, half=0.04, z=z)
        assert measured == pytest.approx((math.pi - 0.05) * along / cone, abs=1e-3)
        # The tip and root cones pass through the apex: metal ends at the tip angle, and is solid from the front
        # cone (or the bore) out to the root angle and no further.
        front = max((cone - width - z * math.cos(delta)) / math.sin(delta) + 0.01, 2.5)
        inside = disc(cq, z * math.tan(root - math.radians(0.01)), front, z)
        assert inside.Area() > 1 and shared(section, inside) == pytest.approx(inside.Area(), rel=1e-6)
        beyond = disc(cq, z * math.tan(root + math.radians(0.5)), front, z)
        assert shared(section, beyond) < 0.999 * beyond.Area()
        assert shared(section, disc(cq, z * math.tan(tip + math.radians(0.01)), z=z)) == pytest.approx(area, rel=1e-9)
        assert shared(section, disc(cq, z * math.tan(tip - math.radians(0.5)), z=z)) < area * 0.999


class BevelPair:
    """Gear a on +Z and gear b on +X with a common apex, and the teeth of each near the mesh.

    A distance between two whole bevel gears takes seconds; between the slices kept here (the teeth within 5 mm of
    the plane of the two axes) it takes a fraction. Cutting metal away can only widen a gap, so a gap that equals
    the expected play was measured where the teeth are closest.
    """

    def __init__(self, cq, a, b, da, db):
        self.cq, self.ratio = cq, da['teeth'] / db['teeth']
        self.a, self.b = a, turned(cq, turned(cq, b, db['mesh_rotation_deg']), 90, (0, 1, 0))
        reach = da['cone_distance_mm'] + 10
        near = cq.Solid.makeBox(reach, 10, reach, cq.Vector(0, -5, 0))
        self.near_a, self.near_b = self.a.intersect(near), self.b.intersect(near)

    def placed(self, a, b, turn=0.0, nudge=0.0):
        """a turned by ``turn`` degrees and nudged on, b following about its own axis."""
        return turned(self.cq, a, turn + nudge), turned(self.cq, b, -turn * self.ratio, (1, 0, 0))

    def gap(self, turn=0.0, nudge=0.0):
        first, second = self.placed(self.near_a, self.near_b, turn, nudge)
        return first.distance(second)

    def overlap(self, turn=0.0, nudge=0.0):
        """Common volume of the whole gears."""
        return common(*self.placed(self.a, self.b, turn, nudge))

    def collision(self, turn=0.0, nudge=0.0, push=0.0):
        """Common volume of the teeth near the mesh, which is no more than that of the whole gears; b pushed toward
        the apex by ``push``."""
        first, second = self.placed(self.near_a, self.near_b, turn, nudge)
        return common(first, second.translate(self.cq.Vector(-push, 0, 0)))


@pytest.mark.parametrize('teeth_a,teeth_b,width,angle,undercut', [(13, 14, 6, 20, False), (10, 10, 5, 14.5, True)])
def test_a_bevel_pair_meshes_at_90_degrees_with_the_backlash_it_was_given(cq, built, teeth_a, teeth_b, width, angle,
                                                                          undercut):
    module, backlash = 2, 0.05
    options = dict(pressure_angle=angle, backlash=backlash)
    da = bevel_gear_dimensions(module, teeth_a, teeth_b, width, **options)
    db = bevel_gear_dimensions(module, teeth_b, teeth_a, width, **options)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')                            # the undercut pair warns; tested below
        a, _ = built('bevel_gear', module, teeth_a, teeth_b, width, **options, **({} if undercut else {'bore': 5}))
        b, _ = built('bevel_gear', module, teeth_b, teeth_a, width, **options)
    assert da['undercut'] is undercut
    pair = BevelPair(cq, a, b, da, db)
    pitch = 360 / teeth_a
    assert pair.overlap() < 1e-6
    # The allowance shrinks with the tooth toward the apex, so the flanks are closest at the small end: there they
    # stand backlash * cos(pressure angle) * (cone - face) / cone apart. The angular play is that of the large end.
    play = backlash * math.cos(math.radians(angle)) * (1 - width / da['cone_distance_mm'])
    free = math.degrees(backlash / (module * teeth_a / 2))
    assert pair.gap() == pytest.approx(play, abs=PLAY_TOLERANCE)
    turn = 0.3 * pitch
    # a may turn either way by the play, and no more. Tredgold's teeth are not exactly conjugate, and an undercut
    # pair has lost part of its involute: away from the pitch point one side of the 10-tooth pair has 0.003 mm more
    # play than the allowance (0.0005 mm for the 13 and 14 tooth pair). Never less.
    for side in (1, -1):
        left = pair.gap(turn, nudge=side * 0.6 * free)
        assert 0.4 * play - PLAY_TOLERANCE < left < 0.4 * play + (4 if undercut else 1) * PLAY_TOLERANCE
        assert pair.collision(turn, nudge=side * 1.4 * free) > 1e-4
    assert pair.collision(push=0.3) > 0.1                          # mounted too close to the apex


def test_a_mitre_pair_without_backlash_touches_without_overlap(cq, built):
    module, teeth, width = 2, 14, 6                                # one gear is both halves of a mitre pair
    d = bevel_gear_dimensions(module, teeth, teeth, width)
    assert d['pitch_angle_deg'] == pytest.approx(45) and d['mesh_rotation_deg'] == pytest.approx(180 / teeth)
    gear, raised = built('bevel_gear', module, teeth, teeth, width)
    assert raised == [] and not d['undercut']                      # 14 / cos(45 deg) = 19.8 virtual teeth
    pair = BevelPair(cq, gear, gear, d, d)
    turn = 0.3 * 360 / teeth
    assert pair.overlap(turn) < 1e-4 and pair.gap(turn) < 1e-4
    for nudge in (0.05, -0.05):                                    # 0.012 mm at the large-end pitch circle
        assert pair.collision(turn, nudge) > 1e-3


def test_a_wide_face_and_an_undercut_each_warn_for_the_caller(cq, built):
    gear, raised = built('bevel_gear', *WIDE_UNDERCUT_BEVEL, **WIDE_OPTIONS)
    assert isinstance(gear, cq.Solid) and gear.isValid()
    messages = sorted(str(w.message) for w in raised)
    assert len(messages) == 2 and 'undercut' in messages[0]
    assert 'above a third of the cone distance (4.714 mm)' in messages[1]
    assert all(w.category is UserWarning and w.filename == __file__ for w in raised)


def test_public_names():
    assert set(gears.__all__) == {'spur_gear_dimensions', 'gear_pair_dimensions', 'spur_gear', 'external_ring_gear',
                                  'bevel_gear_dimensions', 'bevel_gear'}
    assert not hasattr(gears, 'module_from_diametral_pitch')       # one home for it: cadagent.formulas, in metres
