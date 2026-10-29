"""Hole-clearance check: every hole in a part is empty of material.

A rib, boss or skirt added to a part *after* its fastener holes were cut refills part of the hole: the part is still a
valid watertight solid, every fit and strength check passes, and the screw head will not seat. This check finds that
from the B-rep alone, with no declaration from the project.

Method:

* A **bore** is a set of concave cylindrical faces (the part's material outside the cylinder, the face normal pointing
  at the axis) on one axis line with one radius. Faces a feature split apart (a rib across a counterbore leaves the
  bore's wall in pieces) group back together.
* Each bore is probed with a cylinder ``tol_mm`` smaller in radius, spanning the bore's full axial extent (from the
  lowest to the highest point of any of its faces, less ``tol_mm`` at each end). The volume the probe shares with the
  part is material inside the hole.
* A bore with more than ``min_volume_mm3`` inside fails; the finding gives its axis, diameter, axial range, the
  intrusion volume and the intrusion's centre, so it can be found in a viewer.

What counts as a hole: wall faces covering at least ``min_arc_deg`` (200 degrees) of the circle once they are joined,
so a concave fillet (90 degrees) or a rounded slot end (180 degrees) is not one, and a diameter up to
``max_diameter_mm`` (30 mm: fastener holes, counterbores, insert bores, pins, small bearing seats; a fan grille's ring
openings are larger and are crossed by spokes on purpose). A boss (convex cylinder) is not a hole. Faces on one axis
line are one bore where their axial ranges overlap or are less than ``merge_gap_mm`` (the larger of 5 mm and the
diameter) apart, so a rib across a counterbore is inside the bore, while coaxial holes in opposite walls of a box stay
separate. A thin solid layer across a bore on purpose (a sacrificial bridge layer) reads as an intrusion: list it in
``exceptions`` with the reason.

Limits, stated in every result: cylindrical holes only (not tapered, threaded-as-helix or polygonal holes); the probe
measures material inside the hole's own wall, not clearance for a tool or a screw head beyond it.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cadagent._deps import require

VERSION = 1
TOL_MM = 0.05
MIN_VOLUME_MM3 = 0.05
MIN_ARC_DEG = 200.0
MAX_DIAMETER_MM = 30.0
LIMITS = ("cylindrical holes only (not tapered, polygonal or helical-thread geometry)",
          "material inside each hole's own wall is measured, not tool or screw-head clearance beyond it",
          "the model, not the print: no shrink, elephant foot or support material")


@dataclass
class Bore:
    """One hole: an axis line, a radius and the concave cylindrical faces that make its wall."""
    origin: Tuple[float, float, float]      # a point on the axis (the foot of the perpendicular from the world origin)
    axis: Tuple[float, float, float]        # unit vector, sign fixed (first non-zero component positive)
    radius: float
    t0: float = math.inf                    # axial extent along ``axis`` from ``origin``
    t1: float = -math.inf
    faces: int = 0
    arc_deg: float = 0.0                    # angular coverage of the wall faces, joined (360 for a full hole)
    pieces: List[Tuple[float, float, float, float]] = field(default_factory=list, repr=False)  # (t0, t1, a0, a1) per face

    def to_dict(self) -> Dict[str, Any]:
        lo = [o + self.t0 * a for o, a in zip(self.origin, self.axis)]
        hi = [o + self.t1 * a for o, a in zip(self.origin, self.axis)]
        return {"diameter_mm": round(2 * self.radius, 3), "axis": [round(a, 6) for a in self.axis],
                "from_mm": [round(v, 3) for v in lo], "to_mm": [round(v, 3) for v in hi],
                "depth_mm": round(self.t1 - self.t0, 3), "faces": self.faces, "arc_deg": round(self.arc_deg, 1)}


def _canonical(axis) -> Tuple[float, float, float]:
    v = [axis.X(), axis.Y(), axis.Z()]
    n = math.sqrt(sum(c * c for c in v))
    v = [c / n for c in v]
    for c in v:
        if abs(c) > 1e-9:
            if c < 0:
                v = [-x for x in v]
            break
    return tuple(v)


def _foot(point, axis) -> Tuple[float, float, float]:
    """The point on the line through ``point`` along ``axis`` nearest the world origin."""
    p = (point.X(), point.Y(), point.Z())
    t = sum(pc * ac for pc, ac in zip(p, axis))
    return tuple(pc - t * ac for pc, ac in zip(p, axis))


def find_bores(shape: Any, line_tol: float = 1e-3) -> List[Bore]:
    """Every hole in ``shape`` (a CadQuery shape or TopoDS_Shape) as a list of bores."""
    require("OCP", "the hole-clearance check")
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    wrapped = getattr(shape, "wrapped", shape)
    bores: Dict[Tuple, Bore] = {}
    exp = TopExp_Explorer(wrapped, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        exp.Next()
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() != GeomAbs_Cylinder:
            continue
        cyl = surf.Cylinder()
        pos, r = cyl.Position(), cyl.Radius()
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
        um, vm = (umin + umax) / 2, (vmin + vmax) / 2
        p, d1u, d1v = gp_Pnt(), gp_Vec(), gp_Vec()
        surf.D1(um, vm, p, d1u, d1v)
        n = d1u.Crossed(d1v)
        if n.Magnitude() < 1e-12:
            continue
        if face.Orientation() == TopAbs_REVERSED:
            n.Reverse()
        loc = pos.Location()
        ax = pos.Direction()
        # radial vector from the surface point to the axis
        w = gp_Vec(p, loc)
        along = w.Dot(gp_Vec(ax))
        to_axis = w.Subtracted(gp_Vec(ax).Multiplied(along))
        if n.Dot(to_axis) <= 0:      # outward normal points away from the axis: a boss, not a hole
            continue
        axis = _canonical(ax)
        origin = _foot(loc, axis)
        key = (round(r / line_tol), tuple(round(c / 1e-6) for c in axis), tuple(round(c / line_tol) for c in origin))
        b = bores.get(key)
        if b is None:
            b = bores[key] = Bore(origin=origin, axis=axis, radius=r)
        # axial extent of this face in the bore's frame: the cylinder's V is along its own direction from its location
        sign = 1.0 if sum(a * c for a, c in zip(axis, (ax.X(), ax.Y(), ax.Z()))) > 0 else -1.0
        base = sum((lc - oc) * a for lc, oc, a in zip((loc.X(), loc.Y(), loc.Z()), origin, axis))
        ta, tb = base + sign * vmin, base + sign * vmax
        # angular range of the face in a frame fixed by the bore's axis, so faces of one hole line up
        e1 = _perpendicular(axis)
        e2 = _cross(axis, e1)
        xd, yd = pos.XDirection(), pos.YDirection()
        X, Y = (xd.X(), xd.Y(), xd.Z()), (yd.X(), yd.Y(), yd.Z())
        p0 = [math.cos(umin) * xc + math.sin(umin) * yc for xc, yc in zip(X, Y)]
        a0 = math.atan2(_dot(p0, e2), _dot(p0, e1))
        span = umax - umin
        if _dot(_cross(X, Y), axis) < 0:
            a0 -= span
        b.pieces.append((min(ta, tb), max(ta, tb), a0, a0 + span))
    out: List[Bore] = []
    for b in bores.values():
        out.extend(_split(b))
    return out


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b) -> Tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _perpendicular(axis) -> Tuple[float, float, float]:
    world = min(((1, 0, 0), (0, 1, 0), (0, 0, 1)), key=lambda w: abs(_dot(w, axis)))
    v = _cross(axis, world)
    n = math.sqrt(_dot(v, v))
    return tuple(c / n for c in v)


def _coverage(arcs: Sequence[Tuple[float, float]]) -> float:
    """Degrees of the circle covered by the union of angular intervals (radians, any start)."""
    two = 2 * math.pi
    spans = []
    for a0, a1 in arcs:
        if a1 - a0 >= two - 1e-9:
            return 360.0
        s = a0 % two
        e = s + (a1 - a0)
        spans += [(s, min(e, two))] + ([(0.0, e - two)] if e > two else [])
    spans.sort()
    total, cur_s, cur_e = 0.0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e + 1e-9:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return math.degrees(total)


def _split(b: Bore) -> List[Bore]:
    """Faces on one axis line, cut into separate bores where their axial ranges are far apart."""
    gap = max(5.0, 2 * b.radius)
    pieces = sorted(b.pieces)
    groups: List[List[Tuple[float, float, float, float]]] = []
    for pc in pieces:
        if groups and pc[0] <= max(q[1] for q in groups[-1]) + gap:
            groups[-1].append(pc)
        else:
            groups.append([pc])
    out = []
    for g in groups:
        nb = Bore(origin=b.origin, axis=b.axis, radius=b.radius, t0=min(q[0] for q in g), t1=max(q[1] for q in g),
                  faces=len(g), arc_deg=_coverage([(q[2], q[3]) for q in g]), pieces=g)
        if nb.t1 > nb.t0:
            out.append(nb)
    return out


def probe(shape: Any, bore: Bore, tol_mm: float = TOL_MM) -> Tuple[float, Optional[List[float]]]:
    """Volume of ``shape`` inside ``bore`` (shrunk by ``tol_mm``) and the centre of that material."""
    cq = require("cadquery", "the hole-clearance check")
    r, h = bore.radius - tol_mm, bore.t1 - bore.t0 - 2 * tol_mm
    if r <= 0 or h <= 0:
        return 0.0, None
    start = [o + (bore.t0 + tol_mm) * a for o, a in zip(bore.origin, bore.axis)]
    probe_ = cq.Solid.makeCylinder(r, h, cq.Vector(*start), cq.Vector(*bore.axis))
    solid = shape if hasattr(shape, "intersect") else cq.Shape.cast(shape)
    common = solid.intersect(probe_)
    vol = common.Volume()
    if vol <= 0:
        return 0.0, None
    c = common.Center()
    return vol, [round(c.x, 3), round(c.y, 3), round(c.z, 3)]


def _excepted(bore: Bore, exceptions: Sequence[Dict[str, Any]]) -> Optional[str]:
    for ex in exceptions:
        at, dia = ex.get("at"), ex.get("diameter_mm")
        if dia is not None and abs(float(dia) - 2 * bore.radius) > 0.01:
            continue
        if at is not None:
            # distance from the point to the bore's axis line
            v = [float(p) - o for p, o in zip(at, bore.origin)]
            t = sum(vc * a for vc, a in zip(v, bore.axis))
            dist = math.sqrt(max(0.0, sum(vc * vc for vc in v) - t * t))
            if dist > float(ex.get("radius_mm", 0.5)):
                continue
        return str(ex.get("reason") or "listed as an exception")
    return None


def holes(shape: Any, min_arc_deg: float = MIN_ARC_DEG, max_diameter_mm: float = MAX_DIAMETER_MM) -> List[Bore]:
    """The bores of ``shape`` that count as holes (see the module notes)."""
    return [b for b in find_bores(shape) if b.arc_deg >= min_arc_deg and 2 * b.radius <= max_diameter_mm]


def check_shape(shape: Any, tol_mm: float = TOL_MM, min_volume_mm3: float = MIN_VOLUME_MM3,
                exceptions: Sequence[Dict[str, Any]] = (), min_arc_deg: float = MIN_ARC_DEG,
                max_diameter_mm: float = MAX_DIAMETER_MM) -> Dict[str, Any]:
    """Check every hole of one shape. Returns ``{pass, holes, findings, excepted, ...}``."""
    bores = holes(shape, min_arc_deg, max_diameter_mm)
    findings, excepted = [], []
    for b in bores:
        vol, centre = probe(shape, b, tol_mm)
        if vol <= min_volume_mm3:
            continue
        item = dict(b.to_dict(), intrusion_mm3=round(vol, 3), intrusion_centre_mm=centre)
        if b.arc_deg < 359.0 and b.faces == 1:
            item["hint"] = ("the wall is one face with a gap, along the hole's full depth: a D-flat or key cut on "
                            "purpose? If so, list it in cad.holes.exceptions with the reason")
        reason = _excepted(b, exceptions)
        if reason:
            excepted.append(dict(item, reason=reason))
        else:
            findings.append(item)
    findings.sort(key=lambda f: -f["intrusion_mm3"])
    return {"pass": not findings, "holes": len(bores), "findings": findings, "excepted": excepted,
            "tol_mm": tol_mm, "min_volume_mm3": min_volume_mm3, "min_arc_deg": min_arc_deg,
            "max_diameter_mm": max_diameter_mm}


def load_step(path: Path) -> Any:
    cq = require("cadquery", "the hole-clearance check")
    return cq.importers.importStep(str(path)).val()


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def config(project) -> Dict[str, Any]:
    """``cad: holes:`` with defaults, validated. Raises ``CadConfigError`` on a bad value."""
    from cadagent.project import CadConfigError

    cfg = dict(getattr(project, "holes", None) or {})
    unknown = set(cfg) - {"tol_mm", "min_volume_mm3", "min_arc_deg", "max_diameter_mm", "exceptions", "skip"}
    if unknown:
        raise CadConfigError(f"cad.holes: unknown keys {sorted(unknown)}")
    out: Dict[str, Any] = {}
    for key, default in (("tol_mm", TOL_MM), ("min_volume_mm3", MIN_VOLUME_MM3), ("min_arc_deg", MIN_ARC_DEG),
                         ("max_diameter_mm", MAX_DIAMETER_MM)):
        try:
            out[key] = float(cfg.get(key, default))
        except (TypeError, ValueError):
            raise CadConfigError(f"cad.holes.{key} must be a number") from None
        if out[key] < 0:
            raise CadConfigError(f"cad.holes.{key} must not be negative")
    exc = cfg.get("exceptions") or {}
    if not isinstance(exc, dict):
        raise CadConfigError("cad.holes.exceptions must map part -> [{at: [x, y, z], diameter_mm, reason}]")
    for part, items in exc.items():
        if not isinstance(items, list):
            raise CadConfigError(f"cad.holes.exceptions.{part} must be a list")
        for it in items:
            if not isinstance(it, dict) or not str(it.get("reason") or "").strip():
                raise CadConfigError(f"cad.holes.exceptions.{part}: every exception needs a reason")
            if it.get("at") is None and it.get("diameter_mm") is None:
                raise CadConfigError(f"cad.holes.exceptions.{part}: give at: [x, y, z] and/or diameter_mm")
            if it.get("at") is not None and (not isinstance(it["at"], list) or len(it["at"]) != 3):
                raise CadConfigError(f"cad.holes.exceptions.{part}: at must be [x, y, z] (mm, part coordinates)")
    skip = cfg.get("skip") or {}
    if not isinstance(skip, dict) or not all(str(v or "").strip() for v in skip.values()):
        raise CadConfigError("cad.holes.skip must map part -> reason")
    out["exceptions"], out["skip"] = exc, {k: str(v) for k, v in skip.items()}
    return out


def check_project(project, parts: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Check every part's ``exports/<part>.step`` and write ``exports/hole-checks.json``."""
    from cadagent.report import load_parts

    cfg = config(project)
    tol, vmin, exc, skip = cfg["tol_mm"], cfg["min_volume_mm3"], cfg["exceptions"], cfg["skip"]
    known, error = load_parts(project)
    if error:
        raise ValueError(error)
    names = list(parts or known)
    rows: Dict[str, Any] = {}
    for name in names:
        if name in skip:
            rows[name] = {"pass": True, "skipped": skip[name]}
            continue
        step = project.exports_dir / f"{name}.step"
        if not step.is_file():
            rows[name] = {"pass": False, "error": f"{step.name} not found (the check reads each part's STEP)"}
            continue
        try:
            r = check_shape(load_step(step), tol, vmin, exc.get(name) or (), cfg["min_arc_deg"], cfg["max_diameter_mm"])
        except Exception as e:     # a kernel failure must fail the row, never pass it
            r = {"pass": False, "error": f"{type(e).__name__}: {e}"}
        r["step"] = step.name
        r["sha256"] = _sha(step)
        rows[name] = r
    report = {"version": VERSION, "check": "holes clear", "limits": list(LIMITS), "parts": rows,
              "pass": all(r.get("pass") for r in rows.values())}
    out = project.exports_dir / "hole-checks.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    return report


def current(project, part: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """The recorded result for ``part`` if it was made from the STEP on disk now, else ``(None, why)``."""
    path = project.exports_dir / "hole-checks.json"
    if not path.is_file():
        return None, "not run (cad-agent holes)"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return None, f"unreadable {path.name}: {e}"
    row = (data.get("parts") or {}).get(part)
    if row is None:
        return None, "part not checked"
    step = project.exports_dir / f"{part}.step"
    if not step.is_file() or _sha(step) != row.get("sha256"):
        return None, "stale: the STEP changed since the check ran"
    return row, ""
