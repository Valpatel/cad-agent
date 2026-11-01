"""Helical compression springs of round wire: index, rate, curvature factor and shear stress.

SI units: metres, newtons, pascals; rate in N/m.

Static, linear elastic, round wire, coils close enough to treat each as a ring in torsion (pitch angle under about
12 degrees), the active coil count given by the caller (it depends on the end type: plain, squared, ground), and no
buckling, surge or set. Shigley recommends a spring index between 4 and 12; outside it the factors lose accuracy and
the spring is hard to make. The rate is only linear between about 15 % and 85 % of the travel to solid.
"""
from __future__ import annotations

import math

from cadagent.formulas._registry import cite, formula

_SPRING = ("round wire, static load, coils treated as rings in torsion (small pitch angle); active coils from the "
           "end type; no buckling, surge or set")


@formula(units={"mean_diameter": "m", "wire_diameter": "m"}, returns="spring index C, dimensionless",
         limits=("Shigley recommends 4 <= C <= 12",),
         source=cite("shigley", "Section 10-2 (Stresses in Helical Springs), Eq. (10-3)"))
def spring_index(mean_diameter: float, wire_diameter: float) -> float:
    """Spring index C = D / d (mean coil diameter over wire diameter)."""
    return mean_diameter / wire_diameter


@formula(units={"wire_diameter": "m", "mean_diameter": "m", "active_coils": "count", "shear_modulus": "Pa"},
         returns="spring rate k, N/m", limits=(_SPRING, "linear between about 15 % and 85 % of the travel to solid"),
         source=cite("shigley", "Section 10-4 (Deflection of Helical Springs), Eq. (10-9)"))
def spring_rate(wire_diameter: float, mean_diameter: float, active_coils: float, shear_modulus: float) -> float:
    """Rate of a helical compression spring: k = G d^4 / (8 D^3 Na)."""
    return shear_modulus * wire_diameter ** 4 / (8.0 * mean_diameter ** 3 * active_coils)


@formula(units={"index": "C = D / d"}, returns="Bergstrasser factor K_B, dimensionless",
         limits=("round wire; within 1.5 % of the Wahl factor for 4 <= C <= 12 (tested)",),
         source=cite("shigley", "Section 10-3 (The Curvature Effect), Eq. (10-5)"))
def bergstrasser_factor(index: float) -> float:
    """Stress factor for direct shear and coil curvature together: K_B = (4C + 2) / (4C - 3)."""
    return (4.0 * index + 2.0) / (4.0 * index - 3.0)


@formula(units={"force": "N", "wire_diameter": "m", "mean_diameter": "m"},
         returns="peak shear stress at the inside of the coil, Pa", limits=(_SPRING,),
         source=cite("shigley", "Sections 10-2 and 10-3, Eq. (10-7)"))
def spring_shear_stress(force: float, wire_diameter: float, mean_diameter: float) -> float:
    """Peak wire shear stress: tau = K_B 8 F D / (pi d^3), with the Bergstrasser factor for curvature."""
    kb = bergstrasser_factor(spring_index(mean_diameter, wire_diameter))
    return kb * 8.0 * force * mean_diameter / (math.pi * wire_diameter ** 3)
