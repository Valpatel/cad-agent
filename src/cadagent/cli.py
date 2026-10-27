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
from cadagent.project import CadConfigError, CadProject, Step, load_project

SUBCOMMANDS = ("build", "export-3mf", "check", "report", "package", "serve", "site", "view", "webkit", "all",
               "catalogue", "compare", "optimise")
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
    # VPTEST_CAD_PROJECT is still set for steps written against vptest cad
    env = dict(os.environ, PYTHONUNBUFFERED="1", CAD_AGENT_PROJECT=str(project.root),
               VPTEST_CAD_PROJECT=str(project.root))
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
    from cadagent.mesh3mf import export_parts_3mf
    from cadagent.report import load_parts

    parts, error = load_parts(project)
    if error:
        raise _Unusable(error)
    if not project.printer.bed_mm:
        raise _Unusable("cad.printer.bed_mm is required to centre 3MF files on the bed")
    reports = export_parts_3mf(project.exports_dir, list(parts), project.printer.bed_mm[:2])
    for r in reports:
        _say(f"  {r['part']}.3mf  {r['triangles']} triangles  watertight  {r['volume_mm3']:.1f} mm3")
    _say(f"{len(reports)} 3MF file(s) written and read back")
    return 0

def _print_results(results: Dict[str, Any]) -> None:
    from cadagent.report import summarize

    width = max([len(c.get("name", "")) for f in results["features"] for c in f["checks"]] + [10])
    width = min(width, 48)
    for feature in results["features"]:
        _say(feature["feature_title"])
        for check in feature["checks"]:
            status = str(check.get("status", "")).upper()
            _say(f"  {status:<5} {check.get('name', '')[:width]:<{width}}  {check.get('message', '')}")
    counts = summarize(results)
    _say(f"{counts['pass']} pass / {counts['fail']} fail / {counts['skip']} skip"
         " · CAD only: physical fit not verified, slicer not run")

def cmd_check(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.report import collect, summarize

    results = collect(project)
    if getattr(args, "json", False):
        print(json.dumps(results, indent=2))
    else:
        _print_results(results)
    return 1 if summarize(results)["fail"] else 0

def cmd_report(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.report import summarize, write_report

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

def cmd_serve(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.serve import serve

    return serve(project, getattr(args, "host", None), getattr(args, "port", None))

def cmd_site(project: CadProject, args: argparse.Namespace) -> int:
    from cadagent.site import build_site, serve_site

    if not getattr(args, "serve", False):
        summary = build_site(project.root, project.site, project.title)
        _say(f"site: {summary['site']}/index.html ({summary['pages']} pages, {summary['milestones']} milestones, "
             f"{summary['decisions']} decisions, {summary['designs']} designs)")
        return 0
    host = getattr(args, "host", None) or project.serve.host
    port = project.serve.port if getattr(args, "port", None) is None else args.port
    server, url = serve_site(project.root, project.site, project.title, host, port)
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
    from cadagent.view import export_view

    r = export_view(project)
    _say(f"view: {r['manifest']} ({r['parts']} parts" + (f"; no STEP for {', '.join(r['skipped'])}" if r["skipped"] else "") + ")")
    _say("open it with `cad-agent site --serve` (3D model link) or webkit/viewer.html")
    return 0

def cmd_webkit(project: CadProject, args: argparse.Namespace) -> int:
    import shutil
    from cadagent.site import KIT_DIR

    dest = (project.root / args.dest).resolve()
    shutil.copytree(KIT_DIR, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    _say(f"webkit: copied to {dest}")
    return 0

def cmd_all(project: CadProject, args: argparse.Namespace) -> int:
    args.from_step = None
    args.only = None
    if cmd_build(project, args):
        return 1
    if cmd_export_3mf(project, args):
        return 1
    report_rc = cmd_report(project, args)
    package_rc = cmd_package(project, args)
    if report_rc:
        _say("checks FAILED; the package was still written for review")
    return report_rc or package_rc

# ----------------------------------------------------------------------------- explore: catalogue, compare, optimise

def _warn(msg: str) -> None:
    """A warning on stderr, so `--json` output on stdout stays parseable."""
    print(f"cad-agent: WARN {msg}", file=sys.stderr, flush=True)


def _explore(project: CadProject):
    """The project's explore config and catalogue, with the catalogue's load problems."""
    from cadagent.explore.catalogue import load_configured
    from cadagent.explore.config import explore_config

    if not project.explore:
        raise _Unusable("no explore: section under cad: in cad-agent.yaml (docs/explore.md)")
    cfg = explore_config(project.root, project.explore, project.title)
    if cfg.unknown_keys:
        _warn(f"unknown explore: keys ignored: {', '.join(cfg.unknown_keys)}")
    if not cfg.catalogue:
        raise _Unusable("cad.explore.catalogue lists no catalogue files")
    catalogue, issues = load_configured(cfg)
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
    from cadagent.explore.catalogue import check_catalogue, counts
    from cadagent.explore.design import DesignError, check_slots, load_design, resolve

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
        _say(f"catalogue: {len(catalogue)} parts in {len(set(catalogue.files.values()))} file(s) ({cats}); "
             f"{n['error']} errors, {n['warn']} warnings")
        _say(f"designs: {len(designs)} checked against it, {design_errors} errors")
    return 1 if n["error"] or design_errors else 0


def _print_leaderboard(comp: Dict[str, Any], limit: int = 25) -> None:
    from cadagent.explore import metrics as M

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
    from cadagent.explore.catalogue import check_catalogue, counts
    from cadagent.explore.compare import compare_designs, write_comparison
    from cadagent.explore.evaluate import load_evaluator

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
        print(json.dumps(comp, indent=1, default=str))
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
    from cadagent.explore.evaluate import load_evaluator
    from cadagent.explore.optimise import run_search

    cfg, catalogue, issues = _explore(project)
    for issue in issues:
        if issue.level == "error":
            _say(f"  {issue}")
    if any(i.level == "error" for i in issues):
        raise _Unusable("the catalogue has errors (cad-agent catalogue)")
    evaluator = load_evaluator(cfg.evaluator, project.root, project.python)
    r = run_search(cfg, catalogue, evaluator, trials=args.trials, workers=args.workers, sampler=args.sampler,
                   seed=args.seed, fresh=args.fresh, progress=_say)
    _say(f"search ({r['sampler']}): {r['new']} new trial(s) in {r['seconds']:.1f}s, {r['trials']} in total; "
         f"{r['feasible']} feasible, {r['pareto']} on the Pareto front" + (" (interrupted)" if r["interrupted"] else ""))
    for name in r["best"]:
        _say(f"  front: {name}")
    _say(f"leaderboard: {r['leaderboard']}")
    return 0 if r["feasible"] and not r["interrupted"] else 1


HANDLERS = {
    "build": cmd_build,
    "export-3mf": cmd_export_3mf,
    "check": cmd_check,
    "report": cmd_report,
    "package": cmd_package,
    "serve": cmd_serve,
    "site": cmd_site,
    "view": cmd_view,
    "webkit": cmd_webkit,
    "all": cmd_all,
    "catalogue": cmd_catalogue,
    "compare": cmd_compare,
    "optimise": cmd_optimise,
}

def dispatch(args: argparse.Namespace) -> int:
    sub = getattr(args, "cad_command", None)
    if sub not in HANDLERS:
        _err("choose a subcommand: " + ", ".join(SUBCOMMANDS) + " (cad-agent --help)")
        return 2
    try:
        project = load_project(getattr(args, "project", None))
        if project.unknown_keys:
            _say(f"WARN unknown cad: keys ignored: {', '.join(project.unknown_keys)}")
        return HANDLERS[sub](project, args)
    except (CadConfigError, MissingDependency, _Unusable) as exc:
        _err(f"{sub}: {exc}")
        return 2
    except FileNotFoundError as exc:
        _err(f"{sub}: {exc}")
        return 2
    except RuntimeError as exc:
        # GeometryError / Mesh3mfError: the output was produced but failed verification
        _err(f"{sub}: FAILED: {exc}")
        return 1

PROJECT_HELP = "CAD project root containing cad-agent.yaml or vptest.yaml with a cad: section (default: cwd)"

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
    sub.add_parser("export-3mf", parents=[common], help="Write a bed-centred 3MF per part STL and verify it")
    check_p = sub.add_parser("check", parents=[common], help="Collect check results; exit 1 if any fail")
    check_p.add_argument("--json", action="store_true", help="Print the results JSON (schema 1.0)")
    report_p = sub.add_parser("report", parents=[common], help="Write results JSON + standalone HTML report")
    report_p.add_argument("--open", action="store_true", help="Open the report in a browser")
    sub.add_parser("package", parents=[common], help="Zip the review package with a sha256 manifest")
    serve_p = sub.add_parser("serve", parents=[common], help="Serve the project over http (Bambu Studio links)")
    serve_p.add_argument("--port", type=int, default=None,
                         help="Port (default: cad.serve.port, 0 = any free port)")
    serve_p.add_argument("--host", default=None, help="Bind address (default: cad.serve.host, 127.0.0.1)")
    site_p = sub.add_parser("site", parents=[common], help="Build the project site (progress, designs, decisions, docs)")
    site_p.add_argument("--serve", action="store_true", help="Serve it, rebuilding when a source file changes")
    site_p.add_argument("--port", type=int, default=None, help="Port (default: cad.serve.port, 0 = any free port)")
    site_p.add_argument("--host", default=None, help="Bind address (default: cad.serve.host, 127.0.0.1)")
    sub.add_parser("view", parents=[common], help="Export every part in assembly position for the 3D viewer")
    webkit_p = sub.add_parser("webkit", parents=[common], help="Copy the web kit (3D stage, viewer, HUD) into the project")
    webkit_p.add_argument("dest", nargs="?", default="web/kit", help="Destination folder (default: web/kit)")
    sub.add_parser("all", parents=[common], help="build, export-3mf, check + report, package")
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
    return parser

def main(argv: Optional[Sequence[str]] = None) -> int:
    return dispatch(build_parser().parse_args(argv))

if __name__ == "__main__":
    sys.exit(main())
