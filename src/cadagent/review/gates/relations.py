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

plus two states that are never a pass:

* ``unknown``: the kernel failed on the pair, or its answers disagreed (see below);
* ``unchecked``: ``RelationTable.get`` on a pair the table never examined (excluded by
  ``only=`` or ``skip_pairs``) whose boxes do not prove it apart.

``overlapping`` and ``contains`` between two *parts* are both volume interference
(``Relation.interferes``): a pin wholly buried in a block is ``contains``, and a gate must
treat it as an interference unless it is declared (an intended overlap, or an item against a
declared *cavity* solid, where ``contains`` is the goal).

How each state is decided (all tolerances absolute; see ``Tolerances``):

1. **Broad phase.** Each part's axis-aligned box (``BRepBndLib.AddOptimal``, exact geometry).
   Pairs whose boxes are farther apart than ``near_mm`` are ``apart`` without a kernel call;
   the box distance is a lower bound on their gap (``gap_lower_bound_mm``).
2. **Volumes.** ``BRepAlgoAPI_Common`` for the shared volume and ``BRepAlgoAPI_Cut`` for each
   part's volume outside the other, all run non-destructive (OCCT otherwise raises the
   arguments' tolerances in place). More than ``overlap_mm3`` shared is an overlap; a part with
   no more than ``contain_mm3`` outside the other is inside it.
3. **Distance** (``BRepExtrema_DistShapeShape``) when nothing is shared: ``touching`` at or below
   ``touch_mm``, else ``apart``. On solids it skips BRepExtrema's inner-solution test when the same test
   (one classifier, not one per chunk of vertices) finds nothing and the faces are clear of each other:
   the same gap and points, most of the time of a many-faced apart pair saved (``_solid_distance``, #186).
4. **Crossing probe** (#46) where a ``touching`` or ``contains`` answer has the two boundaries meeting (gap or
   wall within ``touch_mm / 10``): OCCT's boolean can miss a shallow near-tangent crossing, and then Common and Cut
   agree with each other and read none. ``BRepAlgoAPI_Section`` still finds the curves where the faces meet; points
   of each face around them are classified against the other solid (``_crossing_probe``). One on the wrong side by
   more than ``touch_mm / 10`` that the kernel's own common or cut does not hold makes the pair ``unknown``.

Fail-safe rules. OCP 7.9 binds no error report on ``BRepAlgoAPI_Common`` (``HasErrors`` is
absent and ``DSFiller()`` crashes the interpreter at exit), and ``IsDone()`` stays true when an
argument is invalid (a compound of interfering solids gives an *empty* common). So:

* ``Assembly.add`` refuses a multi-solid part whose solids share volume (fuse them first), and
  ``relate`` returns ``unknown`` for one;
* every narrow-phase answer is cross-checked: ``vol(a) = common + cut(a, b)`` (and the same for
  ``b`` when they overlap) within ``volume_check_mm3`` plus 1e-6 of the larger volume; a mismatch
  is ``unknown``, never ``touching``, ``apart`` or ``contains``;
* any exception from the kernel is ``unknown`` with the error;
* a crossing the probe finds and the booleans missed is ``unknown`` (its volume is not measured), with the point,
  its depth and the surface in ``witness["crossing_probe"]``; so is a probe that fails.

Witnesses, so a reviewer can look at the right place:

* apart, touching: the closest pair of points (one on each part);
* touching with an exact (zero) gap: the contact area, the area of ``a``'s faces that lie on
  ``b``; point and line contacts give 0, and so does a gap inside ``touch_mm`` but above zero;
* overlapping: the centroid and box of the shared volume, and each part's volume outside the other;
* contains: as overlapping, plus the wall, the smallest distance from the inner part's boundary
  to the outer part's boundary, with its two points.

Limits. Exact B-rep queries on the model as given: no tolerance stack, no deflection, no print
shrink. ``touching`` means the model puts the surfaces within ``touch_mm``; it does not prove the
printed parts meet, and ``apart`` by 0.2 mm does not prove a printed clearance. The crossing probe
is a safety net, not a proof: a crossing the section also misses, one no deeper than ``touch_mm / 10``
or one between its samples is not seen, and its depth is that of the deepest sample (a lower bound).
``apart`` rests on ``BRepExtrema_DistShapeShape``, which read 0 at every crossing tried.
"""

from __future__ import annotations

import numbers
import math
import sys
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from cadagent._deps import require
from cadagent.review.evidence import shape_content_hash
from cadagent.review.gates.cache import PairCache, digest, matrix_key

STATES = ("apart", "touching", "overlapping", "contains", "unknown", "unchecked")
CONTACT_STATES = ("touching", "overlapping", "contains")
INTERFERENCE_STATES = ("overlapping", "contains")
RELATIONS_VERSION = "5"   # 5: the crossing probe (#46) turns crossings the boolean missed into unknown
_IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)


@dataclass(frozen=True)
class Tolerances:
    """Absolute tolerances for the relation states (mm, mm³). Defaults suit FDM-scale parts.

    * ``touch_mm`` (0.01): a gap at or below this, with no shared volume, is ``touching``.
    * ``overlap_mm3`` (0.001, a 0.1 mm cube): shared volume above this is an overlap.
    * ``contain_mm3`` (0.001): a part with no more than this of its volume outside the
      other is inside it. A ball resting on a cavity wall has exactly 0 outside.
    * ``near_mm`` (1.0): broad-phase margin. Pairs whose boxes are within this get the exact
      queries (so a 0.5 mm hover is measured, not just bounded).
    * ``volume_check_mm3`` (0.01): allowed disagreement in ``vol = common + cut`` (plus 1e-6 of
      the larger part's volume for integration noise) before the pair is ``unknown``.
    """
    touch_mm: float = 0.01
    overlap_mm3: float = 0.001
    contain_mm3: float = 0.001
    near_mm: float = 1.0
    volume_check_mm3: float = 0.01

    def __post_init__(self):
        if min(self.touch_mm, self.overlap_mm3, self.contain_mm3, self.near_mm, self.volume_check_mm3) < 0:
            raise ValueError("tolerances must be non-negative")
        if self.near_mm < self.touch_mm:
            raise ValueError("near_mm must be at least touch_mm, or touching pairs would be skipped")

    def key(self) -> str:
        return (f"t{self.touch_mm!r}:o{self.overlap_mm3!r}:c{self.contain_mm3!r}"
                f":v{self.volume_check_mm3!r}")


@dataclass(frozen=True)
class Relation:
    """One unordered pair's relation, oriented as (``a``, ``b``).

    ``gap_mm`` is the exact minimum distance when the narrow phase ran, 0 for overlaps, and None
    when the pair was not examined (then ``gap_lower_bound_mm`` is the box distance and
    ``exact`` is false). ``contained`` is ``"a_in_b"``, ``"b_in_a"`` or ``"both"`` for ``contains``.
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

    @property
    def interferes(self) -> bool:
        """Shared volume (overlapping or contains): an interference between two parts unless declared."""
        return self.state in INTERFERENCE_STATES

    def flipped(self) -> "Relation":
        """The same relation oriented as (``b``, ``a``)."""
        swap = {"a_in_b": "b_in_a", "b_in_a": "a_in_b"}
        w = dict(self.witness)
        vx, vy = w.pop("point_a", None), w.pop("point_b", None)
        if vy is not None:
            w["point_a"] = vy
        if vx is not None:
            w["point_b"] = vx
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

    ``body`` names the rigid body the part moves with (default: its own name); the motion gate
    poses whole bodies. ``group`` is a free label (subassembly or section id). For a cavity,
    ``container`` names the part whose void it is.
    """
    name: str
    shape: Any
    matrix: Tuple[float, ...] = _IDENTITY
    body: str = ""
    group: Optional[str] = None
    container: Optional[str] = None
    kind: str = "part"
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
    def content_hash(self) -> str:
        """Content hash of ``shape`` as given (placement excluded): the recorded one when passed to
        ``add``, else ``shape_content_hash(shape)`` computed once."""
        if self._hash is None:
            self._hash = shape_content_hash(self.shape)
        return self._hash

    @property
    def key(self) -> str:
        """Content hash plus rounded placement: what a cached relation is bound to."""
        return digest(self.content_hash, matrix_key(self.matrix))


class Assembly:
    """Named parts in assembly coordinates, plus declared cavity solids: the input of every gate.

    >>> asm = Assembly()
    >>> asm.add("base", base_shape)
    >>> asm.add("arm", arm_shape, location=(40, 0, 12), body="arm", group="S2")
    >>> asm.add_cavity("hopper_cavity", void_shape, part="hopper")

    Shapes may be CadQuery or build123d shapes or raw ``TopoDS_Shape`` and must contain at least one
    solid. A multi-solid part whose solids share volume is refused (fuse it first): the kernel gives
    wrong relations for one. Cavities are not parts: they never enter the pair table, and are
    queried with ``relate_pair``. A mapping ``{name: shape}`` (already placed) is accepted too.
    """

    def __init__(self, parts: Optional[Mapping[str, Any]] = None):
        self._parts: Dict[str, Part] = {}
        self.cavities: Dict[str, Part] = {}
        self.joints: Dict[str, Any] = {}           # from a dossier build: {interface: {kind, moving, fixed, axis, ...}}
        self.fastener_axes: Dict[str, Any] = {}    # from a dossier build: {fastener: [Axis(seat, advance), ...]}
        for name, shape in (parts or {}).items():
            self.add(name, shape)

    def _new(self, name: str, shape: Any, location: Any, content_hash: Optional[str]) -> Tuple[Any, Tuple[float, ...]]:
        if not name or not isinstance(name, str):
            raise ValueError("a part needs a non-empty string name")
        if name in self._parts or name in self.cavities:
            raise ValueError(f"{name!r} is already in the assembly")
        if content_hash is not None and (len(content_hash) != 64 or not all(c in "0123456789abcdef"
                                                                          for c in content_hash)):
            raise ValueError(f"{name!r}: content_hash must be a sha256 hex digest")
        topods = getattr(shape, "wrapped", shape)
        clash = solid_interference(topods)
        if clash:
            raise ValueError(f"{name!r} is a compound whose solids share volume ({clash[0][2]:.4g} mm3 between solids "
                             f"{clash[0][0]} and {clash[0][1]}); fuse it into one solid first")
        return topods, _matrix(_trsf(location))

    def add(self, name: str, shape: Any, location: Any = None, *, body: Optional[str] = None,
            group: Optional[str] = None, content_hash: Optional[str] = None) -> Part:
        """Add a part. ``location``: None, a CadQuery/build123d ``Location``, ``TopLoc_Location``,
        ``gp_Trsf``, a translation ``(x, y, z)`` or 3x4/4x4 matrix rows (rigid motions only).

        ``content_hash``: the ``shape_content_hash`` recorded when ``shape`` (as passed, before
        ``location``) was built. Pass it for shapes read back from BREP files: a read-back re-hashes
        differently, and the recorded hash is what keeps the pair cache warm."""
        topods, matrix = self._new(name, shape, location, content_hash)
        part = Part(name, topods, matrix, body or name, group, None, _hash=content_hash)
        self._parts[name] = part
        return part

    def add_cavity(self, name: str, shape: Any, *, part: str, location: Any = None,
                   content_hash: Optional[str] = None) -> Part:
        """Declare the void of ``part`` as a solid (the containment gate's reference). It moves with
        ``part``'s body in ``posed``. The part must be added first."""
        if part not in self._parts:
            raise KeyError(f"cavity {name!r}: no part {part!r} in the assembly")
        topods, matrix = self._new(name, shape, location, content_hash)
        cav = Part(name, topods, matrix, self._parts[part].body, self._parts[part].group, part, "cavity",
                   _hash=content_hash)
        self.cavities[name] = cav
        return cav

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

    def item(self, name: str) -> Part:
        """A part or a cavity by name."""
        if name in self._parts:
            return self._parts[name]
        if name in self.cavities:
            return self.cavities[name]
        raise KeyError(f"no part or cavity {name!r}")

    def shape(self, name: str):
        """The part's (or cavity's) ``TopoDS_Shape`` in assembly coordinates."""
        return self.item(name).located

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
        """A copy with every part (and cavity) of ``body`` moved by ``location``, applied after its
        placement. Parts that do not move keep their located shapes and hashes."""
        if body not in self.bodies():
            raise KeyError(f"no body {body!r}; bodies: {sorted(self.bodies())}")
        move = _trsf(location)

        def pose(p: Part) -> Part:
            if p.body != body:
                return p
            t = _trsf([p.matrix[0:4], p.matrix[4:8], p.matrix[8:12]])
            return replace(p, matrix=_matrix(move.Multiplied(t)), _located=None)

        out = Assembly()
        out._parts = {n: pose(p) for n, p in self._parts.items()}
        out.cavities = {n: pose(c) for n, c in self.cavities.items()}
        out.joints, out.fastener_axes = self.joints, self.fastener_axes
        return out

    @classmethod
    def from_cadquery(cls, assy: Any, *, body_from: str = "top") -> "Assembly":
        """Flatten a ``cadquery.Assembly``: one part per node that holds geometry, named by its path
        (``"root/arm/pin"``) and placed by the composed locations. ``body_from="top"`` labels every
        part with the root child it sits under (so a moving subassembly is one body); ``"self"``
        gives each part its own body. A node holding several solids that share volume is refused."""
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

    @classmethod
    def from_build(cls, result: Any, *, fasteners: bool = True) -> "Assembly":
        """The assembly a dossier build made: a ``cadagent.review.dossier`` ``BuildResult``, live or from
        ``load_geometry``.

        * parts and placed fasteners from ``assembly_shapes(with_hashes=True)``, already in assembly coordinates,
          keyed as the build keys them (``"hopper"``, ``"ball#3"``), each with the content hash recorded at build
          time, so a shape read back from BREP is never re-hashed and the pair cache stays warm;
        * ``Part.kind`` from ``result.kind(key)`` (``"part"`` or ``"fastener"``), ``group`` = the part's section;
        * every cavity via ``add_cavity`` with its recorded hash (its host must be a single placed part);
        * ``joints`` and ``fastener_axes`` copied onto the assembly for the motion and fastener gates;
        * body labels from ``moving_bodies`` (final; docs/dossier.md), a joint's ``moving`` part
          seeds its body, which grows transitively across ``fixed`` joints and fasteners (the fastener, what it
          clamps and what it threads into), never into a grounded part or a joint's ``fixed`` part.
        """
        geo = getattr(result, "geometry", None) or {}
        hashes = result.content_hashes() if hasattr(result, "content_hashes") else {}
        owner = getattr(result, "owner", None) or (lambda k: k)
        kind = getattr(result, "kind", None) or (lambda k: "part")
        joints = dict(getattr(result, "joints", None) or {})
        grounded = [n for n, info in (geo.get("parts") or {}).items() if info.get("grounded")]
        body_of = moving_bodies(joints, geo.get("fasteners") or {}, grounded)
        out = cls()
        for key, (shape, recorded) in result.assembly_shapes(fasteners=fasteners, with_hashes=True).items():
            name = owner(key)
            section = ((geo.get("parts") or {}).get(name) or {}).get("section") or None
            part = out.add(key, shape, content_hash=recorded, group=section, body=body_of.get(name))
            part.kind = kind(key) or "part"
        for name, shape in (getattr(result, "cavities", None) or {}).items():
            host = ((geo.get("cavities") or {}).get(name) or {}).get("part")
            if host not in out:
                raise KeyError(f"cavity {name!r} belongs to {host!r}, which is not a single placed part")
            out.add_cavity(name, shape, part=host, content_hash=hashes.get(name))
        out.joints = joints
        out.fastener_axes = dict(getattr(result, "fastener_axes", None) or {})
        return out


def moving_bodies(joints: Mapping[str, Mapping[str, Any]], fasteners: Mapping[str, Mapping[str, Any]] = {},
                  grounded: Iterable[str] = ()) -> Dict[str, str]:
    """``{name: body}`` for the parts that move: each non-fixed joint's ``moving`` part seeds a body named after
    it, which grows transitively across ``fixed`` joints and fastener declarations (the fastener, what it
    clamps and what it threads into). Growth stops at grounded parts, at any non-fixed joint's ``fixed``
    part and at another body's parts; the connectivity gate reports such links. Names, not instance keys."""
    seeds = {str(j["moving"]): str(j["moving"]) for _, j in sorted(joints.items())
             if j.get("kind") != "fixed" and j.get("moving")}
    stop = set(grounded) | {str(j.get("fixed")) for j in joints.values() if j.get("kind") != "fixed"}
    links: Dict[str, List[str]] = {}

    def link(a: Any, b: Any) -> None:
        if a and b and a != b:
            links.setdefault(str(a), []).append(str(b))
            links.setdefault(str(b), []).append(str(a))

    for _, j in sorted(joints.items()):
        if j.get("kind") == "fixed":
            link(j.get("moving"), j.get("fixed"))
    for name, info in sorted(fasteners.items()):
        link(name, info.get("clamps"))
        link(name, info.get("into"))
        link(info.get("clamps"), info.get("into"))
    body_of = dict(seeds)
    for seed in sorted(seeds):
        queue = [seed]
        while queue:
            for m in sorted(links.get(queue.pop(0), [])):
                if m not in body_of and m not in stop:
                    body_of[m] = seed
                    queue.append(m)
    return body_of


def _solids(topods) -> List[Any]:
    topexp = require("OCP.TopExp", "solid list")
    topabs = require("OCP.TopAbs", "solid list")
    ex, out = topexp.TopExp_Explorer(topods, topabs.TopAbs_SOLID), []
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _count_solids(topods) -> int:
    return len(_solids(topods))


def _validate_volume_shape(topods, *, require_solid: bool = False) -> int:
    """Reject invalid/open solids and missing exact surfaces before integration.

    OCCT's volume routines silently skip non-geometric faces. A valid compound
    may also contain free faces alongside solids; those must not contribute an
    unclosed surface integral. Valid lower-dimensional Boolean results have zero
    volume, but cannot be assembly inputs. Return the solid count.
    """
    if topods.IsNull():
        raise ValueError("null BREP cannot establish a volume")
    count = _count_solids(topods)
    if require_solid and not count:
        raise ValueError("shape has no solid; relations are volume relations")
    check = require("OCP.BRepCheck", "volume topology validation")
    if not check.BRepCheck_Analyzer(topods, True).IsValid():
        raise ValueError("invalid BREP (including open solids) cannot establish a volume")
    exp = require("OCP.TopExp", "volume topology validation")
    abs_ = require("OCP.TopAbs", "volume topology validation")
    brep = require("OCP.BRep", "volume surface validation")
    ds = require("OCP.TopoDS", "volume surface validation")
    classifier = require("OCP.BRepClass3d", "bounded solid validation")
    precision = require("OCP.Precision", "bounded solid validation")
    for solid in _solids(topods):
        region = classifier.BRepClass3d_SolidClassifier(ds.TopoDS.Solid_s(solid))
        region.PerformInfinitePoint(precision.Precision.Confusion_s())
        if region.State() != abs_.TopAbs_OUT:
            raise ValueError("solid is inverted, unbounded or has an indeterminate interior")
    faces = exp.TopExp_Explorer(topods, abs_.TopAbs_FACE)
    while faces.More():
        if not brep.BRep_Tool.IsGeometric_s(ds.TopoDS.Face_s(faces.Current())):
            raise ValueError("BREP face has no exact geometric surface")
        faces.Next()
    if count and exp.TopExp_Explorer(topods, abs_.TopAbs_FACE, abs_.TopAbs_SOLID).More():
        raise ValueError("volume shape contains faces outside its solids")
    return count


def solid_interference(shape: Any, overlap_mm3: float = 0.001) -> List[Tuple[int, int, float]]:
    """``[(i, j, shared mm3)]`` for the solids of a compound that share more than ``overlap_mm3``.

    Such a compound is not a valid boolean argument: OCCT reports the common of it with another
    shape as done and empty. Empty for a single solid."""
    topods = getattr(shape, "wrapped", shape)
    _validate_volume_shape(topods, require_solid=True)
    solids = _solids(topods)
    if len(solids) < 2:
        return []
    boxes = [bounding_box(s) for s in solids]
    out = []
    for i in range(len(solids)):
        for j in range(i + 1, len(solids)):
            a, b = boxes[i], boxes[j]
            if any(a[k + 3] < b[k] or b[k + 3] < a[k] for k in range(3)):
                continue
            shared = _measure_volume(_boolean("common", solids[i], solids[j]))
            if _above_volume(shared.value, shared.error, overlap_mm3):
                out.append((i, j, shared.value))
    return out


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


@dataclass(frozen=True)
class _VolumeEstimate:
    value: float
    error: float
    reported_error: float
    refinement_delta: float


def _measure_volume(topods) -> _VolumeEstimate:
    """Adaptive BREP integration, with an estimated (not rigorous) uncertainty.

    The default overload can badly mismeasure curved/trimmed faces. Ask for two
    refinements and retain both OCCT's aggregate absolute-error estimate and their
    delta. The Gauss overload reports a maximum face-relative error, which cannot
    be scaled by net volume when signed face contributions cancel. The GK overload
    instead sums absolute face errors at a shared reference point (OCCT 7.9.3).
    This does not change any geometric/conservation acceptance threshold.
    """
    gprop = require("OCP.GProp", "volume")
    bgprop = require("OCP.BRepGProp", "volume")
    if not _validate_volume_shape(topods):
        return _VolumeEstimate(0.0, 0.0, 0.0, 0.0)
    measured = []
    for eps in (1e-6, 1e-8):
        props = gprop.GProp_GProps()
        # OnlyClosed=False: validate, never silently omit an open shell.
        # IsUseSpan=True: split BSpline spans. CGFlag=False: centroid moments are
        # an optional witness, not a decision input; integrating tiny symmetric
        # moments with GK can be thousands of times slower than the mass itself.
        error = float(bgprop.BRepGProp.VolumePropertiesGK_s(
            topods, props, eps, False, True, False, False, False))
        value = float(props.Mass())
        if not math.isfinite(value) or not math.isfinite(error) or error < 0 or value <= 0:
            raise RuntimeError("volume integration returned invalid value/error")
        # GK divides its absolute-error sum by mass only above Epsilon(1.0).
        # In the tiny-volume branch the returned value is already absolute.
        absolute_error = error * value if value > sys.float_info.epsilon else error
        if not math.isfinite(absolute_error):
            raise RuntimeError("volume integration returned invalid absolute error")
        measured.append((props, value, error, absolute_error))
    props, value, error, absolute_error = measured[-1]
    delta = abs(value - measured[0][1])
    return _VolumeEstimate(value, max(absolute_error, delta), error, delta)


def _overlap_centroid(topods) -> Dict[str, Any]:
    """Optional approximate witness, separate from mass/error decisions.

    Gauss centroid refinements are inexpensive even for symmetric shapes. Their
    agreement is not a rigorous position bound. Never use GK mass-only GProps'
    uncomputed centroid, nor pretend a failed witness invalidates a mass verdict.
    """
    details: Dict[str, Any] = {"method": "Gauss centroid refinements 1e-6 and 1e-8; approximate witness only"}
    out = {"overlap_centroid_estimate": details}
    try:
        gprop = require("OCP.GProp", "centroid witness")
        bgprop = require("OCP.BRepGProp", "centroid witness")
        points = []
        for eps in (1e-6, 1e-8):
            props = gprop.GProp_GProps()
            error = bgprop.BRepGProp.VolumeProperties_s(topods, props, eps)
            point = props.CentreOfMass()
            xyz = (point.X(), point.Y(), point.Z())
            if not all(math.isfinite(v) for v in (*xyz, props.Mass(), error)) or props.Mass() <= 0 or error < 0:
                raise RuntimeError("centroid integration returned invalid value/error")
            points.append(xyz)
        delta = math.dist(*points)
        details["refinement_delta_mm"] = delta
        if delta > 1e-6:
            raise RuntimeError("centroid refinements disagree by more than 1e-6 mm")
        out["overlap_centroid"] = [round(v, 6) for v in points[-1]]
    except Exception as exc:
        details["unavailable"] = str(exc)
    return out


def _volume(topods) -> float:
    return _measure_volume(topods).value


def _above_volume(value: float, error: float, threshold: float) -> bool:
    if error and value - error <= threshold < value + error:
        raise RuntimeError(f"volume uncertainty straddles {threshold:g} mm3 threshold ({value:g} +/- {error:g})")
    return value > threshold


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


_INNER_TOL = 0.001   # BRepExtrema_DistShapeShape's inner-solution classification tolerance (OCCT 7.9)


def _loose(topods) -> bool:
    """Whether ``topods`` has an edge outside every face, a vertex outside every edge or a face outside every
    solid: sub-shapes a distance between faces would not see."""
    topexp = require("OCP.TopExp", "loose sub-shapes")
    abs_ = require("OCP.TopAbs", "loose sub-shapes")
    return any(topexp.TopExp_Explorer(topods, what, outside).More()
               for what, outside in ((abs_.TopAbs_EDGE, abs_.TopAbs_FACE), (abs_.TopAbs_VERTEX, abs_.TopAbs_EDGE),
                                     (abs_.TopAbs_FACE, abs_.TopAbs_SOLID)))


def _inner_vertex(solid, other) -> bool:
    """BRepExtrema_DistShapeShape's inner-solution test, one way round: whether a vertex of ``other`` classifies IN
    ``solid`` at its tolerance, with anything but OUT counted as a yes (the caller then asks BRepExtrema itself).
    BRepExtrema runs it only when ``solid`` is a SOLID or COMPSOLID, so for any other shape the answer is no.

    The same test, done once: OCCT 7.9 (``BRepExtrema_DistShapeShape::SolidTreatment``) splits the vertices into
    about ten chunks per thread, of at least three each, and builds a new ``BRepClass3d_SolidClassifier`` for every
    chunk; that construction is most of its time. It classifies at the same tolerance and looks only for IN.
    It is not a bit-for-bit copy. A reused classifier carries its choice of ray from point to point, and OCCT's
    chunks depend on the thread count. The two agree wherever the answer does not depend on the ray: every vertex
    clear of the other's boundary, which is what the clearance in ``_solid_distance`` is for. Anything but OUT
    counts as inside, so any doubt goes to BRepExtrema itself."""
    abs_ = require("OCP.TopAbs", "inner-solution test")
    if solid.ShapeType() not in (abs_.TopAbs_SOLID, abs_.TopAbs_COMPSOLID):
        return False
    classifier = require("OCP.BRepClass3d", "inner-solution test")
    topexp = require("OCP.TopExp", "inner-solution test")
    toptools = require("OCP.TopTools", "inner-solution test")
    brep = require("OCP.BRep", "inner-solution test")
    ds = require("OCP.TopoDS", "inner-solution test")
    vertices = toptools.TopTools_IndexedMapOfShape()
    topexp.TopExp.MapShapes_s(other, abs_.TopAbs_VERTEX, vertices)
    region = classifier.BRepClass3d_SolidClassifier(solid)
    for i in range(1, vertices.Extent() + 1):
        region.Perform(brep.BRep_Tool.Pnt_s(ds.TopoDS.Vertex_s(vertices.FindKey(i))), _INNER_TOL)
        if region.State() != abs_.TopAbs_OUT:
            return True
    return False


def _solid_distance(a, b, tol: Tolerances):
    """``_distance(a, b)``, the same gap and points, without BRepExtrema's slow inner-solution test (#186).

    ``BRepExtrema_DistShapeShape`` on two solids first classifies every vertex of each against the other
    (``_inner_vertex``). Only if none is IN does it measure between their vertices, edges and faces, and those are
    the sub-shapes of the faces when nothing is loose (``_loose``), met in the same order (``_faces`` keeps the
    shape's own), so its ties break the same way and the points match too. So when the faces are more than
    ``max(touch_mm, 10 x the classification tolerance)`` apart, no vertex is anywhere near the other boundary, and
    ``_inner_vertex`` finds none either way round, the distance between the faces is the call's answer. Otherwise,
    or on any kernel error, ``_distance(a, b)`` itself decides, as before."""
    if not (_loose(a) or _loose(b)):
        try:
            gap, pa, pb = _distance(_faces(a), _faces(b))
            if gap > max(tol.touch_mm, 10 * _INNER_TOL) and not _inner_vertex(a, b) and not _inner_vertex(b, a):
                return gap, pa, pb
        except Exception:  # _distance(a, b) below runs the same kernel calls and reports the failure
            pass
    return _distance(a, b)


def _shape_list(shapes):
    toptools = require("OCP.TopTools", "boolean arguments")
    out = toptools.TopTools_ListOfShape()
    for s in shapes:
        out.Append(s)
    return out


def _boolean(kind: str, a, b):
    """Non-destructive ``common`` or ``cut`` of ``a`` by ``b``. OCP 7.9 binds no error report here
    (``IsDone`` is the only signal, and it stays true on invalid input), so callers cross-check volumes."""
    algo = require("OCP.BRepAlgoAPI", "boolean")
    op = {"common": algo.BRepAlgoAPI_Common, "cut": algo.BRepAlgoAPI_Cut}[kind]()
    op.SetNonDestructive(True)        # by default OCCT may raise the arguments' tolerances in place
    op.SetArguments(_shape_list([a]))
    op.SetTools(_shape_list([b]))
    op.Build()
    if not op.IsDone():
        raise RuntimeError(f"BRepAlgoAPI_{kind.title()} did not finish")
    return op.Shape()


# ----------------------------------------------------------------------------- the crossing probe (#46)

_PROBE_GRID = 12      # samples per direction over each section patch's UV box, plus one cell of margin each side
_PROBE_CONFIRM = 8    # wrong-side samples per surface confirmed by an exact distance, farthest from the curve first
_PROBE_PER_EDGE = 24  # points taken along each section edge


def _probe_floor(tol: Tolerances) -> float:
    """The depth a point must reach on the wrong side before the crossing probe counts it: a tenth of ``touch_mm``,
    at least 1e-6 mm. Exact tangent contacts are coincident to about 1e-7 mm, so they never count."""
    return max(tol.touch_mm / 10, 1e-6)


def _section_patches(a, b) -> List[Tuple[Any, Any, List[Any]]]:
    """Where the boundaries of ``a`` and ``b`` meet: ``[(face of a, face of b, points along the curves between
    them)]``, one entry per pair of faces (either face None when the kernel names none), from a non-destructive
    ``BRepAlgoAPI_Section``.

    The section finds the curves the boolean misses (#46): on a 4 mm ball crossing a cone wall by 0.02-0.23 mm,
    where Common and Cut read no crossing, it returned the whole closed intersection curve every time."""
    occ = {m: require(f"OCP.{m}", "the crossing probe") for m in
           ("BRepAlgoAPI", "BRepAdaptor", "TopExp", "TopAbs", "TopoDS", "TopTools")}
    op = occ["BRepAlgoAPI"].BRepAlgoAPI_Section()
    op.SetNonDestructive(True)
    op.ComputePCurveOn1(False)
    op.ComputePCurveOn2(False)
    op.Approximation(False)
    op.SetArguments(_shape_list([a]))
    op.SetTools(_shape_list([b]))
    op.Build()
    if not op.IsDone():
        raise RuntimeError("BRepAlgoAPI_Section did not finish")
    abs_, ds = occ["TopAbs"], occ["TopoDS"]
    maps = []
    for s in (a, b):
        m = occ["TopTools"].TopTools_IndexedMapOfShape()
        occ["TopExp"].TopExp.MapShapes_s(s, abs_.TopAbs_FACE, m)
        maps.append(m)
    patches: Dict[Tuple[int, int], List[Any]] = {}
    ex = occ["TopExp"].TopExp_Explorer(op.Shape(), abs_.TopAbs_EDGE)
    while ex.More():
        edge = ex.Current()
        ex.Next()
        fa, fb = ds.TopoDS_Shape(), ds.TopoDS_Shape()
        ia = maps[0].FindIndex(fa) if op.HasAncestorFaceOn1(edge, fa) else 0
        ib = maps[1].FindIndex(fb) if op.HasAncestorFaceOn2(edge, fb) else 0
        curve = occ["BRepAdaptor"].BRepAdaptor_Curve(ds.TopoDS.Edge_s(edge))
        t0, t1 = curve.FirstParameter(), curve.LastParameter()
        patches.setdefault((ia, ib), []).extend(curve.Value(t0 + (t1 - t0) * k / _PROBE_PER_EDGE)
                                                for k in range(_PROBE_PER_EDGE + 1))
    return [(ds.TopoDS.Face_s(maps[0].FindKey(i)) if i else None, ds.TopoDS.Face_s(maps[1].FindKey(j)) if j else None,
             pts) for (i, j), pts in sorted(patches.items())]


def _patch_grid(face, curve: Sequence[Any], n: int) -> List[Any]:
    """Points of ``face`` on an (n + 2) x (n + 2) grid over the UV box of the ``curve`` points (projected onto the
    face), one cell of margin each side, and their UV centroid, kept where the face is; plus points along the
    face's edges in that box and every vertex of the face.

    The box follows the crossing: a 0.03 mm cap on a 4 mm ball is about 1 mm across, so the grid's spacing is
    about 0.1 mm there, where a fixed grid over the face would step over it. A corner is the deepest point of a
    tilted box's crossing, so the vertices are taken as they are."""
    occ = {m: require(f"OCP.{m}", "the crossing probe") for m in
           ("BRep", "BRepAdaptor", "BRepTools", "BRepTopAdaptor", "ShapeAnalysis", "TopAbs", "TopExp", "TopoDS",
            "gp")}
    surf = occ["BRep"].BRep_Tool.Surface_s(face)            # with the face's location applied
    project = occ["ShapeAnalysis"].ShapeAnalysis_Surface(surf)
    uv = [project.ValueOfUV(p, 1e-7) for p in curve]
    us, vs = [q.X() for q in uv], [q.Y() for q in uv]
    lo = occ["BRepTools"].BRepTools.UVBounds_s(face)
    periods = (surf.UPeriod() if surf.IsUPeriodic() else None, surf.VPeriod() if surf.IsVPeriodic() else None)

    def unwrap(x, ref, period):     # across the seam, to within half a period of ``ref``
        return ref + ((x - ref + period / 2) % period) - period / 2 if period else x
    us, vs = [unwrap(x, us[0], periods[0]) for x in us], [unwrap(x, vs[0], periods[1]) for x in vs]
    boxes = []
    for vals in (us, vs):
        step = (max(vals) - min(vals)) / (n - 1)
        boxes.append((min(vals) - step, max(vals) + step))
    inside = occ["BRepTopAdaptor"].BRepTopAdaptor_FClass2d(face, 1e-7)

    def on_face(u, v):
        if periods[0]:
            u = lo[0] + (u - lo[0]) % periods[0]
        if periods[1]:
            v = lo[2] + (v - lo[2]) % periods[1]
        if inside.Perform(occ["gp"].gp_Pnt2d(u, v)) == occ["TopAbs"].TopAbs_IN:
            return surf.Value(u, v)
        return None

    (u0, u1), (v0, v1) = boxes
    m = n + 2
    uvs = [(u0 + (u1 - u0) * i / (m - 1), v0 + (v1 - v0) * j / (m - 1)) for i in range(m) for j in range(m)]
    uvs.append((sum(us) / len(us), sum(vs) / len(vs)))
    points = [p for p in (on_face(u, v) for u, v in uvs) if p is not None]
    # The face's own boundary in the box (a tilted cylinder's rim), and every vertex: a crossing can run from the
    # curve to the face's edge, and a corner is the deepest point of a tilted box's crossing.
    ex = occ["TopExp"].TopExp_Explorer(face, occ["TopAbs"].TopAbs_EDGE)
    while ex.More():
        edge = occ["TopoDS"].TopoDS.Edge_s(ex.Current())
        ex.Next()
        if occ["BRep"].BRep_Tool.Degenerated_s(edge):        # a pole: its vertex is taken below
            continue
        pcurve = occ["BRepAdaptor"].BRepAdaptor_Curve2d(edge, face)
        line = occ["BRepAdaptor"].BRepAdaptor_Curve(edge)
        t0, t1 = pcurve.FirstParameter(), pcurve.LastParameter()
        for k in range(4 * n + 1):
            t = t0 + (t1 - t0) * k / (4 * n)
            uv = pcurve.Value(t)
            if u0 <= unwrap(uv.X(), us[0], periods[0]) <= u1 and v0 <= unwrap(uv.Y(), vs[0], periods[1]) <= v1:
                points.append(line.Value(t))
    ex = occ["TopExp"].TopExp_Explorer(face, occ["TopAbs"].TopAbs_VERTEX)
    while ex.More():
        points.append(occ["BRep"].BRep_Tool.Pnt_s(occ["TopoDS"].TopoDS.Vertex_s(ex.Current())))
        ex.Next()
    return points


def _has_faces(topods) -> bool:
    topexp = require("OCP.TopExp", "the crossing probe")
    abs_ = require("OCP.TopAbs", "the crossing probe")
    return topods is not None and not topods.IsNull() and topexp.TopExp_Explorer(topods, abs_.TopAbs_FACE).More()


def _crossing_probe(a, b, looks: Sequence[Tuple[int, str]], piece, floor: float) -> Optional[Dict[str, Any]]:
    """An independent check of a ``touching`` or ``contains`` answer where the two boundaries meet (#46).

    OCCT's boolean can miss a shallow near-tangent crossing: Common and Cut then agree with each other
    (``vol = common + cut`` holds) and read no crossing at all. ``BRepAlgoAPI_Section`` finds the intersection
    curves in those cases. So sample each surface on a grid over the box of each patch of curve
    (``_patch_grid``) and classify the samples against the other solid (``BRepClass3d_SolidClassifier``, a ray
    test with no surface intersection). ``looks`` names which surface must not be on which side: ``(0, "in")``
    means no point of ``a``'s surface inside ``b``; ``(1, "out")`` no point of ``b``'s surface outside ``a``.

    A sample on the wrong side is confirmed by its exact distance to the other's faces (more than ``floor``),
    then checked against ``piece``, the kernel's own result for that region (the common for ``touching``, the
    inner part's cut for ``contains``): a sample on ``piece`` is a crossing the kernel saw and measured (a sharp
    corner 0.02 mm in, with 1e-6 mm3 shared, is ``touching`` by the tolerances). The deepest sample that is
    not on ``piece`` is returned (``None`` when there is none): the kernel missed a crossing at least that deep.

    A safety net, not a proof: a crossing the section also misses, or one whose samples all lie within ``floor``
    of the other's boundary, is not seen."""
    occ = {m: require(f"OCP.{m}", "the crossing probe") for m in ("BRepClass3d", "BRepBuilderAPI", "TopAbs")}
    np = require("numpy", "the crossing probe")
    patches = _section_patches(a, b)
    if not patches:
        return None
    target = {"in": occ["TopAbs"].TopAbs_IN, "out": occ["TopAbs"].TopAbs_OUT}
    on_piece = _has_faces(piece)
    found: Optional[Dict[str, Any]] = None
    for side, want in looks:
        other = b if side == 0 else a
        classifier = occ["BRepClass3d"].BRepClass3d_SolidClassifier(other)
        wrong = []
        for patch in patches:
            if patch[side] is None:
                continue
            curve = np.array([(q.X(), q.Y(), q.Z()) for q in patch[2]])
            for p in _patch_grid(patch[side], patch[2], _PROBE_GRID):
                classifier.Perform(p, floor)
                if classifier.State() == target[want]:   # farthest from the curve first: the middle of a cap
                    far = float(np.min(np.linalg.norm(curve - (p.X(), p.Y(), p.Z()), axis=1)))
                    wrong.append((-far, len(wrong), p))
        if not wrong:
            continue
        other_faces = _faces(other)
        for _, _, p in sorted(wrong)[:_PROBE_CONFIRM]:
            vertex = occ["BRepBuilderAPI"].BRepBuilderAPI_MakeVertex(p).Vertex()
            depth, _, near = _distance(vertex, other_faces)
            if depth <= floor or (found is not None and depth <= found["depth_mm"]):
                continue
            if on_piece and _distance(vertex, piece)[0] <= floor:
                continue            # the kernel's own result has this point: a crossing it saw and measured
            found = {"surface": side, "lies": f"{want}side", "point": _pt(p), "depth_mm": round(depth, 6),
                     "nearest_point": near, "floor_mm": floor, "section_patches": len(patches)}
    return found


def _kernel_version() -> str:
    try:
        import OCP
        return str(getattr(OCP, "__version__", "unknown"))
    except ImportError:
        return "none"


# ----------------------------------------------------------------------------- narrow phase

def relate(a: Any, b: Any, tol: Tolerances = Tolerances(), *, names: Tuple[str, str] = ("a", "b"),
           volumes: Optional[Tuple[Any, Any]] = None, contact_area: bool = True,
           validated: bool = False) -> Relation:
    """Exact relation of two shapes (already in one frame), no broad phase and no cache.

    Use ``relate_pair`` for named parts and cavities of an ``Assembly`` (it is cached). ``volumes``
    may pass two trusted volumes (or internal estimates) when the caller has them; a raw float declares
    no additional measurement uncertainty. ``validated`` skips the input topology and
    multi-solid checks (``Assembly`` already ran them). Anything doubtful gives ``unknown``
    with the reason in ``error``.
    """
    sa, sb = getattr(a, "wrapped", a), getattr(b, "wrapped", b)
    integration = {"method": "adaptive BRepGProp GK, requested relative errors 1e-6 and 1e-8",
                   "error_basis": "max(OCCT summed absolute face-error estimates, refinement delta); not a rigorous bound",
                   "max_estimated_error_mm3": 0.0, "max_refinement_delta_mm3": 0.0}

    def measure(shape, supplied=None):
        m = (_measure_volume(shape) if supplied is None else supplied if isinstance(supplied, _VolumeEstimate)
             else _VolumeEstimate(float(supplied), 0.0, 0.0, 0.0))
        if not all(math.isfinite(v) for v in (m.value, m.error, m.refinement_delta)) or m.error < 0:
            raise RuntimeError("volume integration returned invalid value/error")
        if m.value < -m.error:
            raise RuntimeError("volume integration returned a negative volume")
        integration["max_estimated_error_mm3"] = max(integration["max_estimated_error_mm3"], m.error)
        integration["max_refinement_delta_mm3"] = max(integration["max_refinement_delta_mm3"], m.refinement_delta)
        return m

    def unknown(why: str, **witness) -> Relation:
        return Relation(names[0], names[1], "unknown", error=why,
                        witness={**witness, "volume_integration": integration})

    def crossing(state: str, looks, piece) -> Optional[Relation]:
        """``unknown`` when the crossing probe finds a crossing the kernel's ``state`` answer leaves out (#46)."""
        try:
            hit = _crossing_probe(sa, sb, looks, piece, _probe_floor(tol))
        except Exception as exc:  # the cross-check could not run: the answer is not checked, so not given
            return unknown(f"crossing probe failed on a {state} pair: {type(exc).__name__}: {exc}")
        if hit is None:
            return None
        surface, other = names[hit["surface"]], names[1 - hit["surface"]]
        hit.update(surface=surface, other=other)
        return unknown(f"crossing probe: a point of {surface}'s surface lies {hit['depth_mm']:.3g} mm {hit['lies']} "
                       f"{other} at {hit['point']}, which the boolean's {state} answer leaves out (a near-tangent "
                       "crossing the kernel missed, #46; its volume is not measured)", crossing_probe=hit)

    try:
        if not validated:
            for n, s in zip(names, (sa, sb)):
                clash = solid_interference(s, tol.overlap_mm3)
                if clash:
                    return unknown(f"{n} is a compound whose solids share volume; fuse it first")
        ma, mb = (measure(s, v) for s, v in zip((sa, sb), volumes or (None, None)))
        va, vb = ma.value, mb.value
        if va <= ma.error or vb <= mb.error:
            return unknown(f"non-positive volume ({va:.6g}, {vb:.6g} mm3)")
        check = tol.volume_check_mm3 + 1e-6 * max(va, vb)
        common = _boolean("common", sa, sb)
        mc = measure(common)
        vc = mc.value
        cut_a = _boolean("cut", sa, sb)
        mac = measure(cut_a)
        a_out = mac.value
        # Uncertainty consumes the existing conservation budget; it never enlarges it.
        if abs(va - vc - a_out) + ma.error + mc.error + mac.error > check:
            return unknown(f"volumes disagree: vol(a) {va:.6g} != common {vc:.6g} + cut {a_out:.6g} mm3")
        if _above_volume(vc, mc.error, tol.overlap_mm3):
            cut_b = _boolean("cut", sb, sa)
            mbc = measure(cut_b)
            b_out = mbc.value
            if abs(vb - vc - b_out) + mb.error + mc.error + mbc.error > check:
                return unknown(f"volumes disagree: vol(b) {vb:.6g} != common {vc:.6g} + cut {b_out:.6g} mm3")
            a_out, b_out = max(a_out, 0.0), max(b_out, 0.0)
            a_in = not _above_volume(a_out, mac.error, tol.contain_mm3)
            b_in = not _above_volume(b_out, mbc.error, tol.contain_mm3)
            witness: Dict[str, Any] = {**_overlap_centroid(common),
                                       "overlap_box": [round(v, 6) for v in bounding_box(common)],
                                       "volume_integration": integration}
            fields = dict(gap_mm=0.0, overlap_mm3=round(vc, 6), a_outside_b_mm3=round(a_out, 6),
                          b_outside_a_mm3=round(b_out, 6))
            if a_in or b_in:
                contained = "both" if a_in and b_in else ("a_in_b" if a_in else "b_in_a")
                inner, outer = (sa, sb) if contained != "b_in_a" else (sb, sa)
                wall, p_in, p_out = _distance(_faces(inner), _faces(outer))
                if contained != "both" and wall <= _probe_floor(tol):    # the boundaries meet: check for a crossing
                    looks, piece = (((0, "out"), (1, "in")), cut_a) if contained == "a_in_b" else \
                        (((1, "out"), (0, "in")), cut_b)
                    missed = crossing("contains", looks, piece)
                    if missed is not None:
                        return missed
                witness.update(inner_point=p_in, outer_point=p_out)
                return Relation(names[0], names[1], "contains", contained=contained, wall_mm=round(wall, 6),
                                witness=witness, **fields)
            return Relation(names[0], names[1], "overlapping", witness=witness, **fields)
        gap, pa, pb = _solid_distance(sa, sb, tol)
        witness = {"point_a": pa, "point_b": pb, "volume_integration": integration}
        if gap <= tol.touch_mm:
            if gap <= _probe_floor(tol):         # the boundaries meet: check for a crossing the booleans missed
                missed = crossing("touching", ((0, "in"), (1, "in")), common)
                if missed is not None:
                    return missed
            area = None
            if contact_area:
                try:
                    area = round(_area(_boolean("common", _faces(sa), sb)), 6) if gap <= 1e-9 else 0.0
                except Exception:   # a witness only: the state does not depend on it
                    area = None
            return Relation(names[0], names[1], "touching", gap_mm=round(gap, 6), overlap_mm3=round(max(vc, 0.0), 6),
                            contact_area_mm2=area, witness=witness)
        return Relation(names[0], names[1], "apart", gap_mm=round(gap, 6), overlap_mm3=round(max(vc, 0.0), 6),
                        witness=witness)
    except Exception as exc:  # the OCCT wrappers raise several types; record, never pass silently
        return unknown(f"{type(exc).__name__}: {exc}")


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

    ``get(a, b)`` always answers: a stored relation; ``apart`` with ``exact=False`` when the boxes
    alone prove a gap over ``touch_mm``; otherwise ``unchecked`` (a pair excluded by ``only`` or
    ``skip_pairs``). ``get(a, b, exact=True)`` runs the kernel for any pair not yet examined.
    """
    assembly: Assembly
    tolerances: Tolerances
    relations: Dict[Tuple[str, str], Relation]
    lower_bounds: Dict[Tuple[str, str], float]
    stats: Dict[str, Any]
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    cache: Optional[PairCache] = None
    contact_area: bool = True

    def get(self, a: str, b: str, *, exact: bool = False) -> Relation:
        for key, flip in (((a, b), False), ((b, a), True)):
            if key in self.relations:
                rel = self.relations[key]
                return rel.flipped() if flip else rel
        if a not in self.assembly or b not in self.assembly or a == b:
            raise KeyError(f"no pair ({a!r}, {b!r}) in the assembly")
        if exact:
            rel = _relate_items(self.assembly, a, b, self.tolerances, self.cache, self.contact_area)
            self.relations[(a, b)] = rel
            return rel
        bound = self.lower_bounds.get((a, b), self.lower_bounds.get((b, a)))
        state = "apart" if bound is not None and bound > self.tolerances.touch_mm else "unchecked"
        return Relation(a, b, state, gap_lower_bound_mm=None if bound is None else round(bound, 6), exact=False)

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

    def interferences(self) -> List[Relation]:
        """overlapping and contains relations: shared volume between two parts."""
        return self.by_state(*INTERFERENCE_STATES)

    def of(self, name: str) -> List[Relation]:
        """Every exact relation involving ``name``, oriented with ``name`` as ``a``."""
        return [r if r.a == name else r.flipped() for r in self.relations.values() if name in (r.a, r.b)]

    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready: tolerances, stats, and the exact relations (broad-phase-only pairs are counted, not listed)."""
        return {"tolerances": asdict(self.tolerances), "stats": dict(self.stats),
                "relations": [r.to_dict() for r in self.relations.values()],
                "skipped_pairs": [list(p) for p in self.skipped],
                "method": "AABB broad phase (near_mm), then non-destructive BRepAlgoAPI Common and Cut volumes "
                          "(cross-checked) and BRepExtrema_DistShapeShape, with a section-guided crossing probe "
                          "where the boundaries meet",
                "kernel": f"OCP {_kernel_version()}",
                "physical_fit_verified": False}


def _pair_key(asm: Assembly, a: str, b: str, tol: Tolerances, contact_area: bool) -> Tuple[str, bool]:
    ka, kb = asm.item(a).key, asm.item(b).key
    flip = kb < ka
    lo, hi = (kb, ka) if flip else (ka, kb)
    return digest("relation", RELATIONS_VERSION, _kernel_version(), tol.key(), f"area={contact_area}", lo, hi), flip


def _relate_items(asm: Assembly, a: str, b: str, tol: Tolerances, cache: Optional[PairCache],
                  contact_area: bool, volumes: Optional[Dict[str, _VolumeEstimate]] = None) -> Relation:
    """One pair (parts or cavities) through the cache. ``volumes`` memoises volumes across pairs."""
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
        try:
            for n in (a, b):
                if n not in volumes:
                    volumes[n] = _measure_volume(asm.shape(n))
        except Exception as exc:
            return Relation(a, b, "unknown", error=f"volume integration failed: {exc}")
        vols = (volumes[a], volumes[b])
    rel = relate(asm.shape(a), asm.shape(b), tol, names=(a, b), volumes=vols, contact_area=contact_area,
                 validated=True)
    if cache is not None and rel.state != "unknown":
        stored = rel.flipped() if flip else rel
        cache.put(key, {k: v for k, v in stored.to_dict().items() if k not in ("a", "b", "cached")})
    return rel


def relate_pair(assembly: Assembly, a: str, b: str, tol: Tolerances = Tolerances(), *,
                cache: Optional[PairCache] = None, contact_area: bool = True) -> Relation:
    """The exact relation of two named items of ``assembly`` (parts or cavities), through ``cache``
    when given: the containment gate's item-against-cavity query."""
    if a == b:
        raise ValueError("a relation needs two different items")
    assembly.item(a), assembly.item(b)          # KeyError for an unknown name
    return _relate_items(assembly, a, b, tol, cache, contact_area)


def relation_table(assembly: Any, tol: Tolerances = Tolerances(), *, cache: Optional[PairCache] = None,
                   only: Optional[Iterable[str]] = None, skip_pairs: Iterable[Sequence[str]] = (),
                   contact_area: bool = True) -> RelationTable:
    """Build the relation table of an assembly's parts (an ``Assembly`` or a ``{name: shape}`` mapping).

    ``only`` restricts the narrow phase to pairs with at least one part in it (the moving set of a
    motion pose); ``skip_pairs`` lists pairs never queried (variants that never coexist), reported
    in ``skipped``. Pairs left out either way read ``unchecked`` unless their boxes prove them apart.
    ``cache`` (a ``PairCache``) makes unchanged pairs free on the next run.
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
    volumes: Dict[str, _VolumeEstimate] = {}
    kernel = 0
    for a, b in candidates:
        rel = _relate_items(asm, a, b, tol, cache, contact_area, volumes)
        kernel += 0 if rel.cached else 1
        rels[(a, b)] = rel
    t2 = time.perf_counter()
    n = len(asm)
    stats = {"parts": n, "pairs": n * (n - 1) // 2, "candidates": len(candidates), "kernel_queries": kernel,
             "cache_hits": (cache.hits - hits0) if cache is not None else 0,
             "broad_phase_s": round(t1 - t0, 4), "narrow_phase_s": round(t2 - t1, 4),
             "states": {s: sum(1 for r in rels.values() if r.state == s) for s in STATES}}
    return RelationTable(asm, tol, rels, bounds, stats, skipped, cache, contact_area)
