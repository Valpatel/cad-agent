"""Connectivity and floating-parts gate (plan ``docs/design-process-plan.md`` §4.2, task T4).

It answers: does every part hang on something, and is every declared connection really there?

* **The contact graph.** Nodes are the parts of an ``Assembly`` (instances and placed fasteners
  included). Edges come from the relation table (``touching``, ``overlapping`` or ``contains``
  between two parts), from declared containment (an instance of a ``contains`` declaration that
  lies inside its container's registered cavity is held by the container, touching or not), from
  fasteners that have no modelled solid (the declaration joins what it clamps to what it threads
  into, unmeasured), and from joints.
* **Rigid groups.** A body that holds the ``moving`` part of a non-fixed joint moves as one; every
  other part belongs to the static frame. An edge is *rigid* when both ends are in the same group
  and it is not a non-fixed joint. A contact across groups (an arm resting on its stop, a shaft in
  its bearing) is recorded but holds nothing up: a part of the static frame that touches only a
  moving body would be left hanging when the body moves.
* **Ground.** The static frame's anchors are the grounded parts; a moving body's anchor is its
  joint's ``moving`` part. Every part must reach its group's anchor through rigid edges. A moving
  body is grounded when its joint's ``fixed`` part reaches ground (chains of joints are followed).
* **Floating islands** (rigid components without an anchor) fail, with a witness: the nearest
  part outside the island, the exact gap and the closest points. An island made only of
  allowed-free parts (``free`` with a reason, or ``contains`` with ``free: true``) is an exclusion.
* **Declared against actual, both ways.** A declared interface must be realised: a mechanism kind
  by a registered joint of that id, a rigid kind by a contact between its parties or a gap within
  its declared ``clearance``. A fastener's solid must touch what it clamps and what it threads
  into. A contact that no interface, joint, fastener, ``contains`` or intended overlap declares is
  an *undeclared contact*: a warning, or a failure with ``strict_interfaces``.

Output: a verdict (``write_verdict``) whose extra keys hold the graph (nodes, edges, components,
groups), the floating islands, the undeclared contacts and the unrealised declarations, plus a
Graphviz DOT file (``write_dot``) for the review site.

Limits. The graph is built from the model's geometry with the relation table's absolute
tolerances: a contact in the model does not prove that printed parts meet, stay put or carry load,
and a joint is trusted as a connection whatever its clearance (the gap is reported). Body labels
are provisional (``Assembly.from_build``: a joint's moving part, the fasteners that clamp or thread
into it and its fixed-joint partners). The kernel is imported only by ``connectivity_gate``;
``analyse`` is pure Python and runs on relations given to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from cadagent.gates.relations import CONTACT_STATES, Relation, Tolerances
from cadagent.gates.verdict import Check, verdict, write_verdict

GATE = "connectivity"
STATIC = "static"
MECHANISM_KINDS = ("revolute", "slider", "cylindrical", "planar", "ball")
NON_GEOMETRIC_KINDS = ("electrical", "thermal", "fluid", "other")
NEAREST_CANDIDATES = 3          # exact queries spent on the nearest neighbour of an island with no measured pair

ASSUMPTIONS = [
    "contact is the relation table's: no shared volume and a gap within touch_mm, or shared volume; a contact in "
    "the model does not prove that printed parts meet, stay put or carry load",
    "a body that holds the moving part of a non-fixed joint moves as one; every other part belongs to the static "
    "frame and must reach a grounded part through contacts, fasteners and fixed joints inside its own group; "
    "contact across groups holds nothing up",
    "a joint connects its moving and fixed parts whatever their gap (a clearance fit is a connection); the gap is "
    "reported and limited only by a declared interface clearance",
    "an item inside its container's declared cavity (contains) is held by the container whether or not it touches",
    "a fastener with a modelled solid connects only what that solid touches; a fastener without one joins what it "
    "clamps to what it threads into on its declaration alone, unmeasured",
    "body labels are provisional: a joint's moving part, the fasteners that clamp or thread into it and its "
    "fixed-joint partners (docs/dossier.md, open for the motion gate)",
    "an interface between sections, or between parts with several instances, is realised by any one contact "
    "between their instances",
]


def owner(key: str) -> str:
    """The part name of an instance key (``"ball#3"`` -> ``"ball"``)."""
    head, _, tail = key.rpartition("#")
    return head if head and tail.isdigit() else key


# ----------------------------------------------------------------------------- declarations

@dataclass
class Declarations:
    """What the design declares about connections. Build it by hand, or with ``from_build``.

    * ``grounded``: part names the static frame hangs on;
    * ``free``: ``{part: reason}`` parts allowed to float (an empty reason is a finding);
    * ``interfaces``: ``[{id, between: [a, b], kind, clearance}]`` (``parts`` is accepted for
      ``between``; dossier ``Interface`` objects too); parties are part names or section ids;
    * ``joints``: ``{id: {kind, moving, fixed, intended_contacts}}``; None takes ``assembly.joints``;
    * ``fasteners``: ``{name: {clamps, into}}``, the placed fastener's name as the build keys it;
    * ``contains``: ``[{what, cavity, container, free}]``;
    * ``intended_overlaps`` and ``ignore_pairs``: ``[{parts: [a, b], reason}]``;
    * ``strict_interfaces``: an undeclared contact fails instead of warning;
    * ``touch_mm``: the dossier's ``gates.touch_tol_mm`` (None keeps the tolerance given).
    """
    grounded: List[str] = field(default_factory=list)
    free: Dict[str, str] = field(default_factory=dict)
    interfaces: List[Dict[str, Any]] = field(default_factory=list)
    joints: Optional[Dict[str, Dict[str, Any]]] = None
    fasteners: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    contains: List[Dict[str, Any]] = field(default_factory=list)
    intended_overlaps: List[Dict[str, Any]] = field(default_factory=list)
    ignore_pairs: List[Dict[str, Any]] = field(default_factory=list)
    strict_interfaces: bool = False
    touch_mm: Optional[float] = None

    def __post_init__(self):
        self.interfaces = [_interface(i) for i in self.interfaces]
        self.intended_overlaps = [_pair_decl(p) for p in self.intended_overlaps]
        self.ignore_pairs = [_pair_decl(p) for p in self.ignore_pairs]
        self.contains = [dict(c) for c in self.contains]
        if not isinstance(self.free, Mapping):
            self.free = _free_map(self.free)

    @classmethod
    def from_build(cls, result: Any, dossier: Any = None, extra: Optional[Mapping[str, Any]] = None,
                   **overrides: Any) -> "Declarations":
        """Collect the declarations of a dossier build (``BuildResult``, live or from ``load_geometry``),
        the loaded YAML ``Dossier`` (``gates:``, interfaces, cards' ``contains``) and ``extra``, a plain
        mapping with the same keys as the YAML (``grounded``, ``free_parts``, ``interfaces``,
        ``contains``, ``intended_overlaps``, ``ignore_pairs``, ``strict_interfaces``). Lists are joined;
        keyword ``overrides`` replace a field."""
        geo = getattr(result, "geometry", None) or {}
        grounded: List[str] = []
        free: Dict[str, str] = {}
        for name, info in sorted((geo.get("parts") or {}).items()):
            if info.get("grounded"):
                grounded.append(name)
            if info.get("free"):
                free[name] = str(info.get("free_reason") or "")
        interfaces: List[Any] = []
        contains: List[Dict[str, Any]] = []
        overlaps: List[Any] = []
        ignore: List[Any] = []
        strict, touch = False, None
        if dossier is not None:
            g = dossier.gates
            grounded += list(g.grounded)
            for fp in g.free_parts:
                free.setdefault(fp.part, fp.reason)
            overlaps += [{"parts": list(p.parts), "reason": p.reason} for p in g.intended_overlaps]
            ignore += [{"parts": list(p.parts), "reason": p.reason} for p in g.ignore_pairs]
            strict, touch = bool(g.strict_interfaces), g.touch_tol_mm
            interfaces += list(dossier.interfaces.values())
            for card in dossier.parts.values():
                for c in card.contains:
                    contains.append({"what": c.what, "cavity": c.cavity, "container": card.id, "free": c.free,
                                     "count": c.count})
        extra = dict(extra or {})
        grounded += list(extra.get("grounded", []))
        for name, reason in _free_map(extra.get("free_parts", [])).items():
            free.setdefault(name, reason)
        interfaces += list(extra.get("interfaces", []))
        contains += [dict(c) for c in extra.get("contains", [])]
        overlaps += list(extra.get("intended_overlaps", []))
        ignore += list(extra.get("ignore_pairs", []))
        strict = bool(extra.get("strict_interfaces", strict))
        for c in contains:
            if c.get("free") and c.get("what"):
                free.setdefault(c["what"], f"loose in {c.get('container') or 'its container'}'s cavity "
                                           f"{c.get('cavity')} (contains, free: true)")
        joints = {k: dict(v) for k, v in (getattr(result, "joints", None) or {}).items()}
        fasteners = {n: {"clamps": f.get("clamps"), "into": f.get("into")}
                     for n, f in (geo.get("fasteners") or {}).items()}
        fields = dict(grounded=_unique(grounded), free=free, interfaces=interfaces, joints=joints,
                      fasteners=fasteners, contains=contains, intended_overlaps=overlaps, ignore_pairs=ignore,
                      strict_interfaces=strict, touch_mm=touch)
        fields.update(overrides)
        return cls(**fields)


def _unique(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


def _free_map(items: Any) -> Dict[str, str]:
    if isinstance(items, Mapping):
        return {str(k): str(v or "") for k, v in items.items()}
    out: Dict[str, str] = {}
    for it in items or ():
        if isinstance(it, str):
            out[it] = ""
        elif isinstance(it, Mapping):
            out[str(it.get("part"))] = str(it.get("reason") or "")
        else:
            out[str(getattr(it, "part"))] = str(getattr(it, "reason", "") or "")
    return out


def _interface(i: Any) -> Dict[str, Any]:
    get = i.get if isinstance(i, Mapping) else (lambda k, d=None: getattr(i, k, d))
    between = list(get("between", None) or get("parts", None) or [])
    if len(between) != 2:
        raise ValueError(f"interface {get('id')!r}: needs exactly two parties, got {between!r}")
    clearance = get("clearance", None)
    return {"id": str(get("id")), "between": [str(b) for b in between], "kind": str(get("kind", "") or ""),
            "clearance": None if clearance is None else float(clearance)}


def _pair_decl(p: Any) -> Dict[str, Any]:
    if isinstance(p, Mapping):
        return {"parts": [str(x) for x in p["parts"]], "reason": str(p.get("reason") or "")}
    if hasattr(p, "parts"):
        return {"parts": [str(x) for x in p.parts], "reason": str(getattr(p, "reason", "") or "")}
    return {"parts": [str(x) for x in p], "reason": ""}


# ----------------------------------------------------------------------------- the analysis (pure)

@dataclass
class Node:
    """One graph node: an assembly key with its owner part, kind, body and section."""
    key: str
    owner: str = ""
    kind: str = "part"
    body: str = ""
    section: Optional[str] = None

    def __post_init__(self):
        self.owner = self.owner or owner(self.key)
        self.body = self.body or self.key


@dataclass
class Analysis:
    checks: List[Check]
    exclusions: List[Dict[str, Any]]
    extra: Dict[str, Any]


Measure = Callable[[str, str], Relation]


def analyse(nodes: Mapping[str, Node], relations: Iterable[Relation], decl: Declarations, *,
            contained: Iterable[Tuple[str, str, str, Relation]] = (), measure: Optional[Measure] = None,
            lower_bounds: Optional[Mapping[Tuple[str, str], float]] = None,
            notes: Iterable[Mapping[str, Any]] = ()) -> Analysis:
    """The connectivity analysis on given relations, without the kernel.

    ``relations``: the exact pair relations (a ``RelationTable`` iterates as them); pairs absent are
    apart beyond the broad phase. ``contained``: ``(item, container, cavity, relation)`` for items
    found inside a declared cavity. ``measure(a, b)``: an exact query for pairs not in
    ``relations`` (witnesses and interface gaps); without it those read as unmeasured.
    ``lower_bounds``: box distances, to pick which pairs to measure. ``notes``: declarations the
    caller could not check, passed through to the verdict."""
    a = _Analyser(nodes, relations, decl, measure, lower_bounds or {})
    return a.run(list(contained), list(notes))


class _Analyser:
    def __init__(self, nodes, relations, decl: Declarations, measure, lower_bounds):
        self.nodes: Dict[str, Node] = dict(nodes)
        self.decl = decl
        self.measure = measure
        self.bounds = lower_bounds
        self.rels: Dict[frozenset, Relation] = {}
        for r in relations:
            if r.a in self.nodes and r.b in self.nodes and r.a != r.b:
                self.rels[frozenset((r.a, r.b))] = r
        self.by_owner: Dict[str, List[str]] = {}
        self.by_section: Dict[str, List[str]] = {}
        for k in sorted(self.nodes):
            n = self.nodes[k]
            self.by_owner.setdefault(n.owner, []).append(k)
            if n.section:
                self.by_section.setdefault(n.section, []).append(k)
        self.joints: Dict[str, Dict[str, Any]] = {str(k): dict(v) for k, v in (decl.joints or {}).items()}
        self.moving_bodies: Dict[str, List[str]] = {}
        for jid in sorted(self.joints):
            j = self.joints[jid]
            if j.get("kind", "revolute") != "fixed":
                for k in self.resolve(j.get("moving")):
                    self.moving_bodies.setdefault(self.nodes[k].body, []).append(jid)
        self.checks: List[Check] = []

    # -- lookups
    def resolve(self, name: Any) -> List[str]:
        """Keys a declared name stands for: the key itself, the instances of a part, or a section's parts."""
        if name is None:
            return []
        name = str(name)
        if name in self.nodes:
            return [name]
        return list(self.by_owner.get(name) or self.by_section.get(name) or [])

    def group(self, key: str) -> str:
        body = self.nodes[key].body
        return body if body in self.moving_bodies else STATIC

    def rel(self, a: str, b: str, measure: bool = True) -> Optional[Relation]:
        """The relation oriented (a, b): stored, else measured (when allowed and possible), else None."""
        r = self.rels.get(frozenset((a, b)))
        if r is None and measure and self.measure is not None:
            r = self.measure(a, b)
            self.rels[frozenset((a, b))] = r
        if r is None:
            return None
        return r if r.a == a else r.flipped()

    def bound(self, a: str, b: str) -> float:
        v = self.bounds.get((a, b), self.bounds.get((b, a)))
        return float("inf") if v is None else float(v)

    def nearest(self, inside: Sequence[str], outside: Sequence[str]) -> Optional[Relation]:
        """The closest measured pair between two sets: stored relations first, else up to
        ``NEAREST_CANDIDATES`` exact queries on the pairs whose boxes are closest."""
        ins = set(inside)
        best = None
        for pair, r in self.rels.items():
            x, y = tuple(pair)
            if (x in ins) == (y in ins) or not ({x, y} & set(outside)) or r.gap_mm is None:
                continue
            r = r if r.a in ins else r.flipped()
            if best is None or (r.gap_mm, r.a, r.b) < (best.gap_mm, best.a, best.b):
                best = r
        if best is not None or self.measure is None:
            return best
        cands = sorted((self.bound(x, y), x, y) for x in inside for y in outside if x != y)
        for _, x, y in cands[:NEAREST_CANDIDATES]:
            r = self.rel(x, y)
            if r is not None and r.gap_mm is not None and (best is None or r.gap_mm < best.gap_mm):
                best = r
        return best

    def check(self, cid: str, status: str, message: str, parts: Iterable[str] = (), **evidence: Any) -> None:
        self.checks.append(Check(cid, status, message, tuple(sorted(set(parts))),
                                 {k: v for k, v in evidence.items() if v is not None}))

    # -- the run
    def run(self, contained, notes) -> Analysis:
        free = self._free()
        anchors = self._ground()
        edges, unknown = self._edges(contained)
        for r in unknown:
            self.check(f"relation:{r.a}|{r.b}", "fail", f"the kernel could not decide {r.a} / {r.b}: {r.error}; "
                       "the contact graph is unreliable there", (r.a, r.b), error=r.error)
        comp = _components(sorted(self.nodes), [(e["a"], e["b"]) for e in edges if e["rigid"]])
        groups = sorted({self.group(k) for k in self.nodes}, key=lambda g: (g != STATIC, g))
        group_anchors: Dict[str, List[str]] = {STATIC: anchors}
        for body, jids in self.moving_bodies.items():
            group_anchors[body] = sorted({k for jid in jids for k in self.resolve(self.joints[jid].get("moving"))})
        anchored = {comp[k] for g, ks in group_anchors.items() for k in ks}
        grounded_groups, via = self._grounded_groups(comp, anchored, bool(anchors))
        islands, exclusions = self._islands(comp, anchored, free, groups, group_anchors, bool(anchors))
        self._joint_checks(comp, anchored, grounded_groups)
        unrealised = self._interface_checks() + self._fastener_checks()
        undeclared = self._undeclared(edges, free)
        graph = self._graph(edges, comp, anchored, free, anchors, groups, group_anchors, grounded_groups, via,
                            islands, unrealised)
        extra = {"graph": graph, "floating": islands, "undeclared_contacts": undeclared,
                 "unrealised": unrealised, "not_checked": list(notes)}
        return Analysis(self.checks, exclusions, extra)

    def _free(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name in sorted(self.decl.free):
            reason = str(self.decl.free[name] or "").strip()
            keys = self.resolve(name)
            if not keys:
                self.check(f"free:{name}", "warn", f"allowed-free part {name!r} names nothing in the assembly "
                           "(a stale declaration?)")
            elif not reason:
                self.check(f"free:{name}", "fail", f"{name!r} is declared free with no reason; it is checked like "
                           "any other part until it has one", keys)
            else:
                for k in keys:
                    out[k] = reason
        return out

    def _ground(self) -> List[str]:
        anchors, missing, moving = [], [], []
        for name in self.decl.grounded:
            keys = self.resolve(name)
            if not keys:
                missing.append(name)
            for k in keys:
                (moving if self.group(k) != STATIC else anchors).append(k)
        anchors = sorted(set(anchors))
        if missing or moving or not anchors:
            why = []
            if not self.decl.grounded:
                why.append("no part is declared grounded, so nothing can be checked for floating")
            if missing:
                why.append(f"grounded {missing} not in the assembly")
            if moving:
                why.append(f"grounded {sorted(moving)} belong to a moving body")
            if self.decl.grounded and not anchors and not missing and not moving:
                why.append("no grounded part resolved")
            self.check("ground", "fail", "; ".join(why), moving, grounded=list(self.decl.grounded), missing=missing)
        else:
            self.check("ground", "pass", f"grounded: {', '.join(anchors)}", anchors)
        return anchors

    def _edges(self, contained):
        edges: List[Dict[str, Any]] = []
        unknown: List[Relation] = []
        for pair in sorted(self.rels, key=sorted):
            r = self.rels[pair]
            a, b = sorted(pair)
            r = r if r.a == a else r.flipped()
            if r.state == "unknown":
                unknown.append(r)
            elif r.state in CONTACT_STATES:
                e = {"a": a, "b": b, "kind": "contact", "state": r.state, "gap_mm": r.gap_mm}
                if r.contact_area_mm2 is not None:
                    e["contact_area_mm2"] = r.contact_area_mm2
                if r.state != "touching":
                    e["overlap_mm3"] = r.overlap_mm3
                e["witness"] = dict(r.witness)
                edges.append(e)
        for item, container, cavity, r in sorted(contained, key=lambda c: (c[0], c[1], c[2])):
            if item in self.nodes and container in self.nodes and item != container:
                edges.append({"a": item, "b": container, "kind": "contained", "cavity": cavity,
                              "wall_mm": r.wall_mm})
        for name in sorted(self.decl.fasteners):
            if self.resolve(name):
                continue                       # a modelled solid: its contacts carry the connection
            f = self.decl.fasteners[name]
            for x in self.resolve(f.get("clamps")):
                for y in self.resolve(f.get("into")):
                    if x != y:
                        edges.append({"a": x, "b": y, "kind": "fastener", "fastener": name, "measured": False})
        for jid in sorted(self.joints):
            j = self.joints[jid]
            for x in self.resolve(j.get("moving")):
                for y in self.resolve(j.get("fixed")):
                    if x != y:
                        edges.append({"a": x, "b": y, "kind": "joint", "joint": jid,
                                      "joint_kind": j.get("kind", "revolute")})
        for e in edges:
            nonfixed = e["kind"] == "joint" and e["joint_kind"] != "fixed"
            e["rigid"] = not nonfixed and self.group(e["a"]) == self.group(e["b"])
        return edges, unknown

    def _grounded_groups(self, comp, anchored, has_ground):
        grounded = {STATIC} if has_ground else set()
        via: Dict[str, str] = {}
        changed = True
        while changed:
            changed = False
            for body in sorted(self.moving_bodies):
                if body in grounded:
                    continue
                for jid in self.moving_bodies[body]:
                    fixed = self.resolve(self.joints[jid].get("fixed"))
                    if any(self.group(f) != body and self.group(f) in grounded and comp[f] in anchored
                           for f in fixed):
                        grounded.add(body)
                        via[body] = jid
                        changed = True
                        break
        return grounded, via

    def _islands(self, comp, anchored, free, groups, group_anchors, has_ground):
        members: Dict[int, List[str]] = {}
        for k in sorted(self.nodes):
            members.setdefault(comp[k], []).append(k)
        islands: List[Dict[str, Any]] = []
        exclusions: List[Dict[str, Any]] = []
        by_group: Dict[str, List[Dict[str, Any]]] = {g: [] for g in groups}
        for cid in sorted(members, key=lambda c: members[c]):
            if cid in anchored:
                continue
            parts = members[cid]
            g = self.group(parts[0])
            if g == STATIC and not has_ground:
                continue                       # the ground check already failed; every part would be listed
            loose = [k for k in parts if k in free]
            stuck = [k for k in parts if k not in free]
            if not stuck:
                exclusions.append({"parts": parts, "reason": "; ".join(sorted({free[k] for k in parts})),
                                   "kind": "allowed free"})
                continue
            outside = [k for k in sorted(self.nodes) if comp[k] != cid]
            near = self.nearest(parts, outside)
            touches = []
            for k in parts:
                for o in outside:
                    r = self.rels.get(frozenset((k, o)))
                    if r is not None and r.in_contact:
                        touches.append({"part": k, "other": o, "other_group": self.group(o), "state": r.state})
            isl = {"group": g, "parts": stuck, "free_members": loose, "touches_across_groups": touches,
                   "nearest": _witness(near, self.group(near.b), comp[near.b] in anchored) if near else None}
            islands.append(isl)
            by_group[g].append(isl)
        for g in groups:
            label = STATIC if g == STATIC else f"body:{g}"
            anchors = group_anchors.get(g, [])
            parts = [k for k in self.nodes if self.group(k) == g]
            found = by_group.get(g, [])
            if g == STATIC and not has_ground:
                continue
            if not found:
                self.check(f"connect:{label}", "pass", f"{len(parts)} part(s) reach {', '.join(anchors)} through "
                           "rigid connections", anchors=anchors, parts=len(parts))
                continue
            text = []
            for isl in found:
                n = isl["nearest"]
                where = (f"nearest {n['neighbour']} at {n['gap_mm']:.3f} mm" if n else "no part measured nearby")
                if isl["touches_across_groups"]:
                    others = sorted({t["other"] for t in isl["touches_across_groups"]})
                    where += f"; touches only {', '.join(others)} in another body"
                text.append(f"[{', '.join(isl['parts'])}] ({where})")
            floating = sorted({k for isl in found for k in isl["parts"]})
            self.check(f"connect:{label}", "fail", f"{len(found)} floating island(s) do not reach "
                       f"{', '.join(anchors) or 'an anchor'}: " + "; ".join(text), floating, anchors=anchors,
                       islands=found)
        return islands, exclusions

    def _joint_checks(self, comp, anchored, grounded_groups):
        clearance = {i["id"]: i["clearance"] for i in self.decl.interfaces if i["clearance"] is not None}
        for jid in sorted(self.joints):
            j = self.joints[jid]
            kind = j.get("kind", "revolute")
            mv, fx = self.resolve(j.get("moving")), self.resolve(j.get("fixed"))
            cid = f"joint:{jid}"
            if not mv or not fx:
                missing = [n for n, ks in ((j.get("moving"), mv), (j.get("fixed"), fx)) if not ks]
                self.check(cid, "fail", f"{kind} joint names {missing}, not in the assembly", mv + fx)
                continue
            m, f = mv[0], fx[0]
            r = self.rel(m, f)
            ev = {"kind": kind, "moving": m, "fixed": f, "relation": _rel_summary(r)}
            if kind == "fixed":
                if self.group(m) != self.group(f):
                    self.check(cid, "fail", f"fixed joint joins {m} ({self.group(m)}) and {f} ({self.group(f)}), "
                               "which are labelled as different bodies; give them one body", (m, f), **ev)
                else:
                    self.check(cid, "pass", f"fixed joint joins {m} and {f} rigidly", (m, f), **ev)
                continue
            g = self.group(m)
            if any(self.group(x) == g for x in fx):
                self.check(cid, "fail", f"{kind} joint: the fixed part {f} is in the moving body {g} itself",
                           (m, f), **ev)
                continue
            if not any(self.group(x) in grounded_groups and comp[x] in anchored for x in fx):
                self.check(cid, "fail", f"{m} (body {g}) hangs on {f} through {kind} joint {jid}, but {f} does "
                           "not reach ground", (m, f), **ev)
                continue
            gap = None if r is None else r.gap_mm
            limit = clearance.get(jid)
            if limit is not None and (gap is None or gap > limit + 1e-9):
                got = "unmeasured" if gap is None else f"{gap:.3f} mm"
                self.check(cid, "fail", f"{m} and {f} of {kind} joint {jid} are {got} apart, over the declared "
                           f"clearance {limit:g} mm", (m, f), clearance_mm=limit, **ev)
                continue
            state = "not measured" if r is None else (f"{r.state}, gap {gap:.3f} mm" if gap is not None
                                                      else r.state)
            self.check(cid, "pass", f"{m} (body {g}) hangs on {f} through {kind} joint {jid} ({state})", (m, f), **ev)

    def _interface_checks(self) -> List[Dict[str, Any]]:
        unrealised: List[Dict[str, Any]] = []
        for i in self.decl.interfaces:
            iid, kind, (pa, pb) = i["id"], i["kind"], i["between"]
            cid = f"interface:{iid}"
            if kind in NON_GEOMETRIC_KINDS:
                continue                       # nothing geometric to check; listed in the graph's declarations
            A, B = self.resolve(pa), self.resolve(pb)
            if not A or not B:
                missing = [n for n, ks in ((pa, A), (pb, B)) if not ks]
                self.check(cid, "fail", f"interface {iid} names {missing}, not in the assembly", A + B)
                unrealised.append({"kind": "interface", "id": iid, "parts": [pa, pb], "reason": "missing party"})
                continue
            if kind in MECHANISM_KINDS:
                if iid in self.joints:
                    self.check(cid, "pass", f"{kind} interface {iid} is realised by its registered joint",
                               A[:1] + B[:1], joint=iid)
                else:
                    self.check(cid, "fail", f"{kind} interface {iid} ({pa} / {pb}) has no registered joint",
                               A[:1] + B[:1])
                    unrealised.append({"kind": "interface", "id": iid, "parts": [pa, pb], "reason": "no joint"})
                continue
            pairs = [(x, y) for x in A for y in B if x != y]
            stored = [self.rel(x, y, measure=False) for x, y in pairs]
            bad = [r for r in stored if r is not None and r.state == "unknown"]
            if bad:
                self.check(cid, "fail", f"interface {iid}: the kernel could not decide {bad[0].a} / {bad[0].b}",
                           (bad[0].a, bad[0].b), error=bad[0].error)
                unrealised.append({"kind": "interface", "id": iid, "parts": [bad[0].a, bad[0].b],
                                   "reason": "unknown relation"})
                continue
            touching = [r for r in stored if r is not None and r.in_contact]
            if touching:
                r = touching[0]
                self.check(cid, "pass", f"interface {iid} is realised: {r.a} / {r.b} {r.state}"
                           + (f" ({len(touching)} of {len(pairs)} instance pairs)" if len(pairs) > 1 else ""),
                           (r.a, r.b), relation=_rel_summary(r))
                continue
            near = self.nearest(A, [y for y in B if y not in A])
            if near is not None and near.in_contact:
                self.check(cid, "pass", f"interface {iid} is realised: {near.a} / {near.b} {near.state}",
                           (near.a, near.b), relation=_rel_summary(near))
                continue
            clearance = i["clearance"]
            gap = None if near is None else near.gap_mm
            if clearance is not None and gap is not None and gap <= clearance + 1e-9:
                self.check(cid, "pass", f"interface {iid}: {near.a} / {near.b} apart by {gap:.3f} mm, within the "
                           f"declared clearance {clearance:g} mm", (near.a, near.b), relation=_rel_summary(near),
                           clearance_mm=clearance)
                continue
            if kind == "gap" and clearance is None:
                why = "a gap interface needs a declared clearance"
            elif gap is None:
                why = "no instance pair was measured (the parts are beyond the broad phase and no kernel was given)"
            else:
                why = f"{near.a} and {near.b} are apart by {gap:.3f} mm" + (
                    f", over the declared clearance {clearance:g} mm" if clearance is not None else
                    "; declare a clearance if the gap is intended")
            parts = (near.a, near.b) if near is not None else tuple(A[:1] + B[:1])
            self.check(cid, "fail", f"declared interface {iid} ({pa} / {pb}) is not realised: {why}", parts,
                       relation=_rel_summary(near), clearance_mm=clearance)
            unrealised.append({"kind": "interface", "id": iid, "parts": list(parts), "gap_mm": gap,
                               "clearance_mm": clearance, "reason": why,
                               "witness": dict(near.witness) if near is not None else None})
        return unrealised

    def _fastener_checks(self) -> List[Dict[str, Any]]:
        unrealised: List[Dict[str, Any]] = []
        for name in sorted(self.decl.fasteners):
            f = self.decl.fasteners[name]
            keys = self.resolve(name)
            clamps, into = self.resolve(f.get("clamps")), self.resolve(f.get("into"))
            cid = f"fastener:{name}"
            if not clamps or not into:
                missing = [n for n, ks in ((f.get("clamps"), clamps), (f.get("into"), into)) if not ks]
                self.check(cid, "fail", f"fastener {name} names {missing}, not in the assembly", keys + clamps + into)
                unrealised.append({"kind": "fastener", "id": name, "parts": keys, "reason": "missing party"})
                continue
            if not keys:
                self.check(cid, "pass", f"fastener {name} has no modelled solid: {f.get('clamps')} / "
                           f"{f.get('into')} joined on its declaration, not measured", clamps + into, measured=False)
                continue
            misses = []
            for k in keys:
                for role, targets in (("clamps", clamps), ("into", into)):
                    if any((r := self.rel(k, t, measure=False)) is not None and r.in_contact for t in targets):
                        continue
                    near = self.nearest([k], targets)
                    misses.append({"instance": k, "role": role, "targets": targets,
                                   "nearest": _witness(near, None, None) if near else None})
            if misses:
                text = "; ".join(f"{m['instance']} does not touch what it {'clamps' if m['role'] == 'clamps' else 'threads into'}"
                                 + (f" (nearest {m['nearest']['neighbour']} at {m['nearest']['gap_mm']:.3f} mm)"
                                    if m["nearest"] else "") for m in misses)
                parts = {m["instance"] for m in misses} | {m["nearest"]["neighbour"] for m in misses if m["nearest"]}
                self.check(cid, "fail", f"fastener {name}: {text}", parts, misses=misses)
                unrealised += [{"kind": "fastener", "id": name, "parts": [m["instance"]] + m["targets"],
                                "role": m["role"], "gap_mm": (m["nearest"] or {}).get("gap_mm")} for m in misses]
            else:
                self.check(cid, "pass", f"fastener {name}: every solid touches {f.get('clamps')} and "
                           f"{f.get('into')}", keys)
        return unrealised

    def _covered(self) -> Dict[frozenset, List[str]]:
        cover: Dict[frozenset, List[str]] = {}

        def add(xs: Iterable[str], ys: Iterable[str], label: str) -> None:
            for x in xs:
                for y in ys:
                    if x != y:
                        cover.setdefault(frozenset((x, y)), []).append(label)

        for i in self.decl.interfaces:
            add(self.resolve(i["between"][0]), self.resolve(i["between"][1]), f"interface:{i['id']}")
        for jid, j in self.joints.items():
            add(self.resolve(j.get("moving")), self.resolve(j.get("fixed")), f"joint:{jid}")
            for pair in j.get("intended_contacts") or ():
                add(self.resolve(pair[0]), self.resolve(pair[1]), f"joint:{jid}:intended")
        for name, f in self.decl.fasteners.items():
            keys, clamps, into = self.resolve(name), self.resolve(f.get("clamps")), self.resolve(f.get("into"))
            add(keys, clamps + into, f"fastener:{name}")
            add(clamps, into, f"fastener:{name}")
        for c in self.decl.contains:
            items = self.resolve(c.get("what"))
            add(items, self.resolve(c.get("container")), f"contains:{c.get('cavity')}")
            add(items, items, f"contains:{c.get('cavity')}")
        for o in self.decl.intended_overlaps:
            add(self.resolve(o["parts"][0]), self.resolve(o["parts"][1]), "intended_overlap")
        return cover

    def _undeclared(self, edges, free) -> List[Dict[str, Any]]:
        cover = self._covered()
        out: List[Dict[str, Any]] = []
        status = "fail" if self.decl.strict_interfaces else "warn"
        for e in edges:
            pair = frozenset((e["a"], e["b"]))
            e["declared_by"] = sorted(set(cover.get(pair, [])))
            if e["kind"] != "contact":
                continue
            if not e["declared_by"] and (e["a"] in free or e["b"] in free):
                e["declared_by"] = ["free part"]
            if e["declared_by"]:
                continue
            e["undeclared"] = True
            row = {"parts": [e["a"], e["b"]], "state": e["state"], "contact_area_mm2": e.get("contact_area_mm2"),
                   "overlap_mm3": e.get("overlap_mm3"), "witness": e.get("witness")}
            out.append(row)
            what = e["state"] + (f", {e['contact_area_mm2']:.3g} mm2" if e.get("contact_area_mm2") else "") + (
                f", {e['overlap_mm3']:.4g} mm3 shared" if e.get("overlap_mm3") else "")
            self.check(f"contact:{e['a']}|{e['b']}", status, f"{e['a']} and {e['b']} are in contact ({what}) but no "
                       "interface, joint, fastener, contains or intended overlap declares it", (e["a"], e["b"]),
                       **{k: v for k, v in row.items() if k != "parts"})
        return out

    def _graph(self, edges, comp, anchored, free, anchors, groups, group_anchors, grounded_groups, via, islands,
               unrealised):
        floating = {k for isl in islands for k in isl["parts"]}
        order = {c: i for i, c in enumerate(sorted(set(comp.values()), key=lambda c: min(
            k for k in self.nodes if comp[k] == c)))}
        nodes = []
        for k in sorted(self.nodes):
            n = self.nodes[k]
            nodes.append({"id": k, "owner": n.owner, "kind": n.kind, "group": self.group(k), "body": n.body,
                          "section": n.section, "grounded": k in anchors, "free": free.get(k),
                          "component": f"c{order[comp[k]]}", "anchored": comp[k] in anchored,
                          "floating": k in floating})
        comps = []
        for c in sorted(order, key=order.get):
            parts = sorted(k for k in self.nodes if comp[k] == c)
            comps.append({"id": f"c{order[c]}", "group": self.group(parts[0]), "parts": parts,
                          "anchored": c in anchored})
        grp = [{"group": g, "anchors": group_anchors.get(g, []), "grounded": g in grounded_groups,
                "via_joint": via.get(g)} for g in groups]
        return {"nodes": nodes, "edges": [{k: v for k, v in e.items() if v is not None} for e in edges],
                "components": comps, "groups": grp,
                "missing": [u for u in unrealised if len(u.get("parts", [])) >= 2]}


def _components(keys: Sequence[str], links: Iterable[Tuple[str, str]]) -> Dict[str, int]:
    parent = {k: i for i, k in enumerate(keys)}
    idx = list(range(len(keys)))

    def find(i: int) -> int:
        while idx[i] != i:
            idx[i] = idx[idx[i]]
            i = idx[i]
        return i

    for a, b in links:
        ra, rb = find(parent[a]), find(parent[b])
        if ra != rb:
            idx[max(ra, rb)] = min(ra, rb)
    return {k: find(parent[k]) for k in keys}


def _rel_summary(r: Optional[Relation]) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    out = {"a": r.a, "b": r.b, "state": r.state, "gap_mm": r.gap_mm, "exact": r.exact}
    if r.gap_lower_bound_mm is not None:
        out["gap_lower_bound_mm"] = r.gap_lower_bound_mm
    if r.witness:
        out["witness"] = dict(r.witness)
    return {k: v for k, v in out.items() if v is not None}


def _witness(r: Relation, group: Optional[str], anchored: Optional[bool]) -> Dict[str, Any]:
    out = {"part": r.a, "neighbour": r.b, "gap_mm": r.gap_mm, "state": r.state,
           "point_a": r.witness.get("point_a"), "point_b": r.witness.get("point_b")}
    if group is not None:
        out["neighbour_group"] = group
    if anchored is not None:
        out["neighbour_anchored"] = anchored
    return {k: v for k, v in out.items() if v is not None}


# ----------------------------------------------------------------------------- the gate (kernel)

def connectivity_gate(assembly: Any, declarations: Optional[Declarations] = None, *, table: Any = None,
                      tol: Optional[Tolerances] = None, cache: Any = None, out: Any = None,
                      dot: Any = None) -> Dict[str, Any]:
    """Run the connectivity gate on an ``Assembly`` and return (with ``out``, write) the verdict.

    ``declarations`` default to none (then the ground check fails: something must be grounded).
    ``table``: a ``RelationTable`` already built for this assembly (else one is built with ``tol``,
    the dossier's ``touch_mm`` and ``ignore_pairs``, through ``cache``). ``dot``: where to write the
    Graphviz graph (default: beside ``out`` with the suffix ``.dot``)."""
    from cadagent.gates.relations import relate_pair, relation_table

    decl = declarations or Declarations()
    if table is not None:
        tol = table.tolerances
    elif tol is None:
        tol = Tolerances(touch_mm=decl.touch_mm) if decl.touch_mm is not None else Tolerances()
    if table is None:
        table = relation_table(assembly, tol, cache=cache, skip_pairs=[p["parts"] for p in decl.ignore_pairs])
    joints = decl.joints if decl.joints is not None else dict(getattr(assembly, "joints", {}) or {})
    decl = replace(decl, joints=joints)
    nodes = {k: Node(k, owner(k), assembly[k].kind, assembly[k].body, assembly[k].group) for k in assembly}
    relations = list(table)
    contained: List[Tuple[str, str, str, Relation]] = []
    notes: List[Dict[str, Any]] = []
    for c in decl.contains:
        cav, what = c.get("cavity"), c.get("what")
        if cav not in assembly.cavities:
            notes.append({"contains": what, "cavity": cav, "reason": "cavity not registered (a dossier lint "
                          "finding); its items are held only by their contacts"})
            continue
        container = assembly.cavities[cav].container
        items = [k for k in assembly if k == what or owner(k) == what]
        for k in items:
            r = relate_pair(assembly, k, cav, tol, cache=cache)
            if r.state == "contains" and r.contained in ("a_in_b", "both"):
                contained.append((k, container, cav, r))
            elif r.state == "unknown":
                notes.append({"contains": k, "cavity": cav, "reason": f"the kernel could not decide: {r.error}"})
    an = analyse(nodes, relations, decl, contained=contained, measure=lambda a, b: table.get(a, b, exact=True),
                 lower_bounds=table.lower_bounds, notes=notes)
    stats = {k: table.stats[k] for k in ("parts", "pairs", "candidates") if k in table.stats}
    stats["states"] = {s: sum(1 for r in table if r.state == s) for s in ("apart", "touching", "overlapping",
                                                                          "contains", "unknown")}
    an.extra["relation_stats"] = stats
    data = verdict(GATE, an.checks, assumptions=ASSUMPTIONS, exclusions=an.exclusions, extra=an.extra,
                   limits={"touch_mm": tol.touch_mm, "near_mm": tol.near_mm, "overlap_mm3": tol.overlap_mm3,
                           "strict_interfaces": decl.strict_interfaces,
                           "nearest_candidates": NEAREST_CANDIDATES})
    if out is not None:
        write_verdict(out, data)
        if dot is None:
            dot = Path(out).with_suffix(".dot")
    if dot is not None:
        write_dot(data, dot)
    return data


def connectivity_from_build(result: Any, dossier: Any = None, extra: Optional[Mapping[str, Any]] = None, *,
                            assembly: Any = None, **kwargs: Any) -> Dict[str, Any]:
    """The gate on a dossier build: ``Assembly.from_build(result)`` (unless ``assembly`` is given) and
    ``Declarations.from_build(result, dossier, extra)``. ``kwargs`` go to ``connectivity_gate``."""
    if assembly is None:
        from cadagent.gates.relations import Assembly
        assembly = Assembly.from_build(result)
    return connectivity_gate(assembly, Declarations.from_build(result, dossier, extra), **kwargs)


# ----------------------------------------------------------------------------- the graph as DOT

def _q(s: Any) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_dot(data: Mapping[str, Any]) -> str:
    """Graphviz DOT of a connectivity verdict (or of its ``graph``): one cluster per rigid group,
    grounded parts double-framed, floating parts red, free parts dashed; contacts solid (grey across
    groups, orange when undeclared), containment dotted, unmeasured fasteners bold, joints blue
    dashed, unrealised declarations red dashed. Deterministic: same verdict, same bytes."""
    g = data.get("graph", data)
    lines = ["graph connectivity {", '  graph [rankdir=LR, fontname="Helvetica", fontsize=10];',
             '  node [shape=box, style=rounded, fontname="Helvetica", fontsize=10];',
             '  edge [fontname="Helvetica", fontsize=8];']
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for n in g.get("nodes", []):
        groups.setdefault(n["group"], []).append(n)
    info = {x["group"]: x for x in g.get("groups", [])}
    for i, name in enumerate(sorted(groups, key=lambda x: (x != STATIC, x))):
        gi = info.get(name, {})
        label = ("static frame" if name == STATIC else f"body {name}") + (
            "" if gi.get("grounded", True) else " (not grounded)")
        lines.append(f"  subgraph cluster_{i} {{")
        lines.append(f"    label={_q(label)}; style=rounded; color=gray60;")
        for n in groups[name]:
            attrs = []
            if n.get("grounded"):
                attrs.append("peripheries=2")
            if n.get("floating"):
                attrs += ["color=red", "fontcolor=red"]
            if n.get("free"):
                attrs.append('style="rounded,dashed"')
            if n.get("kind") == "fastener":
                attrs.append("shape=ellipse")
            lines.append(f"    {_q(n['id'])}" + (f" [{', '.join(attrs)}]" if attrs else "") + ";")
        lines.append("  }")
    for e in g.get("edges", []):
        attrs = []
        if e["kind"] == "contact":
            if e.get("undeclared"):
                attrs += ["color=orange", 'label="undeclared"']
            elif not e.get("rigid"):
                attrs.append("color=gray60")
        elif e["kind"] == "contained":
            attrs += ["style=dotted", f"label={_q('in ' + str(e.get('cavity')))}"]
        elif e["kind"] == "fastener":
            attrs += ["style=bold", f"label={_q(str(e.get('fastener')) + ' (declared)')}"]
        elif e["kind"] == "joint":
            attrs += ["style=dashed", "color=blue", f"label={_q(str(e.get('joint')) + ' ' + str(e.get('joint_kind')))}"]
        lines.append(f"  {_q(e['a'])} -- {_q(e['b'])}" + (f" [{', '.join(attrs)}]" if attrs else "") + ";")
    for m in g.get("missing", []):
        gap = m.get("gap_mm")
        label = f"{m.get('id')} unrealised" + (f" {gap:.3f} mm" if isinstance(gap, (int, float)) else "")
        lines.append(f"  {_q(m['parts'][0])} -- {_q(m['parts'][1])} [style=dashed, color=red, fontcolor=red, "
                     f"label={_q(label)}];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_dot(data: Mapping[str, Any], path: Any) -> Path:
    """Write ``to_dot(data)`` to ``path`` (parent directories created). Render it with Graphviz
    (``dot -Tsvg``) where it is installed; the toolkit does not require it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_dot(data))
    return path


__all__ = ["Declarations", "Node", "Analysis", "analyse", "connectivity_gate", "connectivity_from_build", "to_dot",
           "write_dot", "owner", "ASSUMPTIONS", "GATE", "STATIC"]
