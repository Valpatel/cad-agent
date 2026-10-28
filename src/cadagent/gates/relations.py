"""The assembly container and the pairwise relation table every integrity gate reads.

Relations follow the four states of build123d-mcp's ``clearance`` tool
(Apache-2.0, vendored under ``vendor/build123d-mcp``; semantics adapted, no code
copied), renamed to the plan's words:

==============  =====================================  ======================
state           meaning                                build123d-mcp name
==============  =====================================  ======================
``apart``       no shared volume, gap > ``touch_mm``    apart
``touching``    no shared volume, gap <= ``touch_mm``   touching
``overlapping`` shared volume, neither inside the       interpenetrating
                other
``contains``    shared volume, one (nearly) wholly      containing
                inside the other
==============  =====================================  ======================

plus ``unknown`` when the kernel failed on the pair (a gate must treat it as a
failure, never as apart).

How each state is decided (all tolerances are absolute; see ``Tolerances``):

1. **Broad phase.** Each part's axis-aligned box (``BRepBndLib.AddOptimal``,
   exact geometry, not the triangulation). Pairs whose boxes are farther apart
   than ``near_mm`` are ``apart`` without a kernel call; their gap is only known
   to be at least the box distance (``gap_lower_bound_mm``).
2. **Common volume** (``BRepAlgoAPI_Common`` + ``BRepGProp``). More than
   ``overlap_mm3`` in common is an overlap; if one part has no more than
   ``contain_mm3`` of its volume outside the other, it is ``contains``.
3. **Minimum distance** (``BRepExtrema_DistShapeShape``) when there is no overlap:
   ``touching`` at or below ``touch_mm``, else ``apart``.

Witnesses, so a reviewer can look at the right place:

* apart, touching: the closest pair of points (one on each part);
* touching with an exact (zero) gap: the contact area, the area of ``a``'s
  faces that lie on ``b`` (``Common`` of ``a``'s faces with solid ``b``); point
  and line contacts give 0; a gap inside ``touch_mm`` but above zero gives 0;
* overlapping: the centroid and box of the common volume, and each part's
  volume outside the other;
* contains: as overlapping, plus the wall, the smallest distance from the inner
  part's boundary to the outer part's boundary, with its two points.

Limits. These are exact B-rep queries on the model as given: no tolerance
stack, no deflection under load, no print shrink. ``touching`` means the model
puts the surfaces within ``touch_mm``; it does not prove the printed parts
meet, and ``apart`` by 0.2 mm does not prove a printed clearance. The kernel's
own accuracy (Common on faceted or spline faces) is why the tolerances are not
zero. A relation is between two parts as placed; motion is the motion gate's
job (it calls this with posed assemblies).
"""

from __future__ import annotations

import numbers
import time
from dataclasses import asdict, dataclass, field, replace
from itertools import combinations
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require
from cadagent.gates.cache import PairCache, digest, matrix_key, shape_hash

STATES = ("apart", "touching", "overlapping", "contains", "unknown")
CONTACT_STATES = ("touching", "overlapping", "contains")
RELATIONS_VERSION = "1"   # bump when the meaning of a cached record changes
_IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)


@dataclass(frozen=True)
class Tolerances:
    """Absolute tolerances for the relation states (mm, mm³). Defaults suit FDM-scale parts.

    * ``touch_mm`` (0.01): a gap at or below this, with no shared volume, is ``touching``.
    * ``overlap_mm3`` (0.001, a 0.1 mm cube): shared volume above this is an overlap;
      at or below it the pair is judged by its gap (Common's own noise on curved faces is
      far below this).
    * ``contain_mm3`` (0.001): a part with no more than this of its volume outside the
      other is inside it. A ball resting on a cavity wall has exactly 0 outside.
    * ``near_mm`` (1.0): broad-phase margin. Pairs whose boxes are within this get the exact
      queries (so a 0.5 mm hover is measured, not just bounded); farther pairs are ``apart``
      with only a lower bound on the gap.
    """
    touch_mm: float = 0.01
    overlap_mm3: float = 0.001
    contain_mm3: float = 0.001
    near_mm: float = 1.0

    def __post_init__(self):
        if min(self.touch_mm, self.overlap_mm3, self.contain_mm3, self.near_mm) < 0:
            raise ValueError("tolerances must be non-negative")
        if self.near_mm < self.touch_mm:
            raise ValueError("near_mm must be at least touch_mm, or touching pairs would be skipped")

    def key(self) -> str:
        return f"t{self.touch_mm!r}:o{self.overlap_mm3!r}:c{self.contain_mm3!r}"


@dataclass(frozen=True)
class Relation:
    """One unordered pair's relation, oriented as (``a``, ``b``).

    ``gap_mm`` is the exact minimum distance when the narrow phase ran, 0 for overlaps,
    and None for broad-phase-only pairs (then ``gap_lower_bound_mm`` is set).
    ``contained`` is ``"a_in_b"``, ``"b_in_a"`` or ``"both"`` (equal shapes) for ``contains``.
    """
    a: str
    b: str
    state: str
    gap_mm: Optional[float] = None
    gap_lower_bound_mm: Optional[float] = None
    overlap_mm3: Optional[float] = None
    a_outside_b_mm3: Optional[float] = None
    b_outside_a_mm3: Optional[float] = None
    contained: Optional[str] = None
    wall_mm: Optional[float] = None
    contact_area_mm2: Optional[float] = None
    witness: Dict[str, Any] = field(default_factory=dict)
    exact: bool = True
    cached: bool = False
    error: Optional[str] = None

    @property
    def in_contact(self) -> bool:
        """touching, overlapping or contains."""
        return self.state in CONTACT_STATES

    def flipped(self) -> "Relation":
        """The same relation oriented as (``b``, ``a``)."""
        swap = {"a_in_b": "b_in_a", "b_in_a": "a_in_b"}
        w = dict(self.witness)
        for x, y in (("point_a", "point_b"),):
            vx, vy = w.pop(x, None), w.pop(y, None)
            if vy is not None:
                w[x] = vy
            if vx is not None:
                w[y] = vx
        return replace(self, a=self.b, b=self.a, a_outside_b_mm3=self.b_outside_a_mm3,
                       b_outside_a_mm3=self.a_outside_b_mm3,
                       contained=swap.get(self.contained, self.contained), witness=w)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != {}}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Relation":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ----------------------------------------------------------------------------- placement

def _trsf(location: Any):
    """gp_Trsf from None, a cq/build123d Location, TopLoc_Location, gp_Trsf, (x, y, z), 3x4 or 4x4 rows."""
    gp = require("OCP.gp", "assembly placement")
    if location is None:
        return gp.gp_Trsf()
    loc = getattr(location, "wrapped", location)
    if hasattr(loc, "Transformation"):
        return loc.Transformation()
    if isinstance(loc, gp.gp_Trsf):
        return loc
    rows = None if isinstance(loc[0], numbers.Real) else [list(map(float, r)) for r in loc]
    trsf = gp.gp_Trsf()
    if rows is None:
        if len(loc) != 3:
            raise ValueError(f"a flat location must be a translation (x, y, z), got {location!r}")
        trsf.SetTranslation(gp.gp_Vec(*map(float, loc)))
        return trsf
    if len(rows) not in (3, 4) or any(len(r) != 4 for r in rows[:3]):
        raise ValueError("a matrix location must be 3x4 or 4x4 rows")
    if len(rows) == 4 and [round(v, 12) for v in rows[3]] != [0, 0, 0, 1]:
        raise ValueError("the last row of a 4x4 placement must be 0 0 0 1")
    trsf.SetValues(*rows[0], *rows[1], *rows[2])
    return trsf


def _matrix(trsf) -> Tuple[float, ...]:
    return tuple(trsf.Value(r, c) for r in (1, 2, 3) for c in (1, 2, 3, 4))


@dataclass
class Part:
    """A named shape in its local frame plus its placement in the assembly.

    ``body`` names the rigid body the part moves with (default: its own name); the motion
    gate poses whole bodies. ``group`` is a free label (subassembly or section id).
    """
    name: str
    shape: Any
    matrix: Tuple[float, ...] = _IDENTITY
    body: str = ""
    group: Optional[str] = None
    _located: Any = field(default=None, repr=False, compare=False)
    _hash: Optional[str] = field(default=None, repr=False, compare=False)

    @property
    def located(self):
        """The ``TopoDS_Shape`` in assembly coordinates."""
        if self._located is None:
            toploc = require("OCP.TopLoc", "assembly placement")
            self._located = self.shape.Moved(toploc.TopLoc_Location(_trsf([self.matrix[0:4], self.matrix[4:8],
                                                                           self.matrix[8:12]])))
        return self._located

    @property
    def shape_hash(self) -> str:
        """Content hash of the local shape (placement excluded)."""
        if self._hash is None:
            self._hash = shape_hash(self.shape)
        return self._hash

    @property
    def key(self) -> str:
        """Content hash of the shape plus its rounded placement: what a cached relation is bound to."""
        return digest(self.shape_hash, matrix_key(self.matrix))


class Assembly:
    """Named parts in assembly coordinates: the input of every gate.

    >>> asm = Assembly()
    >>> asm.add("base", base_shape)
    >>> asm.add("arm", arm_shape, location=(40, 0, 12), body="arm", group="S2")

    Shapes may be CadQuery or build123d shapes or raw ``TopoDS_Shape`` and must contain at
    least one solid (relations are volume relations). A mapping ``{name: shape}`` (shapes
    already in assembly coordinates, the ``pairwise_intersections`` input) is accepted too.
    """

    def __init__(self, parts: Optional[Mapping[str, Any]] = None):
        self._parts: Dict[str, Part] = {}
        for name, shape in (parts or {}).items():
            self.add(name, shape)

    def add(self, name: str, shape: Any, location: Any = None, *, body: Optional[str] = None,
            group: Optional[str] = None) -> Part:
        """Add a part. ``location``: None, a CadQuery/build123d ``Location``, ``TopLoc_Location``,
        ``gp_Trsf``, a translation ``(x, y, z)`` or 3x4/4x4 matrix rows (rigid motions only)."""
        if not name or not isinstance(name, str):
            raise ValueError("a part needs a non-empty string name")
        if name in self._parts:
            raise ValueError(f"part {name!r} is already in the assembly")
        topods = getattr(shape, "wrapped", shape)
        if _count_solids(topods) == 0:
            raise ValueError(f"part {name!r} has no solid; relations are volume relations")
        part = Part(name, topods, _matrix(_trsf(location)), body or name, group)
        self._parts[name] = part
        return part

    def __getitem__(self, name: str) -> Part:
        return self._parts[name]

    def __contains__(self, name: object) -> bool:
        return name in self._parts

    def __iter__(self) -> Iterator[str]:
        return iter(self._parts)

    def __len__(self) -> int:
        return len(self._parts)

    @property
    def names(self) -> List[str]:
        return list(self._parts)

    def shape(self, name: str):
        """The part's ``TopoDS_Shape`` in assembly coordinates."""
        return self._parts[name].located

    def bodies(self) -> Dict[str, List[str]]:
        """``{body: [part names]}``."""
        out: Dict[str, List[str]] = {}
        for p in self._parts.values():
            out.setdefault(p.body, []).append(p.name)
        return out

    def groups(self) -> Dict[Optional[str], List[str]]:
        """``{group: [part names]}`` (ungrouped parts under None)."""
        out: Dict[Optional[str], List[str]] = {}
        for p in self._parts.values():
            out.setdefault(p.group, []).append(p.name)
        return out

    def posed(self, body: str, location: Any) -> "Assembly":
        """A copy with every part of ``body`` moved by ``location`` (applied after its placement).

        Shape hashes are carried over, so only the moved parts' cache keys change.
        """
        if body not in self.bodies():
            raise KeyError(f"no body {body!r}; bodies: {sorted(self.bodies())}")
        move = _trsf(location)
        out = Assembly()
        for p in self._parts.values():
            q = replace(p, _located=None)
            if p.body == body:
                t = _trsf([p.matrix[0:4], p.matrix[4:8], p.matrix[8:12]])
                q = replace(q, matrix=_matrix(move.Multiplied(t)))
            out._parts[p.name] = q
        return out

    @classmethod
    def from_cadquery(cls, assy: Any, *, body_from: str = "top") -> "Assembly":
        """Flatten a ``cadquery.Assembly``: one part per node that holds geometry, named by its path
        (``"root/arm/pin"``) and placed by the composed locations. ``body_from="top"`` labels every
        part with the root child it sits under (so a moving subassembly is one body); ``"self"``
        gives each part its own body."""
        if body_from not in ("top", "self"):
            raise ValueError('body_from must be "top" or "self"')
        out = cls()

        def walk(node, loc, path, top):
            loc = node.loc if loc is None else loc * node.loc
            name = f"{path}/{node.name}" if path else node.name
            top = top if top is not None else (name if path else None)
            shapes = [getattr(v, "wrapped", v) for v in (node.shapes or [])]
            if shapes:
                out.add(name, shapes[0] if len(shapes) == 1 else _compound(shapes), loc,
                        body=(top or name) if body_from == "top" else name)
            for child in node.children:
                walk(child, loc, name, top)

        walk(assy, None, "", None)
        return out


def _count_solids(topods) -> int:
    topexp = require("OCP.TopExp", "solid count")
    topabs = require("OCP.TopAbs", "solid count")
    ex, n = topexp.TopExp_Explorer(topods, topabs.TopAbs_SOLID), 0
    while ex.More():
        n += 1
        ex.Next()
    return n


def _compound(shapes: Iterable[Any]):
    topods = require("OCP.TopoDS", "compound")
    brep = require("OCP.BRep", "compound")
    comp, builder = topods.TopoDS_Compound(), brep.BRep_Builder()
    builder.MakeCompound(comp)
    for s in shapes:
        builder.Add(comp, s)
    return comp


def _faces(topods):
    topexp = require("OCP.TopExp", "face compound")
    topabs = require("OCP.TopAbs", "face compound")
    ex, faces = topexp.TopExp_Explorer(topods, topabs.TopAbs_FACE), []
    while ex.More():
        faces.append(ex.Current())
        ex.Next()
    return _compound(faces)


def _volume_props(topods):
    gprop = require("OCP.GProp", "volume")
    bgprop = require("OCP.BRepGProp", "volume")
    props = gprop.GProp_GProps()
    bgprop.BRepGProp.VolumeProperties_s(topods, props)
    return props


def _volume(topods) -> float:
    return float(_volume_props(topods).Mass())


def _area(topods) -> float:
    gprop = require("OCP.GProp", "area")
    bgprop = require("OCP.BRepGProp", "area")
    props = gprop.GProp_GProps()
    bgprop.BRepGProp.SurfaceProperties_s(topods, props)
    return float(props.Mass())


def bounding_box(topods) -> Tuple[float, float, float, float, float, float]:
    """Tight axis-aligned box ``(xmin, ymin, zmin, xmax, ymax, zmax)`` from the exact geometry."""
    bnd = require("OCP.Bnd", "bounding box")
    bndlib = require("OCP.BRepBndLib", "bounding box")
    box = bnd.Bnd_Box()
    bndlib.BRepBndLib.AddOptimal_s(getattr(topods, "wrapped", topods), box, False, False)
    return tuple(float(v) for v in box.Get())


def _pt(p, digits: int = 6) -> List[float]:
    return [round(p.X(), digits), round(p.Y(), digits), round(p.Z(), digits)]


def _distance(a, b):
    extrema = require("OCP.BRepExtrema", "minimum distance")
    dist = extrema.BRepExtrema_DistShapeShape(a, b)
    dist.Perform()
    if not dist.IsDone() or dist.NbSolution() < 1:
        raise RuntimeError("BRepExtrema_DistShapeShape did not converge")
    return float(dist.Value()), _pt(dist.PointOnShape1(1)), _pt(dist.PointOnShape2(1))


def _shape_list(shapes):
    toptools = require("OCP.TopTools", "boolean arguments")
    out = toptools.TopTools_ListOfShape()
    for s in shapes:
        out.Append(s)
    return out


def _common(a, b):
    algo = require("OCP.BRepAlgoAPI", "common volume")
    op = algo.BRepAlgoAPI_Common()
    op.SetNonDestructive(True)        # by default OCCT may raise the arguments' tolerances in place
    op.SetArguments(_shape_list([a]))
    op.SetTools(_shape_list([b]))
    op.Build()
    if not op.IsDone() or (hasattr(op, "HasErrors") and op.HasErrors()):
        raise RuntimeError("BRepAlgoAPI_Common failed")
    return op.Shape()


# ----------------------------------------------------------------------------- narrow phase

def relate(a: Any, b: Any, tol: Tolerances = Tolerances(), *, names: Tuple[str, str] = ("a", "b"),
           volumes: Optional[Tuple[float, float]] = None, contact_area: bool = True) -> Relation:
    """Exact relation of two shapes (already in one frame), no broad phase and no cache.

    Use this directly for a part against a declared cavity solid or for a pair the broad
    phase skipped. ``volumes`` may pass the two volumes when the caller already has them.
    Kernel failures give state ``unknown`` with the error, never an exception or ``apart``.
    """
    sa, sb = getattr(a, "wrapped", a), getattr(b, "wrapped", b)
    try:
        va, vb = volumes if volumes is not None else (_volume(sa), _volume(sb))
        common = _common(sa, sb)
        props = _volume_props(common)
        vc = float(props.Mass())
        if vc > tol.overlap_mm3:
            a_out, b_out = max(va - vc, 0.0), max(vb - vc, 0.0)
            a_in, b_in = a_out <= tol.contain_mm3, b_out <= tol.contain_mm3
            box = bounding_box(common)
            witness: Dict[str, Any] = {"overlap_centroid": _pt(props.CentreOfMass()),
                                       "overlap_box": [round(v, 6) for v in box]}
            common_fields = dict(gap_mm=0.0, overlap_mm3=round(vc, 6), a_outside_b_mm3=round(a_out, 6),
                                 b_outside_a_mm3=round(b_out, 6))
            if a_in or b_in:
                contained = "both" if a_in and b_in else ("a_in_b" if a_in else "b_in_a")
                inner, outer = (sa, sb) if contained != "b_in_a" else (sb, sa)
                wall, p_in, p_out = _distance(_faces(inner), _faces(outer))
                witness.update(inner_point=p_in, outer_point=p_out)
                return Relation(names[0], names[1], "contains", contained=contained, wall_mm=round(wall, 6),
                                witness=witness, **common_fields)
            return Relation(names[0], names[1], "overlapping", witness=witness, **common_fields)
        gap, pa, pb = _distance(sa, sb)
        witness = {"point_a": pa, "point_b": pb}
        if gap <= tol.touch_mm:
            area = None
            if contact_area:
                area = round(_area(_common(_faces(sa), sb)), 6) if gap <= 1e-9 else 0.0
            return Relation(names[0], names[1], "touching", gap_mm=round(gap, 6), overlap_mm3=round(vc, 6),
                            contact_area_mm2=area, witness=witness)
        return Relation(names[0], names[1], "apart", gap_mm=round(gap, 6), overlap_mm3=round(vc, 6), witness=witness)
    except Exception as exc:  # the OCCT wrappers raise several types; record, never pass silently
        return Relation(names[0], names[1], "unknown", error=f"{type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------------- broad phase

def aabb_distances(boxes: Mapping[str, Sequence[float]]) -> Dict[Tuple[str, str], float]:
    """Distance between every pair of axis-aligned boxes (0 when they overlap), keyed by ``(a, b)``
    in ``boxes`` order. A lower bound on the true gap of the shapes inside."""
    np = require("numpy", "broad phase")
    names = list(boxes)
    if len(names) < 2:
        return {}
    arr = np.asarray([boxes[n] for n in names], dtype=float)
    lo, hi = arr[:, :3], arr[:, 3:]
    i, j = np.triu_indices(len(names), k=1)
    sep = np.maximum(0.0, np.maximum(lo[j] - hi[i], lo[i] - hi[j]))
    d = np.sqrt((sep ** 2).sum(axis=1))
    return {(names[x], names[y]): float(v) for x, y, v in zip(i.tolist(), j.tolist(), d.tolist())}


# ----------------------------------------------------------------------------- the table

@dataclass
class RelationTable:
    """Relations for every pair of an assembly: exact for broad-phase candidates, bounded for the rest.

    ``get(a, b)`` always answers: a stored relation, or ``apart`` with ``exact=False`` and the
    box distance as ``gap_lower_bound_mm``. ``get(a, b, exact=True)`` runs the kernel for a
    skipped pair. ``stats`` has the counts and timings of the run that built the table.
    """
    assembly: Assembly
    tolerances: Tolerances
    relations: Dict[Tuple[str, str], Relation]
    lower_bounds: Dict[Tuple[str, str], float]
    stats: Dict[str, Any]
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    cache: Optional[PairCache] = None

    def get(self, a: str, b: str, *, exact: bool = False) -> Relation:
        for key, flip in (((a, b), False), ((b, a), True)):
            if key in self.relations:
                rel = self.relations[key]
                return rel.flipped() if flip else rel
        if a not in self.assembly or b not in self.assembly or a == b:
            raise KeyError(f"no pair ({a!r}, {b!r}) in the assembly")
        if exact:
            rel = _relate_parts(self.assembly, a, b, self.tolerances, self.cache, True)
            self.relations[(a, b)] = rel
            return rel
        bound = self.lower_bounds.get((a, b), self.lower_bounds.get((b, a)))
        return Relation(a, b, "apart", gap_lower_bound_mm=None if bound is None else round(bound, 6), exact=False)

    def __iter__(self) -> Iterator[Relation]:
        return iter(self.relations.values())

    def by_state(self, *states: str) -> List[Relation]:
        bad = set(states) - set(STATES)
        if bad:
            raise ValueError(f"unknown state(s) {sorted(bad)}; states are {STATES}")
        return [r for r in self.relations.values() if r.state in states]

    def contacts(self) -> List[Relation]:
        """touching, overlapping and contains relations: the edges of a contact graph."""
        return self.by_state(*CONTACT_STATES)

    def of(self, name: str) -> List[Relation]:
        """Every exact relation involving ``name``, oriented with ``name`` as ``a``."""
        return [r if r.a == name else r.flipped() for r in self.relations.values() if name in (r.a, r.b)]

    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready: tolerances, stats, and the exact relations (broad-phase-only pairs are counted, not listed)."""
        return {"tolerances": asdict(self.tolerances), "stats": dict(self.stats),
                "relations": [r.to_dict() for r in self.relations.values()],
                "skipped_pairs": [list(p) for p in self.skipped],
                "method": "AABB broad phase (near_mm), then BRepAlgoAPI_Common volume and BRepExtrema_DistShapeShape",
                "physical_fit_verified": False}


def _pair_key(asm: Assembly, a: str, b: str, tol: Tolerances, contact_area: bool) -> Tuple[str, bool]:
    ka, kb = asm[a].key, asm[b].key
    flip = kb < ka
    lo, hi = (kb, ka) if flip else (ka, kb)
    return digest("relation", RELATIONS_VERSION, tol.key(), f"area={contact_area}", lo, hi), flip


def _relate_parts(asm: Assembly, a: str, b: str, tol: Tolerances, cache: Optional[PairCache],
                  contact_area: bool, volumes: Optional[Dict[str, float]] = None) -> Relation:
    """One pair through the cache. ``volumes`` memoises part volumes across pairs (filled on misses only)."""
    key = flip = None
    if cache is not None:
        key, flip = _pair_key(asm, a, b, tol, contact_area)
        hit = cache.get(key)
        if hit is not None:
            rel = Relation.from_dict({**hit, "a": "low", "b": "high"})   # stored oriented low key -> high key
            rel = rel.flipped() if flip else rel
            return replace(rel, a=a, b=b, cached=True)
    vols = None
    if volumes is not None:
        for n in (a, b):
            if n not in volumes:
                volumes[n] = _volume(asm.shape(n))
        vols = (volumes[a], volumes[b])
    rel = relate(asm.shape(a), asm.shape(b), tol, names=(a, b), volumes=vols, contact_area=contact_area)
    if cache is not None and rel.state != "unknown":
        stored = rel.flipped() if flip else rel
        cache.put(key, {k: v for k, v in stored.to_dict().items() if k not in ("a", "b", "cached")})
    return rel


def relation_table(assembly: Any, tol: Tolerances = Tolerances(), *, cache: Optional[PairCache] = None,
              only: Optional[Iterable[str]] = None, skip_pairs: Iterable[Sequence[str]] = (),
              contact_area: bool = True) -> RelationTable:
    """Build the relation table of an assembly (an ``Assembly`` or a ``{name: shape}`` mapping).

    ``only`` restricts the narrow phase to pairs with at least one part in it (the moving set of a
    motion pose); ``skip_pairs`` lists pairs never queried (variants that never coexist), reported
    in ``skipped``. ``cache`` (a ``PairCache``) makes unchanged pairs free on the next run.
    """
    asm = assembly if isinstance(assembly, Assembly) else Assembly(assembly)
    t0 = time.perf_counter()
    boxes = {n: bounding_box(asm.shape(n)) for n in asm}
    bounds = aabb_distances(boxes)
    only_set = set(only) if only is not None else None
    skip = {frozenset(p) for p in skip_pairs}
    candidates, skipped = [], []
    for (a, b), d in bounds.items():
        if frozenset((a, b)) in skip:
            skipped.append((a, b))
        elif d <= tol.near_mm and (only_set is None or a in only_set or b in only_set):
            candidates.append((a, b))
    t1 = time.perf_counter()
    hits0 = cache.hits if cache is not None else 0
    rels: Dict[Tuple[str, str], Relation] = {}
    volumes: Dict[str, float] = {}
    kernel = 0
    for a, b in candidates:
        rel = _relate_parts(asm, a, b, tol, cache, contact_area, volumes)
        kernel += 0 if rel.cached else 1
        rels[(a, b)] = rel
    t2 = time.perf_counter()
    n = len(asm)
    stats = {"parts": n, "pairs": n * (n - 1) // 2, "candidates": len(candidates), "kernel_queries": kernel,
             "cache_hits": (cache.hits - hits0) if cache is not None else 0,
             "broad_phase_s": round(t1 - t0, 4), "narrow_phase_s": round(t2 - t1, 4),
             "states": {s: sum(1 for r in rels.values() if r.state == s) for s in STATES}}
    return RelationTable(asm, tol, rels, bounds, stats, skipped, cache)
