"""Involute spur gears and straight bevel gears: tooth geometry, tooth forces and the Lewis bending stress.

    from cadagent import formulas as fx
    spur = fx.spur_tooth_bending(torque=2.0, module=2e-3, teeth=18, face_width=0.012)      # stress at the root, Pa
    bevel = fx.bevel_tooth_bending(torque=2.0, module=2e-3, teeth=18, mate_teeth=36, face_width=0.012)
    bevel["stress"], bevel["force_large_end"], bevel["force_mean"], bevel["cone_factor"]

Lengths in metres, forces in newtons, torques in newton metres, stresses in pascals and angles in radians. The
module is in metres too (a 2 mm module is ``2e-3``); ``module_from_diametral_pitch`` converts an inch-series pitch.
Teeth are standard full depth without profile shift: addendum one module, dedendum 1.25 modules. Bevel gears are
straight-toothed on shafts at 90 degrees, with the module, the pitch diameter and the cone distance all measured at
the large end, as gear makers quote them.

A straight bevel tooth tapers toward the cone's apex, so three radii matter and must not be mixed:

- the **large-end pitch radius** d / 2, where the module is defined and where the Lewis equation takes its force;
- the **mean pitch radius**, at the middle of the face, where the resultant tooth force acts on the shaft and its
  bearings (``bevel_mean_radius``, ``bevel_gear_forces``);
- the cone distance L, which sets how much of a full tooth the face width b uses: the bevel Lewis equation carries
  the cone factor (L - b) / L (``bevel_cone_factor``).

``bevel_tooth_bending`` takes a torque and returns all of them, so a stress is never worked out with the force of
one radius and the tooth of another.

What this does not cover. The Lewis equation is a first check of a tooth as a cantilever under a static or
slow-moving load. It has none of AGMA's geometry, load-distribution, size, rim or reliability factors, no stress
concentration at the root fillet, and it puts the whole load on one tooth at its tip. It says nothing about pitting
(surface contact stress), wear, scuffing or fatigue, any of which can govern a gear that runs. The velocity factor
is an old empirical allowance for cut metal teeth, not a dynamic analysis. No allowable stress is given here: for
steels the caller brings one, and for printed plastic gears there is no agreed allowable at all (the strength
depends on the layer direction, the infill, the temperature and creep), so a printed gear is sized by testing it.
Helical, spiral bevel, hypoid and worm gears, profile-shifted teeth and internal gears are outside this module.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from cadagent.formulas._registry import cite, formula

INCH = 0.0254
ADDENDUM = 1.0        # in modules: standard full-depth teeth (Shigley, Table 13-1)
DEDENDUM = 1.25       # in modules; the same table also lists 1.35 for teeth to be shaved or ground
PRESSURE_ANGLE = math.radians(20.0)
MIN_CONTACT_RATIO = 1.2   # Shigley, Chapter 13, 'Contact Ratio': gears should not be designed below about 1.2

# Lewis form factor Y (the diametral-pitch form: stress = force / (face width x module x Y)) by tooth count, for a
# load at the tip of one tooth. math.inf is a rack.
#
# Shigley's Mechanical Engineering Design, Table 14-2: a normal pressure angle of 20 degrees, full-depth teeth.
_SHIGLEY_20 = ((12, 0.245), (13, 0.261), (14, 0.277), (15, 0.290), (16, 0.296), (17, 0.303), (18, 0.309),
               (19, 0.314), (20, 0.322), (21, 0.328), (22, 0.331), (24, 0.337), (26, 0.346), (28, 0.353),
               (30, 0.359), (34, 0.371), (38, 0.384), (43, 0.397), (50, 0.409), (60, 0.422), (75, 0.435),
               (100, 0.447), (150, 0.460), (300, 0.472), (400, 0.480), (math.inf, 0.485))
# Boston Gear, Engineering Information: Spur Gears (P-1930-BG, 4/19), p. 311, Table I, 'Tooth Form Factor (Y)': the
# columns '14-1/2 deg Full Depth Involute' and '20 deg Full Depth Involute'.
_BOSTON_COUNTS = (10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 45, 50, 55,
                  60, 65, 70, 75, 80, 90, 100, 150, 200, 300, math.inf)
_BOSTON_14_5 = (0.176, 0.192, 0.210, 0.223, 0.236, 0.245, 0.255, 0.264, 0.270, 0.277, 0.283, 0.292, 0.302, 0.308,
                0.314, 0.318, 0.322, 0.325, 0.329, 0.332, 0.336, 0.340, 0.346, 0.352, 0.355, 0.358, 0.360, 0.361,
                0.363, 0.366, 0.368, 0.375, 0.378, 0.382, 0.390)
_BOSTON_20 = (0.201, 0.226, 0.245, 0.264, 0.276, 0.289, 0.295, 0.302, 0.308, 0.314, 0.320, 0.330, 0.337, 0.344,
              0.352, 0.358, 0.364, 0.370, 0.377, 0.383, 0.389, 0.399, 0.408, 0.415, 0.421, 0.425, 0.429, 0.433,
              0.436, 0.442, 0.446, 0.458, 0.463, 0.471, 0.484)
# {table: {pressure angle in degrees: ((teeth, Y), ...)}}
LEWIS_FORM_FACTORS: Dict[str, Dict[float, Tuple[Tuple[float, float], ...]]] = {
    "shigley": {20.0: _SHIGLEY_20},
    "boston": {14.5: tuple(zip(_BOSTON_COUNTS, _BOSTON_14_5)), 20.0: tuple(zip(_BOSTON_COUNTS, _BOSTON_20))},
}
_DEFAULT_TABLE = {20.0: "shigley", 14.5: "boston"}

# Shigley, Eqs. (14-6a) to (14-6d), pitch-line speed V in m/s: Kv multiplies the stress.
VELOCITY_PROFILES = {"cast": "cast iron, cast profile: (3.05 + V) / 3.05 (the Barth equation)",
                     "cut": "cut or milled profile: (6.1 + V) / 6.1",
                     "hobbed": "hobbed or shaped profile: (3.56 + sqrt V) / 3.56",
                     "ground": "shaved or ground profile: sqrt((5.56 + sqrt V) / 5.56)"}

_FULL_DEPTH = ("standard full-depth involute teeth without profile shift (addendum 1 module, dedendum 1.25 modules); "
               "stub, long-addendum and shifted teeth differ")
_EXTERNAL = "external gears on parallel shafts at the standard centre distance; no internal gear, no backlash allowance"
_RIGHT_ANGLE = ("straight bevel gears on shafts at 90 degrees only; other shaft angles, spiral, Zerol and hypoid "
                "teeth are not covered")
_LARGE_END = "the module, pitch diameter and cone distance are those of the large end of the teeth"
_RIGID_STATICS = ("statics of rigid gears with the whole load on one tooth at the pitch point, without friction; "
                  "these are the mean forces, with no dynamic, shock or misalignment allowance")
_LEWIS = ("the Lewis cantilever model, a static or low-speed first check: the whole load on one tooth at its tip, "
          "spread evenly across the face, with no stress concentration at the root fillet and the radial "
          "(compressive) component ignored")
_NOT_AGMA = ("none of the AGMA geometry, load-distribution, size, rim-thickness or reliability factors; no pitting "
             "(contact stress), wear, scuffing or fatigue check, any of which can govern a gear that runs")
_NO_ALLOWABLE = ("the result is a stress, not a verdict: the allowable is the caller's, and for printed plastic "
                 "gears there is no agreed allowable (layer direction, infill, temperature and creep all move it), "
                 "so test the gear")
_TREDGOLD = ("Tredgold's approximation: the tooth form at the large end is that of a spur gear on the developed "
             "back cone")
_SLIDES = " (equation, table and example numbers as the 9th edition prints them)"


def _positive(name: str, v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise ValueError(f"{name} must be a finite number above 0, not {v!r}")
    return float(v)


def _number(name: str, v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{name} must be a finite number, not {v!r}")
    return float(v)


def _teeth(name: str, v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v != int(v) or v < 3:
        raise ValueError(f"{name} must be a whole number of teeth, 3 or more, not {v!r}")
    return int(v)


def _pressure_angle(v: Any) -> float:
    v = _positive("pressure_angle", v)
    if v >= math.pi / 4:
        raise ValueError(f"pressure_angle is in radians and below pi/4 (20 degrees is {PRESSURE_ANGLE:.4f}), not "
                         f"{v!r}")
    return v


def _pitch_angle(v: Any) -> float:
    v = _positive("pitch_angle", v)
    if v >= math.pi / 2:
        raise ValueError(f"pitch_angle is in radians, above 0 and below pi/2, not {v!r}")
    return v


def _face_on_cone(face_width: Any, cone_distance: Any) -> Tuple[float, float]:
    b, cone = _positive("face_width", face_width), _positive("cone_distance", cone_distance)
    if b >= cone:
        raise ValueError(f"face_width {b!r} must be less than the cone distance {cone!r}: the teeth would pass the "
                         "apex")
    return b, cone


# ----------------------------------------------------------------------------- geometry: spur gears

@formula(units={"diametral_pitch": "teeth per inch of pitch diameter"}, returns="module, m",
         limits=("a definition: the module is the pitch diameter per tooth, the diametral pitch is teeth per inch "
                 "of pitch diameter, so m = 25.4 mm / P; a gear cut to one series only approximates the other",),
         source=cite("shigley", "Chapter 13, 'Nomenclature': Eqs. (13-1) and (13-2), P = N / d and m = d / N"
                     + _SLIDES))
def module_from_diametral_pitch(diametral_pitch: float) -> float:
    """Module of a gear from its diametral pitch: m = 0.0254 / P, in metres."""
    return INCH / _positive("diametral_pitch", diametral_pitch)


@formula(units={"module": "m"}, returns="diametral pitch, teeth per inch of pitch diameter",
         limits=("a definition, P = 25.4 mm / m; a gear cut to one series only approximates the other",),
         source=cite("shigley", "Chapter 13, 'Nomenclature': Eqs. (13-1) and (13-2), P = N / d and m = d / N"
                     + _SLIDES))
def diametral_pitch_from_module(module: float) -> float:
    """Diametral pitch of a gear from its module: P = 0.0254 / m, in teeth per inch."""
    return INCH / _positive("module", module)


@formula(units={"module": "m", "teeth": "count"}, returns="pitch diameter, m",
         limits=("the standard (cutting) pitch circle; a pair mounted at another centre distance runs on other "
                 "operating pitch circles", "for a bevel gear, the large end"),
         source=cite("shigley", "Chapter 13, 'Nomenclature': Eq. (13-2), m = d / N" + _SLIDES))
def gear_pitch_diameter(module: float, teeth: int) -> float:
    """Pitch diameter of a gear: d = m N."""
    return _positive("module", module) * _teeth("teeth", teeth)


@formula(units={"module": "m", "teeth_pinion": "count", "teeth_gear": "count"}, returns="centre distance, m",
         limits=(_EXTERNAL, "teeth without profile shift; real pairs are mounted slightly wider for backlash"),
         source=cite("shigley", "Chapter 13, Example 13-1: the centre distance (dP + dG) / 2" + _SLIDES))
def gear_centre_distance(module: float, teeth_pinion: int, teeth_gear: int) -> float:
    """Centre distance of an external spur pair: C = m (N1 + N2) / 2."""
    return _positive("module", module) * (_teeth("teeth_pinion", teeth_pinion) + _teeth("teeth_gear", teeth_gear)) / 2


@formula(units={"module": "m", "teeth": "count", "addendum": "modules (1 for full-depth teeth)"},
         returns="tip (addendum, outside) diameter, m", limits=(_FULL_DEPTH, "an external spur gear"),
         source=cite("shigley", "Chapter 13, Table 13-1 (standard tooth systems for spur gears): addendum 1 m"
                     + _SLIDES))
def gear_tip_diameter(module: float, teeth: int, addendum: float = ADDENDUM) -> float:
    """Tip diameter of an external spur gear: da = m (N + 2 a), a = 1 for full-depth teeth."""
    return _positive("module", module) * (_teeth("teeth", teeth) + 2 * _positive("addendum", addendum))


@formula(units={"module": "m", "teeth": "count", "dedendum": "modules (1.25 for full-depth teeth)"},
         returns="root (dedendum) diameter, m",
         limits=(_FULL_DEPTH, "an external spur gear; teeth to be shaved or ground have a dedendum of 1.35 modules",
                 "the root circle only: the fillet's shape and any undercut depend on the cutter"),
         source=cite("shigley", "Chapter 13, Table 13-1 (standard tooth systems for spur gears): dedendum 1.25 m"
                     + _SLIDES))
def gear_root_diameter(module: float, teeth: int, dedendum: float = DEDENDUM) -> float:
    """Root diameter of an external spur gear: df = m (N - 2 b), b = 1.25 for full-depth teeth."""
    df = _positive("module", module) * (_teeth("teeth", teeth) - 2 * _positive("dedendum", dedendum))
    if df <= 0:
        raise ValueError(f"{teeth!r} teeth with a dedendum of {dedendum!r} modules leave no root circle")
    return df


@formula(units={"module": "m", "teeth": "count", "pressure_angle": "rad (20 degrees by default)"},
         returns="base circle diameter, m", limits=("an involute tooth cut at this pressure angle",),
         source=cite("shigley", "Chapter 13, 'Involute Properties' and Example 13-1: rb = r cos(phi)" + _SLIDES))
def gear_base_diameter(module: float, teeth: int, pressure_angle: float = PRESSURE_ANGLE) -> float:
    """Base circle diameter of an involute gear: db = m N cos(phi)."""
    return gear_pitch_diameter(module, teeth) * math.cos(_pressure_angle(pressure_angle))


@formula(units={"module": "m", "teeth_pinion": "count", "teeth_gear": "count",
                "pressure_angle": "rad (20 degrees by default)", "addendum": "modules (1 for full-depth teeth)"},
         returns="contact ratio (the mean number of tooth pairs in contact)",
         limits=(_EXTERNAL, _FULL_DEPTH,
                 "rigid, perfect involutes with no interference: where a tip would reach past the mate's base "
                 "circle (see gear_min_teeth) the real path of contact is shorter than this",
                 "a pair should have a contact ratio of at least about 1.2"),
         source=cite("shigley", "Chapter 13, 'Contact Ratio': Eq. (13-9), mc = Lab / (p cos(phi))" + _SLIDES))
def gear_contact_ratio(module: float, teeth_pinion: int, teeth_gear: int, pressure_angle: float = PRESSURE_ANGLE,
                       addendum: float = ADDENDUM) -> float:
    """Contact ratio of an external spur pair: the length of the path of contact along the line of action, between
    the two tip circles, over the base pitch: mc = (sqrt(ra1^2 - rb1^2) + sqrt(ra2^2 - rb2^2) - C sin(phi)) /
    (pi m cos(phi))."""
    m, phi = _positive("module", module), _pressure_angle(pressure_angle)
    a = _positive("addendum", addendum)
    n1, n2 = _teeth("teeth_pinion", teeth_pinion), _teeth("teeth_gear", teeth_gear)
    path = -m * (n1 + n2) / 2 * math.sin(phi)
    for n in (n1, n2):
        tip, base = m * (n + 2 * a) / 2, m * n * math.cos(phi) / 2
        path += math.sqrt(tip * tip - base * base)
    return path / (math.pi * m * math.cos(phi))


@formula(units={"pressure_angle": "rad (20 degrees by default)",
                "ratio": "teeth of the mate over teeth of the pinion, 1 or more; math.inf for a rack",
                "addendum": "modules (1 for full-depth teeth, 0.8 for stub teeth)"},
         returns="dict: bound (the least tooth count as a real number) and teeth (the least whole count)",
         limits=("interference between the mating teeth of a pair: the mate's tip must not reach below the pinion's "
                 "base circle; teeth without profile shift",
                 "the rack value (ratio = math.inf) is also the least count a rack-type cutter or hob generates "
                 "without undercutting the root: 2 k / sin^2(phi), 17.1 at 20 degrees",
                 "a pinion below the bound can still be made, undercut or with profile shift, which this does not "
                 "model"),
         source=cite("shigley", "Chapter 13, 'Interference': Eqs. (13-10), (13-11) and (13-13)" + _SLIDES))
def gear_min_teeth(pressure_angle: float = PRESSURE_ANGLE, ratio: float = math.inf,
                   addendum: float = ADDENDUM) -> Dict[str, Any]:
    """Least number of pinion teeth that mesh without interference (undercut) with a mate ``ratio`` times larger:
    N = 2 k / ((1 + 2 r) sin^2(phi)) (r + sqrt(r^2 + (1 + 2 r) sin^2(phi))), which tends to 2 k / sin^2(phi) for a
    rack."""
    s2 = math.sin(_pressure_angle(pressure_angle)) ** 2
    k = _positive("addendum", addendum)
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or math.isnan(ratio) or ratio < 1:
        raise ValueError(f"ratio is the mate's teeth over the pinion's, 1 or more (math.inf for a rack), not {ratio!r}")
    if math.isinf(ratio):
        bound = 2 * k / s2
    else:
        bound = 2 * k / ((1 + 2 * ratio) * s2) * (ratio + math.sqrt(ratio * ratio + (1 + 2 * ratio) * s2))
    return {"bound": bound, "teeth": math.ceil(bound - 1e-9)}


@formula(units={"teeth_pinion": "count", "pressure_angle": "rad (20 degrees by default)",
                "addendum": "modules (1 for full-depth teeth)"},
         returns="dict: bound (the largest mate's tooth count as a real number, math.inf when any mate and a rack "
                 "are free of interference) and teeth (the largest whole count, or None for no limit)",
         limits=("interference between the mating teeth of a pair, teeth without profile shift",
                 "the pinion must itself be able to mesh with an equal gear (gear_min_teeth with ratio 1): below "
                 "that no mate is free of interference and this raises"),
         source=cite("shigley", "Chapter 13, 'Interference': Eq. (13-12), and the table of its values at 20 degrees"
                     + _SLIDES))
def gear_max_mate_teeth(teeth_pinion: int, pressure_angle: float = PRESSURE_ANGLE,
                        addendum: float = ADDENDUM) -> Dict[str, Any]:
    """Largest gear a pinion meshes with free of interference: NG = (NP^2 sin^2(phi) - 4 k^2) / (4 k - 2 NP
    sin^2(phi))."""
    n = _teeth("teeth_pinion", teeth_pinion)
    s2 = math.sin(_pressure_angle(pressure_angle)) ** 2
    k = _positive("addendum", addendum)
    denominator = 4 * k - 2 * n * s2
    if denominator <= 0:
        return {"bound": math.inf, "teeth": None}
    bound = (n * n * s2 - 4 * k * k) / denominator
    if bound < n - 1e-9:
        least = gear_min_teeth(pressure_angle, 1.0, addendum)["teeth"]
        raise ValueError(f"a pinion of {n} teeth interferes even with an equal gear at this pressure angle; the "
                         f"least is {least}")
    return {"bound": bound, "teeth": math.floor(bound + 1e-9)}


# ----------------------------------------------------------------------------- geometry: straight bevel gears

@formula(units={"teeth_pinion": "count", "teeth_gear": "count"},
         returns="dict: pinion and gear (their pitch cone angles, rad; they add to pi/2)",
         limits=(_RIGHT_ANGLE,),
         source=cite("shigley", "Chapter 13, 'Straight Bevel Gears': Eq. (13-14), tan(gamma) = NP / NG and "
                     "tan(Gamma) = NG / NP" + _SLIDES) + "; "
                + cite("khurmi", "Section 30.4 (determination of pitch angle for bevel gears), the note for a shaft "
                       "angle of 90 degrees"))
def bevel_pitch_angles(teeth_pinion: int, teeth_gear: int) -> Dict[str, float]:
    """Pitch cone angles of a straight bevel pair on shafts at 90 degrees: tan(gamma) = NP / NG for the pinion and
    tan(Gamma) = NG / NP for the gear."""
    n1, n2 = _teeth("teeth_pinion", teeth_pinion), _teeth("teeth_gear", teeth_gear)
    return {"pinion": math.atan2(n1, n2), "gear": math.atan2(n2, n1)}


@formula(units={"module": "m (at the large end)", "teeth_pinion": "count", "teeth_gear": "count"},
         returns="cone distance (the slant height of the pitch cone), m", limits=(_RIGHT_ANGLE, _LARGE_END),
         source=cite("khurmi", "Section 30.7 (strength of bevel gears): L = sqrt((DG / 2)^2 + (DP / 2)^2)") + "; "
                + cite("shigley", "Chapter 15, Eq. (15-25), A0 = dP / (2 sin(gamma))" + _SLIDES))
def bevel_cone_distance(module: float, teeth_pinion: int, teeth_gear: int) -> float:
    """Cone distance of a straight bevel pair on shafts at 90 degrees, from the apex to the large end of the teeth:
    L = (m / 2) sqrt(NP^2 + NG^2)."""
    return _positive("module", module) / 2 * math.hypot(_teeth("teeth_pinion", teeth_pinion),
                                                         _teeth("teeth_gear", teeth_gear))


@formula(units={"pitch_diameter": "m (at the large end)", "face_width": "m (along the pitch cone)",
                "cone_distance": "m"},
         returns="mean pitch radius, at the middle of the face, m",
         limits=(_LARGE_END, "the middle of the face width, where the resultant tooth force is taken to act; the "
                 "true resultant of a load spread along a tapered tooth sits slightly further out"),
         source=cite("khurmi", "Section 30.8 (forces acting on a bevel gear): Rm = (L - b / 2) DP / (2 L)"))
def bevel_mean_radius(pitch_diameter: float, face_width: float, cone_distance: float) -> float:
    """Mean pitch radius of a straight bevel gear: Rm = (L - b / 2) d / (2 L), which is d / 2 - (b / 2) sin(gamma)."""
    d = _positive("pitch_diameter", pitch_diameter)
    b, cone = _face_on_cone(face_width, cone_distance)
    return (cone - b / 2) * d / (2 * cone)


@formula(units={"cone_distance": "m", "module": "m (at the large end)"},
         returns="dict: third_of_cone (L / 3, m), ten_modules (10 m, m) and maximum (the smaller of the two, m)",
         limits=("recommendations, not limits of strength: past them the added face is at the small end, where the "
                 "teeth are small, hard to cut and carry little, and the Lewis cone factor's dropped term grows",
                 "Shigley prints 0.3 of the cone distance rather than one third; Khurmi and Gupta also give 6.3 to "
                 "9.5 modules as the usual range"),
         source=cite("shigley", "Chapter 15, Eq. (15-24), F = min(0.3 A0, 10 / Pd)" + _SLIDES) + "; "
                + cite("khurmi", "Section 30.7 (strength of bevel gears), note 2: the ratio L / b should not exceed 3"))
def bevel_face_width_limits(cone_distance: float, module: float) -> Dict[str, float]:
    """Largest face width commonly recommended for a straight bevel gear: a third of the cone distance, and ten
    modules, whichever is smaller."""
    third, ten = _positive("cone_distance", cone_distance) / 3, 10 * _positive("module", module)
    return {"third_of_cone": third, "ten_modules": ten, "maximum": min(third, ten)}


@formula(units={"teeth": "count", "pitch_angle": "rad (the gear's own pitch cone angle)"},
         returns="virtual (formative, equivalent) number of teeth, not a whole number",
         limits=(_TREDGOLD, "the pitch angle is this gear's own, from bevel_pitch_angles"),
         source=cite("shigley", "Chapter 13, 'Straight Bevel Gears': Eq. (13-15), N' = 2 pi rb / p" + _SLIDES) + "; "
                + cite("khurmi", "Section 30.6 (formative or equivalent number of teeth for bevel gears, Tredgold's "
                       "approximation): TE = T sec(theta_P)"))
def bevel_virtual_teeth(teeth: int, pitch_angle: float) -> float:
    """Virtual number of teeth of a straight bevel gear, the teeth of the spur gear its back cone develops into:
    N' = N / cos(gamma). The Lewis form factor of a bevel tooth is read at this number."""
    return _teeth("teeth", teeth) / math.cos(_pitch_angle(pitch_angle))


# ----------------------------------------------------------------------------- tooth forces

@formula(units={"torque": "N m (on this gear)", "radius": "m (the radius the force acts at)"},
         returns="tangential force, N",
         limits=("statics: the force that carries the torque at that radius. For a spur gear the pitch radius; for "
                 "a straight bevel gear the mean pitch radius for shaft and bearing loads, and the large-end pitch "
                 "radius for the Lewis equation. The two bevel forces differ and are not interchangeable",),
         source=cite("shigley", "Chapter 13, 'Force Analysis: Spur Gearing' and 'Force Analysis: Bevel Gearing': "
                     "T = (d / 2) Wt and Eq. (13-37), Wt = T / rav" + _SLIDES))
def gear_tangential_force(torque: float, radius: float) -> float:
    """Tangential (transmitted) tooth force from a torque at a radius: Wt = T / r."""
    return abs(_number("torque", torque)) / _positive("radius", radius)


@formula(units={"torque": "N m (on this gear)", "pitch_diameter": "m",
                "pressure_angle": "rad (20 degrees by default)"},
         returns="dict: tangential, radial (separating) and normal (the resultant along the line of action), N",
         limits=(_RIGID_STATICS, "a spur gear: no axial force"),
         source=cite("shigley", "Chapter 13, 'Force Analysis: Spur Gearing': T = (d / 2) Wt, with the radial "
                     "component Wt tan(phi)" + _SLIDES))
def spur_gear_forces(torque: float, pitch_diameter: float, pressure_angle: float = PRESSURE_ANGLE) -> Dict[str, float]:
    """Tooth forces on a spur gear: tangential Wt = 2 T / d at the pitch circle, radial Wr = Wt tan(phi) pushing the
    gears apart, and the normal force Wt / cos(phi)."""
    phi = _pressure_angle(pressure_angle)
    wt = gear_tangential_force(torque, _positive("pitch_diameter", pitch_diameter) / 2)
    return {"tangential": wt, "radial": wt * math.tan(phi), "normal": wt / math.cos(phi)}


@formula(units={"torque": "N m (on this gear)", "mean_radius": "m (bevel_mean_radius of this gear)",
                "pitch_angle": "rad (this gear's own pitch cone angle)",
                "pressure_angle": "rad (20 degrees by default)"},
         returns="dict: tangential, radial (toward this gear's axis), axial (along this gear's axis, away from the "
                 "apex) and normal, N",
         limits=(_RIGID_STATICS, _RIGHT_ANGLE,
                 "the force acts at the mean pitch radius, the middle of the face",
                 "the tangential force here is for shafts and bearings; the Lewis equation takes the force at the "
                 "large-end pitch radius instead (bevel_tooth_bending returns both)",
                 "on shafts at 90 degrees the pinion's axial force is the gear's radial force and the reverse"),
         source=cite("shigley", "Chapter 13, 'Force Analysis: Bevel Gearing': Eqs. (13-37) and (13-38), checked on "
                     "Example 13-8" + _SLIDES) + "; "
                + cite("khurmi", "Section 30.8 (forces acting on a bevel gear)"))
def bevel_gear_forces(torque: float, mean_radius: float, pitch_angle: float,
                      pressure_angle: float = PRESSURE_ANGLE) -> Dict[str, float]:
    """Tooth forces on a straight bevel gear, at its mean pitch radius: tangential Wt = T / rav, radial Wr = Wt
    tan(phi) cos(gamma) and axial Wa = Wt tan(phi) sin(gamma)."""
    phi, gamma = _pressure_angle(pressure_angle), _pitch_angle(pitch_angle)
    wt = gear_tangential_force(torque, mean_radius)
    return {"tangential": wt, "radial": wt * math.tan(phi) * math.cos(gamma),
            "axial": wt * math.tan(phi) * math.sin(gamma), "normal": wt / math.cos(phi)}


# ----------------------------------------------------------------------------- Lewis bending

def _table_for(pressure_angle: float, table: Optional[str]) -> Tuple[str, float, Tuple[Tuple[float, float], ...]]:
    degrees = math.degrees(_pressure_angle(pressure_angle))
    angle = next((a for a in _DEFAULT_TABLE if abs(a - degrees) < 1e-6), None)
    if angle is None:
        raise ValueError(f"the Lewis form factor is tabulated for full-depth teeth at 14.5 and 20 degrees only, not "
                         f"{degrees:g} degrees (pressure_angle is in radians)")
    name = _DEFAULT_TABLE[angle] if table is None else table
    if not isinstance(name, str) or name not in LEWIS_FORM_FACTORS:
        raise ValueError(f"table must be one of {sorted(LEWIS_FORM_FACTORS)} or None, not {table!r}")
    if angle not in LEWIS_FORM_FACTORS[name]:
        raise ValueError(f"the {name} table has no column for {angle:g} degrees; it has "
                         f"{sorted(LEWIS_FORM_FACTORS[name])}")
    return name, angle, LEWIS_FORM_FACTORS[name][angle]


@formula(units={"teeth": "count (a bevel gear's virtual number, which need not be whole; math.inf for a rack)",
                "pressure_angle": "rad: 20 degrees (the default) or 14.5 degrees",
                "table": "'shigley' (20 degrees) or 'boston' (14.5 and 20 degrees); None takes Shigley's at 20 "
                         "degrees and Boston Gear's at 14.5"},
         returns="Lewis form factor Y, dimensionless (stress = force / (face width x module x Y))",
         limits=(_FULL_DEPTH + "; 14.5 and 20 degree teeth only",
                 "the load at the tip of one tooth, no sharing with the next pair, no stress concentration",
                 "between tabulated tooth counts Y is interpolated linearly in 1 / N (which also reaches the rack "
                 "row at 1 / N = 0); the tables give three figures and the interpolation adds none",
                 "below the table's first row (12 teeth in Shigley's, 10 in Boston Gear's) it raises: such teeth "
                 "are undercut and their form depends on the cutter",
                 "the two 20 degree tables differ by up to 0.003, about 1 %"),
         source=cite("shigley", "Chapter 14, Table 14-2 (values of the Lewis form factor Y: a normal pressure angle "
                     "of 20 degrees, full-depth teeth)" + _SLIDES) + "; "
                + cite("boston-gear-spur", "p. 311, Table I (tooth form factor Y), columns for 14-1/2 degree and 20 "
                       "degree full depth involute teeth"))
def lewis_form_factor(teeth: float, pressure_angle: float = PRESSURE_ANGLE, table: Optional[str] = None) -> float:
    """Lewis form factor Y of a full-depth involute tooth, from a published table, interpolated between its tooth
    counts."""
    _, _, rows = _table_for(pressure_angle, table)
    if isinstance(teeth, bool) or not isinstance(teeth, (int, float)) or math.isnan(teeth) or teeth <= 0:
        raise ValueError(f"teeth must be a number above 0 (math.inf for a rack), not {teeth!r}")
    if teeth < rows[0][0]:
        raise ValueError(f"the table starts at {rows[0][0]} teeth; {teeth!r} is below it (undercut teeth are not "
                         "tabulated)")
    x = 0.0 if math.isinf(teeth) else 1.0 / teeth
    for (n0, y0), (n1, y1) in zip(rows, rows[1:]):
        x0, x1 = 1.0 / n0, (0.0 if math.isinf(n1) else 1.0 / n1)
        if x1 <= x <= x0:
            if x == x0:
                return y0
            if x == x1:
                return y1
            return y0 + (y1 - y0) * (x0 - x) / (x0 - x1)
    raise AssertionError("unreachable: the table spans every tooth count from its first row to a rack")


@formula(units={"speed": "m/s (pitch-line velocity; for a bevel gear, at the large end)",
                "profile": "'cast', 'cut', 'hobbed' or 'ground': how the teeth were made"},
         returns="velocity factor Kv, 1 or more (it multiplies the Lewis stress)",
         limits=("an empirical allowance for the profile errors of metal teeth at speed, after Barth's velocity "
                 "factor; not a dynamic analysis, and AGMA's Kv with a quality number has replaced it",
                 "metal teeth: nothing here was fitted to plastic or printed gears",
                 "Boston Gear rates its cut gears with 600 / (600 + V), V in ft/min, the reciprocal of the 'cast' "
                 "form, and only to 1500 ft/min (7.6 m/s)"),
         source=cite("shigley", "Chapter 14, 'Dynamic Effects': Eqs. (14-6a) to (14-6d), V in m/s" + _SLIDES) + "; "
                + cite("khurmi", "Section 28.18 (permissible working stress for gear teeth in the Lewis equation): "
                       "the Barth formula, a velocity factor on the allowable stress"))
def gear_velocity_factor(speed: float, profile: str = "cut") -> float:
    """Velocity (Barth) factor Kv for the Lewis equation, by how the teeth were made: (3.05 + V) / 3.05 cast,
    (6.1 + V) / 6.1 cut or milled, (3.56 + sqrt V) / 3.56 hobbed or shaped, sqrt((5.56 + sqrt V) / 5.56) shaved or
    ground, with V in m/s."""
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or speed < 0:
        raise ValueError(f"speed must be a finite number, 0 or more, not {speed!r}")
    if not isinstance(profile, str) or profile not in VELOCITY_PROFILES:
        raise ValueError(f"profile must be one of {sorted(VELOCITY_PROFILES)}: {VELOCITY_PROFILES}")
    v = float(speed)
    if profile == "cast":
        return (3.05 + v) / 3.05
    if profile == "cut":
        return (6.1 + v) / 6.1
    if profile == "hobbed":
        return (3.56 + math.sqrt(v)) / 3.56
    return math.sqrt((5.56 + math.sqrt(v)) / 5.56)


def _velocity_factor(v: Any) -> float:
    v = _positive("velocity_factor", v)
    if v < 1:
        raise ValueError(f"velocity_factor multiplies the stress and is 1 or more (1 for a static load), not {v!r}")
    return v


@formula(units={"force": "N (tangential, at the pitch circle)", "face_width": "m", "module": "m",
                "form_factor": "Lewis form factor Y (lewis_form_factor)",
                "velocity_factor": "Kv, 1 or more (gear_velocity_factor); 1 for a static load"},
         returns="bending stress at the root of the tooth, Pa",
         limits=(_LEWIS, _NOT_AGMA, _NO_ALLOWABLE,
                 "Shigley's rule of thumb is a face width of 3 to 5 circular pitches (about 9 to 16 modules): a "
                 "wider face does not load evenly unless the mountings are stiff and well aligned"),
         source=cite("shigley", "Chapter 14, 'The Lewis Bending Equation': Eq. (14-8), sigma = Kv Wt / (F m Y), "
                     "checked on Example 14-1" + _SLIDES))
def lewis_bending_stress(force: float, face_width: float, module: float, form_factor: float,
                         velocity_factor: float = 1.0) -> float:
    """Lewis bending stress of a spur gear tooth: sigma = Kv Wt / (b m Y)."""
    return (_velocity_factor(velocity_factor) * abs(_number("force", force))
            / (_positive("face_width", face_width) * _positive("module", module)
               * _positive("form_factor", form_factor)))


@formula(units={"face_width": "m (along the pitch cone)", "cone_distance": "m"},
         returns="cone (bevel) factor (L - b) / L, between 0 and 1",
         limits=("it comes from applying the Lewis equation to thin slices of the tapered tooth and adding their "
                 "torques: the exact sum is 1 - b / L + b^2 / (3 L^2), and the last term is dropped, which "
                 "understates the strength by at most 5.3 % for a face up to a third of the cone distance and "
                 "grows fast past it",
                 "every slice at the same root stress, which needs the mounting to keep the teeth in line along "
                 "the whole face"),
         source=cite("khurmi", "Section 30.7 (strength of bevel gears), note 1: the factor (L - b) / L, the bevel "
                     "factor"))
def bevel_cone_factor(face_width: float, cone_distance: float) -> float:
    """Cone (bevel) factor of a straight bevel tooth, the share of a spur tooth's Lewis strength its taper leaves:
    (L - b) / L."""
    b, cone = _face_on_cone(face_width, cone_distance)
    return (cone - b) / cone


@formula(units={"force": "N (tangential, at the LARGE-END pitch radius: torque / (pitch diameter / 2))",
                "face_width": "m (along the pitch cone)", "module": "m (at the large end)",
                "form_factor": "Lewis form factor Y at the VIRTUAL number of teeth (bevel_virtual_teeth)",
                "cone_distance": "m",
                "velocity_factor": "Kv, 1 or more (gear_velocity_factor at the large end's speed); 1 for a static "
                                   "load"},
         returns="bending stress at the root of the tooth, Pa",
         limits=(_LEWIS, _NOT_AGMA, _NO_ALLOWABLE, _TREDGOLD, _RIGHT_ANGLE,
                 "the force is the torque over the large-end pitch radius, not the larger force at the mean radius "
                 "that loads the bearings; using the mean-radius force here, or leaving the cone factor out, are "
                 "the two usual mistakes",
                 "a face width within the recommended limits (bevel_face_width_limits), where the cone factor's "
                 "dropped term is small"),
         source=cite("khurmi", "Section 30.7 (strength of bevel gears): WT = (sigma_o Cv) b pi m y' (L - b) / L, with "
                     "y' at the equivalent number of teeth"))
def lewis_bevel_bending_stress(force: float, face_width: float, module: float, form_factor: float,
                               cone_distance: float, velocity_factor: float = 1.0) -> float:
    """Lewis bending stress of a straight bevel gear tooth: sigma = Kv Wt L / (b m Y' (L - b)), the spur equation
    over the cone factor, with the force at the large-end pitch radius and Y' at the virtual number of teeth."""
    return (lewis_bending_stress(force, face_width, module, form_factor, velocity_factor)
            / bevel_cone_factor(face_width, cone_distance))


@formula(units={"torque": "N m (on this gear)", "module": "m", "teeth": "count", "face_width": "m",
                "pressure_angle": "rad: 20 degrees (the default) or 14.5 degrees",
                "velocity_factor": "Kv, 1 or more; 1 for a static load", "table": "as lewis_form_factor"},
         returns="dict: stress (Pa), force (tangential at the pitch circle, N), radial (N), pitch_diameter (m), "
                 "form_factor and velocity_factor",
         limits=(_LEWIS, _NOT_AGMA, _NO_ALLOWABLE, _FULL_DEPTH + "; 14.5 and 20 degree teeth only",
                 "check both gears of a pair: the smaller has the lower form factor, the weaker material may be "
                 "the other"),
         source=cite("shigley", "Chapter 14, 'The Lewis Bending Equation': Eq. (14-8) and Table 14-2" + _SLIDES))
def spur_tooth_bending(torque: float, module: float, teeth: int, face_width: float,
                       pressure_angle: float = PRESSURE_ANGLE, velocity_factor: float = 1.0,
                       table: Optional[str] = None) -> Dict[str, float]:
    """Lewis bending stress of a spur gear tooth from the torque on the gear: the force at the pitch circle, the
    tabulated form factor, and sigma = Kv Wt / (b m Y)."""
    d = gear_pitch_diameter(module, teeth)
    forces = spur_gear_forces(torque, d, pressure_angle)
    y = lewis_form_factor(teeth, pressure_angle, table)
    kv = _velocity_factor(velocity_factor)
    return {"stress": lewis_bending_stress(forces["tangential"], face_width, module, y, kv),
            "force": forces["tangential"], "radial": forces["radial"], "pitch_diameter": d, "form_factor": y,
            "velocity_factor": kv}


@formula(units={"torque": "N m (on this gear)", "module": "m (at the large end)", "teeth": "count (this gear)",
                "mate_teeth": "count (the gear it meshes with)", "face_width": "m (along the pitch cone)",
                "pressure_angle": "rad: 20 degrees (the default) or 14.5 degrees",
                "velocity_factor": "Kv, 1 or more; 1 for a static load", "table": "as lewis_form_factor"},
         returns="dict: stress (Pa); force_large_end (tangential at the large-end pitch radius, the Lewis force, N); "
                 "force_mean, radial and axial (at the mean pitch radius, for shafts and bearings, N); "
                 "pitch_diameter, mean_radius, cone_distance and face_width_limit (m); pitch_angle (rad); "
                 "virtual_teeth, form_factor, cone_factor, velocity_factor; and face_width_ok (bool: within the "
                 "recommended limit)",
         limits=(_LEWIS, _NOT_AGMA, _NO_ALLOWABLE, _TREDGOLD, _RIGHT_ANGLE, _LARGE_END,
                 _FULL_DEPTH + "; 14.5 and 20 degree teeth only. Bevel teeth are often cut with a long-addendum "
                 "pinion, whose form factor the makers tabulate separately and which this does not use",
                 "the virtual tooth number must reach the table's first row",
                 "check both gears of a pair, each with its own torque, tooth count and material"),
         source=cite("khurmi", "Sections 30.6 to 30.8: the equivalent number of teeth, the strength of bevel gears "
                     "and the forces acting on a bevel gear") + "; "
                + cite("shigley", "Chapter 13, Eqs. (13-14), (13-15), (13-37) and (13-38), and Chapter 14, Table 14-2"
                       + _SLIDES))
def bevel_tooth_bending(torque: float, module: float, teeth: int, mate_teeth: int, face_width: float,
                        pressure_angle: float = PRESSURE_ANGLE, velocity_factor: float = 1.0,
                        table: Optional[str] = None) -> Dict[str, Any]:
    """Lewis bending stress of a straight bevel gear tooth from the torque on the gear, with every radius kept
    apart: the force at the large-end pitch radius, the form factor at the virtual tooth number and the cone factor
    give the stress; the forces at the mean radius are returned for the shaft and its bearings."""
    d = gear_pitch_diameter(module, teeth)
    gamma = bevel_pitch_angles(teeth, mate_teeth)["pinion"]         # this gear's own angle: atan(teeth / mate_teeth)
    cone = bevel_cone_distance(module, teeth, mate_teeth)
    virtual = bevel_virtual_teeth(teeth, gamma)
    y = lewis_form_factor(virtual, pressure_angle, table)
    kv = _velocity_factor(velocity_factor)
    force = gear_tangential_force(torque, d / 2)
    mean_radius = bevel_mean_radius(d, face_width, cone)
    at_mean = bevel_gear_forces(torque, mean_radius, gamma, pressure_angle)
    limit = bevel_face_width_limits(cone, module)["maximum"]
    return {"stress": lewis_bevel_bending_stress(force, face_width, module, y, cone, kv),
            "force_large_end": force, "force_mean": at_mean["tangential"], "radial": at_mean["radial"],
            "axial": at_mean["axial"], "pitch_diameter": d, "mean_radius": mean_radius, "cone_distance": cone,
            "pitch_angle": gamma, "virtual_teeth": virtual, "form_factor": y,
            "cone_factor": bevel_cone_factor(face_width, cone), "velocity_factor": kv, "face_width_limit": limit,
            "face_width_ok": float(face_width) <= limit * (1 + 1e-12)}
