"""The dossier lint and status machine (plan T2): every rule has a failing and a passing case, statuses climb
draft -> built -> gated -> reviewed -> signed_off on evidence, and a geometry change voids a sign-off.

No CAD kernel: the geometry record is the JSON mapping the registry writes, gate verdicts are plain dicts.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pytest
import yaml

from cadagent.dossier import load_dossier
from cadagent.dossier.lint import (RULES, CheckState, Evidence, Review, lint, lint_project, load_reviews,
                                   write_outputs)


def _verdict(gate: str, ok: bool = True, parts=(), geometry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """A verdict bound to ``geometry`` (default ``base_geometry()``), as ``cad-agent gates`` writes it."""
    from cadagent.gates.verdict import bind_inputs
    findings = [] if ok else [{"id": f"{gate}:x", "status": "fail", "message": "bad", "parts": list(parts)}]
    return bind_inputs({"schema": "cadagent.gate/1", "gate": gate, "pass": ok, "status": "pass" if ok else "fail",
                        "findings": findings}, geometry if geometry is not None else base_geometry())


def base_files() -> Dict[str, Any]:
    """A small, complete dossier: one section, four parts, two requirements, decisions with alternatives."""
    project = {
        "title": "Demo feeder",
        "requirements": [
            {"id": "R1", "text": "Holds two balls", "source": {"kind": "user", "quote": "hold two"},
             "verify_by": "analysis", "checks": ["gate:containment"]},
            {"id": "R2", "text": "The lid stays on", "verify_by": "analysis"},
        ],
        "sections": ["sections/*.yaml"],
        "assembly": {"steps": [{"order": 1, "fit": "hopper", "onto": "base", "direction": "-Z",
                                "access_check": "gate:assembly"}]},
        "gates": {"grounded": ["base"]},
    }
    store = {
        "id": "S1", "title": "Store", "purpose": "Hold the balls", "requirements": ["R1", "R2"],
        "interfaces": [
            {"id": "I1", "between": ["base", "hopper"], "kind": "fastened", "datum": "base top", "owner": "S1"},
            {"id": "I2", "between": ["hopper", "lid"], "kind": "fastened", "datum": "hopper rim", "owner": "S1"},
        ],
        "parts": [
            {"id": "base", "function": "Carries the hopper", "interfaces": ["I1"],
             "decisions": [{"id": "D1", "decision": "Flat plate", "why": "simplest",
                            "alternatives": [{"option": "Ribbed plate", "rejected": "not needed"}]}]},
            {"id": "hopper", "function": "Holds the balls", "interfaces": ["I1", "I2"],
             "material": {"name": "PETG", "process": "FDM", "wall_mm": 2.4},
             "fasteners": [{"to": "lid", "screws": "m3", "qty": 2, "via": "I2"}],
             "contains": [{"what": "ball", "count": 2, "cavity": "hopper_cavity", "free": True}],
             "checks": ["gate:wall"],
             "decisions": [{"id": "D2", "decision": "Square box", "why": "prints flat",
                            "alternatives": [{"option": "Cone", "rejected": "needs supports"}]}]},
            {"id": "lid", "function": "Closes the hopper", "interfaces": ["I2"]},
            {"id": "ball", "function": "Loose item"},
        ],
    }
    return {"project.yaml": project, "sections/store.yaml": store}


def base_geometry() -> Dict[str, Any]:
    def part(sec, sha, **kw):
        return {"section": sec, "sha256": sha, "count": 1, "declared_at": "cad/build.py:10", **kw}
    return {
        "schema": "cad-agent.dossier-geometry/1", "actor": "builder",
        "parts": {"base": part("S1", "a" * 64, grounded=True), "hopper": part("S1", "b" * 64),
                  "lid": part("S1", "c" * 64), "ball": part("S1", "d" * 64, free=True, count=2)},
        "cavities": {"hopper_cavity": {"part": "hopper", "sha256": "e" * 64, "declared_at": "cad/build.py:12"}},
        "joints": {},
        "fasteners": {"m3:lid-hopper": {"key": "m3", "clamps": "lid", "into": "hopper", "via": "I2", "count": 2,
                                        "declared_at": "cad/build.py:14"}},
        "assembly": {"steps": []},
    }


def base_evidence(**changes) -> Evidence:
    ev = Evidence(geometry=base_geometry(), geometry_file="exports/dossier-geometry.json",
                  gates={g: _verdict(g) for g in ("wall", "connectivity", "containment", "assembly")})
    for k, v in changes.items():
        setattr(ev, k, v)
    return ev


def write(root: Path, files: Dict[str, Any]) -> Path:
    for name, data in files.items():
        path = root / "dossier" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False))
    return root / "dossier" / "project.yaml"


def rebind(ev: Evidence) -> Evidence:
    """Bind every verdict made for ``base_geometry()`` to ``ev.geometry``: the gates were run again after the build
    that the test's change stands for. A verdict bound to another geometry on purpose stays stale."""
    from cadagent.gates.verdict import bind_inputs, geometry_digest
    base = geometry_digest(base_geometry())
    for v in ev.gates.values():
        if ev.geometry is not None and ((v.get("inputs") or {}).get("geometry") or {}).get("digest") == base:
            bind_inputs(v, ev.geometry)
    return ev


def run(tmp_path: Path, mutate: Optional[Callable[[Dict[str, Any]], Any]] = None,
        evidence: Optional[Evidence] = None, **kw):
    files = base_files()
    ev = evidence if evidence is not None else base_evidence()
    ev.root = str(tmp_path)
    if mutate:
        mutate(files, ev) if mutate.__code__.co_argcount == 2 else mutate(files)
    d = load_dossier(write(tmp_path, files), strict=False, root=tmp_path)
    return lint(d, rebind(ev), **kw)


def card(files, pid):
    return next(c for c in files["sections/store.yaml"]["parts"] if c["id"] == pid)


def test_clean_dossier_has_no_finding_and_every_part_is_gated(tmp_path):
    res = run(tmp_path)
    assert res.findings == [], [str(f) for f in res.findings]
    assert res.passed
    assert {p: r["status"] for p, r in res.parts.items()} == dict.fromkeys(["base", "hopper", "lid", "ball"], "gated")
    assert res.sections["S1"]["status"] == "gated"
    assert res.requirements["R1"]["status"] == "verified"


# --------------------------------------------------------------------------------------------- one rule per case
# (rule code, a change that breaks it, a change of the same thing that satisfies it)

def _drop(key):
    return lambda f: card(f, "lid").pop(key, None)


CASES = {
    "card-no-function": (lambda f: card(f, "lid").update(function=""),
                         lambda f: card(f, "lid").update(function="Keeps the balls in")),
    "card-no-interfaces": (lambda f: card(f, "lid").update(interfaces=[]),
                           lambda f, ev: (card(f, "lid").update(interfaces=[]),
                                          f["project.yaml"]["gates"].update(
                                              free_parts=[{"part": "lid", "reason": "shown lifted off"}]),
                                          f["sections/store.yaml"]["interfaces"].pop(1),
                                          card(f, "hopper").update(interfaces=["I1"], fasteners=[]))),
    "card-no-decision": (lambda f: [c.pop("decisions", None) for c in f["sections/store.yaml"]["parts"]],
                         lambda f: ([c.pop("decisions", None) for c in f["sections/store.yaml"]["parts"]],
                                    f["sections/store.yaml"].update(decisions=[
                                        {"id": "D9", "decision": "One store", "why": "fewer parts",
                                         "alternatives": [{"option": "Two stores", "rejected": "no room"}]}]))),
    "interface-not-party": (lambda f: card(f, "lid").update(interfaces=["I2", "I1"]),
                            lambda f: card(f, "lid").update(interfaces=["I2"])),
    "interface-one-sided": (lambda f: card(f, "lid").update(interfaces=[]),
                            lambda f: card(f, "lid").update(interfaces=["I2"])),
    "interface-datum-conflict": (
        lambda f: f.update({"sections/other.yaml": _other_section(datum="hopper base")}),
        lambda f: f.update({"sections/other.yaml": _other_section(datum="base top")})),
    "interface-conflict": (
        lambda f: f.update({"sections/other.yaml": _other_section(kind="bonded")}),
        lambda f: f.update({"sections/other.yaml": _other_section(kind="fastened")})),
    "fastener-via-mismatch": (lambda f: card(f, "hopper")["fasteners"][0].update(via="I1"),
                              lambda f: card(f, "hopper")["fasteners"][0].update(via="I2")),
    "wall-undeclared": (lambda f: card(f, "hopper")["material"].pop("wall_mm"),
                        lambda f: card(f, "hopper")["material"].update(wall_mm=2.0)),
    "decision-incomplete": (lambda f: card(f, "hopper")["decisions"][0].update(alternatives=[]),
                            lambda f: card(f, "hopper")["decisions"][0].update(
                                alternatives=[{"option": "Round", "rejected": "rolls"}])),
    "alternative-no-reason": (lambda f: card(f, "hopper")["decisions"][0].update(alternatives=["Cone"]),
                              lambda f: card(f, "hopper")["decisions"][0].update(
                                  alternatives=[{"option": "Cone", "rejected": "needs supports"}])),
    "decision-open": (lambda f: card(f, "hopper")["decisions"][0].update(status="open"),
                      lambda f: card(f, "hopper")["decisions"][0].update(status="decided")),
    "unknown-check": (lambda f: card(f, "hopper").update(checks=["gate:wall", "fea:drop"]),
                      lambda f, ev: (card(f, "hopper").update(checks=["gate:wall", "fea:drop"]),
                                     ev.checks.update({"fea:drop": CheckState("fea:drop", "pass")}))),
    "requirement-untraced": (lambda f: f["sections/store.yaml"].update(requirements=["R1"]),
                             lambda f: f["sections/store.yaml"].update(requirements=["R1", "R2"])),
    "requirement-unchecked": (lambda f: card(f, "hopper").update(checks=[]),
                              lambda f: f["project.yaml"]["requirements"][1].update(checks=["gate:connectivity"])),
    "waiver-no-rationale": (lambda f: f["project.yaml"]["requirements"][1].update(status="waived"),
                            lambda f: f["project.yaml"]["requirements"][1].update(
                                status="waived", rationale="the user dropped it")),
    "requirement-status-ignored": (lambda f: f["project.yaml"]["requirements"][0].update(status="verified"),
                                   lambda f: f["project.yaml"]["requirements"][0].pop("status", None)),
    "section-no-requirements": (lambda f: (f["sections/store.yaml"].update(requirements=[]),
                                           [r.update(status="waived", rationale="x")
                                            for r in f["project.yaml"]["requirements"]]),
                                lambda f: f["sections/store.yaml"].update(requirements=["R1", "R2"])),
    "section-no-parts": (lambda f: f.update({"sections/empty.yaml": {"id": "S2", "title": "Empty",
                                                                     "requirements": ["R1"]}}),
                         lambda f: f.update({"sections/empty.yaml": _other_section()})),
    "section-below-gated": (lambda f, ev: ev.gates.update(wall=_verdict("wall", False, ["hopper"])),
                            lambda f, ev: ev.gates.update(wall=_verdict("wall", True))),
    "status-not-earned": (lambda f: card(f, "lid").update(status="signed_off"),
                          lambda f: card(f, "lid").update(status="gated")),
    "status-overclaimed": (lambda f, ev: (card(f, "lid").update(status="gated"), ev.gates.pop("connectivity"),
                                          ev.gates.update(connectivity=_verdict("connectivity", False, ["lid"]))),
                           lambda f, ev: (card(f, "lid").update(status="built"),
                                          ev.gates.update(connectivity=_verdict("connectivity", False, ["lid"])))),
    "geometry-missing": (lambda f, ev: setattr(ev, "geometry", None), lambda f, ev: None),
    "verdict-stale": (lambda f, ev: ev.gates.update(wall=_verdict("wall", geometry={**base_geometry(), "joints": {
                          "J": {"kind": "fixed"}}})),
                      lambda f, ev: ev.gates.update(wall=_verdict("wall"))),
    # the registry join (docs/dossier.md "Joining cards and geometry"), reported by the lint
    "card-without-shape": (lambda f, ev: ev.geometry["parts"].pop("lid"), lambda f, ev: None),
    "shape-without-card": (lambda f, ev: ev.geometry["parts"].update(extra={"section": "S1", "sha256": "f" * 64,
                                                                             "declared_at": "cad/build.py:30"}),
                           lambda f, ev: None),
    "unknown-cavity": (lambda f, ev: ev.geometry["cavities"].clear(), lambda f, ev: None),
    "contains-count": (lambda f: card(f, "hopper")["contains"][0].update(count=3),
                       lambda f: card(f, "hopper")["contains"][0].update(count=2)),
    "fastener-count": (lambda f: card(f, "hopper")["fasteners"][0].update(qty=4),
                       lambda f: card(f, "hopper")["fasteners"][0].update(qty=2)),
    # gate exemptions may name fasteners and instance keys (#56); the lint resolves them against the record
    "exemption-unknown-party": (
        lambda f: f["project.yaml"]["gates"].update(intended_overlaps=[
            {"parts": ["m3:lid-hopper#5", "hopper"], "reason": "thread envelope in the boss"}]),
        lambda f: f["project.yaml"]["gates"].update(intended_overlaps=[
            {"parts": ["m3:lid-hopper#1", "hopper"], "reason": "thread envelope in the boss"},
            {"parts": ["m3:lid-hopper", "lid"], "reason": "a fastener by name"},
            {"parts": ["ball#1", "hopper"], "reason": "an instance key"},
            {"parts": ["ball", "ball"], "reason": "the two balls among themselves"}])),
    # loader errors are lint findings too
    "unknown-id": (lambda f: card(f, "lid").update(interfaces=["I2", "I99"]),
                   lambda f: card(f, "lid").update(interfaces=["I2"])),
}


def _other_section(datum="base top", kind="fastened"):
    """A second section that re-declares I1 (as the other side of an interface does, plan §5.4)."""
    return {"id": "S2", "title": "Other", "requirements": ["R1"],
            "interfaces": [{"id": "I1", "between": ["base", "hopper"], "kind": kind, "datum": datum}],
            "parts": [{"id": "spare", "function": "A spare", "interfaces": [], "checks": ["gate:wall"],
                       "material": {"name": "PETG", "wall_mm": 2}}]}


def _setup_other(files, ev):
    if "sections/other.yaml" in files or "sections/empty.yaml" in files:
        ev.geometry["parts"]["spare"] = {"section": "S2", "sha256": "9" * 64, "count": 1, "free": True}


def _apply(change, files, ev):
    change(files, ev) if change.__code__.co_argcount == 2 else change(files)
    _setup_other(files, ev)


@pytest.mark.parametrize("code", sorted(CASES))
def test_rule_fails_on_the_broken_case(tmp_path, code):
    bad, _ = CASES[code]
    ev = base_evidence()
    res = run(tmp_path, lambda f, e: _apply(bad, f, e), ev)
    found = [f for f in res.findings if f.code == code]
    assert found, f"{code} not reported; got {[str(f) for f in res.findings]}"
    for f in found:                       # file, line and code; a missing input file has no line to point at
        assert f.where is not None and f.where.file, f
        assert f.where.line >= 1 or code in ("geometry-missing", "verdict-stale"), f
    if (RULES.get(code) or ("error",))[0] == "error":
        assert not res.passed


@pytest.mark.parametrize("code", sorted(CASES))
def test_rule_passes_on_the_fixed_case(tmp_path, code):
    _, good = CASES[code]
    ev = base_evidence()
    res = run(tmp_path, lambda f, e: _apply(good, f, e), ev)
    assert code not in res.codes(), [str(f) for f in res.findings if f.code == code]


def test_every_lint_rule_has_a_case():
    review_rules = {"review-invalid", "review-unknown-section", "review-same-actor", "review-stale",
                    "signoff-open-decision", "geometry-invalid", "verdict-invalid"}   # tested below
    assert set(RULES) - review_rules <= set(CASES)


# --------------------------------------------------------------------------------------------- file and line

def test_findings_carry_the_file_and_line_of_the_item(tmp_path):
    res = run(tmp_path, lambda f: card(f, "hopper")["decisions"][0].update(alternatives=[]))
    f = next(f for f in res.findings if f.code == "decision-incomplete")
    text = (tmp_path / "dossier" / "sections" / "store.yaml").read_text().splitlines()
    assert f.where.file == "dossier/sections/store.yaml"
    assert text[f.where.line - 1].lstrip().startswith("- id: D2")
    assert f.parts == ("hopper",) and f.item == "hopper"


def test_wall_on_an_additive_card_without_a_gate_is_a_warning(tmp_path):
    def change(f):
        card(f, "hopper")["material"].pop("wall_mm")
        card(f, "hopper")["checks"] = []
        f["project.yaml"]["requirements"][1]["checks"] = ["gate:connectivity"]
    res = run(tmp_path, change)
    [f] = [f for f in res.findings if f.code == "wall-undeclared"]
    assert f.severity == "warning" and res.passed


def test_seed_decision_without_alternatives_is_caught(tmp_path):
    """Plan §6 seed 10: remove a decision's alternatives; the lint names the part it belongs to."""
    res = run(tmp_path, lambda f: card(f, "hopper")["decisions"][0].pop("alternatives"))
    v = res.to_verdict()
    assert v["pass"] is False
    assert any(f["evidence"]["code"] == "decision-incomplete" and f["parts"] == ["hopper"] for f in v["findings"])


# --------------------------------------------------------------------------------------------- status machine

def test_status_climbs_only_on_evidence(tmp_path):
    res = run(tmp_path, evidence=base_evidence(geometry=None), min_section_status=None)
    assert {r["status"] for r in res.parts.values()} == {"draft"}
    assert res.parts["lid"]["blocked_by"] == ["no geometry record"]

    res = run(tmp_path, evidence=base_evidence(gates={}), min_section_status=None)
    assert res.parts["lid"]["status"] == "built"
    assert "no check applies" in res.parts["lid"]["blocked_by"][0]
    assert res.parts["hopper"]["status"] == "built" and "gate:wall unrun" in res.parts["hopper"]["blocked_by"][0]
    assert res.passed                     # informational without a required status

    res = run(tmp_path, lambda f: card(f, "lid").update(function=""), min_section_status=None)
    assert res.parts["lid"]["status"] == "draft" and "card-no-function" in res.parts["lid"]["blocked_by"][0]
    assert res.parts["hopper"]["status"] == "gated"
    assert res.sections["S1"]["status"] == "draft"


def test_a_gate_counts_against_the_parts_its_findings_name(tmp_path):
    ev = base_evidence()
    ev.gates["connectivity"] = _verdict("connectivity", False, ["ball#1"])
    res = run(tmp_path, evidence=ev)
    assert res.parts["ball"]["status"] == "built"
    assert res.parts["hopper"]["status"] == "gated"
    [f] = [f for f in res.findings if f.code == "section-below-gated"]
    assert f.parts == ("ball",)
    ev.gates["connectivity"] = _verdict("connectivity", False, [])       # names no part: blocks every part
    res = run(tmp_path, evidence=ev)
    assert {r["status"] for r in res.parts.values()} == {"built"}


def _review(section="S1", date="2026-10-28", actor="reviewer", signed_off=True, hashes=None, file=None):
    hashes = hashes if hashes is not None else {p: v["sha256"] for p, v in base_geometry()["parts"].items()}
    return Review(file=file or f"dossier/reviews/{section}-{date}.json", section=section, date=date, actor=actor,
                  signed_off=signed_off, hashes=hashes)


def record_json(section="S1", actor="reviewer", signed_off=True, hashes=None, date="2026-10-28") -> Dict[str, Any]:
    """A complete reviewer record (cadagent.dossier.review.validate_record) as a file holds it."""
    return {"schema": "cad-agent.review/1", "section": section, "date": date, "timestamp": f"{date}T10:00:00Z",
            "actor": actor, "verdict": "sign_off" if signed_off else "changes_requested", "signed_off": signed_off,
            "hashes": hashes if hashes is not None else {p: v["sha256"] for p, v in base_geometry()["parts"].items()},
            "checklist": [{"id": "q1", "answer": "yes", "evidence": "seen in the cut", "views": ["solid-iso"],
                           "image_only": True}],
            "decisions": [], "requirements": [],
            "findings": [] if signed_off else [{"id": "F1", "severity": "major", "text": "fix the lid"}]}


def test_reviewed_and_signed_off_need_a_current_record_by_another_actor(tmp_path):
    res = run(tmp_path, evidence=base_evidence(reviews=[_review(signed_off=False)]))
    assert res.sections["S1"]["status"] == "reviewed"
    res = run(tmp_path, evidence=base_evidence(reviews=[_review()]))
    assert res.sections["S1"]["status"] == "signed_off" and res.passed
    assert "review-stale" not in res.codes()
    assert res.parts["hopper"]["review"]["actor"] == "reviewer"
    res = run(tmp_path, lambda f: card(f, "lid").update(status="signed_off"), base_evidence(reviews=[_review()]))
    assert "status-not-earned" not in res.codes()


@pytest.mark.parametrize("actor", ["builder", "unknown", ""])
def test_review_same_actor_is_refused(tmp_path, actor):
    res = run(tmp_path, evidence=base_evidence(reviews=[_review(actor=actor)]))
    assert "review-same-actor" in res.codes() and not res.passed
    assert res.sections["S1"]["status"] == "gated"
    res = run(tmp_path, evidence=base_evidence(reviews=[_review(actor=actor)]), require_separate_reviewer=False)
    if actor == "builder":
        assert "review-same-actor" not in res.codes() and res.sections["S1"]["status"] == "signed_off"


def test_review_by_another_actor_is_accepted(tmp_path):
    res = run(tmp_path, evidence=base_evidence(reviews=[_review(actor="someone-else")]))
    assert "review-same-actor" not in res.codes()


def test_geometry_change_sends_a_signed_off_section_back_to_gated(tmp_path):
    ev = base_evidence(reviews=[_review()])
    ev.geometry["parts"]["hopper"]["sha256"] = "0" * 64                  # the hopper was rebuilt differently
    res = run(tmp_path, evidence=ev)
    assert res.sections["S1"]["status"] == "gated"
    assert res.parts["hopper"]["status"] == "gated" and res.parts["lid"]["status"] == "gated"
    assert res.parts["hopper"]["invalidated"]["changed"] == ["hopper"]
    assert res.sections["S1"]["invalidated"]["signed_off"] is True
    [stale] = [f for f in res.findings if f.code == "review-stale"]
    assert stale.severity == "warning" and stale.parts == ("hopper",)
    assert res.passed                                                    # gated still meets the bar
    res = run(tmp_path, lambda f: card(f, "lid").update(status="signed_off"), ev)
    assert "status-not-earned" in res.codes()


def test_an_older_matching_record_still_counts_after_a_revert(tmp_path):
    old = _review(date="2026-10-01")
    new = _review(date="2026-10-20", hashes={**old.hashes, "hopper": "0" * 64})
    res = run(tmp_path, evidence=base_evidence(reviews=[old, new]))
    assert res.sections["S1"]["review"]["date"] == "2026-10-01"
    assert "review-stale" in res.codes()


def test_signoff_with_an_open_decision(tmp_path):
    mutate = lambda f: card(f, "hopper")["decisions"][0].update(status="open")  # noqa: E731
    res = run(tmp_path, mutate, base_evidence(reviews=[_review()]))
    assert "signoff-open-decision" in res.codes()
    assert res.sections["S1"]["status"] == "reviewed"
    assert "open decision" in res.parts["hopper"]["blocked_by"][0]
    res = run(tmp_path, mutate, base_evidence(reviews=[_review(signed_off=False)]))
    assert "signoff-open-decision" not in res.codes()


def test_review_for_an_unknown_section(tmp_path):
    res = run(tmp_path, evidence=base_evidence(reviews=[_review(section="S9")]))
    assert "review-unknown-section" in res.codes()
    res = run(tmp_path, evidence=base_evidence(reviews=[_review(section="S1")]))
    assert "review-unknown-section" not in res.codes()


def test_review_records_are_read_and_validated(tmp_path):
    d = tmp_path / "reviews"
    d.mkdir()
    good = {"schema": "cad-agent.review/1", "section": "S1", "date": "2026-10-28",
            "timestamp": "2026-10-28T10:00:00Z", "actor": "r", "verdict": "sign_off", "signed_off": True,
            "hashes": {"hopper": "b" * 64}, "findings": [], "decisions": [], "requirements": [],
            "checklist": [{"id": "q1", "answer": "yes", "evidence": "seen", "views": ["solid-iso"],
                           "image_only": True}]}
    (d / "S1-2026-10-28.json").write_text(json.dumps(good))
    (d / "S1-bad.json").write_text(json.dumps({"section": "S1", "signed_off": "yes"}))
    (d / "S1-broken.json").write_text("{")
    # the minimal shape the lint read before T11 is no longer a record: no verdict, no answers, no evidence
    (d / "S1-minimal.json").write_text(json.dumps({k: good[k] for k in ("schema", "section", "date", "actor",
                                                                      "signed_off", "hashes", "findings")}))
    reviews, findings = load_reviews(d, tmp_path)
    assert [r.file for r in reviews] == ["reviews/S1-2026-10-28.json"]
    assert reviews[0].verdict == "sign_off" and reviews[0].timestamp == "2026-10-28T10:00:00Z"
    assert sorted(f.where.file for f in findings) == ["reviews/S1-bad.json", "reviews/S1-broken.json",
                                                      "reviews/S1-minimal.json"]
    assert {f.code for f in findings} == {"review-invalid"}


def test_requirement_statuses(tmp_path):
    def change(f):
        f["project.yaml"]["requirements"].append({"id": "R3", "text": "Survives a drop", "verify_by": "test",
                                                  "checks": ["gate:wall"]})
        f["project.yaml"]["requirements"].append({"id": "R4", "text": "Looks tidy", "verify_by": "inspection",
                                                  "checks": ["gate:wall"]})
        f["sections/store.yaml"]["requirements"] += ["R3", "R4"]
    res = run(tmp_path, change)
    assert res.requirements["R3"]["status"] == "not_tested"
    assert res.requirements["R4"]["status"] == "unverified"         # inspection needs the section reviewed
    # R2 has no check of its own: the hopper's wall gate covers the trace but verifies nothing about the lid
    assert res.requirements["R2"]["status"] == "unverified"
    assert res.requirements["R2"]["covered_by"] == ["gate:wall"] and res.requirements["R2"]["checks"] == []
    res = run(tmp_path, change, base_evidence(reviews=[_review()]))
    assert res.requirements["R4"]["status"] == "verified"
    ev = base_evidence()
    ev.gates["containment"] = _verdict("containment", False, ["ball#0"])
    res = run(tmp_path, change, ev)
    assert res.requirements["R1"]["status"] == "failed"


# --------------------------------------------------------------------------------------------- project and files

def make_project(root: Path, files=None, geometry=None, gates=None, checks_yaml="") -> Path:
    write(root, files or base_files())
    (root / "cad-agent.yaml").write_text("cad:\n  name: demo\n  dossier: dossier/project.yaml\n" + checks_yaml)
    exports = root / "exports"
    (exports / "gates").mkdir(parents=True)
    if geometry is not False:
        (exports / "dossier-geometry.json").write_text(json.dumps(geometry or base_geometry()))
    from cadagent.gates import run as gr
    from cadagent.gates.verdict import bind_inputs
    from cadagent.project import load_project
    project = load_project(root)
    cfg = gr.gates_config(project)
    extra, dossier = gr.load_extra(cfg), gr.load_dossier(project)
    for g in (gates if gates is not None else ("wall", "connectivity", "containment", "assembly")):
        v = bind_inputs(_verdict(g), geometry or base_geometry(), **gr.expected_inputs(g, cfg, dossier, extra))
        (exports / "gates" / f"{g}.json").write_text(json.dumps(v))   # as `cad-agent gates` writes it
    return root


def test_lint_project_reads_every_input_and_writes_stable_outputs(tmp_path):
    from cadagent.project import load_project

    root = make_project(tmp_path, checks_yaml="  checks:\n    - {id: 'fea:drop', file: exports/fea.json}\n")
    files = base_files()
    card(files, "hopper")["checks"] = ["gate:wall", "fea:drop"]
    write(root, files)
    project = load_project(root)
    res = lint_project(project)
    assert res.parts["hopper"]["status"] == "built"
    assert "fea:drop unrun" in res.parts["hopper"]["blocked_by"][0]
    (root / "exports" / "fea.json").write_text(json.dumps({"pass": True}))
    res = lint_project(project)
    assert res.passed and res.parts["hopper"]["status"] == "gated"
    (root / "dossier" / "reviews").mkdir()
    rec = record_json(hashes={p: v["sha256"] for p, v in base_geometry()["parts"].items()})
    (root / "dossier" / "reviews" / "S1-2026-10-28.json").write_text(json.dumps(rec))
    res = lint_project(project)
    assert res.sections["S1"]["status"] == "signed_off"
    status, verdict = write_outputs(res, project.exports_dir)
    first = (status.read_bytes(), verdict.read_bytes())
    write_outputs(lint_project(project), project.exports_dir)       # the lint's own verdict is not an input
    assert (status.read_bytes(), verdict.read_bytes()) == first
    data = json.loads(first[0])
    assert data["schema"] == "cad-agent.dossier-status/1" and data["physical_fit_verified"] is False
    assert data["sections"]["S1"]["review"]["record"] == "dossier/reviews/S1-2026-10-28.json"
    v = json.loads(first[1])
    assert v["gate"] == "dossier-lint" and v["pass"] is True and v["findings"] == []


def test_lint_project_without_a_dossier_or_with_a_broken_one(tmp_path):
    from cadagent.project import load_project

    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: demo\n")
    assert lint_project(load_project(tmp_path)) is None
    root = make_project(tmp_path / "p", files={"project.yaml": "requirements: [\n"})
    res = lint_project(load_project(root))
    assert not res.passed and res.findings[0].code == "yaml"
    assert res.findings[0].where.file == "dossier/project.yaml"
    assert res.to_status()["pass"] is False


def test_unreadable_inputs_are_findings(tmp_path):
    from cadagent.project import load_project

    root = make_project(tmp_path)
    (root / "exports" / "dossier-geometry.json").write_text("[")
    (root / "exports" / "gates" / "motion.json").write_text("{}")
    res = lint_project(load_project(root))
    assert {"geometry-invalid", "verdict-invalid"} <= set(res.codes())
    assert "geometry-missing" not in res.codes()


def test_the_lint_imports_no_cad_kernel():
    import subprocess
    import sys
    code = ("import sys; import cadagent.dossier.lint, cadagent.cli, cadagent.report; "
            "print(any(m in sys.modules for m in ('cadquery', 'OCP')))")
    src = str(Path(__file__).resolve().parents[1] / "src")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": src, "PATH": ""})
    assert out.stdout.strip() == "False", out.stderr


def test_demo_is_not_tested_and_a_parent_rolls_up_its_children(tmp_path):
    def change(f, demo_ok=True):
        reqs = f["project.yaml"]["requirements"]
        reqs.append({"id": "R0", "text": "Feeds balls", "verify_by": "analysis"})
        reqs[0]["parent"] = "R0"
        reqs[1].update(parent="R0", checks=["gate:connectivity"])
        reqs.append({"id": "R5", "text": "Feeds when the button is pressed", "verify_by": "demo",
                     "checks": ["gate:connectivity"]})
        f["sections/store.yaml"]["requirements"] += ["R5"]
    res = run(tmp_path, change)
    assert res.requirements["R5"]["status"] == "not_tested"
    assert res.requirements["R0"]["status"] == "verified"
    assert [f.code for f in res.findings] == []
    ev = base_evidence()
    ev.gates["connectivity"] = _verdict("connectivity", False, ["lid"])
    assert run(tmp_path, change, ev).requirements["R0"]["status"] == "failed"


def test_a_part_scoped_open_decision_in_project_yaml_blocks_its_section(tmp_path):
    def change(f):
        f["project.yaml"]["decisions"] = [{"id": "D7", "decision": "Lid hinge or loose lid", "part": "lid",
                                           "status": "open"}]
    res = run(tmp_path, change, base_evidence(reviews=[_review()]))
    assert res.sections["S1"]["status"] == "reviewed" and res.sections["S1"]["open_decisions"] == ["D7"]
    assert "signoff-open-decision" in res.codes()
    [f] = [f for f in res.findings if f.code == "decision-open"]
    assert "section 'S1'" in f.message and f.parts == ("lid",)


def test_decisions_kept_in_project_decisions_count_for_their_cards(tmp_path):
    def change(f):
        for c in f["sections/store.yaml"]["parts"]:
            c.pop("decisions", None)
        alt = [{"option": "Other", "rejected": "worse"}]
        f["project.yaml"]["decisions"] = [
            {"id": "D1", "decision": "Flat plate", "why": "simplest", "part": "base", "alternatives": alt},
            {"id": "D3", "decision": "One store", "why": "fewer parts", "section": "S1", "alternatives": alt}]
    assert "card-no-decision" not in run(tmp_path, change).codes()


def test_a_loader_error_inside_a_card_is_the_cards(tmp_path):
    res = run(tmp_path, lambda f: card(f, "lid").update(interfaces=["I2", "I99"]), min_section_status=None)
    [f] = [f for f in res.findings if f.code == "unknown-id"]
    assert f.parts == ("lid",) and f.item == "lid"
    assert res.parts["lid"]["status"] == "draft" and res.parts["hopper"]["status"] == "gated"


def test_a_datum_conflict_between_sections_drops_the_declaring_section(tmp_path):
    def change(f, ev):
        f["sections/store.yaml"]["interfaces"].append(
            {"id": "I3", "between": ["S1", "S2"], "kind": "contact", "datum": "A", "owner": "S1"})
        other = _other_section()
        other["interfaces"] = [{"id": "I3", "between": ["S1", "S2"], "kind": "contact", "datum": "B"}]
        f["sections/other.yaml"] = other
        _setup_other(f, ev)
    res = run(tmp_path, change, min_section_status=None)
    [f] = [f for f in res.findings if f.code == "interface-datum-conflict"]
    assert f.item == "S2" and res.sections["S2"]["status"] == "draft"
    assert res.sections["S1"]["status"] == "gated"


@pytest.mark.parametrize("named, blocked", [
    (["m3:lid-hopper#0"], {"lid", "hopper"}),           # a screw: what it clamps and what it threads into
    (["hopper_cavity"], {"hopper"}),
    (["no_such_thing"], {"base", "hopper", "lid", "ball"}),   # names nothing known: blocks every part
])
def test_gate_findings_on_fasteners_cavities_and_unknown_names(tmp_path, named, blocked):
    ev = base_evidence()
    ev.gates["fasteners"] = _verdict("fasteners", False, named)
    res = run(tmp_path, evidence=ev, min_section_status=None)
    assert {p for p, r in res.parts.items() if r["status"] == "built"} == blocked


@pytest.mark.parametrize("process, warned", [("FDM", True), ("SLA resin", True), ("3D printed PETG", True),
                                             ("injection moulded, pad print", False), ("slab cast", False)])
def test_additive_process_match_is_by_word(tmp_path, process, warned):
    def change(f):
        card(f, "hopper")["material"] = {"name": "x", "process": process}
        card(f, "hopper")["checks"] = []
        f["project.yaml"]["requirements"][1]["checks"] = ["gate:connectivity"]
    assert ("wall-undeclared" in run(tmp_path, change).codes()) is warned


def test_without_a_build_no_review_is_refused_for_the_actor(tmp_path):
    res = run(tmp_path, evidence=base_evidence(geometry=None, reviews=[_review()]), min_section_status=None)
    assert "review-same-actor" not in res.codes()
    assert res.sections["S1"]["status"] == "draft"


# --------------------------------------------------------------------------------------------- stale verdicts (#51)

def test_a_verdict_from_an_earlier_build_is_stale_and_does_not_gate(tmp_path):
    """The hopper is rebuilt and the gates are not run again: every verdict names the changed shape, counts as
    stale (not pass), and the parts fall back to built."""
    ev = base_evidence()
    ev.geometry["parts"]["hopper"]["instances"] = [{"key": "hopper", "sha256": "0" * 64}]
    for v in ev.gates.values():                     # verdicts as the gates wrote them for the previous build
        v["inputs"]["geometry"]["hashes"]["hopper"] = "b" * 64
    files = base_files()
    d = load_dossier(write(tmp_path, files), strict=False, root=tmp_path)
    ev.root = str(tmp_path)
    res = lint(d, ev, min_section_status=None)
    stale = [f for f in res.findings if f.code == "verdict-stale"]
    assert {f.item for f in stale} == {"gate:wall", "gate:connectivity", "gate:containment", "gate:assembly"}
    assert all("hopper" in f.message and f.severity == "error" for f in stale), [str(f) for f in stale]
    assert res.parts["lid"]["status"] == "built" and "stale" in res.parts["lid"]["blocked_by"][0]
    assert not res.passed


def test_an_unbound_verdict_is_stale(tmp_path):
    ev = base_evidence()
    ev.gates["wall"].pop("inputs")
    res = run(tmp_path, evidence=ev, min_section_status=None)
    [f] = [f for f in res.findings if f.code == "verdict-stale"]
    assert "no inputs" in f.message and res.parts["hopper"]["status"] == "built"


def test_a_rebuild_by_another_actor_keeps_verdicts_current(tmp_path):
    """Who built it and where a declaration sits are not inputs: the same shapes stay gated."""
    ev = base_evidence()
    ev.geometry["actor"] = "someone-else"
    ev.geometry["parts"]["hopper"]["declared_at"] = "cad/build.py:99"
    files = base_files()
    d = load_dossier(write(tmp_path, files), strict=False, root=tmp_path)
    ev.root = str(tmp_path)
    res = lint(d, ev)
    assert "verdict-stale" not in res.codes() and res.sections["S1"]["status"] == "gated"


def test_exemption_parties_are_reported_once_and_pairs_of_one_part_need_instances(tmp_path):
    def mutate(f):
        f["project.yaml"]["gates"].update(intended_overlaps=[
            {"parts": ["I1", "hopper"], "reason": "an interface is not a part"},
            {"parts": ["lid", "lid"], "reason": "the lid's instances among themselves"},
            {"parts": ["screw_9", "hopper"], "reason": "a typo"}])
    res = run(tmp_path, mutate)
    codes = [(f.code, f.item) for f in res.findings if f.code in ("unknown-id", "exemption-unknown-party")]
    assert sorted(codes) == [("exemption-unknown-party", "lid"), ("exemption-unknown-party", "screw_9"),
                             ("unknown-id", "")], [str(f) for f in res.findings]
    msg = next(str(f) for f in res.findings if f.item == "screw_9")
    assert "fasteners: m3:lid-hopper" in msg and "project.yaml:" in msg
    # without a geometry record, names the YAML does not know cannot be checked (geometry-missing says why)
    res = run(tmp_path, mutate, base_evidence(geometry=None))
    assert "exemption-unknown-party" not in res.codes()
