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

**Not in the model.** A gate sees the shapes the build registered and nothing else. When the geometry record lists
components declared not drawn (``cadagent.review.dossier.not_drawn``), ``cad-agent gates`` runs ``note_not_drawn`` on
every verdict: ``not_drawn`` (``[{"name", "reason", "near"}]``), an assumption that names them, and, in every gate
but those in ``NOT_DRAWN_NOTE_ONLY``, a ``<gate>:not-drawn`` check with status ``warn``. So the ``status`` of a gate
that would have passed is ``warn``; ``pass`` stays true, and a declaration alone never fails a gate. Only declared
components appear: nothing detects an omission nobody declared.

The same statement is applied wherever a verdict is made for a build: a gate given ``Assembly.from_build(result)``
applies it before it returns or writes (the assembly carries ``not_drawn``), and ``bind_inputs`` applies it to
whatever it binds (a project's own gate). ``stale_reason`` refuses a verdict that does not name the components the
record declares, so no verdict is current for such a record without the statement. The one exception is a gate
called on a hand-built ``Assembly``, which has no record to read.
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


# gates whose result an absent component cannot change, so they record the list without a warning. The wall gate
# measures each drawn part's own walls. Every other gate's result depends on which solids are present.
NOT_DRAWN_NOTE_ONLY = frozenset({"wall"})
NOT_DRAWN_CHECK = "not-drawn"


def not_drawn_of(record: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """The components a geometry record declares not drawn, as ``[{"name", "reason", "near"}]`` in name order
    (``[]`` for a record without any, or with a malformed table)."""
    table = (record or {}).get("not_drawn")
    if not isinstance(table, Mapping):
        return []
    out = []
    for name in sorted(table, key=str):
        info = table[name] if isinstance(table[name], Mapping) else {}
        near = info.get("near")
        out.append({"name": str(name), "reason": str(info.get("reason") or ""),
                    "near": [str(n) for n in near] if isinstance(near, (list, tuple)) else []})
    return out


def not_drawn_names(items: Sequence[Mapping[str, Any]], limit: int = 0) -> str:
    """``"bevel_pinion (near wheel), motor_shaft"``: the names with their neighbours, the first ``limit`` when
    given, then how many more."""
    shown = list(items[:limit] if limit else items)
    text = ", ".join(str(i.get("name")) + (f" (near {', '.join(map(str, i['near']))})" if i.get("near") else "")
                     for i in shown)
    return text + (f" and {len(items) - len(shown)} more" if len(items) > len(shown) else "")


def not_drawn_summary(items: Sequence[Mapping[str, Any]], limit: int = 0) -> str:
    """One sentence for a report: how many components are not drawn, which, and that no gate saw them (``""`` for
    none)."""
    if not items:
        return ""
    n = len(items)
    return (f"{n} component{'s' if n != 1 else ''} of the design {'are' if n != 1 else 'is'} declared not drawn, so "
            f"no gate saw {'them' if n != 1 else 'it'}: {not_drawn_names(items, limit)}")


def not_drawn_markdown(data: Mapping[str, Any]) -> List[str]:
    """The "Not in the model" section of a verdict's Markdown, as lines (``[]`` when the verdict names none)."""
    missing = [m for m in data.get("not_drawn") or [] if isinstance(m, Mapping)]
    if not missing:
        return []
    n = len(missing)

    def cell(value: Any) -> str:
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")
    lines = ["## Not in the model", "",
             f"**{n} component{'s' if n != 1 else ''} of the design {'are' if n != 1 else 'is'} declared not "
             f"drawn. This gate did not see {'them' if n != 1 else 'it'}, and its result does not cover "
             f"{'them' if n != 1 else 'it'}.**", "",
             "| Component | Near | Why it is not drawn |", "|---|---|---|"]
    lines += [f"| `{cell(m.get('name'))}` | {cell(', '.join(m.get('near') or []) or '-')} "
              f"| {cell(m.get('reason'))} |" for m in missing]
    return lines + [""]


def is_not_drawn_check(check: Mapping[str, Any]) -> bool:
    """Whether a check or finding is a gate's ``<gate>:not-drawn`` row or the lint's ``not-drawn`` warning. Such a
    row concerns every part and every section: the component has no extent, so nothing limits what it reaches."""
    ev = check.get("evidence") if isinstance(check.get("evidence"), Mapping) else {}
    if ev.get("code") == NOT_DRAWN_CHECK or check.get("code") == NOT_DRAWN_CHECK:
        return True
    return (check.get("status") == "warn" and str(check.get("id") or "").endswith(f":{NOT_DRAWN_CHECK}")
            and isinstance(ev.get("not_drawn"), list) and bool(ev["not_drawn"]))


def note_not_drawn(data: Dict[str, Any], record: Any) -> Dict[str, Any]:
    """State in a verdict (in place, and returned) which components of the design the geometry record declares not
    drawn. ``record`` is the geometry record, or the list ``not_drawn_of`` made from it (``Assembly.not_drawn``).
    An existing verdict may be bound again only if its list still matches the record.

    Adds ``not_drawn``, one assumption, and (unless the gate is in ``NOT_DRAWN_NOTE_ONLY``) a ``<gate>:not-drawn``
    check with status ``warn`` whose ``parts`` are the declared neighbours. A ``pass`` status becomes ``warn``; a
    ``fail`` stays a fail, and ``pass`` (the boolean) never changes. The warning is not limited to the declared
    neighbours: the gate has no geometry for the component, so it cannot tell what the component would reach."""
    items = [dict(i) for i in record] if isinstance(record, (list, tuple)) else not_drawn_of(record)
    if "not_drawn" in data and data["not_drawn"] != items:
        raise ValueError("components declared not drawn changed: rerun the gate before binding its verdict")
    if not items:
        return data
    if data.get("not_drawn") and data.get("counts"):
        # Older omission rows could overwrite a project check while leaving its pass or fail in the totals.
        for status in ("pass", "fail"):
            actual = sum(row.get("status") == status for row in data.get("checks") or [])
            if data["counts"].get(status, 0) != actual:
                raise ValueError("verdict counts disagree with the retained checks: rerun the gate")
    gate = str(data.get("gate") or "")
    names = not_drawn_names(items)
    n = len(items)
    data["not_drawn"] = items
    assumption = (
        f"{n} component{'s' if n != 1 else ''} of the design {'are' if n != 1 else 'is'} declared not drawn "
        f"({names}): this gate did not see {'them' if n != 1 else 'it'}, and its result says nothing about "
        f"{'them' if n != 1 else 'it'} or about what {'they' if n != 1 else 'it'} would touch, block, carry or fill")
    assumptions = data.get("assumptions") or []
    if assumption not in assumptions:
        data["assumptions"] = [*assumptions, assumption]
    if gate in NOT_DRAWN_NOTE_ONLY:
        return data
    near = sorted({p for i in items for p in i["near"]})
    check = Check(f"{gate}:{NOT_DRAWN_CHECK}", "warn",
                  f"not in the model: {names}. This gate checked the drawn parts only; its result does not cover "
                  f"{'these components' if n != 1 else 'this component'}. Draw {'them' if n != 1 else 'it'} and "
                  "remove the not_drawn declaration to clear this warning",
                  parts=near, evidence={"not_drawn": items}).to_dict()
    # Project gates choose their own check IDs. Reuse an identical warning on rebind and keep any other row.
    existing = [*(data.get("checks") or []), *(data.get("findings") or [])]
    suffix = 0
    while any(row.get("id") == check["id"] and row != check for row in existing):
        suffix += 1
        check["id"] = f"{gate}:{suffix}:{NOT_DRAWN_CHECK}"
    for field in ("checks", "findings"):
        rows = data.get(field) or []
        matching = [row for row in rows if row.get("id") == check["id"]]
        if matching != [check]:
            data[field] = [row for row in rows if row.get("id") != check["id"]] + [check]
    counts = dict(data.get("counts") or {})
    counts["warn"] = sum(row.get("status") == "warn" for row in data["checks"])
    data["counts"] = counts
    if data.get("status") == "pass":
        data["status"] = "warn"
    return data


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
                                                               # steps, not_drawn (``actor``: who built a part, T11)
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
    for table in ("parts", "cavities", "joints", "fasteners", "not_drawn"):
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
    ``options`` are digested (``digest_of``) when given, so a change to them makes the verdict stale too.

    When the record declares components that are not drawn, the verdict is first made to name them
    (``note_not_drawn``), so nothing is bound to such a record without that statement: a project's own gate gets
    it here. A record without declarations leaves the verdict as it was."""
    note_not_drawn(data, record)
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
    went), changed declarations or options, or a verdict that does not name the components the record declares
    not drawn. With no record, a verdict cannot be current."""
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
                if changed else "the declarations in the record changed (flags, joints, fasteners, steps or "
                                "components declared not drawn)")
        return f"geometry changed since this verdict ({what})"
    declared = not_drawn_of(record)
    if declared:                                    # same digest, yet the verdict does not say what no gate saw
        named = {str(m.get("name")) for m in data.get("not_drawn") or [] if isinstance(m, Mapping)}
        unnamed = [i["name"] for i in declared if i["name"] not in named]
        if unnamed:
            return ("does not name the component(s) the record declares not drawn "
                    f"({', '.join(unnamed[:6])}{' ...' if len(unnamed) > 6 else ''}): apply note_not_drawn, or "
                    "rerun cad-agent gates")
    if data.get("not_drawn", []) != declared:
        return "the verdict describes different components declared not drawn: rerun the gate"
    if declared:
        # A custom writer can supply the list and digest without the warning that readers rely on.
        try:
            annotated = note_not_drawn(dict(data), declared)
        except (AttributeError, TypeError, ValueError):
            return "invalid gate evidence for the components declared not drawn: rerun the gate"
        if annotated != data:
            return "incomplete gate evidence for the components declared not drawn: rerun the gate"
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
