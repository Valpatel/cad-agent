"""Containment gate: every declared content instance inside its container's registered cavity.

A ``contains`` declaration says that ``count`` instances of part ``what`` sit in the cavity solid
``cavity`` of part ``container`` (a dossier card's ``contains:`` entry; the cavity is registered in
code by ``@cavity``). For each declaration, in each pose, the gate reports:

* **inside** (one check per instance): the instance against the cavity solid, from the cached
  pair query (``relate_pair``). Inside means at most ``Tolerances.contain_mm3`` of the instance
  lies outside the cavity; a ball resting tangent on a cavity wall has exactly 0 outside and
  passes. An escapee's evidence is the volume outside and the point furthest outside the cavity
  (its depth: distance from that point to the cavity);
* **wall** (one check per instance): the instance against the container's own solid. Touching
  is the intended rest; shared volume above ``overlap_mm3`` is a wall-piercing finding. This is
  independent of *inside*: a cavity drawn larger than the void reads every ball inside while the
  balls sit in the wall;
* **interpenetration** (one check per declaration): content instances sharing volume, with the
  overlap per pair;
* **count** (one check per declaration): the instances found against ``count``;
* **support** (one check per declaration, optional): every instance rests on the cavity or on
  another instance that does, followed down a chain. An instance *rests on* something when moving
  it ``support_mm`` along ``down`` pushes more than ``overlap_mm3`` into it (the cavity's
  outside, or the other instance). ``support="report"`` (default) makes an unsupported instance a
  warning, ``"fail"`` a failure, ``"off"`` skips the check;
* **cavity** (one check per declaration): the cavity is registered and belongs to the container.
  There is no derived cavity: a declaration without a registered cavity solid fails here with the
  dossier lint's code (``unknown-cavity`` or ``cavity-wrong-part``).

Instances are the assembly parts named ``what`` or ``what#0``, ``what#1``, ... (the dossier
registry's instance keys). Items that exist only as meshes (an STL with no B-rep) are passed in
``meshes`` under the same keys and take the **sample-only** path: points sampled in the mesh are
classified against the exact cavity and container solids, so their volumes are Monte Carlo
estimates with a standard error, and they get no interpenetration or support check.

Poses: ``poses={"name": {body: location, ...}}`` runs every check on the assembly with those
bodies moved (``Assembly.posed``, applied per body). A container that moves while its contents
are modelled in fixed positions is caught in the pose where they part. Check ids are prefixed
with ``<pose>/``.

Limits, stated in every verdict: the model is checked against its declared cavity, not the print;
the cavity solid is taken as the truth (a wrong cavity is only caught through the wall check);
the furthest-outside point is the furthest of a sampled set (vertices of a tessellation of the
escaped piece), so its depth is a lower bound to within the tessellation's deflection; support
is a static contact test along one direction, not a stability or settling simulation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require
from cadagent.gates.cache import PairCache, digest, matrix_key
from cadagent.gates.relations import (Assembly, Relation, Tolerances, _boolean, _kernel_version, _pt, _trsf,
                                      _volume, aabb_distances, bounding_box, relate_pair)
from cadagent.gates.verdict import Check, verdict, write_verdict

GATE = "containment"
VERSION = "1"            # bump when a cached support or escape record changes meaning
SUPPORT_MODES = ("off", "report", "fail")

ASSUMPTIONS = [
    "each content instance is tested against the registered cavity solid with non-destructive OCCT "
    "booleans (common and cut volumes, cross-checked); the cavity solid is taken as the declared truth",
    "inside means no more than contain_mm3 of the instance is outside the cavity; touching the cavity "
    "boundary is inside",
    "the wall check tests each instance against the container's solid: touching is allowed, shared volume "
    "above overlap_mm3 fails",
    "the point furthest outside is the furthest of the vertices of a tessellation of the escaped piece, "
    "so its depth is a lower bound to within the tessellation deflection",
    "support is a static contact test (the instance moved support_mm along `down` pushes into the cavity "
    "boundary or into a supported instance), not a settling or stability simulation",
    "mesh-only items are sample-only: Monte Carlo volume estimates against the exact solids, with no "
    "interpenetration or support check",
    "the model is checked, not the print: no tolerance stack, shrink or deflection",
]


# ----------------------------------------------------------------------------- declarations

@dataclass(frozen=True)
class Contains:
    """One ``contains`` declaration: ``count`` instances of part ``what`` in ``cavity`` of ``container``."""
    container: str
    cavity: str
    what: str
    count: Optional[int] = None
    free: bool = False

    def __post_init__(self):
        for f in ("container", "what"):
            if not getattr(self, f) or not isinstance(getattr(self, f), str):
                raise ValueError(f"a contains declaration needs a {f!r} name, got {getattr(self, f)!r}")
        if self.count is not None and (isinstance(self.count, bool) or not isinstance(self.count, int)
                                       or self.count < 0):
            raise ValueError(f"contains {self.what!r}: count must be a non-negative integer, got {self.count!r}")

    @classmethod
    def coerce(cls, item: Any, container: Optional[str] = None) -> "Contains":
        """From a ``Contains``, a mapping ``{container, cavity, what, count, free}`` or a dossier
        ``Containment`` (then ``container`` is the card's part id)."""
        if isinstance(item, Contains):
            return item
        get = item.get if isinstance(item, Mapping) else (lambda k, d=None: getattr(item, k, d))
        return cls(container=get("container") or container or "", cavity=get("cavity") or "",
                   what=get("what") or "", count=get("count"), free=bool(get("free", False)))

    def to_dict(self) -> Dict[str, Any]:
        return {"container": self.container, "cavity": self.cavity, "what": self.what, "count": self.count,
                "free": self.free}


def contains_declarations(dossier: Any) -> List[Contains]:
    """The ``contains`` entries of every part card of a loaded ``cadagent.dossier.Dossier``."""
    out = []
    for pid, card in dossier.parts.items():
        for c in card.contains:
            out.append(Contains.coerce(c, container=pid))
    return out


def instances(names: Iterable[str], what: str) -> List[str]:
    """The instance keys of part ``what`` among ``names``: ``what`` itself or ``what#<n>``, in index order."""
    pat = re.compile(rf"^{re.escape(what)}(?:#(\d+))?$")
    found = [(m.group(1), n) for n in names for m in [pat.match(n)] if m]
    return [n for _, n in sorted(found, key=lambda t: -1 if t[0] is None else int(t[0]))]


def posed_assembly(assembly: Assembly, locations: Mapping[str, Any]) -> Assembly:
    """``assembly`` with each body in ``locations`` moved by its location (``Assembly.posed`` per body)."""
    out = assembly
    for body, loc in locations.items():
        out = out.posed(body, loc)
    return out


# ----------------------------------------------------------------------------- kernel helpers

def _cached(cache: Optional[PairCache], key: Optional[str], compute):
    if cache is not None and key is not None:
        hit = cache.get(key)
        if hit is not None:
            return hit, True
    value = compute()
    if cache is not None and key is not None and not value.get("error"):
        cache.put(key, value)
    return value, False


def _key(kind: str, tol: Tolerances, *parts: str) -> str:
    return digest(GATE, kind, VERSION, _kernel_version(), tol.key(), *parts)


def _points_of(topods, deflection: float, max_points: int, angular: float = 0.1) -> List[Any]:
    """Vertices of a tessellation of a copy of ``topods`` (in its location; the caller's shape keeps
    its triangulation), thinned evenly to ``max_points``."""
    occ = {m: require(f"OCP.{m}", "the containment witness") for m in
           ("BRepMesh", "BRep", "TopExp", "TopAbs", "TopoDS", "TopLoc", "BRepBuilderAPI")}
    topods = occ["BRepBuilderAPI"].BRepBuilderAPI_Copy(topods, True, False).Shape()
    occ["BRepMesh"].BRepMesh_IncrementalMesh(topods, deflection, False, angular, True)
    pts = []
    ex = occ["TopExp"].TopExp_Explorer(topods, occ["TopAbs"].TopAbs_FACE)
    while ex.More():
        face = occ["TopoDS"].TopoDS.Face_s(ex.Current())
        loc = occ["TopLoc"].TopLoc_Location()
        tri = occ["BRep"].BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            trsf = loc.Transformation()
            for i in range(1, tri.NbNodes() + 1):
                pts.append(tri.Node(i).Transformed(trsf))
        ex.Next()
    ex = occ["TopExp"].TopExp_Explorer(topods, occ["TopAbs"].TopAbs_VERTEX)
    while ex.More():
        pts.append(occ["BRep"].BRep_Tool.Pnt_s(occ["TopoDS"].TopoDS.Vertex_s(ex.Current())))
        ex.Next()
    if len(pts) > max_points:
        step = len(pts) / max_points
        pts = [pts[int(i * step)] for i in range(max_points)]
    return pts


def _distances_to(points: Sequence[Any], solid) -> List[Tuple[float, Any]]:
    """Distance from each point to ``solid`` (0 inside), with the closest point on the solid."""
    builder = require("OCP.BRepBuilderAPI", "the containment witness")
    extrema = require("OCP.BRepExtrema", "the containment witness")
    out = []
    for p in points:
        d = extrema.BRepExtrema_DistShapeShape(builder.BRepBuilderAPI_MakeVertex(p).Vertex(), solid)
        d.Perform()
        if not d.IsDone() or d.NbSolution() < 1:
            raise RuntimeError("BRepExtrema_DistShapeShape did not converge on a witness point")
        out.append((float(d.Value()), d.PointOnShape2(1)))
    return out


def _contact_probe(item, cavity, deflection: float, max_points: int, touch_mm: float) -> Dict[str, Any]:
    """Independent check of a ``contains`` answer for an instance that touches the cavity boundary.

    Near-tangent surface pairs are where OCCT's surface intersection can miss a shallow crossing
    (seen: a sphere 0.03-0.1 mm through a cone wall read 0 mm3 outside at some positions), and a
    missed crossing gives a consistent common = volume, cut = 0. So the instance's tessellation
    vertices (on its true surface) are classified against the cavity (``BRepClass3d``, no surface
    intersection involved); a vertex outside by more than ``touch_mm`` proves an escape."""
    pts = _points_of(item, deflection, max_points)
    clf = _classifier(cavity)
    out = [p for p, st in zip(pts, _states(clf, [(p.X(), p.Y(), p.Z()) for p in pts], touch_mm)) if st == "out"]
    res: Dict[str, Any] = {"probe_points": len(pts), "probe_deflection_mm": deflection, "probe_outside": len(out)}
    if out:
        dists = _distances_to(out, cavity)
        i = max(range(len(out)), key=lambda k: dists[k][0])
        res.update(probe_depth_mm=round(dists[i][0], 6), probe_point=_pt(out[i]),
                   probe_cavity_point=_pt(dists[i][1]))
    return res


def _escape_witness(item, cavity, whole: bool, deflection: float, max_points: int) -> Dict[str, Any]:
    """The point of ``item`` furthest outside ``cavity`` (sampled), from the escaped piece."""
    piece = item if whole else _boolean("cut", item, cavity)
    pts = _points_of(piece, deflection, max_points)
    if not pts:
        return {"error": "the escaped piece has no tessellation points"}
    dists = _distances_to(pts, cavity)
    i = max(range(len(pts)), key=lambda k: dists[k][0])
    best = (dists[i][0], pts[i], dists[i][1])
    refined = 0
    for _ in range(3):              # climb: the piece's extreme point along (point - nearest cavity point)
        depth, p, q = best
        if depth <= 1e-9:
            break
        cand = _extreme_point(piece, p, q)
        if cand is None:
            break
        (d2, q2), = _distances_to([cand], cavity)
        if d2 <= depth + 1e-7:
            break
        best, refined = (d2, cand, q2), refined + 1
    depth, p, q = best
    return {"furthest_outside_point": _pt(p), "depth_mm": round(depth, 6), "nearest_cavity_point": _pt(q),
            "points_sampled": len(pts), "refinements": refined, "deflection_mm": deflection}


def _extreme_point(piece, p, q):
    """The point of ``piece`` furthest along the direction from ``q`` to ``p`` (closest to a far plane)."""
    gp = require("OCP.gp", "the containment witness")
    builder = require("OCP.BRepBuilderAPI", "the containment witness")
    extrema = require("OCP.BRepExtrema", "the containment witness")
    v = gp.gp_Vec(q, p)
    if v.Magnitude() < 1e-12:
        return None
    n = gp.gp_Dir(v)
    box = bounding_box(piece)
    size = max(box[3] - box[0], box[4] - box[1], box[5] - box[2], 1.0) * 4
    origin = gp.gp_Pnt(p.X() + n.X() * size, p.Y() + n.Y() * size, p.Z() + n.Z() * size)
    face = builder.BRepBuilderAPI_MakeFace(gp.gp_Pln(origin, n), -size, size, -size, size).Face()
    d = extrema.BRepExtrema_DistShapeShape(piece, face)
    d.Perform()
    if not d.IsDone() or d.NbSolution() < 1:
        return None
    return d.PointOnShape1(1)


def _shifted(topods, down: Sequence[float], dist: float):
    gp = require("OCP.gp", "the support check")
    toploc = require("OCP.TopLoc", "the support check")
    t = gp.gp_Trsf()
    t.SetTranslation(gp.gp_Vec(*(float(c) * dist for c in down)))
    return topods.Moved(toploc.TopLoc_Location(t))


def _unit(v: Sequence[float]) -> Tuple[float, float, float]:
    n = sum(float(c) ** 2 for c in v) ** 0.5
    if len(v) != 3 or n == 0:
        raise ValueError(f"down must be a non-zero 3-vector, got {v!r}")
    return tuple(float(c) / n for c in v)


# ----------------------------------------------------------------------------- sample-only (mesh items)

def _winding(tris, points, chunk: int = 2048):
    """Generalised winding number of a closed triangle mesh at each point (1 inside, 0 outside)."""
    np = require("numpy", "the sample-only containment check")
    out = np.zeros(len(points))
    for s in range(0, len(points), chunk):
        p = points[s:s + chunk, None, None, :]
        a, b, c = (tris[None, :, k, :] - p[:, :, 0, :] for k in range(3))
        la, lb, lc = (np.linalg.norm(x, axis=-1) for x in (a, b, c))
        det = np.einsum("ijk,ijk->ij", a, np.cross(b, c))
        den = (la * lb * lc + np.einsum("ijk,ijk->ij", a, b) * lc + np.einsum("ijk,ijk->ij", b, c) * la
               + np.einsum("ijk,ijk->ij", c, a) * lb)
        out[s:s + chunk] = np.arctan2(det, den).sum(axis=1) / (2 * np.pi)
    return out


def _classifier(solid):
    cls = require("OCP.BRepClass3d", "the sample-only containment check")
    return cls.BRepClass3d_SolidClassifier(solid)


def _states(classifier, points, tol: float) -> List[str]:
    gp = require("OCP.gp", "the sample-only containment check")
    topabs = require("OCP.TopAbs", "the sample-only containment check")
    names = {topabs.TopAbs_IN: "in", topabs.TopAbs_OUT: "out", topabs.TopAbs_ON: "on"}
    out = []
    for p in points:
        classifier.Perform(gp.gp_Pnt(*map(float, p)), tol)
        out.append(names.get(classifier.State(), "unknown"))
    return out


def sample_mesh_item(mesh: Any, cavity, container=None, *, samples: int = 4000, seed: int = 0,
                     touch_mm: float = 0.01) -> Dict[str, Any]:
    """Sample-only relation of a mesh item to a cavity (and container) solid.

    ``samples`` points uniform in the mesh's box are kept when inside the mesh (winding number), then
    classified against the exact solids: volume outside the cavity and inside the container are
    Monte Carlo estimates, each with its standard error. The mesh's vertices are classified too, and
    the one furthest outside the cavity is the witness."""
    np = require("numpy", "the sample-only containment check")
    from cadagent.gates.wall import _as_mesh
    m = _as_mesh(mesh)
    tris = np.asarray(m.triangles, dtype=float)
    lo, hi = m.bounds
    box_vol = float(np.prod(hi - lo))
    rng = np.random.default_rng(seed)
    pts = lo + rng.random((samples, 3)) * (hi - lo)
    inside = _winding(tris, pts) > 0.5
    body = pts[inside]
    cav_states = _states(_classifier(cavity), body, touch_mm)
    out_n = sum(1 for s in cav_states if s == "out")

    def est(n):
        p = n / samples
        return round(box_vol * p, 6), round(box_vol * (p * (1 - p) / samples) ** 0.5, 6)

    vol, vol_se = est(int(inside.sum()))
    outside, outside_se = est(out_n)
    verts = np.asarray(m.vertices, dtype=float)
    vstates = _states(_classifier(cavity), verts, touch_mm)
    out_pts = [verts[i] for i, s in enumerate(vstates) if s == "out"]
    witness: Dict[str, Any] = {}
    if out_pts:
        gp = require("OCP.gp", "the sample-only containment check")
        dists = _distances_to([gp.gp_Pnt(*map(float, p)) for p in out_pts], cavity)
        i = max(range(len(out_pts)), key=lambda k: dists[k][0])
        witness = {"furthest_outside_point": [round(float(c), 6) for c in out_pts[i]],
                   "depth_mm": round(dists[i][0], 6), "nearest_cavity_point": _pt(dists[i][1])}
    res = {"method": "sample-only", "samples": samples, "samples_in_item": int(inside.sum()),
           "volume_mm3": vol, "volume_se_mm3": vol_se, "outside_mm3": outside, "outside_se_mm3": outside_se,
           "vertices": len(verts), "vertices_outside": len(out_pts), "watertight": bool(m.is_watertight),
           "seed": seed, **witness}
    if container is not None:
        in_wall = sum(1 for s in _states(_classifier(container), body, touch_mm) if s == "in")
        res["wall_overlap_mm3"], res["wall_overlap_se_mm3"] = est(in_wall)
    return res


# ----------------------------------------------------------------------------- the checks

@dataclass
class _Ctx:
    assembly: Assembly
    tol: Tolerances
    cache: Optional[PairCache]
    support: str
    down: Tuple[float, float, float]
    support_mm: float
    excluded: set
    meshes: Mapping[str, Any]
    mesh_samples: int
    seed: int
    deflection: float
    max_points: int
    probe: bool = True
    probe_deflection: float = 0.01
    probe_points: int = 20000
    prefix: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)

    def cid(self, *parts: str) -> str:
        return self.prefix + ":".join(("contains",) + parts)


def _rel_evidence(rel: Relation) -> Dict[str, Any]:
    keep = ("state", "gap_mm", "overlap_mm3", "a_outside_b_mm3", "b_outside_a_mm3", "contained", "wall_mm",
            "contact_area_mm2", "witness", "cached", "error")
    return {k: v for k, v in rel.to_dict().items() if k in keep}


def _inside_check(ctx: _Ctx, d: Contains, inst: str) -> Tuple[Check, Dict[str, Any]]:
    asm, tol = ctx.assembly, ctx.tol
    rel = relate_pair(asm, inst, d.cavity, tol, cache=ctx.cache, contact_area=False)
    ev: Dict[str, Any] = {"relation": _rel_evidence(rel)}
    cid = ctx.cid(d.cavity, inst, "inside")
    if rel.state == "unknown":
        return Check(cid, "fail", f"{inst} vs {d.cavity}: the kernel could not decide ({rel.error})",
                     [inst, d.container], ev), {"name": inst, "state": "unknown"}
    if rel.state == "contains" and rel.contained in ("a_in_b", "both"):
        ev.update(outside_mm3=rel.a_outside_b_mm3, clearance_mm=rel.wall_mm)
        if ctx.probe and rel.wall_mm is not None and rel.wall_mm <= tol.touch_mm:
            key = None if ctx.cache is None else _key("probe", tol, asm.item(inst).key, asm.item(d.cavity).key,
                                                      f"{ctx.probe_deflection!r}:{ctx.probe_points}")
            try:
                probe, _ = _cached(ctx.cache, key, lambda: _contact_probe(
                    asm.shape(inst), asm.shape(d.cavity), ctx.probe_deflection, ctx.probe_points, tol.touch_mm))
            except Exception as exc:
                probe = {"error": f"{type(exc).__name__}: {exc}"}
            ev["probe"] = probe
            if probe.get("error"):
                return Check(cid, "fail", f"{inst} touches {d.cavity}'s boundary and the contact probe failed "
                                          f"({probe['error']})", [inst, d.container], ev), \
                    {"name": inst, "state": "unknown"}
            if probe.get("probe_depth_mm", 0.0) > tol.touch_mm:
                ev.update(outside_mm3=None, depth_mm=probe["probe_depth_mm"],
                          furthest_outside_point=probe["probe_point"], nearest_cavity_point=probe["probe_cavity_point"],
                          kernel_missed_crossing=True)
                return Check(cid, "fail", f"{inst} escapes {d.cavity}: the boolean read "
                                          f"{rel.a_outside_b_mm3:.4g} mm3 outside, but a surface point lies "
                                          f"{probe['probe_depth_mm']:.3g} mm outside at {probe['probe_point']} "
                                          "(a near-tangent crossing the kernel missed; volume not measured)",
                             [inst, d.container], ev), \
                    {"name": inst, "state": "escaped", "outside_mm3": None, "depth_mm": probe["probe_depth_mm"]}
        return Check(cid, "pass", f"{inst} inside {d.cavity} ({rel.a_outside_b_mm3:.4g} mm3 outside, "
                                  f"{rel.wall_mm:.4g} mm from its boundary)", [inst], ev), \
            {"name": inst, "state": "inside", "outside_mm3": rel.a_outside_b_mm3}
    vol = _volume(asm.shape(inst))
    whole = rel.state in ("apart", "touching")
    outside = vol if whole else float(rel.a_outside_b_mm3 or 0.0)
    if rel.state == "contains":       # the cavity inside the instance: the instance is still mostly outside
        outside = float(rel.a_outside_b_mm3 or 0.0)
    key = None if ctx.cache is None else _key("escape", tol, asm.item(inst).key, asm.item(d.cavity).key,
                                              f"{ctx.deflection!r}:{ctx.max_points}")
    try:
        wit, _ = _cached(ctx.cache, key, lambda: _escape_witness(asm.shape(inst), asm.shape(d.cavity), whole,
                                                                 ctx.deflection, ctx.max_points))
    except Exception as exc:        # a witness only: the failure stands without it
        wit = {"error": f"{type(exc).__name__}: {exc}"}
    ev.update(volume_mm3=round(vol, 6), outside_mm3=round(outside, 6),
              outside_fraction=round(outside / vol, 6) if vol > 0 else None, **wit)
    where = "wholly outside" if whole else f"{outside:.4g} mm3 ({100 * outside / vol:.1f} %) outside"
    depth = f", furthest {wit['depth_mm']:.3g} mm out at {wit['furthest_outside_point']}" if "depth_mm" in wit \
        else ""
    return Check(cid, "fail", f"{inst} escapes {d.cavity}: {where}{depth}", [inst, d.container], ev), \
        {"name": inst, "state": "escaped", "outside_mm3": round(outside, 6), "depth_mm": wit.get("depth_mm")}


def _wall_check(ctx: _Ctx, d: Contains, inst: str) -> Check:
    cid = ctx.cid(d.cavity, inst, "wall")
    if frozenset((inst, d.container)) in ctx.excluded:
        return Check(cid, "pass", f"{inst} vs {d.container}: declared intended overlap, not checked", [inst],
                     {"excluded": True})
    rel = relate_pair(ctx.assembly, inst, d.container, ctx.tol, cache=ctx.cache, contact_area=False)
    ev = {"relation": _rel_evidence(rel)}
    if rel.state == "unknown":
        return Check(cid, "fail", f"{inst} vs {d.container}: the kernel could not decide ({rel.error})",
                     [inst, d.container], ev)
    if rel.interferes:
        return Check(cid, "fail", f"{inst} is in {d.container}'s material: {rel.overlap_mm3:.4g} mm3 shared "
                                  f"around {rel.witness.get('overlap_centroid')}", [inst, d.container], ev)
    return Check(cid, "pass", f"{inst} vs {d.container}: {rel.state} (gap {rel.gap_mm:.4g} mm)", [inst], ev)


def _pairs(ctx: _Ctx, names: List[str], margin: float) -> List[Tuple[str, str]]:
    boxes = {n: bounding_box(ctx.assembly.shape(n)) for n in names}
    return [p for p, dist in aabb_distances(boxes).items() if dist <= margin]


def _interpenetration_check(ctx: _Ctx, d: Contains, names: List[str]) -> Check:
    cid = ctx.cid(d.cavity, d.what, "interpenetration")
    bad, unknown, excluded = [], [], []
    candidates = _pairs(ctx, names, ctx.tol.touch_mm)
    for a, b in candidates:
        if frozenset((a, b)) in ctx.excluded:
            excluded.append([a, b])
            continue
        rel = relate_pair(ctx.assembly, a, b, ctx.tol, cache=ctx.cache, contact_area=False)
        if rel.state == "unknown":
            unknown.append({"pair": [a, b], "error": rel.error})
        elif rel.interferes:
            bad.append({"pair": [a, b], "overlap_mm3": rel.overlap_mm3,
                        "overlap_centroid": rel.witness.get("overlap_centroid")})
    ev = {"instances": len(names), "pairs_checked": len(candidates), "overlaps": bad, "unknown": unknown,
          "excluded": excluded}
    if bad or unknown:
        parts = sorted({n for row in bad + unknown for n in row["pair"]})
        worst = max(bad, key=lambda r: r["overlap_mm3"]) if bad else None
        msg = (f"{len(bad)} pair(s) of {d.what} share volume"
               + (f", worst {worst['pair'][0]}/{worst['pair'][1]} {worst['overlap_mm3']:.4g} mm3" if worst else "")
               + (f"; {len(unknown)} pair(s) undecided" if unknown else ""))
        return Check(cid, "fail", msg, parts, ev)
    return Check(cid, "pass", f"no two of the {len(names)} {d.what} instances share volume "
                              f"({len(candidates)} pairs in contact range)", [], ev)


def _common(a, b) -> Dict[str, Any]:
    try:
        return {"common_mm3": round(_volume(_boolean("common", a, b)), 6)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _rests(ctx: _Ctx, upper: str, lower: str, kind: str) -> Dict[str, Any]:
    """Whether ``upper`` moved ``support_mm`` along ``down`` pushes into ``lower``: out of the cavity
    (``kind="cavity"``) or into another instance's solid (``"solid"``).

    Booleans first; when they read no penetration but the gap is within ``support_mm``, the moved
    instance's tessellation vertices are classified against ``lower`` (the same near-tangent
    fallback as the contact probe), because the surface intersection can miss a shallow crossing."""
    asm, tol = ctx.assembly, ctx.tol
    us, ls = asm.shape(upper), asm.shape(lower)
    moved = _shifted(us, ctx.down, ctx.support_mm)
    res = _common(moved, ls)
    if res.get("error"):
        return res
    pushed = (_volume(us) - res["common_mm3"]) if kind == "cavity" else res["common_mm3"]
    out: Dict[str, Any] = {"rests": pushed > tol.overlap_mm3, "pushed_mm3": round(pushed, 6), "method": "boolean"}
    if out["rests"]:
        return out
    from cadagent.gates.relations import _distance, _faces
    gap = _distance(_faces(us), _faces(ls))[0] if kind == "cavity" else _distance(us, ls)[0]
    out["gap_mm"] = round(gap, 6)
    if gap > ctx.support_mm + tol.touch_mm:
        return out
    shift = [c * ctx.support_mm for c in ctx.down]
    pts = [(p.X() + shift[0], p.Y() + shift[1], p.Z() + shift[2])
           for p in _points_of(us, ctx.probe_deflection, ctx.probe_points)]
    want = "out" if kind == "cavity" else "in"
    hits = sum(1 for st in _states(_classifier(ls), pts, tol.touch_mm) if st == want)
    out.update(method="vertex probe", probe_points=len(pts), probe_hits=hits, rests=hits > 0)
    return out


def _support_check(ctx: _Ctx, d: Contains, names: List[str]) -> Check:
    asm, tol = ctx.assembly, ctx.tol
    cid = ctx.cid(d.cavity, d.what, "support")
    sig = f"{ctx.support_mm!r}:{ctx.down!r}:{ctx.probe_deflection!r}:{ctx.probe_points}"
    on_floor, errors, rests = {}, [], {n: [] for n in names}

    def query(upper, lower, kind):
        key = None if ctx.cache is None else _key(f"rests-{kind}", tol, asm.item(upper).key, asm.item(lower).key,
                                                  sig)
        try:
            res, _ = _cached(ctx.cache, key, lambda: _rests(ctx, upper, lower, kind))
        except Exception as exc:
            res = {"error": f"{type(exc).__name__}: {exc}"}
        if res.get("error"):
            errors.append({"item": upper, "on": lower, "error": res["error"]})
        return bool(res.get("rests"))

    for n in names:
        on_floor[n] = query(n, d.cavity, "cavity")
    for a, b in _pairs(ctx, names, ctx.support_mm + tol.touch_mm):
        for upper, lower in ((a, b), (b, a)):
            if query(upper, lower, "solid"):
                rests[upper].append(lower)
    supported = {n for n, f in on_floor.items() if f}
    grew = True
    while grew:
        grew = False
        for n in names:
            if n not in supported and any(m in supported for m in rests[n]):
                supported.add(n)
                grew = True
    loose = [n for n in names if n not in supported]
    ev = {"down": list(ctx.down), "support_mm": ctx.support_mm, "mode": ctx.support,
          "on_cavity": sorted(n for n in names if on_floor[n]),
          "rests_on": {n: sorted(v) for n, v in rests.items() if v}, "unsupported": loose, "errors": errors}
    if loose or errors:
        status = "fail" if ctx.support == "fail" else "warn"
        msg = (f"{len(loose)} of {len(names)} {d.what} instance(s) rest on nothing within {ctx.support_mm} mm "
               f"along {list(ctx.down)}: {', '.join(loose[:8])}{' ...' if len(loose) > 8 else ''}"
               + (f"; {len(errors)} kernel error(s)" if errors else ""))
        return Check(cid, status, msg, loose or [e["item"] for e in errors], ev)
    return Check(cid, "pass", f"every {d.what} instance rests on {d.cavity} or on another instance", [], ev)


def _mesh_checks(ctx: _Ctx, d: Contains, inst: str) -> Tuple[List[Check], Dict[str, Any]]:
    asm, tol = ctx.assembly, ctx.tol
    container = None if frozenset((inst, d.container)) in ctx.excluded else asm.shape(d.container)
    try:
        res = sample_mesh_item(ctx.meshes[inst], asm.shape(d.cavity), container, samples=ctx.mesh_samples,
                               seed=ctx.seed, touch_mm=tol.touch_mm)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        return [Check(ctx.cid(d.cavity, inst, "inside"), "fail", f"{inst} (mesh): sampling failed ({err})",
                      [inst], {"method": "sample-only", "error": err})], {"name": inst, "state": "unknown"}
    cid = ctx.cid(d.cavity, inst, "inside")
    escaped = res["outside_mm3"] > tol.contain_mm3 or res.get("depth_mm", 0.0) > tol.touch_mm
    if escaped:
        depth = f", furthest vertex {res['depth_mm']:.3g} mm out" if "depth_mm" in res else ""
        checks = [Check(cid, "fail", f"{inst} (mesh, sample-only) escapes {d.cavity}: about "
                                     f"{res['outside_mm3']:.4g} ± {res['outside_se_mm3']:.2g} mm3 outside{depth}",
                        [inst, d.container], res)]
    else:
        checks = [Check(cid, "pass", f"{inst} (mesh, sample-only) inside {d.cavity}: no sample outside "
                                     f"({res['samples_in_item']} interior points, {res['vertices']} vertices)",
                        [inst], res)]
    if container is not None:
        wid = ctx.cid(d.cavity, inst, "wall")
        if res["wall_overlap_mm3"] > tol.overlap_mm3:
            checks.append(Check(wid, "fail", f"{inst} (mesh, sample-only) is in {d.container}'s material: about "
                                             f"{res['wall_overlap_mm3']:.4g} mm3", [inst, d.container],
                                {"method": "sample-only", "wall_overlap_mm3": res["wall_overlap_mm3"],
                                 "wall_overlap_se_mm3": res["wall_overlap_se_mm3"]}))
        else:
            checks.append(Check(wid, "pass", f"{inst} (mesh, sample-only): no sample in {d.container}'s material",
                                [inst], {"method": "sample-only"}))
    return checks, {"name": inst, "state": "escaped" if escaped else "inside", "method": "sample-only",
                    "outside_mm3": res["outside_mm3"]}


def check_contains(assembly: Assembly, declaration: Any, *, tol: Tolerances = Tolerances(),
                   cache: Optional[PairCache] = None, support: str = "report", down: Sequence[float] = (0, 0, -1),
                   support_mm: float = 0.05, exclusions: Iterable[Mapping[str, Any]] = (),
                   meshes: Optional[Mapping[str, Any]] = None, mesh_samples: int = 4000, seed: int = 0,
                   deflection_mm: float = 0.05, max_points: int = 600, probe: bool = True,
                   probe_deflection_mm: float = 0.01, probe_points: int = 20000, pose: str = "") -> List[Check]:
    """The checks for one declaration on one assembly (one pose). See the module docstring."""
    if support not in SUPPORT_MODES:
        raise ValueError(f"support must be one of {SUPPORT_MODES}, got {support!r}")
    if support_mm <= 0:
        raise ValueError("support_mm must be positive")
    d = Contains.coerce(declaration)
    ctx = _Ctx(assembly, tol, cache, support, _unit(down), float(support_mm),
               {frozenset(e["parts"]) for e in exclusions}, dict(meshes or {}), mesh_samples, seed,
               deflection_mm, max_points, probe, probe_deflection_mm, probe_points, f"{pose}/" if pose else "")
    return _checks(ctx, d)


def _checks(ctx: _Ctx, d: Contains) -> List[Check]:
    asm = ctx.assembly
    checks: List[Check] = []
    cav_id = ctx.cid(d.cavity or "?", d.what, "cavity")
    lint = None
    if not d.cavity:
        lint = ("unknown-cavity", f"{d.container} contains {d.what} without naming a cavity")
    elif d.cavity not in asm.cavities:
        lint = ("unknown-cavity", f"{d.container} contains {d.what} in cavity {d.cavity!r}, which is not registered "
                                  "(@cavity); there are no derived cavities")
    elif asm.cavities[d.cavity].container != d.container:
        lint = ("cavity-wrong-part", f"cavity {d.cavity!r} is registered on {asm.cavities[d.cavity].container!r}, "
                                     f"not {d.container!r}")
    elif d.container not in asm:
        lint = ("unknown-part", f"container {d.container!r} is not in the assembly")
    names = instances(asm.names, d.what)
    mesh_names = [n for n in instances(ctx.meshes, d.what) if n not in names]
    found = len(names) + len(mesh_names)
    if d.count is not None:
        ok = found == d.count
        checks.append(Check(ctx.cid(d.cavity or "?", d.what, "count"), "pass" if ok else "fail",
                            f"{found} {d.what} instance(s) found, {d.count} declared",
                            [] if ok else [d.what, d.container],
                            {"declared": d.count, "found": found, "brep": len(names), "mesh": len(mesh_names)}))
    elif not found:
        checks.append(Check(ctx.cid(d.cavity or "?", d.what, "count"), "fail",
                            f"no instance of {d.what} in the assembly", [d.what, d.container], {"found": 0}))
    if lint:
        checks.append(Check(cav_id, "fail", lint[1], [d.container], {"lint": lint[0]}))
        return checks
    checks.append(Check(cav_id, "pass", f"cavity {d.cavity} is registered on {d.container}", [],
                        {"cavity_volume_mm3": round(_volume(asm.shape(d.cavity)), 6)}))
    rows = []
    for inst in names:
        c, row = _inside_check(ctx, d, inst)
        checks += [c, _wall_check(ctx, d, inst)]
        rows.append(row)
    for inst in mesh_names:
        cs, row = _mesh_checks(ctx, d, inst)
        checks += cs
        rows.append(row)
    if len(names) > 1:
        checks.append(_interpenetration_check(ctx, d, names))
    if ctx.support != "off" and names:
        checks.append(_support_check(ctx, d, names))
    return checks


def _summary(d: Contains, checks: List[Check], pose: str) -> Dict[str, Any]:
    inside = [c for c in checks if c.id.endswith(":inside")]
    escaped = [{"name": c.parts[0], "outside_mm3": c.evidence.get("outside_mm3"),
                "depth_mm": c.evidence.get("depth_mm"),
                "furthest_outside_point": c.evidence.get("furthest_outside_point")}
               for c in inside if c.status == "fail"]
    return {"pose": pose or None, **d.to_dict(), "instances": len(inside),
            "inside": sum(1 for c in inside if c.status == "pass"), "escaped": escaped,
            "status": "fail" if any(c.status == "fail" for c in checks)
            else ("warn" if any(c.status == "warn" for c in checks) else "pass")}


def containment_gate(assembly: Assembly, declarations: Iterable[Any], *, tol: Tolerances = Tolerances(),
                     cache: Optional[PairCache] = None, poses: Optional[Mapping[str, Mapping[str, Any]]] = None,
                     support: str = "report", down: Sequence[float] = (0, 0, -1), support_mm: float = 0.05,
                     exclusions: Iterable[Mapping[str, Any]] = (), meshes: Optional[Mapping[str, Any]] = None,
                     mesh_samples: int = 4000, seed: int = 0, deflection_mm: float = 0.05, max_points: int = 600,
                     probe: bool = True, probe_deflection_mm: float = 0.01, probe_points: int = 20000,
                     out: Any = None) -> Dict[str, Any]:
    """Run every ``contains`` declaration (in every pose) and return, with ``out`` also write, the verdict.

    * ``declarations``: ``Contains``, mappings ``{container, cavity, what, count, free}`` (the gate
      bench's form), or ``contains_declarations(dossier)``;
    * ``poses``: ``{pose_name: {body: location}}``; None checks the assembly as placed. A pose with
      an empty map is the assembly as placed;
    * ``support``: ``"report"`` (an unsupported instance is a warning), ``"fail"`` or ``"off"``;
      ``down`` (assembly frame, default -Z) and ``support_mm`` (0.05) define resting;
    * ``exclusions``: declared intended overlaps ``[{parts: [a, b], reason}]`` left out of the wall and
      interpenetration checks (listed in the verdict);
    * ``meshes``: ``{instance key: mesh}`` (trimesh, STL path or shape) for mesh-only items (sample-only).
    """
    decls = [Contains.coerce(x) for x in declarations]
    excl = [dict(e) for e in exclusions]
    for e in excl:
        if len(set(e.get("parts", ()))) != 2:
            raise ValueError(f"an exclusion names two parts: {e!r}")
    checks: List[Check] = []
    summary = []
    pose_items = list((poses or {"": {}}).items())
    for pose, locations in pose_items:
        asm = posed_assembly(assembly, locations) if locations else assembly
        for d in decls:
            cs = check_contains(asm, d, tol=tol, cache=cache, support=support, down=down, support_mm=support_mm,
                                exclusions=excl, meshes=meshes, mesh_samples=mesh_samples, seed=seed,
                                deflection_mm=deflection_mm, max_points=max_points, probe=probe,
                                probe_deflection_mm=probe_deflection_mm, probe_points=probe_points, pose=pose)
            checks += cs
            summary.append(_summary(d, cs, pose))
    limits = {"touch_mm": tol.touch_mm, "contain_mm3": tol.contain_mm3, "overlap_mm3": tol.overlap_mm3,
              "volume_check_mm3": tol.volume_check_mm3, "support": support, "down": list(_unit(down)),
              "support_mm": support_mm, "witness_deflection_mm": deflection_mm, "witness_max_points": max_points, "contact_probe": probe,
              "probe_deflection_mm": probe_deflection_mm, "probe_points": probe_points,
              "mesh_samples": mesh_samples, "seed": seed,
              "poses": {p: {b: matrix_key(_matrix_of(loc)) for b, loc in locs.items()} for p, locs in pose_items
                        if p}}
    data = verdict(GATE, checks, assumptions=ASSUMPTIONS, limits=limits, exclusions=excl,
                   extra={"declarations": summary})
    if out is not None:
        write_verdict(out, data)
    return data


def _matrix_of(location: Any) -> Tuple[float, ...]:
    t = _trsf(location)
    return tuple(t.Value(r, c) for r in (1, 2, 3) for c in (1, 2, 3, 4))
