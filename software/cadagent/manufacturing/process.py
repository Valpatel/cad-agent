"""Manufacturing-process profiles: the cited design rules of docs/research/process-profiles.yaml as typed values (#99).

    from cadagent.manufacturing import process
    fdm = process.profile("fdm")
    fdm.rule("fdm-wall-min-hubs").limit()            # Limit(min=0.8 mm, source hubs-fdm-design, verified)
    fdm.limits("wall", nozzle=0.4)                   # every source's minimum wall, side by side
    fdm.tolerance(50)                                # each source's +/- band on a 50 mm dimension
    fdm.material("petg-bambu-basic").factors         # across-the-layers / in-plane: modulus, strength, strain
    sheet = process.profile("sheet-metal")
    sheet.material("5052").stock(1.6)                # one shop's R, K, minimum flange and relief for 1.6 mm 5052
    sheet.limits(compare="sm-clinch-to-bend", shop="sendcutsend", E=7.0, BA=2.5)   # generic and that shop's rules

Checks and calculators read their numbers here instead of hard-coding one printer's or one shop's: the minimum-feature
check (:mod:`cadagent.manufacturing.dfm`), the sheet-metal bend calculator (:mod:`cadagent.manufacturing.sheet_metal`)
and the fit coupons' allowances (:mod:`cadagent.manufacturing.fit_coupons`).

**Every value carries its rule id and its source id**, and whether it was read in the source (``verified``). A rule
whose ``status`` is ``u`` was not verified: it loads, prints with ``(u)`` after it, and a check lists it as advisory but
never passes or fails a part on it. :meth:`Profile.verified_rule` refuses one, for code that would enforce it.

**Where the data comes from.**

* Rules, formulas and the shop table: ``docs/research/process-profiles.yaml`` at the root of the cad-agent checkout this
  package runs from (an editable install or ``PYTHONPATH=software``), or the file named by ``CADAGENT_PROCESS_PROFILES``, or
  the ``path`` given to :func:`load`. A wheel without the checkout has no data: :func:`load` says so.
* FDM materials: the maker's data sheets that :mod:`cadagent.mechanical.compliant.allowables` holds, one entry per
  filament with every edition read. Their source ids (``bambu-petg-basic-tds`` and so on) are the reference registry's
  (#118), and so are the rules' sources: ``docs/research/references.yaml`` beside the data file holds every one. A data
  file with no registry beside it (a copy elsewhere) still loads, but its ids do not resolve, so
  :attr:`Source.resolved` is False and each factor keeps the sheet's own link as its citation.
* Sheet metal: the shop's table (``shop_tables``) for 5052 aluminium and cold-rolled mild steel, and the generic rules.
  :data:`SHEET_MATERIALS` says which generic K-factor row (soft, medium) a material takes and which rules are for other
  alloys; that grouping is this module's reading of the source's words, stated in each entry. A shop's other tables
  (stainless and galvanised bend rows, cutting and hardware limits) load as :attr:`Profiles.shops` tables.
* Shops: a rule with ``shop: <id>`` is that shop's own (``shops`` in the data file names each one, #283). The queries
  leave shop rules out unless asked for one (``shop="sendcutsend"``, or ``"*"`` for every shop), so the generic rules
  stay supplier-neutral; a project's chosen suppliers (#284) pick the shop.

**Limits.** The rules are published guidance from bureaus, makers and textbooks, not measurements of your printer or
shop. Sources disagree; a profile keeps every one and a check reports the spread. A rule's ``applies`` text (material,
machine, thickness) is shown with it and is not parsed, so a reader must still judge whether it applies. Design rules
make a part likely to be made well; they do not prove fit or strength.
"""
from __future__ import annotations

import ast
import math
import os
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "docs" / "research" / "process-profiles.yaml"
REGISTRY = ROOT / "docs" / "research" / "references.yaml"     # the reference registry (#118): every source id resolves there
ENV = "CADAGENT_PROCESS_PROFILES"
UNVERIFIED = "(u)"


class ProfileDataError(ValueError):
    """The profile data is missing, or a value asked for is not in it."""


# ----------------------------------------------------------------------------- expressions

_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b}
_CMP = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b}
_FUN = {"min": min, "max": max}
_FUN1 = {"sqrt": math.sqrt, "cos": math.cos}          # one argument each (#323: the hole rules)


def evaluate(expr: Any, env: Mapping[str, float]) -> float:
    """A rule's min/max/value as a number. Numbers pass through; a string may use the names in ``env``, numbers,
    + - * / ( ), unary minus, min(), max(), sqrt(), cos() (radians), pi, and one ``a if <comparison> else b`` (not nested, not two). Anything
    else raises ValueError, as does dividing by zero, so a typo in the data file fails the tests instead of being
    skipped and a caller needs to catch only ValueError."""
    if isinstance(expr, bool):
        raise ValueError(f"{expr!r} is not a number")
    if isinstance(expr, (int, float)):
        return float(expr)
    names = dict(env, pi=math.pi)

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise ValueError(f"{expr!r}: unknown name {node.id!r}")
            return float(names[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUN and node.args \
                and not node.keywords:
            return _FUN[node.func.id](ev(a) for a in node.args)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUN1 \
                and len(node.args) == 1 and not node.keywords:
            arg = ev(node.args[0])
            if node.func.id == "sqrt" and arg < 0:
                raise ValueError(f"{expr!r}: sqrt of {arg:g} at {dict(env)}")
            return _FUN1[node.func.id](arg)
        if isinstance(node, ast.IfExp) and isinstance(node.test, ast.Compare) and len(node.test.ops) == 1 \
                and type(node.test.ops[0]) in _CMP:
            test = _CMP[type(node.test.ops[0])](ev(node.test.left), ev(node.test.comparators[0]))
            return ev(node.body) if test else ev(node.orelse)
        raise ValueError(f"{expr!r}: {type(node).__name__} is not allowed in a rule expression")

    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"{expr!r}: {e.msg}") from None
    if sum(isinstance(n, ast.IfExp) for n in ast.walk(tree)) > 1:
        raise ValueError(f"{expr!r}: only one `a if <comparison> else b` is allowed")
    try:
        return ev(tree)
    except ZeroDivisionError:
        raise ValueError(f"{expr!r}: division by zero at {dict(env)}") from None


def names_in(expr: Any) -> Tuple[str, ...]:
    """The variables an expression uses (``"2*T + R"`` -> ``("R", "T")``); none for a number."""
    if isinstance(expr, (int, float)):
        return ()
    return tuple(sorted({n.id for n in ast.walk(ast.parse(str(expr), mode="eval"))
                         if isinstance(n, ast.Name) and n.id not in _FUN and n.id not in _FUN1 and n.id != "pi"}))


# ----------------------------------------------------------------------------- typed values

@dataclass(frozen=True)
class Source:
    """Who a value comes from. ``resolved`` is False for an id this checkout cannot look up (no
    docs/research/references.yaml beside the data file, or an id it lacks); ``url`` is then the citation the value itself
    carries."""
    id: str
    title: str = ""
    org: str = ""
    authors: Tuple[str, ...] = ()
    year: Optional[int] = None
    url: str = ""
    access: str = ""
    resolved: bool = True

    @property
    def credit(self) -> str:
        who = ", ".join(self.authors) if self.authors else self.org
        return f"{who}, {self.title}".strip(", ") if self.title else (who or self.id)


@dataclass(frozen=True)
class Limit:
    """One rule evaluated: ``min`` (at least), ``max`` (at most), both (a range, or with ``window`` an allowed
    window), or ``value`` (a typical or nominal figure), in ``units``; with its rule and source ids and whether it was
    read in the source."""
    rule: str
    quantity: str
    units: str
    source: str
    verified: bool
    applies: str = ""
    min: Optional[float] = None
    max: Optional[float] = None
    value: Optional[float] = None
    window: bool = False
    variant: str = ""
    env: Tuple[Tuple[str, float], ...] = ()

    @property
    def flag(self) -> str:
        return "" if self.verified else UNVERIFIED

    def _num(self, v: float) -> str:
        return f"{v:.4g}"

    @property
    def text(self) -> str:
        """``"at least 0.8 mm"``, ``"0.2-0.3 mm"``, ``"0.25 mm"``, with ``(u)`` after an unverified value."""
        u = "" if self.units in ("ratio", "count") else (" %" if self.units == "percent" else f" {self.units}")
        if self.value is not None:
            s = f"{self._num(self.value)}{u}"
        elif self.min is not None and self.max is not None:
            s = f"{self._num(self.min)}-{self._num(self.max)}{u}"
        elif self.min is not None:
            s = f"at least {self._num(self.min)}{u}"
        else:
            s = f"at most {self._num(self.max)}{u}"
        return f"{s} {self.flag}".strip()

    def cite(self) -> str:
        """``"fdm-wall-min-hubs (hubs-fdm-design)"``, with ``(u)`` for an unverified value."""
        return f"{self.rule} ({self.source}) {self.flag}".strip()

    def as_dict(self) -> Dict[str, Any]:
        out = {k: getattr(self, k) for k in ("rule", "quantity", "units", "source", "verified", "applies")}
        out.update({k: getattr(self, k) for k in ("min", "max", "value") if getattr(self, k) is not None})
        if self.window:
            out["window"] = True
        if self.variant:
            out["variant"] = self.variant
        out["text"] = self.text
        return out


@dataclass(frozen=True)
class Rule:
    """One row of ``rules`` in the data file, its numbers still expressions where the file gives one."""
    id: str
    process: str
    feature: str
    quantity: str
    units: str
    applies: str
    source: str
    status: str
    verified_on: str
    min: Any = None
    max: Any = None
    value: Any = None
    window: bool = False
    compare: str = ""
    variant: str = ""
    datum: str = ""
    note: str = ""
    shop: str = ""           # a shop id of ``shops`` for that shop's own rule; "" for a generic one
    applied_by: Tuple[str, ...] = ()     # the functions or gates that apply it (``cadagent.mechanical.inserts.printed_hole``)
    # when to use it (#323 phase 7b, served by ``cad-agent rules``): each "" where the file does not say, and
    # ``"unstated"`` where no source says (the card flags it)
    when: str = ""           # the conditions it holds under; the card falls back to ``applies``
    not_when: str = ""       # when it does not hold, and what to use instead
    instead: Tuple[str, ...] = ()        # the rule ids or cards to use instead
    strictness: str = ""     # non-negotiable, guideline or unstated
    wiggle: str = ""         # how far it may move, and which way
    cost: str = ""           # what holding it tighter costs
    materials: Tuple[str, ...] = ()      # the material families it is for; () for any
    cards: Tuple[str, ...] = ()          # the rule cards it belongs to besides its feature's

    @property
    def verified(self) -> bool:
        return self.status == "read"

    @property
    def flag(self) -> str:
        return "" if self.verified else UNVERIFIED

    @property
    def variables(self) -> Tuple[str, ...]:
        """The variables its expressions need (``T``, ``R``, ``nozzle``, ...)."""
        return tuple(sorted({n for k in ("min", "max", "value") for n in names_in(getattr(self, k))
                             if getattr(self, k) is not None}))

    def limit(self, **env: float) -> Limit:
        """The rule's numbers at ``env`` (``T=1.5, R=1.5``). A variable it needs and ``env`` lacks raises
        ProfileDataError naming it."""
        missing = [v for v in self.variables if v not in env]
        if missing:
            raise ProfileDataError(f"{self.id}: give {', '.join(missing)} ({self.quantity})")
        used = tuple(sorted((k, float(env[k])) for k in self.variables))
        nums = {k: evaluate(getattr(self, k), env) for k in ("min", "max", "value") if getattr(self, k) is not None}
        return Limit(self.id, self.quantity, self.units, self.source, self.verified, self.applies,
                     window=self.window, variant=self.variant, env=used, **nums)


@dataclass(frozen=True)
class Factor:
    """A ratio from a data sheet, such as strength across the layers over strength in the layer plane."""
    quantity: str
    value: float
    source: str
    citation: str            # the sheet, its edition, page and link
    verified: bool = True
    verified_on: str = ""

    @property
    def flag(self) -> str:
        return "" if self.verified else UNVERIFIED


@dataclass(frozen=True)
class FdmMaterial:
    """A filament: its family (``petg``, ``pla``, ``asa``, ``pa``, ``pa-cf``, ``petg-cf``), and its across-the-layers
    factors (Z over XY) for ``modulus``, ``strength`` and ``strain`` to failure, each the lowest any edition of its data
    sheet gives (the cautious edition, as cadagent.mechanical.compliant.allowables takes it)."""
    key: str
    name: str
    family: str
    source: str
    condition: str
    factors: Mapping[str, Factor]

    def factor(self, quantity: str) -> Factor:
        if quantity not in self.factors:
            raise ProfileDataError(f"{self.key}: no {quantity!r} factor; there are {sorted(self.factors)}")
        return self.factors[quantity]


@dataclass(frozen=True)
class Stock:
    """One shop's tooling for one sheet: inside radius ``R``, ``K``-factor, the shortest flange it bends and the bend
    relief depth, in mm, from the shop's published table."""
    sku: str
    material: str
    T: float
    R: float
    K: float
    min_flange: float
    relief_depth: float
    table: str
    source: str
    verified_on: str
    verified: bool = True

    def cite(self) -> str:
        return f"{self.table} {self.sku} ({self.source})"


@dataclass(frozen=True)
class SheetMaterial:
    """A sheet alloy: which generic K-factor rows it takes (``hardness``: soft, medium or hard, the source's three
    classes), the shop table's rows for it, and the generic rules that are written for other alloys (``excludes``)."""
    key: str
    name: str
    hardness: str
    shop_material: str
    excludes: Tuple[str, ...]
    why: str
    stocks: Tuple[Stock, ...] = ()

    def stock(self, thickness_mm: float, tol_mm: float = 0.02) -> Optional[Stock]:
        """The shop's row for this thickness (within ``tol_mm``), or None when the shop does not stock it."""
        near = [s for s in self.stocks if abs(s.T - thickness_mm) <= tol_mm]
        return min(near, key=lambda s: abs(s.T - thickness_mm)) if near else None


# Which generic rules suit which sheet alloy. The K-factor table (hubs-sheet-metal) gives three classes, "soft metal
# (aluminium)", "medium metal (steel)" and "hard metal (stainless steel)", so 5052 takes the soft rows and mild steel the
# medium ones. Davis's bend-radius rows split soft aluminium and mild steel (minimum radius T) from 6061 and 2024 (4-8 T),
# so 4-8 T is excluded for both.
SHEET_MATERIALS: Dict[str, Dict[str, Any]] = {
    "5052": {"name": "5052 aluminium", "hardness": "soft", "shop_material": "5052 aluminium",
             "excludes": ("sm-bend-radius-min-davis-hard-al",),
             "why": "the K table's 'soft metal (aluminium)'; Davis puts soft aluminium (3003, 5052) with mild steel at "
                    "a minimum radius of T, and 4-8 T is for 6061 and 2024"},
    "mild-steel": {"name": "cold-rolled mild steel", "hardness": "medium", "shop_material": "cold-rolled mild steel",
                   "excludes": ("sm-bend-radius-min-davis-hard-al",),
                   "why": "the K table's 'medium metal (steel)'; Davis's minimum radius for mild steel is T"},
    "g90": {"name": "G90 galvanised steel", "hardness": "medium", "shop_material": "G90 galvanised steel",
            "excludes": ("sm-bend-radius-min-davis-hard-al",),
            "why": "zinc-coated mild steel: the K table's 'medium metal (steel)' and Davis's mild-steel radius T"},
    "304": {"name": "304 stainless steel", "hardness": "hard", "shop_material": "304 stainless steel",
            "excludes": ("sm-bend-radius-min-davis-hard-al", "sm-bend-radius-min-davis-mild"),
            "why": "the K table's 'hard metal (stainless steel)'; Davis's radius rows are for aluminium and mild steel, "
                   "not stainless"},
    "316": {"name": "316 stainless steel", "hardness": "hard", "shop_material": "316 stainless steel",
            "excludes": ("sm-bend-radius-min-davis-hard-al", "sm-bend-radius-min-davis-mild"),
            "why": "the K table's 'hard metal (stainless steel)'; Davis's radius rows are for aluminium and mild steel, "
                   "not stainless"},
}

# The FDM filaments whose data sheets cadagent.mechanical.compliant.allowables holds, by its PRINTED key: the family and
# the reference-registry id (#118) of the sheet.
FDM_MATERIALS: Dict[str, Tuple[str, str]] = {
    "pla-bambu-basic": ("pla", "bambu-pla-basic-tds"),
    "pla-bambu-matte": ("pla", "bambu-pla-matte-tds"),
    "pla-polymaker": ("pla", "polymaker-polylite-pla-tds"),
    "petg-bambu-basic": ("petg", "bambu-petg-basic-tds"),
    "petg-bambu-hf": ("petg", "bambu-petg-hf-tds"),
    "petg-polymaker": ("petg", "polymaker-polylite-petg-tds"),
    "petg-cf-bambu": ("petg-cf", "bambu-petg-cf-tds"),
    "asa-bambu": ("asa", "bambu-asa-tds"),
    "asa-polymaker": ("asa", "polymaker-polylite-asa-tds"),
    "copa-polymaker-dry": ("pa", "polymaker-polymide-copa-tds"),
    "copa-polymaker-wet": ("pa", "polymaker-polymide-copa-tds"),
    "pa6-cf20-polymaker-dry": ("pa-cf", "polymaker-fiberon-pa6-cf20-tds"),
    "pa6-cf20-polymaker-wet": ("pa-cf", "polymaker-fiberon-pa6-cf20-tds"),
}
SHEETS_READ_ON = "2026-10-31"     # the date allowables.Sheet records its values were read
_FACTOR_AXES = {"modulus": "e_mpa", "strength": "uts_mpa", "strain": "break_pct"}


# ----------------------------------------------------------------------------- profiles

@dataclass(frozen=True)
class Profile:
    """One process: its rules, the sources they cite, and its materials (FDM filaments, sheet alloys)."""
    process: str
    title: str
    rules: Tuple[Rule, ...]
    sources: Mapping[str, Source]
    materials: Mapping[str, Any] = field(default_factory=dict)
    formulas: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    shops: Tuple[str, ...] = ()          # the ids of the data file's ``shops``, so a misspelt shop is refused

    def rule(self, rule_id: str) -> Rule:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise ProfileDataError(f"{self.process} has no rule {rule_id!r}")

    def verified_rule(self, rule_id: str) -> Rule:
        """The rule, refusing one marked ``u``: for code that enforces a value."""
        r = self.rule(rule_id)
        if not r.verified:
            raise ProfileDataError(f"{rule_id} is marked {UNVERIFIED} (not verified in its source); it may be shown "
                                   "as advisory but never enforced")
        return r

    def features(self) -> Tuple[str, ...]:
        return tuple(sorted({r.feature for r in self.rules}))

    def rules_for(self, feature: Optional[str] = None, compare: Optional[str] = None,
                  units: Optional[str] = None, shop: Optional[str] = None) -> Tuple[Rule, ...]:
        """The matching rules: the generic ones, plus one shop's own with ``shop="<id>"`` (``"*"``: every shop's).
        A shop the data file does not list raises ProfileDataError, so a misspelt id is not read as "no shop rules"."""
        if shop is not None and shop != "*" and shop not in self.shops:
            raise ProfileDataError(f"no shop {shop!r}; the data file lists {', '.join(self.shops) or 'none'}")
        return tuple(r for r in self.rules if (feature is None or r.feature == feature)
                     and (compare is None or r.compare == compare) and (units is None or r.units == units)
                     and (not r.shop or shop == "*" or r.shop == shop))

    def limits(self, feature: Optional[str] = None, compare: Optional[str] = None, units: Optional[str] = None,
               exclude: Iterable[str] = (), shop: Optional[str] = None, **env: float) -> List[Limit]:
        """Every matching rule evaluated at ``env``; a rule that needs a variable ``env`` lacks is left out (see
        :meth:`Rule.limit` to ask for one). Shop rules are left out unless ``shop`` names one (see :meth:`rules_for`)."""
        skip = set(exclude)
        out = []
        for r in self.rules_for(feature, compare, units, shop):
            if r.id in skip or any(v not in env for v in r.variables):
                continue
            out.append(r.limit(**env))
        return out

    def tolerance(self, length_mm: float) -> List[Limit]:
        """Each source's +/- tolerance on a dimension ``length_mm`` long, for this process."""
        return self.limits("tolerance", units="mm", L=length_mm)

    def material(self, key: str) -> Any:
        if key not in self.materials:
            raise ProfileDataError(f"{self.process}: no material {key!r}; there are {sorted(self.materials)}")
        return self.materials[key]

    def family(self, family: str) -> List[FdmMaterial]:
        """The FDM filaments of one family (``petg``, ``pla``, ``asa``, ``pa-cf``, ...)."""
        return [m for m in self.materials.values() if getattr(m, "family", None) == family]

    def source(self, source_id: str) -> Source:
        return self.sources.get(source_id) or Source(source_id, resolved=False)

    def unverified(self) -> Tuple[Rule, ...]:
        return tuple(r for r in self.rules if not r.verified)


@dataclass(frozen=True)
class Profiles:
    """Everything in the data file, by process."""
    path: Path
    updated: str
    profiles: Mapping[str, Profile]
    sources: Mapping[str, Source]
    shops: Mapping[str, "Shop"] = field(default_factory=dict)

    def shop(self, shop_id: str) -> "Shop":
        if shop_id not in self.shops:
            raise ProfileDataError(f"no shop {shop_id!r}; there are {sorted(self.shops)}")
        return self.shops[shop_id]

    def __getitem__(self, process: str) -> Profile:
        if process not in self.profiles:
            raise ProfileDataError(f"no process {process!r}; there are {sorted(self.profiles)}")
        return self.profiles[process]

    def __iter__(self):
        return iter(self.profiles.values())

    def rules(self) -> List[Rule]:
        return [r for p in self for r in p.rules]


@dataclass(frozen=True)
class ShopTable:
    """One of a shop's published tables, by stock SKU: ``row("ALU-063")`` gives its values by column (lengths in mm)."""
    id: str
    shop: str
    source: str
    verified_on: str
    columns: Tuple[str, ...]
    rows: Tuple[Tuple[Any, ...], ...]
    units: Mapping[str, str] = field(default_factory=dict)

    def row(self, sku: str) -> Dict[str, Any]:
        for r in self.rows:
            if r[0] == sku:
                return dict(zip(self.columns, r))
        raise ProfileDataError(f"{self.id} has no row {sku!r}")


@dataclass(frozen=True)
class Shop:
    """A named supplier (``shops`` in the data file): its own rules (``Rule.shop``) and tables."""
    id: str
    name: str
    url: str
    sources: Tuple[str, ...]
    tables: Mapping[str, ShopTable]
    rules: Tuple[Rule, ...]
    note: str = ""

    def table(self, table_id: str) -> ShopTable:
        if table_id not in self.tables:
            raise ProfileDataError(f"{self.id} has no table {table_id!r}; there are {sorted(self.tables)}")
        return self.tables[table_id]


def _source(s: Mapping[str, Any]) -> Source:
    return Source(s["id"], s.get("title", ""), s.get("org", ""), tuple(s.get("authors") or ()), s.get("year"),
                  s.get("url", ""), s.get("access", ""))


def _rule(r: Mapping[str, Any]) -> Rule:
    return Rule(r["id"], r["process"], r["feature"], r["quantity"], r["units"], r["applies"], r["source"], r["status"],
                str(r["verified"]), r.get("min"), r.get("max"), r.get("value"), bool(r.get("window", False)),
                r.get("compare", ""), r.get("variant", ""), r.get("datum", ""), r.get("note", ""), r.get("shop", ""),
                tuple(r.get("applied_by") or ()), *(" ".join(str(r.get(k) or "").split()) for k in ("when", "not_when")),
                tuple(r.get("instead") or ()), *(" ".join(str(r.get(k) or "").split()) for k in ("strictness", "wiggle", "cost")),
                tuple(r.get("materials") or ()), tuple(r.get("cards") or ()))


def _shops(data: Mapping[str, Any], rules: List[Rule]) -> Dict[str, Shop]:
    tables: Dict[str, Dict[str, ShopTable]] = {}
    for t in data.get("shop_tables", []):
        tables.setdefault(t.get("shop", ""), {})[t["id"]] = ShopTable(
            t["id"], t.get("shop", ""), t["source"], str(t["verified"]), tuple(t["columns"]),
            tuple(tuple(r) for r in t["rows"]), dict(t.get("units") or {}))
    known = {s["id"] for s in data.get("shops", [])}
    stray = sorted({r.shop for r in rules if r.shop and r.shop not in known} | (set(tables) - known - {""}))
    if stray:
        raise ProfileDataError(f"rules or tables name shops that `shops` does not list: {stray}")
    return {s["id"]: Shop(s["id"], s["name"], s.get("url", ""), tuple(s.get("sources", ())), tables.get(s["id"], {}),
                          tuple(r for r in rules if r.shop == s["id"]), s.get("note", ""))
            for s in data.get("shops", [])}


def _fdm_materials(sources: Mapping[str, Source]) -> Dict[str, FdmMaterial]:
    from cadagent.mechanical.compliant.allowables import PRINTED
    out = {}
    for key, (family, source_id) in FDM_MATERIALS.items():
        m = PRINTED[key]
        factors = {}
        for quantity, attr in _FACTOR_AXES.items():
            ratio, sheet = min(((getattr(s, attr)[1] / getattr(s, attr)[0], s) for s in m.sheets), key=lambda x: x[0])
            factors[quantity] = Factor(f"{quantity} across the layers (Z) over in the layer plane (XY)",
                                       round(ratio, 4), source_id, sheet.citation, True, SHEETS_READ_ON)
        out[key] = FdmMaterial(key, m.name, family, source_id, m.condition, factors)
    return out


BEND_COLUMNS = ("sku", "material", "T", "R", "K", "min_flange_after_bend", "relief_depth")   # a bend-tooling table


def _sheet_materials(data: Mapping[str, Any]) -> Dict[str, SheetMaterial]:
    stocks: Dict[str, List[Stock]] = {}
    for table in data.get("shop_tables", []):
        cols = table["columns"]
        if not set(BEND_COLUMNS) <= set(cols):
            continue                    # a shop's other tables (cutting and hardware limits) are not bend tooling
        for row in table["rows"]:
            v = dict(zip(cols, row))
            stocks.setdefault(v["material"], []).append(Stock(
                v["sku"], v["material"], float(v["T"]), float(v["R"]), float(v["K"]), float(v["min_flange_after_bend"]),
                float(v["relief_depth"]), table["id"], table["source"], str(table["verified"])))
    return {key: SheetMaterial(key, spec["name"], spec["hardness"], spec["shop_material"], tuple(spec["excludes"]),
                               spec["why"], tuple(sorted(stocks.get(spec["shop_material"], []), key=lambda s: s.T)))
            for key, spec in SHEET_MATERIALS.items()}


def data_path(path: Any = None) -> Path:
    p = Path(path) if path is not None else Path(os.environ[ENV]) if os.environ.get(ENV) else DATA
    if not p.is_file():
        raise ProfileDataError(f"no process-profile data at {p}: it is docs/research/process-profiles.yaml in a cad-agent "
                               f"checkout; run from one (an editable install) or set {ENV} to the file")
    return p


@lru_cache(maxsize=8)
def _load(path: Path, mtime: float, registry_mtime: Optional[float]) -> Profiles:
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # The sources live in the registry since #118; a data file of before then carries its own blocks.
    sources: Dict[str, Source] = {s["id"]: _source(s) for s in data.get("sources", [])}
    sources.update({s["id"]: _source(s) for s in data.get("standards", [])})
    registry = path.parent / REGISTRY.name
    if registry.is_file():
        reg = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
        entries = reg if isinstance(reg, list) else (reg.get("sources") or reg.get("references") or []) \
            if isinstance(reg, dict) else []
        for s in entries:
            if isinstance(s, dict) and "id" in s:
                sources.setdefault(s["id"], _source(s))
    # and the schema-2 shards beside it (#323): a record read at source may back a rule; a catalogued one stays
    # unresolved, so a rule that cites it fails the tests. Which files are shards, and which records are read, is
    # the registry's to say.
    from cadagent.review.references import NOT_SHARDS, is_read
    for shard in sorted(path.parent.glob(f"{REGISTRY.stem}/*.yaml")):
        if shard.name in NOT_SHARDS:
            continue
        doc = yaml.safe_load(shard.read_text(encoding="utf-8"))
        for s in (doc.get("sources") if isinstance(doc, dict) else None) or []:
            if is_read(s) and "id" in s and not s.get("extends"):
                sources.setdefault(s["id"], _source(s))
    datasets = {f"dataset:{d['id']}": Source(f"dataset:{d['id']}", d["what"], d.get("cites", ""), (), None,
                                             d.get("where", "")) for d in data.get("datasets", [])}
    sources.update(datasets)
    for key, (_, source_id) in FDM_MATERIALS.items():
        sources.setdefault(source_id, Source(source_id, resolved=False))
    rules = [_rule(r) for r in data["rules"]]
    formulas = {f["id"]: f for f in data.get("formulas", [])}
    materials: Dict[str, Dict[str, Any]] = {"fdm": _fdm_materials(sources), "sheet-metal": _sheet_materials(data)}
    profiles = {}
    for process, title in data["processes"].items():
        mine = tuple(r for r in rules if r.process == process)
        cited = {r.source for r in mine} | {m.source for m in materials.get(process, {}).values()
                                            if isinstance(m, FdmMaterial)}
        cited |= {s.source for m in materials.get(process, {}).values() if isinstance(m, SheetMaterial)
                  for s in m.stocks}
        mine_formulas = {k: f for k, f in formulas.items() if process == "sheet-metal" and k.startswith("sm-")}
        cited |= {f["source"] for f in mine_formulas.values()}
        profiles[process] = Profile(process, title, mine, {k: sources[k] for k in cited if k in sources},
                                    materials.get(process, {}), mine_formulas)
    shops = _shops(data, rules)
    profiles = {k: replace(v, shops=tuple(shops)) for k, v in profiles.items()}
    return Profiles(path, str(data.get("updated", "")), profiles, sources, shops)


def load(path: Any = None) -> Profiles:
    """Every process profile from the data file (cached until it, the registry beside it or the registry's shards change)."""
    p = data_path(path).resolve()
    reg = p.parent / REGISTRY.name
    shards = [f.stat().st_mtime for f in p.parent.glob(f"{REGISTRY.stem}/*.yaml")]
    return _load(p, p.stat().st_mtime, max([reg.stat().st_mtime] + shards) if reg.is_file() else None)


def profile(process: str, path: Any = None) -> Profile:
    """One process's profile: ``fdm``, ``sla``, ``sls``, ``mjf``, ``injection-moulding``, ``sheet-metal`` or ``cnc``."""
    return load(path)[process]


# ------------------------------------------------------------ how each part of a project is made (#577)
#
# The print pipeline (the report's "Printed parts" and "Print files" rows, `export-3mf`, the build plates, the slicer's
# default part list, the overhang screen) applies to printed parts only. A process is read from free text (a dossier
# card's ``material.process``) or a name (``cad: part_process:``): additive words first, then the names below.

# The additive words: a part made by one of these is printed. (The dossier lint's ``wall-undeclared`` uses the same.)
ADDITIVE_RE = re.compile(r"\b(?:fdm|fff|sla|sls|mjf|dlp|polyjet|additive)\b|\b3d[ -]?print", re.I)
# Any other "print" word keeps a part in the print pipeline too (``printed PETG, bore machined after``): when the
# words are unclear the part is checked, not skipped.
_PRINT_WORD_RE = re.compile(r"\bprint(?:s|ed|ing)?\b", re.I)

# The routes that are not printing: name -> (what a report row calls it, the words that mean it). ``sheet-metal``,
# ``cnc`` and ``injection-moulding`` are the data file's processes; ``weldment`` and ``purchased`` name routes it has no
# rules for, so there is no profile or rule card for them. Order decides the name when a text matches several.
NOT_PRINTED: Dict[str, Tuple[str, "re.Pattern[str]"]] = {
    "purchased": ("bought, not made", re.compile(
        r"\b(?:purchas\w*|bought|buy|off[- ]the[- ]shelf|cots)\b", re.I)),
    "weldment": ("welded fabrication", re.compile(r"\bweld\w*", re.I)),
    "sheet-metal": ("cut or bent sheet, plate or stock", re.compile(
        r"\bsheet[- ]?metal\b|\b(?:laser|plasma|water[- ]?jet|flame|oxy|saw|hand)[- ]?cut\b|\bcut[- ](?:plate|sheet)\b",
        re.I)),
    "cnc": ("machined", re.compile(r"\b(?:cnc|machin\w*|mill(?:ed|ing)|turn(?:ed|ing)|lathe)\b", re.I)),
    "injection-moulding": ("injection moulded", re.compile(r"\binjection\b|\bmou?ld\w*", re.I)),
}
PART_PROCESS_DEFAULT = "*"      # the ``cad: part_process:`` key for every part nothing else names


def process_route(text: Any) -> Optional[str]:
    """How a process named in words is made: ``"additive"``, a ``NOT_PRINTED`` name, or None when the words name no
    process this module knows. Additive and "print" words win (``FDM, then machined`` is a printed part). Words are
    matched, not parsed: ``not welded`` reads as welded, so write what the part is, not what it is not."""
    words = str(text or "")
    if ADDITIVE_RE.search(words) or _PRINT_WORD_RE.search(words):
        return "additive"
    for name, (_, pattern) in NOT_PRINTED.items():
        if pattern.search(words):
            return name
    return None


def known_process_names() -> List[str]:
    """The names ``cad: part_process:`` documents (any text ``process_route`` reads is accepted too)."""
    return ["fdm", "sla", "sls", "mjf", *sorted(NOT_PRINTED)]


@dataclass(frozen=True)
class PartProcess:
    """How one part is made, and who said so. ``printed`` is True unless a declaration names a ``NOT_PRINTED`` route:
    a part nobody declared, and one whose words name no known process, stay in the print pipeline."""
    part: str
    route: Optional[str] = None     # "additive", a NOT_PRINTED name, or None (undeclared or not recognised)
    declared: str = ""              # the words as written
    source: str = ""                # where they were written; "" when nothing declares the part

    @property
    def printed(self) -> bool:
        return self.route not in NOT_PRINTED

    @property
    def skip_reason(self) -> str:
        """The report's words for a part the print pipeline leaves out. Not a verdict on the part."""
        what = NOT_PRINTED[self.route][0] if self.route in NOT_PRINTED else "not printed"
        return (f"not checked by the print pipeline: {what} ({self.source} {self.declared!r}); "
                "no check here says this part can be made")


def part_processes(project: Any, parts: Iterable[str]) -> Dict[str, PartProcess]:
    """``{part: PartProcess}`` for a project's parts. For each part, the first of:

    1. its dossier card's ``material.process`` (``cad: dossier:``; the card whose id is the part's name), when its
       words name a process ``process_route`` reads;
    2. ``cad: part_process: {<part>: <process>}`` in ``cad-agent.yaml``;
    3. ``cad: part_process: {"*": <process>}``, the project's default;
    4. nothing: the part is printed, as every part was before a process could be declared (a card's unread words
       are kept in ``declared``).

    Reads files only. A dossier that does not load declares nothing here (the dossier lint reports it)."""
    cards: Dict[str, Any] = {}
    if getattr(project, "dossier", None):
        from cadagent.review.dossier.load import DossierError, load_project_dossier
        try:
            cards = load_project_dossier(project, strict=False).parts
        except (DossierError, OSError, AttributeError):
            cards = {}
    config = dict(getattr(project, "part_process", None) or {})
    out: Dict[str, PartProcess] = {}
    for part in parts:
        card = cards.get(part)
        said = (card.material.process if card is not None and card.material else "").strip()
        if said and process_route(said) is not None:
            source = "dossier material.process"
        elif part in config:
            said, source = config[part], "cad.part_process"
        elif PART_PROCESS_DEFAULT in config:
            said, source = config[PART_PROCESS_DEFAULT], f"cad.part_process {PART_PROCESS_DEFAULT!r}"
        else:       # nothing declared, or a card whose words name no known process: printed
            out[part] = PartProcess(part, None, said, "dossier material.process" if said else "")
            continue
        out[part] = PartProcess(part, process_route(said), said, source)
    return out


def printed_parts(project: Any, parts: Iterable[str]) -> List[str]:
    """The parts the print pipeline applies to, in the order given (``part_processes``)."""
    return [p for p, how in part_processes(project, parts).items() if how.printed]
