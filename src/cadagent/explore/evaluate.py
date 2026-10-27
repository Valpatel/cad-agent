"""Evaluate designs: the generic part (parts, BOM, cost, mass) plus the project's own evaluator.

The project supplies the evaluator, so the physics stays in the project. In Python
(``evaluator: tools/evaluate.py:evaluate``)::

    def evaluate(candidate):               # cadagent.explore.design.Candidate
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
JSON file holding the resolved design, ``{id}`` the design's id (a name for a folder of per-design outputs, such as
``trial-00007``) and ``{python}`` the project's python. The command runs in the project root.

A crash, a non-zero exit, a timeout or output that is not JSON makes that design an ``error`` with the reason; it
never stops the other designs.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from cadagent.explore import metrics as M
from cadagent.explore.catalogue import Catalogue, is_number
from cadagent.explore.config import Constraint, EvaluatorSpec, ExploreConfig, Objective
from cadagent.explore.design import Candidate, bom, bom_checks, bom_metrics, resolve
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
            sys.path.insert(0, str(path.parent))          # as when the file is run as a script: siblings import
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
            sys.path.insert(0, str(Path(root).resolve()))
        try:
            module = importlib.import_module(target)
        except Exception as exc:
            raise CadConfigError(f"evaluator module {target} failed to import: {type(exc).__name__}: {exc}") from exc
    fn = getattr(module, func, None)
    if not callable(fn):
        raise CadConfigError(f"evaluator {spec.python}: {func!r} is not a function in {target}")
    return fn


def _command_evaluator(spec: EvaluatorSpec, root: Path, python: str) -> Evaluator:
    def run(candidate: Candidate) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="cadagent-eval-") as tmp:
            design_file = Path(tmp) / f"{candidate.id or 'design'}.json"
            design_file.write_text(json.dumps(candidate.design, indent=1) + "\n")
            argv = [a.replace("{design}", str(design_file)).replace("{python}", python).replace("{id}", candidate.id)
                    for a in spec.command]
            env = dict(os.environ, CAD_AGENT_PROJECT=str(root), PYTHONUNBUFFERED="1")
            try:
                proc = subprocess.run(argv, input=json.dumps(candidate.request()), capture_output=True, text=True,
                                      cwd=root, env=env, timeout=spec.timeout_s)
            except subprocess.TimeoutExpired:
                raise EvaluatorError(f"timed out after {spec.timeout_s:g} s") from None
            except OSError as exc:
                raise EvaluatorError(f"could not start {argv[0]}: {exc}") from exc
        if proc.returncode != 0:
            tail = (proc.stderr.strip().splitlines() or proc.stdout.strip().splitlines() or [""])[-1]
            raise EvaluatorError(f"exit code {proc.returncode}: {tail[:300]}")
        out = proc.stdout.strip()
        for text in (out, (out.splitlines() or [""])[-1]):     # the whole output, else its last line (after logs)
            try:
                return json.loads(text)
            except ValueError:
                continue
        raise EvaluatorError(f"stdout is not a JSON object: {out[:200]!r}")
    return run


# ----------------------------------------------------------------------------- normalising what it returns

def normalise_result(raw: Any) -> Dict[str, Any]:
    """Check an evaluator result; returns ``{metrics, checks, lines, summary, data, problems}``. Raises
    ``EvaluatorError`` when it is not a mapping; smaller problems are returned as ``problems`` (shown as warnings)."""
    if not isinstance(raw, dict):
        raise EvaluatorError(f"must return a mapping, got {type(raw).__name__}")
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
            "data": raw.get("data"), "problems": problems}


# ----------------------------------------------------------------------------- objectives and constraints

def value_of(metrics: Dict[str, Dict[str, Any]], name: str) -> Optional[float]:
    v = (metrics.get(name) or {}).get("value")
    return float(v) if is_number(v) else None


def goal_checks(metrics: Dict[str, Dict[str, Any]], objectives: List[Objective],
                constraints: List[Constraint]) -> List[Dict[str, str]]:
    """A ``fail`` check per missing objective and per unmet or missing constraint; an ``ok`` check per met constraint.
    The metric gets ``level`` ``ok`` or ``fail`` so tables can colour it."""
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
        low = c.min is not None and v < c.min
        high = c.max is not None and v > c.max
        level = "fail" if low or high else "ok"
        bound = f"below the minimum {c.min:g}" if low else f"above the maximum {c.max:g}" if high else f"meets {c.describe()}"
        out.append({"id": cid, "level": level, "text": f"{c.metric} = {v:g}: {bound}."})
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
        evaluated: Dict[str, Any] = {"metrics": {}, "checks": [], "lines": [], "summary": "", "data": None, "problems": []}
        if evaluator is not None:
            try:
                evaluated = normalise_result(evaluator(cand))
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
    return result
