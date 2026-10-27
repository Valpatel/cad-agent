"""Project site: a local dashboard of progress, designs, decisions and documents.

Built from plain files the project already keeps, configured under ``cad: site:`` in ``cad-agent.yaml``::

    site:
      title: My robot
      tagline: What it is, in one line
      notice: Private. Closed source for now.     # optional banner
      accent: "#ef7d32"
      milestones: docs/milestones.yaml   # [{id, title, status: done|active|next|blocked, done_when, notes, evidence: [..]}]
      decisions: docs/decisions.yaml     # [{id, date, title, decision, why, status: decided|open|superseded,
                                         #   source: {kind: user|research|agent, quote, ref}, alternatives: [..]}]
      designs: exports/designs.json      # {"designs": [{name, file, summary, verdict, link,
                                         #   metrics: [{label, value, unit, estimate, level}], checks: {ok, warn, fail}}]}
      pages: [README.md, "docs/*.md", "research/*.md"]
      links: [{title: Designer, href: designer/}]

Every source is optional; a missing file shows as an empty section, never an error. ``cad-agent site`` writes
``<root>/site/`` (index.html plus one page per Markdown file); ``--serve`` serves the project and rebuilds the site when
a source changes, so a browser refresh always shows the current state.
"""

from __future__ import annotations

import html
import json
import os
import posixpath
import time
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote

from cadagent._deps import require

SITE_DIR = "site"
KIT_URL = "/_cadagent/kit/"
KIT_DIR = Path(__file__).resolve().parent / "webkit"
STATUS_ORDER = {"done": 0, "active": 1, "next": 2, "blocked": 3}


@dataclass
class SiteConfig:
    title: str = ""
    tagline: str = ""
    notice: str = ""
    accent: str = "#2f7f8f"
    milestones: str = ""
    decisions: str = ""
    designs: str = ""
    pages: List[str] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)
    nav: List[Dict[str, str]] = field(default_factory=list)   # app-wide top bar: [{title, href}], hrefs from the root
    theme: str = "light"                                       # light | hud (the control-room look of the web kit)
    live_reload: Dict[str, Any] = field(default_factory=dict)  # {watch: [folders], skip: [names]}: what `--serve` watches


def site_config(raw: Optional[Dict[str, Any]], default_title: str) -> SiteConfig:
    raw = dict(raw or {})
    cfg = SiteConfig(**{k: raw[k] for k in SiteConfig.__dataclass_fields__ if k in raw})
    cfg.title = cfg.title or default_title
    return cfg


# ----------------------------------------------------------------------------- inputs

def _load(root: Path, rel: str) -> Any:
    if not rel:
        return None
    p = root / rel
    if not p.is_file():
        return None
    if p.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(p.read_text())
    return json.loads(p.read_text())


def page_files(root: Path, patterns: List[str]) -> List[Path]:
    out: List[Path] = []
    for pat in patterns:
        for p in sorted(root.glob(pat)):
            if p.is_file() and p.suffix == ".md" and p not in out:
                out.append(p)
    return out


def sources(root: Path, cfg: SiteConfig) -> List[Path]:
    """Every file the site is built from (for staleness checks)."""
    files = page_files(root, cfg.pages)
    for rel in (cfg.milestones, cfg.decisions, cfg.designs, "exports/view/view.json"):
        if rel and (root / rel).is_file():
            files.append(root / rel)
    head = root / ".git" / "HEAD"
    if head.is_file():
        files.append(head)
        ref = head.read_text().strip()
        if ref.startswith("ref: ") and (root / ".git" / ref[5:]).is_file():
            files.append(root / ".git" / ref[5:])
    cfg_file = root / "cad-agent.yaml"
    if cfg_file.is_file():
        files.append(cfg_file)
    return files


def git_log(root: Path, n: int = 15) -> List[Dict[str, str]]:
    try:
        out = subprocess.run(["git", "log", f"-{n}", "--date=short", "--pretty=format:%h%x1f%ad%x1f%s"],
                             cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    rows = []
    for line in out.stdout.splitlines():
        h, d, s = (line.split("\x1f") + ["", "", ""])[:3]
        rows.append({"hash": h, "date": d, "subject": s})
    return rows


# ----------------------------------------------------------------------------- markdown pages

def slug(rel: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-")


def _title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def _summary_of(text: str) -> str:
    """First real paragraph of a Markdown document, as plain text."""
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b or b.startswith(("#", "|", "```", "<", "-", ">", "*", "!")):
            continue
        plain = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", b)
        plain = re.sub(r"[*_`]", "", plain).replace("\n", " ")
        return plain[:260] + ("…" if len(plain) > 260 else "")
    return ""


def render_markdown(text: str, src: Path, root: Path, page_map: Dict[str, str]) -> str:
    """Markdown → HTML for a page served from ``site/pages/``. Links to other rendered pages go to their page; other
    relative links and images are rewritten to the file in the project."""
    md = require("markdown", "the project site (pip install 'cad-agent[site]')")
    body = md.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"], output_format="html")
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<pre class="mermaid">{m.group(1)}</pre>', body, flags=re.S)

    def fix(m: re.Match) -> str:
        attr, url = m.group(1), m.group(2)
        if re.match(r"^[a-z][a-z0-9+.-]*:|^#|^/", url):
            return m.group(0)
        path, _, frag = url.partition("#")
        target = (src.parent / html.unescape(path)).resolve()
        try:
            rel = target.relative_to(root.resolve()).as_posix()
        except ValueError:
            return m.group(0)
        if rel in page_map:
            new = page_map[rel]
        elif target.is_dir() and (target / "README.md").is_file() and f"{rel}/README.md" in page_map:
            new = page_map[f"{rel}/README.md"]
        else:
            new = f"../../{rel}" + ("/" if target.is_dir() or path.endswith("/") else "")
        return f'{attr}="{new}{"#" + frag if frag else ""}"'

    return re.sub(r'(href|src)="([^"]+)"', fix, body)


# ----------------------------------------------------------------------------- HTML

_CSS = """
:root{--bg:#f6f4ef;--card:#fff;--ink:#202227;--muted:#686c75;--line:#e4e0d7;--accent:ACCENT;
--ok:#2f9e6e;--warn:#c98700;--fail:#d1453b;--okbg:#e3f4ec;--warnbg:#fdf1d8;--failbg:#fbe3e1;--nextbg:#eceae5;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#16171b;--card:#1f2126;--ink:#ecebe8;--muted:#a3a6ad;
--line:#33353c;--okbg:#18342a;--warnbg:#3a2f14;--failbg:#3d1f1d;--nextbg:#2a2c31;color-scheme:dark}}
:root[data-theme=dark]{--bg:#16171b;--card:#1f2126;--ink:#ecebe8;--muted:#a3a6ad;--line:#33353c;--okbg:#18342a;
--warnbg:#3a2f14;--failbg:#3d1f1d;--nextbg:#2a2c31;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}header.top{padding:26px 24px 18px;border-bottom:1px solid var(--line)}
.wrap{max-width:none;margin:0;padding:0 32px}header.top .wrap{padding:0}
h1{margin:0;font-size:32px;letter-spacing:.2px}h2{font-size:22px;margin:34px 0 12px}h3{margin:0 0 6px;font-size:17px}
.tag{color:var(--muted);margin:4px 0 0}.notice{display:inline-block;margin-top:10px;padding:3px 10px;border-radius:999px;
background:var(--nextbg);font-size:13px;color:var(--muted)}nav.links{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
nav.links a,.btn{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:6px 12px;text-decoration:none;
font-weight:600;font-size:14px;color:var(--ink)}nav.links a.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:22px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.stat b{display:block;font-size:24px}.stat span{color:var(--muted);font-size:13px}
.bar{height:8px;border-radius:99px;background:var(--nextbg);overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.card p{margin:6px 0;color:var(--muted);font-size:14px}.pill{display:inline-block;font-size:12px;font-weight:700;
padding:1px 8px;border-radius:99px;text-transform:uppercase;letter-spacing:.5px}
.done,.ok,.decided{background:var(--okbg);color:var(--ok)}.active,.warn,.open{background:var(--warnbg);color:var(--warn)}
.blocked,.fail{background:var(--failbg);color:var(--fail)}.next,.superseded{background:var(--nextbg);color:var(--muted)}
.milestones{list-style:none;padding:0;margin:0;display:grid;gap:8px}.milestones li{display:grid;grid-template-columns:90px 1fr;
gap:12px;align-items:start;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px}
.milestones .when{color:var(--muted);font-size:14px}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:10px 0}
.metric{background:var(--bg);border-radius:10px;padding:6px 9px}.metric b{display:block}.metric span{color:var(--muted);font-size:12px}
.metric.warn{background:var(--warnbg)}.metric.fail{background:var(--failbg)}.est{font-size:11px;color:var(--muted)}
details.decision{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin-bottom:8px}
details.decision summary{cursor:pointer;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
details.decision summary .d{color:var(--muted);font-size:13px}details.decision blockquote{margin:8px 0;padding:4px 12px;
border-left:3px solid var(--accent);color:var(--muted)}.docs{columns:3 360px;column-gap:16px}.docs .card{break-inside:avoid;margin-bottom:12px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.tablewrap{overflow-x:auto}.log td:first-child{font-family:ui-monospace,monospace;color:var(--muted)}
article.doc{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:8px 36px 28px;margin:20px 0 40px;max-width:1500px}
article.doc table{display:block;overflow-x:auto}article.doc img{max-width:100%}article.doc pre{overflow-x:auto;background:var(--bg);
padding:10px;border-radius:8px}article.doc code{font-size:.92em}pre.mermaid{background:none}
footer{color:var(--muted);font-size:13px;padding:30px 0}
@media (max-width:640px){.wrap{padding:0 16px}header.top{padding:20px 16px}article.doc{padding:4px 16px 16px}.milestones li{grid-template-columns:1fr}}
"""

_HUD = """
:root,:root[data-theme]{--bg:#0a0a0f;--card:#12121a;--ink:#e8edf5;--muted:#8892a4;--line:#2a303c;--accent:#00f0ff;
--ok:#05ffa1;--warn:#fcee0a;--fail:#ff2a6d;--okbg:rgba(5,255,161,.08);--warnbg:rgba(252,238,10,.08);--failbg:rgba(255,42,109,.1);
--nextbg:#1a1a2e;color-scheme:dark}
body{font-family:'Inter',system-ui,sans-serif;background:linear-gradient(180deg,#0a0a0f,#060609) fixed}
h1,h2,h3{letter-spacing:-.01em}h2{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:13px;letter-spacing:.14em;
text-transform:uppercase;color:var(--ink);display:flex;align-items:center;gap:8px}h2::before{content:"";width:12px;height:2px;
background:var(--accent);box-shadow:0 0 6px rgba(0,240,255,.3)}
.stat b,.metric b,.pill,.milestones .when,.d,code,.log td{font-family:'JetBrains Mono',ui-monospace,monospace}
.card,.stat,.milestones li,details.decision,article.doc{background:rgba(18,18,26,.9);border-color:var(--line)}
.card:hover{border-color:#0e7490}nav.links a.primary{color:#060609}
"""

_NAV_CSS = """
.appnav{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:4px;padding:0 16px;min-height:46px;
background:rgba(6,6,9,.94);backdrop-filter:blur(10px);border-bottom:1px solid #2a303c;overflow-x:auto}
.appnav .brand{font-weight:700;margin-right:12px;white-space:nowrap;display:flex;align-items:center;gap:8px;color:#e8edf5;text-decoration:none}
.appnav .brand i{width:9px;height:9px;background:#00f0ff;transform:rotate(45deg);box-shadow:0 0 10px rgba(0,240,255,.3)}
.appnav a.tab{font:500 12px 'JetBrains Mono',ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:#8892a4;
text-decoration:none;padding:6px 10px;border-radius:6px;white-space:nowrap}
.appnav a.tab:hover{color:#00f0ff}.appnav a.tab.on{color:#00f0ff;background:rgba(0,240,255,.06);box-shadow:inset 0 -2px 0 #00f0ff}
"""


def nav_html(cfg: "SiteConfig", current: str, prefix: str) -> str:
    """The app-wide top bar. ``prefix`` turns root-relative hrefs into page-relative ones."""
    if not cfg.nav:
        return ""
    tabs = "".join(f'<a class="tab{" on" if n.get("id", n["href"]) == current else ""}" href="{_e(n["href"] if re.match(r"^[a-z]+:", n["href"]) else prefix + n["href"])}">{_e(n["title"])}</a>'
                   for n in cfg.nav)
    return f'<nav class="appnav"><a class="brand" href="{prefix}site/"><i></i>{_e(cfg.title)}</a>{tabs}</nav>'


_MERMAID = ('<script type="module">import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";'
            'mermaid.initialize({startOnLoad:true,theme:matchMedia("(prefers-color-scheme: dark)").matches?"dark":"default"});</script>')


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _page(title: str, body: str, accent: str, depth: int = 0, theme: str = "light") -> str:
    css = _CSS.replace("ACCENT", accent) + _NAV_CSS + (_HUD if theme == "hud" else "")
    fonts = f'<link rel="stylesheet" href="{"../" * (depth + 1)}_cadagent/kit/vendor/fonts/fonts.css">' if theme == "hud" else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{_e(title)}</title>{fonts}<style>{css}</style></head><body>{body}{_MERMAID}</body></html>\n")


def _md_inline(text: str) -> str:
    """Escape, then allow **bold**, `code` and [links](url) in short YAML text fields."""
    t = _e(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)


def build_site(root: Path, raw_site: Optional[Dict[str, Any]], default_title: str,
               auto_nav: Optional[Callable[[], List[Dict[str, str]]]] = None) -> Dict[str, Any]:
    """Write ``<root>/site/``. Returns a summary (pages written, counts). ``auto_nav`` gives the top bar when the
    config has no ``nav`` (cad-agent passes :func:`default_nav` for the project)."""
    root = Path(root).resolve()
    cfg = site_config(raw_site, default_title)
    if not cfg.nav and auto_nav:
        cfg.nav = auto_nav()
    out = root / SITE_DIR
    (out / "pages").mkdir(parents=True, exist_ok=True)
    pages = page_files(root, cfg.pages)
    page_map = {p.relative_to(root).as_posix(): f"{slug(p.relative_to(root).as_posix())}.html" for p in pages}
    docs = []
    for p in pages:
        rel = p.relative_to(root).as_posix()
        text = p.read_text()
        title = _title_of(text, rel)
        docs.append({"rel": rel, "title": title, "summary": _summary_of(text), "href": f"pages/{page_map[rel]}",
                     "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")})
        body = (nav_html(cfg, "docs", "../../") + f'<header class="top"><div class="wrap"><a href="../index.html">← {_e(cfg.title)}</a>'
                f'<p class="tag"><code>{_e(rel)}</code></p></div></header>'
                f'<main class="wrap"><article class="doc">{render_markdown(text, p, root, page_map)}</article></main>')
        (out / "pages" / page_map[rel]).write_text(_page(f"{title} · {cfg.title}", body, cfg.accent, depth=1, theme=cfg.theme))

    milestones = _load(root, cfg.milestones) or []
    decisions = _load(root, cfg.decisions) or []
    designs = (_load(root, cfg.designs) or {}).get("designs", [])
    log = git_log(root)

    done = sum(1 for m in milestones if m.get("status") == "done")
    pct = round(100 * done / len(milestones)) if milestones else 0
    active = next((m for m in milestones if m.get("status") == "active"), None)
    open_dec = sum(1 for d in decisions if d.get("status") == "open")

    def href(h: str) -> str:
        return h if re.match(r"^[a-z][a-z0-9+.-]*:", h) else f"../{h}"

    all_links = list(cfg.links)
    if (root / "exports" / "view" / "view.json").is_file():   # written by `cad-agent view`
        all_links.append({"title": "3D model", "href": KIT_URL.strip("/") + "/viewer.html"})
    links = "".join(f'<a href="{_e(href(l["href"]))}" class="{"primary" if i == 0 else ""}">{_e(l["title"])}</a>'
                    for i, l in enumerate(all_links))
    head = (f'<header class="top"><div class="wrap"><h1>{_e(cfg.title)}</h1><p class="tag">{_e(cfg.tagline)}</p>'
            + (f'<span class="notice">{_e(cfg.notice)}</span>' if cfg.notice else "")
            + (f'<nav class="links">{links}</nav>' if links else "") + "</div></header>")
    stats = (f'<div class="stats"><div class="stat"><b>{done} / {len(milestones)}</b><span>milestones done</span>'
             f'<div class="bar"><i style="width:{pct}%"></i></div></div>'
             f'<div class="stat"><b>{_e(active["id"]) if active else "—"}</b><span>working on now{": " + _e(active["title"]) if active else ""}</span></div>'
             f'<div class="stat"><b>{len(decisions)}</b><span>decisions ({open_dec} open)</span></div>'
             f'<div class="stat"><b>{len(designs)}</b><span>designs evaluated</span></div>'
             f'<div class="stat"><b>{_e(log[0]["date"]) if log else "—"}</b><span>last change</span></div></div>')

    ms = "".join(
        f'<li><div><span class="pill {_e(m.get("status", "next"))}">{_e(m.get("status", "next"))}</span><br><b>{_e(m.get("id", ""))}</b></div>'
        f'<div><h3>{_md_inline(m.get("title", ""))}</h3><div class="when">Done when: {_md_inline(m.get("done_when", ""))}</div>'
        + (f'<p>{_md_inline(m["notes"])}</p>' if m.get("notes") else "")
        + "".join(f' <a href="../{_e(ev)}">{_e(Path(ev).name)}</a>' for ev in m.get("evidence", []) or []) + "</div></li>"
        for m in milestones)

    def metric(x: Dict[str, Any]) -> str:
        unit = f' {_e(x.get("unit"))}' if x.get("unit") else ""
        est = ' <span class="est">est.</span>' if x.get("estimate") else ""
        return f'<div class="metric {_e(x.get("level", ""))}"><b>{_e(x.get("value"))}{unit}</b><span>{_e(x.get("label"))}{est}</span></div>'

    def badges_html(d: Dict[str, Any]) -> str:
        bs = d.get("badges") or []
        return ("<p>" + "".join(f'<span class="pill {_e(b.get("level", ""))}" title="{_e(b.get("title", ""))}">{_e(b["label"])}</span> ' for b in bs)
                + "</p>") if bs else ""

    def links_html(d: Dict[str, Any]) -> str:
        ls = d.get("links") or []
        return ("<p>" + " · ".join(f'<a href="{_e(href(l["href"]))}">{_e(l["title"])}</a>' for l in ls) + "</p>") if ls else ""

    def design_card(d: Dict[str, Any]) -> str:
        checks = d.get("checks", {})
        tail = (f'<p>{checks.get("ok", 0)} ok · {checks.get("warn", 0)} warnings · {checks.get("fail", 0)} problems'
                + (f' · <a href="../{_e(d["link"])}">open</a>' if d.get("link") else "")
                + (f' · <code>{_e(d["file"])}</code>' if d.get("file") else "") + "</p>")
        return (f'<div class="card"><span class="pill {_e(d.get("verdict", "next"))}">{_e(d.get("verdict", ""))}</span>'
                f'<h3>{_e(d.get("name"))}</h3><p>{_md_inline(d.get("summary", ""))}</p>'
                f'<div class="metrics">{"".join(metric(x) for x in d.get("metrics", []))}</div>'
                + badges_html(d) + links_html(d) + tail + "</div>")

    ds = "".join(design_card(d) for d in designs)

    def decision(d: Dict[str, Any]) -> str:
        src = d.get("source") or {}
        quote = f'<blockquote>“{_e(src["quote"])}”</blockquote>' if src.get("quote") else ""
        ref = f'<p>Source: {_md_inline(src["ref"])}</p>' if src.get("ref") else ""
        alts = d.get("alternatives") or []
        alt = ("<p>Considered: " + "; ".join(_md_inline(a) for a in alts) + "</p>") if alts else ""
        return (f'<details class="decision"><summary><span class="pill {_e(d.get("status", "decided"))}">{_e(d.get("status", "decided"))}</span>'
                f'<b>{_e(d.get("title"))}</b><span class="d">{_e(d.get("id", ""))} · {_e(d.get("date", ""))} · {_e(src.get("kind", ""))}</span></summary>'
                f'<p><b>{_md_inline(d.get("decision", ""))}</b></p><p>{_md_inline(d.get("why", ""))}</p>{quote}{ref}{alt}</details>')

    decs = sorted(decisions, key=lambda d: (d.get("status") != "open", str(d.get("date", ""))), reverse=False)
    decs = [d for d in decs if d.get("status") == "open"] + sorted([d for d in decs if d.get("status") != "open"],
                                                                    key=lambda d: str(d.get("date", "")) + str(d.get("id", "")), reverse=True)
    doc_cards = "".join(f'<div class="card"><h3><a href="{_e(d["href"])}">{_e(d["title"])}</a></h3><p>{_e(d["summary"])}</p>'
                        f'<p><code>{_e(d["rel"])}</code> · {_e(d["mtime"])}</p></div>' for d in docs)
    log_rows = "".join(f'<tr><td>{_e(c["hash"])}</td><td>{_e(c["date"])}</td><td>{_e(c["subject"])}</td></tr>' for c in log)

    section = lambda t, body, empty: f'<h2 id="{slug(t)}">{t}</h2>' + (body or f'<p class="tag">{empty}</p>')
    main = (f'<main class="wrap">{stats}'
            + section("Progress", f'<ul class="milestones">{ms}</ul>' if ms else "", "No milestones file yet.")
            + section("Designs", f'<div class="grid">{ds}</div>' if ds else "", "No designs evaluated yet.")
            + section("Decisions", "".join(decision(d) for d in decs), "No decisions recorded yet.")
            + section("Documents", f'<div class="docs">{doc_cards}</div>' if doc_cards else "", "No documents configured.")
            + section("Recent changes", f'<div class="tablewrap"><table class="log">{log_rows}</table></div>' if log_rows else "", "No git history.")
            + f'<footer>Built {datetime.now().strftime("%Y-%m-%d %H:%M")} by cad-agent from the project files. Refresh to rebuild.</footer></main>')
    (out / "index.html").write_text(_page(cfg.title, nav_html(cfg, "overview", "../") + head + main, cfg.accent, theme=cfg.theme))
    # the same top bar for the project's own pages: they fetch site/nav.json and render it with webkit/appnav.js
    (out / "nav.json").write_text(json.dumps({"title": cfg.title, "nav": cfg.nav}, indent=1) + "\n")
    return {"site": str(out), "pages": len(pages), "milestones": len(milestones), "decisions": len(decisions),
            "designs": len(designs), "progress_pct": pct}


# ----------------------------------------------------------------------------- serving

def default_nav(root: Path, html_pages: Optional[List[str]] = None, site_pages: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """The top bar when the project configures none: the overview, the rendered documents, the 3D model, then each
    project HTML page (``cad: html_pages``, plus the cad-agent report, the simulation report, the design comparison
    and the search leaderboard when present), titled by its ``<title>``. Every page the local server sends gets this
    bar, so the pages link to each other."""
    root = Path(root)
    nav = [{"id": "overview", "title": "Overview", "href": "site/"}]
    if page_files(root, list(site_pages or [])):
        nav.append({"id": "docs", "title": "Docs", "href": "site/#documents"})
    if (root / "exports" / "view" / "view.json").is_file():
        nav.append({"id": "model", "title": "3D model", "href": KIT_URL.strip("/") + "/viewer.html"})
    seen = set()
    for rel in list(html_pages or []) + ["docs/cad-agent-report.html", "preview/simulation.html",
                                         "exports/explore/compare.html", "exports/explore/search/leaderboard.html"]:
        rel = posixpath.normpath(str(rel).replace("\\", "/")).lstrip("/")
        f = root / rel
        if not rel.endswith(".html") or rel in seen or rel.startswith("..") or not f.is_file():
            continue
        seen.add(rel)
        m = re.search(r"<title>(.*?)</title>", f.read_text(errors="replace")[:4000], re.S | re.I)
        title = html.unescape(m.group(1)).strip().split(" · ")[0].split(" | ")[0] if m else Path(rel).stem
        nav.append({"id": rel, "title": title[:28] or Path(rel).stem, "href": rel})
    return nav


_INJECT = ('<script type="module">import {{ mountAppNav }} from "{kit}appnav.js";'
           'mountAppNav({{ root: "/", current: {current}, injected: true }});</script>')
_OPT_OUT = re.compile(rb'<meta[^>]+name=["\']cadagent-nav["\'][^>]+content=["\']off["\']', re.I)


def inject_nav(page: bytes, request_path: str, nav: List[Dict[str, str]]) -> bytes:
    """Add the app-wide top bar to an HTML page the local server sends (bytes in, bytes out, so any encoding
    survives). Skipped when the page has a bar in its markup or opts out with <meta name="cadagent-nav" content="off">;
    a bar a page mounts from its own script replaces the injected one in the browser (webkit/appnav.js)."""
    if not nav or b"appnav" in page or _OPT_OUT.search(page):
        return page
    path = unquote(request_path.split("?")[0].split("#")[0])
    current = ""
    for n in nav:
        h = "/" + n["href"].split("#")[0]
        if not re.match(r"^/[a-z]+:", h) and (path == h or (h.endswith("/") and path in (h + "index.html", h.rstrip("/")))):
            current = n.get("id", n["href"])
            break
    tag = _INJECT.format(kit=KIT_URL, current=json.dumps(current)).encode()
    i = page.lower().rfind(b"</body>")
    return page[:i] + tag + page[i:] if i >= 0 else page + tag


def _stale(root: Path, cfg: SiteConfig) -> bool:
    index = root / SITE_DIR / "index.html"
    if not index.is_file():
        return True
    built = index.stat().st_mtime
    return any(p.stat().st_mtime > built for p in sources(root, cfg))


LIVE_URL = "/_cadagent/changes"
LIVE_SKIP = {".git", ".venv", "node_modules", "__pycache__", "build", "runs", "logs", "references", "vendor", ".pytest_cache"}
LIVE_EXT = {".html", ".js", ".css", ".json", ".md", ".png", ".jpg", ".svg", ".mp4", ".stl", ".step", ".3mf", ".glb", ".yaml"}


class _Watcher:
    """The newest modification time of the files pages show, for live reload while someone works on the project.
    `live_reload: {watch: [folders], skip: [folder names]}` in the site config narrows it; scans are cached for 1 s."""

    def __init__(self, root: Path, cfg: Dict[str, Any]):
        self.root = root
        self.dirs = [root / d for d in cfg.get("watch", [])] or [root]
        self.skip = LIVE_SKIP | set(cfg.get("skip", []))
        self._at, self._stamp = 0.0, 0.0

    def stamp(self) -> float:
        now = time.time()
        if now - self._at > 1.0:
            newest = 0.0
            for d in self.dirs:
                newest = max(newest, self._scan(d))
            self._at, self._stamp = now, newest
        return self._stamp

    def _scan(self, d: Path) -> float:
        newest = 0.0
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        if e.name not in self.skip and not e.name.startswith("."):
                            newest = max(newest, self._scan(Path(e.path)))
                    elif os.path.splitext(e.name)[1].lower() in LIVE_EXT:
                        newest = max(newest, e.stat().st_mtime)
        except OSError:
            pass
        return newest


def serve_site(root: Path, raw_site: Optional[Dict[str, Any]], default_title: str, host: str = "127.0.0.1",
               port: int = 0, auto_nav: Optional[Callable[[], List[Dict[str, str]]]] = None) -> Tuple[ThreadingHTTPServer, str]:
    """Serve the project root; ``/`` redirects to the site, which rebuilds when a source changed. Every HTML page
    goes out with the top bar: the config's ``nav``, else ``auto_nav()``, worked out again at most every 2 s so a
    report written while the server runs gets its tab."""
    root = Path(root).resolve()
    cfg = site_config(raw_site, default_title)
    build_site(root, raw_site, default_title, auto_nav)
    nav_cache = {"at": 0.0, "nav": cfg.nav}

    def current_nav() -> List[Dict[str, str]]:
        if cfg.nav or not auto_nav:
            return cfg.nav
        if time.time() - nav_cache["at"] > 2.0:
            nav_cache.update(at=time.time(), nav=auto_nav())
        return nav_cache["nav"]

    watch = _Watcher(root, cfg.live_reload or {})

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            if self.path.startswith(LIVE_URL):          # live reload: the newest change under the watched folders
                body = json.dumps({"stamp": watch.stamp()}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path in ("/", "/index.html"):
                self.send_response(302)
                self.send_header("Location", f"/{SITE_DIR}/")
                self.end_headers()
                return
            if self.path.startswith(f"/{SITE_DIR}/") and _stale(root, cfg):
                build_site(root, raw_site, default_title, auto_nav)
            if self._send_with_nav():
                return
            super().do_GET()

        def do_HEAD(self):  # noqa: N802 (http.server API): the same headers as GET
            if not self._send_with_nav(head=True):
                super().do_HEAD()

        def _send_with_nav(self, head: bool = False) -> bool:
            """Project HTML pages get the site's top bar on the way out (the files on disk are not changed), and
            site/nav.json is always the current bar."""
            nav = current_nav()
            if not nav:
                return False
            if self.path.split("?")[0] == f"/{SITE_DIR}/nav.json":
                body = (json.dumps({"title": cfg.title, "nav": nav}, indent=1) + "\n").encode()
                ctype = "application/json"
            else:
                target = Path(self.translate_path(self.path))
                if target.is_dir():
                    if not self.path.split("?")[0].endswith("/"):
                        return False                     # the stock handler redirects to the slash form
                    target = target / "index.html"
                if target.suffix.lower() not in (".html", ".htm") or not target.is_file():
                    return False
                body = inject_nav(target.read_bytes(), self.path, nav)
                ctype = "text/html"                      # no charset: the page's own <meta charset> still applies
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head:
                self.wfile.write(body)
            return True

        def translate_path(self, path):
            if path.startswith(KIT_URL):   # the web kit ships inside cad-agent
                rel = path[len(KIT_URL):].split("?")[0].split("#")[0]
                target = (KIT_DIR / rel).resolve()
                return str(target) if KIT_DIR in target.parents or target == KIT_DIR else str(KIT_DIR / "missing")
            return super().translate_path(path)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, fmt, *args):
            if os.environ.get("CAD_AGENT_SITE_LOG"):
                super().log_message(fmt, *args)

    server = ThreadingHTTPServer((host, port), partial(Handler, directory=str(root)))
    shown = "127.0.0.1" if host in ("", "0.0.0.0") else host
    return server, f"http://{shown}:{server.server_port}/{SITE_DIR}/"
