"""Evaluate designs: the generic part (parts, BOM, cost, mass) plus the project's own evaluator.

The project supplies the evaluator, so the physics stays in the project. In Python
(``evaluator: tools/evaluate.py:evaluate``)::

    def evaluate(candidate):               # cadagent.simulation.explore.design.Candidate
        motor = candidate.part("drive_motor")              # the catalogue item, or None
        torque = candidate.spec("drive_motor", "peak_torque_nm")
        wheel = candidate.param("wheel_diameter_mm", 150)
        mass = candidate.bom["totals"]["mass_kg"]          # the catalogue parts so far
        return {
            "metrics": {"top_speed_kmh": 6.2, "runtime_min": {"value": 84, "estimate": True}},
            "checks": [{"id": "voltage", "level": "fail", "text": "The battery is above the motor's 24 V."}],
            "lines": [{"name": "Printed parts", "qty": 1, "price_usd": 9.5, "mass_g": 620, "estimate": True}],
            "summary": "One line for the comparison.",
            "data": {},                                     # anything else to keep in comparison.json
        }

Every key is optional. ``lines`` are BOM lines that are not catalogue parts (printed parts, an allowance); they count
in the cost and mass. A metric the evaluator returns replaces the BOM's metric of the same name (``mass_kg`` from CAD,
say). Check levels are ``ok``, ``warn`` and ``fail``; any other level counts as ``fail``.

Any language (``evaluator: {command: [node, tools/evaluate.mjs], timeout_s: 120}``): the request
(``Candidate.request()``: the design, the resolved parts with quantities and the BOM so far) arrives as JSON on
stdin, and the result above is printed as JSON on stdout. In the argv, ``{design}`` becomes the path of a temporary
JSON file holding the resolved design (in a private temporary folder), ``{id}`` the design's id as a plain file name
(``safe_name``: letters, digits and ``. _ + -``, such as ``trial-00007``; an id with other characters gets them
replaced and a short hash added) for a folder of per-design outputs, and ``{python}`` the project's python. The command
runs in the project root, in its own process group: on a timeout the evaluator and everything it started are killed,
and so is anything it leaves running when it exits.

A crash, a non-zero exit, a timeout, output that is not JSON or a number that is not finite makes that design an
``error`` with the reason; it never stops the other designs.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from cadagent.simulation.explore import metrics as M
from cadagent.simulation.explore.catalogue import Catalogue, finite_or_none, is_number, json_default, non_finite
from cadagent.simulation.explore.config import Constraint, EvaluatorSpec, ExploreConfig, Objective
from cadagent.simulation.explore.design import Candidate, bom, bom_checks, bom_metrics, resolve
from cadagent.project import CadConfigError

LEVELS = ("ok", "warn", "fail")
RESULT_KEYS = {"metrics", "checks", "lines", "summary", "data"}
Evaluator = Callable[[Candidate], Dict[str, Any]]


class EvaluatorError(RuntimeError):
    """The evaluator crashed, timed out or returned something unusable for one design."""


# ----------------------------------------------------------------------------- loading the project's evaluator

def load_evaluator(spec: Optional[EvaluatorSpec], root: Path, python: str = "") -> Optional[Evaluator]:
    """A callable ``candidate -> result dict`` for the configured evaluator, or None when there is none."""
    if spec is None:
        return None
    if spec.command:
        return _command_evaluator(spec, Path(root), python or sys.executable)
    target, _, func = spec.python.rpartition(":")
    if target.endswith(".py") or "/" in target:
        path = (Path(root) / target).resolve()
        if not path.is_file():
            raise CadConfigError(f"evaluator file not found: {path}")
        if str(path.parent) not in sys.path:
            sys.path.append(str(path.parent))             # siblings import; appended, so it never shadows a library
        name = f"_cadagent_evaluator_{abs(hash(str(path)))}"
        module_spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[name] = module
        try:
            module_spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(name, None)
            raise CadConfigError(f"evaluator {path.name} failed to import: {type(exc).__name__}: {exc}") from exc
    else:
        if str(Path(root).resolve()) not in sys.path:
            sys.path.append(str(Path(root).resolve()))
        try:
            module = importlib.import_module(target)
        except Exception as exc:
            raise CadConfigError(f"evaluator module {target} failed to import: {type(exc).__name__}: {exc}") from exc
    fn = getattr(module, func, None)
    if not callable(fn):
        raise CadConfigError(f"evaluator {spec.python}: {func!r} is not a function in {target}")
    return fn


SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._+-]+")
_RUNNING: set = set()                      # evaluator processes running now (kill_running_evaluators)
_RUNNING_LOCK = threading.Lock()


def safe_name(text: str) -> str:
    """``text`` as a plain file name: letters, digits and ``. _ + -`` only, never empty, ``.`` or ``..``, never
    starting with ``-`` or ``.``. A name that had to change gets a short hash of the original, so two ids that differ
    only in the characters replaced (``designs/a/std``, ``designs-a/std``) stay apart."""
    text = str(text)
    name = SAFE_NAME_RE.sub("-", text).strip(".-")[:80] or "design"
    if name != text:
        name = f"{name}-{hashlib.sha1(text.encode()).hexdigest()[:8]}"
    return name


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the evaluator and everything it started (its process group, on POSIX)."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass


def kill_running_evaluators() -> int:
    """Kill every command evaluator running now, with what it started, and return how many there were. Evaluators run
    in their own session, so the terminal's Ctrl-C does not reach them: an interrupted run calls this."""
    with _RUNNING_LOCK:
        procs = list(_RUNNING)
    for proc in procs:
        _kill_group(proc)
    return len(procs)


def _command_evaluator(spec: EvaluatorSpec, root: Path, python: str) -> Evaluator:
    def run(candidate: Candidate) -> Dict[str, Any]:
        name = safe_name(candidate.id or "design")
        # a private folder per call; nothing is written anywhere else, whatever the design's id is
        with tempfile.TemporaryDirectory(prefix="cadagent-eval-") as tmp:
            design_file = Path(tmp) / f"{name}.json"
            design_file.write_text(json.dumps(candidate.design, indent=1, default=json_default) + "\n")
            request = Path(tmp) / "request.json"
            request.write_text(json.dumps(candidate.request(), default=json_default))
            argv = [a.replace("{design}", str(design_file)).replace("{python}", python).replace("{id}", name)
                    for a in spec.command]
            env = dict(os.environ, CAD_AGENT_PROJECT=str(root), PYTHONUNBUFFERED="1")
            # stdout and stderr go to files, not pipes: a child the evaluator leaves behind cannot hold the result up
            with open(request, "rb") as stdin, open(Path(tmp) / "stdout", "w+b") as stdout, \
                    open(Path(tmp) / "stderr", "w+b") as stderr:
                try:
                    proc = subprocess.Popen(argv, stdin=stdin, stdout=stdout, stderr=stderr, cwd=root, env=env,
                                            start_new_session=os.name == "posix")
                except OSError as exc:
                    raise EvaluatorError(f"could not start {argv[0]}: {exc}") from exc
                with _RUNNING_LOCK:
                    _RUNNING.add(proc)
                try:
                    returncode = proc.wait(timeout=spec.timeout_s)
                except subprocess.TimeoutExpired:
                    raise EvaluatorError(f"timed out after {spec.timeout_s:g} s") from None
                finally:
                    _kill_group(proc)              # on a timeout or Ctrl-C, and whatever it left running
                    proc.wait()
                    with _RUNNING_LOCK:
                        _RUNNING.discard(proc)
                stdout.seek(0)
                stderr.seek(0)
                out_text = stdout.read().decode(errors="replace")
                err_text = stderr.read().decode(errors="replace")
        if returncode != 0:
            tail = (err_text.strip().splitlines() or out_text.strip().splitlines() or [""])[-1]
            raise EvaluatorError(f"exit code {returncode}: {tail[:300]}")
        out = out_text.strip()
        for text in (out, (out.splitlines() or [""])[-1]):     # the whole output, else its last line (after logs)
            try:
                return json.loads(text)
            except ValueError:
                continue
        raise EvaluatorError(f"stdout is not a JSON object: {out[:200]!r}")
    return run


# ----------------------------------------------------------------------------- normalising what it returns

def normalise_result(raw: Any) -> Dict[str, Any]:
    """Check an evaluator result; returns ``{metrics, checks, lines, summary, data, problems, errors}``. Raises
    ``EvaluatorError`` when it is not a mapping; smaller problems are returned as ``problems`` (shown as warnings).
    A NaN or infinity anywhere in it is an ``error`` (the design cannot be ranked on it) and is replaced by null."""
    if not isinstance(raw, dict):
        raise EvaluatorError(f"must return a mapping, got {type(raw).__name__}")
    errors = [f"the evaluator returned {value} at {path}, not a finite number"
              for path, value in non_finite({k: raw.get(k) for k in ("metrics", "lines", "data") if k in raw})]
    raw = finite_or_none(raw)
    problems: List[str] = []
    unknown = sorted(set(raw) - RESULT_KEYS)
    if unknown:
        problems.append(f"unknown keys {unknown} were ignored (expected {sorted(RESULT_KEYS)})")
    metrics: Dict[str, Dict[str, Any]] = {}
    raw_metrics = raw.get("metrics") or {}
    if not isinstance(raw_metrics, dict):
        problems.append("metrics must be a mapping of name -> value")
        raw_metrics = {}
    for name, value in raw_metrics.items():
        metric, problem = M.normalise(str(name), value)
        metrics[str(name)] = metric
        if problem:
            problems.append(problem)
    checks: List[Dict[str, str]] = []
    raw_checks = raw.get("checks") or []
    if not isinstance(raw_checks, list):
        problems.append("checks must be a list")
        raw_checks = []
    for i, c in enumerate(raw_checks):
        if not isinstance(c, dict):
            problems.append(f"checks[{i}] is not a mapping")
            continue
        level = str(c.get("level", "")).lower()
        text = str(c.get("text") or c.get("message") or "")
        if level not in LEVELS:
            text = f"{text} (level {c.get('level')!r} is not ok, warn or fail, so it counts as fail)"
            level = "fail"
        checks.append({"id": str(c.get("id") or f"check-{i + 1}"), "level": level, "text": text})
    lines = raw.get("lines") or []
    if not isinstance(lines, list) or not all(isinstance(x, dict) for x in lines):
        problems.append("lines must be a list of mappings")
        lines = []
    summary = raw.get("summary") or ""
    return {"metrics": metrics, "checks": checks, "lines": lines, "summary": str(summary),
            "data": raw.get("data"), "problems": problems, "errors": errors}


# ----------------------------------------------------------------------------- objectives and constraints

def value_of(metrics: Dict[str, Dict[str, Any]], name: str) -> Optional[float]:
    v = (metrics.get(name) or {}).get("value")
    return float(v) if is_number(v) else None


def goal_checks(metrics: Dict[str, Dict[str, Any]], objectives: List[Objective],
                constraints: List[Constraint]) -> List[Dict[str, str]]:
    """A ``fail`` check per missing objective and per unmet or missing constraint; an ``ok`` check per met constraint.
    An incomplete total is a lower bound (the true value is at least the one shown): a maximum it might exceed, or a
    minimum it does not reach yet, cannot be confirmed, which is a ``warn``. The metric gets the check's ``level``."""
    out = []
    for o in objectives:
        if value_of(metrics, o.metric) is None:
            out.append({"id": f"objective-{o.metric}", "level": "fail",
                        "text": f"No numeric value for the objective {o.metric}."})
    for c in constraints:
        v = value_of(metrics, c.metric)
        cid = f"constraint-{c.metric}"
        if v is None:
            out.append({"id": cid, "level": "fail", "text": f"Constraint {c.describe()}: no numeric value."})
            continue
        lower_bound = bool(metrics[c.metric].get("incomplete"))
        shown = f"{c.metric} {'≥ ' if lower_bound else '= '}{v:g}"
        if c.max is not None and v > c.max:
            level, text = "fail", f"{shown}: above the maximum {c.max:g}."
        elif c.min is not None and v < c.min and not lower_bound:
            level, text = "fail", f"{shown}: below the minimum {c.min:g}."
        elif lower_bound and (c.max is not None or (c.min is not None and v < c.min)):
            level, text = "warn", (f"{shown}: cannot confirm {c.describe()}, as the total leaves out parts without a "
                                   "value; add them to check it.")
        else:
            level, text = "ok", f"{shown}: meets {c.describe()}."
        out.append({"id": cid, "level": level, "text": text})
        metrics[c.metric]["level"] = level
    return out


def verdict(checks: List[Dict[str, str]], errors: List[str]) -> str:
    if errors:
        return "error"
    levels = {c["level"] for c in checks}
    return "fail" if "fail" in levels else "warn" if "warn" in levels else "ok"


def check_counts(checks: List[Dict[str, str]]) -> Dict[str, int]:
    return {lvl: sum(1 for c in checks if c["level"] == lvl) for lvl in LEVELS}


# ----------------------------------------------------------------------------- one design, end to end

def evaluate_design(design: Dict[str, Any], catalogue: Catalogue, cfg: ExploreConfig,
                    evaluator: Optional[Evaluator] = None, design_id: str = "", file: Optional[str] = None,
                    path: Optional[Path] = None) -> Dict[str, Any]:
    """Resolve, cost and weigh a loaded design, run the project's evaluator, and judge it against the objectives and
    constraints. Never raises for a problem with the design or the evaluator: the result's ``verdict`` is ``error``
    and ``errors`` says why."""
    started = time.monotonic()
    name = str(design.get("name") or design_id)
    result: Dict[str, Any] = {"id": design_id or name, "name": name, "file": file, "verdict": "error", "summary": "",
                              "notes": design.get("notes") or "", "metrics": {}, "checks": [], "errors": [],
                              "counts": {}, "parts": {}, "params": design.get("params") or {}, "bom": None}
    cand, errors, checks = resolve(design, catalogue, cfg.slots, result["id"], file, path)
    if cand is not None:
        result["parts"] = {s: p.item.get("id") for s, p in cand.picks.items()}
        cand.bom = bom(cand, cfg.slots)
        evaluated: Dict[str, Any] = {"metrics": {}, "checks": [], "lines": [], "summary": "", "data": None,
                                     "problems": [], "errors": []}
        if evaluator is not None:
            try:
                evaluated = normalise_result(evaluator(cand))
                errors += evaluated["errors"]
            except EvaluatorError as exc:
                errors.append(f"evaluator: {exc}")
            except Exception as exc:    # the project's code: report it on this design, keep going with the others
                tb = traceback.extract_tb(exc.__traceback__)
                at = f" ({Path(tb[-1].filename).name}:{tb[-1].lineno})" if tb else ""
                errors.append(f"evaluator raised {type(exc).__name__}: {exc}{at}")
        final = bom(cand, cfg.slots, evaluated["lines"])
        metrics = bom_metrics(final)
        metrics.update(evaluated["metrics"])
        checks += bom_checks(final)
        checks += [{"id": "evaluator-output", "level": "warn", "text": p} for p in evaluated["problems"]]
        checks += evaluated["checks"]
        result.update(bom=final, metrics=metrics, summary=evaluated["summary"])
        if evaluated["data"] is not None:
            result["data"] = evaluated["data"]
    if not errors:
        checks += goal_checks(result["metrics"], cfg.objectives, cfg.constraints)
    checks += [{"id": "error", "level": "fail", "text": e} for e in errors]
    result.update(checks=checks, errors=errors, verdict=verdict(checks, errors), counts=check_counts(checks),
                  seconds=round(time.monotonic() - started, 3))
    return finite_or_none(result)       # a NaN was reported above; JSON output never carries one
