"""Minimum-wall gate: wall and rib thickness by inward rays, on the print mesh and on the B-rep.

Two samplers, each giving thickness samples ``(point, inward direction, thickness)``:

* **mesh rays** (the primary evidence, as text-to-cad's ``dfam-check`` does, MIT; idea only):
  one ray per triangle from its centroid along the inward normal; the thickness is the
  distance to the first triangle hit. Large meshes are sub-sampled (``max_rays``, area-weighted,
  seeded, so runs repeat). Uses trimesh's ray engine when ``rtree`` is importable, else an
  exact numpy Möller–Trumbore fallback (slower: keep ``max_rays`` modest without rtree).
* **B-rep rays**: a ``grid`` x ``grid`` set of samples in the UV box of *every* B-rep face (points
  outside a trimmed face are dropped), each cast along the face's inward normal against the exact
  solid (``IntCurvesFace_ShapeIntersector``). Every face gets samples whatever its area, so a thin
  rib that a sub-sampled mesh misses is still probed.

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
    "on curved walls the mesh reads thin by up to its chord deviation (0.05 mm when tessellated here); "
    "tol_mm absorbs that only when it is at least as large, and the B-rep rays are exact",
    "the model is checked, not the print: no shrink, elephant foot, or slicer perimeter rounding",
]


# ----------------------------------------------------------------------------- mesh rays

def _as_mesh(mesh: Any, tolerance: float = 0.05, angular: float = 0.2):
    trimesh = require("trimesh", "the mesh wall check")
    if isinstance(mesh, trimesh.Trimesh):
        return mesh
    if isinstance(mesh, (str, Path)):
        return trimesh.load_mesh(mesh, force="mesh")
    shape = mesh
    if not hasattr(shape, "tessellate"):
        cq = require("cadquery", "tessellating a B-rep for the wall check")
        shape = cq.Shape.cast(getattr(mesh, "wrapped", mesh))
    verts, tris = shape.tessellate(tolerance, angular)
    return trimesh.Trimesh([(v.x, v.y, v.z) for v in verts], tris, process=True)


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

def brep_thickness(shape: Any, *, grid: int = 3, eps: float = 1e-3) -> Dict[str, Any]:
    """Exact thickness samples: ``grid`` x ``grid`` UV samples per B-rep face, rays along the inward normal.

    Same keys as ``mesh_thickness`` (``areas`` is the face area over its kept samples).
    """
    np = require("numpy", "ray casting")
    topexp = require("OCP.TopExp", "B-rep wall probe")
    topabs = require("OCP.TopAbs", "B-rep wall probe")
    topods = require("OCP.TopoDS", "B-rep wall probe")
    breptools = require("OCP.BRepTools", "B-rep wall probe")
    bgprop = require("OCP.BRepGProp", "B-rep wall probe")
    gprop = require("OCP.GProp", "B-rep wall probe")
    gp = require("OCP.gp", "B-rep wall probe")
    fclass = require("OCP.BRepTopAdaptor", "B-rep wall probe")
    inter = require("OCP.IntCurvesFace", "B-rep wall probe")
    if grid < 1:
        raise ValueError("grid must be at least 1")
    solid = getattr(shape, "wrapped", shape)
    caster = inter.IntCurvesFace_ShapeIntersector()
    caster.Load(solid, 1e-7)
    pts, dirs, thick, areas = [], [], [], []
    faces = 0
    ex = topexp.TopExp_Explorer(solid, topabs.TopAbs_FACE)
    while ex.More():
        face = topods.TopoDS.Face_s(ex.Current())
        ex.Next()
        faces += 1
        props = gprop.GProp_GProps()
        bgprop.BRepGProp.SurfaceProperties_s(face, props)
        u0, u1, v0, v1 = breptools.BRepTools.UVBounds_s(face)
        classifier = fclass.BRepTopAdaptor_FClass2d(face, 1e-7)
        evaluator = bgprop.BRepGProp_Face(face)
        kept = []
        for i in range(grid):
            for j in range(grid):
                u = u0 + (u1 - u0) * (i + 0.5) / grid
                v = v0 + (v1 - v0) * (j + 0.5) / grid
                if classifier.Perform(gp.gp_Pnt2d(u, v)) != topabs.TopAbs_IN:
                    continue
                p, n = gp.gp_Pnt(), gp.gp_Vec()
                evaluator.Normal(u, v, p, n)          # outward for the face's orientation
                if n.Magnitude() < 1e-12:
                    continue
                n.Normalize()
                d = gp.gp_Dir(-n.X(), -n.Y(), -n.Z())
                caster.Perform(gp.gp_Lin(p, d), eps, 1e9)
                best = min((caster.WParameter(k) for k in range(1, caster.NbPnt() + 1)), default=float("inf"))
                kept.append(((p.X(), p.Y(), p.Z()), (d.X(), d.Y(), d.Z()), best))
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
            "faces": faces, "grid": grid}


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
    for k in ("triangles", "engine", "watertight", "faces", "grid"):
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
               max_rays: int = 20000, grid: int = 3, witnesses: int = 10) -> Check:
    """One part's minimum-wall check. Give the print ``mesh`` (trimesh, STL/3MF path, or a shape to
    tessellate), the B-rep ``shape``, or both (both is best: they miss different things).

    Fails when any sample is thinner than ``wall_mm - tol_mm``, when a mesh is not watertight
    (inward rays then mean nothing), or when more than 1 % of rays find no exit.
    """
    if wall_mm <= 0 or tol_mm < 0:
        raise ValueError("wall_mm must be positive and tol_mm non-negative")
    if mesh is None and shape is None:
        raise ValueError(f"part {name!r}: give a mesh, a shape, or both")
    limit = wall_mm - tol_mm
    runs = []
    if mesh is not None:
        runs.append(mesh_thickness(mesh, max_rays=max_rays))
    if shape is not None:
        runs.append(brep_thickness(shape, grid=grid))
    evidence: Dict[str, Any] = {"wall_mm": wall_mm, "tol_mm": tol_mm}
    problems, wit = [], []
    for run in runs:
        evidence[run["method"]] = _summary(run, limit)
        wit += _witnesses(run, limit, witnesses)
        if run.get("watertight") is False:
            problems.append("mesh is not watertight, so inward rays are meaningless")
        if run["rays"] and run["misses"] > 0.01 * run["rays"]:
            problems.append(f"{run['misses']} of {run['rays']} {run['method']} rays found no exit")
    wit.sort(key=lambda w: w["thickness_mm"])
    evidence["witnesses"] = wit[:witnesses]
    mins = [evidence[r["method"]]["min_mm"] for r in runs if evidence[r["method"]]["min_mm"] is not None]
    thinnest = min(mins) if mins else None
    if problems:
        return Check(f"wall:{name}", "fail", "; ".join(problems), (name,), evidence)
    if wit:
        return Check(f"wall:{name}", "fail",
                     f"thinnest {thinnest:.3f} mm < {wall_mm:g} mm (sampled; see witnesses)", (name,), evidence)
    if thinnest is None:
        return Check(f"wall:{name}", "fail", "no ray found an exit; nothing measured", (name,), evidence)
    return Check(f"wall:{name}", "pass", f"thinnest sampled {thinnest:.3f} mm >= {wall_mm:g} mm", (name,), evidence)


def wall_gate(parts: Mapping[str, Mapping[str, Any]], *, out: Any = None, tol_mm: float = 0.01,
              max_rays: int = 20000, grid: int = 3) -> Dict[str, Any]:
    """Run ``check_wall`` per part and return (and with ``out``, write) the verdict.

    ``parts``: ``{name: {"wall_mm": 2.4, "mesh": ..., "shape": ...}}``; ``wall_mm`` is per part.
    """
    checks = [check_wall(name, float(spec["wall_mm"]), mesh=spec.get("mesh"), shape=spec.get("shape"),
                         tol_mm=tol_mm, max_rays=max_rays, grid=grid) for name, spec in parts.items()]
    limits = {name: {"wall_mm": float(spec["wall_mm"])} for name, spec in parts.items()}
    data = verdict("wall", checks, assumptions=ASSUMPTIONS, limits={"tol_mm": tol_mm, "max_rays": max_rays,
                                                                    "brep_grid": grid, "parts": limits})
    if out is not None:
        write_verdict(out, data)
    return data
