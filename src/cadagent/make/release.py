"""Print release: a browsable page of the printed parts with their CAD files and the source that builds them.

``cad-agent release`` writes ``release/<name>-rev<revision>/`` (or ``--out DIR``) and ``<folder>.zip`` next to it:

* ``index.html``: one standalone page (inline CSS, light and dark, no scripts, opens from ``file://``). For each
  printed part: a thumbnail, its quantity, material and notes, the slicer's mass and time when the slice report is
  current for that part, and links to its STEP, STL and 3MF. Then the assembly pages, the hardware list and the source;
* ``cad/<part>.{step,stl,3mf}`` and any ``extra_cad`` files;
* ``images/<part>.png``: the thumbnails;
* ``docs/<project path>``: the ``pages`` (Markdown is also rendered to HTML when the ``markdown`` package is
  installed) and the images they link to, at their project paths, so their relative links keep working;
* ``source/<project path>``: the files matched by ``include`` minus ``exclude``;
* ``manifest.json``: the parts, the git commit (and whether the tree was dirty), and the sha256 of every file.

Simulation results, render galleries and review evidence stay out unless a glob asks for them: this is what someone
who wants to print and build the design downloads. The review package (``cad-agent package``) is a different thing.

Every configured path and glob must stay inside the project (no absolute paths, no ``..``); files that resolve
outside it (symlinks) are skipped. Hidden files and files git ignores are never released from globs. The output is
reproducible: the folder is rewritten from scratch, and the zip has sorted entries with fixed dates.

Config ``cad: release:`` (all optional)::

    release:
      title: J501 enclosure                # default: cad.title
      revision: 0.9.1                      # default: cad.revision / revision_from (or --revision)
      groups:                              # or `parts: [a, b]`; default: every part in the parts file
        - {title: Print these, parts: [base, cover], note: The enclosure set.}
        - {title: Base (print one), parts: [base, base_wall], pick_one: true}
        - {title: Drive storage, parts: [tray], optional: true}
      build: {title: Desktop build, parts: [lid, base]}   # one complete build: its filament and time on the page
      quantities: {rail_key: 2}            # default 1
      material: PLA                        # default: the filament in cad.slicer
      notes:                               # shown on the part's card, in this order
        cover: {orientation: roof down, supports: none}
      thumbnail: "{preview}/part-{part}.png"
      extra_cad: [exports/assembly.step]   # more CAD files for cad/
      pages: [ASSEMBLY.md, "docs/assembly/*"]
      hardware: docs/hardware.csv          # a CSV, or a list of mappings ({item, qty, ...})
      include: ["cad/**", "tools/**", cad-agent.yaml, "requirements*.txt", README.md, "LICENSE*"]
      exclude: ["**/__pycache__/**", "**/*.pyc"]
      max_file_mb: 20                      # warn about any released file larger than this
      date: 2026-10-29                     # default: --date, SOURCE_DATE_EPOCH, the last commit's date, today
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

from cadagent.project import CadConfigError, CadProject

DEFAULT_INCLUDE = ["cad/**", "tools/**", "cad-agent.yaml", "requirements*.txt", "README.md", "LICENSE*"]
DEFAULT_EXCLUDE = ["**/__pycache__/**", "**/*.pyc"]
DEFAULT_THUMBNAIL = "{preview}/part-{part}.png"
DEFAULT_MAX_FILE_MB = 20.0
CAD_SUFFIXES = (".step", ".stl", ".3mf")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
MARKER = "cad-agent.release/1"
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_KEYS = {"title", "revision", "parts", "groups", "build", "quantities", "material", "notes", "thumbnail", "extra_cad", "pages",
         "hardware", "include", "exclude", "max_file_mb", "date"}
_GROUP_KEYS = {"title", "parts", "note", "optional", "pick_one"}


@dataclass
class Group:
    title: str
    parts: List[str]
    note: str = ""
    optional: bool = False
    pick_one: bool = False      # alternatives: print one of these parts, not all of them


@dataclass
class ReleaseConfig:
    title: str
    groups: List[Group]
    revision: str = ""
    quantities: Dict[str, int] = field(default_factory=dict)
    material: str = ""
    notes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    thumbnail: str = DEFAULT_THUMBNAIL
    extra_cad: List[str] = field(default_factory=list)
    pages: List[str] = field(default_factory=list)
    hardware: Any = None
    include: List[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE))
    exclude: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    max_file_mb: float = DEFAULT_MAX_FILE_MB
    date: str = ""
    left_out: List[str] = field(default_factory=list)      # known parts no group lists
    build: Optional[Group] = None                            # one complete build, totalled on the page
    build_gaps: List[str] = field(default_factory=list)      # required pick-one groups the build takes nothing from


@dataclass
class ReleaseResult:
    folder: Path
    zip_path: Optional[Path]
    files: Dict[str, str]
    parts: List[Dict[str, Any]]
    warnings: List[str] = field(default_factory=list)


def _strings(value: Any, where: str, allow_none: bool = True) -> List[str]:
    if value is None:
        if not allow_none:
            raise CadConfigError(f"{where} is empty; give a list (or [] for none)")
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CadConfigError(f"{where} must be a list of strings")
    return list(value)


def _inside(pattern: str, where: str) -> str:
    """A configured path or glob, refused when it is absolute or climbs out of the project with ``..``."""
    p = pattern.replace("\\", "/")
    if not p or p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", p) or ".." in p.split("/"):
        raise CadConfigError(f"{where}: {pattern!r} must be a relative path inside the project (no '..', not absolute)")
    return pattern


def release_config(project: CadProject, known_parts: Sequence[str]) -> ReleaseConfig:
    """Parse and check ``cad.release``; ``known_parts`` (from the parts file) is the default part list."""
    raw = project.release or {}
    if not isinstance(raw, dict):
        raise CadConfigError("cad.release must be a mapping")
    unknown = sorted(set(raw) - _KEYS)
    if unknown:
        raise CadConfigError(f"cad.release: unknown keys {unknown}; known: {sorted(_KEYS)}")
    if "groups" in raw and "parts" in raw:
        raise CadConfigError("cad.release: give either parts or groups, not both")
    groups: List[Group] = []
    if "groups" in raw:
        if not isinstance(raw["groups"], list) or not raw["groups"]:
            raise CadConfigError("cad.release.groups must be a non-empty list of {title, parts, note, optional, "
                                 "pick_one}")
        for i, g in enumerate(raw["groups"]):
            if not isinstance(g, dict) or not g.get("title") or not g.get("parts"):
                raise CadConfigError(f"cad.release.groups[{i}] needs a title and a non-empty parts list")
            bad = sorted(set(g) - _GROUP_KEYS)
            if bad:
                raise CadConfigError(f"cad.release.groups[{i}]: unknown keys {bad}; known: {sorted(_GROUP_KEYS)}")
            for flag in ("optional", "pick_one"):
                if not isinstance(g.get(flag, False), bool):
                    raise CadConfigError(f"cad.release.groups[{i}].{flag} must be true or false")
            if g.get("pick_one") and len(_strings(g["parts"], f"cad.release.groups[{i}].parts")) < 2:
                raise CadConfigError(f"cad.release.groups[{i}] is pick one but lists one part; leave pick_one out")
            groups.append(Group(str(g["title"]), _strings(g["parts"], f"cad.release.groups[{i}].parts"),
                                str(g.get("note") or ""), bool(g.get("optional", False)), bool(g.get("pick_one", False))))
    elif "parts" in raw:
        parts = _strings(raw["parts"], "cad.release.parts", allow_none=False)
        if not parts:
            raise CadConfigError("cad.release.parts is empty; leave it out to release every part")
        groups.append(Group("Parts", parts))
    else:
        if not known_parts:
            raise CadConfigError("cad.release: no parts (list them, or build first so the parts file exists)")
        groups.append(Group("Parts", list(known_parts)))
    seen: List[str] = []
    for g in groups:
        for p in g.parts:
            if p in seen:
                raise CadConfigError(f"cad.release: part {p!r} is listed twice")
            seen.append(p)
    quantities = raw.get("quantities") or {}
    if not isinstance(quantities, dict) or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 1
                                                   for v in quantities.values()):
        raise CadConfigError("cad.release.quantities must map part -> a whole number >= 1")
    notes = raw.get("notes") or {}
    if not isinstance(notes, dict) or not all(isinstance(v, dict) for v in notes.values()):
        raise CadConfigError("cad.release.notes must map part -> {label: text}")
    for part, labels in notes.items():
        empty = [k for k, v in labels.items() if v is None or isinstance(v, (dict, list))]
        if empty:   # usually an unquoted comma in a YAML {flow: mapping} that split one note into two keys
            raise CadConfigError(f"cad.release.notes.{part}: {empty} have no text; quote values that contain commas")
    for name in list(quantities) + list(notes):
        if name not in seen:
            raise CadConfigError(f"cad.release: {name!r} has a quantity or notes but is not a released part")
    build, build_gaps = None, []
    if raw.get("build") is not None:
        b = raw["build"]
        if not isinstance(b, dict) or not b.get("title") or not b.get("parts"):
            raise CadConfigError("cad.release.build must be {title, parts} with a non-empty parts list")
        bad = sorted(set(b) - {"title", "parts"})
        if bad:
            raise CadConfigError(f"cad.release.build: unknown keys {bad}; known: ['parts', 'title']")
        build = Group(str(b["title"]), _strings(b["parts"], "cad.release.build.parts"))
        twice = sorted({n for n in build.parts if build.parts.count(n) > 1})
        unreleased = [n for n in build.parts if n not in seen]
        if twice or unreleased:
            raise CadConfigError(f"cad.release.build.parts must be released parts, each listed once (listed twice: "
                                 f"{twice or 'none'}; not released: {unreleased or 'none'})")
        for g in groups:
            picked = [n for n in build.parts if n in g.parts]
            if g.pick_one and len(picked) > 1:
                raise CadConfigError(f"cad.release.build takes {picked} from {g.title!r}, which is pick one")
            if g.pick_one and not g.optional and not picked:
                build_gaps.append(g.title)
    hardware = raw.get("hardware")
    if hardware is not None and not isinstance(hardware, (str, list)):
        raise CadConfigError("cad.release.hardware must be a CSV path or a list of mappings")
    if isinstance(hardware, str):
        _inside(hardware, "cad.release.hardware")
    if isinstance(hardware, list):
        if not all(isinstance(r, dict) for r in hardware):
            raise CadConfigError("cad.release.hardware rows must be mappings")
        for i, row in enumerate(hardware):
            if any(v is None for v in row.values()):
                raise CadConfigError(f"cad.release.hardware[{i}]: {[k for k, v in row.items() if v is None]} have no "
                                     "value; quote values that contain commas")
    thumbnail = raw.get("thumbnail", DEFAULT_THUMBNAIL)
    if not isinstance(thumbnail, str) or not thumbnail:
        raise CadConfigError("cad.release.thumbnail must be a path pattern such as '{preview}/part-{part}.png'")
    try:
        _inside(thumbnail.format(part="x", preview="preview"), "cad.release.thumbnail")
    except (KeyError, IndexError, ValueError) as exc:
        raise CadConfigError(f"cad.release.thumbnail {thumbnail!r}: only the fields {{part}} and {{preview}} may be "
                             f"used ({exc!r})") from exc
    max_mb = raw.get("max_file_mb", DEFAULT_MAX_FILE_MB)
    if isinstance(max_mb, bool) or not isinstance(max_mb, (int, float)) or max_mb <= 0:
        raise CadConfigError("cad.release.max_file_mb must be a positive number")
    globs = {}
    for key, default in (("include", DEFAULT_INCLUDE), ("exclude", DEFAULT_EXCLUDE), ("extra_cad", []), ("pages", [])):
        values = _strings(raw[key], f"cad.release.{key}", allow_none=False) if key in raw else list(default)
        globs[key] = [_inside(v, f"cad.release.{key}") for v in values]
    return ReleaseConfig(
        title=str(raw.get("title") or project.title or project.name),
        groups=groups,
        build=build,
        build_gaps=build_gaps,
        revision=str(raw.get("revision") or ""),
        quantities={str(k): int(v) for k, v in quantities.items()},
        material=str(raw.get("material") or ""),
        notes={str(k): {str(a): str(b) for a, b in v.items()} for k, v in notes.items()},
        thumbnail=thumbnail,
        extra_cad=globs["extra_cad"],
        pages=globs["pages"],
        hardware=hardware,
        include=globs["include"],
        exclude=globs["exclude"],
        max_file_mb=float(max_mb),
        date=str(raw.get("date") or ""),
        left_out=[p for p in known_parts if p not in seen] if "groups" in raw or "parts" in raw else [],
    )


# ----------------------------------------------------------------------------- helpers

def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _glob_match(rel: str, pattern: str) -> bool:
    """``**`` matches any number of folders (``Path.match`` before Python 3.13 does not)."""
    rx = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    return re.fullmatch(rx, rel) is not None


def _git(root: Path, *args: str, stdin: Optional[str] = None) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30, input=stdin)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _git_ignored(root: Path, rels: Sequence[str]) -> Tuple[set, str]:
    """The paths among ``rels`` that git ignores, and an error when git could not say (empty outside a git work
    tree). Tracked files are never ignored, so a force-added file is kept."""
    if not rels or _git(root, "rev-parse", "--is-inside-work-tree") is None:
        return set(), ""
    try:
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "--stdin", "-z"], capture_output=True,
                           text=True, timeout=60, input="\0".join(rels) + "\0")
    except (OSError, subprocess.SubprocessError) as exc:
        return set(), f"git check-ignore failed ({exc}); git-ignored files were not filtered out"
    if r.returncode not in (0, 1):            # 1 = nothing ignored; anything else is an error (e.g. dubious ownership)
        return set(), (f"git check-ignore failed (exit {r.returncode}: {r.stderr.strip()[:200]}); git-ignored files "
                       "were not filtered out")
    return {p for p in r.stdout.split("\0") if p}, ""


def _glob(root: Path, patterns: Sequence[str], exclude: Sequence[str] = (),
          skipped: Optional[List[str]] = None) -> List[Path]:
    """Files under ``root`` matched by ``patterns`` minus ``exclude``. Hidden files, files git ignores and anything
    that resolves outside ``root`` (a symlink out of the project) are left out; ``skipped`` collects why."""
    real_root = root.resolve()
    out: Dict[str, Path] = {}
    for pattern in patterns:
        if pattern.endswith("**"):          # a trailing ** names folders only in pathlib.glob: take their files
            pattern += "/*"
        for p in sorted(root.glob(pattern)):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if any(_glob_match(rel, g) for g in exclude):
                continue
            if any(bit.startswith(".") for bit in rel.split("/")):
                if skipped is not None:
                    skipped.append(f"{rel}: hidden; not released")
                continue
            if not p.resolve().is_relative_to(real_root):
                if skipped is not None:
                    skipped.append(f"{rel}: links outside the project; not released")
                continue
            out.setdefault(rel, p)
    ignored, error = _git_ignored(root, list(out))
    if skipped is not None:
        skipped.extend(f"{rel}: ignored by git; not released" for rel in sorted(ignored))
        if error:
            skipped.append(error)
    return [out[k] for k in sorted(out) if k not in ignored]


def _git_state(root: Path) -> Dict[str, Any]:
    """The commit, its date and whether tracked files differ from it (an empty dict outside git)."""
    commit = _git(root, "rev-parse", "HEAD")
    if commit is None:
        return {}
    status = _git(root, "status", "--porcelain", "--untracked-files=no") or ""
    modified = sorted(line[3:] for line in status.splitlines() if line.strip())
    return {"commit": commit.strip(), "date": (_git(root, "log", "-1", "--format=%cs") or "").strip(),
            "dirty": bool(modified), "modified": modified}


def _stable_date(explicit: str, git_date: str) -> Tuple[str, bool]:
    """The release date and whether it is reproducible."""
    if explicit:
        return explicit, True
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.strip().isdigit():
        return datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc).date().isoformat(), True
    if git_date:
        return git_date, True
    return datetime.date.today().isoformat(), False


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def _duration(minutes: Optional[float]) -> str:
    if minutes is None:
        return ""
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "release"


def _e(v: Any) -> str:
    return html.escape(str(v), quote=True)


def _u(rel: str) -> str:
    """A relative path as an escaped, URL-encoded href (``#``, ``?``, ``%`` and spaces in names)."""
    return _e(quote(rel, safe="/"))


def _slice_rows(project: CadProject) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], str]:
    """The slice report, its per-part rows that are still current, and why the others are not.

    A row is current only while the report was made with the settings ``cad.slicer`` names now (the rule
    ``slicer.current_report`` uses) and the part's 3MF still has the sha256 recorded for it."""
    from cadagent.make.slicer import _settings

    path = project.exports_dir / "slice-report.json"
    try:
        rep = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}, {}, "no slice report (run cad-agent slice)"
    if not isinstance(rep, dict):
        return {}, {}, "the slice report is not a JSON object"
    differ = [k for k, v in _settings(project).items() if rep.get(k) != v]
    if differ:
        return rep, {}, f"the slice report used other settings ({', '.join(differ)}) than cad.slicer now"
    current = {}
    for name, row in (rep.get("parts") or {}).items():
        f = project.exports_dir / f"{name}.3mf"
        if isinstance(row, dict) and row.get("grams") and f.is_file() and _sha(f) == row.get("sha256"):
            current[name] = row
    return rep, current, ""


def _hardware_rows(project: CadProject, hardware: Any) -> List[Dict[str, str]]:
    if hardware is None:
        return []
    if isinstance(hardware, list):
        return [{str(k): str(v) for k, v in row.items()} for row in hardware]
    path = project.root / hardware
    if not path.is_file() or not path.resolve().is_relative_to(project.root.resolve()):
        raise CadConfigError(f"cad.release.hardware: {hardware} not found inside the project")
    with open(path, newline="") as fh:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(fh)]


# ----------------------------------------------------------------------------- pages

_URL = r"^[a-z][a-z0-9+.-]*:|^#|^/"


def _rewrite(text: str, links: Dict[str, str], src_rel: str, at: str, markdown_links: bool) -> str:
    """Relative links in a page at project path ``src_rel``, now at release path ``at``: a link to a file the release
    carries (``links``: project path -> release path) points at that copy. ``markdown_links`` also rewrites
    ``[text](url)`` and ``![alt](url)``."""
    base = Path(src_rel).parent

    def new(url: str) -> Optional[str]:
        if re.match(_URL, url):
            return None
        path, _, frag = url.partition("#")
        target = _norm((base / html.unescape(path)).as_posix())
        if target is None or target not in links:
            return None
        return quote(_rel_from(at, links[target]), safe="/") + ("#" + frag if frag else "")

    def attr(m: re.Match) -> str:
        n = new(m.group(2))
        return m.group(0) if n is None else f'{m.group(1)}="{_e(n)}"'

    text = re.sub(r'(href|src)="([^"]+)"', attr, text)
    if markdown_links:
        def md(m: re.Match) -> str:
            n = new(m.group(2))
            return m.group(0) if n is None else f"{m.group(1)}({n}{m.group(3)})"
        text = re.sub(r'(!?\[[^\]]*\])\(([^)\s]+)((?:\s+"[^"]*")?)\)', md, text)
    return text


def _render_markdown(text: str, links: Dict[str, str], src_rel: str, at: str) -> Optional[str]:
    """Markdown -> HTML (None without the ``markdown`` package), its links rewritten for the page at ``at``."""
    try:
        import markdown  # type: ignore
    except ImportError:
        return None
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"], output_format="html")
    return _rewrite(body, links, src_rel, at, markdown_links=False)


def _norm(rel: str) -> Optional[str]:
    """``a/./b/../c`` -> ``a/c``; None when the path climbs out of the project."""
    parts: List[str] = []
    for bit in rel.split("/"):
        if bit in ("", "."):
            continue
        if bit == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(bit)
    return "/".join(parts)


def _rel_from(from_file: str, to_file: str) -> str:
    a, b = Path(from_file).parent.parts, Path(to_file).parts
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return "/".join([".."] * (len(a) - i) + list(b[i:])) or "."


def _linked_images(text: str, src_rel: str, root: Path) -> List[str]:
    """Project-relative images a Markdown or HTML page links to that exist inside the project."""
    base = Path(src_rel).parent
    real_root = root.resolve()
    out = []
    for url in re.findall(r'!\[[^\]]*\]\(([^)\s]+)|(?:src|href)="([^"]+)"', text):
        u = url[0] or url[1]
        if re.match(_URL, u):
            continue
        rel = _norm((base / html.unescape(u.split("#")[0])).as_posix())
        if rel is None or Path(rel).suffix.lower() not in IMAGE_SUFFIXES:
            continue
        f = root / rel
        if f.is_file() and f.resolve().is_relative_to(real_root) and not any(b.startswith(".") for b in rel.split("/")):
            out.append(rel)
    return out


# ----------------------------------------------------------------------------- page

_CSS = """
:root{color-scheme:light dark;
--bg:#f5f7f9;--surface:#fff;--surface-2:#eef2f5;--text:#16212b;--muted:#5a6873;--line:#dde5eb;
--accent:#1f5f8b;--ok:#1d7a3e;--ok-bg:#e3f4e8;--warn:#8a5a00;--warn-bg:#fff4d6;--warn-line:#e8c66a}
@media (prefers-color-scheme:dark){:root{
--bg:#0f1418;--surface:#171e24;--surface-2:#1f2830;--text:#e4eaef;--muted:#9aa8b3;--line:#2b3640;
--accent:#7db7e0;--ok:#6fd394;--ok-bg:#173523;--warn:#f2c76b;--warn-bg:#352a10;--warn-line:#6b5420}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
.page{max-width:1180px;margin:0 auto;padding:28px 16px 48px}
header h1{margin:0 0 6px;font-size:1.75rem;line-height:1.25}
.meta{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0;padding:0;list-style:none;color:var(--muted);font-size:.92rem}
.meta b{color:var(--text);font-weight:600}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0 6px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.stat b{display:block;font-size:1.35rem}.stat span{color:var(--muted);font-size:.85rem}
.settings{margin:14px 0 0;padding:12px 16px;background:var(--surface);border:1px solid var(--line);border-radius:10px;font-size:.92rem}
.settings dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:6px 0 0}
.settings dt{color:var(--muted)}.settings dd{margin:0;overflow-wrap:anywhere}
.alert{margin:14px 0;padding:10px 14px;border:1px solid var(--warn-line);border-left-width:5px;border-radius:8px;background:var(--warn-bg)}
nav.toc{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 0}
nav.toc a{border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:5px 12px;text-decoration:none;font-weight:600;font-size:.9rem}
h2{margin:34px 0 4px;font-size:1.25rem}.lead{margin:0 0 12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.card{display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card .thumb{display:block;aspect-ratio:4/3;background:var(--surface-2);border-bottom:1px solid var(--line)}
.card .thumb img{width:100%;height:100%;object-fit:contain;display:block}
.card .thumb.none{display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:.85rem}
.card .body{padding:10px 14px 12px;display:flex;flex-direction:column;gap:6px;flex:1}
.card h3{margin:0;font-size:1.02rem;display:flex;gap:8px;align-items:baseline;justify-content:space-between}
.card h3 .qty{font-size:.85rem;font-weight:600;color:var(--accent);white-space:nowrap}
.card .id{color:var(--muted);font-weight:500;font-size:.85rem}
.card dl{display:grid;grid-template-columns:fit-content(42%) 1fr;gap:2px 10px;margin:0;font-size:.88rem}
.card dt{color:var(--muted)}.card dd{margin:0}
.pill{display:inline-block;padding:0 8px;border-radius:99px;font-size:.78rem;font-weight:700}
.pill.ok{background:var(--ok-bg);color:var(--ok)}.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.opt{background:var(--surface-2);color:var(--muted);vertical-align:middle;font-size:.72rem}
p.count{margin:0 0 4px;font-size:.9rem;font-weight:600}
.files{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto;padding-top:6px}
.files a{border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:.82rem;text-decoration:none;font-weight:600}
.files a small{font-weight:400;color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:.9rem;background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{background:var(--surface-2)}
.tablewrap{overflow-x:auto}
ul.plain{margin:0;padding-left:18px}code{font:.88em ui-monospace,SFMono-Regular,Menlo,monospace}
pre{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 12px;overflow-x:auto}
footer{margin-top:40px;color:var(--muted);font-size:.85rem}
@media (max-width:560px){.grid{grid-template-columns:1fr}}
"""

_DOC_CSS = _CSS + """
article{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:8px 28px 24px}
article img{max-width:100%}article table{display:block;overflow-x:auto}
"""


def _card(project: CadProject, cfg: ReleaseConfig, p: Dict[str, Any]) -> str:
    name = p["part"]
    thumb = (f'<a class="thumb" href="{_u(p["image"])}"><img src="{_u(p["image"])}" alt="{_e(name)}" loading="lazy"></a>'
             if p.get("image") else '<div class="thumb none">no thumbnail</div>')
    pid = project.part_ids.get(name)
    rows = [("Material", p["material"])] if p["material"] else []
    rows += [(k.replace("_", " ").capitalize(), v) for k, v in cfg.notes.get(name, {}).items()]
    sliced = (f'{p["grams"]:.1f} g · {_e(_duration(p.get("minutes")))}' if p.get("grams")
              else '<span class="pill warn">not sliced</span>')
    dl = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in rows) + f"<dt>Each</dt><dd>{sliced}</dd>"
    files = "".join(f'<a href="{_u(f["href"])}" download>{_e(f["kind"])} <small>{_e(f["size"])}</small></a>'
                    for f in p["files"])
    qty = f'<span class="qty">× {p["quantity"]}</span>'
    return (f'<article class="card" id="part-{_e(name)}">{thumb}<div class="body">'
            f'<h3><span>{_e(name.replace("_", " "))}{" <span class=id>" + _e(pid) + "</span>" if pid else ""}</span>{qty}</h3>'
            f"<dl>{dl}</dl><div class=\"files\">{files}</div></div></article>")


def _sum(parts: Sequence[Dict[str, Any]]) -> Tuple[float, float, int]:
    """Grams and minutes for the listed quantities of the sliced parts, and how many parts are sliced."""
    sliced = [p for p in parts if p.get("grams")]
    return (sum(p["grams"] * p["quantity"] for p in sliced), sum((p.get("minutes") or 0) * p["quantity"] for p in sliced),
            len(sliced))


def _build_entry(cfg: ReleaseConfig, parts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not cfg.build:
        return None
    grams, minutes, n = _sum([p for p in parts if p["part"] in cfg.build.parts])
    whole = n == len(cfg.build.parts)
    return {"title": cfg.build.title, "parts": cfg.build.parts, "grams": round(grams, 2) if whole else None,
            "minutes": round(minutes, 1) if whole else None}


def _page(project: CadProject, cfg: ReleaseConfig, revision: str, date: str, parts: List[Dict[str, Any]],
          settings: Dict[str, Any], slice_note: str, docs: List[Dict[str, str]], hardware: List[Dict[str, str]],
          sources: List[str], extra: List[Dict[str, str]], zip_name: Optional[str], git: Dict[str, Any]) -> str:
    missing = [p["part"] for p in parts if not p.get("grams")]
    meta = [("Revision", revision)] + ([("Date", date)] if date else [])
    if git.get("commit"):
        meta.append(("Commit", git["commit"][:10] + (" + uncommitted changes" if git.get("dirty") else "")))
    if zip_name:
        meta.append(("Download", zip_name))
    meta_html = "".join(f"<li>{_e(k)} <b>{_e(v)}</b></li>" for k, v in meta)
    # Totals cover every listed part once at its quantity; groups may hold alternatives and optional parts, so the
    # page never claims this is what one build needs. Each group carries its own count. With pick-one groups a total
    # over every part adds up alternatives nobody prints together, so it is left out (`build` names one build).
    grams, minutes, n_sliced = _sum(parts)
    stats = [(str(len(parts)), "parts in this release"), (str(len(cfg.groups)), "groups" if len(cfg.groups) > 1 else "group")]
    if n_sliced and not any(g.pick_one for g in cfg.groups):
        scope = "every listed part" if not missing else f"the {n_sliced} sliced parts"
        stats += [(f"{grams:.0f} g", f"filament for {scope}"), (_duration(minutes), f"print time for {scope}")]
    build = _build_entry(cfg, parts)
    if build:
        stats.insert(0, (f"{build['grams']:.0f} g", f"{_duration(build['minutes'])} for one build: {build['title']}")
                     if build["grams"] is not None else
                     ("not sliced", f"one build: {build['title']} (slice every part in it for its total)"))
    stats_html = "".join(f'<div class="stat"><b>{_e(a)}</b><span>{_e(b)}</span></div>' for a, b in stats)
    rows = [("Printer", settings.get("printer") or project.printer.name), ("Process", settings.get("process")),
            ("Filament", settings.get("filament")),
            ("Overrides", ", ".join(f"{k} = {v}" for k, v in (settings.get("overrides") or {}).items()))]
    rows = [(k, v) for k, v in rows if v]
    if settings and rows:
        said = " (Bambu Studio presets; the mass and time on the cards were sliced with them)" if n_sliced else \
            " (Bambu Studio presets)"
        settings_html = (f'<div class="settings"><b>Recommended print settings</b>{said}<dl>'
                         + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in rows) + "</dl></div>")
    else:
        settings_html = ('<div class="settings"><b>Print settings:</b> no slicer settings configured (<code>cad.slicer'
                         "</code>); use your slicer's defaults for the material.</div>")
    alert = ""
    if missing:
        why = f" ({_e(slice_note)})" if slice_note else ""
        alert = (f'<div class="alert"><b>Not sliced:</b> {_e(", ".join(missing))}{why}. Their mass and time are not '
                 "in the totals.</div>")
    toc = ['<a href="#parts">Parts</a>'] + (['<a href="#assembly">Assembly</a>'] if docs else []) \
        + (['<a href="#hardware">Hardware</a>'] if hardware else []) + ['<a href="#source">Source</a>']
    body = [f'<header><h1>{_e(cfg.title)}</h1><ul class="meta">{meta_html}</ul></header>',
            f'<div class="stats">{stats_html}</div>', settings_html, alert, f'<nav class="toc">{"".join(toc)}</nav>',
            '<section id="parts">']
    by_name = {p["part"]: p for p in parts}
    for g in cfg.groups:
        members = [by_name[n] for n in g.parts]
        g_grams, g_min, g_sliced = _sum(members)
        count = f"{len(members)} part{'s' if len(members) != 1 else ''}"
        if g.pick_one:
            count += " · print one of these"
        elif g_sliced:
            count += (f" · {g_grams:.0f} g, {_duration(g_min)} for all of them" if g_sliced == len(members)
                      else f" · {g_grams:.0f} g, {_duration(g_min)} for the {g_sliced} sliced")
        flag = (' <span class="pill opt">optional</span>' if g.optional else "") \
            + (' <span class="pill opt">pick one</span>' if g.pick_one else "")
        cards = "".join(_card(project, cfg, m) for m in members)
        body.append(f'<h2>{_e(g.title)}{flag}</h2><p class="count">{_e(count)}</p>'
                    + (f'<p class="lead">{_e(g.note)}</p>' if g.note else "") + f'<div class="grid">{cards}</div>')
    if extra:
        body.append('<h2>More CAD</h2><ul class="plain">' + "".join(
            f'<li><a href="{_u(x["href"])}" download>{_e(x["name"])}</a> <small>{_e(x["size"])}</small></li>' for x in extra)
            + "</ul>")
    body.append("</section>")
    if docs:
        body.append('<section id="assembly"><h2>Assembly</h2><ul class="plain">' + "".join(
            f'<li><a href="{_u(d["href"])}">{_e(d["title"])}</a></li>' for d in docs) + "</ul></section>")
    if hardware:
        cols = list(dict.fromkeys(k for row in hardware for k in row))
        head = "".join(f"<th>{_e(c)}</th>" for c in cols)
        trs = "".join("<tr>" + "".join(f"<td>{_e(r.get(c, ''))}</td>" for c in cols) + "</tr>" for r in hardware)
        body.append(f'<section id="hardware"><h2>Hardware</h2><div class="tablewrap"><table><tr>{head}</tr>{trs}'
                    "</table></div></section>")
    tops: Dict[str, int] = {}
    for s in sources:
        top = s.split("/", 1)[0]
        tops[top] = tops.get(top, 0) + 1
    src_list = "".join(f'<li><a href="{_u("source/" + t)}">{_e(t)}</a>{f" ({n} files)" if n > 1 else ""}</li>'
                       for t, n in sorted(tops.items()))
    lead = "The design's source files."
    if "cad-agent.yaml" in sources:
        lead = ("The build inputs: <code>source/cad-agent.yaml</code> lists the steps that make these files with "
                "<code>cad-agent all</code>. Some projects also need reference files that are not redistributed; "
                "their README says how to fetch them.")
    body.append(f'<section id="source"><h2>Source</h2><p class="lead">{lead}</p><ul class="plain">{src_list}</ul></section>')
    body.append('<footer>Made with cad-agent release · every file is listed with its sha256 in '
                '<a href="manifest.json">manifest.json</a>. CAD only: physical fit is checked by printing.</footer>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(cfg.title)} · rev {_e(revision)}</title>'
            f'<style>{_CSS}</style></head><body><div class="page">{"".join(body)}</div></body></html>\n')


# ----------------------------------------------------------------------------- build

def _prepare(folder: Path) -> None:
    """Empty ``folder`` for a new release; refuse a non-empty folder that is not an earlier release."""
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise FileExistsError(f"{folder} is not a folder; choose another --out")
    if folder.exists():
        manifest = folder / "manifest.json"
        try:
            ours = json.loads(manifest.read_text()).get("format") == MARKER
        except (OSError, json.JSONDecodeError, AttributeError):
            ours = False
        if any(folder.iterdir()) and not ours:
            raise FileExistsError(f"{folder} exists and is not a cad-agent release; choose another --out")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)


def _zip(folder: Path, zip_path: Path) -> None:
    files = sorted((p for p in folder.rglob("*") if p.is_file()), key=lambda p: p.relative_to(folder).as_posix())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info = zipfile.ZipInfo(f"{folder.name}/{p.relative_to(folder).as_posix()}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            with open(p, "rb") as src, z.open(info, "w") as dst:      # streamed: large STEP files stay out of memory
                shutil.copyfileobj(src, dst, 1 << 20)


def build_release(project: CadProject, out: Optional[Path] = None, make_zip: bool = True,
                  revision: Optional[str] = None, date: Optional[str] = None) -> ReleaseResult:
    """Write the release folder (and ``<folder>.zip``). ``revision`` and ``date`` override the config's and the
    project's (``--revision``, ``--date``)."""
    from cadagent.publish.report import load_parts
    from cadagent.make.slicer import _settings

    known, _ = load_parts(project)
    cfg = release_config(project, list(known))
    revision = revision or cfg.revision or project.resolve_revision() or "unversioned"
    root = project.root.resolve()
    git = _git_state(root)
    date, stable = _stable_date(date or cfg.date, git.get("date", ""))
    warnings: List[str] = []
    if git.get("dirty"):
        warnings.append(f"the git tree has uncommitted changes ({', '.join(git['modified'][:5])}"
                        f"{', ...' if len(git['modified']) > 5 else ''}); the release carries them")
    if not stable:
        warnings.append(f"not a git checkout: dated {date} (today); pass --date or set SOURCE_DATE_EPOCH for a "
                        "reproducible release")
    if cfg.left_out:
        warnings.append(f"not released (no group lists them): {', '.join(cfg.left_out)}")
    if cfg.build_gaps:
        warnings.append(f"build {cfg.build.title!r} takes no part from the pick-one group(s) "
                        f"{', '.join(repr(t) for t in cfg.build_gaps)}; it is not a complete build")
    folder = (Path(out) if out else root / "release" / f"{_slug(project.name)}-rev{_slug(revision)}").resolve()
    if root == folder or root.is_relative_to(folder):
        raise CadConfigError(f"release folder {folder} would contain the project")
    _prepare(folder)
    report, current, slice_note = _slice_rows(project)
    # Recommended settings: cad.slicer when the project names them, else those of a current slice report; never the
    # slicer module's defaults on their own (a Prusa project must not be told to use Bambu presets).
    if project.slicer:
        settings = _settings(project)
    elif report and not slice_note:
        settings = {k: report.get(k) for k in ("printer", "process", "filament", "overrides")}
    else:
        settings = {}
    material = cfg.material or str(settings.get("filament") or "").split(" @")[0]
    copied: Dict[str, Path] = {}
    origin: Dict[str, str] = {}      # project path -> its copy in the release (rewrites the pages' links)
    limit = cfg.max_file_mb * 1024 * 1024

    def put(src: Path, rel: str) -> str:
        dst = (folder / rel).resolve()
        if not dst.is_relative_to(folder) or dst == folder:
            raise CadConfigError(f"{rel}: would be written outside the release folder")
        real = src.resolve()
        if not real.is_relative_to(root):
            raise CadConfigError(f"{src}: is outside the project; not released")
        if src.stat().st_size > limit:
            warnings.append(f"{rel} is {_size(src.stat().st_size)} (over cad.release.max_file_mb = {cfg.max_file_mb:g})")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(real, dst)
        copied[rel] = dst
        origin.setdefault(real.relative_to(root).as_posix(), rel)
        return rel

    preview = os.path.relpath(project.preview_dir, project.root)
    parts: List[Dict[str, Any]] = []
    for g in cfg.groups:
        for name in g.parts:
            files = []
            for suffix in CAD_SUFFIXES:
                src = project.exports_dir / f"{name}{suffix}"
                if src.is_file():
                    rel = put(src, f"cad/{name}{suffix}")
                    files.append({"kind": suffix[1:].upper(), "href": rel, "size": _size(src.stat().st_size)})
            if not files:
                raise FileNotFoundError(f"release part {name!r}: no STEP, STL or 3MF in {project.exports_dir}")
            thumb_rel = cfg.thumbnail.format(part=name, preview=preview)
            thumb_src = project.root / thumb_rel
            image = ""
            if thumb_src.is_file() and thumb_src.resolve().is_relative_to(root):
                image = put(thumb_src, f"images/{name}{thumb_src.suffix}")
            else:
                warnings.append(f"{name}: no thumbnail ({thumb_rel})")
            row = current.get(name, {})
            if not row:
                warnings.append(f"{name}: not sliced" + (f" ({slice_note})" if slice_note else
                                                         f" (no current slice-report row for {name}.3mf)"))
            parts.append({"part": name, "group": g.title, "optional": g.optional, "pick_one": g.pick_one, "quantity": cfg.quantities.get(name, 1),
                          "material": material, "files": files, "image": image, "grams": row.get("grams"),
                          "minutes": row.get("minutes")})
    skipped: List[str] = []
    extra = []
    for src in _glob(project.root, cfg.extra_cad, skipped=skipped):
        rel = put(src, f"cad/{src.name}")
        extra.append({"name": src.name, "href": rel, "size": _size(src.stat().st_size)})
    hardware = _hardware_rows(project, cfg.hardware)
    sources = []
    for src in _glob(project.root, cfg.include, cfg.exclude, skipped=skipped):
        if src.resolve().is_relative_to(folder):
            continue
        rel = src.relative_to(project.root).as_posix()
        put(src, f"source/{rel}")
        sources.append(rel)
    # Assembly pages at their project paths under docs/, with the images they link to, so their own relative links
    # keep working; links to files the release carries elsewhere (a part's CAD, a source file) are rewritten in the
    # copy, and Markdown is also rendered to HTML.
    page_files = _glob(project.root, cfg.pages, skipped=skipped)
    texts: Dict[str, str] = {}
    for src in page_files:
        rel = src.relative_to(project.root).as_posix()
        put(src, f"docs/{rel}")
        origin[rel] = f"docs/{rel}"                   # the docs copy, not a source/ copy of the same file
        if src.suffix.lower() in IMAGE_SUFFIXES:
            continue
        try:
            texts[rel] = src.read_text()
        except UnicodeDecodeError:
            continue
        for img in _linked_images(texts[rel], rel, project.root):
            if f"docs/{img}" not in copied:
                put(project.root / img, f"docs/{img}")
            origin[img] = f"docs/{img}"
    warnings.extend(dict.fromkeys(skipped))
    if git:
        others = set((_git(root, "ls-files", "--others", "--exclude-standard", "-z") or "").split("\0")) - {""}
        released = set(sources) | {f.relative_to(project.root).as_posix() for f in page_files} | {
            f.relative_to(project.root).as_posix() for f in _glob(project.root, cfg.extra_cad)}
        git["untracked_released"] = sorted(others & released)
        if git["untracked_released"]:
            warnings.append(f"not in git (the commit cannot rebuild them): {', '.join(git['untracked_released'][:5])}"
                            f"{', ...' if len(git['untracked_released']) > 5 else ''}")
    raw_links = dict(origin)
    html_links = dict(origin)
    html_links.update({rel: f"docs/{rel[:-3]}.html" for rel in texts if rel.endswith(".md")})
    docs = []
    for src in page_files:
        rel = src.relative_to(project.root).as_posix()
        if rel not in texts:
            continue
        text = texts[rel]
        if rel.endswith(".md"):
            title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("#")), rel)
        else:
            m = re.search(r"<title>(.*?)</title>", text, re.S | re.I)
            title = html.unescape(m.group(1).strip()) if m else rel
        raw_at = f"docs/{rel}"
        fixed = _rewrite(text, raw_links, rel, raw_at, markdown_links=rel.endswith(".md"))
        if fixed != text:
            (folder / raw_at).write_text(fixed)
        href = raw_at
        body = _render_markdown(text, html_links, rel, html_links[rel]) if rel.endswith(".md") else None
        if body is not None:
            at = html_links[rel]
            (folder / at).write_text(
                f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
                f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{_DOC_CSS}</style>'
                f'</head><body><div class="page"><p><a href="{_u(_rel_from(at, "index.html"))}">← {_e(cfg.title)}</a></p>'
                f"<article>{body}</article></div></body></html>\n")
            copied[at] = folder / at
            href = at
        docs.append({"title": title, "href": href})
    zip_path = folder.with_name(folder.name + ".zip") if make_zip else None
    (folder / "index.html").write_text(_page(project, cfg, revision, date, parts, settings, slice_note, docs, hardware,
                                             sources, extra, zip_path.name if zip_path else None, git))
    copied["index.html"] = folder / "index.html"
    files = {rel: _sha(p) for rel, p in sorted(copied.items())}
    manifest = {"format": MARKER, "project": project.name, "title": cfg.title, "revision": revision, "date": date,
                "date_reproducible": stable,
                "git": {k: git[k] for k in ("commit", "dirty", "modified", "untracked_released")} if git else None,
                "slicer": {"settings": settings, "report_current": not slice_note,
                           "report_settings": {k: report.get(k) for k in settings} if report else None},
                "parts": [{k: p[k] for k in ("part", "group", "optional", "pick_one", "quantity", "grams", "minutes")}
                          for p in parts],
                "build": _build_entry(cfg, parts),
                "warnings": warnings, "files": files}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if zip_path:
        _zip(folder, zip_path)
    return ReleaseResult(folder, zip_path, files, parts, warnings)
