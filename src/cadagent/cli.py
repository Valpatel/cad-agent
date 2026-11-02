"""``cad-agent <subcommand>``: the parser (``build_parser``), ``main`` and the handlers.

Exit codes: 0 all good, 1 a step or check failed, 2 the project or environment
is not usable (bad config, missing dependency, missing build output).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from cadagent._deps import MissingDependency
from cadagent.project import CadConfigError, CadProject, SourceDateEpochError, Step, load_project

SUBCOMMANDS = ("build", "export-3mf", "holes", "check", "report", "package", "serve", "site", "view", "slice", "webkit", "pcb-check", "all",
               "mcmaster", "catalogue", "compare", "optimise", "dossier", "gates", "review-packet",
               "review-section", "agents", "motion-trace", "release", "snapfit", "inserts", "bearings",
               "overhangs")
LOG_TAIL_LINES = 20

class _Unusable(Exception):
    """Raised inside a subcommand for an exit-2 condition with a message."""

def _say(msg: str) -> None:
    print(msg, flush=True)

def _err(msg: str) -> None:
    print(f"cad-agent: {msg}", file=sys.stderr, flush=True)

def _tail(path: Path, lines: int = LOG_TAIL_LINES) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""

def select_steps(project: CadProject, start: Optional[str] = None, only: Optional[List[str]] = None) -> List[Step]:
    names = [s.name for s in project.steps]
    for name in [start] + list(only or []):
        if name is not None and name not in names:
            raise CadConfigError(f"unknown step {name!r}; steps: {names}")
    steps = project.steps
    if start is not None:
        steps = steps[names.index(start):]
    if only:
        steps = [s for s in steps if s.name in set(only)]
    return steps

def run_step(project: CadProject, step: Step) -> Dict[str, Any]:
    """Run one step with the project python, cwd = project root. Never raises for
    a failing script; the result carries ``ok`` and the reason."""
    script = project.root / step.run
    result: Dict[str, Any] = {"name": step.name, "ok": False, "seconds": 0.0, "log": None, "reason": ""}
    if not script.is_file():
        result["reason"] = f"script not found: {script}"
        return result
    env = dict(os.environ, PYTHONUNBUFFERED="1", CAD_AGENT_PROJECT=str(project.root))
    cmd = [project.python, str(script)]
    log_path = project.exports_dir / step.log if step.log else None
    started = time.monotonic()
    try:
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            result["log"] = str(log_path)
            with open(log_path, "w") as log:
                proc = subprocess.run(cmd, cwd=project.root, env=env, stdout=log,
                                      stderr=subprocess.STDOUT, timeout=step.timeout_s)
        else:
            proc = subprocess.run(cmd, cwd=project.root, env=env, timeout=step.timeout_s)
    except subprocess.TimeoutExpired:
        result["reason"] = f"timed out after {step.timeout_s}s"
    except OSError as exc:
        result["reason"] = f"could not start {project.python}: {exc}"
    else:
        result["ok"] = proc.returncode == 0
        result["reason"] = "" if result["ok"] else f"exit code {proc.returncode}"
    result["seconds"] = round(time.monotonic() - started, 2)
    return result

def cmd_build(project: CadProject, args: argparse.Namespace) -> int:
    steps = select_steps(project, getattr(args, "from_step", None), getattr(args, "only", None))
    if not steps:
        raise _Unusable("no build steps configured (cad.steps)")
    selected = {s.name for s in steps}
    total = 0.0
    for i, step in enumerate(steps, 1):
        skipped_needs = [n for n in step.needs if n not in selected]
        note = f" (needs {', '.join(skipped_needs)}, not run now)" if skipped_needs else ""
        _say(f"[{i}/{len(steps)}] {step.name}: {step.run}{note}")
        res = run_step(project, step)
        total += res["seconds"]
        if not res["ok"]:
            _say(f"  FAILED {step.name} after {res['seconds']:.1f}s: {res['reason']}")
            if res["log"]:
                _say(f"  log: {res['log']}")
                tail = _tail(Path(res["log"]))
                if tail:
                    _say("  " + tail.replace("\n", "\n  "))
            _say(f"build stopped at {step.name}; {i - 1}/{len(steps)} step(s) passed ({total:.1f}s)")
            return 1
        _say(f"  ok {res['seconds']:.1f}s" + (f" -> {res['log']}" if res["log"] else ""))
    _say(f"build ok: {len(steps)} step(s) in {total:.1f}s")
    return 0

def cmd_export_3mf(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.manufacturing.mesh3mf import export_parts_3mf
    from cadagent.publish.report import load_parts

    parts, error = load_parts(project)
    if error:
        raise _Unusable(error)
    if not project.printer.bed_mm:
        raise _Unusable("cad.printer.bed_mm is required to centre 3MF files on the bed")
    reports = export_parts_3mf(project.exports_dir, list(parts), project.printer.bed_mm[:2])
    for r in reports:
        _say(f"  {r['part']}.3mf  {r['triangles']} triangles  watertight  {r['volume_mm3']:.1f} mm3")
    _say(f"{len(reports)} 3MF file(s) written and read back")
    return _export_plates(project, list(parts))

def _export_plates(project: CadProject, parts: List[str]) -> int:
    """The build plates file after the per-part 3MFs; 1 when the parts cannot be laid out."""
    from cadagent.manufacturing.plates import PlatesError, export_plates

    try:
        rec = export_plates(project, parts)
    except PlatesError as exc:
        _say(f"plates: FAILED: {exc}")
        return 1
    if rec is None:
        return 0
    for p in rec["plates"]:
        _say(f"  plate {p['plate']}  {p['name']:<28} {len(p['parts'])} part(s)  {p['covered'] * 100:.0f} % covered")
    for w in rec["warnings"]:
        _say(f"  note: {w}")
    _say(f"{sum(rec['quantities'].values())} copies on {len(rec['plates'])} plate(s), read back -> {rec['file']}")
    return 0

def cmd_slice(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.manufacturing.slicer import engine_executable, engine_of, not_installed, slice_project

    engine = engine_of(project)
    if not engine_executable(engine):
        raise _Unusable(f"{not_installed(engine)}; nothing was sliced")
    try:
        rep = slice_project(project, getattr(args, "parts", None) or None)
    except (ValueError, KeyError, FileNotFoundError) as exc:   # PrusaSlicer: a profile name or override key it lacks
        if engine == "bambu":
            raise
        raise _Unusable(f"cannot slice: {exc.args[0] if exc.args else exc}") from None
    for name, row in rep["parts"].items():
        if row.get("grams"):
            minutes = f"{row['minutes']:7.1f} min" if row.get("minutes") is not None else "   time not reported"
            flag = "  NOT OK" if row.get("ok") is False else ""
            _say(f"  {name:<24} {row['grams']:8.1f} g  {minutes}{flag}")
        else:
            _say(f"  {name:<24} FAILED: {row.get('error')}")
        # what PrusaSlicer's log said (Bambu Studio rows carry none of these)
        if row.get("stability_issues"):
            _say(f"      stability: {', '.join(row['stability_issues'])}")
        for level in ("errors", "warnings"):
            for line in row.get(level) or []:
                if "print stability issues" not in line:      # listed above, by category
                    _say(f"      {level[:-1]}: {line}")
    not_ok = [n for n, row in rep["parts"].items() if row.get("ok") is False and row.get("grams")]
    if not_ok:
        _say(f"{len(not_ok)} part(s) sliced but not ok (a slicer error or print stability issue): {', '.join(not_ok)}")
    _say(f"{rep['total_grams']} g, {rep['total_hours']} h ({rep['process']}, {rep['filament']}) -> {rep['path']}")
    return 0 if rep["pass"] else 1

def _print_results(results: Dict[str, Any]) -> None:
    from cadagent.publish.report import summarize

    width = max([len(c.get("name", "")) for f in results["features"] for c in f["checks"]] + [10])
    width = min(width, 48)
    for feature in results["features"]:
        _say(feature["feature_title"])
        for check in feature["checks"]:
            status = str(check.get("status", "")).upper()
            _say(f"  {status:<5} {check.get('name', '')[:width]:<{width}}  {check.get('message', '')}")
    counts = summarize(results)
    _say(f"{counts['pass']} pass / {counts['fail']} fail / {counts['skip']} skip"
         " · CAD only: physical fit not verified, " + _slicer_note(results))

def _slicer_note(results: Dict[str, Any]) -> str:
    return results.get("footer_meta", {}).get("slicer", "slicer not run")

def cmd_check(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.publish.report import collect, summarize

    results = collect(project)
    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
    else:
        _print_results(results)
    return 1 if summarize(results)["fail"] else 0

def cmd_report(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.publish.report import summarize, write_report

    json_path, html_path, results = write_report(project)
    _print_results(results)
    _say(f"results: {json_path}")
    _say(f"report:  {html_path}")
    if getattr(args, "open", False):
        import webbrowser
        webbrowser.open(html_path.resolve().as_uri())
    return 1 if summarize(results)["fail"] else 0

def cmd_package(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.package import build_package

    try:
        result = build_package(project)
    except (ValueError, FileNotFoundError) as exc:
        raise _Unusable(str(exc)) from exc
    for pattern in result.unmatched:
        _say(f"  WARN include pattern matched nothing: {pattern}")
    _say(f"packaged {len(result.files)} file(s): {result.zip_path}")
    _say(f"manifest: {result.manifest_path}")
    return 0

def cmd_release(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.publish.release import build_release

    out = Path(args.out).expanduser() if getattr(args, "out", None) else None
    try:
        result = build_release(project, out=out, make_zip=not getattr(args, "no_zip", False),
                               revision=getattr(args, "revision", None), date=getattr(args, "date", None))
    except (FileNotFoundError, FileExistsError) as exc:
        raise _Unusable(str(exc)) from exc
    for w in result.warnings:
        _say(f"  WARN {w}")
    _say(f"release: {len(result.parts)} part(s), {len(result.files)} file(s): {result.folder / 'index.html'}")
    if result.zip_path:
        _say(f"zip: {result.zip_path}")
    return 0

def cmd_serve(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.publish.serve import serve

    return serve(project, getattr(args, "host", None), getattr(args, "port", None))

def cmd_site(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.publish.site import build_site, default_nav, serve_site
    from cadagent.publish.site_review import nav_entries

    site = project.site
    from cadagent.review.gates.run import enabled
    review = project if enabled(project) else None     # a dossier or gates project gets the review pages
    # without a configured `nav`, every page still gets a top bar: the overview, docs, 3D model, the review pages
    # and the HTML pages
    auto_nav = lambda: default_nav(project.root, project.html_pages, site.get("pages"), nav_entries(project))  # noqa: E731
    gates_exports = project.exports_dir if review is not None else None
    if not getattr(args, "serve", False):
        summary = build_site(project.root, site, project.title, auto_nav, gates_exports, review)
        _say(f"site: {summary['site']}/index.html ({summary['pages']} pages, {summary['milestones']} milestones, "
             f"{summary['decisions']} decisions, {summary['designs']} designs)")
        if "review" in summary:
            r = summary["review"]
            graph = {"graphviz": "drawn by Graphviz", "python": "drawn by the built-in layout"}.get(r["graph"], "none yet")
            _say(f"review: {summary['site']}/review/ ({r['sections']} section page(s), requirements, gates; "
                 f"connectivity graph {graph})")
        return 0
    host = getattr(args, "host", None) or project.serve.host
    port = project.serve.port if getattr(args, "port", None) is None else args.port
    server, url = serve_site(project.root, site, project.title, host, port, auto_nav, gates_exports, review)
    project.preview_dir.mkdir(parents=True, exist_ok=True)
    (project.preview_dir / "site-url.txt").write_text(url + "\n")
    print(url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

def cmd_view(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.publish.view import export_view

    r = export_view(project)
    _say(f"view: {r['manifest']} ({r['parts']} parts" + (f"; no STEP for {', '.join(r['skipped'])}" if r["skipped"] else "") + ")")
    _say("open it with `cad-agent site --serve` (3D model link) or webkit/viewer.html")
    return 0

def cmd_webkit(project: CadProject, args: argparse.Namespace) -> int:
    import shutil
    from cadagent.publish.site import KIT_DIR

    dest = (project.root / args.dest).resolve()
    shutil.copytree(KIT_DIR, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    _say(f"webkit: copied to {dest}")
    return 0

def cmd_pcb_check(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.electrical.pcb import evidence_bundle, manifest_problems
    config_path = project.root / args.manifest
    try:
        manifest = json.loads(config_path.read_text())
    except (OSError, ValueError) as exc:
        raise _Unusable(f"cannot read evidence manifest {args.manifest}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise _Unusable(f"{args.manifest}: the evidence manifest must be a JSON object")
    fields = [manifest.get("reports", {}), manifest.get("sources", []), manifest.get("release_gates", []),
              manifest.get("waivers")]
    problems = manifest_problems(*fields)
    if problems:
        raise _Unusable(f"{args.manifest}: " + "; ".join(problems))
    bundle = evidence_bundle(project.root, *fields)
    destination = project.root / args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(bundle, indent=2) + "\n")
    for problem in bundle["problems"]:
        _say(f"  {problem}")
    for check in bundle["checks"]:
        if check["reason"]:
            _say(f"  {check['kind']}: {check['reason']}")
    _say(f"PCB checks: {'pass' if bundle['pass'] else 'FAIL'}; production: {'qualified' if bundle['production_ready'] else 'not released'}")
    return 0 if bundle['pass'] else 1


def cmd_dossier(project: CadProject, args: argparse.Namespace) -> int:
    """Lint the design dossier, compute every item's status and write exports/dossier-status.json and
    exports/gates/dossier-lint.json (docs/dossier.md "Lint and status")."""
    from cadagent.review.dossier.lint import STATUSES, lint_project, write_outputs

    minimum = None if getattr(args, "min_status", "gated") == "none" else getattr(args, "min_status", "gated")
    result = lint_project(project, min_section_status=minimum)
    if result is None:
        raise _Unusable("no dossier: add `dossier: dossier/project.yaml` to the cad: section (docs/dossier.md)")
    if not getattr(args, "no_write", False):
        status_path, verdict_path = write_outputs(result, project.exports_dir)
    if getattr(args, "json", False):
        print(json.dumps(result.to_status(), indent=2))
        return 0 if result.passed else 1
    for sid, row in result.sections.items():
        _say(f"{row['status'].upper():<10} {sid}  {row['title']}")
        for pid in row["parts"]:
            prow = result.parts[pid]
            why = f"  ({'; '.join(prow['blocked_by'])})" if prow["blocked_by"] else ""
            _say(f"  {prow['status']:<10} {pid}{why}")
    for f in result.findings:
        _say(f"  {f.severity.upper():<7} {f.code:<26} {f}")
    counts = {s: sum(1 for r in result.sections.values() if r["status"] == s) for s in STATUSES}
    _say(f"dossier: {len(result.errors)} error(s), {len(result.warnings)} warning(s); sections "
         + ", ".join(f"{n} {s}" for s, n in counts.items() if n) + " · declarations only, physical fit not verified")
    if not getattr(args, "no_write", False):
        _say(f"status:  {status_path}")
        _say(f"verdict: {verdict_path}")
    return 0 if result.passed else 1

def cmd_review_packet(project: CadProject, args: argparse.Namespace) -> int:
    """Render each section's review packet: exports/review/<section>/*.png and manifest.json
    (docs/review-packet.md)."""
    from cadagent.review.packet import PacketError, plan_project_packet, project_sections, review_packet

    try:
        size = tuple(int(v) for v in args.size.lower().split("x"))
    except ValueError:
        size = ()
    if len(size) != 2 or min(size) < 200:
        raise _Unusable(f"--size {args.size!r}: give WIDTHxHEIGHT, each at least 200")
    try:
        sections = list(args.sections or project_sections(project.root))
        for sid in sections:
            if args.list:
                manifest, target = plan_project_packet(sid, root=project.root, explode=args.explode,
                                                       context=args.context)
            else:
                manifest = review_packet(sid, root=project.root, size=size, explode=args.explode,
                                         context=args.context, only=args.view or None)
            _packet_summary(manifest, listed=args.list)
    except PacketError as exc:
        raise _Unusable(str(exc)) from None
    return 0


def cmd_review_section(project: CadProject, args: argparse.Namespace) -> int:
    """The reviewer pass (plan §5.3, T11): write the reviewer's prompt bundle for a section, or check and submit a
    filled-in reviewer record (docs/dossier.md "The reviewer pass")."""
    from cadagent.review.dossier.review import ReviewError, submit_record, write_bundle

    record = args.submit or args.check
    try:
        if record:
            path, rec, problems = submit_record(project, args.section, record, write=bool(args.submit))
            for prob in problems:
                _say(f"  REFUSED {prob}")
            if problems:
                _say(f"review-section {args.section}: the record is not accepted ({len(problems)} problem(s)); "
                     "nothing written")
                return 1
            if path is None:
                _say(f"review-section {args.section}: the record is valid ({rec['verdict']}, actor {rec['actor']}); "
                     "not written (--check)")
                return 0
            try:
                shown = path.resolve().relative_to(Path(project.root).resolve()).as_posix()
            except ValueError:
                shown = str(path)
            _say(f"review-section {args.section}: {rec['verdict']} by {rec['actor']} -> {shown}")
            from cadagent.review.dossier.lint import lint_project
            res = lint_project(project, min_section_status=None)
            row = (res.sections.get(args.section) if res is not None else None) or {}
            _say(f"  section status now: {row.get('status', '?')}"
                 + (f" ({'; '.join(row.get('blocked_by') or [])})" if row.get("blocked_by") else "")
                 + " · run cad-agent dossier to write it")
            return 0
        manifest = write_bundle(project, args.section, args.bundle_dir, since=args.since)
    except ReviewError as exc:
        raise _Unusable(str(exc)) from None
    sec = manifest["section"]
    _say(f"{sec['id']}  {sec['title']}  ({sec['status']})  -> {manifest['dir']}")
    _say(f"  packet: {manifest['packet']['questions']} question(s)"
         + (f", {manifest['packet']['stale']}" if manifest["packet"]["stale"] else ", current"))
    diff = manifest["diff"]
    _say(f"  diff: {'since ' + diff['base'][:12] if diff.get('base') else diff.get('note') or 'none'}"
         + (f" ({len(diff['paths'])} path(s))" if diff.get("base") else ""))
    for b in manifest["blockers"]:
        _say(f"  BLOCKER {b}")
    _say(f"  reviewer: read {manifest['dir']}/PROMPT.md; submit with {manifest['submit']}")
    return 0 if manifest["ready"] else 1


def _packet_summary(manifest: Dict[str, Any], listed: bool) -> None:
    sec = manifest["section"]
    m = manifest["measurements"]
    stale = sorted(g for g, v in m["gates"].items() if v.get("stale"))
    fails = [f for f in manifest["findings"] if f["status"] == "fail"]
    _say(f"{sec['id']}  {sec.get('title', '')}  ({sec.get('status', 'no status')})  -> {manifest['dir']}")
    for v in manifest["views"]:
        mark = "" if listed else ("  ok " if v.get("sha256") else "  -- ")
        _say(f"  {mark}{v['id']:<34} {v['note']}")
    for n in manifest["not_rendered"]:
        _say(f"  not rendered: {n['what']}: {n['why']}")
    _say(f"  {len(manifest['checklist']['questions'])} checklist question(s); {len(fails)} failing finding(s), "
         f"{len(manifest['findings']) - len(fails)} warning(s)"
         + (f"; stale verdicts: {', '.join(stale)}" if stale else "")
         + (f"; no verdict: {', '.join(m['missing_gates'])}" if m.get("missing_gates") else "")
         + " · renders are for diagnosis, not proof")


def cmd_gates(project: CadProject, args: argparse.Namespace) -> int:
    """Run every integrity gate that applies, each in a process of its own, then the dossier lint; write
    exports/gates/<gate>.json and .md (docs/gates.md "Running the gates")."""
    from cadagent.review.gates.run import GatesConfigError, enabled, run_gates

    if not enabled(project):
        raise _Unusable("no dossier: or gates: key in the cad: section; the gates read the dossier geometry "
                        "(docs/gates.md \"Running the gates\")")
    dry = getattr(args, "dry_run", False)
    if getattr(args, "jobs", None) is not None and args.jobs < 1:
        raise _Unusable("--jobs must be 1 or more")
    try:
        res = run_gates(project, only=getattr(args, "gate_only", None) or (), skip=getattr(args, "gate_skip", None)
                        or (), jobs=getattr(args, "jobs", None), no_cache=getattr(args, "no_cache", False),
                        build=getattr(args, "build", False), dry_run=dry, progress=_say)
    except GatesConfigError as exc:
        raise _Unusable(str(exc)) from exc
    width = max([len(r.gate) for r in res.rows] + [8])
    if dry:
        for r in res.rows:
            _say(f"  {r.status.upper() if r.status != 'na' else 'N/A':<4} {r.gate:<{width}}  {r.message}")
        return 0
    for r in res.rows:
        if r.status in ("na", "skip"):
            _say(f"  {'N/A' if r.status == 'na' else 'SKIP':<4} {r.gate:<{width}}  {r.message}")
    counts = {s: sum(1 for r in res.rows if r.status == s) for s in ("pass", "fail", "na", "skip")}
    _say(f"gates: {counts['pass']} pass, {counts['fail']} fail, {counts['na']} not applicable, {counts['skip']} "
         f"skipped in {res.seconds:.1f}s" + (f" ({res.record})" if res.record else "")
         + " · checks of the CAD model, physical fit not verified")
    if res.rows and not res.passed:
        _say(f"verdicts: {project.exports_dir / 'gates'}")
    return 0 if res.passed else 1


def cmd_holes(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.mechanical import holes
    from cadagent.mechanical.holes import check_project
    from cadagent.project import CadConfigError

    out = getattr(args, "out", None)
    try:
        result = check_project(project, getattr(args, "parts", None) or None, Path(out) if out else None)
    except (ValueError, CadConfigError) as exc:
        raise _Unusable(str(exc)) from exc
    for part, row in result["parts"].items():
        if row.get("skipped"):
            _say(f"  SKIP  {part}: {row['skipped']}")
        elif row.get("error"):
            _say(f"  FAIL  {part}: {row['error']}")
        elif row["findings"]:
            _say(f"  FAIL  {part}: {len(row['findings'])} of {holes.describe_count(row)} have material inside")
            for f in row["findings"]:
                _say(f"          {f.get('label') or 'D' + str(f['diameter_mm'])} {f['from_mm']} -> {f['to_mm']}: {f['intrusion_mm3']} mm3 at "
                     f"{f['intrusion_centre_mm']}")
        else:
            ex = f" ({len(row['excepted'])} listed exception(s))" if row.get("excepted") else ""
            _say(f"  PASS  {part}: {holes.describe_count(row)} clear{ex}")
    _say(f"holes: {out or project.exports_dir / 'hole-checks.json'}")
    return 0 if result["pass"] else 1

def cmd_all(project: CadProject, args: argparse.Namespace) -> int:
    args.from_step = None
    args.only = None
    if cmd_build(project, args):
        return 1
    if cmd_export_3mf(project, args):
        return 1
    try:                            # writes exports/hole-checks.json; the report's "Holes clear" rows fail on findings
        cmd_holes(project, args)
    except _Unusable as exc:
        _say(f"holes FAILED to run: {exc} (the report's Holes clear rows fail)")
    from cadagent.review.gates.run import GatesConfigError, enabled, gates_config
    if enabled(project):
        try:                    # rebuild the record unless a build step already runs the gates' build script
            gb = gates_config(project).build
        except GatesConfigError:
            gb = None
        stepped = {(project.root / s.run).resolve() for s in project.steps}
        args.gate_only, args.gate_skip, args.dry_run, args.build = None, None, False, gb is not None and gb not in stepped
        args.no_cache, args.jobs = False, None
        try:
            cmd_gates(project, args)    # writes the verdicts and the dossier status; `check` (in report) fails on them
        except _Unusable as exc:
            _say(f"gates not run: {exc}")
            if project.dossier:
                args.json, args.no_write, args.min_status = False, False, "gated"
                cmd_dossier(project, args)
    report_rc = cmd_report(project, args)
    package_rc = cmd_package(project, args)
    if report_rc:
        _say("checks FAILED; the package was still written for review")
    return report_rc or package_rc

def _mcmaster_choices(pns: List[str], choose: Optional[List[str]]) -> Dict[str, List[str]]:
    """--choose values -> option texts per part number. 'PN:OPTION' is for that part; a bare 'OPTION' is allowed only
    when one part number is given."""
    from cadagent.mechanical.mcmaster import PN_RE

    per: Dict[str, List[str]] = {pn: [] for pn in pns}
    for c in choose or []:
        head, sep, rest = c.partition(":")
        if sep and PN_RE.match(head.strip().upper()):
            pn = head.strip().upper()
            if pn not in per:
                raise _Unusable(f"--choose {c!r}: {pn} is not one of the part numbers given")
            per[pn].append(rest.strip())
        elif len(pns) == 1:
            per[pns[0]].append(c.strip())
        else:
            raise _Unusable(f"--choose {c!r}: with several part numbers, say which part it is for (PN:OPTION)")
    return per


def cmd_mcmaster(args: argparse.Namespace) -> int:
    """Download each part's STEP and product data from McMaster-Carr (one product page at a time), normalise its
    frame, and optionally record it in a catalogue JSON. Needs no project. The browser is started only when a part
    actually needs its page (no STEP or page data here yet, or --force), so re-normalising works offline."""
    import contextlib

    from cadagent.mechanical import mcmaster as mc

    try:
        pns = [mc.validate_pn(p) for p in args.pns]
    except ValueError as exc:
        raise _Unusable(str(exc))
    if args.key and len(pns) != 1:
        raise _Unusable("--key names one catalogue entry: give one part number with it")
    if not args.kind and (args.catalog or args.density is not None):
        raise _Unusable("--catalog and --density need --kind (the frame the part is normalised into)")
    choices = _mcmaster_choices(pns, args.choose)
    if args.delay < mc.MIN_DELAY_S:
        _say(f"WARN --delay {args.delay:g} s is below the minimum; using {mc.MIN_DELAY_S:g} s between pages")
    out_root = Path(args.out)
    rc = 0
    with contextlib.ExitStack() as stack:
        session = None
        gated = ""                                          # the first part McMaster asked a login for

        def browser():
            nonlocal session
            if session is None:
                session = stack.enter_context(mc.Session(delay_s=args.delay))
            return session

        for pn in pns:
            folder = out_root / pn
            step, page_file = folder / f"{pn}.step", folder / f"{pn}.page.json"
            try:
                if step.exists() and page_file.exists() and not args.force:
                    _say(f"{pn}: already here ({step}); --force downloads it again")
                elif gated:                                 # the next page would meet the same login: do not ask
                    _err(f"mcmaster {pn}: not fetched: McMaster asked for a login at {gated} in this run; "
                         "the part number may be fine")
                    rc = 1
                    continue
                else:
                    try:
                        browser().fetch(pn, folder, choose=choices[pn] or None)
                    except mc.LoginRequired:
                        gated = pn
                        raise
                    _say(f"{pn}: downloaded -> {step}")
                page = json.loads(page_file.read_text())
                _say(f"{pn}: {page.get('description')} | {page.get('price_text')}")
                if args.kind:
                    material = mc.material_of(page.get("specs", {}).get("raw", {}))
                    norm, info = mc.normalise(step, args.kind, density=args.density, material=material)
                    (folder / f"{pn}.norm.json").write_text(json.dumps(info, indent=1) + "\n")
                    _say(f"{pn}: {args.kind} -> {norm} bbox {info['bbox_mm']['size']} mm, "
                         f"{info['volume_mm3']:.0f} mm3, ~{info['mass_g_est']} g")
                    if args.catalog:
                        cat = Path(args.catalog)
                        n, cwd = norm.resolve(), Path.cwd().resolve()
                        cad = str(n.relative_to(cwd)) if n.is_relative_to(cwd) else str(n)
                        mc.update_catalog(cat, args.key or pn, mc.catalog_entry(page, info, cad=cad))
                        _say(f"{pn}: catalogue {cat} [{args.key or pn}]")
            except MissingDependency:
                raise                                       # no Playwright or no Chrome: nothing else will work
            except Exception as exc:  # one bad part should not stop the others
                _err(f"mcmaster {pn}: {exc}")
                rc = 1
    return rc


# ----------------------------------------------------------------------------- explore: catalogue, compare, optimise

def _warn(msg: str) -> None:
    """A warning on stderr, so `--json` output on stdout stays parseable."""
    print(f"cad-agent: WARN {msg}", file=sys.stderr, flush=True)


def _explore(project: CadProject):
    """The project's explore config and catalogue, with the catalogue's load problems."""
    from cadagent.simulation.explore.catalogue import load_configured
    from cadagent.simulation.explore.config import explore_config

    if not project.explore:
        raise _Unusable("no explore: section under cad: in cad-agent.yaml (docs/explore.md)")
    cfg = explore_config(project.root, project.explore, project.title)
    if cfg.unknown_keys:
        _warn(f"unknown explore: keys ignored: {', '.join(cfg.unknown_keys)}")
    if not cfg.catalogue and cfg.slots:
        raise _Unusable(f"cad.explore.catalogue lists no catalogue files, but slots are declared "
                        f"({', '.join(cfg.slots)}): parts come from a catalogue. A search that changes only "
                        "parameters needs neither")
    catalogue, issues = load_configured(cfg)           # no catalogue, no slots: a parameter search, empty BOMs
    return cfg, catalogue, issues


def _design_paths(cfg, given: Optional[List[str]]) -> List[Path]:
    """Design files named on the command line (relative to the project root, else to the current folder), or the
    configured ones."""
    if given:
        paths, missing = [], []
        for name in given:
            found = next((p for p in (cfg.root / name, Path.cwd() / name) if p.is_file()), None)
            (paths.append(found.resolve()) if found else missing.append(name))
        if missing:
            raise _Unusable(f"design file not found: {', '.join(missing)}")
        return paths
    files, unmatched = cfg.design_files()
    for pat in unmatched:
        _warn(f"design pattern {pat!r} matches no file")
    if not files:
        raise _Unusable("no design files (cad.explore.designs, default designs/*.json)")
    return files


def cmd_catalogue(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.simulation.explore.catalogue import check_catalogue, counts
    from cadagent.simulation.explore.design import DesignError, check_slots, load_design, resolve

    cfg, catalogue, issues = _explore(project)
    issues += check_catalogue(catalogue, cfg.categories or None, cfg.max_price_age_days)
    issues += check_slots(cfg.slots, catalogue)
    designs = []
    files, _ = cfg.design_files()
    for path in files:
        rel = path.relative_to(cfg.root).as_posix() if path.is_relative_to(cfg.root) else str(path)
        try:
            cand, errors, checks = resolve(load_design(path), catalogue, cfg.slots)
        except DesignError as exc:
            errors, checks = [str(exc)], []
        designs.append({"file": rel, "errors": errors, "warnings": [c["text"] for c in checks if c["level"] == "warn"]})
    n = counts(issues)
    design_errors = sum(len(d["errors"]) for d in designs)
    by_cat = {c: len(catalogue.in_category(c)) for c in catalogue.categories()}
    if getattr(args, "json", False):
        print(json.dumps({"parts": len(catalogue), "files": sorted(set(catalogue.files.values())), "categories": by_cat,
                          "issues": [vars(i) for i in issues], "designs": designs}, indent=1))
    else:
        for issue in sorted(issues, key=lambda i: i.level != "warn"):
            if issue.level == "error" or not getattr(args, "errors_only", False):
                _say(f"  {issue}")
        for d in designs:
            for e in d["errors"]:
                _say(f"  ERROR design {d['file']}: {e}")
        cats = ", ".join(f"{c} {k}" for c, k in by_cat.items())
        if not cfg.catalogue:
            _say("catalogue: none configured and no slots, so designs differ only in their parameters "
                 "(their BOMs hold no catalogue parts)")
        else:
            _say(f"catalogue: {len(catalogue)} parts in {len(set(catalogue.files.values()))} file(s) ({cats}); "
                 f"{n['error']} errors, {n['warn']} warnings")
        _say(f"designs: {len(designs)} checked against it, {design_errors} errors")
    return 1 if n["error"] or design_errors else 0


def _print_leaderboard(comp: Dict[str, Any], limit: int = 25) -> None:
    from cadagent.simulation.explore import metrics as M

    cols = comp["metrics"]
    objectives = [o["metric"] for o in comp["objectives"]]
    shown = [m for m in objectives + [m for m in cols if m not in objectives] if m in cols][:5]
    arrows = {o["metric"]: "↓" if o["goal"] == "min" else "↑" for o in comp["objectives"]}
    heads = [f"{cols[m]['label']}{' ' + arrows[m] if m in arrows else ''}" for m in shown]
    width = min(max([len(str(d.get("name"))) for d in comp["designs"]] + [6]), 40)
    _say(f"  {'rank':<5} {'design':<{width}}  {'verdict':<7}  " + "  ".join(f"{h:>14}" for h in heads))
    for d in comp["designs"][:limit]:
        rank = f"{d['rank']}{'*' if d.get('pareto') else ''}" if d.get("rank") else "-"
        vals = []
        for m in shown:
            metric = (d.get("metrics") or {}).get(m)
            col = cols[m]
            vals.append(M.format_value(metric.get("value"), col["unit"], col.get("digits"), bool(metric.get("estimate")),
                                       bool(metric.get("incomplete"))) if metric else "—")
        _say(f"  {rank:<5} {str(d.get('name'))[:width]:<{width}}  {d.get('verdict', ''):<7}  "
             + "  ".join(f"{v:>14}" for v in vals))
    if len(comp["designs"]) > limit:
        _say(f"  ... {len(comp['designs']) - limit} more in the JSON")
    s = comp["summary"]
    _say(f"{s['designs']} {'trials' if comp['kind'] == 'search' else 'designs'}: {s['feasible']} feasible, "
         f"{s['pareto']} on the Pareto front (*), {s['errors']} could not be evaluated · est. = estimate, "
         "≥ = total leaves out unpriced or unweighed parts · on paper only, nothing measured")


def cmd_compare(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.simulation.explore.catalogue import check_catalogue, counts
    from cadagent.simulation.explore.compare import compare_designs, to_json, write_comparison
    from cadagent.simulation.explore.evaluate import load_evaluator

    cfg, catalogue, issues = _explore(project)
    paths = _design_paths(cfg, getattr(args, "designs", None))
    evaluator = load_evaluator(cfg.evaluator, project.root, project.python)
    workers = getattr(args, "workers", 1) or 1
    if workers < 1:
        raise _Unusable("--workers must be 1 or more")
    comp = compare_designs(cfg, catalogue, evaluator, paths, with_swaps=getattr(args, "swaps", False), workers=workers)
    written = write_comparison(comp, cfg.out, cfg=cfg)
    data = counts(issues + check_catalogue(catalogue, cfg.categories or None, cfg.max_price_age_days))
    if getattr(args, "json", False):
        print(to_json(comp), end="")
    else:
        _print_leaderboard(comp)
        if data["error"] or data["warn"]:
            _say(f"catalogue: {data['error']} errors, {data['warn']} warnings (cad-agent catalogue lists them)")
        _say(f"comparison: {written['json']}")
        _say(f"page:       {written['html']}")
        _say(f"site cards: {written['cards']} (cad: site: designs:)")
    if getattr(args, "open", False):
        import webbrowser
        webbrowser.open(written["html"].resolve().as_uri())
    return 1 if comp["summary"]["errors"] or any(i.level == "error" for i in issues) else 0


def cmd_optimise(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.simulation.explore.evaluate import load_evaluator
    from cadagent.simulation.explore.optimise import run_search

    cfg, catalogue, issues = _explore(project)
    for issue in issues:
        if issue.level == "error":
            _say(f"  {issue}")
    if any(i.level == "error" for i in issues):
        raise _Unusable("the catalogue has errors (cad-agent catalogue)")
    evaluator = load_evaluator(cfg.evaluator, project.root, project.python)
    r = run_search(cfg, catalogue, evaluator, trials=args.trials, workers=args.workers, sampler=args.sampler,
                   seed=args.seed, fresh=args.fresh, progress=_say, confirm=not getattr(args, "no_confirm", False),
                   python=project.python)
    _say(f"search ({r['sampler']}): {r['new']} new trial(s) in {r['seconds']:.1f}s ({r['evaluated']} evaluated, "
         f"{r['repeats']} repeats of earlier combinations), {r['trials']} in total; {r['feasible']} feasible, "
         f"{r['pareto']} on the Pareto front" + (" (interrupted)" if r["interrupted"] else ""))
    c = r.get("confirm")
    if c:
        _say(f"confirm ({c['evaluator']}): {c['new']} evaluated this run" + ("" if c["ran"] else " (--no-confirm)")
             + f"; {c['leaders_confirmed']} of the top {c['top']} feasible confirmed, {c['confirmed']} trial(s) in all; "
             f"{len(c['flagged'])} changed by more than {c['tolerance_pct']:g} % or failed")
        for line in c["flagged"]:
            _say(f"  flagged: {line}")
    for name in r["best"]:
        _say(f"  front: {name}")
    _say(f"leaderboard: {r['leaderboard']}")
    return 0 if r["feasible"] and not r["interrupted"] else 1


OVERHANG_SCREEN_VERSION = 1


def cmd_overhangs(project: CadProject, args: argparse.Namespace) -> int:
    """Group each part STL's downward faces flatter than --limit into connected regions and write
    exports/overhang-screen.json (``cadagent.geometry.overhang_regions``). A screen, not a slicer."""
    import hashlib

    from cadagent.geometry import overhang_regions
    from cadagent.publish.report import load_parts

    known, error = load_parts(project)
    if error:
        raise _Unusable(error)
    parts = list(getattr(args, "parts", None) or [])
    stray = sorted(set(parts) - set(known))
    if stray:
        raise _Unusable(f"no such part(s) {stray}; parts: {sorted(known)}")
    limit, min_area = float(args.limit), float(args.min_area)
    if not 0.0 < limit <= 90.0:
        raise _Unusable(f"--limit must be in (0, 90] degrees, not {limit:g}")
    settings = {"limit_deg": limit, "min_area_mm2": min_area}
    path = project.exports_dir / "overhang-screen.json"
    rows: Dict[str, Any] = {}
    if parts and path.is_file():          # a partial run keeps the other parts' current rows from a run with the same settings
        try:
            old = json.loads(path.read_text())
            if old.get("version") == OVERHANG_SCREEN_VERSION and all(old.get(k) == v for k, v in settings.items()):
                rows = {k: v for k, v in (old.get("parts") or {}).items()     # only rows whose STL is unchanged
                        if k in known and isinstance(v, dict) and (project.exports_dir / f"{k}.stl").is_file()
                        and hashlib.sha256((project.exports_dir / f"{k}.stl").read_bytes()).hexdigest() == v.get("sha256")}
        except (OSError, ValueError, AttributeError):
            rows = {}
    failed = 0
    for name in parts or list(known):
        stl = project.exports_dir / f"{name}.stl"
        if not stl.is_file():
            rows[name] = {"error": f"{stl.name} not found; run the build first"}
            failed += 1
            _say(f"  FAIL  {name}: {stl.name} not found")
            continue
        try:
            r = overhang_regions(stl, limit_deg=limit, min_area=min_area)
        except (ValueError, OSError, IndexError, KeyError) as exc:     # an STL trimesh cannot read
            rows[name] = {"error": f"{stl.name}: {type(exc).__name__}: {exc}"}
            failed += 1
            _say(f"  FAIL  {name}: {rows[name]['error']}")
            continue
        rows[name] = {"stl": stl.name, "sha256": hashlib.sha256(stl.read_bytes()).hexdigest(),
                      **{k: r[k] for k in ("downward_area_mm2", "regions", "small_regions", "small_area_mm2")}}
        big = r["regions"][0] if r["regions"] else None
        where = (f"; largest {big['area_mm2']} mm2 at {big['centre_mm']} (z {big['bounds_mm'][2]}-{big['bounds_mm'][5]}, "
                 f"flattest {big['flattest_deg']} deg)") if big else ""
        _say(f"  {name:<24} {r['downward_area_mm2']:9.1f} mm2 flatter than {limit:g} deg, "
             f"{len(r['regions'])} region(s) of {min_area:g} mm2 or more{where}")
    project.exports_dir.mkdir(parents=True, exist_ok=True)
    data = {"version": OVERHANG_SCREEN_VERSION, **settings, "bed_z_mm": 0.3,
            "angle": "slope from horizontal: 0 = flat ceiling, 90 = vertical wall; faces flatter than limit_deg",
            "note": "a screen of downward faces, not a slicer: bridges anchored on both sides are listed too",
            "parts": {k: rows[k] for k in sorted(rows)}}
    path.write_text(json.dumps(data, indent=1) + "\n")
    _say(f"overhangs: {path}")
    return 1 if failed else 0

HANDLERS = {
    "build": cmd_build,
    "export-3mf": cmd_export_3mf,
    "holes": cmd_holes,
    "check": cmd_check,
    "report": cmd_report,
    "package": cmd_package,
    "release": cmd_release,
    "serve": cmd_serve,
    "site": cmd_site,
    "view": cmd_view,
    "slice": cmd_slice,
    "webkit": cmd_webkit,
    "all": cmd_all,
    "pcb-check": cmd_pcb_check,
    "catalogue": cmd_catalogue,
    "compare": cmd_compare,
    "optimise": cmd_optimise,
    "dossier": cmd_dossier,
    "gates": cmd_gates,
    "review-packet": cmd_review_packet,
    "review-section": cmd_review_section,
    "overhangs": cmd_overhangs,
}

def cmd_agents(args: argparse.Namespace) -> int:
    """Install or list the agent workflow kit (skills/ and agents/) for Claude Code and Codex: cadagent.agentkit."""
    from cadagent import agentkit
    root = agentkit.kit_root(args.source)
    home = Path(args.home).expanduser() if args.home else Path.home()
    targets = agentkit.TARGETS if args.target == "all" else (args.target,)
    if args.action == "list":
        for row in agentkit.status(home, root, targets):
            _say(f"{row['kind']:5}  {row['name']:24} {row['state']:12} {row['dest']}")
        return 0
    warning = None if args.copy else agentkit.worktree_warning(root)
    if warning:
        _warn(warning)
    result = agentkit.install(home, root, targets, copy=args.copy, dry_run=args.dry_run)
    for line in result["done"]:
        _say(("would " if args.dry_run else "") + line)
    for dest in result["conflicts"]:
        _err(f"agents: {dest} exists and was not installed by cad-agent; left untouched (move it away and rerun)")
    _say(f"agents: {len(result['done'])} {'planned' if args.dry_run else 'installed'} from {root}"
         + (f", {len(result['conflicts'])} conflicts" if result["conflicts"] else ""))
    return 1 if result["conflicts"] else 0

def cmd_snapfit(args: argparse.Namespace) -> int:
    """Size and check declared snap fits (cadagent.mechanical.compliant.snapfit); exit 1 if any check fails."""
    from cadagent.mechanical.compliant import snapfit
    text = Path(args.spec).read_text()
    if str(args.spec).endswith((".yaml", ".yml")):
        import yaml
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"{args.spec} is not valid YAML: {exc}") from None
    else:
        data = json.loads(text)
    result = snapfit.check_spec(data)
    for snap in result["snaps"]:
        forces = ", ".join(f"{k.replace('_n', '').replace('_', ' ')} {v:.1f} N" for k, v in snap.items()
                           if k.endswith("_force_n") and v is not None)
        if snap.get("self_locking"):
            forces += ("; " if forces else "") + "self-locking"
        _say(f"{'PASS' if snap['pass'] else 'FAIL'}  {snap['name']}: root strain {snap['strain'] * 100:.2f} % "
             f"(allowed {snap['material']['allowable'] * 100:.2f} %)" + (f"; {forces}" if forces else ""))
        for row in snap["rows"]:
            if not row["pass"]:
                _say(f"      {row['check']}: {row['detail']}")
        for warning in snap.get("warnings", []):
            _say(f"      warning: {warning}")
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, default=str, allow_nan=False) + "\n")
    return 0 if result["pass"] else 1


def cmd_inserts(args: argparse.Namespace) -> int:
    """Check heat-set insert and compression-limiter joints declared in a file (cadagent.mechanical.inserts); exit 1
    if any joint fails (a warning does not fail it)."""
    from cadagent.mechanical import inserts
    text = Path(args.spec).read_text()
    if str(args.spec).endswith((".yaml", ".yml")):
        import yaml
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"{args.spec} is not valid YAML: {exc}") from None
    else:
        data = json.loads(text)
    result = inserts.check_spec(data)
    for joint in result["joints"]:
        torque = joint["torque"]
        what = (f"{joint['insert']['thread']} {joint['insert']['part']} in {joint['material']['name']}, "
                f"{joint['clamp']['path']}" if "insert" in joint else
                f"{joint['thread']} clamping {joint['material']['name']}" +
                (" through a limiter" if joint["limiter"] else ""))
        _say(f"{joint['verdict'].upper():4}  {joint['name']}: {what}; tighten to at most "
             f"{torque['allowed_nm']:.2f} N m ({torque['governed_by'].replace('_', ' ')})")
        for row in joint["checks"]:
            if row["verdict"] != "pass":
                _say(f"      {row['verdict']}: {row['check']}: {row['detail']}")
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, default=str, allow_nan=False) + "\n")
    return 0 if result["verdict"] != "fail" else 1


def _read_spec(path: str) -> Any:
    text = Path(path).read_text()
    if str(path).endswith((".yaml", ".yml")):
        import yaml
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"{path} is not valid YAML: {exc}") from None
    return json.loads(text)


def cmd_bearings(args: argparse.Namespace) -> int:
    """Check rolling bearings declared in a file (cadagent.mechanical.bearings): life, static safety, axial load and
    speed, turning or oscillating; exit 1 if any bearing fails (a warning does not fail it)."""
    from cadagent.mechanical import bearings
    result = bearings.check_spec(_read_spec(args.spec))
    for b in result["bearings"]:
        life = b["life"]
        what = (f"{life['life_million']:.3g} million {life['unit']}" + (f" ({life['hours']:,.0f} h)" if life.get("hours")
                                                                     else "") if life else "static only")
        s0 = min((s["s0"] for s in b["static"]), default=None)
        _say(f"{b['verdict'].upper():4}  {b['name']}: {b['motion']}, {what}" +
             (f", least s0 {s0:.2f}" if s0 is not None else ""))
        for row in b["checks"]:
            if row["verdict"] != "pass":
                _say(f"      {row['verdict']}: {row['check']}: {row['detail']}")
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, default=str, allow_nan=False) + "\n")
    return 0 if result["verdict"] != "fail" else 1


def cmd_motion_trace(args: argparse.Namespace) -> int:
    """Check captured rendered landmarks, or print the required capture poses; no project config needed."""
    from cadagent.mechanical.motion_trace import required_poses, validate_motion_trace
    import json
    contract = json.loads(args.contract.read_text())
    if args.poses_only:
        result = required_poses(contract)
        code = 0
    else:
        if args.trace is None:
            raise ValueError("trace is required unless --poses-only is set")
        trace = json.loads(args.trace.read_text())
        result = validate_motion_trace(contract, trace, tolerance_mm=args.tolerance_mm)
        code = 0 if result["status"] == "pass" else 1
    content = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end="")
    return code


def dispatch(args: argparse.Namespace) -> int:
    sub = getattr(args, "cad_command", None)
    if sub == "motion-trace":
        try:
            return cmd_motion_trace(args)
        except (OSError, ValueError) as exc:
            _err(f"motion-trace: {exc}")
            return 2
    if sub == "agents":                                    # installs into the user's home: no project needed
        try:
            return cmd_agents(args)
        except (FileNotFoundError, ValueError) as exc:
            _err(f"agents: {exc}")
            return 2
    if sub == "snapfit":                                   # works on a declaration file only: no project needed
        try:
            return cmd_snapfit(args)
        except (OSError, ValueError, KeyError) as exc:
            _err(f"snapfit: {exc}")
            return 2
    if sub == "inserts":                                   # works on a declaration file only: no project needed
        try:
            return cmd_inserts(args)
        except (OSError, ValueError, KeyError) as exc:
            _err(f"inserts: {exc}")
            return 2
    if sub == "bearings":                                  # works on a declaration file only: no project needed
        try:
            return cmd_bearings(args)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            _err(f"bearings: {exc}")
            return 2
    if sub == "mcmaster":                                  # works on files only: no project needed
        try:
            return cmd_mcmaster(args)
        except (MissingDependency, _Unusable) as exc:
            _err(f"mcmaster: {exc}")
            return 2
    if sub not in HANDLERS:
        _err("choose a subcommand: " + ", ".join(SUBCOMMANDS) + " (cad-agent --help)")
        return 2
    try:
        project = load_project(getattr(args, "project", None))
        if project.unknown_keys:
            _warn(f"unknown cad: keys ignored: {', '.join(project.unknown_keys)}")
        return HANDLERS[sub](project, args)
    except (CadConfigError, MissingDependency, _Unusable, SourceDateEpochError) as exc:
        _err(f"{sub}: {exc}")
        return 2
    except FileNotFoundError as exc:
        _err(f"{sub}: {exc}")
        return 2
    except RuntimeError as exc:
        # GeometryError / Mesh3mfError: the output was produced but failed verification
        _err(f"{sub}: FAILED: {exc}")
        return 1
    except KeyboardInterrupt:
        if sub in ("compare", "optimise"):
            from cadagent.simulation.explore.evaluate import kill_running_evaluators
            kill_running_evaluators()
        _err(f"{sub}: interrupted")
        return 130

PROJECT_HELP = "CAD project root containing cad-agent.yaml with a cad: section (default: cwd)"

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cad-agent",
        description="CAD design verification: build, check, report, package (docs/toolkit.md)",
    )
    parser.add_argument("--project", default=None, help=PROJECT_HELP)
    # also accepted after the subcommand; SUPPRESS keeps it from resetting the parent's value
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS, help=PROJECT_HELP)
    sub = parser.add_subparsers(dest="cad_command")

    build_p = sub.add_parser("build", parents=[common], help="Run the configured build steps in order")
    build_p.add_argument("--from", dest="from_step", metavar="STEP", help="Start at this step")
    build_p.add_argument("--only", nargs="+", metavar="STEP", help="Run only these steps (config order)")
    sub.add_parser("export-3mf", parents=[common], help="Write a bed-centred 3MF per part STL, and every part on build plates in one Bambu Studio project 3MF; verify both")
    holes_p = sub.add_parser("holes", parents=[common], help="Check every hole of every part (exports/<part>.step) is "
                                                             "clear of material: ribs or bosses added after the holes")
    holes_p.add_argument("parts", nargs="*", help="only these parts (default: every part in the parts file); the other "
                                                  "parts' rows are kept from a result made with the same settings")
    holes_p.add_argument("--out", help="write the result here instead of exports/hole-checks.json (a reviewer's "
                                       "read-only run)")
    oh_p = sub.add_parser("overhangs", parents=[common], help="Group each part STL's downward faces flatter than "
                          "--limit into regions (area, height, centre): exports/overhang-screen.json; a screen, not a slicer")
    oh_p.add_argument("parts", nargs="*", help="only these parts (default: every part in the parts file); the other "
                                               "parts' rows are kept from a result made with the same settings")
    oh_p.add_argument("--limit", type=float, default=45.0, help="slope from horizontal in degrees (0 = flat ceiling, "
                                                                "90 = vertical wall) under which a face is listed "
                                                                "(default 45)")
    oh_p.add_argument("--min-area", type=float, default=4.0, help="regions smaller than this in mm2 are counted, "
                                                                  "not listed (default 4)")
    check_p = sub.add_parser("check", parents=[common], help="Collect check results; exit 1 if any fail")
    check_p.add_argument("--json", action="store_true", help="Print the results JSON (schema 1.0)")
    report_p = sub.add_parser("report", parents=[common], help="Write results JSON + standalone HTML report")
    report_p.add_argument("--open", action="store_true", help="Open the report in a browser")
    sub.add_parser("package", parents=[common], help="Zip the review package with a sha256 manifest")
    rel_p = sub.add_parser("release", parents=[common], help="Write the print release: a browsable page of the parts "
                                                            "(thumbnails, print settings) with CAD files and source, and a zip")
    rel_p.add_argument("--out", help="Release folder (default: release/<name>-rev<revision>); the zip is <out>.zip")
    rel_p.add_argument("--no-zip", action="store_true", help="Write the folder only")
    rel_p.add_argument("--revision", help="Release revision for the title, folder name and manifest (default: "
                                          "cad.release.revision, else the project's revision)")
    rel_p.add_argument("--date", help="Release date (default: cad.release.date, SOURCE_DATE_EPOCH, the last commit's date)")
    serve_p = sub.add_parser("serve", parents=[common], help="Serve the project over http (Bambu Studio links)")
    serve_p.add_argument("--port", type=int, default=None,
                         help="Port (default: cad.serve.port, 0 = any free port)")
    serve_p.add_argument("--host", default=None, help="Bind address (default: cad.serve.host, 127.0.0.1)")
    site_p = sub.add_parser("site", parents=[common], help="Build the project site (progress, designs, decisions, docs)")
    site_p.add_argument("--serve", action="store_true", help="Serve it, rebuilding when a source file changes")
    site_p.add_argument("--port", type=int, default=None, help="Port (default: cad.serve.port, 0 = any free port)")
    site_p.add_argument("--host", default=None, help="Bind address (default: cad.serve.host, 127.0.0.1)")
    sub.add_parser("view", parents=[common], help="Export every part in assembly position for the 3D viewer")
    slice_p = sub.add_parser("slice", parents=[common], help="Slice each part's 3MF (Bambu Studio or PrusaSlicer CLI): grams and print time")
    slice_p.add_argument("parts", nargs="*", help="Parts to slice (default: cad.slicer.parts, else all)")
    webkit_p = sub.add_parser("webkit", parents=[common], help="Copy the web kit (3D stage, viewer, HUD) into the project")
    webkit_p.add_argument("dest", nargs="?", default="web/kit", help="Destination folder (default: web/kit)")
    pcb_p = sub.add_parser("pcb-check", parents=[common], help="Bind KiCad ERC/DRC evidence to current PCB sources")
    pcb_p.add_argument("manifest", help="JSON with reports, sources, release_gates and optional waivers (paths relative to project root)")
    pcb_p.add_argument("--output", default="exports/pcb-evidence.json")
    sub.add_parser("all", parents=[common], help="build, export-3mf, holes, gates and the dossier lint (when configured), "
                                                 "check + report, package")
    mt_p = sub.add_parser("motion-trace", help="Validate rendered joint pivots against independent CAD landmarks")
    mt_p.add_argument("contract", type=Path, help="Independent joint/component reference JSON")
    mt_p.add_argument("trace", type=Path, nargs="?", help="Actual renderer capture JSON")
    mt_p.add_argument("--poses-only", action="store_true", help="Emit required capture angles instead of validating")
    mt_p.add_argument("--output", type=Path, help="Write JSON to a file (default: stdout)")
    mt_p.add_argument("--tolerance-mm", type=float, default=.01, help="Landmark error limit in mm (default: 0.01)")
    sf_p = sub.add_parser("snapfit", help="Size and check snap fits declared in a YAML/JSON file (docs/compliant.md)")
    sf_p.add_argument("spec", help="file with a 'snaps' list")
    sf_p.add_argument("--output", help="write the full result as JSON")
    in_p = sub.add_parser("inserts", help="Check heat-set insert and compression-limiter joints declared in a "
                                          "YAML/JSON file (docs/inserts.md)")
    in_p.add_argument("spec", help="file with a 'joints' list")
    in_p.add_argument("--output", help="write the full result as JSON")
    be_p = sub.add_parser("bearings", help="Check rolling bearings declared in a YAML/JSON file: life, static safety, "
                                           "axial load and speed, turning or oscillating (docs/bearings.md)")
    be_p.add_argument("spec", help="file with a 'bearings' list")
    be_p.add_argument("--output", help="write the full result as JSON")
    ag_p = sub.add_parser("agents", help="Install the agent workflow kit (skills and subagents) for Claude Code and Codex, "
                                         "or list what is installed (docs/agent-workflow.md)")
    ag_p.add_argument("action", choices=("install", "list"))
    ag_p.add_argument("--target", choices=("all", "claude", "codex"), default="all")
    ag_p.add_argument("--source", type=Path, help="cad-agent checkout holding skills/ and agents/ (default: the one "
                                                  "this cadagent is installed from)")
    ag_p.add_argument("--home", help="home folder to install into (default: yours)")
    ag_p.add_argument("--copy", action="store_true", help="copy instead of linking (for a checkout that will move)")
    ag_p.add_argument("--dry-run", action="store_true", help="show what would be installed")
    mc_p = sub.add_parser("mcmaster", help="Download McMaster-Carr STEP + product data per part number and normalise "
                                           "it (one page at a time; skills/mcmaster-parts/SKILL.md)")
    mc_p.add_argument("pns", nargs="+", metavar="PN", help="McMaster-Carr part numbers, e.g. 91290A242")
    from cadagent.mechanical.mcmaster import KINDS as MC_KINDS
    mc_p.add_argument("--kind", choices=MC_KINDS,
                      help="Normalise into the frame for this kind of part (cadagent.mechanical.mcmaster.FRAMES)")
    mc_p.add_argument("--out", default="references/vendor/mcmaster", help="Folder; each part goes in OUT/<PN>/ "
                                                                          "(keep it out of git except SOURCE.txt)")
    mc_p.add_argument("--catalog", help="Catalogue JSON to record the part in: {source, items: {key: entry}}, or a list "
                                             "of items with ids (needs --kind)")
    mc_p.add_argument("--key", help="Catalogue key for the part (default: the part number)")
    mc_p.add_argument("--density", type=float, help="g/cm3 for the mass estimate (default: from the Material row)")
    mc_p.add_argument("--delay", type=float, default=3.0, help="Seconds between product pages (default 3, minimum 2)")
    mc_p.add_argument("--choose", action="append", metavar="[PN:]OPTION",
                      help="Option text to click on the product page before the CAD download (a part with variants), "
                           "one per flag, e.g. --choose 59935K53:\"Right Hand\"; the PN: prefix may be left out when "
                           "one part number is given")
    mc_p.add_argument("--force", action="store_true", help="Download again even when the STEP is already here")
    cat_p = sub.add_parser("catalogue", parents=[common],
                           help="Check the part catalogue and the designs against it (cad: explore:, docs/explore.md)")
    cat_p.add_argument("--json", action="store_true", help="Print the parts, categories and every issue as JSON")
    cat_p.add_argument("--errors-only", action="store_true", help="Leave out the warnings")
    cmp_p = sub.add_parser("compare", parents=[common],
                           help="Evaluate the designs and rank them: comparison JSON, HTML page, site design cards")
    cmp_p.add_argument("designs", nargs="*", metavar="DESIGN", help="Design files (default: cad.explore.designs)")
    cmp_p.add_argument("--swaps", action="store_true",
                       help="Also evaluate every one-part swap from the catalogue for each design")
    cmp_p.add_argument("--workers", type=int, default=1,
                       help="Swaps evaluated at the same time (threads; a command evaluator runs that many processes)")
    cmp_p.add_argument("--json", action="store_true", help="Print the comparison JSON instead of the table")
    cmp_p.add_argument("--open", action="store_true", help="Open the comparison page in a browser")
    opt_p = sub.add_parser("optimise", parents=[common],
                           help="Search slots and parameters for the best trade-offs (cad: explore: search:)")
    opt_p.add_argument("--trials", type=int, default=None, help="Trials this run (default: search.trials)")
    opt_p.add_argument("--workers", type=int, default=None, help="Evaluations at the same time (default: search.workers)")
    opt_p.add_argument("--sampler", choices=("random", "grid", "nsga2", "tpe"), default=None,
                       help="Override search.sampler (nsga2 and tpe need optuna)")
    opt_p.add_argument("--seed", type=int, default=None, help="Override search.seed")
    opt_p.add_argument("--fresh", action="store_true", help="Delete the previous trials and start over")
    opt_p.add_argument("--no-confirm", action="store_true",
                       help="Skip search.confirm this run (the leaderboard keeps earlier confirmations)")
    dos_p = sub.add_parser("dossier", parents=[common],
                           help="Lint the design dossier and write each item's status (exports/dossier-status.json)")
    dos_p.add_argument("--json", action="store_true", help="Print the status JSON instead of the table")
    dos_p.add_argument("--no-write", action="store_true", help="Do not write the status and verdict files")
    dos_p.add_argument("--min-status", choices=("draft", "built", "gated", "reviewed", "signed_off", "none"),
                       default="gated", help="Status every section must reach (default gated, plan §5.4); "
                                             "none: report statuses without failing on them")
    from cadagent.review.gates.run import NAMES as GATE_NAMES
    gates_p = sub.add_parser("gates", parents=[common],
                             help="Run the integrity gates on the dossier geometry: exports/gates/<gate>.json + .md")
    gates_p.add_argument("--only", dest="gate_only", nargs="+", choices=GATE_NAMES, metavar="GATE",
                         help=f"Run only these gates ({', '.join(GATE_NAMES)})")
    gates_p.add_argument("--skip", dest="gate_skip", nargs="+", choices=GATE_NAMES, metavar="GATE",
                         help="Leave these gates out of this run")
    gates_p.add_argument("--jobs", type=int, default=None,
                         help="Gates run at once, each in its own process (default: cad.gates.jobs, else 1)")
    gates_p.add_argument("--no-cache", action="store_true", help="Run without the pair cache (every query exact)")
    gates_p.add_argument("--build", action="store_true",
                         help="Build the geometry first with cad.gates.build (else only when the record is missing)")
    gates_p.add_argument("--dry-run", action="store_true", help="List what would run and why, and run nothing")
    rp_p = sub.add_parser("review-packet", parents=[common],
                          help="Render each dossier section's review packet: exports/review/<section>/ + manifest.json")
    rp_p.add_argument("sections", nargs="*", metavar="SECTION", help="Section ids (default: every section)")
    rp_p.add_argument("--list", action="store_true", help="List the views each section gets; render and write nothing")
    rp_p.add_argument("--view", nargs="+", metavar="VIEW", help="Render only these view ids (others kept if current)")
    rp_p.add_argument("--size", default="1400x1000", help="Image size WIDTHxHEIGHT (default 1400x1000)")
    rp_p.add_argument("--explode", type=float, default=1.0, help="Scale of the exploded view (0: no exploded view)")
    rp_p.add_argument("--context", choices=("neighbours", "all", "none"), default="neighbours",
                      help="Other sections' parts drawn faint (default: neighbours)")
    rs_p = sub.add_parser("review-section", parents=[common],
                          help="Reviewer pass: write a section's reviewer bundle, or --submit a reviewer record")
    rs_p.add_argument("section", metavar="SECTION", help="The dossier section id")
    rs_p.add_argument("--bundle-dir", default=None,
                      help="Where to write the bundle (default: <exports>/review-bundle/<section>/)")
    rs_p.add_argument("--since", default=None, metavar="REV",
                      help="Diff the section's sources against this git revision (default: the last sign-off)")
    rs_grp = rs_p.add_mutually_exclusive_group()
    rs_grp.add_argument("--submit", metavar="RECORD",
                        help="Check a filled-in reviewer record against the current build and write it to "
                             "dossier/reviews/ (the actor is CAD_AGENT_ACTOR)")
    rs_grp.add_argument("--check", metavar="RECORD", help="Like --submit, but write nothing")
    return parser

def main(argv: Optional[Sequence[str]] = None) -> int:
    return dispatch(build_parser().parse_args(argv))

if __name__ == "__main__":
    sys.exit(main())
