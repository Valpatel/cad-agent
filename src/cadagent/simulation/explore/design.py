"""Designs: one catalogue part per slot, plus free-form parameters for the project's evaluator.

A design file (JSON or YAML)::

    {
      "name": "Long range",
      "extends": "standard.json",                    # optional: start from another design, then override
      "parts": {
        "drive_motor": "hub-motor-90",               # a catalogue id; the quantity comes from the slot (default 1)
        "battery": {"part": "pack-6s-5ah", "qty": 2},
        "frame": {"custom": {"name": "Printed frame", "category": "frame", "price_usd": 18, "mass_g": 900,
                             "price_checked": "2026-10-20", "confidence": "estimate"}},   # a part not in the catalogue
        "camera": null                               # empty
      },
      "params": {"wheel_diameter_mm": 160},
      "notes": "why this variant exists"
    }

``extends`` is resolved relative to the file: mappings merge key by key (so ``{"battery": {"qty": 3}}`` changes only
the quantity, also when the parent wrote the slot as a bare id), anything else replaces, and ``null`` empties a slot.
In a slot, ``part`` and ``custom`` replace each other. ``name`` is not inherited; it defaults to the file name. One part
per slot: use more slots for more parts.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from cadagent.simulation.explore.catalogue import (Catalogue, Issue, check_item, display_name, in_stock, is_estimate,
                                                   is_number, mass_of, non_finite, normal_confidence, pack_qty,
                                                   price_of, read_data, source_url)
from cadagent.simulation.explore.config import SlotSpec


class DesignError(ValueError):
    """A design file cannot be read or does not fit the catalogue (unknown part, wrong category, bad quantity)."""


def deep_merge(base: Any, override: Any) -> Any:
    """``override`` on top of ``base``: mappings merge recursively, anything else replaces."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = deep_merge(base.get(k), v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(override)


def merge_slot(base: Any, override: Any) -> Any:
    """One slot of a design that ``extends`` another: a mapping override merges into the parent's slot, read as
    ``{"part": id}`` when the parent gave a bare id; naming ``part`` drops an inherited ``custom`` and the other way
    round (the quantity stays unless overridden). Anything else replaces."""
    if isinstance(override, dict) and isinstance(base, (str, dict)):
        merged = {"part": base} if isinstance(base, str) else dict(base)
        if "part" in override:
            merged.pop("custom", None)
        if "custom" in override:
            merged.pop("part", None)
        return deep_merge(merged, override)
    return copy.deepcopy(override)


def merge_designs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """``override`` on top of ``base``: ``parts`` slot by slot (``merge_slot``), everything else by ``deep_merge``."""
    out = deep_merge(base, {k: v for k, v in override.items() if k != "parts"})
    parts, extra = base.get("parts"), override.get("parts")
    if isinstance(parts, dict) and isinstance(extra, dict):
        out["parts"] = copy.deepcopy(parts)
        for slot, value in extra.items():
            out["parts"][slot] = merge_slot(parts[slot], value) if slot in parts else copy.deepcopy(value)
    elif "parts" in override:
        out["parts"] = copy.deepcopy(extra)
    return out


def load_design(path: Path, _chain: Tuple[Path, ...] = ()) -> Dict[str, Any]:
    """Read a design file and resolve its ``extends`` chain. The result has no ``extends`` key; ``name`` defaults to
    the file stem."""
    path = Path(path).resolve()
    if path in _chain:
        raise DesignError("extends loop: " + " -> ".join(p.name for p in _chain + (path,)))
    try:
        data = read_data(path)
    except (OSError, ValueError) as exc:
        raise DesignError(f"{path.name}: unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise DesignError(f"{path.name}: a design must be a mapping")
    data = dict(data)
    parent = data.pop("extends", None)
    if parent:
        base = load_design(path.parent / str(parent), _chain + (path,))
        base.pop("name", None)
        data = merge_designs(base, data)
    data.setdefault("name", path.stem)
    for key in ("parts", "params"):
        if data.get(key) is not None and not isinstance(data[key], dict):
            raise DesignError(f"{path.name}: '{key}' must be a mapping")
    return data


def get_path(data: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_path(data: Dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    node = data
    for part in keys[:-1]:
        if not isinstance(node.get(part), dict):
            node[part] = {}
        node = node[part]
    node[keys[-1]] = value


# ----------------------------------------------------------------------------- what fits a slot

def fits(item: Dict[str, Any], spec: Optional[SlotSpec]) -> Optional[str]:
    """None when a catalogue part may go in the slot, else why not: its category, the slot's ``choices`` and every
    ``where`` condition (a list means one of; a missing field counts as null)."""
    if spec is None:
        return None
    if spec.category and item.get("category") != spec.category:
        return f"takes category {spec.category!r}; {item.get('id')} is {item.get('category')!r}"
    if spec.choices is not None and item.get("id") not in spec.choices:
        return f"takes only {', '.join(spec.choices)}; not {item.get('id')}"
    for path, want in spec.where.items():
        have = get_path(item, str(path))
        if not (have in want if isinstance(want, list) else have == want):
            return f"needs {path} = {want!r}; {item.get('id')} has {have!r}"
    return None


def candidates(catalogue: Catalogue, spec: Optional[SlotSpec], category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Catalogue parts that fit a slot (preferred first, then by price): the slot's category, else ``category``;
    with only ``choices`` configured, those parts."""
    cat = spec.category if spec and spec.category else category
    if cat:
        pool = catalogue.in_category(cat)
    elif spec and spec.choices is not None:
        pool = [catalogue[i] for i in spec.choices if i in catalogue]
    else:
        return []
    return [it for it in pool if fits(it, spec) is None]


def check_slots(slots: Dict[str, SlotSpec], catalogue: Catalogue) -> List[Issue]:
    """Slot ``choices`` that are not in the catalogue (errors), and required or narrowed slots (``choices``, ``where``)
    that no catalogue part fits (warnings). A slot left for custom parts has no catalogue parts, and that is fine."""
    issues = []
    for spec in slots.values():
        missing = [c for c in spec.choices or [] if c not in catalogue]
        if missing:
            issues.append(Issue("error", f"slot {spec.name}", f"choices not in the catalogue: {', '.join(missing)}"))
        narrowed = spec.choices is not None or bool(spec.where)
        if (narrowed or spec.required) and not candidates(catalogue, spec):
            issues.append(Issue("warn", f"slot {spec.name}", "no catalogue part fits it"))
    return issues


# ----------------------------------------------------------------------------- resolving against a catalogue

@dataclass
class Pick:
    slot: str
    item: Dict[str, Any]
    qty: int
    custom: bool = False


@dataclass
class Candidate:
    """A design resolved against a catalogue: what the project's evaluator receives."""
    id: str
    name: str
    design: Dict[str, Any]
    picks: Dict[str, Pick]
    catalogue: Catalogue
    file: Optional[str] = None          # the design file, relative to the project root (for display)
    path: Optional[Path] = None         # its absolute path (a command evaluator's {design})
    bom: Dict[str, Any] = field(default_factory=dict)

    @property
    def params(self) -> Dict[str, Any]:
        return self.design.get("params") or {}

    def param(self, dotted: str, default: Any = None) -> Any:
        return get_path(self.params, dotted, default)

    def part(self, slot: str) -> Optional[Dict[str, Any]]:
        pick = self.picks.get(slot)
        return pick.item if pick else None

    def qty(self, slot: str) -> int:
        pick = self.picks.get(slot)
        return pick.qty if pick else 0

    def spec(self, slot: str, key: str, default: Any = None) -> Any:
        """``specs.<key>`` of the part in ``slot`` (``mass_g`` and ``price_<currency>`` are read off the item too)."""
        item = self.part(slot)
        if item is None:
            return default
        specs = item.get("specs") if isinstance(item.get("specs"), dict) else {}
        value = specs.get(key)
        if value is None and key in ("mass_g", self.catalogue.price_key):
            value = mass_of(item) if key == "mass_g" else price_of(item, self.catalogue.currency)
        return default if value is None else value

    def request(self) -> Dict[str, Any]:
        """The JSON a command evaluator gets on stdin."""
        return {"id": self.id, "name": self.name, "file": self.file, "design": self.design, "params": self.params,
                "currency": self.catalogue.currency,
                "parts": {s: {"item": p.item, "qty": p.qty, "custom": p.custom} for s, p in self.picks.items()},
                "bom": self.bom}


def _pick(slot: str, value: Any, spec: Optional[SlotSpec], catalogue: Catalogue) -> Tuple[Optional[Pick], List[str], List[Dict[str, str]]]:
    """One slot -> (pick or None, errors, checks)."""
    errors: List[str] = []
    checks: List[Dict[str, str]] = []
    default_qty = spec.qty if spec else 1
    if value is None:
        return None, errors, checks
    if isinstance(value, str):
        ref, qty, custom = value, default_qty, None
    elif isinstance(value, dict):
        unknown = set(value) - {"part", "custom", "qty"}
        if unknown:
            errors.append(f"slot {slot}: unknown keys {sorted(unknown)} (use part, custom and qty)")
        ref, custom, qty = value.get("part"), value.get("custom"), value.get("qty", default_qty)
        if bool(ref) == (custom is not None):
            errors.append(f"slot {slot}: give either 'part' (a catalogue id) or 'custom' (an inline part)")
            return None, errors, checks
    else:
        errors.append(f"slot {slot}: expected a catalogue id, a mapping or null, got {value!r}")
        return None, errors, checks
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
        errors.append(f"slot {slot}: qty must be a whole number ≥ 0, got {qty!r}")
        return None, errors, checks
    if custom is not None:
        if not isinstance(custom, dict):
            errors.append(f"slot {slot}: custom must be a mapping (a catalogue item)")
            return None, errors, checks
        item = {"id": f"custom-{slot}", **custom}
        # only the errors: a missing price or mass is reported per BOM line, and a custom part has no catalogue source
        errors += [f"{i.where}: {i.text}" for i in check_item(item, f"slot {slot} (custom)", catalogue.currency, None, None)
                   if i.level == "error"]
        if errors:
            return None, errors, checks
    else:
        item = catalogue.get(str(ref))
        if item is None:
            empty = " (the catalogue is empty: configure cad.explore.catalogue)" if not len(catalogue) else ""
            errors.append(f"slot {slot}: unknown part id {ref!r}{empty}")
            return None, errors, checks
        bad = [f"{path} = {value}" for path, value in non_finite(item)]
        if bad:
            errors.append(f"slot {slot}: part {ref} has numbers that are not finite ({', '.join(bad)}); "
                          "cad-agent catalogue reports them")
            return None, errors, checks
        item = copy.deepcopy(item)              # the evaluator may change its copy; the catalogue stays as it is
    if custom is None:
        why = fits(item, spec)
    elif spec and spec.category and item.get("category") != spec.category:     # a custom part: only its category
        why = f"takes category {spec.category!r}; {item['id']} is {item.get('category')!r}"
    else:
        why = None
    if why:
        errors.append(f"slot {slot} {why}")
        return None, errors, checks
    if qty == 0:
        return None, errors, checks
    return Pick(slot, item, qty, custom is not None), errors, checks


def resolve(design: Dict[str, Any], catalogue: Catalogue, slots: Optional[Dict[str, SlotSpec]] = None,
            design_id: str = "", file: Optional[str] = None, path: Optional[Path] = None,
            ) -> Tuple[Optional[Candidate], List[str], List[Dict[str, str]]]:
    """Resolve every slot of a loaded design. Returns ``(candidate, errors, checks)``; the candidate is None when
    there are errors (unknown part, wrong category, bad quantity, empty required slot)."""
    slots = slots or {}
    parts = design.get("parts") or {}
    picks: Dict[str, Pick] = {}
    errors: List[str] = []
    checks: List[Dict[str, str]] = []
    for slot, value in parts.items():
        pick, errs, chks = _pick(str(slot), value, slots.get(str(slot)), catalogue)
        errors += errs
        checks += chks
        if pick:
            picks[str(slot)] = pick
        if slots and str(slot) not in slots:
            checks.append({"id": f"slot-{slot}", "level": "warn", "text": f"slot {slot} is not one of the configured slots"})
    for spec in slots.values():
        if spec.required and spec.name not in picks:
            errors.append(f"slot {spec.name} is required but empty")
    for path, value in non_finite({k: v for k, v in design.items() if k != "parts"}):
        errors.append(f"design: {path} is {value}, not a finite number")
    if errors:
        return None, errors, checks
    name = str(design.get("name") or design_id or "design")
    return Candidate(design_id or name, name, design, picks, catalogue, file, path), errors, checks


# ----------------------------------------------------------------------------- bill of materials

def _line(slot: str, item: Dict[str, Any], qty: int, currency: str, group: str, custom: bool) -> Dict[str, Any]:
    unit, k, mass = price_of(item, currency), pack_qty(item), mass_of(item)
    packs = math.ceil(qty / k) if isinstance(qty, int) else qty / k     # whole packs of pieces; fractions of a bulk unit
    return {
        "slot": slot, "id": item.get("id"), "name": display_name(item), "category": item.get("category"),
        "qty": qty, "pack_qty": k, "packs": packs, "unit_price": unit,
        "line_price": round(packs * unit, 2) if unit is not None else None,
        "mass_g": mass, "line_mass_g": round(qty * mass, 3) if mass is not None else None,
        "price_estimate": is_estimate(item, f"price_{currency}"), "mass_estimate": is_estimate(item, "mass_g"),
        "confidence": normal_confidence(item.get("confidence")), "price_checked": item.get("price_checked"),
        "source": source_url(item), "in_stock": in_stock(item), "custom": custom, "group": group,
    }


def extra_line(raw: Dict[str, Any], currency: str) -> Dict[str, Any]:
    """A BOM line the evaluator adds (printed parts, an allowance): ``{name, qty, price_<cur>, mass_g, estimate, group}``;
    price and mass are per piece."""
    est = bool(raw.get("estimate"))
    item = {"id": raw.get("id") or "", "name": str(raw.get("name") or "unnamed"), "category": raw.get("category"),
            f"price_{currency}": raw.get(f"price_{currency}"), "mass_g": raw.get("mass_g"),
            "confidence": "estimate" if est else raw.get("confidence"), "sources": raw.get("sources")}
    qty = raw.get("qty", 1)
    qty = qty if is_number(qty) and qty >= 0 else 1
    line = _line(str(raw.get("slot") or ""), item, qty, currency, str(raw.get("group") or ""), custom=True)
    line["from_evaluator"] = True
    return line


def bom(candidate: Candidate, slots: Optional[Dict[str, SlotSpec]] = None,
        extra_lines: Iterable[Dict[str, Any]] = ()) -> Dict[str, Any]:
    """Lines for every filled slot (plus ``extra_lines``) and the totals. A line without a price or mass is left out of
    that total, and the total says it is incomplete; any estimated number makes the total an estimate."""
    slots = slots or {}
    currency = candidate.catalogue.currency
    lines = [_line(s, p.item, p.qty, currency, slots[s].group if s in slots else "", p.custom)
             for s, p in candidate.picks.items()]
    lines += [extra_line(x, currency) for x in extra_lines]
    priced = [l for l in lines if l["line_price"] is not None]
    weighed = [l for l in lines if l["line_mass_g"] is not None]
    groups: Dict[str, float] = {}
    for l in priced:
        groups[l["group"]] = round(groups.get(l["group"], 0.0) + l["line_price"], 2)
    return {
        "currency": currency,
        "lines": lines,
        "totals": {
            "cost": round(sum(l["line_price"] for l in priced), 2),
            "cost_complete": len(priced) == len(lines),
            "cost_estimate": any(l["price_estimate"] for l in priced),
            "mass_kg": round(sum(l["line_mass_g"] for l in weighed) / 1000.0, 4),
            "mass_complete": len(weighed) == len(lines),
            "mass_estimate": any(l["mass_estimate"] for l in weighed),
            "groups": groups,
        },
    }


def bom_checks(b: Dict[str, Any]) -> List[Dict[str, str]]:
    """Warnings for lines that leave a total incomplete, and for parts nobody has in stock."""
    out = []
    for l in b["lines"]:
        key = l["slot"] or l["id"] or l["name"]
        if l["line_price"] is None:
            out.append({"id": f"price-{key}", "level": "warn", "text": f"{l['name']} has no price; the cost leaves it out."})
        if l["line_mass_g"] is None:
            out.append({"id": f"mass-{key}", "level": "warn", "text": f"{l['name']} has no mass; the mass leaves it out."})
        if l["in_stock"] is False:
            out.append({"id": f"stock-{key}", "level": "warn", "text": f"No seller lists {l['name']} in stock."})
    return out


def bom_metrics(b: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The BOM's two metrics. ``missing`` lists the lines a total leaves out (``slot|part|qty``): two totals that leave
    out the same lines differ by exactly what they show."""
    t, cur = b["totals"], b["currency"]

    def left_out(key: str) -> List[str]:
        return sorted(f"{l['slot']}|{l['id'] or l['name']}|{l['qty']}" for l in b["lines"] if l[key] is None)
    return {
        f"cost_{cur}": {"value": t["cost"], "unit": cur.upper(), "label": "cost", "estimate": t["cost_estimate"],
                        "incomplete": not t["cost_complete"], "source": "bom", "missing": left_out("line_price")},
        "mass_kg": {"value": t["mass_kg"], "unit": "kg", "label": "mass", "estimate": t["mass_estimate"],
                    "incomplete": not t["mass_complete"], "source": "bom", "missing": left_out("line_mass_g")},
    }
