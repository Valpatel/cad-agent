"""Planar four-bar linkages: Grashof class, position analysis (coupler and output angles from the input angle, open
and crossed), and the transmission angle.

Lengths in any one unit (metres for consistency with the rest of the package); angles in radians, measured
counter-clockwise from the ground link (the line from the input pivot to the output pivot).

Norton's naming: ``a`` the input crank (link 2), ``b`` the coupler (link 3), ``c`` the output rocker (link 4), ``d``
the ground (link 1). Rigid links, ideal pin joints with no clearance, planar motion, position only (no velocity, force
or dynamics). For synthesis and optimisation, pylinkage (MIT) is the open-source tool to reach for.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from cadagent.formulas._registry import cite, formula

_RIGID = "rigid links, ideal pin joints without clearance, planar, position only"


@formula(units={"a": "length (input crank)", "b": "length (coupler)", "c": "length (output rocker)",
                "d": "length (ground)"},
         returns="dict: grashof (bool), kind ('grashof', 'non-grashof', 'change-point'), crank_rotates (bool)",
         limits=(_RIGID,),
         source=cite("norton", "Chapter 2, the Grashof condition (S + L <= P + Q)"))
def grashof(a: float, b: float, c: float, d: float) -> Dict[str, object]:
    """Grashof class: with S and L the shortest and longest links, S + L < P + Q lets at least one link turn fully;
    equality is a change-point linkage. The input crank turns fully when it is the shortest link and the linkage is
    Grashof (a crank-rocker, or a double crank when the ground is shortest too)."""
    links = sorted((a, b, c, d))
    s_l, p_q = links[0] + links[3], links[1] + links[2]
    if math.isclose(s_l, p_q, rel_tol=1e-12):
        kind = "change-point"
    else:
        kind = "grashof" if s_l < p_q else "non-grashof"
    # the shortest link turns fully: the input crank does when it is the shortest (crank-rocker) or the ground is
    # (double crank)
    return {"grashof": kind != "non-grashof", "kind": kind,
            "crank_rotates": kind != "non-grashof" and links[0] in (a, d)}


@formula(units={"a": "length (input crank)", "b": "length (coupler)", "c": "length (output rocker)",
                "d": "length (ground)", "theta2": "rad (input angle from the ground link)",
                "crossed": "False for the open branch, True for the crossed one"},
         returns="(theta3, theta4) in rad, or None where the links cannot close at this input angle",
         limits=(_RIGID, "the branch must be chosen: open and crossed are the two assemblies at the same input angle"),
         source=cite("norton", "Chapter 4 (position analysis), the algebraic four-bar solution with Freudenstein's "
                     "K1 to K3; ") + "after " + cite("freudenstein", "the displacement equation"))
def fourbar_angles(a: float, b: float, c: float, d: float, theta2: float,
                   crossed: bool = False) -> Optional[Tuple[float, float]]:
    """Coupler and output angles of a four-bar from its input angle. theta4 is the root of Freudenstein's equation
    K1 cos theta4 - K2 cos theta2 + K3 = cos(theta2 - theta4); theta3 then follows from the loop closure."""
    k1, k2, k3 = d / a, d / c, (a * a - b * b + c * c + d * d) / (2.0 * a * c)
    cos2, sin2 = math.cos(theta2), math.sin(theta2)
    # A = (1 - K2) cos theta2 + K3 - K1, written so it cancels exactly: a kite (a = b, c = d) has A = 0 at every input
    # angle, and the round-off of the textbook form there turns the discriminant negative near theta2 = pi.
    A = (c - d) / c * cos2 + ((a - b) * (a + b) + (c - d) ** 2) / (2.0 * a * c)
    B = -2.0 * sin2
    C = k1 - (k2 + 1.0) * cos2 + k3
    disc = B * B - 4.0 * A * C
    if disc < 0.0:
        return None
    root = math.sqrt(disc)
    # tan(theta4 / 2) = num / 2A = 2C / conj, since num * conj = 4AC. Take the larger of num and conj, so that A = 0
    # (a kite) does not leave 0 / 0; when both are 0 (B = 0, a double root), A = 0 puts the root at infinity, theta4 = pi.
    num = -B + root if crossed else -B - root
    conj = -B - root if crossed else -B + root
    if abs(num) > abs(conj) or (abs(num) == abs(conj) and abs(A) >= abs(C)):
        theta4 = 2.0 * math.atan2(num, 2.0 * A)
    else:
        theta4 = 2.0 * math.atan2(2.0 * C, conj)
    theta4 = math.atan2(math.sin(theta4), math.cos(theta4))
    # b e^{i theta3} = d + c e^{i theta4} - a e^{i theta2}
    theta3 = math.atan2(c * math.sin(theta4) - a * sin2, d + c * math.cos(theta4) - a * cos2)
    return theta3, theta4


@formula(units={"a": "length (input crank)", "b": "length (coupler)", "c": "length (output rocker)",
                "d": "length (ground)", "theta2": "rad (input angle)"},
         returns="transmission angle, rad, folded to 0..pi/2 (pi/2 is ideal; below about 40 degrees the linkage binds)",
         limits=(_RIGID, "the same for both branches"),
         source=cite("norton", "Chapter 4, the transmission angle of the four-bar (law of cosines)"))
def transmission_angle(a: float, b: float, c: float, d: float, theta2: float) -> Optional[float]:
    """Angle between coupler and rocker: cos mu = (b^2 + c^2 - a^2 - d^2 + 2 a d cos theta2) / (2 b c), folded so
    the result is acute. None when the linkage cannot close."""
    cos_mu = (b * b + c * c - a * a - d * d + 2.0 * a * d * math.cos(theta2)) / (2.0 * b * c)
    if abs(cos_mu) > 1.0:
        return None
    mu = math.acos(cos_mu)
    return min(mu, math.pi - mu)
