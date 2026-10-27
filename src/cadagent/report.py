"""Collect a CAD project's check outputs into results JSON (schema 1.0).

``collect(project)`` reads what the build and the project's checks wrote; it
runs nothing. Features:

* ``cad-parts``: one row per printable part — valid CAD, exactly one solid,
  watertight STL, within the printer bed. Evidence: ``preview/part-<name>.png``.
* ``cad-print-files``: STL, 3MF and STEP present for every part.
* ``cad-checks``: one row per configured check, from its ``pass_key``.
* ``cad-links``: local links in ``html_pages`` resolve.

A missing file, missing key or non-boolean verdict is a failure, never a pass.
Evidence paths are relative to ``docs_dir``, where the HTML report is written.
The JSON keeps the vptest web schema 1.0 shape, so ``vptest web`` can render it too.
"""

from __future__ import annotations

import html as _html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from cadagent.geometry import within_bed
from cadagent.htmlreport import SCHEMA_VERSION, canonical_status, render_page
from cadagent.links import missing_links
from cadagent.project import CadProject, Check, lookup

RESULTS_NAME = "cad-agent-results.json"
REPORT_NAME = "cad-agent-report.html"
PRINT_FORMATS = ("stl", "3mf", "step")
HONESTY_NOTE = (
    "CAD checks only. They do not verify physical fit, print quality, slicer "
    "output, fastener engagement, thermal behaviour or load capacity."
)

def _rel(path: Path, base: Path) -> str:
    return Path(os.path.relpath(Path(path).resolve(), Path(base).resolve())).as_posix()

def _row(name: str, ok: bool, message: str = "", error: str = "",
         evidence: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    row: Dict[str, Any] = {"name": name, "status": "pass" if ok else "fail"}
    if message:
        row["message"] = message
    if error and not ok:
        row["error"] = error
    if evidence:
        row["evidence"] = evidence
    return row

def _load_json(path: Path) -> Tuple[Any, Optional[str]]:
    if not path.is_file():
        return None, f"file not found: {path}"
    try:
        return json.loads(path.read_text()), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable JSON in {path}: {exc}"

def _fmt_mm(values: Sequence[float]) -> str:
    return " × ".join(f"{float(v):g}" for v in values)

def load_parts(project: CadProject) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """The parts file as ``{part: info}``, or ``({}, error)``."""
    data, error = _load_json(project.parts_file)
    if error:
        return {}, error
    if not isinstance(data, dict) or not data:
        return {}, f"{project.parts_file} must be a non-empty object of part -> checks"
    bad = [k for k, v in data.items() if not isinstance(v, dict)]
    if bad:
        return {}, f"{project.parts_file}: entries are not objects: {bad}"
    return data, None

def _part_row(project: CadProject, part: str, info: Dict[str, Any], report_dir: Path) -> Dict[str, Any]:
    problems: List[str] = []
    if info.get("cad_valid") is not True:
        problems.append("CAD shape not valid" if "cad_valid" in info else "cad_valid not recorded")
    if info.get("solid_count") != 1:
        problems.append(f"solid_count is {info.get('solid_count', 'not recorded')} (expected 1)")
    if info.get("watertight") is not True:
        problems.append("STL not watertight" if "watertight" in info else "watertight not recorded")
    bounds = info.get("print_bounds_mm")
    bed = project.printer.bed_mm
    facts = []
    if isinstance(bounds, list) and len(bounds) == 3:
        facts.append(f"{_fmt_mm(bounds)} mm")
    if bed:
        printer = project.printer.name or "printer"
        if not (isinstance(bounds, list) and len(bounds) == 3):
            problems.append("print_bounds_mm not recorded; bed fit unknown")
        elif not within_bed(bounds, bed):
            problems.append(f"{_fmt_mm(bounds)} mm exceeds the {printer} bed {_fmt_mm(bed)} mm")
        else:
            facts.append(f"fits {printer} bed {_fmt_mm(bed)} mm")
    else:
        facts.append("bed fit not checked (cad.printer.bed_mm not set)")
    image = project.preview_dir / f"part-{part}.png"
    evidence = (
        {"type": "screenshot", "path": _rel(image, report_dir), "title": project.part_label(part)}
        if image.is_file() else None
    )
    ok = not problems
    message = ("valid single solid · watertight · " if ok else "; ".join(problems) + " · ") + " · ".join(facts)
    return _row(project.part_label(part), ok, message, "\n".join(problems), evidence)

def parts_feature(project: CadProject, report_dir: Path) -> Dict[str, Any]:
    parts, error = load_parts(project)
    checks = (
        [_row("parts file", False, "no part results; run the build", error)]
        if error else [_part_row(project, p, info, report_dir) for p, info in parts.items()]
    )
    return {"feature_id": "cad-parts", "feature_title": "Printed parts", "checks": checks}

def print_files_feature(project: CadProject, report_dir: Path) -> Dict[str, Any]:
    parts, error = load_parts(project)
    if error:
        return {"feature_id": "cad-print-files", "feature_title": "Print files",
                "checks": [_row("parts file", False, "no part list", error)]}
    checks = []
    for part in parts:
        files = {ext: project.exports_dir / f"{part}.{ext}" for ext in PRINT_FORMATS}
        missing = [str(p.relative_to(project.root)) for p in files.values() if not p.is_file()]
        ok = not missing
        evidence = None
        if files["3mf"].is_file():
            evidence = {"type": "link", "url": _rel(files["3mf"], report_dir), "label": f"{part}.3mf"}
        message = "STL + 3MF (print orientation), STEP (assembly)" if ok else "missing " + ", ".join(missing)
        checks.append(_row(project.part_label(part), ok, message, "\n".join(missing), evidence))
    return {"feature_id": "cad-print-files", "feature_title": "Print files", "checks": checks}

def _check_row(project: CadProject, check: Check, report_dir: Path) -> Dict[str, Any]:
    path = project.root / check.file
    data, error = _load_json(path)
    title = f"{check.id} · {check.title}" if check.title != check.id else check.id
    if error:
        return _row(title, False, "check output missing or unreadable", error)
    failed, unknown = [], []
    for key in check.pass_keys:
        found, value = lookup(data, key)
        if not found:
            unknown.append(f"{key}: not present")
        elif not isinstance(value, bool):
            unknown.append(f"{key}: {value!r} is not a boolean")
        elif value is False:
            failed.append(key)
    from cadagent.evidence import hashes_are_current
    if isinstance(data, dict) and not hashes_are_current(project.root, data):
        unknown.append("source or artifact evidence is stale")
    ok = not failed and not unknown
    problems = [f"{k} is false" for k in failed] + unknown
    evidence = None
    for image in check.evidence:
        if (project.root / image).is_file():
            evidence = {"type": "screenshot", "path": _rel(project.root / image, report_dir), "title": check.title}
            break
    if evidence is None:
        evidence = {"type": "link", "url": _rel(path, report_dir), "label": check.file}
    keys = ", ".join(check.pass_keys)
    message = f"{keys} true in {check.file}" if ok else "; ".join(problems) + f" ({check.file})"
    if isinstance(data, dict) and data.get("physical_fit_verified") is False:
        message += " · physical fit not verified"
    row = _row(title, ok, message, "\n".join(problems), evidence)
    if check.links:
        row["links"] = check.links
    return row

def checks_feature(project: CadProject, report_dir: Path) -> Dict[str, Any]:
    checks = [_check_row(project, c, report_dir) for c in project.checks]
    if not checks:
        checks = [{"name": "no checks configured", "status": "skip",
                   "message": "add cad.checks to cad-agent.yaml"}]
    return {"feature_id": "cad-checks", "feature_title": "Design checks", "checks": checks}

def links_feature(project: CadProject) -> Dict[str, Any]:
    checks = []
    for page in project.html_pages:
        missing = missing_links([page], project.root)
        ok = not missing
        message = "all local links resolve" if ok else f"{len(missing)} broken local link(s)"
        checks.append(_row(page, ok, message, "\n".join(missing)))
    if not checks:
        checks = [{"name": "no pages configured", "status": "skip",
                   "message": "add cad.html_pages to cad-agent.yaml"}]
    return {"feature_id": "cad-links", "feature_title": "Review pages and links", "checks": checks}

def collect(project: CadProject) -> Dict[str, Any]:
    """Results dict in schema 1.0 (the vptest web shape; ``vptest web validate`` accepts it)."""
    report_dir = project.docs_dir
    features = [
        parts_feature(project, report_dir),
        print_files_feature(project, report_dir),
        checks_feature(project, report_dir),
        links_feature(project),
    ]
    counts = summarize({"features": features})
    revision = project.resolve_revision()
    return {
        "schema_version": SCHEMA_VERSION,
        "title": f"{project.title} · CAD verification",
        "features": features,
        "header_meta": {
            "project": project.name,
            "revision": f"rev {revision}" if revision else "revision unknown",
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        },
        "footer_meta": {
            "checks": f"{counts['pass']} pass / {counts['fail']} fail / {counts['skip']} skip",
            "physical_fit": "physical fit NOT verified (CAD only)",
            "slicer": "slicer not run",
        },
        "project": project.name,
        "revision": revision,
        "physical_fit_verified": False,
        "slicer_run": False,
        "pass": counts["fail"] == 0,
    }

def summarize(results: Dict[str, Any]) -> Dict[str, int]:
    counts = {"pass": 0, "fail": 0, "skip": 0}
    for feature in results.get("features") or []:
        for check in feature.get("checks") or []:
            counts[canonical_status(check.get("status"))] += 1
    return counts

def failures(results: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    return [
        (feature.get("feature_title", ""), check)
        for feature in results.get("features") or []
        for check in feature.get("checks") or []
        if canonical_status(check.get("status")) == "fail"
    ]

def render_html(results: Dict[str, Any], extra_panels: Iterable[str] = ()) -> str:
    """A standalone page (styles inline, relative links, so it opens from file://)."""
    alerts = [{"severity": "warning", "title": "CAD verification only", "body": HONESTY_NOTE}]
    return render_page(results, alerts=alerts, extra_panels=extra_panels)

def write_report(project: CadProject) -> Tuple[Path, Path, Dict[str, Any]]:
    """Write ``<exports>/cad-agent-results.json`` and ``<docs>/cad-agent-report.html``."""
    results = collect(project)
    project.exports_dir.mkdir(parents=True, exist_ok=True)
    project.docs_dir.mkdir(parents=True, exist_ok=True)
    json_path = project.exports_dir / RESULTS_NAME
    json_path.write_text(json.dumps(results, indent=2) + "\n")
    parts, _ = load_parts(project)
    extra = [downloads_snippet(project, page_dir=project.docs_dir)] if parts else []
    html_path = project.docs_dir / REPORT_NAME
    html_path.write_text(render_html(results, extra))
    return json_path, html_path, results

def bambu_studio_url(file_url: str, name: str) -> str:
    """``bambustudio://open`` link; ``file_url`` must be an absolute http(s) URL."""
    from urllib.parse import quote

    if not file_url.startswith(("http://", "https://")):
        raise ValueError(f"Bambu Studio needs an absolute http(s) URL, got {file_url!r}")
    return f"bambustudio://open?file={quote(file_url, safe='')}&name={quote(name, safe='')}"

# the var() fallbacks keep the snippet styled on pages without the report's tokens
_DOWNLOADS_CSS = (
    ".vcad-dl{border-collapse:collapse;width:100%}"
    ".vcad-dl td,.vcad-dl th{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line,#dde5eb);vertical-align:middle}"
    ".vcad-dl img{width:110px;border-radius:6px;background:var(--surface-2,#f3f5f7);display:block}"
    ".vcad-dl a{font-weight:600}.vcad-dl .vcad-missing{color:var(--fail,#b3261e)}"
)

# Upgrades the slicer links in place when the page is served over http(s); the
# slicer fetches the 3MF by URL, which a file:// page cannot provide.
_DOWNLOADS_JS = (
    "(function(){if(!location.protocol.startsWith('http'))return;"
    "document.querySelectorAll('a[data-vcad-3mf]').forEach(function(a){"
    "var u=new URL(a.getAttribute('data-vcad-3mf'),location.href).href;"
    "a.href='bambustudio://open?file='+encodeURIComponent(u)+'&name='+encodeURIComponent(a.getAttribute('data-vcad-name'));"
    "a.textContent='Open in Bambu Studio';});})();"
)

def downloads_snippet(
    project: CadProject,
    page_dir: Optional[Path] = None,
    parts: Optional[Iterable[str]] = None,
) -> str:
    """HTML table: thumbnail, part, STL / 3MF / STEP links and a slicer link per part.

    Paths are relative to ``page_dir`` (default ``preview_dir``), so the snippet
    can be dropped into any page of the project. Missing files are shown as
    missing, not linked. The Bambu Studio link only works when the page is
    served over http (``cad-agent serve``); from file:// it downloads the 3MF.
    """
    page_dir = Path(page_dir or project.preview_dir)
    names = list(parts) if parts is not None else list(load_parts(project)[0])
    esc = _html.escape
    rows = []
    for part in names:
        image = project.preview_dir / f"part-{part}.png"
        thumb = (
            f'<a href="{esc(_rel(image, page_dir))}"><img loading="lazy" src="{esc(_rel(image, page_dir))}" '
            f'alt="{esc(part)}"></a>' if image.is_file() else '<span class="vcad-missing">no render</span>'
        )
        cells = []
        for ext in PRINT_FORMATS:
            path = project.exports_dir / f"{part}.{ext}"
            cells.append(
                f'<td><a href="{esc(_rel(path, page_dir))}" download>{ext.upper()}</a></td>'
                if path.is_file() else f'<td><span class="vcad-missing">{ext.upper()} missing</span></td>'
            )
        three_mf = project.exports_dir / f"{part}.3mf"
        slicer = (
            f'<td><a href="{esc(_rel(three_mf, page_dir))}" data-vcad-3mf="{esc(_rel(three_mf, page_dir))}" '
            f'data-vcad-name="{esc(part)}" title="bambustudio:// link when served over http">3MF (serve over http for Bambu Studio)</a></td>'
            if three_mf.is_file() else "<td></td>"
        )
        rows.append(f"<tr><td>{thumb}</td><td>{esc(project.part_label(part))}</td>{''.join(cells)}{slicer}</tr>")
    return (
        '<section class="vcad-downloads"><h2>Print files</h2>'
        f"<style>{_DOWNLOADS_CSS}</style>"
        '<p>STL and 3MF are in print orientation (3MF centred on the bed); STEP is in assembly coordinates.</p>'
        '<table class="vcad-dl"><thead><tr><th></th><th>Part</th><th>STL</th><th>3MF</th><th>STEP</th><th>Slicer</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"<script>{_DOWNLOADS_JS}</script></section>"
    )
