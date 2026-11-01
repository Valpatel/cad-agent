"""Torsion bars: torsion constants of round, hollow and rectangular sections, the twist, the stiffness and the peak
shear stress.

SI units: metres, newtons, pascals, radians; torque in N m, stiffness in N m / rad.

Saint-Venant torsion of a straight prismatic bar: linear elastic, isotropic, small twist, ends free to warp, and
the section remote from the ends and from any change of section. The torsion snap of the Covestro guide is
:func:`cadagent.mechanical.compliant.snapfit.torsion_snap`, which works in strain at the guide's limits for a round
bar; these are the general relations underneath it. :func:`torsion_snap_bar` is the rectangular bar a printed torsion
snap usually has, twisted through a given angle: its shear strain against the guide's allowable, its torque and the
force at the lever, as :func:`cadagent.formulas.snap_arm` is for a cantilever.
"""
from __future__ import annotations

import math
from typing import Any, Dict

from cadagent.formulas._registry import cite, formula
from cadagent.mechanical.compliant import snapfit

# torsion_snap_bar flags a twist as large when the trapeze effect adds more than this share to the torque
SMALL_TWIST_TRAPEZE = 0.1
_SV = "Saint-Venant torsion: linear elastic, isotropic, small twist, ends free to warp, away from ends and steps"


@formula(units={"modulus": "Pa", "poisson": "dimensionless"}, returns="shear modulus G, Pa",
         limits=("isotropic linear elastic material only: a printed part is not isotropic",),
         source=cite("roark", "Section 2.2 (strain and the stress-strain relations: G = E / 2(1 + nu))"))
def shear_modulus(modulus: float, poisson: float) -> float:
    """Shear modulus of an isotropic material: G = E / (2 (1 + nu))."""
    return modulus / (2.0 * (1.0 + poisson))


@formula(units={"outer_radius": "m", "inner_radius": "m (0 for a solid bar)"}, returns="torsion constant K, m^4",
         limits=(_SV, "circular or concentric hollow circular section (K equals the polar moment J)"),
         source=cite("roark", "Table 10.1, the solid circular and the hollow concentric circular sections"))
def torsion_constant_round(outer_radius: float, inner_radius: float = 0.0) -> float:
    """Torsion constant of a solid or hollow round bar: K = J = pi (ro^4 - ri^4) / 2."""
    if not 0.0 <= inner_radius < outer_radius:
        raise ValueError("need 0 <= inner_radius < outer_radius")
    return math.pi * (outer_radius ** 4 - inner_radius ** 4) / 2.0


@formula(units={"width": "m", "thickness": "m"}, returns="torsion constant K, m^4",
         limits=(_SV, "solid rectangle; within 0.5 % of the exact series at any aspect ratio (worst 0.49 % low, at "
                       "1.145; tested)"),
         source=cite("roark", "Table 10.1, the solid rectangular section (a and b are half the sides)"))
def torsion_constant_rect(width: float, thickness: float) -> float:
    """Torsion constant of a solid rectangle: K = a b^3 [16/3 - 3.36 (b/a)(1 - b^4 / 12 a^4)], a and b half the long
    and short sides."""
    a, b = max(width, thickness) / 2.0, min(width, thickness) / 2.0
    # products, not powers: pow() differs in the last bit between engines, and the browser port must agree exactly
    b3, a4 = b * b * b, a * a * a * a
    return a * b3 * (16.0 / 3.0 - 3.36 * b / a * (1.0 - b3 * b / (12.0 * a4)))


@formula(units={"torque": "N m", "width": "m", "thickness": "m"},
         returns="peak shear stress, Pa (at the middle of the long sides)",
         limits=(_SV, "solid rectangle"),
         source=cite("roark", "Table 10.1, the solid rectangular section"))
def torsion_shear_stress_rect(torque: float, width: float, thickness: float) -> float:
    """Peak shear stress in a twisted solid rectangle: 3T / (8 a b^2) times Roark's polynomial in b/a."""
    a, b = max(width, thickness) / 2.0, min(width, thickness) / 2.0
    q = b / a
    q2 = q * q                                     # products, not powers, as in torsion_constant_rect
    return 3.0 * torque / (8.0 * a * b * b) * (1.0 + 0.6095 * q + 0.8865 * q2 - 1.8023 * q2 * q + 0.9100 * q2 * q2)


@formula(units={"torque": "N m", "outer_radius": "m", "inner_radius": "m (0 for a solid bar)"},
         returns="peak shear stress, Pa (at the outer surface)", limits=(_SV, "circular or hollow circular section"),
         source=cite("roark", "Table 10.1, the solid circular and the hollow concentric circular sections "
                     "(tau = T r / J)"))
def torsion_shear_stress_round(torque: float, outer_radius: float, inner_radius: float = 0.0) -> float:
    """Peak shear stress in a twisted round bar: tau = T ro / J."""
    return torque * outer_radius / torsion_constant_round(outer_radius, inner_radius)


@formula(units={"torque": "N m", "length": "m", "shear_modulus": "Pa", "constant": "m^4 (torsion constant K)"},
         returns="angle of twist, rad", limits=(_SV, "constant section along the length"),
         source=cite("roark", "Section 10.1 and Table 10.1 (theta = T L / K G)"))
def torsion_bar_twist(torque: float, length: float, shear_modulus: float, constant: float) -> float:
    """Angle of twist of a uniform bar: theta = T L / (K G)."""
    return torque * length / (constant * shear_modulus)


@formula(units={"length": "m", "shear_modulus": "Pa", "constant": "m^4 (torsion constant K)"},
         returns="torsional stiffness, N m / rad", limits=(_SV, "constant section along the length"),
         source=cite("roark", "Section 10.1 and Table 10.1 (T / theta = K G / L)"))
def torsion_bar_stiffness(length: float, shear_modulus: float, constant: float) -> float:
    """Torsional stiffness of a uniform bar: T / theta = K G / L."""
    return constant * shear_modulus / length


@formula(units={"twist": "rad", "length": "m", "width": "m", "thickness": "m"},
         returns="peak shear strain, dimensionless (at the middle of the long sides)",
         limits=(_SV, "solid rectangle; the strain follows from the twist and the section alone, whatever the modulus"),
         source=cite("roark", "Table 10.1, the solid rectangular section (gamma = tau / G, with theta = T L / K G)"))
def torsion_shear_strain_rect(twist: float, length: float, width: float, thickness: float) -> float:
    """Peak shear strain in a solid rectangular bar twisted through ``twist`` over ``length``: gamma = tau / G with
    T = K G theta / L, so gamma = theta K (tau / T) / L, which the section alone sets (for a thin strip, theta t / L)."""
    return twist * torsion_constant_rect(width, thickness) * torsion_shear_stress_rect(1.0, width, thickness) / length


def _positive(**values: float) -> None:
    for name, v in values.items():
        if not (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0):
            raise ValueError(f"{name} must be a finite number above 0, not {v!r}")


@formula(units={"length": "m (of each bar)", "width": "m", "thickness": "m", "twist": "rad (at the lever)",
                "modulus": "Pa (tensile; G = E / 2(1 + nu))", "allowable_strain": "dimensionless (the snap-fit "
                "tensile allowable, a fraction)", "lever": "m (from the bar's axis to where the force is applied)",
                "bars": "1 (the lever at the free end of one bar) or 2 (a rocker between two bars, Fig. 21)",
                "poisson": "dimensionless"},
         returns="dict: shear_strain, allowable_shear_strain, ratio, passes, shear_modulus (Pa), stiffness (N m/rad, "
                 "all bars), torque (N m), force (N at the lever), travel (m at the lever), permissible_twist (rad), "
                 "and for large twist: trapeze_ratio, edge_axial_strain and small_twist",
         limits=(_SV, "the guide's allowable shear strain (1 + nu) eps: the maximum-shear-stress criterion, in strain",
                 "small twist: twisted far, a wide thin bar's edges stretch along it (the trapeze effect). Its torque "
                 "gains E t b^5 (theta / L)^3 / 360 and its edges an axial strain (theta / L)^2 b^2 / 12, which the "
                 "torque, the force and the shear check leave out; trapeze_ratio is that torque over the Saint-Venant "
                 "torque, and small_twist is false above 0.1",
                 "isotropic G = E / 2(1 + nu) from the tensile modulus: a printed bar is not isotropic, and the secant "
                 "modulus at the design strain is lower, so the force is an upper bound",
                 "a pass has no extra margin: the strain is within the allowable, nothing more"),
         source=cite("covestro", "Section C (torsion snap-fits: gamma_pm = (1 + nu) eps_pm, the lever force from the "
                     "bars' torque), with the rectangular section of Roark 8th ed., Table 10.1"))
def torsion_snap_bar(length: float, width: float, thickness: float, twist: float, modulus: float,
                     allowable_strain: float, lever: float, bars: int = 1,
                     poisson: float = snapfit.POISSON_PLASTICS) -> Dict[str, Any]:
    """A rectangular torsion bar twisted through ``twist`` by a lever: the peak shear strain against the guide's
    allowable (1 + nu) eps, the torque and the force at the lever, and the twist the allowable permits. Two bars (a
    rocker between two supports) take the same twist and strain and double the torque."""
    _positive(length=length, width=width, thickness=thickness, modulus=modulus, allowable_strain=allowable_strain,
              lever=lever)
    if not (isinstance(twist, (int, float)) and not isinstance(twist, bool) and math.isfinite(twist) and twist >= 0):
        raise ValueError(f"twist must be a finite angle of 0 or more, not {twist!r}")
    if bars not in (1, 2) or isinstance(bars, bool):
        raise ValueError(f"bars must be 1 or 2, not {bars!r}")
    if not (isinstance(poisson, (int, float)) and not isinstance(poisson, bool) and -1.0 < poisson < 0.5):
        raise ValueError(f"poisson must be between -1 and 0.5, not {poisson!r}")
    per_radian = torsion_shear_strain_rect(1.0, length, width, thickness)
    strain = per_radian * twist
    allowable = snapfit.torsion_allowable_shear(allowable_strain, poisson)
    g = shear_modulus(modulus, poisson)
    stiffness = bars * torsion_bar_stiffness(length, g, torsion_constant_rect(width, thickness))
    torque = stiffness * twist
    # The trapeze (Buckley) effect: twisted, the fibres off the axis run as helices and stretch, and with no net
    # axial force the edges are in tension, eps(y) = (theta')^2 (y^2 - b^2 / 12) / 2 across the long side b. Their
    # pull, leaning at y theta', adds a torque integral of E eps y^2 theta' t dy = E t b^5 theta'^3 / 360 (derived in
    # tests/test_torsion_snap_boss.py). A thin-strip result, used as a flag for when the closed form stops holding.
    long_side, short_side, rate = max(width, thickness), min(width, thickness), twist / length
    b2 = long_side * long_side
    trapeze = modulus * short_side * b2 * b2 * long_side * rate * rate / (360.0 * torsion_constant_rect(width, thickness) * g)
    return {"shear_strain": strain, "allowable_shear_strain": allowable, "ratio": strain / allowable,
            "passes": strain <= allowable, "shear_modulus": g, "stiffness": stiffness, "torque": torque,
            "force": torque / lever, "travel": lever * math.sin(twist), "permissible_twist": allowable / per_radian,
            "trapeze_ratio": trapeze, "edge_axial_strain": rate * rate * long_side * long_side / 12.0,
            "small_twist": trapeze <= SMALL_TWIST_TRAPEZE}
