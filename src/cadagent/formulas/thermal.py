"""Heat and air: steady 1-D conduction through a layered wall with surface films, and the operating point of a fan
against a system curve.

SI units: metres, W/(m K), W/(m^2 K), kelvin or degrees C (differences), watts; flow in m^3/s, pressure in Pa.

For plate-fin heatsinks, use :mod:`cadagent.thermal.heatsink` (developing laminar channel flow, fin efficiency, spreading);
its fan curve is the same straight datasheet line as :func:`fan_curve_line`. For convection correlations, fittings
and duct losses beyond these closed forms, Caleb Bell's ``ht`` and ``fluids`` (MIT) are the libraries to use.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from cadagent.formulas._registry import cite, formula

_WALL = ("steady, one-dimensional (a wall much wider than it is thick), constant conductivity, no heat generated "
         "in the wall, perfect contact between layers (no contact resistance)")
_FAN = ("steady flow; the fan curve is the caller's (datasheet points, joined by straight lines); the system loss "
        "is r Q + k Q^2 (laminar plus turbulent terms); fan and system at the same air density")


@formula(units={"thickness": "m", "conductivity": "W/(m K)", "area": "m^2"}, returns="thermal resistance, K/W",
         limits=(_WALL,), source=cite("incropera", "Section 3.1.2 (Thermal Resistance), Eq. (3.6)"))
def wall_resistance(thickness: float, conductivity: float, area: float) -> float:
    """Conduction resistance of a plane layer: R = L / (k A)."""
    return thickness / (conductivity * area)


@formula(units={"coefficient": "W/(m^2 K)", "area": "m^2"}, returns="thermal resistance, K/W",
         limits=("the film coefficient is the caller's (from a correlation or a test)",),
         source=cite("incropera", "Section 3.1.2 (Thermal Resistance), Eq. (3.9)"))
def film_resistance(coefficient: float, area: float) -> float:
    """Convection (film) resistance of a surface: R = 1 / (h A)."""
    return 1.0 / (coefficient * area)


@formula(units={"layers": "[(thickness m, conductivity W/(m K)), ...] from the hot side", "area": "m^2",
                "t_hot": "degC or K", "t_cold": "degC or K",
                "h_hot": "W/(m^2 K), above 0, or None (wall face held at t_hot)",
                "h_cold": "W/(m^2 K), above 0, or None (wall face held at t_cold)"},
         returns="dict: heat_flow (W), flux (W/m^2), resistance (K/W), surfaces (temperatures at each face, hot to "
                 "cold)",
         limits=(_WALL,), source=cite("incropera", "Section 3.1.3 (The Composite Wall)"))
def wall_heat_flow(layers: Sequence[Tuple[float, float]], area: float, t_hot: float, t_cold: float,
                   h_hot: Optional[float] = None, h_cold: Optional[float] = None) -> Dict[str, object]:
    """Heat flow through layers in series, with an optional film on each side: q = (t_hot - t_cold) / sum(R), and the
    temperature at every face (linear within each layer)."""
    if not layers:
        raise ValueError("give at least one (thickness, conductivity) layer")
    for name, h in (("h_hot", h_hot), ("h_cold", h_cold)):
        if h is not None and not h > 0.0:
            raise ValueError(f"{name} must be above 0: h = 0 is an insulated face (no heat flows through it), and None "
                             "holds the face at its temperature")
    rs: List[float] = ([film_resistance(h_hot, area)] if h_hot is not None else []) + \
        [wall_resistance(t, k, area) for t, k in layers] + \
        ([film_resistance(h_cold, area)] if h_cold is not None else [])
    total = sum(rs)
    q = (t_hot - t_cold) / total
    temps, t = [], t_hot
    for i, r in enumerate(rs):
        if i or h_hot is None:
            temps.append(t)
        t -= q * r
    if h_cold is None:
        temps.append(t)
    return {"heat_flow": q, "flux": q / area, "resistance": total, "surfaces": temps}


@formula(units={"dp_shutoff": "Pa (pressure at zero flow)", "q_free": "m^3/s (flow at zero pressure)"},
         returns="fan curve points [(Q m^3/s, dp Pa)]",
         limits=("a straight line between the datasheet end points: real axial fans sag in the middle and may "
                 "stall; use the datasheet's own points when it has them",),
         source=cite("white", "Section 11.5 (Matching Pumps to System Characteristics); the same line as "
                     "cadagent.thermal.heatsink.FanCurve"))
def fan_curve_line(dp_shutoff: float, q_free: float) -> List[Tuple[float, float]]:
    """The straight-line fan curve between shut-off pressure and free-air flow."""
    return [(0.0, dp_shutoff), (q_free, 0.0)]


@formula(units={"dp": "Pa", "q": "m^3/s"}, returns="system coefficient k in dp = k Q^2, Pa s^2/m^6",
         limits=("fully turbulent losses (dp proportional to Q^2), from one measured or computed point",),
         source=cite("white", "Section 11.5 (the system curve)"))
def system_coefficient(dp: float, q: float) -> float:
    """Quadratic system curve through one point: k = dp / Q^2."""
    return dp / (q * q)


@formula(units={"fan_curve": "[(Q m^3/s, dp Pa)] with Q increasing", "k": "Pa s^2/m^6 (quadratic loss)",
                "r": "Pa s/m^3 (linear loss, laminar paths such as filters and fins)"},
         returns="dict: flow (m^3/s), pressure (Pa), intersections (every crossing, low flow first), stable (bool)",
         limits=(_FAN, "beyond the last fan point there is no flow: the curve must reach zero pressure or the system "
                 "must cross it first"),
         source=cite("white", "Section 11.5 (Matching Pumps to System Characteristics)"))
def fan_operating_point(fan_curve: Sequence[Tuple[float, float]], k: float, r: float = 0.0) -> Dict[str, object]:
    """Where the fan curve meets the system curve dp = r Q + k Q^2, solved exactly on each straight segment of the
    fan curve. The operating point is the highest-flow crossing; more than one crossing (a stall dip) is flagged as
    unstable."""
    pts = [(float(q), float(p)) for q, p in fan_curve]
    if len(pts) < 2 or any(q2 <= q1 for (q1, _), (q2, _) in zip(pts, pts[1:])):
        raise ValueError("the fan curve needs at least two points with increasing flow")
    if k < 0 or r < 0 or (k == 0 and r == 0):
        raise ValueError("the system needs a positive loss: k > 0 or r > 0")
    found: List[Tuple[float, float]] = []
    for (q1, p1), (q2, p2) in zip(pts, pts[1:]):
        s = (p2 - p1) / (q2 - q1)                     # fan: p = p1 + s (Q - q1); system: r Q + k Q^2
        qa, qb, qc = k, r - s, -(p1 - s * q1)         # k Q^2 + (r - s) Q - (p1 - s q1) = 0
        if qa == 0.0:
            roots = [-qc / qb] if qb else []
        else:
            disc = qb * qb - 4.0 * qa * qc
            if disc < 0.0:
                continue
            sq = math.sqrt(disc)
            # the numerically stable pair of roots
            t = -0.5 * (qb + math.copysign(sq, qb))
            roots = [t / qa, qc / t] if t else [-qb / (2.0 * qa)]
        for q in roots:
            if q1 - 1e-12 * q2 <= q <= q2 * (1 + 1e-12) and q >= 0.0:
                q = min(max(q, q1), q2)
                if not any(math.isclose(q, f, rel_tol=1e-9, abs_tol=1e-15) for f, _ in found):
                    found.append((q, r * q + k * q * q))
    if not found:
        raise ValueError("the fan and system curves do not cross within the fan curve's points")
    found.sort()
    q, p = found[-1]
    return {"flow": q, "pressure": p, "intersections": found, "stable": len(found) == 1}
