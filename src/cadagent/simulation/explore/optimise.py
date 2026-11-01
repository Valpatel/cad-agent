"""Search: generate and evaluate many designs, and rank them (``cad-agent optimise``).

The project says what may change and what "better" means; cad-agent runs the loop. Config under ``explore:``::

    objectives: [...]                       # shared with `cad-agent compare`
    constraints: [...]
    evaluator: ...
    search:
      base: designs/standard.json           # every trial starts from this design
      sampler: nsga2                        # random | grid (built in) | nsga2 | tpe (need optuna: the explore extra)
      trials: 200                           # per run; grid stops when every combination is done
      workers: 4                            # evaluations running at the same time (threads)
      seed: 1
      population: 24                        # nsga2 only
      space:
        - {slot: drive_motor}                                  # every catalogue part of the slot's category
        - {slot: battery, choices: [pack-a, pack-b, null]}     # or these; null leaves the slot empty
        - {param: wheel_diameter_mm, low: 120, high: 200, step: 10}
        - {param: frame.material, choices: [pla, petg]}        # dotted paths into the design's params
      confirm:                              # optional: re-evaluate the leaders with a finer, slower evaluator
        top: 3                              # the first 3 feasible trials of the leaderboard
        args: [--mesh, "3"]                 # appended to the evaluator's command; or `evaluator:` (its own)
        tolerance_pct: 5                    # flag a change of more than 5 % in an objective or constraint

Every trial is written as a design (``<out>/search/trials/trial-00007.json``) and evaluated exactly like a design in
``cad-agent compare``. ``trials.jsonl`` records each trial (one JSON object per line) and ``leaderboard.json`` +
``leaderboard.html`` rank them, refreshed as trials finish. The first trial of a new search is the base design
itself, when the space can express it. Running again continues the numbering and, for optuna, the study in
``study.db`` (with a new seed); ``search.json`` records what the trials were computed against, and a run whose inputs
changed stops and says what; ``fresh=True`` (``--fresh``) deletes the previous trials first. A combination that was
already evaluated is not evaluated again. Ctrl-C stops the running command evaluators and writes the leaderboard.

``confirm`` runs after the trials: the leaders are evaluated again with the confirm evaluator (``confirm_leaders``),
recorded in ``confirm.jsonl``, and the leaderboard ranks each confirmed trial on its confirmed evaluation, keeping the
screening values beside it (``confirmed_evaluation``). When that brings an unconfirmed trial into the top, it is
confirmed too, up to ``limit`` confirmations a run. The sampler only ever learns the screening values, so the search
itself stays at one fidelity.

With ``workers`` above 1 a Python evaluator runs in threads, so it must be thread-safe, and it only runs in parallel
where it waits on something else (a subprocess, a solver that releases the GIL). For CPU-heavy evaluation in Python,
use a command evaluator: each trial is then its own process.

The optimiser searches the model the evaluator encodes: a winning trial is as good as that model and the catalogue.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import math
import random
import shlex
import shutil
import time
import warnings
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from cadagent._deps import require
from cadagent.simulation.explore.catalogue import Catalogue, finite_or_none, is_number, json_default
from cadagent.simulation.explore.compare import comparison, describe_choice, feasible, with_part, write_comparison
from cadagent.simulation.explore.config import EvaluatorSpec, ExploreConfig, parse_evaluator
from cadagent.simulation.explore.design import (DesignError, bom, bom_metrics, candidates, fits, get_path, load_design,
                                                resolve, set_path)
from cadagent.simulation.explore.evaluate import (Evaluator, check_counts, evaluate_design, kill_running_evaluators,
                                                  load_evaluator, value_of, verdict)
from cadagent.project import CadConfigError

SAMPLERS = ("random", "grid", "nsga2", "tpe")
OPTUNA_HINT = "the nsga2 and tpe samplers (pip install -e '.[explore]' in the cad-agent checkout, or pip install optuna)"
_SEARCH_KEYS = {"base", "sampler", "trials", "workers", "seed", "population", "space", "name", "confirm"}
_CONFIRM_KEYS = {"top", "args", "evaluator", "timeout_s", "tolerance_pct", "limit"}
# A screening value that moves by more than this when confirmed is flagged. 5 % is a common bar for a converged mesh
# (a peak that changes less between two meshes is taken as settled); tighten it where a gate has little margin.
DEFAULT_TOLERANCE_PCT = 5.0
CONFIRM_LOG = "confirm.jsonl"


@dataclass
class Dimension:
    """One thing the search may change: the part in a slot, or a parameter."""
    key: str                                  # "slot:drive_motor" or "param:wheel_diameter_mm"
    kind: str                                 # "slot" or "param"
    target: str                               # the slot name or the dotted parameter path
    choices: Optional[List[Any]] = None
    low: Optional[float] = None
    high: Optional[float] = None
    step: Optional[float] = None
    log: bool = False
    integer: bool = False

    @property
    def label(self) -> str:
        return self.target.rsplit(".", 1)[-1]

    def values(self) -> List[Any]:
        """Every value, for the grid sampler (a range needs a step)."""
        if self.choices is not None:
            return list(self.choices)
        if self.step is None:
            raise CadConfigError(f"search space {self.key}: the grid sampler needs a 'step' (or 'choices')")
        n = int(math.floor((self.high - self.low) / self.step + 1e-9))
        return [self._cast(self.low + i * self.step) for i in range(n + 1)]

    def sample(self, rng: random.Random) -> Any:
        if self.choices is not None:
            return rng.choice(self.choices)
        if self.step is not None:
            n = int(math.floor((self.high - self.low) / self.step + 1e-9))
            return self._cast(self.low + rng.randint(0, n) * self.step)
        if self.log:
            return self._cast(math.exp(rng.uniform(math.log(self.low), math.log(self.high))))
        return self._cast(rng.uniform(self.low, self.high))

    def contains(self, value: Any) -> bool:
        if self.choices is not None:
            return value in self.choices
        if not is_number(value) or not self.low - 1e-9 <= value <= self.high + 1e-9:
            return False
        if self.step is None:
            return True
        k = (value - self.low) / self.step
        return abs(k - round(k)) < 1e-6

    def _cast(self, v: float) -> Any:
        return int(round(v)) if self.integer else round(v, 10)


@dataclass
class ConfirmConfig:
    """``search.confirm``: evaluate the leaders again with a finer (slower) evaluator, such as a finer mesh."""
    spec: EvaluatorSpec                    # what runs: the search's evaluator with ``args`` appended, or its own
    top: int = 3                           # the first ``top`` feasible trials of the leaderboard
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT
    limit: int = 9                         # confirmations per run, at most (default 3 x top)

    def describe(self) -> str:
        return self.spec.describe()


def _whole(value: Any, where: str, least: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < least:
        raise CadConfigError(f"{where} must be a whole number ≥ {least}, got {value!r}")
    return value


def confirm_config(raw: Any, cfg: ExploreConfig) -> Optional[ConfirmConfig]:
    """Parse ``search.confirm`` (None when absent). It needs ``args`` (appended to a command evaluator's argv, such as
    ``[--mesh, "3"]``), its own ``evaluator``, or both: the same evaluator again would only repeat the trial."""
    where = "cad.explore.search.confirm"
    if raw in (None, False, {}):
        return None
    if not isinstance(raw, dict):
        raise CadConfigError(f"{where} must be a mapping, got {raw!r}")
    unknown = sorted(set(raw) - _CONFIRM_KEYS)
    if unknown:
        raise CadConfigError(f"{where}: unknown keys {unknown}")
    top = _whole(raw.get("top", 3), f"{where}.top", 1)
    limit = _whole(raw.get("limit", 3 * top), f"{where}.limit", top)
    tolerance = raw.get("tolerance_pct", DEFAULT_TOLERANCE_PCT)
    if not is_number(tolerance) or tolerance < 0:
        raise CadConfigError(f"{where}.tolerance_pct must be a number ≥ 0 (a percentage), got {tolerance!r}")
    args = raw.get("args") or []
    if isinstance(args, str):
        args = shlex.split(args)
    if not isinstance(args, list) or not all(isinstance(a, str) or is_number(a) for a in args):
        raise CadConfigError(f"{where}.args must be a list of command-line arguments, such as [--mesh, '3'], got {args!r}")
    args = [str(a) for a in args]               # YAML reads `--mesh 3` as a number: the argv gets "3"
    own = parse_evaluator(raw.get("evaluator"), f"{where}.evaluator")
    base = own or cfg.evaluator
    if base is None:
        raise CadConfigError(f"{where}: the search has no evaluator, so confirm needs its own 'evaluator'")
    if own is None and not args:
        raise CadConfigError(f"{where} needs 'args' (appended to the evaluator's command, such as [--mesh, '3']) or "
                             "its own 'evaluator': the same evaluator again would only repeat each trial")
    if args and base.python:
        raise CadConfigError(f"{where}.args go on a command evaluator's argv, and {base.python} is a Python function: "
                             "give confirm its own evaluator (another function, or a command) instead")
    timeout = raw.get("timeout_s", base.timeout_s)
    if not is_number(timeout) or timeout <= 0:
        raise CadConfigError(f"{where}.timeout_s must be a number of seconds > 0, got {timeout!r}")
    spec = EvaluatorSpec(python=base.python, command=list(base.command) + args, timeout_s=float(timeout))
    return ConfirmConfig(spec=spec, top=top, tolerance_pct=float(tolerance), limit=limit)


@dataclass
class SearchConfig:
    base: Path
    sampler: str = "random"
    trials: int = 50
    workers: int = 1
    seed: int = 0
    population: int = 24
    name: str = "explore"
    space: List[Dimension] = field(default_factory=list)
    confirm: Optional[ConfirmConfig] = None


def _dimension(i: int, raw: Any, base: Dict[str, Any], cfg: ExploreConfig, catalogue: Catalogue) -> Dimension:
    where = f"cad.explore.search.space[{i}]"
    if not isinstance(raw, dict) or bool(raw.get("slot")) == bool(raw.get("param")):
        raise CadConfigError(f"{where} needs exactly one of 'slot' or 'param', got {raw!r}")
    unknown = set(raw) - {"slot", "param", "choices", "low", "high", "step", "log"}
    if unknown:
        raise CadConfigError(f"{where}: unknown keys {sorted(unknown)}")
    if raw.get("slot"):
        slot = str(raw["slot"])
        spec = cfg.slots.get(slot)
        choices = raw.get("choices")
        if choices is None:
            ref = (base.get("parts") or {}).get(slot)
            ref = ref.get("part") if isinstance(ref, dict) else ref
            category = (catalogue.get(ref) or {}).get("category") if isinstance(ref, str) else None
            if not len(catalogue):
                raise CadConfigError(f"{where}: slot {slot} draws its parts from the catalogue, and none is "
                                     "configured (cad.explore.catalogue); a parameter search lists only params")
            if not (spec and (spec.category or spec.choices is not None)) and not category:
                raise CadConfigError(f"{where}: slot {slot} has no category (configure slots.{slot}.category, "
                                     "put a catalogue part in it in the base design, or list choices)")
            choices = [it["id"] for it in candidates(catalogue, spec, category)]
        if not isinstance(choices, list) or not choices:
            raise CadConfigError(f"{where}: slot {slot} has no choices (nothing in the catalogue fits it)")
        missing = [c for c in choices if c is not None and c not in catalogue]
        if missing:
            raise CadConfigError(f"{where}: not in the catalogue: {missing}")
        misfits = [f"{c} ({fits(catalogue[c], spec)})" for c in choices if c is not None and fits(catalogue[c], spec)]
        if misfits:
            raise CadConfigError(f"{where}: these do not fit slot {slot}: {'; '.join(misfits)}")
        if spec and spec.required and None in choices:
            raise CadConfigError(f"{where}: slot {slot} is required, so null cannot be a choice")
        return Dimension(f"slot:{slot}", "slot", slot, choices=list(choices))
    param = str(raw["param"])
    if raw.get("choices") is not None:
        choices = raw["choices"]
        if not isinstance(choices, list) or not choices:
            raise CadConfigError(f"{where}: choices must be a non-empty list")
        if not all(c is None or isinstance(c, (bool, int, float, str)) for c in choices):
            raise CadConfigError(f"{where}: choices must be numbers, text, true/false or null")
        return Dimension(f"param:{param}", "param", param, choices=list(choices))
    low, high, step = raw.get("low"), raw.get("high"), raw.get("step")
    if not (is_number(low) and is_number(high) and low < high) or (step is not None and (not is_number(step) or step <= 0)):
        raise CadConfigError(f"{where}: a range needs numbers low < high (and step > 0), got {raw!r}")
    log = bool(raw.get("log", False))
    if log and (low <= 0 or step is not None):
        raise CadConfigError(f"{where}: a log range needs low > 0 and no step")
    integer = all(isinstance(v, int) for v in (low, high)) and (step is None or isinstance(step, int))
    return Dimension(f"param:{param}", "param", param, low=float(low), high=float(high),
                     step=float(step) if step is not None else None, log=log, integer=integer)


def search_config(cfg: ExploreConfig, catalogue: Catalogue, **overrides: Any) -> SearchConfig:
    """Parse ``explore.search`` (with CLI overrides such as ``trials=10``) against the catalogue."""
    raw = dict(cfg.search or {})
    raw.update({k: v for k, v in overrides.items() if v is not None})
    unknown = sorted(set(raw) - _SEARCH_KEYS)
    if unknown:
        raise CadConfigError(f"cad.explore.search: unknown keys {unknown}")
    if not raw.get("base"):
        raise CadConfigError("cad.explore.search.base is required: the design every trial starts from")
    base_path = cfg.root / str(raw["base"])
    if not base_path.is_file():
        raise CadConfigError(f"cad.explore.search.base not found: {base_path}")
    sampler = str(raw.get("sampler", "random"))
    if sampler not in SAMPLERS:
        raise CadConfigError(f"cad.explore.search.sampler must be one of {', '.join(SAMPLERS)}, got {sampler!r}")
    ints = {}
    for key, default, least in (("trials", 50, 1), ("workers", 1, 1), ("seed", 0, 0), ("population", 24, 2)):
        v = raw.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int) or v < least:
            raise CadConfigError(f"cad.explore.search.{key} must be a whole number ≥ {least}, got {v!r}")
        ints[key] = v
    space_raw = raw.get("space") or []
    if not isinstance(space_raw, list) or not space_raw:
        raise CadConfigError("cad.explore.search.space must list at least one slot or param")
    try:
        base = load_design(base_path)
    except DesignError as exc:
        raise CadConfigError(f"cad.explore.search.base: {exc}") from exc
    space = [_dimension(i, d, base, cfg, catalogue) for i, d in enumerate(space_raw)]
    keys = [d.key for d in space]
    if len(set(keys)) != len(keys):
        raise CadConfigError(f"cad.explore.search.space names something twice: {keys}")
    return SearchConfig(base=base_path, sampler=sampler, space=space, name=str(raw.get("name") or "explore"),
                        confirm=confirm_config(raw.get("confirm"), cfg), **ints)


# ----------------------------------------------------------------------------- samplers: ask for a choice, tell the result

class RandomSampler:
    def __init__(self, space: List[Dimension], seed: int, offset: int):
        self.space = space
        self.rng = random.Random(f"{seed}:{offset}")      # a continued run does not repeat the first run's draws

    def ask(self, fixed: Optional[Dict[str, Any]] = None):
        return None, dict(fixed) if fixed else {d.key: d.sample(self.rng) for d in self.space}

    def tell(self, handle: Any, evaluation: Dict[str, Any]) -> None:
        pass

    def abandon(self, handle: Any) -> None:
        pass


class GridSampler:
    """Every combination once, in order (the slots' parts in catalogue order: preferred first, then by price)."""

    def __init__(self, space: List[Dimension], done: set):
        self.space = space
        self.done = done
        self.combos: Iterator[Tuple[Any, ...]] = itertools.product(*[d.values() for d in space])

    def ask(self, fixed: Optional[Dict[str, Any]] = None):
        for combo in self.combos:
            choice = {d.key: v for d, v in zip(self.space, combo)}
            if choice_key(choice) not in self.done:
                return None, choice
        return None, None

    def tell(self, handle: Any, evaluation: Dict[str, Any]) -> None:
        pass

    def abandon(self, handle: Any) -> None:
        pass


class OptunaSampler:
    """NSGA-II or TPE through optuna's ask-and-tell interface. Constraints (failed checks, unmet constraints) go to
    optuna's constraint handling, so an infeasible trial still teaches the search which way to go; a trial that could
    not be evaluated is marked failed."""

    def __init__(self, kind: str, space: List[Dimension], cfg: ExploreConfig, seed: int, population: int,
                 storage: Path, name: str, base_missing: Optional[Dict[str, int]] = None):
        optuna = require("optuna", OPTUNA_HINT)
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        self.optuna, self.cfg, self.base_missing = optuna, cfg, base_missing or {}
        # optuna 5 takes constraints per trial (Trial.set_constraint); older versions through constraints_func
        self.keyed = hasattr(optuna.trial.Trial, "set_constraint")
        extra = {} if self.keyed else {"constraints_func": lambda t: t.user_attrs.get("constraints", [0.0])}
        with warnings.catch_warnings():     # optuna flags multivariate TPE (and, before 5, constraints) experimental
            warnings.simplefilter("ignore", optuna.exceptions.ExperimentalWarning)
            if kind == "nsga2":
                sampler = optuna.samplers.NSGAIISampler(population_size=population, seed=seed, **extra)
            else:
                sampler = optuna.samplers.TPESampler(seed=seed, multivariate=True, **extra)
        storage.parent.mkdir(parents=True, exist_ok=True)
        self.study = optuna.create_study(study_name=name, storage=_sqlite_storage(optuna, storage), sampler=sampler,
                                         directions=["minimize" if o.goal == "min" else "maximize" for o in cfg.objectives],
                                         load_if_exists=True)
        D = optuna.distributions
        self.dists = {}
        for d in space:
            if d.choices is not None:
                self.dists[d.key] = D.CategoricalDistribution(d.choices)
            elif d.integer:
                self.dists[d.key] = D.IntDistribution(int(d.low), int(d.high), step=int(d.step or 1), log=d.log)
            else:
                self.dists[d.key] = D.FloatDistribution(d.low, d.high, step=d.step, log=d.log)

    def ask(self, fixed: Optional[Dict[str, Any]] = None):
        if fixed:
            self.study.enqueue_trial(fixed, skip_if_exists=True)
        trial = self.study.ask(self.dists)
        return trial, {k: trial.params[k] for k in self.dists}

    def tell(self, trial: Any, ev: Dict[str, Any]) -> None:
        values = [value_of(ev.get("metrics") or {}, o.metric) for o in self.cfg.objectives]
        if ev.get("verdict") == "error" or any(v is None for v in values):
            self.study.tell(trial, state=self.optuna.trial.TrialState.FAIL)
            return
        constraints = constraint_values(ev, self.cfg, self.base_missing)
        if self.keyed:
            for i, v in enumerate(constraints):
                trial.set_constraint(f"c{i}", v)
        else:
            trial.set_user_attr("constraints", constraints)
        self.study.tell(trial, values)

    def abandon(self, trial: Any) -> None:
        self.study.tell(trial, state=self.optuna.trial.TrialState.FAIL)


def _sqlite_storage(optuna: Any, path: Path) -> Any:
    """The study in SQLite with a write-ahead log and normal syncing: about four times faster than the default for
    optuna's many small writes, and still safe against corruption (a power cut can lose the last few writes; the
    trials themselves are in trials.jsonl)."""
    storage = optuna.storages.RDBStorage(f"sqlite:///{path}")
    try:
        from sqlalchemy import event

        def pragmas(con: Any, _record: Any) -> None:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
        event.listen(storage.engine, "connect", pragmas)
        storage.engine.dispose()               # connections opened from now on get the pragmas
    except Exception:  # an optuna or SQLAlchemy without these hooks: the defaults still work, just slower
        pass
    return storage


def missing_count(metric: Optional[Dict[str, Any]]) -> int:
    """How many lines an incomplete total leaves out (1 when it does not say)."""
    if not metric or not metric.get("incomplete"):
        return 0
    return len(metric["missing"]) if isinstance(metric.get("missing"), list) else 1


def constraint_values(ev: Dict[str, Any], cfg: ExploreConfig, base_missing: Optional[Dict[str, int]] = None) -> List[float]:
    """Optuna's convention, ≤ 0 is satisfied: the number of failed checks other than the constraints; each
    constraint's shortfall relative to its bound (absolute for a bound of 0; 1.0 when the metric has no value); and
    how many more lines a minimised total leaves out than the base design's does, so the search cannot drift towards
    parts without a price (a lower bound looks like a saving)."""
    fails = sum(1 for c in ev.get("checks") or [] if c["level"] == "fail" and not c["id"].startswith("constraint-"))
    out = [float(fails)]
    for c in cfg.constraints:
        v = value_of(ev.get("metrics") or {}, c.metric)
        if v is None:
            out.append(1.0)
            continue
        worst = -math.inf
        for bound, gap in ((c.min, (c.min - v) if c.min is not None else None), (c.max, (v - c.max) if c.max is not None else None)):
            if gap is not None:
                worst = max(worst, gap / abs(bound) if bound else gap)    # relative, or absolute for a bound of 0
        out.append(float(worst))
    metrics, base_missing = ev.get("metrics") or {}, base_missing or {}
    out.append(float(sum(max(0, missing_count(metrics.get(o.metric)) - base_missing.get(o.metric, 0))
                         for o in cfg.objectives if o.goal == "min")))
    return out


# ----------------------------------------------------------------------------- the loop

def base_missing(base: Dict[str, Any], catalogue: Catalogue, cfg: ExploreConfig) -> Dict[str, int]:
    """How many lines each of the base design's BOM totals leaves out (no evaluator needed)."""
    cand, errors, _ = resolve(base, catalogue, cfg.slots)
    if cand is None:
        return {}
    return {name: missing_count(m) for name, m in bom_metrics(bom(cand, cfg.slots)).items()}


FINGERPRINT = "search.json"


def _evaluator_identity(cfg: ExploreConfig, spec: Optional[EvaluatorSpec]) -> Optional[Dict[str, Any]]:
    """What an evaluator's results depend on, as far as cad-agent can tell: its argv or function, its timeout, and a
    hash of each of its source files."""
    if spec is None:
        return None
    return {"spec": spec.describe(), "timeout_s": spec.timeout_s,
            "files": {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in _evaluator_files(cfg, spec)}}
_WHAT = {"objectives": "objectives", "constraints": "constraints", "currency": "currency", "space": "search space",
         "slots": "slot settings", "base": "base design", "evaluator": "evaluator", "parts": "catalogue parts"}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _evaluator_files(cfg: ExploreConfig, spec: Optional[EvaluatorSpec] = None) -> List[Path]:
    """The evaluator's own source files, as far as they can be told: the Python file, or the files a command names.
    ``spec`` defaults to the search's evaluator."""
    spec = cfg.evaluator if spec is None else spec
    if spec is None:
        return []
    if spec.command:
        return [cfg.root / a for a in spec.command if not a.startswith("{") and (cfg.root / a).is_file()]
    target = spec.python.rpartition(":")[0]
    if target.endswith(".py") or "/" in target:
        return [cfg.root / target]
    try:
        found = importlib.util.find_spec(target)
    except Exception:  # a parent package that fails to import: nothing to hash
        return []
    return [Path(found.origin)] if found and found.origin and Path(found.origin).is_file() else []


def fingerprint(cfg: ExploreConfig, catalogue: Catalogue, sc: "SearchConfig", base: Dict[str, Any]) -> Dict[str, str]:
    """A digest per input a trial's result depends on. A search continues only while they all match."""
    ids = {c for d in sc.space if d.kind == "slot" for c in d.choices or [] if c}
    for v in (base.get("parts") or {}).values():
        ref = v if isinstance(v, str) else v.get("part") if isinstance(v, dict) else None
        if ref:
            ids.add(ref)
    evaluator = _evaluator_identity(cfg, cfg.evaluator)
    inputs = {
        "objectives": [(o.metric, o.goal) for o in cfg.objectives],
        "constraints": [(c.metric, c.min, c.max) for c in cfg.constraints],
        "currency": cfg.currency,
        "space": [vars(d) for d in sc.space],
        "slots": {k: vars(v) for k, v in sorted(cfg.slots.items())},
        "base": {k: v for k, v in base.items() if k not in ("name", "notes")},
        "evaluator": evaluator,
        "parts": {i: catalogue.get(i) for i in sorted(ids)},
    }
    return {k: _digest(v) for k, v in inputs.items()}


def check_fingerprint(path: Path, current: Dict[str, str], trials: int) -> None:
    """Refuse to continue a search whose earlier trials were computed against other inputs."""
    if not trials or not path.is_file():
        return
    try:
        earlier = json.loads(path.read_text())
    except ValueError:
        earlier = {}
    changed = [_WHAT.get(k, k) for k in current if earlier.get(k) != current[k]]
    if changed:
        raise CadConfigError(f"the {trials} earlier trials in {path.parent} were run with a different "
                             f"{', '.join(changed)}: run with --fresh to start over, or change "
                             f"{'it' if len(changed) == 1 else 'them'} back")


def choice_key(choice: Dict[str, Any]) -> str:
    return json.dumps(choice, sort_keys=True, default=str)


def base_choice(base: Dict[str, Any], space: List[Dimension]) -> Optional[Dict[str, Any]]:
    """The base design's own values, or None when one of them is outside the space."""
    choice = {}
    for d in space:
        if d.kind == "slot":
            ref = (base.get("parts") or {}).get(d.target)
            value = ref.get("part") if isinstance(ref, dict) else ref
        else:
            value = get_path(base.get("params") or {}, d.target)
        if not d.contains(value):
            return None
        choice[d.key] = value
    return choice


def trial_design(base: Dict[str, Any], space: List[Dimension], choice: Dict[str, Any], number: int,
                 base_name: str) -> Dict[str, Any]:
    d = json.loads(json.dumps(base, default=json_default))
    for dim in space:
        if dim.kind == "slot":
            d = with_part(d, dim.target, choice[dim.key])
        else:
            set_path(d.setdefault("params", {}), dim.target, choice[dim.key])
    d["name"] = f"trial {number}"
    d["notes"] = f"Trial {number} of the search from {base_name}: {describe_choice(choice)}."
    return d



def read_records(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue                 # a line cut short by a crash: that trial runs again
    return out


def run_search(cfg: ExploreConfig, catalogue: Catalogue, evaluator: Optional[Evaluator], *, trials: Optional[int] = None,
               workers: Optional[int] = None, sampler: Optional[str] = None, seed: Optional[int] = None,
               fresh: bool = False, progress: Callable[[str], None] = print, board_seconds: float = 2.0,
               confirm: bool = True, confirm_evaluator: Optional[Evaluator] = None, python: str = "") -> Dict[str, Any]:
    """Run (or continue) the search; returns a summary with the leaderboard paths. The leaderboard is rewritten as
    trials finish, at most every ``board_seconds``, and once more at the end.

    With ``search.confirm`` configured the leaders are then confirmed (``confirm_leaders``); ``confirm=False`` skips
    that for this run, and the leaderboard still uses the confirmations made earlier. ``confirm_evaluator`` is a
    callable to confirm with (an API caller's own); without it the configured one is loaded, with ``python`` as a
    command's ``{python}``. Confirmations are recorded against the configured confirm evaluator either way."""
    sc = search_config(cfg, catalogue, trials=trials, workers=workers, sampler=sampler, seed=seed)
    out = cfg.out / "search"
    trials_dir, log, db = out / "trials", out / "trials.jsonl", out / "study.db"
    if fresh:
        shutil.rmtree(trials_dir, ignore_errors=True)
        for p in (log, db, out / FINGERPRINT, out / CONFIRM_LOG, out / "leaderboard.json", out / "leaderboard.html"):
            p.unlink(missing_ok=True)
    trials_dir.mkdir(parents=True, exist_ok=True)
    records = read_records(log)
    base = load_design(sc.base)
    fp = fingerprint(cfg, catalogue, sc, base)
    check_fingerprint(out / FINGERPRINT, fp, len(records))
    (out / FINGERPRINT).write_text(json.dumps(fp, indent=1) + "\n")
    cc = sc.confirm
    confirmed = read_confirmations(out / CONFIRM_LOG, confirm_digest(cfg, cc)) if cc else {}
    if cc and confirm and confirm_evaluator is None:     # loaded now, so a bad config stops before the long search
        confirm_evaluator = load_evaluator(cc.spec, cfg.root, python)

    def board() -> Dict[str, Any]:
        return write_leaderboard(cfg, records, out, confirmed, cc)

    cache: Dict[str, Dict[str, Any]] = {}
    for r in records:
        if r.get("evaluation", {}).get("verdict") != "error" and not r.get("duplicate_of"):
            cache.setdefault(choice_key(r["choice"]), r)
    base_name = sc.base.relative_to(cfg.root).as_posix() if sc.base.is_relative_to(cfg.root) else str(sc.base)
    if sc.sampler == "random":
        smp: Any = RandomSampler(sc.space, sc.seed, len(records))
    elif sc.sampler == "grid":
        smp = GridSampler(sc.space, set(cache))
    else:   # a continued run gets its own seed, or the seeded first generation would propose the same trials again
        smp = OptunaSampler(sc.sampler, sc.space, cfg, sc.seed + len(records), sc.population, db, sc.name,
                            base_missing(base, catalogue, cfg))
    first = base_choice(base, sc.space) if not records and sc.sampler != "grid" else None
    number = max([r["trial"] for r in records] or [0])
    started, new, repeats, interrupted = time.monotonic(), 0, 0, False
    last_board, board_cost = started, 0.0
    in_flight: Dict[Future, Tuple[int, Any, Dict[str, Any]]] = {}
    running: set = set()                                                  # combinations being evaluated now
    waiting: Dict[str, List[Tuple[int, Any, Dict[str, Any]]]] = {}       # repeats of those, until their result is in

    def record(n: int, choice: Dict[str, Any], ev: Dict[str, Any], dup: Optional[int]) -> Dict[str, Any]:
        rec = {"trial": n, "id": ev["id"], "choice": choice, "design": ev.get("file"), "duplicate_of": dup,
               "evaluation": ev}
        records.append(rec)
        with open(log, "a") as fh:
            fh.write(json.dumps(rec, default=json_default) + "\n")
        if ev["verdict"] != "error" and dup is None:
            cache.setdefault(choice_key(choice), rec)
        objs = " ".join(f"{o.metric}={value_of(ev['metrics'], o.metric):.4g}" if value_of(ev["metrics"], o.metric) is not None
                        else f"{o.metric}=—" for o in cfg.objectives)
        progress(f"  trial {n}: {ev['verdict']}" + (f" (same as trial {dup})" if dup else "") + f"  {objs}")
        return rec

    def reuse(n: int, handle: Any, choice: Dict[str, Any], original: Dict[str, Any]) -> None:
        """A combination that was evaluated already: the same result under a new trial number."""
        nonlocal repeats
        ev = {**original["evaluation"], "id": f"trial-{n:05d}", "name": f"trial {n} (= trial {original['trial']})",
              "choice": choice}
        smp.tell(handle, ev)
        record(n, choice, ev, original["trial"])
        repeats += 1

    pool = ThreadPoolExecutor(max_workers=sc.workers)
    try:
        try:
            exhausted = False
            while True:
                queued = len(in_flight) + sum(len(w) for w in waiting.values())
                while not exhausted and len(in_flight) < sc.workers and new + queued < sc.trials:
                    handle, choice = smp.ask(first)
                    first = None
                    if choice is None:
                        exhausted = True
                        break
                    number += 1
                    key = choice_key(choice)
                    if key in cache:
                        reuse(number, handle, choice, cache[key])
                        new += 1
                        continue
                    queued += 1
                    if key in running:
                        waiting.setdefault(key, []).append((number, handle, choice))
                        continue
                    design = trial_design(base, sc.space, choice, number, base_name)
                    path = trials_dir / f"trial-{number:05d}.json"
                    path.write_text(json.dumps(design, indent=1, default=json_default) + "\n")
                    rel = path.relative_to(cfg.root).as_posix() if path.is_relative_to(cfg.root) else str(path)
                    fut = pool.submit(evaluate_design, design, catalogue, cfg, evaluator, f"trial-{number:05d}", rel, path)
                    in_flight[fut] = (number, handle, choice)
                    running.add(key)
                if not in_flight:
                    break
                done, _ = wait(list(in_flight), return_when=FIRST_COMPLETED)
                for fut in done:
                    n, handle, choice = in_flight.pop(fut)
                    key = choice_key(choice)
                    running.discard(key)
                    ev = fut.result()
                    ev["choice"] = choice
                    smp.tell(handle, ev)
                    original = record(n, choice, ev, None)
                    new += 1
                    for m, h, c in waiting.pop(key, []):
                        reuse(m, h, c, original)
                        new += 1
                    # rewritten as trials finish, but never more than a tenth of the time, so workers are not kept waiting
                    if time.monotonic() - last_board >= max(board_seconds, 10 * board_cost):
                        t0 = time.monotonic()
                        board()
                        last_board = time.monotonic()
                        board_cost = last_board - t0
        except KeyboardInterrupt:
            interrupted = True
            for fut, (_, handle, _) in in_flight.items():
                fut.cancel()
                smp.abandon(handle)
            for _, handle, _ in (w for ws in waiting.values() for w in ws):
                smp.abandon(handle)
            stopped = kill_running_evaluators()    # they run in their own session: Ctrl-C does not reach them
            board()
            python_left = len(in_flight) - stopped     # Python evaluators cannot be stopped from outside
            progress(f"stopping: the leaderboard has the {len(records)} finished trials"
                     + (f"; waiting for {python_left} running Python evaluation(s) (Ctrl-C again to stop now)"
                        if python_left > 0 else ""))
            pool.shutdown(wait=False, cancel_futures=True)
    finally:
        pool.shutdown(wait=True)
    new_confirmed = 0
    if cc and confirm and not interrupted:
        new_confirmed, interrupted = confirm_leaders(cfg, catalogue, sc, records, out, confirm_evaluator, confirmed,
                                                     board, progress)
    comp = board()
    summary = None
    if cc:
        flagged = [d for d in comp["designs"] if (d.get("confirm") or {}).get("flag")]
        summary = {"evaluator": cc.describe(), "top": cc.top, "tolerance_pct": cc.tolerance_pct, "new": new_confirmed,
                   "confirmed": comp["confirm"]["confirmed"], "ran": bool(confirm),
                   "leaders_confirmed": comp["confirm"]["leaders_confirmed"],
                   "flagged": [f"{d['name']}: {'; '.join(d['confirm']['reasons'])}" for d in flagged]}
    return {"trials": len(records), "new": new, "evaluated": new - repeats, "repeats": repeats,
            "seconds": round(time.monotonic() - started, 1),
            "feasible": comp["summary"]["feasible"], "pareto": comp["summary"]["pareto"],
            "errors": comp["summary"]["errors"], "interrupted": interrupted, "sampler": sc.sampler,
            "leaderboard": str(out / "leaderboard.html"), "json": str(out / "leaderboard.json"),
            "best": [f"{d['name']}: {describe_choice(d.get('choice') or {})}" for d in comp["designs"] if d.get("pareto")][:10],
            "confirm": summary}


def write_leaderboard(cfg: ExploreConfig, records: List[Dict[str, Any]], out: Path,
                      confirmed: Optional[Dict[int, Dict[str, Any]]] = None,
                      confirm: Optional[ConfirmConfig] = None) -> Dict[str, Any]:
    """Rank every distinct trial (repeats of a combination are left out) and write the leaderboard. Its JSON keeps
    each trial's metrics, checks and BOM totals; the full evaluations stay in trials.jsonl. A trial in ``confirmed``
    (trial number -> its ``confirm.jsonl`` record) is ranked on its confirmed evaluation (``confirmed_evaluation``)."""
    # finite_or_none: trials.jsonl written before NaN checks existed may hold NaN, which strict JSON refuses
    evaluations = []
    for r in records:
        if r.get("duplicate_of"):
            continue
        ev = finite_or_none(r["evaluation"])
        c = (confirmed or {}).get(r["trial"]) if confirm is not None else None
        if c is not None:
            ev = confirmed_evaluation(ev, finite_or_none(c["evaluation"]), cfg, confirm.tolerance_pct,
                                      str(c.get("evaluator") or confirm.describe()))
        evaluations.append(ev)
    comp = comparison(evaluations, cfg, kind="search")
    comp["summary"]["repeats"] = len(records) - len(evaluations)
    comp["records"] = "trials.jsonl"
    if confirm is not None:
        done = [d for d in comp["designs"] if d.get("confirm")]
        leaders = [d for d in comp["designs"] if d.get("feasible")][:confirm.top]
        comp["confirm"] = {"evaluator": confirm.describe(), "top": confirm.top, "tolerance_pct": confirm.tolerance_pct,
                           "limit": confirm.limit, "records": CONFIRM_LOG, "confirmed": len(done),
                           "flagged": sum(1 for d in done if d["confirm"]["flag"]),
                           "leaders_confirmed": sum(1 for d in leaders if d.get("confirm") and not d["confirm"]["errors"])}
        comp["summary"].update(confirmed=len(done), flagged=comp["confirm"]["flagged"])
        comp["notes"].append(
            f"The first {confirm.top} feasible trials are evaluated again with {confirm.describe()} and ranked on those "
            f"confirmed values; the others keep their screening values, which may be off by as much as the confirmed "
            f"ones moved. A change of more than {confirm.tolerance_pct:g} % in an objective or constraint is flagged.")
    write_comparison(comp, out, "leaderboard.json", "leaderboard.html", cards=False, slim_json=True)
    return comp


# ----------------------------------------------------------------------------- confirming the leaders

def confirm_digest(cfg: ExploreConfig, cc: Optional[ConfirmConfig]) -> str:
    """What a confirmation was computed with; a confirmation made with anything else is not used."""
    return _digest(_evaluator_identity(cfg, cc.spec)) if cc else ""


def read_confirmations(path: Path, digest: str) -> Dict[int, Dict[str, Any]]:
    """Trial number -> its latest ``confirm.jsonl`` record made with the current confirm evaluator (``digest``)."""
    out: Dict[int, Dict[str, Any]] = {}
    for rec in read_records(path):
        if rec.get("confirm") == digest and isinstance(rec.get("trial"), int) and isinstance(rec.get("evaluation"), dict):
            out[rec["trial"]] = rec
    return out


def change_pct(screen: Optional[float], confirmed: Optional[float]) -> Optional[float]:
    """The confirmed value's change from the screening value, in percent of the screening value; None when either is
    missing, or when the screening value is 0 and the confirmed one is not (no percentage says how far that moved)."""
    if screen is None or confirmed is None:
        return None
    if confirmed == screen:
        return 0.0
    return None if screen == 0 else (confirmed - screen) / abs(screen) * 100.0


def confirmed_evaluation(screen: Dict[str, Any], confirmed: Dict[str, Any], cfg: ExploreConfig,
                         tolerance_pct: float = DEFAULT_TOLERANCE_PCT, evaluator: str = "") -> Dict[str, Any]:
    """The trial as the leaderboard ranks it once confirmed: the confirmed evaluation (its metrics, checks and verdict)
    under the trial's own id and name, or the screening one when the confirmation could not be evaluated. ``confirm``
    holds both values of every objective and constraint metric, their change in percent, and ``flag`` with its
    ``reasons``: a change of more than ``tolerance_pct``, a value that appeared or went, a trial that became feasible
    or infeasible, or a confirmation that failed. A flag adds a ``warn`` check."""
    names = list(dict.fromkeys([o.metric for o in cfg.objectives] + [c.metric for c in cfg.constraints]))
    failed = confirmed.get("verdict") == "error"
    values: Dict[str, Dict[str, Any]] = {}
    flagged: List[str] = []
    reasons: List[str] = []
    for name in names:
        a = value_of(screen.get("metrics") or {}, name)
        b = value_of(confirmed.get("metrics") or {}, name)
        pct = change_pct(a, b)
        values[name] = {"screen": a, "confirmed": b, "change_pct": None if pct is None else round(pct, 2)}
        if failed or (a is None and b is None):
            continue
        if a is None or b is None or pct is None or abs(pct) > tolerance_pct:
            flagged.append(name)
            shown = "" if pct is None else f" ({pct:+.1f} %)"
            reasons.append(f"{name} {'—' if a is None else f'{a:.4g}'} → {'—' if b is None else f'{b:.4g}'}{shown}")
    if failed:
        reasons.append("the confirmation could not be evaluated (" + "; ".join(confirmed.get("errors") or ["error"])[:300]
                       + "), so the trial is ranked on its screening values")
    elif feasible(screen) != feasible(confirmed):
        reasons.append(f"{'feasible' if feasible(confirmed) else 'infeasible'} once confirmed ({confirmed.get('verdict')})")
    block = {"evaluator": evaluator, "tolerance_pct": tolerance_pct, "verdict": confirmed.get("verdict"),
             "screen_verdict": screen.get("verdict"), "values": values, "flagged": flagged, "flag": bool(reasons),
             "reasons": reasons, "errors": list(confirmed.get("errors") or []) if failed else []}
    merged = dict(screen if failed else confirmed)
    merged.update(id=screen.get("id"), name=screen.get("name"), file=screen.get("file"), confirm=block)
    if "choice" in screen:
        merged["choice"] = screen["choice"]
    if reasons:
        checks = list(merged.get("checks") or []) + [{
            "id": "confirm", "level": "warn",
            "text": f"Confirmed with {evaluator or 'the confirm evaluator'}: {'; '.join(reasons)}."}]
        merged.update(checks=checks, counts=check_counts(checks), verdict=verdict(checks, merged.get("errors") or []))
    return merged


def confirm_leaders(cfg: ExploreConfig, catalogue: Catalogue, sc: SearchConfig, records: List[Dict[str, Any]],
                    out: Path, evaluator: Optional[Evaluator], confirmed: Dict[int, Dict[str, Any]],
                    board: Callable[[], Dict[str, Any]], progress: Callable[[str], None] = print) -> Tuple[int, bool]:
    """Evaluate the first ``top`` feasible trials of the leaderboard again with the confirm evaluator, re-rank, and
    repeat while that brings unconfirmed trials into the top, up to ``limit`` evaluations. A trial already confirmed
    with the same evaluator is not evaluated again (one whose confirmation failed is, on a later run). Each result is
    appended to ``confirm.jsonl`` and added to ``confirmed``. Returns ``(evaluations, interrupted)``."""
    cc = sc.confirm
    if cc is None:
        return 0, False
    digest, log = confirm_digest(cfg, cc), out / CONFIRM_LOG
    by_id = {r["id"]: r for r in records if not r.get("duplicate_of")}
    base = load_design(sc.base)
    base_name = sc.base.relative_to(cfg.root).as_posix() if sc.base.is_relative_to(cfg.root) else str(sc.base)
    tried: set = set()                           # this run: a failed confirmation is not retried until the next one
    new = 0
    pool = ThreadPoolExecutor(max_workers=sc.workers)
    futures: Dict[Future, Dict[str, Any]] = {}
    try:
        while new < cc.limit:
            leaders = [d for d in board()["designs"] if d.get("feasible")][:cc.top]
            todo = [by_id[d["id"]] for d in leaders if d["id"] in by_id]
            todo = [r for r in todo if r["trial"] not in tried
                    and (r["trial"] not in confirmed or confirmed[r["trial"]]["evaluation"].get("verdict") == "error")]
            todo = todo[:cc.limit - new]
            if not todo:
                break
            for rec in todo:
                n = rec["trial"]
                tried.add(n)
                design = trial_design(base, sc.space, rec["choice"], n, base_name)
                futures[pool.submit(evaluate_design, design, catalogue, cfg, evaluator, f"{rec['id']}-confirm",
                                    rec.get("design"), out / "trials" / f"trial-{n:05d}.json")] = rec
            while futures:
                done, _ = wait(list(futures), return_when=FIRST_COMPLETED)
                for fut in done:
                    rec = futures.pop(fut)
                    ev = fut.result()
                    ev["choice"] = rec["choice"]
                    crec = {"trial": rec["trial"], "id": rec["id"], "confirm": digest, "evaluator": cc.describe(),
                            "evaluation": ev}
                    with open(log, "a") as fh:
                        fh.write(json.dumps(crec, default=json_default) + "\n")
                    confirmed[rec["trial"]] = crec
                    new += 1
                    merged = confirmed_evaluation(finite_or_none(rec["evaluation"]), finite_or_none(ev), cfg,
                                                  cc.tolerance_pct, cc.describe())
                    c = merged["confirm"]
                    moved = [f"{m} {v['screen']:.4g} → {v['confirmed']:.4g} ({v['change_pct']:+.1f} %)"
                             for m, v in c["values"].items() if v["change_pct"] is not None]
                    said = "; ".join(c["reasons"]) if c["flag"] else "; ".join(moved + [f"within {cc.tolerance_pct:g} %"])
                    progress(f"  confirm trial {rec['trial']}: {ev['verdict']}  {said}")
    except KeyboardInterrupt:
        for fut in futures:
            fut.cancel()
        kill_running_evaluators()                # they run in their own session: Ctrl-C does not reach them
        board()
        progress(f"stopping the confirmation: {new} trial(s) confirmed this run are on the leaderboard")
        pool.shutdown(wait=False, cancel_futures=True)
        return new, True
    finally:
        pool.shutdown(wait=True)
    return new, False
