"""A thread-forming screw in a printed boss: the maker's screw sizes, the friction band, and the check of one boss in
one of the datasheet filaments of :data:`cadagent.mechanical.compliant.allowables.PRINTED`.

    from cadagent.mechanical.bosses import printed_boss
    printed_boss("pla-bambu-basic", size="30", outside_mm=6, engagement_mm=6, torque_nm=0.3)
    # clamp 132-374 N; the boss's thread strips at 767 N (0.62-1.74 N m); tighten to at most 0.31 N m

The closed forms are :func:`cadagent.formulas.screw_boss` and the functions it calls (Shigley's torque-preload
relation and thread statics, the ISO 68-1 stripping area, Lame's thick-walled cylinder), with Covestro's tightening
window and the screw maker's boss proportions. This module picks the numbers for a printed boss:

* **Shear strength** of the boss's thread: half the lowest datasheet tensile strength across the layers (the
  maximum-shear-stress criterion, Shigley 10th ed. Section 5-4). Pull-out shears the thread along a cylinder round the
  screw, and in a printed boss that cylinder crosses the layers whichever way the boss stands.
* **Hoop strength**: the lowest datasheet tensile strength along the layers for an upright boss (its hoop stress runs
  round the perimeters, in the layer plane), across them for a boss lying on its side (the hoop stress crosses the
  layers at its top and bottom).
* **Friction**, steel on plastic, under the head and on the flanks: 0.20 to 0.65, the span of the Covestro snap-fit
  guide's Table 3 (PTFE aside). PLA and PETG are not in that table, and no printed surface was measured.

**What is missing.** No published pull-out or stripping data for thread-forming screws in FDM bosses was found
(2026-11-01). The datasheets' strengths are for 100 % infill bars; a boss is a few perimeters round a hole, the thread
is formed across layer seams, and the drive torque that forms it is not computed here. So a result is a starting
point for a test boss (drive torque, stripping torque and pull-out, measured), not a rating.
"""
from __future__ import annotations

from typing import Any, Dict

from cadagent import formulas as fx
from cadagent.mechanical.compliant.allowables import PRINTED, STATUS

# EJOT DELTA PT thread-forming screws: nominal (crest) diameter and pitch in mm, by size (Bulten AB, DELTA PT brochure
# version 250422, p. 4, Delta PT dimensions; made under licence from EJOT). The flank is 30 degrees (p. 2).
DELTA_PT: Dict[str, Dict[str, float]] = {
    "20": {"diameter_mm": 2.0, "pitch_mm": 0.78}, "22": {"diameter_mm": 2.2, "pitch_mm": 0.85},
    "25": {"diameter_mm": 2.5, "pitch_mm": 0.95}, "30": {"diameter_mm": 3.0, "pitch_mm": 1.12},
    "35": {"diameter_mm": 3.5, "pitch_mm": 1.29}, "40": {"diameter_mm": 4.0, "pitch_mm": 1.46},
    "45": {"diameter_mm": 4.5, "pitch_mm": 1.63}, "50": {"diameter_mm": 5.0, "pitch_mm": 1.80},
    "60": {"diameter_mm": 6.0, "pitch_mm": 2.14}, "70": {"diameter_mm": 7.0, "pitch_mm": 2.48},
    "80": {"diameter_mm": 8.0, "pitch_mm": 2.82}, "100": {"diameter_mm": 10.0, "pitch_mm": 3.50},
}
DELTA_PT_SOURCE = ("Bulten AB, DELTA PT: a superior thread-former for plastics, brochure version 250422, p. 4 "
                   "(dimensions) and p. 7 (boss recommendations): https://www.bulten.com/media/b5eby1nc/"
                   "deltapt-version-250422.pdf")
FRICTION_BAND = (0.20, 0.65)
FRICTION_SOURCE = ("Covestro, Snap-Fit Joints for Plastics - A Design Guide, Table 3 (plastic on steel): 0.20 for POM "
                   "and rigid PE to 0.65 for ABS, PTFE aside; PLA and PETG are not listed")
SHEAR_FROM_TENSILE = 0.5             # maximum-shear-stress criterion (Shigley 10th ed., Section 5-4)
AXES = {"upright": "along", "lying": "across"}    # the boss's axis -> the layer direction its hoop stress runs in
LIMITS = (
    "closed forms (cadagent.formulas.screw_boss): torque to clamp through a nut factor from the friction band, even "
    "load sharing over the engaged thread, a frictionless flank for the radial push, a Lame cylinder for the wall",
    "the drive (forming) torque is not computed: measure it on a test boss and tighten to at least 1.2 x it",
    "the hoop stress is the clamp's share only; forming the thread pushes the wall out further, which the maker's hole "
    "and boss proportions keep in check",
    "datasheet strengths are short-term, for 100 % infill bars: a boss of a few perimeters is weaker, and a held clamp "
    "creeps and relaxes",
    "no published pull-out or stripping data for thread-forming screws in printed bosses was found (2026-11-01): a "
    "starting point to test, not a rating",
)


def printed_boss(material: str, size: str, outside_mm: float, engagement_mm: float, torque_nm: float,
                 axis: str = "upright") -> Dict[str, Any]:
    """One DELTA PT screw of ``size`` in a printed boss: :func:`cadagent.formulas.screw_boss` with the filament's
    strengths and the friction band, its inputs and where each number came from, and the limits."""
    if material not in PRINTED:
        raise ValueError(f"material must be one of {sorted(PRINTED)}, not {material!r}")
    if size not in DELTA_PT:
        raise ValueError(f"size must be one of {list(DELTA_PT)} (DELTA PT), not {size!r}")
    if axis not in AXES:
        raise ValueError(f"axis must be 'upright' (built along Z) or 'lying' (axis in the bed plane), not {axis!r}")
    m, screw = PRINTED[material], DELTA_PT[size]
    shear = SHEAR_FROM_TENSILE * m.strength("across") * 1e6
    hoop = m.strength(AXES[axis]) * 1e6
    result = fx.screw_boss(screw["diameter_mm"] * 1e-3, screw["pitch_mm"] * 1e-3, engagement_mm * 1e-3,
                           outside_mm * 1e-3, torque_nm, shear, hoop, *FRICTION_BAND)
    return {**result, "inputs": {"material": material, "size": size, "outside_mm": outside_mm,
                                 "engagement_mm": engagement_mm, "torque_nm": torque_nm, "axis": axis},
            "screw": {**screw, "source": DELTA_PT_SOURCE},
            "material": {"name": m.name, "shear_strength": shear, "hoop_strength": hoop,
                         "shear_sheet": m.strength_sheet("across").label,
                         "hoop_sheet": m.strength_sheet(AXES[axis]).label, "source": m.source, "status": STATUS},
            "friction": {"band": list(FRICTION_BAND), "source": FRICTION_SOURCE},
            "guide": {"hole": fx.BOSS_HOLE, "outside": fx.BOSS_OUTSIDE, "engagement": fx.BOSS_ENGAGEMENT,
                      "tighten_over_drive": fx.TIGHTEN_OVER_DRIVE, "tighten_over_strip": fx.TIGHTEN_OVER_STRIP},
            "limits": list(LIMITS)}
