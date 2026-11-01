"""Torsion bars: torsion constants of round, hollow and rectangular sections, the twist, the stiffness and the peak
shear stress.

SI units: metres, newtons, pascals, radians; torque in N m, stiffness in N m / rad.

Saint-Venant torsion of a straight prismatic bar: linear elastic, isotropic, small twist, ends free to warp, and
the section remote from the ends and from any change of section. The torsion snap of the Covestro guide is
:func:`cadagent.mechanical.compliant.snapfit.torsion_snap`, which works in strain at the guide's limits; these are the general
relations underneath it.
"""
from __future__ import annotations

import math

from cadagent.formulas._registry import cite, formula

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
    return a * b ** 3 * (16.0 / 3.0 - 3.36 * b / a * (1.0 - b ** 4 / (12.0 * a ** 4)))


@formula(units={"torque": "N m", "width": "m", "thickness": "m"},
         returns="peak shear stress, Pa (at the middle of the long sides)",
         limits=(_SV, "solid rectangle"),
         source=cite("roark", "Table 10.1, the solid rectangular section"))
def torsion_shear_stress_rect(torque: float, width: float, thickness: float) -> float:
    """Peak shear stress in a twisted solid rectangle: 3T / (8 a b^2) times Roark's polynomial in b/a."""
    a, b = max(width, thickness) / 2.0, min(width, thickness) / 2.0
    q = b / a
    return 3.0 * torque / (8.0 * a * b * b) * (1.0 + 0.6095 * q + 0.8865 * q ** 2 - 1.8023 * q ** 3 + 0.9100 * q ** 4)


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
