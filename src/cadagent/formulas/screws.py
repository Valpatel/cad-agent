"""Screws: preload from tightening torque with the nut factor, the ISO tensile stress area, and the thread shear areas
for a stripping estimate (a screw in a printed boss, a tapped hole, a heat-set insert's own thread).

SI units: metres, newtons, pascals; torque in N m.

The nut factor lumps thread and head friction, so torque gives preload only to about +/- 25 % even with a known
factor, and much worse in plastic, where it is rarely measured. The stripping estimate takes the ISO 68-1 basic
profile with full thread depth and no tolerances, and spreads the load evenly over the engaged threads; real threads
carry most of the load in the first few, have clearance, and printed threads are weaker across layers and creep under
preload. It ranks designs and finds the weaker side; it is not a rating. Test the joint.
"""
from __future__ import annotations

import math
from typing import Dict

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
                "collar_friction": "dimensionless (under the head or nut)"},
         returns="nut factor K, dimensionless",
         limits=("60 degree thread; the head or nut bears on a collar of mean diameter 1.25 d", _TORQUE),
         source=cite("shigley", "Section 8-8, Eq. (8-26) (thread and collar torque before it is written as T = K F d)"))
def nut_factor(diameter: float, pitch: float, thread_friction: float, collar_friction: float) -> float:
    """Nut factor from friction: K = (dm / 2d)(tan lambda + f sec alpha) / (1 - f tan lambda sec alpha) + 0.625 fc,
    with dm the pitch diameter and lambda the lead angle."""
    dm = diameter - PITCH_DIAMETER * pitch
    tan_lead = pitch / (math.pi * dm)
    sec = 1.0 / math.cos(FLANK_HALF_ANGLE)
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
