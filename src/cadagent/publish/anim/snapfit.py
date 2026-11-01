"""A printed cantilever snap engaging, drawn from cad-agent's snap-fit calculator: the arm bends as the mating part's
edge rides its hook, and its root strain is charted against two filaments' allowables, with the push to mate.

Two stages, as for the other figures, so the committed SVG can be checked anywhere:

* ``record(spec, root)`` runs :mod:`cadagent.mechanical.compliant.snapfit` on the spec's ``snaps``, a ``cad-agent
  snapfit`` declaration of one arm in two filaments. Per snap it keeps:
  - what :func:`~cadagent.mechanical.compliant.snapfit.check_spec_entry` says: the verdict, the rows, the material
    derivation with its data-sheet editions, the forces;
  - the closed form along the insertion (:func:`~cadagent.mechanical.compliant.snapfit.engagement`);
  - the travel where the root strain first reaches the allowable.

  It also keeps the arm's bent shape at the drawn slices (:func:`cadagent.formulas.cantilever_shape`), the toolkit's
  version and commit and the sha256 of the files that made it. It is pure Python and takes well under a second.
* ``render(scene, present)`` is plain Python. It writes the SVG, with CSS keyframes and both colour schemes, from the
  scene and the spec's ``present`` words. The same inputs always give the same bytes.

The figure is the guide's closed form on stated inputs, drawn: small-deflection beam theory with the mating part rigid,
and allowables derived from data sheets. It is not a measurement: printed snaps need a test print. The drawing turns the
hook with the arm's tip, as a real hook turns; the closed form, like the guide, does not. Turned, the hook's lowest
point sits about ``sin(tip slope) x hook depth`` further out, so the drawn edge reaches the top of the lead after that
much less travel (1.95 mm, against the calculator's 2.25 mm here). The drawing and the charts meet at the same moments.
The turned face is steeper too, so the closed form under-states the push near the top of the lead: the scene records
the turn (:func:`turned_lead`) and the guide's push on the turned face (:func:`turned_push`), and the docs state both.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from cadagent.publish.anim import svg as S

SCHEMA = "cadagent.anim.snapfit/1"
# the files whose sha256 a scene records: the calculator, the allowables, the beam shape and this module (record()
# adds the spec)
CODE = ("src/cadagent/mechanical/compliant/snapfit.py", "src/cadagent/mechanical/compliant/allowables.py",
        "src/cadagent/formulas/beams.py", "src/cadagent/publish/anim/snapfit.py")
# the geometry every snap in the spec must share: the figure draws one arm
ARM_KEYS = ("length_mm", "undercut_mm", "design", "section", "root_radius_mm", "lead_deg", "orientation")


# ----------------------------------------------------------------------------------------------------- the record

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


def _round(v: Any, digits: int = 9) -> Any:
    """Floats to ``digits`` significant figures, through dicts and lists, so the JSON diff of a re-record shows only
    numbers that moved (and not the last bits of a tangent from another libm)."""
    if isinstance(v, float):
        return float(f"{v:.{digits}g}") if math.isfinite(v) else v
    if isinstance(v, dict):
        return {k: _round(x, digits) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_round(x, digits) for x in v]
    return v


def arm(spec: Mapping[str, Any]) -> Dict[str, Any]:
    """The one arm the spec's snaps share, in mm and degrees. A ValueError if they differ in geometry or print
    direction, or the section is not a rectangle."""
    snaps = spec["snaps"]
    if len(snaps) != 2:
        raise ValueError("the figure draws one arm in two materials: give two snaps")
    for k in ARM_KEYS:
        if any(s.get(k) != snaps[0].get(k) for s in snaps):
            raise ValueError(f"the snaps differ in {k}: the figure draws one arm")
    s = snaps[0]
    rect = (s.get("section") or {}).get("rect")
    if not isinstance(rect, dict):
        raise ValueError("the figure draws a rectangular arm: section: {rect: {width_mm, thickness_mm}}")
    if any(x.get("share", 1.0) != 1.0 for x in snaps):
        raise ValueError("the figure draws the arm taking all of the undercut (share 1)")
    return {"length_mm": float(s["length_mm"]), "thickness_mm": float(rect["thickness_mm"]),
            "width_mm": float(rect["width_mm"]), "design": int(s.get("design", 1)),
            "undercut_mm": float(s["undercut_mm"]), "lead_deg": float(s["lead_deg"]),
            "root_radius_mm": float(s["root_radius_mm"]), "orientation": s["orientation"]}


def shape(design: int, slices: int) -> Dict[str, List[float]]:
    """The bent arm per unit tip deflection: at the middle of each of ``slices`` equal slices, and at the tip, the
    deflection y(x) / y_tip (:func:`cadagent.formulas.cantilever_shape`) and its slope d(y / y_tip) / d(x / L), by
    central differences (one-sided, second order, at the tip)."""
    from cadagent.formulas import cantilever_shape as phi

    e = 1e-6
    xi = [(i + 0.5) / slices for i in range(slices)]
    defl = [phi(x, design) for x in xi] + [phi(1.0, design)]
    slope = [(phi(x + e, design) - phi(x - e, design)) / (2 * e) for x in xi]
    slope.append((3 * phi(1.0, design) - 4 * phi(1.0 - e, design) + phi(1.0 - 2 * e, design)) / (2 * e))
    return {"xi": xi + [1.0], "deflection": [round(v, 6) for v in defl], "slope": [round(v, 6) for v in slope]}


def record(spec: Mapping[str, Any], root: Path, spec_path: Optional[Path] = None) -> Dict[str, Any]:
    """Run the calculator on the spec's snaps and return the scene. ``root``: the cad-agent checkout whose code runs it
    (its commit, version and file hashes are recorded); ``spec_path``: the spec file, whose sha256 is recorded too."""
    from cadagent.mechanical.compliant import snapfit as sf

    t0 = time.perf_counter()
    root = Path(root)
    geo = arm(spec)
    draw = dict(spec["drawing"])
    section = sf.rect_section(geo["width_mm"], geo["thickness_mm"])
    sh = shape(geo["design"], int(draw["slices"]))
    snaps = []
    turn = None
    for entry in spec["snaps"]:
        r = sf.check_spec_entry(dict(entry))
        m = r["material"]
        curve = sf.engagement(length=geo["length_mm"], section=section, undercut=geo["undercut_mm"],
                              lead_deg=geo["lead_deg"], design=geo["design"], secant_mpa=m["secant_mpa"],
                              friction=m.get("friction"), land_mm=float(draw["land_mm"]))
        turn = turned_lead(geo, sh, curve["peak"]["deflection_mm"])
        snaps.append({"name": r["name"], "pass": r["pass"], "strain": r["strain"], "deflection_mm": r["deflection_mm"],
                      "deflection_force_n": r.get("deflection_force_n"), "mating_force_n": r.get("mating_force_n"),
                      "warnings": r["warnings"], "rows": r["rows"], "material": m, "engagement": curve,
                      "over_from_mm": sf.travel_at_strain(curve, m["allowable"]),
                      "turned_mating_force_n": turned_push(curve, turn["lead_face_deg"])})
    inputs = {rel: _sha256(root / rel) for rel in CODE}
    if spec_path is not None:
        try:
            rel = Path(spec_path).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = Path(spec_path).name
        inputs[rel] = _sha256(spec_path)
    return _round({
        "schema": SCHEMA, "name": spec["name"],
        "source": {"repo": spec["source"]["repo"], "name": spec["source"]["name"],
                   "licence": spec["source"]["licence"], "commit": _git(root, "rev-parse", "HEAD"),
                   "version": _version(root), "inputs": dict(sorted(inputs.items()))},
        "recorded": time.strftime("%Y-%m-%d", time.gmtime()),
        "method": sf.GUIDE,
        "arm": geo, "drawing": draw,
        "shape": sh,
        "turn": turn,
        "snaps": snaps,
        "record_seconds": round(time.perf_counter() - t0, 2),
    })


def turned_lead(geo: Mapping[str, Any], sh: Mapping[str, Any], y: float) -> Dict[str, float]:
    """How far the hook has turned with the arm's tip at tip deflection ``y`` (degrees), and so the angle of the lead
    face the mating edge rides then: the lead angle plus that turn. The closed form, like the guide, keeps the lead at
    its as-made angle; the figure draws the turn, and records what it does to the push (:func:`turned_push`)."""
    tip = math.degrees(math.atan(y * sh["slope"][-1] / geo["length_mm"]))
    return {"tip_deg": tip, "lead_face_deg": geo["lead_deg"] + tip}


def turned_push(curve: Mapping[str, Any], face_deg: float) -> Optional[float]:
    """The guide's push to mate at the top of the lead, W = P (mu + tan a) / (1 - mu tan a), with the turned face's
    angle ``face_deg`` instead of the as-made lead: a check on how much the closed form under-states the peak push.
    None without a friction or a deflection force, or when the turned face would self-lock."""
    from cadagent.mechanical.compliant import snapfit as sf

    p, mu = curve["peak"]["deflection_force_n"], curve["friction"]
    if p is None or mu is None:
        return None
    w = sf.mating_force(p, mu, face_deg)
    return None if math.isinf(w) else w


def write_scene(scene: Mapping[str, Any], path: Path) -> None:
    """The scene as JSON, indented as the other scenes are, so a re-record's diff shows which numbers moved."""
    Path(path).write_text(json.dumps(scene, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------------- words

def pct(fraction: float, digits: int = 2) -> str:
    return f"{100 * fraction:.{digits}f} %"


def ratio(snap: Mapping[str, Any]) -> float:
    """The root strain over the allowable, as the root-strain row compares them."""
    return snap["strain"] / snap["material"]["allowable"]


def sheet(material: Mapping[str, Any]) -> str:
    """The data-sheet edition the allowable comes from, short: "Bambu Lab PETG-CF V3.0". Along the layers it is the
    in-plane (XY) value's sheet; across them, whichever of XY and Z gives the lower strain."""
    xy, z = material["xy"], material["z"]
    gov = xy if material["orientation"] == "along" or xy["strain"] <= z["strain"] else z
    return gov["sheet"].replace(" Technical Data Sheet", "")


def _fill(template: str, scene: Mapping[str, Any], present: Mapping[str, Any], **more: Any) -> str:
    """A ``present`` string with {placeholders} from the scene: version, commit, the arm's dimensions (length,
    thickness, width, undercut, lead, root, laid) and the filled ``arm`` line, the peak root strain, each snap's
    short name, allowable and ratio (short_0, allow_0, ratio_0, ...) and the data sheets."""
    a, src = scene["arm"], scene["source"]
    words = {"version": src.get("version") or "?", "commit": (src.get("commit") or "?")[:7],
             "length": f"{a['length_mm']:g}", "thickness": f"{a['thickness_mm']:g}", "width": f"{a['width_mm']:g}",
             "undercut": f"{a['undercut_mm']:g}", "lead": f"{a['lead_deg']:g}", "root": f"{a['root_radius_mm']:g}",
             "laid": present["orientation"][a["orientation"]], "strain": pct(scene["snaps"][0]["strain"]),
             "sheets": " and ".join(sheet(s["material"]) for s in scene["snaps"])}
    for i, s in enumerate(scene["snaps"]):
        words.update({f"short_{i}": present["short"][s["name"]], f"allow_{i}": pct(s["material"]["allowable"]),
                      f"ratio_{i}": f"{100 * ratio(s):.0f} %", f"verdict_{i}": "pass" if s["pass"] else "fail"})
    words["arm"] = present["arm"].format(**words)
    words.update(more)
    return template.format(**words)


# ----------------------------------------------------------------------------------------------------- render

# (light, dark) colours this figure adds to the shared theme: the printed part and its arm, the mating part, the
# gauges' bars and tracks, and one colour per material (the first is the shared theme's good green, the second its accent)
COLOURS = {"part": ("#e3ebdc", "#22312e"), "mate": ("#efe9d8", "#2a2a22"), "bar": ("#7d918b", "#71857f"),
           "track": ("#efece0", "#1f2b29"),
           "m0": ("#2f7d5b", "#5cc8a0"), "m1": ("#bd3a12", "#ff7a45")}
K_MM = 15.0                       # drawing scale, CSS px per mm: true scale, deflection included


class Phases:
    """The loop's timeline in seconds. The mating part waits, closes in at ``speed`` mm/s of travel (the chart's
    travel: the calculator's), the hook drops off in ``drop``, the joint holds, and the scene fades and starts
    again."""
    period = 11.0
    start = 0.5
    speed = 1.0
    drop = 0.18
    hold = 3.4
    fade = 0.35
    jump = 0.4                    # after fading out: the mating part goes back to its start, unseen


def times(scene: Mapping[str, Any]) -> Dict[str, float]:
    """The moments of the loop: start (the part moves), contact, top (of the lead), land (its end), released, out
    (the fade starts), and per snap the moment its root strain reaches its allowable (``over_<i>``, if it does)."""
    ph = Phases
    s0 = scene["snaps"][0]["engagement"]
    t = {"start": ph.start}
    t["contact"] = t["start"] + scene["drawing"]["approach_mm"] / ph.speed
    t["top"] = t["contact"] + s0["lead_travel_mm"] / ph.speed
    t["land"] = t["top"] + s0["land_mm"] / ph.speed
    t["released"] = t["land"] + ph.drop
    t["out"] = t["released"] + ph.hold
    for i, s in enumerate(scene["snaps"]):
        if s["over_from_mm"] is not None:
            t[f"over_{i}"] = t["contact"] + s["over_from_mm"] / ph.speed
    if t["out"] + ph.fade + ph.jump + 2 * ph.fade >= ph.period:
        raise ValueError("the engagement is too long for the loop")
    return t


def _hook_pose(a: Mapping[str, Any], sh: Mapping[str, Any], y: float) -> Tuple[float, float]:
    """The hook's turn (radians, counter-clockwise) and lift (mm) at tip deflection ``y``: it moves with the tip."""
    return math.atan(y * sh["slope"][-1] / a["length_mm"]), y * sh["deflection"][-1]


def edge_x(a: Mapping[str, Any], sh: Mapping[str, Any], clearance: float, y: float) -> float:
    """Where the mating part's edge (at the height the hook rides over) touches the drawn hook's lead face when the
    tip is lifted ``y`` mm, in mm from the root along the arm: the lead face turned with the tip. Its lowest point
    (the top of the lead) where the edge is past it."""
    theta, lift = _hook_pose(a, sh, y)
    h, u, alpha = a["thickness_mm"], a["undercut_mm"], math.radians(a["lead_deg"])
    deep = h / 2 + u + clearance
    p0, p1 = (0.0, -deep), ((u + clearance) / math.tan(alpha), -h / 2)        # the lead face, hook frame
    world = lambda p: (a["length_mm"] + p[0] * math.cos(theta) - p[1] * math.sin(theta),
                       lift + p[0] * math.sin(theta) + p[1] * math.cos(theta))
    (x0, z0), (x1, z1) = world(p0), world(p1)
    zb = -h / 2 - clearance
    lam = min(1.0, max(0.0, (zb - z0) / (z1 - z0)))
    return x0 + lam * (x1 - x0)


def render(scene: Mapping[str, Any], present: Mapping[str, Any]) -> str:
    """The SVG for a snap-fit ``scene`` with the words in ``present``. Deterministic: the same inputs give the same
    bytes. Every animated element's own style is the still: the arm at the top of the lead, where the strain peaks,
    with the whole strain and force curves, both gauges at their peak and both verdicts, which is what a reader who
    asked for reduced motion sees."""
    if scene.get("schema") != SCHEMA:
        raise ValueError(f"not a {SCHEMA} scene")
    snaps = scene["snaps"]
    if len(snaps) != 2:
        raise ValueError("the figure draws one arm in two materials")
    strains = [[p["strain"] for p in s["engagement"]["points"]] for s in snaps]
    if strains[0] != strains[1]:
        raise ValueError("the two snaps must strain alike: the figure draws one arm")
    U = S.UNITS_PER_PX
    W, H = present["width"], present["height"]
    a, sh, dr = scene["arm"], scene["shape"], scene["drawing"]
    ph, t = Phases, times(scene)
    P, f = ph.period, ph.fade
    t_back = t["out"] + f + ph.jump
    tl = S.Timeline(P)
    light = dict(S.THEME.light, **{k: v[0] for k, v in COLOURS.items()})
    dark = dict(S.THEME.dark, **{k: v[1] for k, v in COLOURS.items()})
    u = lambda v: S.num(v * U, 0)                      # CSS px to whole units
    body: List[str] = []
    eng = snaps[0]["engagement"]
    lead, land, peak = eng["lead_travel_mm"], eng["land_mm"], eng["peak"]
    y_top = peak["deflection_mm"]

    def text(x, y, s, cls, anchor=None, extra=""):
        an = f' text-anchor="{anchor}"' if anchor else ""
        return f'<text x="{u(x)}" y="{u(y)}" class="{cls}"{an}{extra}>{escape(s)}</text>'

    def fade_in(selector: str, at: float) -> None:
        """Hidden until ``at``, then shown until the loop fades out: its still is shown."""
        tl.opacity(selector, [(0, 0), (at, 0), (at + 0.25, 1), (t["out"], 1), (t["out"] + f, 0), (P, 0)])

    css = [f".t{{font-size:{16 * U}px;font-weight:700;fill:var(--ink)}}.st{{font-size:{12 * U}px;fill:var(--muted)}}"
           f".sm{{font-size:{11 * U}px;fill:var(--muted)}}.ax{{font-size:{10.5 * U}px;fill:var(--muted)}}"
           f".lb{{font-size:{11 * U}px;fill:var(--ink)}}.b{{font-weight:700}}"
           f".nb{{font-size:{22 * U}px;font-weight:700;fill:var(--ink)}}.n{{visibility:hidden}}"
           f"@media (max-width:480px){{.w{{visibility:hidden}}.n{{visibility:visible}}}}",
           f".ed{{fill:none;stroke:var(--edge);stroke-width:{1.4 * U}}}"
           f".rs{{fill:none;stroke:var(--muted);stroke-width:{U};stroke-dasharray:{3 * U} {3 * U}}}"
           f".af{{fill:var(--part)}}.mt{{fill:var(--mate);stroke:var(--edge);stroke-width:{1.4 * U};"
           f"stroke-linejoin:round}}"
           f".gr{{stroke:var(--line);stroke-width:{U}}}.ok{{fill:var(--good)}}.no{{fill:var(--accent)}}"
           f".cv{{fill:none;stroke:var(--ink);stroke-width:{2 * U};stroke-linejoin:round;stroke-dasharray:1}}"
           f".al{{stroke-width:{1.6 * U};stroke-dasharray:{6 * U} {4 * U}}}"
           f".m0s{{stroke:var(--m0)}}.m1s{{stroke:var(--m1)}}"]

    # ---- title
    body.append(text(20, 30, present["title"], "t w"))
    body.append(text(20, 49, _fill(present["subtitle"], scene, present), "st w"))
    body.append(text(20, 38, present["short_title"], "t n", extra=f' style="font-size:{26 * U}px"'))

    # ---- the mechanism, side view at true scale: the printed part's wall and its arm, the hook, the mating part
    L, h, ud = a["length_mm"], a["thickness_mm"], a["undercut_mm"]
    c, R = dr["clearance_mm"], a["root_radius_mm"]
    x_root, y_mid = 56.0, 128.0                         # the root, on the arm's centre line, CSS px
    X = lambda mm: x_root + K_MM * mm                   # mm along the arm from its root, to px
    ht, rr = h * K_MM / 2, R * K_MM
    wall_top, wall_bot = 74.0, 204.0
    # the wall and the root's fillets, one part with the arm: no line where the arm leaves the wall
    body.append(f'<path class="af" d="M{u(30)} {u(wall_top)}H{u(x_root)}V{u(y_mid - ht - rr)}'
                f'a{u(rr)} {u(rr)} 0 0 0 {u(rr)} {u(rr)}H{u(x_root)}V{u(y_mid + ht)}h{u(rr)}'
                f'a{u(rr)} {u(rr)} 0 0 0 {u(-rr)} {u(rr)}V{u(wall_bot)}H{u(30)}z"/>')
    body.append(f'<path class="ed" style="stroke-linejoin:round" d="M{u(x_root + rr)} {u(y_mid + ht)}'
                f'a{u(rr)} {u(rr)} 0 0 0 {u(-rr)} {u(rr)}V{u(wall_bot)}H{u(30)}V{u(wall_top)}H{u(x_root)}'
                f'V{u(y_mid - ht - rr)}a{u(rr)} {u(rr)} 0 0 0 {u(rr)} {u(rr)}"/>')
    body.append(text(30, wall_bot + 16, present["part_a"], "sm w"))
    # the arm, in slices: each one moves and turns with the bent shape at its middle, so the arm bends smoothly while
    # every keyframe is exact (the lift and the turn are both linear in the tip deflection)
    n = len(sh["xi"]) - 1
    seg = L * K_MM / n
    rot = lambda y, slope: -math.degrees(math.atan(y * slope / L))

    def pose(phi: float, slope: float, y: float) -> str:
        return f"transform:translate(0,{S.num(-y * phi * K_MM * U, 1)}px) rotate({S.num(rot(y, slope), 3)}deg)"

    fills, edges = [], []
    for i in range(n):
        x0, x1 = x_root + i * seg, x_root + (i + 1) * seg
        xc = (x0 + x1) / 2
        css.append(f".a{i}{{transform-origin:{u(xc)}px {u(y_mid)}px;{pose(sh['deflection'][i], sh['slope'][i], y_top)}}}")
        fills.append(f'<rect class="a{i} af" x="{u(x0 - (0 if i == 0 else 0.6))}" y="{u(y_mid - ht)}" '
                     f'width="{u(x1 - x0 + (0.6 if i == 0 else 1.2))}" height="{u(2 * ht)}"/>')
        e0 = max(x0, x_root + rr)                       # the fillets carry the edges to here
        if e0 < x1:
            edges.append(f'<path class="a{i} ed" d="M{u(e0)} {u(y_mid - ht)}H{u(x1)}M{u(e0)} {u(y_mid + ht)}'
                         f'H{u(x1)}"/>')
    # the arm as made, dashed, under the bent one: the bend is drawn at true scale
    rl = (ud + c) / math.tan(math.radians(a["lead_deg"]))
    xt, xe = X(L), X(L + rl)
    yb, yp = y_mid + ht, y_mid + ht + (ud + c) * K_MM
    body.append(f'<path class="rs" d="M{u(x_root + rr)} {u(y_mid - ht)}H{u(xe)}V{u(yb)}L{u(xt)} {u(yp)}V{u(yb)}'
                f'H{u(x_root + rr)}"/>')
    body += fills + edges
    # the hook: rigid, turning with the tip about the end of the arm's centre line
    css.append(f".hk{{transform-origin:{u(xt)}px {u(y_mid)}px;"
               f"{pose(sh['deflection'][-1], sh['slope'][-1], y_top)}}}")
    body.append(f'<g class="hk"><path class="af" d="M{u(xt - 1)} {u(y_mid - ht)}H{u(xe)}V{u(yb)}L{u(xt)} {u(yp)}'
                f'V{u(yb)}H{u(xt - 1)}z"/><path class="ed" d="M{u(xt)} {u(y_mid - ht)}H{u(xe)}V{u(yb)}'
                f'L{u(xt)} {u(yp)}V{u(yb)}" style="stroke-linejoin:round"/></g>')
    # the root, where the strain peaks: on the hook's side, which the bend stretches
    body.append(f'<circle cx="{u(x_root + 2)}" cy="{u(yb + 1)}" r="{u(4)}" class="no" '
                f'style="stroke:var(--bg);stroke-width:{1.5 * U}px"/>')
    body.append(text(x_root + 10, yb + 22, present["root"], "sm w"))
    # the mating part: a wall as thick as the land, on a base, closing in from the right; drawn with its edge at x = 0
    tw, zb = land * K_MM, y_mid + ht + c * K_MM
    base_r = tw + 4.0 * K_MM
    body.append(f'<g class="mp"><path class="mt" d="M0 {u(zb)}h{u(tw)}V{u(wall_bot - 16)}H{u(base_r)}'
                f'V{u(wall_bot)}H0z"/>'
                f'<path d="M{u(base_r - 8)} {u(wall_bot - 28)}h{u(-34)}m{u(7)} {u(-5)}l{u(-7)} {u(5)} {u(7)} {u(5)}" '
                f'style="fill:none;stroke:var(--muted);stroke-width:{1.6 * U}px;stroke-linecap:round;'
                f'stroke-linejoin:round"/>' + text(tw + 6, wall_bot + 16, present["part_b"], "sm w") + "</g>")
    # where the edge is: waiting, then on the drawn lead face, along the land, and past the hook as it drops
    edge0 = edge_x(a, sh, c, 0.0)
    xs = {"wait": edge0 + dr["approach_mm"]}
    lead_keys = [(t["contact"] + k / 4 * lead / ph.speed, edge_x(a, sh, c, k / 4 * y_top)) for k in range(5)]
    top_edge = lead_keys[-1][1]
    theta, _ = _hook_pose(a, sh, y_top)
    tip_x = L + math.sin(theta) * (h / 2 + ud + c)      # the hook's lowest point, turned with the tip
    land_end = tip_x - land
    seat = L - land - 0.05                              # behind the hook's return face, with a hair of play
    px = lambda mm: S.num(X(mm) * U, 0) + "px"
    css.append(f".mp{{transform:translateX({px(top_edge)})}}")
    frames = [(0, xs["wait"]), (t["start"], xs["wait"])] + lead_keys + [(t["land"], land_end),
                                                                          (t["released"], seat), (t_back, seat),
                                                                          (t_back + 0.01, xs["wait"]), (P, xs["wait"])]
    tl.add(".mp", frames, lambda v: f"transform:translateX({px(v)})", "linear")
    tl.opacity(".mp", [(0, 1), (t["out"], 1), (t["out"] + f, 0), (t_back + 0.05, 0), (t_back + 0.05 + f, 1), (P, 1)])
    arm_frames = [(0, 0.0), (t["contact"], 0.0), (t["top"], y_top), (t["land"], y_top), (t["released"], 0.0),
                  (P, 0.0)]
    for i in range(n):
        tl.add(f".a{i}", arm_frames, lambda y, i=i: pose(sh["deflection"][i], sh["slope"][i], y), "linear")
    tl.add(".hk", arm_frames, lambda y: pose(sh["deflection"][-1], sh["slope"][-1], y), "linear")

    # ---- the charts: root strain, and the push to mate, against the calculator's travel
    cx0, cx1 = 452.0, 628.0
    t_lo, t_hi = -dr["approach_mm"], lead + land + 0.4
    CX = lambda s: cx0 + (cx1 - cx0) * (s - t_lo) / (t_hi - t_lo)
    s_top = 0.5 * math.ceil(max(max(s["material"]["allowable"], s["strain"]) for s in snaps) * 100 / 0.5 + 0.2)
    sy0, sy1 = 74.0, 200.0
    SY = lambda e: sy1 - (sy1 - sy0) * 100 * e / s_top
    forces = [s for s in snaps if s["engagement"]["points"][1]["mating_force_n"] is not None]
    f_max = max([p["mating_force_n"] for s in forces for p in s["engagement"]["points"]] + [1.0])
    f_step = 5.0 if f_max > 8 else 2.0
    f_top = f_step * math.ceil(f_max * 1.1 / f_step)
    fy0, fy1 = 262.0, 336.0
    FY = lambda w: fy1 - (fy1 - fy0) * w / f_top
    for v in [k * 0.5 for k in range(int(round(s_top / 0.5)) + 1)]:
        body.append(f'<path class="gr" d="M{u(cx0)} {u(SY(v / 100))}H{u(cx1)}"/>')
        body.append(text(cx0 - 5, SY(v / 100) + 3.5, f"{v:g}", "ax w", "end"))
    for v in [k * f_step for k in range(int(round(f_top / f_step)) + 1)]:
        body.append(f'<path class="gr" d="M{u(cx0)} {u(FY(v))}H{u(cx1)}"/>')
        body.append(text(cx0 - 5, FY(v) + 3.5, f"{v:g}", "ax w", "end"))
    for s_ in range(math.ceil(t_lo), math.floor(t_hi) + 1):
        for y_ in (sy1, fy1):
            body.append(text(CX(s_), y_ + 14, f"{s_:g}".replace("-", "−"), "ax w", "middle"))
    body.append(text((cx0 + cx1) / 2, fy1 + 30, present["travel_axis"], "ax w", "middle"))
    for (y0_, y1_), key in (((sy0, sy1), "strain_axis"), ((fy0, fy1), "force_axis")):
        ym = (y0_ + y1_) / 2
        body.append(text(424, ym, present[key], "ax w", "middle", f' transform="rotate(-90 {u(424)} {u(ym)})"'))
    # each material's allowable, labelled at the right
    for i, s in enumerate(snaps):
        al = s["material"]["allowable"]
        body.append(f'<path class="al m{i}s" d="M{u(cx0)} {u(SY(al))}H{u(cx1)}"/>')
        body.append(text(cx1 + 5, SY(al) + 4, f"{pct(al)} {present['short'][s['name']]}", "lb w"))

    def trace(points: Sequence[Tuple[float, float, float]], cls: str, key: str) -> None:
        """A curve through chart points (time, x px, y px) drawn as the loop reaches them, and a dot that rides it;
        both fade out with the scene. Its still is the whole curve, with the dot at the top of the lead."""
        d = S.PathBuilder()
        d.polyline([(x * U, y * U) for _, x, y in points])
        run = [0.0]
        for (_, xa, ya), (_, xb, yb_) in zip(points, points[1:]):
            run.append(run[-1] + math.hypot(xb - xa, yb_ - ya))
        total = run[-1] or 1.0
        body.append(f'<path class="{cls} c{key}" pathLength="1" d="{d.d()}"/>')
        tl.add(f".c{key}", [(0, 1.0), *((tt, 1 - r / total) for (tt, _, _), r in zip(points, run)), (t_back, 0.0),
                            (t_back + 0.01, 1.0), (P, 1.0)], lambda o: f"stroke-dashoffset:{S.num(o, 4)}", "linear")
        css.append(f".c{key}{{stroke-dashoffset:0}}")
        at_top = next((x, y) for tt, x, y in points if tt == t["top"])
        dot = [(tt, (x, y)) for tt, x, y in points]
        key_d = f"d{key}"
        body.append(f'<circle class="{key_d}" cx="0" cy="0" r="{u(4.5)}" '
                    f'style="fill:var(--bg);stroke:var(--ink);stroke-width:{2 * U}px"/>')
        tr = lambda p: f"transform:translate({S.num(p[0] * U, 0)}px,{S.num(p[1] * U, 0)}px)"
        css.append(f".{key_d}{{{tr(at_top)}}}")
        tl.add(f".{key_d}", [(0, dot[0][1]), *dot, (t_back, dot[-1][1]), (t_back + 0.01, dot[0][1]), (P, dot[0][1])],
               tr, "linear")
        tl.opacity(f".c{key}", [(0, 1), (t["out"], 1), (t["out"] + f, 0), (t_back, 0), (t_back + 0.01, 1), (P, 1)])
        tl.opacity(f".{key_d}", [(0, 1), (t["out"], 1), (t["out"] + f, 0), (t_back + 0.05, 0),
                                 (t_back + 0.05 + f, 1), (P, 1)])

    eps = 0.04                                           # a vertical step in a curve takes this long
    st_pts = _distinct([(t["start"], CX(t_lo), SY(0))] + [(t[m], CX(p["travel_mm"]), SY(p["strain"]))
                                                          for p, m in zip(eng["points"], _moments(eng["points"]))], eps)
    trace(st_pts, "cv", "s")
    body.append(text(CX(lead + land / 2), SY(peak["strain"]) - 11, _fill(present["peak"], scene, present),
                     "lb b w pk", "middle"))
    fade_in(".pk", t["top"])
    for i, s in enumerate(snaps):
        if s["over_from_mm"] is not None:
            cls = f"x{i}"
            body.append(f'<circle class="{cls}" cx="{u(CX(s["over_from_mm"]))}" cy="{u(SY(s["material"]["allowable"]))}" '
                        f'r="{u(5)}" style="fill:var(--m{i});stroke:var(--bg);stroke-width:{1.5 * U}px"/>')
            fade_in(f".{cls}", t[f"over_{i}"])
    for i, s in enumerate(snaps):
        pts = s["engagement"]["points"]
        if pts[1]["mating_force_n"] is None:
            continue
        fp = _distinct([(t["start"], CX(t_lo), FY(0))] + [(t[m], CX(p["travel_mm"]), FY(p["mating_force_n"]))
                                                           for p, m in zip(pts, _moments(pts))], eps)
        trace(fp, f"cv m{i}s", f"f{i}")
        w = pts[1]["mating_force_n"]
        body.append(text(CX(lead), FY(w) - 7, f"{w:.1f} N", f"lb b w pk{i}", "middle"))
        body.append(text(cx1 + 5, FY(pts[-2]["mating_force_n"]) + 4, present["short"][s["name"]], "lb w"))
        fade_in(f".pk{i}", t["top"])

    # ---- the gauges: each material's root strain over its allowable, and its verdict
    gx0, gw = 20.0, 230.0
    g_top = max(1.5, math.ceil(max(ratio(s) for s in snaps) * 10 + 1) / 10)
    GX = lambda r: gx0 + gw * r / g_top
    rows_y = (258.0, 312.0)
    for i, (s, gy) in enumerate(zip(snaps, rows_y)):
        name = present["short"][s["name"]]
        r_pk = ratio(s)
        body.append(text(gx0, gy, _fill(present["gauge"], scene, present, name=s["material"]["material"]), "lb w"))
        body.append(f'<rect x="{u(gx0)}" y="{u(gy + 7)}" width="{u(gw)}" height="{u(14)}" rx="{u(3)}" '
                    f'style="fill:var(--track)"/>')
        under = min(1.0, r_pk)
        bar = f"g{i}"
        body.append(f'<rect class="{bar}" x="{u(gx0)}" y="{u(gy + 7)}" width="{u(GX(under) - gx0)}" height="{u(14)}" '
                    f'style="fill:var(--bar)"/>')
        css.append(f".{bar}{{transform-origin:{u(gx0)}px 0;transform:scaleX(1)}}")
        cross = t.get(f"over_{i}")
        if cross is None:                               # grows with the strain to its peak
            g_frames = [(0, 0), (t["contact"], 0), (t["top"], 1), (t["land"], 1), (t["released"], 0), (P, 0)]
        else:                                           # fills to the allowable, then the rest goes over it
            g_frames = [(0, 0), (t["contact"], 0), (cross, 1), (t["land"], 1), (t["released"], 0), (P, 0)]
        tl.add(f".{bar}", g_frames, lambda v: f"transform:scaleX({S.num(v, 4)})", "linear")
        if r_pk > 1:
            ov = f"o{i}"
            body.append(f'<rect class="{ov}" x="{u(GX(1))}" y="{u(gy + 7)}" width="{u(GX(r_pk) - GX(1))}" '
                        f'height="{u(14)}" style="fill:var(--accent)"/>')
            css.append(f".{ov}{{transform-origin:{u(GX(1))}px 0;transform:scaleX(1)}}")
            tl.add(f".{ov}", [(0, 0), (cross, 0), (t["top"], 1), (t["land"], 1), (t["released"], 0), (P, 0)],
                   lambda v: f"transform:scaleX({S.num(v, 4)})", "linear")
        body.append(f'<path d="M{u(GX(1))} {u(gy + 3)}v{u(22)}" style="stroke:var(--ink);stroke-width:{1.6 * U}px"/>')
        body.append(text(GX(1), gy + 37, "100 %", "ax w", "middle"))
        body.append(text(gx0 + gw + 8, gy + 18, _fill(present["gauge_value"], scene, present,
                                                     ratio=f"{100 * r_pk:.0f} %", allow=pct(s["material"]["allowable"])),
                         "lb w"))
        ok = bool(s["pass"])
        v = f"v{i}"
        word = "✓ PASS" if ok else "✗ FAIL"
        body.append(f'<g class="{v}"><rect x="{u(gx0 + gw + 104)}" y="{u(gy + 5)}" width="{u(58)}" height="{u(18)}" '
                    f'rx="{u(4)}" class="{"ok" if ok else "no"} w"/>'
                    + text(gx0 + gw + 133, gy + 18, word, "lb b w", "middle", ' style="fill:var(--bg)"')
                    + text(gx0, gy + 1, f"{name} {word[0]} {100 * r_pk:.0f} %", "nb n")
                    + "</g>")
        fade_in(f".{v}", cross if cross is not None else t["top"])

    # ---- under the gauges: when the failing one went over, and the push to mate, per material
    notes = []
    for i, s in enumerate(snaps):
        name = present["short"][s["name"]]
        if s["over_from_mm"] is not None:
            notes.append(_fill(present["crossing"], scene, present, short=name, travel=f"{s['over_from_mm']:.2f}",
                               lead_travel=f"{s['engagement']['lead_travel_mm']:.2f}"))
    for i, s in enumerate(snaps):
        name = present["short"][s["name"]]
        top = s["engagement"]["points"][1]
        if top["mating_force_n"] is None:
            notes.append(_fill(present["no_force"], scene, present, short=name))
        else:
            notes.append(_fill(present["force_line"], scene, present, short=name, force=f"{top['mating_force_n']:.1f} N",
                               mu=f"{s['engagement']['friction']:.3g}"))
    for j, line in enumerate(notes):
        body.append(text(20, 378 + 15 * j, line, "sm w"))
    # ---- the caption: what this is, and what it is not
    for j, line in enumerate(present["caption"]):
        body.append(text(20, H - 40 + 15 * j, _fill(line, scene, present), "sm w"))
    return S.document(W, H, _fill(present["label"], scene, present), _fill(present["description"], scene, present),
                      "".join(css) + tl.stylesheet(), body, S.Theme(light, dark))


def _moments(points: Sequence[Mapping[str, Any]]) -> List[str]:
    """The loop's moment (a key of :func:`times`) at each point of an engagement curve: contact and the top of the lead,
    the land's start (the top again) and end, and released."""
    out = []
    for p in points:
        if p["phase"] == "lead":
            out.append("top" if out else "contact")
        elif p["phase"] == "land":
            out.append("land" if out[-1] == "top" and out.count("top") > 1 else "top")
        else:
            out.append("released")
    return out


def _distinct(points: List[Tuple[float, float, float]], eps: float) -> List[Tuple[float, float, float]]:
    """Chart points with strictly rising times: a point at the same moment as the one before it (a vertical step)
    moves ``eps`` later."""
    out: List[Tuple[float, float, float]] = []
    for tt, x, y in points:
        if out and tt <= out[-1][0]:
            tt = out[-1][0] + eps
        out.append((tt, x, y))
    return out
