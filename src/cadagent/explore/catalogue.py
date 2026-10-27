"""Part catalogues: lists of parts with specs, prices, sources and confidence flags.

A catalogue file is JSON or YAML in one of three layouts:

* a list of items, each with an ``id``;
* ``{"items": [...]}``, optionally with ``"defaults": {...}`` merged under every item (a ``category`` for the whole
  file, say);
* ``{"items": {"<id>": {...}}}``, keyed by id (the layout ``cadagent.mcmaster`` writes).

One item::

    {
      "id": "hub-motor-90",                 # unique across the catalogue: letters, digits, . _ - +
      "category": "drive_motor",            # what kind of part; a design slot takes one category
      "name": "90 mm hub motor",            # or "vendor" + "model", or "description"; falls back to the id
      "price_usd": 89.0,                    # one pack (pack_qty pieces, default 1), before shipping and tax
      "price_checked": "2026-10-20",        # required with a price; older than max_price_age_days is a warning
      "pack_qty": 1,
      "mass_g": 410,                        # one piece; "specs.mass_g" is read too
      "specs": {"peak_torque_nm": 2.0, "voltage_range_v": [12, 24]},   # units in the key names
      "confidence": "datasheet",            # measured | datasheet | product_page | seller_listing | estimate
      "estimates": ["specs.peak_torque_nm"],# fields that are estimates even when the rest is not
      "sources": ["https://..."],
      "buy": [{"seller": "...", "url": "https://...", "in_stock": true}],
      "preferred": true,                    # the default choice for its category
      "notes": "anything that matters"
    }

Unknown values are ``null``, never guessed. Prices are read from ``price_<currency>`` for the project's currency, so a
number is never in an unstated currency. Everything else on an item is kept and passed to the project's evaluator.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

CONFIDENCE = ("measured", "datasheet", "product_page", "seller_listing", "estimate")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
CURRENCY_PRICE_RE = re.compile(r"^price_[a-z]{3}$")


@dataclass
class Issue:
    level: str    # "error" or "warn"
    where: str
    text: str

    def __str__(self) -> str:
        return f"{'ERROR' if self.level == 'error' else 'warn '} {self.where}: {self.text}"


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def normal_confidence(value: Any) -> Optional[str]:
    """``"product page"`` and ``"Product-Page"`` both mean ``product_page``; None when unset."""
    if value in (None, ""):
        return None
    return re.sub(r"[\s-]+", "_", str(value).strip().lower())


class Catalogue:
    """Items by id, in the project's currency."""

    def __init__(self, items: Optional[Dict[str, Dict[str, Any]]] = None, currency: str = "usd",
                 files: Optional[Dict[str, str]] = None):
        self.items: Dict[str, Dict[str, Any]] = dict(items or {})
        self.currency = currency
        self.files: Dict[str, str] = dict(files or {})     # id -> the file it came from

    def __contains__(self, item_id: object) -> bool:
        return item_id in self.items

    def __getitem__(self, item_id: str) -> Dict[str, Any]:
        return self.items[item_id]

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        return iter(self.items.values())

    def __len__(self) -> int:
        return len(self.items)

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self.items.get(item_id)

    @property
    def price_key(self) -> str:
        return f"price_{self.currency}"

    def categories(self) -> List[str]:
        return sorted({str(it.get("category")) for it in self if it.get("category")})

    def in_category(self, category: str) -> List[Dict[str, Any]]:
        """Items of a category: preferred first, then by price (unpriced last), then id."""
        found = [it for it in self if it.get("category") == category]
        return sorted(found, key=lambda it: (it.get("preferred") is not True,
                                             self.price(it) if self.price(it) is not None else float("inf"), it["id"]))

    def price(self, item: Dict[str, Any]) -> Optional[float]:
        return price_of(item, self.currency)


# ----------------------------------------------------------------------------- reading values off an item

def display_name(item: Dict[str, Any]) -> str:
    if item.get("name"):
        return str(item["name"])
    vm = " ".join(str(item[k]) for k in ("vendor", "model") if item.get(k))
    return vm or str(item.get("description") or item.get("id") or "?")


def price_of(item: Dict[str, Any], currency: str = "usd") -> Optional[float]:
    v = item.get(f"price_{currency}")
    return float(v) if is_number(v) else None


def mass_of(item: Dict[str, Any]) -> Optional[float]:
    """Grams per piece: ``mass_g``, else ``specs.mass_g``."""
    v = item.get("mass_g")
    if v is None:
        v = (item.get("specs") or {}).get("mass_g") if isinstance(item.get("specs"), dict) else None
    return float(v) if is_number(v) else None


def pack_qty(item: Dict[str, Any]) -> int:
    n = item.get("pack_qty")
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else 1


def is_estimate(item: Dict[str, Any], field: str) -> bool:
    """True when ``field`` (``mass_g``, ``price_usd``, ``specs.<key>``) is an estimate: the whole item is, or the field
    is listed in ``estimates``. ``mass_g`` and ``specs.mass_g`` are the same field."""
    if normal_confidence(item.get("confidence")) == "estimate":
        return True
    listed = set(item.get("estimates") or []) if isinstance(item.get("estimates"), list) else set()
    if field in ("mass_g", "specs.mass_g"):
        return bool(listed & {"mass_g", "specs.mass_g"})
    return field in listed


def in_stock(item: Dict[str, Any]) -> Optional[bool]:
    """False when every seller listed says out of stock, True when any says in stock, None when nobody says."""
    flags = [b.get("in_stock") for b in item.get("buy") or [] if isinstance(b, dict)]
    if any(f is True for f in flags):
        return True
    if flags and all(f is False for f in flags):
        return False
    return None


def source_url(item: Dict[str, Any]) -> Optional[str]:
    for b in item.get("buy") or []:
        if isinstance(b, dict) and b.get("url"):
            return str(b["url"])
    for s in item.get("sources") or []:
        if isinstance(s, str) and s:
            return s
    return str(item["url"]) if item.get("url") else None


# ----------------------------------------------------------------------------- loading

def read_data(path: Path) -> Any:
    """Parse a JSON or YAML file; a parse error is raised as ``ValueError``."""
    text = Path(path).read_text()
    if Path(path).suffix in (".yaml", ".yml"):
        import yaml
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(str(exc)) from exc
    return json.loads(text)


def items_in(data: Any, where: str) -> Tuple[List[Dict[str, Any]], List[Issue]]:
    """The items of one parsed catalogue file, with ``defaults`` applied, and any layout problems."""
    issues: List[Issue] = []
    defaults: Dict[str, Any] = {}
    if isinstance(data, dict) and "items" in data:
        if not isinstance(data.get("defaults", {}), dict):
            issues.append(Issue("error", where, "'defaults' must be a mapping"))
        else:
            defaults = dict(data.get("defaults") or {})
        data = data["items"]
        if isinstance(data, dict):
            keyed = []
            for key, item in data.items():
                if not isinstance(item, dict):
                    issues.append(Issue("error", f"{where} {key}", "an item must be a mapping"))
                    continue
                if item.get("id") not in (None, key):
                    issues.append(Issue("error", f"{where} {key}", f"id {item['id']!r} differs from its key"))
                keyed.append({**item, "id": key})
            data = keyed
    if not isinstance(data, list):
        return [], issues + [Issue("error", where, "must be a list of items, {items: [...]} or {items: {id: item}}")]
    out = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            issues.append(Issue("error", f"{where}[{i}]", "an item must be a mapping"))
            continue
        out.append({**defaults, **item})
    return out, issues


def load_catalogue(files: Iterable[Path], currency: str = "usd", root: Optional[Path] = None) -> Tuple[Catalogue, List[Issue]]:
    """Read every file into one ``Catalogue``. Unreadable files, bad layouts, missing ids and duplicate ids are
    errors; the first item with an id wins."""
    items: Dict[str, Dict[str, Any]] = {}
    origin: Dict[str, str] = {}
    issues: List[Issue] = []
    for path in files:
        path = Path(path)
        name = path.relative_to(root).as_posix() if root and path.is_relative_to(root) else str(path)
        try:
            data = read_data(path)
        except (OSError, ValueError) as exc:
            issues.append(Issue("error", name, f"unreadable: {exc}"))
            continue
        found, problems = items_in(data, name)
        issues += problems
        for i, item in enumerate(found):
            item_id = item.get("id")
            where = f"{name}[{i}]" + (f" {item_id}" if item_id else "")
            if not isinstance(item_id, str) or not item_id:
                issues.append(Issue("error", where, "missing id"))
                continue
            if item_id in items:
                issues.append(Issue("error", where, f"duplicate id (also in {origin[item_id]})"))
                continue
            items[item_id] = item
            origin[item_id] = name
    return Catalogue(items, currency, origin), issues


# ----------------------------------------------------------------------------- checking

def check_item(item: Dict[str, Any], where: str, currency: str = "usd", categories: Optional[Iterable[str]] = None,
               max_price_age_days: Optional[int] = 90, today: Optional[date] = None) -> List[Issue]:
    """Problems with one item. Errors make the data wrong; warnings make it incomplete or unverifiable."""
    issues: List[Issue] = []
    err = lambda text: issues.append(Issue("error", where, text))    # noqa: E731
    warn = lambda text: issues.append(Issue("warn", where, text))    # noqa: E731
    today = today or date.today()
    item_id = item.get("id")
    if isinstance(item_id, str) and item_id and not ID_RE.match(item_id):
        err(f"id {item_id!r} may only use letters, digits and . _ - +")
    category = item.get("category")
    if not isinstance(category, str) or not category:
        err("missing category")
    elif categories and category not in set(categories):
        err(f"unknown category {category!r}; known: {', '.join(sorted(set(categories)))}")
    key = f"price_{currency}"
    price = item.get(key)
    if price is not None and (not is_number(price) or price < 0):
        err(f"{key} must be a number ≥ 0 or null, got {price!r}")
    if price is None:
        others = sorted(k for k in item if CURRENCY_PRICE_RE.match(k) and k != key and item[k] is not None)
        if others:
            warn(f"no {key} (has {', '.join(others)}): convert it and note the rate in price_note")
        else:
            warn(f"no {key}: it is left out of cost totals")
    checked = item.get("price_checked")
    if price is not None and not checked:
        err("a price needs price_checked (YYYY-MM-DD)")
    if checked:
        try:
            age = (today - date.fromisoformat(str(checked))).days
        except ValueError:
            err(f"price_checked {checked!r} is not YYYY-MM-DD")
        else:
            if age < 0:
                err(f"price_checked {checked} is in the future")
            elif max_price_age_days is not None and age > max_price_age_days:
                warn(f"price is {age} days old (checked {checked})")
    if "pack_qty" in item and pack_qty(item) != item["pack_qty"]:
        err(f"pack_qty must be a whole number ≥ 1, got {item['pack_qty']!r}")
    specs = item.get("specs")
    if specs is not None and not isinstance(specs, dict):
        err("specs must be a mapping")
        specs = {}
    top, nested = item.get("mass_g"), (specs or {}).get("mass_g")
    for label, v in (("mass_g", top), ("specs.mass_g", nested)):
        if v is not None and (not is_number(v) or v < 0):
            err(f"{label} must be a number ≥ 0 or null, got {v!r}")
    if is_number(top) and is_number(nested) and top != nested:
        err(f"mass_g {top} and specs.mass_g {nested} disagree")
    if mass_of(item) is None:
        warn("no mass_g: it is left out of mass totals")
    conf = item.get("confidence")
    if conf is not None and normal_confidence(conf) not in CONFIDENCE:
        err(f"confidence {conf!r} is not one of {', '.join(CONFIDENCE)}")
    estimates = item.get("estimates")
    if estimates is not None and (not isinstance(estimates, list) or not all(isinstance(e, str) for e in estimates)):
        err("estimates must be a list of field names, such as [\"mass_g\", \"specs.peak_torque_nm\"]")
    if "preferred" in item and not isinstance(item["preferred"], bool):
        err("preferred must be true or false")
    sources, buy = item.get("sources"), item.get("buy")
    if sources is not None and (not isinstance(sources, list) or not all(isinstance(s, str) for s in sources)):
        err("sources must be a list of URLs or references")
    if buy is not None and (not isinstance(buy, list) or not all(isinstance(b, dict) for b in buy)):
        err("buy must be a list of {seller, url, in_stock}")
    if not sources and not buy and not item.get("url"):
        warn("no sources or buy links: the numbers cannot be checked")
    return issues


def check_catalogue(catalogue: Catalogue, categories: Optional[Iterable[str]] = None,
                    max_price_age_days: Optional[int] = 90, today: Optional[date] = None) -> List[Issue]:
    issues: List[Issue] = []
    for item in catalogue:
        where = f"{catalogue.files.get(item['id'], '?')} {item['id']}"
        issues += check_item(item, where, catalogue.currency, categories, max_price_age_days, today)
    return issues


def load_configured(cfg: Any) -> Tuple[Catalogue, List[Issue]]:
    """The project's catalogue (``explore.catalogue`` globs, in its currency) and the problems reading it: unreadable
    files, bad layouts, duplicate ids, and patterns that match no file."""
    files, unmatched = cfg.catalogue_files()
    catalogue, issues = load_catalogue(files, cfg.currency, cfg.root)
    issues = [Issue("error", f"catalogue pattern {pat!r}", "matches no JSON or YAML file") for pat in unmatched] + issues
    return catalogue, issues


def counts(issues: Iterable[Issue]) -> Dict[str, int]:
    out = {"error": 0, "warn": 0}
    for issue in issues:
        out[issue.level] = out.get(issue.level, 0) + 1
    return out
