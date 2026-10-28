"""Motion-range interference: pose every declared joint across its range and look for collisions.

For each joint with a range (``revolute``, ``slider``, ``cylindrical``), the moving body is posed at
sampled values across the range, both ends included, and every part that moves is related to every
part it moves against (``cadagent.gates.relations``: apart / touching / overlapping / contains):

* **Bodies.** What moves with a joint is its ``moving`` part's body: the transitive closure over
  ``fixed`` joints and fastener ``clamps``/``into`` (``relations.moving_bodies``, set by
  ``Assembly.from_build``), or the body labels of a hand-built ``Assembly``.
* **Chains.** A joint whose ``fixed`` part lies in another joint's moving body is that joint's
  child: it rides on the parent, and the two are sampled together on a grid (every parent sample
  times every child sample). Independent joints are sampled one at a time with the others held at
  home; ``combine=[[...]]`` grids independent joints too. Home is 0 (the pose the model was built
  in), clamped into the range.
* **Pairs.** Per pose, a moving part against every part outside its body (the static frame, other
  bodies). Pairs that never move relative to each other (static against static, parts of one
  body) are the same in every pose and are never queried here: the relation table and the
  connectivity gate cover them. Broad phase: each part's home box, its 8 corners moved with the
  pose (a box that encloses the moved part), against ``near_mm``. Narrow phase: the exact relation,
  memoised in memory and through ``cache`` (a ``PairCache``) on both parts' content hash and posed
  placement, so a pose seen before costs nothing and an unchanged rerun reads the cache.
* **Verdicts per pair.** Shared volume (``overlapping``/``contains``) is a collision and fails,
  unless the pair is a declared intended overlap. A joint's ``intended_contacts`` (and its own
  ``moving``/``fixed`` pair, the bearing) may touch; shared volume between them beyond
  ``overlap_mm3`` still fails (a stop driven into its face). Touching anything else is a warning
  (``strict_contacts=True`` fails it). ``unknown`` fails.
* **Witnesses.** For each colliding pair: the colliding pose nearest home (met first moving out
  from rest), the overlap volume, centroid and box there, and its clear grid neighbour nearest
  home with the gap and the two closest points. The boundary between the two is bisected along
  their axis (``refine_steps``) to bracket the onset.
* **Density.** Per joint axis: the samples, the step (deg or mm between samples) and, for a
  rotation, the largest travel of any point of the carried parts between two samples (step × the
  largest distance of their boxes' corners from the axis over the sampled poses, a child joint's
  motion included). Anything thinner than that travel, or a
  contact that starts and ends between two samples, can be missed: sampling is not a swept volume.

Containment per pose (``contains=``): every ``contains`` declaration whose container or contents
are moved by a joint group is checked by ``containment_gate`` at that group's poses.

Kernel-free core: ``run_motion(world, joints, ...)`` works on any object with the ``World`` methods
(names, body labels, home boxes and a ``relate`` per pose), which is how the rules are tested
without CadQuery. ``motion_gate(assembly, ...)`` wraps an ``Assembly``.
"""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from cadagent.gates.cache import PairCache, matrix_key
from cadagent.gates.relations import Relation, Tolerances
from cadagent.gates.verdict import Check, verdict, write_verdict

GATE = "motion"
RANGED = ("revolute", "slider", "cylindrical")
UNSAMPLED = ("planar", "ball")
DEFAULT_SAMPLES = 12
DEFAULT_MAX_POSES = 2000
IDENTITY: Tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)

ASSUMPTIONS = [
    "joints are sampled at discrete values across their declared ranges, both ends included; the density is "
    "reported per joint axis. A collision that starts and ends between two samples, or a feature thinner than the "
    "travel per sample, can be missed: this is not a swept-volume check",
    "a joint's range is measured from the pose the model was built in (0 = as modelled); a joint's axis is in "
    "assembly coordinates at that pose, and a child joint's axis is carried by its parent",
    "what moves with a joint is its moving part's body: the transitive closure over fixed joints and fastener "
    "clamps/into (relations.moving_bodies), or the assembly's own body labels",
    "joints in one chain are sampled on a grid; independent joints one at a time with the others at home "
    "(0 clamped into the range) unless combined",
    "pairs that do not move relative to each other (static against static, parts of one body) are not queried; "
    "the relation table and connectivity gate cover them",
    "exact B-rep relations within the relation tolerances; no tolerance stack, print shrink, deflection or "
    "backlash: a clear pose in the model does not prove the printed parts clear",
]


# ----------------------------------------------------------------------------- 3x4 rigid transforms

def _mul(a: Sequence[float], b: Sequence[float]) -> Tuple[float, ...]:
    """``a · b`` for 3x4 row-major rigid transforms (``b`` applied first)."""
    out = []
    for r in range(3):
        ar = a[4 * r:4 * r + 4]
        for c in range(4):
            v = ar[0] * b[c] + ar[1] * b[4 + c] + ar[2] * b[8 + c]
            out.append(v + (ar[3] if c == 3 else 0.0))
    return tuple(out)


def _apply(m: Sequence[float], p: Sequence[float]) -> Tuple[float, float, float]:
    return tuple(m[4 * r] * p[0] + m[4 * r + 1] * p[1] + m[4 * r + 2] * p[2] + m[4 * r + 3]
                 for r in range(3))  # type: ignore[return-value]


def rotation(origin: Sequence[float], direction: Sequence[float], degrees: float) -> Tuple[float, ...]:
    """Right-handed rotation by ``degrees`` about the axis through ``origin`` along ``direction``."""
    n = math.sqrt(sum(c * c for c in direction))
    x, y, z = (c / n for c in direction)
    t = math.radians(degrees)
    c, s, k = math.cos(t), math.sin(t), 1 - math.cos(t)
    r = (c + x * x * k, x * y * k - z * s, x * z * k + y * s,
         y * x * k + z * s, c + y * y * k, y * z * k - x * s,
         z * x * k - y * s, z * y * k + x * s, c + z * z * k)
    o = origin
    ro = [r[3 * i] * o[0] + r[3 * i + 1] * o[1] + r[3 * i + 2] * o[2] for i in range(3)]
    return (r[0], r[1], r[2], o[0] - ro[0], r[3], r[4], r[5], o[1] - ro[1], r[6], r[7], r[8], o[2] - ro[2])


def translation(direction: Sequence[float], mm: float) -> Tuple[float, ...]:
    """Translation by ``mm`` along ``direction``."""
    n = math.sqrt(sum(c * c for c in direction))
    d = [c / n * mm for c in direction]
    return (1.0, 0.0, 0.0, d[0], 0.0, 1.0, 0.0, d[1], 0.0, 0.0, 1.0, d[2])


def moved_box(box: Sequence[float], m: Sequence[float]) -> Tuple[float, ...]:
    """The axis-aligned box of ``box``'s 8 corners moved by ``m``: it encloses the moved part."""
    if tuple(m) == IDENTITY:
        return tuple(box)
    pts = [_apply(m, (x, y, z)) for x in (box[0], box[3]) for y in (box[1], box[4]) for z in (box[2], box[5])]
    return tuple(min(p[i] for p in pts) for i in range(3)) + tuple(max(p[i] for p in pts) for i in range(3))


def box_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Distance between two axis-aligned boxes (0 when they overlap): a lower bound on the parts' gap."""
    sep = [max(0.0, a[i] - b[i + 3], b[i] - a[i + 3]) for i in range(3)]
    return math.sqrt(sum(s * s for s in sep))


def _union(a: Optional[Sequence[float]], b: Sequence[float]) -> Tuple[float, ...]:
    if a is None:
        return tuple(b)
    return tuple(min(a[i], b[i]) for i in range(3)) + tuple(max(a[i + 3], b[i + 3]) for i in range(3))


# ----------------------------------------------------------------------------- joints

@dataclass(frozen=True)
class Dof:
    """One sampled axis of a joint: a rotation (deg) or a slide (mm) about/along the joint axis."""
    joint: str
    kind: str            # "rotate" | "slide"
    lo: float
    hi: float
    samples: int

    @property
    def unit(self) -> str:
        return "deg" if self.kind == "rotate" else "mm"

    @property
    def home(self) -> float:
        return min(max(0.0, self.lo), self.hi)

    def values(self, n: Optional[int] = None) -> List[float]:
        n = self.samples if n is None else n
        if self.hi == self.lo or n < 2:
            return [float(self.lo)]          # a zero-length range is one pose
        return [self.lo + (self.hi - self.lo) * i / (n - 1) for i in range(n)]

    def step(self, n: Optional[int] = None) -> float:
        n = self.samples if n is None else n
        return 0.0 if n < 2 or self.hi == self.lo else (self.hi - self.lo) / (n - 1)


@dataclass
class Joint:
    """A joint normalised from a dossier build's ``joints`` entry or a hand-written mapping."""
    id: str
    kind: str
    moving: str
    fixed: str
    origin: Tuple[float, float, float]
    direction: Tuple[float, float, float]
    dofs: List[Dof] = field(default_factory=list)
    intended_contacts: List[Tuple[str, str]] = field(default_factory=list)

    def transform(self, values: Sequence[float]) -> Tuple[float, ...]:
        """The joint's motion (in assembly coordinates at home) for one value per dof."""
        m = IDENTITY
        for dof, v in zip(self.dofs, values):
            step = rotation(self.origin, self.direction, v) if dof.kind == "rotate" else translation(self.direction, v)
            m = _mul(step, m)
        return m

    @classmethod
    def coerce(cls, jid: str, data: Mapping[str, Any], *, samples: Optional[int] = None,
               default_samples: int = DEFAULT_SAMPLES, max_step_deg: Optional[float] = None,
               max_step_mm: Optional[float] = None) -> "Joint":
        """From ``{kind, moving, fixed, axis, range, unit, range_mm, intended_contacts, samples}`` (the build
        record; ``axis`` an ``Axis``, ``{origin, direction}`` or ``(origin, direction)``), or the registry's
        spelling (``parts=(moving, fixed)``, ``range_deg``, ``range_mm``)."""
        kind = str(data.get("kind") or "revolute")
        moving, fixed = data.get("moving"), data.get("fixed")
        if (moving is None or fixed is None) and data.get("parts"):
            moving, fixed = list(data["parts"])[:2]
        axis = data.get("axis")
        if hasattr(axis, "origin") and hasattr(axis, "direction"):
            origin, direction = axis.origin, axis.direction
        elif isinstance(axis, Mapping):
            origin, direction = axis.get("origin"), axis.get("direction")
        elif isinstance(axis, (list, tuple)) and len(axis) == 2:
            origin, direction = axis
        else:
            origin, direction = (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
            if kind in RANGED:
                raise ValueError(f"joint {jid!r}: no axis")
        origin = tuple(float(c) for c in origin)
        direction = tuple(float(c) for c in direction)
        if len(origin) != 3 or len(direction) != 3 or not any(direction):
            raise ValueError(f"joint {jid!r}: the axis needs an origin and a non-zero direction")
        rdeg = data.get("range_deg")
        rmm = data.get("range_mm")
        rng, unit = data.get("range"), data.get("unit")
        if rng is not None:            # the build record: ``range`` in ``unit`` (deg, or mm for a slider)
            unit = unit or ("mm" if kind == "slider" else "deg")
            if unit not in ("deg", "mm"):
                raise ValueError(f"joint {jid!r}: unit must be deg or mm, got {unit!r}")
            if unit == "deg" and rdeg is None:
                rdeg = rng
            elif unit == "mm" and rmm is None:
                rmm = rng
        need = {"revolute": ("deg",), "slider": ("mm",), "cylindrical": ("deg", "mm")}.get(kind, ())
        have = tuple(u for u, r in (("deg", rdeg), ("mm", rmm)) if r is not None)
        if kind in RANGED and set(have) != set(need):
            missing = [u for u in need if u not in have]
            extra = [u for u in have if u not in need]
            why = (f"needs a range in {' and '.join(missing)}" if missing else "") + \
                  ("; " if missing and extra else "") + (f"has a range in {' and '.join(extra)} it cannot use"
                                                         if extra else "")
            raise ValueError(f"joint {jid!r} ({kind}) {why}")
        n = samples if samples is not None else data.get("samples")
        n = int(n) if n is not None else int(default_samples)
        if n < 2:
            raise ValueError(f"joint {jid!r}: samples must be at least 2")
        dofs = []
        for want, r, kd, cap in (("deg", rdeg, "rotate", max_step_deg), ("mm", rmm, "slide", max_step_mm)):
            if want not in need:
                continue
            lo, hi = sorted(float(v) for v in r)
            k = n
            if cap and hi > lo:
                k = max(k, int(math.ceil((hi - lo) / cap - 1e-9)) + 1)
            dofs.append(Dof(jid, kd, lo, hi, k if hi > lo else 1))
        contacts = [(str(a), str(b)) for a, b in (data.get("intended_contacts") or [])]
        return cls(jid, kind, str(moving), str(fixed), origin, direction, dofs, contacts)


# ----------------------------------------------------------------------------- the world (kernel or fake)

class World:
    """What the motion core needs from an assembly. ``AssemblyWorld`` is the kernel one; tests use boxes.

    * ``names``: part keys; ``body(key)``: its rigid-body label; ``box(key)``: its home AABB;
    * ``relate(mats, a, b)``: the ``Relation`` of parts ``a`` and ``b`` with each body in ``mats``
      (``{body: 3x4 transform}``) moved by its transform after its home placement;
    * ``stats``: counters merged into the verdict.
    """
    names: List[str]

    def body(self, key: str) -> str:
        raise NotImplementedError

    def box(self, key: str) -> Sequence[float]:
        raise NotImplementedError

    def relate(self, mats: Mapping[str, Sequence[float]], a: str, b: str) -> Relation:
        raise NotImplementedError

    @property
    def stats(self) -> Dict[str, Any]:
        return {}


class AssemblyWorld(World):
    """An ``Assembly`` posed per body, with relations memoised in memory and through a ``PairCache``."""

    def __init__(self, assembly: Any, tol: Tolerances = Tolerances(), cache: Optional[PairCache] = None):
        from cadagent.gates.relations import bounding_box
        self.assembly, self.tol, self.cache = assembly, tol, cache
        self.names = list(assembly.names)
        self._boxes = {n: bounding_box(assembly.shape(n)) for n in self.names}
        self._memo: Dict[Tuple[str, ...], Relation] = {}
        self._volumes: Dict[str, float] = {}
        self._posed: Tuple[Optional[Tuple], Any] = (None, None)
        self.kernel_queries = self.memo_hits = self.cache_hits = 0
        if cache is not None:          # hash moving candidates once, before posed copies are made
            for n in self.names:
                assembly[n].content_hash

    def body(self, key: str) -> str:
        return self.assembly[key].body

    def box(self, key: str) -> Sequence[float]:
        return self._boxes[key]

    def _asm(self, mats: Mapping[str, Sequence[float]]):
        key = tuple(sorted((b, matrix_key(m)) for b, m in mats.items()))
        if self._posed[0] != key:
            asm = self.assembly
            for b, m in sorted(mats.items()):
                if tuple(m) != IDENTITY:
                    asm = asm.posed(b, [m[0:4], m[4:8], m[8:12]])
            self._posed = (key, asm)
        return self._posed[1]

    def relate(self, mats: Mapping[str, Sequence[float]], a: str, b: str) -> Relation:
        from cadagent.gates.relations import _relate_items
        asm = self._asm(mats)
        memo = (a, b, matrix_key(asm[a].matrix), matrix_key(asm[b].matrix))
        if memo in self._memo:
            self.memo_hits += 1
            return self._memo[memo]
        rel = _relate_items(asm, a, b, self.tol, self.cache, False, self._volumes)
        if rel.cached:
            self.cache_hits += 1
        else:
            self.kernel_queries += 1
        self._memo[memo] = rel
        return rel

    @property
    def stats(self) -> Dict[str, Any]:
        return {"kernel_queries": self.kernel_queries, "memo_hits": self.memo_hits, "cache_hits": self.cache_hits}


# ----------------------------------------------------------------------------- planning

def _owner(key: str) -> str:
    return key.split("#", 1)[0]


def _keys(names: Iterable[str], name: str) -> List[str]:
    return [k for k in names if k == name or _owner(k) == name]


def _pair_id(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def _matches(pairs: Iterable[frozenset], a: str, b: str) -> bool:
    for p in pairs:
        if len(p) != 2:
            continue
        x, y = tuple(p)
        if (x in (a, _owner(a)) and y in (b, _owner(b))) or (x in (b, _owner(b)) and y in (a, _owner(a))):
            return True
    return False


@dataclass
class _Group:
    id: str
    joints: List[str]                      # root first, then descendants (parents before children)
    axes: List[Dof]                        # the grid axes, in joint order
    counts: List[int]                      # samples per axis actually used
    coarsened: bool = False


def _fmt(v: float) -> str:
    return f"{round(v, 6):g}"


def _label(group: _Group, values: Sequence[float]) -> str:
    return ",".join(f"{a.joint}={_fmt(v)}{a.unit}" for a, v in zip(group.axes, values))


# ----------------------------------------------------------------------------- the core

def run_motion(world: World, joints: Mapping[str, Any], *, tol: Tolerances = Tolerances(),
               samples: Optional[Mapping[str, int]] = None, default_samples: int = DEFAULT_SAMPLES,
               max_step_deg: Optional[float] = None, max_step_mm: Optional[float] = None,
               combine: Iterable[Sequence[str]] = (), intended_contacts: Iterable[Sequence[str]] = (),
               intended_overlaps: Iterable[Mapping[str, Any]] = (), ignore_pairs: Iterable[Any] = (),
               strict_contacts: bool = False, refine_steps: int = 8, max_poses: int = DEFAULT_MAX_POSES,
               containment: Optional[Callable[[str, Dict[str, Dict[str, Sequence[float]]], List[str]],
                                              Tuple[List[Check], List[str]]]] = None) -> Dict[str, Any]:
    """The motion gate on any ``World``; returns the verdict dict (see ``motion_gate`` for the options).

    ``containment(group_id, poses, moved_bodies)``, when given, is called once per group with
    ``{pose_label: {body: transform}}`` and returns extra checks plus ``not_checked`` lines."""
    t0 = time.perf_counter()
    combine = [list(c) for c in combine]
    checks: List[Check] = []
    not_checked: List[str] = []
    names = list(world.names)
    samples = dict(samples or {})
    excl = [dict(e) for e in intended_overlaps]
    for e in excl:
        if len(set(e.get("parts", ()))) != 2:
            raise ValueError(f"an intended overlap names two parts: {e!r}")
    overlap_pairs = [frozenset(e["parts"]) for e in excl]
    ignore = [frozenset(p.get("parts", ()) if isinstance(p, Mapping) else p) for p in ignore_pairs]
    global_contacts = [frozenset(p) for p in intended_contacts]

    # -- joints and their bodies
    js: Dict[str, Joint] = {}
    body_of_joint: Dict[str, List[str]] = {}
    for jid in sorted(joints):
        raw = joints[jid]
        kind = str(raw.get("kind") or "revolute")
        if kind == "fixed":
            continue
        if kind in UNSAMPLED:
            not_checked.append(f"joint {jid} ({kind}): no range to sample; its motion is not checked")
            checks.append(Check(f"joint:{jid}", "warn", f"{kind} joint {jid} has no declared range, so its motion "
                                "is not sampled", [str(raw.get("moving") or "")]))
            continue
        try:
            j = Joint.coerce(jid, raw, samples=samples.get(jid), default_samples=default_samples,
                             max_step_deg=max_step_deg, max_step_mm=max_step_mm)
        except (ValueError, TypeError) as exc:
            checks.append(Check(f"joint:{jid}", "fail", f"joint {jid} cannot be sampled: {exc}"))
            continue
        if kind not in RANGED or not j.dofs:
            checks.append(Check(f"joint:{jid}", "fail", f"joint {jid} ({kind}) has no range to sample",
                                [j.moving]))
            continue
        for d in j.dofs:
            if d.hi == d.lo:
                checks.append(Check(f"range:{jid}:{d.unit}", "warn", f"joint {jid}'s {d.unit} range is "
                                    f"{_fmt(d.lo)}..{_fmt(d.hi)}: one pose, no motion along it", [j.moving]))
        mk, fk = _keys(names, j.moving), _keys(names, j.fixed)
        problems = []
        if not mk:
            problems.append(f"its moving part {j.moving!r} is not in the assembly")
        if not fk:
            problems.append(f"its fixed part {j.fixed!r} is not in the assembly")
        bodies = sorted({world.body(k) for k in mk})
        if fk and set(bodies) & {world.body(k) for k in fk}:
            problems.append(f"its fixed part {j.fixed} is in the moving body {bodies[0]}, so nothing moves "
                            "relative to it")
        for other, ob in body_of_joint.items():
            if set(ob) & set(bodies):
                problems.append(f"joint {other} already moves body {sorted(set(ob) & set(bodies))[0]}")
        if problems:
            checks.append(Check(f"joint:{jid}", "fail", f"joint {jid} cannot be posed: " + "; ".join(problems),
                                [j.moving, j.fixed]))
            continue
        js[jid] = j
        body_of_joint[jid] = bodies

    # -- the kinematic tree: a joint whose fixed part rides on another joint's body is its child
    parent: Dict[str, Optional[str]] = {}
    for jid, j in js.items():
        fixed_bodies = {world.body(k) for k in _keys(names, j.fixed)}
        owners = [o for o, b in body_of_joint.items() if o != jid and o in js and set(b) & fixed_bodies]
        parent[jid] = owners[0] if owners else None
    for jid in sorted(js):
        if jid not in js:
            continue
        seen, cur = [jid], parent[jid]
        while cur is not None and cur in js and cur not in seen:
            seen.append(cur)
            cur = parent.get(cur)
        if cur is not None and cur in seen:
            loop = seen[seen.index(cur):]
            for x in loop:
                checks.append(Check(f"joint:{x}", "fail", f"joints {' -> '.join(loop + [loop[0]])} carry each other "
                                    "in a loop", [js[x].moving]))
            for x in loop:
                js.pop(x)
                body_of_joint.pop(x, None)
    changed = True
    while changed:                      # a joint riding on one that cannot be posed cannot be posed either
        changed = False
        for jid in sorted(js):
            p = parent.get(jid)
            if p is not None and p not in js:
                checks.append(Check(f"joint:{jid}", "fail", f"joint {jid} rides on joint {p}, which cannot be posed",
                                    [js[jid].moving]))
                js.pop(jid)
                body_of_joint.pop(jid, None)
                changed = True
    parent = {k: v for k, v in parent.items() if k in js}

    def root(jid: str) -> str:
        while parent.get(jid) is not None:
            jid = parent[jid]
        return jid

    groups_of: Dict[str, List[str]] = {}
    for jid in sorted(js):
        groups_of.setdefault(root(jid), []).append(jid)
    merged: Dict[str, str] = {r: r for r in groups_of}

    def find(r: str) -> str:
        while merged[r] != r:
            r = merged[r]
        return r

    for combo in combine:
        roots = []
        for jid in combo:
            if jid not in js:
                checks.append(Check(f"combine:{jid}", "fail", f"combine names {jid!r}, which is not a sampled joint"))
                continue
            roots.append(find(root(jid)))
        for r in roots[1:]:
            merged[find(r)] = find(roots[0])
    members: Dict[str, List[str]] = {}
    for r in groups_of:
        members.setdefault(find(r), []).extend(groups_of[r])

    def depth(jid: str) -> int:
        d = 0
        while parent.get(jid) is not None:
            jid, d = parent[jid], d + 1
        return d

    groups: List[_Group] = []
    for r in sorted(members):
        order = sorted(members[r], key=lambda j: (depth(j), j))
        axes = [d for j in order for d in js[j].dofs]
        counts = [a.samples for a in axes]
        coarsened = False
        if math.prod(counts) > max_poses:
            moving_axes = sum(1 for c in counts if c > 1)
            per = max(2, int(max_poses ** (1.0 / moving_axes) + 1e-9))
            counts = [min(c, per) for c in counts]
            coarsened = True
        groups.append(_Group("+".join(order), order, axes, counts, coarsened))

    def home_values(jid: str) -> List[float]:
        return [d.home for d in js[jid].dofs]

    def world_mats(values: Mapping[str, Sequence[float]]) -> Dict[str, Tuple[float, ...]]:
        """{body: transform} for every posed joint, children carried by their parents."""
        cache: Dict[str, Tuple[float, ...]] = {}

        def w(jid: str) -> Tuple[float, ...]:
            if jid not in cache:
                local = js[jid].transform(values.get(jid) or home_values(jid))
                p = parent.get(jid)
                cache[jid] = _mul(w(p), local) if p is not None else local
            return cache[jid]

        out: Dict[str, Tuple[float, ...]] = {}
        for jid in js:
            for b in body_of_joint[jid]:
                out[b] = w(jid)
        return out

    body_keys: Dict[str, List[str]] = {}
    for k in names:
        body_keys.setdefault(world.body(k), []).append(k)

    # -- sample and query
    group_rows: List[Dict[str, Any]] = []
    swept: Dict[str, Dict[str, Tuple[float, ...]]] = {}
    poses_total = candidates_total = 0
    for g in groups:
        moving_bodies_g = sorted({b for j in g.joints for b in body_of_joint[j]})
        moving_keys = [k for b in moving_bodies_g for k in body_keys.get(b, [])]
        others = [k for k in names if world.body(k) not in moving_bodies_g]
        intended = list(global_contacts)
        for jid in g.joints:
            intended += [frozenset(p) for p in js[jid].intended_contacts]
            intended.append(frozenset((js[jid].moving, js[jid].fixed)))
        grid = [a.values(c) for a, c in zip(g.axes, g.counts)]
        poses = list(itertools.product(*grid))
        poses_total += len(poses)

        def values_of(vals: Sequence[float]) -> Dict[str, List[float]]:
            out: Dict[str, List[float]] = {}
            i = 0
            for jid in g.joints:
                n = len(js[jid].dofs)
                out[jid] = list(vals[i:i + n])
                i += n
            return out

        def carried_rel(vals: Dict[str, List[float]], ancestor: str, jid: str) -> Tuple[float, ...]:
            """The motion of ``jid``'s body relative to ``ancestor``'s moving frame (children below it)."""
            m = IDENTITY
            while jid != ancestor:
                m = _mul(js[jid].transform(vals.get(jid) or home_values(jid)), m)
                jid = parent[jid]  # type: ignore[assignment]
            return m

        carried = {i: [(jj, k) for jj in g.joints if _carries(parent, a.joint, jj)
                       for b in body_of_joint[jj] for k in body_keys.get(b, [])]
                   for i, a in enumerate(g.axes) if a.kind == "rotate"}
        radius = {i: 0.0 for i in carried}
        pair_rows: Dict[Tuple[str, str], List[Tuple[int, Relation]]] = {}
        min_box: Dict[str, Any] = {}
        pose_mats: Dict[str, Dict[str, Tuple[float, ...]]] = {}
        for pi, vals in enumerate(poses):
            vmap = values_of(vals)
            mats = world_mats(vmap)
            pose_mats[_label(g, vals)] = {b: mats[b] for b in moving_bodies_g}
            for i, rows_c in carried.items():         # how far the carried parts reach from this axis, in this pose
                j = js[g.axes[i].joint]
                for jj, k in rows_c:
                    rel = carried_rel(vmap, j.id, jj)
                    radius[i] = max(radius[i], _radius(moved_box(world.box(k), rel), j.origin, j.direction))
            boxes = {k: moved_box(world.box(k), mats.get(world.body(k), IDENTITY)) for k in names}
            for k in moving_keys:
                swept.setdefault(g.id, {})[k] = _union(swept.get(g.id, {}).get(k), boxes[k])
            seen = set()
            for a in moving_keys:
                for b in moving_keys + others:
                    if a == b or world.body(a) == world.body(b):
                        continue
                    pair = tuple(sorted((a, b)))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    if _matches(ignore, a, b):
                        continue
                    d = box_distance(boxes[a], boxes[b])
                    if d > tol.near_mm:
                        if not _matches(intended, a, b) and (not min_box or d < min_box["mm"]):
                            min_box = {"mm": round(d, 6), "pair": list(pair), "pose": _label(g, vals)}
                        continue
                    candidates_total += 1
                    rel = world.relate(mats, pair[0], pair[1])
                    pair_rows.setdefault(pair, []).append((pi, rel))

        # -- classify
        collisions, contacts, unknown, touched = [], [], [], {}
        best: Dict[str, Any] = {}
        for pair, rows in sorted(pair_rows.items()):
            a, b = pair
            is_intended = _matches(intended, a, b)
            is_overlap_ok = _matches(overlap_pairs, a, b)
            hits = [(pi, r) for pi, r in rows if r.interferes]
            bad = [(pi, r) for pi, r in rows if r.state in ("unknown", "unchecked")]
            touch = [(pi, r) for pi, r in rows if r.state == "touching"]
            for pi, r in rows:
                if r.state in ("apart", "touching") and not is_intended and r.gap_mm is not None and \
                        (not best or r.gap_mm < best["gap_mm"]):
                    best = {"gap_mm": r.gap_mm, "pair": list(pair), "pose": _label(g, poses[pi]),
                            "point_a": r.witness.get("point_a"), "point_b": r.witness.get("point_b")}
            if bad:
                pi, r = bad[0]
                unknown.append(pair)
                checks.append(Check(f"relation:{_pair_id(a, b)}", "fail",
                                    f"the kernel could not decide {a} against {b} at {_label(g, poses[pi])}: "
                                    f"{r.error or r.state}", [a, b],
                                    {"pose": _label(g, poses[pi]), "poses": len(bad), "relation": r.to_dict()}))
            if hits and not is_overlap_ok:
                collisions.append(pair)
                checks.append(_collision_check(world, g, grid, poses, values_of, world_mats, pair, rows, hits,
                                               is_intended, refine_steps, tol))
            if touch and is_intended:
                touched[_pair_id(a, b)] = {"poses": len(touch), "first": _label(g, poses[touch[0][0]]),
                                           "last": _label(g, poses[touch[-1][0]])}
            elif touch and not hits:
                contacts.append(pair)
                pi, r = touch[0]
                checks.append(Check(f"contact:{_pair_id(a, b)}", "fail" if strict_contacts else "warn",
                                    f"{a} touches {b} at {_label(g, poses[pi])} (and {len(touch) - 1} more poses); "
                                    f"not an intended contact of {g.id}", [a, b],
                                    {"first_pose": _label(g, poses[pi]), "poses": len(touch),
                                     "gap_mm": r.gap_mm, "point_a": r.witness.get("point_a"),
                                     "point_b": r.witness.get("point_b")}))
        density = []
        for a, c in zip(g.axes, g.counts):
            row: Dict[str, Any] = {"joint": a.joint, "axis": a.kind, "unit": a.unit, "range": [a.lo, a.hi],
                                   "samples": c, "declared_samples": a.samples, "step": round(a.step(c), 6)}
            i = len(density)
            if a.kind == "rotate":
                row["max_radius_mm"] = round(radius[i], 3)
                row["max_travel_per_step_mm"] = round(math.radians(a.step(c)) * radius[i], 3)
            else:
                row["max_travel_per_step_mm"] = round(a.step(c), 3)
            density.append(row)
        failed = bool(collisions or unknown or (strict_contacts and contacts))
        text = "; ".join(f"{d['joint']} {d['range'][0]:g}..{d['range'][1]:g} {d['unit']} in {d['samples']} samples "
                         f"({d['step']:g} {d['unit']} apart, up to {d['max_travel_per_step_mm']:g} mm of travel)"
                         for d in density)
        if collisions:
            msg = f"{g.id}: {len(collisions)} colliding pair(s) over {len(poses)} poses ({text})"
        elif unknown:
            msg = f"{g.id}: the kernel could not decide {len(unknown)} pair(s) ({text})"
        else:
            msg = f"{g.id}: no collision in {len(poses)} poses ({text})"
        clearance: Dict[str, Any] = {"min_clearance_mm": best.get("gap_mm"), "at": best or None}
        if min_box and (not best or min_box["mm"] < best["gap_mm"]):
            clearance["unmeasured_gap_at_least_mm"] = min_box["mm"]     # pairs whose boxes stayed beyond near_mm
            clearance["unmeasured_at"] = min_box
        evidence = {"joints": g.joints, "poses": len(poses), "density": density, "coarsened": g.coarsened,
                    "max_poses": max_poses, "moving": moving_keys, "bodies": moving_bodies_g,
                    "intended_contacts": sorted(_pair_id(*sorted(p)) for p in set(intended) if len(p) == 2),
                    "intended_contacts_touching": touched, "collisions": [_pair_id(*p) for p in collisions],
                    **clearance}
        involved = sorted({x for p in collisions for x in p}) or [js[j].moving for j in g.joints]
        checks.append(Check(f"motion:{g.id}", "fail" if failed else "pass", msg, involved, evidence))
        if g.coarsened:
            floor = " (2 per axis is the floor, so this is over max_poses too)" if len(poses) > max_poses else ""
            checks.append(Check(f"density:{g.id}", "warn", f"{g.id}: the full grid of "
                                f"{math.prod(a.samples for a in g.axes)} poses exceeds max_poses={max_poses}; "
                                f"sampled {len(poses)} ({', '.join(str(c) for c in g.counts)} per axis){floor}",
                                [js[j].moving for j in g.joints], {"density": density}))
        group_rows.append({"id": g.id, **{k: v for k, v in evidence.items() if k != "moving"},
                           "status": "fail" if failed else "pass"})
        if containment is not None:
            extra_checks, extra_not = containment(g.id, pose_mats, moving_bodies_g)
            checks += extra_checks
            not_checked += extra_not

    # -- independent groups whose swept boxes meet were never sampled together
    ids = [g.id for g in groups]
    for x, y in itertools.combinations(ids, 2):
        near = None
        for ka, ba in swept.get(x, {}).items():
            for kb, bb in swept.get(y, {}).items():
                if world.body(ka) == world.body(kb):
                    continue
                d = box_distance(ba, bb)
                if d <= tol.near_mm and (near is None or d < near[0]):
                    near = (d, ka, kb)
        if near is not None:
            checks.append(Check(f"combination:{x}+{y}", "warn", f"{x} and {y} were sampled one at a time, but the "
                                f"swept boxes of {near[1]} and {near[2]} come within {near[0]:.3g} mm: pass "
                                f"combine=[[...]] to sample them together", [near[1], near[2]],
                                {"groups": [x, y], "box_distance_mm": round(near[0], 6)}))
            not_checked.append(f"{x} with {y}: combined poses (sampled separately)")
    limits = {"touch_mm": tol.touch_mm, "overlap_mm3": tol.overlap_mm3, "near_mm": tol.near_mm,
              "volume_check_mm3": tol.volume_check_mm3, "default_samples": default_samples,
              "max_step_deg": max_step_deg, "max_step_mm": max_step_mm, "max_poses": max_poses,
              "refine_steps": refine_steps, "strict_contacts": strict_contacts,
              "combine": [list(c) for c in combine]}
    stats = {"joints": len(js), "groups": len(groups), "poses": poses_total, "pair_queries": candidates_total,
             **world.stats, "seconds": round(time.perf_counter() - t0, 3)}
    return verdict(GATE, checks, assumptions=ASSUMPTIONS, limits=limits, exclusions=excl,
                   extra={"groups": group_rows, "not_checked": not_checked, "stats": stats})


def _carries(parent: Mapping[str, Optional[str]], ancestor: str, jid: str) -> bool:
    """True when joint ``jid`` is ``ancestor`` or rides on it."""
    while jid is not None:
        if jid == ancestor:
            return True
        jid = parent.get(jid)  # type: ignore[assignment]
    return False


def _radius(box: Sequence[float], origin: Sequence[float], direction: Sequence[float]) -> float:
    """Largest distance of the box's corners from the axis: a bound on how far its points swing."""
    n = math.sqrt(sum(c * c for c in direction))
    d = [c / n for c in direction]
    best = 0.0
    for x in (box[0], box[3]):
        for y in (box[1], box[4]):
            for z in (box[2], box[5]):
                v = (x - origin[0], y - origin[1], z - origin[2])
                t = sum(v[i] * d[i] for i in range(3))
                best = max(best, math.sqrt(max(0.0, sum(c * c for c in v) - t * t)))
    return best


def _collision_check(world: World, g: _Group, grid, poses, values_of, world_mats, pair, rows, hits,
                     is_intended: bool, refine_steps: int, tol: Tolerances) -> Check:
    """The witness of one colliding pair. The *first* colliding pose is the one nearest home (the sum over axes of
    the distance from home as a fraction of the range; ties in sweep order), the pose the joint meets first moving
    out from rest. Its clear grid neighbour nearest home (one sample away on one axis) gives the last clear pose and
    the closest points, and the boundary between the two is bisected along that axis."""
    a, b = pair
    index = list(itertools.product(*[range(len(v)) for v in grid]))
    at = {idx: pi for pi, idx in enumerate(index)}
    by_pose = {pi: r for pi, r in rows}

    def from_home(pi: int) -> float:
        return sum(abs(v - ax.home) / ((ax.hi - ax.lo) or 1.0) for v, ax in zip(poses[pi], g.axes))

    first_i, first = min(hits, key=lambda t: (from_home(t[0]), t[0]))
    clear = []                                     # grid neighbours of the hit where the pair shares no volume
    for axis in range(len(grid)):
        for step in (-1, 1):
            idx = list(index[first_i])
            idx[axis] += step
            if 0 <= idx[axis] < len(grid[axis]):
                pi = at[tuple(idx)]
                r = by_pose.get(pi)
                if r is None or r.state in ("apart", "touching"):
                    clear.append((from_home(pi), pi, axis, r))
    clear.sort(key=lambda t: (t[0], t[1]))
    worst_i, worst = max(hits, key=lambda t: t[1].overlap_mm3 or 0.0)
    ev: Dict[str, Any] = {
        "first_pose": _label(g, poses[first_i]), "overlap_mm3": first.overlap_mm3, "state": first.state,
        "overlap_centroid": first.witness.get("overlap_centroid"), "overlap_box": first.witness.get("overlap_box"),
        "colliding_poses": len(hits), "poses": len(poses),
        "worst_pose": _label(g, poses[worst_i]), "worst_overlap_mm3": worst.overlap_mm3,
        "intended_contact": is_intended,
    }

    def points(r: Relation) -> Tuple[Any, Any]:
        pa, pb = r.witness.get("point_a"), r.witness.get("point_b")
        return (pb, pa) if r.a != a else (pa, pb)

    if clear:
        _, ci, axis, r = clear[0]
        ev["last_clear_pose"] = _label(g, poses[ci])
        if r is not None:
            ev["last_clear_gap_mm"] = r.gap_mm
            ev["point_a"], ev["point_b"] = points(r)
        else:
            ev["last_clear_gap_mm"] = f"> {tol.near_mm} (boxes apart)"
        if refine_steps > 0:
            lo, hi = poses[ci][axis], poses[first_i][axis]
            lo_rel, hi_rel = r, first
            base = list(poses[first_i])
            for _ in range(refine_steps):
                mid = (lo + hi) / 2
                base[axis] = mid
                rel = world.relate(world_mats(values_of(tuple(base))), a, b)
                if rel.interferes or rel.state in ("unknown", "unchecked"):
                    hi, hi_rel = mid, rel
                else:
                    lo, lo_rel = mid, rel
            ev["onset"] = {"joint": g.axes[axis].joint, "clear": round(lo, 6), "hit": round(hi, 6),
                           "unit": g.axes[axis].unit, "bisections": refine_steps,
                           "overlap_mm3": hi_rel.overlap_mm3, "overlap_centroid": hi_rel.witness.get("overlap_centroid")}
            if len(grid) > 1:
                ev["onset"]["others"] = _label(g, poses[first_i])
            if lo_rel is not None:
                pa, pb = points(lo_rel)
                ev["onset"].update(gap_mm=lo_rel.gap_mm, point_a=pa, point_b=pb)
    where = f"first at {ev['first_pose']}"
    if "onset" in ev:
        o = ev["onset"]
        where += f" (onset between {o['joint']}={_fmt(o['clear'])} and {_fmt(o['hit'])} {o['unit']})"
    if is_intended:
        msg = (f"{a} and {b}, an intended contact, share {first.overlap_mm3:g} mm3 (over {tol.overlap_mm3:g}) "
               f"{where}; {len(hits)} of {len(poses)} poses overlap")
    else:
        msg = f"{a} collides with {b}: {first.overlap_mm3:g} mm3 shared {where}; {len(hits)} of {len(poses)} poses"
    return Check(f"collision:{_pair_id(a, b)}", "fail", msg, [a, b], ev)


# ----------------------------------------------------------------------------- the gate on an Assembly

def motion_gate(assembly: Any, joints: Optional[Mapping[str, Any]] = None, *, tol: Tolerances = Tolerances(),
                cache: Optional[PairCache] = None, samples: Optional[Mapping[str, int]] = None,
                default_samples: int = DEFAULT_SAMPLES, max_step_deg: Optional[float] = None,
                max_step_mm: Optional[float] = None, combine: Iterable[Sequence[str]] = (),
                intended_contacts: Iterable[Sequence[str]] = (), intended_overlaps: Iterable[Mapping[str, Any]] = (),
                ignore_pairs: Iterable[Any] = (), strict_contacts: bool = False, refine_steps: int = 8,
                max_poses: int = DEFAULT_MAX_POSES, contains: Optional[Iterable[Any]] = None,
                containment_options: Optional[Mapping[str, Any]] = None, out: Any = None) -> Dict[str, Any]:
    """Sample every ranged joint of ``assembly`` and return (with ``out`` also write) the verdict.

    * ``joints``: ``{interface: joint}`` (default ``assembly.joints``, from ``Assembly.from_build``);
    * ``samples``: per-joint sample counts; they override the joint's own ``samples``, which overrides
      ``default_samples`` (12);
      ``max_step_deg`` / ``max_step_mm`` raise a joint's count until its step is at most that;
    * ``combine``: lists of joint ids sampled together on a grid (chains are always gridded);
      ``max_poses`` (2000) caps a grid, coarsening every axis evenly (a warning);
    * ``intended_contacts``: pairs allowed to touch in every group (each joint's own are added);
    * ``intended_overlaps``: ``[{parts, reason}]`` pairs whose shared volume is by design (exclusions);
    * ``ignore_pairs``: pairs never queried (variants that never coexist);
    * ``strict_contacts``: an undeclared touch fails instead of warning;
    * ``refine_steps``: bisections of a one-axis collision's onset (0 turns it off);
    * ``contains``: ``contains`` declarations; those whose cavity or contents a group moves are
      checked by ``containment_gate`` at that group's poses (``containment_options`` passed on).
    """
    world = AssemblyWorld(assembly, tol, cache)
    joints = dict(assembly.joints if joints is None else joints)
    hook = None
    if contains is not None:
        hook = _containment_hook(assembly, list(contains), tol, cache, dict(containment_options or {}))
    data = run_motion(world, joints, tol=tol, samples=samples, default_samples=default_samples,
                      max_step_deg=max_step_deg, max_step_mm=max_step_mm, combine=combine,
                      intended_contacts=intended_contacts, intended_overlaps=intended_overlaps,
                      ignore_pairs=ignore_pairs, strict_contacts=strict_contacts, refine_steps=refine_steps,
                      max_poses=max_poses, containment=hook)
    if out is not None:
        write_verdict(out, data)
    return data


def _containment_hook(assembly: Any, decls: List[Any], tol: Tolerances, cache: Optional[PairCache],
                      options: Dict[str, Any]):
    from cadagent.gates.containment import Contains, containment_gate, instances

    parsed = [Contains.coerce(d) for d in decls]

    def hook(gid: str, poses: Dict[str, Dict[str, Sequence[float]]], bodies: List[str]):
        moved = set(bodies)
        mine, skipped = [], []
        for d in parsed:
            cav = assembly.cavities.get(d.cavity)
            items = instances(assembly.names, d.what)
            hit = (cav is not None and cav.body in moved) or any(assembly[k].body in moved for k in items)
            (mine if hit else skipped).append(d)
        if not mine:
            return [], [f"contains {d.what} in {d.cavity}: not moved by {gid}" for d in skipped]
        locs = {p: {b: [m[0:4], m[4:8], m[8:12]] for b, m in mats.items()} for p, mats in poses.items()}
        v = containment_gate(assembly, mine, tol=tol, cache=cache, poses=locs, **options)
        out = [Check(f"containment@{gid}/{c['id']}", c["status"], c["message"], c.get("parts", ()),
                     c.get("evidence", {})) for c in v["checks"]]
        return out, []

    return hook


def motion_from_build(result: Any, dossier: Any = None, extra: Optional[Mapping[str, Any]] = None, *,
                      containment: bool = True, **kwargs: Any) -> Dict[str, Any]:
    """The motion gate on a dossier build: ``Assembly.from_build(result)`` with its joints, the dossier's
    ``gates:`` (``motion_samples``, ``intended_overlaps``, ``ignore_pairs``, ``touch_tol_mm``) and cards'
    ``contains`` (with ``containment``), and ``extra`` (the same keys as plain data). ``kwargs`` override."""
    from cadagent.gates.relations import Assembly
    asm = Assembly.from_build(result)
    overlaps: List[Any] = []
    ignore: List[Any] = []
    contains: List[Dict[str, Any]] = []
    opts: Dict[str, Any] = {}
    if dossier is not None:
        g = dossier.gates
        overlaps += [{"parts": list(p.parts), "reason": p.reason} for p in g.intended_overlaps]
        ignore += [{"parts": list(p.parts), "reason": p.reason} for p in g.ignore_pairs]
        opts["default_samples"] = int(g.motion_samples)
        opts["tol"] = Tolerances(touch_mm=float(g.touch_tol_mm))
        for card in dossier.parts.values():
            for c in card.contains:
                contains.append({"what": c.what, "cavity": c.cavity, "container": card.id, "count": c.count})
    extra = dict(extra or {})
    overlaps += list(extra.get("intended_overlaps", []))
    ignore += list(extra.get("ignore_pairs", []))
    contains += [dict(c) for c in extra.get("contains", [])]
    if "motion_samples" in extra:
        opts["default_samples"] = int(extra["motion_samples"])
    opts.update(intended_overlaps=overlaps, ignore_pairs=ignore)
    if containment and contains:
        opts["contains"] = contains
    opts.update(kwargs)
    return motion_gate(asm, **opts)
