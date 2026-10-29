"""Assembly-sequence access: can every part go in, in the declared order, along its declared direction?

The dossier's assembly steps (``assembly.step(order, fit, onto, direction=..., tool=..., fasteners=...)``) are
read in order. The gate checks:

============================ ==========================================================================================
check                        fails when
============================ ==========================================================================================
``steps``                    no steps, or two steps share an order number
``cover:<part>``             a part instance is fitted by no step, or by more than one (``fit`` names a part, which
                             fits all its instances, or one instance key)
``cover:<fastener>``         no step installs a declared fastener, or steps list it by name more than once
``step:<n>:refs``            ``fit`` is not a part; an ``onto`` part does not exist or is fitted at this step or later;
                             a ``fasteners`` entry names no fastener, or installs nothing (every fastener of that
                             catalogue key goes in at another step), or a key listed k > 1 times does not match the
                             k screws that go in there; the direction is not ``+X``..``-Z`` or a vector
``step:<n>:fasteners``       a fastener installed here clamps or threads into a part fitted at a later step
``step:<n>:insert``          an instance of the fitted part, moved in along ``direction`` from beyond every part
                             present to its seat, shares volume with a present part on the way or at the seat
                             (``undecided`` kernel answers fail too). No direction: a warning (``missing_direction``)
``step:<n>:tool:<screw>``    the tool's envelope (the fastener gate's sweep, ``fasteners.tool_access``) overlaps a
                             part present when the screw is driven at this step; a step that declares a tool but
                             installs no fastener warns
``service:<instance>``       (``service=``, off by default; a warning) pulling the part back out along its direction,
                             in the finished assembly, meets a part fitted later other than its own fasteners
============================ ==========================================================================================

**Present at a step.** For an insertion: the parts fitted at earlier steps and the solids of fasteners installed
at earlier steps; parts no step fits (``cover:`` fails them) are left out and listed in ``not_checked``. For a tool
sweep: the fastener gate's ``present_at`` (everything fitted at or before the step, and, conservatively, parts no
step fits), so both gates agree. Instances fitted at the same step are not checked against each other (their
order within the step is not declared). A fastener goes in at its ``install_step`` (the fastener gate's rule).

**The insertion sweep.** The part instance moves along the line ``seat - s * direction`` with ``s`` from beyond
the far side of each present part's box (``margin_mm`` past it) down to 0. It is conservative advancement: from
each position the part steps by the gap to the obstacle, the box distance or the exact one (moving by less than
the gap cannot close it), and by ``max_step_mm`` only while the gap is smaller than that, i.e. while it is within
reach of contact or sliding along a face; within ``max_step_mm`` of the obstacle's box every sample is exact. Shared volume over ``overlap_mm3`` at any sample blocks the step; the
first contact is then bisected (``refine_steps``) between the last clear sample and the first hit. At the seat
(``s = 0``) contact is expected and shared volume blocks, unless the pair is a declared intended overlap (then it
is excluded from the sweep, with its reason, like a press-fit or heat-set insert).

Kernel-free core: ``run_sequence(world, steps, fasteners, ...)`` works on any ``SequenceWorld`` (part names and
kinds, boxes, the relation of a translated part to another, and the tool sweep), which is how the rules are tested
without CadQuery. ``assembly_gate(assembly, steps, ...)`` wraps an ``Assembly``; ``assembly_from_build`` reads a
dossier build.

Limits, stated in every verdict: straight-line insertion along one declared direction, no rotation or tilt, no
hand or fixture room; the part is rigid and at its modelled size (no tolerance, flex or print shrink). Where the
part is within ``max_step_mm`` of an obstacle the line is sampled, so a feature thinner than that step, crossing
another between two samples, can be missed. A clear path in the model does not prove the parts go together.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from cadagent.gates.fasteners import (FastenerSpec, install_step, owner, present_at, tool_access, tool_check,
                                      tools_from, fasteners_from_build)
from cadagent.gates.motion import _mul, box_distance
from cadagent.gates.relations import Relation, Tolerances
from cadagent.gates.verdict import Check, verdict, write_verdict

GATE = "assembly"
Vec = Tuple[float, float, float]
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}

ASSUMPTIONS = [
    "Each part goes in along a straight line in its step's declared direction, from beyond every part present "
    "to its modelled position: no rotation, tilt or wiggle, and no room for hands or fixtures is checked.",
    "An insertion is checked against the parts fitted and the fasteners installed at earlier steps (the fastener "
    "gate's install_step); parts no step fits are not obstacles (the cover check fails them). A tool sweep is "
    "checked against the fastener gate's present_at (parts no step fits count as present). Instances fitted at "
    "one step are not checked against each other.",
    "Conservative advancement: the part steps by its gap to each obstacle (box distance or exact), which cannot "
    "skip a contact, and by max_step_mm only within that distance of it; a feature thinner than that step can "
    "pass another between two samples there.",
    "Exact B-rep relations within the relation tolerances (overlap_mm3 of shared volume blocks; touching and "
    "sliding along a face are allowed); no tolerance stack, print shrink or flex, so a clear path in the model "
    "does not prove the printed parts go together.",
    "Tool access is the fastener gate's straight sweep of the declared envelope along the screw axis, against "
    "the parts present when the screw is driven.",
]


@dataclass(frozen=True)
class AccessOptions:
    """Gate-wide settings (mm)."""
    max_step_mm: float = 1.0           # sample spacing while the part is within this distance of an obstacle
    margin_mm: float = 1.0             # the sweep starts this far beyond the obstacle's box
    refine_steps: int = 12             # bisection steps for the first contact
    max_samples: int = 5000            # per part and obstacle; more fails the pair as unchecked
    tool_access: bool = True           # sweep the tool of every fastener at the step that installs it
    missing_direction: str = "warn"    # a step with no direction: "warn" or "fail"

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                raise ValueError(f"AccessOptions.{f.name} must be non-negative, got {v!r}")
        if self.max_step_mm <= 0:
            raise ValueError("AccessOptions.max_step_mm must be positive")
        if self.missing_direction not in ("warn", "fail"):
            raise ValueError("AccessOptions.missing_direction must be 'warn' or 'fail'")


# ------------------------------------------------------------------------------------------ steps

def direction_vector(value: Any) -> Optional[Vec]:
    """``"+X"``..``"-Z"`` or ``(x, y, z)`` as a unit vector; None for an empty direction. Raises ValueError."""
    if value in (None, "", [], ()):
        return None
    if isinstance(value, str):
        v = value.strip().upper()
        if len(v) == 2 and v[0] in "+-" and v[1] in AXES:
            sign = -1.0 if v[0] == "-" else 1.0
            return tuple(sign * c + 0.0 for c in AXES[v[1]])  # type: ignore[return-value]
        raise ValueError(f"direction {value!r}: use +X..-Z or (x, y, z)")
    try:
        x, y, z = (float(c) for c in value)
    except (TypeError, ValueError):
        raise ValueError(f"direction {value!r}: use +X..-Z or (x, y, z)") from None
    n = math.sqrt(x * x + y * y + z * z)
    if not n > 1e-12 or not math.isfinite(n):
        raise ValueError(f"direction {value!r} has no length")
    return (x / n, y / n, z / n)


def normalise_steps(steps: Iterable[Any]) -> List[Dict[str, Any]]:
    """Steps as plain dicts sorted by order: ``order``, ``fit``, ``onto`` (list), ``direction`` (as given),
    ``tool``, ``fasteners`` (list, repeats kept), ``access_check``, ``note``, ``declared_at``. Accepts the
    registry's ``StepDecl``, the dossier's ``AssemblyStep`` and mappings (the geometry record's steps)."""
    out = []
    for s in steps or ():
        g = (lambda k, d=None: s.get(k, d)) if isinstance(s, Mapping) else (lambda k, d=None: getattr(s, k, d))
        onto = g("onto") or []
        where = g("declared_at") or g("where") or ""
        out.append({"order": g("order"), "fit": str(g("fit") or ""),
                    "onto": [onto] if isinstance(onto, str) else [str(o) for o in onto],
                    "direction": g("direction") or "", "tool": str(g("tool") or ""),
                    "fasteners": [str(f) for f in (g("fasteners") or [])], "access_check": str(g("access_check") or ""),
                    "note": str(g("note") or ""), "declared_at": str(where) if where else ""})
    return sorted(out, key=lambda s: (not isinstance(s["order"], (int, float)), s["order"]
                                      if isinstance(s["order"], (int, float)) else 0))


def _instances(names: Iterable[str], name: str) -> List[str]:
    return [k for k in names if k == name or owner(k) == name]


# ------------------------------------------------------------------------------------------ the world

class SequenceWorld:
    """What the sequence core needs from an assembly. ``AssemblySequenceWorld`` is the kernel one; tests use boxes.

    * ``names``: assembly keys (part instances and placed fastener solids); ``kind(key)``: ``"part"`` or
      ``"fastener"``; ``box(key)``: its axis-aligned box in assembly coordinates;
    * ``relate_at(key, shift, other)``: the ``Relation`` of ``key`` translated by ``shift`` with ``other`` in place;
    * ``tool(spec, i, tool_name, decl, present, step, later)``: the fastener gate's tool sweep (``tool_access``);
    * ``stats``: counters merged into the verdict.
    """
    names: List[str] = []

    def kind(self, key: str) -> str:
        return "part"

    def box(self, key: str) -> Sequence[float]:
        raise NotImplementedError

    def relate_at(self, key: str, shift: Vec, other: str) -> Relation:
        raise NotImplementedError

    def tool(self, spec: FastenerSpec, i: int, tool_name: str, decl: Any, present: Sequence[str],
             step: Mapping[str, Any], later: Sequence[str] = ()) -> Dict[str, Any]:
        raise NotImplementedError

    @property
    def stats(self) -> Dict[str, Any]:
        return {}


class _View:
    """The two items ``_relate_items`` reads: ``item(name)`` and ``shape(name)``."""

    def __init__(self, items: Mapping[str, Any]):
        self._items = dict(items)

    def item(self, name: str):
        return self._items[name]

    def shape(self, name: str):
        return self._items[name].located


class AssemblySequenceWorld(SequenceWorld):
    """An ``Assembly`` with parts translated one at a time; relations memoised in memory and through a
    ``PairCache`` (keyed like the relation table: content hash plus the translated placement)."""

    def __init__(self, assembly: Any, tol: Tolerances = Tolerances(), cache: Any = None):
        from cadagent.gates.relations import bounding_box
        self.assembly, self.tol, self.cache = assembly, tol, cache
        self.names = list(assembly.names)
        self._boxes = {n: bounding_box(assembly.shape(n)) for n in self.names}
        self._memo: Dict[Tuple[Any, ...], Relation] = {}
        self._volumes: Dict[str, float] = {}
        self._probe = None
        self.kernel_queries = self.memo_hits = self.cache_hits = self.tool_sweeps = 0

    def kind(self, key: str) -> str:
        return getattr(self.assembly[key], "kind", "part") or "part"

    def box(self, key: str) -> Sequence[float]:
        return self._boxes[key]

    def relate_at(self, key: str, shift: Vec, other: str) -> Relation:
        from cadagent.gates.relations import _relate_items
        memo = (key, other) + tuple(round(c, 9) for c in shift)
        if memo in self._memo:
            self.memo_hits += 1
            return self._memo[memo]
        part = self.assembly[key]
        if any(abs(c) > 0 for c in shift):
            part = replace(part, matrix=_mul((1.0, 0.0, 0.0, shift[0], 0.0, 1.0, 0.0, shift[1],
                                              0.0, 0.0, 1.0, shift[2]), part.matrix), _located=None)
        rel = _relate_items(_View({key: part, other: self.assembly[other]}), key, other, self.tol, self.cache,
                            False, self._volumes)
        if rel.cached:
            self.cache_hits += 1
        else:
            self.kernel_queries += 1
        self._memo[memo] = rel
        return rel

    def tool(self, spec: FastenerSpec, i: int, tool_name: str, decl: Any, present: Sequence[str],
             step: Mapping[str, Any], later: Sequence[str] = ()) -> Dict[str, Any]:
        from cadagent.gates.fasteners import _Probe
        if self._probe is None:
            self._probe = _Probe(self.assembly)
        self.tool_sweeps += 1
        return tool_access(self.assembly, spec, i, tool_name, decl, present, step, self.tol, later=later,
                           probe=self._probe)

    @property
    def stats(self) -> Dict[str, Any]:
        return {"kernel_queries": self.kernel_queries, "memo_hits": self.memo_hits, "cache_hits": self.cache_hits,
                "tool_sweeps": self.tool_sweeps}


# ------------------------------------------------------------------------------------------ the sweep

def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _shift_box(box: Sequence[float], v: Sequence[float]) -> Tuple[float, ...]:
    return tuple(box[i] + v[i % 3] for i in range(6))


def _extent(box: Sequence[float], v: Sequence[float]) -> Tuple[float, float]:
    """Min and max of ``x . v`` over the box's corners."""
    vals = [_dot((x, y, z), v) for x in (box[0], box[3]) for y in (box[1], box[4]) for z in (box[2], box[5])]
    return min(vals), max(vals)


def _r(x: Optional[float], digits: int = 4) -> Optional[float]:
    if x is None or not math.isfinite(x):
        return None
    v = round(float(x), digits)
    return 0.0 if v == 0 else v


def sweep_pair(world: SequenceWorld, key: str, direction: Vec, other: str, *,
               options: AccessOptions = AccessOptions(), tol: Tolerances = Tolerances(),
               seat: bool = True) -> Dict[str, Any]:
    """Move ``key`` in along ``direction`` (a unit vector: the way it travels to its seat) from beyond ``other``'s
    box to its seat, and report what it meets.

    The positions are ``seat - s * direction``, ``s`` from the far side of ``other``'s box (plus ``margin_mm``)
    down to 0. Returns ``{"part": other, "state": ..., ...}`` with ``state`` one of ``clear`` (never shares
    volume; the closest approach lies between ``gap_lower_bound_mm``, which holds over the whole path, between
    samples too, and ``min_gap_mm``, the smallest exact gap measured (the seat, and every sample within
    ``max_step_mm`` of the obstacle's box; None when nothing was measured); ``touching`` when it slides along or
    seats on ``other``),
    ``blocked`` (shares volume on the way: ``first_contact_mm`` = [last clear s, first hit s] after bisection,
    ``overlap_mm3`` and its centroid at the hit, the closest points at the clear side), ``seat`` (shares volume
    at its seat), ``unknown`` (the kernel could not decide a sample) or ``unchecked`` (over ``max_samples``).
    ``seat=False`` leaves the seat (s = 0) out: the service check pulls a part out past parts fitted later."""
    back = tuple(-c for c in direction)
    pb, qb = world.box(key), world.box(other)
    p_lo, _ = _extent(pb, back)
    _, q_hi = _extent(qb, back)
    travel = max(q_hi - p_lo, 0.0) + options.margin_mm
    out: Dict[str, Any] = {"part": other, "travel_mm": _r(travel)}
    swept = tuple(min(pb[i], pb[i] + travel * back[i % 3]) if i < 3 else max(pb[i], pb[i] + travel * back[i % 3])
                  for i in range(6))
    lb = box_distance(swept, qb)
    if lb > tol.touch_mm:
        out.update(state="clear", min_gap_mm=None, gap_lower_bound_mm=_r(lb), touching=False, samples=0)
        return out
    samples = 0
    measured = math.inf                 # the smallest exact gap measured on the path
    bound = math.inf                    # a lower bound on the gap over the whole sampled path
    touching = False
    last: Optional[Tuple[float, float]] = None   # (s, lower bound on the gap there) of the previous sample

    def note(at: float, g: float) -> None:
        # translating by h changes the gap by at most h, so between two samples h apart with gaps (at least)
        # g1 and g2 the gap is at least (g1 + g2 - h) / 2
        nonlocal bound, last
        bound = min(bound, g)
        if last is not None:
            bound = min(bound, max(0.0, (last[1] + g - abs(last[0] - at)) / 2))
        last = (at, g)

    if seat:
        rel0 = world.relate_at(key, (0.0, 0.0, 0.0), other)
        samples += 1
        if rel0.state == "unknown":
            out.update(state="unknown", at_mm=0.0, error=rel0.error, samples=samples)
            return out
        if rel0.interferes:
            out.update(state="seat", overlap_mm3=rel0.overlap_mm3, samples=samples,
                       overlap_centroid=rel0.witness.get("overlap_centroid"))
            if "member_pair" in rel0.witness:
                out["member_pair"] = rel0.witness["member_pair"]
            return out
        g0 = rel0.gap_mm if rel0.gap_mm is not None else 0.0
        touching = g0 <= tol.touch_mm
        measured = g0
    s, prev, prev_rel = travel, None, None
    step = options.max_step_mm
    while s > 1e-9:
        if samples >= options.max_samples:
            out.update(state="unchecked", samples=samples, at_mm=_r(s),
                       error=f"over max_samples ({options.max_samples}) before the seat")
            return out
        shift = tuple(s * c for c in back)
        gb = box_distance(_shift_box(pb, shift), qb)
        rel = None
        if gb >= step and prev is not None:     # far: the box gap is a safe step, no kernel query (the first
            gap = gb                            # sample is exact, so the start offset never reads as a clearance)
        else:                           # within reach of contact: measure exactly
            rel = world.relate_at(key, shift, other)
            samples += 1
            if rel.state == "unknown":
                out.update(state="unknown", at_mm=_r(s), error=rel.error, samples=samples)
                return out
            if rel.interferes:
                out.update(_onset(world, key, back, other, s, prev, rel, prev_rel, options))
                out["samples"] = samples + out.pop("refine_samples", 0)
                return out
            gap = rel.gap_mm if rel.gap_mm is not None else 0.0
            measured = min(measured, gap)
            touching = touching or gap <= tol.touch_mm
        note(s, gap)
        prev, prev_rel = s, rel
        s -= max(gap, step)
    if seat:
        note(0.0, g0)
    out.update(state="clear", min_gap_mm=_r(measured) if math.isfinite(measured) else None,
               gap_lower_bound_mm=_r(bound) if math.isfinite(bound) else None, touching=touching, samples=samples)
    return out


def _onset(world: SequenceWorld, key: str, back: Vec, other: str, hit: float, clear: Optional[float],
           hit_rel: Relation, clear_rel: Optional[Relation], options: AccessOptions) -> Dict[str, Any]:
    """Bisect the first contact between the last clear position ``clear`` and the first hit ``hit``."""
    n = 0
    if clear is not None:
        for _ in range(options.refine_steps):
            mid = (hit + clear) / 2
            rel = world.relate_at(key, tuple(mid * c for c in back), other)
            n += 1
            if rel.state == "unknown":
                break
            if rel.interferes:
                hit, hit_rel = mid, rel
            else:
                clear, clear_rel = mid, rel
    out: Dict[str, Any] = {"state": "blocked", "first_contact_mm": [_r(clear), _r(hit)],
                           "overlap_mm3": hit_rel.overlap_mm3,
                           "overlap_centroid": hit_rel.witness.get("overlap_centroid"), "refine_samples": n}
    if "member_pair" in hit_rel.witness:
        out["member_pair"] = hit_rel.witness["member_pair"]
    if clear_rel is not None:
        out["clear_gap_mm"] = clear_rel.gap_mm
        out["clear_points"] = [clear_rel.witness.get("point_a"), clear_rel.witness.get("point_b")]
    return out


# ------------------------------------------------------------------------------------------ the core

def _overlap_reason(overlaps: Sequence[Tuple[frozenset, str]], a: str, b: str) -> Optional[str]:
    for pair, reason in overlaps:
        if (a in pair or owner(a) in pair) and (b in pair or owner(b) in pair):
            return reason or "intended overlap"
    return None


def _plan(steps: List[Dict[str, Any]], names: List[str], kinds: Mapping[str, str],
          specs: Mapping[str, FastenerSpec]) -> Dict[str, Any]:
    """Which step fits which instance and installs which fastener, and the reference problems per step."""
    parts = [k for k in names if kinds.get(k, "part") != "fastener"]
    part_names = list(dict.fromkeys(owner(k) for k in parts))
    fitted: Dict[str, List[Any]] = {k: [] for k in parts}
    by_key: Dict[str, List[str]] = {}
    for n, sp in specs.items():
        if sp.key:
            by_key.setdefault(sp.key, []).append(n)
    named: Dict[str, List[Any]] = {n: [] for n in specs}
    for s in steps:
        for k in _instances(parts, s["fit"]) if s["fit"] else []:
            fitted[k].append(s["order"])
        for f in dict.fromkeys(s["fasteners"]):          # a name repeated within one step is a refs problem
            if f in specs:
                named[f].append(s["order"])
    install = {n: (install_step(sp, steps) or {}).get("order") for n, sp in specs.items()}
    first_fit = {k: v[0] for k, v in fitted.items() if v}

    def fit_order(name: str) -> Tuple[List[str], List[str]]:
        """A part's instance keys, and those no step fits."""
        keys = _instances(parts, name)
        return keys, [k for k in keys if k not in first_fit]

    refs: Dict[Any, Dict[str, Any]] = {}
    for s in steps:
        probs, ev = [], {}
        o = s["order"]
        if not s["fit"]:
            probs.append("no part to fit")
        elif not _instances(parts, s["fit"]):
            probs.append(f"fit {s['fit']!r} is a fastener: list it under fasteners" if s["fit"] in specs or
                         _instances([k for k in names if kinds.get(k) == "fastener"], s["fit"])
                         else f"fit {s['fit']!r} is not a part in the assembly")
        try:
            direction_vector(s["direction"])
        except ValueError as exc:
            probs.append(str(exc))
        for name in s["onto"]:
            keys, unfitted = fit_order(name)
            if not keys:
                probs.append(f"onto {name!r} is not a part in the assembly")
                continue
            if name == s["fit"] or owner(s["fit"]) == name:
                probs.append(f"onto {name!r} is the part this step fits")
                continue
            late = sorted({first_fit[k] for k in keys if k in first_fit and first_fit[k] >= o})
            if late:
                probs.append(f"onto {name!r} is fitted at step {', '.join(map(str, late))}, not before step {o}")
            if unfitted:
                ev.setdefault("onto_fitted_by_no_step", []).extend(unfitted)
        counts: Dict[str, int] = {}
        for f in s["fasteners"]:
            counts[f] = counts.get(f, 0) + 1
        for f, k in counts.items():
            if f in specs:
                if k > 1:
                    probs.append(f"fastener {f!r} is listed {k} times")
                continue
            if f not in by_key:
                probs.append(f"fasteners entry {f!r} names no declared fastener (name or catalogue key)")
                continue
            here = [n for n in by_key[f] if install[n] == o and o not in named[n]]
            screws = sum(len(specs[n].axes) for n in here)
            if not here:
                elsewhere = sorted({install[n] for n in by_key[f] if install[n] is not None}, key=str)
                probs.append(f"fasteners entry {f!r} installs nothing here: every {f} goes in at step "
                             f"{', '.join(map(str, elsewhere))}")
            elif k > 1 and k != screws:
                probs.append(f"{f!r} is listed {k} times but {screws} go in here ({', '.join(here)})")
        refs[o] = {"problems": probs, "evidence": ev}
    return {"parts": parts, "part_names": part_names, "fitted": fitted, "first_fit": first_fit,
            "named": named, "install": install, "refs": refs}


def run_sequence(world: SequenceWorld, steps: Iterable[Any], fasteners: Any = None, *,
                 tools: Optional[Mapping[str, Any]] = None, options: AccessOptions = AccessOptions(),
                 tol: Tolerances = Tolerances(), intended_overlaps: Iterable[Mapping[str, Any]] = (),
                 service: Any = False, subassemblies: Optional[Mapping[str, Any]] = None,
                 service_after: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The gate's rules on any ``SequenceWorld``. Returns ``{"checks", "steps", "exclusions", "not_checked"}``.

    ``fasteners``: ``{name: FastenerSpec | mapping}`` or a list of specs. ``service``: True checks every part's
    removal from the finished assembly, a list of part names checks those (warnings). ``subassemblies`` maps
    module names to exact ``members`` and internal ``steps``; ``service_after`` lists explicitly assumed-removed
    parent keys for conditional module withdrawal. See ``docs/subassembly-insertion.md``."""
    if subassemblies is not None or service_after is not None:
        from cadagent.gates.subassembly import run_subassemblies
        return run_subassemblies(world, steps, fasteners, tools=tools, options=options, tol=tol,
                                 intended_overlaps=intended_overlaps, service=service,
                                 subassemblies=subassemblies, service_after=service_after)
    if isinstance(fasteners, Mapping):
        specs = {n: FastenerSpec.coerce(f, n) for n, f in fasteners.items()}
    else:
        specs = {s.name: s for s in (FastenerSpec.coerce(f) for f in (fasteners or ()))}
    tools = dict(tools or {})
    step_list = normalise_steps(steps)
    names = list(world.names)
    kinds = {k: world.kind(k) for k in names}
    overlaps = [(frozenset(o["parts"]), str(o.get("reason", ""))) for o in intended_overlaps]
    checks: List[Check] = []
    rows: List[Dict[str, Any]] = []
    exclusions: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    not_checked: List[Dict[str, Any]] = []

    orders = [s["order"] for s in step_list]
    bad = [o for o in orders if isinstance(o, bool) or not isinstance(o, int)]
    dupes = sorted({o for o in orders if orders.count(o) > 1 and o not in bad})
    if not step_list:
        checks.append(Check("steps", "fail", "no assembly steps declared: nothing says how the parts go together",
                            sorted({owner(k) for k in names if kinds[k] != "fastener"})))
        return {"checks": checks, "steps": rows, "exclusions": [], "not_checked": not_checked}
    if dupes or bad:
        msg = "; ".join(([f"steps share order {', '.join(map(str, dupes))}"] if dupes else []) +
                        ([f"order {', '.join(map(repr, bad))} is not an integer"] if bad else []))
        checks.append(Check("steps", "fail", msg, [], {"orders": orders}))
        return {"checks": checks, "steps": rows, "exclusions": [], "not_checked": not_checked}
    checks.append(Check("steps", "pass", f"{len(step_list)} steps in order {orders[0]}..{orders[-1]}", [],
                        {"orders": orders}))

    plan = _plan(step_list, names, kinds, specs)
    parts, fitted, first_fit = plan["parts"], plan["fitted"], plan["first_fit"]

    # coverage: every part instance fitted at exactly one step, every fastener installed at exactly one
    for name in plan["part_names"]:
        keys = _instances(parts, name)
        none = [k for k in keys if not fitted[k]]
        many = {k: fitted[k] for k in keys if len(fitted[k]) > 1}
        probs = []
        if none:
            probs.append("no step fits " + ", ".join(none))
        for k, os_ in many.items():
            probs.append(f"{k} is fitted at steps {', '.join(map(str, os_))}")
        at = sorted({o for k in keys for o in fitted[k]})
        ev = {"steps": at, "instances": len(keys)}
        if probs:
            checks.append(Check(f"cover:{name}", "fail", "; ".join(probs), keys if len(keys) > 1 else [name], ev))
        else:
            checks.append(Check(f"cover:{name}", "pass", f"fitted at step {', '.join(map(str, at))}", [name], ev))
    for n in sorted(specs):
        by_name, st = plan["named"][n], plan["install"][n]
        cid = f"cover:fastener:{n}" if n in plan["part_names"] else f"cover:{n}"   # a hand-built name clash
        if len(by_name) > 1:
            checks.append(Check(cid, "fail", f"listed by name at steps {', '.join(map(str, by_name))}",
                                [n], {"steps": by_name}))
        elif st is None:
            checks.append(Check(cid, "fail", "no step installs it (list its name or catalogue key under a "
                                "step's fasteners)", [n]))
        else:
            checks.append(Check(cid, "pass", f"installed at step {st}", [n], {"step": st}))

    installed_at = {sp.instance_key(i): plan["install"][n] for n, sp in specs.items() for i in range(len(sp.axes))}

    def present_before(order: Any) -> List[str]:
        """The obstacles of an insertion: parts fitted and fastener solids installed at earlier steps. Unlike the
        tool sweep (``present_at``), parts and fasteners no step brings in are left out: ``cover:`` fails them."""
        out = []
        for k in names:
            at = installed_at.get(k) if (kinds[k] == "fastener" or k in installed_at) else first_fit.get(k)
            if at is not None and at < order:
                out.append(k)
        return out

    unplaced = [k for k in names if (installed_at.get(k) if (kinds[k] == "fastener" or k in installed_at)
                                     else first_fit.get(k)) is None]
    if unplaced:
        not_checked.append({"what": "insertion obstacles", "parts": unplaced,
                            "reason": "no step fits or installs them, so no insertion is checked against them"})

    service_set = None if service is True else set([service] if isinstance(service, str) else (service or []))
    service_on = service is True or bool(service_set)
    for s in step_list:
        o = s["order"]
        row: Dict[str, Any] = {"order": o, "fit": s["fit"], "onto": s["onto"], "direction": s["direction"],
                               "tool": s["tool"], "fasteners": s["fasteners"]}
        ref = plan["refs"][o]
        refs_status = "fail" if ref["problems"] else "pass"
        checks.append(Check(f"step:{o}:refs", refs_status, "; ".join(ref["problems"]) or
                            "fit, onto and fasteners resolve; onto parts come earlier",
                            [p for p in [s["fit"]] + s["onto"] if p],
                            ref["evidence"]))
        # fasteners installed here: what they clamp and thread into must already be fitted
        here = sorted(n for n, st in plan["install"].items() if st == o)
        row["installs"] = here
        if here:
            probs, ev = [], {}
            for n in here:
                sp = specs[n]
                for role, pname in [("clamps", p) for p in sp.stack] + [("threads into", sp.into)]:
                    keys = _instances(parts, pname)
                    late = sorted({first_fit[k] for k in keys if k in first_fit and first_fit[k] > o})
                    if late:
                        probs.append(f"{n} {role} {pname}, fitted at step {', '.join(map(str, late))}")
                    unfitted = [k for k in keys if k not in first_fit]
                    if unfitted:
                        ev.setdefault("parties_fitted_by_no_step", []).extend(unfitted)
            msg = ("driven at step %s before what it holds is fitted: " % o + "; ".join(probs)) if probs else \
                f"{', '.join(here)}: clamped parts and receivers are fitted at or before step {o}"
            parties = sorted({p for n in here for p in specs[n].stack + [specs[n].into]})
            checks.append(Check(f"step:{o}:fasteners", "fail" if probs else "pass", msg, here + parties, ev))

        # insertion sweep of every instance of the fitted part
        inst = _instances(parts, s["fit"]) if s["fit"] else []
        try:
            d = direction_vector(s["direction"])
        except ValueError:
            d = None
            inst = []          # refs already fails
        present = [k for k in present_before(o) if k not in inst]
        row["present"] = len(present)
        if inst and d is None:
            sev = options.missing_direction
            checks.append(Check(f"step:{o}:insert", sev, f"no direction declared: the way {s['fit']} goes in is not "
                                "checked", [s["fit"]]))
            not_checked.append({"step": o, "what": "insertion", "reason": "no direction"})
        elif inst:
            blocked, results, nearest, floor = [], {}, None, None
            for k in inst:
                rs = []
                for q in present:
                    reason = _overlap_reason(overlaps, k, q)
                    if reason is not None:
                        exclusions[(k, q)] = {"parts": [k, q], "reason": reason, "step": o}
                        continue
                    r = sweep_pair(world, k, d, q, options=options, tol=tol)
                    if r["state"] != "clear" or r.get("min_gap_mm") is not None or r.get("touching"):
                        rs.append(r)
                    if r["state"] == "clear" and not r.get("touching"):
                        if r.get("min_gap_mm") is not None:
                            cand = (r["min_gap_mm"], k, q)
                            nearest = cand if nearest is None or cand < nearest else nearest
                        if r.get("gap_lower_bound_mm") is not None:
                            cand = (r["gap_lower_bound_mm"], k, q)
                            floor = cand if floor is None or cand < floor else floor
                    if r["state"] != "clear":
                        blocked.append((k, r))
                results[k] = rs
            slides = sorted({r["part"] for rs in results.values() for r in rs if r.get("touching")})
            ev = {"direction": list(d), "instances": inst, "present": present,
                  "max_step_mm": options.max_step_mm, "margin_mm": options.margin_mm,
                  "touching": slides, "near": {k: rs for k, rs in results.items() if rs}}
            if nearest is not None:
                ev["min_clearance"] = {"gap_mm": nearest[0], "part": nearest[1], "other": nearest[2]}
            if floor is not None:
                ev["clearance_at_least"] = {"gap_mm": floor[0], "part": floor[1], "other": floor[2]}
            row.update(touching=slides, min_clearance_mm=nearest[0] if nearest else None,
                       clearance_at_least_mm=floor[0] if floor else None,
                       blocked=[{"instance": k, **r} for k, r in blocked])
            if blocked:
                msgs = []
                for k, r in blocked:
                    if r["state"] == "blocked":
                        fc, at = r["first_contact_mm"], r.get("overlap_centroid")
                        msgs.append(f"{k} meets {r['part']} {fc[1]:.2f} mm before its seat" +
                                    (f" (first contact near ({', '.join(f'{c:.1f}' for c in at)}))" if at else ""))
                    elif r["state"] == "seat":
                        msgs.append(f"{k} overlaps {r['part']} at its seat ({r.get('overlap_mm3') or 0:.3f} mm³)")
                    else:
                        msgs.append(f"{k} against {r['part']}: {r['state']} ({r.get('error', '')})")
                ps = list(dict.fromkeys([k for k, _ in blocked] + [r["part"] for _, r in blocked]))
                checks.append(Check(f"step:{o}:insert", "fail", f"moving in along {s['direction']}: " +
                                    "; ".join(msgs), ps, ev))
            else:
                msg = f"{s['fit']} goes in along {s['direction']} clear of {len(present)} present part(s)"
                if slides:
                    msg += f", touching {', '.join(slides)}"
                checks.append(Check(f"step:{o}:insert", "pass", msg, inst, ev))

        # tools for the fasteners driven here
        if options.tool_access:
            if s["tool"] and not here:
                checks.append(Check(f"step:{o}:tool", "warn", f"tool {s['tool']!r} declared but the step installs "
                                    "no fastener: nothing to reach", [s["fit"]]))
                not_checked.append({"step": o, "what": "tool", "reason": "no fastener installed at the step"})
            stepd = {"order": o, "fit": s["fit"]}
            tool_rows = []
            pres = present_at(stepd, step_list, names, specs, kinds) if here else []
            for n in here:
                sp = specs[n]
                tool_name = sp.tool or s["tool"]
                for i in range(len(sp.axes)):
                    ik = sp.instance_key(i)
                    res = world.tool(sp, i, tool_name, tools.get(tool_name), pres, stepd)
                    c = tool_check(f"step:{o}:tool:{ik}", ik, sp, res)
                    checks.append(c)
                    tool_rows.append({"fastener": ik, "tool": tool_name, "status": c.status})
            if tool_rows:
                row["tools"] = tool_rows

        # service: pull each instance back out of the finished assembly past the parts fitted later
        chosen = [k for k in inst if service_set is None or k in service_set or owner(k) in service_set
                  or s["fit"] in service_set]
        if service_on and chosen and d is not None:
            # what goes in at or after this step (fasteners driven here come after the part); parts no step
            # brings in are not "fitted later" and are listed in not_checked instead
            later = [k for k in names if k not in inst and (installed_at.get(k) if (kinds[k] == "fastener" or
                                                                                   k in installed_at)
                                                            else first_fit.get(k)) is not None and k not in present]
            own = {sp.instance_key(i) for sp in specs.values() for i in range(len(sp.axes))
                   if owner(s["fit"]) in sp.stack + [sp.into] or s["fit"] in sp.stack + [sp.into]}
            for k in chosen:
                first, own_hit, undecided = [], [], []
                for q in later:
                    r = sweep_pair(world, k, d, q, options=options, tol=tol, seat=False)
                    if r["state"] in ("unknown", "unchecked"):
                        undecided.append({"part": q, "state": r["state"], "error": r.get("error")})
                    elif r["state"] != "clear":
                        (own_hit if q in own else first).append(q)
                ev = {"remove_first": first, "own_fasteners_first": own_hit, "direction": list(d)}
                if undecided:
                    ev["undecided"] = undecided
                    checks.append(Check(f"service:{k}", "warn", f"removal of {k} not decided against "
                                        f"{', '.join(u['part'] for u in undecided)}" +
                                        (f"; {', '.join(first)} (fitted later) must come off first" if first else ""),
                                        [k] + first + [u["part"] for u in undecided], ev))
                elif first:
                    checks.append(Check(f"service:{k}", "warn", f"to pull {k} out along {s['direction']} reversed, "
                                        f"{', '.join(first)} (fitted later) must come off first", [k] + first, ev))
                else:
                    checks.append(Check(f"service:{k}", "pass", f"{k} comes out once " +
                                        (f"its fasteners ({', '.join(sorted(own_hit))}) are out" if own_hit
                                         else "nothing is in its way"), [k], ev))
        rows.append(row)
    return {"checks": checks, "steps": rows, "exclusions": list(exclusions.values()), "not_checked": not_checked}


# ------------------------------------------------------------------------------------------ gate

def assembly_gate(assembly: Any, steps: Iterable[Any], *, fasteners: Any = None,
                  tools: Optional[Mapping[str, Any]] = None, options: AccessOptions = AccessOptions(),
                  tol: Optional[Tolerances] = None, cache: Any = None,
                  intended_overlaps: Iterable[Mapping[str, Any]] = (), service: Any = False,
                  out: Any = None, subassemblies: Optional[Mapping[str, Any]] = None,
                  service_after: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Run the assembly-access gate on an ``Assembly`` and return (with ``out``, also write, plus a ``.md`` table
    beside it) the verdict.

    ``steps``: ``BuildResult.steps``, the dossier's ``AssemblyStep`` list or mappings (``order``, ``fit``,
    ``onto``, ``direction``, ``tool``, ``fasteners``). ``fasteners``: ``{name: FastenerSpec | mapping}``
    (``fasteners_from_build``). ``tools``: ``{name: envelope}`` (``fasteners.tool_envelope``).
    ``intended_overlaps``: ``[{parts, reason}]`` pairs left out of the insertion sweep (a press fit, a heat-set
    insert), each listed as an exclusion. ``service``: True, or a list of part names, to check removal for
    service (warnings)."""
    tol = tol or Tolerances()
    world = AssemblySequenceWorld(assembly, tol, cache)
    res = run_sequence(world, steps, fasteners, tools=tools, options=options, tol=tol,
                       intended_overlaps=intended_overlaps, service=service, subassemblies=subassemblies,
                       service_after=service_after)
    limits = {f.name: getattr(options, f.name) for f in fields(options)}
    limits.update(touch_mm=tol.touch_mm, overlap_mm3=tol.overlap_mm3, service=bool(service))
    assumptions = list(ASSUMPTIONS)
    extra = {}
    if subassemblies is not None or service_after is not None:
        from cadagent.gates.subassembly import ASSUMPTIONS as SUBASSEMBLY_ASSUMPTIONS
        assumptions += SUBASSEMBLY_ASSUMPTIONS
        limits.update(rigid_subassemblies=True, conditional_service=bool(service_after),
                      prerequisite_removal_verified=False)
        extra = {"subassemblies": res.get("subassemblies", {}), "service_after": res.get("service_after", {})}
    data = verdict(GATE, res["checks"], assumptions=assumptions, limits=limits, exclusions=res["exclusions"],
                   extra={"steps": res["steps"], "not_checked": res["not_checked"], "world_stats": world.stats,
                          "tools": dict(tools or {}), **extra})
    if out is not None:
        path = write_verdict(out, data)
        path.with_suffix(".md").write_text("# Assembly sequence\n\n" + steps_markdown(data))
    return data


def steps_from(result: Any = None, dossier: Any = None) -> List[Dict[str, Any]]:
    """The assembly steps of a build (``BuildResult.steps`` or the geometry record's), plus the dossier's YAML
    steps whose order the build does not declare (the lint reports steps that disagree)."""
    built = list(getattr(result, "steps", None) or ((getattr(result, "geometry", None) or
                                                      (result if isinstance(result, Mapping) else {}))
                                                     .get("assembly") or {}).get("steps") or [])
    out = normalise_steps(built)
    seen = {s["order"] for s in out}
    if dossier is not None:
        out += [s for s in normalise_steps(getattr(dossier, "assembly", None) or []) if s["order"] not in seen]
    return normalise_steps(out)


def assembly_from_build(result: Any, dossier: Any = None, extra: Optional[Mapping[str, Any]] = None, *,
                        assembly: Any = None, **kwargs: Any) -> Dict[str, Any]:
    """The gate on a dossier build: steps from ``steps_from``, fasteners from ``fasteners_from_build``, tools
    from ``tools_from``, intended overlaps from the dossier's ``gates:`` and ``extra``; ``assembly`` defaults to
    ``Assembly.from_build(result)``. Other keyword arguments go to ``assembly_gate``."""
    from cadagent.gates.relations import Assembly
    asm = assembly if assembly is not None else Assembly.from_build(result)
    overlaps = list((extra or {}).get("intended_overlaps") or [])
    if dossier is not None:
        overlaps += [{"parts": list(p.parts), "reason": p.reason} for p in dossier.gates.intended_overlaps]
    kwargs.setdefault("intended_overlaps", overlaps)
    return assembly_gate(asm, steps_from(result, dossier), fasteners=fasteners_from_build(result, dossier, extra),
                         tools=tools_from(dossier, extra), **kwargs)


def steps_markdown(data: Mapping[str, Any]) -> str:
    """The verdict's step table as Markdown: order, fit, onto, direction, parts present, the closest clearance,
    what it touches on the way, the fasteners driven and their tools, and the status."""
    status: Dict[Any, str] = {}
    for c in data.get("checks") or []:
        parts = c["id"].split(":")
        if parts[0] == "step" and len(parts) >= 3:
            try:
                o = int(parts[1])
            except ValueError:
                continue
            prev = status.get(o, "pass")
            status[o] = "fail" if "fail" in (prev, c["status"]) else ("warn" if "warn" in (prev, c["status"])
                                                                     else "pass")
    lines = ["| Step | Fit | Onto | Direction | Present | Clearance (mm) | Touching | Fasteners | Tool | Status |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in data.get("steps") or []:
        tools = ", ".join(f"{t['fastener']}: {t['status']}" for t in r.get("tools") or [])
        mc, lo = r.get("min_clearance_mm"), r.get("clearance_at_least_mm")
        if isinstance(mc, (int, float)) and isinstance(lo, (int, float)) and lo < mc - 5e-3:
            mc = f"{lo:.2f}..{mc:.2f}"
        else:
            mc = f"{mc:.2f}" if isinstance(mc, (int, float)) else (f"≥ {lo:.2f}" if isinstance(lo, (int, float))
                                                                   else "-")
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            r["order"], r["fit"], ", ".join(r.get("onto") or []) or "-", r.get("direction") or "-",
            r.get("present", "-"), mc,
            ", ".join(r.get("touching") or []) or "-", ", ".join(r.get("installs") or []) or "-",
            (r.get("tool") or "-") + (f" ({tools})" if tools else ""), status.get(r["order"], "pass")))
    blocked = [(r["order"], b) for r in data.get("steps") or [] for b in r.get("blocked") or []]
    if blocked:
        lines += ["", "Blocked:", ""]
        for o, b in blocked:
            what = (f"{b['instance']} meets {b['part']} {b['first_contact_mm'][1]:.2f} mm before its seat"
                    if b["state"] == "blocked" else f"{b['instance']}: {b['state']} against {b['part']}")
            lines.append(f"- step {o}: {what}")
    for name, internal in (data.get("subassemblies") or {}).items():
        lines += ["", f"## Internal assembly: {name}", "",
                  "Members: " + ", ".join(internal["members"]), "", steps_markdown(internal)]
    if data.get("service_after"):
        lines += ["", "## Conditional service removal", "",
                  "Prerequisites are assumed already removed; their removal and tool access are not proved.", ""]
        for name, evidence in data["service_after"].items():
            lines.append(f"- {name}: after removing {', '.join(evidence['assumed_removed']) or 'nothing'}; "
                         f"withdrawal {evidence['status']}.")
    return "\n".join(lines) + "\n"


__all__ = ["AccessOptions", "SequenceWorld", "AssemblySequenceWorld", "assembly_gate", "assembly_from_build",
           "run_sequence", "sweep_pair", "direction_vector", "normalise_steps", "steps_from", "steps_markdown",
           "ASSUMPTIONS", "GATE"]
