"""The verdict file every gate writes: pass/warn/fail per check, the evidence, and the assumptions.

Shape (``schema: cadagent.gate/1``), compatible with a ``cad.checks`` entry in
``cad-agent.yaml`` (``pass`` is the top-level boolean the report reads)::

    {"schema": "cadagent.gate/1", "gate": "wall", "pass": false, "status": "fail",
     "counts": {"pass": 3, "warn": 0, "fail": 1},
     "checks": [{"id": "wall:hopper", "status": "fail", "message": "...", "parts": ["hopper"],
                 "evidence": {...}}, ...],
     "findings": [<the checks that are not pass>],
     "exclusions": [{"parts": [...], "reason": "..."}],
     "limits": {"wall_mm": 2.4, ...},
     "assumptions": ["what was sampled, the tolerances, what is not checked"],
     "physical_fit_verified": false}

Rules: ``pass`` is false when any check fails *or when no check ran* (an empty gate
proves nothing). ``warn`` never fails the gate. A verdict must state at least one
assumption. ``physical_fit_verified`` is always false: a gate checks the model.
The file has no timestamp, so an unchanged run rewrites identical bytes.

**Inputs.** ``cad-agent gates`` adds ``inputs`` (``bind_inputs``): the digest of the geometry record the gate read
(``geometry_digest``), the content hash of every part instance, placed fastener and cavity in it, and digests of
the gate's declarations and options. ``stale_reason(verdict, record)`` says why a verdict no longer describes the
current record (or that it carries no inputs), so a verdict from an earlier build is never taken as current.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

SCHEMA = "cadagent.gate/1"
STATUSES = ("pass", "warn", "fail")


@dataclass
class Check:
    """One gate result. ``evidence`` holds the numbers and witness points behind ``status``."""
    id: str
    status: str
    message: str
    parts: Sequence[str] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"check {self.id!r}: status must be one of {STATUSES}, got {self.status!r}")
        if not self.id:
            raise ValueError("a check needs an id")

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"id": self.id, "status": self.status, "message": self.message}
        if self.parts:
            out["parts"] = list(self.parts)
        if self.evidence:
            out["evidence"] = _jsonable(self.evidence)
        return out


def verdict(gate: str, checks: Iterable[Check], *, assumptions: Sequence[str],
            limits: Optional[Mapping[str, Any]] = None, exclusions: Iterable[Mapping[str, Any]] = (),
            extra: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Assemble a verdict dict (see the module docstring). ``exclusions`` are the declared intended
    cases left out of the checks, each with its ``reason``; ``extra`` adds gate-specific keys."""
    if not gate:
        raise ValueError("a verdict needs a gate name")
    assumptions = [str(a) for a in assumptions if str(a).strip()]
    if not assumptions:
        raise ValueError(f"gate {gate!r}: state at least one assumption (what was sampled, the tolerances)")
    rows = [c if isinstance(c, Check) else Check(**c) for c in checks]
    ids = [c.id for c in rows]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"gate {gate!r}: duplicate check ids {dupes}")
    excl: List[Dict[str, Any]] = []
    for e in exclusions:
        if not str(e.get("reason", "")).strip():
            raise ValueError(f"gate {gate!r}: exclusion {dict(e)!r} has no reason")
        excl.append(_jsonable(dict(e)))
    counts = {s: sum(1 for c in rows if c.status == s) for s in STATUSES}
    status = "fail" if counts["fail"] or not rows else ("warn" if counts["warn"] else "pass")
    findings = [c.to_dict() for c in rows if c.status != "pass"]
    if not rows:
        findings.append({"id": f"{gate}:nothing-checked", "status": "fail",
                         "message": "no check ran, so the gate proves nothing"})
    out: Dict[str, Any] = {"schema": SCHEMA, "gate": gate, "pass": status != "fail", "status": status,
                           "counts": counts, "checks": [c.to_dict() for c in rows], "findings": findings,
                           "exclusions": excl, "limits": _jsonable(dict(limits or {})),
                           "assumptions": assumptions, "physical_fit_verified": False}
    if extra:
        clash = set(extra) & set(out)
        if clash:
            raise ValueError(f"gate {gate!r}: extra keys {sorted(clash)} would overwrite the verdict")
        out.update(_jsonable(dict(extra)))
    return out


def write_verdict(path: Any, data: Mapping[str, Any]) -> Path:
    """Write a verdict dict as indented JSON (parent directories created). Returns the path."""
    if data.get("schema") != SCHEMA or "pass" not in data:
        raise ValueError("write_verdict expects a dict from verdict()")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


# what in the geometry record says who built it or where, not what was built: left out of the digest, so a rebuild of
# the same geometry by another actor, or a declaration moved to another line, keeps verdicts current. Only these
# fields are dropped, at these places: a part, joint or fastener *named* like one of them is still digested.
# ``hash`` holds the hash recipe and, since #144, the platform the hashes were made on ({"recipe", "platform"}):
# where they were made, not what was built. The hashes themselves are in the parts and stay in the digest.
VOLATILE_TOP = frozenset({"actor", "parameters", "shapes_dir", "out_dir", "hash"})
VOLATILE_ENTRY = frozenset({"declared_at", "file", "actor"})  # in an entry of parts, cavities, joints, fasteners,
                                                               # steps (``actor``: who built a part, plan T11)
VOLATILE_KEYS = VOLATILE_TOP | VOLATILE_ENTRY


def digest_of(value: Any) -> str:
    """sha256 of the canonical JSON of ``value`` (sorted keys, no whitespace)."""
    text = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def _entry(value: Any) -> Any:
    """An entry of a record table without its volatile fields (and its instances' ``file``)."""
    if not isinstance(value, Mapping):
        return value
    out = {k: v for k, v in value.items() if k not in VOLATILE_ENTRY}
    if isinstance(out.get("instances"), list):
        out["instances"] = [_entry(i) for i in out["instances"]]
    return out


def _strip_volatile(record: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {k: v for k, v in record.items() if k not in VOLATILE_TOP}
    for table in ("parts", "cavities", "joints", "fasteners"):
        if isinstance(out.get(table), Mapping):
            out[table] = {name: _entry(v) for name, v in out[table].items()}
    asm = out.get("assembly")
    if isinstance(asm, Mapping) and isinstance(asm.get("steps"), list):
        out["assembly"] = {**asm, "steps": [_entry(s) for s in asm["steps"]]}
    return out


def geometry_digest(record: Mapping[str, Any]) -> str:
    """The digest of a geometry record (``exports/dossier-geometry.json``) as a gate input: every shape's content
    hash, box and volume, the flags, joints, fasteners and steps, without the fields in ``VOLATILE_TOP`` (top level)
    and ``VOLATILE_ENTRY`` (in each table entry, instance and step)."""
    return digest_of(_strip_volatile(record))


def record_hashes(record: Mapping[str, Any]) -> Dict[str, str]:
    """``{key: content hash}`` of every part instance, placed fastener and cavity in a geometry record (the same
    keys as ``BuildResult.content_hashes``), read from the JSON alone."""
    out: Dict[str, str] = {}
    for table in ("parts", "fasteners"):
        for info in (record.get(table) or {}).values():
            for inst in (info or {}).get("instances") or []:
                if isinstance(inst, Mapping) and inst.get("sha256") and inst.get("key"):
                    out[str(inst["key"])] = str(inst["sha256"])
    for name, info in (record.get("cavities") or {}).items():
        if isinstance(info, Mapping) and info.get("sha256"):
            out[str(name)] = str(info["sha256"])
    return dict(sorted(out.items()))


def bind_inputs(data: Dict[str, Any], record: Mapping[str, Any], *, record_file: str = "",
                declarations: Any = None, options: Any = None) -> Dict[str, Any]:
    """Add ``inputs`` to a verdict dict (in place, and returned): what it was computed from. ``declarations`` and
    ``options`` are digested (``digest_of``) when given, so a change to them makes the verdict stale too."""
    inputs: Dict[str, Any] = {"geometry": {"file": record_file, "digest": geometry_digest(record),
                                           "hashes": record_hashes(record)}, "toolkit": _toolkit_version()}
    if declarations is not None:
        inputs["declarations"] = digest_of(declarations)
    if options is not None:
        inputs["options"] = digest_of(options)
    data["inputs"] = inputs
    return data


def _toolkit_version() -> str:
    """Recorded with the inputs, not compared: an editable install keeps one version across code changes, and a
    release would otherwise void every verdict whether or not its gate changed. Rerun the gates after an upgrade."""
    try:
        from importlib.metadata import version
        return version("cad-agent")
    except Exception:
        return "unknown"


def stale_reason(data: Mapping[str, Any], record: Optional[Mapping[str, Any]], *, declarations: Any = None,
                 options: Any = None) -> Optional[str]:
    """None when the verdict's ``inputs`` match ``record`` (and, when given, the declarations and options digests);
    otherwise why not: no inputs, a different geometry (naming the keys whose content hash changed, appeared or
    went), or changed declarations or options. With no record, a verdict cannot be current."""
    inputs = data.get("inputs")
    if not isinstance(inputs, Mapping) or not isinstance(inputs.get("geometry"), Mapping):
        return "not bound to a geometry record (no inputs): rerun cad-agent gates"
    if record is None:
        return "no geometry record to compare with"
    geo = inputs["geometry"]
    if geo.get("digest") != geometry_digest(record):
        old = geo.get("hashes") if isinstance(geo.get("hashes"), Mapping) else {}
        new = record_hashes(record)
        changed = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
        what = (f"{len(changed)} shape(s) changed: {', '.join(changed[:6])}" + (" ..." if len(changed) > 6 else "")
                if changed else "the declarations in the record changed (flags, joints, fasteners or steps)")
        return f"geometry changed since this verdict ({what})"
    if declarations is not None and inputs.get("declarations") != digest_of(declarations):
        return "the gate's declarations changed since this verdict"
    if options is not None and inputs.get("options") != digest_of(options):
        return "the gate's options changed since this verdict"
    return None


def _jsonable(value: Any) -> Any:
    """Plain JSON types: tuples to lists, numpy scalars and arrays to Python, NaN refused."""
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if isinstance(value, float) and value != value:
        raise ValueError("NaN in verdict evidence; report the failure instead")
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        return value.item()
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    return value
