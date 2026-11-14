"""Rotational symmetry of a solid about an axis, measured from its geometry.

The motion gate turns a revolute joint's body through its range. A body that a rotation about the joint
axis maps onto itself (a shaft, a plain gear blank, a wheel with twelve identical lugs) is in the same
place at many of those samples, and the same pose need not be queried twice. Whether that holds is
measured here on the solid: it is never taken from a declaration.

``rotational_symmetry(shape, origin, direction)`` returns a ``Symmetry`` or ``None``:

* ``order == 0``: a body of revolution, unchanged by any rotation about the axis;
* ``order == N`` (2 or more): unchanged by a rotation of ``360 / N`` degrees, and by no finer one up to
  ``max_order``.

A rotation by an angle counts as leaving the solid unchanged when both hold:

1. **Volume.** The volume the solid shares with its rotated copy (``BRepAlgoAPI_Common``) equals its own
   volume within ``volume_check_mm3`` plus 1e-6 of the volume (the allowance the relation table gives
   ``vol = common + cut``), so the two differ by at most twice that.
2. **Boundary points.** Every vertex of the solid and three points along each of its edges, rotated, lie
   within ``touch_mm`` of the solid's faces (``BRepExtrema_DistShapeShape``). A fin or pocket too thin to
   register in the volume still moves its corners and edges off the surface.

A body of revolution must pass at three angles that are irrational fractions of a turn and share no close
rational approximation (``GENERIC_DEG``): a pattern of N teeth can sit within tolerance of itself at one
such angle, not at all three. A part whose centre of mass is off the axis is not symmetric and is
answered without a boolean.

Limits. This is a measurement within the two tolerances above, not a proof: a feature that moves none
of those points by more than ``touch_mm`` and changes less volume than the allowance is not seen. A kernel failure
or any doubt gives ``None`` (no symmetry), which only costs time. Orders above ``max_order`` (a pattern
finer than 1 degree) are not looked for.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require
from cadagent.review.gates.relations import Tolerances, _boolean, _faces, _measure_volume, _trsf

SYMMETRY_VERSION = "1"
MAX_ORDER = 360
# 360/phi^2, 360/e, 360/pi: irrational fractions of a turn whose close rational approximations differ
GENERIC_DEG = (137.50776405003785, 132.43657741585718, 114.59155902616465)
_EDGE_POINTS = 3          # points taken inside each edge, besides its vertices
_MAX_REFUSED = 8          # volume tests allowed to refuse a period the boundary points accepted before giving up


@dataclass(frozen=True)
class Symmetry:
    """What was measured: ``order`` (0 = body of revolution, N = repeats every 360/N deg), the largest
    volume not shared with the rotated copy and the largest distance of a rotated boundary point from the
    faces, over the ``angles_deg`` tested, with the limits they were held to and the number of points."""
    order: int
    difference_mm3: float
    boundary_mm: float
    angles_deg: Tuple[float, ...] = ()
    limit_mm3: float = 0.0
    limit_mm: float = 0.0
    points: int = 0

    @property
    def period_deg(self) -> float:
        """Degrees after which the solid repeats; 0 for a body of revolution (any angle)."""
        return 360.0 / self.order if self.order else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "angles_deg": list(self.angles_deg)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Symmetry":
        return cls(**{**data, "angles_deg": tuple(data.get("angles_deg", ()))})


def _rotation_rows(origin: Sequence[float], direction: Sequence[float], degrees: float) -> List[List[float]]:
    from cadagent.review.gates.motion import rotation
    m = rotation(origin, direction, degrees)
    return [list(m[0:4]), list(m[4:8]), list(m[8:12])]


def _boundary_points(topods) -> List[Tuple[float, float, float]]:
    """Every vertex of the solid plus ``_EDGE_POINTS`` points along each edge: points of its boundary that a
    rotation leaving it unchanged must put back on its faces."""
    topexp = require("OCP.TopExp", "boundary points")
    topabs = require("OCP.TopAbs", "boundary points")
    topo = require("OCP.TopoDS", "boundary points")
    brep = require("OCP.BRep", "boundary points")
    adaptor = require("OCP.BRepAdaptor", "boundary points")
    seen: Dict[Tuple[float, ...], Tuple[float, float, float]] = {}

    def add(p) -> None:
        xyz = (p.X(), p.Y(), p.Z())
        seen.setdefault(tuple(round(v, 7) for v in xyz), xyz)

    ex = topexp.TopExp_Explorer(topods, topabs.TopAbs_VERTEX)
    while ex.More():
        add(brep.BRep_Tool.Pnt_s(topo.TopoDS.Vertex_s(ex.Current())))
        ex.Next()
    ex = topexp.TopExp_Explorer(topods, topabs.TopAbs_EDGE)
    while ex.More():
        edge = topo.TopoDS.Edge_s(ex.Current())
        if not brep.BRep_Tool.Degenerated_s(edge):
            curve = adaptor.BRepAdaptor_Curve(edge)
            u0, u1 = curve.FirstParameter(), curve.LastParameter()
            if math.isfinite(u0) and math.isfinite(u1):
                for i in range(1, _EDGE_POINTS + 1):
                    add(curve.Value(u0 + (u1 - u0) * i / (_EDGE_POINTS + 1)))
        ex.Next()
    return list(seen.values())


def _off_axis(p: Sequence[float], origin: Sequence[float], unit: Sequence[float]) -> float:
    v = [p[i] - origin[i] for i in range(3)]
    t = sum(v[i] * unit[i] for i in range(3))
    return math.sqrt(max(0.0, sum(c * c for c in v) - t * t))


def rotational_symmetry(shape: Any, origin: Sequence[float], direction: Sequence[float],
                        tol: Tolerances = Tolerances(), *, max_order: int = MAX_ORDER) -> Optional[Symmetry]:
    """The rotational symmetry of ``shape`` (in the coordinates of the axis) about the axis through ``origin``
    along ``direction``, or ``None`` when none is measured (see the module docstring for the test)."""
    try:
        return _measure(getattr(shape, "wrapped", shape), [float(c) for c in origin],
                        [float(c) for c in direction], tol, int(max_order))
    except Exception:            # any kernel failure: no symmetry claimed, the joint is sampled in full
        return None


def _measure(topods, origin: List[float], direction: List[float], tol: Tolerances,
             max_order: int) -> Optional[Symmetry]:
    gp = require("OCP.gp", "symmetry")
    gprop = require("OCP.GProp", "symmetry")
    bgprop = require("OCP.BRepGProp", "symmetry")
    builder = require("OCP.BRepBuilderAPI", "symmetry")
    extrema = require("OCP.BRepExtrema", "symmetry")
    toploc = require("OCP.TopLoc", "symmetry")
    from cadagent.review.gates.motion import _apply, rotation

    n = math.sqrt(sum(c * c for c in direction))
    if not n:
        return None
    unit = [c / n for c in direction]
    volume = _measure_volume(topods)
    if volume.value <= 0:
        return None
    limit = tol.volume_check_mm3 + 1e-6 * volume.value
    props = gprop.GProp_GProps()
    bgprop.BRepGProp.VolumeProperties_s(topods, props, 1e-6)
    c = props.CentreOfMass()
    if _off_axis((c.X(), c.Y(), c.Z()), origin, unit) > tol.touch_mm:
        return None                                   # a symmetric solid balances on its axis
    points = sorted(_boundary_points(topods), key=lambda p: -_off_axis(p, origin, unit))
    faces = _faces(topods)
    dist = extrema.BRepExtrema_DistShapeShape()
    dist.LoadS2(faces)

    def boundary_off(degrees: float) -> Optional[float]:
        """Largest distance of a rotated boundary point from the faces, or None once one is beyond ``touch_mm``
        (that point is then tried first at the next angle: the points that tell angles apart are few)."""
        m = rotation(origin, unit, degrees)
        worst = 0.0
        for i, p in enumerate(points):
            q = _apply(m, p)
            dist.LoadS1(builder.BRepBuilderAPI_MakeVertex(gp.gp_Pnt(*q)).Vertex())
            dist.Perform()
            if not dist.IsDone() or dist.NbSolution() < 1:
                return None
            d = float(dist.Value())
            if d > tol.touch_mm:
                points.insert(0, points.pop(i))
                return None
            worst = max(worst, d)
        return worst

    def volume_off(degrees: float) -> Optional[float]:
        """Volume of the solid outside its rotated copy, or None when it is over the limit or uncertain."""
        turned = topods.Moved(toploc.TopLoc_Location(_trsf(_rotation_rows(origin, unit, degrees))))
        common = _measure_volume(_boolean("common", topods, turned))
        diff = abs(volume.value - common.value)
        return diff if diff + common.error <= limit else None

    def unchanged(angles: Sequence[float]) -> Optional[Tuple[float, float]]:
        worst_v = worst_d = 0.0
        for a in angles:                # every point test first: a boolean costs far more than they do
            v = boundary_off(a)
            if v is None:
                return None
            worst_v = max(worst_v, v)
        for a in angles:
            d = volume_off(a)
            if d is None:
                return None
            worst_d = max(worst_d, d)
        return worst_d, worst_v

    def found(order: int, angles: Sequence[float], got: Tuple[float, float]) -> Symmetry:
        return Symmetry(order, round(got[0], 9), round(got[1], 9), tuple(round(a, 9) for a in angles),
                        round(limit, 9), tol.touch_mm, len(points))

    got = unchanged(GENERIC_DEG)
    if got is not None:
        return found(0, GENERIC_DEG, got)
    refused = 0
    for order in range(max_order, 1, -1):          # the finest period first: its divisors repeat too
        angle = 360.0 / order
        v = boundary_off(angle)
        if v is None:
            continue
        d = volume_off(angle)
        if d is None:
            refused += 1
            if refused >= _MAX_REFUSED:
                return None
            continue
        return found(order, (angle,), (d, v))
    return None
