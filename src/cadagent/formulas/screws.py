"""Screws: preload from tightening torque with the nut factor, the ISO tensile stress area, and the thread shear areas
for a stripping estimate (a screw in a printed boss, a tapped hole, a heat-set insert's own thread).

SI units: metres, newtons, pascals; torque in N m.

A thread-forming screw in a plastic boss (:func:`screw_boss`) joins these with the boss's own checks: the radial
push of the loaded flanks (:func:`thread_radial_pressure`), the hoop stress it raises in the boss wall
(:func:`boss_hoop_stress`), the makers' boss proportions and Covestro's tightening window, between 1.2 x the drive
torque and half the stripping torque.

The nut factor lumps thread and head friction, so torque gives preload only to about +/- 25 % even with a known
factor, and much worse in plastic, where it is rarely measured. The stripping estimate takes the ISO 68-1 basic
profile with full thread depth and no tolerances, and spreads the load evenly over the engaged threads; real threads
carry most of the load in the first few, have clearance, and printed threads are weaker across layers and creep under
preload. It ranks designs and finds the weaker side; it is not a rating. Test the joint.
"""
from __future__ import annotations

import math
from typing import Any, Dict

from cadagent.formulas._registry import cite, formula

# Shigley Table 8-15: torque factor K for T = K F d, by bolt condition (after Blake and Kurtz).
NUT_FACTORS = {"nonplated-black": 0.30, "zinc-plated": 0.20, "lubricated": 0.18, "cadmium-plated": 0.16,
               "anti-seize": 0.12, "unstated": 0.20}
FLANK_HALF_ANGLE = math.radians(30.0)          # ISO metric and Unified threads: 60 degree flanks
PITCH_DIAMETER = 0.649519                       # d2 = d - 0.649519 p (ISO 68-1 basic profile)
MINOR_DIAMETER = 1.082532                       # D1 = d - 1.082532 p (internal thread, basic)
STRESS_DIAMETER = 0.938194                      # ds = d - 0.938194 p ((d2 + d3) / 2)
_TORQUE = ("the nut factor lumps thread and head friction: preload from torque is good to about +/- 25 % with a "
           "known factor, and unknown in plastic until measured")
_STRIP = ("ISO 68-1 basic profile, full depth, no tolerances, load spread evenly over the engaged length (real "
          "threads load the first few most); static; printed threads are weaker across layers and creep")


@formula(units={"torque": "N m", "diameter": "m (nominal)", "nut_factor": "dimensionless (see NUT_FACTORS)"},
         returns="preload, N", limits=(_TORQUE,),
         source=cite("shigley", "Section 8-8 (Relating Bolt Torque to Bolt Tension), Eq. (8-27) and Table 8-15"))
def preload_from_torque(torque: float, diameter: float, nut_factor: float = NUT_FACTORS["unstated"]) -> float:
    """Clamp force from tightening torque: Fi = T / (K d). K = 0.2 when the condition is not stated."""
    return torque / (nut_factor * diameter)


@formula(units={"preload": "N", "diameter": "m (nominal)", "nut_factor": "dimensionless (see NUT_FACTORS)"},
         returns="tightening torque, N m", limits=(_TORQUE,),
         source=cite("shigley", "Section 8-8, Eq. (8-27)"))
def torque_for_preload(preload: float, diameter: float, nut_factor: float = NUT_FACTORS["unstated"]) -> float:
    """Tightening torque for a target clamp force: T = K Fi d."""
    return nut_factor * preload * diameter


@formula(units={"diameter": "m (nominal)", "pitch": "m", "thread_friction": "dimensionless",
                "collar_friction": "dimensionless (under the head or nut)",
                "flank_angle": "rad (the included angle between the flanks: 60 degrees for ISO metric)"},
         returns="nut factor K, dimensionless",
         limits=("the head or nut bears on a collar of mean diameter 1.25 d; the pitch diameter is the ISO 68-1 "
                 "relation d - 0.6495 p, an approximation for any other thread form", _TORQUE),
         source=cite("shigley", "Section 8-8, Eq. (8-26) (thread and collar torque before it is written as T = K F d)"))
def nut_factor(diameter: float, pitch: float, thread_friction: float, collar_friction: float,
               flank_angle: float = math.radians(60.0)) -> float:
    """Nut factor from friction: K = (dm / 2d)(tan lambda + f sec alpha) / (1 - f tan lambda sec alpha) + 0.625 fc,
    with dm the pitch diameter, lambda the lead angle and alpha half the flank angle."""
    dm = diameter - PITCH_DIAMETER * pitch
    tan_lead = pitch / (math.pi * dm)
    sec = 1.0 / math.cos(flank_angle / 2.0)
    thread = dm / (2.0 * diameter) * (tan_lead + thread_friction * sec) / (1.0 - thread_friction * tan_lead * sec)
    return thread + 0.625 * collar_friction


@formula(units={"diameter": "m (nominal)", "pitch": "m"}, returns="tensile stress area, m^2",
         limits=("ISO metric 60 degree thread",),
         source=cite("iso898", "nominal stress area As = pi/4 ((d2 + d3) / 2)^2; tabulated in Shigley 10th ed., "
                     "Section 8-1, Table 8-1"))
def tensile_stress_area(diameter: float, pitch: float) -> float:
    """Tensile stress area of an ISO metric thread: As = pi / 4 (d - 0.9382 p)^2."""
    return math.pi / 4.0 * (diameter - STRESS_DIAMETER * pitch) ** 2


@formula(units={"diameter": "m (nominal)", "pitch": "m", "engagement": "m (length of full thread engaged)"},
         returns="dict: external (the screw's threads) and internal (the hole's threads) shear areas, m^2",
         limits=(_STRIP,),
         source=cite("iso68", "basic profile; the shear-area relations of FED-STD-H28/2B with zero tolerances"))
def thread_shear_areas(diameter: float, pitch: float, engagement: float) -> Dict[str, float]:
    """Shear areas that strip a thread: the screw's teeth shear at the hole's minor diameter (0.75 pi D1 Le), the
    hole's teeth at the screw's major diameter (0.875 pi d Le)."""
    d1 = diameter - MINOR_DIAMETER * pitch
    return {"external": 0.75 * math.pi * d1 * engagement, "internal": 0.875 * math.pi * diameter * engagement}


@formula(units={"diameter": "m (nominal)", "pitch": "m", "engagement": "m", "shear_strength": "Pa",
                "side": "'internal' (the hole strips) or 'external' (the screw strips)"},
         returns="force that strips the thread, N", limits=(_STRIP,),
         source=cite("iso68", "basic profile; shear area times shear strength"))
def thread_strip_force(diameter: float, pitch: float, engagement: float, shear_strength: float,
                       side: str = "internal") -> float:
    """Stripping force of one side of a thread: its shear area times the material's shear strength. For a screw in
    plastic the plastic (internal) side strips first."""
    areas = thread_shear_areas(diameter, pitch, engagement)
    if side not in areas:
        raise ValueError("side must be 'internal' or 'external'")
    return areas[side] * shear_strength


# ----------------------------------------------------------------------------- a thread-forming screw in a boss
# Boss proportions for a thread-forming screw, as multiples of its nominal diameter d, from the maker's boss
# recommendations for the DELTA PT (Bulten, p. 7: the figure and its text). Covestro's own (self-tapping screws,
# Fig. 3) are wider: an outside diameter of 1.8 to 2.5 d and at least 2.3 d engaged.
BOSS_HOLE = 0.8                       # the most favourable hole; 0.72 to 0.88 d for some materials
BOSS_HOLE_RANGE = (0.72, 0.88)
BOSS_OUTSIDE = 2.0                    # boss outside diameter
BOSS_ENGAGEMENT = 2.0                 # engaged length
# Covestro's tightening window (self-tapping screws, Section A and Fig. 1; joining guide p. 10, Fig. 6): tighten to at
# least 1.2 x the drive (insertion) torque and at most 0.5 x the stripping torque, both measured.
TIGHTEN_OVER_DRIVE = 1.2
TIGHTEN_OVER_STRIP = 0.5
_RATIO_SLACK = 1e-9
FORMING_FLANK_ANGLE = math.radians(30.0)   # DELTA PT: a 30 degree flank, backing off to 20 (Bulten, p. 2)
_FLANK = ("frictionless flank under an axial load spread evenly over the engaged length; the pressure is taken on "
          "the cylinder through the screw's crests, the inside of the boss's unbroken wall")
_LAME = ("Lame thick-walled cylinder: linear elastic, isotropic, uniform internal pressure, no axial stress; a printed "
         "wall is not isotropic and its layers are weaker across than along")


def _number(v: float) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _finite(name: str, v: float, low: float = 0.0, strict: bool = True) -> float:
    if not (_number(v) and (v > low if strict else v >= low)):
        raise ValueError(f"{name} must be a finite number {'above' if strict else 'of at least'} {low:g}, not {v!r}")
    return v


@formula(units={"load": "N (axial, carried by the thread)", "diameter": "m (nominal: the screw's crests)",
                "engagement": "m", "flank_angle": "rad (included: 60 degrees ISO, 30 degrees a DELTA PT)"},
         returns="radial pressure on the boss, Pa", limits=(_FLANK,),
         source=cite("shigley", "Section 8-2 (the normal force on a thread flank inclined at the half-angle alpha: "
                     "its axial part carries the load, its radial part F tan alpha pushes the nut outward)"))
def thread_radial_pressure(load: float, diameter: float, engagement: float,
                           flank_angle: float = math.radians(60.0)) -> float:
    """Radial pressure an axially loaded thread puts on the boss around it: the flanks' radial push F tan(alpha),
    alpha half the flank angle, spread over the crest cylinder, p = F tan(alpha) / (pi d Le)."""
    _finite("load", load, strict=False)
    _finite("diameter", diameter)
    _finite("engagement", engagement)
    if not (_number(flank_angle) and 0.0 < flank_angle < math.pi):
        raise ValueError(f"flank_angle must be between 0 and pi radians, not {flank_angle!r}")
    return load * math.tan(flank_angle / 2.0) / (math.pi * diameter * engagement)


@formula(units={"pressure": "Pa (internal)", "inner_diameter": "m", "outer_diameter": "m"},
         returns="tangential (hoop) stress at the bore, Pa, the highest in the wall", limits=(_LAME,),
         source=cite("shigley", "Section 3-14 (Stresses in Pressurized Cylinders: the tangential stress with no "
                     "outside pressure, at the inner radius)"))
def boss_hoop_stress(pressure: float, inner_diameter: float, outer_diameter: float) -> float:
    """Hoop stress at the bore of a thick-walled cylinder under internal pressure: sigma_t = p (D^2 + d^2) /
    (D^2 - d^2). It grows without bound as the wall thins: (D^2 + d^2) / (D^2 - d^2) is 1.67 at D = 2 d and 4.6
    at D = 1.25 d."""
    _finite("pressure", pressure, strict=False)
    _finite("inner_diameter", inner_diameter)
    if not (_number(outer_diameter) and outer_diameter > inner_diameter):
        raise ValueError(f"outer_diameter must be finite and above the inner diameter, not {outer_diameter!r}")
    d2, o2 = inner_diameter * inner_diameter, outer_diameter * outer_diameter
    return pressure * (o2 + d2) / (o2 - d2)


@formula(units={"diameter": "m (nominal)", "pitch": "m", "engagement": "m (length of full thread engaged)",
                "outside_diameter": "m (the boss)", "torque": "N m (tightening)",
                "shear_strength": "Pa (the boss material's, across its weakest plane)",
                "hoop_strength": "Pa (the boss material's tensile strength in the hoop direction)",
                "friction_low": "dimensionless (steel on the plastic: the low end)",
                "friction_high": "dimensionless (the high end)",
                "flank_angle": "rad (included)"},
         returns="dict: nut_factor, preload and strip_torque as {low, high}; strip_force (N), margin {low, high} "
                 "(strip torque over the tightening torque), torque_ceiling (N m), drive_torque_limit (N m), "
                 "radial_pressure and hoop_stress (Pa), hoop_ratio, outside_ratio, engagement_ratio, and the checks "
                 "torque_ok, outside_ok, engagement_ok, hoop_ok and passes",
         limits=(_TORQUE, _STRIP, _FLANK, _LAME,
                 "the drive (forming) torque is not computed: measure it, and tighten to at least 1.2 x it",
                 "the hoop stress is the clamp's share only: forming the thread pushes the wall out further, which "
                 "the makers' hole and boss proportions keep in check and which no closed form here predicts",
                 "no published pull-out or stripping data for thread-forming screws in printed bosses was found "
                 "(2026-11-01): a starting point to test, not a rating"),
         source=cite("covestro-screws", "Section A and Fig. 1 (tighten to 1.2 x the insertion torque, at most 0.5 x "
                     "the stripping torque), with the boss proportions of Bulten's DELTA PT brochure, p. 7"))
def screw_boss(diameter: float, pitch: float, engagement: float, outside_diameter: float, torque: float,
               shear_strength: float, hoop_strength: float, friction_low: float = 0.2, friction_high: float = 0.5,
               flank_angle: float = FORMING_FLANK_ANGLE) -> Dict[str, Any]:
    """A thread-forming screw tightened in a plastic boss: the clamp from the torque (a band, from the friction
    band), the force and torque that strip the boss's thread, Covestro's tightening window against them, the hoop
    stress the clamp raises at the wall's inside, and the boss proportions against the maker's."""
    for name, v in (("diameter", diameter), ("pitch", pitch), ("engagement", engagement), ("torque", torque),
                    ("shear_strength", shear_strength), ("hoop_strength", hoop_strength)):
        _finite(name, v)
    _finite("friction_low", friction_low, strict=False)
    if not (_number(friction_high) and friction_high >= friction_low):
        raise ValueError(f"friction_high must be finite and at least friction_low, not {friction_high!r}")
    if not (_number(outside_diameter) and outside_diameter > diameter):
        raise ValueError(f"outside_diameter must be finite and above the screw's diameter, not {outside_diameter!r}")
    k_low = nut_factor(diameter, pitch, friction_low, friction_low, flank_angle)
    k_high = nut_factor(diameter, pitch, friction_high, friction_high, flank_angle)
    strip = thread_strip_force(diameter, pitch, engagement, shear_strength, "internal")
    strip_low, strip_high = torque_for_preload(strip, diameter, k_low), torque_for_preload(strip, diameter, k_high)
    preload_high = preload_from_torque(torque, diameter, k_low)          # least friction: the most clamp
    pressure = thread_radial_pressure(preload_high, diameter, engagement, flank_angle)
    hoop = boss_hoop_stress(pressure, diameter, outside_diameter)
    ceiling = TIGHTEN_OVER_STRIP * strip_low
    out = {"nut_factor": {"low": k_low, "high": k_high},
           "preload": {"low": preload_from_torque(torque, diameter, k_high), "high": preload_high},
           "strip_force": strip, "strip_torque": {"low": strip_low, "high": strip_high},
           "margin": {"low": strip_low / torque, "high": strip_high / torque},
           "torque_ceiling": ceiling, "drive_torque_limit": torque / TIGHTEN_OVER_DRIVE,
           "radial_pressure": pressure, "hoop_stress": hoop, "hoop_ratio": hoop / hoop_strength,
           "outside_ratio": outside_diameter / diameter, "engagement_ratio": engagement / diameter}
    # the ratios are compared with a part in a billion to spare, so a boss drawn at exactly 2 d is not failed by
    # rounding in d and D
    out.update(torque_ok=torque <= ceiling, outside_ok=out["outside_ratio"] >= BOSS_OUTSIDE * (1 - _RATIO_SLACK),
               engagement_ok=out["engagement_ratio"] >= BOSS_ENGAGEMENT * (1 - _RATIO_SLACK),
               hoop_ok=out["hoop_ratio"] < 1.0)
    out["passes"] = out["torque_ok"] and out["outside_ok"] and out["engagement_ok"] and out["hoop_ok"]
    return out
