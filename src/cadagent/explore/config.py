"""The ``explore:`` section under ``cad:`` in ``cad-agent.yaml``. Every key is optional::

    cad:
      explore:
        title: Drive options                      # default: the project title
        currency: usd                             # prices are read from "price_<currency>" (price_usd)
        catalogue: ["catalogue/*.json"]           # part lists (JSON or YAML), globs relative to the project root
        categories: [motor, battery, frame]       # when set, any other category is an error
        max_price_age_days: 90                    # older price_checked dates are warnings (null: never)
        slots:                                    # what each slot of a design takes
          drive_motor: {category: motor, qty: 2, required: true, group: Drive, label: Drive motors}
          computer: {category: compute, choices: [sbc-8gb, sbc-16gb]}           # only these ids fit
          lidar: {category: sensor, where: {specs.type: lidar}}               # or parts whose fields match
        designs: ["designs/*.json"]
        evaluator: tools/evaluate.py:evaluate     # or {command: [node, tools/evaluate.mjs], timeout_s: 120}
        objectives: [{metric: cost_usd, goal: min}, {metric: runtime_min, goal: max}]
        constraints: [{metric: top_speed_kmh, min: 5}]
        metrics: {runtime_min: {label: Runtime, unit: min, digits: 0}}   # display names, units, decimals
        card_metrics: [cost_usd, mass_kg, runtime_min]                    # shown on the project site's design cards
        out: exports/explore
        search: {...}                             # the optimiser (cadagent.explore.optimise)

``objectives`` default to the two numbers every design has: ``cost_<currency>`` and ``mass_kg``, both minimised.
"""

from __future__ import annotations

import glob
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cadagent.project import CadConfigError

GOALS = ("min", "max")
CURRENCY_RE = re.compile(r"^[a-z]{3}$")
_KEYS = {"title", "currency", "catalogue", "categories", "max_price_age_days", "slots", "designs", "evaluator",
         "objectives", "constraints", "metrics", "card_metrics", "out", "search"}


@dataclass
class Objective:
    metric: str
    goal: str = "min"

    @property
    def sign(self) -> float:
        """+1 to minimise, -1 to maximise: ``sign * value`` is always minimised."""
        return 1.0 if self.goal == "min" else -1.0


@dataclass
class Constraint:
    metric: str
    min: Optional[float] = None
    max: Optional[float] = None

    def describe(self) -> str:
        if self.min is not None and self.max is not None:
            return f"{self.min:g} ≤ {self.metric} ≤ {self.max:g}"
        return f"{self.metric} ≥ {self.min:g}" if self.min is not None else f"{self.metric} ≤ {self.max:g}"


@dataclass
class SlotSpec:
    name: str
    category: Optional[str] = None   # a part in this slot must be of this category; swaps and searches draw from it
    qty: int = 1                     # default quantity when a design names only the part
    required: bool = False           # an empty slot fails the design
    group: str = ""                  # BOM subtotal group
    label: str = ""
    choices: Optional[List[str]] = None                     # only these catalogue ids fit
    where: Dict[str, Any] = field(default_factory=dict)     # {"specs.type": "lidar"}: field conditions a part must meet


@dataclass
class EvaluatorSpec:
    python: str = ""                                    # "tools/evaluate.py:evaluate" or "package.module:function"
    command: List[str] = field(default_factory=list)    # argv; "{design}" becomes the design file's path
    timeout_s: float = 600.0

    def describe(self) -> str:
        return self.python or " ".join(self.command)


@dataclass
class ExploreConfig:
    root: Path
    title: str
    currency: str = "usd"
    catalogue: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    max_price_age_days: Optional[int] = 90
    slots: Dict[str, SlotSpec] = field(default_factory=dict)
    designs: List[str] = field(default_factory=list)
    evaluator: Optional[EvaluatorSpec] = None
    objectives: List[Objective] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    card_metrics: List[str] = field(default_factory=list)
    out: Path = Path("exports/explore")
    search: Dict[str, Any] = field(default_factory=dict)
    unknown_keys: List[str] = field(default_factory=list)

    @property
    def price_key(self) -> str:
        return f"price_{self.currency}"

    @property
    def cost_metric(self) -> str:
        return f"cost_{self.currency}"

    def design_files(self) -> Tuple[List[Path], List[str]]:
        """``(files, patterns that matched nothing)``."""
        return expand(self.root, self.designs)

    def catalogue_files(self) -> Tuple[List[Path], List[str]]:
        return expand(self.root, self.catalogue)


DATA_SUFFIXES = (".json", ".yaml", ".yml")


def expand(root: Path, patterns: List[str]) -> Tuple[List[Path], List[str]]:
    """JSON and YAML files matching ``patterns`` (globs or plain paths, relative to ``root``), in pattern order, and
    the patterns that matched none."""
    out: List[Path] = []
    unmatched: List[str] = []
    for pat in patterns:
        full = str(root / pat)                    # an absolute pattern stays absolute
        hits = [Path(h) for h in sorted(glob.glob(full, recursive=True))] if any(c in pat for c in "*?[") else [Path(full)]
        found = [p.resolve() for p in hits if p.is_file() and p.suffix in DATA_SUFFIXES]
        if not found:
            unmatched.append(pat)
        out += [p for p in found if p not in out]
    return out, unmatched


def _dict(value: Any, where: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CadConfigError(f"{where} must be a mapping, got {type(value).__name__}")
    return value


def _list(value: Any, where: str) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise CadConfigError(f"{where} must be a list, got {type(value).__name__}")
    return value


def _number(value: Any, where: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CadConfigError(f"{where} must be a number, got {value!r}")
    return float(value)


def parse_evaluator(raw: Any, where: str = "cad.explore.evaluator") -> Optional[EvaluatorSpec]:
    if raw in (None, "", {}):
        return None
    if isinstance(raw, str):
        raw = {"python": raw}
    raw = _dict(raw, where)
    python, command = raw.get("python") or "", raw.get("command") or []
    if isinstance(command, str):
        command = shlex.split(command)
    if bool(python) == bool(command):
        raise CadConfigError(f"{where} needs exactly one of 'python' (file.py:function) or 'command' (argv)")
    if python and ":" not in str(python):
        raise CadConfigError(f"{where}.python must be 'path/to/file.py:function' or 'module:function', got {python!r}")
    timeout = _number(raw.get("timeout_s", 600), f"{where}.timeout_s")
    return EvaluatorSpec(python=str(python), command=[str(c) for c in _list(command, f"{where}.command")],
                         timeout_s=timeout if timeout and timeout > 0 else 600.0)


def parse_objectives(raw: Any, where: str = "cad.explore.objectives") -> List[Objective]:
    out = []
    for i, item in enumerate(_list(raw, where)):
        item = {"metric": item} if isinstance(item, str) else _dict(item, f"{where}[{i}]")
        goal = str(item.get("goal", "min"))
        if not item.get("metric") or goal not in GOALS:
            raise CadConfigError(f"{where}[{i}] needs 'metric' and goal min or max, got {item!r}")
        out.append(Objective(str(item["metric"]), goal))
    return out


def parse_constraints(raw: Any, where: str = "cad.explore.constraints") -> List[Constraint]:
    out = []
    for i, item in enumerate(_list(raw, where)):
        item = _dict(item, f"{where}[{i}]")
        c = Constraint(str(item.get("metric") or ""), _number(item.get("min"), f"{where}[{i}].min"),
                       _number(item.get("max"), f"{where}[{i}].max"))
        if not c.metric or (c.min is None and c.max is None):
            raise CadConfigError(f"{where}[{i}] needs 'metric' and 'min' and/or 'max', got {item!r}")
        out.append(c)
    return out


def _parse_slots(raw: Any) -> Dict[str, SlotSpec]:
    slots = {}
    for name, spec in _dict(raw, "cad.explore.slots").items():
        spec = {"category": spec} if isinstance(spec, str) else _dict(spec, f"cad.explore.slots.{name}")
        qty = spec.get("qty", 1)
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
            raise CadConfigError(f"cad.explore.slots.{name}.qty must be a whole number ≥ 0, got {qty!r}")
        unknown = set(spec) - {"category", "qty", "required", "group", "label", "choices", "where"}
        if unknown:
            raise CadConfigError(f"cad.explore.slots.{name}: unknown keys {sorted(unknown)}")
        choices = spec.get("choices")
        if choices is not None and (not isinstance(choices, list) or not all(isinstance(c, str) for c in choices)):
            raise CadConfigError(f"cad.explore.slots.{name}.choices must be a list of catalogue ids")
        slots[str(name)] = SlotSpec(name=str(name), category=str(spec["category"]) if spec.get("category") else None,
                                    qty=qty, required=bool(spec.get("required", False)),
                                    group=str(spec.get("group") or ""), label=str(spec.get("label") or ""),
                                    choices=list(choices) if choices is not None else None,
                                    where=_dict(spec.get("where"), f"cad.explore.slots.{name}.where"))
    return slots


def explore_config(root: Path, raw: Optional[Dict[str, Any]], default_title: str = "") -> ExploreConfig:
    """Parse and validate the ``explore:`` mapping. Raises ``CadConfigError`` for anything malformed."""
    raw = _dict(raw, "cad.explore")
    root = Path(root).resolve()
    currency = str(raw.get("currency") or "usd").lower()
    if not CURRENCY_RE.match(currency):
        raise CadConfigError(f"cad.explore.currency must be a three-letter code such as usd or eur, got {currency!r}")
    age = raw.get("max_price_age_days", 90)
    if age is not None and (isinstance(age, bool) or not isinstance(age, int) or age < 0):
        raise CadConfigError(f"cad.explore.max_price_age_days must be a whole number of days or null, got {age!r}")
    metrics = {str(k): _dict(v, f"cad.explore.metrics.{k}") for k, v in _dict(raw.get("metrics"), "cad.explore.metrics").items()}
    cfg = ExploreConfig(
        root=root,
        title=str(raw.get("title") or default_title or root.name),
        currency=currency,
        catalogue=[str(p) for p in _list(raw.get("catalogue"), "cad.explore.catalogue")],
        categories=[str(c) for c in _list(raw.get("categories"), "cad.explore.categories")],
        max_price_age_days=age,
        slots=_parse_slots(raw.get("slots")),
        designs=[str(p) for p in _list(raw.get("designs", ["designs/*.json"]), "cad.explore.designs")],
        evaluator=parse_evaluator(raw.get("evaluator")),
        objectives=parse_objectives(raw.get("objectives")),
        constraints=parse_constraints(raw.get("constraints")),
        metrics=metrics,
        card_metrics=[str(m) for m in _list(raw.get("card_metrics"), "cad.explore.card_metrics")],
        out=root / str(raw.get("out") or "exports/explore"),
        search=_dict(raw.get("search"), "cad.explore.search"),
        unknown_keys=sorted(set(raw) - _KEYS),
    )
    if not cfg.objectives:
        cfg.objectives = [Objective(cfg.cost_metric), Objective("mass_kg")]
    if cfg.categories:
        for slot in cfg.slots.values():
            if slot.category and slot.category not in cfg.categories:
                raise CadConfigError(f"cad.explore.slots.{slot.name}.category {slot.category!r} is not in categories")
    return cfg
