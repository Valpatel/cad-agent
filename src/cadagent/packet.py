"""The section review packet (plan T10, ``docs/review-packet.md``): captioned renders of one dossier section with
the measurements first, for a reviewer to critique against the render checklist.

Two halves:

* ``plan_packet(section, record, dossier, verdicts, status)`` is kernel-free. From the geometry record
  (``exports/dossier-geometry.json``), the YAML dossier and the gate verdicts it works out the views (solid,
  opposite iso, x-ray, cuts through cavities, joint axes and fastener axes, exploded along the assembly steps,
  access along the fastener axes, joint range ends, findings), the section's findings with their witness points,
  the content hashes, and the render checklist instantiated for the section. It returns the manifest without image
  hashes.
* ``review_packet(section, root=...)`` (also ``cadagent.render.review_packet``) loads a project, plans, renders
  every view with ``cadagent.render.Renderer`` (CadQuery, VTK, Pillow) and writes
  ``exports/review/<section>/manifest.json``.

Renders are for diagnosis, not proof: the gates measure, the checklist never asks an image for a count or a gap.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple, Union

SCHEMA = "cad-agent.review-packet/1"
CHECKLIST_SCHEMA = "cad-agent.render-checklist/1"
ANSWERS = ("yes", "no", "unclear")
LINT_GATE = "dossier-lint"
CONTEXT_MODES = ("neighbours", "all", "none")
MAX_WITNESSES = 4
MAX_CALLOUTS = 10

# ------------------------------------------------------------------------------------------- the checklist

# Each item is asked of one kind of view. ``per`` says what it is instantiated for: None (once per section), or one
# question per cut/pose/access target. ``bad_answer`` is the answer that is a finding; ``unclear`` is never a pass.
CHECKLIST: Tuple[Dict[str, Any], ...] = (
    {"id": "contained-inside", "kind": "cut", "per": "cavity", "bad_answer": "no", "gate": "containment",
     "question": "In the cut through {cavity}, is every {what} fully inside the inner wall of {part}?"},
    {"id": "joint-bearing", "kind": "cut", "per": "joint", "bad_answer": "no", "gate": "connectivity",
     "question": "In the cut through {interface}, does {moving} turn or slide on a real bearing feature of {fixed} "
                 "(a bore around the pin, a slot around the slider), with no material in its path?"},
    {"id": "fastener-stack", "kind": "cut", "per": "fastener", "bad_answer": "no", "gate": "fasteners",
     "question": "In the cut through {fastener}, does the head sit on {clamps} and does the thread end inside "
                 "{into}?"},
    {"id": "mating-feature", "kind": "exploded", "per": None, "bad_answer": "no", "gate": "connectivity",
     "question": "In the exploded view, does every part have a visible mating feature (bore, boss, slot, seat, "
                 "screw hole) that meets one on its neighbour?"},
    {"id": "assembly-order", "kind": "exploded", "per": None, "bad_answer": "no", "gate": "assembly",
     "question": "Does the explode order (later steps further out) look buildable: nothing shown going in through a "
                 "part fitted before it?"},
    {"id": "plain-box", "kind": "solid", "per": None, "bad_answer": "yes", "gate": None,
     "question": "Does any part appear as a plain box with no features where a mechanism or interface should be?"},
    {"id": "matches-card", "kind": "solid", "per": None, "bad_answer": "no", "gate": None,
     "question": "Does every part look like the function its card states (parts.*.function in the manifest)? Name "
                 "any that does not."},
    {"id": "floating", "kind": "solid-rear", "per": None, "bad_answer": "yes", "gate": "connectivity",
     "question": "Is anything floating in the opposite iso: a part with nothing visibly holding it?"},
    {"id": "hidden-overlap", "kind": "xray", "per": None, "bad_answer": "yes", "gate": "connectivity",
     "question": "In the x-ray, does any part sit inside another part's material where no insert or press fit is "
                 "declared?"},
    {"id": "fastener-access", "kind": "access", "per": "access", "bad_answer": "no", "gate": "fasteners",
     "question": "Looking along the screws' axis from the tool's side, is every head of {fasteners} visible and "
                 "unobstructed?"},
    {"id": "motion-contact", "kind": "pose", "per": "pose", "bad_answer": "yes", "gate": "motion",
     "question": "At this end of {interface}'s range ({value}), does {moving} touch anything other than its declared "
                 "contacts ({contacts})?"},
    {"id": "findings-located", "kind": "findings", "per": None, "bad_answer": "no", "gate": None,
     "question": "Is each numbered callout on the parts its finding names?"},
)

# What an image is never asked: the gates measure it (DW §5: counting and small gaps are where vision models fail).
MEASURED_ONLY: Tuple[Dict[str, Any], ...] = (
    {"id": "count", "topic": "how many items there are", "answered_by": ["gate:containment", "gate:assembly"]},
    {"id": "gap", "topic": "gaps and clearances under about a millimetre, and whether two parts touch",
     "answered_by": ["gate:connectivity", "gate:motion", "gate:assembly"]},
    {"id": "wall", "topic": "wall thickness", "answered_by": ["gate:wall"]},
    {"id": "thread", "topic": "thread engagement, screw length and tip clearance", "answered_by": ["gate:fasteners"]},
    {"id": "overlap", "topic": "overlap volumes and how far an item is outside its cavity",
     "answered_by": ["gate:containment", "gate:connectivity"]},
    {"id": "path", "topic": "whether something moves clear between the drawn poses, or goes in clear along its path",
     "answered_by": ["gate:motion", "gate:assembly"]},
)

INSTRUCTIONS: Tuple[str, ...] = (
    "Read `measurements` and `findings` before looking at any image; the gates measured what the images show.",
    "Answer every question with yes, no or unclear, citing the view you answered from. unclear is a valid answer "
    "and is never a pass: say what view would settle it.",
    "Do not answer a count, a gap, a wall thickness or an engagement from an image: read it from the gate named in "
    "`measured_only`.",
    "When an image and a measurement disagree, the measurement wins, and the disagreement is a finding (a wrong "
    "declaration, or a misleading view).",
    "Record the part hashes (`parts.*.sha256`) your answers are for; a change of geometry voids them.",
)

LIMITS: Tuple[str, ...] = (
    "Renders are for diagnosis, not proof: they do not show that printed parts fit, hold or move.",
    "Views are tessellated: a gap or overlap under the chord error can look closed or open, so the checklist never "
    "asks an image for one.",
    "Cut planes are fixed (through a cavity's box centre, through a joint or screw axis); a defect away from the "
    "plane shows only in the other views.",
    "Poses are the declared range ends, not the path between them; the motion gate samples the path.",
    "Exploded offsets are illustrative: their direction comes from the declared steps, their length from the "
    "section's size.",
)

PALETTE = ("#3b7dd8", "#2f9e77", "#8a63d2", "#c9a227", "#d0457a", "#3aa0b5", "#7a8b2e", "#b0603a", "#5562c8",
           "#45a55a", "#a8458f", "#2b8c8c")
FREE_COLOR = "#f08c00"
FASTENER_COLOR = "#4a4f55"
CONTEXT_COLOR = "#b4bcc4"
CAVITY_COLOR = "#7fb3e6"
OPPOSITE_ISO = (-1.0, 1.05, 0.85)
DIRS = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}


class PacketError(ValueError):
    """The packet cannot be planned: an unknown section, no geometry record."""


def checklist_items() -> List[Dict[str, Any]]:
    """The generic render checklist (``CHECKLIST``) as plain JSON."""
    return [dict(item) for item in CHECKLIST]


# ------------------------------------------------------------------------------------------- small helpers

def owner(key: str) -> str:
    """The part or fastener name of an instance key (``ball#3`` -> ``ball``)."""
    key = str(key)
    if "#" in key:
        base, idx = key.rsplit("#", 1)
        if idx.isdigit():
            return base
    return key


def safe_name(text: str) -> str:
    """A file-name-safe form of an id (fastener names may contain ``:``)."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_") or "x"


def _unit(v: Sequence[float]) -> Tuple[float, float, float]:
    n = math.sqrt(sum(float(c) ** 2 for c in v))
    if n == 0:
        raise ValueError("zero vector")
    return (float(v[0]) / n, float(v[1]) / n, float(v[2]) / n)


def _cross(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _r(v: Iterable[float], nd: int = 6) -> List[float]:
    return [round(float(x), nd) + 0.0 for x in v]


def direction_vector(direction: Any) -> Optional[Tuple[float, float, float]]:
    """``+X``..``-Z`` or ``[x, y, z]`` as a unit vector; None when missing or invalid."""
    if isinstance(direction, str):
        d = DIRS.get(direction.strip().upper())
        return tuple(float(c) for c in d) if d else None  # type: ignore[return-value]
    if isinstance(direction, (list, tuple)) and len(direction) == 3:
        try:
            return _unit([float(c) for c in direction])
        except (TypeError, ValueError):
            return None
    return None


def plane_containing(axis_dir: Sequence[float]) -> Tuple[float, float, float]:
    """The normal of a plane that contains ``axis_dir``, as close to horizontal as possible (a vertical cut seen
    from the side): ``axis × Z``, or ``axis × Y`` for a vertical axis."""
    d = _unit(axis_dir)
    n = _cross(d, (0.0, 0.0, 1.0))
    if math.sqrt(sum(c * c for c in n)) < 0.1:
        n = _cross(d, (0.0, 1.0, 0.0))
    n = _unit(n)
    # point the kept half towards +X/+Y so the camera (on the removed side) looks from -X/-Y like the front views
    if n[0] + n[1] + 0.5 * n[2] < 0:
        n = (-n[0], -n[1], -n[2])
    return (n[0] + 0.0, n[1] + 0.0, n[2] + 0.0)


def rotate_point(p: Sequence[float], origin: Sequence[float], axis: Sequence[float], deg: float) -> List[float]:
    """Right-handed rotation of ``p`` about the axis through ``origin`` (Rodrigues)."""
    k = _unit(axis)
    t = math.radians(deg)
    v = [p[i] - origin[i] for i in range(3)]
    c, s = math.cos(t), math.sin(t)
    kxv = _cross(k, v)
    kdv = sum(k[i] * v[i] for i in range(3))
    return [origin[i] + v[i] * c + kxv[i] * s + k[i] * kdv * (1 - c) for i in range(3)]


Box = Tuple[List[float], List[float]]


def _box(info: Mapping[str, Any]) -> Optional[Box]:
    b = info.get("bbox") if isinstance(info, Mapping) else None
    if not isinstance(b, Mapping) or "min" not in b or "max" not in b:
        return None
    return [float(c) for c in b["min"]], [float(c) for c in b["max"]]


def _union(boxes: Iterable[Optional[Box]]) -> Optional[Box]:
    out: Optional[Box] = None
    for b in boxes:
        if b is None:
            continue
        if out is None:
            out = (list(b[0]), list(b[1]))
        else:
            out = ([min(out[0][i], b[0][i]) for i in range(3)], [max(out[1][i], b[1][i]) for i in range(3)])
    return out


def _diag(b: Optional[Box]) -> float:
    if b is None:
        return 1.0
    return max(1.0, math.sqrt(sum((b[1][i] - b[0][i]) ** 2 for i in range(3))))


def _box_gap(a: Box, b: Box) -> float:
    d = [max(0.0, a[0][i] - b[1][i], b[0][i] - a[1][i]) for i in range(3)]
    return math.sqrt(sum(c * c for c in d))


def _grow(b: Optional[Box], margin: float) -> Optional[Box]:
    if b is None:
        return None
    return [c - margin for c in b[0]], [c + margin for c in b[1]]


def _fit(b: Optional[Box]) -> Optional[Dict[str, List[float]]]:
    return {"min": _r(b[0], 4), "max": _r(b[1], 4)} if b is not None else None


def _corners(b: Box) -> List[List[float]]:
    return [[b[i >> k & 1][k] for k in range(3)] for i in range(8)]


def _box_of(points: Iterable[Sequence[float]]) -> Box:
    pts = list(points)
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def hash_lines(items: Mapping[str, str]) -> str:
    """sha256 over the sorted ``name sha256`` lines: the section hash."""
    text = "".join(f"{k} {items[k]}\n" for k in sorted(items))
    return hashlib.sha256(text.encode()).hexdigest()


def file_sha256(path: Union[str, Path]) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def witness_points(evidence: Any, limit: int = MAX_WITNESSES) -> List[Dict[str, Any]]:
    """3D points in a check's evidence: values of keys containing ``point`` or ``centroid`` (nested witnesses
    included), as ``{label, point}``, at most ``limit``, near-duplicates dropped."""
    found: List[Dict[str, Any]] = []

    def is_point(v: Any) -> bool:
        return (isinstance(v, (list, tuple)) and len(v) == 3
                and all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in v))

    def walk(node: Any, path: str, depth: int) -> None:
        if depth > 6 or len(found) >= 64:
            return
        if isinstance(node, Mapping):
            for k in node:
                v = node[k]
                label = f"{path}.{k}" if path else str(k)
                kl = str(k).lower()
                if ("point" in kl or "centroid" in kl) and is_point(v):
                    found.append({"label": label, "point": _r(v, 4)})
                elif isinstance(v, (Mapping, list, tuple)) and not is_point(v):
                    walk(v, label, depth + 1)
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node[:16]):
                walk(v, f"{path}[{i}]", depth + 1)

    walk(evidence, "", 0)
    out: List[Dict[str, Any]] = []
    for w in found:
        if all(math.dist(w["point"], o["point"]) > 1e-3 for o in out):
            out.append(w)
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------------------------------- the section

class _Record:
    """The geometry record, indexed: parts, fasteners, cavities, joints, steps and instance keys."""

    def __init__(self, record: Mapping[str, Any], dossier: Any = None):
        self.raw = record
        self.parts: Dict[str, Mapping[str, Any]] = dict(record.get("parts") or {})
        self.fasteners: Dict[str, Mapping[str, Any]] = dict(record.get("fasteners") or {})
        self.cavities: Dict[str, Mapping[str, Any]] = dict(record.get("cavities") or {})
        self.joints: Dict[str, Mapping[str, Any]] = dict(record.get("joints") or {})
        steps = list(((record.get("assembly") or {}).get("steps")) or [])
        orders = {s.get("order") for s in steps}
        for s in getattr(dossier, "assembly", None) or []:       # YAML steps the build does not declare
            if s.order not in orders:
                steps.append({"order": s.order, "fit": s.fit, "onto": list(s.onto), "direction": s.direction,
                              "tool": s.tool, "fasteners": list(s.fasteners)})
        self.steps = sorted((s for s in steps if isinstance(s.get("order"), int)), key=lambda s: s["order"])
        self.instances: Dict[str, Tuple[str, str, Mapping[str, Any]]] = {}     # key -> (kind, name, instance)
        for table, kind in ((self.parts, "part"), (self.fasteners, "fastener")):
            for name, info in table.items():
                for inst in (info.get("instances") or []):
                    self.instances[str(inst.get("key"))] = (kind, name, inst)

    def keys_of(self, name: str) -> List[str]:
        """Instance keys of a part or fastener name, or the key itself."""
        if name in self.instances:
            return [name]
        return [k for k, (_, n, _) in self.instances.items() if n == name]

    def box(self, key: str) -> Optional[Box]:
        entry = self.instances.get(key)
        return _box(entry[2]) if entry else None


def sections_of(record: Mapping[str, Any], dossier: Any = None) -> List[str]:
    """Section ids: the dossier's, in order, then any the build registered that the dossier does not have."""
    out = list(getattr(dossier, "sections", {}) or {})
    for info in (record.get("parts") or {}).values():
        s = info.get("section") if isinstance(info, Mapping) else None
        if s and s not in out:
            out.append(s)
    return out


def _members(sid: str, rec: _Record, dossier: Any) -> Tuple[List[str], List[str], List[str]]:
    """(section parts with shapes, section fasteners, cards without a shape)."""
    names: List[str] = [n for n, info in rec.parts.items() if info.get("section") == sid]
    missing: List[str] = []
    sec = (getattr(dossier, "sections", {}) or {}).get(sid) if dossier is not None else None
    if sec is not None:
        for card in sec.parts:
            if card.id in rec.parts:
                if card.id not in names:
                    names.append(card.id)
            else:
                missing.append(card.id)
    fasteners = [n for n, f in rec.fasteners.items()
                 if f.get("clamps") in names or f.get("into") in names]
    return names, fasteners, missing


def _gate_names(findings_parts: Iterable[Any], rec: _Record, parts: Set[str], fasteners: Set[str]) -> Tuple[bool, bool]:
    """(names something of the section, names anything known at all) for a finding's ``parts``."""
    mine = known = False
    for name in findings_parts:
        o = owner(str(name))
        if o in rec.parts:
            known = True
            mine |= o in parts
        elif o in rec.fasteners:
            known = True
            f = rec.fasteners[o]
            mine |= o in fasteners or f.get("clamps") in parts or f.get("into") in parts
        elif o in rec.cavities:
            known = True
            mine |= rec.cavities[o].get("part") in parts
    return mine, known


def _section_checks(verdict: Mapping[str, Any], rec: _Record, sid: str, parts: Set[str],
                    fasteners: Set[str]) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]]:
    """The verdict's checks for the section, and its findings with their scope (``section`` or ``unattributed``)."""
    rows: List[Dict[str, Any]] = []
    found: List[Tuple[Dict[str, Any], str]] = []
    for c in verdict.get("checks") or []:
        if not isinstance(c, Mapping):
            continue
        names = list(c.get("parts") or [])
        ev = c.get("evidence") if isinstance(c.get("evidence"), Mapping) else {}
        item = c.get("item") or ev.get("item")
        if item:
            names.append(item)
        mine, known = _gate_names(names, rec, parts, fasteners)
        mine |= item == sid
        if mine:
            rows.append({"id": c.get("id"), "status": c.get("status"), "message": c.get("message", "")})
        if c.get("status") in ("fail", "warn"):
            if mine:
                found.append((dict(c), "section"))
            elif not known and c.get("status") == "fail" and item != sid and not (item and item in rec.parts):
                found.append((dict(c), "unattributed"))
    return rows, found


# ------------------------------------------------------------------------------------------- planning

def plan_packet(section: str, record: Mapping[str, Any], dossier: Any = None,
                verdicts: Optional[Mapping[str, Mapping[str, Any]]] = None, status: Optional[Mapping[str, Any]] = None,
                *, lint: Optional[Mapping[str, Any]] = None, expected: Optional[Mapping[str, Mapping[str, Any]]] = None,
                record_file: str = "exports/dossier-geometry.json", out_dir: str = "",
                gate_files: Optional[Mapping[str, str]] = None, explode: float = 1.0,
                context: str = "neighbours", toolkit: str = "") -> Dict[str, Any]:
    """The packet manifest for ``section`` without image hashes (``views[].file`` set, ``sha256`` null).

    ``record``: the geometry record (JSON); ``dossier``: a loaded ``Dossier`` or None; ``verdicts``: ``{gate: verdict}``
    from ``exports/gates/``; ``status``: ``exports/dossier-status.json``; ``lint``: the dossier-lint verdict;
    ``expected``: ``{gate: {declarations, options}}`` to judge staleness as ``cad-agent check`` does (else the
    geometry only)."""
    from cadagent.gates.verdict import geometry_digest, stale_reason

    if context not in CONTEXT_MODES:
        raise PacketError(f"context must be one of {CONTEXT_MODES}, got {context!r}")
    if not isinstance(record, Mapping) or not isinstance(record.get("parts"), Mapping):
        raise PacketError("no geometry record (exports/dossier-geometry.json): run the build first")
    rec = _Record(record, dossier)
    all_sections = sections_of(record, dossier)
    if section not in all_sections:
        raise PacketError(f"unknown section {section!r}; sections: {', '.join(all_sections) or 'none'}")
    sec = (getattr(dossier, "sections", {}) or {}).get(section) if dossier is not None else None
    names, fnames, missing = _members(section, rec, dossier)
    part_set, fast_set = set(names), set(fnames)
    sec_keys = [k for n in names + fnames for k in rec.keys_of(n)]
    sec_key_set = set(sec_keys)
    sec_box = _union(rec.box(k) for k in sec_keys)
    diag = _diag(sec_box)
    not_rendered: List[Dict[str, str]] = [{"what": f"part {m}", "why": "its card has no registered shape"}
                                          for m in missing]
    if not sec_keys:
        not_rendered.append({"what": f"section {section}", "why": "no part of the section has a shape"})

    # -- parts, colours, hashes
    cards = {c.id: c for c in (sec.parts if sec is not None else [])}
    part_status = (status or {}).get("parts") or {}
    parts: Dict[str, Dict[str, Any]] = {}
    ci = 0
    for n in names:
        info = rec.parts[n]
        if info.get("free"):
            color = FREE_COLOR
        else:
            color = PALETTE[ci % len(PALETTE)]
            ci += 1
        boxes = [_box(i) for i in info.get("instances") or []]
        row: Dict[str, Any] = {"sha256": info.get("sha256"), "kind": "part", "count": info.get("count", len(boxes)),
                               "free": bool(info.get("free")), "grounded": bool(info.get("grounded")), "color": color}
        card = cards.get(n) or ((getattr(dossier, "parts", {}) or {}).get(n) if dossier is not None else None)
        if card is not None:
            row["function"] = card.function
            row["decisions"] = [{"id": d.id, "decision": d.decision} for d in card.decisions]
        if isinstance(part_status.get(n), Mapping):
            row["status"] = part_status[n].get("status")
        ub = _union(boxes)
        if ub:
            row["bbox"] = {"min": _r(ub[0]), "max": _r(ub[1])}
        vol = sum(float(i.get("volume_mm3") or 0) for i in info.get("instances") or [])
        row["volume_mm3"] = round(vol, 3)
        row["instances"] = [{"key": i.get("key"), "sha256": i.get("sha256")} for i in info.get("instances") or []]
        parts[n] = row
    for n in fnames:
        f = rec.fasteners[n]
        parts[n] = {"sha256": hash_lines({i.get("key"): i.get("sha256") or "" for i in f.get("instances") or []}),
                    "kind": "fastener", "count": f.get("count", len(f.get("instances") or [])), "key": f.get("key"),
                    "clamps": f.get("clamps"), "into": f.get("into"), "color": FASTENER_COLOR,
                    "instances": [{"key": i.get("key"), "sha256": i.get("sha256")} for i in f.get("instances") or []]}
    section_hash = hash_lines({n: str(parts[n].get("sha256") or "") for n in parts})

    # -- context
    def partners() -> Set[str]:
        out: Set[str] = set()
        if dossier is not None:
            for itf in (getattr(dossier, "interfaces", {}) or {}).values():
                between = set(itf.between)
                if between & (part_set | {section}):
                    out |= between
        for f in (rec.fasteners[n] for n in fnames):
            out |= {f.get("clamps"), f.get("into")} - {None}
        for j in rec.joints.values():
            pair = {j.get("moving"), j.get("fixed")} - {None}
            if pair & part_set:
                out |= pair
        return {o for o in out if o in rec.parts or o in rec.fasteners}

    context_keys: List[str] = []
    if context != "none":
        near = partners()
        for key, (kind, name, inst) in rec.instances.items():
            if key in sec_key_set:
                continue
            if context == "all" or name in near:
                context_keys.append(key)
                continue
            b = _box(inst)
            if sec_box is not None and b is not None and _box_gap(sec_box, b) <= 0.1 * diag:
                context_keys.append(key)
    context_rows = [{"key": k, "section": rec.parts.get(rec.instances[k][1], {}).get("section", "")
                     if rec.instances[k][0] == "part" else "", "kind": rec.instances[k][0],
                     "sha256": rec.instances[k][2].get("sha256")} for k in context_keys]

    # -- measurements and findings
    verdicts = dict(verdicts or {})
    expected = dict(expected or {})
    gate_files = dict(gate_files or {})
    gates_m: Dict[str, Dict[str, Any]] = {}
    raw_findings: List[Tuple[str, Dict[str, Any], str]] = []
    for g in sorted(verdicts):
        v = verdicts[g]
        if not isinstance(v, Mapping):
            continue
        rows, found = _section_checks(v, rec, section, part_set, fast_set)
        try:
            stale = stale_reason(v, record, **dict(expected.get(g) or {}))
        except Exception as exc:            # a malformed verdict is reported, never read as current
            stale = f"cannot compare inputs: {exc}"
        gates_m[g] = {"file": gate_files.get(g, f"exports/gates/{g}.json"), "status": v.get("status"),
                      "pass": v.get("pass"), "stale": stale, "checks": len(v.get("checks") or []),
                      "section_checks": rows}
        raw_findings += [(g, c, scope) for c, scope in found]
    wanted = {c[5:] for card in cards.values() for c in card.checks if str(c).startswith("gate:")}
    lint_m: Optional[Dict[str, Any]] = None
    if isinstance(lint, Mapping):
        rows, found = _section_checks(lint, rec, section, part_set, fast_set)
        lint_m = {"file": f"exports/gates/{LINT_GATE}.json", "status": lint.get("status"), "pass": lint.get("pass"),
                  "section_checks": [r for r in rows if r["status"] != "pass"]}
        raw_findings += [(LINT_GATE, c, scope) for c, scope in found if scope == "section"]
    measurements: Dict[str, Any] = {"gates": gates_m, "missing_gates": sorted(wanted - set(gates_m))}
    if lint_m is not None:
        measurements["lint"] = lint_m
    findings: List[Dict[str, Any]] = []
    order = {"fail": 0, "warn": 1}
    raw_findings.sort(key=lambda t: (order.get(t[1].get("status"), 2), t[2] != "section", t[0], str(t[1].get("id"))))
    for g, c, scope in raw_findings:
        findings.append({"id": f"F{len(findings) + 1}", "gate": g, "check": c.get("id"), "status": c.get("status"),
                         "message": c.get("message", ""), "parts": list(c.get("parts") or []), "scope": scope,
                         "witness": witness_points(c.get("evidence"))})

    # -- views
    views: List[Dict[str, Any]] = []
    sid_title = f"{section} {sec.title}" if sec is not None and sec.title else section

    def view(vid: str, kind: str, title: str, note: str, camera: Any, **extra: Any) -> Dict[str, Any]:
        row = {"id": vid, "kind": kind, "file": f"{safe_name(vid)}.png", "sha256": None,
               "caption": f"{sid_title}: {title}", "note": note,
               "camera": camera if isinstance(camera, str) else _r(camera, 4), "clip": None, "target": None,
               "keys": list(sec_keys), "offsets": {}, "pose": None, "callouts": [],
               "fit": _fit(_grow(sec_box, 0.05 * diag))}
        row.update(extra)
        views.append(row)
        return row

    if sec_keys:
        view("solid-iso", "solid", "solid, front iso", "The section in place. Measurements first: see the manifest.",
             "iso")
        view("solid-rear", "solid-rear", "solid, opposite iso",
             "From behind and the other side: what the front iso hides.", list(OPPOSITE_ISO))
        view("xray-iso", "xray", "x-ray",
             "Section parts translucent; free items, fasteners and declared cavities shown inside.", "iso")

    # cuts through cavities
    contains_by_cavity: Dict[str, List[str]] = {}
    for card in cards.values():
        for c in card.contains:
            if c.cavity:
                contains_by_cavity.setdefault(c.cavity, []).append(c.what)
    for cname, cav in sorted(rec.cavities.items()):
        if cav.get("part") not in part_set:
            continue
        b = _box(cav)
        if b is None:
            not_rendered.append({"what": f"cut through {cname}", "why": "the cavity has no box in the record"})
            continue
        centre = [(b[0][i] + b[1][i]) / 2 for i in range(3)]
        cav_fit = _fit(_grow(_union([b] + [rec.box(k) for k in rec.keys_of(str(cav.get("part")))]), 0.08 * diag))
        target = {"cavity": cname, "part": cav.get("part"), "contains": contains_by_cavity.get(cname, [])}
        view(f"cut-cavity-{cname}", "cut", f"cut through {cname}, side",
             f"Vertical plane through the centre of {cname} (normal +Y), seen from -Y: contents against the walls.",
             [0.0, -1.0, 0.0], clip={"origin": _r(centre), "normal": [0.0, 1.0, 0.0]}, fit=cav_fit, target=target)
        view(f"cut-cavity-{cname}-plan", "cut", f"cut through {cname}, plan",
             f"Horizontal plane through the centre of {cname}, seen from above: the walls as a ring around the "
             "contents.", [0.0, 0.0, 1.0], clip={"origin": _r(centre), "normal": [0.0, 0.0, -1.0]}, fit=cav_fit,
             target=dict(target))

    # cuts through joint axes, and poses
    from cadagent.gates.relations import moving_bodies
    grounded = [n for n, p in rec.parts.items() if p.get("grounded")]
    body_of = moving_bodies(rec.joints, rec.fasteners, grounded)
    for jid, j in sorted(rec.joints.items()):
        moving, fixed = j.get("moving"), j.get("fixed")
        body = {n for n, b in body_of.items() if b == moving} | ({moving} if moving else set())
        involved = ({moving, fixed} | body) & (part_set | fast_set)
        if not involved:
            continue
        axis = j.get("axis") or {}
        origin, d = axis.get("origin"), axis.get("direction")
        if not (isinstance(origin, list) and isinstance(d, list) and len(origin) == 3 and len(d) == 3):
            not_rendered.append({"what": f"joint {jid}", "why": "no axis in the record"})
            continue
        n = plane_containing(d)
        view(f"cut-joint-{jid}", "cut", f"cut through joint {jid}",
             f"Plane containing the {j.get('kind')} axis of {jid}: {moving} on {fixed}.",
             [-c for c in n], clip={"origin": _r(origin), "normal": _r(n)},
             fit=_fit(_grow(_union(rec.box(k) for name in (moving, fixed) for k in rec.keys_of(str(name))),
                            0.08 * diag)),
             target={"joint": jid, "moving": moving, "fixed": fixed, "kind": j.get("kind")})
        rng, unit = j.get("range"), j.get("unit")
        if j.get("kind") in ("planar", "ball", "fixed") or not (isinstance(rng, list) and len(rng) == 2):
            if j.get("kind") != "fixed":
                not_rendered.append({"what": f"poses of joint {jid}", "why": f"a {j.get('kind')} joint has no "
                                                                             "declared range to pose"})
            continue
        carried = _carried(jid, rec.joints, body_of)
        keys_moving = sorted({k for name in carried for k in rec.keys_of(name)})
        for end, value in (("min", rng[0]), ("max", rng[1])):
            moved_boxes = [_pose_box(rec.box(k), origin, d, value, unit, j.get("range_mm"), end) for k in keys_moving]
            pose_fit = _fit(_grow(_union([sec_box] + moved_boxes + [rec.box(k) for k in rec.keys_of(str(fixed))]),
                                  0.05 * diag))
            pose = {"interface": jid, "kind": j.get("kind"), "value": value, "unit": unit, "body": sorted(carried),
                    "keys": keys_moving, "axis": {"origin": _r(origin), "direction": _r(d)}}
            if j.get("kind") == "cylindrical" and isinstance(j.get("range_mm"), list):
                pose["slide_mm"] = j["range_mm"][0 if end == "min" else 1]
            contacts = ", ".join("-".join(map(str, p)) for p in j.get("intended_contacts") or []) or "none"
            view(f"pose-{jid}-{end}", "pose", f"{jid} at {value:g} {unit or ''} ({end} of range)".replace("  ", " "),
                 f"The moving body at the {end} end of its declared range; declared contacts: {contacts}.",
                 "iso", pose=pose, fit=pose_fit, target={"joint": jid, "moving": moving, "fixed": fixed,
                                          "contacts": j.get("intended_contacts") or []})

    # cuts through fastener axes (one per catalogue key and clamped part: alike screws need one look), access views
    by_dir: Dict[Tuple[float, ...], List[str]] = {}
    groups: Dict[Tuple[str, str], List[str]] = {}
    for fname in fnames:
        f = rec.fasteners[fname]
        insts = f.get("instances") or []
        if not insts:
            not_rendered.append({"what": f"fastener {fname}", "why": "not placed (no axes)"})
            continue
        groups.setdefault((str(f.get("key") or fname), str(f.get("clamps"))), []).append(fname)
        for inst in insts:
            dd = inst.get("direction")
            if isinstance(dd, list) and len(dd) == 3:
                by_dir.setdefault(tuple(round(c, 3) + 0.0 for c in _unit(dd)), []).append(fname)
    for (key, clamps), group in sorted(groups.items()):
        fname = group[0]
        f = rec.fasteners[fname]
        inst = f["instances"][0]
        o, d = inst.get("origin"), inst.get("direction")
        if not (isinstance(o, list) and isinstance(d, list) and len(o) == 3 and len(d) == 3):
            not_rendered.append({"what": f"cut through {fname}", "why": "its axis is not in the record"})
            continue
        n = plane_containing(d)
        alike = sum(len(rec.fasteners[g].get("instances") or []) for g in group)
        view(f"cut-fastener-{fname}", "cut", f"cut through {inst.get('key')}",
             f"Plane containing the axis of {inst.get('key')}: head on {clamps}, thread in {f.get('into')}"
             + (f" ({alike} {key} on {clamps} alike; the fastener gate measures each)." if alike > 1 else "."),
             [-c for c in n], clip={"origin": _r(o), "normal": _r(n)},
             fit=_fit(_grow(_box(inst), max(8.0, 1.2 * _diag(_box(inst))))),
             target={"fastener": fname, "key": f.get("key"), "clamps": clamps, "into": f.get("into"),
                     "instance": inst.get("key"), "alike": group})
    for d, fl in sorted(by_dir.items()):
        fl = sorted(set(fl))
        side = _side(tuple(-c for c in d))
        view(f"access-from-{side}", "access", f"access from the {side}",
             f"Looking along the screws' advance from the tool's side ({side}): {', '.join(fl)}.",
             [-c for c in d], target={"advance": list(d), "fasteners": fl}, keys=list(sec_keys) + context_keys)

    # exploded
    if explode and sec_keys:
        offsets, unplaced = _explode(rec, sec_keys, fnames, diag * float(explode))
        if offsets:
            moved = [(lambda b, off: ([b[0][i] + off[i] for i in range(3)], [b[1][i] + off[i] for i in range(3)])
                      if b else None)(rec.box(k), offsets.get(k, [0.0, 0.0, 0.0])) for k in sec_keys]
            view("exploded", "exploded", "exploded along the assembly steps",
                 "Each part backed out along its step's direction, later steps further; screws along their axis.",
                 "iso", offsets=offsets, target={"unplaced": unplaced},
                 fit=_fit(_grow(_union(moved + [sec_box]), 0.05 * diag)))
            if unplaced:
                not_rendered.append({"what": f"explode of {', '.join(unplaced[:6])}",
                                     "why": "fitted by no step with a direction: drawn in place"})
        else:
            not_rendered.append({"what": "exploded view", "why": "no assembly step with a direction fits a part of "
                                                                 "this section"})

    # findings view
    callouts = []
    for f in findings:
        for w in f["witness"]:
            if len(callouts) >= MAX_CALLOUTS:
                break
            callouts.append({"code": f"{f['id']}" + (f".{len([c for c in callouts if c['finding'] == f['id']]) + 1}"
                                                      if len(f["witness"]) > 1 else ""),
                             "finding": f["id"], "label": w["label"], "point": w["point"],
                             "text": f"{_short(str(f['check']), 28)} {w['label'].split('.')[-1][:16]}"})
    if callouts:
        view("findings", "findings", "gate findings at their witness points",
             f"{len(findings)} finding(s); numbered callouts at the witness points (see findings in the manifest).",
             "iso", callouts=callouts)

    manifest: Dict[str, Any] = {
        "schema": SCHEMA,
        "toolkit": toolkit,
        "dir": out_dir,
        "section": _section_row(section, sec, status),
        "geometry": {"file": record_file, "digest": geometry_digest(record), "actor": record.get("actor", "")},
        "section_hash": section_hash,
        "parts": parts,
        "context": context_rows,
        "measurements": measurements,
        "findings": findings,
        "views": views,
        "checklist": checklist_for(views, parts),
        "not_rendered": not_rendered,
        "limits": list(LIMITS),
        "physical_fit_verified": False,
    }
    for f in findings:
        f["views"] = ["findings"] if any(c["finding"] == f["id"] for c in callouts) else []
    return manifest


def _pose_box(b: Optional[Box], origin: Sequence[float], d: Sequence[float], value: float, unit: Any,
              range_mm: Any, end: str) -> Optional[Box]:
    """The box of a box's corners moved to a joint pose (kernel-free framing of the pose views)."""
    if b is None:
        return None
    pts = _corners(b)
    u = _unit(d)
    if unit == "mm":
        pts = [[p[i] + u[i] * float(value) for i in range(3)] for p in pts]
    else:
        pts = [rotate_point(p, origin, u, float(value)) for p in pts]
        if isinstance(range_mm, list) and len(range_mm) == 2:
            t = float(range_mm[0 if end == "min" else 1])
            pts = [[p[i] + u[i] * t for i in range(3)] for p in pts]
    return _box_of(pts)


def _section_row(sid: str, sec: Any, status: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    row: Dict[str, Any] = {"id": sid}
    if sec is not None:
        row.update({"title": sec.title, "purpose": sec.purpose, "requirements": list(sec.requirements)})
        if sec.where is not None:
            row["file"] = sec.where.file
    srow = ((status or {}).get("sections") or {}).get(sid)
    if isinstance(srow, Mapping):
        row["status"] = srow.get("status")
        row["blocked_by"] = list(srow.get("blocked_by") or [])
    return row


def _short(text: str, n: int) -> str:
    """At most ``n`` characters, the end kept (check ids differ at their end)."""
    return text if len(text) <= n else "..." + text[-(n - 3):]


SIDES = {"+X": "right", "-X": "left", "+Y": "back", "-Y": "front", "+Z": "top", "-Z": "bottom"}


def _side(d: Sequence[float]) -> str:
    """The side of the model a direction points to (front is -Y, as in the named views), or the rounded vector."""
    for name, v in DIRS.items():
        if all(abs(d[i] - v[i]) < 1e-6 for i in range(3)):
            return SIDES[name]
    return "_".join(f"{c:+.2f}" for c in d).replace("+", "p").replace("-", "m")


def _carried(jid: str, joints: Mapping[str, Mapping[str, Any]], body_of: Mapping[str, str]) -> Set[str]:
    """The parts a joint moves: its moving body, plus every body whose joint's fixed part it carries (chains)."""
    seed = joints[jid].get("moving")
    moved = {n for n, b in body_of.items() if b == seed} | ({seed} if seed else set())
    changed = True
    while changed:
        changed = False
        for other, j in joints.items():
            if other == jid or j.get("kind") == "fixed":
                continue
            if j.get("fixed") in moved and j.get("moving") not in moved:
                child = j.get("moving")
                moved |= {n for n, b in body_of.items() if b == child} | {child}
                changed = True
    return moved


def _explode(rec: _Record, sec_keys: Sequence[str], fnames: Sequence[str],
             scale: float) -> Tuple[Dict[str, List[float]], List[str]]:
    """``{key: offset}`` for the exploded view, and the section parts no step places."""
    keyset = set(sec_keys)
    fit_steps: List[Tuple[Dict[str, Any], List[str], Tuple[float, float, float]]] = []
    placed: Set[str] = set()
    for s in rec.steps:
        keys = [k for k in rec.keys_of(str(s.get("fit", ""))) if k in keyset and k not in placed]
        d = direction_vector(s.get("direction"))
        if keys and d is not None:
            fit_steps.append((s, keys, d))
            placed |= set(keys)
    offsets: Dict[str, List[float]] = {}
    n = len(fit_steps)
    if not n and not fnames:
        return offsets, []
    stride = min(0.3, 1.2 / max(n, 1)) * scale
    level_of: Dict[int, int] = {}
    for level, (s, keys, d) in enumerate(fit_steps):
        level_of[s["order"]] = level
        for k in keys:
            offsets[k] = _r([-c * stride * (level + 1) for c in d], 4)
    for fname in fnames:
        f = rec.fasteners[fname]
        install = next((s for s in rec.steps if fname in (s.get("fasteners") or [])), None) or \
            next((s for s in rec.steps if f.get("key") in (s.get("fasteners") or [])), None)
        base: List[float] = [0.0, 0.0, 0.0]
        if install is not None:
            host = next((k for k in rec.keys_of(str(install.get("fit", ""))) if k in offsets), None)
            if host:
                base = list(offsets[host])
        for inst in f.get("instances") or []:
            dd = inst.get("direction")
            if not (isinstance(dd, list) and len(dd) == 3):
                continue
            u = _unit(dd)
            offsets[str(inst.get("key"))] = _r([base[i] - u[i] * 0.25 * scale for i in range(3)], 4)
            placed.add(str(inst.get("key")))
    unplaced = sorted({owner(k) for k in sec_keys if k not in placed})
    return offsets, unplaced


def checklist_for(views: Sequence[Mapping[str, Any]], parts: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """The render checklist instantiated for a packet's views: one question per applicable item and target."""
    questions: List[Dict[str, Any]] = []

    def ask(item: Mapping[str, Any], qid: str, views_: List[str], **fmt: Any) -> None:
        questions.append({"id": qid, "item": item["id"], "question": item["question"].format(**fmt),
                          "views": views_, "bad_answer": item["bad_answer"], "gate": item["gate"]})

    by_kind: Dict[str, List[Mapping[str, Any]]] = {}
    for v in views:
        by_kind.setdefault(v["kind"], []).append(v)
    for item in CHECKLIST:
        kind, per = item["kind"], item["per"]
        if per is None:
            if kind == "solid":
                vs = [v["id"] for v in by_kind.get("solid", []) + by_kind.get("solid-rear", [])]
            else:
                vs = [v["id"] for v in by_kind.get(kind, [])]
            if vs:
                ask(item, item["id"], vs)
            continue
        for v in views:
            t = v.get("target") or {}
            if per == "cavity" and v["kind"] == "cut" and "cavity" in t and not v["id"].endswith("-plan"):
                cuts = [w["id"] for w in views if w["kind"] == "cut" and (w.get("target") or {}).get("cavity")
                        == t["cavity"]]
                for what in t.get("contains") or []:
                    ask(item, f"{item['id']}:{t['cavity']}:{what}", cuts, cavity=t["cavity"], what=what,
                        part=t.get("part"))
            elif per == "joint" and v["kind"] == "cut" and "joint" in t:
                ask(item, f"{item['id']}:{t['joint']}", [v["id"]], interface=t["joint"], moving=t.get("moving"),
                    fixed=t.get("fixed"))
            elif per == "fastener" and v["kind"] == "cut" and "fastener" in t:
                ask(item, f"{item['id']}:{t['fastener']}", [v["id"]], fastener=t["fastener"],
                    clamps=t.get("clamps"), into=t.get("into"))
            elif per == "access" and v["kind"] == "access":
                ask(item, f"{item['id']}:{v['id'][len('access-'):]}", [v["id"]],
                    fasteners=", ".join(t.get("fasteners") or []))
            elif per == "pose" and v["kind"] == "pose":
                p = v.get("pose") or {}
                contacts = ", ".join("-".join(map(str, c)) for c in t.get("contacts") or []) or "none"
                ask(item, f"{item['id']}:{v['id'][len('pose-'):]}", [v["id"]], interface=p.get("interface"),
                    value=f"{p.get('value')} {p.get('unit') or ''}".strip(), moving=t.get("moving"),
                    contacts=contacts)
    return {"schema": CHECKLIST_SCHEMA, "instructions": list(INSTRUCTIONS), "answers": list(ANSWERS),
            "measured_only": [dict(m) for m in MEASURED_ONLY], "items": checklist_items(), "questions": questions}


def packet_stale(manifest: Mapping[str, Any], record: Optional[Mapping[str, Any]]) -> Optional[str]:
    """None while the packet was made from ``record`` (its geometry digest matches), else why it is stale."""
    from cadagent.gates.verdict import geometry_digest
    if record is None:
        return "no geometry record to compare with"
    geo = manifest.get("geometry") if isinstance(manifest, Mapping) else None
    if not isinstance(geo, Mapping) or not geo.get("digest"):
        return "the packet records no geometry digest"
    if geo["digest"] != geometry_digest(record):
        return "the geometry changed since the packet was rendered: render it again"
    return None


def write_manifest(manifest: Mapping[str, Any], out_dir: Union[str, Path]) -> Path:
    out = Path(out_dir) / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1, sort_keys=False) + "\n")
    return out


# ------------------------------------------------------------------------------------------- rendering

def _rgb(hex_color: str, alpha: float = 1.0) -> Tuple[float, float, float, float]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, alpha)


def _posed(shape: Any, pose: Mapping[str, Any]) -> Any:
    cq = __import__("cadquery")
    axis = pose["axis"]
    o, d = cq.Vector(*axis["origin"]), cq.Vector(*axis["direction"])
    out = shape
    value = float(pose.get("value") or 0.0)
    if pose.get("unit") == "mm":
        return out.translate(d.normalized() * value)
    if value:
        out = out.rotate(o, o + d, value)
    if pose.get("slide_mm"):
        out = out.translate(d.normalized() * float(pose["slide_mm"]))
    return out


def render_views(manifest: Dict[str, Any], result: Any, out_dir: Union[str, Path], *,
                 size: Tuple[int, int] = (1400, 1000), only: Optional[Iterable[str]] = None,
                 renderer: Any = None) -> Dict[str, Any]:
    """Render the planned views of ``manifest`` from ``result`` (a dossier ``BuildResult`` with shapes) into
    ``out_dir``, filling ``views[].sha256`` (``file`` is set to null for views not rendered)."""
    from cadagent.render import Renderer

    out_dir = Path(out_dir)
    shapes = result.assembly_shapes()
    cavities = getattr(result, "cavities", {}) or {}
    parts = manifest["parts"]
    context = [c["key"] for c in manifest.get("context") or []]
    wanted = set(only) if only is not None else None
    sec = manifest["section"]
    subtitle = (f"section hash {manifest['section_hash'][:12]} | {sum(1 for p in parts.values() if p['kind'] == 'part')}"
                f" part(s), {sum(1 for p in parts.values() if p['kind'] == 'fastener')} fastener(s) | geometry "
                f"{manifest['geometry']['digest'][:12]} | for diagnosis, not proof")
    r = renderer or Renderer(out_dir, size=size, subtitle=subtitle, only=None)
    if renderer is not None:
        r.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
    contained = {w for v in manifest["views"] for w in ((v.get("target") or {}).get("contains") or [])}

    def color_of(key: str, kind: str) -> Tuple[float, float, float, float]:
        row = parts.get(owner(key)) or {}
        base = row.get("color", CONTEXT_COLOR)
        if kind == "xray":
            opaque = row.get("kind") == "fastener" or row.get("free") or owner(key) in contained
            return _rgb(base, 1.0 if opaque else 0.2)
        if kind == "findings":
            return _rgb(base, 0.55)
        return _rgb(base)

    for v in manifest["views"]:
        if wanted is not None and v["id"] not in wanted:
            v["file"] = None
            continue
        kind = v["kind"]
        pose = v.get("pose")
        moved = set(pose.get("keys") or []) if pose else set()
        items = []
        for key in v["keys"]:
            if key not in shapes:
                continue
            shp = _posed(shapes[key], pose) if key in moved else shapes[key]
            off = v.get("offsets", {}).get(key, (0.0, 0.0, 0.0))
            items.append((shp, color_of(key, kind), off))
        ctx_alpha = 0.85 if kind == "access" else 0.28
        for key in context:
            if key in shapes and key not in v["keys"]:
                shp = _posed(shapes[key], pose) if key in moved else shapes[key]
                items.append((shp, _rgb(CONTEXT_COLOR, ctx_alpha)))
        if kind == "xray":
            for cname, cshape in cavities.items():
                if any(cname == (vv.get("target") or {}).get("cavity") for vv in manifest["views"]):
                    items.append((cshape, _rgb(CAVITY_COLOR, 0.12)))
        if not items:
            v["file"] = None
            continue
        clip = v.get("clip")
        camera = v["camera"] if isinstance(v["camera"], str) else tuple(v["camera"])
        labels = []
        if v.get("callouts"):
            x0 = size[0] - 520
            for i, c in enumerate(v["callouts"]):
                labels.append((c["code"], c["text"], c["point"], (x0, 120 + i * 48)))
        fit = v.get("fit")
        path = r.render(v["file"], shapes=items, caption=v["caption"], note=v["note"], view=camera,
                        clip=(clip["origin"], clip["normal"]) if clip else None, labels=labels, size=size,
                        fit=(fit["min"], fit["max"]) if fit else None)
        v["sha256"] = file_sha256(path) if path else None
        if path is None:
            v["file"] = None
    manifest["rendered"] = sum(1 for v in manifest["views"] if v.get("sha256"))
    return manifest


def plan_project_packet(section: str, *, root: Union[str, Path] = ".", out_dir: Union[str, Path, None] = None,
                        explode: float = 1.0, context: str = "neighbours") -> Tuple[Dict[str, Any], Path]:
    """``plan_packet`` for a section of the project at ``root``, from its files: the geometry record, the dossier,
    the gate verdicts (staleness judged as ``cad-agent check`` does) and the dossier status. Returns the manifest
    and the directory it belongs in. Needs no CAD kernel."""
    from cadagent.dossier import load_project_dossier
    from cadagent.dossier.lint import project_evidence
    from cadagent.gates.verdict import _toolkit_version
    from cadagent.project import load_project

    project = load_project(root)
    ev = project_evidence(project)
    if ev.geometry is None:
        raise PacketError(f"no geometry record ({ev.geometry_file}): run the build (cad-agent gates --build) first")
    dossier = load_project_dossier(project, strict=False)
    exports = Path(project.exports_dir)
    target = Path(out_dir) if out_dir is not None else exports / "review" / safe_name(section)
    try:
        shown = target.resolve().relative_to(Path(project.root).resolve()).as_posix()
    except ValueError:
        shown = str(target)
    manifest = plan_packet(section, ev.geometry, dossier, ev.gates, _read_json(exports / "dossier-status.json"),
                           lint=_read_json(exports / "gates" / f"{LINT_GATE}.json"), expected=ev.expected,
                           record_file=ev.geometry_file, out_dir=shown, gate_files=ev.gate_files, explode=explode,
                           context=context, toolkit=_toolkit_version())
    return manifest, target


def project_sections(root: Union[str, Path] = ".") -> List[str]:
    """The section ids of the project at ``root`` (dossier order, then any only the build names)."""
    from cadagent.dossier import load_project_dossier
    from cadagent.project import load_project

    project = load_project(root)
    record = _read_json(Path(project.exports_dir) / "dossier-geometry.json")
    if record is None:
        raise PacketError("no geometry record (exports/dossier-geometry.json): run the build first")
    return sections_of(record, load_project_dossier(project, strict=False))


def review_packet(section: str, *, root: Union[str, Path] = ".", out_dir: Union[str, Path, None] = None,
                  size: Tuple[int, int] = (1400, 1000), explode: float = 1.0, context: str = "neighbours",
                  only: Optional[Iterable[str]] = None, renderer: Any = None) -> Dict[str, Any]:
    """Render the review packet of one dossier section of the project at ``root`` into
    ``<exports>/review/<section>/`` (or ``out_dir``) and write its ``manifest.json``; returns the manifest.

    Reads the geometry record and its shapes, the YAML dossier, the gate verdicts and the dossier status. Needs
    CadQuery, VTK and Pillow (``MissingDependency`` otherwise); ``plan_project_packet`` is the kernel-free half."""
    from cadagent._deps import require
    from cadagent.dossier import load_geometry

    for module, purpose in (("cadquery", "review packet shapes"), ("vtk", "review packet renders"),
                            ("PIL.Image", "review packet captions")):
        require(module, purpose)
    manifest, target = plan_project_packet(section, root=root, out_dir=out_dir, explode=explode, context=context)
    from cadagent.project import load_project
    result = load_geometry(Path(load_project(root).exports_dir) / "dossier-geometry.json")
    target.mkdir(parents=True, exist_ok=True)
    previous = _read_json(target / "manifest.json")
    render_views(manifest, result, target, size=size, only=only, renderer=renderer)
    if only is not None:
        _reuse(manifest, previous, target)
    keep = {v["file"] for v in manifest["views"] if v.get("file")}
    for old in target.glob("*.png"):        # images this packet does not list (another plan, or not current)
        if old.name not in keep:
            old.unlink()
    write_manifest(manifest, target)
    return manifest


def _reuse(manifest: Dict[str, Any], previous: Optional[Mapping[str, Any]], target: Path) -> None:
    """With ``only=``, keep an earlier packet's image of a view not rendered now when it is still current: the
    same geometry digest and section hash, the same planned view, and the file's bytes still match its hash."""
    if not isinstance(previous, Mapping) or previous.get("schema") != SCHEMA:
        return
    if (previous.get("geometry") or {}).get("digest") != manifest["geometry"]["digest"] or \
            previous.get("section_hash") != manifest["section_hash"]:
        return
    old = {v.get("id"): v for v in previous.get("views") or [] if isinstance(v, Mapping)}
    strip = ("file", "sha256")
    for v in manifest["views"]:
        if v.get("sha256"):
            continue
        p = old.get(v["id"])
        if not p or not p.get("file") or not p.get("sha256"):
            continue
        same = {k: x for k, x in p.items() if k not in strip} == {k: x for k, x in v.items() if k not in strip}
        path = target / str(p["file"])
        if same and path.is_file() and file_sha256(path) == p["sha256"]:
            v["file"], v["sha256"] = p["file"], p["sha256"]
    manifest["rendered"] = sum(1 for v in manifest["views"] if v.get("sha256"))


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
