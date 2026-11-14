"""Rotational symmetry of a solid about an axis, measured from its geometry.

The motion gate turns a revolute joint's body through its range. A body that a rotation about the joint
axis maps onto itself (a shaft, a plain gear blank, a wheel with twelve identical lugs) is in the same
place at many of those samples, and the same pose need not be queried twice. Whether that holds is
measured here on the solid: it is never taken from a declaration.

**The rule the tolerances follow.** The gate reports shared volume above ``overlap_mm3`` and a gap at or
below ``touch_mm``, and its crossing probe ignores a depth of ``touch_mm / 10``. A symmetry claimed here
replaces a sampled pose by another one, so whatever this test ignores has to be smaller than anything the
gate reports: between any two poses it treats as the same, the solid's boundary moves by no more than
``touch_mm / 10`` and no more than ``overlap_mm3 / 2`` of its volume changes place. An asymmetry that is
ignored can therefore not be, on its own, an interference or a contact the gate reports. A solid on which
that cannot be measured is refused (no symmetry is claimed), which only costs time.

``measure_symmetry(shape, origin, direction)`` returns a ``Symmetry``:

* ``order == 0``: a body of revolution, unchanged by any rotation about the axis;
* ``order == N`` (2 or more): unchanged by a rotation of ``360 / N`` degrees, and by no finer one among
  the orders looked for;
* ``order == 1``: no symmetry is claimed; ``reason`` says why, and ``refused`` is true when the solid was
  not measured to the end (a free-form face, too much work, an integration error over the limit, a kernel
  failure) rather than measured and found asymmetric.

``rotational_symmetry`` is the same measurement returning ``None`` for order 1.

A rotation by an angle counts as leaving the solid unchanged when both hold, each to the limit below:

1. **Volume.** The volume of the solid outside its rotated copy (``BRepAlgoAPI_Cut``, integrated on its
   own), and the solid's volume less the volume it shares with the copy (``BRepAlgoAPI_Common``), are each
   within the limit *with the kernel's integration error estimates added*. There is no allowance that
   grows with the part: a large curved solid whose integration error estimate alone is over the limit is
   refused.
2. **Boundary points.** Points of the solid's boundary, rotated by the angle and by its reverse, lie
   within the limit of the solid's faces (``BRepExtrema_DistShapeShape``). The points are every vertex,
   ``_EDGE_POINTS`` points inside every edge and a ``_FACE_GRID`` by ``_FACE_GRID`` grid inside every face
   (finer where a narrow face would get none), so a smooth feature that has no edge or vertex of its own
   in view (a spherical bump with a buried seam, a dome, a dimple) is still sampled on its own face.

The limits, from ``touch_mm / 10`` (boundary) and ``overlap_mm3 / 2`` (volume):

* **Order N** is tested at one step of ``360 / N`` and held to those limits divided by ``N / 2``. A pose is
  at most ``N / 2`` steps from one that was queried, and the differences of single steps add up over
  them, so the whole drift stays within the undivided limits. (A shaft whose joint axis is a few microns
  off its own axis repeats almost exactly after one degree and is visibly elsewhere after 180.) The
  boundary points are also tested at the multiple nearest a half turn, to the undivided limit.
* **A body of revolution** must pass at three angles that are irrational fractions of a turn and share no
  close rational approximation (``GENERIC_DEG``), held to the limits times ``_GENERIC_SHARE``: a pattern
  of N lobes can sit close to itself at one such angle, and that factor is the least share of a lobed
  pattern's largest difference that the best of the three angles shows (for every lobe count to 20000).

Faces have to be planes, cylinders, cones, spheres or tori. On those a feature has faces of its own, each
of which is sampled; a free-form face (a spline, an offset, a swept curve) can carry a local feature
between sample points, so a solid with one is refused. The work is capped (``MAX_POINTS`` boundary points,
``MAX_DISTANCES`` point-to-face distances): beyond it the solid is refused and the reason says so.

Limits. This is a measurement, not a proof. The boundary is compared at sample points, the booleans and
integrals are OCCT's, and a pair whose gap or shared volume sits within the limits above of one of the
gate's thresholds can read either way. The point tests run before any boolean, so a solid that is plainly
not symmetric is answered by its first few points. Orders above ``max_order`` (a pattern finer than 1 degree)
are not looked for.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require
from cadagent.review.gates.relations import Tolerances, _boolean, _trsf, _validate_volume_shape

SYMMETRY_VERSION = "2"    # 2: limits under the gate's own thresholds, face-interior points, per-step scaling (#724)
MAX_ORDER = 360
# 360/phi^2, 360/e, 360/pi: irrational fractions of a turn whose close rational approximations differ
GENERIC_DEG = (137.50776405003785, 132.43657741585718, 114.59155902616465)
# min over m = 1..20000 of max over GENERIC_DEG of |sin(m * angle / 2)| is 0.0443 (at m = 1775): the share of an
# m-lobed difference's maximum over all angles that the best of the three angles shows
_GENERIC_SHARE = 0.04
_EDGE_POINTS = 3          # points taken inside each edge, besides its vertices
_FACE_GRID = 5            # grid inside each face's parameter box (odd, so its middle is a point)
_FACE_GRID_RETRIES = 2    # times the grid is refined (n -> 2n + 1) when no point of it is inside the face
MAX_POINTS = 20000        # boundary points beyond which the solid is refused
MAX_DISTANCES = 400000    # point-to-face distances beyond which the measurement is abandoned
_MAX_REFUSED = 8          # volume tests allowed to refuse a period the boundary points accepted before giving up
_VOLUME_EPS = 1e-10       # relative tolerance asked of the adaptive volume integration


@dataclass(frozen=True)
class Symmetry:
    """What was measured. ``order``: 0 = body of revolution, N = repeats every 360/N deg, 1 = no symmetry
    claimed (``reason`` says why; ``refused`` when the solid was not measured to the end, ``failed`` when that
    was a kernel failure). ``difference_mm3`` and ``boundary_mm`` are the largest volume not shared with the
    rotated copy and the largest distance of a rotated boundary point from the faces: for a body of revolution
    the maximum over the three ``angles_deg``, for order N those of one step of 360/N. ``limit_mm3`` and
    ``limit_mm`` are what they were held to and ``points`` the number of boundary points compared."""
    order: int
    difference_mm3: float = 0.0
    boundary_mm: float = 0.0
    angles_deg: Tuple[float, ...] = ()
    limit_mm3: float = 0.0
    limit_mm: float = 0.0
    points: int = 0
    reason: str = ""
    refused: bool = False
    failed: bool = False

    @property
    def period_deg(self) -> float:
        """Degrees after which the solid repeats; 0 for a body of revolution (any angle) and for none."""
        return 360.0 / self.order if self.order > 1 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "angles_deg": list(self.angles_deg)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Symmetry":
        return cls(**{**data, "angles_deg": tuple(data.get("angles_deg", ()))})


class _Refused(Exception):
    """The solid cannot be measured to the limits: no symmetry is claimed, for the reason given."""


def boundary_limit_mm(tol: Tolerances) -> float:
    """The most the boundary may move between two poses treated as one: the crossing probe's depth."""
    return tol.touch_mm / 10.0


def volume_limit_mm3(tol: Tolerances) -> float:
    """The most volume that may change place between two poses treated as one: half of what is an overlap."""
    return tol.overlap_mm3 / 2.0


def _rotation_rows(origin: Sequence[float], direction: Sequence[float], degrees: float) -> List[List[float]]:
    from cadagent.review.gates.motion import rotation
    m = rotation(origin, direction, degrees)
    return [list(m[0:4]), list(m[4:8]), list(m[8:12])]


def _volume(topods) -> Tuple[float, float]:
    """(volume, absolute error estimate) by adaptive integration at ``_VOLUME_EPS``; (0, 0) for a valid shape
    with no solid (an empty boolean result). An invalid or open result raises."""
    gprop = require("OCP.GProp", "volume")
    bgprop = require("OCP.BRepGProp", "volume")
    if not _validate_volume_shape(topods):
        return 0.0, 0.0
    props = gprop.GProp_GProps()
    error = float(bgprop.BRepGProp.VolumePropertiesGK_s(topods, props, _VOLUME_EPS, False, True, False, False, False))
    value = float(props.Mass())
    if not math.isfinite(value) or not math.isfinite(error) or error < 0:
        raise RuntimeError("volume integration returned an invalid value or error")
    return value, (error * abs(value) if abs(value) > 2.3e-16 else error)   # relative above Epsilon(1.0), as OCCT


@dataclass
class _Face:
    """One face with what a point is compared against: its surface, its trimmed region and its box."""
    shape: Any
    surface: Any          # BRepAdaptor_Surface
    kind: str             # plane, cylinder, cone, sphere or torus
    inside: Any           # BRepTopAdaptor_FClass2d: is a (u, v) inside the trimmed face
    edges: int


def _boundary(topods) -> Tuple[List[Tuple[float, float, float]], List[_Face]]:
    """(points, faces): every vertex, ``_EDGE_POINTS`` points inside each edge and a grid of points inside each
    face. A rotation that leaves the solid unchanged must put each of them back on its faces. Raises
    ``_Refused`` for a free-form face, a face no grid point falls inside, or more than ``MAX_POINTS``."""
    topexp = require("OCP.TopExp", "boundary points")
    topabs = require("OCP.TopAbs", "boundary points")
    topo = require("OCP.TopoDS", "boundary points")
    brep = require("OCP.BRep", "boundary points")
    adaptor = require("OCP.BRepAdaptor", "boundary points")
    tools = require("OCP.BRepTools", "boundary points")
    fclass = require("OCP.BRepTopAdaptor", "boundary points")
    geomabs = require("OCP.GeomAbs", "boundary points")
    gp = require("OCP.gp", "boundary points")
    analytic = {geomabs.GeomAbs_Plane: "plane", geomabs.GeomAbs_Cylinder: "cylinder", geomabs.GeomAbs_Cone: "cone",
                geomabs.GeomAbs_Sphere: "sphere", geomabs.GeomAbs_Torus: "torus"}
    seen: Dict[Tuple[float, ...], Tuple[float, float, float]] = {}

    def add(p) -> None:
        xyz = (p.X(), p.Y(), p.Z())
        seen.setdefault(tuple(round(v, 7) for v in xyz), xyz)
        if len(seen) > MAX_POINTS:
            raise _Refused(f"more than {MAX_POINTS} boundary points to compare (the work limit)")

    faces: List[_Face] = []
    ex = topexp.TopExp_Explorer(topods, topabs.TopAbs_FACE)
    while ex.More():
        face = topo.TopoDS.Face_s(ex.Current())
        surface = adaptor.BRepAdaptor_Surface(face)
        if surface.GetType() not in analytic:
            raise _Refused("a free-form face (not a plane, cylinder, cone, sphere or torus): a local feature of it "
                           "could lie between sample points")
        u0, u1, v0, v1 = tools.BRepTools.UVBounds_s(face)
        if not all(math.isfinite(x) for x in (u0, u1, v0, v1)):
            raise _Refused("a face with an unbounded parameter range")
        inside = fclass.BRepTopAdaptor_FClass2d(face, 1e-9)
        count, edge = 0, topexp.TopExp_Explorer(face, topabs.TopAbs_EDGE)
        while edge.More():
            count += 1
            edge.Next()
        faces.append(_Face(face, surface, analytic[surface.GetType()], inside, count))
        n, got = _FACE_GRID, 0
        for _ in range(_FACE_GRID_RETRIES + 1):
            for i in range(n):
                for k in range(n):
                    u, v = u0 + (u1 - u0) * (i + 0.5) / n, v0 + (v1 - v0) * (k + 0.5) / n
                    if inside.Perform(gp.gp_Pnt2d(u, v)) == topabs.TopAbs_IN:
                        add(surface.Value(u, v))
                        got += 1
            if got:
                break
            n = 2 * n + 1
        if not got:
            raise _Refused("a face too narrow for any grid point to fall inside it")
        ex.Next()
    ex = topexp.TopExp_Explorer(topods, topabs.TopAbs_VERTEX)
    while ex.More():
        add(brep.BRep_Tool.Pnt_s(topo.TopoDS.Vertex_s(ex.Current())))
        ex.Next()
    ex = topexp.TopExp_Explorer(topods, topabs.TopAbs_EDGE)
    while ex.More():
        edge = topo.TopoDS.Edge_s(ex.Current())
        if not brep.BRep_Tool.Degenerated_s(edge):
            curve = adaptor.BRepAdaptor_Curve(edge)
            c0, c1 = curve.FirstParameter(), curve.LastParameter()
            if not (math.isfinite(c0) and math.isfinite(c1)):
                raise _Refused("an edge with an unbounded parameter range")
            for i in range(1, _EDGE_POINTS + 1):
                add(curve.Value(c0 + (c1 - c0) * i / (_EDGE_POINTS + 1)))
        ex.Next()
    return list(seen.values()), faces


def _off_axis(p: Sequence[float], origin: Sequence[float], unit: Sequence[float]) -> float:
    v = [p[i] - origin[i] for i in range(3)]
    t = sum(v[i] * unit[i] for i in range(3))
    return math.sqrt(max(0.0, sum(c * c for c in v) - t * t))


def measure_symmetry(shape: Any, origin: Sequence[float], direction: Sequence[float],
                     tol: Tolerances = Tolerances(), *, max_order: int = MAX_ORDER,
                     orders: Optional[Sequence[int]] = None) -> Symmetry:
    """The rotational symmetry of ``shape`` (in the coordinates of the axis) about the axis through ``origin``
    along ``direction``: always a ``Symmetry``, whose ``order`` is 1 with a ``reason`` when none is claimed (the
    module docstring has the test). ``orders`` limits the repeating patterns looked for to those orders (the
    finest first); a body of revolution is looked for either way."""
    try:
        wanted = sorted({int(n) for n in (range(2, int(max_order) + 1) if orders is None else orders)
                         if 2 <= int(n) <= int(max_order)}, reverse=True)
        return _measure(getattr(shape, "wrapped", shape), [float(c) for c in origin],
                        [float(c) for c in direction], tol, wanted)
    except _Refused as exc:
        return Symmetry(1, reason=str(exc), refused=True)
    except Exception as exc:     # any kernel failure: no symmetry claimed, the joint is sampled in full
        return Symmetry(1, reason=f"the kernel failed while measuring: {type(exc).__name__}: {exc}",
                        refused=True, failed=True)


def rotational_symmetry(shape: Any, origin: Sequence[float], direction: Sequence[float],
                        tol: Tolerances = Tolerances(), *, max_order: int = MAX_ORDER,
                        orders: Optional[Sequence[int]] = None) -> Optional[Symmetry]:
    """``measure_symmetry``, or ``None`` when no symmetry is claimed (measured asymmetric, refused or failed)."""
    found = measure_symmetry(shape, origin, direction, tol, max_order=max_order, orders=orders)
    return found if found.order != 1 else None


def _measure(topods, origin: List[float], direction: List[float], tol: Tolerances, orders: List[int]) -> Symmetry:
    gp = require("OCP.gp", "symmetry")
    builder = require("OCP.BRepBuilderAPI", "symmetry")
    extrema = require("OCP.BRepExtrema", "symmetry")
    toploc = require("OCP.TopLoc", "symmetry")
    bnd = require("OCP.Bnd", "symmetry")
    bndlib = require("OCP.BRepBndLib", "symmetry")
    from cadagent.review.gates.motion import _apply, rotation

    n = math.sqrt(sum(c * c for c in direction))
    if not n:
        return Symmetry(1, reason="the axis has no direction")
    unit = [c / n for c in direction]
    limit_mm, limit_mm3 = boundary_limit_mm(tol), volume_limit_mm3(tol)
    if limit_mm <= 0 or limit_mm3 <= 0:
        raise _Refused("touch_mm or overlap_mm3 is 0: nothing can be measured to be under it")
    volume, volume_error = _volume(topods)
    if volume <= 0:
        return Symmetry(1, reason="the shape has no volume")
    points, faces = _boundary(topods)
    points.sort(key=lambda p: -_off_axis(p, origin, unit))
    faces.sort(key=lambda f: f.edges)        # a point is tried on the simplest faces near it first
    np = require("numpy", "symmetry")
    elslib = require("OCP.ElSLib", "symmetry").ElSLib
    topabs = require("OCP.TopAbs", "symmetry")
    low, high = [], []
    for face in faces:               # the box of each face, from its geometry (a triangulation can fall short of it)
        box = bnd.Bnd_Box()
        bndlib.BRepBndLib.Add_s(face.shape, box, False)
        x0, y0, z0, x1, y1, z1 = box.Get()
        low.append((x0, y0, z0))
        high.append((x1, y1, z1))
    low, high = np.array(low), np.array(high)
    spent = [0]

    def on_face(face: _Face, pnt) -> float:
        """Distance from ``pnt`` to its foot on the face's surface when that foot is inside the trimmed face
        (an upper bound of the distance to the face, exact for a plane, cylinder and sphere), else ``inf``."""
        u, v = elslib.Parameters_s(getattr(face.surface, face.kind.title())(), pnt)
        if face.inside.Perform(gp.gp_Pnt2d(u, v)) not in (topabs.TopAbs_IN, topabs.TopAbs_ON):
            return math.inf
        return float(pnt.Distance(face.surface.Value(u, v)))

    def distance(q: Sequence[float], limit: float) -> float:
        """Distance from ``q`` to the nearest face among those whose box comes within ``limit`` of it (``inf``
        when none does): each point is measured against the few faces near it, not against all of them. A
        foot inside a face settles it; only a point no face settles that way is given to
        ``BRepExtrema_DistShapeShape`` (which also measures to the face's edges), the simplest faces first."""
        at = np.array(q)
        near = [faces[int(i)] for i in np.nonzero(np.all((low - limit <= at) & (at <= high + limit), axis=1))[0]]
        spent[0] += len(near)
        if spent[0] > MAX_DISTANCES:
            raise _Refused(f"more than {MAX_DISTANCES} point-to-face distances (the work limit)")
        pnt = gp.gp_Pnt(*q)
        best = math.inf
        for face in near:
            best = min(best, on_face(face, pnt))
            if best <= limit * 1e-3:
                return best
        if best <= limit:
            return best
        vertex = builder.BRepBuilderAPI_MakeVertex(pnt).Vertex()
        for face in near:
            dist = extrema.BRepExtrema_DistShapeShape(vertex, face.shape)
            if not dist.IsDone() or dist.NbSolution() < 1:
                raise RuntimeError("BRepExtrema_DistShapeShape gave no distance")
            best = min(best, float(dist.Value()))
            if best <= limit * 1e-3:
                break
        return best

    def boundary_off(degrees: float, limit: float) -> Optional[float]:
        """Largest distance of a boundary point, rotated either way, from the faces; None once one is beyond
        ``limit`` (that point is then tried first at the next angle: the points that tell angles apart are few)."""
        worst = 0.0
        turns = (rotation(origin, unit, degrees), rotation(origin, unit, -degrees))
        for i, p in enumerate(points):
            for m in turns:
                d = distance(_apply(m, p), limit)
                if d > limit:
                    points.insert(0, points.pop(i))
                    return None
                worst = max(worst, d)
        return worst

    def volume_off(degrees: float, limit: float) -> Optional[float]:
        """Volume of the solid outside its rotated copy (the larger of the cut's own volume and the solid's
        less the shared volume), or None when either, with the integration error estimates, is over ``limit``."""
        turned = topods.Moved(toploc.TopLoc_Location(_trsf(_rotation_rows(origin, unit, degrees))))
        outside, outside_error = _volume(_boolean("cut", topods, turned))
        if outside + outside_error > limit:
            return None
        shared, shared_error = _volume(_boolean("common", topods, turned))
        unshared = abs(volume - shared)
        if unshared + volume_error + shared_error > limit:
            if volume_error + shared_error > limit:
                raise _Refused(f"the volume integration error estimate ({volume_error + shared_error:.3g} mm3) is "
                               f"over the {limit:.3g} mm3 limit, so the volumes cannot be compared that closely")
            return None
        return max(outside, unshared)

    def found(order: int, angles: Sequence[float], diff: float, off: float, lim3: float, lim: float) -> Symmetry:
        return Symmetry(order, round(diff, 9), round(off, 9), tuple(round(a, 9) for a in angles),
                        float(f"{lim3:.6g}"), float(f"{lim:.6g}"), len(points))

    # -- a body of revolution: three generic angles, the point tests first (a boolean costs far more)
    lim, lim3 = limit_mm * _GENERIC_SHARE, limit_mm3 * _GENERIC_SHARE
    offs = []
    for a in GENERIC_DEG:
        off = boundary_off(a, lim)
        if off is None:
            break
        offs.append(off)
    else:
        diffs = [volume_off(a, lim3) for a in GENERIC_DEG]
        if all(d is not None for d in diffs):
            return found(0, GENERIC_DEG, max(diffs), max(offs), lim3, lim)

    # -- a repeating pattern: the finest period first (its divisors repeat too)
    refused = 0
    for order in orders:
        angle, steps = 360.0 / order, order / 2.0
        lim, lim3 = limit_mm / steps, limit_mm3 / steps
        off = boundary_off(angle, lim)
        if off is None:
            continue
        if order // 2 > 1 and boundary_off(angle * (order // 2), limit_mm) is None:
            continue                                  # one step looked the same and half a turn does not: a drift
        diff = volume_off(angle, lim3)
        if diff is None:
            refused += 1
            if refused >= _MAX_REFUSED:
                raise _Refused(f"{refused} periods passed the boundary points and not the volume test")
            continue
        return found(order, (angle,), diff, off, lim3, lim)
    return Symmetry(1, points=len(points), reason="no rotation about the axis leaves it unchanged within the limits")
