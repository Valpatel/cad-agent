"""A mesh-convergence study at an inside corner, recorded from a real run of ``cadagent.simulation.fea`` and animated:
the mesh round the corner gets finer step by step, and the design peak's number and the convergence chart follow it.
A sharp corner's peak keeps rising; a filleted one settles.

Two stages, as for the hero, so the committed SVG can be checked anywhere:

* ``record(spec, root)`` needs CadQuery, gmsh and scikit-fem. It builds the spec's L-bracket twice, with a sharp and
  with a filleted inside corner. Each one is meshed and solved at a series of element sizes at the corner:
  - with ``Study(refine=...)``, a ball at the corner inside one coarse mesh;
  - with the whole part meshed at that size, no ``refine``.
  Each step records what the result says: the tets, the design peak and where it is, the peak's resolution flags
  (``result['mesh']['peak']``) and ``converge()``'s verdict. A refined step also records the front face's mesh round
  the corner, to draw. The run records the mesher (``result['mesh']['mesher']``), the toolkit's version and commit,
  and the sha256 of the files that made it. It writes plain JSON.
* ``render(scene, present)`` is plain Python. It writes the SVG, with CSS keyframes and both colour schemes, from the
  scene and the spec's ``present`` words. The same inputs always give the same bytes.

The figure shows one recorded run on one mesher build. Another gmsh build can mesh the bracket differently (see
``result['mesh']['mesher']``), and a linear-elastic study, converged or not, does not prove that a part holds.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from cadagent.publish.anim import svg as S

SCHEMA = "cadagent.anim.convergence/1"
# the files whose sha256 a scene records: the study code, this module and the spec (added by record())
CODE = ("src/cadagent/simulation/fea.py", "src/cadagent/publish/anim/convergence.py")


# ----------------------------------------------------------------------------------------------------- the study

def williams_lambda(angle_deg: float = 270.0) -> float:
    """Williams' (1952) mode I eigenvalue for a re-entrant corner of ``angle_deg`` of material: the root of
    sin(λα) = -λ sin(α) in (0.5, 1), with α the angle in radians. Stress near the corner grows as r^(λ-1). For 270°
    (an L-bracket's inside corner), sin(3πλ/2) = λ and λ = 0.5445."""
    a = math.radians(angle_deg)
    f = lambda lam: math.sin(lam * a) + lam * math.sin(a)
    lo, hi = 0.5, 0.99
    if f(lo) * f(hi) > 0:
        raise ValueError(f"no mode I root in (0.5, 1) for a {angle_deg:g}° corner")
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(lo) * f(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def bracket(part: Mapping[str, Any], fillet_mm: float = 0.0):
    """An L-bracket in the XZ plane, extruded along +Y: legs ``leg_mm`` long and ``thickness_mm`` thick,
    ``width_mm`` wide, its inside corner at (t, t) sharp or filleted to ``fillet_mm``. Needs CadQuery."""
    import cadquery as cq

    L, t, w = part["leg_mm"], part["thickness_mm"], part["width_mm"]
    s = cq.Workplane("XZ").polyline([(0, 0), (L, 0), (L, t), (t, t), (t, L), (0, L)]).close().extrude(-w)
    if fillet_mm:
        s = s.edges("|Y").edges(cq.selectors.NearestToPointSelector((t, w / 2, t))).fillet(fillet_mm)
    return s


def corner_point(part: Mapping[str, Any], fillet_mm: float = 0.0) -> Tuple[float, float, float]:
    """The middle of the inside corner (of its fillet's arc), halfway across the width: where refine= is centred."""
    t, w = part["thickness_mm"], part["width_mm"]
    c = t + fillet_mm * (1 - math.sqrt(0.5))
    return (c, w / 2, c)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _version(root: Path) -> Optional[str]:
    import re
    m = re.search(r'^version\s*=\s*"([^"]+)"', (Path(root) / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def _chains(edges: Sequence[Tuple[int, int]]) -> List[List[int]]:
    """Edges as few polylines as a greedy walk finds (each edge once), so the drawn path continues instead of
    moving to each edge's start. Deterministic: the walk starts at the lowest unused edge and takes the lowest
    unused neighbour."""
    adj: Dict[int, List[int]] = {}
    for i, (a, b) in enumerate(edges):
        adj.setdefault(a, []).append(i)
        adj.setdefault(b, []).append(i)
    used = [False] * len(edges)
    out = []
    for i0 in range(len(edges)):
        if used[i0]:
            continue
        used[i0] = True
        a, b = edges[i0]
        chain = [a, b]
        while True:
            nxt = next((j for j in adj[chain[-1]] if not used[j]), None)
            if nxt is None:
                break
            used[nxt] = True
            p, q = edges[nxt]
            chain.append(q if p == chain[-1] else p)
        out.append(chain)
    return out


def _face_drawing(st, window: Sequence[float], plane_y: float = 0.0) -> Dict[str, Any]:
    """The front face's (y = ``plane_y``) surface mesh round the corner, in mm (x, z): its points, its inner edges
    as polylines (``chains``) and its whole outline (the edges of one triangle, a closed loop). Inner edges that
    cannot reach the window are left out; the renderer clips the rest to it."""
    import numpy as np

    from cadagent.simulation.fea import plane_at

    tags = st.select(plane_at(1, plane_y))
    tris = np.concatenate([st.face_tris[t] for t in tags])
    pairs = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    uniq, count = np.unique(pairs, axis=0, return_counts=True)
    xz = st.points[:, [0, 2]]
    x0, z0, x1, z1 = window
    lo, hi = xz[uniq].min(axis=1), xz[uniq].max(axis=1)
    reach = (hi[:, 0] >= x0) & (lo[:, 0] <= x1) & (hi[:, 1] >= z0) & (lo[:, 1] <= z1)
    inner, outline = uniq[reach & (count > 1)], uniq[count == 1]
    nodes = np.unique(np.concatenate([inner, outline]))
    index = {int(n): i for i, n in enumerate(nodes)}
    rows = lambda e: [(index[int(a)], index[int(b)]) for a, b in e]
    return {"plane_y_mm": plane_y, "points": [[round(float(x), 3), round(float(z), 3)] for x, z in xz[nodes]],
            "edges": len(inner) + len(outline), "chains": _chains(rows(inner)), "outline": _chains(rows(outline))}


def _step(shape, material, spec: Mapping[str, Any], mesh_mm: float, refine, window=None) -> Dict[str, Any]:
    """Mesh, solve and converge() one study; what its result says, and (with ``window``) the face to draw."""
    from cadagent.simulation.fea import MeshWarning, Study, plane_at

    fix, load, conv = spec["fix"], spec["load"], spec["converge"]
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", MeshWarning)
        st = Study(shape, material, mesh_mm=mesh_mm, name="bracket", refine=refine)
        st.fix(plane_at(fix["axis"], fix["at_mm"])).force(plane_at(load["axis"], load["at_mm"]), load["force_n"])
        res = st.solve()
        c = st.converge(factor=conv["factor"], tolerance=conv["tolerance"])
    m = res["mesh"]
    rec = {"mesh_mm": mesh_mm, "refine": m["refine"], "tets": m["tets"], "nodes": m["nodes"],
           "peak_mpa": res["von_mises_design_mpa"], "max_displacement_mm": res["max_displacement_mm"],
           "peak": m["peak"], "converge": c, "slivers": m["slivers"],
           "warnings": sorted({str(w.message) for w in caught if issubclass(w.category, MeshWarning)}),
           "seconds": round(time.perf_counter() - t0, 1), "mesher": m["mesher"]}
    if window is not None:
        rec["face"] = _face_drawing(st, window)
    return rec


def record(spec: Mapping[str, Any], root: Path, spec_path: Optional[Path] = None, log=print) -> Dict[str, Any]:
    """Run the spec's study (needs CadQuery, gmsh and scikit-fem) and return the scene. ``root``: the cad-agent
    checkout whose code runs it (its commit, version and file hashes are recorded); ``spec_path``: the spec file, whose
    sha256 is recorded too."""
    from cadagent.simulation.fea import Material

    t_start = time.perf_counter()
    root = Path(root)
    m = spec["material"]
    material = Material(m["name"], m["E_mpa"], m["nu"], m["strength_mpa"], m["density_g_cm3"])
    part, ref = spec["part"], spec["refine"]
    mesh_mm = spec["mesh_mm"]
    corners = []
    mesher = None
    for r in part["fillets_mm"]:
        shape = bracket(part, r)
        at = corner_point(part, r)
        name = "sharp corner" if not r else f"R{r:g} fillet"
        steps = []
        for size in [None] + list(ref["sizes_mm"]):
            zone = [(at, ref["radius_mm"], size)] if size else None
            s = _step(shape, material, spec, mesh_mm, zone, window=spec["window_mm"])
            s["size_mm"] = size or mesh_mm
            steps.append(s)
            log(f"{name}: {s['size_mm']:g} mm at the corner: {s['tets']} tets, {s['peak_mpa']:g} MPa, "
                f"converge {s['converge']['change']:+.1%} {'converged' if s['converge']['converged'] else 'not converged'}"
                f" ({s['seconds']} s)")
        uniform = []
        for u in spec["uniform_mm"]:
            s = _step(shape, material, spec, u, None)
            s["size_mm"] = u
            uniform.append(s)
            log(f"{name}: whole part at {u:g} mm: {s['tets']} tets, {s['peak_mpa']:g} MPa ({s['seconds']} s)")
        for s in steps + uniform:
            if mesher is None:
                mesher = s["mesher"]
            elif s["mesher"] != mesher:
                raise RuntimeError("the mesher changed during the run")
            del s["mesher"]
        corners.append({"fillet_mm": r, "name": name, "refine_at_mm": [round(v, 4) for v in at],
                        "steps": steps, "uniform": uniform})
    inputs = {rel: _sha256(root / rel) for rel in CODE}
    if spec_path is not None:
        try:
            rel = Path(spec_path).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = Path(spec_path).name
        inputs[rel] = _sha256(spec_path)
    lam = williams_lambda(270.0)
    return {
        "schema": SCHEMA, "name": spec["name"],
        "source": {"repo": spec["source"]["repo"], "name": spec["source"]["name"],
                   "licence": spec["source"]["licence"], "commit": _git(root, "rev-parse", "HEAD"),
                   "version": _version(root), "inputs": dict(sorted(inputs.items()))},
        "recorded": time.strftime("%Y-%m-%d", time.gmtime()),
        "mesher": mesher,
        "study": {"part": dict(part), "material": dict(m), "fix": dict(spec["fix"]), "load": dict(spec["load"]),
                  "mesh_mm": mesh_mm, "refine": dict(ref), "uniform_mm": list(spec["uniform_mm"]),
                  "converge": dict(spec["converge"]), "window_mm": list(spec["window_mm"]),
                  "element": "P2 tetrahedra", "solver": "linear elastic, small deflection"},
        "williams": {"corner_deg": 270.0, "lambda": round(lam, 6), "per_halving": round(2 ** (1 - lam), 4)},
        "corners": corners,
        "record_seconds": round(time.perf_counter() - t_start, 1),
    }


def write_scene(scene: Mapping[str, Any], path: Path) -> None:
    """The scene as JSON: one line per drawn point list, so a re-record's diff stays readable."""
    Path(path).write_text(json.dumps(scene, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------------- render

# (light, dark) colours this figure adds to the shared theme: the filleted corner's series
COLOURS = {"fillet": ("#2f6f9f", "#6cb4ff"), "mesh": ("#7d918b", "#71857f")}


class Phases:
    """The loop's timeline in seconds: one step every ``step`` seconds from ``start``, the last one held."""
    period = 16.0
    start = 0.0
    step = 2.6
    fade = 0.35
    out = 15.4                   # the final frame holds to here, then the loop returns to its first step


def summary(scene: Mapping[str, Any]) -> Dict[str, Any]:
    """The figure's claims, computed from the scene alone: the sharp corner's mean growth per halving and the
    filleted one's spread over the refined steps, each corner's first and last peak, and which steps converge()
    passed."""
    out = {}
    for c in scene["corners"]:
        v = [s["peak_mpa"] for s in c["steps"]]
        sizes = [s["size_mm"] for s in c["steps"]]
        halvings = math.log2(sizes[0] / sizes[-1])
        out[c["name"]] = {"first": v[0], "last": v[-1], "lo": min(v), "hi": max(v),
                          "per_halving": (v[-1] / v[0]) ** (1 / halvings) if halvings else None,
                          "spread": max(v) / min(v) - 1,
                          "converged": [bool(s["converge"]["converged"]) for s in c["steps"]]}
    return out


def _thousands(n: int) -> str:
    return f"{n:,}"


def _mpa(v: float) -> str:
    return f"{v:,.0f}"


def _fill(template: str, scene: Mapping[str, Any]) -> str:
    """A ``present`` string with {placeholders} from the scene: version, commit, gmsh, occ, recorded, platform, and
    the coarsest and finest element sizes at the corner (coarse, fine)."""
    m, src = scene["mesher"], scene["source"]
    plat = m.get("platform") or {}
    sizes = [s["size_mm"] for s in scene["corners"][0]["steps"]]
    return template.format(version=src.get("version") or "?", commit=(src.get("commit") or "?")[:7],
                           gmsh=m.get("gmsh") or "?", occ=m.get("occ") or "?", recorded=scene["recorded"],
                           platform=f"{plat.get('system', '?')} {plat.get('machine', '?')}".strip(),
                           coarse=f"{sizes[0]:g}", fine=f"{sizes[-1]:g}")


def render(scene: Mapping[str, Any], present: Mapping[str, Any]) -> str:
    """The SVG for a convergence ``scene`` with the words in ``present``. Deterministic: the same inputs give the same
    bytes. The loop starts on the coarsest mesh and adds a step every ``Phases.step`` seconds. Every animated element's
    own style is the final frame (the finest mesh, the whole chart, the claims), which is what a reader who asked for
    reduced motion sees."""
    if scene.get("schema") != SCHEMA:
        raise ValueError(f"not a {SCHEMA} scene")
    corners = scene["corners"]
    n = len(corners[0]["steps"])
    if len(corners) != 2 or any(len(c["steps"]) != n for c in corners) or n < 2:
        raise ValueError("the figure draws two corners with the same steps (two or more)")
    sizes = [s["size_mm"] for s in corners[0]["steps"]]
    if any([s["size_mm"] for s in c["steps"]] != sizes for c in corners):
        raise ValueError("the figure draws two corners with the same steps (two or more)")
    U = S.UNITS_PER_PX
    W, H = present["width"], present["height"]
    ph = Phases
    P, f = ph.period, ph.fade
    t_on = [ph.start + ph.step * k for k in range(n)]
    if t_on[-1] + f >= ph.out:
        raise ValueError("too many steps for the loop")
    tl = S.Timeline(P)
    light = dict(S.THEME.light, **{k: v[0] for k, v in COLOURS.items()})
    dark = dict(S.THEME.dark, **{k: v[1] for k, v in COLOURS.items()})
    colour = ["accent", "fillet"]
    u = lambda v: S.num(v * U, 0)                      # CSS px to whole units
    body: List[str] = []

    def text(x, y, s, cls, anchor=None, extra=""):
        a = f' text-anchor="{anchor}"' if anchor else ""
        return f'<text x="{u(x)}" y="{u(y)}" class="{cls}"{a}{extra}>{escape(s)}</text>'

    # text sizes are in units (U per CSS px). On a phone (the <img> 480 px wide or less) the small words (.w) hide
    # and a few large ones (.n) show instead
    css = [f".t{{font-size:{16 * U}px;font-weight:700;fill:var(--ink)}}.st{{font-size:{12 * U}px;fill:var(--muted)}}"
           f".h{{font-size:{13 * U}px;font-weight:700}}.big{{font-size:{22 * U}px;font-weight:700}}"
           f".sm{{font-size:{11 * U}px;fill:var(--muted)}}.ax{{font-size:{10.5 * U}px;fill:var(--muted)}}"
           f".v{{font-size:{11 * U}px;font-weight:600;fill:var(--bg)}}.nb{{font-size:{22 * U}px;font-weight:700}}"
           f".c0{{fill:var(--accent)}}.c1{{fill:var(--fillet)}}.n{{visibility:hidden}}"
           f"@media (max-width:480px){{.w{{visibility:hidden}}.n{{visibility:visible}}}}",
           f".me{{fill:none;stroke:var(--mesh);stroke-width:{0.55 * U};stroke-linejoin:round}}"
           f".ol{{fill:none;stroke:var(--ink);stroke-width:{1.6 * U};stroke-linejoin:round}}"
           f".fc{{fill:var(--panel)}}.fr{{fill:none;stroke:var(--line);stroke-width:{U}}}"
           f".gr{{stroke:var(--line);stroke-width:{U}}}"
           f".ln0,.ln1{{fill:none;stroke-width:{2.2 * U};stroke-linecap:round}}"
           f".ln0{{stroke:var(--accent)}}.ln1{{stroke:var(--fillet)}}"
           f".wl{{fill:none;stroke:var(--muted);stroke-width:{1.3 * U};stroke-dasharray:{5 * U} {4 * U}}}"
           f".ok{{fill:var(--good)}}.no{{fill:var(--accent)}}"]

    def per_step(k: int) -> str:
        """Shown only during step k: the final step's elements are drawn, the others start hidden."""
        return "" if k == n - 1 else ' opacity="0"'

    # ---- title
    body.append(text(20, 30, present["title"], "t w"))
    body.append(text(20, 49, _fill(present["subtitle"], scene), "st w"))
    body.append(text(20, 38, present["short_title"], "t n", extra=f' style="font-size:{26 * U}px"'))

    # ---- the two mesh panels: the front face round the corner, one drawing per step
    wx0, wz0, wx1, wz1 = scene["study"]["window_mm"]
    side, panel_y = 180.0, 86.0
    panel_x = [20.0, 20.0 + side + 12.0]
    k_mm = side / max(wx1 - wx0, wz1 - wz0)
    body.append("<defs>" + "".join(
        f'<clipPath id="cp{i}"><rect x="{u(px)}" y="{u(panel_y)}" width="{u(side)}" height="{u(side)}"/></clipPath>'
        for i, px in enumerate(panel_x)) + "</defs>")
    below = panel_y + side
    for i, c in enumerate(corners):
        px = panel_x[i]
        to = lambda x, z, px=px: ((px + (x - wx0) * k_mm) * U, (panel_y + (wz1 - z) * k_mm) * U)
        body.append(text(px, panel_y - 8, c["name"], f"h c{i} w"))
        body.append(text(px, panel_y - 8, c["name"], f"nb c{i} n"))
        body.append(f'<rect x="{u(px)}" y="{u(panel_y)}" width="{u(side)}" height="{u(side)}" class="fr"/>')
        for k, s in enumerate(c["steps"]):
            fd = s["face"]
            pts = [to(x, z) for x, z in fd["points"]]
            mesh, ol = S.PathBuilder(), S.PathBuilder()
            for ch in fd["chains"]:
                mesh.polyline([pts[j] for j in ch])
            loops = [[pts[j] for j in ch] for ch in fd["outline"]]
            for loop in loops:
                ol.polyline(loop)
            fill = S.polygon_d([lp[:-1] for lp in loops if len(lp) > 3 and lp[0] == lp[-1]])
            pk = s["peak"]["at_mm"]
            dx, dy = to(pk[0], pk[2])
            cv = s["converge"]
            ok = bool(cv["converged"])
            word = "converged" if ok else "not converged"
            g = [f'<g class="s{k}"{per_step(k)}><g clip-path="url(#cp{i})">',
                 f'<path class="fc" d="{fill}"/>' if fill else "",
                 f'<path class="me" d="{mesh.d()}"/><path class="ol" d="{ol.d()}"/>',
                 f'<circle cx="{S.num(dx, 0)}" cy="{S.num(dy, 0)}" r="{u(4.5)}" class="c{i}" '
                 f'style="stroke:var(--bg);stroke-width:{1.5 * U}px"/></g>',
                 # under the panel: the peak, the mesh and its flags, and converge()'s verdict
                 text(px, below + 30, f"{_mpa(s['peak_mpa'])} MPa", f"big c{i}"),
                 text(px, below + 47, f"{_thousands(s['tets'])} tets", "sm w"),
                 *(text(px, below + 62 + 15 * j, line, "sm w") for j, line in enumerate(_flags(s["peak"]))),
                 text(px, below + 92, f"a {cv['factor']:g}× finer mesh: {cv['change']:+.1%}", "sm w"),
                 f'<rect x="{u(px)}" y="{u(below + 100)}" width="{u(side)}" height="{u(21)}" rx="{u(4)}" '
                 f'class="{"ok" if ok else "no"}"/>',
                 text(px + 7, below + 114.5, f"converge(): {word}", "v w"),
                 text(px + side / 2, below + 117, word, "v n", "middle", f' style="font-size:{18 * U}px"'),
                 "</g>"]
            body.append("".join(g))

    # ---- the chart: the design peak against the element size at the corner (log scale, finer to the right)
    x0, x1, y0, y1 = 470.0, 704.0, 86.0, 300.0
    lo, hi = math.log2(sizes[0]), math.log2(sizes[-1])
    X = lambda size: x0 + 12 + (x1 - x0 - 24) * (math.log2(size) - lo) / (hi - lo)
    vals = [s["peak_mpa"] for c in corners for s in c["steps"] + c["uniform"]]
    top = 250 * math.ceil(max(vals) * 1.1 / 250)
    Y = lambda v: y1 - (y1 - y0) * v / top
    band_w = 28.0
    body.append(f'<rect class="band" x="{u(X(sizes[0]) - band_w / 2)}" y="{u(y0 - 4)}" width="{u(band_w)}" '
                f'height="{u(y1 - y0 + 8)}" rx="{u(5)}" style="fill:var(--soft);opacity:.6"/>')
    for v in range(0, int(top) + 1, 250):
        body.append(f'<path class="gr" d="M{u(x0)} {u(Y(v))}H{u(x1)}"/>')
        body.append(text(x0 - 6, Y(v) + 3.5, f"{v:,}", "ax w", "end"))
    for size in sizes:
        body.append(text(X(size), y1 + 16, f"{size:g}", "ax w", "middle"))
    body.append(text((x0 + x1) / 2, y1 + 32, present["x_axis"], "ax w", "middle"))
    ym = (y0 + y1) / 2
    body.append(text(426, ym, present["y_axis"], "ax w", "middle", f' transform="rotate(-90 {u(426)} {u(ym)})"'))
    # Williams' rate, fixed, through the sharp corner's finest step: what a singular corner does
    w = scene["williams"]
    ref = corners[0]["steps"][-1]
    span = [sizes[1] * 2 ** (-j / 4) for j in range(4 * (n - 2) + 1)]
    wl = S.PathBuilder()
    wl.polyline([(X(s_) * U, Y(ref["peak_mpa"] * (s_ / ref["size_mm"]) ** (w["lambda"] - 1)) * U) for s_ in span])
    body.append(f'<path class="wl w" d="{wl.d()}"/>')
    # each corner's line and dots appear step by step and stay to the end of the loop; the whole part meshed at a
    # size (no refine=) shows as an open square with the step of that size
    for i, c in enumerate(corners):
        steps = c["steps"]
        for s in c["uniform"]:
            k = sizes.index(s["size_mm"]) if s["size_mm"] in sizes else n - 1
            cx, cy = X(s["size_mm"]), Y(s["peak_mpa"])
            body.append(f'<rect class="p{k}" x="{u(cx - 6)}" y="{u(cy - 6)}" width="{u(12)}" height="{u(12)}" '
                        f'style="fill:none;stroke:var(--{colour[i]});stroke-width:{1.4 * U}px"/>')
        for k, s in enumerate(steps):
            cx, cy = X(s["size_mm"]), Y(s["peak_mpa"])
            if k:
                bx, by = X(steps[k - 1]["size_mm"]), Y(steps[k - 1]["peak_mpa"])
                body.append(f'<path class="ln{i} p{k}" d="M{u(bx)} {u(by)}L{u(cx)} {u(cy)}"/>')
            body.append(f'<circle class="p{k}" cx="{u(cx)}" cy="{u(cy)}" r="{u(4.5)}" '
                        f'style="fill:var(--bg);stroke:var(--{colour[i]});stroke-width:{2 * U}px"/>')
        last = steps[-1]
        body.append(text(X(last["size_mm"]) - 9, Y(last["peak_mpa"]) + (-9 if i == 0 else 19), _mpa(last["peak_mpa"]),
                         f"sm c{i} p{n - 1}", "end", ' style="font-weight:700"'))
    # the legend, under the chart
    ly, lx = y1 + 52, 420.0
    legend = [(lx, ly, f'<path class="ln0" d="M0 0h{u(16)}"/>', corners[0]["name"]),
              (lx + 140, ly, f'<path class="ln1" d="M0 0h{u(16)}"/>', corners[1]["name"]),
              (lx, ly + 16, f'<rect x="{u(3)}" y="{u(-5)}" width="{u(10)}" height="{u(10)}" '
               f'style="fill:none;stroke:var(--muted);stroke-width:{1.4 * U}px"/>', present["uniform_legend"]),
              (lx, ly + 32, f'<path class="wl" d="M0 0h{u(16)}"/>',
               present["williams_legend"].format(exponent=f"{w['lambda'] - 1:.2f}".replace("-", "−")))]
    for gx, gy, mark, words in legend:
        body.append(f'<g class="w" transform="translate({u(gx)} {u(gy)})">{mark}{text(22, 4, words, "sm")}</g>')

    # ---- under everything, per step: what this step is and what it cost, against meshing the whole part that fine
    for k, size in enumerate(sizes):
        tets = present["tets_pair"].format(*(_thousands(c["steps"][k]["tets"]) for c in corners))
        key = "step_first" if k == 0 else "step_line"
        line = present[key].format(step=k + 1, steps=n, size=f"{size:g}", tets=tets)
        whole = [next((u_ for u_ in c["uniform"] if u_["size_mm"] == size), None) for c in corners]
        if k and all(whole):
            line += present["step_cost"].format(size=f"{size:g}", whole=present["tets_pair"].format(
                *(_thousands(u_["tets"]) for u_ in whole)))
        body.append(f'<g class="s{k} w"{per_step(k)}>{text(20, 418, line, "sm")}</g>')
    # the end state's claims, from the scene
    sm = summary(scene)
    a, b = sm[corners[0]["name"]], sm[corners[1]["name"]]
    claims = [present["sharp_claim"].format(per_halving=f"{a['per_halving']:.2f}", rate=f"{w['per_halving']:.2f}"),
              present["fillet_claim"].format(spread=f"{100 * b['spread']:.1f}", steps=n)]
    for j, words in enumerate(claims):
        body.append(f'<g class="p{n - 1} w">{text(20, 438 + 16 * j, words, f"sm c{j}")}</g>')
    # ---- the caption: what this is, and what it is not
    for j, line in enumerate(present["caption"]):
        body.append(text(20, H - 27 + 15 * j, _fill(line, scene), "sm w"))

    # ---- the timeline
    for k in range(n):
        on = t_on[k]
        off = t_on[k + 1] if k + 1 < n else ph.out
        if k == 0:
            pts = [(0, 1), (off, 1), (off + f, 0), (ph.out, 0), (ph.out + f, 1), (P, 1)]
        elif k == n - 1:
            pts = [(0, 0), (on, 0), (on + f, 1), (ph.out, 1), (ph.out + f, 0), (P, 0)]
        else:
            pts = [(0, 0), (on, 0), (on + f, 1), (off, 1), (off + f, 0), (P, 0)]
        tl.opacity(f".s{k}", pts)
        if k:                                          # the chart's step-k marks: from their step to the loop's end
            tl.opacity(f".p{k}", [(0, 0), (on, 0), (on + f, 1), (ph.out, 1), (ph.out + f, 0), (P, 0)])
    shift = lambda k: u(X(sizes[k]) - X(sizes[0]))
    frames = [(0, shift(0))]
    for k in range(1, n):
        frames += [(t_on[k] - 0.45, shift(k - 1)), (t_on[k], shift(k))]
    frames += [(ph.out, shift(n - 1)), (ph.out + f, shift(0)), (P, shift(0))]
    css.append(f".band{{transform:translateX({shift(n - 1)}px)}}")
    tl.add(".band", frames, lambda d: f"transform:translateX({d}px)", "ease-in-out")
    return S.document(W, H, _fill(present["label"], scene), _fill(present["description"], scene),
                      "".join(css) + tl.stylesheet(), body, S.Theme(light, dark))


def _flags(peak: Mapping[str, Any]) -> List[str]:
    """The peak's resolution flags in words, a line each: elements across the wall, and the elements against the
    fillet's radius (or, at a sharp corner, that the peak is singular)."""
    out = []
    if peak.get("elements_across") is not None:
        out.append(f"wall {peak['wall_mm']:.3g} mm: {peak['elements_across']:g} elements across "
                   + ("✓" if peak["wall_resolved"] else "✗"))
    if peak.get("radius_mm") is not None:
        out.append(f"R{peak['radius_mm']:g}: elements {peak['element_mm']:.2g} mm "
                   + ("✓" if peak["radius_resolved"] else "✗"))
    elif "sharp inside corner" in (peak.get("where") or ""):
        out.append("sharp corner: singular ✗")
    return out
