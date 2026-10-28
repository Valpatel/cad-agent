"""Minimum-wall gate: wall and rib thickness by inward rays, on the print mesh and on the B-rep.

Two samplers, each giving thickness samples ``(point, inward direction, thickness)``:

* **mesh rays** (the primary evidence, as text-to-cad's ``dfam-check`` does, MIT; idea only):
  one ray per triangle from its centroid along the inward normal; the thickness is the
  distance to the first triangle hit. Large meshes are sub-sampled (``max_rays``, area-weighted,
  seeded, so runs repeat). Uses trimesh's ray engine when ``rtree`` is importable, else an
  exact numpy Möller–Trumbore fallback (slower: keep ``max_rays`` modest without rtree).
* **B-rep rays**: an n x n set of samples in the UV box of *every* B-rep face (n from ``grid`` up to
  ``max_grid``, about one sample per ``spacing_mm``; points outside a trimmed face are dropped), each
  cast along the face's inward normal against the exact solid (``IntCurvesFace_ShapeIntersector``).
  Every face gets samples whatever its area, so a thin rib that a sub-sampled mesh misses is still probed.

The mesh is repaired before use: vertices within 1e-5 mm merged, degenerate and duplicate triangles
dropped (CadQuery's tessellation leaves open seams at sphere poles, cone apexes and fillet corners).
When the B-rep is given too, every thin mesh sample (up to ``remeasure``, thinnest first) is measured
again exactly: from the nearest point on the B-rep along its inward surface normal. Mesh readings
the B-rep does not confirm are chord error and are dismissed (counted in the evidence); a mesh that
is still open after repair is then a warning, with the B-rep rays as the evidence.

The plan (§4.6) asked for a negative-offset probe on the B-rep. Tried on this kernel (OCCT 7.9
through CadQuery 2.8), ``BRepOffsetAPI_MakeOffsetShape`` by -t/2 returned a shell or a null shape
for exactly the cases it exists for (a 0.8 mm rib on a plate, a 2.4 mm-walled box), so the exact
ray probe replaces it.

Limits, stated in every verdict:

* A ray along the surface normal measures thickness *across* the wall at that point. Walls met
  at a slant, thin regions between samples, and gaps (as opposed to walls) are not measured;
  a knife edge reads thin near its tip, which is correct.
* Samples, not a proof: the count of samples is in the evidence. A pass means no sample was
  thinner than ``wall_mm - tol_mm``.
* The threshold is the part's own (the dossier's ``material.wall_mm``, passed in as a plain
  number until the dossier exists). Whether that threshold suits the printer, nozzle, material
  and load is not checked here.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from cadagent._deps import require
from cadagent.gates.verdict import Check, verdict, write_verdict

ASSUMPTIONS = [
    "thickness is measured by rays along the inward surface normal: mesh rays from triangle centroids "
    "(sub-sampled to max_rays) and exact B-rep rays from a UV grid on every face",
    "a pass means no sample was thinner than wall_mm - tol_mm; regions between samples and walls met "
    "at a slant are not measured",
    "the per-part wall_mm is the declared minimum; whether it suits the printer, nozzle, material and "
    "load is not checked",
    "a mesh reads curved walls thin by its chord error (about 0.09 mm seen on a 2.4 mm spherical shell "
    "tessellated at 0.05 mm); with the B-rep given, thin mesh samples are re-measured exactly and only "
    "confirmed ones fail; with a mesh alone, tol_mm must cover that error",
    "the model is checked, not the print: no shrink, elephant foot, or slicer perimeter rounding",
]


# ----------------------------------------------------------------------------- mesh rays

def _as_mesh(mesh: Any, tolerance: float = 0.05, angular: float = 0.2, merge_digits: int = 5):
    """A repaired copy: vertices merged to ``merge_digits`` decimals (1e-5 mm), degenerate and duplicate
    triangles dropped. Orientation is left as the tessellator made it (``fix_normals`` flips the inner
    skin of a shelled part)."""
    trimesh = require("trimesh", "the mesh wall check")
    if isinstance(mesh, trimesh.Trimesh):
        m = mesh.copy()
    elif isinstance(mesh, (str, Path)):
        m = trimesh.load_mesh(mesh, force="mesh")
    else:
        shape = mesh
        if not hasattr(shape, "tessellate"):
            cq = require("cadquery", "tessellating a B-rep for the wall check")
            shape = cq.Shape.cast(getattr(mesh, "wrapped", mesh))
        verts, tris = shape.tessellate(tolerance, angular)
        m = trimesh.Trimesh([(v.x, v.y, v.z) for v in verts], tris, process=True)
    m.merge_vertices(digits_vertex=merge_digits)
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    return m


def _first_hits_numpy(tri, origins, dirs, chunk: int = 256):
    """Distance to the nearest triangle along each ray (inf on a miss): Möller–Trumbore, exact."""
    np = require("numpy", "ray casting")
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    out = np.full(len(origins), np.inf)
    for s in range(0, len(origins), chunk):
        o, d = origins[s:s + chunk, None, :], dirs[s:s + chunk, None, :]
        p = np.cross(d, e2[None])
        det = (e1[None] * p).sum(-1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tvec = o - v0[None]
        u = (tvec * p).sum(-1) * inv
        q = np.cross(tvec, e1[None])
        v = (d * q).sum(-1) * inv
        t = (e2[None] * q).sum(-1) * inv
        hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 0)
        out[s:s + chunk] = np.where(hit, t, np.inf).min(axis=1)
    return out


def mesh_thickness(mesh: Any, *, max_rays: int = 20000, seed: int = 0, eps: float = 1e-4) -> Dict[str, Any]:
    """Thickness samples by inward rays from triangle centroids of a closed mesh.

    ``mesh``: a trimesh, an STL/3MF path, or a CadQuery shape (tessellated at 0.05 mm). Returns
    ``{"method", "points", "hits", "thickness", "areas", "rays", "misses", "triangles", "engine",
    "watertight"}`` with numpy arrays; ``areas`` is the mesh area each sample stands for.
    """
    np = require("numpy", "ray casting")
    m = _as_mesh(mesh)
    n = len(m.faces)
    if n == 0:
        raise ValueError("empty mesh")
    areas = np.asarray(m.area_faces)
    if n > max_rays:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(n, size=max_rays, replace=False, p=areas / areas.sum()))
        weight = np.full(len(idx), areas.sum() / len(idx))
    else:
        idx, weight = np.arange(n), areas
    normals = np.asarray(m.face_normals)[idx]
    dirs = -normals
    centres = np.asarray(m.triangles_center)[idx]
    origins = centres + dirs * eps
    engine = "numpy"
    try:
        require("rtree", "fast mesh rays")
        locs, ray_i, _ = m.ray.intersects_location(origins, dirs, multiple_hits=False)
        dist = np.full(len(idx), np.inf)
        d = np.linalg.norm(locs - origins[ray_i], axis=1)
        np.minimum.at(dist, ray_i, d)
        engine = "trimesh+rtree"
    except Exception:
        dist = _first_hits_numpy(np.asarray(m.triangles), origins, dirs)
    hit = np.isfinite(dist)
    thickness = np.where(hit, dist + eps, np.inf)
    return {"method": "mesh-ray", "points": centres, "dirs": dirs, "hits": centres + dirs * np.where(hit, thickness, 0)[:, None],
            "thickness": thickness, "areas": weight, "rays": int(len(idx)), "misses": int((~hit).sum()),
            "triangles": int(n), "engine": engine, "watertight": bool(m.is_watertight)}


# ----------------------------------------------------------------------------- B-rep rays

def _occ():
    names = ("TopExp", "TopAbs", "TopoDS", "BRepTools", "BRepGProp", "GProp", "gp", "BRepTopAdaptor",
             "IntCurvesFace", "BRepExtrema", "BRepBuilderAPI")
    return {n: require(f"OCP.{n}", "B-rep wall probe") for n in names}


def _caster(solid, occ):
    caster = occ["IntCurvesFace"].IntCurvesFace_ShapeIntersector()
    caster.Load(solid, 1e-7)
    return caster


def _ray_at(caster, face, u, v, occ, eps: float):
    """``(point, inward dir, thickness)`` from face parameter (u, v), or None where the normal is undefined."""
    gp = occ["gp"]
    p, n = gp.gp_Pnt(), gp.gp_Vec()
    occ["BRepGProp"].BRepGProp_Face(face).Normal(u, v, p, n)       # outward for the face's orientation
    if n.Magnitude() < 1e-12:
        return None
    n.Normalize()
    d = gp.gp_Dir(-n.X(), -n.Y(), -n.Z())
    caster.Perform(gp.gp_Lin(p, d), eps, 1e9)
    best = min((caster.WParameter(k) for k in range(1, caster.NbPnt() + 1)), default=float("inf"))
    return (p.X(), p.Y(), p.Z()), (d.X(), d.Y(), d.Z()), best


def brep_thickness(shape: Any, *, grid: int = 3, spacing_mm: float = 2.0, max_grid: int = 16,
                   eps: float = 1e-3) -> Dict[str, Any]:
    """Exact thickness samples: an n x n UV grid on every B-rep face, rays along the inward normal.

    n = sqrt(face area) / ``spacing_mm``, at least ``grid`` and at most ``max_grid``. Same keys as
    ``mesh_thickness`` (``areas`` is the face area over its kept samples).
    """
    np = require("numpy", "ray casting")
    occ = _occ()
    if grid < 1 or max_grid < grid or spacing_mm <= 0:
        raise ValueError("need 1 <= grid <= max_grid and spacing_mm > 0")
    solid = getattr(shape, "wrapped", shape)
    caster = _caster(solid, occ)
    pts, dirs, thick, areas = [], [], [], []
    faces = 0
    ex = occ["TopExp"].TopExp_Explorer(solid, occ["TopAbs"].TopAbs_FACE)
    while ex.More():
        face = occ["TopoDS"].TopoDS.Face_s(ex.Current())
        ex.Next()
        faces += 1
        props = occ["GProp"].GProp_GProps()
        occ["BRepGProp"].BRepGProp.SurfaceProperties_s(face, props)
        n = int(min(max_grid, max(grid, math.ceil(math.sqrt(max(props.Mass(), 0.0)) / spacing_mm))))
        u0, u1, v0, v1 = occ["BRepTools"].BRepTools.UVBounds_s(face)
        classifier = occ["BRepTopAdaptor"].BRepTopAdaptor_FClass2d(face, 1e-7)
        kept = []
        for i in range(n):
            for j in range(n):
                u = u0 + (u1 - u0) * (i + 0.5) / n
                v = v0 + (v1 - v0) * (j + 0.5) / n
                if classifier.Perform(occ["gp"].gp_Pnt2d(u, v)) != occ["TopAbs"].TopAbs_IN:
                    continue
                ray = _ray_at(caster, face, u, v, occ, eps)
                if ray is not None:
                    kept.append(ray)
        for point, direction, t in kept:
            pts.append(point)
            dirs.append(direction)
            thick.append(t)
            areas.append(props.Mass() / len(kept))
    pts_a, dirs_a, thick_a = np.asarray(pts, float).reshape(-1, 3), np.asarray(dirs, float).reshape(-1, 3), np.asarray(thick, float)
    hit = np.isfinite(thick_a)
    return {"method": "brep-ray", "points": pts_a, "dirs": dirs_a,
            "hits": pts_a + dirs_a * np.where(hit, thick_a, 0)[:, None], "thickness": thick_a,
            "areas": np.asarray(areas, float), "rays": int(len(thick_a)), "misses": int((~hit).sum()),
            "faces": faces, "grid": [grid, max_grid], "spacing_mm": spacing_mm}


def brep_thickness_near(shape: Any, points: Any, *, eps: float = 1e-3) -> List[Optional[Dict[str, Any]]]:
    """Exact thickness at the B-rep surface point nearest each of ``points`` (e.g. mesh samples):
    ``{"point", "exit_point", "thickness_mm"}`` per point, None where the nearest support is not a face."""
    occ = _occ()
    solid = getattr(shape, "wrapped", shape)
    caster = _caster(solid, occ)
    topods = occ["TopoDS"]
    builder = require("OCP.BRep", "B-rep wall probe").BRep_Builder()
    comp = topods.TopoDS_Compound()
    builder.MakeCompound(comp)
    ex = occ["TopExp"].TopExp_Explorer(solid, occ["TopAbs"].TopAbs_FACE)
    while ex.More():
        builder.Add(comp, ex.Current())
        ex.Next()
    out: List[Optional[Dict[str, Any]]] = []
    for q in points:
        vertex = occ["BRepBuilderAPI"].BRepBuilderAPI_MakeVertex(occ["gp"].gp_Pnt(*map(float, q))).Vertex()
        dist = occ["BRepExtrema"].BRepExtrema_DistShapeShape(vertex, comp)
        dist.Perform()
        if not dist.IsDone() or dist.NbSolution() < 1 or \
                dist.SupportTypeShape2(1) != occ["BRepExtrema"].BRepExtrema_SupportType.BRepExtrema_IsInFace:
            out.append(None)
            continue
        face = topods.TopoDS.Face_s(dist.SupportOnShape2(1))
        u, v = dist.ParOnFaceS2(1)
        ray = _ray_at(caster, face, u, v, occ, eps)
        if ray is None or not math.isfinite(ray[2]):
            out.append(None)
            continue
        (p, d, t) = ray
        out.append({"point": list(p), "exit_point": [p[k] + d[k] * t for k in range(3)], "thickness_mm": t})
    return out


# ----------------------------------------------------------------------------- the gate

def _summary(samples: Mapping[str, Any], limit: float) -> Dict[str, Any]:
    np = require("numpy", "wall summary")
    t = samples["thickness"]
    finite = t[np.isfinite(t)]
    thin = np.isfinite(t) & (t < limit)
    out = {"rays": samples["rays"], "misses": samples["misses"],
           "min_mm": round(float(finite.min()), 4) if len(finite) else None,
           "thin_samples": int(thin.sum()), "thin_area_mm2": round(float(samples["areas"][thin].sum()), 3)}
    if len(finite):
        out["percentiles_mm"] = {f"p{q}": round(float(np.percentile(finite, q)), 4) for q in (1, 5, 50)}
    for k in ("triangles", "engine", "watertight", "faces", "grid", "spacing_mm"):
        if k in samples:
            out[k] = samples[k]
    return out


def _witnesses(samples: Mapping[str, Any], limit: float, count: int, spacing: float = 1.0) -> List[Dict[str, Any]]:
    """The thinnest samples under ``limit``, at most one per ``spacing`` mm cell."""
    np = require("numpy", "wall witnesses")
    t = samples["thickness"]
    order = [i for i in np.argsort(t) if np.isfinite(t[i]) and t[i] < limit]
    seen, out = set(), []
    for i in order:
        cell = tuple(np.floor(samples["points"][i] / spacing).astype(int).tolist())
        if cell in seen:
            continue
        seen.add(cell)
        out.append({"method": samples["method"], "thickness_mm": round(float(t[i]), 4),
                    "point": [round(float(v), 4) for v in samples["points"][i]],
                    "exit_point": [round(float(v), 4) for v in samples["hits"][i]]})
        if len(out) >= count:
            break
    return out


def check_wall(name: str, wall_mm: float, *, mesh: Any = None, shape: Any = None, tol_mm: float = 0.01,
               max_rays: int = 20000, grid: int = 3, spacing_mm: float = 2.0, max_grid: int = 16,
               remeasure: int = 500, witnesses: int = 10) -> Check:
    """One part's minimum-wall check. Give the print ``mesh`` (trimesh, STL/3MF path, or a shape to
    tessellate), the B-rep ``shape``, or both (both is best: they miss different things, and the B-rep
    re-measures thin mesh readings exactly).

    Fails when a sample (a confirmed one, when the B-rep is given) is thinner than ``wall_mm - tol_mm``,
    when more than 1 % of rays find no exit, or when the mesh is open after repair and there is no
    B-rep (with a B-rep, an open mesh is a warning).
    """
    np = require("numpy", "wall check")
    if wall_mm <= 0 or tol_mm < 0:
        raise ValueError("wall_mm must be positive and tol_mm non-negative")
    if mesh is None and shape is None:
        raise ValueError(f"part {name!r}: give a mesh, a shape, or both")
    limit = wall_mm - tol_mm
    evidence: Dict[str, Any] = {"wall_mm": wall_mm, "tol_mm": tol_mm}
    problems, warnings, wit, mins = [], [], [], []
    if mesh is not None:
        run = mesh_thickness(mesh, max_rays=max_rays)
        summary = evidence["mesh-ray"] = _summary(run, limit)
        if run["watertight"] is False:
            (warnings if shape is not None else problems).append(
                "mesh is open after vertex merge" + ("; the B-rep rays are the evidence" if shape is not None
                                                     else ", so inward rays are meaningless"))
        elif run["rays"] and run["misses"] > 0.01 * run["rays"]:
            problems.append(f"{run['misses']} of {run['rays']} mesh rays found no exit")
        t = run["thickness"]
        thin = [i for i in np.argsort(t) if np.isfinite(t[i]) and t[i] < limit]
        if shape is not None and run["watertight"] is not False:
            checked = thin[:remeasure]
            exact = brep_thickness_near(shape, run["points"][checked]) if checked else []
            confirmed = []
            for i, e in zip(checked, exact):
                if e is None:
                    confirmed.append({"method": "mesh-ray (no B-rep face nearby)", "thickness_mm": round(float(t[i]), 4),
                                      "point": [round(float(v), 4) for v in run["points"][i]],
                                      "exit_point": [round(float(v), 4) for v in run["hits"][i]]})
                elif e["thickness_mm"] < limit:
                    confirmed.append({"method": "mesh-ray, B-rep confirmed", "thickness_mm": round(e["thickness_mm"], 4),
                                      "mesh_thickness_mm": round(float(t[i]), 4),
                                      "point": [round(v, 4) for v in e["point"]],
                                      "exit_point": [round(v, 4) for v in e["exit_point"]]})
            summary["remeasured"] = len(checked)
            summary["dismissed_as_chord_error"] = len(checked) - len(confirmed)
            summary["not_remeasured"] = len(thin) - len(checked)
            if summary["not_remeasured"] and not confirmed:
                summary["note"] = ("samples beyond the remeasure cap read no thinner on the mesh than ones the "
                                   "B-rep cleared, and are dismissed with them")
            wit += _dedupe(confirmed, witnesses)
            mins += [w["thickness_mm"] for w in confirmed] or ([summary["min_mm"]] if not thin and summary["min_mm"]
                                                               is not None else [])
        else:
            wit += _witnesses(run, limit, witnesses)
            if summary["min_mm"] is not None:
                mins.append(summary["min_mm"])
    if shape is not None:
        run = brep_thickness(shape, grid=grid, spacing_mm=spacing_mm, max_grid=max_grid)
        evidence["brep-ray"] = _summary(run, limit)
        wit += _witnesses(run, limit, witnesses)
        if run["rays"] and run["misses"] > 0.01 * run["rays"]:
            problems.append(f"{run['misses']} of {run['rays']} B-rep rays found no exit")
        if evidence["brep-ray"]["min_mm"] is not None:
            mins.append(evidence["brep-ray"]["min_mm"])
    wit.sort(key=lambda w: w["thickness_mm"])
    evidence["witnesses"] = wit[:witnesses]
    thinnest = min(mins) if mins else None
    cid = f"wall:{name}"
    if problems:
        return Check(cid, "fail", "; ".join(problems + warnings), (name,), evidence)
    if wit:
        return Check(cid, "fail", f"thinnest {wit[0]['thickness_mm']:.3f} mm < {wall_mm:g} mm (sampled; see witnesses)",
                     (name,), evidence)
    if thinnest is None:
        return Check(cid, "fail", "no ray found an exit; nothing measured", (name,), evidence)
    message = f"thinnest sampled {thinnest:.3f} mm >= {wall_mm:g} mm"
    if warnings:
        return Check(cid, "warn", f"{message}; " + "; ".join(warnings), (name,), evidence)
    return Check(cid, "pass", message, (name,), evidence)


def _dedupe(rows: List[Dict[str, Any]], count: int, spacing: float = 1.0) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["thickness_mm"]):
        cell = tuple(math.floor(v / spacing) for v in r["point"])
        if cell not in seen:
            seen.add(cell)
            out.append(r)
        if len(out) >= count:
            break
    return out


def wall_gate(parts: Mapping[str, Mapping[str, Any]], *, out: Any = None, tol_mm: float = 0.01,
              max_rays: int = 20000, grid: int = 3, spacing_mm: float = 2.0, max_grid: int = 16) -> Dict[str, Any]:
    """Run ``check_wall`` per part and return (and with ``out``, write) the verdict.

    ``parts``: ``{name: {"wall_mm": 2.4, "mesh": ..., "shape": ...}}``; ``wall_mm`` is per part.
    """
    checks = [check_wall(name, float(spec["wall_mm"]), mesh=spec.get("mesh"), shape=spec.get("shape"),
                         tol_mm=tol_mm, max_rays=max_rays, grid=grid, spacing_mm=spacing_mm, max_grid=max_grid)
              for name, spec in parts.items()]
    limits = {name: {"wall_mm": float(spec["wall_mm"])} for name, spec in parts.items()}
    data = verdict("wall", checks, assumptions=ASSUMPTIONS, limits={"tol_mm": tol_mm, "max_rays": max_rays,
                                                                    "brep_grid": [grid, max_grid],
                                                                    "brep_spacing_mm": spacing_mm, "parts": limits})
    if out is not None:
        write_verdict(out, data)
    return data
