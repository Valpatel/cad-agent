"""Compare evaluated designs (or optimiser trials): Pareto ranking over the objectives, a leaderboard, one-part swaps.

``comparison.json``::

    {"schema": "cad-agent/explore-comparison/1", "kind": "designs" | "search", "title", "generated", "currency",
     "evaluator", "objectives": [{metric, goal}], "constraints": [{metric, min, max}],
     "metrics": {name: {label, unit, digits}},                 # the columns: objectives first
     "summary": {designs, feasible, pareto, errors},
     "designs": [<evaluation> + {rank, pareto, feasible, swaps?}],   # in leaderboard order
     "notes": [...]}

A design is **feasible** when its verdict is ``ok`` or ``warn``: no failed check, every constraint met and every
objective has a number. Feasible designs are sorted into Pareto fronts (rank 1 is the front: no other feasible design
is at least as good on every objective and better on one); infeasible ones follow, fewest failures first. Ranking
says nothing about how good the numbers themselves are: they are as good as the catalogue and the evaluator.
"""

from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from cadagent.explore import metrics as M
from cadagent.explore.catalogue import Catalogue, display_name
from cadagent.explore.config import ExploreConfig, Objective
from cadagent.explore.evaluate import Evaluator, evaluate_design, value_of

SCHEMA = "cad-agent/explore-comparison/1"
NOTES = [
    "Numbers come from the catalogue (each part's cited specs and prices) and the project's evaluator. "
    "Values marked est. rest on estimates; totals marked ≥ leave out parts without a price or mass.",
    "Nothing here is measured: a comparison ranks designs on paper. Weigh, test and price the real parts "
    "before deciding.",
]


def anchor(design_id: Any) -> str:
    """The HTML id of a design's section on the page (letters, digits, - and _ only)."""
    return "d-" + (re.sub(r"[^A-Za-z0-9_-]+", "-", str(design_id)).strip("-") or "design")


def describe_choice(choice: Dict[str, Any]) -> str:
    """``wheel_motor hub-90 · length_mm 160``: what an optimiser trial changed (keys ``slot:<name>``, ``param:<path>``)."""
    return " · ".join(f"{k.split(':', 1)[-1].rsplit('.', 1)[-1]} {'none' if v is None else v}" for k, v in choice.items())


def feasible(ev: Dict[str, Any]) -> bool:
    return ev.get("verdict") in ("ok", "warn")


def objective_vector(ev: Dict[str, Any], objectives: Sequence[Objective]) -> Optional[Tuple[float, ...]]:
    """Signed values (smaller is better for every entry), or None when one is missing."""
    values = [value_of(ev.get("metrics") or {}, o.metric) for o in objectives]
    return None if any(v is None for v in values) else tuple(o.sign * v for o, v in zip(objectives, values))


def dominates(a: Sequence[float], b: Sequence[float]) -> bool:
    """``a`` is at least as good as ``b`` everywhere and better somewhere (all minimised)."""
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def pareto_ranks(vectors: Sequence[Sequence[float]]) -> List[int]:
    """Non-dominated sorting: rank 1 is the Pareto front, rank 2 the front once rank 1 is removed, and so on."""
    n = len(vectors)
    dominated_by = [0] * n
    beats: List[List[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if dominates(vectors[i], vectors[j]):
                beats[i].append(j)
                dominated_by[j] += 1
            elif dominates(vectors[j], vectors[i]):
                beats[j].append(i)
                dominated_by[i] += 1
    ranks = [0] * n
    front = [i for i in range(n) if dominated_by[i] == 0]
    rank = 1
    while front:
        nxt = []
        for i in front:
            ranks[i] = rank
            for j in beats[i]:
                dominated_by[j] -= 1
                if dominated_by[j] == 0:
                    nxt.append(j)
        front, rank = nxt, rank + 1
    return ranks


def rank(evaluations: Iterable[Dict[str, Any]], objectives: Sequence[Objective]) -> List[Dict[str, Any]]:
    """The evaluations in leaderboard order, each with ``feasible``, ``rank`` (None when infeasible) and ``pareto``."""
    evs = [dict(ev, rank=None) for ev in evaluations]           # a rank from an earlier ranking never carries over
    ok = [ev for ev in evs if feasible(ev) and objective_vector(ev, objectives) is not None]
    for ev, r in zip(ok, pareto_ranks([objective_vector(ev, objectives) for ev in ok])):
        ev["rank"] = r
    for ev in evs:
        ev["feasible"] = ev["rank"] is not None
        ev["pareto"] = ev["rank"] == 1

    def key(ev: Dict[str, Any]):
        vec = objective_vector(ev, objectives) or (float("inf"),)
        if ev["feasible"]:
            return (0, ev["rank"], vec[0] if vec else 0.0, str(ev.get("name")))
        counts = ev.get("counts") or {}
        return (1 if ev.get("verdict") != "error" else 2, counts.get("fail", 0), vec[0] if vec else 0.0, str(ev.get("name")))
    return sorted(evs, key=key)


def metric_columns(evaluations: Sequence[Dict[str, Any]], cfg: ExploreConfig) -> Dict[str, Dict[str, Any]]:
    """Display info for every metric that appears, objectives first, then the cost and mass, then the rest in the
    order they first appear."""
    order: List[str] = [o.metric for o in cfg.objectives]
    for name in (cfg.cost_metric, "mass_kg"):
        if name not in order:
            order.append(name)
    for ev in evaluations:
        for name in ev.get("metrics") or {}:
            if name not in order:
                order.append(name)
    seen = {name for ev in evaluations for name in (ev.get("metrics") or {})}
    out = {}
    for name in order:
        if name not in seen:
            continue
        sample = next((ev["metrics"][name] for ev in evaluations if name in (ev.get("metrics") or {})), {})
        out[name] = M.info(name, sample, cfg.metrics.get(name))
        if out[name]["digits"] is None:          # one precision per column, from its largest value
            out[name]["digits"] = M.column_digits([value_of(ev.get("metrics") or {}, name) for ev in evaluations])
    return out


def comparison(evaluations: Iterable[Dict[str, Any]], cfg: ExploreConfig, kind: str = "designs",
               title: Optional[str] = None, evaluator: str = "") -> Dict[str, Any]:
    ranked = rank(evaluations, cfg.objectives)
    return {
        "schema": SCHEMA,
        "kind": kind,
        "title": title or cfg.title,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "currency": cfg.currency,
        "evaluator": evaluator or (cfg.evaluator.describe() if cfg.evaluator else "none (catalogue cost and mass only)"),
        "objectives": [{"metric": o.metric, "goal": o.goal} for o in cfg.objectives],
        "constraints": [{"metric": c.metric, "min": c.min, "max": c.max} for c in cfg.constraints],
        "metrics": metric_columns(ranked, cfg),
        "summary": {"designs": len(ranked), "feasible": sum(1 for e in ranked if e["feasible"]),
                    "pareto": sum(1 for e in ranked if e["pareto"]),
                    "errors": sum(1 for e in ranked if e.get("verdict") == "error")},
        "designs": ranked,
        "notes": list(NOTES),
    }


# ----------------------------------------------------------------------------- one-part swaps

def _ref(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("part"), str):
        return value["part"]
    return None


def swap_options(design: Dict[str, Any], catalogue: Catalogue, cfg: ExploreConfig) -> List[Tuple[str, str]]:
    """Every (slot, part id) that differs from the design in one slot: the other catalogue parts that fit the slot
    (its category, else the current part's, narrowed by the slot's ``choices`` and ``where``). Custom parts and empty
    slots are left alone."""
    from cadagent.explore.design import candidates

    out = []
    for slot, value in (design.get("parts") or {}).items():
        current = _ref(value)
        if current is None or current not in catalogue:
            continue
        fitting = candidates(catalogue, cfg.slots.get(slot), catalogue[current].get("category"))
        out += [(slot, it["id"]) for it in fitting if it["id"] != current]
    return out


def with_part(design: Dict[str, Any], slot: str, part_id: Optional[str]) -> Dict[str, Any]:
    """A copy of ``design`` with ``part_id`` in ``slot``, keeping the slot's quantity."""
    d = copy.deepcopy(design)
    parts = d.setdefault("parts", {})
    value = parts.get(slot)
    parts[slot] = {**value, "part": part_id} if isinstance(value, dict) and "part" in value and part_id else part_id
    return d


def swaps(design: Dict[str, Any], base: Dict[str, Any], catalogue: Catalogue, cfg: ExploreConfig,
          evaluator: Optional[Evaluator] = None, workers: int = 1) -> List[Dict[str, Any]]:
    """Evaluate every one-part swap of ``design`` and compare each with ``base`` (the design's own evaluation) on the
    objectives. ``dominates`` marks a feasible swap that is at least as good on every objective and better on one.
    ``workers`` > 1 evaluates swaps in threads (a command evaluator then runs that many processes at once; a Python
    evaluator must be thread-safe)."""
    base_vec = objective_vector(base, cfg.objectives)
    options = swap_options(design, catalogue, cfg)

    def one(option: Tuple[str, str]) -> Dict[str, Any]:
        slot, part_id = option
        return evaluate_design(with_part(design, slot, part_id), catalogue, cfg, evaluator,
                               design_id=f"{base['id']}~{slot}={part_id}")
    if workers > 1 and len(options) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, options))
    else:
        results = [one(o) for o in options]
    out = []
    for (slot, part_id), ev in zip(options, results):
        values = {o.metric: value_of(ev["metrics"], o.metric) for o in cfg.objectives}
        delta, better, worse = {}, [], []
        for o in cfg.objectives:
            a, b = values[o.metric], value_of(base.get("metrics") or {}, o.metric)
            if a is None or b is None:
                continue
            delta[o.metric] = round(a - b, 6)
            if o.sign * (a - b) < 0:
                better.append(o.metric)
            elif o.sign * (a - b) > 0:
                worse.append(o.metric)
        vec = objective_vector(ev, cfg.objectives)
        out.append({"slot": slot, "from": _ref((design.get("parts") or {}).get(slot)), "to": part_id,
                    "name": display_name(catalogue[part_id]), "verdict": ev["verdict"], "feasible": feasible(ev),
                    "values": values, "delta": delta, "better": better, "worse": worse,
                    "dominates": bool(feasible(ev) and vec and base_vec and dominates(vec, base_vec)),
                    "problems": [c["text"] for c in ev["checks"] if c["level"] == "fail"][:3]})
    out.sort(key=lambda s: (not s["dominates"], not s["feasible"], len(s["worse"]) - len(s["better"]), s["slot"], s["to"]))
    return out


# ----------------------------------------------------------------------------- comparing a project's designs

def design_ids(paths: Sequence[Path], root: Path) -> List[str]:
    """File stems, or the path from the root where two stems clash."""
    stems = [Path(p).stem for p in paths]
    out = []
    for p, stem in zip(paths, stems):
        if stems.count(stem) == 1:
            out.append(stem)
        else:
            rel = Path(p).resolve().relative_to(root) if Path(p).resolve().is_relative_to(root) else Path(p)
            out.append(rel.with_suffix("").as_posix())
    return out


def compare_designs(cfg: ExploreConfig, catalogue: Catalogue, evaluator: Optional[Evaluator] = None,
                    files: Optional[Sequence[Path]] = None, with_swaps: bool = False, workers: int = 1) -> Dict[str, Any]:
    """Evaluate the configured designs (or ``files``), optionally with every one-part swap (``workers`` at a time),
    and rank them."""
    from cadagent.explore.design import DesignError, load_design

    paths = [Path(f).resolve() for f in (files if files is not None else cfg.design_files()[0])]
    evaluations = []
    for path, design_id in zip(paths, design_ids(paths, cfg.root)):
        rel = path.relative_to(cfg.root).as_posix() if path.is_relative_to(cfg.root) else str(path)
        try:
            design = load_design(path)
        except DesignError as exc:
            evaluations.append({"id": design_id, "name": design_id, "file": rel, "verdict": "error", "metrics": {},
                                "checks": [{"id": "error", "level": "fail", "text": str(exc)}], "errors": [str(exc)],
                                "counts": {"ok": 0, "warn": 0, "fail": 1}, "parts": {}, "params": {}, "bom": None})
            continue
        ev = evaluate_design(design, catalogue, cfg, evaluator, design_id, rel, path)
        if with_swaps and ev["verdict"] != "error":
            ev["swaps"] = swaps(design, ev, catalogue, cfg, evaluator, workers)
        evaluations.append(ev)
    return comparison(evaluations, cfg, "designs")


# ----------------------------------------------------------------------------- the project site's design cards

def site_cards(comp: Dict[str, Any], cfg: ExploreConfig, page_href: str) -> Dict[str, Any]:
    """``{"designs": [...]}`` in the shape ``cad-agent site`` shows as design cards (``site: designs:``)."""
    columns = comp["metrics"]
    show = [m for m in (cfg.card_metrics or list(columns)[:6]) if m in columns]
    cards = []
    for ev in comp["designs"]:
        metrics = []
        for name in show:
            m = (ev.get("metrics") or {}).get(name)
            if not m:
                continue
            col = columns[name]
            metrics.append({"label": col["label"], "unit": col["unit"], "estimate": bool(m.get("estimate")),
                            "level": m.get("level", ""),
                            "value": M.format_value(m.get("value"), "", col.get("digits"), incomplete=bool(m.get("incomplete")))})
        badges = []
        if ev.get("pareto"):
            badges.append({"label": "Pareto front", "level": "done", "title": "No feasible design beats it on every objective"})
        elif ev.get("rank"):
            badges.append({"label": f"front {ev['rank']}", "level": "next", "title": "Pareto rank"})
        if ev.get("verdict") == "error":
            badges.append({"label": "error", "level": "fail", "title": "; ".join(ev.get("errors") or [])})
        cards.append({"name": ev.get("name"), "file": ev.get("file"), "summary": ev.get("summary") or "",
                      "verdict": "fail" if ev.get("verdict") == "error" else ev.get("verdict"),
                      "metrics": metrics, "checks": ev.get("counts") or {}, "badges": badges,
                      "link": f"{page_href}#{anchor(ev.get('id'))}"})
    return {"designs": cards}


def write_comparison(comp: Dict[str, Any], out_dir: Path, json_name: str = "comparison.json",
                     html_name: str = "compare.html", cfg: Optional[ExploreConfig] = None,
                     cards: bool = True) -> Dict[str, Path]:
    """Write the JSON, the standalone HTML page and (for a design comparison) the site's design cards."""
    from cadagent.explore.page import render_page

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {"json": out_dir / json_name, "html": out_dir / html_name}
    _write(written["json"], json.dumps(comp, indent=1, default=str) + "\n")
    _write(written["html"], render_page(comp))
    if cards and cfg is not None:
        href = Path(os.path.relpath(written["html"], cfg.root)).as_posix()
        written["cards"] = out_dir / "designs.json"
        _write(written["cards"], json.dumps(site_cards(comp, cfg, href), indent=1) + "\n")
    return written


def _write(path: Path, text: str) -> None:
    """Write through a temporary file, so a page being served never shows half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)
