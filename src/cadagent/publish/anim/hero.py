"""An assembly hero: a real assembly's CAD edges draw in exploded, the parts slide together, a check pass runs
(clearance, FEA stress, the linkage's motion) and the figure settles on a wordmark and tagline.

Two stages, so the committed SVG can be checked anywhere:

* ``extract(spec, source)`` needs CadQuery and a checkout of the project the spec names. It reads the assembly STEP,
  draws every solid's visible edges by hidden-line removal (``cad.hlr_segments``) and its filled silhouette,
  orders the solids for painting, solves the linkage along its path (``linkage``), measures clearances between
  moving solids with the assembly gates' relation engine (``cadagent.gates.relations.relate``), bands the FEA field
  (``field``) and writes a scene: plain JSON with the drawing in SVG units, the numbers and where they came from
  (the source commit and every input file's sha256).
* ``render(scene, present)`` is plain Python. It writes the SVG, with CSS keyframes and both colour schemes, and
  the words from the spec's ``present`` section (labels, captions), which can change without re-extracting. The
  same inputs always give the same bytes.

What the drawing approximates, stated in the scene and its caption:

* Each solid hides only its own edges. Solids hide each other by painting filled silhouettes back to front, in
  the order that draws the fewest cells wrong, counted on depth rasters of the assembled and the exploded states.
  Interlocking parts (a pin through a bore) have no right order; the scene records how many overlapping cells
  are drawn wrong, of how many.
* The linkage moves each solid as one 2D transform of its drawing: the body's exact rotation in the linkage's
  plane, taken at the middle depth (along the joint axis) of the solid's visible surface. Geometry nearer or farther
  than that depth is off by up to ``motion_error_px`` at the worst pose (the scene records it and the part). The
  hidden lines stay those of the reference pose.
* Clearance is checked at the sampled poses only. A pair of solids whose extents along the joint axes do not
  overlap can never meet while every joint turns about that axis. Such pairs are counted, not queried. The sweep
  is slow (#186), so a previous scene's result is reused when its key (the assembly's sha256 and the parts,
  linkage and clearance specs) is unchanged.
"""
from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from cadagent.publish.anim import raster
from cadagent.publish.anim import svg as S
from cadagent.publish.anim.linkage import Linkage, ellipse_path

SCHEMA = "cadagent.anim.hero/1"
AXES = {"x": 0, "y": 1, "z": 2}


# ----------------------------------------------------------------------------------------------------- extract

def _git_head(root: Path) -> Optional[str]:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _plane(spec: Mapping[str, Any]) -> Tuple[int, int, int]:
    """Indices of the linkage plane's two axes and of the joint axis."""
    u, v = (AXES[a] for a in spec["linkage"]["plane"])
    return u, v, 3 - u - v


def _r(v: float, d: int = 3) -> float:
    return float(round(float(v), d))


CLEARANCE_VERSION = 2      # bump when _clearances changes what it measures: cached results are then recomputed
JOINT_GAP_SPREAD_MM = 0.02  # a pair whose gap changes less than this over the stride is a joint's own interface


def _clearance_key(spec: Mapping[str, Any], assembly_sha256: str) -> str:
    """What the clearance sweep depends on, hashed: a previous result with the same key can be reused."""
    import hashlib

    basis = {"version": CLEARANCE_VERSION, "assembly": assembly_sha256, "parts": spec["parts"],
             "linkage": spec["linkage"], "clearance": spec.get("clearance", {})}
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()


def extract(spec: Mapping[str, Any], source: Path, *, clearance: bool = True,
            previous: Optional[Mapping[str, Any]] = None, workers: int = 1, log=print) -> Dict[str, Any]:
    """The scene for ``spec`` from the project checkout at ``source``. See the module docstring. ``previous``: an
    earlier scene whose clearance result is reused if its key still matches; ``workers``: processes for the
    clearance sweep."""
    from cadagent.publish.anim import cad
    from cadagent.publish.anim.field import read_viewer_field, triangle_fraction
    from cadagent.publish.anim.text import DEJAVU, DEJAVU_BOLD, find_font, outline

    t_start = time.time()
    source = Path(source)
    inputs: Dict[str, str] = {}

    def src(rel: str) -> Path:
        p = source / rel
        inputs[rel] = cad.file_sha256(p)
        return p

    asm_path = src(spec["assembly"])
    solids = cad.read_solids(asm_path)
    log(f"read {len(solids)} solids from {spec['assembly']} ({time.time() - t_start:.1f} s)")

    # ---- parts: named groups of solids, each with its body, explode distance and style; printed parts matched
    parts: List[Dict[str, Any]] = []
    for name, p in spec["parts"].items():
        for i in p["solids"]:
            if not 0 <= i < len(solids):
                raise ValueError(f"part {name}: solid {i} is not in {spec['assembly']} ({len(solids)} solids)")
            parts.append({"solid": i, "part": name, "body": p.get("body", "ground"), "explode": float(p.get("explode", 0)),
                          "style": p.get("style", "plain")})
        if p.get("match"):
            ref = cad.read_solids(src(p["match"]))[0].Volume()
            for i in p["solids"]:
                vol = solids[i].Volume()
                if abs(vol - ref) > 1e-3 * ref:
                    raise ValueError(f"part {name}: solid {i} has {vol:.0f} mm3, {p['match']} has {ref:.0f}: "
                                     "the spec's solid numbers no longer fit the STEP")
    used = [p["solid"] for p in parts]
    if len(set(used)) != len(used):
        raise ValueError("a solid is listed under two parts")

    # ---- linkage: joints measured from the CAD, lengths checked against the design's, poses along the path
    lk = spec["linkage"]
    iu, iv, iaxis = _plane(spec)

    def centre(i: int) -> Tuple[float, float]:
        bb = solids[i].BoundingBox()
        lo, hi = (bb.xmin, bb.ymin, bb.zmin), (bb.xmax, bb.ymax, bb.zmax)
        return ((lo[iu] + hi[iu]) / 2, (lo[iv] + hi[iv]) / 2)

    joints = {j: centre(d["solid"]) for j, d in lk["joints"].items()}
    link = Linkage(ground={g: joints[g] for g in lk["ground"]}, links={b: tuple(js) for b, js in lk["links"].items()},
                   reference=joints, solve=[tuple(s) for s in lk["solve"]])
    tol = float(lk.get("expect", {}).get("tolerance_mm", 0.5))
    lengths = {}
    for pair, want in lk.get("expect", {}).get("lengths", {}).items():
        a, b = pair.split("-")
        got = math.dist(joints[a], joints[b])
        lengths[pair] = _r(got, 2)
        if abs(got - want) > tol:
            raise ValueError(f"linkage {pair}: {got:.2f} mm in the CAD, {want} in the design")
    path_spec = lk["path"]["ellipse"]
    samples = int(lk["path"]["samples"])
    path = ellipse_path(tuple(path_spec["centre"]), tuple(path_spec["radii"]), path_spec["start_deg"], samples)
    if math.dist(path[0], joints[lk["driven"]]) > tol:
        raise ValueError(f"the path starts at {path[0]}, not at {lk['driven']}'s reference {joints[lk['driven']]}")
    poses = link.sweep(lk["driven"], path)
    dead = [min(min(a, 180 - a) for a in (link.angle_at(p, j, x, y) for p in poses)) for j, x, y in lk.get("dead_points", [])]
    log(f"linkage: {len(poses)} poses, lengths {lengths}")

    # ---- view and per-solid geometry
    view = cad.View(tuple(spec["view"]["direction"]), tuple(spec["view"].get("up", (0, 0, 1))))
    d3, right, up = view.basis()
    geo: Dict[int, Dict[str, Any]] = {}
    t0 = time.time()
    for p in parts:
        s = solids[p["solid"]]
        v, t = cad.triangles(s, float(spec.get("mesh_mm", 0.3)), 0.4)
        xy, z = view.project(v)
        geo[p["solid"]] = {"seg": cad.hlr_segments(s, view), "v": v, "t": t, "xy": xy, "z": z}
    log(f"hidden lines and meshes for {len(parts)} solids: {time.time() - t0:.1f} s")

    def plane_to_world(uv: Tuple[float, float], depth: float) -> np.ndarray:
        w = np.zeros(3)
        w[iu], w[iv], w[iaxis] = uv[0], uv[1], depth
        return w

    # M2: the linkage plane's (u, v) to drawing (x, y down), per mm; a_axis: the joint axis's drawing direction
    eu, ev = np.zeros(3), np.zeros(3)
    eu[iu], ev[iv] = 1, 1
    M2 = np.stack([view.vector(eu), view.vector(ev)], axis=1)            # columns: images of u and v
    axis_vec = np.zeros(3)
    axis_vec[iaxis] = 1
    a_axis = view.vector(axis_vec)
    bodies = sorted({p["body"] for p in parts if p["body"] != "ground"})
    for b in bodies:
        if b not in link.links:
            raise ValueError(f"body {b} is not a link of the linkage")

    # Each body turns about its first joint. A solid at depth w along the joint axis is drawn exactly by the body's
    # 2D motion conjugated with a shift of w along the axis's drawing direction: shift, move, shift back. The body's
    # motion is written once (pivot at depth 0); each solid carries its own static shift (its visible mean depth).
    def motion2d(b: str, pose, depth: float = 0.0) -> np.ndarray:
        """3x3 drawing-space (mm) affine for body b at pose, exact at ``depth`` along the joint axis."""
        turn, r0, p0 = link.body_motion(b, pose)
        c, s_ = math.cos(turn), math.sin(turn)
        L = M2 @ np.array([[c, -s_], [s_, c]]) @ np.linalg.inv(M2)
        q0 = view.project([plane_to_world(r0, depth)])[0][0]
        q1 = view.project([plane_to_world(p0, depth)])[0][0]
        A = np.eye(3)
        A[:2, :2] = L
        A[:2, 2] = q1 - L @ q0
        return A

    solid_depth = {p["solid"]: float(geo[p["solid"]]["v"][:, iaxis].mean()) for p in parts}

    explode_vec = {p["solid"]: a_axis * p["explode"] for p in parts}

    # ---- layout: the assembled leg and every pose fill the stage; the exploded start is fitted by a camera zoom
    stage = spec["stage"]
    pts_all, pts_ex = [], []
    for p in parts:
        xy = geo[p["solid"]]["xy"]
        pts_all.append(xy)
        pts_ex.append(xy + explode_vec[p["solid"]])
        if p["body"] != "ground":
            for pose in poses:
                A = motion2d(p["body"], pose, solid_depth[p["solid"]])
                pts_all.append(xy @ A[:2, :2].T + A[:2, 2])
    allp = np.concatenate(pts_all)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    U = S.UNITS_PER_PX
    k = min(stage["w"] * U / (hi[0] - lo[0]), stage["h"] * U / (hi[1] - lo[1]))       # units per mm
    off = np.array([stage["x"] * U + (stage["w"] * U - (hi[0] - lo[0]) * k) / 2 - lo[0] * k,
                    stage["y"] * U + (stage["h"] * U - (hi[1] - lo[1]) * k) / 2 - lo[1] * k])
    to_units = lambda xy: np.asarray(xy) * k + off
    ex = to_units(np.concatenate(pts_ex))
    elo, ehi = ex.min(axis=0), ex.max(axis=0)
    room = spec.get("explode_room", stage)
    rlo = np.array([room["x"], room["y"]]) * U
    rsz = np.array([room["w"], room["h"]]) * U
    zoom = float(min(1.0, *(rsz / (ehi - elo))))
    cam = (rlo + rsz / 2) - zoom * (elo + ehi) / 2
    log(f"scale {k / U:.3f} px/mm; exploded start zoomed to {zoom:.2f}")

    # ---- depth rasters: assembled and exploded, one cell per unit (half a pixel)
    W, H = int(spec["width"] * U), int(spec["height"] * U)
    grid = (0.0, 0.0, 1.0)
    t0 = time.time()
    zb: Dict[str, Dict[int, np.ndarray]] = {"assembled": {}, "exploded": {}}
    for p in parts:
        g = geo[p["solid"]]
        tri = to_units(g["xy"])[g["t"]]
        dz = g["z"][g["t"]]
        zb["assembled"][p["solid"]] = raster.zbuffer(tri, dz, grid, (H, W))[0]
        zb["exploded"][p["solid"]] = raster.zbuffer(tri + explode_vec[p["solid"]] * k, dz, grid, (H, W))[0]
    log(f"depth rasters: {time.time() - t0:.1f} s")
    ids = [p["solid"] for p in parts]
    visible = {i: 0 for i in ids}
    in_front: Dict[Tuple[int, int], int] = {}   # (a, b): cells, over both states, where a is in front of b
    for state in zb.values():
        stack = np.stack([state[i] for i in ids])
        covered = np.isfinite(stack)
        front = np.argmax(stack, axis=0)
        anything = covered.any(axis=0)
        for n, i in enumerate(ids):
            visible[i] += int(((front == n) & anything).sum())
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                both = covered[a] & covered[b]
                if not both.any():
                    continue
                a_front = int((stack[a][both] > stack[b][both]).sum())
                b_front = int(both.sum()) - a_front
                in_front[(ids[a], ids[b])] = in_front.get((ids[a], ids[b]), 0) + a_front
                in_front[(ids[b], ids[a])] = in_front.get((ids[b], ids[a]), 0) + b_front
    min_cells = int(spec.get("min_visible_cells", 6))
    drawn = [i for i in ids if visible[i] >= min_cells]
    hidden = [i for i in ids if visible[i] < min_cells]
    # painter's order: back to front by the depth rasters' majority, cycles broken where they cost fewest cells.
    # Interlocking parts make some cells wrong whatever the order: the scene records how many, of all the cells
    # where two solids overlap.
    meanz = {i: float(geo[i]["z"].mean()) for i in drawn}
    order, left = painter_order(drawn, in_front, meanz)
    overlap_cells = sum(in_front.get((a, b), 0) for a in drawn for b in drawn if a != b)
    # where two solids each lie in front over some cells (a pin through a bore), one of the two sets is drawn wrong
    # whatever the order: that much is unavoidable, the rest is the order's own error
    unavoidable = sum(min(in_front.get((a, b), 0), in_front.get((b, a), 0)) for a in drawn for b in drawn if a < b)
    log(f"painter's order: {left} of {overlap_cells} overlapping cells drawn wrong, {unavoidable} of them unavoidable")

    # ---- depth slabs: a moving solid is drawn in slices along the joint axis, each moved at its own middle depth
    asm = zb["assembled"]
    stack = np.stack([asm[i] for i in ids])
    front_id = np.array(ids)[np.argmax(stack, axis=0)]
    front_z = stack.max(axis=0)
    slab_mm = float(spec.get("slab_mm", 12.0))
    max_slabs = int(spec.get("max_slabs", 6))
    seen_v: Dict[int, np.ndarray] = {}
    slabs: Dict[int, List[Tuple[float, float, float]]] = {}       # solid -> [(from, to, depth)] along the axis
    axis_depth: Dict[int, np.ndarray] = {}
    for p in parts:
        i = p["solid"]
        g = geo[i]
        q = np.round(to_units(g["xy"])).astype(int)
        ok = (q[:, 0] >= 0) & (q[:, 1] >= 0) & (q[:, 0] < W) & (q[:, 1] < H)
        seen = np.zeros(len(q), bool)
        seen[ok] = (front_id[q[ok, 1], q[ok, 0]] == i) & (g["z"][ok] >= front_z[q[ok, 1], q[ok, 0]] - 1.0)
        seen_v[i] = g["v"][seen]
        if p["body"] == "ground":
            slabs[i] = [(-math.inf, math.inf, solid_depth[i])]
            continue
        # the depth along the axis of the solid's front surface, per cell (each triangle's mean)
        tri = to_units(g["xy"])[g["t"]]
        axis_depth[i] = raster.zbuffer(tri, g["z"][g["t"]], grid, (H, W),
                                       values=g["v"][:, iaxis][g["t"]].mean(axis=1))[1]
        visible_depths = np.concatenate([axis_depth[i][(front_id == i) & np.isfinite(asm[i])], seen_v[i][:, iaxis]])
        if not len(visible_depths):
            slabs[i] = [(-math.inf, math.inf, solid_depth[i])]      # hidden when assembled: its mean depth
            continue
        # the visible depths, cut into slices no deeper than slab_mm; each slice's middle depth minimises the
        # largest error over it
        lo_d, hi_d = float(visible_depths.min()), float(visible_depths.max())
        n = max(1, min(max_slabs, math.ceil((hi_d - lo_d) / slab_mm - 1e-9)))
        cuts = np.linspace(lo_d, hi_d, n + 1)
        slabs[i] = [(-math.inf if j == 0 else float(cuts[j]), math.inf if j == n - 1 else float(cuts[j + 1]),
                     float(cuts[j] + cuts[j + 1]) / 2) for j in range(n)]
        solid_depth[i] = (lo_d + hi_d) / 2

    def slab_of(i: int, depth: np.ndarray) -> np.ndarray:
        edges_ = np.array([b for _, b, _ in slabs[i][:-1]])
        return np.searchsorted(edges_, depth, side="right")

    # how far the drawn motion is from the exact 3D one, over each moving solid's visible vertices, at every pose
    motion_err, worst = 0.0, None
    err_by_part: Dict[str, float] = {}
    for p in parts:
        i = p["solid"]
        if p["body"] == "ground" or not len(seen_v[i]):
            continue
        v = seen_v[i]
        xy = view.project(v)[0]
        which = slab_of(i, v[:, iaxis])
        for pose in poses:
            turn, r0, p0 = link.body_motion(p["body"], pose)
            c, s_ = math.cos(turn), math.sin(turn)
            w = v.copy()
            du, dv = v[:, iu] - r0[0], v[:, iv] - r0[1]
            w[:, iu], w[:, iv] = p0[0] + c * du - s_ * dv, p0[1] + s_ * du + c * dv
            exact = view.project(w)[0]
            for j, (_, _, depth) in enumerate(slabs[i]):
                m = which == j
                if not m.any():
                    continue
                A = motion2d(p["body"], pose, depth)
                e = float(np.linalg.norm(exact[m] - (xy[m] @ A[:2, :2].T + A[:2, 2]), axis=1).max()) * k / U
                err_by_part[p["part"]] = max(err_by_part.get(p["part"], 0.0), e)
                if e > motion_err:
                    motion_err, worst = e, p["part"]
    n_slabs = sum(len(v) for v in slabs.values())
    log(f"painter's order: {len(order)} solids drawn, {len(hidden)} never visible; "
        f"{n_slabs} depth slabs; motion error up to {motion_err:.2f} px ({worst})")

    # ---- the drawing: per solid and slab, its silhouette and its edges, in units
    out_solids = []
    for i in order:
        p = next(q for q in parts if q["solid"] == i)
        mask = np.isfinite(asm[i])
        segs = cad.transform_segments(geo[i]["seg"], k, tuple(off))
        if len(slabs[i]) == 1:
            masks, seg_groups = [mask], [segs]
        else:
            # each cell and edge goes to the slab of its depth along the axis
            cell_slab = np.where(mask, slab_of(i, np.nan_to_num(axis_depth[i], nan=0.0)), -1)
            # one cell of overlap between neighbouring slabs, so no seam shows between their fills
            masks = [raster.dilate(cell_slab == j) & mask for j in range(len(slabs[i]))]
            seg_groups = [[] for _ in slabs[i]]
            for sg in segs:
                ends = [(sg[1], sg[2]), (sg[-2], sg[-1])] if sg[0] != "A" else [(sg[1], sg[2]), (sg[3], sg[4])]
                found = [raster.nearest(cell_slab, x, y, -1) for x, y in ends]
                found = [f for f in found if f >= 0]
                seg_groups[int(round(sum(found) / len(found))) if found else 0].append(sg)
        out = []
        for (_, _, depth), m, sg in zip(slabs[i], masks, seg_groups):
            loops = raster.region(m, grid, float(spec.get("outline_tol", 0.6)), min_area=2.0)
            out.append({"shift": [_r(c, 2) for c in a_axis * depth * k], "depth_mm": _r(depth, 1),
                        "fill": S.polygon_d(loops), "edges": S.segments_d(sg)})
        out_solids.append({"solid": i, "part": p["part"], "body": p["body"], "style": p["style"],
                           "explode": [_r(c, 1) for c in explode_vec[i] * k], "slabs": out})

    # ---- the FEA field on its part
    fea_out = None
    if spec.get("fea"):
        fs = spec["fea"]
        f = read_viewer_field(src(fs["field"]))
        host = [p for p in parts if p["part"] == fs["part"]]
        if len(host) != 1:
            raise ValueError(f"fea.part {fs['part']} must name one solid")
        host_id = host[0]["solid"]
        xy, z = view.project(f["positions"])
        tri = to_units(xy)[f["triangles"]]
        frac = triangle_fraction(f)
        fz, fv = raster.zbuffer(tri, z[f["triangles"]], grid, (H, W), values=frac)
        mine = np.isfinite(asm[host_id])
        edges_ = [float(e) for e in fs["bands"]]
        bands = []
        for n, (lo_b, hi_b) in enumerate(zip(edges_, edges_[1:] + [math.inf])):
            m = mine & np.isfinite(fv) & (fv >= lo_b) & (fv < hi_b)
            loops = raster.region(m, grid, 0.8, min_area=3.0)
            if loops:
                bands.append({"band": n, "from": lo_b, "to": None if hi_b == math.inf else hi_b, "d": S.polygon_d(loops)})
        # the hottest point a viewer can see: the highest band cell where the frame is in front in the assembly
        seen = mine & (front_id == host_id) & np.isfinite(fv)
        j, i_ = np.unravel_index(np.nanargmax(np.where(seen, fv, -1)), fv.shape)
        fea_out = {"part": fs["part"], "solid": host_id, "case": fs.get("case", ""), "title": fs.get("title", ""),
                   "bands": bands, "band_edges": edges_, "material": f["material"],
                   "strength_mpa": f["strength_mpa"], "design_mpa": _r(f["design_mpa"], 2),
                   "first_failure_factor": f["first_failure_factor"], "safety_factor": f["safety_factor"],
                   "load_from": f["load_from"], "mesh": f["mesh"], "assumptions": f["assumptions"],
                   "visible_peak": {"x": int(i_), "y": int(j), "fraction": _r(fv[j, i_], 3)},
                   "peak_fraction": _r(f["design_mpa"] / f["strength_mpa"], 3)}
        log(f"FEA bands: {len(bands)}; visible peak {fv[j, i_]:.3f} of strength")

    # ---- clearance between moving solids along the path
    clear_out = None
    if clearance:
        key = _clearance_key(spec, inputs[spec["assembly"]])
        old = (previous or {}).get("clearance") or {}
        if old.get("key") == key:
            clear_out = json.loads(json.dumps(old))
            log(f"clearance: reused the previous scene's sweep ({old.get('pairs_queried')} queries, key {key[:12]})")
        else:
            clear_out = _clearances(spec, solids, parts, link, poses, iaxis, iu, iv, log, assembly=asm_path,
                                    workers=workers)
            clear_out["key"] = key
        w = clear_out.get("closest")
        if w:
            # the witness points where the closest pose draws them: shown when the stride passes that pose
            w["drawn"] = [[_r(c, 1) for c in to_units(view.project([np.array(q, float)])[0][0])]
                          for q in (w["point_a"], w["point_b"])]

    # ---- kinematics for the drawing
    def units_pt(uv, depth):
        return [_r(c, 1) for c in to_units(view.project([plane_to_world(uv, depth)])[0][0])]

    frames = {}
    for b in bodies:
        rows = []
        for pose in poses:
            turn, r0, p0 = link.body_motion(b, pose)
            q0 = to_units(view.project([plane_to_world(r0, 0.0)])[0][0])
            q1 = to_units(view.project([plane_to_world(p0, 0.0)])[0][0])
            rows.append([_r(q1[0] - q0[0], 2), _r(q1[1] - q0[1], 2), _r(math.degrees(turn), 3)])
        frames[b] = {"pivot": units_pt(link.reference[link.links[b][0]], 0.0), "frames": rows}
    # the driven joint's trace, at the depth of the outermost solid it carries (for a wheel: its outer face)
    driven = lk["driven"]
    drive_body = next(b for b in bodies if driven in link.links[b])
    trace_depth = max(solid_depth[p["solid"]] for p in parts if p["body"] == drive_body)
    trace = [units_pt(p[driven], trace_depth) for p in poses]

    # ---- text outlines
    texts = {}
    for key, t in spec.get("text", {}).items():
        font = find_font(DEJAVU_BOLD if t.get("weight") == "bold" else DEJAVU)
        size = float(t["size"])
        o = outline(t["text"], font, size * U, t.get("tracking", 0.0))
        if t.get("max_width") and o["width"] > t["max_width"] * U:          # shrink to fit its column
            size *= t["max_width"] * U / o["width"]
            o = outline(t["text"], font, size * U, t.get("tracking", 0.0))
        texts[key] = {"text": t["text"], "d": S.polygon_d(o["loops"]), "width": _r(o["width"] / U, 1),
                      "size": _r(size, 2), "font": font.name}

    lin = M2
    scene = {
        "schema": SCHEMA,
        "name": spec["name"],
        "source": {"repo": spec["source"]["repo"], "name": spec["source"]["name"], "licence": spec["source"]["licence"],
                   "commit": _git_head(source), "inputs": dict(sorted(inputs.items()))},
        "width": spec["width"], "height": spec["height"], "units_per_px": U, "px_per_mm": _r(k / U, 4),
        "view": {"direction": list(spec["view"]["direction"]), "up": list(spec["view"].get("up", (0, 0, 1)))},
        "plane_matrix": [_r(lin[0, 0], 6), _r(lin[1, 0], 6), _r(lin[0, 1], 6), _r(lin[1, 1], 6)],
        "camera": {"zoom": _r(zoom, 4), "translate": [_r(cam[0], 1), _r(cam[1], 1)]},
        "solids": out_solids, "hidden_solids": sorted(hidden), "painter": {"misordered_cells": left, "unavoidable_cells": unavoidable, "overlap_cells": overlap_cells},
        "linkage": {"lengths_mm": lengths, "samples": samples, "path": path_spec, "dead_point_margin_deg": [_r(d, 1) for d in dead],
                    "bodies": frames, "trace": trace, "trace_depth_mm": _r(trace_depth, 1),
                    "motion_error_px": _r(motion_err, 2), "motion_error_part": worst,
                    "motion_error_px_by_part": {n: _r(e, 2) for n, e in sorted(err_by_part.items())},
                    "reach_mm": [_r(min(math.dist(p[driven], (0, 0)) for p in poses), 1),
                                 _r(max(math.dist(p[driven], (0, 0)) for p in poses), 1)]},
        "fea": fea_out, "clearance": clear_out, "text": texts,
        "extract_seconds": None,
    }
    scene["extract_seconds"] = _r(time.time() - t_start, 1)
    return scene


def _clearances(spec, solids, parts, link, poses, iaxis, iu, iv, log, *, assembly: Path,
                workers: int = 1) -> Dict[str, Any]:
    """The closest approach between solids that move relative to each other, over the sampled poses, by the
    relation engine, per pair of parts.

    Pairs whose extents along the joint axis do not overlap are counted as separated. A pair of parts whose gap is
    the same at every sampled pose turns about its own shared axis: it is a joint's own interface (a flange on its
    motor, a pin in its bearing, a spacer beside a bearing). It is listed, and left out of the closest gap, which is
    about parts that move past each other. ``workers`` > 1 measures poses in parallel processes, each reading the STEP
    once; the result is the same."""
    cs = spec.get("clearance", {})
    every = int(cs.get("every", 1))
    near = float(cs.get("near_mm", 10.0))
    skip = {tuple(sorted(p)) for p in cs.get("skip_parts", [])}
    named = {p["solid"]: p for p in parts}
    ids = sorted(named)
    rng = {}
    for i in ids:
        bb = solids[i].BoundingBox()
        lo, hi = (bb.xmin, bb.ymin, bb.zmin), (bb.xmax, bb.ymax, bb.zmax)
        rng[i] = (lo[iaxis], hi[iaxis])
    pairs, separated = [], 0
    for x in range(len(ids)):
        for y in range(x + 1, len(ids)):
            a, b = ids[x], ids[y]
            if named[a]["body"] == named[b]["body"]:
                continue                                   # one rigid body: they never move relative to each other
            if tuple(sorted((named[a]["part"], named[b]["part"]))) in skip:
                continue
            if rng[a][1] < rng[b][0] or rng[b][1] < rng[a][0]:
                separated += 1
                continue
            pairs.append((a, b))

    def matrix(i, pose) -> List[float]:
        body = named[i]["body"]
        if body == "ground":
            return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]
        turn, r0, p0 = link.body_motion(body, pose)
        c, s_ = math.cos(turn), math.sin(turn)
        R = np.eye(3)
        R[iu, iu], R[iu, iv], R[iv, iu], R[iv, iv] = c, -s_, s_, c
        r0w, p0w = np.zeros(3), np.zeros(3)
        r0w[iu], r0w[iv], p0w[iu], p0w[iv] = r0[0], r0[1], p0[0], p0[1]
        t = p0w - R @ r0w
        return [float(v) for v in (*R[0], t[0], *R[1], t[1], *R[2], t[2])]

    checked = [n for n in range(len(poses) - 1) if n % every == 0]     # the last pose repeats the first
    jobs = []
    for n in checked:
        mine = [(a, b) for a, b in pairs if not (named[a]["body"] == "ground" and named[b]["body"] == "ground")]
        used = sorted({i for ab in mine for i in ab})
        jobs.append((str(assembly), n, {i: matrix(i, poses[n]) for i in used}, mine, near))
    t0 = time.time()
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        from multiprocessing import get_context

        with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as ex:
            results = []
            for r in ex.map(_sweep_pose, jobs):
                results.append(r)
                log(f"  clearance pose {r[0]}: {len(r[1])} queries, {time.time() - t0:.0f} s")
    else:
        results = []
        for job in jobs:
            results.append(_sweep_pose(job, solids))
            log(f"  clearance pose {results[-1][0]}: {len(results[-1][1])} queries, {time.time() - t0:.0f} s")

    clashes, closest, interfaces, table = summarise_sweep(results, {i: named[i]["part"] for i in named}, checked)
    queried = sum(len(rows) for _, rows in results)
    return {"poses": len(checked), "pairs_queried": queried, "pairs_separated_along_axis": separated,
            "pairs_in_reach": len(pairs), "clashes": clashes, "closest": closest, "joint_interfaces": interfaces,
            "pairs": table, "near_mm": near, "seconds": _r(time.time() - t0, 1), "workers": workers,
            "limits": "sampled poses only (not a swept volume); exact gaps by cadagent.gates.relations.relate; "
                      f"a pair whose gap varies by at most {JOINT_GAP_SPREAD_MM} mm over every pose is taken as a "
                      "joint's own interface and left out of the closest gap"}


def painter_order(ids: Sequence[int], front: Mapping[Tuple[int, int], int],
                  depth: Mapping[int, float]) -> Tuple[List[int], int]:
    """Back to front (``front[(a, b)]``: cells where a is in front of b). Each step paints the solid that is in
    front, by majority, of the fewest cells of those not yet painted: a solid behind all of them costs nothing, and
    in a cycle the cheapest majority is broken. Ties by ``depth`` (smaller is farther), then id. Returns the order
    and how many cells it draws wrong in all."""
    net = lambda i, j: front.get((i, j), 0) - front.get((j, i), 0)
    order, done, wrong = [], set(), 0
    while len(order) < len(ids):
        todo = [i for i in ids if i not in done]
        cost = {i: sum(max(0, net(i, j)) for j in todo if j != i) for i in todo}
        nxt = min(todo, key=lambda i: (cost[i], depth[i], i))
        wrong += sum(front.get((nxt, j), 0) for j in todo if j != nxt)
        order.append(nxt)
        done.add(nxt)
    return order, wrong


def summarise_sweep(results, part_of: Mapping[int, str], checked: Sequence[int]):
    """The sweep's per-pose rows ``[(pose, [(solid a, solid b, state, gap, overlap, point a, point b)])]`` per pair
    of parts: (clashes, the closest gap between parts that move past each other, joint interfaces, the table).
    ``part_of`` names each solid's part; ``checked`` are the poses measured."""
    by_pair: Dict[Tuple[str, str], Dict[str, Any]] = {}
    clashes = []
    for n, rows in results:
        for a, b, state, gap, overlap, pa, pb in rows:
            key = tuple(sorted((part_of[a], part_of[b])))
            e = by_pair.setdefault(key, {"parts": list(key), "poses": set(), "touching": set(), "min_gap_mm": None,
                                         "gaps": {}})
            e["poses"].add(n)
            if state in ("overlapping", "contains"):
                clashes.append({"pose": n, "a": part_of[a], "b": part_of[b], "overlap_mm3": overlap})
                continue
            if state == "touching":
                e["touching"].add(n)
            e["gaps"][n] = min(gap, e["gaps"].get(n, math.inf))      # per pose: the closest of the parts' solids
            if e["min_gap_mm"] is None or gap < e["min_gap_mm"]:
                e.update(min_gap_mm=gap, pose=n, solids=[a, b], point_a=pa, point_b=pb)
    table, interfaces, closest, best = [], [], None, math.inf
    for key in sorted(by_pair):
        e = by_pair[key]
        gaps = list(e["gaps"].values())
        spread = max(gaps) - min(gaps) if gaps else math.inf
        # the same gap at every pose: the pair turns about its own shared axis, a joint's own interface
        joint = set(e["gaps"]) == set(checked) and spread <= JOINT_GAP_SPREAD_MM
        table.append({"parts": e["parts"], "queried_poses": len(e["poses"]), "touching_poses": len(e["touching"]),
                      "min_gap_mm": None if e["min_gap_mm"] is None else _r(e["min_gap_mm"], 3),
                      "gap_spread_mm": None if not gaps else _r(spread, 3), "joint_interface": joint})
        if joint:
            interfaces.append(e["parts"])
        elif e["min_gap_mm"] is not None and e["min_gap_mm"] < best:
            best = e["min_gap_mm"]
            a, b = e["solids"]
            closest = {"pose": e["pose"], "a": a, "b": b, "part_a": part_of[a], "part_b": part_of[b],
                       "gap_mm": _r(best, 3), "point_a": e["point_a"], "point_b": e["point_b"]}
    return clashes, closest, interfaces, table


_WORKER_SOLIDS: Dict[str, list] = {}


def _sweep_pose(job, solids=None):
    """One pose of the clearance sweep: (pose, [(solid a, solid b, state, gap, overlap, point a, point b)]). Runs
    in a worker process when ``solids`` is None, reading the STEP once per process."""
    from cadagent.gates.relations import Tolerances, relate
    from cadagent.publish.anim import cad

    path, n, matrices, pairs, near = job
    if solids is None:
        if path not in _WORKER_SOLIDS:
            _WORKER_SOLIDS[path] = cad.read_solids(Path(path))
        solids = _WORKER_SOLIDS[path]
    tol = Tolerances()
    placed = {i: cad.moved(solids[i], m) for i, m in matrices.items()}
    rows = []
    for a, b in pairs:
        pa, pb = placed[a], placed[b]
        ba, bb_ = pa.BoundingBox(), pb.BoundingBox()
        gapbox = max(ba.xmin - bb_.xmax, bb_.xmin - ba.xmax, ba.ymin - bb_.ymax, bb_.ymin - ba.ymax,
                     ba.zmin - bb_.zmax, bb_.zmin - ba.zmax, 0.0)
        if gapbox > near:
            continue
        r = relate(pa, pb, tol, contact_area=False)
        if r.state == "unknown":
            raise RuntimeError(f"relation unknown for solids {a} / {b} at pose {n}: {r.error}")
        rows.append((a, b, r.state, float(r.gap_mm or 0.0), float(r.overlap_mm3 or 0.0),
                     r.witness.get("point_a"), r.witness.get("point_b")))
    return n, rows


def read_spec(path: Path) -> Dict[str, Any]:
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def write_scene(scene: Mapping[str, Any], path: Path) -> None:
    Path(path).write_text(json.dumps(scene, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------------- render

# style -> fill colour; every style's edges use --edge
FILLS = {"frame": "fill", "link": "linkf", "metal": "metal", "dark": "dark", "tyre": "dark", "hub": "metal",
         "stop": "stop", "plain": "fill"}
# (light, dark) colours the hero adds to the shared theme. Stress bands run cold to hot, as FEA plots do.
HERO_COLOURS = {
    "linkf": ("#fbe3ad", "#5a4518"), "stop": ("#e38f72", "#8c3a24"), "scan": ("#2f7d5b", "#5cc8a0"),
    "tyreedge": ("#8c9a96", "#7f8e8a"),
}
STRESS = ["#2c6fbb", "#1f9fd0", "#22c0b4", "#8bd88f", "#e9e46a", "#f5b744", "#ef7d2d", "#d8401f", "#a8170f"]


class Phases:
    """The loop's timeline in seconds."""
    period = 10.5
    draw = (0.25, 2.3)           # edges draw in, solid by solid in painter's order; each takes ``stroke``
    stroke = 0.9
    fills = (1.4, 2.4)
    assemble = (2.4, 3.4)
    scan = (3.5, 4.5)            # clearance
    fea = (4.5, 5.8)
    motion = (5.9, 8.3)
    words = (8.1, 8.7)
    fade = (10.1, 10.5)          # everything out, before the loop restarts


def _fmt(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}"


def render(scene: Mapping[str, Any], present: Mapping[str, Any]) -> str:
    """The SVG for a hero ``scene`` with the words in ``present`` (the spec's ``present`` section). Deterministic:
    the same inputs give the same bytes."""
    if scene.get("schema") != SCHEMA:
        raise ValueError(f"not a {SCHEMA} scene")
    U = scene["units_per_px"]
    W, H = scene["width"], scene["height"]
    ph = Phases
    P = ph.period
    tl = S.Timeline(P)
    css: List[str] = []
    body: List[str] = []
    light = dict(S.THEME.light, **{k: v[0] for k, v in HERO_COLOURS.items()})
    dark = dict(S.THEME.dark, **{k: v[1] for k, v in HERO_COLOURS.items()})
    theme = S.Theme(light, dark)
    n_ = lambda v, d=1: S.num(v, d)

    css.append(".e{fill:none;stroke:var(--edge);stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round;"
               "stroke-dasharray:1 1}.ty .e{stroke:var(--tyreedge)}")
    for style, var in FILLS.items():
        css.append(f".s{style[:2]}{{fill:var(--{var})}}")
    css.append(".m{transform-box:view-box;transform-origin:0 0}")

    # ---- the camera: the exploded start is zoomed out to fit, and zooms in as the parts come together
    cam = scene["camera"]
    z0, (cx, cy) = cam["zoom"], cam["translate"]
    a0, a1 = ph.assemble
    cam_tf = lambda v: (f"transform:translate({n_(cx * v)}px,{n_(cy * v)}px) "
                        f"scale({n_(1 + (z0 - 1) * v, 4)})")
    tl.add(".cam", [(0, 1), (a0, 1), (a1, 0), (P, 0)], cam_tf, "ease-in-out")
    css.append(f".cam{{{cam_tf(0)}}}")

    # ---- each body's motion along the path: translate, then the plane's rotation, about its pivot at depth 0
    a, b_, c, d = scene["plane_matrix"]
    det = a * d - b_ * c
    inv = (d / det, -b_ / det, -c / det, a / det)
    mat = lambda m: "matrix(" + ",".join(S.num(v, 5) for v in m) + ",0,0)"
    m0, m1 = ph.motion
    body_cls = {}
    for i, (name, bd) in enumerate(sorted(scene["linkage"]["bodies"].items())):
        body_cls[name] = f"k{i}"
        px, py = bd["pivot"]
        rows = bd["frames"]
        n = len(rows) - 1
        frames = [(0, rows[0])] + [(m0 + (m1 - m0) * j / n, f) for j, f in enumerate(rows)] + [(P, rows[0])]

        def tf(f, px=px, py=py):
            return (f"transform:translate({n_(px + f[0], 2)}px,{n_(py + f[1], 2)}px) {mat((a, b_, c, d))} "
                    f"rotate({n_(f[2], 3)}deg) {mat(inv)} translate({n_(-px, 2)}px,{n_(-py, 2)}px)")
        css.append(f".k{i}{{{tf(rows[0])}}}")
        tl.add(f".k{i}", frames, tf, "linear")

    # ---- explode: each distinct offset is a class; outer parts start moving last
    solids = scene["solids"]
    mags = sorted({math.hypot(*s_["explode"]) for s_ in solids})
    ex_cls: Dict[Tuple[float, float], str] = {}
    for s_ in solids:
        key = tuple(s_["explode"])
        if key in ex_cls:
            continue
        name = f"x{len(ex_cls)}"
        ex_cls[key] = name
        frac = mags.index(math.hypot(*key)) / max(1, len(mags) - 1)
        go = a0 + 0.3 * (a1 - a0) * frac
        arrive = min(a1, go + 0.7 * (a1 - a0))
        tr = lambda v, ex=key[0], ey=key[1]: f"transform:translate({n_(ex * v)}px,{n_(ey * v)}px)"
        tl.add(f".{name}", [(0, 1), (go, 1), (arrive, 0), (P, 0)], tr, "ease-in-out")

    # ---- the drawing, in painter's order; the FEA bands sit on their part, under its edges
    fea = scene.get("fea")
    clear = scene.get("clearance") or {}
    closest = clear.get("closest") or {}
    pair = {closest.get("a"), closest.get("b")} - {None}
    highlight: List[str] = []
    body.append('<g class="cam m"><g class="draw">')
    for n, s_ in enumerate(solids):
        moving = s_["body"] != "ground"

        def slab(sl, inner, body_=s_["body"]):
            """A slab moves with its body, exactly at its own depth: shift to that depth, move, shift back."""
            if not moving:
                return inner
            sx, sy = sl["shift"]
            return (f'<g transform="translate({n_(sx)} {n_(sy)})"><g class="m {body_cls[body_]}">'
                    f'<g transform="translate({n_(-sx)} {n_(-sy)})">{inner}</g></g></g>')
        fea_here = fea and s_["solid"] == fea["solid"]
        fills = "".join(slab(sl, f'<path class="f s{s_["style"][:2]}" fill-rule="evenodd" d="{sl["fill"]}"/>'
                             + ("".join(f'<path class="fb fb{bd["band"]}" d="{bd["d"]}"/>' for bd in fea["bands"])
                                if fea_here else "")) for sl in s_["slabs"] if sl["fill"])
        edges = "".join(slab(sl, f'<path class="e d{n}" pathLength="1" d="{sl["edges"]}"/>')
                        for sl in s_["slabs"] if sl["edges"])
        cls = " ty" if s_["style"] == "tyre" else ""
        body.append(f'<g class="m {ex_cls[tuple(s_["explode"])]}{cls}">{fills}{edges}</g>')
        if s_["solid"] in pair:
            highlight += [sl["edges"] for sl in s_["slabs"] if sl["edges"]]
        t0 = ph.draw[0] + (ph.draw[1] - ph.stroke - ph.draw[0]) * n / max(1, len(solids) - 1)
        tl.add(f".d{n}", [(0, 1), (t0, 1), (t0 + ph.stroke, 0), (P, 0)],
               lambda v: f"stroke-dashoffset:{n_(v, 2)}", "ease-out")
    body.append("</g>")
    tl.opacity(".f", [(0, 0), (ph.fills[0], 0), (ph.fills[1], 1), (P, 1)])
    tl.opacity(".draw", [(0, 1), (ph.fade[0], 1), (ph.fade[1], 0)])
    if fea:
        f0, f1 = ph.fea
        nb = len(fea["bands"])
        for i, bd in enumerate(fea["bands"]):
            css.append(f".fb{bd['band']}{{fill:{STRESS[min(bd['band'], len(STRESS) - 1)]}}}")
            on = f0 + 0.15 + (f1 - f0 - 0.6) * i / max(1, nb - 1)
            tl.opacity(f".fb{bd['band']}", [(0, 0), (on, 0), (on + 0.35, 1), (P, 1)])

    # ---- the clearance check: a scan across the drawing, the closest pair lit, its gap marked
    s0, s1 = ph.scan
    sx0, sx1 = 6 * U, (W // 2 + 30) * U
    body.append(f'<g class="sc"><rect x="{sx0 - 36 * U}" y="0" width="{36 * U}" height="{H * U}" class="scb"/>'
                f'<path d="M{sx0} 0V{H * U}" class="scl"/></g>')
    css.append(f".scb{{fill:var(--scan);opacity:.12}}.scl{{stroke:var(--scan);stroke-width:{2 * U}}}.sc{{opacity:0}}")
    tl.add(".sc", [(0, 0), (s0, 0), (s1 - 0.2, sx1 - sx0), (P, sx1 - sx0)],
           lambda v: f"transform:translateX({n_(v, 0)}px)", "ease-in-out")
    tl.opacity(".sc", [(0, 0), (s0, 0), (s0 + 0.12, 1), (s1 - 0.35, 1), (s1 - 0.15, 0)])
    if highlight:
        body.append('<g class="hl">' + "".join(f'<path d="{d_}"/>' for d_ in highlight) + "</g>")
        css.append(f".hl{{fill:none;stroke:var(--accent);stroke-width:{1.6 * U};stroke-linejoin:round;opacity:0}}")
        tl.opacity(".hl", [(0, 0), (s0 + 0.45, 0), (s0 + 0.65, 1), (ph.fea[0] + 0.5, 1), (ph.fea[0] + 0.8, 0),
                           (P, 0)])
    if closest.get("drawn"):
        # the gap itself, between its witness points, when the stride passes the pose where it is smallest
        (ax_, ay_), (bx_, by_) = closest["drawn"]
        mx, my = (ax_ + bx_) / 2, (ay_ + by_) / 2
        lx, ly = mx + 40 * U, my - 34 * U
        body.append(f'<g class="cl"><path d="M{n_(ax_, 0)} {n_(ay_, 0)}L{n_(bx_, 0)} {n_(by_, 0)}" class="gap"/>'
                    f'<path d="M{n_(mx, 0)} {n_(my, 0)}L{n_(lx - 3 * U, 0)} {n_(ly + 5 * U, 0)}"/>'
                    f'<text x="{n_(lx, 0)}" y="{n_(ly, 0)}">{_fmt(closest["gap_mm"])} mm</text></g>')
        css.append(f".cl{{opacity:0}}.cl path{{fill:none;stroke:var(--accent);stroke-width:{1.5 * U};"
                   f"stroke-linecap:round}}.cl .gap{{stroke-width:{3 * U}}}"
                   f".cl text{{font-size:{14 * U}px;font-weight:700;fill:var(--accent);paint-order:stroke;"
                   f"stroke:var(--bg);stroke-width:{4 * U}px}}")
        n_poses = len(scene["linkage"]["trace"]) - 1
        tc = m0 + (m1 - m0) * closest["pose"] / n_poses
        tl.opacity(".cl", [(0, 0), (tc - 0.3, 0), (tc - 0.1, 1), (tc + 0.6, 1), (tc + 0.8, 0), (P, 0)])

    # ---- the wheel's path, drawn as it is travelled
    trace = scene["linkage"]["trace"]
    tb = S.PathBuilder()
    tb.polyline([tuple(p) for p in trace])
    run = [0.0]
    for p, q in zip(trace, trace[1:]):
        run.append(run[-1] + math.dist(p, q))
    total = run[-1]
    body.append(f'<path class="tr" d="{tb.d()}"/>')
    css.append(f".tr{{fill:none;stroke:var(--trace);stroke-width:{1.5 * U};stroke-linecap:round;"
               f"stroke-dasharray:{n_(total, 0)} {n_(total, 0)}}}")
    n = len(trace) - 1
    tl.add(".tr", [(0, total), (m0, total)] + [(m0 + (m1 - m0) * i / n, total - run[i]) for i in range(n + 1)]
           + [(P, 0)], lambda v: f"stroke-dashoffset:{n_(v, 1)}", "linear")
    tl.opacity(".tr", [(0, 0), (m0, 0), (m0 + 0.2, 1), (ph.fade[0], 1), (ph.fade[1], 0)])
    body.append("</g>")

    # ---- the right column: a caption per phase, the checks, then the wordmark and tagline
    col = present.get("column_px", W // 2 + 54) * U
    words = scene["text"]
    spans = {"draw": (0.3, ph.assemble[0]), "assemble": (ph.assemble[0] + 0.25, ph.scan[0]),
             "checks": (ph.scan[0] + 0.25, ph.words[0] - 0.25)}
    for i, (key, cap) in enumerate(present.get("captions", {}).items()):
        t_on, t_off = spans[key]
        body.append(f'<text x="{col}" y="{98 * U}" class="cap w c{i}">{S.attr(cap)}</text>')
        tl.opacity(f".c{i}", [(0, 0), (t_on, 0), (t_on + 0.25, 1), (t_off, 1), (t_off + 0.25, 0), (P, 0)])
    css.append(f".cap{{font-size:{15 * U}px;fill:var(--muted);opacity:0}}")
    rows = _check_rows(scene)
    y0 = present.get("rows_y_px", 186) * U
    narrow = []
    for i, (label, detail, t_on, ok) in enumerate(rows):
        yy = y0 + i * 54 * U
        rx, ry = col + 11 * U, yy - 6 * U
        # a tick on green when the check passed, a cross on the accent colour when it did not
        mark = (f"M{rx - 6 * U} {ry}l{4 * U} {4 * U} {8 * U} {-9 * U}" if ok else
                f"M{rx - 5 * U} {ry - 5 * U}l{10 * U} {10 * U}m0 {-10 * U}l{-10 * U} {10 * U}")
        body.append(f'<g class="r r{i}"><circle class="ring{"" if ok else " bad"}" cx="{rx}" cy="{ry}" r="{11 * U}"/>'
                    f'<path class="tick t{i}" d="{mark}"/>'
                    f'<text x="{col + 32 * U}" y="{yy}" class="rl">{S.attr(label)}</text>'
                    f'<text x="{col + 32 * U}" y="{yy + 21 * U}" class="rd w">{S.attr(detail)}</text></g>')
        tl.opacity(f".r{i}", [(0, 0.28), (t_on - 0.9, 0.28), (t_on - 0.7, 1), (ph.fade[0], 1), (ph.fade[1], 0.28)])
        tl.opacity(f".t{i}", [(0, 0), (t_on, 0), (t_on + 0.2, 1), (ph.fade[0], 1), (ph.fade[1], 0)])
        narrow.append(f".r{i}{{transform-origin:{rx}px {ry}px}}")
    css.append(f".ring{{fill:var(--good)}}.ring.bad{{fill:var(--accent)}}.tick{{fill:none;stroke:var(--bg);stroke-width:{3 * U};"
               f"stroke-linecap:round;stroke-linejoin:round}}.rl{{font-size:{17 * U}px;font-weight:700;fill:var(--ink)}}"
               f".rd{{font-size:{13 * U}px;fill:var(--muted)}}.r{{transform-box:view-box}}")
    if fea:
        k_row = [r[0] for r in rows].index("strength")
        lx0, ly0 = col + 128 * U, y0 + k_row * 54 * U - 16 * U
        sw = 14 * U
        ramp = "".join(f'<rect x="{lx0 + j * sw}" y="{ly0}" width="{sw}" height="{9 * U}" fill="{STRESS[j]}"/>'
                       for j in range(len(fea["band_edges"])))
        body.append(f'<g class="lg w">{ramp}<text x="{lx0 + len(fea["band_edges"]) * sw + 6 * U}" y="{ly0 + 9 * U}" '
                    f'class="lgt">0–{_fmt(fea["band_edges"][-1])}+ of strength</text></g>')
        css.append(f".lgt{{font-size:{11 * U}px;fill:var(--muted)}}")
        tl.opacity(".lg", [(0, 0), (ph.fea[0], 0), (ph.fea[0] + 0.3, 1), (ph.fade[0], 1), (ph.fade[1], 0)])
    wm, tg = words["wordmark"], words.get("tagline")
    group = f'<path transform="translate({col} {98 * U})" class="wmp" d="{wm["d"]}"/>'
    if tg:
        group += f'<path transform="translate({col + 2 * U} {130 * U})" class="tgp w" d="{tg["d"]}"/>'
    body.append(f'<g class="wm">{group}</g>')
    css.append(".wmp{fill:var(--ink)}.tgp{fill:var(--muted)}")
    w0, w1 = ph.words
    tl.add(".wm", [(0, 0), (w0, 0), (w1, 1), (ph.fade[0], 1), (ph.fade[1], 0), (P, 0)],
           lambda v: f"opacity:{n_(v, 2)};transform:translateY({n_((1 - v) * 14 * U, 0)}px)", "ease-out")
    src = scene["source"]
    credit = present.get("credit") or f'{src["name"]} · {src["repo"].replace("https://github.com/", "")} · {src["licence"]}'
    body.append(f'<text x="{(W - 16) * U}" y="{(H - 14) * U}" class="cr w">{S.attr(credit)}</text>')
    css.append(f".cr{{font-size:{11 * U}px;fill:var(--muted);text-anchor:end}}")
    # narrow (a phone): only the drawing, the wordmark and the check names, larger
    css.append("@media (max-width:520px){.w{visibility:hidden}" + "".join(narrow).replace("}", ";transform:scale(1.8)}")
               + "}")
    return S.document(W, H, present["label"], present["description"], "".join(css) + tl.stylesheet(), body, theme)


def _check_rows(scene: Mapping[str, Any]) -> List[Tuple[str, str, float, bool]]:
    """(name, result, when it is marked, passed) for each check the scene carries."""
    ph = Phases
    rows = []
    c = scene.get("clearance")
    if c:
        clash = len(c.get("clashes", []))
        w = c.get("closest") or {}
        rows.append(("fit", (f"{clash} clashes" if clash else "no clash") + f" in {c['poses']} poses · passing parts "
                     f"≥ {_fmt(w.get('gap_mm', 0))} mm apart", ph.scan[1], not clash))
    f = scene.get("fea")
    if f:
        ok = f["first_failure_factor"] is None or f["first_failure_factor"] > 1.0
        rows.append(("strength", f"FEA {f['part'].replace('_', ' ')}: {_fmt(f['design_mpa'])} MPa, "
                     f"fails at {_fmt(f['first_failure_factor'], 2)}× load", ph.fea[1], ok))
    lk = scene["linkage"]
    margin = min(lk["dead_point_margin_deg"])
    rows.append(("motion", f"five-bar stride · knees ≥ {_fmt(margin, 0)}° from a dead point", ph.motion[1],
                 margin > 0))
    return rows
