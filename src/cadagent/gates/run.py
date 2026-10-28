"""Running the integrity gates for a project: ``cad-agent gates`` (plan ``docs/design-process-plan.md`` §4, T14).

The parent side (``plan``, ``run_gates``, ``gate_rows``) needs no CAD kernel: it reads ``cad-agent.yaml``, the
geometry record (``exports/dossier-geometry.json``), the YAML dossier and the verdict files. Each gate runs in a
worker process of its own (``python -m cadagent.gates.run <root> <gate>``), which loads the geometry (with the
kernel), runs the gate, binds the verdict to its inputs (``verdict.bind_inputs``) and writes
``exports/gates/<gate>.json`` and ``.md``. A gate that crashes, hangs or raises gets a failing verdict that says
so, so an old verdict can never stand in for a run that did not finish. The dossier lint runs last, in this
process, because it reads the other verdicts.

Configuration, ``cad: gates:`` in ``cad-agent.yaml`` (every key optional)::

    gates:
      geometry: exports/dossier-geometry.json    # the record the build writes (this is the default)
      build: cad/build.py                        # build_module() it when the record is missing, or with --build
      declarations: dossier/gate-declarations.yaml   # plain-data declarations the YAML schema does not cover yet
      cache: .cadagent-cache/gates               # the pair cache (gitignored); --no-cache runs without it
      jobs: 2                                    # gates run at once, each in its own process
      timeout_s: 3600                            # per gate
      skip: {motion: "slow; run with --only motion before a review"}   # a reason is required
      assembly: {max_step_mm: 2.0, margin_mm: 1.0, service: true}      # per-gate options (OPTIONS below)

Declarations come from the dossier (``gates:``, interfaces, cards' ``contains`` and ``material.wall_mm``,
``assembly``) and the ``declarations`` file, passed as ``extra`` to the gates' ``*_from_build`` functions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from cadagent.gates.verdict import (SCHEMA, Check, bind_inputs, record_hashes, stale_reason, verdict,
                                    write_verdict)

GATES = ("connectivity", "containment", "fasteners", "motion", "assembly", "wall")   # geometric gates, run order
LINT = "dossier-lint"
NAMES = GATES + (LINT,)
GEOMETRY_FILE = "dossier-geometry.json"
DEFAULT_CACHE = Path(".cadagent-cache") / "gates"
LOG_DIR = Path(".cadagent-cache") / "logs"
CONFIG_KEYS = ("geometry", "build", "declarations", "cache", "jobs", "timeout_s", "skip") + GATES
# keys a declarations file may hold: what the gates' *_from_build functions read from `extra`
EXTRA_KEYS = ("grounded", "free_parts", "interfaces", "contains", "intended_overlaps", "ignore_pairs",
              "strict_interfaces", "max_joint_gap_mm", "fasteners", "tools", "motion_samples", "wall_mm")
_TOL = ("tol",)
_CONTAINMENT = ("support", "down", "support_mm", "mesh_samples", "seed", "deflection_mm", "max_points", "probe",
                "probe_deflection_mm", "probe_points", "probe_spacing_mm")
_MOTION = ("samples", "default_samples", "max_step_deg", "max_step_mm", "combine", "intended_contacts",
           "strict_contacts", "refine_steps", "max_poses", "containment", "containment_options")
_WALL = ("tol_mm", "max_rays", "grid", "spacing_mm", "max_grid", "parts")


def _access_fields() -> Tuple[str, ...]:
    from cadagent.gates.assembly import AccessOptions
    return tuple(f.name for f in fields(AccessOptions))


def _fastener_fields() -> Tuple[str, ...]:
    from cadagent.gates.fasteners import FastenerOptions
    return tuple(f.name for f in fields(FastenerOptions))


def options_allowed(gate: str) -> Tuple[str, ...]:
    """The option keys ``cad: gates: <gate>:`` accepts."""
    return {"connectivity": _TOL, "containment": _TOL + _CONTAINMENT, "motion": _TOL + _MOTION,
            "fasteners": _TOL + _fastener_fields(), "assembly": _TOL + ("service",) + _access_fields(),
            "wall": _WALL}[gate]


class GatesConfigError(ValueError):
    """``cad: gates:`` or a declarations file is malformed."""


@dataclass
class GatesConfig:
    root: Path
    geometry: Path
    build: Optional[Path] = None
    declarations: Optional[Path] = None
    cache: Path = DEFAULT_CACHE
    jobs: int = 1
    timeout_s: int = 3600
    skip: Dict[str, str] = field(default_factory=dict)
    options: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def rel(self, path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path)


def enabled(project: Any) -> bool:
    """Whether the project uses the gates: it has a ``dossier:`` or a ``gates:`` key. Without either, nothing in
    the pipeline changes."""
    return bool(getattr(project, "dossier", None)) or getattr(project, "gates", None) is not None


def gates_config(project: Any) -> GatesConfig:
    """Parse and check ``cad: gates:`` (paths resolved against the project root). Raises ``GatesConfigError``."""
    raw = dict(getattr(project, "gates", None) or {})
    root = Path(project.root).resolve()
    unknown = sorted(set(raw) - set(CONFIG_KEYS))
    if unknown:
        raise GatesConfigError(f"cad.gates: unknown key(s) {unknown}; known: {list(CONFIG_KEYS)}")

    def path(key: str, default: Optional[Path] = None) -> Optional[Path]:
        value = raw.get(key)
        if value in (None, ""):
            return default
        if not isinstance(value, str):
            raise GatesConfigError(f"cad.gates.{key} must be a path, got {value!r}")
        return (root / value).resolve()

    cfg = GatesConfig(root=root, geometry=path("geometry", Path(project.exports_dir) / GEOMETRY_FILE),
                      build=path("build"), declarations=path("declarations"),
                      cache=path("cache", root / DEFAULT_CACHE))
    for key in ("jobs", "timeout_s"):
        if key in raw:
            value = raw[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise GatesConfigError(f"cad.gates.{key} must be a positive integer, got {value!r}")
            setattr(cfg, key, value)
    skip = raw.get("skip") or {}
    if not isinstance(skip, Mapping):
        raise GatesConfigError("cad.gates.skip maps a gate to the reason it is skipped: {motion: \"why\"}")
    for gate, reason in skip.items():
        if gate not in NAMES:
            raise GatesConfigError(f"cad.gates.skip: {gate!r} is not a gate; gates: {list(NAMES)}")
        if not str(reason or "").strip():
            raise GatesConfigError(f"cad.gates.skip.{gate} needs a reason (a skipped gate is an explained exclusion)")
        cfg.skip[gate] = str(reason).strip()
    for gate in GATES:
        opts = raw.get(gate)
        if opts is None:
            continue
        if not isinstance(opts, Mapping):
            raise GatesConfigError(f"cad.gates.{gate} must be a mapping of options")
        bad = sorted(set(opts) - set(options_allowed(gate)))
        if bad:
            raise GatesConfigError(f"cad.gates.{gate}: unknown option(s) {bad}; known: {list(options_allowed(gate))}")
        try:
            gate_kwargs(gate, opts)
        except (TypeError, ValueError) as exc:
            raise GatesConfigError(f"cad.gates.{gate}: {exc}") from exc
        cfg.options[gate] = dict(opts)
    if cfg.build is not None and cfg.geometry.name != GEOMETRY_FILE:
        raise GatesConfigError(f"cad.gates.geometry must be named {GEOMETRY_FILE} when cad.gates.build is set "
                               "(build_module writes that name)")
    return cfg


def gate_kwargs(gate: str, opts: Mapping[str, Any]) -> Dict[str, Any]:
    """Options from ``cad: gates: <gate>:`` as keyword arguments of the gate's function: ``tol`` becomes
    ``Tolerances``, the assembly gate's ``AccessOptions`` and the fastener gate's ``FastenerOptions`` fields are
    gathered into ``options=``, and the wall gate's ``parts`` (extra walls) is left out (the adapter reads it)."""
    kw = {k: v for k, v in opts.items() if not (gate == "wall" and k == "parts")}
    if "tol" in kw:
        from cadagent.gates.relations import Tolerances
        if not isinstance(kw["tol"], Mapping):
            raise ValueError("tol must be a mapping of Tolerances fields (touch_mm, overlap_mm3, ...)")
        kw["tol"] = Tolerances(**kw["tol"])
    if gate == "assembly":
        from cadagent.gates.assembly import AccessOptions
        sub = {k: kw.pop(k) for k in _access_fields() if k in kw}
        kw["options"] = AccessOptions(**sub)
    if gate == "fasteners":
        from cadagent.gates.fasteners import FastenerOptions
        sub = {k: kw.pop(k) for k in _fastener_fields() if k in kw}
        if sub.get("stock_lengths_mm") is not None:
            sub["stock_lengths_mm"] = tuple(float(x) for x in sub["stock_lengths_mm"])
        kw["options"] = FastenerOptions(**sub)
    if gate == "wall" and "parts" in opts and not isinstance(opts["parts"], Mapping):
        raise ValueError("parts maps a part to its minimum wall in mm")
    return kw


# ------------------------------------------------------------------------------------------------- inputs

def load_extra(cfg: GatesConfig) -> Dict[str, Any]:
    """The declarations file as a mapping ({} when none is configured). Raises ``GatesConfigError``."""
    if cfg.declarations is None:
        return {}
    path = cfg.declarations
    try:
        text = path.read_text()
    except OSError as exc:
        raise GatesConfigError(f"cad.gates.declarations: cannot read {cfg.rel(path)}: {exc}") from exc
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            import yaml
            data = yaml.safe_load(text)
    except ValueError as exc:
        raise GatesConfigError(f"{cfg.rel(path)}: {exc}") from exc
    data = data or {}
    if not isinstance(data, dict):
        raise GatesConfigError(f"{cfg.rel(path)} must be a mapping of declarations")
    unknown = sorted(set(data) - set(EXTRA_KEYS))
    if unknown:
        raise GatesConfigError(f"{cfg.rel(path)}: unknown key(s) {unknown}; known: {list(EXTRA_KEYS)}")
    return data


def load_record(cfg: GatesConfig) -> Optional[Dict[str, Any]]:
    """The geometry record as JSON (no shapes, no kernel), or None when it does not exist."""
    if not cfg.geometry.is_file():
        return None
    try:
        data = json.loads(cfg.geometry.read_text())
    except (OSError, ValueError) as exc:
        raise GatesConfigError(f"cannot read the geometry record {cfg.rel(cfg.geometry)}: {exc}") from exc
    if not isinstance(data, dict):
        raise GatesConfigError(f"{cfg.rel(cfg.geometry)} is not a geometry record")
    return data


def load_dossier(project: Any) -> Any:
    """The loaded YAML dossier (``strict=False``: its errors are the lint's), or None."""
    if not getattr(project, "dossier", None):
        return None
    from cadagent.dossier.load import DossierError, load_project_dossier
    try:
        return load_project_dossier(project, strict=False)
    except DossierError:
        return None                 # the top file is unreadable: the lint reports it


def declarations(dossier: Any, extra: Mapping[str, Any]) -> Dict[str, Any]:
    """What the gates read from the dossier and the declarations file, as plain data: the digest input that makes
    a verdict stale when a declaration changes. Interface datums, loads and texts are left out (no gate reads
    them)."""
    out: Dict[str, Any] = {"extra": dict(extra)}
    if dossier is not None:
        out["gates"] = dossier.gates.to_dict()
        out["interfaces"] = [{"id": i.id, "between": list(i.between), "kind": i.kind, "clearance": i.clearance}
                             for i in dossier.interfaces.values()]
        out["cards"] = {pid: {"contains": [c.to_dict() for c in card.contains],
                              "wall_mm": card.material.wall_mm if card.material else None}
                        for pid, card in sorted(dossier.parts.items())}
        out["assembly"] = [s.to_dict() for s in dossier.assembly]
    return out


def contains_list(dossier: Any, extra: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Every ``contains`` declaration (cards, then the declarations file), one per container, cavity and item."""
    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    if dossier is not None:
        for pid, card in dossier.parts.items():
            for c in card.contains:
                out.setdefault((pid, c.cavity, c.what), {"container": pid, "cavity": c.cavity, "what": c.what,
                                                          "count": c.count, "free": c.free})
    for c in extra.get("contains") or []:
        c = dict(c)
        out.setdefault((str(c.get("container")), str(c.get("cavity")), str(c.get("what"))), c)
    return list(out.values())


def walls(record: Mapping[str, Any], dossier: Any, extra: Mapping[str, Any],
          options: Mapping[str, Any]) -> Dict[str, float]:
    """Part -> minimum wall (mm): cards' ``material.wall_mm``, then the declarations file's ``wall_mm``, then
    ``cad: gates: wall: parts:`` (later wins)."""
    out: Dict[str, float] = {}
    if dossier is not None:
        for pid, card in dossier.parts.items():
            if card.material is not None and card.material.wall_mm is not None:
                out[pid] = float(card.material.wall_mm)
    for source in (extra.get("wall_mm") or {}, options.get("parts") or {}):
        if not isinstance(source, Mapping):
            raise GatesConfigError("wall_mm maps a part to its minimum wall in mm")
        try:
            out.update({str(k): float(v) for k, v in source.items()})
        except (TypeError, ValueError) as exc:
            raise GatesConfigError(f"wall_mm maps a part to its minimum wall in mm: {exc}") from exc
    return dict(sorted(out.items()))


@dataclass
class Planned:
    """One gate in a run: ``state`` is ``run``, ``na`` (nothing it could check) or ``skip`` (configured, with
    the reason in ``reason``)."""
    gate: str
    state: str
    reason: str = ""


def applies(gate: str, record: Optional[Mapping[str, Any]], dossier: Any, extra: Mapping[str, Any],
            cfg: GatesConfig) -> Tuple[bool, str]:
    """Whether a gate has something to check, and if not, why. Read from the record and declarations alone."""
    rec = record or {}
    if gate == "connectivity":
        return bool(rec.get("parts")), "no parts in the geometry record"
    if gate == "containment":
        return bool(contains_list(dossier, extra)), "no contains declaration (cards or the declarations file)"
    if gate == "fasteners":
        return bool(rec.get("fasteners")), "no fastener in the geometry record"
    if gate == "motion":
        moving = [j for j in (rec.get("joints") or {}).values() if (j or {}).get("kind") != "fixed"]
        return bool(moving), "no joint that moves in the geometry record"
    if gate == "assembly":
        steps = ((rec.get("assembly") or {}).get("steps") or []) or (getattr(dossier, "assembly", None) or [])
        return bool(steps), "no assembly steps (registry or dossier)"
    if gate == "wall":
        return bool(walls(rec, dossier, extra, cfg.options.get("wall", {}))), \
            "no part declares material.wall_mm"
    raise KeyError(gate)


def plan(project: Any, cfg: GatesConfig, record: Optional[Mapping[str, Any]], dossier: Any,
         extra: Mapping[str, Any], *, only: Sequence[str] = (), skip: Sequence[str] = ()) -> List[Planned]:
    """Every gate with what this run does with it: run, not applicable, or skipped (``cad.gates.skip``,
    ``--skip``). ``only`` restricts the run to those gates (the others are left out of the plan)."""
    for name in list(only) + list(skip):
        if name not in NAMES:
            raise GatesConfigError(f"unknown gate {name!r}; gates: {list(NAMES)}")
    out = []
    for gate in NAMES:
        if only and gate not in only:
            continue
        if gate == LINT and not getattr(project, "dossier", None):
            if only:
                out.append(Planned(gate, "na", "no dossier: key"))
            continue
        if gate in skip:
            out.append(Planned(gate, "skip", "--skip"))
            continue
        if gate in cfg.skip and gate not in only:
            out.append(Planned(gate, "skip", cfg.skip[gate]))
            continue
        if gate == LINT:
            out.append(Planned(gate, "run"))
            continue
        ok, why = applies(gate, record, dossier, extra, cfg)
        out.append(Planned(gate, "run" if ok else "na", "" if ok else why))
    return out


def expected_inputs(gate: str, cfg: GatesConfig, dossier: Any, extra: Mapping[str, Any]) -> Dict[str, Any]:
    """The declarations and options a verdict of ``gate`` is bound to (``bind_inputs``/``stale_reason``)."""
    return {"declarations": declarations(dossier, extra), "options": cfg.options.get(gate, {})}


# ------------------------------------------------------------------------------------------------- markdown

def _cell(text: Any) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def verdict_markdown(data: Mapping[str, Any]) -> str:
    """A readable copy of a verdict: status, counts, the findings, exclusions, assumptions and limits; the
    fastener table and the assembly step table for those gates."""
    gate = data.get("gate", "?")
    c = data.get("counts") or {}
    lines = [f"# Gate: {gate}", "",
             f"**{str(data.get('status', '?')).upper()}** · {sum(c.values()) if c else 0} checks: "
             f"{c.get('pass', 0)} pass, {c.get('warn', 0)} warn, {c.get('fail', 0)} fail · "
             "a check of the CAD model against its declarations; physical fit not verified", ""]
    geo = ((data.get("inputs") or {}).get("geometry") or {})
    if geo:
        lines += [f"Geometry: `{geo.get('file', '')}` digest `{str(geo.get('digest', ''))[:16]}`, "
                  f"{len(geo.get('hashes') or {})} shapes", ""]
    findings = data.get("findings") or []
    lines += ["## Findings", ""]
    if findings:
        lines += ["| Check | Status | Parts | Message |", "|---|---|---|---|"]
        lines += [f"| `{_cell(f.get('id'))}` | {_cell(f.get('status'))} | {_cell(', '.join(f.get('parts') or []))} "
                  f"| {_cell(f.get('message'))} |" for f in findings]
    else:
        lines.append("None.")
    if data.get("exclusions"):
        lines += ["", "## Exclusions (declared)", ""]
        lines += [f"- {', '.join(map(str, e.get('parts') or []))}: {e.get('reason', '')}" for e in data["exclusions"]]
    if data.get("not_checked"):
        lines += ["", "## Not checked", ""] + [f"- {_cell(x)}" for x in data["not_checked"]]
    lines += ["", "## Assumptions", ""] + [f"- {a}" for a in data.get("assumptions") or []]
    limits = data.get("limits") or {}
    if limits:
        lines += ["", "## Limits", ""] + [f"- `{k}`: {json.dumps(v)}" for k, v in limits.items()]
    text = "\n".join(lines) + "\n"
    if gate == "fasteners" and data.get("table"):
        from cadagent.gates.fasteners import table_markdown
        text += "\n## Fasteners\n\n" + table_markdown(data)
    if gate == "assembly" and data.get("steps"):
        from cadagent.gates.assembly import steps_markdown
        text += "\n## Assembly sequence\n\n" + steps_markdown(data)
    return text


def write_outputs(gates_dir: Path, data: Mapping[str, Any]) -> Path:
    """``<gate>.json`` and ``<gate>.md`` (and the connectivity graph as ``.dot``) in ``gates_dir``."""
    path = write_verdict(Path(gates_dir) / f"{data['gate']}.json", data)
    path.with_suffix(".md").write_text(verdict_markdown(data))
    if data.get("gate") == "connectivity" and data.get("graph"):
        from cadagent.gates.connectivity import write_dot
        write_dot(data, path.with_suffix(".dot"))
    return path


def remove_outputs(gates_dir: Path, gate: str) -> None:
    for suffix in (".json", ".md", ".dot"):
        (Path(gates_dir) / f"{gate}{suffix}").unlink(missing_ok=True)


def crash_verdict(gate: str, reason: str) -> Dict[str, Any]:
    """The failing verdict written for a gate that did not run to the end."""
    return verdict(gate, [Check(f"{gate}:run", "fail", f"the gate did not finish: {reason}")],
                   assumptions=["the gate did not run to the end, so nothing was checked"])


# ------------------------------------------------------------------------------------------------- the worker

def _ensure_cache_ignored(root: Path) -> None:
    base = root / ".cadagent-cache"
    base.mkdir(parents=True, exist_ok=True)
    ignore = base / ".gitignore"
    if not ignore.is_file():
        ignore.write_text("# gate pair cache and logs: regenerated, never committed\n*\n")


def run_one(project: Any, gate: str, *, no_cache: bool = False) -> Dict[str, Any]:
    """Run one geometric gate in this process (needs the CAD kernel) and write its verdict, bound to its inputs.
    The worker entry point; ``run_gates`` calls it in a process of its own."""
    from cadagent.dossier.registry import load_geometry
    from cadagent.gates.cache import PairCache

    cfg = gates_config(project)
    extra = load_extra(cfg)
    dossier = load_dossier(project)
    result = load_geometry(cfg.geometry)
    opts = cfg.options.get(gate, {})
    kwargs = gate_kwargs(gate, opts)
    cache = None
    if not no_cache and gate != "wall":
        _ensure_cache_ignored(cfg.root)
        cache = PairCache(cfg.cache)
    data = ADAPTERS[gate](result, dossier, extra, cache, kwargs, opts)
    exp = expected_inputs(gate, cfg, dossier, extra)
    bind_inputs(data, result.geometry, record_file=cfg.rel(cfg.geometry), **exp)
    write_outputs(Path(project.exports_dir) / "gates", data)
    return data


def _tol_default(dossier: Any, kwargs: Dict[str, Any]) -> None:
    if dossier is not None and "tol" not in kwargs:
        from cadagent.gates.relations import Tolerances
        kwargs["tol"] = Tolerances(touch_mm=float(dossier.gates.touch_tol_mm))


def _overlaps(dossier: Any, extra: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = [dict(o) for o in extra.get("intended_overlaps") or []]
    if dossier is not None:
        out += [{"parts": list(p.parts), "reason": p.reason} for p in dossier.gates.intended_overlaps]
    seen, unique = set(), []
    for o in out:
        key = frozenset(map(str, o.get("parts") or []))
        if key not in seen:
            seen.add(key)
            unique.append(o)
    return unique


def _connectivity(result, dossier, extra, cache, kwargs, opts):
    from cadagent.gates.connectivity import connectivity_from_build
    return connectivity_from_build(result, dossier, extra, cache=cache, **kwargs)


def _containment(result, dossier, extra, cache, kwargs, opts):
    from cadagent.gates.containment import containment_gate
    from cadagent.gates.relations import Assembly
    _tol_default(dossier, kwargs)
    return containment_gate(Assembly.from_build(result), contains_list(dossier, extra), cache=cache,
                            exclusions=_overlaps(dossier, extra), **kwargs)


def _fasteners(result, dossier, extra, cache, kwargs, opts):
    from cadagent.gates.fasteners import fastener_gate_from_build
    _tol_default(dossier, kwargs)
    return fastener_gate_from_build(result, dossier, extra, cache=cache, **kwargs)


def _motion(result, dossier, extra, cache, kwargs, opts):
    from cadagent.gates.motion import motion_from_build
    return motion_from_build(result, dossier, extra, cache=cache, **kwargs)


def _assembly(result, dossier, extra, cache, kwargs, opts):
    from cadagent.gates.assembly import assembly_from_build
    _tol_default(dossier, kwargs)
    return assembly_from_build(result, dossier, extra, cache=cache, **kwargs)


def _wall(result, dossier, extra, cache, kwargs, opts):
    from cadagent.gates.wall import wall_gate
    declared = walls(result.geometry, dossier, extra, opts)
    missing = sorted(set(declared) - set(result.parts))
    if missing:
        raise ValueError(f"a minimum wall is declared for {missing}, which the geometry record does not have")
    parts: Dict[str, Dict[str, Any]] = {}
    for name, wall_mm in declared.items():
        info = result.geometry["parts"][name]
        seen = set()
        shapes = result.parts[name]
        for i, (shape, inst) in enumerate(zip(shapes, info.get("instances") or [{}] * len(shapes))):
            box = inst.get("bbox") or {}
            size = tuple(round(b - a, 4) for a, b in zip(box.get("min", ()), box.get("max", ())))
            copy_key = (round(float(inst.get("volume_mm3") or 0.0), 3), size)
            if inst and copy_key in seen:
                continue                         # a copy of an instance already measured (same volume and size)
            seen.add(copy_key)
            key = name if len(shapes) == 1 else f"{name}#{i}"
            parts[key] = {"wall_mm": wall_mm, "mesh": shape, "shape": shape}
    return wall_gate(parts, **kwargs)


ADAPTERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "connectivity": _connectivity, "containment": _containment, "fasteners": _fasteners, "motion": _motion,
    "assembly": _assembly, "wall": _wall,
}


def build_geometry(project: Any) -> Path:
    """``build_module(cad.gates.build)`` into the record's directory (needs the kernel). Returns the record path."""
    from cadagent.dossier.registry import build_module
    cfg = gates_config(project)
    if cfg.build is None:
        raise GatesConfigError("cad.gates.build is not set: name the build script that registers the geometry")
    out_dir = cfg.rel(cfg.geometry.parent)
    result = build_module(cfg.build, out_dir=out_dir, root=cfg.root)
    return Path(result.path)


# ------------------------------------------------------------------------------------------------- the parent

@dataclass
class GateRun:
    """The outcome of one gate in a run: ``status`` is ``pass``, ``fail``, ``na`` or ``skip``."""
    gate: str
    status: str
    message: str = ""
    seconds: float = 0.0
    log: str = ""
    counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class RunResult:
    rows: List[GateRun]
    seconds: float
    record: str = ""
    built: bool = False

    @property
    def passed(self) -> bool:
        return not any(r.status == "fail" for r in self.rows)


def worker_command(root: Path, gate: str, no_cache: bool = False) -> List[str]:
    """The command that runs one gate (``gate`` may be ``--build``) for the project at ``root``: this interpreter,
    so the gates run with the same toolkit as the command that reads them."""
    cmd = [sys.executable, "-m", "cadagent.gates.run", str(root), gate]
    return cmd + (["--no-cache"] if no_cache else [])


def _env() -> Dict[str, str]:
    import cadagent
    pkg_root = str(Path(cadagent.__file__).resolve().parents[1])
    path = os.environ.get("PYTHONPATH", "")
    return dict(os.environ, PYTHONUNBUFFERED="1",
                PYTHONPATH=pkg_root + (os.pathsep + path if path else ""))


def _spawn(cfg: GatesConfig, gate: str, cmd: List[str]) -> Tuple[int, str, float, str]:
    """Run a worker; returns (exit code or -1 for a timeout or failure to start, reason, seconds, log path)."""
    log_dir = cfg.root / LOG_DIR
    _ensure_cache_ignored(cfg.root)
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"gate-{gate.lstrip('-')}.log"
    started = time.monotonic()
    try:
        with open(log, "w") as handle:
            proc = subprocess.run(cmd, cwd=cfg.root, env=_env(), stdout=handle, stderr=subprocess.STDOUT,
                                  timeout=cfg.timeout_s)
        code, reason = proc.returncode, "" if proc.returncode in (0, 1) else f"exit code {proc.returncode}"
    except subprocess.TimeoutExpired:
        code, reason = -1, f"timed out after {cfg.timeout_s} s (cad.gates.timeout_s)"
    except OSError as exc:
        code, reason = -1, f"could not start {cmd[0]}: {exc}"
    return code, reason, round(time.monotonic() - started, 2), cfg.rel(log)


def _tail(path: Path, lines: int = 6) -> str:
    try:
        return " | ".join(path.read_text(errors="replace").strip().splitlines()[-lines:])
    except OSError:
        return ""


def _summary(data: Mapping[str, Any]) -> str:
    c = data.get("counts") or {}
    text = f"{sum(c.values())} checks, {c.get('warn', 0)} warning(s)"
    fails = [f.get("id", "") for f in data.get("findings") or [] if f.get("status") == "fail"]
    if fails:
        text = f"{len(fails)} failed: {', '.join(fails[:3])}" + (" ..." if len(fails) > 3 else "") + f" ({text})"
    return text


def run_gates(project: Any, *, only: Sequence[str] = (), skip: Sequence[str] = (), jobs: Optional[int] = None,
              no_cache: bool = False, build: bool = False, dry_run: bool = False,
              progress: Callable[[str], None] = lambda s: None) -> RunResult:
    """Run every gate that applies (``plan``), each in a worker process, ``jobs`` at a time, then the dossier lint.
    Raises ``GatesConfigError`` when the project cannot be gated (bad config, no geometry record and no build)."""
    started = time.monotonic()
    cfg = gates_config(project)
    gates_dir = Path(project.exports_dir) / "gates"
    built = False
    wants_geometry = not only or any(g != LINT for g in only)
    if wants_geometry and not dry_run and (build or (cfg.build is not None and not cfg.geometry.is_file())):
        if cfg.build is None:
            raise GatesConfigError("--build needs cad.gates.build (the script that registers the geometry)")
        progress(f"build: {cfg.rel(cfg.build)} -> {cfg.rel(cfg.geometry)}")
        code, reason, secs, log = _spawn(cfg, "--build", worker_command(cfg.root, "--build"))
        if code != 0:
            why = reason or f"exit code {code}"
            return RunResult([GateRun("build", "fail", f"{why}; log {log}: {_tail(cfg.root / log)}", secs, log)],
                             round(time.monotonic() - started, 2))
        built = True
    record = load_record(cfg)
    if record is None and wants_geometry:
        raise GatesConfigError(f"no geometry record at {cfg.rel(cfg.geometry)}: run the build that registers the "
                               "parts (cad-agent build), or set cad.gates.build (docs/gates.md)")
    extra = load_extra(cfg)
    dossier = load_dossier(project)
    planned = plan(project, cfg, record, dossier, extra, only=only, skip=skip)
    rows: Dict[str, GateRun] = {}
    for p in planned:
        if p.state == "na":
            rows[p.gate] = GateRun(p.gate, "na", p.reason)
            if not dry_run and p.gate != LINT:
                remove_outputs(gates_dir, p.gate)      # an old verdict of a gate with nothing to check misleads
        elif p.state == "skip":
            rows[p.gate] = GateRun(p.gate, "skip", p.reason)
    todo = [p.gate for p in planned if p.state == "run" and p.gate != LINT]
    if dry_run:
        for g in todo:
            rows[g] = GateRun(g, "run", "would run")
        if any(p.gate == LINT and p.state == "run" for p in planned):
            rows[LINT] = GateRun(LINT, "run", "would run")
        return RunResult([rows[p.gate] for p in planned], 0.0, cfg.rel(cfg.geometry), built)
    for g in todo:
        remove_outputs(gates_dir, g)
    jobs = max(1, int(jobs or cfg.jobs))
    if todo:
        progress(f"running {len(todo)} gate(s) on {cfg.rel(cfg.geometry)}"
                 + (f", {min(jobs, len(todo))} at a time" if jobs > 1 and len(todo) > 1 else ""))

    def one(gate: str) -> GateRun:
        code, reason, secs, log = _spawn(cfg, gate, worker_command(cfg.root, gate, no_cache))
        path = gates_dir / f"{gate}.json"
        data = None
        if path.is_file() and not reason:
            try:
                data = json.loads(path.read_text())
            except ValueError:
                data = None
        if data is None or data.get("schema") != SCHEMA:
            why = reason or f"exit code {code}, no verdict written"
            data = crash_verdict(gate, f"{why}; log {log}: {_tail(cfg.root / log)}")
            bind_inputs(data, record or {}, record_file=cfg.rel(cfg.geometry),
                        **expected_inputs(gate, cfg, dossier, extra))
            write_outputs(gates_dir, data)
        status = "pass" if data.get("pass") is True else "fail"
        return GateRun(gate, status, _summary(data), secs, log, dict(data.get("counts") or {}))

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(one, g): g for g in todo}
        for fut in as_completed(futures):
            row = fut.result()
            rows[row.gate] = row
            progress(f"  {row.status.upper():<4} {row.gate:<13} {row.seconds:6.1f} s  {row.message}"
                     + (f" · log {row.log}" if row.status == "fail" and row.log else ""))
    if any(p.gate == LINT and p.state == "run" for p in planned):
        rows[LINT] = run_lint(project)
        progress(f"  {rows[LINT].status.upper():<4} {LINT:<13} {rows[LINT].seconds:6.1f} s  {rows[LINT].message}")
    return RunResult([rows[p.gate] for p in planned], round(time.monotonic() - started, 2),
                     cfg.rel(cfg.geometry), built)


def run_lint(project: Any) -> GateRun:
    """The dossier lint (kernel-free), written as ``dossier-status.json`` and ``gates/dossier-lint.json``."""
    from cadagent.dossier.lint import lint_project, write_outputs as write_lint
    started = time.monotonic()
    res = lint_project(project)
    write_lint(res, project.exports_dir)
    gated = sum(1 for s in res.sections.values() if s["status"] not in ("draft", "built"))
    msg = f"{len(res.errors)} error(s), {len(res.warnings)} warning(s); {gated}/{len(res.sections)} section(s) gated"
    if res.errors:
        msg += ": " + ", ".join(dict.fromkeys(f.code for f in res.errors[:20]))
    return GateRun(LINT, "pass" if res.passed else "fail", msg, round(time.monotonic() - started, 2),
                   counts={"fail": len(res.errors), "warn": len(res.warnings)})


# ------------------------------------------------------------------------------------------------- collection

def gate_rows(project: Any) -> List[Dict[str, Any]]:
    """The gates as report rows (``cad-agent check``), kernel-free: one per gate in the plan. A gate that applies
    fails when its verdict is missing, unreadable, stale (its inputs differ from the current geometry record,
    declarations or options) or failing; a gate with nothing to check, or skipped with a reason, is a skip row.
    Other verdict files in ``exports/gates/`` (a project's own gates) are collected too; the dossier lint is the
    ``cad-dossier`` feature's."""
    gates_dir = Path(project.exports_dir) / "gates"
    try:
        cfg = gates_config(project)
        record = load_record(cfg)
        extra = load_extra(cfg)
    except GatesConfigError as exc:
        return [{"name": "gates configuration", "status": "fail", "message": str(exc), "error": str(exc)}]
    if record is None:
        msg = f"no geometry record ({cfg.rel(cfg.geometry)}): run the build, then cad-agent gates"
        return [{"name": "geometry record", "status": "fail", "message": msg, "error": msg}]
    dossier = load_dossier(project)
    rows: List[Dict[str, Any]] = []
    shapes = len(record_hashes(record))
    try:
        planned = plan(project, cfg, record, dossier, extra)
    except (GatesConfigError, TypeError, ValueError) as exc:
        return [{"name": "gates configuration", "status": "fail", "message": str(exc), "error": str(exc)}]
    for p in planned:
        if p.gate == LINT:
            continue
        name = f"gate {p.gate}"
        if p.state != "run":
            rows.append({"name": name, "status": "skip",
                         "message": ("not applicable: " if p.state == "na" else "skipped: ") + p.reason})
            continue
        rows.append(_verdict_row(name, gates_dir / f"{p.gate}.json", record,
                                 expected_inputs(p.gate, cfg, dossier, extra), shapes))
    known = set(NAMES)
    if gates_dir.is_dir():
        for path in sorted(gates_dir.glob("*.json")):
            if path.stem not in known:
                rows.append(_verdict_row(f"gate {path.stem}", path, record, {}, shapes))
    return rows


def _verdict_row(name: str, path: Path, record: Mapping[str, Any], expected: Mapping[str, Any],
                 shapes: int) -> Dict[str, Any]:
    def fail(msg: str) -> Dict[str, Any]:
        return {"name": name, "status": "fail", "message": msg, "error": msg, "file": str(path)}
    if not path.is_file():
        return fail(f"not run: {path.name} missing (cad-agent gates)")
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return fail(f"unreadable verdict {path.name}: {exc}")
    if not isinstance(data, dict) or "pass" not in data:
        return fail(f"{path.name} is not a gate verdict (no `pass`)")
    stale = stale_reason(data, record, **expected)
    if stale:
        return fail(f"stale: {stale}")
    msg = _summary(data) + f" · {shapes} shapes · physical fit not verified"
    if data.get("pass") is not True:
        return fail(msg)
    return {"name": name, "status": "pass", "message": msg, "file": str(path)}


def site_counts(root: Path, exports: str = "exports") -> Optional[Dict[str, int]]:
    """``{"pass", "total", "stale"}`` over the gate verdicts in ``<root>/<exports>/gates/`` (the lint's left out):
    a verdict counts as passing only when it passes and its geometry matches the current record. None when there
    are no verdicts. For the site overview, which reads files only."""
    gates_dir = Path(root) / exports / "gates"
    paths = [p for p in sorted(gates_dir.glob("*.json")) if p.stem != LINT] if gates_dir.is_dir() else []
    if not paths:
        return None
    try:
        record = json.loads((Path(root) / exports / GEOMETRY_FILE).read_text())
    except (OSError, ValueError):
        record = None
    out = {"pass": 0, "total": 0, "stale": 0}
    for path in paths:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
        out["total"] += 1
        if not isinstance(data, dict) or stale_reason(data, record):
            out["stale"] += 1
        elif data.get("pass") is True:
            out["pass"] += 1
    return out


# ------------------------------------------------------------------------------------------------- worker main

def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m cadagent.gates.run <root> <gate|--build> [--no-cache]``: the worker. Exit 0 pass, 1 fail, 2 an
    error before a verdict could be written (the parent then writes a failing one with the log tail)."""
    import traceback

    from cadagent.project import load_project
    args = list(sys.argv[1:] if argv is None else argv)
    no_cache = "--no-cache" in args
    args = [a for a in args if a != "--no-cache"]
    if len(args) != 2:
        print("usage: python -m cadagent.gates.run <project root> <gate|--build> [--no-cache]", file=sys.stderr)
        return 2
    root, gate = args
    try:
        project = load_project(root)
        if gate == "--build":
            path = build_geometry(project)
            print(f"build: wrote {path}")
            return 0
        if gate not in ADAPTERS:
            print(f"unknown gate {gate!r}; gates: {list(ADAPTERS)}", file=sys.stderr)
            return 2
        started = time.monotonic()
        data = run_one(project, gate, no_cache=no_cache)
        print(f"{gate}: {data['status']} ({_summary(data)}) in {time.monotonic() - started:.1f} s")
        return 0 if data["pass"] else 1
    except Exception:
        traceback.print_exc()
        return 2


__all__ = ["GATES", "LINT", "NAMES", "GatesConfig", "GatesConfigError", "GateRun", "Planned", "RunResult",
           "enabled", "gates_config", "gate_kwargs", "options_allowed", "load_extra", "load_record", "plan",
           "applies", "declarations", "expected_inputs", "run_gates", "run_one", "run_lint", "gate_rows",
           "verdict_markdown", "write_outputs", "crash_verdict", "worker_command", "build_geometry", "walls",
           "site_counts"]


if __name__ == "__main__":
    _code = _main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_code)         # skip interpreter teardown: OCP can crash there after the verdict is written
