"""Planar four-bar and five-bar linkages: Grashof class, position analysis (coupler and output angles from the input
angle, open and crossed), the transmission angle, and the five-bar's tip, inputs and singularities.

Lengths in any one unit (metres for consistency with the rest of the package); angles in radians, measured
counter-clockwise from the ground link (the line from the input pivot to the output pivot).

Norton's naming: ``a`` the input crank (link 2), ``b`` the coupler (link 3), ``c`` the output rocker (link 4), ``d``
the ground (link 1). A five-bar has two arms, one from each ground pivot, A = (0, 0) and B = (d, 0): crank ``a1`` at A
then distal link ``b1``, crank ``a2`` at B then distal link ``b2``, the two distal links pinned together at the tip P.
Rigid links, ideal pin joints with no clearance, planar motion, position only (no velocity, force or dynamics). For
synthesis and optimisation, pylinkage (MIT) is the open-source tool to reach for; ``cadagent.mechanical.linkages``
sweeps these over an input's travel.
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


# ----------------------------------------------------------------------------- five-bars

_FIVEBAR_UNITS = {"a1": "length (crank at A = (0, 0))", "b1": "length (distal link from crank a1's tip)",
                  "a2": "length (crank at B = (d, 0))", "b2": "length (distal link from crank a2's tip)",
                  "d": "length (ground, A to B)"}
_FIVEBAR_RIGID = (_RIGID + "; a crank of length 0 pins its distal link to the ground pivot, which makes the five-bar a "
                  "four-bar (a1 = a, b1 = b, a2 = 0, b2 = c gives fourbar_angles' linkage, open as mode +1)")


def _fivebar_lengths(a1: float, b1: float, a2: float, b2: float, d: float) -> float:
    """The closing tolerance for these links, after checking they are lengths a five-bar can have."""
    for name, v, least in (("a1", a1, 0.0), ("a2", a2, 0.0), ("d", d, 0.0)):
        if not v >= least:
            raise ValueError(f"{name} = {v}: a crank or ground length must be 0 or more")
    for name, v in (("b1", b1), ("b2", b2)):
        if not v > 0:
            raise ValueError(f"{name} = {v}: a distal link must be longer than 0")
    return _CLOSE * max(a1, b1, a2, b2, d)


def _apex(p: Tuple[float, float], q: Tuple[float, float], rp: float, rq: float, side: int,
          tol: float) -> Optional[Tuple[float, float]]:
    """The point at rp from p and rq from q on the ``side`` (+1 left, -1 right) of the line from p to q, or None when
    the two circles miss by more than ``tol``. The height above the line comes from Heron's formula in its factored form
    (16 area^2 = (rp + rq + s)(rp + rq - s)(s + rp - rq)(s - rp + rq)), which keeps its digits where the circles
    nearly touch."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    s = math.hypot(dx, dy)
    if s <= tol:
        return None                                  # concentric: a whole circle of points, or none
    if s > rp + rq + tol or s < abs(rp - rq) - tol:
        return None
    q16 = (rp + rq + s) * (rp + rq - s) * (s + rp - rq) * (s - rp + rq)
    h = math.sqrt(max(q16, 0.0)) / (2.0 * s)
    along = (s * s + (rp - rq) * (rp + rq)) / (2.0 * s)
    return (p[0] + (along * dx - side * h * dy) / s, p[1] + (along * dy + side * h * dx) / s)


def _knees(a1: float, a2: float, d: float, theta1: float, theta2: float):
    return (a1 * math.cos(theta1), a1 * math.sin(theta1)), (d + a2 * math.cos(theta2), a2 * math.sin(theta2))


@formula(units={**_FIVEBAR_UNITS, "theta1": "rad (crank a1 from the ground direction A to B)",
                "theta2": "rad (crank a2 from the same direction)",
                "mode": "+1 or -1: the assembly, the tip left (+1) or right (-1) of the line from crank a1's tip to "
                        "crank a2's tip"},
         returns="(x, y) of the tip P in the frame A = (0, 0), B = (d, 0), or None where the distal links cannot "
                 "reach each other",
         limits=(_FIVEBAR_RIGID, "the assembly must be chosen: the two modes are the two ways the distal links fit at "
                 "the same inputs, and they meet where the distal links fall into one line",
                 f"a gap under {_CLOSE:g} of the longest link counts as closed; knees that coincide give None"),
         source=cite("goncalves", "Section 2.2, Eqs. (8)-(15): the direct kinematics of the 5R mechanism, two "
                     "solutions, after Liu, Wang and Zheng (2006)"))
def fivebar_point(a1: float, b1: float, a2: float, b2: float, d: float, theta1: float, theta2: float,
                  mode: int = 1) -> Optional[Tuple[float, float]]:
    """Where the tip of a five-bar is for two crank angles: the intersection of a circle of radius b1 about crank a1's
    tip and one of radius b2 about crank a2's tip, on the side ``mode`` picks."""
    tol = _fivebar_lengths(a1, b1, a2, b2, d)
    if mode not in (1, -1):
        raise ValueError(f"mode = {mode!r}: +1 or -1")
    c1, c2 = _knees(a1, a2, d, theta1, theta2)
    return _apex(c1, c2, b1, b2, mode, tol)


@formula(units={**_FIVEBAR_UNITS, "x": "length (tip, along A to B)", "y": "length (tip, square to it)",
                "working": "(w1, w2), each +1 or -1: the working mode of each arm, +1 where its distal link turns "
                           "counter-clockwise from its crank, -1 clockwise"},
         returns="(theta1, theta2) in rad, or None where the tip is out of either arm's reach",
         limits=(_RIGID, "both cranks longer than 0 (an arm without a crank cannot move its tip)",
                 "the working mode must be chosen: each arm reaches a point two ways, so there are four solutions, "
                 "and an arm's two meet where its crank and distal link fall into one line (the edge of its reach)",
                 f"a gap under {_CLOSE:g} of the longest link counts as reached"),
         source=cite("goncalves", "Section 2.1, Eqs. (3)-(7): the inverse kinematics of the 5R mechanism, four "
                     "solutions, after Liu, Wang and Zheng (2006)"))
def fivebar_inputs(a1: float, b1: float, a2: float, b2: float, d: float, x: float, y: float,
                   working: Tuple[int, int] = (-1, 1)) -> Optional[Tuple[float, float]]:
    """The crank angles that put a five-bar's tip at (x, y). Each arm's knee is where a circle of radius a_i about its
    ground pivot meets one of radius b_i about the tip. The default (-1, +1) is the usual one with the tip above the
    ground link: both knees outside the arms."""
    tol = _fivebar_lengths(a1, b1, a2, b2, d)
    if not (a1 > 0 and a2 > 0):
        raise ValueError("both cranks must be longer than 0 to place the tip")
    if len(working) != 2 or any(w not in (1, -1) for w in working):
        raise ValueError(f"working = {working!r}: two signs, each +1 or -1")
    out = []
    for pivot, a, b, w in (((0.0, 0.0), a1, b1, working[0]), ((d, 0.0), a2, b2, working[1])):
        # cross(knee - pivot, tip - knee) = -cross(tip - pivot, knee - pivot): the knee lies on the side -w of the
        # line from the pivot to the tip
        knee = _apex(pivot, (x, y), a, b, -w, tol)
        if knee is None:
            return None
        out.append(math.atan2(knee[1] - pivot[1], knee[0] - pivot[0]))
    return out[0], out[1]


@formula(units={**_FIVEBAR_UNITS, "theta1": "rad (crank a1)", "theta2": "rad (crank a2)",
                "mode": "+1 or -1: the assembly, as in fivebar_point"},
         returns="dict: tip (x, y); direct (the direct-kinematics Jacobian's determinant over b1 b2, -1..1: 0 where "
                 "the distal links fall into one line, its sign the assembly); inverse (each arm's determinant over "
                 "a_i b_i, -1..1: 0 where crank and distal link fall into one line, its sign the working mode; None "
                 "for an arm without a crank); transmission (rad, 0..pi/2, the angle between the distal links folded "
                 "to acute); or None where the links cannot close",
         limits=(_FIVEBAR_RIGID, "direct = 0 is a parallel (type II) singularity: the two assemblies meet, the cranks "
                 "cannot hold the tip, and it is where a crank-driven linkage locks",
                 "inverse = 0 is a serial (type I) singularity: the tip is at the edge of that arm's reach, and an "
                 "arm's two working modes meet there",
                 "first order only: the determinants say where a singularity is and how near, not a force or a speed"),
         source=cite("gosselin", "the formula relating a closed loop's output and input velocities through two "
                     "Jacobians, and its three kinds of singularity"))
def fivebar_jacobians(a1: float, b1: float, a2: float, b2: float, d: float, theta1: float, theta2: float,
                      mode: int = 1) -> Optional[Dict[str, object]]:
    """How near a five-bar is to locking or to the edge of its reach. Its loop closes when |P - C_i| = b_i for both
    arms; differentiated, A dP = B dtheta, with rows (P - C_i) of A and B_ii = cross(C_i - pivot_i, P - C_i) (the
    letters are ours). det A = cross(C2 - C1, P - C1), so its sign is the assembly; each B_ii's sign is that arm's
    working mode."""
    tip = fivebar_point(a1, b1, a2, b2, d, theta1, theta2, mode)
    if tip is None:
        return None
    c1, c2 = _knees(a1, a2, d, theta1, theta2)

    def cross(u, v):
        return u[0] * v[1] - u[1] * v[0]

    u, v = (tip[0] - c1[0], tip[1] - c1[1]), (tip[0] - c2[0], tip[1] - c2[1])
    # cross(C2 - C1, P - C1) = cross(P - C1, P - C2) = b1 b2 sin(angle between the distal links)
    det = cross(u, v)
    direct = max(-1.0, min(1.0, det / (b1 * b2)))
    # the angle between the distal links folded to acute, from atan2, which keeps its digits near 0 and 90 degrees
    transmission = math.atan2(abs(det), abs(u[0] * v[0] + u[1] * v[1]))
    inverse = []
    for pivot, knee, a, b in (((0.0, 0.0), c1, a1, b1), ((d, 0.0), c2, a2, b2)):
        if a == 0:
            inverse.append(None)
            continue
        v = cross((knee[0] - pivot[0], knee[1] - pivot[1]), (tip[0] - knee[0], tip[1] - knee[1])) / (a * b)
        inverse.append(max(-1.0, min(1.0, v)))
    return {"tip": tip, "direct": direct, "inverse": (inverse[0], inverse[1]), "transmission": transmission}
