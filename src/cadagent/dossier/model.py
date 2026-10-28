"""The design dossier's data model: requirements, sections, part spec cards, interfaces, decisions, assembly steps
and the gate configuration (``docs/dossier.md``; plan ``docs/design-process-plan.md`` §3).

Plain dataclasses, no kernel. ``cadagent.dossier.load`` builds them from YAML with file and line for every item;
``to_dict()`` writes them back in the same shape (fields left at their default are omitted), so a hand-written card
round-trips. Statuses that the toolchain computes (a requirement's verification, a section's sign-off) are not
trusted from YAML: the dossier lint and the reviewer pass set them.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]*$")

SOURCE_KINDS = ("user", "standard", "derived", "research", "agent")
VERIFY_BY = ("analysis", "inspection", "test", "demo")
REQUIREMENT_STATUS = ("unverified", "verified", "failed", "not_tested", "waived")
DECISION_STATUS = ("decided", "open", "superseded")
DECISION_SCOPES = ("project", "section", "part")
PART_STATUS = ("draft", "built", "gated", "reviewed", "signed_off")
INTERFACE_KINDS = (
    # mechanical, rigid (0 DOF): the connectivity gate expects contact or a declared gap
    "fastened", "bonded", "press_fit", "snap_fit", "contact", "gap",
    # mechanisms (Onshape / build123d joint vocabulary): a joint links the parts without contact
    "revolute", "slider", "cylindrical", "planar", "ball",
    # what crosses the interface is not (only) mechanical
    "electrical", "thermal", "fluid", "other",
)
JOINT_KINDS = ("fixed", "revolute", "slider", "cylindrical", "planar", "ball")
DIRECTION_RE = re.compile(r"^[+-][XYZ]$")


@dataclass(frozen=True)
class Where:
    """The file and 1-based line an item was read from."""
    file: str
    line: int = 0

    def __str__(self) -> str:
        return f"{self.file}:{self.line}" if self.line else self.file


def _meta(dump: bool = True) -> Dict[str, Any]:
    return {"dump": dump}


def _where() -> Any:
    return field(default=None, compare=False, repr=False, metadata=_meta(False))


class _Dump:
    """``to_dict()`` for the dataclasses below: fields at their default are left out, nested dataclasses recurse."""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            if not f.metadata.get("dump", True):
                continue
            value = getattr(self, f.name)
            if f.default is not dataclasses.MISSING and value == f.default:
                continue
            if f.default_factory is not dataclasses.MISSING and value == f.default_factory():  # type: ignore[misc]
                continue
            out[f.name] = _plain(value)
        return out


def _plain(value: Any) -> Any:
    if isinstance(value, _Dump):
        return value.to_dict()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


@dataclass
class Source(_Dump):
    """Where a requirement or decision came from. ``quote`` is the user's own words when ``kind`` is ``user``."""
    kind: str = ""
    quote: str = ""
    ref: str = ""


@dataclass
class Requirement(_Dump):
    id: str
    text: str = ""
    source: Optional[Source] = None
    verify_by: str = ""                 # analysis | inspection | test | demo
    parent: str = ""                    # requirement id this one is derived from
    rationale: str = ""
    checks: List[str] = field(default_factory=list)   # check or gate ids that verify it directly
    status: str = ""                    # computed by the lint; in YAML only `waived` (with a rationale) is meaningful
    where: Optional[Where] = _where()


@dataclass
class Alternative(_Dump):
    """An option considered and not chosen. ``rejected`` is the reason; a bare string (the site's older format)
    loads with ``rejected=None`` and dumps back as a string, and the lint reports it as missing a reason."""
    option: str
    rejected: Optional[str] = None

    def to_dict(self) -> Any:  # type: ignore[override]
        if self.rejected is None:
            return self.option
        return {"option": self.option, "rejected": self.rejected}


@dataclass
class Decision(_Dump):
    """A decision record (MADR / ADR shape). ``scope`` and its target (``section`` / ``part``) are set from where
    the decision is written; in ``decisions.yaml`` they are written out."""
    id: str
    title: str = ""
    decision: str = ""
    why: str = ""
    status: str = "decided"             # decided | open | superseded
    date: str = ""
    scope: str = "project"              # project | section | part
    section: str = ""
    part: str = ""
    source: Optional[Source] = None
    alternatives: List[Alternative] = field(default_factory=list)
    consequences: str = ""
    confirmation: str = ""              # the check id that shows the decision still holds
    superseded_by: str = ""
    author: str = ""                    # agent or session id, or a person (the reviewer pass compares it)
    where: Optional[Where] = _where()
    nested: bool = field(default=False, compare=False, repr=False, metadata=_meta(False))

    def to_dict(self) -> Dict[str, Any]:
        out = super().to_dict()
        if self.nested:                 # implied by where it is written
            for key in ("scope", "section", "part"):
                out.pop(key, None)
        return out


@dataclass
class Interface(_Dump):
    """One row of an interface control document: two parties (parts or sections), what kind of joint, the datum,
    what crosses it and who owns it."""
    id: str
    between: List[str] = field(default_factory=list)
    kind: str = ""
    datum: str = ""
    loads: Dict[str, Any] = field(default_factory=dict)
    fastened_by: str = ""
    clearance: Optional[float] = None   # mm: the declared gap the connectivity gate accepts
    owner: str = ""                     # the section (or part) that may change the datum
    description: str = ""
    section: str = field(default="", metadata=_meta(False))     # the section it was declared in ("" = project)
    where: Optional[Where] = _where()


@dataclass
class Material(_Dump):
    name: str = ""
    process: str = ""
    print_axis: str = ""
    wall_mm: Optional[float] = None     # the minimum-wall gate's threshold for this part
    notes: str = ""


@dataclass
class FastenerUse(_Dump):
    """A card's fastener entry: ``qty`` of catalogue item ``screws`` join this part ``to`` another along ``via``."""
    to: str = ""
    screws: str = ""                    # catalogue key (McMaster skill or cadagent.fasteners)
    qty: Optional[int] = None
    via: str = ""                       # interface id
    note: str = ""
    where: Optional[Where] = _where()


@dataclass
class Containment(_Dump):
    """``count`` instances of part ``what`` sit inside this part's ``cavity`` (registered in code)."""
    what: str = ""
    count: Optional[int] = None
    cavity: str = ""
    free: bool = False                  # loose items: exempt from the floating-part gate
    where: Optional[Where] = _where()


@dataclass
class PartCard(_Dump):
    """The part spec card (plan §3.2). The minimum a lint accepts: ``function``, ``interfaces`` and one decision."""
    id: str
    function: str = ""
    interfaces: List[str] = field(default_factory=list)
    loads: Dict[str, Any] = field(default_factory=dict)
    material: Optional[Material] = None
    fasteners: List[FastenerUse] = field(default_factory=list)
    contains: List[Containment] = field(default_factory=list)
    decisions: List[Decision] = field(default_factory=list)
    checks: List[str] = field(default_factory=list)
    status: str = "draft"               # draft | built | gated | reviewed | signed_off
    author: str = ""
    notes: str = ""
    section: str = field(default="", metadata=_meta(False))
    file: str = field(default="", compare=False, repr=False, metadata=_meta(False))   # set when split into its own file
    where: Optional[Where] = _where()


@dataclass
class Section(_Dump):
    id: str
    title: str = ""
    purpose: str = ""
    requirements: List[str] = field(default_factory=list)
    interfaces: List[Interface] = field(default_factory=list)
    parts: List[PartCard] = field(default_factory=list)
    decisions: List[Decision] = field(default_factory=list)
    review: Dict[str, Any] = field(default_factory=dict)   # the author's `self` critique; records live in reviews/
    author: str = ""
    notes: str = ""
    file: str = field(default="", compare=False, repr=False, metadata=_meta(False))
    where: Optional[Where] = _where()

    def to_dict(self) -> Dict[str, Any]:
        out = super().to_dict()
        if self.parts:                  # a card split into its own file is written back as its path
            out["parts"] = [p.file if p.file else p.to_dict() for p in self.parts]
        return out


@dataclass
class AssemblyStep(_Dump):
    """One row of the assembly sequence: fit ``fit`` onto ``onto`` from ``direction`` with ``tool``."""
    order: int
    fit: str = ""
    onto: List[str] = field(default_factory=list)
    direction: Any = ""                 # "+X" .. "-Z", or [x, y, z]: the direction the part moves to its seat
    tool: str = ""
    fasteners: List[str] = field(default_factory=list)   # catalogue keys or registered fastener names
    access_check: str = ""
    note: str = ""
    where: Optional[Where] = _where()

    def to_dict(self) -> Dict[str, Any]:
        out = super().to_dict()
        if len(self.onto) == 1:
            out["onto"] = self.onto[0]
        return out


@dataclass
class FreePart(_Dump):
    part: str
    reason: str = ""

    def to_dict(self) -> Any:  # type: ignore[override]
        return {"part": self.part, "reason": self.reason} if self.reason else self.part


@dataclass
class PairExemption(_Dump):
    """A pair the gates exempt, with its reason. A party is a part, an instance key (``ball#3``) or a fastener name
    or instance key (``screw_0``, ``m3:lid-base#1``); the lint resolves the last two against the geometry record."""
    parts: Tuple[str, str]
    reason: str = ""
    where: Optional[Where] = _where()

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"parts": list(self.parts)}
        if self.reason:
            out["reason"] = self.reason
        return out


@dataclass
class GateConfig(_Dump):
    """``gates:`` in ``dossier/project.yaml`` (plan §4.1). Keys the schema does not know yet are kept in ``extra``
    (and reported) so a new gate option works before this schema catches up."""
    touch_tol_mm: float = 0.01
    grounded: List[str] = field(default_factory=list)
    free_parts: List[FreePart] = field(default_factory=list)
    intended_overlaps: List[PairExemption] = field(default_factory=list)
    ignore_pairs: List[PairExemption] = field(default_factory=list)
    strict_interfaces: bool = False
    motion_samples: int = 12
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = super().to_dict()
        out.update(out.pop("extra", {}))
        return out


@dataclass
class Issue:
    """A loader error or finding, with the file and line it refers to."""
    code: str
    message: str
    where: Optional[Where] = None
    severity: str = "error"             # error | warning

    def __str__(self) -> str:
        return f"{self.where}: {self.message}" if self.where else self.message

    def to_dict(self) -> Dict[str, Any]:
        out = {"code": self.code, "severity": self.severity, "message": self.message}
        if self.where:
            out.update(file=self.where.file, line=self.where.line)
        return out


@dataclass
class Dossier:
    """A loaded dossier. Lists from every file are flattened into id-keyed dicts; ``sections`` keeps file order."""
    file: str
    title: str = ""
    requirements: Dict[str, Requirement] = field(default_factory=dict)
    sections: Dict[str, Section] = field(default_factory=dict)
    parts: Dict[str, PartCard] = field(default_factory=dict)
    interfaces: Dict[str, Interface] = field(default_factory=dict)
    interface_declarations: Dict[str, List[Interface]] = field(default_factory=dict)
    decisions: Dict[str, Decision] = field(default_factory=dict)
    assembly: List[AssemblyStep] = field(default_factory=list)
    gates: GateConfig = field(default_factory=GateConfig)
    findings: List[Issue] = field(default_factory=list)    # warnings: unknown keys, interface conflicts
    errors: List[Issue] = field(default_factory=list)      # only when loaded with strict=False

    def section_of(self, part_id: str) -> Optional[Section]:
        card = self.parts.get(part_id)
        return self.sections.get(card.section) if card else None

    def kind_of(self, item_id: str) -> Optional[str]:
        for kind, table in (("requirement", self.requirements), ("section", self.sections), ("part", self.parts),
                            ("interface", self.interfaces), ("decision", self.decisions)):
            if item_id in table:
                return kind
        return None
