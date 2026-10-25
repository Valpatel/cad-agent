"""Standalone HTML page for a results dict (schema 1.0).

The results shape is the one ``cadagent.report.collect`` writes::

    {"schema_version": "1.0", "title": ..., "header_meta": {...}, "footer_meta": {...},
     "features": [{"feature_id", "feature_title",
                   "checks": [{"name", "status", "message"?, "error"?, "evidence"?, "links"?}]}]}

``evidence`` is ``{"type": "screenshot", "path", "title"?}``, ``{"type": "link",
"url", "label"?}`` or ``{"type": "log", "content"}``. The page carries its CSS
inline and only relative links, so it opens from file://.
"""

from __future__ import annotations

import html as _html
from typing import Any, Dict, Iterable, List, Mapping, Optional

SCHEMA_VERSION = "1.0"

_STATUS_TO_CANONICAL = {
    "pass": "pass", "passed": "pass", "ok": "pass", "true": "pass", "green": "pass",
    "fail": "fail", "failed": "fail", "error": "fail", "false": "fail", "red": "fail",
    "skip": "skip", "skipped": "skip", "n/a": "skip", "none": "skip",
}

def canonical_status(status: Any) -> str:
    """``pass``, ``fail`` or ``skip``. Anything unrecognised, including a missing
    status, is a failure, never a pass."""
    if status is None:
        return "fail"
    return _STATUS_TO_CANONICAL.get(str(status).strip().lower(), "fail")

def counts(checks: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    out = {"pass": 0, "fail": 0, "skip": 0}
    for check in checks:
        out[canonical_status(check.get("status"))] += 1
    return out

def feature_status(checks: List[Mapping[str, Any]]) -> str:
    """``fail`` if any check fails, ``pass`` if any passes, else ``skip``."""
    c = counts(checks)
    return "fail" if c["fail"] else "pass" if c["pass"] else "skip"

_CSS = """
:root{color-scheme:light dark;
--bg:#f5f7f9;--surface:#fff;--surface-2:#eef2f5;--text:#16212b;--muted:#5a6873;--line:#dde5eb;
--accent:#1f5f8b;--pass:#1d7a3e;--pass-bg:#e3f4e8;--fail:#b3261e;--fail-bg:#fbe5e3;
--skip:#6b6f76;--skip-bg:#eceef0;--warn:#8a5a00;--warn-bg:#fff4d6;--warn-line:#e8c66a}
@media (prefers-color-scheme:dark){:root{
--bg:#0f1418;--surface:#171e24;--surface-2:#1f2830;--text:#e4eaef;--muted:#9aa8b3;--line:#2b3640;
--accent:#7db7e0;--pass:#6fd394;--pass-bg:#173523;--fail:#ff8a80;--fail-bg:#3d1a18;
--skip:#a7adb4;--skip-bg:#262c32;--warn:#f2c76b;--warn-bg:#352a10;--warn-line:#6b5420}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
.page{max-width:1100px;margin:0 auto;padding:24px 16px 40px}
header h1{margin:0 0 8px;font-size:1.6rem;line-height:1.25}
.meta{display:flex;flex-wrap:wrap;gap:6px 14px;margin:0;padding:0;list-style:none;color:var(--muted);font-size:.9rem}
.meta b{color:var(--text);font-weight:600}
.totals{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 0}
.alert{margin:18px 0;padding:12px 16px;border:1px solid var(--warn-line);border-left-width:5px;
border-radius:8px;background:var(--warn-bg);color:var(--text)}
.alert strong{display:block;color:var(--warn)}
.panel{margin:18px 0;background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.panel>h2{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin:0;padding:12px 16px;
font-size:1.05rem;background:var(--surface-2);border-bottom:1px solid var(--line)}
.panel>h2 .count{margin-left:auto;font-size:.85rem;font-weight:400;color:var(--muted)}
.panel>.body{padding:12px 16px;overflow-x:auto}
.check{display:grid;grid-template-columns:4.2rem minmax(0,1fr) auto;gap:4px 12px;align-items:start;
padding:10px 16px;border-top:1px solid var(--line)}
.check:first-of-type{border-top:0}
.check .name{font-weight:600;overflow-wrap:anywhere}
.check .msg{grid-column:2;color:var(--muted);font-size:.92rem;overflow-wrap:anywhere}
.check .evidence{grid-column:3;grid-row:1/span 3}
.check .extra{grid-column:2/span 2;min-width:0}
.check img{display:block;width:140px;max-width:28vw;border-radius:6px;border:1px solid var(--line);background:var(--surface-2)}
.check pre{margin:6px 0 0;padding:8px 10px;max-height:16rem;overflow:auto;white-space:pre-wrap;
background:var(--surface-2);border-radius:6px;font-size:.82rem}
.links{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:.9rem}
.badge{display:inline-block;min-width:3.6rem;padding:2px 8px;border-radius:999px;text-align:center;
font-size:.75rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase}
.badge.pass{color:var(--pass);background:var(--pass-bg)}
.badge.fail{color:var(--fail);background:var(--fail-bg)}
.badge.skip{color:var(--skip);background:var(--skip-bg)}
footer{margin-top:28px;padding-top:12px;border-top:1px solid var(--line)}
@media (max-width:640px){.check{grid-template-columns:4.2rem minmax(0,1fr)}
.check .evidence{grid-column:2;grid-row:auto}.check .extra{grid-column:2}}
"""

def _esc(value: Any) -> str:
    return _html.escape(str(value), quote=True)

def _meta(meta: Optional[Mapping[str, Any]]) -> str:
    if not meta:
        return ""
    items = "".join(f"<li>{_esc(k).replace('_', ' ')}: <b>{_esc(v)}</b></li>" for k, v in meta.items())
    return f'<ul class="meta">{items}</ul>'

def _badge(status: str, label: Optional[str] = None) -> str:
    return f'<span class="badge {status}">{_esc(label or status)}</span>'

def _alert(alert: Mapping[str, Any]) -> str:
    title = f"<strong>{_esc(alert['title'])}</strong>" if alert.get("title") else ""
    return f'<div class="alert" role="note">{title}{_esc(alert.get("body", ""))}</div>'

def _evidence(evidence: Mapping[str, Any]) -> str:
    kind = evidence.get("type")
    if kind == "screenshot" and evidence.get("path"):
        path = _esc(evidence["path"])
        alt = _esc(evidence.get("title") or evidence["path"])
        return f'<a href="{path}"><img loading="lazy" src="{path}" alt="{alt}"></a>'
    if kind == "link" and evidence.get("url"):
        return f'<a href="{_esc(evidence["url"])}">{_esc(evidence.get("label") or evidence["url"])}</a>'
    if kind == "log":
        return f"<pre>{_esc(evidence.get('content', ''))}</pre>"
    return ""

def _check(check: Mapping[str, Any]) -> str:
    status = canonical_status(check.get("status"))
    evidence = check.get("evidence") or {}
    side = _evidence(evidence) if evidence.get("type") in ("screenshot", "link") else ""
    extra = []
    if evidence.get("type") == "log":
        extra.append(_evidence(evidence))
    if check.get("error") and status == "fail":
        extra.append(f"<pre>{_esc(check['error'])}</pre>")
    links = [link for link in check.get("links") or [] if isinstance(link, Mapping) and link.get("url")]
    if links:
        extra.append('<div class="links">' + "".join(
            f'<a href="{_esc(link["url"])}">{_esc(link.get("label") or link["url"])}</a>' for link in links
        ) + "</div>")
    return (
        f'<div class="check {status}">{_badge(status)}'
        f'<div class="name">{_esc(check.get("name", ""))}</div>'
        + (f'<div class="evidence">{side}</div>' if side else "")
        + (f'<div class="msg">{_esc(check["message"])}</div>' if check.get("message") else "")
        + (f'<div class="extra">{"".join(extra)}</div>' if extra else "")
        + "</div>"
    )

def _panel(feature: Mapping[str, Any]) -> str:
    checks = list(feature.get("checks") or [])
    c = counts(checks)
    rows = "".join(_check(check) for check in checks)
    return (
        f'<section class="panel" id="{_esc(feature.get("feature_id", ""))}">'
        f'<h2>{_badge(feature_status(checks))}{_esc(feature.get("feature_title", ""))}'
        f'<span class="count">{c["pass"]} pass · {c["fail"]} fail · {c["skip"]} skip</span></h2>'
        f"{rows}</section>"
    )

def render_page(
    results: Mapping[str, Any],
    alerts: Iterable[Mapping[str, Any]] = (),
    extra_panels: Iterable[str] = (),
) -> str:
    """The full HTML document. ``alerts`` are ``{severity, title, body}`` dicts;
    ``extra_panels`` are trusted HTML fragments placed after the feature panels."""
    title = results.get("title") or "CAD verification"
    features = list(results.get("features") or [])
    total = counts(c for f in features for c in f.get("checks") or [])
    verdict = "fail" if total["fail"] else "pass" if total["pass"] else "skip"
    totals = '<div class="totals">' + _badge(verdict, "all pass" if verdict == "pass" else verdict) + "".join(
        _badge(s, f"{n} {s}") for s, n in total.items()
    ) + "</div>"
    extra = "".join(
        f'<section class="panel"><div class="body">{panel}</div></section>' for panel in extra_panels
    )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head>"
        '<body><div class="page">'
        f"<header><h1>{_esc(title)}</h1>{_meta(results.get('header_meta'))}{totals}</header>"
        f"{''.join(_alert(a) for a in alerts)}"
        f"<main>{''.join(_panel(f) for f in features)}{extra}</main>"
        f"<footer>{_meta(results.get('footer_meta'))}</footer>"
        "</div></body></html>\n"
    )
