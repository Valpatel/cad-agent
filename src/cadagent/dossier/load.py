"""Load a design dossier from YAML, with the file and line of every item, and resolve its ids.

Layout (``docs/dossier.md``)::

    dossier/project.yaml          title, requirements, sections (paths or inline), interfaces, decisions, assembly, gates
    dossier/sections/<id>.yaml    one section and its part cards; ``parts: [parts/x.yaml]`` loads a card in place
    dossier/decisions.yaml        project decisions (the site's format, plus scope and structured alternatives)

Paths inside the dossier are relative to the directory of ``project.yaml``; ``sections`` entries may be globs.

Errors (wrong types, malformed or duplicate ids, references to ids that do not exist) carry ``file:line``. With
``strict=True`` (the default) they raise one ``DossierError`` listing all of them; with ``strict=False`` they are
returned in ``Dossier.errors`` so a lint can report everything at once. Unknown keys are never fatal: they are
reported in ``Dossier.findings`` with their line, so a typo is visible instead of silently ignored.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .model import (
    DECISION_SCOPES, DECISION_STATUS, DIRECTION_RE, ID_RE, INTERFACE_KINDS, PART_STATUS, REQUIREMENT_STATUS,
    SOURCE_KINDS, VERIFY_BY, Alternative, AssemblyStep, Containment, Decision, Dossier, FastenerUse, FreePart,
    GateConfig, Interface, Issue, Material, PairExemption, PartCard, Requirement, Section, Source, Where,
)

PathLike = Union[str, Path]


class DossierError(ValueError):
    """The dossier is malformed. ``issues`` lists every error; ``file`` and ``line`` are the first one's."""

    def __init__(self, issues: Sequence[Issue]):
        self.issues = list(issues)
        first = self.issues[0] if self.issues else Issue("error", "invalid dossier (no details)")
        self.file = first.where.file if first.where else ""
        self.line = first.where.line if first.where else 0
        lines = [str(i) for i in self.issues]
        super().__init__(lines[0] if len(lines) == 1 else f"{len(lines)} dossier errors:\n  " + "\n  ".join(lines))


# ------------------------------------------------------------------------------------------- YAML with line numbers

class _Map(dict):
    """A YAML mapping that remembers its file, its line and the line of each key."""
    file = ""
    line = 0
    key_lines: Dict[Any, int] = {}


class _Seq(list):
    """A YAML sequence that remembers its file, its line and the line of each item."""
    file = ""
    line = 0
    item_lines: List[int] = []


def _yaml_load(text: str, file: str) -> Any:
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    def construct_map(loader, node):
        loader.flatten_mapping(node)
        m = _Map()
        m.file, m.line, m.key_lines = file, node.start_mark.line + 1, {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            try:
                hash(key)
            except TypeError:
                raise DossierError([Issue("bad-key", f"a key must be text, got a {'list' if isinstance(key, list) else 'mapping' if isinstance(key, dict) else type(key).__name__}",
                                          Where(file, key_node.start_mark.line + 1))]) from None
            if key in m:
                raise DossierError([Issue("duplicate-key", f"duplicate key {key!r}",
                                          Where(file, key_node.start_mark.line + 1))])
            m[key] = loader.construct_object(value_node, deep=True)
            m.key_lines[key] = key_node.start_mark.line + 1
        return m

    def construct_seq(loader, node):
        s = _Seq(loader.construct_object(child, deep=True) for child in node.value)
        s.file, s.line = file, node.start_mark.line + 1
        s.item_lines = [child.start_mark.line + 1 for child in node.value]
        return s

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_map)
    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, construct_seq)
    try:
        return yaml.load(text, Loader=Loader)  # noqa: S506 - a SafeLoader subclass
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        raise DossierError([Issue("yaml", f"invalid YAML: {exc.problem or exc}",
                                  Where(file, mark.line + 1 if mark else 0))]) from exc
    except yaml.YAMLError as exc:
        raise DossierError([Issue("yaml", f"invalid YAML: {exc}", Where(file))]) from exc


def _where(node: Any, key: Any = None, default_file: str = "") -> Where:
    file = getattr(node, "file", "") or default_file
    if key is not None and isinstance(node, _Map):
        return Where(file, node.key_lines.get(key, node.line))
    if isinstance(key, int) and isinstance(node, _Seq) and key < len(node.item_lines):
        return Where(file, node.item_lines[key])
    return Where(file, getattr(node, "line", 0))


# ------------------------------------------------------------------------------------------------- the parser

_Ref = Tuple[str, str, Where, str]   # (expected kind, id, where, context)


class _Parser:
    def __init__(self, base: Path, rel_to: Path):
        self.base = base            # paths in the dossier resolve against this directory
        self.rel_to = rel_to        # files are shown relative to this directory
        self.errors: List[Issue] = []
        self.findings: List[Issue] = []
        self.refs: List[_Ref] = []
        self.ids: Dict[str, Tuple[str, Where]] = {}
        self.loaded: List[Path] = []

    # -- reporting
    def error(self, where: Where, message: str, code: str = "invalid") -> None:
        self.errors.append(Issue(code, message, where, "error"))

    def warn(self, where: Where, message: str, code: str = "unknown-key") -> None:
        self.findings.append(Issue(code, message, where, "warning"))

    def show(self, path: Path) -> str:
        try:
            return os.path.relpath(path, self.rel_to)
        except ValueError:
            return str(path)

    # -- files
    def read(self, path: Path, where: Optional[Where]) -> Any:
        try:
            text = path.read_text()
        except OSError as exc:
            self.error(where or Where(self.show(path)), f"cannot read {self.show(path)}: {exc.strerror or exc}",
                       "missing-file")
            return None
        self.loaded.append(path)
        try:
            data = _yaml_load(text, self.show(path))
        except DossierError as exc:
            self.errors.extend(exc.issues)
            return None
        if data is None:
            at = where or Where(self.show(path), 1)
            self.error(at, f"{self.show(path)} is empty (no YAML document); write its content or remove the reference",
                       "empty-file")
        return data

    def expand(self, entry: str, where: Where) -> List[Path]:
        pattern = str(self.base / entry)
        if glob.has_magic(entry):
            found = sorted(Path(p) for p in glob.glob(pattern))
            if not found:
                self.error(where, f"{entry!r} matches no files", "missing-file")
            return found
        return [Path(pattern)]

    # -- typed field readers
    def mapping(self, node: Any, where: Where, what: str) -> Optional[_Map]:
        if isinstance(node, dict):
            return node if isinstance(node, _Map) else _plain_map(node, where)
        self.error(where, f"{what} must be a mapping, got {type(node).__name__}")
        return None

    def keys(self, m: _Map, known: Iterable[str], what: str) -> None:
        known = set(known)
        for key in m:
            if key not in known:
                self.warn(_where(m, key), f"unknown key {key!r} in {what} (known: {', '.join(sorted(known))})")

    def text(self, m: _Map, key: str, what: str, required: bool = False) -> str:
        value = m.get(key)
        if value is None:
            if required:
                self.error(_where(m, key), f"{what} needs {key!r}", "missing-field")
            return ""
        if isinstance(value, (dict, list)):
            self.error(_where(m, key), f"{what}.{key} must be text, got {type(value).__name__}")
            return ""
        return str(value)

    def ident(self, m: _Map, what: str, key: str = "id") -> str:
        value = m.get(key)
        if value is None:
            self.error(_where(m), f"{what} needs an {key!r}", "missing-id")
            return ""
        value = str(value)
        if not ID_RE.match(value):
            self.error(_where(m, key), f"bad id {value!r} in {what}: ids start with a letter and use letters, digits, "
                                       "'_', '-' or '.'", "bad-id")
            return ""
        return value

    def register(self, item_id: str, kind: str, where: Where) -> bool:
        if not item_id:
            return False
        if item_id in self.ids:
            other_kind, other = self.ids[item_id]
            self.error(where, f"id {item_id!r} is already used by the {other_kind} at {other}", "duplicate-id")
            return False
        self.ids[item_id] = (kind, where)
        return True

    def number(self, m: _Map, key: str, what: str, integer: bool = False) -> Optional[float]:
        value = m.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (integer and not isinstance(value, int)):
            self.error(_where(m, key), f"{what}.{key} must be {'an integer' if integer else 'a number'}, got {value!r}")
            return None
        return int(value) if integer else float(value)

    def flag(self, m: _Map, key: str, what: str, default: bool = False) -> bool:
        value = m.get(key, default)
        if not isinstance(value, bool):
            self.error(_where(m, key), f"{what}.{key} must be true or false, got {value!r}")
            return default
        return value

    def choice(self, m: _Map, key: str, allowed: Sequence[str], what: str, default: str = "") -> str:
        value = m.get(key)
        if value is None:
            return default
        if str(value) not in allowed:
            self.error(_where(m, key), f"{what}.{key} is {value!r}; one of: {', '.join(allowed)}", "bad-value")
            return default
        return str(value)

    def items(self, m: _Map, key: str, what: str) -> List[Tuple[Any, Where]]:
        value = m.get(key)
        if value is None:
            return []
        if not isinstance(value, list):
            self.error(_where(m, key), f"{what}.{key} must be a list, got {type(value).__name__}")
            return []
        return [(item, _where(value, i, m.file) if isinstance(value, _Seq) else _where(m, key))
                for i, item in enumerate(value)]

    def ref_list(self, m: _Map, key: str, kind: str, what: str, allow_single: bool = False) -> List[str]:
        value = m.get(key)
        if value is None:
            return []
        if allow_single and isinstance(value, str):
            value = [value]
            entries = [(value[0], _where(m, key))]
        else:
            entries = self.items(m, key, what)
        out = []
        for item, where in entries:
            if isinstance(item, (dict, list)) or item is None:
                self.error(where, f"{what}.{key} entries must be ids, got {type(item).__name__}")
                continue
            out.append(str(item))
            if kind:
                self.refs.append((kind, str(item), where, f"{what}.{key}"))
        return out

    def ref(self, m: _Map, key: str, kind: str, what: str) -> str:
        value = self.text(m, key, what)
        if value:
            self.refs.append((kind, value, _where(m, key), f"{what}.{key}"))
        return value

    def free_map(self, m: _Map, key: str, what: str) -> Dict[str, Any]:
        value = m.get(key)
        if value is None:
            return {}
        if not isinstance(value, dict):
            self.error(_where(m, key), f"{what}.{key} must be a mapping, got {type(value).__name__}")
            return {}
        return _strip(value)

    # -- items
    def source(self, m: _Map, key: str, what: str) -> Optional[Source]:
        value = m.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            value = _plain_map({"kind": value}, _where(m, key))
        node = self.mapping(value, _where(m, key), f"{what}.{key}")
        if node is None:
            return None
        self.keys(node, ("kind", "quote", "ref"), f"{what}.{key}")
        return Source(kind=self.choice(node, "kind", SOURCE_KINDS, f"{what}.{key}"),
                      quote=self.text(node, "quote", what), ref=self.text(node, "ref", what))

    def requirement(self, node: Any, where: Where) -> Optional[Requirement]:
        m = self.mapping(node, where, "requirement")
        if m is None:
            return None
        rid = self.ident(m, "requirement")
        what = f"requirement {rid or '?'}"
        self.keys(m, ("id", "text", "source", "verify_by", "parent", "rationale", "checks", "status"), what)
        req = Requirement(
            id=rid, text=self.text(m, "text", what, required=True), source=self.source(m, "source", what),
            verify_by=self.choice(m, "verify_by", VERIFY_BY, what), parent=self.ref(m, "parent", "requirement", what),
            rationale=self.text(m, "rationale", what), checks=self.ref_list(m, "checks", "", what),
            status=self.choice(m, "status", REQUIREMENT_STATUS, what), where=_where(m))
        return req if self.register(rid, "requirement", req.where) else None

    def alternatives(self, m: _Map, what: str) -> List[Alternative]:
        out = []
        for item, where in self.items(m, "alternatives", what):
            if isinstance(item, str):
                out.append(Alternative(option=item))
                continue
            a = self.mapping(item, where, f"{what}.alternatives[]")
            if a is None:
                continue
            self.keys(a, ("option", "rejected"), f"{what}.alternatives[]")
            out.append(Alternative(option=self.text(a, "option", f"{what}.alternatives[]", required=True),
                                   rejected=self.text(a, "rejected", what) if "rejected" in a else None))
        return out

    def decision(self, node: Any, where: Where, section: str = "", part: str = "") -> Optional[Decision]:
        m = self.mapping(node, where, "decision")
        if m is None:
            return None
        did = self.ident(m, "decision")
        what = f"decision {did or '?'}"
        nested = bool(section or part)
        known = ["id", "title", "decision", "why", "status", "date", "source", "alternatives", "consequences",
                 "confirmation", "superseded_by", "author"]
        if not nested:
            known += ["scope", "section", "part"]
        self.keys(m, known, what)
        d = Decision(
            id=did, title=self.text(m, "title", what), decision=self.text(m, "decision", what, required=True),
            why=self.text(m, "why", what), status=self.choice(m, "status", DECISION_STATUS, what, "decided"),
            date=self.text(m, "date", what), source=self.source(m, "source", what),
            alternatives=self.alternatives(m, what), consequences=self.text(m, "consequences", what),
            confirmation=self.text(m, "confirmation", what),
            superseded_by=self.ref(m, "superseded_by", "decision", what), author=self.text(m, "author", what),
            where=_where(m), nested=nested)
        if nested:
            d.scope, d.section, d.part = ("part" if part else "section"), section, part
        else:
            d.section = self.ref(m, "section", "section", what)
            d.part = self.ref(m, "part", "part", what)
            implied = "part" if d.part else "section" if d.section else "project"
            d.scope = self.choice(m, "scope", DECISION_SCOPES, what, implied)
            if d.scope != implied:
                self.error(_where(m, "scope"), f"{what} has scope {d.scope!r} but names "
                           + (f"part {d.part!r}" if d.part else f"section {d.section!r}" if d.section else "no target")
                           + "; a section scope needs `section:`, a part scope needs `part:`", "bad-scope")
        return d if self.register(did, "decision", d.where) else None

    def interface(self, node: Any, where: Where, section: str = "") -> Optional[Interface]:
        m = self.mapping(node, where, "interface")
        if m is None:
            return None
        iid = self.ident(m, "interface")
        what = f"interface {iid or '?'}"
        self.keys(m, ("id", "between", "kind", "datum", "loads", "fastened_by", "clearance", "owner",
                      "description"), what)
        between = self.ref_list(m, "between", "part_or_section", what)
        if len(between) != 2 or between[0] == between[1]:
            self.error(_where(m, "between"), f"{what} needs two different parties in `between`, got {between}",
                       "bad-interface")
        clearance = self.number(m, "clearance", what)
        if clearance is not None and clearance < 0:
            self.error(_where(m, "clearance"), f"{what}.clearance must be >= 0 mm")
        return Interface(id=iid, between=between, kind=self.choice(m, "kind", INTERFACE_KINDS, what),
                         datum=self.text(m, "datum", what), loads=self.free_map(m, "loads", what),
                         fastened_by=self.text(m, "fastened_by", what), clearance=clearance,
                         owner=self.ref(m, "owner", "part_or_section", what),
                         description=self.text(m, "description", what), section=section, where=_where(m))

    def material(self, m: _Map, what: str) -> Optional[Material]:
        value = m.get("material")
        if value is None:
            return None
        if isinstance(value, str):
            return Material(name=value)
        node = self.mapping(value, _where(m, "material"), f"{what}.material")
        if node is None:
            return None
        self.keys(node, ("name", "process", "print_axis", "wall_mm", "notes"), f"{what}.material")
        wall = self.number(node, "wall_mm", f"{what}.material")
        if wall is not None and wall <= 0:
            self.error(_where(node, "wall_mm"), f"{what}.material.wall_mm must be > 0")
        return Material(name=self.text(node, "name", what), process=self.text(node, "process", what),
                        print_axis=self.text(node, "print_axis", what), wall_mm=wall, notes=self.text(node, "notes", what))

    def part(self, node: Any, where: Where, section: str, file: str = "") -> Optional[PartCard]:
        m = self.mapping(node, where, "part card")
        if m is None:
            return None
        pid = self.ident(m, "part card")
        what = f"part {pid or '?'}"
        self.keys(m, ("id", "function", "interfaces", "loads", "material", "fasteners", "contains", "decisions",
                      "checks", "status", "author", "notes"), what)
        fasteners = []
        for item, w in self.items(m, "fasteners", what):
            f = self.mapping(item, w, f"{what}.fasteners[]")
            if f is None:
                continue
            fw = f"{what}.fasteners[]"
            self.keys(f, ("to", "screws", "qty", "via", "note"), fw)
            qty = self.number(f, "qty", fw, integer=True)
            if qty is not None and qty < 1:
                self.error(_where(f, "qty"), f"{fw}.qty must be >= 1")
            fasteners.append(FastenerUse(to=self.ref(f, "to", "part", fw), screws=self.text(f, "screws", fw, True),
                                         qty=qty, via=self.ref(f, "via", "interface", fw),
                                         note=self.text(f, "note", fw), where=_where(f)))
        contains = []
        for item, w in self.items(m, "contains", what):
            c = self.mapping(item, w, f"{what}.contains[]")
            if c is None:
                continue
            cw = f"{what}.contains[]"
            self.keys(c, ("what", "count", "cavity", "free"), cw)
            count = self.number(c, "count", cw, integer=True)
            if count is not None and count < 1:
                self.error(_where(c, "count"), f"{cw}.count must be >= 1")
            contains.append(Containment(what=self.ref(c, "what", "part", cw), count=count,
                                        cavity=self.text(c, "cavity", cw), free=self.flag(c, "free", cw),
                                        where=_where(c)))
        if not self.register(pid, "part", _where(m)):
            return None             # a duplicate: its nested decisions are not read, so they cannot cascade
        card = PartCard(
            id=pid, function=self.text(m, "function", what), interfaces=self.ref_list(m, "interfaces", "interface", what),
            loads=self.free_map(m, "loads", what), material=self.material(m, what), fasteners=fasteners,
            contains=contains, checks=self.ref_list(m, "checks", "", what),
            status=self.choice(m, "status", PART_STATUS, what, "draft"), author=self.text(m, "author", what),
            notes=self.text(m, "notes", what), section=section, file=file, where=_where(m))
        card.decisions = [d for item, w in self.items(m, "decisions", what)
                          if (d := self.decision(item, w, section=section, part=pid))]
        return card

    def section(self, node: Any, where: Where, file: str = "") -> Optional[Section]:
        m = self.mapping(node, where, "section")
        if m is None:
            return None
        sid = self.ident(m, "section")
        what = f"section {sid or '?'}"
        self.keys(m, ("id", "title", "purpose", "requirements", "interfaces", "parts", "decisions", "review",
                      "author", "notes"), what)
        if not self.register(sid, "section", _where(m)):
            return None
        sec = Section(id=sid, title=self.text(m, "title", what, required=True), purpose=self.text(m, "purpose", what),
                      requirements=self.ref_list(m, "requirements", "requirement", what),
                      review=self.free_map(m, "review", what), author=self.text(m, "author", what),
                      notes=self.text(m, "notes", what), file=file, where=_where(m))
        sec.interfaces = [i for item, w in self.items(m, "interfaces", what) if (i := self.interface(item, w, sid))]
        for item, w in self.items(m, "parts", what):
            if isinstance(item, str):
                for path in self.expand(item, w):
                    data = self.read(path, w)
                    rel = os.path.relpath(path, self.base)
                    if data is not None and (card := self.part(data, Where(self.show(path), 1), sid, file=rel)):
                        sec.parts.append(card)
            elif (card := self.part(item, w, sid)):
                sec.parts.append(card)
        sec.decisions = [d for item, w in self.items(m, "decisions", what) if (d := self.decision(item, w, section=sid))]
        return sec

    def step(self, node: Any, where: Where) -> Optional[AssemblyStep]:
        m = self.mapping(node, where, "assembly step")
        if m is None:
            return None
        order = self.number(m, "order", "assembly step", integer=True)
        what = f"assembly step {order if order is not None else '?'}"
        if order is None:
            self.error(_where(m), f"{what} needs an integer 'order'", "missing-field")
            return None
        self.keys(m, ("order", "fit", "onto", "direction", "tool", "fasteners", "access_check", "note"), what)
        direction = m.get("direction", "")
        if direction != "" and not _direction_ok(direction):
            self.error(_where(m, "direction"), f"{what}.direction is {direction!r}; use +X, -X, +Y, -Y, +Z, -Z or "
                                               "[x, y, z] (the way the part moves to its seat)", "bad-value")
        return AssemblyStep(order=int(order), fit=self.ref(m, "fit", "part", what),
                            onto=self.ref_list(m, "onto", "part", what, allow_single=True),
                            direction=list(direction) if isinstance(direction, list) else str(direction),
                            tool=self.text(m, "tool", what), fasteners=self.ref_list(m, "fasteners", "", what),
                            access_check=self.text(m, "access_check", what), note=self.text(m, "note", what),
                            where=_where(m))

    def gates(self, node: Any, where: Where) -> GateConfig:
        m = self.mapping(node, where, "gates")
        if m is None:
            return GateConfig()
        known = ("touch_tol_mm", "grounded", "free_parts", "intended_overlaps", "ignore_pairs", "strict_interfaces",
                 "motion_samples")
        passed_on = ("tools", "fasteners")      # read by the fastener and assembly gates from GateConfig.extra
        cfg = GateConfig()
        tol = self.number(m, "touch_tol_mm", "gates")
        if tol is not None:
            cfg.touch_tol_mm = tol
        samples = self.number(m, "motion_samples", "gates", integer=True)
        if samples is not None:
            cfg.motion_samples = int(samples)
        cfg.strict_interfaces = self.flag(m, "strict_interfaces", "gates")
        cfg.grounded = self.ref_list(m, "grounded", "part", "gates")
        for item, w in self.items(m, "free_parts", "gates"):
            if isinstance(item, str):
                self.error(w, f"gates.free_parts: {item!r} needs a reason: write {{part: {item}, reason: ...}} "
                              "(a part allowed to float is an explained exclusion)", "missing-reason")
                self.refs.append(("part", item, w, "gates.free_parts"))
            elif (f := self.mapping(item, w, "gates.free_parts[]")) is not None:
                self.keys(f, ("part", "reason"), "gates.free_parts[]")
                reason = self.text(f, "reason", "gates.free_parts[]").strip()
                if not reason:
                    self.error(_where(f), "gates.free_parts[] needs a reason", "missing-reason")
                cfg.free_parts.append(FreePart(part=self.ref(f, "part", "part", "gates.free_parts[]"), reason=reason))
        for key in ("intended_overlaps", "ignore_pairs"):
            for item, w in self.items(m, key, "gates"):
                p = self.mapping(item, w, f"gates.{key}[]")
                if p is None:
                    continue
                self.keys(p, ("parts", "reason"), f"gates.{key}[]")
                # a part, an instance of one (ball#3), or a fastener name or instance (screw_0, m3:lid-base#1):
                # names the YAML does not know are the build's, and the lint checks them against its record
                parts = self.ref_list(p, "parts", "pair_party", f"gates.{key}[]")
                if len(parts) != 2:
                    self.error(_where(p, "parts"), f"gates.{key}[].parts must name two parts, got {parts}")
                    continue
                if parts[0] == parts[1]:
                    self.error(_where(p, "parts"), f"gates.{key}[].parts names {parts[0]!r} twice: a pair is two "
                                                   "different parts, instances or fasteners")
                    continue
                reason = self.text(p, "reason", f"gates.{key}[]").strip()
                if not reason:
                    self.error(_where(p), f"gates.{key}[] needs a reason (an explained exclusion)", "missing-reason")
                getattr(cfg, key).append(PairExemption(parts=(parts[0], parts[1]), reason=reason, where=_where(p)))
        for key in m:
            if key not in known:
                cfg.extra[key] = _strip(m[key])
        self.keys(m, known + passed_on, "gates")
        return cfg


def _direction_ok(value: Any) -> bool:
    if isinstance(value, str):
        return bool(DIRECTION_RE.match(value))
    if isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                           for v in value):
        return any(v != 0 for v in value)
    return False


def _plain_map(data: Dict[str, Any], where: Where) -> _Map:
    m = _Map(data)
    m.file, m.line, m.key_lines = where.file, where.line, {}
    return m


def _strip(value: Any) -> Any:
    """Plain dicts and lists (no line bookkeeping) for free-form fields."""
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


# ---------------------------------------------------------------------------------------------- entry points

def load_dossier(path: PathLike, strict: bool = True, root: Optional[PathLike] = None) -> Dossier:
    """Load ``dossier/project.yaml`` (and every file it names) into a resolved ``Dossier``.

    ``root`` is the directory file names are shown relative to (default: the parent of the dossier directory,
    which is the project root in the standard layout).
    """
    path = Path(path).resolve()
    p = _Parser(base=path.parent, rel_to=Path(root).resolve() if root else path.parent.parent)
    dossier = Dossier(file=p.show(path))
    data = p.read(path, None)
    if data is None:
        raise DossierError(p.errors)
    top = p.mapping(data, Where(p.show(path), 1), "dossier project file")
    if top is None:
        raise DossierError(p.errors)
    p.keys(top, ("title", "requirements", "sections", "interfaces", "decisions", "assembly", "gates"), "project.yaml")
    dossier.title = p.text(top, "title", "project")

    for item, w in p.items(top, "requirements", "project"):
        if (req := p.requirement(item, w)):
            dossier.requirements[req.id] = req

    for item, w in p.items(top, "sections", "project"):
        if isinstance(item, str):
            for spath in p.expand(item, w):
                sdata = p.read(spath, w)
                if sdata is not None and (sec := p.section(sdata, Where(p.show(spath), 1), file=p.show(spath))):
                    dossier.sections[sec.id] = sec
        elif (sec := p.section(item, w)):
            dossier.sections[sec.id] = sec

    project_interfaces = [i for item, w in p.items(top, "interfaces", "project") if (i := p.interface(item, w))]

    decisions_node = top.get("decisions")
    if isinstance(decisions_node, str):
        w = _where(top, "decisions")
        ddata = p.read(path.parent / decisions_node, w)
        if isinstance(ddata, dict) and "decisions" in ddata:
            p.keys(ddata, ("decisions",), decisions_node)
            ddata = ddata["decisions"]
        if ddata is not None and not isinstance(ddata, list):
            p.error(w, f"{decisions_node} must hold a list of decisions (or `decisions: [...]`)")
            ddata = None
        top_decisions = []
        for i, item in enumerate(ddata or []):
            dw = _where(ddata, i)
            if (d := p.decision(item, dw)):
                top_decisions.append(d)
    else:
        top_decisions = [d for item, w in p.items(top, "decisions", "project") if (d := p.decision(item, w))]

    assembly_node = top.get("assembly")
    if isinstance(assembly_node, dict):
        am = p.mapping(assembly_node, _where(top, "assembly"), "assembly")
        p.keys(am, ("steps",), "assembly")
        steps = p.items(am, "steps", "assembly")
    elif assembly_node is not None:
        p.error(_where(top, "assembly"), "assembly must be a mapping with `steps: [...]`")
        steps = []
    else:
        steps = []
    seen_orders: Dict[int, Where] = {}
    for item, w in steps:
        if (step := p.step(item, w)):
            if step.order in seen_orders:
                p.error(step.where, f"assembly step order {step.order} is already used at {seen_orders[step.order]}",
                        "duplicate-id")
                continue
            seen_orders[step.order] = step.where
            dossier.assembly.append(step)
    dossier.assembly.sort(key=lambda s: s.order)

    if "gates" in top:
        dossier.gates = p.gates(top["gates"], _where(top, "gates"))

    # flatten: parts, decisions, interfaces
    for sec in dossier.sections.values():
        for card in sec.parts:
            dossier.parts[card.id] = card
    for d in top_decisions:
        dossier.decisions[d.id] = d
    for sec in dossier.sections.values():
        for d in sec.decisions + [d for c in sec.parts for d in c.decisions]:
            dossier.decisions[d.id] = d
    _merge_interfaces(p, dossier, project_interfaces)

    _resolve(p, dossier)
    dossier.findings = p.findings
    if p.errors:
        if strict:
            raise DossierError(p.errors)
        dossier.errors = p.errors
    return dossier


def _merge_interfaces(p: _Parser, dossier: Dossier, project_interfaces: List[Interface]) -> None:
    """An interface may be declared by both sections it joins (plan §5.4); the owner's declaration is the
    reference and a difference between the two is reported."""
    decls: Dict[str, List[Interface]] = {}
    for i in project_interfaces + [i for s in dossier.sections.values() for i in s.interfaces]:
        if not i.id:
            continue
        others = decls.setdefault(i.id, [])
        if any(o.section == i.section for o in others):
            first = next(o for o in others if o.section == i.section)
            p.error(i.where, f"interface {i.id!r} is declared twice in "
                             f"{'section ' + i.section if i.section else 'project.yaml'} (first at {first.where})",
                    "duplicate-id")
            continue
        others.append(i)
    for iid, items in decls.items():
        if not p.register(iid, "interface", items[0].where):
            continue
        primary = next((i for i in items if i.owner and i.section == i.owner), items[0])
        dossier.interfaces[iid] = primary
        dossier.interface_declarations[iid] = items
        for other in items:
            if other is primary:
                continue
            diffs = [f for f in ("between", "kind", "datum", "clearance", "owner", "fastened_by")
                     if getattr(other, f) and getattr(primary, f) and
                     (sorted(getattr(other, f)) if f == "between" else getattr(other, f))
                     != (sorted(getattr(primary, f)) if f == "between" else getattr(primary, f))]
            if diffs:
                p.warn(other.where, f"interface {iid!r} is declared differently here and at {primary.where}: "
                                    f"{', '.join(diffs)} differ", "interface-conflict")


def _resolve(p: _Parser, dossier: Dossier) -> None:
    if any(e.code in ("yaml", "duplicate-key", "bad-key", "missing-file", "empty-file") for e in p.errors):
        return      # ids from the file that failed to load would all report as unknown; fix the file first
    tables: Dict[str, Callable[[str], bool]] = {
        "requirement": lambda i: i in dossier.requirements,
        "section": lambda i: i in dossier.sections,
        "part": lambda i: i in dossier.parts,
        "part_or_section": lambda i: i in dossier.parts or i in dossier.sections,
        "interface": lambda i: i in dossier.interfaces,
        "decision": lambda i: i in dossier.decisions,
        # a dossier part or an instance of one; any other name that is not another kind of dossier id is left to
        # the lint, which resolves fastener names and instance keys against the build's geometry record
        "pair_party": lambda i: _owner(i) in dossier.parts or dossier.kind_of(_owner(i)) is None,
    }
    expected_names = {"pair_party": "part, part instance or fastener"}
    for kind, item_id, where, context in p.refs:
        if not item_id or tables[kind](item_id):
            continue
        if kind == "pair_party":
            item_id = _owner(item_id)
        actual = dossier.kind_of(item_id)
        expected = expected_names.get(kind) or kind.replace("_or_", " or ")
        hint = f" (it is a {actual})" if actual else ""
        p.error(where, f"{context} names {item_id!r}, which is not a {expected} in this dossier{hint}", "unknown-id")


def _owner(key: str) -> str:
    """The part or fastener name of an instance key (``ball#3`` -> ``ball``)."""
    base, _, idx = key.rpartition("#")
    return base if base and idx.isdigit() else key


def load_project_dossier(project: Any, strict: bool = True) -> Optional[Dossier]:
    """The dossier named by ``cad: dossier:`` in a project's ``cad-agent.yaml``, or None when it has none."""
    path = getattr(project, "dossier", None)
    if not path:
        return None
    return load_dossier(path, strict=strict, root=project.root)


def dump_yaml(data: Any) -> str:
    """YAML for a ``to_dict()`` result, keys in schema order."""
    import yaml
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120)
