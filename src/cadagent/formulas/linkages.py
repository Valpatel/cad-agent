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
# How near to closing counts as closed, as a fraction of the longest link. Where coupler and rocker line up (a
# change point, such as a parallelogram at 0 or 180 degrees, or a limit of the input's travel) the two assemblies meet,
# and round-off, or lengths like 0.03 that binary cannot hold exactly, can leave the links a few ulps apart.
_CLOSE = 1e-12


def _diagonal_closes(a: float, b: float, c: float, d: float, theta2: float) -> bool:
    """Whether coupler and rocker can span the diagonal from the crank pin to the output pivot, to _CLOSE of the
    longest link: |b - c| <= e <= b + c. The diagonal's x part is written as a cos theta2 - d =
    a - d - 2 a sin^2(theta2 / 2), which keeps its digits near 0 degrees, where a cos theta2 - d would cancel."""
    s = math.sin(0.5 * theta2)
    e = math.hypot(a - d - 2.0 * a * s * s, a * math.sin(theta2))
    tol = _CLOSE * max(a, b, c, d)
    return abs(b - c) - tol <= e <= b + c + tol


@formula(units={"a": "length (input crank)", "b": "length (coupler)", "c": "length (output rocker)",
                "d": "length (ground)"},
         returns="dict: grashof (bool), kind ('grashof', 'non-grashof', 'change-point'), crank_rotates (bool), "
                 "inversion ('crank-rocker', 'double-crank', 'rocker-crank', 'double-rocker', 'triple-rocker' or "
                 "'change-point')",
         limits=(_RIGID,),
         source=cite("norton", "Chapter 2, the Grashof condition (S + L <= P + Q) and its inversions"))
def grashof(a: float, b: float, c: float, d: float) -> Dict[str, object]:
    """Grashof class: with S and L the shortest and longest links, S + L < P + Q lets at least one link turn fully;
    equality is a change-point linkage. The input crank turns fully when it is the shortest link and the linkage is
    Grashof (a crank-rocker, or a double crank when the ground is shortest too).

    ``inversion`` names a Grashof linkage by its shortest link, which is the one that turns fully against its
    neighbours: the input (a crank-rocker), the ground (a double crank), the output (a rocker-crank: the output turns
    fully and the input rocks) or the coupler (a double rocker). Every non-Grashof linkage is a triple rocker."""
    links = sorted((a, b, c, d))
    s_l, p_q = links[0] + links[3], links[1] + links[2]
    if math.isclose(s_l, p_q, rel_tol=1e-12):
        kind = "change-point"
    else:
        kind = "grashof" if s_l < p_q else "non-grashof"
    if kind == "grashof":
        # S + L < P + Q leaves one shortest link: two equal ones (S = P) would need L < Q
        inversion = ("crank-rocker" if links[0] == a else "double-crank" if links[0] == d
                     else "rocker-crank" if links[0] == c else "double-rocker")
    else:
        inversion = "triple-rocker" if kind == "non-grashof" else "change-point"
    # the shortest link turns fully: the input crank does when it is the shortest (crank-rocker) or the ground is
    # (double crank)
    return {"grashof": kind != "non-grashof", "kind": kind,
            "crank_rotates": kind != "non-grashof" and links[0] in (a, d), "inversion": inversion}


@formula(units={"a": "length (input crank)", "b": "length (coupler)", "c": "length (output rocker)",
                "d": "length (ground)"},
         returns="dict: closes (bool: at some input angle), full_turn (bool), folded and stretched (rad, 0..pi, or "
                 "None): |theta2| where coupler and rocker fold or stretch into one line",
         limits=(_RIGID, "the input closes where folded <= |theta2| <= stretched, reading a None folded as 0 and a "
                 "None stretched as pi; with both limits that is two mirror-image ranges, one each side of the ground",
                 f"the same {_CLOSE:g} closing test as fourbar_angles: a linkage that closes at 0 or pi to within it "
                 "has no limit there"),
         source=cite("norton", "Chapter 4, the toggle positions of the four-bar (law of cosines)"))
def fourbar_input_limits(a: float, b: float, c: float, d: float) -> Dict[str, object]:
    """The input angles where a four-bar locks: coupler and rocker fall into one line, so the diagonal e from the crank
    pin to the output pivot is |b - c| (folded) or b + c (stretched). There the transmission angle is 0, both
    assemblies meet, and the input cannot turn further. A limit is None when the input passes that side freely."""
    tol = _CLOSE * max(a, b, c, d)
    near, far = abs(a - d), a + d                    # the diagonal at theta2 = 0 and at pi: its shortest and longest
    fold, stretch = abs(b - c), b + c
    closes = near <= stretch + tol and fold - tol <= far

    def toggle(span: float) -> float:
        # e = span by the law of cosines, in half angles so it keeps its digits near 0 and pi:
        # sin^2(theta2 / 2) = (span^2 - (a - d)^2) / 4ad and cos^2(theta2 / 2) = ((a + d)^2 - span^2) / 4ad
        return 2.0 * math.atan2(math.sqrt(max((span - near) * (span + near), 0.0)),
                                math.sqrt(max((far - span) * (far + span), 0.0)))

    folded = toggle(fold) if closes and near < fold - tol else None
    stretched = toggle(stretch) if closes and far > stretch + tol else None
    return {"closes": closes, "full_turn": closes and folded is None and stretched is None,
            "folded": folded, "stretched": stretched}


@formula(units={"a": "length (input crank)", "b": "length (coupler)", "c": "length (output rocker)",
                "d": "length (ground)", "theta2": "rad (input angle from the ground link)",
                "crossed": "False for the open branch, True for the crossed one"},
         returns="(theta3, theta4) in rad, or None where the links cannot close at this input angle",
         limits=(_RIGID, "the branch must be chosen: open and crossed are the two assemblies at the same input angle",
                 f"a gap under {_CLOSE:g} of the longest link counts as closed, so a change point or a limit of the "
                 "input's travel gives its one position (both branches) instead of None"),
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
        # disc = ((b + c)^2 - e^2)(e^2 - (b - c)^2) / (a c)^2, with e the diagonal. Where the two assemblies meet it is
        # 0, and round-off can leave it just below; if the diagonal says the links close, it is that double root.
        if not _diagonal_closes(a, b, c, d, theta2):
            return None
        disc = 0.0
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
         limits=(_RIGID, "the same for both branches", f"closes under the same {_CLOSE:g} test as fourbar_angles"),
         source=cite("norton", "Chapter 4, the transmission angle of the four-bar (law of cosines)"))
def transmission_angle(a: float, b: float, c: float, d: float, theta2: float) -> Optional[float]:
    """Angle between coupler and rocker: cos mu = (b^2 + c^2 - a^2 - d^2 + 2 a d cos theta2) / (2 b c), folded so
    the result is acute. None when the linkage cannot close."""
    cos_mu = (b * b + c * c - a * a - d * d + 2.0 * a * d * math.cos(theta2)) / (2.0 * b * c)
    if abs(cos_mu) > 1.0:
        # coupler and rocker in line (mu = 0) at a change point or a limit, pushed past 1 by round-off
        if not _diagonal_closes(a, b, c, d, theta2):
            return None
        cos_mu = math.copysign(1.0, cos_mu)
    mu = math.acos(cos_mu)
    return min(mu, math.pi - mu)
