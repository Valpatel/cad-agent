"""Print release: a browsable page of the printed parts with their CAD files and the source that builds them.

``cad-agent release`` writes ``release/<name>-rev<revision>/`` (or ``--out``) and a zip of it next to the folder:

* ``index.html``: one standalone page (inline CSS, light and dark, no scripts, opens from ``file://``). For each
  printed part: a thumbnail, its quantity, material and recommended print settings, the slicer's mass and time when
  the slice report is current for that part's 3MF, and links to its STEP, STL and 3MF. Then the assembly pages, the
  hardware list and the source;
* ``cad/<part>.{step,stl,3mf}`` and any ``extra_cad`` files;
* ``images/<part>.png``: the thumbnails;
* ``docs/``: the ``pages`` (Markdown is also rendered to HTML when the ``markdown`` package is installed), with the
  images they link to;
* ``source/``: the files matched by ``include`` minus ``exclude``;
* ``manifest.json``: the sha256 of every file above.

Simulation results, render galleries and review evidence stay out unless a glob asks for them: this is what someone
who wants to print and build the design downloads. The review package (``cad-agent package``) is a different thing.

The output is reproducible: the folder is rewritten from scratch, and the zip has sorted entries with fixed dates.

Config ``cad: release:`` (all optional)::

    release:
      title: J501 enclosure                # default: cad.title
      groups:                              # or `parts: [a, b]`; default: every part in the parts file
        - {title: Print these, parts: [base, cover], note: The enclosure set.}
        - {title: Optional, parts: [chimney_cap]}
      quantities: {rail_key: 2}            # default 1
      material: PLA                        # default: the slice report's filament
      notes:                               # shown on the part's card, in this order
        cover: {orientation: roof down, supports: none}
      thumbnail: preview/part-{part}.png   # {part} is replaced
      extra_cad: [exports/assembly.step]   # more CAD files for cad/
      pages: [ASSEMBLY.md, "docs/assembly/*"]
      hardware: docs/hardware.csv          # a CSV, or a list of mappings ({item, qty, ...})
      include: ["cad/**", "tools/**", cad-agent.yaml, "requirements*.txt", README.md, "LICENSE*"]
      exclude: ["**/__pycache__/**", "**/*.pyc"]
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

from cadagent.project import CadConfigError, CadProject

DEFAULT_INCLUDE = ["cad/**", "tools/**", "cad-agent.yaml", "requirements*.txt", "README.md", "LICENSE*"]
DEFAULT_EXCLUDE = ["**/__pycache__/**", "**/*.pyc", "**/.DS_Store"]
DEFAULT_THUMBNAIL = "{preview}/part-{part}.png"
CAD_SUFFIXES = (".step", ".stl", ".3mf")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
MARKER = "cad-agent.release/1"
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_KEYS = {"title", "parts", "groups", "quantities", "material", "notes", "thumbnail", "extra_cad", "pages", "hardware",
         "include", "exclude", "date"}


@dataclass
class Group:
    title: str
    parts: List[str]
    note: str = ""


@dataclass
class ReleaseConfig:
    title: str
    groups: List[Group]
    quantities: Dict[str, int] = field(default_factory=dict)
    material: str = ""
    notes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    thumbnail: str = DEFAULT_THUMBNAIL
    extra_cad: List[str] = field(default_factory=list)
    pages: List[str] = field(default_factory=list)
    hardware: Any = None
    include: List[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE))
    exclude: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    date: str = ""


@dataclass
class ReleaseResult:
    folder: Path
    zip_path: Optional[Path]
    files: Dict[str, str]
    parts: List[Dict[str, Any]]
    warnings: List[str] = field(default_factory=list)


def _strings(value: Any, where: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CadConfigError(f"{where} must be a list of strings")
    return list(value)


def release_config(project: CadProject, known_parts: Sequence[str]) -> ReleaseConfig:
    """Parse and check ``cad.release``; ``known_parts`` (from the parts file) is the default part list."""
    raw = project.release or {}
    if not isinstance(raw, dict):
        raise CadConfigError("cad.release must be a mapping")
    unknown = sorted(set(raw) - _KEYS)
    if unknown:
        raise CadConfigError(f"cad.release: unknown keys {unknown}; known: {sorted(_KEYS)}")
    if raw.get("groups") is not None and raw.get("parts") is not None:
        raise CadConfigError("cad.release: give either parts or groups, not both")
    groups: List[Group] = []
    if raw.get("groups") is not None:
        if not isinstance(raw["groups"], list) or not raw["groups"]:
            raise CadConfigError("cad.release.groups must be a non-empty list of {title, parts, note}")
        for i, g in enumerate(raw["groups"]):
            if not isinstance(g, dict) or not g.get("title") or not g.get("parts"):
                raise CadConfigError(f"cad.release.groups[{i}] needs a title and a non-empty parts list")
            groups.append(Group(str(g["title"]), _strings(g["parts"], f"cad.release.groups[{i}].parts"),
                                str(g.get("note") or "")))
    else:
        parts = _strings(raw.get("parts"), "cad.release.parts") or list(known_parts)
        if not parts:
            raise CadConfigError("cad.release: no parts (list them, or build first so the parts file exists)")
        groups.append(Group("Parts", parts))
    seen: List[str] = []
    for g in groups:
        for p in g.parts:
            if p in seen:
                raise CadConfigError(f"cad.release: part {p!r} is listed twice")
            seen.append(p)
    quantities = raw.get("quantities") or {}
    if not isinstance(quantities, dict) or not all(isinstance(v, int) and v >= 1 for v in quantities.values()):
        raise CadConfigError("cad.release.quantities must map part -> a whole number >= 1")
    notes = raw.get("notes") or {}
    if not isinstance(notes, dict) or not all(isinstance(v, dict) for v in notes.values()):
        raise CadConfigError("cad.release.notes must map part -> {label: text}")
    for name in list(quantities) + list(notes):
        if name not in seen:
            raise CadConfigError(f"cad.release: {name!r} has a quantity or notes but is not a released part")
    hardware = raw.get("hardware")
    if hardware is not None and not isinstance(hardware, (str, list)):
        raise CadConfigError("cad.release.hardware must be a CSV path or a list of mappings")
    if isinstance(hardware, list) and not all(isinstance(r, dict) for r in hardware):
        raise CadConfigError("cad.release.hardware rows must be mappings")
    return ReleaseConfig(
        title=str(raw.get("title") or project.title or project.name),
        groups=groups,
        quantities={str(k): int(v) for k, v in quantities.items()},
        material=str(raw.get("material") or ""),
        notes={str(k): {str(a): str(b) for a, b in v.items()} for k, v in notes.items()},
        thumbnail=str(raw.get("thumbnail") or DEFAULT_THUMBNAIL),
        extra_cad=_strings(raw.get("extra_cad"), "cad.release.extra_cad"),
        pages=_strings(raw.get("pages"), "cad.release.pages"),
        hardware=hardware,
        include=_strings(raw["include"], "cad.release.include") if "include" in raw else list(DEFAULT_INCLUDE),
        exclude=_strings(raw["exclude"], "cad.release.exclude") if "exclude" in raw else list(DEFAULT_EXCLUDE),
        date=str(raw.get("date") or ""),
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


def _glob(root: Path, patterns: Sequence[str], exclude: Sequence[str] = ()) -> List[Path]:
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
            out.setdefault(rel, p)
    return [out[k] for k in sorted(out)]


def _git_date(root: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%cs"], capture_output=True, text=True,
                           timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _size(n: int) -> str:
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


def _slice_rows(project: CadProject) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """The slice report's settings and its per-part rows that are still current (3MF sha256 unchanged)."""
    path = project.exports_dir / "slice-report.json"
    try:
        rep = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}, {}
    current = {}
    for name, row in (rep.get("parts") or {}).items():
        f = project.exports_dir / f"{name}.3mf"
        if isinstance(row, dict) and row.get("grams") and f.is_file() and _sha(f) == row.get("sha256"):
            current[name] = row
    return rep, current


def _hardware_rows(project: CadProject, hardware: Any) -> List[Dict[str, str]]:
    if hardware is None:
        return []
    if isinstance(hardware, list):
        return [{str(k): str(v) for k, v in row.items()} for row in hardware]
    path = project.root / hardware
    if not path.is_file():
        raise CadConfigError(f"cad.release.hardware: {hardware} not found")
    with open(path, newline="") as fh:
        return [{k: (v or "") for k, v in row.items()} for row in csv.DictReader(fh)]


# ----------------------------------------------------------------------------- pages

def _render_markdown(text: str, placed: Dict[str, str], src_rel: str, at: str) -> Optional[str]:
    """Markdown -> HTML (None without the ``markdown`` package). Relative links to files that are in the release
    (``placed``: project path -> release path) are rewritten for the rendered page at release path ``at``."""
    try:
        import markdown  # type: ignore
    except ImportError:
        return None
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"], output_format="html")
    base = Path(src_rel).parent

    def fix(m: re.Match) -> str:
        attr, url = m.group(1), m.group(2)
        if re.match(r"^[a-z][a-z0-9+.-]*:|^#|^/", url):
            return m.group(0)
        path, _, frag = url.partition("#")
        target = _norm((base / html.unescape(path)).as_posix())
        if target in placed:
            return f'{attr}="{_e(_rel_from(at, placed[target]))}{"#" + frag if frag else ""}"'
        return m.group(0)

    return re.sub(r'(href|src)="([^"]+)"', fix, body)


def _norm(rel: str) -> str:
    parts: List[str] = []
    for bit in rel.split("/"):
        if bit in ("", "."):
            continue
        if bit == "..":
            if parts:
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
    """Project-relative images a Markdown or HTML page links to that exist in the project."""
    base = Path(src_rel).parent
    out = []
    for url in re.findall(r'!\[[^\]]*\]\(([^)\s]+)|(?:src|href)="([^"]+)"', text):
        u = url[0] or url[1]
        if re.match(r"^[a-z][a-z0-9+.-]*:|^#|^/", u):
            continue
        rel = _norm((base / u.split("#")[0]).as_posix())
        if Path(rel).suffix.lower() in IMAGE_SUFFIXES and (root / rel).is_file():
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
.card dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 10px;margin:0;font-size:.88rem}
.card dt{color:var(--muted)}.card dd{margin:0}
.pill{display:inline-block;padding:0 8px;border-radius:99px;font-size:.78rem;font-weight:700}
.pill.ok{background:var(--ok-bg);color:var(--ok)}.pill.warn{background:var(--warn-bg);color:var(--warn)}
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
    thumb = (f'<a class="thumb" href="{_e(p["image"])}"><img src="{_e(p["image"])}" alt="{_e(name)}" loading="lazy"></a>'
             if p.get("image") else '<div class="thumb none">no thumbnail</div>')
    pid = project.part_ids.get(name)
    rows = [("Material", p["material"])] if p["material"] else []
    rows += [(k.replace("_", " ").capitalize(), v) for k, v in cfg.notes.get(name, {}).items()]
    if p.get("grams"):
        sliced = f'{p["grams"]:.1f} g · {_duration(p.get("minutes"))}'
    else:
        sliced = '<span class="pill warn">not sliced</span>'
    dl = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in rows) + f"<dt>Each</dt><dd>{sliced}</dd>"
    files = "".join(f'<a href="{_e(f["href"])}" download>{_e(f["kind"])} <small>{_e(f["size"])}</small></a>'
                    for f in p["files"])
    qty = f'<span class="qty">× {p["quantity"]}</span>'
    return (f'<article class="card" id="part-{_e(name)}">{thumb}<div class="body">'
            f'<h3><span>{_e(name.replace("_", " "))}{" <span class=id>" + _e(pid) + "</span>" if pid else ""}</span>{qty}</h3>'
            f"<dl>{dl}</dl><div class=\"files\">{files}</div></div></article>")


def _page(project: CadProject, cfg: ReleaseConfig, revision: str, date: str, parts: List[Dict[str, Any]],
          report: Dict[str, Any], docs: List[Dict[str, str]], hardware: List[Dict[str, str]],
          sources: List[str], extra: List[Dict[str, str]], zip_name: Optional[str]) -> str:
    total_q = sum(p["quantity"] for p in parts)
    sliced = [p for p in parts if p.get("grams")]
    grams = sum(p["grams"] * p["quantity"] for p in sliced)
    minutes = sum((p.get("minutes") or 0) * p["quantity"] for p in sliced)
    missing = [p["part"] for p in parts if not p.get("grams")]
    meta = [("Revision", revision)] + ([("Date", date)] if date else [])
    meta_html = "".join(f"<li>{_e(k)} <b>{_e(v)}</b></li>" for k, v in meta)
    if zip_name:
        meta_html += f'<li><a href="../{_e(zip_name)}">{_e(zip_name)}</a></li>'
    stats = [(str(len(parts)), "different parts"), (str(total_q), "pieces to print")]
    if sliced:
        stats += [(f"{grams:.0f} g", "filament" + (" (sliced parts)" if missing else "")),
                  (_duration(minutes), "print time" + (" (sliced parts)" if missing else ""))]
    stats_html = "".join(f'<div class="stat"><b>{_e(a)}</b><span>{_e(b)}</span></div>' for a, b in stats)
    settings = [("Printer", report.get("printer") or project.printer.name),
                ("Process", report.get("process")), ("Filament", report.get("filament")),
                ("Overrides", ", ".join(f"{k} = {v}" for k, v in (report.get("overrides") or {}).items())),
                ("Slicer", report.get("slicer"))]
    settings = [(k, v) for k, v in settings if v]
    settings_html = ""
    if settings:
        settings_html = ('<div class="settings"><b>Recommended print settings</b> (the slicer estimates below use these)'
                         "<dl>" + "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in settings) + "</dl>"
                         + (f'<p class="lead" style="margin:8px 0 0">{_e(report["note"])}</p>' if report.get("note") else "")
                         + "</div>")
    alert = ""
    if missing:
        alert = (f'<div class="alert"><b>Not sliced:</b> {_e(", ".join(missing))}. Their mass and time are not in the '
                 "totals; the slice report is missing them or was made from different files.</div>")
    toc = ['<a href="#parts">Parts</a>'] + (['<a href="#assembly">Assembly</a>'] if docs else []) \
        + (['<a href="#hardware">Hardware</a>'] if hardware else []) + ['<a href="#source">Source</a>']
    body = [f'<header><h1>{_e(cfg.title)}</h1><ul class="meta">{meta_html}</ul></header>',
            f'<div class="stats">{stats_html}</div>', settings_html, alert, f'<nav class="toc">{"".join(toc)}</nav>',
            '<section id="parts">']
    by_name = {p["part"]: p for p in parts}
    for g in cfg.groups:
        cards = "".join(_card(project, cfg, by_name[n]) for n in g.parts)
        body.append(f"<h2>{_e(g.title)}</h2>" + (f'<p class="lead">{_e(g.note)}</p>' if g.note else "")
                    + f'<div class="grid">{cards}</div>')
    if extra:
        body.append('<h2>More CAD</h2><ul class="plain">' + "".join(
            f'<li><a href="{_e(x["href"])}" download>{_e(x["name"])}</a> <small>{_e(x["size"])}</small></li>' for x in extra)
            + "</ul>")
    body.append("</section>")
    if docs:
        body.append('<section id="assembly"><h2>Assembly</h2><ul class="plain">' + "".join(
            f'<li><a href="{_e(d["href"])}">{_e(d["title"])}</a></li>' for d in docs) + "</ul></section>")
    if hardware:
        cols = list(dict.fromkeys(k for row in hardware for k in row))
        head = "".join(f"<th>{_e(c)}</th>" for c in cols)
        rows = "".join("<tr>" + "".join(f"<td>{_e(r.get(c, ''))}</td>" for c in cols) + "</tr>" for r in hardware)
        body.append(f'<section id="hardware"><h2>Hardware</h2><div class="tablewrap"><table><tr>{head}</tr>{rows}'
                    "</table></div></section>")
    tops: Dict[str, int] = {}
    for s in sources:
        top = s.split("/", 1)[0] if "/" in s else s
        tops[top] = tops.get(top, 0) + 1
    src_list = "".join(f'<li><a href="source/{_e(t)}">{_e(t)}</a>{f" ({n} files)" if n > 1 else ""}</li>'
                       for t, n in sorted(tops.items()))
    body.append('<section id="source"><h2>Source</h2><p class="lead">The code and configuration that build these parts. '
                "Rebuild with <code>cad-agent all</code> in the <code>source</code> folder (see its README).</p>"
                f'<ul class="plain">{src_list}</ul></section>')
    body.append(f"<footer>Made with cad-agent release · every file is listed with its sha256 in "
                f'<a href="manifest.json">manifest.json</a>. CAD only: physical fit is checked by printing.</footer>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{_e(cfg.title)} · rev {_e(revision)}</title>'
            f'<style>{_CSS}</style></head><body><div class="page">{"".join(body)}</div></body></html>\n')


# ----------------------------------------------------------------------------- build

def _prepare(folder: Path) -> None:
    """Empty ``folder`` for a new release; refuse a non-empty folder that is not an earlier release."""
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
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info = zipfile.ZipInfo(f"{folder.name}/{p.relative_to(folder).as_posix()}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, p.read_bytes())


def build_release(project: CadProject, out: Optional[Path] = None, make_zip: bool = True) -> ReleaseResult:
    from cadagent.report import load_parts

    known, _ = load_parts(project)
    cfg = release_config(project, list(known))
    revision = project.resolve_revision() or "unversioned"
    date = cfg.date or _git_date(project.root) or datetime.date.today().isoformat()
    folder = Path(out) if out else project.root / "release" / f"{_slug(project.name)}-rev{_slug(revision)}"
    folder = folder.resolve()
    if project.root.resolve() == folder or project.root.resolve().is_relative_to(folder):
        raise CadConfigError(f"release folder {folder} would contain the project")
    _prepare(folder)
    warnings: List[str] = []
    report, current = _slice_rows(project)
    material = cfg.material or str(report.get("filament") or "").split(" @")[0]
    copied: Dict[str, Path] = {}

    def put(src: Path, rel: str) -> str:
        dst = folder / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied[rel] = dst
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
            thumb_src = project.root / cfg.thumbnail.format(part=name, preview=preview)
            image = put(thumb_src, f"images/{name}{thumb_src.suffix}") if thumb_src.is_file() else ""
            if not image:
                warnings.append(f"{name}: no thumbnail ({cfg.thumbnail.format(part=name, preview=preview)})")
            row = current.get(name, {})
            if not row:
                warnings.append(f"{name}: not sliced (no current slice-report row for {name}.3mf)")
            parts.append({"part": name, "group": g.title, "quantity": cfg.quantities.get(name, 1), "material": material,
                          "files": files, "image": image, "grams": row.get("grams"), "minutes": row.get("minutes")})
    extra = []
    for src in _glob(project.root, cfg.extra_cad):
        rel = put(src, f"cad/{src.name}")
        extra.append({"name": src.name, "href": rel, "size": _size(src.stat().st_size)})
    # Assembly pages under docs/ (a leading docs/ is not repeated), with the images they link to; Markdown is also
    # rendered to HTML, its links pointing at the release copies.
    def doc_dest(rel: str) -> str:
        return "docs/" + (rel[len("docs/"):] if rel.startswith("docs/") else rel)

    page_files = _glob(project.root, cfg.pages)
    placed: Dict[str, str] = {}
    texts: Dict[str, str] = {}
    for src in page_files:
        rel = src.relative_to(project.root).as_posix()
        placed[rel] = doc_dest(rel)
        if src.suffix.lower() not in IMAGE_SUFFIXES:
            try:
                texts[rel] = src.read_text()
            except UnicodeDecodeError:
                continue
            for img in _linked_images(texts[rel], rel, project.root):
                placed.setdefault(img, doc_dest(img))
    for rel, dest in sorted(placed.items()):
        put(project.root / rel, dest)
    links = dict(placed)
    rendered: Dict[str, str] = {}
    for rel, text in texts.items():
        if rel.endswith(".md"):
            at = placed[rel][:-3] + ".html"
            body = _render_markdown(text, links, rel, at)
            if body is not None:
                rendered[rel] = (at, body)
                links[rel] = at
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
        href = placed[rel]
        if rel in rendered:
            at, body = rendered[rel]
            body = _render_markdown(text, links, rel, at)          # again, now that every page's HTML name is known
            back = _rel_from(at, "index.html")
            (folder / at).write_text(
                f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
                f'content="width=device-width,initial-scale=1"><title>{_e(title)}</title><style>{_DOC_CSS}</style>'
                f'</head><body><div class="page"><p><a href="{_e(back)}">← {_e(cfg.title)}</a></p>'
                f"<article>{body}</article></div></body></html>\n")
            copied[at] = folder / at
            href = at
        docs.append({"title": title, "href": href})
    hardware = _hardware_rows(project, cfg.hardware)
    sources = []
    for src in _glob(project.root, cfg.include, cfg.exclude):
        rel = src.relative_to(project.root).as_posix()
        if src.resolve().is_relative_to(folder):
            continue
        put(src, f"source/{rel}")
        sources.append(rel)
    zip_path = folder.with_name(folder.name + ".zip") if make_zip else None
    (folder / "index.html").write_text(_page(project, cfg, revision, date, parts, report, docs, hardware, sources, extra,
                                             zip_path.name if zip_path else None))
    copied["index.html"] = folder / "index.html"
    files = {rel: _sha(p) for rel, p in sorted(copied.items())}
    manifest = {"format": MARKER, "project": project.name, "title": cfg.title, "revision": revision, "date": date,
                "parts": [{k: p[k] for k in ("part", "group", "quantity", "grams", "minutes")} for p in parts],
                "files": files}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if zip_path:
        _zip(folder, zip_path)
    return ReleaseResult(folder, zip_path, files, parts, warnings)
