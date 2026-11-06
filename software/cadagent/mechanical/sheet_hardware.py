"""Bought hardware for bent sheet parts: what the clinch parts and blind rivets the checks list cost, and where to buy
them (#283).

    from cadagent.mechanical import sheet_hardware as sh
    sh.choose_clinch("M3", "5052-h32", 1.6)        # the parts that clinch into 1.6 mm 5052, each with its cheapest offer
    sh.choose_rivet(3.2, 3.2)                       # 1/8 in rivets whose grip takes a 3.2 mm stack, cheapest first
    sh.cost({"S-632-1": 8, "mcmaster-97447A015": 24})   # loose parts, the packs to buy, and a shop's price to press in

The data is ``docs/research/sheet-hardware.yaml``, in cad-agent's part-catalogue layout
(``cadagent.simulation.explore.catalogue``): one item per orderable part number, with the seller's price at its
smallest quantity break, the day it was read, the stock shown, the seller's page and, for clinch parts a shop presses
in, that shop's price per part from its ordering feed. Each item's ``part`` is the key of the part it is checked as:
``cadagent.mechanical.clinch.PARTS`` or ``cadagent.mechanical.rivets.RIVETS``. So a part is chosen by the checks first
(sheet, hardness, thickness, grip), then by price, never the other way round.

**Limits.** Prices are dated facts from public pages; they change without notice, so a result carries the date it
was read and re-reading the page before buying is the caller's job. Shipping, tax, minimum orders and the cost of a
press or a rivet tool are not included. A shop's installed price is per part from its feed; the feed does not say
whether it includes the part. A part the checks list but no seller row prices is returned with ``offer`` None.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from cadagent.mechanical import clinch, rivets
from cadagent.simulation.explore import catalogue as cat

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "docs" / "research" / "sheet-hardware.yaml"
CATEGORIES = ("clinch_nut", "clinch_stud", "clinch_standoff", "blind_rivet")

# Registry ids (docs/research/references.yaml) of the sources the catalogue's numbers come from.
SRC = {
    "bossard-pem-prices": "Bossard Americas web shop, PEM part pages read 2026-11-02: price per piece at 1-249 and "
                          "1000-4999, and the stock count",
    "mcmaster-blind-rivets": "McMaster-Carr blind rivet pages read 2026-11-01: pack size and pack price",
    "sendcutsend-catalog": "SendCutSend ordering feed (generated 2026-04-29, read 2026-11-02): unit_price per hardware "
                           "SKU",
}


class CatalogueError(ValueError):
    """The hardware catalogue does not load or does not check."""


def _item_problems(item: Mapping[str, Any]) -> List[str]:
    """What the generic catalogue check cannot know: the part, its kind, the sources and the installed block."""
    out, iid, part = [], item["id"], item.get("part")
    if item.get("category") == "blind_rivet":
        if part not in rivets.RIVETS:
            out.append(f"{iid}: part {part!r} is not in cadagent.mechanical.rivets.RIVETS")
    elif part not in clinch.PARTS:
        out.append(f"{iid}: part {part!r} is not in cadagent.mechanical.clinch.PARTS")
    elif item.get("category") != f"clinch_{clinch.PARTS[part].kind}":
        out.append(f"{iid}: {part} is a {clinch.PARTS[part].kind}, so its category is clinch_{clinch.PARTS[part].kind}, "
                   f"not {item.get('category')!r}")
    if item.get("reference") not in SRC:
        out.append(f"{iid}: reference {item.get('reference')!r} is not one of {sorted(SRC)}")
    inst = item.get("installed")
    if inst is not None:
        if item.get("category") == "blind_rivet":
            out.append(f"{iid}: a rivet has no installed price")
        elif not isinstance(inst, dict):
            out.append(f"{iid}: installed must be a mapping")
        else:
            for key in ("shop", "sku", "generated", "checked"):
                if not isinstance(inst.get(key), str) or not inst.get(key):
                    out.append(f"{iid}: installed needs {key}")
            if not cat.is_number(inst.get("price_usd")) or inst["price_usd"] < 0:
                out.append(f"{iid}: installed.price_usd must be a number >= 0, got {inst.get('price_usd')!r}")
            if inst.get("reference") not in SRC:
                out.append(f"{iid}: installed.reference {inst.get('reference')!r} is not one of {sorted(SRC)}")
    return out


@lru_cache(maxsize=4)
def _load(path: str) -> cat.Catalogue:
    catalogue, issues = cat.load_catalogue([Path(path)])
    issues += cat.check_catalogue(catalogue, categories=CATEGORIES, max_price_age_days=None)
    errors = [str(i) for i in issues if i.level == "error"]
    for item in catalogue:
        errors += _item_problems(item)
    if errors:
        raise CatalogueError(f"{path}: " + "; ".join(errors))
    return catalogue


def load(path: Any = None) -> cat.Catalogue:
    """The catalogue, checked: every item well formed, priced items dated, each ``part`` a part the checks know."""
    return _load(str(Path(path) if path is not None else DATA))


def each_usd(item: Mapping[str, Any]) -> Optional[float]:
    """The price of one piece: the pack price over the pack quantity; None when the item has no price."""
    p = cat.price_of(dict(item), "usd")
    return None if p is None else round(p / cat.pack_qty(dict(item)), 6)


def _offer(item: Mapping[str, Any]) -> Dict[str, Any]:
    buy = (item.get("buy") or [{}])[0]
    inst = item.get("installed") or {}
    specs = item.get("specs") or {}
    return {"id": item["id"], "model": item.get("model"), "seller": buy.get("seller"), "url": buy.get("url"),
            "each_usd": each_usd(item), "pack_qty": cat.pack_qty(dict(item)), "pack_usd": item.get("price_usd"),
            "each_usd_1000": specs.get("price_usd_1000"), "stock": specs.get("stock"),
            "price_checked": item.get("price_checked"), "source": item.get("reference"),
            "installed": dict(inst) if inst else None}


def _key(o: Dict[str, Any]) -> tuple:
    return (o["each_usd"] is None, o["each_usd"] if o["each_usd"] is not None else 0.0, o["id"])


def offers(part: str, path: Any = None) -> List[Dict[str, Any]]:
    """Every seller row for ``part`` (a clinch or rivet key), the cheapest piece first and unpriced rows last."""
    return sorted((_offer(i) for i in load(path) if i.get("part") == part), key=_key)


def _with_offers(rows: List[Dict[str, Any]], path: Any) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        o = offers(r["key"], path)
        out.append({"part": r, "offer": o[0] if o else None, "offers": o})
    return out


def choose_clinch(thread: str, sheet: str, thickness_mm: float, kind: Optional[str] = None, *,
                  path: Any = None) -> List[Dict[str, Any]]:
    """The parts ``clinch.parts_for`` lists for this thread, sheet and thickness, each with its offers. Nuts, then
    studs, then standoffs; within a kind, the cheapest piece first and unpriced parts last. Place the one you take
    with ``clinch.check_placement``."""
    rank = {"nut": 0, "stud": 1, "standoff": 2}
    rows = _with_offers(clinch.parts_for(thread, sheet, thickness_mm, kind), path)
    return sorted(rows, key=lambda x: (rank[x["part"]["kind"]],) + (_key(x["offer"]) if x["offer"] else (True, 0.0, "")))


def choose_rivet(diameter_mm: float, grip_min_mm: float, grip_max_mm: Optional[float] = None,
                 body: Optional[str] = None, *, path: Any = None) -> List[Dict[str, Any]]:
    """The rivets ``rivets.rivets_for`` lists for this diameter and grip, each with its offers, the cheapest piece
    first and unpriced rivets last. Check the joint with ``rivets.check_joint``."""
    rows = _with_offers(rivets.rivets_for(diameter_mm, grip_min_mm, grip_max_mm, body), path)
    return sorted(rows, key=lambda x: _key(x["offer"]) if x["offer"] else (True, 0.0, x["part"]["key"]))


def cost(quantities: Mapping[str, int], *, path: Any = None) -> Dict[str, Any]:
    """What ``quantities`` ({part key: how many}) cost as loose parts from each part's cheapest offer: whole packs,
    and the price of the pieces used. For clinch parts a shop offers to press in, also its price for doing so. A part
    with no priced offer is listed under ``unpriced`` and left out of the totals."""
    lines, unpriced = [], []
    loose = packs_total = installed = 0.0
    every_installed = True
    for part, qty in quantities.items():
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise ValueError(f"{part}: a quantity is a whole number of at least 1, not {qty!r}")
        if part not in clinch.PARTS and part not in rivets.RIVETS:
            raise KeyError(f"{part!r} is not a clinch part or a rivet the checks know")
        o = next((x for x in offers(part, path) if x["each_usd"] is not None), None)
        if o is None:
            unpriced.append(part)
            every_installed = every_installed and part not in clinch.PARTS     # a rivet is never pressed in
            continue
        packs = math.ceil(qty / o["pack_qty"])
        line = {"part": part, "qty": qty, "model": o["model"], "seller": o["seller"], "url": o["url"],
                "each_usd": o["each_usd"], "packs": packs, "packs_usd": round(packs * o["pack_usd"], 4),
                "pieces_usd": round(qty * o["each_usd"], 4), "price_checked": o["price_checked"]}
        inst = o["installed"]
        if inst and inst.get("price_usd") is not None:
            line["installed"] = {"shop": inst["shop"], "sku": inst["sku"], "each_usd": inst["price_usd"],
                                 "usd": round(qty * inst["price_usd"], 4)}
            installed += line["installed"]["usd"]
        elif part in clinch.PARTS:
            every_installed = False
        lines.append(line)
        loose += line["pieces_usd"]
        packs_total += line["packs_usd"]
    clinch_lines = [x for x in lines if x["part"] in clinch.PARTS]      # priced clinch parts
    return {"lines": lines, "unpriced": unpriced, "pieces_usd": round(loose, 4), "packs_usd": round(packs_total, 4),
            "installed_usd": round(installed, 4) if clinch_lines and every_installed else None,
            "limits": ["prices as read on each line's price_checked date, before shipping and tax; re-read the seller's "
                       "page before buying",
                       "installed_usd is a shop's price per part from its feed, given only when every clinch part on "
                       "the list has one; it does not say whether the part is included"]}
