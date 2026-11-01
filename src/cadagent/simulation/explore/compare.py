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
is at least as good on every objective and better on one); infeasible ones follow, fewest failures first. An
incomplete total (``≥``, a part without a price or mass) is a lower bound and is never counted as better than a value
it might exceed, unless both totals leave out exactly the same lines, so their difference is known. Ranking says
nothing about how good the numbers themselves are: they are as good as the catalogue and the evaluator.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from cadagent.project import source_stamp
from cadagent.simulation.explore import metrics as M
from cadagent.simulation.explore.catalogue import Catalogue, display_name, is_number, json_default
from cadagent.simulation.explore.config import ExploreConfig, Objective
from cadagent.simulation.explore.evaluate import Evaluator, evaluate_design, kill_running_evaluators, value_of

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


def bounds(metric: Optional[Dict[str, Any]], goal: str) -> Optional[Tuple[float, float]]:
    """A metric as an interval in minimisation space (``goal`` max is negated). An exact value is ``(v, v)``. An
    incomplete total is a lower bound, as the true value is at least the one shown: for a minimised objective it lies
    in ``(v, inf)``, for a maximised one in ``(-inf, -v)``. None when there is no number."""
    v = (metric or {}).get("value")
    if not is_number(v):
        return None
    s = float(v) if goal == "min" else -float(v)
    if not (metric or {}).get("incomplete"):
        return (s, s)
    return (s, math.inf) if goal == "min" else (-math.inf, s)


Entry = Tuple[float, float, float, Optional[str]]     # (lo, hi, shown, what it leaves out), minimisation space


def entry(metric: Optional[Dict[str, Any]], goal: str) -> Optional[Entry]:
    """``bounds`` plus the shown value and, for an incomplete total that says which lines it leaves out (the BOM's
    ``missing``), a key for them: two totals with the same key differ by exactly what they show."""
    b = bounds(metric, goal)
    if b is None:
        return None
    missing = metric.get("missing") if metric.get("incomplete") else None
    key = "\n".join(sorted(map(str, missing))) if isinstance(missing, list) else None
    return (b[0], b[1], float(metric["value"]) * (1.0 if goal == "min" else -1.0), key)


def objective_entries(ev: Dict[str, Any], objectives: Sequence[Objective]) -> Optional[List[Entry]]:
    out = [entry((ev.get("metrics") or {}).get(o.metric), o.goal) for o in objectives]
    return None if any(e is None for e in out) else out


def objective_vector(ev: Dict[str, Any], objectives: Sequence[Objective]) -> Optional[Tuple[float, ...]]:
    """The values as shown, signed so smaller is better for every entry; None when one is missing."""
    values = [value_of(ev.get("metrics") or {}, o.metric) for o in objectives]
    return None if any(v is None for v in values) else tuple(o.sign * v for o, v in zip(objectives, values))


def _entry(x: Any) -> Entry:
    """A number, an ``(lo, hi)`` interval or a full entry, as a full entry."""
    if isinstance(x, (tuple, list)):
        if len(x) == 4:
            return (float(x[0]), float(x[1]), float(x[2]), x[3])
        lo, hi = float(x[0]), float(x[1])
        return (lo, hi, hi if lo == -math.inf else lo, None)
    return (float(x), float(x), float(x), None)


def compare_entry(a: Any, b: Any) -> Tuple[bool, bool]:
    """``(a certainly at least as good as b, a certainly better)``, minimised. Totals that leave out the same lines
    compare by what they show; otherwise a lower bound is never better than a value it might exceed."""
    x, y = _entry(a), _entry(b)
    if x[3] is not None and x[3] == y[3]:
        return x[2] <= y[2], x[2] < y[2]
    return x[1] <= y[0], x[1] < y[0]


def dominates(a: Sequence[Any], b: Sequence[Any]) -> bool:
    """``a`` is certainly at least as good as ``b`` on every objective and certainly better on one (all minimised).
    Entries are numbers, ``(lo, hi)`` intervals or full entries (see ``entry``)."""
    pairs = [compare_entry(x, y) for x, y in zip(a, b)]
    return all(le for le, _ in pairs) and any(lt for _, lt in pairs)


def pareto_ranks(vectors: Sequence[Sequence[Any]], chunk: int = 256) -> List[int]:
    """Non-dominated sorting with ``dominates``: rank 1 is the Pareto front, rank 2 the front once rank 1 is removed,
    and so on. Vectorised: thousands of designs rank in seconds (``chunk`` rows at a time; one bit per pair)."""
    n = len(vectors)
    if n == 0:
        return []
    ent = [[_entry(x) for x in v] for v in vectors]
    k = len(ent[0])
    lo = np.array([[e[0] for e in row] for row in ent], dtype=float)
    hi = np.array([[e[1] for e in row] for row in ent], dtype=float)
    shown = np.array([[e[2] for e in row] for row in ent], dtype=float)
    group = np.full((n, k), -1, dtype=np.int64)                 # equal ids >= 0: totals leaving out the same lines
    for j in range(k):
        ids: Dict[str, int] = {}
        for i, row in enumerate(ent):
            if row[j][3] is not None:
                group[i, j] = ids.setdefault(row[j][3], len(ids))
    beaten = np.zeros(n, dtype=np.int64)                         # how many designs dominate each one
    rows = []
    for s0 in range(0, n, chunk):
        sl = slice(s0, s0 + chunk)
        same = (group[sl, None, :] == group[None, :, :]) & (group[sl, None, :] >= 0)
        le = np.where(same, shown[sl, None, :] <= shown[None, :, :], hi[sl, None, :] <= lo[None, :, :])
        lt = np.where(same, shown[sl, None, :] < shown[None, :, :], hi[sl, None, :] < lo[None, :, :])
        dom = le.all(axis=2) & lt.any(axis=2)                    # (c, n): row dominates column
        beaten += dom.sum(axis=0, dtype=np.int64)
        rows.append(np.packbits(dom, axis=1))
    packed = np.concatenate(rows)
    ranks = np.zeros(n, dtype=np.int64)
    front, r = np.flatnonzero(beaten == 0), 1
    while front.size:
        ranks[front] = r
        beaten[front] = -1
        for s0 in range(0, front.size, chunk):
            beaten -= np.unpackbits(packed[front[s0:s0 + chunk]], axis=1, count=n).sum(axis=0, dtype=np.int64)
        front, r = np.flatnonzero(beaten == 0), r + 1
    return [int(x) for x in ranks]


def rank(evaluations: Iterable[Dict[str, Any]], objectives: Sequence[Objective]) -> List[Dict[str, Any]]:
    """The evaluations in leaderboard order, each with ``feasible``, ``rank`` (None when infeasible), ``pareto`` and
    ``lower_bounds`` (the objectives whose value is an incomplete total, so its rank rests on a lower bound)."""
    evs = [dict(ev, rank=None) for ev in evaluations]           # a rank from an earlier ranking never carries over
    ok = [ev for ev in evs if feasible(ev) and objective_entries(ev, objectives) is not None]
    for ev, r in zip(ok, pareto_ranks([objective_entries(ev, objectives) for ev in ok])):
        ev["rank"] = r
    for ev in evs:
        ev["feasible"] = ev["rank"] is not None
        ev["pareto"] = ev["rank"] == 1
        ev["lower_bounds"] = [o.metric for o in objectives if ((ev.get("metrics") or {}).get(o.metric) or {}).get("incomplete")]

    def key(ev: Dict[str, Any]):
        vec = objective_vector(ev, objectives) or (float("inf"),)
        if ev["feasible"]:
            return (0, ev["rank"], vec[0] if vec else 0.0, str(ev.get("name")))
        counts = ev.get("counts") or {}
        return (1 if ev.get("verdict") != "error" else 2, counts.get("fail", 0), vec[0] if vec else 0.0, str(ev.get("name")))
    return sorted(evs, key=key)


def metric_columns(evaluations: Sequence[Dict[str, Any]], cfg: ExploreConfig) -> Dict[str, Dict[str, Any]]:
    """Display info for every metric that appears, objectives first, then the cost and mass, then the rest in the
    order they first appear. When no design buys anything (a parameter-only project: no BOM lines anywhere), the
    BOM's cost and mass, always 0, are left out of the columns unless they are objectives or constraints."""
    order: List[str] = [o.metric for o in cfg.objectives]
    for name in (cfg.cost_metric, "mass_kg"):
        if name not in order:
            order.append(name)
    for ev in evaluations:
        for name in ev.get("metrics") or {}:
            if name not in order:
                order.append(name)
    seen = {name for ev in evaluations for name in (ev.get("metrics") or {})}
    if not any((ev.get("bom") or {}).get("lines") for ev in evaluations):
        goals = {o.metric for o in cfg.objectives} | {c.metric for c in cfg.constraints}
        for name in (cfg.cost_metric, "mass_kg"):
            if name not in goals and all(((ev.get("metrics") or {}).get(name) or {}).get("source") == "bom"
                                         for ev in evaluations if name in (ev.get("metrics") or {})):
                seen.discard(name)
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
        # SOURCE_DATE_EPOCH or the last commit, not the wall clock: a rebuild writes the same page (#150)
        "generated": source_stamp(cfg.root, outputs=[cfg.out]),
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
    from cadagent.simulation.explore.design import candidates

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
    base_entries = objective_entries(base, cfg.objectives)
    options = swap_options(design, catalogue, cfg)

    def one(option: Tuple[str, str]) -> Dict[str, Any]:
        slot, part_id = option
        return evaluate_design(with_part(design, slot, part_id), catalogue, cfg, evaluator,
                               design_id=f"{base['id']}~{slot}={part_id}")
    if workers > 1 and len(options) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            try:
                results = list(pool.map(one, options))
            except KeyboardInterrupt:          # stop the running commands, or the pool would wait for them
                kill_running_evaluators()        # they run in their own session: Ctrl-C does not reach them
                pool.shutdown(wait=False, cancel_futures=True)
                raise
    else:
        results = [one(o) for o in options]
    out = []
    for (slot, part_id), ev in zip(options, results):
        values = {o.metric: value_of(ev["metrics"], o.metric) for o in cfg.objectives}
        delta, better, worse, unsure = {}, [], [], []
        for o in cfg.objectives:
            a = entry(ev["metrics"].get(o.metric), o.goal)
            b = entry((base.get("metrics") or {}).get(o.metric), o.goal)
            if a is None or b is None:
                continue
            delta[o.metric] = round(values[o.metric] - value_of(base["metrics"], o.metric), 6)
            a_ok, a_better = compare_entry(a, b)
            b_ok, b_better = compare_entry(b, a)
            if a_better:
                better.append(o.metric)
            elif b_better:
                worse.append(o.metric)
            elif not (a_ok and b_ok):             # neither is certainly better, and they are not certainly equal
                unsure.append(o.metric)
        cand = objective_entries(ev, cfg.objectives)
        out.append({"slot": slot, "from": _ref((design.get("parts") or {}).get(slot)), "to": part_id,
                    "name": display_name(catalogue[part_id]), "verdict": ev["verdict"], "feasible": feasible(ev),
                    "values": values, "delta": delta, "better": better, "worse": worse, "unsure": unsure,
                    "dominates": bool(feasible(ev) and cand and base_entries and dominates(cand, base_entries)),
                    "problems": [c["text"] for c in ev["checks"] if c["level"] == "fail"][:3]})
    out.sort(key=lambda s: (not s["dominates"], not s["feasible"], len(s["worse"]) - len(s["better"]), s["slot"], s["to"]))
    return out


# ----------------------------------------------------------------------------- comparing a project's designs

def design_ids(paths: Sequence[Path], root: Path) -> List[str]:
    """File stems, or where two stems clash the path from the root (``designs/a/std``), or for a file outside the
    root its stem and a short hash of its path; never an absolute path."""
    stems = [Path(p).stem for p in paths]
    out: List[str] = []
    for p, stem in zip(paths, stems):
        full = Path(p).resolve()
        if stems.count(stem) == 1:
            out.append(stem)
        elif full.is_relative_to(Path(root).resolve()):
            out.append(full.relative_to(Path(root).resolve()).with_suffix("").as_posix())
        else:
            out.append(f"{stem}-{hashlib.sha1(str(full).encode()).hexdigest()[:8]}")
    return out


def compare_designs(cfg: ExploreConfig, catalogue: Catalogue, evaluator: Optional[Evaluator] = None,
                    files: Optional[Sequence[Path]] = None, with_swaps: bool = False, workers: int = 1) -> Dict[str, Any]:
    """Evaluate the configured designs (or ``files``), optionally with every one-part swap (``workers`` at a time),
    and rank them."""
    from cadagent.simulation.explore.design import DesignError, load_design

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


def slim(comp: Dict[str, Any]) -> Dict[str, Any]:
    """The comparison without each design's BOM lines and evaluator ``data`` (the totals stay)."""
    designs = []
    for ev in comp["designs"]:
        ev = {k: v for k, v in ev.items() if k != "data"}
        if ev.get("bom"):
            ev["bom"] = {"currency": ev["bom"].get("currency"), "totals": ev["bom"].get("totals")}
        designs.append(ev)
    return {**comp, "designs": designs}


def write_comparison(comp: Dict[str, Any], out_dir: Path, json_name: str = "comparison.json",
                     html_name: str = "compare.html", cfg: Optional[ExploreConfig] = None,
                     cards: bool = True, slim_json: bool = False) -> Dict[str, Path]:
    """Write the JSON, the standalone HTML page and (for a design comparison) the site's design cards. ``slim_json``
    leaves BOM lines and evaluator data out of the JSON (the page still shows them for the designs it details)."""
    from cadagent.simulation.explore.page import render_page

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {"json": out_dir / json_name, "html": out_dir / html_name}
    _write(written["json"], to_json(slim(comp) if slim_json else comp))
    _write(written["html"], render_page(comp))
    if cards and cfg is not None:
        href = Path(os.path.relpath(written["html"], cfg.root)).as_posix()
        written["cards"] = out_dir / "designs.json"
        _write(written["cards"], to_json(site_cards(comp, cfg, href)))
    return written


def to_json(data: Any) -> str:
    """Strict JSON (no NaN or Infinity, which browsers' ``JSON.parse`` rejects; evaluations have been checked for them
    already), dates as ISO strings."""
    return json.dumps(data, indent=1, default=json_default, allow_nan=False) + "\n"


def _write(path: Path, text: str) -> None:
    """Write through a temporary file, so a page being served never shows half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)
