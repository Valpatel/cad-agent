"""Fillet welds under static load: the throat, a weld group treated as a line, and the strength the AISC specification
allows the weld metal and the base metal.

    from cadagent import formulas as fx
    group = fx.weld_line_box(width=50.8e-3, depth=50.8e-3)                 # a 2 in square tube welded all round
    s = fx.weld_group_stress(group, leg=3e-3, shear_y=1500, moment_x=400)  # throat stress at the worst corner, Pa
    fx.fillet_weld_check(s["stress"], leg=3e-3, electrode_strength=483e6, thickness=3.2e-3,
                         yield_strength=315e6, tensile_strength=400e6, method="asd")

The group lies in the x-y plane with its centroid at the origin, and z runs along the welded member. Every load acts
at the centroid: ``shear_x`` and ``shear_y`` in the plane, ``axial`` along z, ``moment_x`` and ``moment_y`` bending
about x and y, ``torque`` twisting about z. The line method (Shigley, Chapter 9) gives each point of the weld a force
per unit length from each load, adds them as vectors, and puts the whole resultant on the throat as shear, whatever its
direction. The strengths are those of ANSI/AISC 360-16: Section J2.4 and Table J2.5 for the weld metal, Section J4.2
for the base metal beside it.

What this does not cover, and no closed form here can: fatigue (a welded joint under repeated load fails far below
these static strengths), the quality of the weld (fusion, penetration, porosity, undercut, the actual leg), softening
of the heat-affected zone, residual stress and distortion, and burn-through of a thin wall. The strengths assume a weld
made to a qualified procedure with a filler metal that matches the base metal. A calculation that passes does not show
that a weld is sound: a hobbyist's weld needs a break test of a sample, and inspection.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

from cadagent.formulas._registry import cite, formula

THROAT_OVER_LEG = math.sqrt(0.5)      # equal legs at a right angle: the throat is the leg times cos 45 deg

# ANSI/AISC 360-16. Table J2.5, fillet welds, shear on the effective throat: Fnw = 0.60 FEXX, phi 0.75, Omega 2.00.
WELD_METAL = {"stress_over_fexx": 0.60, "phi": 0.75, "omega": 2.00}
# Section J4.2, elements in shear: yielding 0.60 Fy on the gross area (Eq. J4-3), rupture 0.60 Fu on the net area
# (Eq. J4-4). A weld removes no metal, so both areas are the thickness times the length.
BASE_YIELDING = {"stress_over_strength": 0.60, "phi": 1.00, "omega": 1.50}
BASE_RUPTURE = {"stress_over_strength": 0.60, "phi": 0.75, "omega": 2.00}
METHODS = {"lrfd": "factored loads against phi times the nominal strength (load and resistance factor design)",
           "asd": "service loads against the nominal strength over Omega (allowable strength design)"}
# Table J2.4, inch column converted exactly: the thinner part joined up to (m), and the least leg (m): 1/8, 3/16,
# 1/4 and 5/16 in for parts to 1/4, 1/2, 3/4 in and over. The table's SI column (3, 5, 6, 8 mm at 6, 13, 19 mm) rounds
# these, and its rounding contradicts itself on inch stock: a 1/4 in part would need 5 mm and be allowed 4.35 mm.
_IN = 0.0254
MINIMUM_LEG = ((_IN / 4, _IN / 8), (_IN / 2, 3 * _IN / 16), (3 * _IN / 4, _IN / 4), (math.inf, 5 * _IN / 16))
EDGE_FULL_THICKNESS_BELOW = _IN / 4   # Section J2.2b(b): along an edge thinner than this the leg may equal the edge
EDGE_MARGIN = _IN / 16                # and at or above it the leg stops this far short of the edge
PATTERNS = ("parallel", "box", "circle")
_CIRCLE_SAMPLES = 720

_STATIC = ("static load only: no fatigue, where a welded joint fails far below its static strength and the toe and "
           "root are stress raisers")
_SOUND = ("a sound weld made to a qualified procedure: full fusion at the root, the leg as drawn, no porosity, crack "
          "or undercut. A calculation does not show that; a hobbyist's weld needs a break test of a sample")
_EQUAL_LEG = "equal legs between faces at a right angle; a concave or unequal weld has a smaller throat than this"
_LINE = ("the weld as a line of no width at the joint line, linear elastic: the throat's own width and the legs' "
         "offset from the line are left out, and so is the reserve an eccentric group has past first yield (the "
         "instantaneous-centre method)")
_RIGID = ("the member is welded to a plate or a part stiff enough to load the whole weld: on the flexible face of "
          "another tube the load crowds to the corners and only part of the length works (AISC 360-16 Section K5 "
          "gives effective lengths), so the full perimeter used here is unconservative there")
_EVEN_SHEAR = ("a shear force is spread evenly over the whole length, as Shigley does, which leans on the weld's "
               "ductility: the elastic peak in the welds that run along the force is higher (about twice, on a square "
               "or round tube), so a short stub loaded mostly in shear is under-read")
_AS_SHEAR = ("the whole resultant is carried as shear on the throat whatever its direction, which is conservative; "
             "the directional strength increase of AISC 360-16 J2.4(b) is not used (tests found it unsafe on welds to "
             "the ends of rectangular tubes)")
_NOT_HAZ = ("heat-affected-zone softening (cold-worked or heat-treated base metal, and any aluminium), residual "
            "stress and burn-through of a thin wall are not covered")
_MATCHING = ("structural steel with a filler metal no more than one strength level above matching (AISC 360-16 Table "
             "J2.5); FEXX is the electrode's classification strength (E70: 70 ksi, 483 MPa)")


def _positive(name: str, v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise ValueError(f"{name} must be a finite number above 0, not {v!r}")
    return float(v)


def _number(name: str, v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{name} must be a finite number, not {v!r}")
    return float(v)


def _method(method: str) -> str:
    if not isinstance(method, str) or method not in METHODS:
        raise ValueError(f"method must be one of {sorted(METHODS)}: {METHODS}")
    return method


def _available(nominal: float, factors: Mapping[str, float], method: str) -> float:
    return nominal * factors["phi"] if method == "lrfd" else nominal / factors["omega"]


# ----------------------------------------------------------------------------- one fillet

@formula(units={"leg": "m (the weld size: each leg of the fillet)"}, returns="effective throat, m",
         limits=(_EQUAL_LEG, "no credit for penetration past the root, which AISC allows only when tests of the "
                 "production process show it"),
         source=cite("aisc-360-16", "Section J2.2a (effective area of fillet welds): the shortest distance from the "
                     "root to the face of the diagrammatic weld") + "; "
                + cite("shigley", "Chapter 9, 'Butt and Fillet Welds': the throat 0.707 h"))
def fillet_throat(leg: float) -> float:
    """Effective throat of an equal-leg fillet weld, the shortest distance from the root to the face: t = h cos 45 deg
    = 0.707 h."""
    return THROAT_OVER_LEG * _positive("leg", leg)


@formula(units={"leg": "m", "length": "m (the weld's effective length)"}, returns="effective (throat) area, m^2",
         limits=(_EQUAL_LEG, "a weld designed for strength is at least four legs long (AISC 360-16 J2.2b(c)); the "
                 "length is the full-size weld, without its starts and craters, and an end-loaded weld longer than "
                 "100 legs is reduced by J2.2b(d), which this does not apply"),
         source=cite("aisc-360-16", "Section J2.2a: the effective length times the effective throat") + "; "
                + cite("shigley", "Chapter 9, Table 9-1, weld 1: A = 0.707 h d"))
def fillet_throat_area(leg: float, length: float) -> float:
    """Effective area of an equal-leg fillet weld: A = 0.707 h l."""
    return fillet_throat(leg) * _positive("length", length)


@formula(units={"force": "N (along or across the weld, shared evenly by its length)", "leg": "m",
                "length": "m (all the welds sharing the load, added up)"},
         returns="stress on the throat, Pa",
         limits=(_STATIC, _SOUND, _AS_SHEAR, "the load passes through the weld group's centroid, so every part of "
                 "the length carries the same; an eccentric load needs weld_group_stress"),
         source=cite("shigley", "Chapter 9, 'Butt and Fillet Welds': tau = F / (0.707 h l) = 1.414 F / (h l), for a "
                     "fillet loaded across (in tension) or along (in shear)"))
def fillet_throat_stress(force: float, leg: float, length: float) -> float:
    """Stress on the throat of a fillet weld under a direct load, in shear or in tension: tau = F / (0.707 h l). The
    load is taken wholly as shear on the throat."""
    return abs(_number("force", force)) / fillet_throat_area(leg, length)


@formula(units={"thinner_thickness": "m (the thinner of the two parts joined)",
                "edge_thickness": "m (the part along whose edge the weld runs, as on the end of a lapped plate; None "
                                  "when the weld is not along an edge: a tube's end on a plate is a tee joint, and its "
                                  "wall does not cap the leg)"},
         returns="dict: minimum (the least leg, m), maximum (the largest leg along that edge, m, or None) and conflict "
                 "(true when the least exceeds the largest)",
         limits=("the inch column of AISC's table converted exactly (1/8, 3/16, 1/4, 5/16 in for the thinner part to "
                 "1/4, 1/2, 3/4 in and over); its SI column rounds these to 3, 5, 6, 8 mm at 6, 13, 19 mm",
                 "the least leg is for heat input, in a single pass, and the load may need more; it does not show that "
                 "a thin wall takes the heat without burning through", "the largest leg along an edge may be exceeded "
                 "where the drawing calls for the weld to be built out to full throat (J2.2b(b)), which this leaves "
                 "out", _MATCHING),
         source=cite("aisc-360-16", "Table J2.4 (minimum size of fillet welds) and Section J2.2b(b) (maximum size "
                     "along an edge)"))
def fillet_size_limits(thinner_thickness: float, edge_thickness: Optional[float] = None) -> Dict[str, Any]:
    """The least fillet leg AISC allows on parts of this thickness, and the largest along an edge: 1/8, 3/16, 1/4 or
    5/16 in (3.2, 4.8, 6.4, 7.9 mm) for the thinner part up to 1/4, 1/2, 3/4 in or more; along an edge under 1/4 in
    thick no more than the edge, and from 1/4 in the edge less 1/16 in (1.6 mm)."""
    t = _positive("thinner_thickness", thinner_thickness)
    minimum = next(leg for limit, leg in MINIMUM_LEG if t <= limit * (1.0 + 1e-9))     # "to 1/4 in inclusive"
    maximum = None
    if edge_thickness is not None:
        e = _positive("edge_thickness", edge_thickness)
        maximum = e if e < EDGE_FULL_THICKNESS_BELOW * (1.0 - 1e-9) else e - EDGE_MARGIN
    return {"minimum": minimum, "maximum": maximum, "conflict": maximum is not None and minimum > maximum}


# ----------------------------------------------------------------------------- a weld group as a line

def _group(pattern: str, length: float, iu_x: float, iu_y: float, **shape: Any) -> Dict[str, Any]:
    return {"pattern": pattern, **shape, "length": length, "iu_x": iu_x, "iu_y": iu_y, "ju": iu_x + iu_y}


_GROUP_RETURNS = ("dict: pattern, its dimensions, length (all the weld, m), iu_x and iu_y (unit second moments about "
                  "the x and y axes through the centroid, m^3) and ju (the unit polar second moment, m^3); multiply "
                  "each by the throat for the weld's own area and second moments")


@formula(units={"length": "m (each of the two welds, which run parallel to y)",
                "spacing": "m (between the two welds, measured along x)"},
         returns=_GROUP_RETURNS, limits=(_LINE, _RIGID, "two equal welds, opposite each other"),
         source=cite("shigley", "Chapter 9, Table 9-1 (torsional properties of fillet welds), weld 2: Ju = d (3 b^2 + "
                     "d^2) / 6; Table 9-2 (bending properties of fillet welds), welds 2 and 3: Iu = d^3 / 6 and b "
                     "d^2 / 2"))
def weld_line_parallel(length: float, spacing: float) -> Dict[str, Any]:
    """Two parallel welds of length d a distance b apart, as lines: Iu = d^3 / 6 about the axis across them (x),
    b^2 d / 2 about the axis along them (y), and Ju = d (3 b^2 + d^2) / 6."""
    d, b = _positive("length", length), _positive("spacing", spacing)
    return _group("parallel", 2.0 * d, d ** 3 / 6.0, b * b * d / 2.0, weld_length=d, spacing=b)


@formula(units={"width": "m (the rectangle's side along x, at the weld's root: the tube's outside)",
                "depth": "m (its side along y)"},
         returns=_GROUP_RETURNS,
         limits=(_LINE, _RIGID, "welded all round with one leg size; sharp corners (a tube's corner radius shortens the weld "
                 "a little, and the corners of a formed tube are where a weld is hardest to make well)"),
         source=cite("shigley", "Chapter 9, Table 9-1, weld 5: Ju = (b + d)^3 / 6; Table 9-2, weld 6: Iu = d^2 (3 b "
                     "+ d) / 6"))
def weld_line_box(width: float, depth: float) -> Dict[str, Any]:
    """A rectangle b by d welded all round (a box tube on a plate), as a line: Iu = d^2 (3 b + d) / 6 about x,
    b^2 (3 d + b) / 6 about y, and Ju = (b + d)^3 / 6."""
    b, d = _positive("width", width), _positive("depth", depth)
    return _group("box", 2.0 * (b + d), d * d * (3.0 * b + d) / 6.0, b * b * (3.0 * d + b) / 6.0, width=b, depth=d)


@formula(units={"diameter": "m (of the weld's root circle: the tube's or boss's outside)"}, returns=_GROUP_RETURNS,
         limits=(_LINE, _RIGID, "welded all round with one leg size"),
         source=cite("shigley", "Chapter 9, Table 9-1, weld 6: Ju = 2 pi r^3; Table 9-2, weld 9: Iu = pi r^3"))
def weld_line_circle(diameter: float) -> Dict[str, Any]:
    """A circle of radius r welded all round (a round tube or a pin boss on a plate), as a line: Iu = pi r^3 about any
    diameter and Ju = 2 pi r^3."""
    r = _positive("diameter", diameter) / 2.0
    iu = math.pi * r ** 3
    return _group("circle", 2.0 * math.pi * r, iu, iu, diameter=2.0 * r)


def _line_force(g: Mapping[str, float], loads: Tuple[float, ...], x: float, y: float) -> Tuple[float, float, float]:
    """Force per unit length on the weld at (x, y): the direct loads spread over the length, the torque's share
    T r / Ju at right angles to the radius, and the bending's M c / Iu along z."""
    vx, vy, p, mx, my, t = loads
    return (vx / g["length"] - t * y / g["ju"], vy / g["length"] + t * x / g["ju"],
            p / g["length"] + mx * y / g["iu_x"] - my * x / g["iu_y"])


def _norm(v: Tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _critical_point(g: Mapping[str, Any], loads: Tuple[float, ...]) -> Tuple[float, float]:
    """Where the resultant is largest. Each component is linear in x and y, so on a straight weld the resultant's
    square is convex and peaks at an end: the candidates are the ends (the corners). A circle is searched: 720
    samples, then every peak among them refined."""
    if g["pattern"] == "circle":
        r = g["diameter"] / 2.0

        def at(angle: float) -> float:
            return _norm(_line_force(g, loads, r * math.cos(angle), r * math.sin(angle)))

        step = 2.0 * math.pi / _CIRCLE_SAMPLES
        values = [at(i * step) for i in range(_CIRCLE_SAMPLES)]
        best, best_value = 0.0, values[0]
        for i, v in enumerate(values):                        # refine every peak of the samples, then take the highest
            if v < values[i - 1] or v < values[(i + 1) % _CIRCLE_SAMPLES]:
                continue
            lo, hi = (i - 1) * step, (i + 1) * step
            for _ in range(60):                               # ternary search between the two neighbouring samples
                a, b = lo + (hi - lo) / 3.0, hi - (hi - lo) / 3.0
                lo, hi = (a, hi) if at(a) < at(b) else (lo, b)
            angle = (lo + hi) / 2.0
            if at(angle) >= best_value:
                best, best_value = angle, at(angle)
        return r * math.cos(best), r * math.sin(best)
    half_x = (g["spacing"] if g["pattern"] == "parallel" else g["width"]) / 2.0
    half_y = (g["weld_length"] if g["pattern"] == "parallel" else g["depth"]) / 2.0
    corners: List[Tuple[float, float]] = [(sx * half_x, sy * half_y) for sx in (1.0, -1.0) for sy in (1.0, -1.0)]
    return max(corners, key=lambda c: _norm(_line_force(g, loads, *c)))


def _checked_group(group: Any) -> Dict[str, Any]:
    """The group rebuilt from its pattern and dimensions, so a dict edited by the caller cannot carry properties
    that no longer belong to its shape; it is refused when they disagree."""
    builders = {"parallel": (weld_line_parallel, ("weld_length", "spacing")), "box": (weld_line_box, ("width", "depth")),
                "circle": (weld_line_circle, ("diameter",))}
    if not isinstance(group, Mapping) or not isinstance(group.get("pattern"), str) or group["pattern"] not in builders:
        raise ValueError(f"group must be the dict from weld_line_parallel, weld_line_box or weld_line_circle "
                         f"(patterns {PATTERNS}), not {group!r}")
    build, dims = builders[group["pattern"]]
    fresh = build(*(_positive(f"group[{key!r}]", group.get(key)) for key in dims))
    for key in ("length", "iu_x", "iu_y", "ju"):
        given = group.get(key, fresh[key])
        if isinstance(given, bool) or not isinstance(given, (int, float)) or not math.isclose(given, fresh[key],
                                                                                              rel_tol=1e-9):
            raise ValueError(f"group[{key!r}] is {given!r}, but a {group['pattern']} of these dimensions has "
                             f"{fresh[key]!r}: build the group with weld_line_{group['pattern']} and do not edit it")
    return fresh


@formula(units={"group": "dict from weld_line_parallel, weld_line_box or weld_line_circle",
                "leg": "m (one leg size for the whole group)", "shear_x": "N (in the weld's plane)",
                "shear_y": "N (in the weld's plane)", "axial": "N (along z, pulling or pushing the member off the "
                "plate)", "moment_x": "N m (bending about x: it loads the welds farthest in y)",
                "moment_y": "N m (bending about y)", "torque": "N m (about z, twisting in the weld's plane)"},
         returns="dict: throat (m), throat_area (m^2), primary (the direct loads' stress, the same all along, Pa), "
                 "secondary (the moments' and the torque's stress at the critical point, Pa), stress (their vector "
                 "sum on the throat at the critical point, Pa), force_per_length (that resultant per unit of weld, "
                 "N/m) and point ([x, y] of the critical point, m)",
         limits=(_STATIC, _SOUND, _LINE, _RIGID, _EVEN_SHEAR, _AS_SHEAR, "every load acts at the group's centroid: move an offset force "
                 "there and add its moment (force times arm) yourself; compression is counted like tension, though "
                 "a fitted member bears on the plate", _EQUAL_LEG),
         source=cite("shigley", "Chapter 9, 'Stresses in Welded Joints in Torsion' and 'Stresses in Welded Joints in "
                     "Bending': primary shear V / A, secondary shear M r / J and M c / I with J = 0.707 h Ju and I = "
                     "0.707 h Iu, added as vectors (Tables 9-1 and 9-2; Examples 9-1 and 9-4)"))
def weld_group_stress(group: Mapping[str, Any], leg: float, shear_x: float = 0.0, shear_y: float = 0.0,
                      axial: float = 0.0, moment_x: float = 0.0, moment_y: float = 0.0,
                      torque: float = 0.0) -> Dict[str, Any]:
    """Stress on the throat of a fillet weld group at its critical point, by the line method: the direct loads spread
    over the length (V / A), bending as M c / I and torsion as T r / J, added as vectors and taken as shear on the
    throat 0.707 h."""
    g = _checked_group(group)
    throat = fillet_throat(leg)
    loads = tuple(_number(name, v) for name, v in (("shear_x", shear_x), ("shear_y", shear_y), ("axial", axial),
                                                   ("moment_x", moment_x), ("moment_y", moment_y), ("torque", torque)))
    x, y = _critical_point(g, loads)
    resultant = _norm(_line_force(g, loads, x, y))
    if not math.isfinite(resultant):
        raise ValueError("the loads are too large to add up: the resultant overflows")
    primary = _norm(_line_force(g, loads[:3] + (0.0, 0.0, 0.0), x, y))
    secondary = _norm(_line_force(g, (0.0, 0.0, 0.0) + loads[3:], x, y))
    return {"throat": throat, "throat_area": throat * g["length"], "primary": primary / throat,
            "secondary": secondary / throat, "stress": resultant / throat, "force_per_length": resultant,
            "point": [x, y]}


# ----------------------------------------------------------------------------- strength (AISC 360-16)

@formula(units={"electrode_strength": "Pa (FEXX, the filler metal's classification strength: E70 is 483 MPa)",
                "method": "one of METHODS: 'lrfd' or 'asd'"},
         returns="dict: method, nominal (Fnw = 0.60 FEXX, Pa), factor (phi 0.75 for lrfd, which multiplies; Omega "
                 "2.00 for asd, which divides) and available (the stress the throat may carry, Pa)",
         limits=(_STATIC, _SOUND, _MATCHING, _AS_SHEAR, "compare lrfd with factored loads and asd with service "
                 "loads; the base metal is checked apart (base_metal_shear_strength)"),
         source=cite("aisc-360-16", "Section J2.4(a), Eq. (J2-3), and Table J2.5 (fillet welds, shear): Fnw = 0.60 "
                     "FEXX on the effective area, phi = 0.75, Omega = 2.00"))
def weld_metal_strength(electrode_strength: float, method: str = "lrfd") -> Dict[str, Any]:
    """The stress a fillet weld's throat may carry by AISC 360-16: nominal 0.60 FEXX, times phi = 0.75 (LRFD) or over
    Omega = 2.00 (ASD)."""
    nominal = WELD_METAL["stress_over_fexx"] * _positive("electrode_strength", electrode_strength)
    m = _method(method)
    return {"method": m, "nominal": nominal, "factor": WELD_METAL["phi" if m == "lrfd" else "omega"],
            "available": _available(nominal, WELD_METAL, m)}


@formula(units={"thickness": "m (of the part beside this weld that carries its load: a tube's whole wall for a weld "
                "on one side, half a plate's thickness under each of two welds on opposite sides)",
                "yield_strength": "Pa (the base metal's Fy)", "tensile_strength": "Pa (the base metal's Fu)",
                "method": "one of METHODS: 'lrfd' or 'asd'"},
         returns="dict: method, yielding and rupture (the available force per unit length of weld in each limit "
                 "state, N/m), available (the lower, N/m) and mode ('yielding' or 'rupture')",
         limits=(_STATIC, _NOT_HAZ, "the base metal in shear through its thickness beside the weld, on a plane clear "
                 "of the fusion face (AISC 360-16 Commentary J2.4); a wall pulled across the weld is in tension, "
                 "which is stronger, so shear is the cautious reading", "use the strengths of the metal as it is "
                 "beside the weld: Shigley (Chapter 9) takes the hot-rolled values for cold-drawn steel"),
         source=cite("aisc-360-16", "Section J2.4(a), Eq. (J2-2), and Table J2.5 (base metal governed by Section "
                     "J4); Section J4.2: shear yielding 0.60 Fy Agv, phi = 1.00, Omega = 1.50 (Eq. J4-3), and shear "
                     "rupture 0.60 Fu Anv, phi = 0.75, Omega = 2.00 (Eq. J4-4)"))
def base_metal_shear_strength(thickness: float, yield_strength: float, tensile_strength: float,
                              method: str = "lrfd") -> Dict[str, Any]:
    """The force per unit length of weld that the base metal beside it may carry in shear by AISC 360-16 J4.2: the
    lower of yielding, 0.60 Fy t (phi 1.00, Omega 1.50), and rupture, 0.60 Fu t (phi 0.75, Omega 2.00)."""
    t, m = _positive("thickness", thickness), _method(method)
    modes = {"yielding": _available(BASE_YIELDING["stress_over_strength"] * _positive("yield_strength", yield_strength)
                                    * t, BASE_YIELDING, m),
             "rupture": _available(BASE_RUPTURE["stress_over_strength"] * _positive("tensile_strength",
                                                                                   tensile_strength) * t,
                                   BASE_RUPTURE, m)}
    mode = min(modes, key=modes.get)
    return {"method": m, **modes, "available": modes[mode], "mode": mode}


@formula(units={"stress": "Pa (on the throat at the critical point: weld_group_stress's or fillet_throat_stress's)",
                "leg": "m", "electrode_strength": "Pa (FEXX)", "thickness": "m (as base_metal_shear_strength's)",
                "yield_strength": "Pa (base metal, beside the weld)", "tensile_strength": "Pa (base metal)",
                "method": "one of METHODS: 'lrfd' (the stress from factored loads) or 'asd' (from service loads)"},
         returns="dict: method, weld_ratio (stress over the weld metal's available stress), base_ratio (the weld's "
                 "force per unit length over the base metal's), weld_passes, base_passes, passes (both), governs "
                 "('weld' or 'base', the higher ratio), force_per_length (N/m), weld_available (Pa) and "
                 "base_available (N/m)",
         limits=(_STATIC, _SOUND, _MATCHING, _NOT_HAZ, "the two checks are kept apart: the weld metal on its throat, "
                 "the base metal through its thickness; check the other part joined with a second call", "a pass at "
                 "a ratio of 1 has no margin beyond the specification's own factor, and none for fatigue or impact"),
         source=cite("aisc-360-16", "Section J2.4(a): the lower of the base metal's strength, Eq. (J2-2), and the "
                     "weld metal's, Eq. (J2-3), with Table J2.5 and Section J4.2"))
def fillet_weld_check(stress: float, leg: float, electrode_strength: float, thickness: float, yield_strength: float,
                      tensile_strength: float, method: str = "lrfd") -> Dict[str, Any]:
    """A fillet weld's throat stress against AISC 360-16, the weld metal and the base metal apart: the stress over
    0.60 FEXX with its factor, and the weld's force per unit length over the base metal's shear strength."""
    tau = _number("stress", stress)
    if tau < 0:
        raise ValueError(f"stress must be 0 or more, not {stress!r}")
    weld = weld_metal_strength(electrode_strength, method)
    base = base_metal_shear_strength(thickness, yield_strength, tensile_strength, method)
    per_length = tau * fillet_throat(leg)
    weld_ratio, base_ratio = tau / weld["available"], per_length / base["available"]
    return {"method": weld["method"], "weld_ratio": weld_ratio, "base_ratio": base_ratio,
            "weld_passes": weld_ratio <= 1.0, "base_passes": base_ratio <= 1.0,
            "passes": weld_ratio <= 1.0 and base_ratio <= 1.0,
            "governs": "weld" if weld_ratio >= base_ratio else "base", "force_per_length": per_length,
            "weld_available": weld["available"], "base_available": base["available"]}
