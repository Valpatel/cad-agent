"""Declare the geometric facts the gates need, in the build script, next to the code that makes the geometry.

::

    from cadagent.dossier import Axis, part, cavity, joint, fastener, assembly

    @part("hopper", section="S3")                 # registers the shape; joined to the YAML card by id
    def hopper(p): ...                            # returns a shape in assembly coordinates, as today

    @cavity("hopper", "hopper_cavity")            # the void the containment gate tests against (a declared solid)
    def hopper_cavity(p): return hopper_inner(p)

    @joint("I9", kind="revolute", axis=lambda p: Axis(p["flap_pivot"], (0, 1, 0)), range_deg=(0, 70),
           parts=("hopper_flap", "hopper"))
    def flap_pivot(p): ...                        # optional body, never called; the declaration is what matters

    fastener("screw_m3x8", clamps="hopper", into="pan_base", via="I7", tool="hex_2.5",
             at=lambda p: [Axis((x, y, p["flange_z"]), (0, 0, -1)) for x, y in p["flange_holes"]])

    assembly.step(1, fit="pan_base", onto="bench_base", direction="-Z", tool="hex_2.5", fasteners=["screw_m4x12"] * 3)

    if __name__ == "__main__":
        build()                                   # writes exports/dossier-geometry.json and exports/dossier-shapes/

Frames. A part function returns its shape in assembly coordinates, unless ``@part(..., place=...)`` gives the
placement (a ``cq.Location``, an ``(x, y, z)`` translation, or a list of them for several instances), in which case
the function returns the shape in its own frame and the part's cavities follow the same placement. Joint and
fastener axes are always in assembly coordinates. A fastener axis starts on the head seat and points the way the
screw advances; a fastener ``shape`` is modelled in the McMaster screw frame (``skills/mcmaster-parts``: origin on
the seat, +Z out of the hole, shank on -Z).

Instances. A part function (or ``place``) that returns a list makes one instance per item (40 loose balls); the
gates see them as ``ball#0`` .. ``ball#39``.

Migration. A build that does not use decorators keeps ``print_parts()`` and adds ``dossier_items()``;
``build_module()`` registers both, a decorated part winning over a ``print_parts()`` entry of the same name, so a
build moves one part at a time.

Hashes. Every shape's ``sha256`` is the content hash of its BREP text (OCCT format version 1, without
triangulation), the bytes of the file written to ``exports/dossier-shapes/<sha256>.brep``. It is stable across
processes and runs; an OCCT upgrade may change it, which only invalidates a sign-off, never hides a change. Compare
the recorded hashes (a gate cache keys on them); do not re-hash a shape loaded from its file (``shape_brep``). The
shapes directory is build output and gets its own ``.gitignore``; the JSON is the record to commit.

Nothing here proves fit: the registry records what the build made and what the author declared. The gates compare
them; ``physical_fit_verified`` is always false.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from .model import DIRECTION_RE, ID_RE, JOINT_KINDS, Issue, Where

SCHEMA = "cad-agent.dossier-geometry/1"
GEOMETRY_FILE = "dossier-geometry.json"
SHAPES_DIR = "dossier-shapes"
MECHANISM_KINDS = ("revolute", "slider", "cylindrical", "planar", "ball")
RIGID_KINDS = ("fastened", "bonded", "press_fit", "snap_fit", "contact", "gap")
_THIS_FILE = os.path.normcase(os.path.abspath(__file__))


class RegistryError(ValueError):
    """A declaration is malformed, or a declared function failed during ``build()``."""


Vec = Tuple[float, float, float]


@dataclass(frozen=True)
class Axis:
    """A point and a direction in assembly coordinates (mm). Kernel-free; ``Axis.of`` also takes a
    build123d ``Axis`` (``position``/``direction``), a ``cq.Vector`` pair or an ``(origin, direction)`` tuple."""
    origin: Vec
    direction: Vec

    def __init__(self, origin: Any, direction: Any):
        o, d = _vec3(origin, "axis origin"), _vec3(direction, "axis direction")
        n = math.sqrt(sum(c * c for c in d))
        if n == 0:
            raise RegistryError("axis direction is the zero vector")
        object.__setattr__(self, "origin", o)
        object.__setattr__(self, "direction", (d[0] / n, d[1] / n, d[2] / n))

    @classmethod
    def of(cls, value: Any) -> "Axis":
        if isinstance(value, Axis):
            return value
        if hasattr(value, "position") and hasattr(value, "direction"):      # build123d Axis
            return cls(value.position, value.direction)
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return cls(value[0], value[1])
        raise RegistryError(f"expected an Axis or (origin, direction), got {value!r}")

    def to_dict(self) -> Dict[str, List[float]]:
        return {"origin": [_r(c) for c in self.origin], "direction": [_r(c) for c in self.direction]}


def _vec3(value: Any, what: str) -> Vec:
    if hasattr(value, "toTuple"):                                            # cq.Vector
        value = value.toTuple()
    elif hasattr(value, "X") and hasattr(value, "Y") and hasattr(value, "Z") and not callable(value.X):
        value = (value.X, value.Y, value.Z)                                  # build123d Vector
    try:
        out = tuple(float(c) for c in value)
    except (TypeError, ValueError):
        raise RegistryError(f"{what} must be three numbers, got {value!r}") from None
    if len(out) != 3:
        raise RegistryError(f"{what} must be three numbers, got {value!r}")
    return out  # type: ignore[return-value]


def _r(x: float) -> float:
    """Round for a stable JSON diff (1 nm)."""
    v = round(float(x), 6)
    return 0.0 if v == 0 else v


# ----------------------------------------------------------------------------------------------- declarations

@dataclass
class PartDecl:
    name: str
    section: str = ""
    make: Any = None            # callable(p) / callable() returning the shape(s), or the shape itself
    place: Any = None           # callable(p) or value: a location or a list of them
    grounded: bool = False
    free: bool = False
    reason: str = ""
    where: str = ""


@dataclass
class CavityDecl:
    part: str
    name: str
    make: Any = None
    where: str = ""


@dataclass
class JointDecl:
    interface: str
    kind: str
    moving: str
    fixed: str
    axis: Any                   # Axis, (origin, direction) or callable(p)
    range: Optional[Tuple[float, float]] = None
    unit: str = ""              # deg | mm
    range2: Optional[Tuple[float, float]] = None    # the slide range of a cylindrical joint (mm)
    intended_contacts: List[Tuple[str, str]] = field(default_factory=list)
    samples: Optional[int] = None
    body: Optional[Callable] = None
    where: str = ""


@dataclass
class FastenerDecl:
    name: str
    key: str                    # catalogue key (McMaster skill or cadagent.fasteners)
    clamps: str                 # the part under the head
    into: str                   # the part it threads into (insert, tapped hole or nut side)
    at: Any                     # Axis, list of Axis, or callable(p) returning either
    via: str = ""
    tool: str = ""
    length_mm: Optional[float] = None
    diameter_mm: Optional[float] = None
    thread_start_mm: Any = None     # distance from the seat along the axis to the first engaged thread
    thread_depth_mm: Any = None     # thread available beyond thread_start
    min_engagement_mm: Any = None
    shape: Any = None               # optional: callable(p) or shape in the McMaster screw frame
    where: str = ""


@dataclass
class StepDecl:
    order: int
    fit: str
    onto: List[str] = field(default_factory=list)
    direction: Any = ""
    tool: str = ""
    fasteners: List[str] = field(default_factory=list)
    access_check: str = ""
    note: str = ""
    where: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"order": self.order, "fit": self.fit, "onto": list(self.onto)}
        for key in ("direction", "tool", "fasteners", "access_check", "note"):
            value = getattr(self, key)
            if value not in ("", [], None):
                out[key] = list(value) if isinstance(value, (list, tuple)) else value
        out["declared_at"] = self.where
        return out


def _caller_where() -> str:
    """file:line of the first frame outside this module (the build script's declaration)."""
    frame = sys._getframe(1)
    while frame and os.path.normcase(os.path.abspath(frame.f_code.co_filename)) == _THIS_FILE:
        frame = frame.f_back
    return f"{frame.f_code.co_filename}:{frame.f_lineno}" if frame else ""


def _def_where(fn: Any) -> str:
    code = getattr(fn, "__code__", None)
    return f"{code.co_filename}:{code.co_firstlineno}" if code else _caller_where()


def _check_id(value: str, what: str) -> str:
    if not isinstance(value, str) or not ID_RE.match(value):
        raise RegistryError(f"{what} {value!r} is not a valid dossier id (a letter, then letters, digits, _ - .)")
    return value


def _range(value: Any, what: str) -> Optional[Tuple[float, float]]:
    if value is None:
        return None
    try:
        lo, hi = (float(v) for v in value)
    except (TypeError, ValueError):
        raise RegistryError(f"{what} must be (low, high), got {value!r}") from None
    if lo > hi:
        raise RegistryError(f"{what} is ({lo}, {hi}): low is above high")
    return lo, hi


class _Steps:
    """``assembly.step(...)``: bound to one registry."""

    def __init__(self, registry: "Registry"):
        self._registry = registry

    def step(self, order: int, fit: str, onto: Union[str, Sequence[str], None] = None, *, direction: Any = "",
             tool: str = "", fasteners: Sequence[str] = (), access_check: str = "", note: str = "") -> StepDecl:
        if isinstance(order, bool) or not isinstance(order, int):
            raise RegistryError(f"assembly step order must be an integer, got {order!r}")
        if direction and not (isinstance(direction, str) and DIRECTION_RE.match(direction)) and not (
                isinstance(direction, (list, tuple)) and len(direction) == 3):
            raise RegistryError(f"assembly step {order}: direction {direction!r}; use +X..-Z or (x, y, z)")
        onto_list = [onto] if isinstance(onto, str) else list(onto or [])
        decl = StepDecl(order=order, fit=fit, onto=onto_list, direction=direction, tool=tool,
                        fasteners=list(fasteners), access_check=access_check, note=note, where=_caller_where())
        self._registry._add("steps", order, decl, f"assembly step {order}")
        return decl


class Registry:
    """Collects parts, cavities, joints, fasteners and assembly steps. ``cadagent.dossier.REGISTRY`` is the one
    the module-level decorators write to; tests and tools can make their own."""

    def __init__(self) -> None:
        self.parts: Dict[str, PartDecl] = {}
        self.cavities: Dict[str, CavityDecl] = {}
        self.joints: Dict[str, JointDecl] = {}
        self.fasteners: Dict[str, FastenerDecl] = {}
        self.steps: Dict[int, StepDecl] = {}
        self.assembly = _Steps(self)

    def clear(self) -> None:
        for table in (self.parts, self.cavities, self.joints, self.fasteners, self.steps):
            table.clear()

    def __len__(self) -> int:
        return sum(len(t) for t in (self.parts, self.cavities, self.joints, self.fasteners, self.steps))

    def _add(self, table: str, key: Any, decl: Any, what: str) -> None:
        items = getattr(self, table)
        old = items.get(key)
        if old is not None and old.where != decl.where:
            raise RegistryError(f"{what} is declared twice: {old.where} and {decl.where}")
        items[key] = decl      # the same declaration site again (a re-import) replaces it

    # -- declarations
    def part(self, name: str, section: str = "", *, place: Any = None, grounded: bool = False, free: bool = False,
             reason: str = "") -> Callable:
        """Decorator: the function makes part ``name`` (joined to the dossier card with that id).
        ``grounded`` marks a part the connectivity gate treats as ground; ``free`` a part allowed to float (loose
        items, an exploded lid), which needs a ``reason``."""
        _check_id(name, "part name")
        if free and not reason:
            raise RegistryError(f"part {name!r} is declared free (allowed to float) without a reason")
        if free and grounded:
            raise RegistryError(f"part {name!r} cannot be both grounded and free")

        def register(fn: Callable) -> Callable:
            self.add_part(name, fn, section=section, place=place, grounded=grounded, free=free, reason=reason,
                          where=_def_where(fn))
            return fn
        return register

    def add_part(self, name: str, make: Any, *, section: str = "", place: Any = None, grounded: bool = False,
                 free: bool = False, reason: str = "", where: str = "") -> PartDecl:
        """Register a part from a function or an already-built shape (the ``print_parts()`` path)."""
        _check_id(name, "part name")
        if free and not reason:
            raise RegistryError(f"part {name!r} is declared free (allowed to float) without a reason")
        decl = PartDecl(name=name, section=section, make=make, place=place, grounded=grounded, free=free,
                        reason=reason, where=where or _caller_where())
        self._add("parts", name, decl, f"part {name!r}")
        return decl

    def cavity(self, part: str, name: str) -> Callable:
        """Decorator: the function returns the void inside ``part`` that the containment gate tests against, as a
        solid (a cavity is always declared; the gates do not derive one)."""
        _check_id(part, "cavity part")
        _check_id(name, "cavity name")

        def register(fn: Callable) -> Callable:
            self.add_cavity(part, name, fn, where=_def_where(fn))
            return fn
        return register

    def add_cavity(self, part: str, name: str, make: Any, where: str = "") -> CavityDecl:
        decl = CavityDecl(part=part, name=_check_id(name, "cavity name"), make=make, where=where or _caller_where())
        self._add("cavities", name, decl, f"cavity {name!r}")
        return decl

    def joint(self, interface: str, kind: str = "revolute", *, parts: Sequence[str], axis: Any,
              range_deg: Any = None, range_mm: Any = None, intended_contacts: Iterable[Sequence[str]] = (),
              samples: Optional[int] = None) -> Callable:
        """Declare the joint that realises interface ``interface``: ``parts=(moving, fixed)``, the axis in assembly
        coordinates (or a function of the parameters), and the motion range (``range_deg`` for revolute,
        ``range_mm`` for slider, both for cylindrical). ``intended_contacts`` are the pairs allowed to touch over
        the range (the stops). Registers on the call; use it bare or as a decorator on a body that documents it."""
        decl = self._joint_decl(interface, kind, parts, axis, range_deg, range_mm, intended_contacts, samples,
                                _caller_where())
        self._add("joints", interface, decl, f"joint {interface!r}")

        def attach(fn: Callable) -> Callable:
            decl.body = fn
            return fn
        return attach

    @staticmethod
    def _joint_decl(interface, kind, parts, axis, range_deg, range_mm, intended_contacts, samples, where):
        _check_id(interface, "joint interface")
        if kind not in JOINT_KINDS:
            raise RegistryError(f"joint {interface!r}: kind {kind!r}; one of {', '.join(JOINT_KINDS)}")
        parts = list(parts)
        if len(parts) != 2 or parts[0] == parts[1]:
            raise RegistryError(f"joint {interface!r}: parts must be (moving, fixed), got {parts!r}")
        rdeg, rmm = _range(range_deg, f"joint {interface!r} range_deg"), _range(range_mm, f"joint {interface!r} range_mm")
        need = {"revolute": ("deg",), "slider": ("mm",), "cylindrical": ("deg", "mm"), "fixed": (),
                "planar": (), "ball": ()}[kind]
        if "deg" in need and rdeg is None or "mm" in need and rmm is None:
            raise RegistryError(f"joint {interface!r} ({kind}) needs " + " and ".join(
                {"deg": "range_deg", "mm": "range_mm"}[u] for u in need))
        if kind == "fixed" and (rdeg or rmm):
            raise RegistryError(f"joint {interface!r} is fixed and cannot have a range")
        if samples is not None and (isinstance(samples, bool) or not isinstance(samples, int) or samples < 2):
            raise RegistryError(f"joint {interface!r}: samples must be an integer >= 2")
        if not callable(axis):
            axis = Axis.of(axis)
        contacts = []
        for pair in intended_contacts:
            pair = tuple(pair)
            if len(pair) != 2:
                raise RegistryError(f"joint {interface!r}: intended_contacts entries are (part, part), got {pair!r}")
            contacts.append((str(pair[0]), str(pair[1])))
        primary, unit = (rdeg, "deg") if rdeg is not None else (rmm, "mm") if rmm is not None else (None, "")
        return JointDecl(interface=interface, kind=kind, moving=str(parts[0]), fixed=str(parts[1]), axis=axis,
                         range=primary, unit=unit, range2=rmm if kind == "cylindrical" else None,
                         intended_contacts=contacts, samples=samples, where=where)

    def fastener(self, key: str, *, clamps: str, into: str, at: Any, name: str = "", via: str = "", tool: str = "",
                 length_mm: Optional[float] = None, diameter_mm: Optional[float] = None, thread_start_mm: Any = None,
                 thread_depth_mm: Any = None, min_engagement_mm: Any = None, shape: Any = None) -> FastenerDecl:
        """Declare ``len(at)`` fasteners of catalogue item ``key`` clamping ``clamps`` to ``into``. ``at`` is one
        axis per screw (seat point, direction of advance), or a function of the parameters returning them. The
        stack numbers (``thread_start_mm``, ``thread_depth_mm``, ``min_engagement_mm``) may also be functions."""
        name = name or f"{key}:{clamps}-{into}"
        if not key:
            raise RegistryError("fastener needs a catalogue key")
        if via:
            _check_id(via, "fastener via")
        decl = FastenerDecl(name=name, key=key, clamps=clamps, into=into, at=at, via=via, tool=tool,
                            length_mm=length_mm, diameter_mm=diameter_mm, thread_start_mm=thread_start_mm,
                            thread_depth_mm=thread_depth_mm, min_engagement_mm=min_engagement_mm, shape=shape,
                            where=_caller_where())
        self._add("fasteners", name, decl, f"fastener {name!r} (pass name= to tell two groups apart)")
        return decl

    # -- the migration path
    def add_build_items(self, parts: Mapping[str, Any], items: Optional[Mapping[str, Any]] = None,
                        where: str = "") -> None:
        """Register ``print_parts()`` shapes and a ``dossier_items()`` mapping (docs/dossier.md). A part already
        registered by a decorator keeps its decorated declaration."""
        items = dict(items or {})
        unknown = set(items) - {"parts", "cavities", "joints", "fasteners", "assembly"}
        if unknown:
            raise RegistryError(f"dossier_items() has unknown keys: {sorted(unknown)}")
        where = where or _caller_where()
        meta = dict(items.get("parts") or {})
        for name in meta:
            if name not in parts and name not in self.parts:
                raise RegistryError(f"dossier_items() parts names {name!r}, which print_parts() does not return")
        for name, shape in parts.items():
            if name in self.parts:
                continue
            m = dict(meta.get(name) or {})
            bad = set(m) - {"section", "place", "grounded", "free", "reason"}
            if bad:
                raise RegistryError(f"dossier_items() parts[{name!r}] has unknown keys: {sorted(bad)}")
            self.add_part(name, shape, where=f"{where} (print_parts {name})", **m)
        for name, c in dict(items.get("cavities") or {}).items():
            c = dict(c)
            self.add_cavity(c.pop("part"), name, c.pop("shape"), where=f"{where} (cavity {name})")
            if c:
                raise RegistryError(f"dossier_items() cavities[{name!r}] has unknown keys: {sorted(c)}")
        for j in items.get("joints") or []:
            j = dict(j)
            decl = self._joint_decl(j.pop("interface"), j.pop("kind", "revolute"), j.pop("parts"), j.pop("axis"),
                                    j.pop("range_deg", None), j.pop("range_mm", None),
                                    j.pop("intended_contacts", ()), j.pop("samples", None),
                                    f"{where} (joint {j.get('interface', '')})")
            if j:
                raise RegistryError(f"dossier_items() joint {decl.interface!r} has unknown keys: {sorted(j)}")
            self._add("joints", decl.interface, decl, f"joint {decl.interface!r}")
        for f in items.get("fasteners") or []:
            f = dict(f)
            decl = self.fastener(f.pop("key"), **f)
            decl.where = f"{where} (fastener {decl.name})"
        for s in items.get("assembly") or []:
            s = dict(s)
            decl = self.assembly.step(s.pop("order"), s.pop("fit"), s.pop("onto", None), **s)
            decl.where = f"{where} (step {decl.order})"

    # -- building
    def build(self, params: Union[Mapping[str, Any], str, Path, None] = None, *, out_dir: Union[str, Path] = "exports",
              root: Union[str, Path, None] = None, write: bool = True) -> "BuildResult":
        """Run every declaration with the parameters and return the shapes and the geometry record. With
        ``write`` (default) also writes ``<out_dir>/dossier-geometry.json`` and the BREP of every shape.

        ``params``: a mapping, a path to a JSON file, or None for ``<root>/cad/parameters.json`` when it exists
        (else ``{}``). ``root`` defaults to the current directory; paths in the record are relative to it.
        """
        root = Path(root or Path.cwd()).resolve()
        p, param_record = _params(params, root)
        result = BuildResult(root=root, out_dir=(root / out_dir).resolve())
        geo: Dict[str, Any] = {"schema": SCHEMA, "units": "mm", "hash": "sha256 of OCCT BREP text v1, no triangulation",
                               "parameters": param_record, "shapes_dir": "", "parts": {}, "cavities": {},
                               "joints": {}, "fasteners": {}, "assembly": {"steps": []},
                               "physical_fit_verified": False}
        placements: Dict[str, List[Any]] = {}
        for name, decl in self.parts.items():
            try:
                made = _call(decl.make, p)
                shapes = _instances(made, f"part {name!r}")
                places = _placements(_call(decl.place, p) if decl.place is not None else None)
                if places and len(shapes) > 1 and len(places) > 1:
                    raise RegistryError("both the function and place return several instances; use one")
                if places:
                    if len(shapes) == 1:
                        shapes = [shapes[0].moved(loc) for loc in places]
                    else:
                        shapes = [s.moved(places[0]) for s in shapes]
            except RegistryError as exc:
                raise RegistryError(f"part {name!r} ({decl.where}): {exc}") from None
            except Exception as exc:
                raise RegistryError(f"part {name!r} ({decl.where}) failed: {type(exc).__name__}: {exc}") from exc
            placements[name] = places
            result.parts[name] = shapes
            infos = [result._record(s, f"{name}#{i}" if len(shapes) > 1 else name) for i, s in enumerate(shapes)]
            geo["parts"][name] = {
                "section": decl.section, "grounded": decl.grounded, "free": decl.free,
                **({"free_reason": decl.reason} if decl.free else {}),
                "sha256": _combine(i["sha256"] for i in infos), "count": len(infos), "instances": infos,
                "declared_at": _rel(decl.where, root)}
        for name, decl in self.cavities.items():
            try:
                shapes = _instances(_call(decl.make, p), f"cavity {name!r}")
                if len(shapes) != 1:
                    raise RegistryError("a cavity is one shape (fuse the voids)")
                shape = shapes[0]
                places = placements.get(decl.part) or []
                if len(places) > 1:
                    raise RegistryError(f"part {decl.part!r} has {len(places)} placed instances; declare the "
                                        "cavity in assembly coordinates on a single-instance part")
                if places:
                    shape = shape.moved(places[0])
            except RegistryError as exc:
                raise RegistryError(f"cavity {name!r} ({decl.where}): {exc}") from None
            except Exception as exc:
                raise RegistryError(f"cavity {name!r} ({decl.where}) failed: {type(exc).__name__}: {exc}") from exc
            result.cavities[name] = shape
            info = result._record(shape, name)
            info.pop("key")
            geo["cavities"][name] = {"part": decl.part, **info, "declared_at": _rel(decl.where, root)}
        for iid, j in self.joints.items():
            try:
                axis = Axis.of(_call(j.axis, p) if callable(j.axis) else j.axis)
            except RegistryError as exc:
                raise RegistryError(f"joint {iid!r} ({j.where}): {exc}") from None
            record = {"kind": j.kind, "moving": j.moving, "fixed": j.fixed, "axis": axis.to_dict(),
                      "range": list(j.range) if j.range else None, "unit": j.unit,
                      "intended_contacts": [list(c) for c in j.intended_contacts], "samples": j.samples,
                      "declared_at": _rel(j.where, root)}
            if j.range2:
                record["range_mm"] = list(j.range2)
            result.joints[iid] = {**record, "axis": axis}
            geo["joints"][iid] = record
        for fname, f in self.fasteners.items():
            try:
                axes = _axes(_call(f.at, p) if callable(f.at) else f.at)
                stack = {k: _num_or_call(getattr(f, k), p, k) for k in
                         ("length_mm", "diameter_mm", "thread_start_mm", "thread_depth_mm", "min_engagement_mm")}
                screw = _instances(_call(f.shape, p), "fastener shape") if f.shape is not None else None
                if screw is not None and len(screw) != 1:
                    raise RegistryError("a fastener shape is one screw, placed at every axis")
            except RegistryError as exc:
                raise RegistryError(f"fastener {fname!r} ({f.where}): {exc}") from None
            instances = []
            placed = []
            for i, a in enumerate(axes):
                inst: Dict[str, Any] = {"key": f"{fname}#{i}" if len(axes) > 1 else fname, **a.to_dict()}
                if screw is not None:
                    s = screw[0].moved(_seat_location(a))
                    placed.append(s)
                    info = result._record(s, inst["key"])
                    info.pop("key")
                    inst.update(info)
                instances.append(inst)
            if placed:
                result.fasteners[fname] = placed
            result.fastener_axes[fname] = axes
            geo["fasteners"][fname] = {"key": f.key, "clamps": f.clamps, "into": f.into, "via": f.via,
                                       "tool": f.tool, **{k: v for k, v in stack.items() if v is not None},
                                       "count": len(instances), "instances": instances,
                                       "declared_at": _rel(f.where, root)}
        steps = [self.steps[k] for k in sorted(self.steps)]
        geo["assembly"]["steps"] = [dict(s.to_dict(), declared_at=_rel(s.where, root)) for s in steps]
        result.steps = steps
        result.geometry = geo
        if write:
            result.write()
        return result


# --------------------------------------------------------------------------------------------- build helpers

def _params(params: Any, root: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if params is None:
        default = root / "cad" / "parameters.json"
        if not default.is_file():
            return {}, {"file": None, "sha256": _sha_json({})}
        params = default
    if isinstance(params, (str, Path)):
        path = Path(params)
        path = path if path.is_absolute() else root / path
        raw = path.read_bytes()
        return json.loads(raw), {"file": _rel(str(path), root), "sha256": hashlib.sha256(raw).hexdigest()}
    params = dict(params)
    return params, {"file": None, "sha256": _sha_json(params)}


def _sha_json(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _call(fn: Any, p: Mapping[str, Any]) -> Any:
    """Call a declaration with the parameters, or without arguments if it takes none; a value is returned as is."""
    if not callable(fn) or _is_shape_like(fn):
        return fn
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(p)
    required = [q for q in sig.parameters.values()
                if q.default is q.empty and q.kind in (q.POSITIONAL_ONLY, q.POSITIONAL_OR_KEYWORD)]
    takes_any = any(q.kind in (q.POSITIONAL_ONLY, q.POSITIONAL_OR_KEYWORD, q.VAR_POSITIONAL)
                    for q in sig.parameters.values())
    return fn(p) if required or takes_any else fn()


def _is_shape_like(obj: Any) -> bool:
    return hasattr(obj, "wrapped") or type(obj).__name__ in ("Workplane", "Assembly", "TopoDS_Shape")


def _num_or_call(value: Any, p: Mapping[str, Any], what: str) -> Optional[float]:
    value = _call(value, p) if callable(value) else value
    if value is None:
        return None
    try:
        return _r(float(value))
    except (TypeError, ValueError):
        raise RegistryError(f"{what} must be a number, got {value!r}") from None


def _to_shape(obj: Any, what: str) -> Any:
    import cadquery as cq
    if isinstance(obj, cq.Shape):
        return obj
    if isinstance(obj, cq.Workplane):
        vals = [v for v in obj.vals() if isinstance(v, cq.Shape)]
        if not vals:
            raise RegistryError(f"{what} returned a Workplane with no shapes")
        return vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)
    if isinstance(obj, cq.Assembly):
        return obj.toCompound()
    wrapped = getattr(obj, "wrapped", None)          # build123d and other OCP wrappers
    if wrapped is not None:
        return cq.Shape.cast(wrapped)
    if type(obj).__name__.startswith("TopoDS_"):
        return cq.Shape.cast(obj)
    raise RegistryError(f"{what} returned {type(obj).__name__}, not a shape")


def _instances(made: Any, what: str) -> List[Any]:
    if made is None:
        raise RegistryError(f"{what} returned None")
    if isinstance(made, (list, tuple)):
        if not made:
            raise RegistryError(f"{what} returned an empty list")
        return [_to_shape(m, what) for m in made]
    return [_to_shape(made, what)]


def _placements(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)) and value and not all(isinstance(v, (int, float)) for v in value):
        return [_location(v) for v in value]
    return [_location(value)]


def _location(value: Any) -> Any:
    import cadquery as cq
    if isinstance(value, cq.Location):
        return value
    if type(value).__name__ == "TopLoc_Location":
        return cq.Location(value)
    if hasattr(value, "wrapped") and type(value.wrapped).__name__ == "TopLoc_Location":   # build123d Location
        return cq.Location(value.wrapped)
    return cq.Location(cq.Vector(*_vec3(value, "placement")))


def _axes(value: Any) -> List[Axis]:
    if value is None:
        raise RegistryError("needs at least one axis in `at`")
    if isinstance(value, Axis) or hasattr(value, "position"):
        return [Axis.of(value)]
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and not isinstance(value[0], Axis) and _is_vec(value[0]) and _is_vec(value[1]):
            return [Axis.of(value)]                  # a single (origin, direction) pair
        axes = [Axis.of(v) for v in value]
        if not axes:
            raise RegistryError("needs at least one axis in `at`")
        return axes
    raise RegistryError(f"`at` must be an Axis or a list of them, got {value!r}")


def _is_vec(v: Any) -> bool:
    return isinstance(v, (list, tuple)) and len(v) == 3 and all(isinstance(c, (int, float)) for c in v)


def _seat_location(axis: Axis) -> Any:
    """The location that puts a screw modelled in the McMaster frame (+Z out of the hole) on ``axis``."""
    import cadquery as cq
    z = tuple(-c for c in axis.direction)
    helper = (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0)
    dot = sum(a * b for a, b in zip(helper, z))
    x = tuple(h - dot * c for h, c in zip(helper, z))
    return cq.Location(cq.Plane(origin=axis.origin, xDir=x, normal=z))


def shape_brep(shape: Any) -> bytes:
    """The BREP text a shape is hashed and stored as: OCCT format version 1, without triangulation or normals
    (so meshing a shape for an STL does not change it). Building the same shape gives the same bytes in any process;
    queries (volume, bounding box, ``isValid``, ``fix``) do not change them.

    A shape *read back* from this text is not guaranteed to write the same bytes again: the reader recomputes frame
    directions and location matrices (last-digit noise, signed zeros) and marks shapes checked, and no rounding
    removes that for every value. So compare recorded hashes and check a file against its hash; never re-hash a
    loaded shape to identify it.
    """
    from io import BytesIO
    from OCP.BRepTools import BRepTools
    from OCP.TopTools import TopTools_FormatVersion
    buf = BytesIO()
    BRepTools.Write_s(getattr(shape, "wrapped", shape), buf, False, False,
                      TopTools_FormatVersion.TopTools_FormatVersion_VERSION_1)
    return buf.getvalue()


def shape_sha256(shape: Any) -> str:
    """Content hash of a shape (``shape_brep``): stable across processes and runs, changes when geometry or placement
    does. Not for shapes read back from a BREP file (see ``shape_brep``)."""
    return hashlib.sha256(shape_brep(shape)).hexdigest()


def _combine(hashes: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(hashes).encode()).hexdigest()


def _rel(where: str, root: Path) -> str:
    """``/abs/cad/build.py:12 (note)`` -> ``cad/build.py:12 (note)`` when the file is under ``root``."""
    head, sep, tail = where.partition(" (")
    path, colon, line = head.rpartition(":")
    if not colon or not line.isdigit():
        path, colon, line = head, "", ""
    if os.path.isabs(path):
        rel = os.path.relpath(path, root)
        if not rel.startswith(".."):
            path = rel
    return path + (f":{line}" if colon else "") + (f" ({tail}" if sep else "")


def _parse_where(at: str) -> Optional[Where]:
    head = at.partition(" (")[0]
    path, _, line = head.rpartition(":")
    if line.isdigit() and path:
        return Where(path, int(line))
    return Where(at) if at else None


@dataclass
class BuildResult:
    """The shapes a build made and the geometry record. ``assembly_shapes()`` is the hand-over to the gates."""
    root: Path
    out_dir: Path
    parts: Dict[str, List[Any]] = field(default_factory=dict)
    cavities: Dict[str, Any] = field(default_factory=dict)
    joints: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    fasteners: Dict[str, List[Any]] = field(default_factory=dict)     # placed screw solids (when a shape was given)
    fastener_axes: Dict[str, List[Axis]] = field(default_factory=dict)
    steps: List[StepDecl] = field(default_factory=list)
    geometry: Dict[str, Any] = field(default_factory=dict)
    path: Optional[Path] = None
    _breps: Dict[str, bytes] = field(default_factory=dict, repr=False)

    def _record(self, shape: Any, key: str) -> Dict[str, Any]:
        brep = shape_brep(shape)
        sha = hashlib.sha256(brep).hexdigest()
        self._breps[sha] = brep
        bb = shape.BoundingBox()
        solids = len(shape.Solids())
        return {"key": key, "sha256": sha, "file": f"{SHAPES_DIR}/{sha}.brep",
                "bbox": {"min": [_r(bb.xmin), _r(bb.ymin), _r(bb.zmin)], "max": [_r(bb.xmax), _r(bb.ymax), _r(bb.zmax)]},
                "volume_mm3": _r(shape.Volume()) if solids else 0.0, "solids": solids, "valid": bool(shape.isValid())}

    def write(self) -> Path:
        """Write ``dossier-geometry.json`` and the BREP files (content-addressed; stale ones are removed)."""
        shapes_dir = self.out_dir / SHAPES_DIR
        shapes_dir.mkdir(parents=True, exist_ok=True)
        (shapes_dir / ".gitignore").write_text("# build output of cadagent.dossier: regenerated by every build\n*\n")
        keep = set()
        for sha, brep in self._breps.items():
            target = shapes_dir / f"{sha}.brep"
            keep.add(target.name)
            if not target.is_file():
                tmp = target.with_suffix(".tmp")
                tmp.write_bytes(brep)
                tmp.replace(target)
        for old in shapes_dir.glob("*.brep"):
            if old.name not in keep:
                old.unlink()
        self.geometry["shapes_dir"] = os.path.relpath(shapes_dir, self.root)
        self.path = self.out_dir / GEOMETRY_FILE
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.geometry, indent=1) + "\n")
        tmp.replace(self.path)
        return self.path

    def assembly_shapes(self, fasteners: bool = True) -> Dict[str, Any]:
        """``{key: shape in assembly coordinates}`` for the gates: one key per part instance (``name`` for a
        single instance, ``name#i`` for several), plus every placed fastener (``fastener_name#i``)."""
        out: Dict[str, Any] = {}
        for name, shapes in self.parts.items():
            for i, s in enumerate(shapes):
                out[f"{name}#{i}" if len(shapes) > 1 else name] = s
        if fasteners:
            for name, shapes in self.fasteners.items():
                for i, s in enumerate(shapes):
                    out[f"{name}#{i}" if len(shapes) > 1 else name] = s
        return out

    @staticmethod
    def owner(key: str) -> str:
        """The part (or fastener) name of an ``assembly_shapes()`` key."""
        return key.rsplit("#", 1)[0] if "#" in key and key.rsplit("#", 1)[1].isdigit() else key


def load_geometry(path: Union[str, Path], shapes: bool = True) -> BuildResult:
    """Read ``dossier-geometry.json`` back (in another process, e.g. ``cad-agent gates``), with its shapes from the
    BREP files when ``shapes`` is true. A BREP whose hash no longer matches the record raises ``RegistryError``."""
    path = Path(path).resolve()
    geo = json.loads(path.read_text())
    if geo.get("schema") != SCHEMA:
        raise RegistryError(f"{path}: schema {geo.get('schema')!r}, expected {SCHEMA!r}")
    out_dir = path.parent
    root = out_dir.parent
    result = BuildResult(root=root, out_dir=out_dir, geometry=geo, path=path)
    result.joints = {k: {**v, "axis": Axis(v["axis"]["origin"], v["axis"]["direction"])} for k, v in geo["joints"].items()}
    result.fastener_axes = {k: [Axis(i["origin"], i["direction"]) for i in v["instances"]]
                            for k, v in geo["fasteners"].items()}
    if not shapes:
        return result
    import cadquery as cq

    def read(info: Dict[str, Any]) -> Any:
        f = out_dir / info["file"]
        raw = f.read_bytes()
        if hashlib.sha256(raw).hexdigest() != info["sha256"]:
            raise RegistryError(f"{f} does not match its recorded sha256; rebuild")
        from io import BytesIO
        return cq.Shape.importBrep(BytesIO(raw))

    result.parts = {k: [read(i) for i in v["instances"]] for k, v in geo["parts"].items()}
    result.cavities = {k: read(v) for k, v in geo["cavities"].items()}
    result.fasteners = {k: [read(i) for i in v["instances"]] for k, v in geo["fasteners"].items()
                        if v["instances"] and "file" in v["instances"][0]}
    return result


# ---------------------------------------------------------------------------------------- build-script entry

def build_module(module: Any, params: Any = None, *, registry: Optional["Registry"] = None, out_dir: str = "exports",
                 root: Union[str, Path, None] = None, write: bool = True) -> BuildResult:
    """Build a project's ``cad/build.py``: import it (a path or a module) so its decorators register, add its
    ``print_parts()`` and ``dossier_items()`` when it has them, and run ``Registry.build``."""
    reg = registry if registry is not None else REGISTRY
    if isinstance(module, (str, Path)):
        path = Path(module).resolve()
        spec = importlib.util.spec_from_file_location(f"_cadagent_build_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise RegistryError(f"cannot import {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(path.parent))
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(str(path.parent))
        module = mod
    items_fn = getattr(module, "dossier_items", None)
    parts_fn = getattr(module, "print_parts", None)
    if items_fn is not None and parts_fn is None:
        raise RegistryError("dossier_items() needs print_parts() beside it (the shapes it describes)")
    if parts_fn is not None:
        where = getattr(module, "__file__", "") or ""
        reg.add_build_items(parts_fn(), items_fn() if items_fn else None, where=f"{where}:0" if where else "")
    return reg.build(params, out_dir=out_dir, root=root, write=write)


# -------------------------------------------------------------------------------------- joining cards and code

def join(dossier: Any, geometry: Union[Mapping[str, Any], BuildResult]) -> List[Issue]:
    """Findings from joining the YAML cards (``Dossier``) with what the build registered (a ``BuildResult`` or the
    ``dossier-geometry.json`` mapping): a card without a shape, a shape without a card, cavities, joints, fasteners
    and steps that do not match their declarations. The dossier lint (plan T2) includes these."""
    geo = geometry.geometry if isinstance(geometry, BuildResult) else geometry
    parts, cavities, joints = geo.get("parts", {}), geo.get("cavities", {}), geo.get("joints", {})
    fasteners, steps = geo.get("fasteners", {}), geo.get("assembly", {}).get("steps", [])
    out: List[Issue] = []

    def code_where(info: Mapping[str, Any]) -> Optional[Where]:
        return _parse_where(str(info.get("declared_at", "")))

    def add(code: str, message: str, where: Optional[Where], severity: str = "error") -> None:
        out.append(Issue(code, message, where, severity))

    known = set(parts) | set(dossier.parts)
    for pid, card in dossier.parts.items():
        if pid not in parts:
            add("card-without-shape", f"part card {pid!r} has no registered shape (@part or print_parts)", card.where)
    for name, info in parts.items():
        card = dossier.parts.get(name)
        if card is None:
            add("shape-without-card", f"registered part {name!r} has no card in the dossier", code_where(info))
        elif info.get("section") and info["section"] != card.section:
            add("section-mismatch", f"part {name!r} is registered in section {info['section']!r} but its card is in "
                                    f"{card.section!r}", code_where(info))
    for name, info in cavities.items():
        if info.get("part") not in known:
            add("unknown-part", f"cavity {name!r} belongs to {info.get('part')!r}, which is not a part",
                code_where(info))
    for pid, card in dossier.parts.items():
        for c in card.contains:
            if c.cavity:
                cav = cavities.get(c.cavity)
                if cav is None:
                    add("unknown-cavity", f"part {pid!r} contains {c.what!r} in cavity {c.cavity!r}, which no "
                                          "@cavity registers", c.where or card.where)
                elif cav.get("part") != pid:
                    add("cavity-wrong-part", f"cavity {c.cavity!r} is registered on {cav.get('part')!r}, not {pid!r}",
                        c.where or card.where)
            else:
                add("unknown-cavity", f"part {pid!r} contains {c.what!r} without naming a cavity",
                    c.where or card.where)
            if c.count is not None and c.what in parts and parts[c.what].get("count") != c.count:
                add("contains-count", f"part {pid!r} declares {c.count} x {c.what!r}; the build made "
                                      f"{parts[c.what].get('count')}", c.where or card.where)
    for iid, j in joints.items():
        w = code_where(j)
        for role in ("moving", "fixed"):
            if j.get(role) not in known:
                add("unknown-part", f"joint {iid!r} {role} part {j.get(role)!r} is not a part", w)
        iface = dossier.interfaces.get(iid)
        if iface is None:
            add("joint-without-interface", f"joint {iid!r} realises no interface of that id in the dossier", w)
            continue
        if sorted(iface.between) != sorted([j.get("moving"), j.get("fixed")]):
            add("joint-parts-mismatch", f"joint {iid!r} joins {j.get('moving')!r} and {j.get('fixed')!r}; the "
                                        f"interface is between {iface.between}", w)
        kind = j.get("kind")
        if (kind == "fixed" and iface.kind not in RIGID_KINDS + ("",)) or (
                kind != "fixed" and iface.kind and iface.kind != kind):
            add("joint-kind-mismatch", f"joint {iid!r} is {kind}; interface {iid!r} is {iface.kind}", w)
    for iid, iface in dossier.interfaces.items():
        if iface.kind in MECHANISM_KINDS and iid not in joints:
            add("interface-without-joint", f"interface {iid!r} is a {iface.kind} joint but no @joint declares it",
                iface.where)
    registered = {}
    for fname, f in fasteners.items():
        w = code_where(f)
        for role in ("clamps", "into"):
            if f.get(role) not in known:
                add("unknown-part", f"fastener {fname!r} {role} {f.get(role)!r}, which is not a part", w)
        if f.get("via") and f["via"] not in dossier.interfaces:
            add("unknown-interface", f"fastener {fname!r} is via {f['via']!r}, which is not an interface", w)
        registered.setdefault((f.get("key"), frozenset((f.get("clamps"), f.get("into")))), []).append(f)
    for pid, card in dossier.parts.items():
        for use in card.fasteners:
            group = registered.get((use.screws, frozenset((pid, use.to))), [])
            if not group:
                add("fastener-not-registered", f"part {pid!r} card lists {use.qty or ''} {use.screws} to {use.to!r}; "
                                               "no fastener() declares them", card.where, "warning")
            elif use.qty is not None and sum(f.get("count", 0) for f in group) != use.qty:
                add("fastener-count", f"part {pid!r} card lists {use.qty} x {use.screws} to {use.to!r}; fastener() "
                                      f"places {sum(f.get('count', 0) for f in group)}", card.where)
    keys = {f.get("key") for f in fasteners.values()} | set(fasteners)
    by_order = {s.order: s for s in dossier.assembly}
    for s in steps:
        w = code_where(s)
        for pid in [s.get("fit")] + list(s.get("onto", [])):
            if pid and pid not in known:
                add("unknown-part", f"assembly step {s.get('order')} names {pid!r}, which is not a part", w)
        for key in dict.fromkeys(s.get("fasteners", [])):
            if key not in keys:
                add("step-fastener-unregistered", f"assembly step {s.get('order')} installs {key!r}; no fastener() "
                                                  "declares it", w, "warning")
        y = by_order.get(s.get("order"))
        if y is not None:
            diffs = [k for k in ("fit", "onto", "direction", "tool")
                     if getattr(y, k) and s.get(k) and _norm(getattr(y, k)) != _norm(s.get(k))]
            if diffs:
                add("step-conflict", f"assembly step {y.order} differs between the dossier and the build: "
                                     f"{', '.join(diffs)}", y.where)
    return out


def _norm(v: Any) -> Any:
    return [float(x) for x in v] if isinstance(v, (list, tuple)) and v and isinstance(v[0], (int, float)) else (
        list(v) if isinstance(v, (list, tuple)) else v)


# ------------------------------------------------------------------------------------- the default registry

REGISTRY = Registry()
part = REGISTRY.part
cavity = REGISTRY.cavity
joint = REGISTRY.joint
fastener = REGISTRY.fastener
assembly = REGISTRY.assembly
build = REGISTRY.build
