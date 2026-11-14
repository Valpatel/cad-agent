"""Involute gear solids: external spur gears, toothed rings and straight bevel gears, as the basic rack cuts them.

Units are millimetres and degrees. A spur gear lies on the XY plane, from Z = 0 to the face width, turning about Z,
with tooth 0 centred on +X. The tooth is the envelope of a rack cutter rolled round the pitch circle, which is what
a hob or a rack-shaped cutter leaves:

* the flank is the true involute of the base circle, from the tip down to where the cutter's straight side ends;
* the root is the trochoid that the cutter's rounded tip corner sweeps (``root_fillet``), tangent to the root circle
  and to the flank. With ``root_fillet=0`` the corner is sharp and the root is its plain trochoid;
* a low tooth count is **undercut**: the cutter's tip sweeps away the bottom of the involute. The tooth is then drawn
  undercut, as it would be cut, and the dimensions say so (``undercut``); the solid functions also warn. A base
  circle above the root circle needs no special case: the trochoid joins the root to the involute wherever it starts.

Each curve is sampled until the polygon through the samples stays within ``chord_tolerance`` of it, and an
interpolating spline is put through the samples.

A straight bevel gear (shafts at 90 degrees only) uses Tredgold's approximation: the large-end tooth form is that of
a spur gear of teeth / cos(pitch angle) teeth, laid on the back cone, and every point of it runs straight to the
pitch apex. That is the classical drawing-office form, close to but not the spherical involute or the octoid a
bevel generator cuts.

What it does not do: helical, internal, spiral-bevel, hypoid, worm or rack solids; bevel shaft angles other than 90
degrees; tip relief, crowning or chamfers; hubs and keyways; tolerance classes; any strength, wear or life check. The
teeth are theoretical. A printed gear needs its ``backlash`` and ``clearance`` tuned to the printer on a test pair,
and a model that meshes in CAD does not prove a part that runs.
"""
import math
import warnings

from cadagent._deps import require

__all__ = ['module_from_diametral_pitch', 'spur_gear_dimensions', 'gear_pair_dimensions', 'spur_gear',
           'external_ring_gear', 'bevel_gear_dimensions', 'bevel_gear']


def module_from_diametral_pitch(diametral_pitch):
    """Module in mm of an inch-system gear: 25.4 / (teeth per inch of pitch diameter)."""
    if not diametral_pitch > 0:
        raise ValueError('Diametral pitch must be positive')
    return 25.4 / diametral_pitch


def _inv(angle):
    return math.tan(angle) - angle


def _inv_inverse(value):
    """The angle whose involute function is ``value`` (Newton, from a series start)."""
    angle = (3 * value) ** (1 / 3) if value > 0 else 0.0
    for _ in range(50):
        step = (_inv(angle) - value) / max(math.tan(angle) ** 2, 1e-12)
        angle -= step
        if abs(step) < 1e-14:
            break
    return angle


def _sample(curve, t0, t1, tolerance):
    """Points of ``curve(t)`` from t0 to t1 whose polygon stays within ``tolerance`` of the curve at mid-parameter."""
    n = 4
    while True:
        ts = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
        points = [curve(t) for t in ts]
        worst = 0.0
        for (ax, ay), (bx, by), ta, tb in zip(points, points[1:], ts, ts[1:]):
            mx, my = curve((ta + tb) / 2)
            length = math.hypot(bx - ax, by - ay)
            if length < 1e-12:
                worst = max(worst, math.hypot(mx - ax, my - ay))
            else:
                worst = max(worst, abs((bx - ax) * (my - ay) - (by - ay) * (mx - ax)) / length)
        if worst <= tolerance or n >= 1024:
            return points
        n *= 2


class _Tooth:
    """One tooth of a rack-generated external gear: its reference radii and the two curves of a flank.

    Polar coordinates (radius, half angle): ``half_angle`` is measured from the tooth's centre line, so the tooth is
    2 * radius * half_angle thick on that circle.
    """

    def __init__(self, module, teeth, pressure_angle, backlash, clearance, root_fillet, profile_shift):
        if not module > 0:
            raise ValueError('Module must be positive')
        if not teeth >= 4:
            raise ValueError('Tooth count must be at least 4')
        if not 5 <= pressure_angle <= 35:
            raise ValueError('Pressure angle must be between 5 and 35 degrees')
        if backlash < 0 or clearance < 0:
            raise ValueError('Backlash allowance and clearance cannot be negative')
        m, z, x = float(module), teeth, float(profile_shift)
        a = math.radians(pressure_angle)
        self.m, self.z, self.a, self.x = m, z, a, x
        self.r = r = m * z / 2
        self.rb = r * math.cos(a)
        self.thickness = m * (math.pi / 2 + 2 * x * math.tan(a)) - backlash
        self.space = space = math.pi * m - self.thickness
        if not self.thickness > 0:
            raise ValueError('Backlash allowance and profile shift leave no tooth on the pitch circle')
        self.ra = r + (1 + x) * m
        depth = (1 + clearance - x) * m                 # cutter tip below the pitch circle
        self.rf = r - depth
        if not depth > 0 or not self.rf > 0:
            raise ValueError('Profile shift, clearance and tooth count leave no root circle inside the pitch circle')
        land = space / 2 - depth * math.tan(a)          # half width of the cutter tip, before rounding
        if land < 0:
            raise ValueError('The cutter comes to a point above the root: reduce the clearance, backlash allowance '
                             'or pressure angle')
        fullest = land * math.cos(a) / (1 - math.sin(a))
        if root_fillet is None:
            rho = min(clearance * m / (1 - math.sin(a)), fullest)
        else:
            rho = root_fillet * m
            if rho < 0 or rho > fullest * (1 + 1e-9):
                raise ValueError(f'Root fillet must be between 0 and {fullest / m:.4f} modules (a full round)')
            rho = min(rho, fullest)
        self.rho = rho
        self.v0 = depth - rho                           # centre of the tip round below the pitch circle
        self.u0 = max(land - rho * (1 - math.sin(a)) / math.cos(a), 0.0)
        if not self.v0 > 0:
            raise ValueError('Profile shift is too large for this generator: the cutter tip round would centre '
                             'outside the pitch circle')
        straight = depth - rho * (1 - math.sin(a))      # where the cutter's straight side ends
        self.undercut = straight > r * math.sin(a) ** 2 * (1 + 1e-9)
        self.min_teeth = math.ceil(2 * straight / m / math.sin(a) ** 2 - 1e-9)
        self.root_half_space = self.u0 / r              # the root circle spans this either side of a space centre
        theta_root = self.u0 / r
        theta_flank = (self.u0 - self.v0 / math.tan(a)) / r
        self.theta_root, self.theta_join = theta_root, theta_flank
        if self.undercut:
            self.theta_join = self._undercut_crossing(theta_root, theta_flank)
        self.r_start = self._fillet_polar(self.theta_join)[0]
        if not self.r_start < self.ra:
            raise ValueError('No involute is left between the root fillet and the tip')
        self.tip_thickness = 2 * self.ra * self.involute_half_angle(self.ra)
        if not self.tip_thickness > 0:
            raise ValueError('The tooth is pointed below the tip circle: reduce the profile shift or backlash')
        steps = 64
        thinnest = min(self.fillet_half_angle(theta_root + (self.theta_join - theta_root) * i / steps)[1]
                       for i in range(steps + 1))
        if not thinnest > 0:
            raise ValueError('The undercut severs the tooth: use more teeth or a positive profile shift')

    # The cutter's tip round, centre (u0, v0) in rack coordinates, as the rack rolls by angle theta round the gear:
    # the contact normal passes through the pitch point, so the envelope point lies on that line, beyond the centre.
    def _fillet_xy(self, theta):
        w = self.u0 - self.r * theta
        sin, cos = math.sin(theta), math.cos(theta)
        scale = 1 + self.rho / math.hypot(self.v0, w)
        along, inward = w * scale, self.v0 * scale      # from the pitch point, along and into the gear
        return (self.r - inward) * sin + along * cos, (self.r - inward) * cos - along * sin

    def _fillet_polar(self, theta):
        """(radius, angle from the centre of the tooth space) of the fillet point."""
        px, py = self._fillet_xy(theta)
        return math.hypot(px, py), math.atan2(px, py)

    def _space_half_angle(self, radius):
        """Half angle of the tooth space that the cutter's straight side leaves at ``radius`` (the involute)."""
        return self.space / (2 * self.r) - _inv(self.a) + _inv(math.acos(min(1.0, self.rb / radius)))

    def _undercut_crossing(self, theta_root, theta_flank):
        """Where the fillet stops cutting into the involute: between the root and the end of the cutter's round."""
        def gap(theta):
            radius, angle = self._fillet_polar(theta)
            return 1.0 if radius <= self.rb else angle - self._space_half_angle(radius)
        steps, high = 400, theta_root
        for i in range(1, steps + 1):
            low = theta_root + (theta_flank - theta_root) * i / steps
            if gap(low) <= 0:
                for _ in range(60):
                    mid = (low + high) / 2
                    low, high = (mid, high) if gap(mid) <= 0 else (low, mid)
                return low
            high = low
        return theta_flank

    def fillet_half_angle(self, theta):
        radius, angle = self._fillet_polar(theta)
        return radius, math.pi / self.z - angle

    def involute_half_angle(self, radius):
        return math.pi / self.z - self._space_half_angle(radius)

    def flank(self, tolerance, place):
        """The lower flank of tooth 0 as two point lists, root to join and join to tip; ``place(radius, half_angle)``
        gives each point's XY, and the tolerance is measured there."""
        def fillet(theta):
            radius, half = self.fillet_half_angle(theta)
            return place(radius, -half)

        def involute(roll):
            radius = self.rb * math.hypot(1.0, roll)
            return place(radius, -self.involute_half_angle(radius))
        roll_start = math.sqrt(max(self.r_start ** 2 - self.rb ** 2, 0.0)) / self.rb
        roll_tip = math.sqrt(self.ra ** 2 - self.rb ** 2) / self.rb
        return (_sample(fillet, self.theta_root, self.theta_join, tolerance),
                _sample(involute, roll_start, roll_tip, tolerance))


def _whole(teeth, what='Tooth count'):
    if teeth != int(teeth) or teeth < 4:
        raise ValueError(f'{what} must be a whole number of at least 4')
    return int(teeth)


def _outline(cq, tooth, teeth, tolerance, radius_of, angle_scale, z):
    """The closed outline of ``teeth`` teeth as edges on the plane Z = z, tooth 0 centred on +X.

    ``tooth`` gives the profile as (radius, half angle); a point is drawn at radius ``radius_of(radius)`` and angle
    ``angle_scale * half angle``. A spur gear draws it as it is; a bevel gear maps its back-cone development.
    """
    def place(radius, half):
        mapped, angle = radius_of(radius), angle_scale * half
        return mapped * math.cos(angle), mapped * math.sin(angle)

    def spline(points, mirror):
        points = [(x, -y) for x, y in reversed(points)] if mirror else points
        return cq.Edge.makeSpline([cq.Vector(x, y, z) for x, y in points])

    def arc(radius, start, end):
        angles = (start, (start + end) / 2, end)
        return cq.Edge.makeThreePointArc(*(cq.Vector(radius * math.cos(v), radius * math.sin(v), z) for v in angles))
    fillet, involute = tooth.flank(tolerance, place)
    pitch = 2 * math.pi / teeth
    tip_half = angle_scale * tooth.tip_thickness / (2 * tooth.ra)
    root_half = angle_scale * (math.pi / tooth.z - tooth.root_half_space)   # where the fillet meets the root circle
    one = [spline(fillet, False), spline(involute, False), arc(radius_of(tooth.ra), -tip_half, tip_half),
           spline(involute, True), spline(fillet, True)]
    if pitch - 2 * root_half > 1e-9:                    # a full-round fillet leaves no root arc
        one.append(arc(radius_of(tooth.rf), root_half, pitch - root_half))
    edges = list(one)
    for k in range(1, teeth):
        edges.extend(e.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), math.degrees(k * pitch)) for e in one)
    return edges


def spur_gear_dimensions(module, teeth, *, pressure_angle=20.0, backlash=0.0, clearance=0.25, root_fillet=None,
                         profile_shift=0.0):
    """Reference dimensions of one external involute gear, in mm, with whether the rack undercuts it.

    ``backlash`` is the thinning of this gear's tooth, measured along the pitch circle (the cutter is widened; the
    root circle does not move). ``clearance`` and ``profile_shift`` are in modules: the root lies
    ``(1 + clearance - profile_shift) * module`` inside the pitch circle and the tip
    ``(1 + profile_shift) * module`` outside it. ``root_fillet`` is the radius of the cutter's tip corner in
    modules; by default it fills the clearance (0.38 at 20 degrees and a clearance of 0.25), ``0`` is a sharp corner.

    ``tooth_thickness_mm`` is the arc on the pitch circle: pi * module / 2, plus 2 * profile_shift * module *
    tan(pressure angle), less the backlash allowance. ``involute_start_diameter_mm`` is where the flank stops being
    an involute; a mating tip must not reach inside it. ``undercut`` is true when the cutter removed the bottom of the
    involute, which shortens the contact and weakens the root: use ``min_teeth_without_undercut`` teeth, a larger
    pressure angle or a positive profile shift. Geometry only: no strength, wear or tolerance statement.
    """
    t = _Tooth(module, _whole(teeth), pressure_angle, backlash, clearance, root_fillet, profile_shift)
    notes = []
    if t.undercut:
        notes.append(f'undercut: the cutter removes the involute inside diameter {2 * t.r_start:.3f} mm; '
                     f'{t.min_teeth} teeth or more avoid it at this pressure angle and profile shift')
    if t.rb > t.rf:
        notes.append('the base circle is larger than the root circle: the flank below it is the root trochoid')
    return {
        'module_mm': t.m, 'teeth': t.z, 'pressure_angle_deg': float(pressure_angle), 'profile_shift': t.x,
        'pitch_diameter_mm': 2 * t.r, 'base_diameter_mm': 2 * t.rb,
        'tip_diameter_mm': 2 * t.ra, 'root_diameter_mm': 2 * t.rf,
        'circular_pitch_mm': math.pi * t.m, 'base_pitch_mm': math.pi * t.m * math.cos(t.a),
        'tooth_thickness_mm': t.thickness, 'tip_thickness_mm': t.tip_thickness,
        'whole_depth_mm': t.ra - t.rf, 'root_fillet_mm': t.rho,
        'involute_start_diameter_mm': 2 * t.r_start,
        'undercut': t.undercut, 'min_teeth_without_undercut': t.min_teeth,
        'tooth_pitch_deg': 360.0 / t.z, 'notes': notes,
    }


def gear_pair_dimensions(module, teeth_a, teeth_b, *, pressure_angle=20.0, backlash=0.0, clearance=0.25,
                         root_fillet=None, profile_shift_a=0.0, profile_shift_b=0.0):
    """Centre distance and mesh figures of two external gears, with each gear's own dimensions under ``a`` and ``b``.

    ``centre_distance_mm`` is where the unthinned teeth mesh without play: module * (teeth_a + teeth_b) / 2 when the
    profile shifts sum to zero, and otherwise the distance at the working pressure angle that the shifts set.
    ``backlash`` thins each gear by that much, so the play along the pitch circles is about twice it.

    Put gear ``a`` at the origin and gear ``b`` at (centre_distance, 0), turned by ``mesh_rotation_b_deg`` about its
    own axis so that one of its tooth spaces faces tooth 0 of ``a``: half a tooth pitch for an even tooth count, none
    for an odd one.

    ``contact_ratio`` counts only contact on involute, so an undercut gear lowers it (``contact_shortened``).
    ``tip_past_involute`` is true when a tip works inside the start of the involute of a gear that is not undercut
    (the start of the active profile lies below the form diameter): contact there is on the root fillet and is not
    conjugate. It is the usual interference check and it is cautious: in the solids the overlap it predicts can be
    far smaller than any backlash. ``tip_clearance_mm`` is the smaller gap between a tip and the opposite root at
    this centre distance; profile shifts that do not sum to zero reduce it, and the tips are not shortened to
    restore it.
    """
    args = dict(pressure_angle=pressure_angle, backlash=backlash, clearance=clearance, root_fillet=root_fillet)
    ta = _Tooth(module, _whole(teeth_a), profile_shift=profile_shift_a, **args)
    tb = _Tooth(module, _whole(teeth_b), profile_shift=profile_shift_b, **args)
    a = ta.a
    working = _inv_inverse(_inv(a) + 2 * math.tan(a) * (ta.x + tb.x) / (ta.z + tb.z))
    if not working > 0:
        raise ValueError('The profile shifts are too negative for a working mesh')
    centre = ta.m * (ta.z + tb.z) / 2 * math.cos(a) / math.cos(working)
    line = centre * math.sin(working)                   # between the two base-circle tangent points
    notes, lengths, past, shortened = [], [], False, False
    for name, tooth, mate in (('a', ta, tb), ('b', tb, ta)):
        # Contact by the mate's tip falls this far from the tooth's own base tangent point, along the line of action.
        reach = line - math.sqrt(mate.ra ** 2 - mate.rb ** 2)
        start = math.sqrt(max(tooth.r_start ** 2 - tooth.rb ** 2, 0.0))
        if reach < start - 1e-9:
            if tooth.undercut:
                shortened = True
                notes.append(f'gear {name} is undercut where the tip of the other gear would reach: contact is '
                             'lost there')
            else:
                past = True
                notes.append(f'the tip of the other gear works inside the involute of gear {name}, on its root '
                             'fillet: check for interference')
        lengths.append(tooth.rb * math.tan(working) - max(reach, start))
    contact = sum(lengths) / (math.pi * ta.m * math.cos(a))
    if contact < 1.2:
        notes.append(f'contact ratio {contact:.2f} is below 1.2: the mesh will run unevenly')
    odd = tb.z % 2
    return {
        'centre_distance_mm': centre, 'working_pressure_angle_deg': math.degrees(working),
        'ratio': tb.z / ta.z, 'contact_ratio': contact, 'contact_shortened': shortened,
        'tip_past_involute': past,
        'tip_clearance_mm': min(centre - ta.ra - tb.rf, centre - tb.ra - ta.rf),
        'backlash_mm': 2 * backlash if abs(ta.x + tb.x) < 1e-12 else None,
        'mesh_rotation_b_deg': 0.0 if odd else 180.0 / tb.z,
        'a': spur_gear_dimensions(module, teeth_a, profile_shift=profile_shift_a, **args),
        'b': spur_gear_dimensions(module, teeth_b, profile_shift=profile_shift_b, **args),
        'notes': notes,
    }


def spur_gear(module, teeth, face_width, *, pressure_angle=20.0, bore=0.0, backlash=0.0, clearance=0.25,
              root_fillet=None, profile_shift=0.0, chord_tolerance=0.005):
    """An external involute spur gear as one solid: axis Z, Z = 0 to ``face_width``, tooth 0 centred on +X.

    The arguments are those of :func:`spur_gear_dimensions`, which gives the diameters to place it by; ``bore`` is a
    plain through hole (0 for none) and must lie inside the root circle. For an inch gear pass
    ``module_from_diametral_pitch(P)``. An undercut gear is drawn undercut and raises a ``UserWarning``.

    Flanks and root fillets are splines through points sampled to ``chord_tolerance`` mm; tips and roots are arcs.
    No keyway, hub, chamfer, tip relief or crowning, and no strength check.
    """
    if not face_width > 0:
        raise ValueError('Face width must be positive')
    if not chord_tolerance > 0:
        raise ValueError('Chord tolerance must be positive')
    t = _Tooth(module, _whole(teeth), pressure_angle, backlash, clearance, root_fillet, profile_shift)
    if bore < 0 or bore >= 2 * t.rf:
        raise ValueError(f'Bore must be at least 0 and smaller than the root diameter {2 * t.rf:.3f} mm')
    if t.undercut:
        warnings.warn(f'{t.z}-tooth gear at {pressure_angle:g} degrees is undercut inside diameter '
                      f'{2 * t.r_start:.3f} mm ({t.min_teeth} teeth or more avoid it); drawn as cut', stacklevel=2)
    cq = require('cadquery', 'gear solid')
    edges = _outline(cq, t, t.z, chord_tolerance, lambda radius: radius, 1.0, 0.0)
    inner = [cq.Wire.makeCircle(bore / 2, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1))] if bore > 0 else []
    return cq.Solid.extrudeLinear(cq.Wire.assembleEdges(edges), inner, cq.Vector(0, 0, face_width))


def external_ring_gear(module, teeth, face_width, inner_diameter, *, min_rim=None, **options):
    """The teeth of :func:`spur_gear` on the outside of a ring with a plain ``inner_diameter``, as one solid.

    This is an external gear with a large bore (a toothed ring to bolt or press onto a drum or a turntable), not an
    internal gear. The rim between the bore and the root circle must be at least ``min_rim`` mm, by default one
    module: a floor that keeps the ring in one piece when drawn, not a strength rating. A thin rim bends under the
    tooth load and nothing here checks that. ``options`` are the keyword arguments of :func:`spur_gear`.
    """
    known = {k: options[k] for k in ('pressure_angle', 'backlash', 'clearance', 'root_fillet', 'profile_shift')
             if k in options}
    root = spur_gear_dimensions(module, teeth, **known)['root_diameter_mm']
    floor = module if min_rim is None else min_rim
    if not inner_diameter > 0:
        raise ValueError('Inner diameter must be positive')
    if floor <= 0:
        raise ValueError('Minimum rim must be positive')
    rim = (root - inner_diameter) / 2
    if rim < floor:
        raise ValueError(f'Rim under the teeth is {rim:.3f} mm, below the minimum {floor:.3f} mm '
                         f'(root diameter {root:.3f} mm)')
    return spur_gear(module, teeth, face_width, bore=inner_diameter, **options)


class _Bevel:
    """A straight bevel gear for 90 degree shafts by Tredgold's approximation: pitch apex at the origin, axis Z."""

    def __init__(self, module, teeth, mate_teeth, face_width, pressure_angle, backlash, clearance, root_fillet,
                 backing):
        z, mate = _whole(teeth), _whole(mate_teeth, 'Mating tooth count')
        if not module > 0 or not face_width > 0:
            raise ValueError('Module and face width must be positive')
        self.z, self.m, self.b = z, float(module), float(face_width)
        self.delta = delta = math.atan2(z, mate)        # pitch cone half angle
        self.cone = cone = module * z / (2 * math.sin(delta))
        if not face_width < cone:
            raise ValueError(f'Face width must be below the cone distance {cone:.3f} mm')
        # The tooth form at the large end is that of a spur gear of z / cos(delta) teeth, drawn on the back cone.
        self.tooth = t = _Tooth(module, z / math.cos(delta), pressure_angle, backlash, clearance, root_fillet, 0.0)
        self.backing = module if backing is None else backing
        self.rk = t.rf - self.backing                   # back-cone radius where the flat back face starts
        self.ro = t.ra + module                         # back-cone radius where the blank ends, beyond the tips
        if not self.backing >= 0 or not self.rk > 0:
            raise ValueError('Backing under the root must be at least 0 and leave a back face')
        if not self.height(self.ro) > 0:
            raise ValueError('The gear is too flat for this generator: its tips pass the plane of the apex')
        self.inner = (cone - face_width) / cone         # the small end is the large end scaled by this about the apex

    def height(self, radius):
        """Z of the point on the back cone at ``radius`` from the back-cone apex."""
        return self.cone / math.cos(self.delta) - radius * math.sin(self.delta)

    def across(self, radius):
        """Distance from the axis of that point."""
        return radius * math.cos(self.delta)


def bevel_gear_dimensions(module, teeth, mate_teeth, face_width, *, pressure_angle=20.0, backlash=0.0,
                          clearance=0.25, root_fillet=None, backing=None):
    """Reference dimensions of one straight bevel gear of a 90 degree pair, in mm, from the pitch apex at Z = 0.

    ``module`` is at the large end. ``pitch_angle_deg`` is atan(teeth / mate_teeth) and ``cone_distance_mm`` the
    length of the pitch cone, apex to large end. ``tooth_thickness_mm`` is the arc on the large-end pitch circle;
    every tooth dimension shrinks in proportion to the distance from the apex. ``back_face_z_mm`` and
    ``front_face_z_mm`` are the flat faces of the solid, to set the mounting distance by. ``undercut`` is that of the
    virtual spur gear of ``virtual_teeth`` teeth. Geometry only: no strength statement.
    """
    v = _Bevel(module, teeth, mate_teeth, face_width, pressure_angle, backlash, clearance, root_fillet, backing)
    t = v.tooth
    notes = []
    if t.undercut:
        notes.append(f'undercut: the virtual spur gear of {t.z:.2f} teeth is below {t.min_teeth}')
    if v.b > v.cone / 3 * (1 + 1e-9):
        notes.append('face width is above a third of the cone distance: the small-end teeth get very fine')
    return {
        'module_mm': v.m, 'teeth': v.z, 'mate_teeth': int(mate_teeth), 'pressure_angle_deg': float(pressure_angle),
        'pitch_angle_deg': math.degrees(v.delta), 'cone_distance_mm': v.cone, 'face_width_mm': v.b,
        'pitch_diameter_mm': 2 * v.across(t.r), 'tip_diameter_mm': 2 * v.across(t.ra),
        'root_diameter_mm': 2 * v.across(t.rf), 'pitch_circle_z_mm': v.height(t.r),
        'tip_angle_deg': math.degrees(math.atan2(v.across(t.ra), v.height(t.ra))),
        'root_angle_deg': math.degrees(math.atan2(v.across(t.rf), v.height(t.rf))),
        'virtual_teeth': t.z, 'tooth_thickness_mm': t.thickness,
        'back_face_z_mm': v.height(v.rk), 'front_face_z_mm': v.height(v.rk) * v.inner,
        'back_face_diameter_mm': 2 * v.across(v.rk), 'front_face_diameter_mm': 2 * v.across(v.rk) * v.inner,
        'undercut': t.undercut, 'tooth_pitch_deg': 360.0 / v.z,
        'mesh_rotation_deg': 0.0 if v.z % 2 else 180.0 / v.z, 'notes': notes,
    }


def bevel_gear(module, teeth, mate_teeth, face_width, *, pressure_angle=20.0, bore=0.0, backlash=0.0,
               clearance=0.25, root_fillet=None, backing=None, chord_tolerance=0.005):
    """A straight bevel gear for shafts at 90 degrees as one solid: pitch apex at the origin, teeth toward +Z.

    ``teeth`` and ``mate_teeth`` set the pitch cone; make the mate with the two swapped. The gear's axis is Z and its
    large-end pitch circle lies at Z = ``pitch_circle_z_mm`` of :func:`bevel_gear_dimensions`, tooth 0 centred on
    +X. To mesh a pair, leave one on Z, turn the other by its ``mesh_rotation_deg`` about Z and then by 90 degrees
    about Y, so that its axis is X and both apexes stay at the origin.

    The tooth form is Tredgold's (see the module docstring): the rack-generated spur tooth of the virtual tooth
    count on the back cone, running straight to the apex, with tip and root cones through the apex. The ends are the
    back cone and the front cone, ``face_width`` apart along the pitch cone; ``backing`` mm under the root at the
    large end (one module by default) the back turns into a flat face, and the front likewise. ``bore`` is a plain
    through hole. ``backlash`` thins the large-end tooth along its pitch circle. No hub, no keyway, no crowning or
    tip relief, no strength check; an undercut virtual gear is drawn undercut and raises a ``UserWarning``.
    """
    v = _Bevel(module, teeth, mate_teeth, face_width, pressure_angle, backlash, clearance, root_fillet, backing)
    t = v.tooth
    if not chord_tolerance > 0:
        raise ValueError('Chord tolerance must be positive')
    flat = v.across(v.rk) * v.inner                     # radius of the flat front face
    if bore < 0 or bore >= 2 * flat:
        raise ValueError(f'Bore must be at least 0 and smaller than the front face diameter {2 * flat:.3f} mm')
    if t.undercut:
        warnings.warn(f'{v.z}-tooth bevel gear is undercut: its virtual spur gear has {t.z:.2f} teeth, below '
                      f'{t.min_teeth}; drawn as cut', stacklevel=2)
    cq = require('cadquery', 'gear solid')
    # Every point of the back-cone tooth form is joined to the apex. Cut by the plane of the large-end pitch circle,
    # those rays draw a flat outline; the tooth body is the cone over it, kept between the back and front cones.
    plane = v.height(t.r)
    outline = cq.Wire.assembleEdges(_outline(cq, t, v.z, chord_tolerance,
                                             lambda radius: plane * v.across(radius) / v.height(radius),
                                             1 / math.cos(v.delta), plane))
    far = 1.05 * v.height(v.rk) / plane
    near = 0.95 * v.inner * v.height(v.ro) / plane
    cone = cq.Solid.makeLoft([outline.scale(near), outline.scale(far)], True)
    back = [(v.across(v.ro), v.height(v.ro)), (v.across(v.rk), v.height(v.rk)), (0.0, v.height(v.rk))]
    section = back + [(x * v.inner, z * v.inner) for x, z in reversed(back)]
    blank = cq.Workplane('XZ').polyline(section).close().revolve(360, (0, 0, 0), (0, 1, 0)).val()
    gear = cone.intersect(blank)
    if bore > 0:
        gear = gear.cut(cq.Solid.makeCylinder(bore / 2, v.height(v.rk), cq.Vector(0, 0, 0)))
    solids = gear.Solids()
    if len(solids) != 1:
        raise ValueError(f'The bevel gear came out as {len(solids)} solids: check the face width and backing')
    return solids[0]
