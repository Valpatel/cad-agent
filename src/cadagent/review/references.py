"""The reference registry (#118): every outside source a cad-agent rule, check or number relies on, by a stable id.

The registry is ``research/references.yaml`` in a cad-agent checkout. Code cites a source by its id, and the registry
says who wrote it, where it is, what was read and when, and what cad-agent may do with it: sources are summarised and
cited, never copied, and paid documents are cited by number and title only. Nothing here vendors a source.

Where code cites by id (``citations()`` finds them all):

* a module-level ``SRC`` or ``SOURCES`` dict whose keys are ids (``cadagent.formulas``, ``cadagent.mechanical.inserts``,
  ``cadagent.mechanical.printed_joints``), and ``cite("<id>", ...)`` calls;
* ``Material(..., source="<id>")`` (``cadagent.simulation.fea``);
* ``research/process-profiles.yaml``: each rule's, formula's and shop table's ``source``, and each dataset's ``cites``;
* ``[ref:<id>]`` tags in Markdown, YAML and Python text (a malformed tag is reported, not skipped).

A key resolves to one of three kinds of entry:

* ``sources``: read, with an https URL or an ISBN. An entry may list ``aliases``, the shorter keys a module uses for
  the same document (``covestro`` and ``covestro-friction`` both cite ``covestro-snapfit``); the module's own text keeps
  the page or table;
* ``unverified``: named, but not yet read or not yet found online, with the reason. Code that cites one is a known
  gap: ``check()`` warns about it, and ``tests/test_references.py`` pins how many there are, a number that only falls;
* ``uncited``: a key that is not an outside source, said openly: ``general`` (common engineering knowledge),
  ``judgement`` (a stated judgement of the module) or ``internal`` (another cad-agent module, with what it cites).

``lookup(key)`` gives the entry, ``citation(key)`` a one-line citation, ``check()`` every problem in the registry and
in the code that cites it. From a shell::

    python -m cadagent.review.references covestro roark     # print the citations
    python -m cadagent.review.references --check            # exit 1 on a problem

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

ACCESS = ("free", "free-registration", "paid", "print")
UNCITED_KINDS = ("general", "judgement", "internal")
KINDS = ("source", "unverified", "uncited")
# What `terms` must say: that the source is cited and not copied or passed on, or that its open licence lets it be
# vendored or adopted with attribution (code, never a paid document).
NOT_COPIED = ("never copied", "not copied", "not redistributed", "by number and title only")
OPEN_LICENCE = "with attribution"
KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TAG = re.compile(r"\[ref:([^\]\n]*)\]")
PLACEHOLDER = re.compile(r"<[^>]*>")   # "[ref:<id>]" in prose explains the syntax; it cites nothing
TABLES = ("SRC", "SOURCES")         # module-level dicts whose keys are ids
TAG_FOLDERS = ("docs", "lessons", "research", "skills", "src", "agents", "tools", "examples", "web")
TAG_SUFFIXES = (".md", ".py", ".yaml", ".yml")


@dataclass(frozen=True)
class Reference:
    """One registry entry. ``kind`` is ``source``, ``unverified`` or ``uncited``; ``data`` is the entry as written."""
    id: str
    kind: str
    data: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

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
        return text + (" (unverified)" if self.kind == "unverified" else "")


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


class Registry:
    """The registry as loaded: entries by id, aliases to ids, and the raw data."""

    def __init__(self, data: Dict[str, Any], path: Optional[Path] = None):
        self.data = data
        self.path = path
        self.entries: Dict[str, Reference] = {}
        self.aliases: Dict[str, str] = {}
        self._duplicates: List[str] = []
        for section, kind in (("sources", "source"), ("unverified", "unverified"), ("uncited", "uncited")):
            for item in data.get(section) or []:
                rid = item.get("id") if isinstance(item, dict) else None
                if not isinstance(rid, str):
                    continue
                if rid in self.entries:
                    self._duplicates.append(rid)
                self.entries[rid] = Reference(rid, kind, item)
        # aliases after every id, so an alias that names an entry is caught wherever either is written
        for ref in self.entries.values():
            for alias in ref.data.get("aliases") or []:
                if alias in self.aliases or alias in self.entries:
                    self._duplicates.append(alias)
                    continue
                self.aliases[alias] = ref.id

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
        """Every way an entry is malformed: missing fields, bad ids, links, dates, terms or paths."""
        today = today or dt.date.today()
        out = [f"{k}: the id or alias is used twice" for k in sorted(set(self._duplicates))]
        if self.data.get("schema") != 1:
            out.append(f"schema is {self.data.get('schema')!r}, not 1")
        for key in list(self.entries) + list(self.aliases):
            if not KEY.fullmatch(key):
                out.append(f"{key}: not a kebab-case key")
        for ref in self.entries.values():
            out += [f"{ref.id}: {p}" for p in _entry_problems(ref, self, root, today)]
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
    for p in d.get("used_for") or []:
        if not isinstance(p, str) or not _path_ok(p, root):
            out.append(f"used_for {p!r} is not a file or folder in the repo (or 'proposed: ...')")
    if ref.kind == "unverified":
        if not str(d.get("why") or "").strip():
            out.append("an unverified entry needs `why`: what is missing before it can be cited")
        return out
    for name in ("access", "terms", "areas", "used_for", "verified"):
        if not d.get(name):
            out.append(f"no {name}")
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


def load(path: Optional[Path] = None) -> Registry:
    """Read the registry (default ``research/references.yaml`` of this checkout)."""
    path = Path(path) if path else REGISTRY
    if not path.is_file():
        raise FileNotFoundError(f"{path}: the reference registry is read from a cad-agent checkout "
                                "(research/references.yaml); pass path= for another copy")
    return Registry(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, path)


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
    data, lines = yaml.safe_load(text) or {}, text.splitlines()
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

    Problems: a malformed entry, a key that resolves to nothing, or a file that cites an entry its ``used_for`` does
    not list. Warnings: code that cites an ``unverified`` entry (a known gap, to be read and moved up)."""
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
    if args.check:
        problems, warnings = check()
        for w in warnings:
            print(f"warning: {w}")
        for p in problems:
            print(p)
        print(f"{len(problems)} problems, {len(warnings)} warnings")
        if problems:
            return 1
    reg = load()
    status = 0
    for key in args.keys:
        try:
            ref = reg.resolve(key)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            status = 2
            continue
        print(json.dumps({"key": key, "kind": ref.kind, **ref.data}, ensure_ascii=False) if args.json else
              f"{key}: {ref.citation()}")
    return status


if __name__ == "__main__":
    sys.exit(main())
