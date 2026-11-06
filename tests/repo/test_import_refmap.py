"""tools/import_refmap.py (#323 phase 2): the Reference Map's data.json becomes schema-2 shards that check() accepts.

A 6-row fixture runs through the importer in a planted checkout: three projects (a scored GitHub repo under GPL, an
unscored paper, an MIT repo whose summary uses the map's "our note") and three guides (one with a corroborated rule,
one already a read source in the core registry, one already an unverified entry). Each import rule is shown on it:
catalogued snippet-only records, unread licences and study-only geometry, the objective assessment with its neutral
role and nothing else of the map's verdicts, extensions of read sources, unverified entries left alone, the coverage
file's unposted drafts, project-neutral rewrites, determinism and idempotence."""
import copy
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from cadagent.review import references as refs

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("import_refmap", ROOT / "tools" / "import_refmap.py")
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)

CORE = {"schema": 1, "sources": [
    {"id": "maker-boss-guide", "title": "Boss Guide", "authors": [], "org": "Maker", "year": None,
     "url": "https://maker.example.org/boss-guide/", "access": "free", "terms": "cited and summarised, never copied",
     "areas": ["moulding"], "used_for": ["docs/page.md"], "verified": "2026-11-01: read the boss table"}],
    "unverified": [{"id": "gated-guide", "title": "Gated", "org": "Vendor", "why": "behind a form",
                    "url": "https://vendor.example.org/gated"}], "uncited": []}

DATA = {
    "CATS": {}, "DOMS": {"wheel": "Wheel-legged / balancing", "drive": "Gears / bearings"},
    "D": [
        ["Wheelbot", "https://github.com/someone/Wheel_Bot", "R", "wheel", "GPL-3.0", "V", "C",
         "Two-wheeled balancer with printed legs."],
        ["Gear paper: printed cycloidal drives", "https://arxiv.org/abs/0000.00000", "G", "drive", "paper", "-", "M",
         "Measured efficiency of printed cycloidal drives."],
        ["Tiny Gearbox", "https://github.com/other/tiny-gearbox", "C", "drive", "MIT", "N", "",
         "Gearbox generator; README contradicts our note."],
    ],
    "S": {"0": {"built": "works", "evid": "claimed", "supply": "commodity", "cost": "100to500", "make": "print",
                "docs": "guide", "role": "reference", "learn": "One specific thing a project can take.",
                "caveat": "No measured balance numbers.", "cq": {"size": "2 kg", "act": "two BLDC hub motors"},
                "src": "readme", "act": "active"}},
    "PT": {"0": ["print", "pcb"]},
    "PG": [
        {"title": "Snap Guide", "url": "https://shop.example.org/snap guide.pdf", "publisher": "Shop (Old Name)",
         "ptype": "service", "proc": ["snap-fit", "injection"], "authority": "primary", "numbers": "yes",
         "tested": "no", "cost": "no", "fit": "high", "gist": "Snap-fit strain limits.",
         "rule": "Allowable strain 4 % for PC", "note": "Numbers seen in a snippet only.",
         "chk": {"status": "corroborated", "evidence": "A second maker's table agrees."}, "grp": ["mould"]},
        {"title": "Boss Guide", "url": "https://www.maker.example.org/boss-guide", "publisher": "Maker",
         "ptype": "service", "proc": ["injection"], "authority": "primary", "numbers": "some", "tested": "unknown",
         "cost": "no", "fit": "medium", "gist": "Boss rules.", "rule": "Boss OD 2 d",
         "note": "Numbers not read in the snippet.", "grp": ["mould"]},
        {"title": "Gated", "url": "https://vendor.example.org/gated", "publisher": "Vendor", "ptype": "service",
         "proc": ["sheet"], "authority": "primary", "numbers": "unknown", "tested": "no", "cost": "no", "fit": "low",
         "gist": "Gated guide.", "rule": "", "note": "Title only.", "grp": ["sheet"]},
    ],
    "CA": [{"topic": "1 Heat-set insert hole", "status": "implemented", "where": "software/cadagent/mechanical/inserts.py",
            "defaults": "maker hole + 0.2", "source": "makers", "gap": "not by material",
            "issue_title": "Vary insert holes by material", "issue_body": "Add a table."}],
    "PR": {"mould": "Moulding and casting"},
    "PGAP": {"mould": "No gate sizing guide."},
}


@pytest.fixture()
def checkout(tmp_path, monkeypatch):
    # the real map's rewrites are keyed by its rows; the fixture's rows are other text, so they start with none
    monkeypatch.setattr(imp, "NEUTRAL", {})
    (tmp_path / "docs" / "research" / "references").mkdir(parents=True)
    shutil.copy(ROOT / "docs" / "areas.yaml", tmp_path / "docs" / "areas.yaml")
    shutil.copy(ROOT / "docs" / "research" / "references" / "vocab.yaml", tmp_path / "docs" / "research" / "references" / "vocab.yaml")
    (tmp_path / "docs" / "page.md").write_text("A boss rule.\n")
    (tmp_path / "docs" / "research" / "references.yaml").write_text(yaml.safe_dump(CORE, sort_keys=False))
    data = tmp_path / "data.json"
    data.write_text(json.dumps(DATA))
    return tmp_path, data


def _run(root, data, *extra):
    return imp.main([str(data), "--root", str(root), *extra])


def _records(root):
    out = {}
    for f in sorted((root / "docs" / "research" / "references").glob("*.yaml")):
        if f.name not in refs.NOT_SHARDS:
            for rec in yaml.safe_load(f.read_text())["sources"]:
                out[rec["id"]] = (f.name, rec)
    return out


def test_the_import_writes_shards_that_check_accepts(checkout, capsys):
    root, data = checkout
    assert _run(root, data) == 0
    out = capsys.readouterr().out
    assert "3 projects and 1 guides as catalogued records, 1 extensions of read sources, in 3 shards" in out
    assert "left as unverified in docs/research/references.yaml: gated-guide" in out
    names = sorted(p.name for p in (root / "docs" / "research" / "references").glob("*.yaml"))
    assert names == ["coverage.yaml", "guides-mould.yaml", "projects-drive.yaml", "projects-wheel.yaml",
                     "vocab.yaml"]
    reg = refs.load(root / "docs" / "research" / "references.yaml")
    assert not reg.problems(root), reg.problems(root)
    assert len(reg.of_kind("catalogued")) == 4 and reg.resolve("maker-boss-guide").kind == "source"


def test_every_new_record_is_catalogued_with_an_unread_licence(checkout):
    root, data = checkout
    _run(root, data)
    recs = {rid: rec for rid, (_, rec) in _records(root).items() if not rec.get("extends")}
    assert set(recs) == {"someone-wheel-bot", "gear-paper-printed-cycloidal-drives", "other-tiny-gearbox",
                         "shop-snap-guide"}
    for rec in recs.values():
        assert rec["evidence"]["class"] == "snippet-only" and rec["used_for"] == []
        assert rec["licence"]["read"] is False
        assert rec["confidence"] == {"level": "low", "estimate": 0.4, "sources": 1}
    wheel, paper, gearbox, snap = (recs[k] for k in ("someone-wheel-bot", "gear-paper-printed-cycloidal-drives",
                                                     "other-tiny-gearbox", "shop-snap-guide"))
    # licence class and geometry from the map's own rule: GPL is share-alike, so study-only
    assert wheel["licence"] == {"spdx": "GPL-3.0", "class": "share-alike", "read": False,
                                "note": "The map states 'GPL-3.0'; the licence text was not read."}
    assert wheel["reuse"] == {"text": "cite-only", "geometry": "study-only"}
    # an open licence may be adapted with credit, unless the project ships no CAD
    assert gearbox["licence"]["class"] == "open" and gearbox["reuse"]["geometry"] == "none"
    # a paper is a paper, licence unclear, no geometry
    assert (paper["kind"], paper["category"], paper["licence"]["class"], paper["reuse"]["geometry"]) == (
        "paper", "design-guides", "unclear", "none")
    assert paper["evidence"]["numbers"] == "measured" and wheel["evidence"]["numbers"] == "claimed"
    # guides: a publisher's page, cite-only; its rule is a claim with the map's corroboration; its note is kept
    assert snap["licence"]["class"] == "proprietary" and snap["reuse"]["geometry"] == "none"
    assert snap["claims"] == [{"text": "Allowable strain 4 % for PC", "status": "corroborated",
                               "evidence": "A second maker's table agrees."}]
    assert snap["summary"] == "Snap-fit strain limits. Note: Numbers seen in a snippet only."
    assert snap["evidence"] == {"class": "snippet-only", "numbers": "claimed", "tested": "no", "authority": "primary"}
    assert snap["url"] == "https://shop.example.org/snap%20guide.pdf" and snap["org"] == "Shop (Old Name)"
    assert snap["processes"] == ["snap-fit", "injection"] and snap["process_groups"] == ["mould"]
    assert snap["areas"] == ["snap-fits", "moulded-part-design"]


def test_a_project_keeps_the_objective_assessment_and_no_verdict_for_one_project(checkout):
    root, data = checkout
    _run(root, data)
    wheel = _records(root)["someone-wheel-bot"][1]
    assert wheel["assessment"] == {
        "built": "works", "supply": "commodity", "cost": "100to500", "make": "print", "docs": "guide",
        "activity": "active", "role": "reference", "cad": {"seen": "V"},
        "answers": {"size": "2 kg", "act": "two BLDC hub motors"}, "caveat": "No measured balance numbers.",
        "assessed": {"date": "2026-11-02", "from": "readme"}}
    assert wheel["areas"] == ["wheels-and-driving"] and wheel["domains"] == ["wheel"]
    assert wheel["process_groups"] == ["print", "pcb"]
    text = "".join(p.read_text() for p in (root / "docs" / "research" / "references").glob("*.yaml") if p.name != "vocab.yaml")
    assert "One specific thing" not in text and "\n  fit:" not in text and "    fit:" not in text   # learn, "fit for us"
    assert "learn" not in text and "\n  projects:" not in text and "    projects:" not in text
    gearbox = _records(root)["other-tiny-gearbox"][1]
    assert gearbox["summary"] == "Gearbox generator; README contradicts the summary."


def test_a_guide_already_read_extends_its_core_entry(checkout):
    root, data = checkout
    _run(root, data)
    name, ext = _records(root)["maker-boss-guide"]
    assert name == "guides-mould.yaml" and ext["extends"] is True and "class" not in ext["evidence"]
    ref = refs.load(root / "docs" / "research" / "references.yaml").resolve("maker-boss-guide")
    assert ref.evidence_class == "read" and ref["used_for"] == ["docs/page.md"]      # the core's reading stands
    assert ref["areas"] == ["moulding", "moulded-part-design"] and ref["claims"][0]["status"] == "unconfirmed"
    assert ref["title"] == "Boss Guide" and ref["verified"].startswith("2026-11-01")
    assert ref["summary"] == "Boss rules."          # the snippet's note would contradict the core's reading
    assert ref["claims"] == [{"text": "Boss OD 2 d", "status": "unconfirmed", "evidence": (
        "No second source checked. As the map saw it: Numbers not read in the snippet.")}]


@pytest.mark.parametrize("evidence, joined", [
    ("Two tests differ by", "Two tests differ by [cut off in the map]. As the map saw it: Snippet only."),
    ("Two tests agree.", "Two tests agree. As the map saw it: Snippet only."),
])
def test_evidence_the_map_cut_off_is_marked_before_its_note(monkeypatch, evidence, joined):
    monkeypatch.setattr(imp, "NEUTRAL", {})
    g = {"url": "https://example.com/g", "gist": "G.", "ptype": "guide", "proc": [], "rule": "R", "note": "Snippet only.",
         "numbers": next(iter(imp.NUMBERS)), "tested": False, "authority": "vendor",
         "chk": {"status": "conflicting", "evidence": evidence}}
    assert imp.guide_fields(0, g, {"process": {}}, notes=False)["claims"][0]["evidence"] == joined


def test_the_coverage_file_keeps_the_drafts_unposted(checkout):
    root, data = checkout
    _run(root, data)
    cov = yaml.safe_load((root / "docs" / "research" / "references" / "coverage.yaml").read_text())
    assert cov["rows"] == [{"id": "ca-1-heat-set-insert-hole", "number": "1", "topic": "Heat-set insert hole",
                            "status": "implemented", "areas": ["threaded-inserts"],
                            "where": "software/cadagent/mechanical/inserts.py", "defaults": "maker hole + 0.2",
                            "sources": "makers", "gap": "not by material",
                            "draft_issue": {"title": "Vary insert holes by material", "body": "Add a table.",
                                            "posted": False}}]
    assert cov["wanted"] == [{"group": "mould", "title": "Moulding and casting",
                              "areas": ["mould-design", "mould-making"], "text": "No gate sizing guide."}]
    reg = refs.load(root / "docs" / "research" / "references.yaml")
    assert reg.coverage == cov
    cov["rows"][0]["draft_issue"]["posted"] = True           # a boolean is an int in Python: still not an issue number
    cov["rows"][0]["status"] = "done"
    (root / "docs" / "research" / "references" / "coverage.yaml").write_text(yaml.safe_dump(cov))
    problems = "\n".join(refs.load(root / "docs" / "research" / "references.yaml").problems(root))
    assert "draft_issue needs a title and `posted: false`" in problems and "status 'done'" in problems


def test_the_import_is_deterministic_and_idempotent(checkout, capsys):
    root, data = checkout
    _run(root, data)
    first = {p.name: p.read_bytes() for p in (root / "docs" / "research" / "references").glob("*.yaml")}
    assert _run(root, data) == 0 and "wrote 0 files" in capsys.readouterr().out
    assert _run(root, data, "--check") == 0
    assert first == {p.name: p.read_bytes() for p in (root / "docs" / "research" / "references").glob("*.yaml")}
    shard = root / "docs" / "research" / "references" / "projects-wheel.yaml"
    changed = copy.deepcopy(DATA)
    changed["S"]["0"]["role"] = "leader"                                    # the map changes an untouched record
    data.write_text(json.dumps(changed))
    capsys.readouterr()
    assert _run(root, data, "--check") == 1
    assert "would change: docs/research/references/projects-wheel.yaml" in capsys.readouterr().out
    assert shard.read_bytes() == first["projects-wheel.yaml"]                 # --check writes nothing


def test_a_changed_row_under_a_neutral_rewrite_stops_the_import(checkout, monkeypatch):
    root, data = checkout
    monkeypatch.setitem(imp.NEUTRAL, ("S", "0", "caveat"), (imp.text_hash("No measured balance numbers."),
                                                             "No numbers."))
    monkeypatch.setitem(imp.NEUTRAL, ("PG", "0", "gist"), (imp.text_hash("Snap-fit strain limits."),
                                                            "Strain limits for snap fits."))
    _run(root, data)
    assert _records(root)["someone-wheel-bot"][1]["assessment"]["caveat"] == "No numbers."
    assert _records(root)["shop-snap-guide"][1]["summary"].startswith("Strain limits for snap fits.")
    changed = copy.deepcopy(DATA)
    changed["S"]["0"]["caveat"] = "No measured numbers, unlike some other robot."
    data.write_text(json.dumps(changed))
    with pytest.raises(SystemExit, match=r"S\[0\]\.caveat changed in the map"):
        _run(root, data)


def test_every_neutral_rewrite_names_no_project_and_keeps_none_of_the_maps_wording():
    tree = yaml.safe_load((ROOT / "docs" / "areas.yaml").read_text())
    names = [k for k in tree["projects"]] + [p["title"].lower() for p in tree["projects"].values()]
    for (_, _, _), (digest, ours) in imp.NEUTRAL.items():
        assert not any(n in ours.lower() for n in names) and "rs-04" not in ours.lower()
        assert "off-target" not in ours and "our " not in ours and "relevance" not in ours
        assert re.fullmatch(r"[0-9a-f]{16}", digest)              # a hash of the map's text, not the text
    source = (ROOT / "tools" / "import_refmap.py").read_text().lower()
    assert not any(n in source for n in names) and "rs-04" not in source


def test_a_hand_written_shard_is_never_the_imports(checkout, capsys):
    root, data = checkout
    _run(root, data)
    mine = root / "docs" / "research" / "references" / "guides-mould.yaml"
    hand = root / "docs" / "research" / "references" / "hand-picked.yaml"
    hand.write_text(yaml.safe_dump({"schema": 2, "sources": []}))
    mine.write_text(mine.read_text())
    capsys.readouterr()
    assert _run(root, data, "--check") == 0 and "hand-picked" not in capsys.readouterr().out
    assert _run(root, data) == 0 and hand.read_text() == yaml.safe_dump({"schema": 2, "sources": []})


@pytest.mark.parametrize("licence,cls", [("MIT", "open"), ("GPL-3.0", "copyleft"), ("CERN-OHL-S-2.0", "copyleft"),
                                         ("CC BY-NC-SA 4.0", "nc"), ("none stated", "unclear"),
                                         ("NOASSERTION", "unclear"), ("paper", ""), ("MIT / CERN-OHL-S-2.0 (conflict)",
                                                                                     "unclear"), ("-", "")])
def test_the_licence_classifier_is_the_maps(licence, cls):
    assert imp.lclass(licence) == cls


def test_ids_are_unique_and_kebab_case():
    ids = imp.Ids(["taken"])
    assert [ids("taken"), ids("taken"), ids("new")] == ["taken-2", "taken-3", "new"]
    assert imp.slug("Ball-Balancing-Robot: v2 & more!") == "ball-balancing-robot-v2-and-more"
    assert len(imp.slug("word " * 40)) <= 60 and imp.norm_url("https://www.X.org/a/") == imp.norm_url("http://x.org/a")


def _edit(root, shard, rid, fn):
    """Edit one record the way a tool does (load, change, dump in the importer's layout)."""
    f = root / "docs" / "research" / "references" / shard
    text = f.read_text()
    head = text.split("\nsources:\n", 1)[0] + "\nsources:\n"
    out = []
    for i, seg in imp.records_as_written(text):
        if i == rid:
            rec = yaml.safe_load(seg)[0]
            fn(rec)
            seg = imp.dump([rec])
        out.append(seg)
    f.write_text(head + "".join(out))


def _unconfirm(rec):                        # tools/references_health_apply.py: the corroborating page changed
    rec["claims"][0]["status"] = "unconfirmed"
    rec["claims"][0]["evidence"] += " 2026-11-16: the page of x changed; read it again."


def _move(rec):                             # tools/references_health_apply.py: a permanent move
    rec["mirrors"] = [rec["url"]]
    rec["url"] = "https://shop.example.org/new-snap-guide.pdf"


# Each edit, by a person or a tool, on a record the map makes; the map then changes that record's row.
EDITS = {
    "promotion": lambda r: r["evidence"].update({"class": "read"}),
    "summary fixed by hand, no verified": lambda r: r.update({"summary": "Snap-fit strain limits, fixed by hand."}),
    "claim withdrawn by the link check": _unconfirm,
    "url moved by the link check": _move,
}


@pytest.mark.parametrize("what", list(EDITS))
def test_a_reimport_keeps_every_edit_and_still_applies_the_map(checkout, capsys, what):
    """#343 review: the import owns its shards but never undoes an edit, by a person or a tool. An edited record, a
    hand-added one and a comment survive a second import byte for byte; a change in the map to a record nobody
    touched still lands."""
    root, data = checkout
    _run(root, data)
    mould = root / "docs" / "research" / "references" / "guides-mould.yaml"
    _edit(root, "guides-mould.yaml", "shop-snap-guide", EDITS[what])
    hand = ("# a person's note under the last record\n- id: hand-added-record   # written by a person\n"
            "  title: A Guide Read By Hand\n  summary: kept exactly, comment and all.\n")
    mould.write_text(mould.read_text() + hand)
    before = mould.read_text()
    capsys.readouterr()
    assert _run(root, data, "--check") == 0
    changed = copy.deepcopy(DATA)
    changed["PG"][0]["gist"] = "Snap-fit strain limits, revised."         # the edited record's row
    changed["PG"][0]["chk"]["evidence"] = "A third maker's table agrees."
    changed["D"][2][7] = "Gearbox generator, now with a test rig."        # a record nobody touched
    data.write_text(json.dumps(changed))
    assert _run(root, data) == 0
    out = capsys.readouterr().out
    kept = next(line for line in out.splitlines() if line.startswith("kept as written"))
    assert "shop-snap-guide" in kept and "other-tiny-gearbox" not in kept
    assert "not in the map, kept as written: hand-added-record" in out
    after = mould.read_text()
    assert after.split("sources:\n", 1)[1] == before.split("sources:\n", 1)[1]        # every record, byte for byte
    assert "revised" not in after and "third maker" not in after
    assert _records(root)["other-tiny-gearbox"][1]["summary"].startswith("Gearbox generator, now with a test rig.")
    assert _run(root, data, "--check") == 0


def test_every_written_record_carries_the_digest_of_its_text(checkout):
    root, data = checkout
    _run(root, data)
    for f in (root / "docs" / "research" / "references").glob("*.yaml"):
        if f.name not in refs.NOT_SHARDS:
            for rid, text in imp.records_as_written(f.read_text()):
                assert not imp.touched(text, None), rid
                assert imp.touched(text.replace("\n", "\n  # a comment\n", 1), None), rid
    reg = refs.load(root / "docs" / "research" / "references.yaml")
    assert not reg.problems(root), reg.problems(root)


def test_a_record_with_no_digest_is_the_maps_only_while_it_is_exactly_the_maps():
    rec = {"id": "x", "summary": "As the map has it.", "used_for": []}
    text = imp.dump([rec])
    assert not imp.touched(text, rec)
    assert imp.touched(text, {**rec, "summary": "The map changed."})
    assert imp.touched(imp.dump([{**rec, "confidence": {"level": "low"}, "summary": "edited"}]), rec)
