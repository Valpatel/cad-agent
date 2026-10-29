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

What counts as a hole: wall faces that reach at least ``min_arc_deg`` (200 degrees) around the circle (360 less the
largest gap between them, so a rib right across a hole, which splits its wall into two opposite arcs, still leaves a
hole), with a diameter up to ``max_diameter_mm`` (30 mm: fastener holes, counterbores, insert bores, pins, small bearing
seats). A concave fillet (90 degrees) or a rounded slot end (180 degrees) is not a hole, and nor is a boss (convex
cylinder). Faces on one axis line are one bore where their axial ranges overlap or are less than the larger of 5 mm and
the diameter apart, so a rib across a counterbore is inside the bore, while coaxial holes in opposite walls of a box
stay separate. Two same-size bores with a smaller hole through the solid between them are a stepped bore: a **ledge**,
reported for a person to confirm (``ledges`` in the result), not failed.

Limits, stated in every result (``LIMITS``):

* cylindrical holes only (not tapered, polygonal or helical-thread geometry);
* material inside the hole's own wall is measured, not tool or screw-head clearance beyond it;
* a hole capped at one end by a later feature reads as a blind hole, and a rib that blocks a counterbore completely
  while a smaller hole is cut through it reads as a ledge: geometry alone cannot tell them from designed ones, so
  review the ``ledges`` list and the blind holes in a section view;
* concentric openings under ``max_diameter_mm`` that are not holes (a small fan guard's rings, a recess around a post)
  fail: list them in ``exceptions`` with the reason or lower ``max_diameter_mm`` for the part's project.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cadagent._deps import require

VERSION = 2
TOL_MM = 0.05
MIN_VOLUME_MM3 = 0.05
MIN_ARC_DEG = 200.0
MAX_DIAMETER_MM = 30.0
LIMITS = ("cylindrical holes only (not tapered, polygonal or helical-thread geometry)",
          "material inside each hole's own wall is measured, not tool or screw-head clearance beyond it",
          "a hole capped at one end reads as blind, and a counterbore blocked right across with a smaller hole cut "
          "through reads as a ledge: check the ledges and blind holes by eye",
          "concentric openings up to max_diameter_mm that are not holes (small fan-guard rings) need an exception",
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
    span_deg: float = 0.0                   # how far round the circle the wall reaches: 360 less the largest gap
    pieces: List[Tuple[float, float, float, float]] = field(default_factory=list, repr=False)  # (t0, t1, a0, a1) per face

    def to_dict(self) -> Dict[str, Any]:
        lo = [o + self.t0 * a for o, a in zip(self.origin, self.axis)]
        hi = [o + self.t1 * a for o, a in zip(self.origin, self.axis)]
        return {"diameter_mm": round(2 * self.radius, 3), "axis": [round(a, 6) for a in self.axis],
                "from_mm": [round(v, 3) for v in lo], "to_mm": [round(v, 3) for v in hi],
                "depth_mm": round(self.t1 - self.t0, 3), "faces": self.faces, "arc_deg": round(self.arc_deg, 1),
                "span_deg": round(self.span_deg, 1)}


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


def find_bores(shape: Any, line_tol: float = 1e-3, ledges: Optional[List[Dict[str, Any]]] = None) -> List[Bore]:
    """Every concave cylindrical bore in ``shape`` (a CadQuery shape or TopoDS_Shape). Stepped bores split at a ledge
    append the ledge to ``ledges`` when given."""
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
    lines: Dict[Tuple, List[Bore]] = {}
    for key, b in bores.items():
        lines.setdefault(key[1:], []).append(b)
    out: List[Bore] = []
    for key, b in bores.items():
        out.extend(_split(b, [o for o in lines[key[1:]] if o.radius < b.radius], ledges))
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
    return _arc_stats(arcs)[0]


def _arc_stats(arcs: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """(covered degrees, span degrees) of a set of angular intervals: the span is 360 less the largest uncovered gap."""
    two = 2 * math.pi
    spans = []
    for a0, a1 in arcs:
        if a1 - a0 >= two - 1e-9:
            return 360.0, 360.0
        s = a0 % two
        e = s + (a1 - a0)
        spans += [(s, min(e, two))] + ([(0.0, e - two)] if e > two else [])
    spans.sort()
    merged: List[List[float]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1] + 1e-9:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    if not merged:
        return 0.0, 0.0
    total = sum(e - s for s, e in merged)
    gaps = [merged[k + 1][0] - merged[k][1] for k in range(len(merged) - 1)]
    gaps.append(merged[0][0] + two - merged[-1][1])               # around through 0
    return math.degrees(total), math.degrees(two - max(gaps))


def _split(b: Bore, smaller: Sequence[Bore] = (), ledges: Optional[List[Dict[str, Any]]] = None) -> List[Bore]:
    """Faces on one axis line, cut into separate bores where their axial ranges are apart.

    Ranges that overlap are one bore. Across a short gap (up to the larger of 5 mm and the diameter) they are one bore
    with something blocking it, unless a smaller coaxial hole runs through the gap: that is a stepped bore (a ledge
    or shoulder with the screw's clearance hole through it), and the two sides are separate holes."""
    gap = max(5.0, 2 * b.radius)
    eps = 1e-3

    def stepped(t0: float, t1: float) -> bool:
        return any(q[0] <= t0 + eps and q[1] >= t1 - eps for o in smaller for q in o.pieces)

    pieces = sorted(b.pieces)
    groups: List[List[Tuple[float, float, float, float]]] = []
    for pc in pieces:
        end = max(q[1] for q in groups[-1]) if groups else None
        if groups and (pc[0] <= end + eps or (pc[0] <= end + gap and not stepped(end, pc[0]))):
            groups[-1].append(pc)
        else:
            if groups and pc[0] <= end + gap and ledges is not None:
                at = [o + (end + pc[0]) / 2 * a for o, a in zip(b.origin, b.axis)]
                ledges.append({"diameter_mm": round(2 * b.radius, 3), "at_mm": [round(v, 3) for v in at],
                               "axis": [round(a, 6) for a in b.axis], "thickness_mm": round(pc[0] - end, 3)})
            groups.append([pc])
    out = []
    for g in groups:
        cov, span = _arc_stats([(q[2], q[3]) for q in g])
        nb = Bore(origin=b.origin, axis=b.axis, radius=b.radius, t0=min(q[0] for q in g), t1=max(q[1] for q in g),
                  faces=len(g), arc_deg=cov, span_deg=span, pieces=g)
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


def holes(shape: Any, min_arc_deg: float = MIN_ARC_DEG, max_diameter_mm: float = MAX_DIAMETER_MM,
          ledges: Optional[List[Dict[str, Any]]] = None) -> List[Bore]:
    """The bores of ``shape`` that count as holes (see the module notes)."""
    found: List[Dict[str, Any]] = []
    out = [b for b in find_bores(shape, ledges=found) if b.span_deg >= min_arc_deg and 2 * b.radius <= max_diameter_mm]
    if ledges is not None:
        ledges.extend(l for l in found if l["diameter_mm"] <= max_diameter_mm)
    return out


def check_shape(shape: Any, tol_mm: float = TOL_MM, min_volume_mm3: float = MIN_VOLUME_MM3,
                exceptions: Sequence[Dict[str, Any]] = (), min_arc_deg: float = MIN_ARC_DEG,
                max_diameter_mm: float = MAX_DIAMETER_MM) -> Dict[str, Any]:
    """Check every hole of one shape. Returns ``{pass, holes, findings, excepted, ...}``."""
    ledges: List[Dict[str, Any]] = []
    bores = holes(shape, min_arc_deg, max_diameter_mm, ledges)
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
    return {"pass": not findings, "holes": len(bores), "findings": findings, "excepted": excepted, "ledges": ledges,
            "tol_mm": tol_mm, "min_volume_mm3": min_volume_mm3, "min_arc_deg": min_arc_deg,
            "max_diameter_mm": max_diameter_mm}


def load_step(path: Path) -> Any:
    cq = require("cadquery", "the hole-clearance check")
    roots = cq.importers.importStep(str(path)).vals()
    return roots[0] if len(roots) == 1 else cq.Compound.makeCompound(roots)


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


EXCEPTION_KEYS = {"at", "diameter_mm", "radius_mm", "reason"}


def config(project, known_parts: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """``cad: holes:`` with defaults, validated. Raises ``CadConfigError`` on a bad value. With ``known_parts``, part
    names in ``exceptions`` and ``skip`` must be among them (a misspelt name would silently except nothing)."""
    from cadagent.project import CadConfigError

    cfg = dict(getattr(project, "holes", None) or {})
    unknown = set(cfg) - {"tol_mm", "min_volume_mm3", "min_arc_deg", "max_diameter_mm", "exceptions", "skip"}
    if unknown:
        raise CadConfigError(f"cad.holes: unknown keys {sorted(unknown)}")
    out: Dict[str, Any] = {}
    for key, default, lo, hi in (("tol_mm", TOL_MM, 1e-4, 1.0), ("min_volume_mm3", MIN_VOLUME_MM3, 0.0, 1e6),
                                 ("min_arc_deg", MIN_ARC_DEG, 90.0, 360.0), ("max_diameter_mm", MAX_DIAMETER_MM, 0.1, 1e4)):
        try:
            out[key] = float(cfg.get(key, default))
        except (TypeError, ValueError):
            raise CadConfigError(f"cad.holes.{key} must be a number") from None
        if not lo <= out[key] <= hi:
            raise CadConfigError(f"cad.holes.{key} must be between {lo:g} and {hi:g}")
    exc = cfg.get("exceptions") or {}
    if not isinstance(exc, dict):
        raise CadConfigError("cad.holes.exceptions must map part -> [{at: [x, y, z], diameter_mm, radius_mm, reason}]")
    for part, items in exc.items():
        if not isinstance(items, list):
            raise CadConfigError(f"cad.holes.exceptions.{part} must be a list")
        for it in items:
            if not isinstance(it, dict) or not str(it.get("reason") or "").strip():
                raise CadConfigError(f"cad.holes.exceptions.{part}: every exception needs a reason")
            if set(it) - EXCEPTION_KEYS:
                raise CadConfigError(f"cad.holes.exceptions.{part}: unknown keys {sorted(set(it) - EXCEPTION_KEYS)}")
            if it.get("at") is None and it.get("diameter_mm") is None:
                raise CadConfigError(f"cad.holes.exceptions.{part}: give at: [x, y, z] and/or diameter_mm")
            at = it.get("at")
            if at is not None and (not isinstance(at, list) or len(at) != 3
                                   or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in at)):
                raise CadConfigError(f"cad.holes.exceptions.{part}: at must be [x, y, z] numbers (mm, part coordinates)")
            for k in ("diameter_mm", "radius_mm"):
                v = it.get(k)
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0):
                    raise CadConfigError(f"cad.holes.exceptions.{part}: {k} must be a positive number")
    skip = cfg.get("skip") or {}
    if not isinstance(skip, dict) or not all(str(v or "").strip() for v in skip.values()):
        raise CadConfigError("cad.holes.skip must map part -> reason")
    if known_parts is not None:
        stray = sorted((set(exc) | set(skip)) - set(known_parts))
        if stray:
            raise CadConfigError(f"cad.holes: no such part(s) {stray} (parts: {sorted(known_parts)})")
    out["exceptions"], out["skip"] = exc, {k: str(v) for k, v in skip.items()}
    return out


def config_key(cfg: Dict[str, Any]) -> str:
    """Binds a result to the check's version and settings: a change to either makes old results stale."""
    return hashlib.sha256(json.dumps({"version": VERSION, "config": cfg}, sort_keys=True).encode()).hexdigest()


def check_project(project, parts: Optional[Sequence[str]] = None, out: Optional[Path] = None) -> Dict[str, Any]:
    """Check every part's ``exports/<part>.step`` (or only ``parts``, kept with the other rows of a current result) and
    write ``exports/hole-checks.json`` (or ``out``)."""
    from cadagent.project import CadConfigError
    from cadagent.report import load_parts

    known, error = load_parts(project)
    if error:
        raise ValueError(error)
    cfg = config(project, list(known))
    key = config_key(cfg)
    tol, vmin, exc, skip = cfg["tol_mm"], cfg["min_volume_mm3"], cfg["exceptions"], cfg["skip"]
    stray = sorted(set(parts or ()) - set(known))
    if stray:
        raise CadConfigError(f"no such part(s) {stray}")
    path = Path(out) if out else project.exports_dir / "hole-checks.json"
    rows: Dict[str, Any] = {}
    if parts and path.is_file():                 # a partial run keeps the other parts' rows from a result made the same way
        try:
            old = json.loads(path.read_text())
            if old.get("version") == VERSION and old.get("config_key") == key:
                rows = {k: v for k, v in (old.get("parts") or {}).items() if k in known}
        except (OSError, json.JSONDecodeError):
            rows = {}
    for name in list(parts or known):
        step = project.exports_dir / f"{name}.step"
        if name in skip:
            rows[name] = {"pass": True, "skipped": skip[name]}
            continue
        if not step.is_file():
            rows[name] = {"pass": False, "error": f"{step.name} not found: export each part's STEP, or list the part "
                                                  "in cad.holes.skip with the reason"}
            continue
        try:
            r = check_shape(load_step(step), tol, vmin, exc.get(name) or (), cfg["min_arc_deg"], cfg["max_diameter_mm"])
        except Exception as e:     # a kernel failure must fail the row, never pass it
            r = {"pass": False, "error": f"{type(e).__name__}: {e}"}
        r["step"] = step.name
        r["sha256"] = _sha(step)
        rows[name] = r
    report = {"version": VERSION, "check": "holes clear", "config_key": key, "limits": list(LIMITS), "parts": rows,
              "pass": all(r.get("pass") for r in rows.values())}
    path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def current(project, part: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """The recorded result for ``part`` if it was made from the STEP on disk now with the current settings, else
    ``(None, why)``. A skipped part or a missing STEP is returned as recorded (the row says which)."""
    from cadagent.project import CadConfigError
    from cadagent.report import load_parts

    path = project.exports_dir / "hole-checks.json"
    if not path.is_file():
        return None, "not run (cad-agent holes)"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return None, f"unreadable {path.name}: {e}"
    try:
        known, _ = load_parts(project)
        key = config_key(config(project, list(known) or None))
    except CadConfigError as e:
        return None, f"config error: {e}"
    if data.get("version") != VERSION or data.get("config_key") != key:
        return None, "stale: the check or cad.holes changed since it ran"
    row = (data.get("parts") or {}).get(part)
    if row is None:
        return None, "part not checked"
    if row.get("skipped"):
        return row, ""
    step = project.exports_dir / f"{part}.step"
    if not step.is_file():
        return (row, "") if row.get("error") else (None, f"{step.name} not found")
    if _sha(step) != row.get("sha256"):
        return None, "stale: the STEP changed since the check ran"
    return row, ""
