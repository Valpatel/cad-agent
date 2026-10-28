"""Fastener and stack gate: every declared screw against the solids it passes through, and its tool's reach.

For each fastener instance (a dossier ``fastener()`` axis: origin on the head seat, direction the way the
screw advances) the gate reads the model along the screw's own axis frame (``t`` = distance from the
seat along the advance direction; the head is at ``t < 0``) and checks:

========== =================================================================================================
check      fails when
========== =================================================================================================
seat       the head does not bear on the first clamped part all round: a gap over ``seat_tol_mm``, the face
           above the seat (the head buried), another part under the head, nothing under one side
           (overhang off an edge or into a pocket), or material inside the head's volume (a pocket wall)
stack      the clamped parts (``stack``, default ``[clamps]``) are not met in order under the head, an
           undeclared part sits between them, or a gap over ``gap_tol_mm`` opens between two of them or under
           the last one (the clamp pulls against nothing)
holes      a clamped part has material on the axis (no hole) or a hole under ``d + hole_clearance_mm``
           (diametral), the head is no wider than the hole (it pulls through), the receiver has material
           on the axis where the thread starts (no pilot or tap hole), or the screw's solid overlaps a
           clamped part or the receiver above its thread
engagement the thread in the receiver (``into``: an insert, nut or tapped part) engages less than
           ``min_engagement_mm`` (declared; else ``min_engagement_d`` x d), or the screw does not reach it
tip        the tip runs into a solid (any part, the receiver's own bottom included), stops within
           ``tip_clearance_mm`` of one (bottoming), or the screw's solid overlaps any part other than its
           stack and the receiver's thread
length     the placed solid's length differs from the record's ``length_mm``, the length is outside the
           window the stack allows (thread start + minimum engagement .. the room before the next solid),
           or the record's ``thread_start_mm`` differs from the model; an uncommon stock length or a
           ``thread_depth_mm`` that differs from the model warns
tool       the declared tool envelope (stepped cylinders from the head along the axis, away from the work,
           and an optional swing disc for an L key) overlaps a part present at the assembly step that
           installs the fastener; no tool declared or no envelope for it fails; a fastener no step
           installs is checked against every part and warns
========== =================================================================================================

How it measures (no number the fastener was declared from is trusted where the model can answer):

* **lines through the solids**: ``IntCurvesFace_ShapeIntersector`` crossings along a line, the spans
  between them classified with ``BRepClass3d_SolidClassifier``. The *annulus*: ``lines`` (8) lines parallel
  to the axis halfway between the shank and the head rim, where the head and the clamped parts bear;
  the *axis* line; the *thread probe*: 4 lines at 0.92 d/2 (then 1.08 d/2 if the receiver is not met),
  where a receiver modelled at its minor or nominal diameter has material; *radial rays* in each clamped
  part for its hole radius;
* **the screw's solid** when the build placed one (catalogue STEP or ``cadagent.fasteners`` envelope):
  its length and head from its box in the axis frame, its overlaps from the relation table (cached),
  each overlap's extent along the axis from the common solid. Without a solid the head is ``head_d_mm``
  x ``head_h_mm`` when declared, else 1.6 d x 1.0 d (a socket head), and the length is the record's;
* **the tool**: the envelope solid against each part present at the install step (``relate``: shared
  volume above ``overlap_mm3`` blocks; an undecided pair blocks too).

The kernel-free core is ``evaluate(spec, measurement)``: it turns a measurement (plain data) into the
checks and the lesson-04 table row, and is what core CI tests. ``measure`` and ``fastener_gate`` need OCP.

Limits, stated in every verdict: the model is checked, not the hardware. Threads are envelopes: engagement
is the axial overlap with the receiver's modelled thread region, not a pull-out rating. The lines sample
the annulus at ``lines`` angles and the hole at 8 angles and three depths per clamped part; a feature between
the samples is missed. A tool is a declared envelope, swept straight along the axis from the head: no
angled approach, no hand room beyond the envelope. Parts no assembly step fits are treated as present at
every step (conservative).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require
from cadagent.gates.verdict import Check, verdict, write_verdict

GATE = "fasteners"
Vec = Tuple[float, float, float]
CHECKS = ("seat", "stack", "holes", "engagement", "tip", "length", "tool")

ASSUMPTIONS = [
    "Each fastener is read along its own axis from the declared seat (dossier fastener() axes); the model is "
    "checked, not the hardware: no tolerance stack, no print shrink, no torque or pull-out rating.",
    "Threads are envelopes: engagement is the axial overlap of the screw with the receiver's modelled thread "
    "region (material within the nominal diameter, probed at 0.92 d/2, else 1.08 d/2), not proof of strength.",
    "The head bears where 8 lines parallel to the axis, halfway between shank and head rim, first meet the "
    "clamped part; holes are measured by radial rays at 8 angles and three depths per clamped part. Features "
    "between the samples are missed.",
    "Without a placed screw solid the head is the declared head_d_mm x head_h_mm, else 1.6 d x 1.0 d "
    "(socket head), and the length is the record's length_mm.",
    "The tool is the declared envelope (stepped cylinders and an optional swing disc), swept straight along "
    "the axis from the head top; it is checked against the parts present at the assembly step that installs "
    "the fastener (parts no step fits count as present).",
    "Minimum engagement is the declared min_engagement_mm, else min_engagement_d x d; stock lengths are a "
    "default list of common metric and inch lengths unless the project gives its own.",
]

# ISO 261 coarse pitches, to state engagement in threads when the pitch is not declared
COARSE_PITCH_MM = {1.0: 0.25, 1.2: 0.25, 1.4: 0.3, 1.6: 0.35, 2.0: 0.4, 2.5: 0.45, 3.0: 0.5, 3.5: 0.6, 4.0: 0.7,
                   5.0: 0.8, 6.0: 1.0, 8.0: 1.25, 10.0: 1.5, 12.0: 1.75, 14.0: 2.0, 16.0: 2.0, 20.0: 2.5}
# common catalogue lengths: metric (ISO 4762 / 7380 / 10642 series plus the odd sizes suppliers stock) and inch
METRIC_STOCK_MM = (2, 2.5, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 30, 35, 40, 45, 50, 55, 60, 65,
                   70, 75, 80, 90, 100, 110, 120, 130, 140, 150, 160, 180, 200)
INCH_STOCK_MM = tuple(sorted({round(n / 16 * 25.4, 4) for n in range(2, 17)} | {round(n / 8 * 25.4, 4)
                      for n in range(8, 33)} | {round(n / 4 * 25.4, 4) for n in range(16, 25)}))
DEFAULT_STOCK_MM = tuple(sorted(set(float(x) for x in METRIC_STOCK_MM) | set(INCH_STOCK_MM)))


@dataclass(frozen=True)
class FastenerOptions:
    """Gate-wide tolerances (mm). Per-fastener ``hole_clearance_mm`` / ``tip_clearance_mm`` override them."""
    seat_tol_mm: float = 0.05          # head face to the clamped face
    gap_tol_mm: float = 0.05           # between two parts of the stack, and under the last one
    hole_clearance_mm: float = 0.1     # diametral: a clearance hole must be at least d + this
    tip_clearance_mm: float = 0.5      # the tip must stop at least this short of the next solid on the axis
    stack_tol_mm: float = 0.05         # the record's thread_start against the model
    length_tol_mm: float = 0.05        # the placed solid's length against the record's length_mm
    min_engagement_d: float = 0.8      # minimum engagement when none is declared, as a multiple of d
    look_ahead_mm: float = 10.0        # how far past the tip the axis is read
    lines: int = 8                     # annulus lines
    stock_lengths_mm: Optional[Tuple[float, ...]] = None   # None: DEFAULT_STOCK_MM

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if f.name != "stock_lengths_mm" and (v is None or v < 0):
                raise ValueError(f"FastenerOptions.{f.name} must be non-negative, got {v!r}")
        if self.lines < 3:
            raise ValueError("FastenerOptions.lines must be at least 3")

    @property
    def stock(self) -> Tuple[float, ...]:
        return tuple(self.stock_lengths_mm) if self.stock_lengths_mm else DEFAULT_STOCK_MM


SPEC_OPTIONAL = ("key", "via", "tool", "length_mm", "diameter_mm", "thread_start_mm", "thread_depth_mm",
                 "min_engagement_mm", "pitch_mm", "head", "head_d_mm", "head_h_mm", "hole_clearance_mm",
                 "tip_clearance_mm")


@dataclass
class FastenerSpec:
    """One fastener declaration (``n`` identical screws, one per axis), as the dossier registry records it plus
    the gate-only options. ``stack`` lists the clamped parts head side first (default ``[clamps]``); ``head``
    is ``"flat"`` for a countersunk head (its seat is a cone: the annulus seat test is replaced by contact);
    ``instances`` are the assembly keys of the placed solids, one per axis (empty: no solid)."""
    name: str
    clamps: str
    into: str
    axes: List[Tuple[Vec, Vec]] = field(default_factory=list)
    key: str = ""
    via: str = ""
    tool: str = ""
    length_mm: Optional[float] = None
    diameter_mm: Optional[float] = None
    thread_start_mm: Optional[float] = None
    thread_depth_mm: Optional[float] = None
    min_engagement_mm: Optional[float] = None
    pitch_mm: Optional[float] = None
    stack: List[str] = field(default_factory=list)
    head: str = ""
    head_d_mm: Optional[float] = None
    head_h_mm: Optional[float] = None
    hole_clearance_mm: Optional[float] = None
    tip_clearance_mm: Optional[float] = None
    instances: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.name or not self.clamps or not self.into:
            raise ValueError(f"fastener {self.name!r}: name, clamps and into are required")
        self.axes = [(_vec(o), _unit(d)) for o, d in self.axes]
        self.stack = list(self.stack) or [self.clamps]
        if self.stack[0] != self.clamps:
            raise ValueError(f"fastener {self.name!r}: stack must start with clamps ({self.clamps!r}), "
                             f"got {self.stack!r}")
        if self.into in self.stack:
            raise ValueError(f"fastener {self.name!r}: into ({self.into!r}) cannot also be in the stack")
        if self.head not in ("", "flat"):
            raise ValueError(f"fastener {self.name!r}: head must be '' or 'flat', got {self.head!r}")

    def instance_key(self, i: int) -> str:
        """The instance key of axis ``i``: ``instances[i]`` when given, else ``name`` or ``name#i``."""
        if i < len(self.instances):
            return self.instances[i]
        return self.name if len(self.axes) == 1 else f"{self.name}#{i}"

    @property
    def pitch(self) -> Optional[float]:
        if self.pitch_mm:
            return float(self.pitch_mm)
        return COARSE_PITCH_MM.get(round(float(self.diameter_mm), 3)) if self.diameter_mm else None

    @classmethod
    def coerce(cls, value: Any, name: Optional[str] = None) -> "FastenerSpec":
        if isinstance(value, FastenerSpec):
            return value
        m = dict(value)
        if name is not None:
            m.setdefault("name", name)
        if "axes" not in m and "instances" in m and m["instances"] and isinstance(m["instances"][0], Mapping):
            insts = m.pop("instances")
            m["axes"] = [(i["origin"], i["direction"]) for i in insts]
            m["instances"] = [i["key"] for i in insts if "key" in i and "sha256" in i]
            if len(m["instances"]) != len(m["axes"]):
                m["instances"] = []
        m["axes"] = [(a.origin, a.direction) if hasattr(a, "origin") else tuple(a) for a in m.get("axes") or []]
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in m.items() if k in known})


def _vec(v: Any) -> Vec:
    out = tuple(float(c) for c in v)
    if len(out) != 3:
        raise ValueError(f"expected three numbers, got {v!r}")
    return out  # type: ignore[return-value]


def _unit(v: Any) -> Vec:
    x, y, z = _vec(v)
    n = math.sqrt(x * x + y * y + z * z)
    if n == 0:
        raise ValueError("axis direction is the zero vector")
    return (x / n, y / n, z / n)


def _frame(u: Vec) -> Tuple[Vec, Vec]:
    """Two unit vectors perpendicular to ``u`` and to each other (the same helper rule as the registry)."""
    helper = (1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 1.0, 0.0)
    dot = sum(a * b for a, b in zip(helper, u))
    v = _unit(tuple(h - dot * c for h, c in zip(helper, u)))
    w = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return v, w


def _at(p: Vec, u: Vec, t: float, v: Vec = (0, 0, 0), w: Vec = (0, 0, 0), r: float = 0.0, ang: float = 0.0) -> Vec:
    c, s = math.cos(ang), math.sin(ang)
    return tuple(p[i] + t * u[i] + r * (c * v[i] + s * w[i]) for i in range(3))  # type: ignore[return-value]


def owner(key: str) -> str:
    """The part or fastener name of an instance key (``ball#3`` -> ``ball``)."""
    head, sep, tail = key.rpartition("#")
    return head if sep and tail.isdigit() else key


def _keys(names: Iterable[str], name: str) -> List[str]:
    return [k for k in names if k == name or owner(k) == name]


def _r(x: Optional[float], digits: int = 4) -> Optional[float]:
    if x is None:
        return None
    v = round(float(x), digits)
    return 0.0 if v == 0 else v


# ------------------------------------------------------------------------------------------ declarations

def fasteners_from_build(result: Any, dossier: Any = None, extra: Optional[Mapping[str, Any]] = None,
                         ) -> Dict[str, FastenerSpec]:
    """The fastener specs of a dossier build (``BuildResult`` live or from ``load_geometry``): the record's
    ``fasteners`` (key, clamps, into, via, tool, stack numbers, axes and placed solids), with per-fastener
    gate options from the dossier's ``gates: fasteners:`` and ``extra["fasteners"]``, each a mapping keyed by
    fastener name or catalogue key (``stack``, ``head``, ``head_d_mm``, ``head_h_mm``, ``pitch_mm``,
    ``hole_clearance_mm``, ``tip_clearance_mm``, or any record field to override). The name wins over the key."""
    geo = getattr(result, "geometry", None) or (result if isinstance(result, Mapping) else {})
    opts: Dict[str, Dict[str, Any]] = {}
    if dossier is not None:
        for k, v in ((getattr(dossier.gates, "extra", None) or {}).get("fasteners") or {}).items():
            opts.setdefault(k, {}).update(v)
    for k, v in ((extra or {}).get("fasteners") or {}).items():
        opts.setdefault(k, {}).update(v)
    out: Dict[str, FastenerSpec] = {}
    for name, f in sorted((geo.get("fasteners") or {}).items()):
        m = {k: f.get(k) for k in ("key", "clamps", "into", "via", "tool", "length_mm", "diameter_mm",
                                   "thread_start_mm", "thread_depth_mm", "min_engagement_mm") if f.get(k) is not None}
        m["instances"] = list(f.get("instances") or [])
        m.update(opts.get(str(f.get("key")), {}))
        m.update(opts.get(name, {}))
        out[name] = FastenerSpec.coerce(m, name)
    return out


def tools_from(dossier: Any = None, extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Tool envelopes by name, from the dossier's ``gates: tools:`` and ``extra["tools"]`` (extra wins)."""
    out: Dict[str, Any] = {}
    if dossier is not None:
        out.update((getattr(dossier.gates, "extra", None) or {}).get("tools") or {})
    out.update((extra or {}).get("tools") or {})
    return out


def tool_envelope(decl: Any) -> Dict[str, Any]:
    """Normalise a tool declaration to ``{"segments": [{"d", "length"}], "start", "offset_mm", "swing"}``.

    Accepted: ``{"envelope_d": 6, "length": 60}`` (or ``d``/``diameter``) for one cylinder; ``{"segments":
    [{"d": 3, "length": 25}, {"d": 28, "length": 100}]}`` for a driver's shaft then handle, nearest the head
    first; ``start``: ``"head"`` (default: from the head top, a key or bit in the socket) or ``"seat"`` (a socket
    or nut driver over the head); ``offset_mm`` moves the start away from the work; ``swing``: ``{"radius",
    "at", "thickness", "min_deg"}`` an L key's arm turning at ``at`` from the start, which needs a free arc of
    ``min_deg`` (default 60, a sixth of a turn) in 12 sectors."""
    if not isinstance(decl, Mapping):
        raise ValueError(f"a tool envelope is a mapping, got {decl!r}")
    if decl.get("segments"):
        segs = [{"d": float(s.get("d", s.get("diameter", s.get("envelope_d")))), "length": float(s["length"])}
                for s in decl["segments"]]
    else:
        d = decl.get("envelope_d", decl.get("d", decl.get("diameter")))
        if d is None or decl.get("length") is None:
            raise ValueError(f"a tool envelope needs envelope_d and length, or segments: {dict(decl)!r}")
        segs = [{"d": float(d), "length": float(decl["length"])}]
    if any(s["d"] <= 0 or s["length"] <= 0 for s in segs):
        raise ValueError(f"tool segments need positive d and length: {segs!r}")
    start = str(decl.get("start", "head"))
    if start not in ("head", "seat"):
        raise ValueError(f"tool start must be 'head' or 'seat', got {start!r}")
    swing = decl.get("swing")
    if swing is not None:
        swing = {"radius": float(swing["radius"]), "at": float(swing.get("at", 0.0)),
                 "thickness": float(swing.get("thickness", 3.0)), "min_deg": float(swing.get("min_deg", 60.0)),
                 "sectors": int(swing.get("sectors", 12))}
        if swing["radius"] <= 0 or swing["thickness"] <= 0 or not 0 < swing["min_deg"] <= 360 or swing["sectors"] < 4:
            raise ValueError(f"bad tool swing {swing!r}")
    return {"segments": segs, "start": start, "offset_mm": float(decl.get("offset_mm", 0.0)), "swing": swing}


def _steps(steps: Iterable[Any]) -> List[Dict[str, Any]]:
    out = []
    for s in steps or ():
        g = (lambda k, d=None: s.get(k, d)) if isinstance(s, Mapping) else (lambda k, d=None: getattr(s, k, d))
        onto = g("onto") or []
        out.append({"order": int(g("order")), "fit": str(g("fit")), "onto": [onto] if isinstance(onto, str) else
                    list(onto), "fasteners": list(g("fasteners") or []), "tool": str(g("tool") or "")})
    return sorted(out, key=lambda s: s["order"])


def install_step(spec: FastenerSpec, steps: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The first step listing the fastener by name; else the first listing its catalogue key that fits or sits
    on what it clamps or threads into; else the first listing its key at all. None when no step lists it."""
    steps = _steps(steps)
    for s in steps:
        if spec.name in s["fasteners"]:
            return s
    if spec.key:
        keyed = [s for s in steps if spec.key in s["fasteners"]]
        parties = {spec.clamps, spec.into, *spec.stack}
        for s in keyed:
            if s["fit"] in parties or parties & set(s["onto"]):
                return s
        if keyed:
            return keyed[0]
    return None


def present_at(step: Optional[Mapping[str, Any]], steps: Sequence[Mapping[str, Any]], names: Iterable[str],
               specs: Mapping[str, FastenerSpec], kinds: Optional[Mapping[str, str]] = None) -> List[str]:
    """Assembly keys present when ``step`` is done: parts fitted at it or before, parts no step fits, and the
    solids of fasteners installed at it or before (or by no step). ``step`` None: everything."""
    names = list(names)
    if step is None:
        return names
    steps = _steps(steps)
    fitted = {s["fit"]: s["order"] for s in reversed(steps)}
    fastener_of = {}
    for spec in specs.values():
        st = install_step(spec, steps)
        for i in range(len(spec.axes)):
            fastener_of[spec.instance_key(i)] = st["order"] if st else None
    out = []
    for k in names:
        if (kinds or {}).get(k) == "fastener" or k in fastener_of or owner(k) in specs:
            order = fastener_of.get(k)
            if order is None or order <= step["order"]:
                out.append(k)
            continue
        order = fitted.get(k, fitted.get(owner(k)))
        if order is None or order <= step["order"]:
            out.append(k)
    return out


# ------------------------------------------------------------------------------------------ kernel-free core

def _merge(ivs: Iterable[Sequence[float]], gap: float = 1e-4) -> List[List[float]]:
    out: List[List[float]] = []
    for a, b in sorted([float(x), float(y)] for x, y in ivs):
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _intersect(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo + 1e-6:
            out.append([lo, hi])
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def _stock_fit(length: float, stock: Sequence[float]) -> bool:
    return any(abs(length - s) <= 0.01 for s in stock)


def _status(probs: List[str], warns: List[str]) -> str:
    return "fail" if probs else ("warn" if warns else "pass")


def evaluate(spec: FastenerSpec, measurement: Mapping[str, Any], options: FastenerOptions = FastenerOptions(),
             ) -> Tuple[List[Check], Dict[str, Any]]:
    """The checks and the lesson-04 table row for one fastener instance from its measurement (plain data, the
    output of ``measure``; see the module docstring). Kernel-free: core CI runs it on hand-written measurements.

    The measurement keys (``t``: distance from the seat along the advance direction; parts are instance keys):
    ``key``, ``origin``, ``direction``, ``d_mm``; ``screw`` (``length_mm``, ``head_h_mm``, ``head_r_mm``) or None;
    ``head`` (``r_mm``, ``h_mm``, ``source``); ``annulus`` (``radius_mm``, ``lines``: one ``{part: [[t0, t1],
    ...]}`` per line); ``axis`` (``{part: intervals}``); ``thread`` (``radius_mm``, ``intervals`` of the receiver,
    common to every probe line); ``holes`` (``{part: {"radius_mm", "point"}}``, the smallest hole radius in each
    clamped part, 0 for material on the axis); ``head_clear`` (``{part: radius}``: material inside the head's
    radius, without a solid); ``interference`` (``{part: {"state", "overlap_mm3", "t_range"}}``, the screw's
    solid against other parts); ``probe_end_t``; ``tool`` (see ``_tool_eval``); ``roles`` (``{key: role}``,
    ``stack`` / ``into`` / ``other``); ``excluded`` (parts with a declared intended overlap)."""
    inst = str(measurement["key"])
    o = options
    d = measurement.get("d_mm")
    roles = dict(measurement.get("roles") or {})
    role = lambda k: roles.get(k, "other")  # noqa: E731
    stack_order = list(spec.stack)
    screw = measurement.get("screw")
    head = measurement.get("head") or {}
    head_r, head_h = head.get("r_mm"), head.get("h_mm")
    length = screw["length_mm"] if screw else spec.length_mm
    seat_tol, gap_tol = o.seat_tol_mm, o.gap_tol_mm
    hole_c = spec.hole_clearance_mm if spec.hole_clearance_mm is not None else o.hole_clearance_mm
    tip_c = spec.tip_clearance_mm if spec.tip_clearance_mm is not None else o.tip_clearance_mm
    lines = [dict(line) for line in (measurement.get("annulus") or {}).get("lines") or []]
    axis = {k: _merge(v) for k, v in (measurement.get("axis") or {}).items()}
    inter = dict(measurement.get("interference") or {})
    excluded = set(measurement.get("excluded") or [])
    checks: List[Check] = []
    cid = lambda c: f"fastener:{inst}:{c}"  # noqa: E731

    # -------------------------------------------------------------- seat
    probs, warns, parts, ev = [], [], {inst}, {}
    first = []
    for line in lines:
        hits = [(iv[0], iv[1], k) for k, ivs in line.items() for iv in ivs if iv[1] > -seat_tol]
        hits.sort()
        first.append(hits[0] if hits else None)
    ev["first_hit"] = [None if f is None else {"part": f[2], "t_mm": _r(f[0])} for f in first]
    if spec.head == "flat":
        rel = measurement.get("seat_contact")
        if screw is None:
            warns.append("a flat (countersunk) head without a placed solid: its conical seat is not measured")
        elif rel is None:
            probs.append(f"the countersunk head does not touch {spec.clamps}")
        else:
            ev["seat_contact"] = rel
            if rel.get("gap_mm", 0.0) > seat_tol:
                probs.append(f"the countersunk head is {rel['gap_mm']:.3f} mm off {spec.clamps}")
    else:
        clamps0 = [h for h in first if h is not None and owner(h[2]) == spec.clamps]
        others = sorted({h[2] for h in first if h is not None and owner(h[2]) != spec.clamps})
        missing = sum(1 for h in first if h is None)
        if not lines:
            probs.append("the seat was not measured")
        if others:
            parts.update(others)
            probs.append(f"the head bears on {', '.join(others)}, not {spec.clamps} (on {len(lines) - len(clamps0)} "
                         f"of {len(lines)} lines)")
        if missing:
            probs.append(f"nothing under the head on {missing} of {len(lines)} lines: it overhangs an edge or a pocket")
        if clamps0:
            parts.add(clamps0[0][2])
            lo, hi = min(h[0] for h in clamps0), max(h[0] for h in clamps0)
            ev.update(seat_gap_mm=[_r(lo), _r(hi)])
            if hi > seat_tol:
                probs.append(f"the head stands {hi:.3f} mm off {clamps0[0][2]}'s face (> {seat_tol:g})")
            if lo < -seat_tol:
                probs.append(f"{clamps0[0][2]}'s face is {-lo:.3f} mm above the seat: the head is buried in it")
    for k, r in sorted((measurement.get("head_clear") or {}).items()):
        if k in excluded:
            continue
        parts.add(k)
        probs.append(f"{k} has material {r:.2f} mm from the axis, inside the head (r {head_r:.2f}): a pocket wall")
    ev["head"] = head
    checks.append(Check(cid("seat"), _status(probs, warns), "; ".join(probs + warns) or
                        f"the head bears on {spec.clamps} all round", sorted(parts), ev))

    # -------------------------------------------------------------- stack (along the annulus)
    probs, warns, parts, ev = [], [], {inst}, {}
    grip = None
    per_line = []
    for li, line in enumerate(lines):
        runs = sorted((iv[0], iv[1], k) for k, ivs in line.items() for iv in _merge(ivs) if iv[1] > seat_tol)
        seen, pos, row = [], None, {"line": li}
        for a, b, k in runs:
            if owner(k) in stack_order and owner(k) not in [owner(x) for x in seen]:
                seen.append(k)
        row["order"] = seen
        want_idx = [stack_order.index(owner(k)) for k in seen]
        if want_idx != sorted(want_idx):
            probs.append(f"line {li}: the stack meets {[owner(k) for k in seen]}, not {stack_order}")
        absent = [n for n in stack_order if n not in [owner(k) for k in seen]]
        if absent:
            probs.append(f"line {li}: {', '.join(absent)} not under the head")
        if seen:
            last = seen[-1]
            last_end = None
            for a, b, k in runs:
                if k == last:
                    last_end = b if last_end is None or a <= last_end + gap_tol else last_end
            between = [k for a, b, k in runs if owner(k) not in stack_order and last_end is not None
                       and a < last_end - gap_tol and b > seat_tol and k not in excluded]
            if between:
                parts.update(between)
                probs.append(f"line {li}: {', '.join(sorted(set(between)))} sits inside the clamped stack "
                             f"(not declared in it)")
            # contiguity: walk from the seat over the union of everything, to the end of the last stack part
            union = _merge([(a, b) for a, b, _ in runs])
            pos = None
            for a, b in union:
                if pos is not None and a - pos > gap_tol and pos < (last_end or 0):
                    lo_part = [k for a2, b2, k in runs if abs(b2 - pos) < 1e-3]
                    hi_part = [k for a2, b2, k in runs if abs(a2 - a) < 1e-3]
                    parts.update(lo_part + hi_part)
                    probs.append(f"line {li}: a {a - pos:.3f} mm gap between {'/'.join(lo_part) or '?'} and "
                                 f"{'/'.join(hi_part) or '?'} at t {pos:.2f}")
                pos = b if pos is None else max(pos, b)
                if last_end is not None and b >= last_end - 1e-6:
                    break
            if last_end is not None:
                row["grip_mm"] = _r(last_end)
                grip = last_end if grip is None else max(grip, last_end)
                held = any(k != last and a <= last_end + gap_tol and b > last_end + 1e-6 for a, b, k in runs)
                after = [a for a, b, k in runs if a > last_end and k != last]
                nxt = min(after) if after else None
                if not held:
                    parts.add(last)
                    probs.append(f"line {li}: nothing under {last} within {gap_tol:g} mm" + (
                        f" (next solid {nxt - last_end:.3f} mm further)" if nxt is not None else "") +
                        ": the stack is not pulled against the receiver")
        per_line.append(row)
    ev["lines"] = per_line
    ev["grip_mm"] = _r(grip)
    probs = list(dict.fromkeys(probs))
    parts.update(_keys(roles, spec.clamps)[:1])
    if not probs and grip is None:
        probs.append("no clamped part measured under the head")
    msg = "; ".join(_collapse(probs)) or f"{' + '.join(stack_order)} clamped in contact, grip {grip:.2f} mm"
    checks.append(Check(cid("stack"), _status(probs, warns), msg, sorted(parts), ev))

    # -------------------------------------------------------------- holes
    probs, warns, parts, ev = [], [], {inst}, {}
    holes = dict(measurement.get("holes") or {})
    ev["holes"] = holes
    need_r = (d + hole_c) / 2 if d else None
    for k, h in sorted(holes.items()):
        r = h.get("radius_mm")
        if r is None:
            continue
        if r <= 1e-6:
            parts.add(k)
            probs.append(f"no hole in {k}: material on the axis")
        elif need_r is not None and r < need_r - 1e-6:
            parts.add(k)
            probs.append(f"the hole in {k} is Ø{2 * r:.2f}, under Ø{2 * need_r:.2f} (d {d:g} + {hole_c:g} clearance)")
        if head_r is not None and r >= head_r - 1e-6 and owner(k) == spec.clamps and spec.head != "flat":
            parts.add(k)
            probs.append(f"the head (Ø{2 * head_r:.2f}) is no wider than the hole in {k} (Ø{2 * r:.2f}): it pulls "
                         f"through")
    thread = measurement.get("thread") or {}
    tivs = _merge(thread.get("intervals") or [])
    t_start = tivs[0][0] if tivs else None
    for k, ivs in sorted(axis.items()):
        if role(k) == "stack" and k not in holes:
            hit = [iv for iv in ivs if iv[1] > seat_tol and (grip is None or iv[0] < grip - gap_tol)]
            if hit:
                parts.add(k)
                probs.append(f"no hole in {k}: material on the axis at t {hit[0][0]:.2f}..{hit[0][1]:.2f}")
        if role(k) == "into" and t_start is not None:
            hit = [iv for iv in ivs if iv[0] <= t_start + gap_tol and iv[1] > t_start + gap_tol]
            if hit:
                parts.add(k)
                probs.append(f"no pilot or tap hole in {k}: material on the axis from t {hit[0][0]:.2f}")
    for k, rel in sorted(inter.items()):
        if k.startswith("_") or k in excluded:
            continue
        tr = rel.get("t_range")
        if role(k) == "stack" and rel.get("state") in ("overlapping", "contains"):
            parts.add(k)
            where = "the head cuts into" if tr and tr[1] <= seat_tol else "the screw overlaps"
            probs.append(f"{where} {k} ({rel.get('overlap_mm3', 0):.3f} mm³" +
                         (f", t {tr[0]:.2f}..{tr[1]:.2f}" if tr else "") + ")")
        if role(k) == "into" and rel.get("state") in ("overlapping", "contains") and tr and t_start is not None \
                and tr[0] < t_start - o.stack_tol_mm:
            parts.add(k)
            probs.append(f"the screw overlaps {k} above its thread (from t {tr[0]:.2f}, thread from {t_start:.2f})")
    checks.append(Check(cid("holes"), _status(probs, warns), "; ".join(probs) or
                        "clearance holes on the axis through " + ", ".join(spec.stack), sorted(parts), ev))

    # -------------------------------------------------------------- engagement
    probs, warns, parts, ev = [], [], {inst}, {}
    need = spec.min_engagement_mm
    need_src = "declared"
    if need is None and d:
        need, need_src = o.min_engagement_d * d, f"default {o.min_engagement_d:g} d"
    engage = thread_end = None
    pitch = spec.pitch
    receivers = sorted(k for k, r in roles.items() if r == "into")
    if tivs:
        thread_end = tivs[0][1]
        if length is not None:
            engage = max(0.0, min(length, thread_end) - t_start)
    ev.update(thread_start_mm=_r(t_start), thread_end_mm=_r(thread_end), engagement_mm=_r(engage),
              min_engagement_mm=_r(need), min_source=need_src, pitch_mm=pitch, probe_radius_mm=thread.get("radius_mm"),
              threads=_r(engage / pitch, 2) if engage is not None and pitch else None)
    parts.update(receivers[:1] if not tivs else thread.get("parts", [])[:1])
    if not receivers:
        probs.append(f"{spec.into} is not in the assembly")
    elif not tivs:
        probs.append(f"no thread of {spec.into} on the axis: the receiver is not where the screw goes, or its "
                     f"bore is wider than the screw")
    elif length is None:
        warns.append("no length: engagement not measured")
    elif need is None:
        warns.append(f"{engage:.2f} mm engaged; no minimum declared and no diameter")
    elif engage < need - 1e-6:
        if length <= t_start:
            probs.append(f"the screw stops {t_start - length:.2f} mm short of the thread in {spec.into}")
        else:
            probs.append(f"{engage:.2f} mm of thread in {spec.into}" + (f" ({engage / pitch:.1f} threads)" if pitch else "")
                         + f", under the minimum {need:.2f} mm ({need_src})")
    msg = "; ".join(probs + warns) or (f"{engage:.2f} mm engaged in {spec.into}" +
                                       (f" ({engage / pitch:.1f} threads)" if pitch else "") + f", minimum {need:.2f}")
    checks.append(Check(cid("engagement"), _status(probs, warns), msg, sorted(parts), ev))

    # -------------------------------------------------------------- tip
    probs, warns, parts, ev = [], [], {inst}, {}
    tip_room = None
    hit_at = None
    if length is not None:
        clear_from = grip if grip is not None else 0.0
        nexts = []
        for k, ivs in sorted(axis.items()):
            if k in excluded:
                continue
            for a, b in ivs:
                if b <= clear_from + gap_tol or a < -1e-6:
                    continue
                if role(k) == "stack":
                    continue                       # material in a clamped part is the holes check's
                if role(k) == "into" and t_start is not None and a <= t_start + gap_tol:
                    continue                       # no pilot hole: the holes check's
                if a < length - 1e-6:
                    parts.add(k)
                    probs.append(f"the screw runs {min(b, length) - a:.2f} mm into {k} (t {a:.2f}..{length:.2f})"
                                 + (", past its thread" if role(k) == "into" else ""))
                    hit_at = a if hit_at is None else min(hit_at, a)
                else:
                    nexts.append((a, k))
        if nexts:
            a, k = min(nexts)
            tip_room = a - length
            ev["next_solid"] = {"part": k, "t_mm": _r(a)}
            if tip_room < tip_c - 1e-6:
                parts.add(k)
                probs.append(f"the tip stops {tip_room:.2f} mm short of {k} (bottoming; under {tip_c:g} mm)")
        else:
            ev["next_solid"] = None
        for k, rel in sorted(inter.items()):
            if k.startswith("_") or k in excluded or role(k) == "stack":
                continue
            if rel.get("state") == "unknown":
                parts.add(k)
                probs.append(f"the kernel could not decide the screw against {k}: {rel.get('error', '')}")
                continue
            if rel.get("state") not in ("overlapping", "contains"):
                continue
            tr = rel.get("t_range")
            if role(k) == "into":
                if tr and thread_end is not None and tr[1] > thread_end + o.stack_tol_mm:
                    parts.add(k)
                    probs.append(f"the screw overlaps {k} past its thread (to t {tr[1]:.2f}, thread to "
                                 f"{thread_end:.2f})")
                continue
            parts.add(k)
            probs.append(f"the screw's solid overlaps {k} ({rel.get('overlap_mm3', 0):.3f} mm³" +
                         (f", t {tr[0]:.2f}..{tr[1]:.2f}" if tr else "") + ")")
    else:
        warns.append("no length: the tip is not placed")
    ev.update(tip_t_mm=_r(length), tip_clearance_mm=_r(tip_room), min_tip_clearance_mm=tip_c,
              probe_end_t_mm=measurement.get("probe_end_t"))
    msg = "; ".join(_collapse(list(dict.fromkeys(probs))) + warns) or (
        f"tip clear: {tip_room:.2f} mm to {ev['next_solid']['part']}" if tip_room is not None
        else f"tip clear: nothing within {measurement.get('probe_end_t', 0) - (length or 0):.1f} mm past it")
    checks.append(Check(cid("tip"), _status(probs, warns), msg, sorted(parts), ev))

    # -------------------------------------------------------------- length
    probs, warns, parts, ev = [], [], {inst}, {}
    lo_fit = hi_fit = None
    if screw and spec.length_mm is not None and abs(screw["length_mm"] - spec.length_mm) > o.length_tol_mm:
        probs.append(f"the placed solid is {screw['length_mm']:.2f} mm long, the record says {spec.length_mm:g}")
    if t_start is not None and spec.thread_start_mm is not None and \
            abs(t_start - float(spec.thread_start_mm)) > o.stack_tol_mm:
        probs.append(f"the thread starts {t_start:.2f} mm from the seat in the model, the record says "
                     f"{float(spec.thread_start_mm):g}: recompute the stack")
    if tivs and spec.thread_depth_mm is not None and abs((thread_end - t_start) - float(spec.thread_depth_mm)) > \
            o.stack_tol_mm:
        warns.append(f"{thread_end - t_start:.2f} mm of thread modelled, the record says {float(spec.thread_depth_mm):g}")
    if t_start is not None and need is not None:
        lo_fit = t_start + need
        stop = ev_next = None
        nxt = [(a, k) for k, ivs in axis.items() if k not in excluded and role(k) != "stack"
               for a, b in ivs if a > t_start + gap_tol]
        if nxt:
            ev_next, stop = min(nxt)[1], min(nxt)[0]
            hi_fit = stop - tip_c
        ev.update(fits_mm=[_r(lo_fit), _r(hi_fit)], limited_by=ev_next)
        if length is not None and (length < lo_fit - 1e-6 or (hi_fit is not None and length > hi_fit + 1e-6)):
            probs.append(f"length {length:g} is outside the {lo_fit:.2f}" +
                         (f"..{hi_fit:.2f}" if hi_fit is not None else "+") + " mm the stack takes (thread at "
                         f"{t_start:.2f} + {need:.2f} engagement" + (f"; {ev_next} at {stop:.2f} less "
                                                                      f"{tip_c:g} tip room)" if ev_next else ")"))
    stock = o.stock
    if length is not None and not _stock_fit(length, stock):
        warns.append(f"length {length:g} mm is not a common stock length")
    if lo_fit is not None:
        ev["stock_that_fits_mm"] = [s for s in stock if s >= lo_fit - 1e-6 and (hi_fit is None or s <= hi_fit + 1e-6)][:6]
    ev.update(length_mm=_r(length), record_length_mm=spec.length_mm,
              thread_depth_required_mm=_r(length - t_start) if length is not None and t_start is not None else None)
    msg = "; ".join(probs + warns) or (f"{length:g} mm fits the stack" + (
        f" ({lo_fit:.2f}..{hi_fit:.2f})" if lo_fit is not None and hi_fit is not None else ""))
    checks.append(Check(cid("length"), _status(probs, warns), msg, sorted(parts), ev))

    # -------------------------------------------------------------- tool
    checks.append(_tool_eval(cid("tool"), inst, spec, measurement.get("tool")))

    status = "fail" if any(c.status == "fail" for c in checks) else (
        "warn" if any(c.status == "warn" for c in checks) else "pass")
    o_, u_ = measurement.get("origin"), measurement.get("direction")
    ts_pt = [_r(o_[i] + t_start * u_[i]) for i in range(3)] if o_ and u_ and t_start is not None else None
    tool = measurement.get("tool") or {}
    row = {"fastener": inst, "name": spec.name, "key": spec.key, "clamps": spec.clamps, "stack": list(spec.stack),
           "into": spec.into, "seat": [_r(c) for c in o_] if o_ else None, "direction": list(u_) if u_ else None,
           "thread_start": ts_pt, "grip_mm": _r(grip), "thread_start_mm": _r(t_start),
           "thread_start_record_mm": spec.thread_start_mm, "thread_depth_mm": _r(thread_end - t_start) if tivs else None,
           "engagement_mm": _r(engage), "engagement_threads": _r(engage / pitch, 2) if engage is not None and pitch else None,
           "min_engagement_mm": _r(need), "length_mm": _r(length),
           "stock": bool(length is not None and _stock_fit(length, stock)),
           "fits_mm": [_r(lo_fit), _r(hi_fit)] if lo_fit is not None else None,
           "thread_depth_required_mm": _r(length - t_start) if length is not None and t_start is not None else None,
           "tip_clearance_mm": _r(tip_room), "tool": tool.get("tool") or spec.tool or None,
           "step": tool.get("step"), "tool_clear": tool.get("clear"), "status": status,
           "failed": [c.id.rsplit(":", 1)[1] for c in checks if c.status == "fail"]}
    return checks, row


def _collapse(probs: List[str]) -> List[str]:
    """Merge per-line messages that differ only in their ``line N:`` prefix."""
    out: Dict[str, List[str]] = {}
    for p in probs:
        if p.startswith("line ") and ": " in p:
            head, rest = p.split(": ", 1)
            out.setdefault(rest, []).append(head[5:])
        else:
            out.setdefault(p, [])
    return [f"{msg} (lines {', '.join(ls)})" if ls else msg for msg, ls in out.items()]


def _tool_eval(check_id: str, inst: str, spec: FastenerSpec, tool: Optional[Mapping[str, Any]]) -> Check:
    """The tool check from the sweep's result: ``{"tool", "envelope", "step", "present", "blocked": [{"part",
    "overlap_mm3", "from_head_mm", "state"}], "swing": {...}, "clear", "error"}``."""
    if not tool:
        return Check(check_id, "warn", "tool access not measured", [inst])
    ev = {k: v for k, v in tool.items() if k != "present"}
    ev["present_count"] = len(tool.get("present") or [])
    if tool.get("error"):
        return Check(check_id, "fail", tool["error"], [inst], ev)
    blocked = list(tool.get("blocked") or [])
    probs = []
    for b in blocked:
        if b.get("state") == "unknown":
            probs.append(f"the kernel could not decide the {tool['tool']} envelope against {b['part']}")
        else:
            probs.append(f"the {tool['tool']} envelope hits {b['part']} " +
                         (f"{b['from_head_mm']:.2f} mm from the head " if b.get("from_head_mm") is not None else "") +
                         f"({b.get('overlap_mm3', 0):.3f} mm³)")
    swing = tool.get("swing")
    if swing and not swing.get("ok", True):
        probs.append(f"the key's swing has a free arc of {swing['free_arc_deg']:g}°, under {swing['min_deg']:g}° "
                     f"(blocked by {', '.join(swing.get('blocked_by') or [])})")
    parts = [inst] + sorted({b["part"] for b in blocked} | set((swing or {}).get("blocked_by") or []))
    step = tool.get("step")
    where = f"step {step}" if step is not None else "the finished assembly"
    if probs:
        return Check(check_id, "fail", "; ".join(probs) + f" (at {where})", parts, ev)
    if tool.get("no_step"):
        return Check(check_id, "warn", f"no assembly step installs {spec.name}: the {tool['tool']} reaches it in the "
                     f"finished assembly", parts, ev)
    return Check(check_id, "pass", f"the {tool['tool']} reaches the head at {where}", parts, ev)


def table_markdown(data: Mapping[str, Any]) -> str:
    """The lesson-04 table of a fastener verdict as Markdown: one row per fastener instance."""
    rows = data.get("table") or []
    head = ("| Fastener | Clamps → into | Seat | Thread start | Grip | Engagement | Min | Length | Fits | "
            "Thread depth needed | Tip clearance | Tool (step) | Status |")
    out = [head, "|" + "|".join(["---"] * 13) + "|"]

    def coord(pt, u):
        if not pt or not u:
            return "–"
        i = max(range(3), key=lambda j: abs(u[j]))
        return f"{'XYZ'[i]} {pt[i]:.2f}"

    def num(x, unit=""):
        return "–" if x is None else f"{x:.2f}{unit}"

    for r in rows:
        eng = num(r.get("engagement_mm"))
        if r.get("engagement_threads") is not None:
            eng += f" ({r['engagement_threads']:g} thr)"
        fits = r.get("fits_mm")
        fit = "–" if not fits else f"{num(fits[0])}–{num(fits[1]) if fits[1] is not None else '∞'}"
        length = num(r.get("length_mm")) + ("" if r.get("stock") or r.get("length_mm") is None else " (uncommon)")
        tool = (r.get("tool") or "–") + (f" (step {r['step']})" if r.get("step") is not None else "")
        status = r["status"] + (f": {', '.join(r['failed'])}" if r.get("failed") else "")
        out.append(f"| {r['fastener']} | {' + '.join(r['stack'])} → {r['into']} | {coord(r.get('seat'), r.get('direction'))}"
                   f" | {coord(r.get('thread_start'), r.get('direction'))} | {num(r.get('grip_mm'))} | {eng} | "
                   f"{num(r.get('min_engagement_mm'))} | {length} | {fit} | {num(r.get('thread_depth_required_mm'))} | "
                   f"{num(r.get('tip_clearance_mm'))} | {tool} | {status} |")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------ the kernel side

class _Probe:
    """Lines through the assembly's solids, with per-part intersectors and classifiers built once."""

    def __init__(self, assembly: Any):
        self.asm = assembly
        self._boxes: Dict[str, Tuple[float, ...]] = {}
        self._tools: Dict[str, Any] = {}
        from cadagent.gates.relations import bounding_box
        self._bb = bounding_box

    def box(self, k: str) -> Tuple[float, ...]:
        if k not in self._boxes:
            self._boxes[k] = self._bb(self.asm.shape(k))
        return self._boxes[k]

    def _tool(self, k: str):
        if k not in self._tools:
            ic = require("OCP.IntCurvesFace", "fastener line probe")
            cls = require("OCP.BRepClass3d", "fastener line probe")
            topexp = require("OCP.TopExp", "fastener line probe")
            topabs = require("OCP.TopAbs", "fastener line probe")
            shape = self.asm.shape(k)
            inter = ic.IntCurvesFace_ShapeIntersector()
            inter.Load(shape, 1e-6)
            solids = []
            ex = topexp.TopExp_Explorer(shape, topabs.TopAbs_SOLID)
            while ex.More():
                solids.append(cls.BRepClass3d_SolidClassifier(ex.Current()))
                ex.Next()
            self._tools[k] = (inter, solids)
        return self._tools[k]

    def intervals(self, k: str, p: Vec, u: Vec, t0: float, t1: float) -> List[List[float]]:
        """Parameter spans ``[a, b]`` of ``p + t u`` (t0 <= t <= t1) inside part ``k``."""
        q0, q1 = _at(p, u, t0), _at(p, u, t1)
        bb = self.box(k)
        m = 1e-3
        for i in range(3):
            if max(q0[i], q1[i]) < bb[i] - m or min(q0[i], q1[i]) > bb[i + 3] + m:
                return []
        gp = require("OCP.gp", "fastener line probe")
        topabs = require("OCP.TopAbs", "fastener line probe")
        inter, solids = self._tool(k)
        inter.Perform(gp.gp_Lin(gp.gp_Pnt(*p), gp.gp_Dir(*u)), t0, t1)
        ts = sorted({round(inter.WParameter(i), 7) for i in range(1, inter.NbPnt() + 1)})
        ts = [t0] + [t for t in ts if t0 < t < t1] + [t1]
        out: List[List[float]] = []
        for a, b in zip(ts, ts[1:]):
            if b - a < 1e-5:
                continue
            pt = gp.gp_Pnt(*_at(p, u, (a + b) / 2))
            inside = False
            for c in solids:
                c.Perform(pt, 1e-7)
                if c.State() == topabs.TopAbs_IN:
                    inside = True
                    break
            if inside:
                if out and abs(out[-1][1] - a) < 1e-5:
                    out[-1][1] = b
                else:
                    out.append([a, b])
        return [[round(a, 6), round(b, 6)] for a, b in out]

    def along(self, keys: Iterable[str], p: Vec, u: Vec, t0: float, t1: float) -> Dict[str, List[List[float]]]:
        out = {}
        for k in keys:
            iv = self.intervals(k, p, u, t0, t1)
            if iv:
                out[k] = iv
        return out


def _to_axis_frame(shape: Any, p: Vec, u: Vec, v: Vec):
    gp = require("OCP.gp", "fastener axis frame")
    bb = require("OCP.BRepBuilderAPI", "fastener axis frame")
    trsf = gp.gp_Trsf()
    trsf.SetTransformation(gp.gp_Ax3(gp.gp_Pnt(*p), gp.gp_Dir(*u), gp.gp_Dir(*v)))
    return bb.BRepBuilderAPI_Transform(getattr(shape, "wrapped", shape), trsf, True).Shape()


def _local_box(shape: Any, p: Vec, u: Vec, v: Vec) -> Tuple[float, ...]:
    """The tight box of ``shape`` in the axis frame: x along v, y along w, z (= t) along u."""
    from cadagent.gates.relations import bounding_box
    return bounding_box(_to_axis_frame(shape, p, u, v))


def _t_range(a: Any, b: Any, p: Vec, u: Vec, v: Vec) -> Optional[List[float]]:
    """The extent along the axis of the common of ``a`` and ``b`` (None when it cannot be built)."""
    from cadagent.gates.relations import _boolean, _volume
    try:
        common = _boolean("common", a, b)
        if _volume(common) <= 0:
            return None
        box = _local_box(common, p, u, v)
        return [_r(box[2]), _r(box[5])]
    except Exception:   # a witness only: the state is the relation's
        return None


def measure(assembly: Any, spec: FastenerSpec, i: int, options: FastenerOptions = FastenerOptions(), *,
            relations: Optional[Mapping[str, Any]] = None, excluded: Iterable[str] = (),
            probe: Optional[_Probe] = None) -> Dict[str, Any]:
    """Measure fastener ``spec``'s axis ``i`` in ``assembly`` (see ``evaluate`` for the keys). ``relations``:
    ``{part: Relation}`` of the screw's solid against the parts near it (from the relation table)."""
    o = options
    p, u = spec.axes[i]
    v, w = _frame(u)
    names = list(assembly)
    inst = spec.instance_key(i)
    has_solid = inst in assembly
    others = [k for k in names if k != inst]
    probe = probe if probe is not None else _Probe(assembly)
    m: Dict[str, Any] = {"key": inst, "origin": [_r(c, 6) for c in p], "direction": [_r(c, 6) for c in u]}
    screw = None
    if has_solid:
        box = _local_box(assembly.shape(inst), p, u, v)
        screw = {"length_mm": _r(box[5]), "head_h_mm": _r(-box[2]),
                 "head_r_mm": _r(max(abs(box[0]), abs(box[1]), abs(box[3]), abs(box[4])))}
    d = spec.diameter_mm
    if d is None and screw is not None:
        sbox = None
        try:
            mid = require("cadquery", "fastener shank")
            L = screw["length_mm"]
            cut = mid.Solid.makeCylinder(10 * screw["head_r_mm"] + 10, 0.5 * L, mid.Vector(*_at(p, u, 0.25 * L)),
                                         mid.Vector(*u))
            from cadagent.gates.relations import _boolean
            sbox = _local_box(_boolean("common", assembly.shape(inst), cut.wrapped), p, u, v)
        except Exception:
            sbox = None
        if sbox is not None:
            d = 2 * max(abs(sbox[0]), abs(sbox[1]), abs(sbox[3]), abs(sbox[4]))
    m["d_mm"] = _r(d)
    if d is None:
        m["error"] = "no diameter: declare diameter_mm or place the screw's solid"
        return m
    if screw is not None:
        head = {"r_mm": screw["head_r_mm"], "h_mm": screw["head_h_mm"], "source": "solid"}
    else:
        head = {"r_mm": _r(spec.head_d_mm / 2 if spec.head_d_mm else 0.8 * d),
                "h_mm": _r(spec.head_h_mm if spec.head_h_mm else d),
                "source": "declared" if spec.head_d_mm else "default 1.6 d x 1.0 d"}
    m["screw"], m["head"] = screw, head
    length = screw["length_mm"] if screw else spec.length_mm
    t_end = (length or 0.0) + o.look_ahead_mm
    m["probe_end_t"] = _r(t_end)
    t0 = -head["h_mm"] - 0.5
    roles = {}
    for k in others:
        roles[k] = "stack" if owner(k) in spec.stack else ("into" if owner(k) == spec.into else "other")
    m["roles"] = {k: r for k, r in roles.items() if r != "other"}
    m["excluded"] = sorted(excluded)
    # candidates: parts whose box comes near the screw's cylinder of reach
    reach = max(head["r_mm"], d) + 1.0
    lo = [min(_at(p, u, t0)[j], _at(p, u, t_end)[j]) - reach for j in range(3)]
    hi = [max(_at(p, u, t0)[j], _at(p, u, t_end)[j]) + reach for j in range(3)]
    near = [k for k in others if all(probe.box(k)[j] <= hi[j] and probe.box(k)[j + 3] >= lo[j] for j in range(3))]
    r_ann = (d / 2 + head["r_mm"]) / 2
    n = o.lines
    m["annulus"] = {"radius_mm": _r(r_ann), "lines": [
        probe.along(near, _at(p, u, 0, v, w, r_ann, 2 * math.pi * (j + 0.5) / n), u, t0, t_end) for j in range(n)]}
    m["axis"] = probe.along(near, p, u, t0, t_end)
    receivers = [k for k in near if roles.get(k) == "into"]
    m["thread"] = {"radius_mm": None, "intervals": [], "parts": []}
    for frac in (0.92, 1.08):
        rt = frac * d / 2
        common, hit_parts = None, set()
        for j in range(4):
            got = probe.along(receivers, _at(p, u, 0, v, w, rt, math.pi / 2 * j + math.pi / 8), u, 0.0, t_end)
            hit_parts.update(got)
            ivs = _merge([iv for ivs in got.values() for iv in ivs])
            common = ivs if common is None else _intersect(common, ivs)
        if common:
            m["thread"] = {"radius_mm": _r(rt), "intervals": common, "parts": sorted(hit_parts)}
            break
    # clearance holes: radial rays at three depths in each clamped part met on the annulus
    holes: Dict[str, Any] = {}
    for k in sorted(k for k in near if roles.get(k) == "stack"):
        spans = _merge([iv for line in m["annulus"]["lines"] for iv in line.get(k, []) if iv[1] > 0])
        best = None
        for a, b in spans:
            for t in (a + 0.1 * (b - a), (a + b) / 2, b - 0.1 * (b - a)):
                for j in range(8):
                    ang = 2 * math.pi * j / 8
                    radial = tuple(math.cos(ang) * v[q] + math.sin(ang) * w[q] for q in range(3))
                    ivs = probe.intervals(k, _at(p, u, t), radial, 0.0, r_ann + 0.5)
                    r = ivs[0][0] if ivs else r_ann + 0.5
                    if best is None or r < best[0]:
                        best = (r, [_r(c) for c in _at(p, u, t, v, w, r, ang)])
        if best is not None:
            holes[k] = {"radius_mm": _r(best[0]), "point": best[1]}
    m["holes"] = holes
    # the head's volume (no solid): radial rays at its mid-height
    if screw is None and spec.head != "flat":
        clear = {}
        t = -head["h_mm"] / 2
        for k in near:
            for j in range(8):
                ang = 2 * math.pi * j / 8
                radial = tuple(math.cos(ang) * v[q] + math.sin(ang) * w[q] for q in range(3))
                ivs = probe.intervals(k, _at(p, u, t), radial, 0.0, head["r_mm"] - 1e-3)
                if ivs:
                    clear[k] = min(clear.get(k, 1e9), ivs[0][0])
        m["head_clear"] = {k: _r(r) for k, r in clear.items()}
    # the screw's solid against its neighbours
    if has_solid and relations is not None:
        inter = {}
        for k, rel in relations.items():
            if rel.state in ("overlapping", "contains", "unknown"):
                row = {"state": rel.state, "overlap_mm3": rel.overlap_mm3}
                if rel.state == "unknown":
                    row["error"] = rel.error
                else:
                    row["t_range"] = _t_range(assembly.shape(inst), assembly.shape(k), p, u, v)
                inter[k] = row
        if spec.head == "flat":
            seat = [relations[k] for k in relations if owner(k) == spec.clamps]
            if seat:
                rel = min(seat, key=lambda r: r.gap_mm if r.gap_mm is not None else 1e9)
                m["seat_contact"] = {"state": rel.state, "gap_mm": rel.gap_mm or 0.0}
        m["interference"] = inter
    return m


def _tool_sweep(assembly: Any, spec: FastenerSpec, i: int, m: Mapping[str, Any], tool_name: str,
                decl: Any, present: Sequence[str], step: Optional[Mapping[str, Any]], tol: Any) -> Dict[str, Any]:
    from cadagent.gates.relations import relate
    out: Dict[str, Any] = {"tool": tool_name, "step": step["order"] if step else None,
                           "step_fit": step["fit"] if step else None, "present": list(present)}
    if not tool_name:
        out["error"] = f"no tool declared for {spec.name} (fastener tool= or the step's tool)"
        return out
    if decl is None:
        out["error"] = f"tool {tool_name!r} has no envelope (declare it under gates: tools:)"
        return out
    try:
        env = tool_envelope(decl)
    except (ValueError, KeyError, TypeError) as exc:
        out["error"] = f"tool {tool_name!r}: {exc}"
        return out
    cq = require("cadquery", "tool envelope")
    p, u = spec.axes[i]
    v, w = _frame(u)
    head_h = (m.get("head") or {}).get("h_mm") or 0.0
    t = (-head_h if env["start"] == "head" else 0.0) - env["offset_mm"]
    out["envelope"] = env
    out["start_t_mm"] = _r(t)
    solid = None
    pos = t
    for s in env["segments"]:
        cyl = cq.Solid.makeCylinder(s["d"] / 2, s["length"], cq.Vector(*_at(p, u, pos)), cq.Vector(*(-c for c in u)))
        solid = cyl if solid is None else solid.fuse(cyl)
        pos -= s["length"]
    solid = solid.clean() if hasattr(solid, "clean") else solid
    inst = spec.instance_key(i)
    from cadagent.gates.relations import bounding_box
    ebox = bounding_box(solid.wrapped)
    blocked = []
    for k in present:
        if k == inst:
            continue
        kb = bounding_box(assembly.shape(k))
        if any(kb[j] > ebox[j + 3] + tol.touch_mm or kb[j + 3] < ebox[j] - tol.touch_mm for j in range(3)):
            continue
        rel = relate(solid.wrapped, assembly.shape(k), tol, names=("tool", k), contact_area=False)
        if rel.state in ("overlapping", "contains", "unknown"):
            row = {"part": k, "state": rel.state, "overlap_mm3": rel.overlap_mm3}
            if rel.state != "unknown":
                tr = _t_range(solid.wrapped, assembly.shape(k), p, u, v)
                row["from_head_mm"] = _r(t - tr[1]) if tr else None
            else:
                row["error"] = rel.error
            blocked.append(row)
    out["blocked"] = blocked
    sw = env["swing"]
    if sw:
        n = sw["sectors"]
        base = t - sw["at"]
        free = []
        by = set()
        for j in range(n):
            sector = cq.Solid.makeCylinder(sw["radius"], sw["thickness"], cq.Vector(*_at(p, u, base)),
                                           cq.Vector(*(-c for c in u)), 360.0 / n)
            sector = sector.rotate(cq.Vector(*p), cq.Vector(*_at(p, u, 1.0)), 360.0 * j / n)
            sb = bounding_box(sector.wrapped)
            ok = True
            for k in present:
                if k == inst:
                    continue
                kb = bounding_box(assembly.shape(k))
                if any(kb[q] > sb[q + 3] or kb[q + 3] < sb[q] for q in range(3)):
                    continue
                rel = relate(sector.wrapped, assembly.shape(k), tol, names=("swing", k), contact_area=False)
                if rel.state in ("overlapping", "contains", "unknown"):
                    ok = False
                    by.add(k)
            free.append(ok)
        best = run = 0
        for ok in free + free:
            run = run + 1 if ok else 0
            best = max(best, min(run, n))
        arc = 360.0 * best / n
        out["swing"] = {"free_sectors": [j for j, ok in enumerate(free) if ok], "sectors": n, "free_arc_deg": arc,
                        "min_deg": sw["min_deg"], "ok": arc >= sw["min_deg"] - 1e-9, "blocked_by": sorted(by)}
    out["clear"] = not blocked and (not sw or out["swing"]["ok"])
    return out


def fastener_gate(assembly: Any, fasteners: Any, *, steps: Iterable[Any] = (), tools: Optional[Mapping[str, Any]] = None,
                  options: FastenerOptions = FastenerOptions(), tol: Any = None, cache: Any = None,
                  intended_overlaps: Iterable[Mapping[str, Any]] = (), out: Any = None) -> Dict[str, Any]:
    """Run the fastener gate and return (with ``out``, write, plus a ``.md`` table beside it) the verdict.

    ``fasteners``: ``{name: FastenerSpec | mapping}`` or a list of specs (``fasteners_from_build`` makes them
    from a dossier build). ``steps``: the assembly steps (``BuildResult.steps`` or mappings with ``order``,
    ``fit``, ``onto``, ``fasteners``, ``tool``). ``tools``: ``{name: envelope}`` (``tool_envelope``).
    ``intended_overlaps``: ``[{parts, reason}]`` pairs whose shared volume is declared (beyond a screw and
    its receiver's thread, which is always checked) and is left out, with the reason, as an exclusion."""
    from cadagent.gates.relations import Tolerances, relation_table
    tol = tol or Tolerances()
    if isinstance(fasteners, Mapping):
        specs = {n: FastenerSpec.coerce(f, n) for n, f in fasteners.items()}
    else:
        specs = {s.name: s for s in (FastenerSpec.coerce(f) for f in fasteners)}
    step_list = _steps(steps)
    tools = dict(tools or {})
    names = list(assembly)
    kinds = {k: getattr(assembly[k], "kind", "part") for k in names}
    checks: List[Check] = []
    table: List[Dict[str, Any]] = []
    exclusions: List[Dict[str, Any]] = []
    solids = [spec.instance_key(i) for spec in specs.values() for i in range(len(spec.axes))
              if spec.instance_key(i) in assembly]
    rel_table = relation_table(assembly, tol, cache=cache, only=solids) if solids else None
    probe = _Probe(assembly)
    overlaps = [(frozenset(o["parts"]), o.get("reason", "")) for o in intended_overlaps]
    for name in sorted(specs):
        spec = specs[name]
        decl_probs = []
        if not spec.axes:
            decl_probs.append("no axes: the fastener is not placed")
        for role, n in [("clamps", p) for p in spec.stack] + [("into", spec.into)]:
            if not _keys(names, n):
                decl_probs.append(f"{role} {n!r} is not a part in the assembly")
        if decl_probs:
            checks.append(Check(f"fastener:{name}:declaration", "fail", "; ".join(decl_probs), [name]))
            continue
        step = install_step(spec, step_list) if step_list else None
        present = present_at(step, step_list, names, specs, kinds)
        tool_name = spec.tool or (step or {}).get("tool", "")
        for i in range(len(spec.axes)):
            inst = spec.instance_key(i)
            excl = set()
            rels = None
            if rel_table is not None and inst in assembly:
                rels = {}
                for r in rel_table.of(inst):
                    rels[r.b] = r
            for pair, reason in overlaps:
                hit = {k for k in names if k != inst and (k in pair or owner(k) in pair)}
                if (inst in pair or name in pair) and hit:
                    for k in hit:
                        if owner(k) == spec.into or owner(k) in spec.stack:
                            continue          # the receiver and the stack are always checked
                        excl.add(k)
                        exclusions.append({"parts": [inst, k], "reason": reason or "intended overlap"})
            m = measure(assembly, spec, i, options, relations=rels, excluded=excl, probe=probe)
            if m.get("error"):
                checks.append(Check(f"fastener:{inst}:declaration", "fail", m["error"], [inst]))
                continue
            m["tool"] = _tool_sweep(assembly, spec, i, m, tool_name, tools.get(tool_name), present, step, tol)
            if step is None and step_list:
                m["tool"]["no_step"] = True
            cs, row = evaluate(spec, m, options)
            checks += cs
            table.append(row)
    limits = {k: v for k, v in asdict(options).items() if k != "stock_lengths_mm"}
    limits.update(touch_mm=tol.touch_mm, overlap_mm3=tol.overlap_mm3,
                  stock_lengths="project" if options.stock_lengths_mm else "default metric + inch list")
    data = verdict(GATE, checks, assumptions=ASSUMPTIONS, limits=limits, exclusions=exclusions,
                   extra={"table": table, "tools": {k: v for k, v in tools.items()},
                          "relation_stats": rel_table.stats if rel_table is not None else None})
    if out is not None:
        path = write_verdict(out, data)
        path.with_suffix(".md").write_text("# Fasteners\n\n" + table_markdown(data))
    return data


def fastener_gate_from_build(result: Any, dossier: Any = None, extra: Optional[Mapping[str, Any]] = None, *,
                             assembly: Any = None, **kwargs: Any) -> Dict[str, Any]:
    """The gate on a dossier build: specs from ``fasteners_from_build``, the build's steps, tools from
    ``tools_from``, intended overlaps from the dossier's ``gates:`` and ``extra``; ``assembly`` defaults to
    ``Assembly.from_build(result)``."""
    from cadagent.gates.relations import Assembly
    asm = assembly if assembly is not None else Assembly.from_build(result)
    overlaps = list((extra or {}).get("intended_overlaps") or [])
    if dossier is not None:
        overlaps += [{"parts": list(p.parts), "reason": p.reason} for p in dossier.gates.intended_overlaps]
    steps = getattr(result, "steps", None) or ((getattr(result, "geometry", None) or {}).get("assembly") or {}).get(
        "steps") or []
    kwargs.setdefault("intended_overlaps", overlaps)
    return fastener_gate(asm, fasteners_from_build(result, dossier, extra), steps=steps,
                         tools=tools_from(dossier, extra), **kwargs)


__all__ = ["FastenerSpec", "FastenerOptions", "fastener_gate", "fastener_gate_from_build", "fasteners_from_build",
           "tools_from", "tool_envelope", "install_step", "present_at", "evaluate", "measure", "table_markdown",
           "owner", "ASSUMPTIONS", "GATE", "CHECKS", "DEFAULT_STOCK_MM", "COARSE_PITCH_MM"]
