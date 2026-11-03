"""The reference registry (#118): every outside source a cad-agent rule, check or number relies on, by a stable id.

The registry is ``research/references.yaml`` in a cad-agent checkout. Code cites a source by its id, and the registry
says who wrote it, where it is, what was read and when, and what cad-agent may do with it: sources are summarised and
cited, never copied, and paid documents are cited by number and title only. Nothing here vendors a source.

Where code cites by id (``citations()`` finds them all):

* a module-level ``SRC`` or ``SOURCES`` dict whose keys are ids (``cadagent.formulas``, ``cadagent.mechanical.inserts``,
  ``cadagent.mechanical.printed_joints``), and ``cite("<id>", ...)`` calls. A table keyed by anything else takes
  another name (``cadagent.mechanical.bearings.WHERE`` is keyed by check);
* a module-level ``FDM_MATERIALS`` dict whose values are tuples ending in an id (``cadagent.manufacturing.process``);
* ``Material(..., source="<id>")`` (``cadagent.simulation.fea``);
* ``research/process-profiles.yaml``: each rule's, formula's and shop table's ``source``, and each dataset's ``cites``;
* ``[ref:<id>]`` tags in Markdown, YAML and Python text (a malformed tag is reported, not skipped).

A key resolves to one of three kinds of entry:

* ``sources``: read, with an https URL or an ISBN. An entry may list ``aliases``, the shorter keys a module uses for
  the same document (``covestro`` and ``covestro-friction`` both cite ``covestro-snapfit``); the module's own text keeps
  the page or table;
* ``unverified``: named, but not yet read or not yet found online, with the reason. Code that cites one is a known
  gap: ``check()`` warns about it, and ``tests/review/test_references.py`` pins how many there are, a number that only falls;
* ``uncited``: a key that is not an outside source, said openly: ``general`` (common engineering knowledge),
  ``judgement`` (a stated judgement of the module) or ``internal`` (another cad-agent module, with what it cites).

``lookup(key)`` gives the entry, ``citation(key)`` a one-line citation, ``check()`` every problem in the registry and
in the code that cites it. From a shell::

    python -m cadagent.review.references covestro roark     # print the citations
    python -m cadagent.review.references --check            # exit 1 on a problem

Schema 2 (#323) adds shards: ``research/references/*.yaml`` beside the core file, each ``schema: 2`` with a
``sources`` list of at most ``SHARD_LIMIT`` records. One id space covers the core file and every shard; ``lookup()``
does not care which file an id lives in. A schema-2 record says what it is (``kind``), what its source's licence
allows (``licence``, ``reuse``), how far it has been checked (``evidence.class``, a ladder from ``snippet-only`` to
``measured``) and, for an open project, an objective ``assessment``. Its fixed vocabularies live in
``research/references/vocab.yaml``; its ``areas`` are slugs of ``docs/areas.yaml``. A shard record below ``read`` is
*catalogued*: it may be listed and linked, but a rule, a check or a page's rule line may not cite it (``check()``
reports that, and warns on a ``[ref:]`` to one in ``research/``). A shard record with ``extends: true`` adds schema-2
fields to the core entry of the same id (lists are united, the core's other fields win). ``confidence()`` derives
#143's level from the evidence, so a stored ``confidence`` cannot drift from it. The folder's README has the map.

A citation says where a rule came from. It does not make the rule right for a given part: CAD and simulation do not
prove fit or strength, and a limit taken from a data sheet holds only for the conditions the sheet states.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "research" / "references.yaml"
PROCESS_PROFILES = ROOT / "research" / "process-profiles.yaml"
VOCAB = "vocab.yaml"                  # in the shard folder; every other *.yaml there is a shard

ACCESS = ("free", "free-registration", "paid", "print")
UNCITED_KINDS = ("general", "judgement", "internal")
# `source`: read (every core entry, and a shard record at evidence class `read` or above); `catalogued`: a shard
# record below `read`, listed and linked but never cited by a rule, check or page; `unverified` and `uncited` as before.
KINDS = ("source", "catalogued", "unverified", "uncited")

# ---- schema 2 (#323)
SHARD_LIMIT = 150                     # records per shard; a shard over it is split by topic slug
SHARD_BYTES = 150_000                 # and bytes per shard: one fetch of an agent's context, at most ~40k tokens
# The promotion ladder, lowest first. vocab.yaml lists the same classes in the same order (check() compares them).
LADDER = ("snippet-only", "read", "verified-at-source", "encoded", "measured")
LEVELS = {"high": 0.9, "medium": 0.7, "low": 0.4, "unknown": None}       # #143; vocab.yaml's `confidence`
PRIMARY = ("primary", "independent-tested")           # authorities that count as a primary source
# Where a [ref:] to a catalogued record is only a warning (a survey may list what it has not read); anywhere else,
# and in any code table or profile rule, it is a problem.
CATALOGUED_TAG_OK = ("research/",)
# Record fields a shard may carry. A typo elsewhere would silently drop a fact, so check() reports any other key.
FIELDS = ("id", "extends", "kind", "category", "title", "authors", "org", "year", "url", "isbn", "mirrors", "access",
          "terms", "licence", "reuse", "areas", "processes", "process_groups", "domains", "evidence", "confidence",
          "verified", "archive", "used_for", "rules", "checks", "claims", "summary", "assessment", "projects",
          "aliases", "upstream")
# value field -> the vocab.yaml vocabulary it is drawn from
VOCAB_FIELDS = {("kind",): "kind", ("category",): "category", ("licence", "class"): "licence_class",
                ("reuse", "text"): "reuse_text", ("reuse", "geometry"): "reuse_geometry",
                ("evidence", "class"): "evidence_class", ("evidence", "numbers"): "numbers",
                ("evidence", "tested"): "tested", ("evidence", "authority"): "authority",
                ("assessment", "built"): "built", ("assessment", "supply"): "supply", ("assessment", "cost"): "cost",
                ("assessment", "make"): "make", ("assessment", "docs"): "docs", ("assessment", "activity"): "activity",
                ("assessment", "role"): "role", ("assessment", "cad", "seen"): "cad_seen",
                ("assessment", "assessed", "from"): "assessed_from", ("archive", "kind"): "archive_kind"}
LIST_FIELDS = {"processes": "process", "process_groups": "process_group", "domains": "domain"}
VOCABULARIES = tuple(sorted({*VOCAB_FIELDS.values(), *LIST_FIELDS.values(), "claim_status", "answer", "confidence",
                             "study_only"}))
CHECK_NAME = re.compile(r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+")   # inserts.check_joint
SHA256 = re.compile(r"[0-9a-f]{64}")
# What `terms` must say: that the source is cited and not copied or passed on, or that its open licence lets it be
# vendored or adopted with attribution (code, never a paid document).
NOT_COPIED = ("never copied", "not copied", "not redistributed", "by number and title only")
OPEN_LICENCE = "with attribution"
KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TAG = re.compile(r"\[ref:([^\]\n]*)\]")
PLACEHOLDER = re.compile(r"<[^>]*>")   # "[ref:<id>]" in prose explains the syntax; it cites nothing
TABLES = ("SRC", "SOURCES")         # module-level dicts whose keys are ids
ROW_TABLES = ("FDM_MATERIALS",)     # module-level dicts whose values are tuples that end in an id
TAG_FOLDERS = ("docs", "lessons", "research", "skills", "src", "agents", "tools", "examples", "web")
TAG_SUFFIXES = (".md", ".py", ".yaml", ".yml")
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)   # libyaml when PyYAML has it: the same safe loader, ~9x faster


def _yaml(text: str) -> Any:
    """``yaml.safe_load``, through libyaml when it is built in (the registry is read on every check)."""
    return yaml.load(text, Loader=_LOADER)  # noqa: S506 - a safe loader, never yaml.Loader


@dataclass(frozen=True)
class Reference:
    """One registry entry. ``kind`` is ``source``, ``catalogued``, ``unverified`` or ``uncited``; ``data`` is the entry
    as written (a core entry with a shard's ``extends`` merged in); ``file`` is the repo-relative file it lives in."""
    id: str
    kind: str
    data: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
    file: str = field(default="", compare=False)

    def __getitem__(self, name: str) -> Any:
        return self.data[name]

    def get(self, name: str, default: Any = None) -> Any:
        return self.data.get(name, default)

    @property
    def title(self) -> str:
        return self.data.get("title") or ""

    @property
    def credit(self) -> str:
        """Who to credit: the named people, else the organisation."""
        authors = [a for a in self.data.get("authors") or [] if a]
        if len(authors) > 3:
            return f"{authors[0]} et al."
        return ", ".join(authors) or self.data.get("org") or ""

    @property
    def link(self) -> str:
        """The URL, else ``ISBN <isbn>``, else ''."""
        if self.data.get("url"):
            return self.data["url"]
        return f"ISBN {self.data['isbn']}" if self.data.get("isbn") else ""

    def citation(self) -> str:
        """One line: who, title, year, link. An uncited key says what it is instead."""
        if self.kind == "uncited":
            return f"not an outside source ({self.data.get('kind')}): {' '.join(str(self.data.get('note', '')).split())}"
        year = self.data.get("year")
        parts = [self.credit, self.title, str(year) if year else "n.d."]
        if self.data.get("org") and self.data.get("authors"):
            parts.insert(2, self.data["org"])
        text = ", ".join(p for p in parts if p)
        if self.link:
            text += f": {self.link}"
        return text + {"unverified": " (unverified)", "catalogued": f" ({self.evidence_class})"}.get(self.kind, "")

    @property
    def evidence_class(self) -> Optional[str]:
        """The rung of the ladder (``LADDER``): ``evidence.class`` as written, else ``read`` for a core source (its
        dated ``verified`` note is the reading), else None (unverified and uncited keys are not on the ladder)."""
        ev = self.data.get("evidence")
        if isinstance(ev, dict) and ev.get("class"):
            return ev["class"]
        return "read" if self.kind == "source" else None


@dataclass(frozen=True)
class Citation:
    """One place that cites a key: ``path`` (repo-relative), ``line`` and how (``table``, ``cite``, ``material``,
    ``process-profile``, ``tag``)."""
    key: str
    path: str
    line: int
    how: str

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class Shard:
    """One schema-2 shard file as read: its repo-relative ``file``, its data and its size in bytes."""
    file: str
    data: Dict[str, Any] = field(compare=False, repr=False)
    size: int = 0

    @property
    def records(self) -> List[Any]:
        items = self.data.get("sources") if isinstance(self.data, dict) else None
        return items if isinstance(items, list) else []


class Registry:
    """The registry as loaded: entries by id, aliases to ids, and the raw data.

    ``data`` is the core file (``research/references.yaml``); ``shards`` the schema-2 files beside it and ``vocab``
    their vocabularies (``research/references/vocab.yaml``). One id space covers them all."""

    def __init__(self, data: Dict[str, Any], path: Optional[Path] = None, shards: Sequence[Shard] = (),
                 vocab: Optional[Dict[str, Any]] = None, core_file: str = "research/references.yaml"):
        self.data = data
        self.path = path
        self.shards = list(shards)
        self.vocab = vocab
        self.core_file = core_file
        self.entries: Dict[str, Reference] = {}
        self.aliases: Dict[str, str] = {}
        self._duplicates: List[str] = []
        self._overlays: Dict[str, str] = {}               # id -> the shard that extends it
        self._load_problems: List[str] = []
        for section, kind in (("sources", "source"), ("unverified", "unverified"), ("uncited", "uncited")):
            for item in data.get(section) or []:
                rid = item.get("id") if isinstance(item, dict) else None
                if not isinstance(rid, str):
                    continue
                if rid in self.entries:
                    self._duplicates.append(rid)
                self.entries[rid] = Reference(rid, kind, item, core_file)
        core = set(self.entries)
        for shard in self.shards:
            for item in shard.records:
                rid = item.get("id") if isinstance(item, dict) else None
                if not isinstance(rid, str):
                    self._load_problems.append(f"{shard.file}: a record without a string id: {str(item)[:60]!r}")
                    continue
                if item.get("extends") is True:
                    self._extend(rid, item, shard, core)
                    continue
                if rid in self.entries:
                    self._duplicates.append(rid)
                    self._load_problems.append(f"{rid}: in {shard.file} and in {self.entries[rid].file}; one id, one "
                                               "record (to add fields to a core entry, write `extends: true`)")
                cls = (item.get("evidence") or {}).get("class") if isinstance(item.get("evidence"), dict) else None
                kind = "source" if cls in LADDER[1:] else "catalogued"
                self.entries[rid] = Reference(rid, kind, item, shard.file)
        # aliases after every id, so an alias that names an entry is caught wherever either is written
        for ref in self.entries.values():
            aliases = ref.data.get("aliases") or []
            for alias in aliases if isinstance(aliases, list) else []:      # a string is reported by problems()
                if not isinstance(alias, str):
                    continue
                if alias in self.aliases or alias in self.entries:
                    self._duplicates.append(alias)
                    continue
                self.aliases[alias] = ref.id

    def _extend(self, rid: str, item: Dict[str, Any], shard: Shard, core: set) -> None:
        """Merge a shard's ``extends: true`` record into the core entry of the same id: lists are united in order,
        fields the core lacks are added, and a field both set differently keeps the core's value (and is reported)."""
        if rid not in core:
            self._load_problems.append(f"{rid}: {shard.file} extends it, but research/references.yaml has no such "
                                       "entry (drop `extends: true` to make it a record of its own)")
            return
        if self.entries[rid].kind != "source":
            self._load_problems.append(f"{rid}: {shard.file} extends it, but it is {self.entries[rid].kind} in "
                                       "research/references.yaml; only a read source (under `sources:`) takes "
                                       "schema-2 fields: read it and move it up first")
            return
        if rid in self._overlays:
            self._duplicates.append(rid)
            self._load_problems.append(f"{rid}: extended twice, in {self._overlays[rid]} and {shard.file}")
            return
        self._overlays[rid] = shard.file
        base = self.entries[rid]
        merged = dict(base.data)
        for key, value in item.items():
            if key in ("id", "extends"):
                continue
            have = merged.get(key)
            if key not in merged or have in (None, "", [], {}):
                merged[key] = value
            elif isinstance(have, list) and isinstance(value, list):
                merged[key] = have + [v for v in value if v not in have]
            elif have != value:
                self._load_problems.append(f"{rid}: {shard.file} sets {key} to {str(value)[:60]!r}, but the core "
                                           f"entry says {str(have)[:60]!r}; an extension adds fields, it does not "
                                           "change them")
        self.entries[rid] = Reference(rid, base.kind, merged, base.file)

    def __contains__(self, key: str) -> bool:
        return key in self.entries or key in self.aliases

    def __len__(self) -> int:
        return len(self.entries)

    def of_kind(self, kind: str) -> List[Reference]:
        return [r for r in self.entries.values() if r.kind == kind]

    def resolve(self, key: str) -> Reference:
        """The entry a key names, by id or alias. Unknown keys raise KeyError with the nearest ids."""
        rid = key if key in self.entries else self.aliases.get(key, key)
        if rid in self.entries:
            return self.entries[rid]
        near = difflib.get_close_matches(key, list(self.entries) + list(self.aliases), n=3)
        raise KeyError(f"{key!r} is not in {self.path or 'the registry'}" + (f"; did you mean {', '.join(near)}?" if near else ""))

    def problems(self, root: Path = ROOT, today: Optional[dt.date] = None) -> List[str]:
        """Every way an entry is malformed: missing fields, bad ids, links, dates, terms or paths; and for schema 2,
        shard sizes, vocabularies, area slugs, licence and reuse rules, the evidence ladder and derived confidence."""
        today = today or dt.date.today()
        out = [f"{k}: the id or alias is used twice" for k in sorted(set(self._duplicates))]
        out += self._load_problems
        if self.data.get("schema") != 1:
            out.append(f"schema is {self.data.get('schema')!r}, not 1")
        for key in list(self.entries) + list(self.aliases):
            if not KEY.fullmatch(key):
                out.append(f"{key}: not a kebab-case key")
        out += shard_problems(self.shards)
        ctx = _Schema2(self, Path(root))
        out += ctx.vocab_problems()
        for ref in self.entries.values():
            out += [f"{ref.id}: {p}" for p in _entry_problems(ref, self, root, today)]
        for shard in self.shards:
            for item in shard.records:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    out += [f"{item['id']}: {p}" for p in ctx.record_problems(item, shard.file)]
        for ref in self.entries.values():                 # a core entry may carry schema-2 fields too (or merged in)
            if ref.file == self.core_file and ref.kind == "source" and _has_schema2(ref.data):
                out += [f"{ref.id}: {p}" for p in ctx.record_problems(ref.data, ref.file, core=True)]
            if ref.kind in ("source", "catalogued") and isinstance(ref.data.get("evidence"), dict):
                out += [f"{ref.id}: {p}" for p in ctx.ladder_problems(ref)]
        return list(dict.fromkeys(out))      # an extension's fields are checked as written and as merged: once each


def shard_problems(shards: Sequence[Shard]) -> List[str]:
    """A shard's own rules: kebab-case name, ``schema: 2``, a ``sources`` list, and at most ``SHARD_LIMIT`` records
    and ``SHARD_BYTES`` bytes."""
    out = []
    for shard in shards:
        name = Path(shard.file).stem
        if not KEY.fullmatch(name):
            out.append(f"{shard.file}: a shard's file name is a kebab-case slug")
        if not isinstance(shard.data, dict):
            out.append(f"{shard.file}: not a mapping with `schema: 2` and `sources:`")
            continue
        if shard.data.get("schema") != 2:
            out.append(f"{shard.file}: schema is {shard.data.get('schema')!r}, not 2")
        if not isinstance(shard.data.get("sources"), list):
            out.append(f"{shard.file}: no `sources:` list")
        extra = sorted(set(shard.data) - {"schema", "title", "note", "sources"})
        if extra:
            out.append(f"{shard.file}: unknown top-level keys {extra} (a shard has schema, title, note, sources)")
        n = len(shard.records)
        if n > SHARD_LIMIT or shard.size > SHARD_BYTES:
            out.append(f"{shard.file}: {n} records, {shard.size:,} bytes, over the shard limit of {SHARD_LIMIT} "
                       f"records or {SHARD_BYTES:,} bytes: split by topic slug (one shard per topic, named "
                       f"<shard>-<topic>.yaml)")
    return out


def _has_schema2(d: Dict[str, Any]) -> bool:
    return any(k in d for k in ("kind", "licence", "reuse", "evidence", "assessment", "claims", "confidence",
                                "processes", "process_groups", "domains", "archive", "health", "projects"))


def _get(d: Any, path: Tuple[str, ...]) -> Any:
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def load_tree(path: Path) -> Dict[str, Any]:
    """The slugs records may use from ``docs/areas.yaml``: ``areas`` (area slug -> its domain), ``topics`` (topic slug
    -> its area), ``projects`` (keys of the projects table). Empty when the file is missing."""
    out: Dict[str, Any] = {"areas": {}, "topics": {}, "projects": set()}
    if not Path(path).is_file():
        return out
    tree = _yaml(Path(path).read_text(encoding="utf-8")) or {}
    out["projects"] = set(tree.get("projects") or {})
    for dom in tree.get("domains") or []:
        for area in dom.get("areas") or []:
            out["areas"][area["slug"]] = dom["slug"]
            for topic in area.get("topics") or []:
                out["topics"][topic["slug"]] = area["slug"]
    return out


def area_of(slug: str, tree: Dict[str, Any]) -> Optional[str]:
    """The area slug a record's ``areas`` entry places it in: an area itself, a topic's area, or ``area/topic``;
    None when the tree has no such slug."""
    if "/" in slug:
        area, topic = slug.split("/", 1)
        return area if tree["topics"].get(topic) == area else None
    if slug in tree["areas"]:
        return slug
    return tree["topics"].get(slug)


class _Schema2:
    """The schema-2 checks of one registry against its vocabularies and the topic tree of ``root``."""

    def __init__(self, reg: Registry, root: Path):
        self.reg, self.root = reg, root
        self.vocab = reg.vocab if isinstance(reg.vocab, dict) else {}
        self.tree = load_tree(root / "docs" / "areas.yaml")
        self._rules: Optional[set] = None

    def words(self, name: str) -> Dict[str, Any]:
        v = self.vocab.get(name)
        return v if isinstance(v, dict) else {}

    def vocab_problems(self) -> List[str]:
        if self.reg.vocab is None:
            needs = self.reg.shards or any(_has_schema2(r.data) for r in self.reg.of_kind("source"))
            return [f"research/references/{VOCAB} is missing: schema-2 records are checked against it"] if needs else []
        if not isinstance(self.reg.vocab, dict):
            return [f"{VOCAB}: not a mapping of vocabularies"]
        out = []
        if self.vocab.get("schema") != 2:
            out.append(f"{VOCAB}: schema is {self.vocab.get('schema')!r}, not 2")
        for name in VOCABULARIES:
            if name not in self.vocab:
                out.append(f"{VOCAB}: no `{name}` vocabulary")
        if tuple(self.words("evidence_class")) != LADDER:
            out.append(f"{VOCAB}: evidence_class lists {list(self.words('evidence_class'))}, but the code's ladder is "
                       f"{list(LADDER)}: change both together")
        if set(self.words("confidence")) != set(LEVELS) or any(
                (self.words("confidence")[k] or {}).get("estimate") != LEVELS[k] for k in LEVELS
                if k in self.words("confidence")):
            out.append(f"{VOCAB}: confidence levels and estimates must be {LEVELS}")
        study = self.vocab.get("study_only")
        if not isinstance(study, list) or not set(study) <= set(self.words("licence_class")):
            out.append(f"{VOCAB}: study_only must list licence classes")
        for slug, proc in self.words("process").items():
            if not isinstance(proc, dict) or proc.get("group") not in self.words("process_group"):
                out.append(f"{VOCAB}: process {slug} names no process_group")
        return out

    def _in(self, name: str, value: Any, field_name: str) -> List[str]:
        words = self.words(name)
        if isinstance(value, bool):          # YAML 1.1 reads an unquoted yes/no/on/off as a boolean
            return [f"{field_name} is the YAML boolean {value}: quote the word (\"yes\", \"no\")"]
        if value in words:
            return []
        near = difflib.get_close_matches(str(value), [str(w) for w in words], n=1)
        return [f"{field_name} {value!r} is not in vocab.yaml `{name}`" + (f" (did you mean {near[0]!r}?)" if near else
                                                                           f" ({', '.join(map(str, words))})")]

    def rule_ids(self) -> set:
        if self._rules is None:
            pp = self.root / "research" / "process-profiles.yaml"
            data = _yaml(pp.read_text(encoding="utf-8")) or {} if pp.is_file() else {}
            self._rules = {r.get("id") for r in data.get("rules") or [] if isinstance(r, dict)}
        return self._rules

    def record_problems(self, d: Dict[str, Any], file: str, core: bool = False) -> List[str]:
        """Problems of one schema-2 record. A shard's own record (not an extension, not a core entry) must also say
        its kind, licence class and evidence class, and place itself in the tree."""
        out: List[str] = []
        own = not core and d.get("extends") is not True
        if not core:
            extra = sorted(set(d) - set(FIELDS))
            if extra:
                out.append(f"unknown fields {extra} in {file} (a typo drops a fact; the fields are listed in "
                           "research/references/README.md)")
        if "health" in d:
            out.append("`health` is not kept in git: raw link health lives in the checker's artifacts and the site "
                       "JSON, and only evidence-class changes land here (#323)")
        if "extends" in d and d["extends"] is not True:
            out.append("extends must be `true` (it adds fields to the core entry of the same id) or absent")
        if own:
            for path in (("kind",), ("licence", "class"), ("evidence", "class")):
                if _get(d, path) in (None, ""):
                    out.append(f"no {'.'.join(path)} (a schema-2 record says what it is, its licence class and its "
                               "evidence class)")
            if not isinstance(_get(d, ("licence", "read")), bool):
                out.append("licence.read must be true or false: true only when the licence text itself was read")
            if not d.get("areas"):
                out.append("no areas: place the record in docs/areas.yaml (an area or topic slug)")
        for path, name in VOCAB_FIELDS.items():
            value = _get(d, path)
            if value not in (None, ""):
                out += self._in(name, value, ".".join(path))
        for key, name in LIST_FIELDS.items():
            values = d.get(key)
            if values is None:
                continue
            if not isinstance(values, list):
                out.append(f"{key} must be a list")
                continue
            for v in values:
                out += self._in(name, v, key)
        if not core:                       # core entries keep their free-form area tags (#118); shards use the tree
            areas = d.get("areas") or []
            if not isinstance(areas, list):
                out.append("areas must be a list")
            else:
                for a in areas:
                    if not (isinstance(a, str) and area_of(a, self.tree)):
                        near = difflib.get_close_matches(str(a), list(self.tree["areas"]) + list(self.tree["topics"]), n=1)
                        out.append(f"area {a!r} is not an area or topic slug of docs/areas.yaml"
                                   + (f" (did you mean {near[0]!r}?)" if near else ""))
        out += self._licence_problems(d)
        out += self._claims_problems(d)
        out += self._assessment_problems(d)
        for url in d.get("mirrors") or []:
            if not (isinstance(url, str) and url.startswith("https://") and " " not in url):
                out.append(f"mirror {url!r} is not an https link (mirrors are public copies, never a private host)")
        if d.get("mirrors") is not None and not isinstance(d.get("mirrors"), list):
            out.append("mirrors must be a list")
        for rule in d.get("rules") or []:
            if rule not in self.rule_ids():
                out.append(f"rule {rule!r} is not a rule id of research/process-profiles.yaml")
        for chk in d.get("checks") or []:
            if not (isinstance(chk, str) and CHECK_NAME.fullmatch(chk)):
                out.append(f"check {chk!r} is not a dotted cadagent name such as inserts.check_joint")
        arch = d.get("archive")
        if arch is not None:
            if not isinstance(arch, dict) or not SHA256.fullmatch(str(arch.get("sha256") or "")):
                out.append("archive needs the sha256 of the mirrored bytes; it is a pointer, never a path or a host")
            elif not isinstance(arch.get("redistribute"), bool):
                out.append("archive.redistribute must be true or false")
        projects = d.get("projects")
        if projects is not None:
            if not isinstance(projects, dict):
                out.append("projects must map a docs/areas.yaml project key to that project's mechanism slugs")
            else:
                for key, slugs in projects.items():
                    if key not in self.tree["projects"]:
                        out.append(f"projects key {key!r} is not in the projects table of docs/areas.yaml")
                    if not (isinstance(slugs, list) and all(isinstance(s, str) and KEY.fullmatch(s) for s in slugs)):
                        out.append(f"projects.{key} must be a list of kebab-case mechanism slugs")
        return out

    def _licence_problems(self, d: Dict[str, Any]) -> List[str]:
        out = []
        lic, reuse = d.get("licence"), d.get("reuse")
        if lic is not None and not isinstance(lic, dict):
            return ["licence must be a mapping: spdx, class, read, note"]
        if reuse is not None and not isinstance(reuse, dict):
            return ["reuse must be a mapping: text, geometry"]
        lic, reuse = lic or {}, reuse or {}
        geometry, cls = reuse.get("geometry"), lic.get("class")
        if d.get("kind") == "project" and not geometry:
            out.append("a project needs reuse.geometry: what may be done with its files")
        if cls in (self.vocab.get("study_only") or []) and geometry not in (None, "study-only", "none"):
            out.append(f"licence class {cls} makes geometry study-only (study only, never copy files, cite in the "
                       f"decision), not {geometry}")
        if geometry == "copy" and lic.get("read") is not True:
            out.append("reuse.geometry copy needs licence.read: true; nobody may copy files under an unread licence")
        if lic.get("spdx") is not None and not isinstance(lic.get("spdx"), str):
            out.append("licence.spdx is an SPDX id or null")
        return out

    def _claims_problems(self, d: Dict[str, Any]) -> List[str]:
        claims = d.get("claims")
        if claims is None:
            return []
        if not isinstance(claims, list):
            return ["claims must be a list of {text, status, evidence, corroborated_by}"]
        out = []
        for i, claim in enumerate(claims):
            if not isinstance(claim, dict) or not str(claim.get("text") or "").strip():
                out.append(f"claims[{i}] needs text: the rule as the source states it")
                continue
            out += self._in("claim_status", claim.get("status"), f"claims[{i}].status")
            by = claim.get("corroborated_by", [])
            if not isinstance(by, list):
                out.append(f"claims[{i}].corroborated_by must be a list of record ids")
                continue
            for other in by:
                if other == d.get("id"):
                    out.append(f"claims[{i}] is corroborated by itself")
                elif other not in self.reg:
                    out.append(f"claims[{i}].corroborated_by {other!r} is not a record id")
        return out

    def _assessment_problems(self, d: Dict[str, Any]) -> List[str]:
        a = d.get("assessment")
        if a is None:
            return []
        if not isinstance(a, dict):
            return ["assessment must be a mapping of the objective answers"]
        out = []
        answers = a.get("answers") or {}
        if not isinstance(answers, dict):
            out.append("assessment.answers must map a vocab.yaml `answer` key to its text")
        else:
            for key in answers:
                out += self._in("answer", key, "assessment.answers key")
        formats = _get(a, ("cad", "formats"))
        if formats is not None and not isinstance(formats, list):
            out.append("assessment.cad.formats must be a list")
        assessed = _date(_get(a, ("assessed", "date")))
        if a.get("assessed") is not None and assessed is None:
            out.append("assessment.assessed.date must be an ISO date")
        return out

    def ladder_problems(self, ref: Reference) -> List[str]:
        """The evidence ladder's own rules, and that a stored ``confidence`` equals the derived one."""
        d, cls, out = ref.data, ref.evidence_class, []
        if cls not in LADDER:
            return out                                 # reported by record_problems as a vocabulary problem
        rank = LADDER.index(cls)
        if ref.file == self.reg.core_file and rank == 0 and ref.kind == "source":
            out.append("a core entry is read (it has a dated `verified` note); a snippet-only record goes in a shard")
        if rank >= LADDER.index("read") and not _date(d.get("verified")):
            out.append(f"evidence class {cls} needs `verified`: the ISO date and what was read")
        if rank == 0:
            heavy = [p for p in d.get("used_for") or [] if isinstance(p, str) and not p.startswith(CATALOGUED_TAG_OK)
                     and not p.startswith("proposed:")]
            if heavy:
                out.append(f"used_for {heavy}: a snippet-only record backs nothing outside research/; read it at source "
                           "and promote it first")
            if d.get("rules") or d.get("checks"):
                out.append("a snippet-only record may not back a rule or a check: read it at source first")
        # verified-at-source means a second source agrees. Above it, a primary source whose examples tests reproduce
        # may stand alone (#143's medium: "one primary source with reproduced examples"); a secondary one may not.
        primary = _get(d, ("evidence", "authority")) in PRIMARY
        if (cls == "verified-at-source" or (rank > LADDER.index("verified-at-source") and not primary)) \
                and not _corroborators(ref, self.reg):
            out.append(f"evidence class {cls} needs a claim corroborated_by another record (the second source)"
                       + ("" if cls == "verified-at-source" else ", or evidence.authority primary or "
                          "independent-tested"))
        if rank >= LADDER.index("encoded") and not (d.get("rules") or d.get("checks")):
            out.append(f"evidence class {cls} needs `rules` or `checks`: the profile rules or checks that encode it")
        stored = d.get("confidence")
        if stored is not None:
            want = confidence(ref, self.reg)
            if stored != want:
                out.append(f"confidence {stored!r} is not the derived {want!r}: confidence is derived from the "
                           "evidence, never typed (write the derived value, or drop the field)")
        return out


def _date(text: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def isbn_ok(isbn: str) -> bool:
    """True for a well-formed ISBN-10 or ISBN-13 (hyphens allowed) with a correct check digit."""
    digits = isbn.replace("-", "").replace(" ", "").upper()
    if re.fullmatch(r"\d{13}", digits):
        return sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(digits)) % 10 == 0
    if re.fullmatch(r"\d{9}[\dX]", digits):
        return sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits)) % 11 == 0
    return False


def _path_ok(entry: str, root: Path) -> bool:
    if entry.startswith("proposed:"):
        return True
    return (root / entry.split("#", 1)[0]).exists()


def _entry_problems(ref: Reference, reg: Registry, root: Path, today: dt.date) -> List[str]:
    d, out = ref.data, []
    if ref.kind == "uncited":
        if d.get("kind") not in UNCITED_KINDS:
            out.append(f"kind {d.get('kind')!r}, not one of {', '.join(UNCITED_KINDS)}")
        if not str(d.get("note") or "").strip():
            out.append("no note saying what the key is")
        for cited in d.get("cites") or []:
            if reg.entries.get(reg.aliases.get(cited, cited), Reference("", "")).kind != "source":
                out.append(f"cites {cited!r}, which is not a read source")
        if d.get("kind") == "internal" and not (d.get("where") and _path_ok(d["where"], root)):
            out.append("an internal key needs `where`, the file it points at")
        return out
    if not str(d.get("title") or "").strip():
        out.append("no title")
    authors = d.get("authors", [])
    if not isinstance(authors, list) or not all(isinstance(a, str) and a.strip() for a in authors):
        out.append("authors must be a list of names ([] when the source names none)")
    if not (authors or str(d.get("org") or "").strip()):
        out.append("no author and no publisher (org)")
    aliases = d.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(a, str) and KEY.fullmatch(a) for a in aliases):
        out.append(f"aliases must be a list of kebab-case keys: {aliases!r}")
    for p in d.get("used_for") or []:
        if not isinstance(p, str) or not _path_ok(p, root):
            out.append(f"used_for {p!r} is not a file or folder in the repo (or 'proposed: ...')")
    if ref.kind == "unverified":
        if not str(d.get("why") or "").strip():
            out.append("an unverified entry needs `why`: what is missing before it can be cited")
        return out
    # A core entry is a read source someone relies on. A shard record may be catalogued (nothing read, used_for: [])
    # and places itself by tree slugs, which the schema-2 checks validate.
    shard = ref.file != reg.core_file
    required = ("access", "terms") + (("verified",) if ref.kind == "source" else ()) if shard else \
        ("access", "terms", "areas", "used_for", "verified")
    for name in required:
        if not d.get(name):
            out.append(f"no {name}")
    if not isinstance(d.get("used_for", []), list):
        out.append("used_for must be a list ([] for a catalogued record)")
    year = d.get("year", "missing")
    if year == "missing":
        out.append("no year (write year: null for an undated web page)")
    elif year is None:
        if d.get("access") not in ("free", "free-registration"):
            out.append("year: null is only for an undated web page; a printed or paid source has a year")
    elif not (isinstance(year, int) and 1800 < year <= today.year):
        out.append(f"year {year!r} is not a year")
    url, isbn = d.get("url"), d.get("isbn")
    if not (url or isbn):
        out.append("no url and no isbn")
    if url and (not isinstance(url, str) or not url.startswith("https://") or " " in url):
        out.append(f"url {url!r} is not an https link")
    if isbn and not (isinstance(isbn, str) and isbn_ok(isbn)):
        out.append(f"isbn {isbn!r} has a bad check digit or length")
    if d.get("access") == "print" and not isbn:
        out.append("a print source needs its isbn")
    if d.get("access") and d["access"] not in ACCESS:
        out.append(f"access {d['access']!r}, not one of {', '.join(ACCESS)}")
    terms = str(d.get("terms") or "")
    if terms and not ("cited" in terms and any(p in terms for p in NOT_COPIED)) and not (
            OPEN_LICENCE in terms and d.get("access") == "free"):
        out.append(f"terms must say it is cited and {' / '.join(NOT_COPIED)}, or name the open licence it is used "
                   f"{OPEN_LICENCE}: {terms!r}")
    verified = _date(d.get("verified"))
    if d.get("verified") and (verified is None or verified > today):
        out.append("verified must start with the ISO date it was read, not in the future")
    if not isinstance(d.get("areas", []), list):
        out.append("areas must be a list")
    return out


def _corroborators(ref: Reference, reg: Registry) -> List[Reference]:
    """The other records that corroborate ``ref``'s claims (``claims[].corroborated_by``), each counted once, and only
    when independent (a different record from a different publisher: ``org``, else the credited people) and read (a
    snippet corroborates nothing)."""
    me = (ref.get("org") or ref.credit or "").strip().lower()
    out: Dict[str, Reference] = {}
    for claim in ref.get("claims") or []:
        if not isinstance(claim, dict) or claim.get("status") not in ("corroborated", "encoded"):
            continue
        for key in claim.get("corroborated_by") or []:
            if not isinstance(key, str) or key not in reg:
                continue
            other = reg.resolve(key)
            them = (other.get("org") or other.credit or "").strip().lower()
            if other.id != ref.id and them != me and other.evidence_class in LADDER[1:]:
                out.setdefault(other.id, other)
    return list(out.values())


def confidence(ref: Reference, reg: Registry) -> Dict[str, Any]:
    """#143's confidence for one record, derived from its evidence so it cannot drift: ``{level, estimate, sources}``.

    * ``unknown``: no ``evidence`` block (not yet assessed), or a key not on the ladder;
    * ``low``: a search snippet (``snippet-only``), or a single source read but not reproduced;
    * ``medium``: one read primary source (``evidence.authority`` primary or independent-tested) whose examples tests
      reproduce (``encoded`` or ``measured``), or any read source with an independent corroborating record;
    * ``high``: reproduced (``encoded`` or ``measured``) and corroborated by an independent record that is itself
      ``verified-at-source`` or better: two or more independent sources, both checked at source.

    ``sources`` counts the record and its independent corroborators (0 when unknown). A level states how far the
    evidence has been checked; it does not make a number right for a given part."""
    cls = ref.evidence_class
    if not isinstance(ref.get("evidence"), dict) or cls not in LADDER:
        return {"level": "unknown", "estimate": None, "sources": 0}
    rank = LADDER.index(cls)
    if rank == 0:
        return {"level": "low", "estimate": LEVELS["low"], "sources": 1}
    others = _corroborators(ref, reg)
    strong = [o for o in others if LADDER.index(o.evidence_class) >= LADDER.index("verified-at-source")]
    reproduced = rank >= LADDER.index("encoded")
    primary = _get(ref.data, ("evidence", "authority")) in PRIMARY
    if reproduced and strong:
        level = "high"
    elif (primary and reproduced) or others:
        level = "medium"
    else:
        level = "low"
    return {"level": level, "estimate": LEVELS[level], "sources": 1 + len(others)}


def shard_folder(path: Path) -> Path:
    """The schema-2 shard folder beside a core file: ``research/references.yaml`` -> ``research/references/``."""
    return Path(path).with_suffix("")


def load(path: Optional[Path] = None) -> Registry:
    """Read the registry (default ``research/references.yaml`` of this checkout) and the schema-2 shards beside it
    (``research/references/*.yaml``, with ``vocab.yaml`` as their vocabularies)."""
    path = Path(path) if path else REGISTRY
    if not path.is_file():
        raise FileNotFoundError(f"{path}: the reference registry is read from a cad-agent checkout "
                                "(research/references.yaml); pass path= for another copy")
    folder, shards, vocab = shard_folder(path), [], None
    top = path.parent.parent                       # the checkout root, for repo-relative file names
    rel = lambda p: p.relative_to(top).as_posix() if top in p.parents else p.name   # noqa: E731
    if folder.is_dir():
        for f in sorted(folder.glob("*.yaml")):
            raw = f.read_bytes()
            data = _yaml(raw.decode("utf-8"))
            if f.name == VOCAB:
                vocab = data if data is not None else {}
            else:
                shards.append(Shard(rel(f), data if data is not None else {}, len(raw)))
    return Registry(_yaml(path.read_text(encoding="utf-8")) or {}, path, shards, vocab, rel(path))


def lookup(key: str, path: Optional[Path] = None) -> Reference:
    """The registry entry for an id or alias."""
    return load(path).resolve(key)


def citation(key: str, path: Optional[Path] = None) -> str:
    """A one-line citation for an id or alias: who, title, year and link."""
    return lookup(key, path).citation()


# ----------------------------------------------------------------------------- where the code cites by id

def _python_citations(path: Path, rel: str) -> List[Citation]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out = []
    for node in tree.body:
        target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else \
            node.target if isinstance(node, ast.AnnAssign) else None
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if isinstance(target, ast.Name) and target.id in TABLES and isinstance(value, ast.Dict):
            out += [Citation(k.value, rel, k.lineno, "table") for k in value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if isinstance(target, ast.Name) and target.id in ROW_TABLES and isinstance(value, ast.Dict):
            out += [Citation(v.elts[-1].value, rel, v.elts[-1].lineno, "row") for v in value.values
                    if isinstance(v, ast.Tuple) and v.elts and isinstance(v.elts[-1], ast.Constant)
                    and isinstance(v.elts[-1].value, str)]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else \
            node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if name == "cite" and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            out.append(Citation(node.args[0].value, rel, node.lineno, "cite"))
        if name == "Material":
            for kw in node.keywords:
                if kw.arg == "source" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    out.append(Citation(kw.value.value, rel, kw.value.lineno, "material"))
    return out


def _line_of(lines: Sequence[str], pattern: str, start: int = 0) -> int:
    rx = re.compile(pattern)
    for i in range(start, len(lines)):
        if rx.search(lines[i]):
            return i + 1
    return 0


def _process_profile_citations(path: Path, rel: str) -> List[Citation]:
    text = path.read_text(encoding="utf-8")
    data, lines = _yaml(text) or {}, text.splitlines()
    out = []
    for section, key in (("rules", "source"), ("formulas", "source"), ("shop_tables", "source"), ("datasets", "cites")):
        for item in data.get(section) or []:
            src = item.get(key)
            if not isinstance(src, str) or src.startswith("dataset:") or " " in src:
                continue                      # a dataset id, or the prose `cites` of a dataset kept on another page
            at = _line_of(lines, rf"^\s*-?\s*id:\s*{re.escape(str(item.get('id')))}\s*$")
            out.append(Citation(src, rel, _line_of(lines, rf"^\s*{key}:\s*{re.escape(src)}\s*$", at) or at,
                                "process-profile"))
    return out


def _tag_citations(path: Path, rel: str) -> List[Citation]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []
    out = []
    for i, line in enumerate(lines):
        for m in TAG.finditer(line):
            key = m.group(1)
            if not PLACEHOLDER.fullmatch(key):
                out.append(Citation(key, rel, i + 1, "tag" if KEY.fullmatch(key) else "bad-tag"))
    return out


def citations(root: Path = ROOT) -> List[Citation]:
    """Every place in a cad-agent checkout that cites a source by id (see the module docstring for the forms)."""
    root = Path(root)
    out: List[Citation] = []
    me = Path(__file__).resolve()
    for path in sorted((root / "src" / "cadagent").rglob("*.py")):
        if "__pycache__" not in path.parts and path.resolve() != me:
            out += _python_citations(path, path.relative_to(root).as_posix())
    pp = root / "research" / "process-profiles.yaml"
    if pp.is_file():
        out += _process_profile_citations(pp, pp.relative_to(root).as_posix())
    for path in sorted(root.glob("*.md")):
        if path.name != "CHANGELOG.md":           # released notes quote tags as text; changelog.d is not scanned either
            out += _tag_citations(path, path.relative_to(root).as_posix())
    for folder in TAG_FOLDERS:
        for path in sorted((root / folder).rglob("*")):
            if path.suffix in TAG_SUFFIXES and path.is_file() and "vendor" not in path.parts and path.resolve() != me:
                out += _tag_citations(path, path.relative_to(root).as_posix())
    return out


def lists(used_for: Iterable[str], path: str) -> bool:
    """True when ``used_for`` names ``path``: the file itself, ``path#anchor``, or a folder that holds it."""
    for entry in used_for:
        if not isinstance(entry, str) or entry.startswith("proposed:"):
            continue
        entry = entry.split("#", 1)[0].rstrip("/")
        if path == entry or path.startswith(entry + "/"):
            return True
    return False


def check(root: Path = ROOT, registry: Optional[Registry] = None,
          found: Optional[Iterable[Citation]] = None) -> Tuple[List[str], List[str]]:
    """(problems, warnings) for the registry and the code that cites it.

    Problems: a malformed entry, a key that resolves to nothing, a file that cites an entry its ``used_for`` does
    not list, or a rule, check, code table or page that cites a catalogued (snippet-only) record. Warnings: code that
    cites an ``unverified`` entry (a known gap, to be read and moved up), and a ``[ref:]`` to a catalogued record in
    ``research/`` (a survey may list what it has not read yet)."""
    root = Path(root)
    reg = registry or load(root / "research" / "references.yaml")
    problems, warnings = reg.problems(root), []
    for c in (citations(root) if found is None else found):
        if c.how == "bad-tag":
            problems.append(f"{c.where}: [ref:{c.key}] is not a tag: write [ref:<id>] with one kebab-case id")
            continue
        if c.key not in reg:
            problems.append(f"{c.where}: cites {c.key!r}, which research/references.yaml does not have")
            continue
        ref = reg.resolve(c.key)
        if ref.kind == "catalogued":
            if c.how == "tag" and c.path.startswith(CATALOGUED_TAG_OK):
                warnings.append(f"{c.where}: cites {c.key!r}, a {ref.evidence_class} record (listed, not read)")
            else:
                problems.append(f"{c.where}: cites {c.key!r}, a {ref.evidence_class} record: a rule, check or page "
                                "may cite only what was read; open it at source, write `verified` and promote it "
                                "to evidence.class: read first")
                continue
        if ref.kind == "unverified":
            warnings.append(f"{c.where}: cites {c.key!r}, an unverified entry ({ref.get('why')})")
        if ref.kind != "uncited" and not lists(ref.get("used_for") or [], c.path):
            problems.append(f"{c.where}: cites {c.key!r}; add {c.path} to used_for of {ref.id}")
    return problems, sorted(set(warnings))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cadagent.review.references",
                                 description="Look up cad-agent's cited sources, or check the registry (#118).")
    ap.add_argument("keys", nargs="*", help="ids or aliases to look up")
    ap.add_argument("--check", action="store_true", help="check the registry and every citation in the checkout")
    ap.add_argument("--json", action="store_true", help="print the entries as JSON")
    args = ap.parse_args(argv)
    if not (args.check or args.keys):
        ap.print_usage(sys.stderr)
        return 2
    reg = load()
    if args.check:
        problems, warnings = check(registry=reg)
        for w in warnings:
            print(f"warning: {w}")
        for p in problems:
            print(p)
        print(f"{len(reg)} entries in {1 + len(reg.shards)} files ({len(reg.of_kind('catalogued'))} catalogued); "
              f"{len(problems)} problems, {len(warnings)} warnings")
        if problems:
            return 1
    status = 0
    for key in args.keys:
        try:
            ref = reg.resolve(key)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            status = 2
            continue
        print(json.dumps({"key": key, "kind": ref.kind, "file": ref.file, **ref.data}, ensure_ascii=False,
                         default=str) if args.json else
              f"{key}: {ref.citation()}")
    return status


if __name__ == "__main__":
    sys.exit(main())
