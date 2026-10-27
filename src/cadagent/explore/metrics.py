"""Metric values, their display names and units, and formatting.

A metric is ``{"value": number | bool | str | null, "unit"?, "label"?, "digits"?, "estimate"?, "incomplete"?, "level"?,
"note"?}``. ``estimate`` marks a rule-of-thumb or estimated input; ``incomplete`` marks a total that leaves something
out (a part without a price), so the true value is at least what is shown. Units come from the key name when not
given (``runtime_min`` is in minutes), as the rest of cad-agent names its keys.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional, Tuple

from cadagent.explore.catalogue import is_number

SUFFIX_UNITS = (
    ("_kmh", "km/h"), ("_mps", "m/s"), ("_rpm", "rpm"), ("_nm", "N·m"), ("_mpa", "MPa"), ("_pct", "%"),
    ("_deg", "°"), ("_kg", "kg"), ("_wh", "Wh"), ("_mm", "mm"), ("_min", "min"), ("_hz", "Hz"), ("_g", "g"),
    ("_m", "m"), ("_h", "h"), ("_s", "s"), ("_w", "W"), ("_v", "V"), ("_a", "A"), ("_n", "N"), ("_c", "°C"),
    ("_x", "×"),
)
KNOWN = {"value", "unit", "label", "digits", "estimate", "incomplete", "level", "note", "source"}


def unit_from_name(name: str) -> Tuple[str, str]:
    """``("runtime", "min")`` for ``runtime_min``; currencies: ``cost_usd`` -> ``("cost", "USD")``."""
    if name.startswith("cost_") and len(name) == 8:
        return "cost", name[5:].upper()
    for suffix, unit in SUFFIX_UNITS:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)].replace("_", " "), unit
    return name.replace("_", " "), ""


def normalise(name: str, raw: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """One metric from an evaluator -> ``(metric, problem)``. A bare number is ``{"value": number}``; a value that is
    not finite becomes null with a problem to report."""
    metric = dict(raw) if isinstance(raw, dict) else {"value": raw}
    if isinstance(raw, dict) and "value" not in raw:
        return {"value": None}, f"metric {name} has no 'value'"
    value = metric.get("value")
    if not isinstance(value, (bool, int, float, str)) and callable(getattr(value, "item", None)):
        try:                                     # a NumPy (or similar) scalar: its plain Python value
            value = metric["value"] = value.item()
        except (TypeError, ValueError):
            pass
    problem = None
    if value is not None and not isinstance(value, (bool, int, float, str)):
        metric["value"], problem = None, f"metric {name} must be a number, true/false, text or null, got {type(value).__name__}"
    elif isinstance(value, float) and not math.isfinite(value):
        metric["value"], problem = None, f"metric {name} is {value}, not a finite number"
    for flag in ("estimate", "incomplete"):
        if flag in metric:
            metric[flag] = bool(metric[flag])
    return metric, problem


def info(name: str, metric: Optional[Dict[str, Any]] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Display info for a metric: label, unit, digits, in order of preference the project's ``metrics:`` config, the
    metric itself, then the key name."""
    label, unit = unit_from_name(name)
    out: Dict[str, Any] = {"label": label, "unit": unit, "digits": None}
    for src in (metric or {}, overrides or {}):
        for key in ("label", "unit", "digits"):
            if src.get(key) is not None:
                out[key] = src[key]
    return out


def column_digits(values: Iterable[Optional[float]]) -> Optional[int]:
    """Decimals for a column of numbers: none for whole numbers, else by the largest magnitude (≥100: 0, ≥10: 1,
    ≥1: 2, below: 3). None when there are no numbers."""
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    if all(float(v).is_integer() for v in nums):
        return 0
    top = max(abs(v) for v in nums)
    return 0 if top >= 100 else 1 if top >= 10 else 2 if top >= 1 else 3


def format_value(value: Any, unit: str = "", digits: Optional[int] = None, estimate: bool = False,
                 incomplete: bool = False, with_unit: bool = True) -> str:
    """``"≥ 1,240 USD"``, ``"6.2 kg est."``, ``"yes"``, ``"—"``."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        text = "yes" if value else "no"
    elif is_number(value):
        if digits is None:
            mag = abs(value)
            digits = 0 if mag >= 100 or float(value).is_integer() else 1 if mag >= 10 else 2
        text = f"{value:,.{int(digits)}f}"
    else:
        text = str(value)
    if with_unit and unit and not isinstance(value, bool):
        text = f"{text}{unit}" if unit in ("°", "%", "×") else f"{text} {unit}"
    if incomplete:
        text = f"≥ {text}"
    if estimate:
        text += " est."
    return text
