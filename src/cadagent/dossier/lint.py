"""The dossier lint and status machine (plan ``docs/design-process-plan.md`` §3.2, §4.8, §5.3; ``docs/dossier.md``).

The lint is not geometric and needs no CAD kernel: it reads the loaded YAML dossier, the geometry record the build
wrote (``exports/dossier-geometry.json``), the gate verdicts (``exports/gates/*.json``), the project's configured
checks and the reviewer records (``dossier/reviews/*.json``). From them it

* checks every rule in ``RULES`` (the plan's §3.2 field table, the requirement trace, decision completeness, the
  YAML-to-registry join and the reviewer records), each finding with its file, line and code;
* runs the status machine for every part card and section, ``draft -> built -> gated -> reviewed -> signed_off``;
* computes each requirement's verification status.

``cad-agent dossier`` writes the result to ``exports/dossier-status.json`` (the site and the report read this file,
never the YAML) and the lint verdict to ``exports/gates/dossier-lint.json``; ``cad-agent check`` runs the same lint.

What it does not do: a dossier that lints clean is *declared* and its declarations agree with the build; whether
the geometry is right is the gates' job, whether the declarations meet the requirements is the reviewer's. Nothing
here proves physical fit or strength.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .model import PART_STATUS, Dossier, Issue, PartCard, Section, Where

STATUSES = PART_STATUS                       # draft, built, gated, reviewed, signed_off
RANK = {s: i for i, s in enumerate(STATUSES)}
KNOWN_GATES = ("wall", "connectivity", "containment", "fasteners", "motion", "assembly")
LINT_GATE = "dossier-lint"
STATUS_SCHEMA = "cad-agent.dossier-status/1"
REVIEW_SCHEMA = "cad-agent.review/1"
ADDITIVE = ("fdm", "fff", "sla", "sls", "mjf", "dlp", "polyjet", "additive", "3d print", "3d-print")
_ADDITIVE_RE = re.compile(r"\b(?:fdm|fff|sla|sls|mjf|dlp|polyjet|additive)\b|\b3d[ -]?print", re.I)

# code -> (severity, what the rule checks). Loader codes (unknown-id, bad-interface, ...) and the registry join's
# codes (card-without-shape, ...; docs/dossier.md "Joining cards and geometry") are reported under their own codes.
RULES: Dict[str, Tuple[str, str]] = {
    # part cards (plan §3.2, the minimum card)
    "card-no-function": ("error", "a part card states its function"),
    "card-no-interfaces": ("error", "a part card lists its interfaces (free parts, and a one-part dossier, excepted)"),
    "card-no-decision": ("warning", "a part card, or another card or the section it is in, records a decision"),
    # interfaces
    "interface-not-party": ("error", "a card lists only interfaces whose `between` names the part or its section"),
    "interface-one-sided": ("error", "an interface between two parts is listed on both parts' cards"),
    "interface-datum-conflict": ("error", "the two sections that declare an interface agree on its datum (§5.4)"),
    "interface-conflict": ("warning", "the two declarations of an interface agree on its other fields"),
    # fasteners
    "fastener-via-mismatch": ("error", "a card's fastener runs `via` an interface between this part and `to`"),
    # gate exemptions (gates.intended_overlaps, gates.ignore_pairs)
    "exemption-unknown-party": ("error", "a gates.intended_overlaps or ignore_pairs entry names parts, part instances "
                                         "or fasteners the build registered"),
    # material.wall_mm
    "wall-undeclared": ("error", "a card checked by gate:wall (an error) or made by an additive process "
                                 "(a warning) declares material.wall_mm"),
    # decisions
    "decision-incomplete": ("error", "a decided decision has a `why` and at least one alternative"),
    "alternative-no-reason": ("error", "every alternative says why it was rejected"),
    "decision-open": ("warning", "an open decision is decided; it blocks its section's sign-off"),
    # checks
    "unknown-check": ("error", "every check id is gate:<name> or a cad.checks id in cad-agent.yaml"),
    # requirements (trace)
    "requirement-untraced": ("error", "every requirement is referenced by a section"),
    "requirement-unchecked": ("error", "every requirement has a check (its own, or one on a card of its sections)"),
    "waiver-no-rationale": ("error", "a waived requirement says why in `rationale`"),
    "requirement-status-ignored": ("warning", "a requirement's status is computed; only `waived` belongs in YAML"),
    # sections
    "section-no-requirements": ("error", "a section names the requirements it serves"),
    "section-no-parts": ("warning", "a section has part cards"),
    "section-below-gated": ("error", "every section has reached the required status (§5.4: gated)"),
    # status claims
    "status-not-earned": ("error", "a card claims reviewed/signed_off only with a current reviewer record"),
    "status-overclaimed": ("warning", "a card's YAML status is not above the computed one"),
    # reviewer records
    "review-invalid": ("error", "a reviewer record is a JSON object with section, date, actor, signed_off, hashes"),
    "review-unknown-section": ("error", "a reviewer record names a section of the dossier"),
    "review-same-actor": ("error", "a sign-off is by an actor other than the build's, and not `unknown`"),
    "review-stale": ("warning", "the latest review still matches the geometry (else its sign-off is void)"),
    "signoff-open-decision": ("error", "a section with an open decision is not signed off"),
    # inputs
    "geometry-missing": ("warning", "the build's geometry record exists, so cards can be joined to shapes"),
    "geometry-invalid": ("error", "the geometry record is readable JSON"),
    "verdict-invalid": ("error", "a gate verdict is readable JSON"),
    "verdict-stale": ("error", "a gate verdict was computed from the current geometry record (its inputs match)"),
}


@dataclass
class Finding(Issue):
    """A lint finding: an ``Issue`` (code, message, file:line, severity) plus the item and parts it concerns."""
    item: str = ""
    parts: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        out = super().to_dict()
        if self.item:
            out["item"] = self.item
        if self.parts:
            out["parts"] = list(self.parts)
        return out


@dataclass
class CheckState:
    """A resolved check: ``pass``, ``fail``, ``unrun`` (its output does not exist yet), ``stale`` (a gate verdict
    computed from another geometry record) or ``unknown`` (no such id)."""
    id: str
    status: str
    message: str = ""
    file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out = {"id": self.id, "status": self.status}
        if self.message:
            out["message"] = self.message
        if self.file:
            out["file"] = self.file
        return out


@dataclass
class Review:
    """A reviewer sign-off record (``dossier/reviews/<section>-<date>.json``, schema ``cad-agent.review/1``).

    Only the fields the status machine needs are read here; the full schema and its validator are the reviewer
    pass's (plan T11). ``hashes`` maps each part reviewed to the content hash it had (``dossier-geometry.json``
    ``parts.<name>.sha256``)."""
    file: str
    section: str
    date: str
    actor: str
    signed_off: bool
    hashes: Dict[str, str]
    findings: List[Any] = field(default_factory=list)


@dataclass
class Evidence:
    """What the lint resolves the dossier against. Everything is optional: a missing geometry record leaves every
    card ``draft``, a missing verdict is ``unrun``."""
    geometry: Optional[Mapping[str, Any]] = None
    geometry_file: str = ""
    gates: Dict[str, Mapping[str, Any]] = field(default_factory=dict)       # gate name -> verdict dict
    gate_files: Dict[str, str] = field(default_factory=dict)
    checks: Dict[str, CheckState] = field(default_factory=dict)             # configured check id -> state
    reviews: List[Review] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)                   # problems reading the inputs
    root: Optional[str] = None      # the directory finding files are relative to: lets a loader error on any line
                                    # inside a card be attributed to that card
    expected: Dict[str, Mapping[str, Any]] = field(default_factory=dict)   # gate -> the declarations and options
                                    # its verdict must be bound to (cadagent.gates.run.expected_inputs); else only
                                    # the geometry is compared


@dataclass
class ItemStatus:
    status: str
    blocked_by: List[str] = field(default_factory=list)     # why it is not one status higher


@dataclass
class LintResult:
    """The lint findings and every item's computed status. ``passed`` is false when any finding is an error."""
    dossier: Optional[Dossier]
    findings: List[Finding]
    parts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    sections: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    requirements: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    decisions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    geometry_file: str = ""
    build_actor: str = ""
    min_section_status: Optional[str] = "gated"

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity != "error"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def codes(self) -> List[str]:
        return [f.code for f in self.findings]

    def to_status(self) -> Dict[str, Any]:
        """``exports/dossier-status.json``: every item with its status and evidence; no timestamp, so an unchanged
        dossier and build rewrite identical bytes."""
        d = self.dossier
        return {
            "schema": STATUS_SCHEMA,
            "dossier": d.file if d else "",
            "title": d.title if d else "",
            "statuses": list(STATUSES),
            "required_section_status": self.min_section_status,
            "pass": self.passed,
            "counts": {"error": len(self.errors), "warning": len(self.warnings),
                       "sections": _count(self.sections), "parts": _count(self.parts)},
            "geometry": {"file": self.geometry_file, "actor": self.build_actor},
            "sections": self.sections,
            "parts": self.parts,
            "requirements": self.requirements,
            "decisions": self.decisions,
            "findings": [f.to_dict() for f in self.findings],
            "physical_fit_verified": False,
        }

    def to_verdict(self) -> Dict[str, Any]:
        """The lint as a gate verdict (``exports/gates/dossier-lint.json``, ``cadagent.gate/1``): one check per
        finding (its id ``<code>@<file>:<line>``) and one passing check per rule with no finding."""
        from ..gates.verdict import Check, verdict

        checks: List[Check] = []
        seen: Dict[str, int] = {}
        for f in self.findings:
            cid = f"{f.code}@{f.where}" if f.where else f.code
            seen[cid] = seen.get(cid, 0) + 1
            if seen[cid] > 1:
                cid = f"{cid}#{seen[cid]}"
            evidence = {"code": f.code}
            if f.where:
                evidence.update(file=f.where.file, line=f.where.line)
            if f.item:
                evidence["item"] = f.item
            checks.append(Check(cid, "fail" if f.severity == "error" else "warn", f.message, parts=f.parts,
                                evidence=evidence))
        found = {f.code for f in self.findings}
        for code, (_, text) in RULES.items():
            if code not in found:
                checks.append(Check(f"rule:{code}", "pass", text))
        return verdict(LINT_GATE, checks, assumptions=[
            "declarations only: the lint checks that the dossier is complete and agrees with the build's geometry "
            "record, not that the geometry is right (the gates) or meets the requirements (the reviewer)",
            "a gate verdict counts only when its inputs match the current geometry record and, for a project, the "
            "gate's declarations and options (verdict-stale otherwise)",
        ], limits={"required_section_status": self.min_section_status},
            extra={"sections": {k: v["status"] for k, v in self.sections.items()},
                   "parts": {k: v["status"] for k, v in self.parts.items()}})


def _count(items: Mapping[str, Mapping[str, Any]]) -> Dict[str, int]:
    out = {s: 0 for s in STATUSES}
    for v in items.values():
        out[v["status"]] = out.get(v["status"], 0) + 1
    return out


def _sev(code: str) -> str:
    return RULES.get(code, ("error", ""))[0]


def _owner(key: str) -> str:
    return str(key).split("#", 1)[0]


# --------------------------------------------------------------------------------------------- reading inputs

def load_reviews(directory: Path, rel_to: Path) -> Tuple[List[Review], List[Finding]]:
    """Every ``*.json`` record in ``directory``. A record that cannot be read is a ``review-invalid`` finding."""
    reviews: List[Review] = []
    findings: List[Finding] = []
    if not directory.is_dir():
        return reviews, findings
    for path in sorted(directory.glob("*.json")):
        shown = _show(path, rel_to)
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            findings.append(Finding("review-invalid", f"cannot read reviewer record: {exc}", Where(shown), "error"))
            continue
        problems = []
        if not isinstance(data, dict):
            problems.append("not a JSON object")
            data = {}
        for key, kind in (("section", str), ("date", str), ("actor", str), ("signed_off", bool), ("hashes", dict)):
            if not isinstance(data.get(key), kind):
                problems.append(f"`{key}` missing or not a {kind.__name__}")
        if data.get("schema") not in (None, REVIEW_SCHEMA):
            problems.append(f"schema {data.get('schema')!r} is not {REVIEW_SCHEMA!r}")
        if problems:
            findings.append(Finding("review-invalid", "reviewer record: " + "; ".join(problems), Where(shown),
                                    "error", item=str(data.get("section", ""))))
            continue
        reviews.append(Review(file=shown, section=data["section"], date=data["date"], actor=data["actor"],
                              signed_off=data["signed_off"], hashes={str(k): str(v) for k, v in data["hashes"].items()},
                              findings=list(data.get("findings") or [])))
    return reviews, findings


def load_verdicts(directory: Path, rel_to: Path) -> Tuple[Dict[str, Mapping[str, Any]], Dict[str, str], List[Finding]]:
    """Gate verdicts in ``exports/gates/`` by gate name (the lint's own verdict excluded)."""
    gates: Dict[str, Mapping[str, Any]] = {}
    files: Dict[str, str] = {}
    findings: List[Finding] = []
    if not directory.is_dir():
        return gates, files, findings
    for path in sorted(directory.glob("*.json")):
        if path.stem == LINT_GATE:
            continue
        shown = _show(path, rel_to)
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            findings.append(Finding("verdict-invalid", f"cannot read gate verdict: {exc}", Where(shown), "error"))
            continue
        if not isinstance(data, dict) or "pass" not in data:
            findings.append(Finding("verdict-invalid", "gate verdict has no `pass` (not a cadagent.gate/1 file)",
                                    Where(shown), "error"))
            continue
        name = str(data.get("gate") or path.stem)
        gates[name], files[name] = data, shown
    return gates, files, findings


def configured_check_state(root: Path, check: Any) -> CheckState:
    """A ``cad.checks`` entry's state, by the same rule as the report: every ``pass_key`` must be ``true``."""
    from ..evidence import hashes_are_current
    from ..project import lookup

    path = root / check.file
    if not path.is_file():
        return CheckState(check.id, "unrun", f"{check.file} not written yet", check.file)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return CheckState(check.id, "fail", f"unreadable: {exc}", check.file)
    for key in check.pass_keys:
        found, value = lookup(data, key)
        if not found or value is not True:
            return CheckState(check.id, "fail", f"{key} is {value!r}" if found else f"{key} not present", check.file)
    if isinstance(data, dict) and not hashes_are_current(root, data):
        return CheckState(check.id, "fail", "source or artifact evidence is stale", check.file)
    return CheckState(check.id, "pass", "", check.file)


def project_evidence(project: Any) -> Evidence:
    """Everything a project has written that the lint resolves against: the geometry record, gate verdicts,
    configured checks and reviewer records (``dossier/reviews/`` beside ``project.yaml``)."""
    root = Path(project.root)
    ev = Evidence(root=str(root))
    geo = Path(project.exports_dir) / "dossier-geometry.json"
    ev.geometry_file = _show(geo, root)
    if geo.is_file():
        try:
            data = json.loads(geo.read_text())
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
            ev.geometry = data
        except (OSError, ValueError) as exc:
            ev.findings.append(Finding("geometry-invalid", f"cannot read the geometry record: {exc}",
                                       Where(ev.geometry_file), "error"))
    ev.gates, ev.gate_files, found = load_verdicts(Path(project.exports_dir) / "gates", root)
    ev.findings += found
    for c in project.checks:
        ev.checks[c.id] = configured_check_state(root, c)
    if project.dossier:
        ev.reviews, found = load_reviews(Path(project.dossier).parent / "reviews", root)
        ev.findings += found
    try:                            # what `cad-agent gates` binds each verdict to, so the lint and check agree
        from ..gates.run import GATES, GatesConfigError, expected_inputs, gates_config, load_dossier, load_extra
        cfg = gates_config(project)
        extra, dossier = load_extra(cfg), load_dossier(project)
        ev.expected = {g: expected_inputs(g, cfg, dossier, extra) for g in GATES}
    except (GatesConfigError, TypeError, ValueError):
        pass                        # a bad gates config is check's finding; compare the geometry only
    return ev


def _show(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------------------------- the lint

class _Linter:
    def __init__(self, d: Dossier, ev: Evidence, min_section_status: Optional[str], require_separate_reviewer: bool):
        self.d, self.ev = d, ev
        self.min = min_section_status
        self.separate = require_separate_reviewer
        self.out: List[Finding] = []
        geo = ev.geometry or {}
        self.geo_parts: Mapping[str, Any] = geo.get("parts", {}) if isinstance(geo.get("parts", {}), dict) else {}
        self.build_actor = str(geo.get("actor", "") or "unknown") if ev.geometry is not None else ""
        self.free = self._free_parts()
        self.where_part: Dict[Tuple[str, int], str] = {}
        self.file_part: Dict[str, str] = {}
        self.file_section: Dict[str, str] = {}
        for card in d.parts.values():
            for w in [card.where] + [c.where for c in card.contains] + [f.where for f in card.fasteners] \
                    + [x.where for x in card.decisions]:
                if w:
                    self.where_part[(w.file, w.line)] = card.id
            if card.file and card.where:
                self.file_part[card.where.file] = card.id
        for sec in d.sections.values():
            if sec.where and sec.file:
                self.file_section[sec.where.file] = sec.id
        self.card_lines = self._card_ranges()

    def _card_ranges(self) -> Dict[str, List[Tuple[int, int, str]]]:
        """Per file, the lines each nested card spans: from its first line to the line before the next one indented
        no deeper than its list dash. Needs the files (``Evidence.root``); without them only first lines match."""
        out: Dict[str, List[Tuple[int, int, str]]] = {}
        if self.ev.root is None:
            return out
        texts: Dict[str, List[str]] = {}
        for card in self.d.parts.values():
            w = card.where
            if card.file or not w or not w.line:
                continue
            if w.file not in texts:
                try:
                    texts[w.file] = (Path(self.ev.root) / w.file).read_text().splitlines()
                except OSError:
                    texts[w.file] = []
            lines = texts[w.file]
            if w.line > len(lines):
                continue
            first = lines[w.line - 1]
            col = len(first) - len(first.lstrip())
            end = w.line
            for j in range(w.line, len(lines)):
                text = lines[j]
                if text.strip() and not text.lstrip().startswith("#") and len(text) - len(text.lstrip()) <= col:
                    break
                end = j + 1
            out.setdefault(w.file, []).append((w.line, end, card.id))
        return out

    def _card_at(self, where: Where) -> str:
        pid = self.where_part.get((where.file, where.line)) or self.file_part.get(where.file)
        if pid:
            return pid
        for start, end, cid in self.card_lines.get(where.file, []):
            if start <= where.line <= end:
                return cid
        return ""

    def _dec_section(self, dec: Any) -> str:
        """A decision's section: its own, or its part's (a part-scoped decision in decisions.yaml names no section)."""
        if dec.section:
            return dec.section
        card = self.d.parts.get(dec.part) if dec.part else None
        return card.section if card else ""

    def add(self, code: str, message: str, where: Optional[Where], *, item: str = "", parts: Iterable[str] = (),
            severity: Optional[str] = None) -> None:
        self.out.append(Finding(code, message, where, severity or _sev(code), item=item, parts=tuple(parts)))

    def _free_parts(self) -> Set[str]:
        free = {fp.part for fp in self.d.gates.free_parts}
        free |= {c.what for card in self.d.parts.values() for c in card.contains if c.free}
        free |= {name for name, info in self.geo_parts.items() if isinstance(info, dict) and info.get("free")}
        return free

    # ---- inputs the loader and the join report
    def adopt(self, issues: Iterable[Issue], known_parts: Set[str]) -> None:
        for i in issues:
            if i.code == "interface-conflict":
                continue                    # recomputed below, split by field
            parts: Tuple[str, ...] = ()
            item = ""
            if i.where:
                pid = self._card_at(i.where)
                if pid:
                    parts = (pid,)
                elif i.where.file in self.file_section:
                    item = self.file_section[i.where.file]
            if not parts:
                named = [n for n in re.findall(r"'([^']+)'", i.message) if n in known_parts]
                parts = tuple(dict.fromkeys(named))
            if parts and not item:
                item = parts[0]
            self.out.append(Finding(i.code, i.message, i.where, i.severity, item=item, parts=parts))

    # ---- rules
    def cards(self) -> None:
        d = self.d
        decided_sections = {self._dec_section(x) for x in d.decisions.values()} - {""}
        decided_parts = {x.part for x in d.decisions.values() if x.part}
        for card in d.parts.values():
            w, pid = card.where, card.id
            if not card.function.strip():
                self.add("card-no-function", f"part {pid!r} has no `function`: say what the part does", w,
                         item=pid, parts=[pid])
            if not card.interfaces and pid not in self.free and len(d.parts) > 1:
                self.add("card-no-interfaces", f"part {pid!r} lists no interfaces: name what it joins (or declare it "
                                               "free with a reason in gates.free_parts)", w, item=pid, parts=[pid])
            if pid not in decided_parts and card.section not in decided_sections:
                self.add("card-no-decision", f"part {pid!r} and its section {card.section!r} record no decision "
                                             "(the minimum card has one, with why and a rejected alternative)", w,
                         item=pid, parts=[pid])
            for iid in card.interfaces:
                iface = d.interfaces.get(iid)
                if iface and iface.between and pid not in iface.between and card.section not in iface.between:
                    self.add("interface-not-party", f"part {pid!r} lists interface {iid!r}, which is between "
                                                    f"{iface.between}, not this part or its section {card.section!r}",
                             w, item=pid, parts=[pid])
            for use in card.fasteners:
                iface = d.interfaces.get(use.via) if use.via else None
                if iface is None:
                    continue
                ends = set(iface.between)
                mine = pid in ends or card.section in ends
                other = use.to in ends or (d.parts[use.to].section if use.to in d.parts else "") in ends
                if not (mine and other):
                    self.add("fastener-via-mismatch", f"part {pid!r} fastens to {use.to!r} via {use.via!r}, but that "
                                                      f"interface is between {iface.between}",
                             use.where or w, item=pid, parts=[pid])
            wall = card.material.wall_mm if card.material else None
            if wall is None:
                if "gate:wall" in card.checks:
                    self.add("wall-undeclared", f"part {pid!r} is checked by gate:wall but declares no "
                                                "material.wall_mm (the threshold is per part)", w, item=pid,
                             parts=[pid])
                elif card.material and _ADDITIVE_RE.search(card.material.process):
                    self.add("wall-undeclared", f"part {pid!r} is made by {card.material.process} but declares no "
                                                "material.wall_mm", w, item=pid, parts=[pid], severity="warning")

    def interfaces(self) -> None:
        d = self.d
        for iid, iface in d.interfaces.items():
            for party in iface.between:
                card = d.parts.get(party)
                if card is not None and iid not in card.interfaces:
                    other = [p for p in iface.between if p != party]
                    self.add("interface-one-sided", f"interface {iid!r} joins {party!r} to {other}, but {party!r}'s "
                                                    f"card does not list it (declared at {iface.where})",
                             card.where, item=party, parts=[party])
            decls = d.interface_declarations.get(iid, [])
            primary = iface
            for other in decls:
                if other is primary:
                    continue
                if other.datum and primary.datum and other.datum != primary.datum:
                    self.add("interface-datum-conflict", f"interface {iid!r} has datum {other.datum!r} here and "
                                                         f"{primary.datum!r} at {primary.where} (owner "
                                                         f"{primary.owner or 'not named'}); the owner's datum rules",
                             other.where, item=other.section or primary.section or iid,
                             parts=[p for p in iface.between if p in d.parts])
                diffs = [f for f in ("between", "kind", "clearance", "owner", "fastened_by")
                         if getattr(other, f) and getattr(primary, f) and
                         (sorted(getattr(other, f)) if f == "between" else getattr(other, f))
                         != (sorted(getattr(primary, f)) if f == "between" else getattr(primary, f))]
                if diffs:
                    self.add("interface-conflict", f"interface {iid!r} is declared differently here and at "
                                                   f"{primary.where}: {', '.join(diffs)} differ", other.where,
                             item=iid)

    def exemptions(self) -> None:
        """Each party of a pair exemption is something the build made: a part, one of its instance keys, a fastener
        or one of a fastener's instance keys (what the gates match exemptions against). Needs the geometry record;
        without it, names the YAML does not know stay unchecked (and geometry-missing says why)."""
        geo = self.ev.geometry
        if geo is None:
            return
        fasteners = geo.get("fasteners", {}) if isinstance(geo.get("fasteners"), dict) else {}
        keys: Dict[str, Set[str]] = {}
        for table in (self.geo_parts, fasteners):
            for name, info in table.items():
                insts = info.get("instances") if isinstance(info, dict) else None
                keys[name] = {str(i.get("key")) for i in insts or [] if isinstance(i, dict)}
                count = info.get("count") if isinstance(info, dict) else None
                if not keys[name] and isinstance(count, int) and count > 0:     # a record without instances
                    keys[name] = {name} if count == 1 else {f"{name}#{i}" for i in range(count)}
        for key in ("intended_overlaps", "ignore_pairs"):
            for ex in getattr(self.d.gates, key):
                a, b = ex.parts
                if a == b and a in keys and len(keys[a]) < 2:
                    self.add("exemption-unknown-party", f"gates.{key}: [{a}, {a}] means the instances of {a!r} "
                                                        f"among themselves, but the build makes {len(keys[a])}",
                             ex.where, item=a, parts=[a] if a in self.d.parts else [])
                for party in dict.fromkeys(ex.parts):
                    base = _owner(party)
                    if base not in keys and self.d.kind_of(base) not in (None, "part"):
                        continue            # another kind of dossier id: the loader's unknown-id reports it
                    if party in keys or (base in keys and party in keys[base]):
                        continue
                    if base in self.d.parts and base not in keys:
                        continue            # a card without a shape: card-without-shape reports it
                    if base in keys:
                        have = sorted(keys[base]) or [base]
                        why = (f"{base!r} has {len(have)} instance(s): " + ", ".join(have[:6])
                               + (" ..." if len(have) > 6 else ""))
                    else:
                        why = "the build registers no part or fastener of that name" + (
                            f" (fasteners: {', '.join(sorted(fasteners)[:8])})" if fasteners else "")
                    self.add("exemption-unknown-party", f"gates.{key}: {party!r} is not a part, part instance or "
                                                        f"fastener of the build: {why}", ex.where, item=party,
                             parts=[p for p in ex.parts if _owner(p) in self.d.parts])

    def decisions(self) -> None:
        for did, dec in self.d.decisions.items():
            parts = [dec.part] if dec.part else []
            sid = self._dec_section(dec)
            item = dec.part or sid or did
            if dec.status == "superseded":
                continue
            if dec.status == "open":
                self.add("decision-open", f"decision {did!r} is open"
                         + (f"; section {sid!r} cannot be signed off until it is decided" if sid else ""),
                         dec.where, item=item, parts=parts)
            else:
                missing = [k for k, ok in (("why", dec.why.strip()), ("an alternative", dec.alternatives)) if not ok]
                if missing:
                    self.add("decision-incomplete", f"decision {did!r} has no {' and no '.join(missing)}: record why "
                                                    "and the options rejected", dec.where, item=item, parts=parts)
            for alt in dec.alternatives:
                if not (alt.rejected or "").strip():
                    self.add("alternative-no-reason", f"decision {did!r}: alternative {alt.option!r} has no "
                                                      "`rejected` reason", dec.where, item=item, parts=parts)

    def resolve_check(self, cid: str) -> CheckState:
        if cid.startswith("gate:"):
            name = cid[5:]
            if name in self.ev.gates:
                v = self.ev.gates[name]
                stale = self.stale(name)
                if stale:
                    return CheckState(cid, "stale", stale, self.ev.gate_files.get(name, ""))
                return CheckState(cid, "pass" if v.get("pass") is True else "fail", str(v.get("status", "")),
                                  self.ev.gate_files.get(name, ""))
            if name in KNOWN_GATES:
                return CheckState(cid, "unrun", f"exports/gates/{name}.json not written yet")
            return CheckState(cid, "unknown", f"no gate {name!r} (known: {', '.join(KNOWN_GATES)})")
        if cid in self.ev.checks:
            return self.ev.checks[cid]
        return CheckState(cid, "unknown", "not a gate:<name> and not a cad.checks id in cad-agent.yaml")

    def stale(self, gate: str) -> Optional[str]:
        """Why gate ``gate``'s verdict is not from the current geometry record (None when it is)."""
        from ..gates.verdict import stale_reason
        if self.ev.geometry is None:
            return None             # nothing is built: cards stay draft, and geometry-missing says why
        return stale_reason(self.ev.gates[gate], self.ev.geometry, **dict(self.ev.expected.get(gate) or {}))

    def check_for_part(self, cid: str, pid: str) -> CheckState:
        """A gate verdict counts against a part when a failing finding names it (or names no part at all)."""
        state = self.resolve_check(cid)
        if state.status != "fail" or not cid.startswith("gate:"):
            return state
        v = self.ev.gates[cid[5:]]
        failing = [f for f in v.get("findings", []) if isinstance(f, dict) and f.get("status") == "fail"]
        named = [self._parts_named(f.get("parts") or []) for f in failing]
        mine = [f.get("id", "") for f, n in zip(failing, named) if not n or pid in n]
        if not failing or mine:
            return CheckState(cid, "fail", f"failing: {', '.join(mine[:5]) or v.get('status', 'fail')}", state.file)
        return CheckState(cid, "pass", "the gate fails on other parts only", state.file)

    def _parts_named(self, names: Iterable[Any]) -> Set[str]:
        """The part cards a gate finding's ``parts`` refer to: a part or one of its instances (``ball#3``), both parts
        of a fastener (what it clamps and what it threads into), a cavity's part. Empty when none is known, and a
        failing finding that names no known part counts against every part."""
        geo = self.ev.geometry or {}
        fasteners, cavities = geo.get("fasteners", {}) or {}, geo.get("cavities", {}) or {}
        out: Set[str] = set()
        for name in names:
            o = _owner(str(name))
            if o in self.d.parts or o in self.geo_parts:
                out.add(o)
            elif isinstance(fasteners.get(o), dict):
                out |= {fasteners[o].get("clamps"), fasteners[o].get("into")} - {None}
            elif isinstance(cavities.get(o), dict) and cavities[o].get("part"):
                out.add(cavities[o]["part"])
        return out

    def checks(self) -> None:
        d = self.d
        uses: List[Tuple[str, Optional[Where], str, List[str]]] = []
        for card in d.parts.values():
            uses += [(c, card.where, card.id, [card.id]) for c in card.checks]
        for req in d.requirements.values():
            uses += [(c, req.where, req.id, []) for c in req.checks]
        for dec in d.decisions.values():
            if dec.confirmation:
                uses.append((dec.confirmation, dec.where, dec.id, [dec.part] if dec.part else []))
        for step in d.assembly:
            if step.access_check:
                uses.append((step.access_check, step.where, f"step {step.order}", []))
        for cid, where, item, parts in uses:
            if self.resolve_check(cid).status == "unknown":
                self.add("unknown-check", f"{item}: check {cid!r} does not resolve: "
                                          f"{self.resolve_check(cid).message}", where, item=item, parts=parts)

    def requirements(self) -> None:
        d = self.d
        for rid, req in d.requirements.items():
            if req.status and req.status != "waived":
                self.add("requirement-status-ignored", f"requirement {rid!r} says status {req.status!r}; the lint "
                                                       "computes it (only `waived` belongs in YAML)", req.where,
                         item=rid)
            if req.status == "waived":
                if not req.rationale.strip():
                    self.add("waiver-no-rationale", f"requirement {rid!r} is waived without a `rationale`", req.where,
                             item=rid)
                continue
            sections = [s for s in d.sections.values() if rid in s.requirements]
            children = [r for r in d.requirements.values() if r.parent == rid]
            if not sections and not children:
                self.add("requirement-untraced", f"requirement {rid!r} is not referenced by any section (or derived "
                                                 "into one that is)", req.where, item=rid)
            if not self.req_checks(rid) and not children:
                self.add("requirement-unchecked", f"requirement {rid!r} has no check: list one in its `checks`, or "
                                                  "on a card in a section that serves it", req.where, item=rid)

    def req_checks(self, rid: str) -> List[str]:
        req = self.d.requirements[rid]
        out = list(req.checks)
        for s in self.d.sections.values():
            if rid in s.requirements:
                out += [c for card in s.parts for c in card.checks]
        return list(dict.fromkeys(out))

    def sections(self) -> None:
        for sid, sec in self.d.sections.items():
            if not sec.requirements:
                self.add("section-no-requirements", f"section {sid!r} names no requirements it serves", sec.where,
                         item=sid)
            if not sec.parts:
                self.add("section-no-parts", f"section {sid!r} has no part cards", sec.where, item=sid)

    # ---- status machine
    def run(self) -> LintResult:
        d = self.d
        known = set(d.parts) | set(self.geo_parts)
        self.adopt(d.errors, known)
        self.adopt(d.findings, known)
        self.out += self.ev.findings
        if self.ev.geometry is None:
            if not any(f.code == "geometry-invalid" for f in self.ev.findings):
                self.add("geometry-missing", f"no geometry record ({self.ev.geometry_file or 'not given'}): cards "
                                             "cannot be joined to shapes and stay draft; run the build",
                         Where(self.ev.geometry_file) if self.ev.geometry_file else None)
        else:
            from .registry import join
            self.adopt(join(d, self.ev.geometry), known)
            for name in sorted(self.ev.gates):
                why = self.stale(name)
                if why:
                    file = self.ev.gate_files.get(name) or f"exports/gates/{name}.json"
                    self.add("verdict-stale", f"gate {name!r}: {why}; it does not count until the gates run again",
                             Where(file), item=f"gate:{name}")
        self.cards()
        self.interfaces()
        self.exemptions()
        self.decisions()
        self.checks()
        self.requirements()
        self.sections()

        res = LintResult(d, [], geometry_file=self.ev.geometry_file, build_actor=self.build_actor,
                         min_section_status=self.min)
        open_decisions = self._open_decisions()
        reviews = self._reviews(open_decisions)
        for pid, card in d.parts.items():
            res.parts[pid] = self._part_status(card, reviews.get(card.section, {}), open_decisions)
        for sid, sec in d.sections.items():
            res.sections[sid] = self._section_status(sec, res.parts, reviews.get(sid, {}), open_decisions)
        for pid, card in d.parts.items():
            self._claims(card, res.parts[pid]["status"])
        if self.min:
            for sid, row in res.sections.items():
                if RANK[row["status"]] < RANK[self.min]:
                    sec = d.sections[sid]
                    blocking = sorted(p for p in row["parts"] if RANK[res.parts[p]["status"]] < RANK[self.min])
                    self.add("section-below-gated", f"section {sid!r} is {row['status']}, below {self.min}: "
                                                    + "; ".join(row["blocked_by"][:4]), sec.where, item=sid,
                             parts=blocking)
        for rid in d.requirements:
            self._requirement_status(rid, res)
        res.requirements = {rid: res.requirements[rid] for rid in d.requirements}
        for did, dec in d.decisions.items():
            res.decisions[did] = {"scope": dec.scope, "status": dec.status,
                                  "complete": dec.status != "decided" or bool(dec.why.strip() and dec.alternatives
                                                                              and all((a.rejected or "").strip()
                                                                                      for a in dec.alternatives)),
                                  **({"section": dec.section} if dec.section else {}),
                                  **({"part": dec.part} if dec.part else {}), **_where_dict(dec.where)}
        res.findings = sorted(self.out, key=lambda f: (f.where.file if f.where else "", f.where.line if f.where else 0))
        for row in list(res.parts.values()) + list(res.sections.values()):
            row["findings"] = sum(1 for f in self.out if f.severity == "error" and
                                  (f.item == row["id"] or row["id"] in f.parts))
        return res

    def _open_decisions(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for did, dec in self.d.decisions.items():
            sid = self._dec_section(dec)
            if dec.status == "open" and sid:
                out.setdefault(sid, []).append(did)
        return out

    def _reviews(self, open_decisions: Mapping[str, List[str]]) -> Dict[str, Dict[str, Any]]:
        """Per section: the latest record whose hashes match the current build, and what made others void."""
        out: Dict[str, Dict[str, Any]] = {}
        by_section: Dict[str, List[Review]] = {}
        for r in self.ev.reviews:
            if r.section not in self.d.sections:
                self.add("review-unknown-section", f"reviewer record names section {r.section!r}, which is not in "
                                                   "the dossier", Where(r.file), item=r.section)
                continue
            if self.ev.geometry is None:
                by_section.setdefault(r.section, []).append(r)      # nothing is built, so nothing can be reviewed
                continue
            if self.separate and (r.actor.strip() in ("", "unknown") or r.actor == self.build_actor
                                  or self.build_actor in ("", "unknown")):
                why = ("the reviewer's actor is unknown" if r.actor.strip() in ("", "unknown") else
                       "the build's actor is unknown (set CAD_AGENT_ACTOR for the build)"
                       if self.build_actor in ("", "unknown") else f"the reviewer is the build's actor {r.actor!r}")
                self.add("review-same-actor", f"reviewer record for section {r.section!r} is refused: {why}; a "
                                              "separate reviewer is required", Where(r.file), item=r.section)
                continue
            by_section.setdefault(r.section, []).append(r)
        for sid, records in by_section.items():
            sec = self.d.sections[sid]
            current = {c.id: self._sha(c.id) for c in sec.parts}
            records.sort(key=lambda r: (r.date, r.file))

            def stale(r: Review) -> List[str]:
                return sorted(p for p, h in current.items() if not h or r.hashes.get(p) != h)

            matching = [r for r in records if not stale(r)]
            info: Dict[str, Any] = {"record": None}
            if matching:
                info["record"] = matching[-1]
            latest = records[-1]
            if stale(latest):
                changed = stale(latest)
                info["invalidated"] = {"record": latest.file, "date": latest.date, "signed_off": latest.signed_off,
                                       "changed": changed}
                self.add("review-stale", f"the review of section {sid!r} on {latest.date} ({latest.file}) no longer "
                                         f"applies: {', '.join(changed)} changed or not built since", Where(latest.file),
                         item=sid, parts=changed)
            rec = info["record"]
            if rec is not None and rec.signed_off and open_decisions.get(sid):
                self.add("signoff-open-decision", f"section {sid!r} is signed off in {rec.file} with open decision(s) "
                                                  f"{', '.join(open_decisions[sid])}", Where(rec.file), item=sid)
            out[sid] = info
        return out

    def _sha(self, pid: str) -> str:
        info = self.geo_parts.get(pid)
        return str(info.get("sha256", "")) if isinstance(info, dict) else ""

    def _part_status(self, card: PartCard, review: Mapping[str, Any], open_decisions: Mapping[str, List[str]]
                     ) -> Dict[str, Any]:
        pid = card.id
        errors = [f for f in self.out if f.severity == "error" and pid in f.parts]
        applicable = list(dict.fromkeys(list(card.checks) + [f"gate:{g}" for g in self.ev.gates]))
        states = [self.check_for_part(c, pid) for c in applicable]
        row: Dict[str, Any] = {"id": pid, "section": card.section, **_where_dict(card.where),
                               "claimed": card.status, "sha256": self._sha(pid),
                               "checks": [s.to_dict() for s in states]}
        status, blocked = "draft", []
        if errors:
            blocked = [f"{len(errors)} lint error(s): " + ", ".join(dict.fromkeys(f.code for f in errors))]
        elif self.ev.geometry is None:
            blocked = ["no geometry record"]
        elif pid not in self.geo_parts:
            blocked = ["no registered shape"]
        else:
            status = "built"
            bad = [s for s in states if s.status != "pass"]
            if not states:
                blocked = ["no check applies (list checks on the card, or run the gates)"]
            elif bad:
                blocked = [f"{s.id} {s.status}" + (f" ({s.message})" if s.message else "") for s in bad]
            else:
                status = "gated"
                rec: Optional[Review] = review.get("record")
                if rec is None:
                    blocked = ["no current reviewer record" + (" (geometry changed since the last review)"
                                                               if review.get("invalidated") else "")]
                else:
                    status = "reviewed"
                    if not rec.signed_off:
                        blocked = [f"{rec.file} does not sign off"]
                    elif open_decisions.get(card.section):
                        blocked = [f"open decision(s) {', '.join(open_decisions[card.section])}"]
                    else:
                        status = "signed_off"
        row["status"] = status
        row["blocked_by"] = blocked
        if review.get("record") is not None and status in ("reviewed", "signed_off"):
            rec = review["record"]
            row["review"] = {"record": rec.file, "date": rec.date, "actor": rec.actor}
        if review.get("invalidated") and pid in review["invalidated"]["changed"]:
            row["invalidated"] = review["invalidated"]
        return row

    def _section_status(self, sec: Section, parts: Mapping[str, Mapping[str, Any]], review: Mapping[str, Any],
                        open_decisions: Mapping[str, List[str]]) -> Dict[str, Any]:
        own = [f for f in self.out if f.severity == "error" and f.item == sec.id
               and not f.code.startswith(("review-", "signoff-"))]     # a refused record is not the section's fault
        rows = [parts[c.id] for c in sec.parts]
        row: Dict[str, Any] = {"id": sec.id, "title": sec.title, **_where_dict(sec.where),
                               "requirements": list(sec.requirements), "parts": [c.id for c in sec.parts],
                               "open_decisions": open_decisions.get(sec.id, [])}
        if own:
            status = "draft"
            blocked = [f"{len(own)} lint error(s) on the section: " + ", ".join(dict.fromkeys(f.code for f in own))]
        elif not rows:
            status, blocked = "draft", ["no part cards"]
        else:
            status = min((r["status"] for r in rows), key=lambda s: RANK[s])
            blocked = [f"{r['id']}: {'; '.join(r['blocked_by'])}" for r in rows if r["status"] == status
                       and r["blocked_by"]]
        row["status"], row["blocked_by"] = status, blocked
        rec = review.get("record")
        row["review"] = ({"record": rec.file, "date": rec.date, "actor": rec.actor, "signed_off": rec.signed_off,
                          "findings": len(rec.findings)} if rec is not None else None)
        if review.get("invalidated"):
            row["invalidated"] = review["invalidated"]
        return row

    def _claims(self, card: PartCard, computed: str) -> None:
        claimed = card.status or "draft"
        if RANK.get(claimed, 0) <= RANK[computed]:
            return
        if claimed in ("reviewed", "signed_off"):
            self.add("status-not-earned", f"part {card.id!r} says status {claimed!r}, but the evidence gives "
                                          f"{computed!r}: only a current reviewer record sets reviewed or signed_off "
                                          "(remove `status:`; it is computed into exports/dossier-status.json)",
                     card.where, item=card.id)
        else:
            self.add("status-overclaimed", f"part {card.id!r} says status {claimed!r}; the evidence gives "
                                           f"{computed!r}", card.where, item=card.id)

    def _requirement_status(self, rid: str, res: LintResult) -> Dict[str, Any]:
        """Only the requirement's own ``checks`` and its derived requirements are evidence for it. Checks on the
        cards of the sections that serve it are listed as ``covered_by`` (they satisfy the trace rule) but verify
        nothing on their own: a wall gate passing says nothing about "the lid stays on"."""
        if rid in res.requirements:
            return res.requirements[rid]
        d = self.d
        req = d.requirements[rid]
        res.requirements[rid] = {"status": "unverified"}          # a guard against a parent cycle
        sections = [s.id for s in d.sections.values() if rid in s.requirements]
        states = [self.resolve_check(c) for c in req.checks]
        row: Dict[str, Any] = {"text": req.text, "verify_by": req.verify_by, "sections": sections,
                               "checks": [s.to_dict() for s in states], **_where_dict(req.where)}
        covered = [c for c in self.req_checks(rid) if c not in req.checks]
        if covered:
            row["covered_by"] = covered
        children = [r.id for r in d.requirements.values() if r.parent == rid]
        kids = [self._requirement_status(c, res)["status"] for c in children]
        if children:
            row["derived"] = children
        own_ok = all(s.status == "pass" for s in states)
        reviewed = req.verify_by != "inspection" or all(
            RANK[res.sections[s]["status"]] >= RANK["reviewed"] for s in sections)
        if req.status == "waived":
            status = "waived"
        elif req.verify_by in ("test", "demo"):
            status = "not_tested"            # cad-agent cannot run a physical test or demonstration
        elif any(s.status == "fail" for s in states) or "failed" in kids:
            status = "failed"
        elif not states and not kids:
            status = "unverified"            # no evidence of its own (card checks alone do not verify it)
        elif own_ok and reviewed and all(k in ("verified", "waived") for k in kids):
            status = "verified"
        elif own_ok and reviewed and "not_tested" in kids and all(
                k in ("verified", "waived", "not_tested") for k in kids):
            status = "not_tested"
        else:
            status = "unverified"
        row["status"] = status
        res.requirements[rid] = row
        return row


def _where_dict(where: Optional[Where]) -> Dict[str, Any]:
    return {"file": where.file, "line": where.line} if where else {}


# ------------------------------------------------------------------------------------------------- entry points

def lint(dossier: Dossier, evidence: Optional[Evidence] = None, *, min_section_status: Optional[str] = "gated",
         require_separate_reviewer: bool = True) -> LintResult:
    """Lint a loaded dossier (load it with ``strict=False`` so its loader errors become findings) against
    ``evidence`` and compute every item's status. ``min_section_status`` (default ``gated``, plan §5.4) adds a
    ``section-below-gated`` error for each section below it; ``None`` leaves statuses informational."""
    if min_section_status is not None and min_section_status not in RANK:
        raise ValueError(f"min_section_status must be one of {STATUSES}, got {min_section_status!r}")
    return _Linter(dossier, evidence or Evidence(), min_section_status, require_separate_reviewer).run()


def lint_project(project: Any, *, min_section_status: Optional[str] = "gated",
                 require_separate_reviewer: bool = True) -> Optional[LintResult]:
    """Lint the project's dossier (``cad: dossier:``) against what the project has written. None when the project
    has no dossier. A dossier whose top file cannot be read or parsed gives a result with only those findings."""
    from .load import DossierError, load_project_dossier

    if not getattr(project, "dossier", None):
        return None
    try:
        d = load_project_dossier(project, strict=False)
    except DossierError as exc:
        res = LintResult(None, [Finding(i.code, i.message, i.where, i.severity) for i in exc.issues],
                         min_section_status=min_section_status)
        return res
    return lint(d, project_evidence(project), min_section_status=min_section_status,
                require_separate_reviewer=require_separate_reviewer)


def write_outputs(result: LintResult, exports_dir: Any) -> Tuple[Path, Path]:
    """Write ``dossier-status.json`` and ``gates/dossier-lint.json`` under ``exports_dir``."""
    from ..gates.verdict import write_verdict

    exports = Path(exports_dir)
    exports.mkdir(parents=True, exist_ok=True)
    status = exports / "dossier-status.json"
    status.write_text(json.dumps(result.to_status(), indent=2) + "\n")
    verdict = write_verdict(exports / "gates" / f"{LINT_GATE}.json", result.to_verdict())
    return status, verdict


__all__ = ["ADDITIVE", "CheckState", "Evidence", "Finding", "KNOWN_GATES", "LINT_GATE", "LintResult", "RANK",
           "REVIEW_SCHEMA", "RULES", "Review", "STATUSES", "STATUS_SCHEMA", "configured_check_state", "lint",
           "lint_project", "load_reviews", "load_verdicts", "project_evidence", "write_outputs"]
