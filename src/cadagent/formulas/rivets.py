"""Riveted lap joints, one pitch wide: the rivets shear, the holes bear (crush), the sheet tears between the holes, and
the joint's efficiency against the solid sheet.

    from cadagent import formulas as fx
    fx.rivet_shear_force(diameter=3.264e-3, shear_strength=193e6)            # one 5056 rivet, single shear: 1.6 kN
    fx.lap_joint(diameter=3.264e-3, thickness=1.6e-3, pitch=9.525e-3, tensile_strength=214e6,
                 shear_strength=None, bearing_strength=448e6, rivet_shear=689.5)   # a bought rivet's rated shear

Every force is per pitch: the width of sheet one rivet (or one rivet in each row) serves. The equations are the
textbook ones: MIL-HDBK-5J chapter 8 for a rivet's shear and a hole's bearing strength, and the lecture notes it is
checked against for the tearing and efficiency (the worked examples are the tests' golden vectors).
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from cadagent.formulas._registry import formula, cite


def _positive(name: str, v: Any, strict: bool = True) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or (v <= 0 if strict else v < 0):
        raise ValueError(f"{name} must be a finite number {'above' if strict else 'of at least'} 0, not {v!r}")
    return float(v)


def _count(name: str, v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ValueError(f"{name} must be a whole number of at least 1, not {v!r}")
    return v


_STATIC = "static load, at the strengths given (ultimate gives the failing load; allowable or reduced values give a working load)"
_LAP = ("a lap joint loaded in shear: the rivets carry no tension, and the eccentric pull of a single lap (bending of the "
        "sheets) is not modelled")


@formula(units={"diameter": "m (the hole, as MIL-HDBK-5J uses for its tables)", "shear_strength": "Pa (the rivet's "
                "Fsu)", "rivets": "count (per pitch)", "planes": "count (1 single shear: a lap; 2 double: a butt strap)"},
         returns="force that shears the rivets, N",
         limits=(_STATIC, _LAP, "a solid rivet's strength from its material; a blind rivet's from its maker's test "
                 "(use that rating instead, as lap_joint's rivet_shear)"),
         source=cite("mil-hdbk-5j", "8.1.2, Table 8.1.2(b): single-shear strength of solid rivets, Fsu times the "
                     "hole's area") + "; " + cite("abbud-riveted-joints", "Section 'Shearing of the rivets'"))
def rivet_shear_force(diameter: float, shear_strength: float, rivets: int = 1, planes: int = 1) -> float:
    """Force that shears ``rivets`` rivets in ``planes`` shear planes each: P = n m tau pi d^2 / 4."""
    d = _positive("diameter", diameter)
    return (_count("rivets", rivets) * _count("planes", planes) * _positive("shear_strength", shear_strength)
            * math.pi * d * d / 4.0)


@formula(units={"diameter": "m (the hole)", "thickness": "m (the sheet)", "bearing_strength": "Pa (the sheet's "
                "Fbru at the joint's e/D, or a permissible crushing stress)", "rivets": "count (per pitch)"},
         returns="force at which the rivets crush the holes' sides (bearing), N",
         limits=(_STATIC, "the bearing strength depends on the edge distance: MIL-HDBK-5J tabulates Fbru at e/D 1.5 "
                 "and 2.0, and its bearing allowables need t/D of at least 0.18"),
         source=cite("mil-hdbk-5j", "8.1.2.1, Table 8.1.2.1(a): unit bearing strength, Fbr times d times t") + "; "
                + cite("abbud-riveted-joints", "Section 'Crushing of the plate or rivets'"))
def bearing_force(diameter: float, thickness: float, bearing_strength: float, rivets: int = 1) -> float:
    """Force at which ``rivets`` rivets crush their holes in one sheet: P = n d t sigma_br."""
    return (_count("rivets", rivets) * _positive("diameter", diameter) * _positive("thickness", thickness)
            * _positive("bearing_strength", bearing_strength))


@formula(units={"pitch": "m (centre to centre along the row)", "diameter": "m (the hole)", "thickness": "m",
                "tensile_strength": "Pa (the sheet's)"},
         returns="force that tears the sheet across the row of holes, N per pitch",
         limits=(_STATIC, "pitch must exceed the hole; the net section's stress is taken as uniform (no hole "
                 "stress concentration, which matters under fatigue)"),
         source=cite("abbud-riveted-joints", "Section 'Tearing resistance': Pt = (p - d) t sigma_t"))
def tearing_force(pitch: float, diameter: float, thickness: float, tensile_strength: float) -> float:
    """Force that tears the sheet between two holes: P = (p - d) t sigma_t."""
    p, d = _positive("pitch", pitch), _positive("diameter", diameter)
    if p <= d:
        raise ValueError(f"pitch {pitch!r} must exceed the hole {diameter!r}")
    return (p - d) * _positive("thickness", thickness) * _positive("tensile_strength", tensile_strength)


@formula(units={"pitch": "m", "thickness": "m", "tensile_strength": "Pa"},
         returns="force that breaks the solid sheet, one pitch wide, N",
         limits=(_STATIC,),
         source=cite("abbud-riveted-joints", "Section 'Efficiency of a Riveted Joint': P = p t sigma_t"))
def solid_sheet_force(pitch: float, thickness: float, tensile_strength: float) -> float:
    """Strength of the unriveted sheet one pitch wide: P = p t sigma_t, the base of a joint's efficiency."""
    return _positive("pitch", pitch) * _positive("thickness", thickness) * _positive("tensile_strength", tensile_strength)


@formula(units={"diameter": "m (the hole)", "thickness": "m (the thinner sheet)", "pitch": "m",
                "tensile_strength": "Pa (the sheet's)", "shear_strength": "Pa (the rivet's Fsu; None with rivet_shear)",
                "bearing_strength": "Pa (the sheet's)", "rivets": "count (rivets per pitch: one per row)",
                "planes": "count (shear planes per rivet)", "rivet_shear": "N (one rivet's rated shear, for a bought "
                "blind rivet; None to compute it from shear_strength)"},
         returns="dict: each mode's force per pitch (shear, bearing, tearing), the solid sheet's, the strength (the "
                 "least), the mode that sets it, and the efficiency (strength over the solid sheet)",
         limits=(_STATIC, _LAP, "the tearing is at the first row (later rows carry part of the load only); a riveted "
                 "joint's strength is the least of the modes, as the lecture notes compute it"),
         source=cite("abbud-riveted-joints", "Section 'Efficiency of a Riveted Joint': strength = least of Pt, Ps and Pc") + "; "
                + cite("mil-hdbk-5j", "8.1.2 and 8.1.2.1 for the rivet's shear and the hole's bearing"))
def lap_joint(diameter: float, thickness: float, pitch: float, tensile_strength: float,
              shear_strength: Optional[float], bearing_strength: float, rivets: int = 1, planes: int = 1,
              rivet_shear: Optional[float] = None) -> Dict[str, Any]:
    """A riveted lap joint one pitch wide: the least of shearing the rivets, crushing the holes and tearing the sheet,
    and its efficiency against the solid sheet."""
    n = _count("rivets", rivets)
    if rivet_shear is not None:
        shear = n * _count("planes", planes) * _positive("rivet_shear", rivet_shear)
    elif shear_strength is not None:
        shear = rivet_shear_force(diameter, shear_strength, n, planes)
    else:
        raise ValueError("give shear_strength (the rivet's Fsu) or rivet_shear (one rivet's rated shear, N)")
    modes = {"shear": shear,
             "bearing": bearing_force(diameter, thickness, bearing_strength, n),
             "tearing": tearing_force(pitch, diameter, thickness, tensile_strength)}
    solid = solid_sheet_force(pitch, thickness, tensile_strength)
    mode = min(modes, key=modes.get)
    return {"shear_n": modes["shear"], "bearing_n": modes["bearing"], "tearing_n": modes["tearing"],
            "solid_n": solid, "strength_n": modes[mode], "mode": mode, "efficiency": modes[mode] / solid}
