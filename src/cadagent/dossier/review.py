"""The reviewer pass and its hash-bound sign-off (plan ``docs/design-process-plan.md`` §5.3, task T11).

A section is reviewed by an agent or person that did not build it. This module gives that reviewer everything in
one place and checks what comes back:

* ``write_bundle`` (``cad-agent review-section <id>``) writes a **prompt bundle** for the reviewer: the section's
  YAML, the gate verdicts and lint rows for its parts, the review packet (manifest and images), the checklist, the
  decisions to judge and requirements to trace, the diff since the last sign-off, and a record template.
* ``validate_record`` checks a **reviewer record** (``dossier/reviews/<section>-<date>.json``, schema
  ``cad-agent.review/1``) on its own: every field, every answer with its evidence, and that a sign-off is
  consistent (no blocking finding, no bad or unclear answer, every requirement traced). The dossier lint runs it on
  every record.
* ``check_record`` checks a record against the project as it is now: the hashes are the current build's, the
  reviewer is not the section's builder or author, every checklist question, decision and requirement of the
  section is answered, the packet is current, and no decision is open. ``submit_record``
  (``cad-agent review-section <id> --submit``) runs both, stamps the actor, time and commit, and writes the record.

Who is who: the reviewer's ``actor`` is ``CAD_AGENT_ACTOR`` when the record is submitted; the builder of each part
is ``parts.<name>.actor`` in ``exports/dossier-geometry.json`` (the actor of the build that first produced that
part's current content hash, ``registry.part_actor``). This is only as strong as the variable: a harness that sets
the same value for two agents, or two values for one, defeats it.

What it does not do: a signed-off section has been looked at by someone else against a checklist, with the
geometry they looked at bound by hash. It does not prove physical fit, strength or that a mechanism works.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

RECORD_SCHEMA = "cad-agent.review/1"
BUNDLE_SCHEMA = "cad-agent.review-bundle/1"
VERDICTS = ("sign_off", "changes_requested")
ANSWERS = ("yes", "no", "unclear")
SEVERITIES = ("critical", "major", "minor", "note")
BLOCKING = ("critical", "major")                       # a sign-off carries none of these
DECISION_VERDICTS = ("justified", "weak", "missing_alternative")
TRACED = ("yes", "no", "unclear")
UNKNOWN = ("", "unknown")
MAX_DIFF_BYTES = 2_000_000
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# top-level keys of a record: the required ones, then those submit_record adds or a reviewer may add
REQUIRED = ("schema", "section", "date", "timestamp", "actor", "verdict", "signed_off", "hashes", "checklist",
            "decisions", "requirements", "findings")
OPTIONAL = ("build_actors", "commit", "packet", "bundle", "summary", "toolkit", "physical_fit_verified")


class ReviewError(ValueError):
    """The project cannot give a bundle or take a record (no dossier, no such section, no build)."""


@dataclass
class Problem:
    """Why a record is not valid, or cannot be submitted. ``code`` is stable; ``message`` says what to change."""
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


# --------------------------------------------------------------------------------------------- the record on its own

def validate_record(data: Any) -> List[Problem]:
    """Check a reviewer record on its own (no project needed): every field and its type, each answer with its
    evidence, and that the verdict agrees with what the record says. Empty when the record is valid.

    A sign-off (``verdict: sign_off``, ``signed_off: true``) must answer at least one checklist question, carry no
    ``critical`` or ``major`` finding, have no checklist answer that is ``unclear`` or the question's
    ``bad_answer``, judge no decision ``missing_alternative`` and trace every requirement ``yes``. A
    ``changes_requested`` record must say what to change: at least one finding."""
    out: List[Problem] = []

    def bad(code: str, msg: str) -> None:
        out.append(Problem(code, msg))

    if not isinstance(data, Mapping):
        return [Problem("not-an-object", "a reviewer record is a JSON object")]
    if data.get("schema") != RECORD_SCHEMA:
        bad("schema", f"`schema` must be {RECORD_SCHEMA!r}, got {data.get('schema')!r}")
    for key in REQUIRED:
        if key not in data:
            bad("missing", f"`{key}` is missing")
    unknown = sorted(set(data) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        bad("unknown-key", f"unknown key(s) {', '.join(unknown)} (known: {', '.join(REQUIRED + OPTIONAL)})")
    for key in ("section", "actor"):
        if key in data and not (isinstance(data[key], str) and data[key].strip()):
            bad("type", f"`{key}` must be a non-empty string")
    if "date" in data and not (isinstance(data["date"], str) and _DATE_RE.match(data["date"])):
        bad("type", f"`date` must be YYYY-MM-DD, got {data['date']!r}")
    if "timestamp" in data and _timestamp(data["timestamp"]) is None:
        bad("type", f"`timestamp` must be an ISO 8601 time with a zone (2026-10-28T14:03:12Z), got "
                    f"{data['timestamp']!r}")
    verdict = data.get("verdict")
    if "verdict" in data and verdict not in VERDICTS:
        bad("verdict", f"`verdict` must be one of {', '.join(VERDICTS)}, got {verdict!r}")
    if "signed_off" in data:
        if not isinstance(data["signed_off"], bool):
            bad("type", "`signed_off` must be true or false")
        elif verdict in VERDICTS and data["signed_off"] != (verdict == "sign_off"):
            bad("verdict", f"`signed_off: {str(data['signed_off']).lower()}` contradicts `verdict: {verdict}`")
    hashes = data.get("hashes")
    if "hashes" in data:
        if not isinstance(hashes, Mapping) or not hashes:
            bad("hashes", "`hashes` must map every part reviewed to its content hash")
        else:
            wrong = sorted(str(k) for k, v in hashes.items() if not (isinstance(v, str) and _SHA_RE.match(v)))
            if wrong:
                bad("hashes", f"`hashes` of {', '.join(wrong)} are not sha256 hex digests")
    if data.get("physical_fit_verified") not in (None, False):
        bad("overclaim", "`physical_fit_verified` must be false: a review of renders and gates does not verify fit")
    if "build_actors" in data and not isinstance(data["build_actors"], Mapping):
        bad("type", "`build_actors` must map parts to actors")

    answers = _items(data, "checklist", out)
    decisions = _items(data, "decisions", out)
    requirements = _items(data, "requirements", out)
    findings = _items(data, "findings", out)

    for i, a in answers:
        what = f"checklist[{i}] ({a.get('id', '?')})"
        _need_text(a, "id", what, out)
        if a.get("answer") not in ANSWERS:
            bad("answer", f"{what}: `answer` must be one of {', '.join(ANSWERS)}, got {a.get('answer')!r}")
        _need_text(a, "evidence", what, out, "evidence: what you saw or read that gives this answer")
        image_only = a.get("image_only")
        views, cited = a.get("views", []), a.get("measurements", [])
        if not _str_list(views):
            bad("type", f"{what}: `views` must be a list of view ids")
            views = []
        if not _str_list(cited):
            bad("type", f"{what}: `measurements` must be a list of check ids (gate:<name>, a check or finding id)")
            cited = []
        if not isinstance(image_only, bool):
            bad("image-only", f"{what}: `image_only` must be true (answered from the images alone) or false "
                              "(a measurement backs it, listed in `measurements`)")
        elif image_only and not views:
            bad("image-only", f"{what}: an image-only answer names the views it was read from (`views`)")
        elif image_only and cited:
            bad("image-only", f"{what}: `image_only: true` but it cites measurements; set it false")
        elif not image_only and not cited:
            bad("image-only", f"{what}: `image_only: false` needs the measurement that backs it in `measurements`")
        bad_answer = a.get("bad_answer")
        if bad_answer is not None and bad_answer not in ("yes", "no"):
            bad("type", f"{what}: `bad_answer` is {bad_answer!r}; yes or no")
    _unique(answers, "checklist", out)

    for i, d in decisions:
        what = f"decisions[{i}] ({d.get('id', '?')})"
        _need_text(d, "id", what, out)
        if d.get("verdict") not in DECISION_VERDICTS:
            bad("decision", f"{what}: `verdict` must be one of {', '.join(DECISION_VERDICTS)}, got "
                            f"{d.get('verdict')!r}")
        _need_text(d, "evidence", what, out, "evidence: why the decision is justified, weak or missing an "
                                             "alternative")
    _unique(decisions, "decisions", out)

    for i, r in requirements:
        what = f"requirements[{i}] ({r.get('id', '?')})"
        _need_text(r, "id", what, out)
        if r.get("traced") not in TRACED:
            bad("requirement", f"{what}: `traced` must be one of {', '.join(TRACED)}, got {r.get('traced')!r}")
        _need_text(r, "evidence", what, out, "evidence: the checks and parts that trace it, or what is missing")
    _unique(requirements, "requirements", out)

    for i, f in findings:
        what = f"findings[{i}] ({f.get('id', '?')})"
        _need_text(f, "id", what, out)
        if f.get("severity") not in SEVERITIES:
            bad("finding", f"{what}: `severity` must be one of {', '.join(SEVERITIES)}, got {f.get('severity')!r}")
        _need_text(f, "text", what, out, "text: what is wrong and where")
        if "parts" in f and not _str_list(f["parts"]):
            bad("type", f"{what}: `parts` must be a list of part ids")
    _unique(findings, "findings", out)

    if verdict == "sign_off" and data.get("signed_off") is True:
        if not answers:
            bad("signoff", "a sign-off answers the checklist: `checklist` is empty")
        blocking = [str(f.get("id")) for _, f in findings if f.get("severity") in BLOCKING]
        if blocking:
            bad("signoff", f"a sign-off carries no critical or major finding: {', '.join(blocking)}")
        unclear = [str(a.get("id")) for _, a in answers if a.get("answer") == "unclear"]
        if unclear:
            bad("signoff", f"a sign-off has no unclear answer (ask for another view, or request changes): "
                           f"{', '.join(unclear)}")
        flagged = [str(a.get("id")) for _, a in answers
                   if a.get("bad_answer") in ("yes", "no") and a.get("answer") == a.get("bad_answer")]
        if flagged:
            bad("signoff", f"a sign-off has no answer that is the question's bad answer: {', '.join(flagged)}")
        missing = [str(d.get("id")) for _, d in decisions if d.get("verdict") == "missing_alternative"]
        if missing:
            bad("signoff", f"a sign-off has no decision missing an alternative: {', '.join(missing)}")
        untraced = [str(r.get("id")) for _, r in requirements if r.get("traced") != "yes"]
        if untraced:
            bad("signoff", f"a sign-off traces every requirement: {', '.join(untraced)} not traced")
    if verdict == "changes_requested" and "findings" in data and not findings:
        bad("changes", "a record that requests changes says what to change: add a finding")
    return out


def _items(data: Mapping[str, Any], key: str, out: List[Problem]) -> List[Tuple[int, Mapping[str, Any]]]:
    value = data.get(key, [])
    if not isinstance(value, list):
        out.append(Problem("type", f"`{key}` must be a list"))
        return []
    items = []
    for i, item in enumerate(value):
        if isinstance(item, Mapping):
            items.append((i, item))
        else:
            out.append(Problem("type", f"{key}[{i}] must be an object"))
    return items


def _need_text(m: Mapping[str, Any], key: str, what: str, out: List[Problem], hint: str = "") -> None:
    value = m.get(key)
    if not (isinstance(value, str) and value.strip()):
        out.append(Problem("evidence" if key == "evidence" else "missing",
                           f"{what}: `{key}` is missing or empty" + (f" ({hint})" if hint else "")))


def _str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v for v in value)


def _unique(items: Sequence[Tuple[int, Mapping[str, Any]]], key: str, out: List[Problem]) -> None:
    seen: Dict[str, int] = {}
    for _, item in items:
        k = str(item.get("id", ""))
        seen[k] = seen.get(k, 0) + 1
    twice = sorted(k for k, n in seen.items() if n > 1 and k)
    if twice:
        out.append(Problem("duplicate", f"{key}: id(s) {', '.join(twice)} given more than once"))


def _timestamp(value: Any) -> Optional[_dt.datetime]:
    if not isinstance(value, str):
        return None
    try:
        t = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


# --------------------------------------------------------------------------------------------- who built what

def part_actors(geometry: Optional[Mapping[str, Any]], parts: Iterable[str]) -> Dict[str, str]:
    """``{part: actor}`` for the given parts that the geometry record has: ``parts.<name>.actor`` (the build that
    first produced the part's current hash), else the record's top-level ``actor`` (a record from before per-part
    actors). ``unknown`` when neither is set."""
    geo = geometry or {}
    top = str(geo.get("actor") or "unknown")
    table = geo.get("parts") if isinstance(geo.get("parts"), Mapping) else {}
    out: Dict[str, str] = {}
    for p in parts:
        info = table.get(p)
        if isinstance(info, Mapping):
            out[p] = str(info.get("actor") or top).strip() or "unknown"
    return out


def section_authors(dossier: Any, section: str) -> Dict[str, str]:
    """``{where: author}`` for every ``author`` the dossier gives in a section: the section, its cards and its
    decisions (nested or scoped to it in ``decisions.yaml``)."""
    out: Dict[str, str] = {}
    sec = dossier.sections.get(section) if dossier is not None else None
    if sec is None:
        return out
    if sec.author.strip():
        out[f"section {section}"] = sec.author.strip()
    for card in sec.parts:
        if card.author.strip():
            out[f"card {card.id}"] = card.author.strip()
    for did in section_decisions(dossier, section):
        dec = dossier.decisions[did]
        if dec.author.strip():
            out[f"decision {did}"] = dec.author.strip()
    return out


def actor_refusal(reviewer: str, section: str, dossier: Any, geometry: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Why ``reviewer`` may not sign ``section`` off while separate review is required, or None. Refused: an
    unknown reviewer; a part of the section whose builder is unknown; a reviewer who built a part of the section
    (``parts.<name>.actor``) or is named as an ``author`` of the section, one of its cards or decisions."""
    who = (reviewer or "").strip()
    if who in UNKNOWN:
        return "the reviewer's actor is unknown (set CAD_AGENT_ACTOR for the reviewer)"
    sec = dossier.sections.get(section) if dossier is not None else None
    parts = [c.id for c in sec.parts] if sec is not None else []
    actors = part_actors(geometry, parts)
    unknown = sorted(p for p, a in actors.items() if a in UNKNOWN)
    if unknown:
        return (f"the build actor of {', '.join(unknown)} is unknown (set CAD_AGENT_ACTOR for the build, and "
                "rebuild)")
    built = sorted(p for p, a in actors.items() if a == who)
    if built:
        return f"the reviewer {who!r} built {', '.join(built)}"
    wrote = sorted(k for k, a in section_authors(dossier, section).items() if a == who)
    if wrote:
        return f"the reviewer {who!r} is the author of {', '.join(wrote)}"
    return None


def section_decisions(dossier: Any, section: str) -> List[str]:
    """The ids of the decisions that belong to ``section``: its own, its cards', and those in ``decisions.yaml``
    scoped to it or to one of its parts."""
    out = []
    for did, dec in dossier.decisions.items():
        sid = dec.section
        if not sid and dec.part:
            card = dossier.parts.get(dec.part)
            sid = card.section if card is not None else ""
        if sid == section:
            out.append(did)
    return out


def open_decisions(dossier: Any, section: str) -> List[str]:
    return [d for d in section_decisions(dossier, section) if dossier.decisions[d].status == "open"]


def current_hashes(dossier: Any, section: str, geometry: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """``{part: content hash}`` of every part card in ``section`` as the geometry record holds it now (``""`` for a
    card the build did not register: such a section cannot be reviewed)."""
    sec = dossier.sections[section]
    table = (geometry or {}).get("parts") or {}
    return {c.id: str((table.get(c.id) or {}).get("sha256", "")) if isinstance(table.get(c.id), Mapping) else ""
            for c in sec.parts}


# --------------------------------------------------------------------------------------------- the record in context

def check_record(data: Mapping[str, Any], *, dossier: Any, geometry: Optional[Mapping[str, Any]],
                 packet: Optional[Mapping[str, Any]] = None, packet_stale: Optional[str] = None,
                 section_status: Optional[str] = None,
                 require_separate_reviewer: Optional[bool] = None) -> List[Problem]:
    """Check a record against the project as it is now (on top of ``validate_record``). ``packet`` is the section's
    review packet manifest (``None``: not rendered) and ``packet_stale`` why it is not current evidence (None when
    it is); ``section_status`` the section's computed status.

    Refused for any record: a section the dossier does not have; ``hashes`` that are not exactly the current hash
    of every part of the section (**stale hashes never sign off**, nor request changes on geometry that is gone); a
    reviewer who built or wrote the section, or is unknown, while separate review is required (the dossier's
    ``gates: require_separate_reviewer``, default true); a checklist that does not answer exactly the packet's
    questions, with their text and bad answers; decisions and requirements of the section not judged. Refused for a
    sign-off only: no packet or a stale one, an **open decision** in the section, a section below ``gated``."""
    out = list(validate_record(data))
    if not isinstance(data, Mapping):
        return out

    def bad(code: str, msg: str) -> None:
        out.append(Problem(code, msg))

    sid = str(data.get("section", ""))
    if dossier is None or sid not in dossier.sections:
        bad("section", f"section {sid!r} is not in the dossier")
        return out
    sign = data.get("verdict") == "sign_off"
    if geometry is None:
        bad("geometry", "no geometry record: nothing is built, so nothing can be reviewed")
        return out
    now = current_hashes(dossier, sid, geometry)
    unbuilt = sorted(p for p, h in now.items() if not h)
    if unbuilt:
        bad("unbuilt", f"part(s) {', '.join(unbuilt)} have no shape in the geometry record: build them first")
    given = data.get("hashes") if isinstance(data.get("hashes"), Mapping) else {}
    stale = sorted(p for p, h in now.items() if h and given.get(p) != h)
    if stale:
        bad("stale-hashes", f"the hashes of {', '.join(stale)} are not the current build's: the geometry changed since "
                            "the bundle (or the part was not reviewed); write a new bundle and review that")
    extra = sorted(set(map(str, given)) - set(now))
    if extra:
        bad("stale-hashes", f"`hashes` names {', '.join(extra)}, which are not parts of section {sid}")
    separate = dossier.gates.require_separate_reviewer if require_separate_reviewer is None \
        else require_separate_reviewer
    actor = str(data.get("actor", "") or "")
    if separate:
        why = actor_refusal(actor, sid, dossier, geometry)
        if why:
            bad("same-actor", f"{why}; a separate reviewer is required (gates: require_separate_reviewer)")

    questions = _packet_questions(packet)
    answers = {str(a.get("id")): a for a in data.get("checklist") or [] if isinstance(a, Mapping)}
    if packet is None:
        if sign:
            bad("packet", f"no review packet for {sid}: render it (cad-agent review-packet {sid}) and review the "
                          "images before signing off")
    else:
        missing = [q for q in questions if q not in answers]
        if missing:
            bad("unanswered", f"checklist question(s) not answered: {', '.join(missing)}")
        foreign = sorted(set(answers) - set(questions))
        if foreign:
            bad("unknown-question", f"answers to question(s) the packet does not ask: {', '.join(foreign)}")
        views = {str(v.get("id")) for v in packet.get("views") or [] if isinstance(v, Mapping)}
        gates = set((packet.get("measurements") or {}).get("gates") or {}) | {"dossier-lint"}
        for qid, a in answers.items():
            q = questions.get(qid)
            if q is None:
                continue
            for key in ("question", "bad_answer"):
                if key in a and a[key] != q.get(key):
                    bad("question-changed", f"checklist {qid}: `{key}` is not the packet's ({q.get(key)!r})")
            unseen = [v for v in a.get("views") or [] if isinstance(v, str) and v not in views]
            if unseen:
                bad("unknown-view", f"checklist {qid}: view(s) {', '.join(unseen)} are not in the packet")
            ungated = [m for m in a.get("measurements") or [] if isinstance(m, str) and m.startswith("gate:")
                       and m[5:] not in gates]
            if ungated:
                bad("unknown-measurement", f"checklist {qid}: {', '.join(ungated)} has no verdict in the packet")
            if sign and q.get("bad_answer") in ("yes", "no") and a.get("answer") == q.get("bad_answer"):
                bad("signoff", f"checklist {qid}: the answer {a.get('answer')!r} is a finding; it cannot be "
                               "signed off")
        if sign and packet_stale:
            bad("packet-stale", f"the review packet is not current evidence: {packet_stale}")
    decs = section_decisions(dossier, sid)
    judged = {str(d.get("id")) for d in data.get("decisions") or [] if isinstance(d, Mapping)}
    if set(decs) - judged:
        bad("unjudged", f"decision(s) not judged: {', '.join(d for d in decs if d not in judged)}")
    if judged - set(decs):
        bad("unknown-decision", f"decision(s) {', '.join(sorted(judged - set(decs)))} are not in section {sid}")
    reqs = list(dossier.sections[sid].requirements)
    traced = {str(r.get("id")) for r in data.get("requirements") or [] if isinstance(r, Mapping)}
    if set(reqs) - traced:
        bad("untraced", f"requirement(s) not traced: {', '.join(r for r in reqs if r not in traced)}")
    if traced - set(reqs):
        bad("unknown-requirement", f"requirement(s) {', '.join(sorted(traced - set(reqs)))} are not served by "
                                   f"section {sid}")
    if sign:
        opened = open_decisions(dossier, sid)
        if opened:
            bad("open-decision", f"section {sid} has open decision(s) {', '.join(opened)}: decide them before a "
                                 "sign-off")
        if section_status is not None and section_status in ("draft", "built"):
            bad("below-gated", f"section {sid} is {section_status}: its gates and checks do not all pass, so there "
                               "is nothing to sign off yet")
    return out


def _packet_questions(packet: Optional[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    if not isinstance(packet, Mapping):
        return {}
    qs = (packet.get("checklist") or {}).get("questions") or []
    return {str(q.get("id")): q for q in qs if isinstance(q, Mapping) and q.get("id")}


# --------------------------------------------------------------------------------------------- the project side

@dataclass
class _Project:
    project: Any
    root: Path
    dossier: Any
    geometry: Optional[Dict[str, Any]]
    geometry_file: str
    lint: Any                      # LintResult
    evidence: Any                  # lint.Evidence


def _load(project: Any, section: str) -> _Project:
    from .lint import lint_project, project_evidence
    from .load import DossierError, load_project_dossier

    if not getattr(project, "dossier", None):
        raise ReviewError("no dossier: add `dossier: dossier/project.yaml` to the cad: section (docs/dossier.md)")
    try:
        dossier = load_project_dossier(project, strict=False)
    except DossierError as exc:
        raise ReviewError(f"the dossier cannot be read: {exc}") from None
    if section not in dossier.sections:
        raise ReviewError(f"section {section!r} is not in the dossier (sections: {', '.join(dossier.sections)})")
    ev = project_evidence(project)
    res = lint_project(project)
    return _Project(project, Path(project.root), dossier, ev.geometry, ev.geometry_file, res, ev)


def packet_dir(project: Any, section: str) -> Path:
    from ..packet import safe_name
    return Path(project.exports_dir) / "review" / safe_name(section)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _packet(p: _Project, section: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Path]:
    """The rendered packet's manifest, why it is not current (None when it is), and its directory."""
    from ..packet import SCHEMA, project_packet_stale

    d = packet_dir(p.project, section)
    m = _read_json(d / "manifest.json")
    if m is None or m.get("schema") != SCHEMA:
        return None, f"no review packet in {_rel(d, p.root)} (cad-agent review-packet {section})", d
    if not m.get("rendered"):
        return m, "the packet was planned, not rendered (cad-agent review-packet " + section + ")", d
    return m, project_packet_stale(m, p.root), d


def _rel(path: Union[str, Path], root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _git(root: Path, *args: str) -> Tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return r.returncode, r.stdout if r.returncode == 0 else r.stderr


def head_commit(root: Path) -> Optional[str]:
    code, out = _git(root, "rev-parse", "HEAD")
    return out.strip() if code == 0 and out.strip() else None


def section_records(project: Any, section: str) -> List[Tuple[str, Dict[str, Any]]]:
    """``(file, record)`` of every readable record for ``section`` in ``dossier/reviews/``, oldest first (by
    ``timestamp``, else ``date``, then file name). Invalid records are included; the lint reports them."""
    d = Path(project.dossier).parent / "reviews"
    out = []
    for path in sorted(d.glob("*.json")) if d.is_dir() else []:
        data = _read_json(path)
        if data is not None and data.get("section") == section:
            out.append((_rel(path, Path(project.root)), data))
    out.sort(key=lambda fr: record_order(fr[1], fr[0]))
    return out


_SEQ_RE = re.compile(r"\d{4}-\d{2}-\d{2}-(\d+)\.json$")


def record_order(data: Mapping[str, Any], file: str) -> Tuple[str, int, str]:
    """The order records are read in: by time, then by the ``-2``, ``-3`` ... suffix ``submit_record`` gives a
    second record of the same day (``S1-2026-10-28.json`` before ``S1-2026-10-28-2.json``), then by file."""
    m = _SEQ_RE.search(file)
    return record_time(data), int(m.group(1)) if m else 1, file


def record_time(data: Mapping[str, Any]) -> str:
    """A record's sort key: its timestamp in UTC (``YYYY-MM-DDTHH:MM:SS``), else its date."""
    t = _timestamp(data.get("timestamp"))
    if t is not None:
        return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return str(data.get("date", ""))


def last_signoff(project: Any, section: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    signed = [(f, r) for f, r in section_records(project, section) if r.get("signed_off") is True]
    return signed[-1] if signed else None


def _diff_paths(p: _Project) -> List[str]:
    """What a change to the section can be in: the dossier directory (its reviews left out), the build scripts
    that declared the geometry, the parameters file and ``cad-agent.yaml``."""
    root = p.root
    paths = {_rel(Path(p.project.dossier).parent, root)}
    geo = p.geometry or {}
    for table in ("parts", "cavities", "joints", "fasteners"):
        for info in (geo.get(table) or {}).values():
            if isinstance(info, Mapping) and isinstance(info.get("declared_at"), str):
                paths.add(info["declared_at"].rsplit(":", 1)[0])
    for step in ((geo.get("assembly") or {}).get("steps") or []):
        if isinstance(step, Mapping) and isinstance(step.get("declared_at"), str):
            paths.add(step["declared_at"].rsplit(":", 1)[0])
    params = (geo.get("parameters") or {}).get("file")
    if isinstance(params, str) and params:
        paths.add(params)
    for name in ("cad-agent.yaml", "vptest.yaml"):
        if (root / name).is_file():
            paths.add(name)
    return sorted(x for x in paths if x and (root / x).exists())


def section_diff(p: _Project, section: str, since: Optional[str] = None) -> Dict[str, Any]:
    """The diff of the section's sources since the last sign-off (or ``since``, a git revision): base commit,
    paths, the patch text (working tree against the base, so uncommitted changes are in it) and the untracked
    files under those paths."""
    info: Dict[str, Any] = {"base": None, "since": since, "record": None, "paths": _diff_paths(p), "patch": "",
                            "untracked": [], "note": ""}
    if head_commit(p.root) is None:
        info["note"] = "not a git checkout: no diff"
        return info
    base = since
    if base is None:
        last = last_signoff(p.project, section)
        if last is None:
            info["note"] = "no earlier sign-off of this section: review all of it"
            return info
        info["record"] = last[0]
        base = str(last[1].get("commit") or "")
        if not base or _git(p.root, "cat-file", "-e", f"{base}^{{commit}}")[0] != 0:
            code, out = _git(p.root, "log", "--diff-filter=A", "--format=%H", "-1", "--", last[0])
            base = out.strip() if code == 0 else ""
        if not base:
            info["note"] = f"the last sign-off ({last[0]}) names no commit this checkout has: review all of it"
            return info
    code, resolved = _git(p.root, "rev-parse", "--verify", f"{base}^{{commit}}")
    if code != 0:
        raise ReviewError(f"--since {base!r} is not a commit here: {resolved.strip()}")
    info["base"] = resolved.strip()
    reviews = _rel(Path(p.project.dossier).parent / "reviews", p.root)
    spec = list(info["paths"]) + [f":(exclude){reviews}"]
    code, patch = _git(p.root, "diff", info["base"], "--", *spec)
    if code != 0:
        info["note"] = f"git diff failed: {patch.strip()}"
        return info
    if len(patch.encode()) > MAX_DIFF_BYTES:
        patch = patch.encode()[:MAX_DIFF_BYTES].decode(errors="ignore") + "\n[... truncated at 2 MB ...]\n"
        info["note"] = "the diff is longer than 2 MB and was truncated"
    info["patch"] = patch
    code, out = _git(p.root, "ls-files", "--others", "--exclude-standard", "--", *info["paths"])
    info["untracked"] = [x for x in out.splitlines() if x and not x.startswith(reviews + "/")] if code == 0 else []
    return info


def _section_files(p: _Project, section: str) -> List[str]:
    """The YAML files the section is written in: its own file, split part cards, and the project file (for the
    requirements and project decisions)."""
    sec = p.dossier.sections[section]
    files = []
    for w in [sec.where] + [c.where for c in sec.parts]:
        if w is not None and w.file and w.file not in files:
            files.append(w.file)
    proj = _rel(p.project.dossier, p.root)
    if proj not in files:
        files.append(proj)
    return [f for f in files if (p.root / f).is_file()]


def record_template(p: _Project, section: str, packet: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The record a reviewer fills in: the hashes and questions prefilled, every answer ``null``."""
    d = p.dossier
    sec = d.sections[section]
    plan_questions = _packet_questions(packet)
    checklist = [{"id": qid, "question": q.get("question"), "views": list(q.get("views") or []),
                  "bad_answer": q.get("bad_answer"), **({"gate": q["gate"]} if q.get("gate") else {}),
                  "answer": None, "evidence": "", "image_only": None, "measurements": []}
                 for qid, q in plan_questions.items()]
    for a in checklist:
        if a.get("bad_answer") is None:
            a.pop("bad_answer")
    decisions = []
    for did in section_decisions(d, section):
        dec = d.decisions[did]
        decisions.append({"id": did, "decision": dec.decision, "why": dec.why, "status": dec.status,
                          "alternatives": [a.to_dict() if hasattr(a, "to_dict") else a for a in dec.alternatives],
                          "verdict": None, "evidence": ""})
    reqs = []
    for rid in sec.requirements:
        r = d.requirements.get(rid)
        row = (p.lint.requirements.get(rid) if p.lint is not None else None) or {}
        reqs.append({"id": rid, "text": r.text if r else "", "verify_by": r.verify_by if r else "",
                     "status": row.get("status", ""), "checks": list(r.checks) if r else [],
                     "traced": None, "evidence": ""})
    return {"schema": RECORD_SCHEMA, "section": section, "date": "", "timestamp": "", "actor": "",
            "verdict": None, "signed_off": None,
            "hashes": {k: v for k, v in current_hashes(d, section, p.geometry).items()},
            "checklist": checklist, "decisions": decisions, "requirements": reqs, "findings": [],
            "summary": "", "physical_fit_verified": False}


def write_bundle(project: Any, section: str, bundle_dir: Union[str, Path, None] = None, *,
                 since: Optional[str] = None) -> Dict[str, Any]:
    """Write the reviewer's prompt bundle for ``section`` into ``bundle_dir`` (default
    ``<exports>/review-bundle/<section>/``) and return its manifest (``bundle.json``,
    schema ``cad-agent.review-bundle/1``). Needs no CAD kernel: the packet must have been rendered before
    (``cad-agent review-packet``). ``blockers`` lists what stops a sign-off now (the bundle is written anyway, so
    a reviewer can still request changes)."""
    from ..packet import plan_project_packet, safe_name

    p = _load(project, section)
    if p.geometry is None:
        raise ReviewError(f"no geometry record ({p.geometry_file}): build first (cad-agent gates --build)")
    out = Path(bundle_dir) if bundle_dir is not None else \
        Path(project.exports_dir) / "review-bundle" / safe_name(section)
    if out.exists():
        if not out.is_dir():
            raise ReviewError(f"{out} is a file")
        if any(out.iterdir()) and not (out / "bundle.json").is_file():
            raise ReviewError(f"{out} is not empty and holds no bundle.json: choose an empty or new --bundle-dir")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    sec = p.dossier.sections[section]
    lint_row = p.lint.sections.get(section, {}) if p.lint is not None else {}
    parts = [c.id for c in sec.parts]
    packet, stale, pdir = _packet(p, section)
    try:
        plan, _ = plan_project_packet(section, root=p.root)
    except Exception as exc:                     # noqa: BLE001 (the plan is context; the packet is the evidence)
        plan = {"error": str(exc)}
    files: Dict[str, str] = {}

    def put(name: str, data: Union[str, bytes, Mapping[str, Any]]) -> None:
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        elif isinstance(data, str):
            path.write_text(data)
        else:
            path.write_text(json.dumps(data, indent=1) + "\n")
        files[name] = _sha_file(path)

    for f in _section_files(p, section):
        put(f"section/{f}", (p.root / f).read_text())
    if packet is not None:
        put("packet/manifest.json", packet)
        for v in packet.get("views") or []:
            if isinstance(v, Mapping) and v.get("file") and (pdir / str(v["file"])).is_file():
                put(f"packet/{v['file']}", (pdir / str(v["file"])).read_bytes())
    measurements = (packet or plan).get("measurements") if isinstance(packet or plan, Mapping) else None
    gate_rows = {}
    for g, row in ((measurements or {}).get("gates") or {}).items():
        gate_rows[g] = row
    lint_findings = [f.to_dict() for f in (p.lint.findings if p.lint is not None else [])
                     if f.item == section or set(f.parts) & set(parts)]
    put("gates.json", {"section": section, "parts": parts, "gates": gate_rows,
                       "missing_gates": (measurements or {}).get("missing_gates", []),
                       "findings": (packet or plan).get("findings", []) if isinstance(packet or plan, Mapping) else [],
                       "lint_findings": lint_findings,
                       "note": "the gate checks that name a part of this section (from the review packet); "
                               "a stale verdict is not a pass"})
    actors = part_actors(p.geometry, parts)
    put("status.json", {"section": lint_row, "parts": {pid: {**((p.lint.parts.get(pid) if p.lint else None) or {}),
                                                             "built_by": actors.get(pid, "")} for pid in parts}})
    template = record_template(p, section, packet if packet is not None else plan)
    put("checklist.json", {"checklist": (packet or plan or {}).get("checklist", {}),
                           "decisions": template["decisions"], "requirements": template["requirements"]})
    diff = section_diff(p, section, since)
    put("diff.patch", diff["patch"] or f"# {diff['note'] or 'no change since the base'}\n")
    put("record-template.json", template)

    opened = open_decisions(p.dossier, section)
    blockers = []
    if stale:
        blockers.append(f"packet: {stale}")
    status = lint_row.get("status", "")
    if status in ("draft", "built"):
        blockers.append(f"the section is {status}: " + "; ".join(lint_row.get("blocked_by") or [])[:400])
    if opened:
        blockers.append(f"open decision(s) {', '.join(opened)}: decide them before a sign-off")
    unknown = sorted(pid for pid, a in actors.items() if a in UNKNOWN)
    if unknown and p.dossier.gates.require_separate_reviewer:
        blockers.append(f"the build actor of {', '.join(unknown)} is unknown: rebuild with CAD_AGENT_ACTOR set")
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "section": {"id": section, "title": sec.title, "purpose": sec.purpose, "requirements": list(sec.requirements),
                    "status": status, "blocked_by": lint_row.get("blocked_by", [])},
        "dir": _rel(out, p.root),
        "created": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": head_commit(p.root),
        "geometry": {"file": p.geometry_file, "hashes": template["hashes"], "built_by": actors},
        "require_separate_reviewer": p.dossier.gates.require_separate_reviewer,
        "authors": section_authors(p.dossier, section),
        "packet": {"dir": _rel(pdir, p.root), "rendered": bool(packet and packet.get("rendered")),
                   "stale": stale, "section_hash": (packet or {}).get("section_hash"),
                   "questions": len(_packet_questions(packet))},
        "open_decisions": opened,
        "diff": {k: v for k, v in diff.items() if k != "patch"},
        "previous": [{"file": f, "date": r.get("date"), "actor": r.get("actor"), "verdict": r.get("verdict"),
                      "signed_off": r.get("signed_off")} for f, r in section_records(project, section)],
        "blockers": blockers,
        "ready": not blockers,
        "files": files,
        "submit": f"CAD_AGENT_ACTOR=<you> cad-agent review-section {section} --submit <your record.json>",
        "physical_fit_verified": False,
    }
    (out / "PROMPT.md").write_text(_prompt(manifest, template))
    manifest["files"]["PROMPT.md"] = _sha_file(out / "PROMPT.md")
    (out / "bundle.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def _sha_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _prompt(m: Mapping[str, Any], template: Mapping[str, Any]) -> str:
    sec = m["section"]
    lines = [
        f"# Review of section {sec['id']}: {sec['title']}",
        "",
        "You are the reviewer of this section. You did not build it, and you must not change its geometry or its",
        "YAML: your only output is a reviewer record. Rebuilding unchanged geometry is harmless; changing it voids",
        "your review.",
        "",
        f"Purpose: {sec.get('purpose') or '(none given)'}",
        f"Requirements: {', '.join(sec.get('requirements') or []) or '(none)'}",
        f"Computed status: {sec.get('status') or '?'}",
        f"Built by: {', '.join(f'{k}={v}' for k, v in m['geometry']['built_by'].items()) or '?'}",
        "",
        "## What is in this bundle",
        "",
        "- `section/`: the section's YAML (and the project file for the requirements and project decisions).",
        "- `gates.json`: every gate's verdict for this section's parts (status, stale reason, the checks that name",
        "  its parts) and the dossier lint findings for it. Read this first.",
        "- `status.json`: the computed status of the section and each part, and who built each part.",
        "- `packet/`: the review packet: `manifest.json` (measurements, findings with witness points, views, the",
        "  checklist) and the images it names.",
        "- `checklist.json`: the questions to answer, the decisions to judge, the requirements to trace.",
        "- `diff.patch`: what changed in the section's sources since the last sign-off"
        + (f" ({m['diff']['note']})" if m["diff"].get("note") else "") + ".",
        "- `record-template.json`: your record, with the hashes and questions filled in. Copy it and fill it in.",
        "",
        "## How to review",
        "",
        "1. Read `gates.json` and the packet's `measurements` and `findings` before any image. A stale verdict is",
        "   not a pass.",
        "2. Answer every checklist question `yes`, `no` or `unclear` from the views it names. Give `evidence` (what",
        "   you saw or read), the `views` you used, and set `image_only`: `true` when the answer rests on the images",
        "   alone, `false` when a measurement backs it (list it in `measurements`: `gate:<name>`, a check id or a",
        "   finding id). Never answer a count, a gap, a wall thickness or an engagement from an image: the gates",
        "   measured those (`checklist.measured_only`). `unclear` is never a pass; ask for another view instead.",
        "3. Judge each decision `justified`, `weak` or `missing_alternative`, with evidence.",
        "4. Trace each requirement: `traced` is `yes` when a check or part of this section verifiably serves it,",
        "   with evidence; `no` or `unclear` otherwise.",
        "5. Write `findings`: `id` (F1, F2, ...), `severity` (`critical`, `major`, `minor`, `note`), `text`, and",
        "   where useful `parts`, `view` (a packet view id, so the site shows it beside that image) and `checklist`.",
        "6. Set `verdict`: `sign_off` only with no critical or major finding, no `unclear` answer, no answer that",
        "   is the question's `bad_answer`, no decision missing an alternative and every requirement traced;",
        "   otherwise `changes_requested` with at least one finding. Leave `actor`, `date` and `timestamp` empty.",
        "",
        "Submit it (this checks the hashes against the current build and stamps your actor, the time and the",
        "commit):",
        "",
        "```bash",
        m["submit"],
        "```",
        "",
        "A sign-off is refused when the geometry changed since this bundle (stale hashes), when you built or wrote",
        "any part of the section (separate review" + (" is required" if m["require_separate_reviewer"] else
                                                      " is not required in this dossier, but say so") + "), when a",
        "decision is open, when the packet is not current, or when the section's gates do not pass.",
        "",
    ]
    if m["blockers"]:
        lines += ["## Blockers now", "", "A sign-off would be refused today because:", ""]
        lines += [f"- {b}" for b in m["blockers"]] + ["", "You can still review and request changes.", ""]
    lines += ["## Limits", "",
              "Renders and gates show the model, not the part: a review does not prove fit, strength or that a",
              "mechanism works. Say what you could not see.", ""]
    return "\n".join(lines)


def submit_record(project: Any, section: str, record: Union[str, Path, Mapping[str, Any]], *,
                  reviewer: Optional[str] = None, write: bool = True,
                  now: Optional[_dt.datetime] = None) -> Tuple[Optional[Path], Dict[str, Any], List[Problem]]:
    """Check a filled-in record against the project and, when it has no problem and ``write`` is set, write it to
    ``dossier/reviews/<section>-<date>.json`` (``-2``, ``-3``, ... when that exists). ``reviewer`` is the
    submitting actor (default ``CAD_AGENT_ACTOR``); it becomes the record's ``actor``. The record gets its
    ``date``, ``timestamp``, ``signed_off`` (from ``verdict``), ``commit``, ``build_actors``, ``packet`` binding and
    ``toolkit`` here. Returns the path written (None when not written), the record and its problems."""
    import os
    from ..gates.verdict import _toolkit_version
    from ..packet import safe_name

    if isinstance(record, (str, Path)):
        try:
            data = json.loads(Path(record).read_text())
        except (OSError, ValueError) as exc:
            raise ReviewError(f"cannot read the record {record}: {exc}") from None
    else:
        data = dict(record)
    if not isinstance(data, dict):
        return None, {}, [Problem("not-an-object", "a reviewer record is a JSON object")]
    p = _load(project, section)
    if data.get("section") not in (None, "", section):
        return None, data, [Problem("section", f"the record is for section {data.get('section')!r}, not {section!r}")]
    who = (reviewer if reviewer is not None else os.environ.get("CAD_AGENT_ACTOR") or "").strip()
    given = str(data.get("actor") or "").strip()
    mismatch = ([Problem("actor", f"the record says actor {given!r} but the submitting actor (CAD_AGENT_ACTOR) is "
                                  f"{who or 'unset'!r}: a record is submitted by its own reviewer")]
                if given and given != who else [])
    t = (now or _now()).astimezone(_dt.timezone.utc).replace(microsecond=0)
    packet, stale, pdir = _packet(p, section)
    parts = [c.id for c in p.dossier.sections[section].parts]
    rec = dict(data)
    rec.update({
        "schema": RECORD_SCHEMA, "section": section, "actor": who or "unknown",
        "date": t.strftime("%Y-%m-%d"), "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "signed_off": data.get("verdict") == "sign_off" if data.get("signed_off") is None else data["signed_off"],
        "build_actors": part_actors(p.geometry, parts),
        "commit": head_commit(p.root),
        "packet": {"manifest": _rel(pdir / "manifest.json", p.root), "section_hash": (packet or {}).get("section_hash"),
                   "sha256": _sha_file(pdir / "manifest.json") if packet is not None else None, "stale": stale},
        "toolkit": _toolkit_version(),
        "physical_fit_verified": False,
    })
    for key in ("summary",):
        if key in rec and rec[key] in (None, ""):
            rec.pop(key)
    status = (p.lint.sections.get(section) or {}).get("status") if p.lint is not None else None
    problems = mismatch + check_record(rec, dossier=p.dossier, geometry=p.geometry, packet=packet,
                                       packet_stale=stale, section_status=status)
    if problems or not write:
        return None, rec, problems
    d = Path(project.dossier).parent / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    stem = f"{safe_name(section)}-{rec['date']}"
    path, n = d / f"{stem}.json", 1
    while path.exists():
        n += 1
        path = d / f"{stem}-{n}.json"
    path.write_text(json.dumps(rec, indent=1) + "\n")
    return path, rec, []


__all__ = ["ANSWERS", "BLOCKING", "BUNDLE_SCHEMA", "DECISION_VERDICTS", "Problem", "RECORD_SCHEMA", "ReviewError",
           "SEVERITIES", "TRACED", "VERDICTS", "actor_refusal", "check_record", "current_hashes", "head_commit",
           "last_signoff", "open_decisions", "part_actors", "record_order", "record_template", "record_time",
           "section_authors", "section_decisions", "section_diff", "section_records", "submit_record",
           "validate_record", "write_bundle"]
