"""The reviewer pass and its hash-bound sign-off (plan T11, ``cadagent.dossier.review``).

A record with stale hashes never signs off; a sign-off by the section's builder or author is refused while separate
review is required (a YAML key); an open decision blocks a sign-off; the bundle holds what the reviewer needs; the
per-part build actor survives a rebuild of unchanged geometry. No CAD kernel: the geometry record is JSON and the
packet's images are stand-in bytes (``cad-agent review-packet`` renders the real ones).
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from cadagent import packet as pk
from cadagent.cli import main
from cadagent.dossier.lint import lint_project
from cadagent.dossier.registry import _previous_parts, part_actor
from cadagent.dossier.review import (RECORD_SCHEMA, actor_refusal, check_record, submit_record, validate_record,
                                     write_bundle)
from cadagent.project import load_project

from .test_dossier_lint import base_files, base_geometry, make_project, write


def geometry() -> Dict[str, Any]:
    """``base_geometry()`` with instances and boxes, so the packet plans real views and questions; each part was
    built by ``builder``."""
    geo = copy.deepcopy(base_geometry())
    boxes = {"base": ([0, 0, 0], [100, 60, 5]), "hopper": ([10, 10, 5], [50, 50, 45]),
             "lid": ([10, 10, 45], [50, 50, 48])}
    for name, info in geo["parts"].items():
        if name == "ball":
            info["instances"] = [{"key": f"ball#{i}", "sha256": f"{i + 5}" * 64,
                                  "bbox": {"min": [20 + 12 * i, 20, 8], "max": [30 + 12 * i, 30, 18]}}
                                 for i in range(2)]
        else:
            lo, hi = boxes[name]
            info["instances"] = [{"key": name, "sha256": info["sha256"], "bbox": {"min": lo, "max": hi}}]
        info["actor"] = "builder"
    geo["cavities"]["hopper_cavity"]["bbox"] = {"min": [12, 12, 7], "max": [48, 48, 45]}
    geo["fasteners"]["m3:lid-hopper"]["instances"] = [
        {"key": f"m3:lid-hopper#{i}", "origin": [12 + 36 * i, 12, 48], "direction": [0, 0, -1],
         "sha256": f"{i + 7}" * 64, "bbox": {"min": [10.5 + 36 * i, 10.5, 40], "max": [13.5 + 36 * i, 13.5, 50]}}
        for i in range(2)]
    geo["assembly"]["steps"] = [{"order": 1, "fit": "hopper", "onto": ["base"], "direction": "-Z"},
                                {"order": 2, "fit": "lid", "onto": ["hopper"], "direction": "-Z"}]
    return geo


def render_packet(root: Path, section: str = "S1") -> Dict[str, Any]:
    """The packet as ``cad-agent review-packet`` writes it, with stand-in images."""
    m, target = pk.plan_project_packet(section, root=root)
    target.mkdir(parents=True, exist_ok=True)
    for v in m["views"]:
        v["file"] = f"{v['id']}.png"
        (target / v["file"]).write_bytes(b"\x89PNG stand-in " + v["id"].encode())
        v["sha256"] = pk.file_sha256(target / v["file"])
    m["rendered"] = len(m["views"])
    pk.write_manifest(m, target)
    return m


def setup_project(root: Path, files=None, geo=None) -> Path:
    make_project(root, files=files, geometry=geo or geometry())
    render_packet(root)
    return root


@pytest.fixture
def project(tmp_path):
    return load_project(setup_project(tmp_path))


GATES_RUN = ("wall", "connectivity", "containment", "assembly")          # the verdicts make_project writes


def fill(template: Dict[str, Any], verdict: str = "sign_off") -> Dict[str, Any]:
    """A reviewer's answers: every question answered with its good answer, from the images or a gate."""
    rec = copy.deepcopy(template)
    for a in rec["checklist"]:
        a["answer"] = "yes" if a.get("bad_answer") == "no" else "no"
        a["evidence"] = f"read from {', '.join(a['views'])}"
        if a.get("gate") in GATES_RUN:              # a measurement backs it only when that gate has a verdict
            a["image_only"], a["measurements"] = False, [f"gate:{a['gate']}"]
        else:
            a["image_only"] = True
    for d in rec["decisions"]:
        d["verdict"], d["evidence"] = "justified", "the alternative is rejected for a stated reason"
    for r in rec["requirements"]:
        r["traced"], r["evidence"] = "yes", "checked by the section's gates"
    rec["verdict"] = verdict
    if verdict == "changes_requested":
        rec["findings"] = [{"id": "F1", "severity": "major", "text": "the lid has no locating lip",
                            "view": "solid-iso", "parts": ["lid"]}]
    return rec


def template(project) -> Dict[str, Any]:
    b = write_bundle(project, "S1")
    return json.loads((Path(project.root) / b["dir"] / "record-template.json").read_text())


def valid_record(**changes) -> Dict[str, Any]:
    rec = {"schema": RECORD_SCHEMA, "section": "S1", "date": "2026-10-28", "timestamp": "2026-10-28T10:00:00Z",
           "actor": "reviewer", "verdict": "sign_off", "signed_off": True, "hashes": {"hopper": "b" * 64},
           "checklist": [{"id": "q1", "answer": "yes", "bad_answer": "no", "evidence": "the ball is inside",
                          "views": ["cut-cavity-hopper_cavity"], "image_only": False,
                          "measurements": ["gate:containment"]},
                         {"id": "q2", "answer": "no", "bad_answer": "yes", "evidence": "every part has features",
                          "views": ["solid-iso"], "image_only": True}],
           "decisions": [{"id": "D1", "verdict": "weak", "evidence": "the ribbed plate was not costed"}],
           "requirements": [{"id": "R1", "traced": "yes", "evidence": "gate:containment"}],
           "findings": [{"id": "F1", "severity": "minor", "text": "caption the pin", "view": "solid-iso"}]}
    rec.update(changes)
    return rec


def codes(problems) -> set:
    return {p.code for p in problems}


# ----------------------------------------------------------------------------------------------- the record alone

def test_a_complete_record_is_valid():
    assert validate_record(valid_record()) == []
    assert validate_record(valid_record(verdict="changes_requested", signed_off=False)) == []


@pytest.mark.parametrize("change, code", [
    (lambda r: r.pop("verdict"), "missing"),
    (lambda r: r.update(schema="cad-agent.review/0"), "schema"),
    (lambda r: r.update(signed_off=False), "verdict"),
    (lambda r: r.update(verdict="approved"), "verdict"),
    (lambda r: r.update(date="28/10/2026"), "type"),
    (lambda r: r.update(timestamp="2026-10-28T10:00:00"), "type"),       # no zone
    (lambda r: r.update(hashes={"hopper": "short"}), "hashes"),
    (lambda r: r.update(hashes={}), "hashes"),
    (lambda r: r.update(signed_of=True), "unknown-key"),
    (lambda r: r.update(physical_fit_verified=True), "overclaim"),
    (lambda r: r["checklist"][0].update(answer="maybe"), "answer"),
    (lambda r: r["checklist"][0].update(evidence=""), "evidence"),
    (lambda r: r["checklist"][1].pop("image_only"), "image-only"),
    (lambda r: r["checklist"][1].update(views=[]), "image-only"),           # image-only names its views
    (lambda r: r["checklist"][0].update(measurements=[]), "image-only"),    # not image-only: cite a measurement
    (lambda r: r["checklist"][1].update(measurements=["gate:wall"]), "image-only"),
    (lambda r: r["checklist"].append(dict(r["checklist"][0])), "duplicate"),
    (lambda r: r["decisions"][0].update(verdict="fine"), "decision"),
    (lambda r: r["decisions"][0].update(evidence=" "), "evidence"),
    (lambda r: r["requirements"][0].update(traced=True), "requirement"),
    (lambda r: r["findings"][0].update(severity="blocker"), "finding"),
    (lambda r: r["findings"][0].pop("text"), "missing"),
])
def test_every_field_is_checked(change, code):
    rec = valid_record()
    change(rec)
    assert code in codes(validate_record(rec)), [str(p) for p in validate_record(rec)]


@pytest.mark.parametrize("change", [
    lambda r: r["findings"].append({"id": "F2", "severity": "major", "text": "the lid floats"}),
    lambda r: r["checklist"][0].update(answer="unclear"),
    lambda r: r["checklist"][0].update(answer="no"),                        # its bad answer
    lambda r: r["checklist"][1].update(answer="yes"),                       # its bad answer
    lambda r: r["decisions"][0].update(verdict="missing_alternative"),
    lambda r: r["requirements"][0].update(traced="unclear"),
    lambda r: r.update(checklist=[]),
])
def test_a_sign_off_must_be_consistent_with_what_it_found(change):
    rec = valid_record()
    change(rec)
    assert "signoff" in codes(validate_record(rec))
    rec.update(verdict="changes_requested", signed_off=False)              # the same answers request changes
    assert "signoff" not in codes(validate_record(rec))


def test_changes_requested_says_what_to_change():
    rec = valid_record(verdict="changes_requested", signed_off=False, findings=[])
    assert codes(validate_record(rec)) == {"changes"}


# ----------------------------------------------------------------------------------------------- who built what

def test_part_actor_survives_a_rebuild_of_unchanged_geometry(tmp_path):
    """The #37 limitation: the record kept only the last build's actor. Now each part keeps the actor of the build
    that first produced its current hash."""
    assert part_actor({"sha256": "a", "actor": "author"}, "a", "reviewer") == "author"     # rebuilt unchanged
    assert part_actor({"sha256": "a", "actor": "author"}, "b", "reviewer") == "reviewer"   # changed
    assert part_actor({"sha256": "a", "actor": "unknown"}, "a", "author") == "author"      # known beats unknown
    assert part_actor(None, "a", "author") == "author"
    old = tmp_path / "dossier-geometry.json"
    old.write_text(json.dumps({"actor": "author", "parts": {"lid": {"sha256": "c"}, "hopper": {"sha256": "b",
                                                                                                "actor": "x"}}}))
    prev = _previous_parts(old)                                          # a record from before per-part actors
    assert prev["lid"]["actor"] == "author" and prev["hopper"]["actor"] == "x"
    assert _previous_parts(tmp_path / "missing.json") == {}


def test_registry_records_the_build_actor_per_part(tmp_path, monkeypatch):
    pytest.importorskip("cadquery")
    import cadquery as cq
    from cadagent.dossier.registry import Registry

    def build(width: float):
        reg = Registry()
        reg.part("plate", section="S1")(lambda p: cq.Workplane().box(width, 10, 2).val())
        reg.part("lid", section="S1")(lambda p: cq.Workplane().box(10, 10, 1).translate((0, 0, 5)).val())
        return reg.build({}, root=tmp_path, out_dir="exports").geometry

    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: t\n")
    monkeypatch.setenv("CAD_AGENT_ACTOR", "author")
    geo = build(10)
    assert {p: v["actor"] for p, v in geo["parts"].items()} == {"plate": "author", "lid": "author"}
    monkeypatch.setenv("CAD_AGENT_ACTOR", "reviewer")
    geo2 = build(10)                                                       # the reviewer rebuilds: no change
    assert geo2["actor"] == "reviewer"
    assert {p: v["actor"] for p, v in geo2["parts"].items()} == {"plate": "author", "lid": "author"}
    from cadagent.gates.verdict import geometry_digest
    assert geometry_digest(geo2) == geometry_digest(geo)                    # who built it is not a gate input
    geo3 = build(12)                                                       # the reviewer changes the plate
    assert geo3["parts"]["plate"]["actor"] == "reviewer" and geo3["parts"]["lid"]["actor"] == "author"


def _dossier(tmp_path, files=None):
    from cadagent.dossier import load_dossier
    return load_dossier(write(tmp_path, files or base_files()), strict=False, root=tmp_path)


def test_actor_refusal(tmp_path):
    files = base_files()
    files["sections/store.yaml"]["author"] = "planner"
    d = _dossier(tmp_path, files)
    geo = geometry()
    geo["actor"] = "reviewer"                       # the reviewer rebuilt last; the parts are still the builder's
    assert actor_refusal("reviewer", "S1", d, geo) is None
    assert "built ball, base, hopper, lid" in actor_refusal("builder", "S1", d, geo)
    geo["parts"]["lid"]["actor"] = "helper"
    assert actor_refusal("helper", "S1", d, geo) == "the reviewer 'helper' built lid"
    assert "author of section S1" in actor_refusal("planner", "S1", d, geo)
    assert "reviewer's actor is unknown" in actor_refusal("unknown", "S1", d, geo)
    geo["parts"]["lid"].pop("actor")
    geo["actor"] = "unknown"                        # an old record: the top-level actor stands in, and is unknown
    assert "build actor of lid is unknown" in actor_refusal("reviewer", "S1", d, geo)


# ----------------------------------------------------------------------------------------------- the bundle

def test_the_bundle_holds_what_the_reviewer_needs(project):
    root = Path(project.root)
    b = write_bundle(project, "S1")
    out = root / "exports" / "review-bundle" / "S1"
    assert b["dir"] == "exports/review-bundle/S1" and b["schema"] == "cad-agent.review-bundle/1"
    packet = json.loads((root / "exports" / "review" / "S1" / "manifest.json").read_text())
    expected = {"PROMPT.md", "bundle.json", "gates.json", "status.json", "checklist.json", "diff.patch",
                "record-template.json", "section/dossier/sections/store.yaml", "section/dossier/project.yaml",
                "packet/manifest.json"} | {f"packet/{v['file']}" for v in packet["views"]}
    have = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert have == expected
    assert set(b["files"]) == expected - {"bundle.json"}
    assert (out / "section/dossier/sections/store.yaml").read_text() == \
        (root / "dossier/sections/store.yaml").read_text()
    assert json.loads((out / "packet/manifest.json").read_text()) == packet
    gates = json.loads((out / "gates.json").read_text())
    assert set(gates["gates"]) >= {"wall", "connectivity", "containment", "assembly"}
    status = json.loads((out / "status.json").read_text())
    assert status["section"]["status"] == "gated" and status["parts"]["lid"]["built_by"] == "builder"
    t = json.loads((out / "record-template.json").read_text())
    assert t["hashes"] == {p: v["sha256"] for p, v in geometry()["parts"].items()}
    assert [a["id"] for a in t["checklist"]] == [q["id"] for q in packet["checklist"]["questions"]]
    assert all(a["answer"] is None and a["image_only"] is None for a in t["checklist"]) and t["checklist"]
    assert [d["id"] for d in t["decisions"]] == ["D1", "D2"]
    assert [r["id"] for r in t["requirements"]] == ["R1", "R2"]
    assert validate_record(t), "an unfilled template is not a record"
    checklist = json.loads((out / "checklist.json").read_text())
    assert checklist["checklist"]["questions"] == packet["checklist"]["questions"]
    prompt = (out / "PROMPT.md").read_text()
    assert "Review of section S1: Store" in prompt and "image_only" in prompt and b["submit"] in prompt
    assert b["ready"] and b["blockers"] == [] and b["packet"]["stale"] is None
    assert b["geometry"]["built_by"]["hopper"] == "builder"
    assert "not a git checkout" in b["diff"]["note"]
    # --bundle-dir: written where asked; a directory that is not a bundle is never wiped
    other = root / "elsewhere"
    assert write_bundle(project, "S1", other)["dir"] == "elsewhere" and (other / "bundle.json").is_file()
    write_bundle(project, "S1", other)                                    # a bundle is rewritten in place
    (root / "notes").mkdir()
    (root / "notes" / "mine.txt").write_text("keep")
    from cadagent.dossier.review import ReviewError
    with pytest.raises(ReviewError, match="not empty"):
        write_bundle(project, "S1", root / "notes")
    assert (root / "notes" / "mine.txt").read_text() == "keep"
    with pytest.raises(ReviewError, match="not in the dossier"):
        write_bundle(project, "S9")


def test_the_bundle_says_what_blocks_a_sign_off(tmp_path):
    files = base_files()
    files["sections/store.yaml"]["parts"][1]["decisions"][0]["status"] = "open"
    project = load_project(setup_project(tmp_path, files))
    shutil.rmtree(tmp_path / "exports" / "review")
    b = write_bundle(project, "S1")
    assert not b["ready"]
    assert any("no review packet" in x for x in b["blockers"])
    assert any("open decision(s) D2" in x for x in b["blockers"])


def _git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com"}
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
                          env=env).stdout


def test_the_bundle_diffs_since_the_last_sign_off(project):
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    root = Path(project.root)
    _git(root, "init", "-q")
    (root / ".gitignore").write_text("exports/\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")
    b = write_bundle(project, "S1")
    assert b["diff"]["base"] is None and "no earlier sign-off" in b["diff"]["note"]
    path, rec, problems = submit_record(project, "S1", fill(template(project)), reviewer="reviewer")
    assert problems == [] and rec["commit"] == _git(root, "rev-parse", "HEAD").strip()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "signed off")
    sec = root / "dossier" / "sections" / "store.yaml"
    sec.write_text(sec.read_text().replace("Hold the balls", "Hold the balls dry"))      # uncommitted
    (root / "dossier" / "sections" / "new.yaml").write_text("# untracked\n")
    b = write_bundle(project, "S1")
    assert b["diff"]["base"] == rec["commit"] and b["diff"]["record"] == path.relative_to(root).as_posix()
    patch = (root / b["dir"] / "diff.patch").read_text()
    assert "+purpose: Hold the balls dry" in patch and "reviews/" not in patch
    assert b["diff"]["untracked"] == ["dossier/sections/new.yaml"]
    first = _git(root, "rev-list", "--max-parents=0", "HEAD").strip()
    assert write_bundle(project, "S1", since=first)["diff"]["base"] == first


# ----------------------------------------------------------------------------------------------- submitting

def test_a_reviewer_signs_off_and_the_section_is_signed_off(project):
    root = Path(project.root)
    path, rec, problems = submit_record(project, "S1", fill(template(project)), reviewer="reviewer")
    assert problems == [], [str(p) for p in problems]
    assert path.parent == root / "dossier" / "reviews" and path.name.startswith("S1-")
    saved = json.loads(path.read_text())
    assert saved == rec and validate_record(saved) == []
    assert saved["actor"] == "reviewer" and saved["signed_off"] is True
    assert saved["build_actors"] == dict.fromkeys(["base", "hopper", "lid", "ball"], "builder")
    assert saved["packet"]["stale"] is None and saved["packet"]["sha256"]
    res = lint_project(project)
    assert res.sections["S1"]["status"] == "signed_off" and res.passed, [str(f) for f in res.findings]
    assert res.sections["S1"]["review"]["verdict"] == "sign_off"
    # a second record the same day gets its own file
    path2, _, problems = submit_record(project, "S1", fill(template(project), "changes_requested"),
                                       reviewer="reviewer")
    assert problems == [] and path2.name == path.stem + "-2.json"
    res = lint_project(project)                     # the newest current record decides
    assert res.sections["S1"]["status"] == "reviewed" and res.sections["S1"]["review"]["blocking"] == 1


def test_a_record_with_stale_hashes_does_not_sign_off(project):
    """The geometry changes between the bundle and the submission: refused. A record already written goes stale
    when the geometry changes after it: the section falls back to gated."""
    root = Path(project.root)
    rec = fill(template(project))
    geo_file = root / "exports" / "dossier-geometry.json"
    geo = json.loads(geo_file.read_text())
    geo["parts"]["hopper"]["sha256"] = "0" * 64
    geo_file.write_text(json.dumps(geo))
    path, _, problems = submit_record(project, "S1", rec, reviewer="reviewer")
    assert path is None and "stale-hashes" in codes(problems)
    assert "hopper" in next(str(p) for p in problems if p.code == "stale-hashes")
    assert not (root / "dossier" / "reviews").exists()
    # written while current, then the geometry changes
    geo_file.write_text(json.dumps(geometry()))
    path, _, problems = submit_record(project, "S1", rec, reviewer="reviewer")
    assert problems == [] and lint_project(project).sections["S1"]["status"] == "signed_off"
    geo_file.write_text(json.dumps(geo))
    res = lint_project(project, min_section_status=None)
    assert res.sections["S1"]["status"] != "signed_off"
    assert "review-stale" in res.codes() and res.sections["S1"]["invalidated"]["changed"] == ["hopper"]
    # a record naming a part that is not in the section is not current either
    rec2 = fill(template(project))
    rec2["hashes"]["ghost"] = "e" * 64
    assert "stale-hashes" in codes(submit_record(project, "S1", rec2, reviewer="reviewer", write=False)[2])


def test_a_same_actor_sign_off_is_refused_when_required(tmp_path):
    root = setup_project(tmp_path)
    project = load_project(root)
    rec = fill(template(project))
    path, _, problems = submit_record(project, "S1", rec, reviewer="builder")
    assert path is None and "same-actor" in codes(problems)
    for who in ("", "unknown"):
        assert "same-actor" in codes(submit_record(project, "S1", rec, reviewer=who, write=False)[2])
    # a record written by hand by the builder is refused by the lint
    reviews = root / "dossier" / "reviews"
    reviews.mkdir()
    _, filled, problems = submit_record(project, "S1", rec, reviewer="reviewer", write=False)
    assert problems == []
    (reviews / "S1-2026-10-28.json").write_text(json.dumps({**filled, "actor": "builder"}))
    res = lint_project(project)
    assert "review-same-actor" in res.codes() and not res.passed and res.sections["S1"]["status"] == "gated"
    # turned off in the dossier's gates: (a YAML key): accepted, and the gate verdicts stay current
    files = base_files()
    files["project.yaml"]["gates"]["require_separate_reviewer"] = False
    write(root, files)
    project = load_project(root)
    res = lint_project(project)
    assert "review-same-actor" not in res.codes() and "verdict-stale" not in res.codes()
    assert res.sections["S1"]["status"] == "signed_off" and res.to_status()["require_separate_reviewer"] is False
    assert "same-actor" not in codes(submit_record(project, "S1", rec, reviewer="builder", write=False)[2])
    # a value that is not a boolean is a loader error, never a silent "off"
    files["project.yaml"]["gates"]["require_separate_reviewer"] = "no"
    write(root, files)
    assert any("require_separate_reviewer" in str(f) for f in lint_project(load_project(root)).errors)


def test_an_old_record_does_not_become_an_error_when_its_reviewer_builds_later(project):
    """The reviewer signs off, then changes the lid (and so becomes its builder): the old record no longer counts
    (stale), and is not reported as a same-actor review either."""
    root = Path(project.root)
    path, _, problems = submit_record(project, "S1", fill(template(project)), reviewer="reviewer")
    assert problems == []
    geo = geometry()
    geo["parts"]["lid"].update(sha256="0" * 64, actor="reviewer")
    (root / "exports" / "dossier-geometry.json").write_text(json.dumps(geo))
    res = lint_project(project, min_section_status=None)
    assert "review-stale" in res.codes() and "review-same-actor" not in res.codes()
    assert res.sections["S1"]["status"] != "signed_off"


def test_the_record_actor_is_the_submitting_actor(project, monkeypatch):
    rec = fill(template(project))
    rec["actor"] = "someone"
    _, _, problems = submit_record(project, "S1", rec, reviewer="reviewer", write=False)
    assert "actor" in codes(problems)
    monkeypatch.setenv("CAD_AGENT_ACTOR", "reviewer-from-env")
    rec["actor"] = ""
    _, filled, problems = submit_record(project, "S1", rec, write=False)
    assert problems == [] and filled["actor"] == "reviewer-from-env"


def test_an_author_named_in_the_dossier_cannot_sign_off(tmp_path):
    files = base_files()
    files["sections/store.yaml"]["parts"][2]["author"] = "lid-writer"
    project = load_project(setup_project(tmp_path, files))
    problems = submit_record(project, "S1", fill(template(project)), reviewer="lid-writer", write=False)[2]
    assert "same-actor" in codes(problems)
    assert "author of card lid" in next(str(p) for p in problems if p.code == "same-actor")


def test_an_open_decision_blocks_a_sign_off(tmp_path):
    files = base_files()
    files["sections/store.yaml"]["parts"][1]["decisions"][0]["status"] = "open"
    project = load_project(setup_project(tmp_path, files))
    rec = fill(template(project))
    problems = submit_record(project, "S1", rec, reviewer="reviewer", write=False)[2]
    assert "open-decision" in codes(problems)
    ok = submit_record(project, "S1", fill(template(project), "changes_requested"), reviewer="reviewer")
    assert ok[2] == [] and ok[0] is not None                                # changes may still be requested


def test_a_sign_off_needs_a_current_packet_and_every_question(project):
    root = Path(project.root)
    rec = fill(template(project))
    short = copy.deepcopy(rec)
    dropped = short["checklist"].pop()
    assert "unanswered" in codes(submit_record(project, "S1", short, reviewer="reviewer", write=False)[2])
    wrong = copy.deepcopy(rec)
    wrong["checklist"][0]["question"] = "Is it nice?"
    wrong["checklist"][0]["views"] = ["a-view-not-in-the-packet"]
    probs = codes(submit_record(project, "S1", wrong, reviewer="reviewer", write=False)[2])
    assert {"question-changed", "unknown-view"} <= probs
    bad = copy.deepcopy(rec)
    q = bad["checklist"][0]
    q["answer"] = q.pop("bad_answer")               # the packet's bad answer still applies when the copy is gone
    assert "signoff" in codes(submit_record(project, "S1", bad, reviewer="reviewer", write=False)[2])
    less = copy.deepcopy(rec)
    less["decisions"].pop()
    less["requirements"].pop()
    assert {"unjudged", "untraced"} <= codes(submit_record(project, "S1", less, reviewer="reviewer", write=False)[2])
    # the packet goes stale (a gate verdict is rewritten): a sign-off is refused, a change request is not
    v = root / "exports" / "gates" / "wall.json"
    data = json.loads(v.read_text())
    data["note"] = "rewritten"
    v.write_text(json.dumps(data))
    assert "packet-stale" in codes(submit_record(project, "S1", rec, reviewer="reviewer", write=False)[2])
    assert submit_record(project, "S1", fill(template(project), "changes_requested"), reviewer="reviewer",
                         write=False)[2] == []
    assert dropped["id"]


def test_check_record_without_a_packet(project):
    from cadagent.dossier import load_project_dossier
    d = load_project_dossier(project, strict=False)
    rec = valid_record(hashes={p: v["sha256"] for p, v in geometry()["parts"].items()})
    rec["decisions"] = [{"id": i, "verdict": "justified", "evidence": "ok"} for i in ("D1", "D2")]
    rec["requirements"] = [{"id": i, "traced": "yes", "evidence": "ok"} for i in ("R1", "R2")]
    assert codes(check_record(rec, dossier=d, geometry=geometry())) == {"packet"}
    rec.update(verdict="changes_requested", signed_off=False)
    assert check_record(rec, dossier=d, geometry=geometry()) == []
    assert codes(check_record(rec, dossier=d, geometry=None)) == {"geometry"}
    assert codes(check_record({**rec, "section": "S9"}, dossier=d, geometry=geometry())) == {"section"}


# ----------------------------------------------------------------------------------------------- the CLI

def test_cli_bundle_check_and_submit(project, tmp_path, capsys, monkeypatch):
    root = Path(project.root)
    assert main(["review-section", "S1", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "exports/review-bundle/S1" in out and "PROMPT.md" in out
    t = json.loads((root / "exports/review-bundle/S1/record-template.json").read_text())
    rec_file = tmp_path / "my-review.json"
    rec_file.write_text(json.dumps(t))
    monkeypatch.setenv("CAD_AGENT_ACTOR", "reviewer")
    assert main(["review-section", "S1", "--project", str(root), "--check", str(rec_file)]) == 1
    assert "REFUSED" in capsys.readouterr().out
    rec_file.write_text(json.dumps(fill(t)))
    assert main(["review-section", "S1", "--project", str(root), "--check", str(rec_file)]) == 0
    assert "not written" in capsys.readouterr().out and not (root / "dossier" / "reviews").exists()
    monkeypatch.setenv("CAD_AGENT_ACTOR", "builder")
    assert main(["review-section", "S1", "--project", str(root), "--submit", str(rec_file)]) == 1
    assert "same-actor" in capsys.readouterr().out
    monkeypatch.setenv("CAD_AGENT_ACTOR", "reviewer")
    assert main(["review-section", "S1", "--project", str(root), "--submit", str(rec_file)]) == 0
    out = capsys.readouterr().out
    assert "sign_off by reviewer" in out and "section status now: signed_off" in out
    other = tmp_path / "bundle-here"
    assert main(["review-section", "S1", "--project", str(root), "--bundle-dir", str(other)]) == 1  # packet stale now
    assert (other / "bundle.json").is_file() and "BLOCKER packet" in capsys.readouterr().out
    assert main(["review-section", "S9", "--project", str(root)]) == 2


def test_the_site_shows_the_record(project):
    """The site's section page (T15) lists the record's findings beside the image each one's `view` names, and the
    reviewer's answer under each checklist question; the index says changes were requested."""
    root = Path(project.root)
    rec = fill(template(project), "changes_requested")
    rec["checklist"][0]["answer"] = "unclear"
    rec["checklist"][0]["evidence"] = "the cut hides the far wall"
    path, rec, problems = submit_record(project, "S1", rec, reviewer="reviewer")
    assert problems == []
    row = lint_project(project, min_section_status=None).to_status()["sections"]["S1"]["review"]
    assert row["record"] == path.relative_to(root).as_posix() and row["findings"] == 1 and row["blocking"] == 1
    assert main(["dossier", "--project", str(root), "--min-status", "none"]) == 0
    assert main(["site", "--project", str(root)]) == 0
    index = (root / "site" / "review" / "index.html").read_text()
    assert "changes requested (1 finding(s))" in index
    page = (root / "site" / "review" / "section-s1.html").read_text()
    iso = page.split("<b>solid-iso</b>")[1].split("</figure>")[0]
    assert "the lid has no locating lip" in iso, "a finding sits beside the image its view names"
    q = rec["checklist"][0]
    assert "the cut hides the far wall" in page and 'class="pill warn">unclear<' in page
    assert ("image only" if q["image_only"] else f"measured: {q['measurements'][0]}") in page


# ----------------------------------------------------------------------------------------------- review of #59

def test_a_hand_written_record_gets_the_submit_checks_in_the_lint(project):
    """A sign-off written by hand, with a made-up question and no decisions or requirements judged, does not
    count: the lint runs check_record against the dossier and the packet on disk, as --submit would."""
    root = Path(project.root)
    _, good, problems = submit_record(project, "S1", fill(template(project)), reviewer="reviewer", write=False)
    assert problems == []
    bad = {**good, "decisions": [], "requirements": [],
           "checklist": [{"id": "made-up", "answer": "yes", "evidence": "fine", "views": ["solid-iso"],
                          "image_only": True}]}
    assert validate_record(bad) == []                                       # well formed on its own
    reviews = root / "dossier" / "reviews"
    reviews.mkdir()
    (reviews / "S1-2026-10-28.json").write_text(json.dumps(bad))
    res = lint_project(project)
    [f] = [f for f in res.findings if f.code == "review-incomplete"]
    assert "unjudged" in f.message and "untraced" in f.message and "unknown-question" in f.message
    assert res.sections["S1"]["status"] == "gated" and res.passed            # it does not count; gated is the bar
    (reviews / "S1-2026-10-28.json").write_text(json.dumps(good))
    res = lint_project(project)
    assert "review-incomplete" not in res.codes() and res.sections["S1"]["status"] == "signed_off"
    # without the packet on disk the questions cannot be checked; decisions and requirements still are
    shutil.rmtree(root / "exports" / "review")
    (reviews / "S1-2026-10-28.json").write_text(json.dumps({**bad, "checklist": good["checklist"]}))
    res = lint_project(project)
    [f] = [f for f in res.findings if f.code == "review-incomplete"]
    assert "unknown-question" not in f.message and "unjudged" in f.message


def test_an_unknown_builder_makes_a_review_not_count_without_failing(project):
    """A fresh checkout built without CAD_AGENT_ACTOR: nobody can be shown to be someone else, so the sign-off
    does not count, but that is a warning, not an error that fails `cad-agent check`."""
    root = Path(project.root)
    assert submit_record(project, "S1", fill(template(project)), reviewer="reviewer")[2] == []
    geo = geometry()
    for info in geo["parts"].values():
        info["actor"] = "unknown"
    (root / "exports" / "dossier-geometry.json").write_text(json.dumps(geo))
    res = lint_project(project)
    [f] = [f for f in res.findings if f.code == "review-builder-unknown"]
    assert f.severity == "warning" and "review-same-actor" not in res.codes()
    assert res.passed and res.sections["S1"]["status"] == "gated"


def test_an_inspection_requirement_needs_the_review_to_trace_it(tmp_path):
    files = base_files()
    files["project.yaml"]["requirements"][0]["verify_by"] = "inspection"
    project = load_project(setup_project(tmp_path, files))
    rec = fill(template(project), "changes_requested")
    rec["requirements"][0]["traced"] = "no"
    assert submit_record(project, "S1", rec, reviewer="reviewer")[2] == []
    res = lint_project(project, min_section_status=None)
    assert res.sections["S1"]["status"] == "reviewed" and res.requirements["R1"]["status"] == "unverified"
    render_packet(Path(project.root))               # a record changes the lint the packet quotes: render it again
    assert submit_record(project, "S1", fill(template(project)), reviewer="reviewer")[2] == []
    assert lint_project(project).requirements["R1"]["status"] == "verified"


def test_the_separate_review_switch_is_not_a_gate_input(tmp_path):
    from cadagent.gates import run as gr
    from cadagent.gates.verdict import digest_of
    root = setup_project(tmp_path)

    def digest() -> str:
        project = load_project(root)
        cfg = gr.gates_config(project)
        return digest_of(gr.declarations(gr.load_dossier(project), gr.load_extra(cfg)))

    before = digest()
    files = base_files()
    files["project.yaml"]["gates"]["require_separate_reviewer"] = False
    write(root, files)
    assert digest() == before
    files["project.yaml"]["gates"]["strict_interfaces"] = True                # a real gate option does change it
    write(root, files)
    assert digest() != before


def test_the_diff_covers_the_section_s_own_sources(tmp_path):
    geo = geometry()
    geo["parts"]["lid"]["declared_at"] = "cad/lid.py:3"
    geo["joints"]["I9"] = {"kind": "revolute", "moving": "arm", "fixed": "post", "declared_at": "cad/other.py:5"}
    root = setup_project(tmp_path, geo=geo)
    for f in ("cad/build.py", "cad/lid.py", "cad/other.py"):
        (root / f).parent.mkdir(exist_ok=True)
        (root / f).write_text("# build\n")
    from cadagent.dossier.review import _load, _diff_paths
    paths = _diff_paths(_load(load_project(root), "S1"), "S1")
    assert paths == ["cad-agent.yaml", "cad/build.py", "cad/lid.py", "dossier"]      # not another section's joint


def test_an_incomplete_change_request_still_voids_an_earlier_sign_off(project):
    """A second reviewer stops at a critical flaw and answers one question: the change request is accepted by
    --submit, and even written by hand (incomplete) it voids the earlier sign-off of the same geometry."""
    root = Path(project.root)
    assert submit_record(project, "S1", fill(template(project)), reviewer="reviewer")[2] == []
    assert lint_project(project).sections["S1"]["status"] == "signed_off"
    render_packet(root)
    t = template(project)
    short = {**fill(t, "changes_requested"), "checklist": fill(t)["checklist"][:1], "decisions": [],
             "requirements": []}
    short["findings"][0]["severity"] = "critical"
    _, rec, problems = submit_record(project, "S1", short, reviewer="second-reviewer", write=False)
    assert problems == []                                       # a change request may stop at the first flaw
    rec["checklist"].append({"id": "made-up", "answer": "no", "evidence": "x", "views": ["solid-iso"],
                             "image_only": True})              # and one written by hand that the lint flags
    rec["timestamp"] = "2099-01-01T00:00:00Z"
    (root / "dossier" / "reviews" / "S1-2099-01-01.json").write_text(json.dumps({**rec, "date": "2099-01-01"}))
    res = lint_project(project, min_section_status=None)
    [f] = [f for f in res.findings if f.code == "review-incomplete"]
    assert "counts as a change request" in f.message
    assert res.sections["S1"]["status"] == "reviewed" and res.sections["S1"]["review"]["verdict"] == "changes_requested"


def test_a_packet_rendered_again_later_does_not_void_a_sign_off(project):
    """`review-packet --view` after a sign-off leaves other views without an image: the record's answers cite
    views the packet no longer has an image for, which only --submit judges."""
    root = Path(project.root)
    assert submit_record(project, "S1", fill(template(project)), reviewer="reviewer")[2] == []
    m = json.loads((root / "exports/review/S1/manifest.json").read_text())
    for v in m["views"]:
        v["file"], v["sha256"] = None, None
    m["rendered"] = 0
    pk.write_manifest(m, root / "exports/review/S1")
    res = lint_project(project)
    assert "review-incomplete" not in res.codes() and res.sections["S1"]["status"] == "signed_off"
