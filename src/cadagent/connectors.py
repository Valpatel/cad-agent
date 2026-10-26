"""Mating-connector envelopes: derive panel windows from the plug, then prove the plug fits.

A window sized from a receptacle's bounding box goes wrong in two ways:

* the bounding box includes through-hole pins, pegs and clinch tabs below the
  board, so the window ends up centred too low;
* the plug that mates with the receptacle is often larger than the receptacle
  face. For example, a screw-flange terminal plug is 15 mm tall on an 8.4 mm
  header, and a cable overmold is wider than its USB receptacle.

This module models the mated plug instead. It places the plug on the
receptacle's measured mating axis, derives the window from the part of the plug
that has to pass through the wall, and checks the result in 3D against the
real printed parts.

Panel frame
-----------
Each port is described in a panel frame:

* ``u`` runs along the wall;
* ``v`` points up the wall, away from the board;
* ``w`` points out of the enclosure along the mating axis.

Windows are ``[u0, v0, u1, v1]``. A receptacle's mating face lies at
``w = face_w``. Plug geometry is given relative to that face (``w = 0`` at the
face, positive outward).

Mate spec (plain dict, so it can live in ``parameters.json``)
-------------------------------------------------------------
::

    {"face": [u0, v0, u1, v1],      # receptacle mating-face outline, measured at the face (no pins)
     "face_w": 2.08,                # where that face sits along w
     "centre_on": "receptacle",     # "receptacle" | "plug" | "union" (default)
     "clearance": 0.5,              # per side, plug section to window edge
     "plugs": [{"family": "rj45", "cavity": [...], ...}],
     "basis": "where the numbers came from"}

Plug families (``PLUG_FAMILIES``) return a list of segments. Each segment is a
box ``{"u": [u0, u1], "v": [v0, v1], "w": [w0, w1]}`` (optionally ``"r"``, the
corner radius about the axis) or a cylinder
``{"axis": [u, v], "d": d, "w": [w0, w1]}``, and every segment carries a
``what`` label. Family defaults are typical catalogue values: each family
records its source, and a project overrides a default whenever it knows the
exact cable or plug.

Insertion sweep
---------------
A plug is pushed in from outside along ``w``. Any segment that starts inside
the wall's outer face (``w0 < wall_w1``) must pass through the wall on the way
in, so the window must clear that segment's whole section, not only the part
that sits in the wall once mated. Segments that start beyond the wall, such as
a boot or a cable, never pass through it. They are still checked in 3D
against everything outside, including neighbouring plugs.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require

Seg = Dict[str, Any]
_WHY = "the mating-connector check"
Window = List[float]

# ----------------------------------------------------------------------------- plug families

def rj45(cavity: Sequence[float], latch: str = "up", body_out: float = 8.0, latch_rise: float = 1.5,
         plug_width: float = 11.7, boot: Optional[Sequence[float]] = (14.0, 14.5), length: float = 40.0) -> List[Seg]:
    """8P8C (RJ45) plug in a jack.

    ``cavity`` is the jack's plug opening ``[u0, v0, u1, v1]`` measured at its
    face. ``latch`` is the opening's latch side, ``up`` or ``down``.

    * Plug body: 11.7 mm wide (FCC 68 / TIA-968 plug width 11.68 max; Panduit
      SP6X88 lists 11.7 W x 13.1 H overall).
    * Body outside the jack: about ``body_out`` mm.
    * The latch lever rises ``latch_rise`` above the opening outside the jack.
    * Boot: a typical snagless boot, ``(width, height)`` from the contact side,
      starting where the body ends. These are assumptions; measure the cables
      you will actually use.
    """
    u0, v0, u1, v1 = cavity
    uc = (u0 + u1) / 2
    down = latch == "down"
    lo, hi = (v0, v1 + latch_rise) if not down else (v0 - latch_rise, v1)
    segs = [{"u": [uc - plug_width / 2, uc + plug_width / 2], "v": [lo, hi], "w": [0.0, body_out],
             "what": "plug body + latch lever"}]
    if boot:
        bw, bh = boot
        base = v0 - 0.5 if not down else v1 + 0.5
        bv = [base, base + bh] if not down else [base - bh, base]
        segs.append({"u": [uc - bw / 2, uc + bw / 2], "v": bv, "w": [body_out, length], "what": "cable boot"})
    return segs

def trs35(axis: Sequence[float], overmold_d: float = 8.0, length: float = 35.0) -> List[Seg]:
    """3.5 mm phone plug (IEC 60130-8). The sleeve is hidden in the jack.

    The overmold shoulder stops at the jack nose, which is ``w = 0`` for this
    family. Overmold diameter is not standardised. Slim plugs are 5.5-6 mm
    across and common ones up to 8 mm; give the cable you will actually use.
    """
    return [{"axis": list(axis), "d": overmold_d, "w": [0.0, length], "what": f"plug overmold D{overmold_d:g}"}]

def terminal_plug_flanged(screws: Sequence[Sequence[float]], positions: int = 2, pitch: float = 5.08,
                          height: float = 15.0, body_out: float = 9.9, screw_above_bottom: float = 3.9,
                          flange: float = 4.7, end_margin: float = 5.69, tongue: float = 6.6,
                          lead_d: float = 4.5, length: float = 40.0, up: int = 1) -> List[Seg]:
    """Pluggable terminal-block plug with screw flanges (Phoenix MSTB 2,5/..-STF-5,08 family).

    ``screws`` gives the two flange-screw axes ``[[u, v], [u, v]]``, i.e. the
    threaded holes in the header flange.

    Phoenix dimensional drawing for 1777989:

    * 18.2 mm overall along the mating axis, of which 8.3 mm is the tongue
      inside the header, leaving ``body_out`` = 9.9 mm outside the header face;
    * 15 mm tall (``height``);
    * width = (n-1) * pitch + 5.69 + 2 * 4.7 flange = 20.17 mm for 2 positions;
    * flange-screw axis about 3.9 mm above the plug's contact side (scaled from
      the drawing).

    The wire-clamp screws are on the far side from the contacts (``up`` = +1
    puts them in +v), so wire the plug before you insert it. The leads leave
    straight out of the back of the body.
    """
    (ua, va), (ub, vb) = screws
    uc, vs = (ua + ub) / 2, (va + vb) / 2
    width = (positions - 1) * pitch + end_margin + 2 * flange
    bottom = vs - up * screw_above_bottom
    v = sorted([bottom, bottom + up * height])
    lv = sorted([bottom, bottom + up * tongue])
    half = (positions - 1) * pitch / 2 + lead_d / 2
    return [{"u": [uc - width / 2, uc + width / 2], "v": v, "w": [0.0, body_out], "what": "plug body with flanges"},
            {"u": [uc - half, uc + half], "v": lv, "w": [body_out, length], "what": f"{positions} leads D{lead_d:g}"}]

def overmold(centre: Sequence[float], width: float, height: float, length: float = 35.0, start: float = 0.0,
             r: float = 0.0) -> List[Seg]:
    """Rectangular cable overmold (USB, HDMI, DisplayPort ...), centred on the mating axis.

    The overmold reaches the receptacle face (``start`` = 0) unless the plug
    has a bare metal shell first. Typical sizes: USB-A 16 x 8, USB-C 12.5 x 7.5
    and HDMI 21 x 11 mm, with ``r`` the corner radius about the axis. These are
    assumptions; measure the cables you use.
    """
    u, v = centre
    return [{"u": [u - width / 2, u + width / 2], "v": [v - height / 2, v + height / 2], "w": [start, length],
             "r": r, "what": f"overmold {width:g} x {height:g} R{r:g}"}]

def face_plug(outline: Sequence[float], length: float = 30.0) -> List[Seg]:
    """The mated plug is already in the board model (its face is the receptacle face).

    The wires leave straight out within the face outline.
    """
    u0, v0, u1, v1 = outline
    return [{"u": [u0, u1], "v": [v0, v1], "w": [0.0, length], "what": "modelled plug + leads"}]

def box_plug(u: Sequence[float], v: Sequence[float], w: Sequence[float], what: str = "custom envelope") -> List[Seg]:
    """Any other envelope, given as one box."""
    return [{"u": list(u), "v": list(v), "w": list(w), "what": what}]

PLUG_FAMILIES: Dict[str, Callable[..., List[Seg]]] = {
    "rj45": rj45, "trs35": trs35, "terminal_plug_flanged": terminal_plug_flanged,
    "overmold": overmold, "face_plug": face_plug, "box": box_plug,
}

def plug_segments(plug: Mapping[str, Any]) -> List[Seg]:
    """Segments of one plug spec ``{"family": name, **params}`` (keys starting with '_' or 'basis' are notes)."""
    kw = {k: v for k, v in plug.items() if k != "family" and k != "basis" and not k.startswith("_")}
    try:
        fn = PLUG_FAMILIES[plug["family"]]
    except KeyError:
        raise ValueError(f"unknown plug family {plug.get('family')!r}; known: {sorted(PLUG_FAMILIES)}") from None
    return fn(**kw)

def mate_segments(mate: Mapping[str, Any]) -> List[Seg]:
    """All plug segments of a port, with ``w`` shifted into the panel frame (face at ``face_w``)."""
    fw = mate.get("face_w", 0.0)
    out = []
    for i, plug in enumerate(mate["plugs"]):
        for s in plug_segments(plug):
            s = dict(s, w=[s["w"][0] + fw, s["w"][1] + fw], plug=i)
            out.append(s)
    return out

# ----------------------------------------------------------------------------- windows

def seg_rect(s: Seg) -> Window:
    """Section of a segment across the mating axis, ``[u0, v0, u1, v1]``."""
    if "axis" in s:
        (u, v), r = s["axis"], s["d"] / 2
        return [u - r, v - r, u + r, v + r]
    return [s["u"][0], s["v"][0], s["u"][1], s["v"][1]]

def _union(rects: Iterable[Sequence[float]]) -> Window:
    rs = list(rects)
    return [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]

def passing_segments(mate: Mapping[str, Any], wall_w: Sequence[float]) -> List[Seg]:
    """Segments that pass through the wall on insertion: they start inside its outer face."""
    return [s for s in mate_segments(mate) if s["w"][0] < wall_w[1]]

def window(mate: Mapping[str, Any], wall_w: Sequence[float], clearance: Optional[float] = None) -> Window:
    """Panel window for a port, centred as ``mate['centre_on']`` asks.

    The window is the union of the passing plug sections and the receptacle
    face (so face LEDs and the shell stay visible), both grown by the
    clearance. ``centre_on``:

    * ``"receptacle"``: grow symmetrically about the receptacle face centre;
    * ``"plug"``: grow symmetrically about the passing-plug centre;
    * ``"union"``: no recentring.
    """
    c = mate.get("clearance", 0.5) if clearance is None else clearance
    plug = _union(seg_rect(s) for s in passing_segments(mate, wall_w))
    grown = [plug[0] - c, plug[1] - c, plug[2] + c, plug[3] + c]
    face = mate.get("face")
    if face and mate.get("include_face", True):
        win = _union([grown, [face[0] - c, face[1] - c, face[2] + c, face[3] + c]])
    else:
        win = grown
    mode = mate.get("centre_on", "union")
    if mode in ("receptacle", "plug"):
        ref = face if mode == "receptacle" else plug
        if ref is None:
            raise ValueError("centre_on='receptacle' needs a 'face'")
        cu, cv = (ref[0] + ref[2]) / 2, (ref[1] + ref[3]) / 2
        hu = max(cu - win[0], win[2] - cu)
        hv = max(cv - win[1], win[3] - cv)
        win = [cu - hu, cv - hv, cu + hu, cv + hv]
    return [round(x, 3) for x in win]

def window_margins(mate: Mapping[str, Any], win: Sequence[float], wall_w: Sequence[float]) -> Dict[str, Any]:
    """Per-side margin from the passing plug sections to the window, plus centring offsets.

    The margins are in 2D, ignoring corner radii; the 3D check covers those.
    """
    rect = _union(seg_rect(s) for s in passing_segments(mate, wall_w))
    m = {"left": rect[0] - win[0], "bottom": rect[1] - win[1], "right": win[2] - rect[2], "top": win[3] - rect[3]}
    wc = ((win[0] + win[2]) / 2, (win[1] + win[3]) / 2)
    out = {"plug_section": [round(x, 3) for x in rect], "margins_mm": {k: round(v, 3) for k, v in m.items()},
           "min_margin_mm": round(min(m.values()), 3),
           "window_centre_minus_plug_centre_mm": [round(wc[0] - (rect[0] + rect[2]) / 2, 3), round(wc[1] - (rect[1] + rect[3]) / 2, 3)]}
    face = mate.get("face")
    if face:
        out["window_centre_minus_face_centre_mm"] = [round(wc[0] - (face[0] + face[2]) / 2, 3), round(wc[1] - (face[1] + face[3]) / 2, 3)]
    return out

# ----------------------------------------------------------------------------- 3D

class PanelFrame:
    """Maps panel coordinates (u, v, w) to world coordinates.

    ``origin`` is the world point at u = v = w = 0; ``u``, ``v`` and ``w`` are
    orthonormal world directions. A left-handed frame (for example a rear
    wall seen with u along +x) is handled by mirroring u internally.
    """

    def __init__(self, origin: Sequence[float], u: Sequence[float], v: Sequence[float], w: Sequence[float]):
        self.origin, self.u, self.v, self.w = (tuple(float(c) for c in t) for t in (origin, u, v, w))
        cx = (self.v[1] * self.w[2] - self.v[2] * self.w[1], self.v[2] * self.w[0] - self.v[0] * self.w[2],
              self.v[0] * self.w[1] - self.v[1] * self.w[0])
        self.mirror = sum(a * b for a, b in zip(self.u, cx)) < 0

    def point(self, u: float, v: float, w: float) -> Tuple[float, float, float]:
        o = self.origin
        return tuple(o[i] + u * self.u[i] + v * self.v[i] + w * self.w[i] for i in range(3))

    def _trsf(self):
        gp = require("OCP.gp", _WHY)
        uu = tuple(-c for c in self.u) if self.mirror else self.u
        t = gp.gp_Trsf()
        o = self.origin
        t.SetValues(uu[0], self.v[0], self.w[0], o[0], uu[1], self.v[1], self.w[1], o[1], uu[2], self.v[2], self.w[2], o[2])
        return t

    def solid(self, s: Seg, grow: float = 0.0, w_range: Optional[Sequence[float]] = None):
        """World-space solid for one segment, grown by ``grow`` across the axis, optionally with a new w range."""
        cq = require("cadquery", _WHY)
        w0, w1 = w_range or s["w"]
        sgn = -1 if self.mirror else 1
        if "axis" in s:
            u, v = s["axis"]
            local = cq.Solid.makeCylinder(s["d"] / 2 + grow, w1 - w0, cq.Vector(sgn * u, v, w0), cq.Vector(0, 0, 1))
        else:
            u0, u1 = sorted((sgn * s["u"][0], sgn * s["u"][1]))
            v0, v1 = s["v"]
            local = cq.Solid.makeBox(u1 - u0 + 2 * grow, v1 - v0 + 2 * grow, w1 - w0,
                                     cq.Vector(u0 - grow, v0 - grow, w0))
            # Growing by a clearance is an offset: corners round by the clearance too.
            r = s.get("r", 0.0) + grow
            if r > 1e-6:
                local = cq.Workplane().add(local).edges("|Z").fillet(min(r, (u1 - u0) / 2 + grow - 1e-3,
                                                                         (v1 - v0) / 2 + grow - 1e-3)).val()
        brep = require("OCP.BRepBuilderAPI", _WHY)
        return cq.Shape.cast(brep.BRepBuilderAPI_Transform(local.wrapped, self._trsf(), True).Shape())

def envelope(mate: Mapping[str, Any], frame: PanelFrame, grow: float = 0.0, sweep: bool = True):
    """Mated plug envelope as one compound.

    With ``sweep`` set, each segment is extended out to the plug's far end, so
    the compound is the volume the plug passes through on the way in.
    """
    cq = require("cadquery", _WHY)
    segs = mate_segments(mate)
    far = max(s["w"][1] for s in segs)
    return cq.Compound.makeCompound([frame.solid(s, grow, (s["w"][0], far) if sweep else None) for s in segs])

def _volume(a, b) -> float:
    try:
        return float(a.intersect(b).Volume())
    except Exception:  # OCC boolean failure: report as unknown, never as clear
        return float("nan")

def check_ports(ports: Mapping[str, Mapping[str, Any]], frames: Mapping[str, PanelFrame],
                obstacles: Mapping[str, Any], wall_w: Mapping[str, Sequence[float]],
                windows: Optional[Mapping[str, Sequence[float]]] = None) -> Dict[str, Any]:
    """Prove every mated plug fits.

    ``ports`` maps a port name to its mate spec, and ``frames`` / ``wall_w`` map
    the same name to its panel frame and wall span. ``obstacles`` maps a name to
    a cadquery shape (printed parts in assembly position). ``windows`` holds the
    windows actually cut; it defaults to ``window(mate, wall)``.

    For each port the check reports:

    * the insertion-sweep interference with every obstacle (must be 0 mm³);
    * the interference of the sweep grown by the clearance (0 means the
      clearance is met all round, corner radii included);
    * the 2D window margins and centring offsets.

    Plug-to-plug interference between ports is reported too.
    """
    rows: Dict[str, Any] = {}
    env: Dict[str, Any] = {}
    for name, mate in ports.items():
        fr, wall = frames[name], wall_w[name]
        win = list(windows[name]) if windows and name in windows else window(mate, wall)
        c = mate.get("clearance", 0.5)
        e0 = envelope(mate, fr)
        eg = envelope(mate, fr, grow=max(c - 0.01, 0.0))
        env[name] = envelope(mate, fr, sweep=False)
        hits = {k: round(_volume(e0, s), 3) for k, s in obstacles.items()}
        near = {k: round(_volume(eg, s), 3) for k, s in obstacles.items()}
        plugs = [dict(p) for p in mate["plugs"]]
        row = {"window": win, "clearance_mm": c, "plugs": plugs, "basis": mate.get("basis", ""),
               "sweep_interference_mm3": hits, "clearance_interference_mm3": near,
               **window_margins(mate, win, wall)}
        row["pass"] = all(v == 0 for v in hits.values()) and all(v == 0 for v in near.values()) \
            and row["min_margin_mm"] >= c - 1e-3
        rows[name] = row
    names = list(env)
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            v = round(_volume(env[a], env[b]), 3)
            if v != 0:
                pairs.append({"ports": [a, b], "intersection_mm3": v})
    return {"pass": all(r["pass"] for r in rows.values()) and not pairs, "ports": rows, "plug_to_plug": pairs}

# ----------------------------------------------------------------------------- evidence

def draw_ports(ax, ports: Mapping[str, Mapping[str, Any]], windows: Mapping[str, Sequence[float]],
               wall_w: Mapping[str, Sequence[float]], radius: Optional[Mapping[str, float]] = None,
               to_xy: Optional[Callable[[float, float], Tuple[float, float]]] = None) -> None:
    """Draw windows, receptacle faces and passing plug sections on a matplotlib axis.

    This is the evidence image for "is it centred, does it clear". The plot
    shows the window (black), the receptacle face (grey), the passing plug
    sections (orange) and the mating axes (+). ``to_xy`` maps (u, v) to the
    plot, e.g. to mirror a rear wall seen from outside.
    """
    patches = require("matplotlib.patches", _WHY)
    f = to_xy or (lambda u, v: (u, v))

    def rect(box, **kw):
        (x0, y0), (x1, y1) = f(box[0], box[1]), f(box[2], box[3])
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        rr = kw.pop("r", 0.0)
        rr = min(rr, (x1 - x0) / 2, (y1 - y0) / 2)
        ax.add_patch(patches.FancyBboxPatch((x0 + rr, y0 + rr), x1 - x0 - 2 * rr, y1 - y0 - 2 * rr,
                                            boxstyle=f"round,pad={rr}", **kw))

    for name, mate in ports.items():
        win = windows[name]
        rect(win, r=(radius or {}).get(name, 0.0), fill=False, edgecolor="black", lw=1.2, zorder=3)
        if mate.get("face"):
            rect(mate["face"], fill=True, facecolor="#d9d9d9", edgecolor="#7f7f7f", lw=.6, zorder=1)
        for s in passing_segments(mate, wall_w[name]):
            if "axis" in s:
                x, y = f(*s["axis"])
                ax.add_patch(patches.Circle((x, y), s["d"] / 2, fill=True, facecolor="#f4a259", alpha=.45,
                                            edgecolor="#c8641e", lw=.8, zorder=2))
                ax.plot([x], [y], "+", color="#c8641e", zorder=4)
            else:
                rect(seg_rect(s), r=s.get("r", 0.0), fill=True, facecolor="#f4a259", alpha=.45, edgecolor="#c8641e", lw=.8, zorder=2)
        x, y = f((win[0] + win[2]) / 2, win[3])
        ax.annotate(name, (x, y), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=7)
