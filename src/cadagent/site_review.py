"""Review pages of the project site: the design review by section, the requirements table and the integrity gates.

Built by ``cad-agent site`` for a project that uses the dossier or the gates (a ``dossier:`` or ``gates:`` key in
``cad-agent.yaml``); a project without either sees no change. Pages, under ``site/review/``:

- ``index.html``: one row per dossier section (status, requirements, parts, gate state, review state), the lint
  findings, and links to everything below;
- ``section-<id>.html``: one page per section: its requirements with status and verifying checks, its interfaces,
  every part card (function, material, decisions with the alternatives rejected, checks with their evidence, the
  status ladder draft → built → gated → reviewed → signed_off and a stale badge when the geometry changed since the
  last review), the gate findings that name its parts with their witnesses, and the review packet's images
  (``exports/review/<section>/manifest.json``) with the reviewer's findings beside them;
- ``requirements.html``: every requirement with its status, the sections it traces to, its checks and waivers;
- ``gates.html``: one row per gate (status, counts, stale or missing, links to the verdict's ``.md`` and ``.json``),
  the connectivity graph drawn as SVG from ``exports/gates/connectivity.dot`` (``connectivity.svg`` beside the page),
  and each gate's findings, exclusions and assumptions.

**What is read.** Every status comes from the files the pipeline computes, never from the YAML:
``exports/dossier-status.json`` (``cad-agent dossier``/``cad-agent gates``), the verdicts in ``exports/gates/`` (with
their stale and missing state from ``cadagent.gates.run.gate_rows``) and the reviewer records the status file names.
The YAML dossier is loaded (``strict=False``) only for the words: functions, purposes, decisions and their
alternatives, interfaces, requirement sources and waiver rationales. When the YAML is newer than the status file the
pages say so. Everything is optional: a missing file shows as a gap with the command that makes it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

REVIEW_DIR = "review"
STATUS_FILE = "dossier-status.json"
LADDER = ("draft", "built", "gated", "reviewed", "signed_off")
PACKET_DIR = "review"            # exports/review/<section>/manifest.json (the render packet, plan T10)

CSS = """
.ladder{display:flex;flex-wrap:wrap;gap:0;list-style:none;padding:0;margin:8px 0;font-size:12px}
.ladder li{padding:2px 10px;border:1px solid var(--line);margin-right:-1px;color:var(--muted);background:var(--card)}
.ladder li:first-child{border-radius:99px 0 0 99px}.ladder li:last-child{border-radius:0 99px 99px 0}
.ladder li.on{background:var(--okbg);color:var(--ok);font-weight:700}.ladder li.at{outline:2px solid var(--ok);z-index:1;position:relative}
.ladder li.cap{background:var(--failbg);color:var(--fail)}
.pill.signed_off,.pill.verified,.pill.pass,.pill.gated,.pill.reviewed{background:var(--okbg);color:var(--ok)}
.pill.built,.pill.stale,.pill.unverified,.pill.warn{background:var(--warnbg);color:var(--warn)}
.pill.draft,.pill.unrun,.pill.na,.pill.skipped,.pill.not_tested,.pill.waived,.pill.none{background:var(--nextbg);color:var(--muted)}
.pill.fail,.pill.failed,.pill.missing,.pill.unknown,.pill.invalid,.pill.error{background:var(--failbg);color:var(--fail)}
a.pill{text-decoration:none}.pill+.pill{margin-left:4px}
.badge{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:6px;background:var(--failbg);color:var(--fail)}
.banner{background:var(--warnbg);border:1px solid var(--warn);border-radius:12px;padding:10px 14px;margin:16px 0}
.banner.bad{background:var(--failbg);border-color:var(--fail)}
.partcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin:12px 0}
.partcard h3{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.partcard dl{display:grid;grid-template-columns:150px 1fr;
gap:4px 12px;margin:8px 0}.partcard dt{color:var(--muted);font-size:14px}.partcard dd{margin:0}
.dec{border-left:3px solid var(--accent);padding:2px 12px;margin:8px 0}.dec ul{margin:4px 0;padding-left:20px}
.muted{color:var(--muted)}.small{font-size:13px}code.hash{font-size:12px;color:var(--muted)}
details.witness summary{cursor:pointer;color:var(--muted);font-size:13px}details.witness pre{max-height:320px;overflow:auto;
background:var(--bg);padding:8px;border-radius:8px;font-size:12px}
.packet{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:14px}
.packet figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.packet img{display:block;width:100%;height:auto;background:#eff1ed}.packet figcaption{padding:8px 12px;font-size:14px}
.graph{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;overflow:auto}
.graph svg{max-width:100%;height:auto}.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--muted);margin:8px 0}
.subnav{margin:14px 0 0}.packet+h3,.rf{margin-top:18px}
@media (max-width:640px){.partcard dl{grid-template-columns:1fr}.packet{grid-template-columns:1fr}}
"""


# --------------------------------------------------------------------------------------------------- data

@dataclass
class ReviewData:
    """Everything the review pages show, read from files (kernel-free)."""
    root: Path
    exports: Path
    has_dossier: bool
    status: Optional[Dict[str, Any]] = None        # exports/dossier-status.json
    status_error: str = ""
    dossier: Any = None                            # the YAML, for the words only (cadagent.dossier.Dossier)
    dossier_error: str = ""
    geometry: Optional[Dict[str, Any]] = None
    verdicts: Dict[str, Dict[str, Any]] = field(default_factory=dict)   # gate -> verdict (dossier-lint included)
    rows: List[Dict[str, Any]] = field(default_factory=list)            # cadagent.gates.run.gate_rows
    yaml_newer: List[str] = field(default_factory=list)                 # dossier files newer than the status file

    # ---- lookups
    def section_ids(self) -> List[str]:
        ids = list((self.status or {}).get("sections", {}))
        for sid in (getattr(self.dossier, "sections", None) or {}):
            if sid not in ids:
                ids.append(sid)
        return ids

    def section_row(self, sid: str) -> Dict[str, Any]:
        return ((self.status or {}).get("sections") or {}).get(sid) or {}

    def part_row(self, pid: str) -> Dict[str, Any]:
        return ((self.status or {}).get("parts") or {}).get(pid) or {}

    def section_yaml(self, sid: str) -> Any:
        return (getattr(self.dossier, "sections", None) or {}).get(sid)

    def part_ids(self, sid: str) -> List[str]:
        row = self.section_row(sid)
        if row.get("parts"):
            return list(row["parts"])
        sec = self.section_yaml(sid)
        return [c.id for c in sec.parts] if sec is not None else []

    def section_of_part(self) -> Dict[str, str]:
        return {pid: sid for sid in self.section_ids() for pid in self.part_ids(sid)}


def _read_json(path: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    if not path.is_file():
        return None, f"{path.name} not written yet"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return None, f"{path.name} unreadable: {exc}"
    return (data, "") if isinstance(data, dict) else (None, f"{path.name} is not a JSON object")


def enabled(project: Any) -> bool:
    """A project gets the review pages when it has a ``dossier:`` or a ``gates:`` key."""
    from cadagent.gates.run import enabled as gates_enabled
    return gates_enabled(project)


def collect(project: Any) -> ReviewData:
    """Read the status file, the verdicts, the gate rows and the YAML dossier (for its words)."""
    from cadagent.gates.run import GEOMETRY_FILE, gate_rows
    root = Path(project.root).resolve()
    exports = Path(project.exports_dir)
    data = ReviewData(root=root, exports=exports, has_dossier=bool(getattr(project, "dossier", None)))
    if data.has_dossier:
        status_path = exports / STATUS_FILE
        data.status, data.status_error = _read_json(status_path)
        try:
            from cadagent.dossier import load_project_dossier
            data.dossier = load_project_dossier(project, strict=False)
        except Exception as exc:         # noqa: BLE001 (a broken dossier is shown, never fatal to the site)
            data.dossier_error = str(exc)
        if status_path.is_file():
            built = status_path.stat().st_mtime
            data.yaml_newer = [_rel(p, root) for p in _dossier_files(project, data.dossier)
                               if p.stat().st_mtime > built]
    try:
        from cadagent.gates.run import GatesConfigError, gates_config
        geo_path = gates_config(project).geometry
    except Exception:                    # noqa: BLE001 (the rows report a bad configuration)
        geo_path = exports / GEOMETRY_FILE
    data.geometry, _ = _read_json(geo_path)
    gates_dir = exports / "gates"
    if gates_dir.is_dir():
        for p in sorted(gates_dir.glob("*.json")):
            v, _ = _read_json(p)
            if v is not None:
                data.verdicts[p.stem] = v
    try:
        data.rows = gate_rows(project)
    except Exception as exc:             # noqa: BLE001
        data.rows = [{"name": "gates", "status": "fail", "message": f"could not read the gates: {exc}"}]
    return data


def _dossier_files(project: Any, dossier: Any = None) -> List[Path]:
    """The files the YAML dossier is made of (``project.yaml``, every section and card file it loaded, the decisions
    file) and its reviewer records (``reviews/*.json`` beside ``project.yaml``). Never a walk of the project."""
    path = getattr(project, "dossier", None)
    if not path:
        return []
    root = Path(project.root).resolve()
    main = Path(path).resolve()
    if dossier is None:
        try:
            from cadagent.dossier import load_project_dossier
            dossier = load_project_dossier(project, strict=False)
        except Exception:                # noqa: BLE001 (then only project.yaml and the records are watched)
            dossier = None
    names = {main}
    if dossier is not None:
        items = [*dossier.requirements.values(), *dossier.sections.values(), *dossier.parts.values(),
                 *dossier.interfaces.values(), *dossier.decisions.values(), *dossier.assembly]
        for item in items:
            where = getattr(item, "where", None)
            if where is not None and where.file:
                names.add((root / where.file).resolve())
    reviews = main.parent / "reviews"
    if reviews.is_dir():
        names |= {p.resolve() for p in reviews.glob("*.json")}
    return sorted(p for p in names if p.is_file())


def sources(project: Any) -> List[Path]:
    """Files the review pages are built from, for ``cad-agent site --serve`` to rebuild when one changes."""
    exports = Path(project.exports_dir)
    files = _dossier_files(project)
    for p in [exports / STATUS_FILE, exports / "dossier-geometry.json"]:
        if p.is_file():
            files.append(p)
    for pattern in ("gates/*", f"{PACKET_DIR}/*/manifest.json"):
        files += [p for p in sorted(exports.glob(pattern)) if p.is_file()]
    return files


def nav_entries(project: Any) -> List[Dict[str, str]]:
    """Top-bar tabs for the review pages (hrefs from the project root)."""
    if not enabled(project):
        return []
    base = f"site/{REVIEW_DIR}/"
    out = []
    if getattr(project, "dossier", None):
        out += [{"id": "review", "title": "Review", "href": base},
                {"id": "requirements", "title": "Requirements", "href": base + "requirements.html"}]
    out.append({"id": "gates", "title": "Gates", "href": base + "gates.html"})
    return out


# --------------------------------------------------------------------------------------------------- helpers

def _e(v: Any) -> str:
    from cadagent.site import _e as esc
    return esc(v)


def _int(v: Any) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "x"


def _rel(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def section_page(sid: str) -> str:
    return f"section-{_slug(sid)}.html"


def _pill(status: Any, text: Optional[str] = None, href: str = "", title: str = "") -> str:
    s = str(status or "none")
    cls = _slug(s).replace("-", "_")
    t = f' title="{_e(title)}"' if title else ""
    label = _e(text if text is not None else s.replace("_", " "))
    if href:
        return f'<a class="pill {cls}" href="{_e(href)}"{t}>{label}</a>'
    return f'<span class="pill {cls}"{t}>{label}</span>'


def _ladder(status: str) -> str:
    if status not in LADDER:
        return f'<p class="small muted">Status not computed yet ({_e(status or "no status file")}).</p>'
    at = LADDER.index(status)
    items = []
    for i, s in enumerate(LADDER):
        cls = "on" if i <= at else ""
        if i == at:
            cls += " at"
        items.append(f'<li class="{cls.strip()}">{_e(s.replace("_", " "))}</li>')
    return f'<ol class="ladder" aria-label="status: {_e(status)}">{"".join(items)}</ol>'


class _Links:
    """Hrefs from a page in ``site/review/`` to project files, only for files that exist (every link resolves)."""

    def __init__(self, root: Path):
        self.root = root
        self.prefix = "../../"

    def rel(self, path: Any) -> str:
        """A project-relative path for ``path`` (relative already, or absolute inside the root); "" outside it."""
        text = str(path or "")
        if not text:
            return ""
        p = Path(text)
        if p.is_absolute():
            try:
                return p.resolve().relative_to(self.root).as_posix()
            except ValueError:
                return ""
        return text

    def file(self, rel: Any, text: Optional[str] = None, *, line: Any = None) -> str:
        given = str(rel or "")
        rel = self.rel(given)
        if given and not rel:
            return f"<code>{_e(text if text is not None else given)}</code>"
        shown = _e(text if text is not None else (f"{rel}:{line}" if line else rel))
        path = (self.root / rel).resolve() if rel else None
        if path is None or not rel or not (path == self.root or self.root in path.parents) or not path.exists():
            return f"<code>{shown}</code>" if rel else ""
        return f'<a href="{_e(self.prefix + rel)}"><code>{shown}</code></a>'

    def maybe(self, rel: str, text: Optional[str] = None) -> str:
        """A link when the file exists, else nothing."""
        return self.file(rel, text) if self.exists(rel) else ""

    def exists(self, rel: str) -> bool:
        rel = self.rel(rel)
        if not rel:
            return False
        p = (self.root / rel).resolve()
        return (self.root in p.parents) and p.exists()


def _check_href(check: Mapping[str, Any], links: _Links) -> str:
    cid = str(check.get("id", ""))
    if cid.startswith("gate:"):
        return f"gates.html#gate-{_slug(cid[5:])}"
    f = links.rel(check.get("file"))
    return links.prefix + f if f and links.exists(f) else ""


def _check_pills(checks: Sequence[Mapping[str, Any]], links: _Links) -> str:
    if not checks:
        return '<span class="muted">none</span>'
    return " ".join(_pill(c.get("status"), f'{c.get("id")} · {c.get("status")}', _check_href(c, links),
                          str(c.get("message", ""))) for c in checks)


_WITNESS_KEY = re.compile(r"(gap|depth|thick|wall|clear|volume|outside|overlap|engag|angle|dist|tip|reach|pose|"
                          r"point|witness|min|max|count|state)", re.I)


def witness_summary(evidence: Any, limit: int = 6) -> str:
    """A one-line digest of a finding's evidence: the measured values and witness points, by their key paths."""
    out: List[str] = []

    def num(v: Any) -> str:
        return f"{v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)

    def walk(v: Any, path: str) -> None:
        if len(out) >= limit:
            return
        key = path.rsplit(".", 1)[-1]
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}.{k}" if path else str(k))
        elif isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v):
            if _WITNESS_KEY.search(key):
                out.append(f"{path} ({', '.join(num(x) for x in v)})")
        elif isinstance(v, list):
            for i, x in enumerate(v[:3]):
                walk(x, f"{path}[{i}]")
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and _WITNESS_KEY.search(key):
            out.append(f"{path} {num(v)}")
        elif isinstance(v, str) and key in ("state", "part", "neighbour", "a", "b") and len(v) < 40:
            out.append(f"{path} {v}")
    walk(evidence, "")
    return " · ".join(out)


def _witness(evidence: Any) -> str:
    if not evidence:
        return '<span class="muted small">no witness recorded</span>'
    text = json.dumps(evidence, indent=1, default=str)
    if len(text) > 6000:
        text = text[:6000] + "\n… (truncated; the full witness is in the verdict JSON)"
    summary = witness_summary(evidence)
    return (f'<details class="witness"><summary>{_e(summary or "witness")}</summary><pre>{_e(text)}</pre></details>')


def parts_named(names: Iterable[Any], cards: Set[str], geometry: Optional[Mapping[str, Any]]) -> Set[str]:
    """The part cards a gate finding's ``parts`` refer to (as the dossier lint reads them): a part or one of its
    instances (``ball#3``), both parts of a fastener (what it clamps and what it threads into), a cavity's part."""
    geo = geometry or {}
    geo_parts = geo.get("parts") or {}
    fasteners, cavities = geo.get("fasteners") or {}, geo.get("cavities") or {}
    out: Set[str] = set()
    for name in names:
        o = str(name).split("#", 1)[0]
        if o in cards or o in geo_parts:
            out.add(o)
        elif isinstance(fasteners.get(o), dict):
            out |= {fasteners[o].get("clamps"), fasteners[o].get("into")} - {None}
        elif isinstance(cavities.get(o), dict) and cavities[o].get("part"):
            out.add(cavities[o]["part"])
    return out


def gate_state(row: Mapping[str, Any], verdict: Optional[Mapping[str, Any]]) -> str:
    """pass, warn, fail, stale, missing, invalid, na or skipped, from a ``gate_rows`` row."""
    msg = str(row.get("message", ""))
    if row.get("status") == "skip":
        return "na" if msg.startswith("not applicable") else "skipped"
    if row.get("status") == "pass":
        return "warn" if (verdict or {}).get("status") == "warn" else "pass"
    if msg.startswith("stale"):
        return "stale"
    if msg.startswith("not run"):
        return "missing"
    if msg.startswith(("unreadable", "no geometry")) or "not a gate verdict" in msg:
        return "invalid"
    return "fail"


def gate_states(data: ReviewData) -> Dict[str, str]:
    out = {}
    for row in data.rows:
        name = str(row.get("name", ""))
        if name.startswith("gate "):
            g = name[5:]
            out[g] = gate_state(row, data.verdicts.get(g))
    return out


def _counts(v: Optional[Mapping[str, Any]]) -> str:
    c = (v or {}).get("counts") or {}
    if not c:
        return ""
    return f'{_e(c.get("pass", 0))} pass · {_e(c.get("warn", 0))} warn · {_e(c.get("fail", 0))} fail'


def _decision_html(dec: Any, status_row: Optional[Mapping[str, Any]] = None) -> str:
    alts = "".join(f'<li>{_e(a.option)}: <span class="muted">rejected: {_e(a.rejected) if a.rejected else "<b>no reason given</b>"}</span></li>'
                   if a.rejected else f"<li>{_e(a.option)}: <b>no reason given</b></li>" for a in dec.alternatives)
    complete = (status_row or {}).get("complete")
    flag = "" if complete in (None, True) else ' <span class="badge">incomplete</span>'
    src = dec.source
    quote = f'<p class="small muted">“{_e(src.quote)}”{" (" + _e(src.ref) + ")" if src.ref else ""}</p>' if src and src.quote else ""
    return (f'<div class="dec" id="dec-{_slug(dec.id)}"><b>{_e(dec.id)}</b> {_pill(dec.status)}{flag} '
            f'{_e(dec.title) + " · " if dec.title else ""}{_e(dec.decision)}'
            f'<p class="small">Why: {_e(dec.why) if dec.why else "<b>not stated</b>"}</p>{quote}'
            + (f'<p class="small muted">Alternatives rejected:</p><ul class="small">{alts}</ul>' if alts else
               '<p class="small"><b>No alternative recorded.</b></p>')
            + "</div>")


# --------------------------------------------------------------------------------------------------- pages

def _frame(cfg: Any, current: str, title: str, body: str, *, crumbs: str = "") -> str:
    """A page in site/review/: the shared top bar, a header with links to every review page, then the body."""
    from cadagent.site import _page, nav_html
    sub = (f'<nav class="links subnav"><a href="../index.html">Overview</a><a href="index.html">Sections</a>'
           f'<a href="requirements.html">Requirements</a><a href="gates.html">Gates</a></nav>')
    head = (f'<header class="top"><div class="wrap"><p class="tag"><a href="../index.html">← {_e(cfg.title)}</a>'
            f'{" · " + crumbs if crumbs else ""}</p><h1>{_e(title)}</h1>{sub}</div></header>')
    return _page(f"{title} · {cfg.title}", nav_html(cfg, current, "../../") + head
                 + f'<main class="wrap">{body}<footer>Statuses from the pipeline\'s files (dossier-status.json, '
                   f'the gate verdicts); checks of the CAD model, physical fit not verified.</footer></main>',
                 cfg.accent, depth=1, theme=cfg.theme, extra_css=CSS)


def _banners(data: ReviewData, links: _Links) -> str:
    out = []
    if data.has_dossier and data.status is None:
        out.append(f'<div class="banner bad">No dossier status yet ({_e(data.status_error)}): run '
                   f'<code>cad-agent dossier</code> or <code>cad-agent gates</code>. Statuses below are not computed.</div>')
    elif data.status is not None and not data.status.get("pass", True):
        c = data.status.get("counts") or {}
        out.append(f'<div class="banner bad">The dossier lint fails: {_e(c.get("error", 0))} error(s), '
                   f'{_e(c.get("warning", 0))} warning(s). See <a href="index.html#lint">the findings</a>.</div>')
    if data.yaml_newer:
        files = ", ".join(links.file(f) for f in data.yaml_newer[:6])
        out.append(f'<div class="banner">The dossier changed after the status file was written ({files}); run '
                   f'<code>cad-agent dossier</code> to recompute the statuses.</div>')
    if data.dossier_error:
        out.append(f'<div class="banner bad">The YAML dossier did not load: {_e(data.dossier_error)}</div>')
    bad = [r for r in data.rows if not str(r.get("name", "")).startswith("gate ")]
    for r in bad:
        out.append(f'<div class="banner bad">{_e(r.get("name"))}: {_e(r.get("message"))}</div>')
    return "".join(out)


def _section_gate_state(data: ReviewData, sid: str) -> str:
    """pass / fail / stale / unrun over the gate checks of the section's parts."""
    states = [c.get("status") for pid in data.part_ids(sid) for c in data.part_row(pid).get("checks", [])
              if str(c.get("id", "")).startswith("gate:")]
    if not states:
        return "unrun"
    for s in ("fail", "unknown", "stale", "unrun"):
        if s in states:
            return s
    return "pass"


def _review_state(row: Mapping[str, Any]) -> Tuple[str, str]:
    """(label, pill class) of a section's review: signed off, findings open, reviewed, void, unreviewed."""
    rev = row.get("review")
    if rev:
        if rev.get("signed_off") and row.get("status") == "signed_off":
            return "signed off", "pass"
        if rev.get("findings"):
            return f'{rev["findings"]} finding(s) open', "warn"     # _pill escapes it
        return "reviewed", "pass"
    if row.get("invalidated"):
        return "review void (geometry changed)", "stale"
    return "unreviewed", "none"


def index_page(data: ReviewData, cfg: Any) -> str:
    links = _Links(data.root)
    rows = []
    for sid in data.section_ids():
        row = data.section_row(sid)
        sec = data.section_yaml(sid)
        title = row.get("title") or (sec.title if sec is not None else sid)
        reqs = " ".join(f'<a href="requirements.html#req-{_slug(r)}">{_e(r)}</a>' for r in row.get("requirements") or
                        (sec.requirements if sec is not None else []))
        rlabel, rcls = _review_state(row)
        rev = row.get("review") or {}
        record = (f'{_e(rev.get("date", ""))} · {_e(rev.get("actor", ""))} · ' + links.file(rev.get("record"), "record")
                  if rev else "")
        stale = ' <span class="badge">stale</span>' if row.get("invalidated") else ""
        rows.append(f'<tr><td><a href="{section_page(sid)}"><b>{_e(sid)}</b></a></td>'
                    f'<td><a href="{section_page(sid)}">{_e(title)}</a></td><td>{_pill(row.get("status", "none"))}{stale}</td>'
                    f'<td>{reqs}</td><td>{len(data.part_ids(sid))}</td>'
                    f'<td>{_pill(_section_gate_state(data, sid))}</td><td>{_pill(rcls, rlabel)}</td><td class="small">{record}</td></tr>')
    table = ('<div class="tablewrap"><table><tr><th>Section</th><th>Title</th><th>Status</th><th>Requirements</th>'
             '<th>Parts</th><th>Gates</th><th>Review</th><th>Reviewer record</th></tr>' + "".join(rows) + "</table></div>"
             if rows else '<p class="tag">No sections in the dossier yet.</p>')
    st = data.status or {}
    c = st.get("counts") or {}
    sec_counts = c.get("sections") or {}
    reqs = (st.get("requirements") or {})
    verified = sum(1 for r in reqs.values() if r.get("status") == "verified")
    states = gate_states(data)
    gpass = sum(1 for s in states.values() if s in ("pass", "warn"))
    stats = ('<div class="stats">'
             f'<div class="stat"><b>{_e(sec_counts.get("signed_off", 0))} / {len(data.section_ids())}</b><span>sections signed off</span></div>'
             f'<div class="stat"><b>{_e(sum(_int(sec_counts.get(s)) for s in ("gated", "reviewed", "signed_off")))} / '
             f'{len(data.section_ids())}</b><span>sections gated or better (required: {_e(st.get("required_section_status") or "—")})</span></div>'
             f'<a class="stat" href="requirements.html"><b>{verified} / {len(reqs)}</b><span>requirements verified</span></a>'
             f'<a class="stat" href="gates.html"><b>{gpass} / {len(states)}</b><span>gates pass on the current geometry</span></a>'
             f'<div class="stat"><b>{_e(c.get("error", "—"))} / {_e(c.get("warning", "—"))}</b><span>lint errors / warnings</span></div></div>')
    findings = st.get("findings") or []
    lint = ("".join(f'<tr><td>{_pill("fail" if f.get("severity") == "error" else "warn", f.get("severity"))}</td>'
                    f'<td><code>{_e(f.get("code"))}</code></td><td>{_e(f.get("message"))}</td>'
                    f'<td>{links.file(f.get("file"), line=f.get("line"))}</td></tr>' for f in findings))
    lint_html = (f'<div class="tablewrap"><table><tr><th></th><th>Code</th><th>Finding</th><th>Where</th></tr>{lint}</table></div>'
                 if lint else '<p class="tag">No lint findings.</p>')
    body = (_banners(data, links) + stats + '<h2 id="sections">Sections</h2>' + table
            + '<h2 id="lint">Dossier lint</h2>' + lint_html
            + f'<p class="small muted">Computed by <code>cad-agent dossier</code> into '
              f'{links.file(_rel(data.exports / STATUS_FILE, data.root))}; the dossier itself: '
              f'{links.file(st.get("dossier") or "")}</p>')
    return _frame(cfg, "review", "Design review by section", body)


def _interfaces_for(data: ReviewData, sid: str) -> List[Any]:
    d = data.dossier
    if d is None:
        return []
    names = {sid} | set(data.part_ids(sid))
    out = []
    for iid, itf in d.interfaces.items():
        if names & set(itf.between) or itf.section == sid:
            out.append(itf)
    return out


def _findings_for(data: ReviewData, sid: str) -> List[Tuple[str, Dict[str, Any], Set[str]]]:
    """The gate findings that concern the section: those naming one of its parts, and every failing finding that
    names no known part (the dossier lint counts those against every part, so they block this section too; they come
    back with an empty set of named parts)."""
    cards = set(data.section_of_part())
    mine = set(data.part_ids(sid))
    out = []
    for gate, v in data.verdicts.items():
        if gate == "dossier-lint":
            continue
        for f in v.get("findings") or []:
            if not isinstance(f, dict):
                continue
            named = parts_named(f.get("parts") or [], cards, data.geometry)
            if named & mine or (not named and f.get("status") == "fail" and mine):
                out.append((gate, f, named))
    return out


def _part_card(data: ReviewData, pid: str, links: _Links, shown_interfaces: Set[str]) -> str:
    row = data.part_row(pid)
    card = (getattr(data.dossier, "parts", None) or {}).get(pid)
    status = row.get("status", "")
    head = [f'<h3 id="part-{_slug(pid)}">{_e(pid)} {_pill(status or "none")}']
    if row.get("invalidated"):
        inv = row["invalidated"]
        head.append(f'<span class="badge" title="the review of {_e(inv.get("date"))} no longer matches the geometry">'
                    f'stale: geometry changed since the review of {_e(inv.get("date"))}</span>')
    claimed = row.get("claimed")
    if claimed and status in LADDER and claimed in LADDER and LADDER.index(claimed) > LADDER.index(status):
        head.append(f'<span class="badge">YAML claims {_e(claimed)}</span>')
    head.append("</h3>")
    dl: List[Tuple[str, str]] = []
    if card is not None:
        dl.append(("Function", _e(card.function) or "<b>not stated</b>"))
        if card.material:
            m = card.material
            bits = [m.name, m.process, f"print axis {m.print_axis}" if m.print_axis else "",
                    f"min wall {m.wall_mm:g} mm" if m.wall_mm is not None else "", m.notes]
            dl.append(("Material", _e(", ".join(b for b in bits if b))))
        if card.loads:
            dl.append(("Loads", "<br>".join(f"{_e(k)}: {_e(v)}" for k, v in card.loads.items())))
        if card.interfaces:
            dl.append(("Interfaces", " ".join(f'<a href="#if-{_slug(i)}">{_e(i)}</a>' if i in shown_interfaces
                                              else f'{_e(i)} <span class="badge">not declared</span>'
                                              for i in card.interfaces)))
        if card.fasteners:
            dl.append(("Fasteners", "<br>".join(
                _e(f"{f.qty or '?'} × {f.screws} to {f.to}" + (f" via {f.via}" if f.via else "")) for f in card.fasteners)))
        if card.contains:
            dl.append(("Contains", "<br>".join(
                _e(f"{c.count if c.count is not None else '?'} × {c.what} in {c.cavity}" + (" (free)" if c.free else ""))
                for c in card.contains)))
        if card.notes:
            dl.append(("Notes", _e(card.notes)))
    elif data.dossier is not None:
        dl.append(("Card", "<b>no card in the YAML dossier</b>"))
    checks = row.get("checks") or []
    dl.append(("Checks", _check_pills(checks, links)))
    if row.get("blocked_by"):
        dl.append(("Not higher because", "<br>".join(_e(b) for b in row["blocked_by"])))
    if row.get("review"):
        r = row["review"]
        dl.append(("Reviewed", f'{_e(r.get("date"))} by {_e(r.get("actor"))} · {links.file(r.get("record"), "record")}'))
    where = links.file(row.get("file") or (card.where.file if card is not None and card.where else ""),
                       line=row.get("line") or (card.where.line if card is not None and card.where else None))
    meta = [f"card {where}"] if where else []
    if row.get("sha256"):
        meta.append(f'geometry <code class="hash">{_e(row["sha256"][:16])}</code>')
    if row.get("findings"):
        meta.append(f'<span class="badge">{_e(row["findings"])} lint error(s)</span>')
    decs = "".join(_decision_html(dec, ((data.status or {}).get("decisions") or {}).get(dec.id))
                   for dec in (card.decisions if card is not None else []))
    return (f'<div class="partcard">{"".join(head)}{_ladder(status)}<dl>'
            + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in dl) + "</dl>"
            + (f'<p class="small muted">Decisions</p>{decs}' if decs else "")
            + f'<p class="small muted">{" · ".join(meta)}</p></div>')


def _packet(data: ReviewData, sid: str) -> Optional[Dict[str, Any]]:
    for name in (sid, _slug(sid)):
        path = data.exports / PACKET_DIR / name / "manifest.json"
        m, _ = _read_json(path)
        if m is not None:
            m["_dir"] = path.parent
            return m
    return None


def _packet_images(data: ReviewData, manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """The packet's views. ``cad-agent.review-packet/1`` (T10, ``cadagent.render.review_packet``) lists them under
    ``views`` as ``{id, kind, file, caption, note, sha256}``, ``file`` relative to the manifest's folder and null for
    a view not rendered. Until that schema is merged the reader is tolerant: ``images``, ``renders`` or ``items``,
    each a path or ``{file|path|image, caption|title, id|view|name, hash|sha256}``, resolved against the manifest's
    folder, then the project root."""
    items: List[Any] = []
    for key in ("views", "images", "renders", "items"):
        if isinstance(manifest.get(key), list):
            items = manifest[key]
            break
    out = []
    for it in items:
        d = {"file": it} if isinstance(it, str) else dict(it) if isinstance(it, dict) else {}
        if not d:
            continue
        rel = next((d[k] for k in ("file", "path", "image", "png") if isinstance(d.get(k), str) and d.get(k)), "")
        found = ""
        for base in ((Path(manifest["_dir"]), data.root) if rel else ()):
            p = (base / rel).resolve()
            if p.is_file() and data.root in p.parents:
                found = _rel(p, data.root)
                break
        out.append({"rel": found, "given": rel,
                    "caption": next((str(d[k]) for k in ("caption", "title") if d.get(k)), ""),
                    "view": next((str(d[k]) for k in ("id", "view", "name") if d.get(k)), ""),
                    "note": str(d.get("note") or ""), "kind": str(d.get("kind") or ""),
                    "hash": next((str(d[k]) for k in ("sha256", "hash", "geometry_hash") if d.get(k)), "")})
    return out


def _packet_hashes(manifest: Mapping[str, Any]) -> Dict[str, str]:
    """``{part: sha256}`` the packet was rendered from: ``parts.<name>.sha256`` (T10's schema) or ``hashes``."""
    out: Dict[str, str] = {}
    if isinstance(manifest.get("parts"), dict):
        out.update({k: str(v["sha256"]) for k, v in manifest["parts"].items() if isinstance(v, dict) and v.get("sha256")})
    if isinstance(manifest.get("hashes"), dict):
        out.update({k: str(v) for k, v in manifest["hashes"].items() if v})
    return out


def _reviewer_findings(data: ReviewData, row: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    rev = row.get("review") or {}
    rel = rev.get("record")
    if not rel:
        return [], ""
    rec, _ = _read_json(data.root / rel)
    found = [f for f in (rec or {}).get("findings") or [] if isinstance(f, dict)]
    return found, rel


def _packet_html(data: ReviewData, sid: str, links: _Links) -> str:
    m = _packet(data, sid)
    row = data.section_row(sid)
    if m is None:
        return ('<p class="tag">No review packet for this section yet: the render packet '
                f'(<code>exports/{PACKET_DIR}/{_e(sid)}/manifest.json</code>, made by '
                '<code>cadagent.render.review_packet</code>) adds the views the reviewer answers the checklist from.</p>')
    images = _packet_images(data, m)
    current = {pid: data.part_row(pid).get("sha256") for pid in data.part_ids(sid)}
    hashes = _packet_hashes(m)
    changed = sorted(p for p, h in hashes.items() if p in current and current[p] and h != current[p])
    questions = [q for q in ((m.get("checklist") or {}).get("questions") or []) if isinstance(q, dict)]
    banner = (f'<div class="banner">The packet was rendered from older geometry ({_e(", ".join(changed))} changed): '
              'render it again before the review.</div>' if changed else "")
    findings, record = _reviewer_findings(data, row)

    def matches(f: Mapping[str, Any], img: Mapping[str, Any]) -> bool:
        ref = str(next((f[k] for k in ("render", "image", "view", "file") if f.get(k)), ""))
        return bool(ref) and ref in (img["given"], img["rel"], Path(img["given"]).name, img["view"], img["caption"])

    def f_html(f: Mapping[str, Any]) -> str:
        sev = str(f.get("severity", "") or "")
        text = next((f[k] for k in ("text", "message", "finding", "note") if f.get(k)), json.dumps(f, default=str))
        return f'<li>{_pill("fail" if sev in ("major", "critical", "error", "high") else "warn", sev or "finding")} {_e(text)}</li>'

    used: Set[int] = set()
    figs = []
    for img in images:
        mine = [f for i, f in enumerate(findings) if matches(f, img) and not used.add(i)]
        mine_html = (f'<ul class="small">{"".join(f_html(f) for f in mine)}</ul>' if mine else "")
        if img["rel"]:
            pic = f'<a href="{_e(links.prefix + img["rel"])}"><img src="{_e(links.prefix + img["rel"])}" alt="{_e(img["caption"] or img["view"])}" loading="lazy"></a>'
        elif img["given"]:
            pic = f'<p class="notice">Missing image: {_e(img["given"])}</p>'
        else:
            pic = '<p class="notice">Not rendered in this packet</p>'
        hash_html = f' · <code class="hash">{_e(img["hash"][:16])}</code>' if img["hash"] else ""
        note = f'<br><span class="small muted">{_e(img["note"])}</span>' if img["note"] else ""
        asks = [q for q in questions if img["view"] and img["view"] in (q.get("views") or [])]
        asks_html = ('<p class="small muted">Checklist:</p><ul class="small">'
                     + "".join(f'<li>{_e(q.get("question"))}</li>' for q in asks) + "</ul>") if asks else ""
        figs.append(f'<figure>{pic}<figcaption><b>{_e(img["view"])}</b> {_e(img["caption"])}{hash_html}{note}'
                    f'{asks_html}{mine_html}</figcaption></figure>')
    rest = [f for i, f in enumerate(findings) if i not in used]
    rest_html = (f'<h3 class="rf">Reviewer findings</h3><ul>{"".join(f_html(f) for f in rest)}</ul>' if rest else "")
    skipped = [x for x in m.get("not_rendered") or [] if isinstance(x, dict)]
    if skipped:
        rest_html += ('<p class="small muted">Not rendered: '
                      + "; ".join(f'{_e(x.get("what"))} ({_e(x.get("why"))})' for x in skipped) + "</p>")
    rec_html = f'<p class="small muted">Reviewer record: {links.file(record)}</p>' if record else ""
    manifest_rel = _rel(Path(m["_dir"]) / "manifest.json", data.root)
    return (banner + (f'<div class="packet">{"".join(figs)}</div>' if figs else '<p class="tag">The packet lists no images.</p>')
            + rest_html + rec_html + f'<p class="small muted">Packet: {links.file(manifest_rel)}</p>')


def section_page_html(data: ReviewData, sid: str, cfg: Any) -> str:
    links = _Links(data.root)
    row = data.section_row(sid)
    sec = data.section_yaml(sid)
    title = row.get("title") or (sec.title if sec is not None else sid)
    status = row.get("status", "")
    st = data.status or {}
    reqs_status = st.get("requirements") or {}
    yreqs = getattr(data.dossier, "requirements", None) or {}
    top = [_banners(data, links)]
    if sec is not None and sec.purpose:
        top.append(f'<p><b>Purpose:</b> {_e(sec.purpose)}</p>')
    top.append(_ladder(status))
    if row.get("invalidated"):
        inv = row["invalidated"]
        top.append(f'<div class="banner"><span class="badge">stale</span> The review of {_e(inv.get("date"))} '
                   f'({links.file(inv.get("record"), "record")}) no longer applies: {_e(", ".join(inv.get("changed") or []))} '
                   'changed since. The status fell back to what the current evidence supports.</div>')
    if row.get("blocked_by"):
        top.append('<p class="small muted">Not higher because:</p><ul class="small">'
                   + "".join(f"<li>{_e(b)}</li>" for b in row["blocked_by"]) + "</ul>")
    rlabel, rcls = _review_state(row)
    rev = row.get("review") or {}
    top.append(f'<p>Review: {_pill(rcls, rlabel)}'
               + (f' · {_e(rev.get("date"))} by {_e(rev.get("actor"))} · {links.file(rev.get("record"), "reviewer record")}' if rev else "")
               + (f' · open decisions: {_e(", ".join(row["open_decisions"]))}' if row.get("open_decisions") else "")
               + f' · section file {links.file(row.get("file") or (sec.file if sec is not None else ""), line=row.get("line"))}</p>')

    req_ids = list(row.get("requirements") or (sec.requirements if sec is not None else []))
    req_rows = []
    for rid in req_ids:
        r = reqs_status.get(rid) or {}
        y = yreqs.get(rid)
        text = r.get("text") or (y.text if y is not None else "")
        req_rows.append(f'<tr><td><a href="requirements.html#req-{_slug(rid)}"><b>{_e(rid)}</b></a></td><td>{_e(text)}</td>'
                        f'<td>{_pill(r.get("status", "none"))}</td><td>{_e(r.get("verify_by") or (y.verify_by if y else ""))}</td>'
                        f'<td>{_check_pills(r.get("checks") or [], links)}'
                        + (f'<br><span class="small muted">covered by card checks: {_e(", ".join(r["covered_by"]))}</span>'
                           if r.get("covered_by") else "") + "</td></tr>")
    req_html = ('<div class="tablewrap"><table><tr><th>Id</th><th>Requirement</th><th>Status</th><th>Verify by</th>'
                '<th>Verifying checks</th></tr>' + "".join(req_rows) + "</table></div>"
                if req_rows else '<p class="tag">The section names no requirement.</p>')

    itfs = _interfaces_for(data, sid)
    if_rows = "".join(
        f'<tr id="if-{_slug(i.id)}"><td><b>{_e(i.id)}</b></td><td>{_e(" / ".join(i.between))}</td><td>{_e(i.kind)}</td>'
        f'<td>{_e(i.datum)}</td><td>{"" if i.clearance is None else _e(f"{i.clearance:g} mm")}</td>'
        f'<td>{_e(i.fastened_by)}</td><td>{_e(i.owner)}</td>'
        f'<td class="small">{_e(i.description)}{"<br>" if i.description and i.loads else ""}'
        f'{_e(", ".join(f"{k}: {v}" for k, v in i.loads.items()))}</td></tr>' for i in itfs)
    if_html = ('<div class="tablewrap"><table><tr><th>Id</th><th>Between</th><th>Kind</th><th>Datum</th><th>Clearance</th>'
               '<th>Fastened by</th><th>Owner</th><th>Notes</th></tr>' + if_rows + "</table></div>"
               if if_rows else '<p class="tag">No interfaces declared for this section or its parts.</p>')

    sec_decs = "".join(_decision_html(dec, (st.get("decisions") or {}).get(dec.id))
                       for dec in (getattr(data.dossier, "decisions", None) or {}).values()
                       if dec.scope == "section" and dec.section == sid)
    cards = "".join(_part_card(data, pid, links, {i.id for i in itfs}) for pid in data.part_ids(sid))

    states = gate_states(data)
    f_rows = []
    sec_of = data.section_of_part()
    for gate, f, named in _findings_for(data, sid):
        stale = (' <span class="badge">verdict ' + _e(states[gate]) + "</span>") if states.get(gate) in ("stale", "invalid") else ""
        parts = " ".join(f'<a href="{section_page(sec_of[p]) if sec_of.get(p) != sid else ""}#part-{_slug(p)}">{_e(p)}</a>'
                         if p in sec_of else _e(p) for p in sorted(named))
        if not named:
            raw = ", ".join(str(x) for x in f.get("parts") or [])
            parts = (f'<span class="small muted">{_e(raw) + ": " if raw else ""}names no known part, so it counts '
                     'against every part</span>')
        f_rows.append(f'<tr><td><a href="gates.html#gate-{_slug(gate)}">{_e(gate)}</a>{stale}</td><td><code>{_e(f.get("id"))}</code></td>'
                      f'<td>{_pill(f.get("status"))}</td><td>{parts}</td><td>{_e(f.get("message"))}<br>{_witness(f.get("evidence"))}</td></tr>')
    lint_rows = [f for f in (st.get("findings") or []) if f.get("item") == sid or set(f.get("parts") or []) & set(data.part_ids(sid))
                 or f.get("item") in data.part_ids(sid)]
    lint_html = "".join(f'<tr><td>dossier lint</td><td><code>{_e(f.get("code"))}</code></td>'
                        f'<td>{_pill("fail" if f.get("severity") == "error" else "warn", f.get("severity"))}</td>'
                        f'<td>{_e(", ".join(f.get("parts") or []))}</td><td>{_e(f.get("message"))}<br>'
                        f'{links.file(f.get("file"), line=f.get("line"))}</td></tr>' for f in lint_rows)
    find_html = ('<div class="tablewrap"><table><tr><th>Gate</th><th>Check</th><th>Status</th><th>Parts</th>'
                 '<th>Finding and witness</th></tr>' + "".join(f_rows) + lint_html + "</table></div>"
                 if f_rows or lint_html else '<p class="tag">No gate or lint finding names this section\'s parts.</p>')

    self_review = ""
    if sec is not None and isinstance(sec.review, dict) and sec.review.get("self"):
        self_review = ('<h2 id="self-review">Author\'s self-review</h2><div class="card"><pre class="small">'
                       + _e(json.dumps(sec.review["self"], indent=1, default=str)) + "</pre></div>")

    body = ("".join(top)
            + '<h2 id="requirements">Requirements</h2>' + req_html
            + '<h2 id="interfaces">Interfaces</h2>' + if_html
            + (f'<h2 id="decisions">Section decisions</h2>{sec_decs}' if sec_decs else "")
            + f'<h2 id="parts">Parts ({len(data.part_ids(sid))})</h2>' + (cards or '<p class="tag">No part cards.</p>')
            + '<h2 id="findings">Gate and lint findings</h2>' + find_html
            + '<h2 id="packet">Review packet</h2>' + _packet_html(data, sid, links) + self_review)
    return _frame(cfg, "review", f"{sid}: {title}", body, crumbs='<a href="index.html">Sections</a>')


def requirements_page(data: ReviewData, cfg: Any) -> str:
    links = _Links(data.root)
    st = data.status or {}
    rs = st.get("requirements") or {}
    yreqs = getattr(data.dossier, "requirements", None) or {}
    ids = list(rs) + [r for r in yreqs if r not in rs]
    rows = []
    counts: Dict[str, int] = {}
    for rid in ids:
        r = rs.get(rid) or {}
        y = yreqs.get(rid)
        status = r.get("status", "none")
        counts[status] = counts.get(status, 0) + 1
        text = r.get("text") or (y.text if y is not None else "")
        src = y.source if y is not None else None
        quote = (f'<br><span class="small muted">{_e(src.kind)}: “{_e(src.quote)}”{" (" + _e(src.ref) + ")" if src.ref else ""}</span>'
                 if src and src.quote else "")
        secs = " ".join(f'<a href="{section_page(s)}">{_e(s)}</a>' for s in r.get("sections") or [])
        derived_links = " ".join('<a href="#req-%s">%s</a>' % (_slug(c), _e(c)) for c in r.get("derived") or [])
        derived = (f'<br><span class="small muted">derived: {derived_links}</span>'
                   if r.get("derived") else "")
        parent = (f'<br><span class="small muted">from <a href="#req-{_slug(y.parent)}">{_e(y.parent)}</a></span>'
                  if y is not None and y.parent else "")
        covered = (f'<br><span class="small muted">covered by card checks (trace only): {_e(", ".join(r["covered_by"]))}</span>'
                   if r.get("covered_by") else "")
        waiver = ""
        if status == "waived" or (y is not None and y.status == "waived"):
            why = y.rationale if y is not None else ""
            waiver = f'waived: {_e(why)}' if why else '<span class="badge">waived without a rationale</span>'
        elif y is not None and y.rationale:
            waiver = f'<span class="small muted">rationale: {_e(y.rationale)}</span>'
        rows.append(f'<tr id="req-{_slug(rid)}"><td><b>{_e(rid)}</b></td><td>{_e(text)}{quote}{parent}</td>'
                    f'<td>{_pill(status)}</td><td>{_e(r.get("verify_by") or (y.verify_by if y else ""))}</td>'
                    f'<td>{secs or "<span class=badge>untraced</span>"}{derived}</td>'
                    f'<td>{_check_pills(r.get("checks") or [], links)}{covered}</td><td>{waiver}</td>'
                    f'<td>{links.file(r.get("file") or (y.where.file if y is not None and y.where else ""), "yaml", line=None)}</td></tr>')
    summary = " ".join(f'{_pill(s)} {n}' for s, n in sorted(counts.items()))
    table = ('<div class="tablewrap"><table><tr><th>Id</th><th>Requirement</th><th>Status</th><th>Verify by</th>'
             '<th>Traced sections</th><th>Verifying checks</th><th>Waiver</th><th>Source</th></tr>'
             + "".join(rows) + "</table></div>" if rows else '<p class="tag">No requirements in the dossier yet.</p>')
    body = (_banners(data, links) + (f"<p>{summary}</p>" if summary else "") + table
            + '<p class="small muted">A requirement is verified only when its own checks pass (and, for inspection, every '
              'section that serves it is reviewed); checks on the cards of the sections that serve it satisfy the trace '
              'but verify nothing on their own. <code>test</code> and <code>demo</code> requirements stay '
              '“not tested”: cad-agent cannot run them.</p>')
    return _frame(cfg, "requirements", "Requirements", body, crumbs='<a href="index.html">Sections</a>')


_LEGEND = ('<div class="legend"><span>▭ part · ⬭ fastener</span><span>double frame: grounded</span>'
           '<span>red: floating or failing</span><span>dashed frame: allowed free</span>'
           '<span>grey line: contact that holds nothing up</span><span>orange: undeclared contact</span>'
           '<span>dotted: inside a declared cavity</span><span>blue dashed: joint (red when it does not hold)</span>'
           '<span>red dashed: declared but not realised</span></div>')


def gates_page(data: ReviewData, cfg: Any, out_dir: Path, engine: str = "auto") -> Tuple[str, Dict[str, Any]]:
    """The gates page, and what was drawn (``{"graph": "python"|"graphviz"|"", "svg": path}``)."""
    from cadagent.dotsvg import dot_to_svg
    links = _Links(data.root)
    gates_rel = _rel(data.exports / "gates", data.root)
    info: Dict[str, Any] = {"graph": "", "svg": ""}
    rows = []
    for row in data.rows:
        name = str(row.get("name", ""))
        if not name.startswith("gate "):
            continue
        g = name[5:]
        v = data.verdicts.get(g)
        state = gate_state(row, v)
        files = " · ".join(x for x in (links.maybe(f"{gates_rel}/{g}.md", ".md"), links.maybe(f"{gates_rel}/{g}.json", ".json"),
                                       links.maybe(f"{gates_rel}/{g}.dot", ".dot")) if x)
        details = f'<a href="#gate-{_slug(g)}">details</a>' if v is not None else ""
        rows.append(f'<tr><td><b>{_e(g)}</b></td><td>{_pill(state)}</td><td>{_counts(v) if state not in ("na", "skipped") else ""}</td>'
                    f'<td class="small">{_e(row.get("message"))}</td><td>{" · ".join(x for x in (details, files) if x)}</td></tr>')
    lint = data.verdicts.get("dossier-lint")
    if lint is not None or data.status is not None:
        st = data.status or {}
        # the lint writes both files in one go; either one failing (or missing) is a failing lint
        ok = (lint is None or lint.get("pass") is True) and (data.status is None or data.status.get("pass") is True)
        state = "pass" if ok else "fail"
        c = st.get("counts") or {}
        files = " · ".join(x for x in (links.maybe(f"{gates_rel}/dossier-lint.json", ".json"),
                                       links.maybe(_rel(data.exports / STATUS_FILE, data.root), "status")) if x)
        rows.append(f'<tr><td><b>dossier-lint</b></td><td>{_pill(state)}</td><td>{_e(c.get("error", 0))} error · {_e(c.get("warning", 0))} warning</td>'
                    f'<td class="small">declarations against the build; statuses in dossier-status.json</td>'
                    f'<td><a href="index.html#lint">findings</a> · {files}</td></tr>')
    table = ('<div class="tablewrap"><table><tr><th>Gate</th><th>State</th><th>Checks</th><th>Summary</th><th>Files</th></tr>'
             + "".join(rows) + "</table></div>" if rows else '<p class="tag">No gate verdicts yet: run <code>cad-agent gates</code>.</p>')

    dot = data.exports / "gates" / "connectivity.dot"
    graph = ""
    if dot.is_file():
        try:
            svg, used = dot_to_svg(dot.read_text(), engine=engine, title="connectivity graph")
            (out_dir / "connectivity.svg").write_text(svg)
            info.update(graph=used, svg=str(out_dir / "connectivity.svg"))
            stale = gate_states(data).get("connectivity") in ("stale", "invalid", "missing")
            graph = ((f'<div class="banner">The connectivity verdict is {_e(gate_states(data).get("connectivity"))}: this graph '
                      'is from an earlier build.</div>' if stale else "")
                     + f'<div class="graph">{svg}</div>' + _LEGEND
                     + f'<p class="small muted">Drawn by {"Graphviz" if used == "graphviz" else "the built-in layout (Graphviz not installed)"} '
                       f'from {links.file(_rel(dot, data.root))} · <a href="connectivity.svg">SVG</a></p>')
        except ValueError as exc:
            graph = f'<p class="notice">The connectivity graph could not be drawn: {_e(exc)} ({links.file(_rel(dot, data.root))}).</p>'
    else:
        graph = '<p class="tag">No connectivity graph yet (<code>cad-agent gates</code> writes it with the connectivity verdict).</p>'

    sec_of = data.section_of_part()
    cards = set(sec_of)
    order = [g for g in ("connectivity", "containment", "fasteners", "motion", "assembly", "wall") if g in data.verdicts]
    order += [g for g in sorted(data.verdicts) if g not in order and g != "dossier-lint"]
    states = gate_states(data)
    blocks = []
    for g in order:
        v = data.verdicts[g]
        findings = [f for f in v.get("findings") or [] if isinstance(f, dict)]

        def part_links(f: Mapping[str, Any]) -> str:
            named = parts_named(f.get("parts") or [], cards, data.geometry)
            shown = [f'<a href="{section_page(sec_of[p])}#part-{_slug(p)}">{_e(p)}</a>' for p in sorted(named) if p in sec_of]
            raw = [_e(p) for p in f.get("parts") or [] if str(p).split("#")[0] not in named]
            return " ".join(shown + raw)
        f_rows = "".join(f'<tr><td><code>{_e(f.get("id"))}</code></td><td>{_pill(f.get("status"))}</td><td>{part_links(f)}</td>'
                         f'<td>{_e(f.get("message"))}<br>{_witness(f.get("evidence"))}</td></tr>' for f in findings)
        f_html = ('<div class="tablewrap"><table><tr><th>Check</th><th>Status</th><th>Parts</th><th>Finding and witness</th></tr>'
                  + f_rows + "</table></div>" if f_rows else '<p class="small">No findings.</p>')
        excl = "".join(f'<li>{_e(", ".join(map(str, x.get("parts") or [])))}: {_e(x.get("reason"))}</li>'
                       for x in v.get("exclusions") or [] if isinstance(x, dict))
        nc = "".join(f"<li>{_e(x)}</li>" for x in v.get("not_checked") or [])
        assumptions = "".join(f"<li>{_e(a)}</li>" for a in v.get("assumptions") or [])
        limits = "".join(f"<li><code>{_e(k)}</code>: {_e(json.dumps(x, default=str))}</li>" for k, x in (v.get("limits") or {}).items())
        digest = (((v.get("inputs") or {}).get("geometry") or {}).get("digest") or "")
        blocks.append(
            f'<div class="partcard" id="gate-{_slug(g)}"><h3>{_e(g)} {_pill(states.get(g, v.get("status")))}'
            f'<span class="small muted">{_counts(v)}</span></h3>'
            + (f'<p class="small muted">bound to geometry <code class="hash">{_e(digest[:16])}</code></p>' if digest else
               '<p class="small muted">not bound to a geometry record (stale for <code>check</code>)</p>')
            + f_html
            + (f'<details><summary>Exclusions ({len(v.get("exclusions") or [])})</summary><ul class="small">{excl}</ul></details>' if excl else "")
            + (f'<details><summary>Not checked ({len(v.get("not_checked") or [])})</summary><ul class="small">{nc}</ul></details>' if nc else "")
            + (f'<details><summary>Assumptions</summary><ul class="small">{assumptions}</ul></details>' if assumptions else "")
            + (f'<details><summary>Limits</summary><ul class="small">{limits}</ul></details>' if limits else "")
            + f'<p class="small">{" · ".join(x for x in (links.maybe(f"{gates_rel}/{g}.md", "readable verdict (.md)"), links.maybe(f"{gates_rel}/{g}.json", "verdict JSON")) if x)}</p></div>')
    body = (_banners(data, links) + '<h2 id="summary">Gates</h2>' + table
            + '<h2 id="connectivity-graph">Connectivity graph</h2>' + graph
            + ('<h2 id="details">Findings by gate</h2>' + "".join(blocks) if blocks else "")
            + '<p class="small muted">A gate checks the CAD model against declared intent with stated tolerances; it does not '
              'prove that printed parts fit, move or hold. Run <code>cad-agent gates</code> to refresh.</p>')
    return _frame(cfg, "gates", "Integrity gates", body, crumbs='<a href="index.html">Sections</a>'), info


# --------------------------------------------------------------------------------------------------- entry points

def build_review_pages(project: Any, cfg: Any, site_dir: Path, *, engine: str = "auto") -> Dict[str, Any]:
    """Write ``<site_dir>/review/``: the index, one page per section, the requirements and the gates pages.
    Returns ``{"pages": [paths], "sections": n, "graph": engine used or ""}``. Old section pages are removed."""
    out = Path(site_dir) / REVIEW_DIR
    out.mkdir(parents=True, exist_ok=True)
    data = collect(project)
    written: List[Path] = []

    def write(name: str, text: str) -> None:
        (out / name).write_text(text)
        written.append(out / name)

    keep = set()
    if data.has_dossier:
        write("index.html", index_page(data, cfg))
        for sid in data.section_ids():
            write(section_page(sid), section_page_html(data, sid, cfg))
            keep.add(section_page(sid))
        write("requirements.html", requirements_page(data, cfg))
    else:
        (out / "index.html").write_text(_frame(cfg, "review", "Design review by section",
                                               '<p class="tag">This project has no dossier (<code>cad: dossier:</code> in '
                                               'cad-agent.yaml), so there are no sections to review. The gates are on '
                                               '<a href="gates.html">the gates page</a>.</p>'))
        written.append(out / "index.html")
        (out / "requirements.html").write_text(_frame(cfg, "requirements", "Requirements",
                                                      '<p class="tag">No dossier, so no requirements.</p>'))
        written.append(out / "requirements.html")
    page, info = gates_page(data, cfg, out, engine=engine)
    write("gates.html", page)
    if not info["graph"]:
        (out / "connectivity.svg").unlink(missing_ok=True)
    for old in out.glob("section-*.html"):
        if old.name not in keep:
            old.unlink()
    return {"pages": [str(p) for p in written], "sections": len(keep), "graph": info["graph"], "data": data}


def overview_html(data: ReviewData) -> str:
    """The "Design review" block on the site overview (links relative to ``site/``)."""
    base = f"{REVIEW_DIR}/"
    links = (f'<nav class="links">' + (f'<a class="primary" href="{base}index.html">Sections</a>'
                                       f'<a href="{base}requirements.html">Requirements</a>' if data.has_dossier else "")
             + f'<a href="{base}gates.html">Gates</a></nav>')
    rows = []
    for sid in data.section_ids():
        row = data.section_row(sid)
        sec = data.section_yaml(sid)
        title = row.get("title") or (sec.title if sec is not None else sid)
        rlabel, rcls = _review_state(row)
        stale = ' <span class="badge">stale</span>' if row.get("invalidated") else ""
        rows.append(f'<tr><td><a href="{base}{section_page(sid)}"><b>{_e(sid)}</b> {_e(title)}</a></td>'
                    f'<td>{_pill(row.get("status", "none"))}{stale}</td><td>{_pill(_section_gate_state(data, sid))}</td>'
                    f'<td>{_pill(rcls, rlabel)}</td></tr>')
    table = ('<div class="tablewrap"><table><tr><th>Section</th><th>Status</th><th>Gates</th><th>Review</th></tr>'
             + "".join(rows) + "</table></div>") if rows else ""
    note = ""
    if data.has_dossier and data.status is None:
        note = '<p class="tag">No dossier status yet: run <code>cad-agent dossier</code>.</p>'
    return f'<h2 id="design-review-by-section">Design review</h2>{links}{note}{table}'
