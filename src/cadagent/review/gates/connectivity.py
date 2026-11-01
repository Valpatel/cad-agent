"""Connectivity and floating-parts gate (plan ``docs/design-process-plan.md`` §4.2, task T4).

It answers: does every part hang on something, and is every declared connection really there?

* **The contact graph.** Nodes are the parts of an ``Assembly`` (instances and placed fasteners
  included). Edges come from the relation table (``touching``, ``overlapping`` or ``contains``
  between two parts), from declared containment (an instance of a ``contains`` declaration that
  lies inside its container's registered cavity is held by the container, touching or not), from
  fasteners that have no modelled solid but whose axis is measured to pass through what they clamp
  and what they thread into, and from joints whose parts are measured close enough.
* **Bodies.** A joint's ``moving`` part seeds a moving body; the body grows, transitively, across
  ``fixed`` joints and fastener ``clamps``/``into`` declarations (it never crosses into a grounded
  part, the joint's ``fixed`` part or another body: such a link is a finding). Parts labelled into
  a moving body by the assembly keep that label. Everything else is the static frame. An edge is
  *rigid* when both ends are in one group, neither end is an allowed-free part, and it is not a
  non-fixed joint. A contact across groups (an arm on its stop) or with a loose part is recorded
  but holds nothing up.
* **Ground.** The static frame hangs on the grounded parts; a moving body on the instances of its
  joint's ``moving`` part that the joint holds: within the declared interface ``clearance`` of the
  ``fixed`` part, else within ``max_joint_gap_mm`` (a ``fixed`` joint needs contact or a declared
  clearance). A component is grounded when it holds a grounded part, or a held joint instance whose
  ``fixed`` part is in a grounded component (chains of joints are followed). Every part must be in
  a grounded component.
* **Floating islands** fail with a witness: the nearest part outside the island, the exact gap,
  the closest points, and what the island touches in other bodies or among loose parts. An island
  made only of allowed-free parts is an exclusion.
* **Declared against actual, both ways.** A declared interface must be realised: a mechanism kind
  by a registered joint of that id between the same parts, a rigid kind by a contact between its
  parties or a gap within its declared ``clearance``. A fastener's solid must touch what it clamps
  and what it threads into. A contact that no interface, joint, fastener, ``contains`` or intended
  overlap declares is an *undeclared contact*: a warning, or a failure with ``strict_interfaces``.
  What could not be checked is listed in ``not_checked``.

Output: a verdict (``write_verdict``) whose extra keys hold the graph (nodes, edges, components,
groups), the floating islands, the undeclared contacts and the unrealised declarations, plus a
Graphviz DOT file (``write_dot``) for the review site.

Limits. The graph is built from the model's geometry with the relation table's absolute
tolerances: a contact in the model does not prove that printed parts meet, stay put or carry load.
A joint within its allowed gap is trusted as a connection. The kernel is imported only by
``connectivity_gate``; ``analyse`` is pure Python and runs on relations given to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from cadagent.review.gates.relations import CONTACT_STATES, Relation, Tolerances
from cadagent.review.gates.verdict import Check, verdict, write_verdict

GATE = "connectivity"
STATIC = "static"
BODY = "body:"                  # moving groups are "body:<name>", so a body named "static" cannot merge with the frame
MECHANISM_KINDS = ("revolute", "slider", "cylindrical", "planar", "ball")
NON_GEOMETRIC_KINDS = ("electrical", "thermal", "fluid", "other")
NEAREST_CANDIDATES = 3          # exact queries per nearest-neighbour search, on pairs the table did not measure
MAX_JOINT_GAP_MM = 1.0          # default largest gap a non-fixed joint bridges without a declared clearance

ASSUMPTIONS = [
    "contact is the relation table's: no shared volume and a gap within touch_mm, or shared volume; a contact in "
    "the model does not prove that printed parts meet, stay put or carry load",
    "a joint's moving part seeds a moving body, which grows across fixed joints and fastener clamps/into "
    "declarations; every other part belongs to the static frame and must reach a grounded part through contacts, "
    "fasteners and fixed joints inside its own group; contact across groups, or with an allowed-free part, holds "
    "nothing up",
    "a joint holds only when its parts are measured within the declared interface clearance, else within "
    "max_joint_gap_mm for a moving joint and in contact for a fixed joint",
    "an item inside its container's declared cavity (contains) is held by the container whether or not it touches",
    "a fastener with a modelled solid connects only what that solid touches; one without a solid connects what it "
    "clamps to what it threads into only when its axis, over its length, is measured to reach both",
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

    * ``grounded``: part names (or instance keys) the static frame hangs on; not section ids;
    * ``free``: ``{part: reason}`` parts allowed to float (an empty reason is a finding); a free part
      can be held, but holds nothing up;
    * ``interfaces``: ``[{id, between: [a, b], kind, clearance}]`` (``parts`` is accepted for
      ``between``; dossier ``Interface`` objects too); parties are part names or section ids;
    * ``joints``: ``{id: {kind, moving, fixed, intended_contacts}}``; None takes ``assembly.joints``;
    * ``fasteners``: ``{name: {clamps, into, axes, length_mm}}``, the name as the build keys the placed
      solids; ``axes`` (``[(origin, direction)]``) and ``length_mm`` let a fastener without a solid be
      measured;
    * ``contains``: ``[{what, cavity, container, free}]`` (``container`` defaults to the cavity's part);
    * ``intended_overlaps`` and ``ignore_pairs``: ``[{parts: [a, b], reason}]``;
    * ``strict_interfaces``: an undeclared contact fails instead of warning;
    * ``touch_mm``: the dossier's ``gates.touch_tol_mm`` (None keeps the tolerance given);
    * ``max_joint_gap_mm``: the largest gap a non-fixed joint bridges without a declared clearance.

    Interfaces with the same id are merged when equal; differing ones keep the first and are listed
    in ``duplicates`` (a finding). ``contains``, overlaps and ignored pairs are de-duplicated.
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
    max_joint_gap_mm: float = MAX_JOINT_GAP_MM
    duplicates: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        merged: Dict[str, Dict[str, Any]] = {}
        for raw in self.interfaces:
            i = _interface(raw)
            first = merged.get(i["id"])
            if first is None:
                merged[i["id"]] = i
            elif first != i and i not in [d["declarations"][1] for d in self.duplicates if d["id"] == i["id"]]:
                self.duplicates.append({"kind": "interface", "id": i["id"], "declarations": [first, i]})
        self.interfaces = list(merged.values())
        self.intended_overlaps = _dedupe_pairs(_pair_decl(p) for p in self.intended_overlaps)
        self.ignore_pairs = _dedupe_pairs(_pair_decl(p) for p in self.ignore_pairs)
        contains: List[Dict[str, Any]] = []
        for c in self.contains:
            c = dict(c)
            same = [x for x in contains if (x.get("what"), x.get("cavity")) == (c.get("what"), c.get("cavity"))]
            if same:
                for k, v in c.items():
                    same[0].setdefault(k, v)
            else:
                contains.append(c)
        self.contains = contains
        if not isinstance(self.free, Mapping):
            self.free = _free_map(self.free)
        self.grounded = _unique(str(g) for g in self.grounded)

    @classmethod
    def from_build(cls, result: Any, dossier: Any = None, extra: Optional[Mapping[str, Any]] = None,
                   **overrides: Any) -> "Declarations":
        """Collect the declarations of a dossier build (``BuildResult``, live or from ``load_geometry``),
        the loaded YAML ``Dossier`` (``gates:``, interfaces, cards' ``contains``) and ``extra``, a plain
        mapping with the same keys as the YAML (``grounded``, ``free_parts``, ``interfaces``,
        ``contains``, ``intended_overlaps``, ``ignore_pairs``, ``strict_interfaces``,
        ``max_joint_gap_mm``). Lists are joined; keyword ``overrides`` replace a field."""
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
        fasteners = {}
        for n, f in (geo.get("fasteners") or {}).items():
            axes = [(tuple(i["origin"]), tuple(i["direction"])) for i in f.get("instances", [])
                    if "origin" in i and "direction" in i]
            fasteners[n] = {"clamps": f.get("clamps"), "into": f.get("into"), "axes": axes,
                            "length_mm": f.get("length_mm")}
        fields = dict(grounded=grounded, free=free, interfaces=interfaces, joints=joints,
                      fasteners=fasteners, contains=contains, intended_overlaps=overlaps, ignore_pairs=ignore,
                      strict_interfaces=strict, touch_mm=touch,
                      max_joint_gap_mm=float(extra.get("max_joint_gap_mm", MAX_JOINT_GAP_MM)))
        fields.update(overrides)
        return cls(**fields)


def _unique(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


def _dedupe_pairs(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: Dict[frozenset, Dict[str, Any]] = {}
    for p in items:
        out.setdefault(frozenset(p["parts"]), p)
    return list(out.values())


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
    """Normalise an interface; a party count other than two is kept and reported by the gate."""
    get = i.get if isinstance(i, Mapping) else (lambda k, d=None: getattr(i, k, d))
    between = list(get("between", None) or get("parts", None) or [])
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
    """One graph node: an assembly key with its owner part, kind, body label and section."""
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


Measure = Callable[[str, str], Optional[Relation]]


def analyse(nodes: Mapping[str, Node], relations: Iterable[Relation], decl: Declarations, *,
            contained: Iterable[Tuple[str, str, str, Relation]] = (), measure: Optional[Measure] = None,
            lower_bounds: Optional[Mapping[Tuple[str, str], float]] = None,
            fastener_reach: Optional[Mapping[str, Mapping[str, Any]]] = None,
            notes: Iterable[Mapping[str, Any]] = ()) -> Analysis:
    """The connectivity analysis on given relations, without the kernel.

    ``relations``: the exact pair relations (a ``RelationTable`` iterates as them); pairs absent are
    apart beyond the broad phase. ``contained``: ``(item, container, cavity, relation)`` for items
    found inside a declared cavity. ``measure(a, b)``: an exact query for pairs not in
    ``relations`` (witnesses, joint and interface gaps); without it those read as unmeasured.
    ``lower_bounds``: box distances, to pick which pairs to measure. ``fastener_reach``: for a
    fastener without a solid, ``{name: {"ok": bool, "axes": [...], "reason": str}}`` from measuring
    its axis against what it clamps and threads into; a fastener without it is not counted.
    ``notes``: declarations the caller could not check, passed through to ``not_checked``."""
    a = _Analyser(nodes, relations, decl, measure, lower_bounds or {}, fastener_reach or {})
    return a.run(list(contained), list(notes))


class _Analyser:
    def __init__(self, nodes, relations, decl: Declarations, measure, lower_bounds, fastener_reach):
        self.nodes: Dict[str, Node] = dict(nodes)
        self.decl = decl
        self.measure = measure
        self.bounds = lower_bounds
        self.reach = fastener_reach
        self.by_owner: Dict[str, List[str]] = {}
        self.by_section: Dict[str, List[str]] = {}
        for k in sorted(self.nodes):
            n = self.nodes[k]
            self.by_owner.setdefault(n.owner, []).append(k)
            if n.section:
                self.by_section.setdefault(n.section, []).append(k)
        self.ignored: Set[frozenset] = set()
        for p in decl.ignore_pairs:
            for x in self.resolve(p["parts"][0]):
                for y in self.resolve(p["parts"][1]):
                    self.ignored.add(frozenset((x, y)))
        self.rels: Dict[frozenset, Relation] = {}
        for r in relations:
            pair = frozenset((r.a, r.b))
            if r.a in self.nodes and r.b in self.nodes and r.a != r.b and pair not in self.ignored:
                self.rels[pair] = r
        self.joints: Dict[str, Dict[str, Any]] = {str(k): dict(v) for k, v in (decl.joints or {}).items()}
        self.checks: List[Check] = []
        self.not_checked: List[Dict[str, Any]] = []
        self.body_of: Dict[str, str] = {}
        self.moving: Set[str] = set()

    # -- lookups
    def resolve(self, name: Any) -> List[str]:
        """Keys a declared name stands for: the key itself, the instances of a part, or a section's parts."""
        if name is None:
            return []
        name = str(name)
        if name in self.nodes:
            return [name]
        return list(self.by_owner.get(name) or self.by_section.get(name) or [])

    def resolve_part(self, name: Any) -> List[str]:
        """Keys of a part name or instance key only (never a section)."""
        if name is None:
            return []
        name = str(name)
        return [name] if name in self.nodes else list(self.by_owner.get(name) or [])

    def group(self, key: str) -> str:
        body = self.body_of.get(key)
        if body is None and self.nodes[key].body in self.moving:
            body = self.nodes[key].body
        return STATIC if body is None else BODY + body

    def rel(self, a: str, b: str, measure: bool = True) -> Optional[Relation]:
        """The relation oriented (a, b): stored, else measured (when allowed and possible), else None.
        Ignored pairs are never measured."""
        pair = frozenset((a, b))
        r = self.rels.get(pair)
        if r is None and measure and self.measure is not None and pair not in self.ignored:
            r = self.measure(a, b)
            if r is not None:
                self.rels[pair] = r
        if r is None:
            return None
        return r if r.a == a else r.flipped()

    def bound(self, a: str, b: str) -> float:
        v = self.bounds.get((a, b), self.bounds.get((b, a)))
        return float("inf") if v is None else float(v)

    def nearest(self, inside: Sequence[str], outside: Sequence[str]) -> Optional[Relation]:
        """The closest pair between two sets: the stored relations, then up to ``NEAREST_CANDIDATES``
        exact queries on unmeasured pairs whose boxes are closer than the best stored gap."""
        ins, outs = set(inside), set(outside)
        best = None
        for pair, r in self.rels.items():
            x, y = tuple(pair)
            if (x in ins) == (y in ins) or (y if x in ins else x) not in outs or r.gap_mm is None:
                continue
            r = r if r.a in ins else r.flipped()
            if best is None or (r.gap_mm, r.a, r.b) < (best.gap_mm, best.a, best.b):
                best = r
        if self.measure is None:
            return best
        # pairs the table did not measure can still be nearer than a measured one (a box distance is only a
        # lower bound): measure the few whose boxes are closer than the best gap so far
        limit = float("inf") if best is None else best.gap_mm
        cands = sorted((self.bound(x, y), x, y) for x in inside for y in outside
                       if x != y and frozenset((x, y)) not in self.rels and frozenset((x, y)) not in self.ignored
                       and (best is None or self.bound(x, y) < limit))
        for _, x, y in cands[:NEAREST_CANDIDATES]:
            r = self.rel(x, y)
            if r is not None and r.gap_mm is not None and (best is None or r.gap_mm < best.gap_mm):
                best = r
        return best

    def check(self, cid: str, status: str, message: str, parts: Iterable[str] = (), **evidence: Any) -> None:
        self.checks.append(Check(cid, status, message, tuple(sorted(set(parts))),
                                 {k: v for k, v in evidence.items() if v is not None}))

    def _clearance(self, iid: str) -> Optional[float]:
        for i in self.decl.interfaces:
            if i["id"] == iid:
                return i["clearance"]
        return None

    # -- the run
    def run(self, contained, notes) -> Analysis:
        self.not_checked += [dict(n) for n in notes]
        for d in self.decl.duplicates:
            self.check(f"duplicate:{d['kind']}:{d['id']}", "warn", f"{d['kind']} {d['id']} is declared twice, "
                       "differently; the first declaration is used", declarations=d["declarations"])
        free = self._free()
        grounded_keys = self._ground_keys()
        self._bodies(grounded_keys)
        anchors = self._ground(grounded_keys)
        joint_rows = self._joints()
        self.contained = [(c[0], c[1], c[2]) for c in contained]
        edges, unknown = self._edges(contained, free, joint_rows)
        for r in unknown:
            self.check(f"relation:{r.a}|{r.b}", "fail", f"the kernel could not decide {r.a} / {r.b}: {r.error}; "
                       "the contact graph is unreliable there", (r.a, r.b), error=r.error)
        comp = _components(sorted(self.nodes), [(e["a"], e["b"]) for e in edges if e["rigid"]])
        grounded_comps, via = self._grounded_comps(comp, anchors, joint_rows)
        groups = sorted({self.group(k) for k in self.nodes}, key=lambda g: (g != STATIC, g))
        islands, exclusions = self._islands(comp, grounded_comps, free, groups, anchors, joint_rows)
        self._joint_checks(comp, grounded_comps, joint_rows)
        unrealised = self._interface_checks() + self._fastener_checks()
        undeclared = self._undeclared(edges, free)
        graph = self._graph(edges, comp, grounded_comps, free, anchors, groups, via, islands, unrealised, joint_rows)
        extra = {"graph": graph, "floating": islands, "undeclared_contacts": undeclared,
                 "unrealised": unrealised, "not_checked": self.not_checked}
        return Analysis(self.checks, exclusions, extra)

    def _free(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name in sorted(self.decl.free):
            reason = str(self.decl.free[name] or "").strip()
            keys = self.resolve_part(name)
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

    def _ground_keys(self) -> Dict[str, List[str]]:
        return {name: self.resolve_part(name) for name in self.decl.grounded}

    def _bodies(self, grounded_keys: Mapping[str, List[str]]) -> None:
        """Moving bodies: each non-fixed joint's moving instances, grown across fixed joints and fastener
        declarations (transitively). A link into ground, a joint's fixed part or another body is a finding."""
        seeds: Dict[str, str] = {}
        stop: Dict[str, str] = {k: "a grounded part" for ks in grounded_keys.values() for k in ks}
        for jid in sorted(self.joints):
            j = self.joints[jid]
            if j.get("kind", "revolute") == "fixed":
                continue
            for k in self.resolve_part(j.get("moving")):
                seeds.setdefault(k, self.nodes[k].body)
            for k in self.resolve_part(j.get("fixed")):
                stop.setdefault(k, f"the fixed part of joint {jid}")
        links: Dict[str, List[Tuple[str, str]]] = {}

        def link(xs: Iterable[str], ys: Iterable[str], via: str) -> None:
            for x in xs:
                for y in ys:
                    if x != y:
                        links.setdefault(x, []).append((y, via))
                        links.setdefault(y, []).append((x, via))

        for jid in sorted(self.joints):
            j = self.joints[jid]
            if j.get("kind", "revolute") == "fixed":
                link(self.resolve_part(j.get("moving")), self.resolve_part(j.get("fixed")), f"fixed joint {jid}")
        for name in sorted(self.decl.fasteners):
            f = self.decl.fasteners[name]
            keys, clamps, into = (self.resolve_part(name), self.resolve_part(f.get("clamps")),
                                  self.resolve_part(f.get("into")))
            link(keys, clamps + into, f"fastener {name}")
            link(clamps, into, f"fastener {name}")
        self.moving = set(seeds.values())
        body_of: Dict[str, str] = dict(seeds)
        conflicts: Dict[str, List[Dict[str, Any]]] = {}
        for body in sorted(self.moving):
            queue = sorted(k for k, b in seeds.items() if b == body)
            while queue:
                n = queue.pop(0)
                for m, via in sorted(links.get(n, [])):
                    clash = None
                    if m in stop and m not in seeds:
                        clash = stop[m]
                    elif m in body_of and body_of[m] != body:
                        clash = f"body {body_of[m]}"
                    if clash:
                        conflicts.setdefault(body, []).append({"from": n, "to": m, "via": via, "is": clash})
                        continue
                    if m not in body_of:
                        body_of[m] = body
                        queue.append(m)
        self.body_of = body_of
        for body in sorted(conflicts):
            rows = conflicts[body]
            text = "; ".join(f"{r['via']} joins {r['from']} to {r['to']}, {r['is']}" for r in rows)
            self.check(f"bodies:{body}", "fail", f"declared rigid links tie moving body {body} to what it moves "
                       f"against: {text}", {r["to"] for r in rows} | {r["from"] for r in rows}, links=rows)
        for k in sorted(self.nodes):
            given = self.nodes[k].body
            derived = body_of.get(k)
            if given in self.moving and derived is not None and derived != given:
                self.check(f"body-label:{k}", "warn", f"{k} is labelled into moving body {given}, but its declared "
                           f"links put it in {derived}; the derived body is used", (k,), given=given, derived=derived)

    def _ground(self, grounded_keys: Mapping[str, List[str]]) -> List[str]:
        anchors, missing, moving, sections = [], [], [], []
        for name, keys in grounded_keys.items():
            if not keys:
                (sections if name in self.by_section else missing).append(name)
            for k in keys:
                (moving if self.group(k) != STATIC else anchors).append(k)
            if len(keys) > 1:
                self.check(f"ground:{name}", "warn", f"grounded {name!r} has {len(keys)} instances; each is taken "
                           "as ground. Name the instances that rest on the world to ground only those", keys)
        anchors = sorted(set(anchors))
        why = []
        if not self.decl.grounded:
            why.append("no part is declared grounded, so nothing can be checked for floating")
        if sections:
            why.append(f"grounded {sections} are sections; ground names parts")
        if missing:
            why.append(f"grounded {missing} not in the assembly")
        if moving:
            why.append(f"grounded {sorted(moving)} belong to a moving body")
        if self.decl.grounded and not anchors and not why:
            why.append("no grounded part resolved")
        if why:
            self.check("ground", "fail", "; ".join(why), moving, grounded=list(self.decl.grounded), missing=missing,
                       sections=sections)
        else:
            self.check("ground", "pass", f"grounded: {', '.join(anchors)}", anchors)
        return anchors

    def _joints(self) -> Dict[str, Dict[str, Any]]:
        """Per joint and moving instance: the fixed instances it is held by (measured gap within the limit)."""
        rows: Dict[str, Dict[str, Any]] = {}
        for jid in sorted(self.joints):
            j = self.joints[jid]
            kind = j.get("kind", "revolute")
            mv, fx = self.resolve_part(j.get("moving")), self.resolve_part(j.get("fixed"))
            clearance = self._clearance(jid)
            limit = clearance if clearance is not None else (None if kind == "fixed" else self.decl.max_joint_gap_mm)
            inst = {}
            for m in mv:
                measured = []
                for f in fx:
                    if f == m:
                        continue
                    r = self.rel(m, f)
                    gap = None if r is None or r.state in ("unknown", "unchecked") else r.gap_mm
                    holds = gap is not None and ((r.in_contact) if limit is None else gap <= limit + 1e-9)
                    measured.append({"fixed": f, "state": None if r is None else r.state, "gap_mm": gap,
                                     "holds": holds, "witness": dict(r.witness) if r is not None else None})
                measured.sort(key=lambda x: (not x["holds"], x["gap_mm"] if x["gap_mm"] is not None else float("inf"),
                                             x["fixed"]))
                inst[m] = measured
            rows[jid] = {"kind": kind, "moving": mv, "fixed": fx, "limit_mm": limit, "clearance_mm": clearance,
                         "instances": inst}
        return rows

    def _edges(self, contained, free, joint_rows):
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
            if self.resolve_part(name):
                continue                       # a modelled solid: its contacts carry the connection
            reach = self.reach.get(name) or {}
            if not reach.get("ok"):
                continue                       # reported by the fastener check; not counted as a connection
            f = self.decl.fasteners[name]
            for x in self.resolve_part(f.get("clamps")):
                for y in self.resolve_part(f.get("into")):
                    if x != y:
                        edges.append({"a": x, "b": y, "kind": "fastener", "fastener": name,
                                      "measured": "axis reaches both"})
        for jid, row in joint_rows.items():
            for m, measured in row["instances"].items():
                for x in measured:
                    edges.append({"a": m, "b": x["fixed"], "kind": "joint", "joint": jid, "joint_kind": row["kind"],
                                  "holds": x["holds"], "gap_mm": x["gap_mm"]})
        for e in edges:
            nonfixed = e["kind"] == "joint" and (e["joint_kind"] != "fixed" or not e["holds"])
            loose = e["a"] in free or e["b"] in free
            e["rigid"] = not nonfixed and not loose and self.group(e["a"]) == self.group(e["b"])
            if loose:
                e["via_free_part"] = True
        return edges, unknown

    def _grounded_comps(self, comp, anchors, joint_rows):
        grounded = {comp[k] for k in anchors}
        via: Dict[int, str] = {}
        changed = bool(grounded)
        while changed:
            changed = False
            for jid, row in sorted(joint_rows.items()):
                if row["kind"] == "fixed":
                    continue
                for m, measured in sorted(row["instances"].items()):
                    if comp[m] in grounded or self.group(m) == STATIC:
                        continue
                    if any(x["holds"] and comp[x["fixed"]] in grounded and self.group(x["fixed"]) != self.group(m)
                           for x in measured):
                        grounded.add(comp[m])
                        via[comp[m]] = jid
                        changed = True
        return grounded, via

    def _islands(self, comp, grounded, free, groups, anchors, joint_rows):
        members: Dict[int, List[str]] = {}
        for k in sorted(self.nodes):
            members.setdefault(comp[k], []).append(k)
        held_by: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}   # moving instance -> its joint rows
        for jid, row in joint_rows.items():
            if row["kind"] != "fixed":
                for m, measured in row["instances"].items():
                    held_by.setdefault(m, []).append((jid, {"measured": measured, "limit": row["limit_mm"]}))
        contacts: Dict[str, List[Tuple[str, Relation]]] = {}
        for pair, r in sorted(self.rels.items(), key=lambda kv: sorted(kv[0])):
            if r.in_contact:
                x, y = sorted(pair)
                contacts.setdefault(x, []).append((y, r))
                contacts.setdefault(y, []).append((x, r))
        islands: List[Dict[str, Any]] = []
        exclusions: List[Dict[str, Any]] = []
        by_group: Dict[str, List[Dict[str, Any]]] = {g: [] for g in groups}
        has_ground = bool(anchors)
        for cid in sorted(members, key=lambda c: members[c]):
            if cid in grounded or not has_ground:
                continue                       # without ground the ground check has failed; every part would be listed
            parts = members[cid]
            g = self.group(parts[0])
            loose = [k for k in parts if k in free]
            stuck = [k for k in parts if k not in free]
            if not stuck:
                exclusions.append({"parts": parts, "reason": "; ".join(sorted({free[k] for k in parts})),
                                   "kind": "allowed free"})
                continue
            ground_outside = [k for k in sorted(self.nodes) if comp[k] in grounded]
            # the witness: the nearest grounded part of the same group (what could hold it), else any grounded part
            near = (self.nearest(parts, [k for k in ground_outside if self.group(k) == g])
                    or self.nearest(parts, ground_outside)
                    or self.nearest(parts, [k for k in sorted(self.nodes) if comp[k] != cid]))
            touches = []
            for k in parts:
                for o, r in contacts.get(k, []):
                    if comp[o] != cid:
                        touches.append({"part": k, "other": o, "other_group": self.group(o), "state": r.state,
                                        "other_free": o in free})
            joints = []
            for k in parts:
                for jid, info in held_by.get(k, []):
                    best = info["measured"][0] if info["measured"] else None
                    joints.append({"joint": jid, "moving": k, "limit_mm": info["limit"],
                                   "fixed": best["fixed"] if best else None,
                                   "gap_mm": best["gap_mm"] if best else None,
                                   "holds": bool(best and best["holds"]),
                                   "fixed_grounded": bool(best and comp[best["fixed"]] in grounded)})
            isl = {"group": g, "parts": stuck, "free_members": loose, "touches": touches, "joints": joints,
                   "nearest": _witness(near, self.group(near.b), comp[near.b] in grounded) if near else None}
            islands.append(isl)
            by_group.setdefault(g, []).append(isl)
        if not has_ground:
            return islands, exclusions
        for g in groups:
            parts = [k for k in self.nodes if self.group(k) == g]
            found = by_group.get(g, [])
            hangs = sorted(anchors) if g == STATIC else sorted({m for jid, row in joint_rows.items()
                                                                 if row["kind"] != "fixed"
                                                                 for m in row["instances"] if self.group(m) == g})
            if not found:
                self.check(f"connect:{g}", "pass", f"{len(parts)} part(s) reach ground"
                           + (f" through {', '.join(hangs)}" if hangs else ""), anchors=hangs, part_count=len(parts))
                continue
            text = []
            for isl in found:
                n = isl["nearest"]
                where = (f"nearest {'grounded ' if n.get('neighbour_grounded') else 'ungrounded '}part "
                         f"{n['neighbour']} at {n['gap_mm']:.3f} mm") if n else "no part measured nearby"
                others = sorted({t["other"] for t in isl["touches"] if not t["other_free"]})
                loose = sorted({t["other"] for t in isl["touches"] if t["other_free"]})
                if others:
                    where += f"; touches {', '.join(others)} only across bodies"
                if loose:
                    where += f"; touches only free part(s) {', '.join(loose)}, which hold nothing up"
                for j in isl["joints"]:
                    if not j["holds"]:
                        got = "unmeasured" if j["gap_mm"] is None else f"{j['gap_mm']:.3f} mm"
                        where += f"; joint {j['joint']} does not hold {j['moving']} ({got} from {j['fixed']})"
                    elif not j["fixed_grounded"]:
                        where += f"; hangs on {j['fixed']} through {j['joint']}, which does not reach ground"
                text.append(f"[{', '.join(isl['parts'])}] ({where})")
            floating = sorted({k for isl in found for k in isl["parts"]})
            self.check(f"connect:{g}", "fail", f"{len(found)} floating island(s): " + "; ".join(text), floating,
                       anchors=hangs, islands=found)
        return islands, exclusions

    def _joint_checks(self, comp, grounded, joint_rows):
        for jid, row in joint_rows.items():
            j = self.joints[jid]
            kind, mv, fx, limit = row["kind"], row["moving"], row["fixed"], row["limit_mm"]
            cid = f"joint:{jid}"
            if not mv or not fx:
                missing = [n for n, ks in ((j.get("moving"), mv), (j.get("fixed"), fx)) if not ks]
                self.check(cid, "fail", f"{kind} joint names {missing}, which are not parts in the assembly", mv + fx)
                continue
            ev = {"kind": kind, "limit_mm": limit, "clearance_mm": row["clearance_mm"],
                  "instances": {m: [{k: v for k, v in x.items() if v is not None} for x in ms]
                                for m, ms in row["instances"].items()}}
            problems, held = [], []
            for m in mv:
                measured = row["instances"].get(m, [])
                best = measured[0] if measured else None
                if kind != "fixed" and any(self.group(f) == self.group(m) for f in fx):
                    problems.append(f"the fixed part {fx[0]} is in {m}'s own moving body")
                    continue
                if best is None or not best["holds"]:
                    got = "unmeasured" if best is None or best["gap_mm"] is None else f"{best['gap_mm']:.3f} mm"
                    need = ("contact or a declared clearance" if limit is None else
                            f"<= {limit:g} mm" + (" (declared clearance)" if row["clearance_mm"] is not None else
                                                  " (max_joint_gap_mm)"))
                    problems.append(f"{m} is {got} from {best['fixed'] if best else fx[0]}, needs {need}")
                    continue
                if kind == "fixed":
                    if self.group(m) != self.group(best["fixed"]):
                        problems.append(f"fixed joint joins {m} ({self.group(m)}) and {best['fixed']} "
                                        f"({self.group(best['fixed'])}), which are in different bodies")
                        continue
                elif comp[best["fixed"]] not in grounded:
                    problems.append(f"{m} hangs on {best['fixed']}, which does not reach ground")
                    continue
                held.append(f"{m} on {best['fixed']} ({best['state']}, gap {best['gap_mm']:.3f} mm)")
            if problems:
                self.check(cid, "fail", f"{kind} joint {jid}: " + "; ".join(problems), mv + fx, **ev)
            else:
                self.check(cid, "pass", f"{kind} joint {jid} holds " + "; ".join(held), mv + fx, **ev)

    def _interface_checks(self) -> List[Dict[str, Any]]:
        unrealised: List[Dict[str, Any]] = []
        for i in self.decl.interfaces:
            iid, kind = i["id"], i["kind"]
            cid = f"interface:{iid}"
            if kind in NON_GEOMETRIC_KINDS:
                self.not_checked.append({"interface": iid, "kind": kind, "reason": "not geometric"})
                continue
            if len(i["between"]) != 2:
                self.check(cid, "fail", f"interface {iid} names {len(i['between'])} parties {i['between']}; an "
                           "interface is between exactly two")
                unrealised.append({"kind": "interface", "id": iid, "parts": i["between"], "reason": "not two parties"})
                continue
            pa, pb = i["between"]
            A, B = self.resolve(pa), self.resolve(pb)
            if not A or not B:
                missing = [n for n, ks in ((pa, A), (pb, B)) if not ks]
                self.check(cid, "fail", f"interface {iid} names {missing}, not in the assembly", A + B)
                unrealised.append({"kind": "interface", "id": iid, "parts": [pa, pb], "reason": "missing party"})
                continue
            if kind in MECHANISM_KINDS:
                j = self.joints.get(iid)
                if j is None:
                    self.check(cid, "fail", f"{kind} interface {iid} ({pa} / {pb}) has no registered joint",
                               A[:1] + B[:1])
                    unrealised.append({"kind": "interface", "id": iid, "parts": [pa, pb], "reason": "no joint"})
                    continue
                jm, jf = set(self.resolve_part(j.get("moving"))), set(self.resolve_part(j.get("fixed")))
                if not ((jm <= set(A) and jf <= set(B)) or (jm <= set(B) and jf <= set(A))):
                    self.check(cid, "fail", f"{kind} interface {iid} is between {pa} and {pb}, but joint {iid} "
                               f"joins {j.get('moving')} and {j.get('fixed')}", A[:1] + B[:1])
                    unrealised.append({"kind": "interface", "id": iid, "parts": [pa, pb], "reason": "joint parties"})
                    continue
                self.check(cid, "pass", f"{kind} interface {iid} is realised by its registered joint (see joint:{iid})",
                           A[:1] + B[:1], joint=iid)
                continue
            pairs = [(x, y) for x in A for y in B if x != y]
            skipped = [p for p in pairs if frozenset(p) in self.ignored]
            pairs = [p for p in pairs if frozenset(p) not in self.ignored]
            if not pairs:
                self.not_checked.append({"interface": iid, "reason": "every pair of its parties is in ignore_pairs"})
                continue
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
            if near is not None and frozenset((near.a, near.b)) in self.ignored:
                near = None
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
                why = ("no instance pair was measured: " + ("its pairs are unchecked (outside the table) and no kernel "
                                                           "was given" if self.measure is None else
                                                           "the kernel gave no distance"))
            else:
                why = f"{near.a} and {near.b} are apart by {gap:.3f} mm" + (
                    f", over the declared clearance {clearance:g} mm" if clearance is not None else
                    "; declare a clearance if the gap is intended")
            parts = (near.a, near.b) if near is not None else tuple(A[:1] + B[:1])
            self.check(cid, "fail", f"declared interface {iid} ({pa} / {pb}) is not realised: {why}", parts,
                       relation=_rel_summary(near), clearance_mm=clearance,
                       ignored_pairs=[sorted(p) for p in skipped] or None)
            unrealised.append({"kind": "interface", "id": iid, "parts": list(parts), "gap_mm": gap,
                               "clearance_mm": clearance, "reason": why,
                               "witness": dict(near.witness) if near is not None else None})
        return unrealised

    def _fastener_checks(self) -> List[Dict[str, Any]]:
        unrealised: List[Dict[str, Any]] = []
        for name in sorted(self.decl.fasteners):
            f = self.decl.fasteners[name]
            keys = self.resolve_part(name)
            clamps, into = self.resolve_part(f.get("clamps")), self.resolve_part(f.get("into"))
            cid = f"fastener:{name}"
            if not clamps or not into:
                missing = [n for n, ks in ((f.get("clamps"), clamps), (f.get("into"), into)) if not ks]
                self.check(cid, "fail", f"fastener {name} names {missing}, not parts in the assembly",
                           keys + clamps + into)
                unrealised.append({"kind": "fastener", "id": name, "parts": keys, "reason": "missing party"})
                continue
            if not keys:
                reach = self.reach.get(name)
                if reach is None or reach.get("ok") is None:
                    why = (reach or {}).get("reason") or "no solid, and no axis and length to measure"
                    self.check(cid, "warn", f"fastener {name} has no modelled solid and could not be measured "
                               f"({why}); {f.get('clamps')} / {f.get('into')} are not counted as joined by it",
                               clamps + into, measured=False)
                    self.not_checked.append({"fastener": name, "reason": why})
                elif reach["ok"]:
                    self.check(cid, "pass", f"fastener {name} has no solid; its axis reaches {f.get('clamps')} and "
                               f"{f.get('into')} over its length", clamps + into, axes=reach.get("axes"))
                else:
                    self.check(cid, "fail", f"fastener {name} has no solid, and its axis over its length does not "
                               f"reach both {f.get('clamps')} and {f.get('into')} ({reach.get('reason', '')})",
                               clamps + into, axes=reach.get("axes"))
                    unrealised.append({"kind": "fastener", "id": name, "parts": [clamps[0], into[0]],
                                       "reason": "axis misses"})
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
            if len(i["between"]) == 2:
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
        for item, container, cavity in getattr(self, "contained", []):
            add([item], [container], f"contains:{cavity}")
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

    def _graph(self, edges, comp, grounded, free, anchors, groups, via, islands, unrealised, joint_rows):
        floating = {k for isl in islands for k in isl["parts"]}
        order = {c: i for i, c in enumerate(sorted(set(comp.values()), key=lambda c: min(
            k for k in self.nodes if comp[k] == c)))}
        nodes = []
        for k in sorted(self.nodes):
            n = self.nodes[k]
            nodes.append({"id": k, "owner": n.owner, "kind": n.kind, "group": self.group(k),
                          "body_given": n.body, "section": n.section, "grounded": k in anchors, "free": free.get(k),
                          "component": f"c{order[comp[k]]}", "held": comp[k] in grounded, "floating": k in floating})
        comps = []
        for c in sorted(order, key=order.get):
            parts = sorted(k for k in self.nodes if comp[k] == c)
            comps.append({"id": f"c{order[c]}", "group": self.group(parts[0]), "parts": parts,
                          "grounded": c in grounded, "via_joint": via.get(c)})
        grp = []
        for g in groups:
            cs = [x for x in comps if x["group"] == g]
            grp.append({"group": g, "grounded": bool(cs) and all(x["grounded"] for x in cs if not all(
                p in free for p in x["parts"])), "via_joints": sorted({x["via_joint"] for x in cs if x["via_joint"]})})
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


def _witness(r: Relation, group: Optional[str], grounded: Optional[bool]) -> Dict[str, Any]:
    out = {"part": r.a, "neighbour": r.b, "gap_mm": r.gap_mm, "state": r.state,
           "point_a": r.witness.get("point_a"), "point_b": r.witness.get("point_b")}
    if group is not None:
        out["neighbour_group"] = group
    if grounded is not None:
        out["neighbour_grounded"] = grounded
    return {k: v for k, v in out.items() if v is not None}


# ----------------------------------------------------------------------------- the gate (kernel)

def fastener_reach(assembly: Any, decl: Declarations, tol: Tolerances) -> Dict[str, Dict[str, Any]]:
    """For each declared fastener without a solid in ``assembly``: does its axis, from the seat over
    ``length_mm``, come within ``touch_mm`` of what it clamps and of what it threads into? A fastener
    with no axes or no length is unmeasured (``ok: None``)."""
    from cadagent._deps import require
    from cadagent.review.gates.relations import _distance

    out: Dict[str, Dict[str, Any]] = {}
    names = list(assembly)
    for name, f in sorted(decl.fasteners.items()):
        if any(k == name or owner(k) == name for k in names):
            continue
        axes, length = f.get("axes") or [], f.get("length_mm")
        clamps = [k for k in names if k == f.get("clamps") or owner(k) == f.get("clamps")]
        into = [k for k in names if k == f.get("into") or owner(k) == f.get("into")]
        if not axes or not length or not clamps or not into:
            out[name] = {"ok": None, "reason": "no axes" if not axes else ("no length" if not length else
                                                                            "a party is not in the assembly")}
            continue
        brep = require("OCP.BRepBuilderAPI", "fastener axis")
        gp = require("OCP.gp", "fastener axis")
        rows, ok = [], False
        for origin, direction in axes:
            n = sum(c * c for c in direction) ** 0.5 or 1.0
            end = [o + float(length) * c / n for o, c in zip(origin, direction)]
            seg = brep.BRepBuilderAPI_MakeEdge(gp.gp_Pnt(*map(float, origin)), gp.gp_Pnt(*end)).Edge()
            row = {"origin": list(origin), "end": [round(v, 6) for v in end]}
            for role, keys in (("clamps", clamps), ("into", into)):
                try:
                    row[f"{role}_mm"] = round(min(_distance(seg, assembly.shape(k))[0] for k in keys), 6)
                except Exception as exc:   # an unmeasured axis is not a connection
                    row[f"{role}_mm"] = None
                    row["error"] = f"{type(exc).__name__}: {exc}"
            row["ok"] = all(row.get(f"{r}_mm") is not None and row[f"{r}_mm"] <= tol.touch_mm
                            for r in ("clamps", "into"))
            ok = ok or row["ok"]
            rows.append(row)
        out[name] = {"ok": ok, "axes": rows,
                     "reason": "" if ok else "the axis misses " + ", ".join(
                         sorted({r for row in rows for r in ("clamps", "into")
                                 if row.get(f"{r}_mm") is None or row[f"{r}_mm"] > tol.touch_mm}))}
    return out


def connectivity_gate(assembly: Any, declarations: Optional[Declarations] = None, *, table: Any = None,
                      tol: Optional[Tolerances] = None, cache: Any = None, out: Any = None,
                      dot: Any = None) -> Dict[str, Any]:
    """Run the connectivity gate on an ``Assembly`` and return (with ``out``, write) the verdict.

    ``declarations`` default to none (then the ground check fails: something must be grounded).
    ``table``: a ``RelationTable`` already built for this assembly; it is read, never changed (extra
    queries go through ``relate_pair`` and ``cache``). Without one, a table is built with ``tol``,
    the declarations' ``touch_mm`` and ``ignore_pairs``. ``dot``: where to write the Graphviz graph
    (default: beside ``out`` with the suffix ``.dot``)."""
    from cadagent.review.gates.relations import relate_pair, relation_table

    decl = declarations or Declarations()
    mismatch = None
    if table is not None:
        if tol is not None and tol != table.tolerances:
            raise ValueError("tol differs from the given table's tolerances; pass one or the other")
        tol = table.tolerances
        if decl.touch_mm is not None and decl.touch_mm != tol.touch_mm:
            mismatch = (decl.touch_mm, tol.touch_mm)
    elif tol is None:
        tol = Tolerances(touch_mm=decl.touch_mm) if decl.touch_mm is not None else Tolerances()
    if table is None:
        table = relation_table(assembly, tol, cache=cache, skip_pairs=[p["parts"] for p in decl.ignore_pairs])
    joints = decl.joints if decl.joints is not None else dict(getattr(assembly, "joints", {}) or {})
    contains = []
    for c in decl.contains:
        c = dict(c)
        cav = assembly.cavities.get(c.get("cavity"))
        if cav is not None and not c.get("container"):
            c["container"] = cav.container
        contains.append(c)
    decl = replace(decl, joints=joints, contains=contains, duplicates=list(decl.duplicates))
    nodes = {k: Node(k, owner(k), assembly[k].kind, assembly[k].body, assembly[k].group) for k in assembly}
    contained: List[Tuple[str, str, str, Relation]] = []
    notes: List[Dict[str, Any]] = []
    for c in decl.contains:
        cav, what = c.get("cavity"), c.get("what")
        if cav not in assembly.cavities:
            notes.append({"contains": what, "cavity": cav, "reason": "cavity not registered (a dossier lint "
                          "finding); its items are held only by their contacts"})
            continue
        container = assembly.cavities[cav].container
        for k in [k for k in assembly if k == what or owner(k) == what]:
            r = relate_pair(assembly, k, cav, tol, cache=cache)
            if r.state == "contains" and r.contained in ("a_in_b", "both"):
                contained.append((k, container, cav, r))
            elif r.state == "unknown":
                notes.append({"contains": k, "cavity": cav, "reason": f"the kernel could not decide: {r.error}"})
    for a, b in getattr(table, "skipped", []):
        notes.append({"pair": [a, b], "reason": "skipped by the relation table (skip_pairs); never measured"})

    def measure(a: str, b: str) -> Optional[Relation]:
        r = table.relations.get((a, b)) or table.relations.get((b, a))
        return r if r is not None else relate_pair(assembly, a, b, tol, cache=cache)

    an = analyse(nodes, list(table), decl, contained=contained, measure=measure, lower_bounds=table.lower_bounds,
                 fastener_reach=fastener_reach(assembly, decl, tol), notes=notes)
    if mismatch is not None:
        an.checks.append(Check("tolerances", "warn", f"the declarations ask touch_mm {mismatch[0]:g} but the given "
                               f"relation table used {mismatch[1]:g}; the table's is used"))
    stats = {k: table.stats[k] for k in ("parts", "pairs", "candidates") if k in table.stats}
    stats["states"] = {s: sum(1 for r in table if r.state == s) for s in ("apart", "touching", "overlapping",
                                                                          "contains", "unknown")}
    an.extra["relation_stats"] = stats
    data = verdict(GATE, an.checks, assumptions=ASSUMPTIONS, exclusions=an.exclusions, extra=an.extra,
                   limits={"touch_mm": tol.touch_mm, "near_mm": tol.near_mm, "overlap_mm3": tol.overlap_mm3,
                           "max_joint_gap_mm": decl.max_joint_gap_mm, "strict_interfaces": decl.strict_interfaces,
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
        from cadagent.review.gates.relations import Assembly
        assembly = Assembly.from_build(result)
    return connectivity_gate(assembly, Declarations.from_build(result, dossier, extra), **kwargs)


# ----------------------------------------------------------------------------- the graph as DOT

def _q(s: Any) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_dot(data: Mapping[str, Any]) -> str:
    """Graphviz DOT of a connectivity verdict (or of its ``graph``): one cluster per group, grounded
    parts double-framed, floating parts red, free parts dashed; contacts solid (grey when they hold
    nothing up, orange when undeclared), containment dotted, measured fasteners bold, joints blue
    dashed (red when they do not hold), unrealised declarations red dashed. Deterministic."""
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
        label = ("static frame" if name == STATIC else name.replace(BODY, "body ", 1)) + (
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
            attrs += ["style=bold", f"label={_q(str(e.get('fastener')) + ' (axis)')}"]
        elif e["kind"] == "joint":
            attrs += ["style=dashed", "color=blue" if e.get("holds") else "color=red",
                      f"label={_q(str(e.get('joint')) + ' ' + str(e.get('joint_kind')))}"]
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


__all__ = ["Declarations", "Node", "Analysis", "analyse", "connectivity_gate", "connectivity_from_build",
           "fastener_reach", "to_dot", "write_dot", "owner", "ASSUMPTIONS", "GATE", "STATIC", "MAX_JOINT_GAP_MM"]
