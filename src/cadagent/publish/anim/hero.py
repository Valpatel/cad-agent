"""An assembly hero: a real assembly's CAD edges draw in exploded, the parts slide together, a check pass runs
(clearance, FEA stress, the linkage's motion) and the figure settles on a wordmark and tagline.

Two stages, so the committed SVG can be checked anywhere:

* ``extract(spec, source)`` needs CadQuery and a checkout of the project the spec names. It reads the assembly STEP,
  draws every solid's visible edges by hidden-line removal (``cad.hlr_segments``) and its filled silhouette,
  orders the solids for painting, solves the linkage along its path (``linkage``), measures clearances between
  moving solids with the assembly gates' relation engine (``cadagent.gates.relations.relate``), bands the FEA field
  (``field``) and writes a scene: plain JSON with the drawing in SVG units, the numbers and where they came from
  (the source commit and every input file's sha256).
* ``render(scene)`` is plain Python. It writes the SVG, with CSS keyframes and both colour schemes. The same scene
  always gives the same bytes.

What the drawing approximates, stated in the scene and its caption:

* Each solid hides only its own edges. Solids hide each other by painting filled silhouettes back to front, an
  order taken from a depth raster of the assembled and the exploded states. A pair whose order flips inside one
  state (interlocking parts) is painted by its majority order.
* The linkage moves each body as one 2D transform of its drawing: an exact rotation in the linkage's plane, at a
  depth chosen as the mean depth of the body's visible surface. Geometry nearer or farther than that depth is off
  by up to ``motion_error_px`` at the pose farthest from the reference (the scene records it). The hidden lines
  stay those of the reference pose.
* Clearance is checked at the sampled poses only. A pair of solids whose extents along the joint axes do not
  overlap can never meet while every joint turns about that axis. Such pairs are counted, not queried.
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


def extract(spec: Mapping[str, Any], source: Path, *, clearance: bool = True, log=print) -> Dict[str, Any]:
    """The scene for ``spec`` from the project checkout at ``source``. See the module docstring."""
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

    # ---- layout: fit every state (assembled, exploded, every pose) into the stage
    stage = spec["stage"]
    pts_all = []
    for p in parts:
        xy = geo[p["solid"]]["xy"]
        pts_all += [xy, xy + explode_vec[p["solid"]]]
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
    log(f"scale {k / U:.3f} px/mm")

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
    votes: Dict[Tuple[int, int], int] = {}
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
                votes[(ids[a], ids[b])] = votes.get((ids[a], ids[b]), 0) + a_front - b_front
    min_cells = int(spec.get("min_visible_cells", 6))
    drawn = [i for i in ids if visible[i] >= min_cells]
    hidden = [i for i in ids if visible[i] < min_cells]
    # painter's order: b before a when a is in front where they overlap; ties by mean depth
    behind = {i: set() for i in drawn}
    for (a, b), v in votes.items():
        if a in behind and b in behind and v:
            (behind[a].add(b) if v > 0 else behind[b].add(a))
    meanz = {i: float(geo[i]["z"].mean()) for i in drawn}
    order, done, cycles = [], set(), 0
    while len(order) < len(drawn):
        ready = [i for i in drawn if i not in done and behind[i] <= done]
        if not ready:                                     # a cycle: paint the one with fewest unpainted behind it
            cycles += 1
            ready = [min((i for i in drawn if i not in done), key=lambda i: (len(behind[i] - done), meanz[i]))]
        nxt = min(ready, key=lambda i: (meanz[i], i))
        order.append(nxt)
        done.add(nxt)

    # refine each solid's depth: the mean, along the joint axis, of its vertices seen in the assembled state
    asm = zb["assembled"]
    stack = np.stack([asm[i] for i in ids])
    front_id = np.array(ids)[np.argmax(stack, axis=0)]
    front_z = stack.max(axis=0)
    seen_v: Dict[int, np.ndarray] = {}
    for p in parts:
        g = geo[p["solid"]]
        q = np.round(to_units(g["xy"])).astype(int)
        ok = (q[:, 0] >= 0) & (q[:, 1] >= 0) & (q[:, 0] < W) & (q[:, 1] < H)
        seen = np.zeros(len(q), bool)
        seen[ok] = (front_id[q[ok, 1], q[ok, 0]] == p["solid"]) & (g["z"][ok] >= front_z[q[ok, 1], q[ok, 0]] - 1.0)
        seen_v[p["solid"]] = g["v"][seen]
        if seen.sum() >= 3:
            solid_depth[p["solid"]] = float(g["v"][seen][:, iaxis].mean())
    # how far the drawn motion is from the exact 3D one, over each moving solid's visible vertices, at every pose
    motion_err, worst = 0.0, None
    for p in parts:
        if p["body"] == "ground" or not len(seen_v[p["solid"]]):
            continue
        v = seen_v[p["solid"]]
        xy = view.project(v)[0]
        for pose in poses:
            turn, r0, p0 = link.body_motion(p["body"], pose)
            c, s_ = math.cos(turn), math.sin(turn)
            w = v.copy()
            du, dv = v[:, iu] - r0[0], v[:, iv] - r0[1]
            w[:, iu], w[:, iv] = p0[0] + c * du - s_ * dv, p0[1] + s_ * du + c * dv
            exact = view.project(w)[0]
            A = motion2d(p["body"], pose, solid_depth[p["solid"]])
            e = float(np.abs(exact - (xy @ A[:2, :2].T + A[:2, 2])).max()) * k / U
            if e > motion_err:
                motion_err, worst = e, p["part"]
    log(f"painter's order: {len(order)} solids drawn, {len(hidden)} never visible, {cycles} cycles broken; "
        f"motion error up to {motion_err:.2f} px ({worst})")

    # ---- the drawing: per solid, its silhouette and its edges, in units
    out_solids = []
    for i in order:
        p = next(q for q in parts if q["solid"] == i)
        loops = raster.region(np.isfinite(asm[i]), grid, float(spec.get("outline_tol", 0.6)), min_area=2.0)
        segs = cad.transform_segments(geo[i]["seg"], k, tuple(off))
        out_solids.append({"solid": i, "part": p["part"], "body": p["body"], "style": p["style"],
                           "explode": [_r(c, 1) for c in explode_vec[i] * k],
                           "shift": [_r(c, 2) for c in a_axis * solid_depth[i] * k], "depth_mm": _r(solid_depth[i], 1),
                           "fill": S.polygon_d(loops), "edges": S.segments_d(segs)})

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
        clear_out = _clearances(spec, solids, parts, link, poses, iaxis, iu, iv, log)
        w = clear_out.get("closest")
        if w:
            pose = poses[w["pose"]]
            pts = []
            for key, pa in (("a", w["point_a"]), ("b", w["point_b"])):
                body = next(p["body"] for p in parts if p["solid"] == w[key])
                q = np.array(pa, float)
                # carry the witness back to the reference pose of its body, where it is drawn
                if body != "ground":
                    turn, r0, p0 = link.body_motion(body, pose)
                    c, s_ = math.cos(-turn), math.sin(-turn)
                    du, dv = q[iu] - p0[0], q[iv] - p0[1]
                    q[iu], q[iv] = r0[0] + c * du - s_ * dv, r0[1] + s_ * du + c * dv
                pts.append([_r(c, 1) for c in to_units(view.project([q])[0][0])])
            w["drawn"] = pts

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
        o = outline(t["text"], font, t["size"] * U, t.get("tracking", 0.0))
        texts[key] = {"text": t["text"], "d": S.polygon_d(o["loops"]), "width": _r(o["width"], 1),
                      "size": t["size"], "font": font.name}

    lin = M2
    scene = {
        "schema": SCHEMA,
        "name": spec["name"],
        "source": {"repo": spec["source"]["repo"], "name": spec["source"]["name"], "licence": spec["source"]["licence"],
                   "commit": _git_head(source), "inputs": dict(sorted(inputs.items()))},
        "width": spec["width"], "height": spec["height"], "units_per_px": U, "px_per_mm": _r(k / U, 4),
        "view": {"direction": list(spec["view"]["direction"]), "up": list(spec["view"].get("up", (0, 0, 1)))},
        "plane_matrix": [_r(lin[0, 0], 6), _r(lin[1, 0], 6), _r(lin[0, 1], 6), _r(lin[1, 1], 6)],
        "solids": out_solids, "hidden_solids": sorted(hidden), "painter_cycles": cycles,
        "linkage": {"lengths_mm": lengths, "samples": samples, "path": path_spec, "dead_point_margin_deg": [_r(d, 1) for d in dead],
                    "bodies": frames, "trace": trace, "trace_depth_mm": _r(trace_depth, 1),
                    "motion_error_px": _r(motion_err, 2), "motion_error_part": worst,
                    "reach_mm": [_r(min(math.dist(p[driven], (0, 0)) for p in poses), 1),
                                 _r(max(math.dist(p[driven], (0, 0)) for p in poses), 1)]},
        "fea": fea_out, "clearance": clear_out, "text": texts,
        "extract_seconds": None,
    }
    scene["extract_seconds"] = _r(time.time() - t_start, 1)
    return scene


def _clearances(spec, solids, parts, link, poses, iaxis, iu, iv, log) -> Dict[str, Any]:
    """The closest approach between solids that move relative to each other, over the sampled poses, by the
    relation engine. Pairs whose extents along the joint axis do not overlap are counted as separated."""
    from cadagent.gates.relations import Tolerances, relate
    from cadagent.publish.anim import cad

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

    def place(i, pose):
        body = named[i]["body"]
        if body == "ground":
            return solids[i]
        turn, r0, p0 = link.body_motion(body, pose)
        c, s_ = math.cos(turn), math.sin(turn)
        m = np.eye(3)
        R = np.eye(3)
        R[iu, iu], R[iu, iv], R[iv, iu], R[iv, iv] = c, -s_, s_, c
        r0w, p0w = np.zeros(3), np.zeros(3)
        r0w[iu], r0w[iv], p0w[iu], p0w[iv] = r0[0], r0[1], p0[0], p0[1]
        t = p0w - R @ r0w
        m = [*R[0], t[0], *R[1], t[1], *R[2], t[2]]
        return cad.moved(solids[i], m)

    tol = Tolerances()
    checked, queried, clashes, closest = 0, 0, [], None
    t0 = time.time()
    for n, pose in enumerate(poses[:-1]):                 # the last pose repeats the first
        if n % every:
            continue
        checked += 1
        placed = {}
        for a, b in pairs:
            if named[a]["body"] == "ground" and named[b]["body"] == "ground":
                continue
            pa = placed.setdefault(a, place(a, pose))
            pb = placed.setdefault(b, place(b, pose))
            ba, bb_ = pa.BoundingBox(), pb.BoundingBox()
            gapbox = max(ba.xmin - bb_.xmax, bb_.xmin - ba.xmax, ba.ymin - bb_.ymax, bb_.ymin - ba.ymax,
                         ba.zmin - bb_.zmax, bb_.zmin - ba.zmax, 0.0)
            if gapbox > near:
                continue
            queried += 1
            r = relate(pa, pb, tol, names=(named[a]["part"], named[b]["part"]), contact_area=False)
            if r.state == "unknown":
                raise RuntimeError(f"relation unknown for {named[a]['part']} / {named[b]['part']}: {r.error}")
            if r.interferes:
                clashes.append({"pose": n, "a": named[a]["part"], "b": named[b]["part"], "overlap_mm3": r.overlap_mm3})
            elif closest is None or r.gap_mm < closest["gap_mm"]:
                closest = {"pose": n, "a": a, "b": b, "part_a": named[a]["part"], "part_b": named[b]["part"],
                           "gap_mm": r.gap_mm, "point_a": r.witness.get("point_a"), "point_b": r.witness.get("point_b")}
        log(f"  clearance pose {n}: {queried} queries so far, {time.time() - t0:.0f} s")
    return {"poses": checked, "pairs_queried": queried, "pairs_separated_along_axis": separated,
            "pairs_in_reach": len(pairs), "clashes": clashes, "closest": closest,
            "near_mm": near, "seconds": _r(time.time() - t0, 1),
            "limits": "sampled poses only (not a swept volume); exact gaps by cadagent.gates.relations.relate"}


def read_spec(path: Path) -> Dict[str, Any]:
    import yaml
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def write_scene(scene: Mapping[str, Any], path: Path) -> None:
    Path(path).write_text(json.dumps(scene, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------------- render

# style -> fill colour variable; every style's edges use --edge
FILLS = {"frame": "fill", "link": "linkf", "metal": "metal", "dark": "dark", "tyre": "dark", "hub": "metal",
         "stop": "stop", "plain": "fill"}
HERO_COLOURS = {
    # light, dark
    "linkf": ("#fbe6b8", "#4a3a17"), "stop": ("#e9a48a", "#7a3422"), "scan": ("#2f7d5b", "#5cc8a0"),
    "b0": ("#eef3df", "#22312b"), "b1": ("#d9ebb6", "#2f4a2e"), "b2": ("#f6e27a", "#6b6a1e"), "b3": ("#f7b74a", "#9a6614"),
    "b4": ("#ef7d36", "#c45a1c"), "b5": ("#d4471f", "#e0552a"), "b6": ("#9e2312", "#ff6a3d"),
}


class Phases:
    """The loop's timeline in seconds."""
    period = 10.5
    draw = (0.2, 2.2)            # edges draw in (each solid takes ``stroke``); fills follow
    stroke = 0.9
    fills = (1.3, 2.3)
    assemble = (2.3, 3.3)
    scan = (3.4, 4.4)            # clearance
    fea = (4.4, 5.7)
    motion = (5.8, 8.2)
    words = (8.0, 8.6)
    fade = (10.1, 10.5)          # everything out, before the loop restarts


def _fmt(v: float, d: int = 1) -> str:
    return f"{v:.{d}f}"


def render(scene: Mapping[str, Any]) -> str:
    """The SVG for a hero scene. Deterministic: the same scene gives the same bytes."""
    if scene.get("schema") != SCHEMA:
        raise ValueError(f"not a {SCHEMA} scene")
    U = scene["units_per_px"]
    W, H = scene["width"], scene["height"]
    ph = Phases
    tl = S.Timeline(ph.period)
    css: List[str] = []
    body: List[str] = []
    light = dict(S.THEME.light, **{k: v[0] for k, v in HERO_COLOURS.items()})
    dark = dict(S.THEME.dark, **{k: v[1] for k, v in HERO_COLOURS.items()})
    theme = S.Theme(light, dark)

    # every element of the drawing fades out at the loop's end and in at its start
    css.append(".e{fill:none;stroke:var(--edge);stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round;"
               "stroke-dasharray:1 1}")
    for style, var in FILLS.items():
        css.append(f".s{style[:2]}{{fill:var(--{var})}}")
    css.append(".m{transform-box:view-box;transform-origin:0 0}")

    # ---- the drawing, in painter's order
    solids = scene["solids"]
    bodies = scene["linkage"]["bodies"]
    a, b_, c, d = scene["plane_matrix"]
    det = a * d - b_ * c
    inv = (d / det, -b_ / det, -c / det, a / det)
    mat = lambda m: "matrix(" + ",".join(S.num(v, 5) for v in m) + ",0,0)"
    for name, bd in bodies.items():
        px, py = bd["pivot"]
        cls = "k" + name.replace("_", "")[:6]
        start, end = ph.motion
        n = len(bd["frames"]) - 1
        frames = [(0, bd["frames"][0])]
        for i, f in enumerate(bd["frames"]):
            frames.append((start + (end - start) * i / n, f))
        frames.append((ph.period, bd["frames"][0]))

        def tf(f, px=px, py=py):
            return (f"transform:translate({S.num(px + f[0], 2)}px,{S.num(py + f[1], 2)}px) {mat((a, b_, c, d))} "
                    f"rotate({S.num(f[2], 3)}deg) {mat(inv)} translate({S.num(-px, 2)}px,{S.num(-py, 2)}px)")
        css.append(f".{cls}{{{tf(bd['frames'][0])[len('transform:'):] and tf(bd['frames'][0])}}}")
        tl.add(f".{cls}", frames, tf, "linear")

    explode_classes: Dict[Tuple[float, float], str] = {}
    order_rank = sorted({s_["explode"][0] ** 2 + s_["explode"][1] ** 2 for s_ in solids})
    for s_ in solids:
        key = tuple(s_["explode"])
        if key not in explode_classes:
            name = f"x{len(explode_classes)}"
            explode_classes[key] = name
            ex, ey = key
            a0, a1 = ph.assemble
            frac = order_rank.index(ex * ex + ey * ey) / max(1, len(order_rank) - 1)
            t_go = a0 + 0.35 * (a1 - a0) * frac
            t_in = min(a1, t_go + 0.65 * (a1 - a0))
            tr = lambda v, ex=ex, ey=ey: f"transform:translate({S.num(ex * v, 1)}px,{S.num(ey * v, 1)}px)"
            tl.add(f".{name}", [(0, 1), (t_go, 1), (t_in, 0), (ph.period, 0)], tr, "ease-in-out")
    body.append('<g class="draw">')
    fea = scene.get("fea")
    for n, s_ in enumerate(solids):
        sx, sy = s_["shift"]
        mv = s_["body"] != "ground"
        open_ = ""
        close = ""
        if mv:
            k_ = "k" + s_["body"].replace("_", "")[:6]
            open_ += (f'<g transform="translate({S.num(sx, 1)} {S.num(sy, 1)})"><g class="m {k_}">'
                      f'<g transform="translate({S.num(-sx, 1)} {S.num(-sy, 1)})">')
            close = "</g></g></g>" + close
        open_ += f'<g class="m {explode_classes[tuple(s_["explode"])]}">'
        close = "</g>" + close
        inner = f'<path class="f s{s_["style"][:2]}" fill-rule="evenodd" d="{s_["fill"]}"/>'
        if fea and s_["solid"] == fea["solid"]:
            for band in fea["bands"]:
                inner += f'<path class="fb fb{band["band"]}" style="fill:var(--b{band["band"]})" d="{band["d"]}"/>'
        inner += f'<path class="e d{n}" pathLength="1" d="{s_["edges"]}"/>'
        body.append(open_ + inner + close)
        # draw-in: edges by explode distance (inner layers first)
        t0 = ph.draw[0] + (ph.draw[1] - ph.stroke - ph.draw[0]) * n / max(1, len(solids) - 1)
        tl.add(f".d{n}", [(0, 1), (t0, 1), (t0 + ph.stroke, 0), (ph.period, 0)],
               lambda v: f"stroke-dashoffset:{S.num(v, 2)}", "ease-out")
    body.append("</g>")
    tl.opacity(".f", [(0, 0), (ph.fills[0], 0), (ph.fills[1], 1), (ph.period, 1)])
    tl.opacity(".draw", [(0, 1), (ph.fade[0], 1), (ph.fade[1], 0)])
    if fea:
        f0, f1 = ph.fea
        nb = len(fea["bands"])
        for i, band in enumerate(fea["bands"]):
            on = f0 + (f1 - f0 - 0.3) * i / max(1, nb - 1)
            tl.opacity(f".fb{band['band']}", [(0, 0), (on, 0), (on + 0.3, 1), (ph.period, 1)])

    # ---- the wheel's path, drawn as it is travelled
    trace = scene["linkage"]["trace"]
    tb = S.PathBuilder()
    tb.polyline([tuple(p) for p in trace])
    lengths = [0.0]
    for p, q in zip(trace, trace[1:]):
        lengths.append(lengths[-1] + math.dist(p, q))
    total = lengths[-1]
    body.append(f'<path class="tr" d="{tb.d()}"/>')
    css.append(".tr{fill:none;stroke:var(--trace);stroke-width:3;stroke-linecap:round;"
               f"stroke-dasharray:{S.num(total, 0)} {S.num(total, 0)};stroke-dashoffset:0}}")
    m0, m1 = ph.motion
    n = len(trace) - 1
    tr_frames = [(0, total), (m0, total)] + [(m0 + (m1 - m0) * i / n, total - lengths[i]) for i in range(n + 1)] + \
        [(ph.fade[0], 0), (ph.period, 0)]
    tl.add(".tr", tr_frames, lambda v: f"stroke-dashoffset:{S.num(v, 1)}", "linear")
    tl.opacity(".tr", [(0, 0), (m0, 0), (m0 + 0.2, 1), (ph.fade[0], 1), (ph.fade[1], 0)])

    # ---- the clearance check: a scan across the drawing, then the closest gap
    clear = scene.get("clearance") or {}
    s0, s1 = ph.scan
    x0, x1 = 10 * U, (scene["width"] // 2 + 20) * U
    body.append(f'<path class="sc" d="M{x0} {6 * U}V{(H - 6) * U}"/>')
    css.append(".sc{stroke:var(--scan);stroke-width:3;opacity:0}")
    tl.add(".sc", [(0, 0), (s0, 0), (s1 - 0.25, x1 - x0), (ph.period, x1 - x0)],
           lambda v: f"transform:translateX({S.num(v, 0)}px)", "ease-in-out")
    tl.opacity(".sc", [(0, 0), (s0, 0), (s0 + 0.15, 0.9), (s1 - 0.35, 0.9), (s1 - 0.2, 0)])
    w = clear.get("closest")
    if w and w.get("drawn"):
        (ax_, ay_), (bx_, by_) = w["drawn"]
        mx, my = (ax_ + bx_) / 2, (ay_ + by_) / 2
        lx, ly = mx - 70 * U, my - 46 * U
        body.append(f'<g class="cl"><path class="cll" d="M{S.num(mx, 0)} {S.num(my, 0)}L{S.num(lx + 4 * U, 0)} '
                    f'{S.num(ly + 4 * U, 0)}"/><circle cx="{S.num(mx, 0)}" cy="{S.num(my, 0)}" r="{5 * U}"/>'
                    f'<text x="{S.num(lx, 0)}" y="{S.num(ly, 0)}" class="lab">{_fmt(w["gap_mm"])} mm</text></g>')
        css.append(".cl circle{fill:none;stroke:var(--accent);stroke-width:3}.cll{stroke:var(--accent);stroke-width:2}"
                   f".lab{{font-size:{13 * U}px;font-weight:700;fill:var(--accent);text-anchor:end;"
                   "paint-order:stroke;stroke:var(--bg);stroke-width:6px}")
        tl.opacity(".cl", [(0, 0), (s1 - 0.5, 0), (s1 - 0.3, 1), (ph.fea[0] + 0.6, 1), (ph.fea[0] + 0.9, 0), (ph.period, 0)])

    # ---- the right column: checks, then the wordmark
    col = (W // 2 + 50) * U
    rows = _check_rows(scene)
    y = 178 * U
    for i, (label, detail, t_on) in enumerate(rows):
        yy = y + i * 52 * U
        body.append(f'<g class="r{i}"><circle class="ring" cx="{col + 11 * U}" cy="{yy - 5 * U}" r="{11 * U}"/>'
                    f'<path class="tick" d="M{col + 5 * U} {yy - 5 * U}l{4 * U} {4 * U} {8 * U} {-9 * U}"/>'
                    f'<text x="{col + 32 * U}" y="{yy}" class="rl">{S.attr(label)}</text>'
                    f'<text x="{col + 32 * U}" y="{yy + 20 * U}" class="rd w">{S.attr(detail)}</text></g>')
        tl.opacity(f".r{i}", [(0, 0.25), (t_on - 0.9, 0.25), (t_on - 0.6, 1), (ph.fade[0], 1), (ph.fade[1], 0.25)])
        tl.opacity(f".r{i} .tick", [(0, 0), (t_on, 0), (t_on + 0.2, 1), (ph.fade[0], 1), (ph.fade[1], 0)])
    css.append(f".ring{{fill:var(--good)}}.tick{{fill:none;stroke:var(--bg);stroke-width:{3 * U};stroke-linecap:round;"
               f"stroke-linejoin:round}}.rl{{font-size:{17 * U}px;font-weight:700;fill:var(--ink)}}"
               f".rd{{font-size:{13 * U}px;fill:var(--muted)}}")
    wm = scene["text"]["wordmark"]
    body.append(f'<g class="wm"><path transform="translate({col} {96 * U})" style="fill:var(--ink)" d="{wm["d"]}"/>'
                f'<text x="{col}" y="{126 * U}" class="tg">{S.attr(scene.get("tagline", ""))}</text></g>')
    css.append(f".tg{{font-size:{15 * U}px;fill:var(--muted)}}")
    w0, w1 = ph.words
    tl.add(".wm", [(0, 0), (w0, 0), (w1, 1), (ph.fade[0], 1), (ph.fade[1], 0)],
           lambda v: f"opacity:{S.num(v, 2)};transform:translateY({S.num((1 - v) * 12 * U, 0)}px)", "ease-out")
    cap = scene.get("caption", "")
    body.append(f'<text x="{col}" y="{96 * U}" class="cap w">{S.attr(cap)}</text>')
    css.append(f".cap{{font-size:{14 * U}px;fill:var(--muted);opacity:0}}")
    tl.opacity(".cap", [(0, 0), (0.3, 0), (0.6, 1), (w0, 1), (w0 + 0.3, 0)])
    credit = f'{scene["source"]["name"]} · {scene["source"]["repo"].replace("https://github.com/", "")} ({scene["source"]["licence"]})'
    body.append(f'<text x="{(W - 16) * U}" y="{(H - 14) * U}" class="cr w">{S.attr(credit)}</text>')
    css.append(f".cr{{font-size:{11 * U}px;fill:var(--muted);text-anchor:end}}")

    css.append(f"@media (max-width:520px){{.w{{visibility:hidden}}.rl{{font-size:{30 * U}px}}}}")
    label = scene.get("label") or "cad-agent"
    desc = scene.get("description", "")
    return S.document(W, H, label, desc, "".join(css) + tl.stylesheet(), body, theme)


def _check_rows(scene: Mapping[str, Any]) -> List[Tuple[str, str, float]]:
    ph = Phases
    rows = []
    c = scene.get("clearance") or {}
    if c:
        clash = len(c.get("clashes", []))
        w = c.get("closest") or {}
        rows.append(("fit", (f"{clash} clashes" if clash else "no clash") + f" in {c['poses']} poses · closest "
                     f"{_fmt(w.get('gap_mm', 0))} mm", ph.scan[1]))
    else:
        rows.append(("fit", "clearance not extracted", ph.scan[1]))
    f = scene.get("fea")
    if f:
        rows.append(("strength", f"FEA {f['part'].replace('_', ' ')}: {_fmt(f['design_mpa'])} MPa, "
                     f"fails at {_fmt(f['first_failure_factor'], 2)}× load", ph.fea[1]))
    lk = scene["linkage"]
    rows.append(("motion", f"five-bar stride · knees ≥ {_fmt(min(lk['dead_point_margin_deg']), 0)}° from dead point",
                 ph.motion[1]))
    return rows
