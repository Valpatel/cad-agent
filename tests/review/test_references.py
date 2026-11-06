"""The reference registry, docs/research/references.yaml (#118): every entry is well formed, every id the code cites
resolves, every file that cites an entry is in its used_for, and no source is vendored.

The checks run on the real registry and code, and on a planted checkout (tmp_path) with one mistake of each kind, so
each rule is shown to catch what it is for."""
import re
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

from cadagent.review import references as refs
from cadagent.review.references import Registry, check, citations, isbn_ok, load

ROOT = Path(__file__).resolve().parents[2]

# Code that cites an `unverified` entry: each is a source the code's author read but whose URL was not recorded or
# could not be found. The list only shrinks: record the URL, move the entry up to `sources`, and drop it here.
UNVERIFIED_CITED = {"goncalves", "pem-si", "ruthex-tip", "bossard-proof", "bossard-head", "vdi2230-friction"}


@pytest.fixture(scope="module")
def registry():
    return load()


def test_default_registry_requires_the_moved_source_despite_a_stale_old_copy(tmp_path, monkeypatch):
    content = refs.REGISTRY.read_bytes()
    current, stale = tmp_path / "docs/research/references.yaml", tmp_path / "research/references.yaml"
    for path in (current, stale):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    monkeypatch.setattr(refs, "ROOT", tmp_path)
    monkeypatch.setattr(refs, "REGISTRY", current)
    monkeypatch.chdir(tmp_path)
    assert load().core_file == "docs/research/references.yaml"
    current.unlink()
    with pytest.raises(FileNotFoundError, match="reference registry") as error:
        load()
    assert str(current) in str(error.value) and stale.exists()


def test_the_registry_is_well_formed(registry):
    problems = registry.problems(ROOT)
    assert not problems, "\n".join(problems)
    assert len(registry.of_kind("source")) >= 150


def test_every_cited_id_resolves_and_its_files_are_in_used_for(registry):
    problems, _ = check(ROOT, registry)
    assert not problems, "\n".join(problems)


def test_unverified_sources_the_code_cites_only_shrink(registry):
    _, warnings = check(ROOT, registry)
    cited = {w.split("cites '", 1)[1].split("'", 1)[0] for w in warnings}
    assert not cited - UNVERIFIED_CITED, f"code now cites unverified entries {sorted(cited - UNVERIFIED_CITED)}: " \
                                         "read them and move them up to `sources`"
    assert not UNVERIFIED_CITED - cited, f"{sorted(UNVERIFIED_CITED - cited)} no longer cited unverified: remove " \
                                         "them from UNVERIFIED_CITED"


def test_the_scan_finds_every_key_the_modules_define():
    """The AST scan must not miss a key the modules really use: compare it with the modules' own tables."""
    from cadagent.formulas import SOURCES
    from cadagent.manufacturing.process import FDM_MATERIALS
    from cadagent.mechanical import inserts, printed_joints
    from cadagent.simulation.fea import MATERIALS
    found = {c.key for c in citations(ROOT)}
    want = set(SOURCES) | set(inserts.sources()) | set(printed_joints.sources()) | \
        {m.source for m in MATERIALS.values() if m.source} | {source for _, source in FDM_MATERIALS.values()}
    assert not want - found, f"keys the scan misses: {sorted(want - found)}"
    pp = yaml.safe_load((ROOT / "docs" / "research" / "process-profiles.yaml").read_text(encoding="utf-8"))
    assert {r["source"] for r in pp["rules"] if not r["source"].startswith("dataset:")} <= found


def test_no_pdf_is_kept_in_the_repo():
    """Sources are cited, never copied: no data sheet, guide or standard is vendored as a PDF."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.pdf", "*.PDF"], capture_output=True, text=True,
                             check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    assert not out, f"PDFs in the repo: {out}; cite the source in docs/research/references.yaml instead"


def test_paid_and_print_sources_are_cited_not_copied(registry):
    for ref in registry.of_kind("source"):
        if ref["access"] in ("paid", "print"):
            assert "never copied" in ref["terms"] or "by number and title only" in ref["terms"], ref.id


def test_lookup_resolves_ids_and_aliases(registry):
    assert registry.resolve("covestro").id == "covestro-snapfit"
    assert registry.resolve("covestro-friction").id == "covestro-snapfit"
    assert registry.resolve("shigley-torque").id == registry.resolve("shigley").id == "shigley"
    assert registry.resolve("iso68").id == "iso-68-1"
    assert registry.resolve("judgement").kind == "uncited"
    assert registry.resolve("goncalves").kind == "unverified"
    with pytest.raises(KeyError, match="did you mean"):
        registry.resolve("covestro-snapfi")


def test_a_citation_names_the_people_and_the_link(registry):
    roark = registry.resolve("roark").citation()
    assert roark.startswith("Warren C. Young, Richard G. Budynas, Ali M. Sadegh, Roark's Formulas")
    assert "2012" in roark and roark.endswith("ISBN 978-0-07-174247-4")
    assert registry.resolve("covestro").citation() == (
        "Covestro LLC (formerly Bayer MaterialScience LLC), Snap-Fit Joints for Plastics - A Design Guide, n.d.: "
        "https://cdn.sparkfun.com/assets/home_page_posts/1/4/1/0/Plastic_Snap_fit_design.pdf")
    assert registry.resolve("goncalves").citation().endswith("(unverified)")
    assert "not an outside source (general)" in registry.resolve("lug-shear-out").citation()


def test_the_command_line(capsys):
    assert refs.main(["roark", "iso898"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("roark: Warren C. Young") and "iso898: ISO, ISO 898-1:2013" in out
    assert refs.main(["no-such-source"]) == 2
    assert refs.main([]) == 2                                   # nothing asked: usage, not a silent success
    capsys.readouterr()
    assert refs.main(["judgement"]) == 0
    assert capsys.readouterr().out.startswith("judgement: not an outside source (judgement): ")
    assert refs.main(["--check"]) == 0
    assert "0 problems" in capsys.readouterr().out


@pytest.mark.parametrize("isbn,ok", [("978-0-07-174247-4", True), ("978-1-111-57773-5", True),
                                      ("0-07-352935-4", True), ("978-0-07-174247-5", False), ("978-0-07-1742", False)])
def test_isbn_check_digits(isbn, ok):
    assert isbn_ok(isbn) is ok


# ----------------------------------------------------------------------------- planted mistakes

GOOD = {"id": "good-guide", "title": "A Guide", "authors": [], "org": "Maker", "year": 2020,
        "url": "https://example.org/guide", "access": "free", "terms": "cited and summarised, never copied",
        "areas": ["fdm"], "used_for": ["src/cadagent/mod.py"], "verified": "2026-11-01: read p. 2"}


def _planted(tmp_path: Path, sources, unverified=(), uncited=()) -> Path:
    (tmp_path / "docs" / "research").mkdir(parents=True)
    (tmp_path / "src" / "cadagent").mkdir(parents=True)
    (tmp_path / "src" / "cadagent" / "mod.py").write_text(textwrap.dedent('''
        SRC = {"good-guide": "Maker, A Guide, p. 2", "gone": "nowhere"}
        x = cite("good-guide", "p. 3")
        m = Material("PLA", 1, 0.3, 1, 1, source="good-guide")
        FDM_MATERIALS = {"pla-maker": ("pla", "good-guide"), "odd": ("pla", 3)}
    '''))
    (tmp_path / "docs" / "page.md").write_text("A rule [ref:good-guide] and one [ref:elsewhere]; the syntax is "
                                               "[ref:<id>].\n")
    (tmp_path / "README.md").write_text("Top level: [ref:good-guide].\n")
    (tmp_path / "CHANGELOG.md").write_text("Released notes quote a tag as text: [ref:not-scanned].\n")
    (tmp_path / "docs" / "research" / "process-profiles.yaml").write_text(yaml.safe_dump({
        "rules": [{"id": "fdm-wall-maker", "source": "good-guide"}, {"id": "fdm-x", "source": "dataset:tds"}],
        "datasets": [{"id": "tds", "cites": "prose, not an id"}]}))
    (tmp_path / "docs" / "research" / "references.yaml").write_text(yaml.safe_dump(
        {"schema": 1, "sources": list(sources), "unverified": list(unverified), "uncited": list(uncited)}))
    return tmp_path


def test_the_scan_reads_each_way_of_citing(tmp_path):
    root = _planted(tmp_path, [GOOD])
    found = {(c.key, c.path, c.how) for c in citations(root)}
    assert found == {("good-guide", "src/cadagent/mod.py", "table"), ("gone", "src/cadagent/mod.py", "table"),
                     ("good-guide", "src/cadagent/mod.py", "cite"), ("good-guide", "src/cadagent/mod.py", "material"),
                     ("good-guide", "src/cadagent/mod.py", "row"),
                     ("good-guide", "docs/page.md", "tag"), ("elsewhere", "docs/page.md", "tag"),
                     ("good-guide", "README.md", "tag"),
                     ("good-guide", "docs/research/process-profiles.yaml", "process-profile")}


def test_check_reports_unknown_keys_and_missing_used_for(tmp_path):
    root = _planted(tmp_path, [GOOD])
    problems, warnings = check(root)
    assert any("cites 'gone'" in p for p in problems) and any("cites 'elsewhere'" in p for p in problems)
    assert any("add docs/page.md to used_for of good-guide" in p for p in problems)
    assert any("add README.md to used_for of good-guide" in p for p in problems)
    assert any("add docs/research/process-profiles.yaml to used_for" in p for p in problems)
    assert not any("src/cadagent/mod.py to used_for" in p for p in problems) and not warnings


def test_check_warns_on_code_citing_an_unverified_entry(tmp_path):
    root = _planted(tmp_path, [{**GOOD, "used_for": ["src/cadagent/mod.py", "docs/page.md", "README.md#top",
                                                     "docs/research/process-profiles.yaml"]}],
                    unverified=[{"id": "gone", "title": "Lost", "org": "Maker", "why": "no URL recorded",
                                 "used_for": ["src/cadagent/mod.py"]}],
                    uncited=[{"id": "elsewhere", "kind": "general", "note": "common knowledge"}])
    problems, warnings = check(root)
    assert not problems and warnings == ["src/cadagent/mod.py:2: cites 'gone', an unverified entry (no URL recorded)"]


@pytest.mark.parametrize("change,message", [
    ({"title": ""}, "no title"),
    ({"org": "", "authors": []}, "no author and no publisher"),
    ({"url": None}, "no url and no isbn"),
    ({"url": "http://example.org"}, "not an https link"),
    ({"isbn": "978-0-07-174247-5", "url": None}, "bad check digit"),
    ({"access": "print", "url": None, "isbn": None}, "a print source needs its isbn"),
    ({"year": None, "access": "paid"}, "only for an undated web page"),
    ({"year": 3020}, "is not a year"),
    ({"terms": "use freely"}, "terms must say it is cited"),
    ({"terms": "cited"}, "terms must say it is cited"),
    ({"verified": "read it"}, "verified must start with the ISO date"),
    ({"used_for": ["src/missing.py"]}, "is not a file or folder"),
    ({"access": "online"}, "access 'online'"),
    ({"id": "Bad_Id"}, "not a kebab-case key"),
    ({"aliases": ["good-guide"]}, "used twice"),
    ({"aliases": "gg"}, "aliases must be a list"),
    ({"aliases": ["Good Guide"]}, "aliases must be a list"),
])
def test_each_malformed_entry_is_reported(tmp_path, change, message):
    entry = {**GOOD, **change}
    if "year" in change and change["year"] is None:
        entry["year"] = None
    root = _planted(tmp_path, [entry])
    problems = load(root / "docs" / "research" / "references.yaml").problems(root)
    assert any(message in p for p in problems), problems
    assert not Registry({"schema": 1, "sources": [GOOD]}).problems(root)


def test_uncited_and_unverified_entries_are_checked_too(tmp_path):
    root = _planted(tmp_path, [GOOD], unverified=[{"id": "lost", "title": "Lost", "org": "Maker"}],
                    uncited=[{"id": "mine", "kind": "hunch", "note": ""},
                             {"id": "inner", "kind": "internal", "note": "a module", "cites": ["lost"]}])
    problems = "\n".join(load(root / "docs" / "research" / "references.yaml").problems(root))
    assert "lost: an unverified entry needs `why`" in problems
    assert "mine: kind 'hunch'" in problems and "mine: no note" in problems
    assert "inner: cites 'lost', which is not a read source" in problems
    assert "inner: an internal key needs `where`" in problems


def test_used_for_may_name_a_folder_or_an_anchor(tmp_path):
    root = _planted(tmp_path, [{**GOOD, "used_for": ["src/cadagent", "docs/page.md#rules", "README.md",
                                                     "docs/research/process-profiles.yaml"]}],
                    unverified=[{"id": "gone", "title": "Lost", "org": "Maker", "why": "no URL", "used_for": ["src/"]}],
                    uncited=[{"id": "elsewhere", "kind": "general", "note": "common knowledge"}])
    problems, _ = check(root)
    assert not problems, problems
    assert refs.lists(["src/cadagent"], "src/cadagent/mod.py") and not refs.lists(["src/cad"], "src/cadagent/mod.py")
    assert not refs.lists(["proposed: src/cadagent/mod.py"], "src/cadagent/mod.py")


def test_a_malformed_tag_is_reported_not_skipped(tmp_path):
    root = _planted(tmp_path, [{**GOOD, "used_for": ["src", "docs", "README.md", "docs/research"]}],
                    unverified=[{"id": "gone", "title": "Lost", "org": "Maker", "why": "no URL", "used_for": ["src"]}],
                    uncited=[{"id": "elsewhere", "kind": "general", "note": "common knowledge"}])
    (root / "docs" / "bad.md").write_text("[ref:Covestro] [ref: good-guide] [ref:a, b] [ref:a_b] [ref:<key>]\n")
    problems, _ = check(root)
    bad = sorted(p.split("[ref:", 1)[1].split("]", 1)[0] for p in problems if "is not a tag" in p)
    assert bad == [" good-guide", "Covestro", "a, b", "a_b"], problems


def test_an_alias_that_names_another_entry_is_caught_in_either_order(tmp_path):
    other = {**GOOD, "id": "other-guide"}
    for sources in ([{**GOOD, "aliases": ["other-guide"]}, other], [other, {**GOOD, "aliases": ["other-guide"]}]):
        reg = Registry({"schema": 1, "sources": sources})
        assert reg.resolve("other-guide").id == "other-guide"
        assert any("other-guide: the id or alias is used twice" in p for p in reg.problems(tmp_path))


# ----------------------------------------------------------------------------- schema 2: shards (#323)

TREE = {"projects": {"demo-bot": {"title": "Demo bot", "url": "https://example.org/demo-bot"}},
        "domains": [{"slug": "mechanical", "areas": [
            {"slug": "fasteners-and-hardware", "topics": [{"slug": "threaded-inserts"}]},
            {"slug": "walking", "topics": [{"slug": "five-bar-legs"}]}]}]}
TERMS = "cited and summarised, never copied"
GUIDE = {"id": "maker-insert-guide", "kind": "guide", "title": "Insert guide", "authors": [], "org": "Maker",
         "year": None, "url": "https://example.org/inserts", "access": "free", "terms": TERMS,
         "licence": {"spdx": None, "class": "proprietary", "read": False, "note": ""},
         "reuse": {"text": "cite-only", "geometry": "none"}, "areas": ["threaded-inserts"],
         "processes": ["inserts"], "process_groups": ["inserts"],
         "evidence": {"class": "snippet-only", "numbers": "claimed", "tested": "no", "authority": "primary"},
         "claims": [{"text": "M3 insert hole 4.0 mm", "status": "unconfirmed", "evidence": ""}],
         "used_for": [], "summary": "Hole sizes for heat-set inserts."}
PROJECT = {"id": "demo-walker", "kind": "project", "category": "robots", "title": "demo-walker", "authors": [],
           "org": "someone", "year": None, "url": "https://github.com/someone/demo-walker", "access": "free",
           "terms": TERMS, "licence": {"spdx": "GPL-3.0", "class": "share-alike", "read": False, "note": ""},
           "reuse": {"text": "cite-only", "geometry": "study-only"}, "areas": ["walking", "walking/five-bar-legs"],
           "domains": ["legged"], "process_groups": ["print"], "evidence": {"class": "snippet-only", "numbers": "none"},
           "assessment": {"built": "works", "supply": "commodity", "cost": "100to500", "make": "print",
                          "docs": "guide", "activity": "active", "role": "reference",
                          "cad": {"seen": "V", "formats": ["step"]}, "answers": {"size": "12 DOF, 1.2 kg"},
                          "caveat": "No test data.", "assessed": {"date": "2026-11-02", "from": "readme"}},
           "projects": {"demo-bot": ["leg-fivebar"]}, "used_for": []}


def _shard(records, **extra):
    return {"schema": 2, "sources": list(records), **extra}


def _planted2(tmp_path: Path, shards, sources=(GOOD,), vocab=True) -> Path:
    """A planted checkout with the core registry, docs/areas.yaml, the real vocab.yaml and the given shards."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = _planted(tmp_path, list(sources))
    (root / "docs" / "areas.yaml").write_text(yaml.safe_dump(TREE))
    folder = root / "docs" / "research" / "references"
    folder.mkdir()
    if vocab:
        (folder / "vocab.yaml").write_text((ROOT / "docs" / "research" / "references" / "vocab.yaml").read_text())
    for name, data in shards.items():
        (folder / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    return root


def _problems(root: Path):
    return load(root / "docs" / "research" / "references.yaml").problems(root)


def test_the_loader_merges_the_core_file_and_every_shard(tmp_path):
    root = _planted2(tmp_path, {"guides-inserts": _shard([GUIDE]), "projects-legged": _shard([PROJECT])})
    reg = load(root / "docs" / "research" / "references.yaml")
    assert [s.file for s in reg.shards] == ["docs/research/references/guides-inserts.yaml",
                                            "docs/research/references/projects-legged.yaml"]
    assert set(reg.entries) == {"good-guide", "maker-insert-guide", "demo-walker"}
    assert reg.resolve("good-guide").file == "docs/research/references.yaml"
    guide = reg.resolve("maker-insert-guide")
    assert (guide.kind, guide.file, guide.evidence_class) == (
        "catalogued", "docs/research/references/guides-inserts.yaml", "snippet-only")
    assert guide.citation() == "Maker, Insert guide, n.d.: https://example.org/inserts (snippet-only)"
    assert reg.resolve("good-guide").evidence_class == "read"        # a core source: its `verified` note is the read
    assert {r.id for r in reg.of_kind("catalogued")} == {"maker-insert-guide", "demo-walker"}
    assert not _problems(root), _problems(root)
    problems, _ = check(root)          # the planted pages cite on purpose; none of them cites a shard record
    assert not [p for p in problems if "maker-insert-guide" in p or "demo-walker" in p], problems


def test_the_real_registry_loads_its_shard_folder():
    reg = load()
    assert reg.vocab and reg.vocab["schema"] == 2 and tuple(reg.vocab["evidence_class"]) == refs.LADDER
    assert all(s.file.startswith("docs/research/references/") for s in reg.shards)
    for shard in reg.shards:
        assert len(shard.records) <= refs.SHARD_LIMIT and shard.size <= refs.SHARD_BYTES, shard.file


def test_an_id_in_two_files_is_reported(tmp_path):
    root = _planted2(tmp_path, {"guides-a": _shard([GUIDE]), "guides-b": _shard([{**GUIDE, "title": "Again"}]),
                                "guides-c": _shard([{**GUIDE, "id": "good-guide"}])})
    problems = "\n".join(_problems(root))
    assert "maker-insert-guide: the id or alias is used twice" in problems
    assert "maker-insert-guide: in docs/research/references/guides-b.yaml and in docs/research/references/guides-a.yaml" in problems
    assert "good-guide: in docs/research/references/guides-c.yaml and in docs/research/references.yaml" in problems
    assert "write `extends: true`" in problems


def test_extends_adds_schema2_fields_to_a_core_entry(tmp_path):
    ext = {"id": "good-guide", "extends": True, "kind": "guide", "used_for": ["docs/page.md", "src/cadagent/mod.py"],
           "areas": ["threaded-inserts"], "evidence": {"numbers": "claimed", "authority": "primary"},
           "claims": [{"text": "wall 1.2 mm", "status": "unconfirmed"}]}
    root = _planted2(tmp_path, {"guides-inserts": _shard([ext])})
    reg = load(root / "docs" / "research" / "references.yaml")
    ref = reg.resolve("good-guide")
    assert ref.file == "docs/research/references.yaml" and ref.kind == "source" and ref.evidence_class == "read"
    assert ref["used_for"] == ["src/cadagent/mod.py", "docs/page.md"]          # united, the core's order first
    assert ref["areas"] == ["fdm", "threaded-inserts"] and ref["kind"] == "guide" and ref["claims"]
    assert not _problems(root), _problems(root)
    # an extension changes nothing the core says, extends only what exists, and only once
    root2 = _planted2(tmp_path / "b", {"g1": _shard([{**ext, "title": "Other title"},
                                                     {**ext, "id": "nowhere"}]), "g2": _shard([ext])})
    problems = "\n".join(_problems(root2))
    assert "good-guide: docs/research/references/g1.yaml sets title to 'Other title'" in problems
    assert "nowhere: docs/research/references/g1.yaml extends it, but docs/research/references.yaml has no such entry" in problems
    assert "good-guide: extended twice, in docs/research/references/g1.yaml and docs/research/references/g2.yaml" in problems
    # only a read source takes schema-2 fields: an unverified key is read and moved up first
    root3 = _planted2(tmp_path / "c", {"g1": _shard([{"id": "lost", "extends": True,
                                                      "evidence": {"class": "measured"}}])},
                      )
    (root3 / "docs" / "research" / "references.yaml").write_text(yaml.safe_dump({"schema": 1, "sources": [GOOD], "unverified": [
        {"id": "lost", "title": "Lost", "org": "Maker", "why": "no URL"}]}))
    problems = _problems(root3)
    assert any("lost: docs/research/references/g1.yaml extends it, but it is unverified" in p for p in problems), problems
    assert load(root3 / "docs" / "research" / "references.yaml").resolve("lost").get("evidence") is None
    # a field an extension gets wrong is reported once, not once as written and once as merged
    root4 = _planted2(tmp_path / "d", {"g1": _shard([{**ext, "kind": "blogpost"}])})
    assert sum("kind 'blogpost'" in p for p in _problems(root4)) == 1


def test_a_shard_over_the_limit_is_split_by_topic(tmp_path, monkeypatch):
    many = [{**GUIDE, "id": f"guide-{i}"} for i in range(refs.SHARD_LIMIT + 1)]
    root = _planted2(tmp_path, {"guides-inserts": _shard(many), "guides-ok": _shard([GUIDE])})
    over = [p for p in _problems(root) if "over the shard limit" in p]
    assert len(over) == 1 and over[0].startswith(f"docs/research/references/guides-inserts.yaml: {refs.SHARD_LIMIT + 1} "
                                                 "records") and "split by topic slug" in over[0]
    monkeypatch.setattr(refs, "SHARD_BYTES", 500)          # the byte limit, on a shard under the record limit
    assert any("guides-ok.yaml: 1 records" in p and "split by topic slug" in p for p in _problems(root))


def test_a_shard_file_is_checked(tmp_path):
    root = _planted2(tmp_path, {"Bad_Name": _shard([GUIDE]), "guides-v1": {"schema": 1, "sources": [], "extra": 1},
                                "guides-none": {"schema": 2}})
    problems = "\n".join(_problems(root))
    assert "Bad_Name.yaml: a shard's file name is a kebab-case slug" in problems
    assert "guides-v1.yaml: schema is 1, not 2" in problems and "unknown top-level keys ['extra']" in problems
    assert "guides-none.yaml: no `sources:` list" in problems


@pytest.mark.parametrize("record,change,message", [
    (GUIDE, {"kind": "blogpost"}, "kind 'blogpost' is not in vocab.yaml `kind`"),
    (GUIDE, {"licence": {"class": "copyleft", "read": False}}, "licence.class 'copyleft' is not in vocab.yaml"),
    (GUIDE, {"licence": {"class": "open"}}, "licence.read must be true or false"),
    (GUIDE, {"evidence": {"class": "skimmed"}}, "evidence.class 'skimmed' is not in vocab.yaml `evidence_class`"),
    (GUIDE, {"evidence": {"class": "snippet-only", "numbers": "yes"}}, "evidence.numbers 'yes' is not in vocab.yaml"),
    (GUIDE, {"evidence": {"class": "snippet-only", "authority": "maker"}}, "evidence.authority 'maker'"),
    (GUIDE, {"evidence": {"class": "snippet-only", "tested": True}}, "evidence.tested is the YAML boolean True"),
    (GUIDE, {"kind": None}, "no kind"),
    (GUIDE, {"evidence": {"numbers": "none"}}, "no evidence.class"),
    (GUIDE, {"areas": []}, "no areas: place the record in docs/areas.yaml"),
    (GUIDE, {"areas": ["inserts"]}, "area 'inserts' is not an area or topic slug of docs/areas.yaml"),
    (GUIDE, {"areas": ["walking/threaded-inserts"]}, "area 'walking/threaded-inserts' is not an area or topic"),
    (GUIDE, {"processes": ["3d-print"]}, "processes '3d-print' is not in vocab.yaml `process`"),
    (GUIDE, {"process_groups": "print"}, "process_groups must be a list"),
    (GUIDE, {"claims": [{"text": "x", "status": "maybe"}]}, "claims[0].status 'maybe' is not in vocab.yaml"),
    (GUIDE, {"claims": [{"status": "unconfirmed"}]}, "claims[0] needs text"),
    (GUIDE, {"claims": [{"text": "x", "status": "corroborated", "corroborated_by": ["nobody"]}]},
     "claims[0].corroborated_by 'nobody' is not a record id"),
    (GUIDE, {"claims": [{"text": "x", "status": "corroborated", "corroborated_by": ["maker-insert-guide"]}]},
     "claims[0] is corroborated by itself"),
    (GUIDE, {"health": {"status": "ok"}}, "`health` is not kept in git"),
    (GUIDE, {"verifed": "2026-11-01"}, "unknown fields ['verifed']"),
    (GUIDE, {"extends": "good-guide"}, "extends must be `true`"),
    (GUIDE, {"mirrors": ["http://example.org/copy"]}, "is not an https link (mirrors are public copies"),
    (GUIDE, {"archive": {"kind": "pdf", "path": "/srv/x.pdf"}}, "archive needs the sha256"),
    (GUIDE, {"archive": {"sha256": "0" * 64, "kind": "pdf"}}, "archive.redistribute must be true or false"),
    (GUIDE, {"rules": ["no-such-rule"]}, "rule 'no-such-rule' is not a rule id"),
    (GUIDE, {"checks": ["check_joint"]}, "check 'check_joint' is not a dotted cadagent name"),
    (PROJECT, {"assessment": {**PROJECT["assessment"], "role": "favourite"}}, "assessment.role 'favourite'"),
    (PROJECT, {"assessment": {**PROJECT["assessment"], "cad": {"seen": "Y"}}}, "assessment.cad.seen 'Y'"),
    (PROJECT, {"assessment": {**PROJECT["assessment"], "answers": {"speed": "fast"}}},
     "assessment.answers key 'speed' is not in vocab.yaml `answer`"),
    (PROJECT, {"assessment": {**PROJECT["assessment"], "assessed": {"date": "soon"}}}, "assessed.date must be an ISO"),
    (PROJECT, {"domains": ["walker"]}, "domains 'walker' is not in vocab.yaml `domain`"),
    (PROJECT, {"category": "R"}, "category 'R' is not in vocab.yaml `category`"),
    (PROJECT, {"projects": {"other-bot": ["leg"]}}, "projects key 'other-bot' is not in the projects table"),
    (PROJECT, {"projects": {"demo-bot": "leg"}}, "projects.demo-bot must be a list of kebab-case mechanism slugs"),
    (PROJECT, {"reuse": {"text": "cite-only", "geometry": "adapt-with-attribution"}},
     "licence class share-alike makes geometry study-only"),
    (PROJECT, {"reuse": {"text": "cite-only"}}, "a project needs reuse.geometry"),
    (PROJECT, {"licence": {"class": "open", "read": False}, "reuse": {"text": "cite-only", "geometry": "copy"}},
     "reuse.geometry copy needs licence.read: true"),
])
def test_each_schema2_mistake_is_reported(tmp_path, record, change, message):
    root = _planted2(tmp_path, {"shard-a": _shard([{**record, **change}])})
    problems = _problems(root)
    assert any(message in p for p in problems), problems
    clean = _planted2(tmp_path / "clean", {"shard-a": _shard([record])})
    assert not _problems(clean), _problems(clean)


def test_open_geometry_may_be_copied_once_the_licence_is_read(tmp_path):
    ok = {**PROJECT, "licence": {"spdx": "MIT", "class": "open", "read": True, "note": "LICENSE read 2026-11-02"},
          "reuse": {"text": "cite-only", "geometry": "copy"}}
    assert not _problems(_planted2(tmp_path, {"projects-legged": _shard([ok])}))


def test_the_vocabulary_file_is_checked(tmp_path):
    assert not [p for p in load().problems(ROOT) if "vocab.yaml" in p]
    root = _planted2(tmp_path, {"guides-inserts": _shard([GUIDE])}, vocab=False)
    assert any("docs/research/references/vocab.yaml is missing" in p for p in _problems(root))
    vocab = yaml.safe_load((ROOT / "docs" / "research" / "references" / "vocab.yaml").read_text())
    ladder = dict(reversed(list(vocab["evidence_class"].items())))
    del vocab["role"]
    vocab["confidence"]["high"]["estimate"] = 0.95
    vocab["study_only"] = ["copyleft"]
    vocab["process"]["fdm"]["group"] = "printing"
    (root / "docs" / "research" / "references" / "vocab.yaml").write_text(yaml.safe_dump({**vocab, "evidence_class": ladder}))
    problems = "\n".join(_problems(root))
    for message in ("no `role` vocabulary", "but the code's ladder is", "confidence levels and estimates must be",
                    "study_only must list licence classes", "process fdm names no process_group"):
        assert message in problems, message


def test_the_vocabularies_name_no_project():
    """cad-agent stays general purpose: the vocabularies are objective and name no project (the `projects` join of a
    record is keyed by docs/areas.yaml, never by vocab.yaml), and the map's per-project `learn` notes are not kept."""
    text = (ROOT / "docs" / "research" / "references" / "vocab.yaml").read_text().lower()
    tree = yaml.safe_load((ROOT / "docs" / "areas.yaml").read_text())
    for key, project in tree["projects"].items():
        assert key not in text and project["title"].lower() not in text, key
    vocab = yaml.safe_load(text)
    assert "learn" not in vocab and set(vocab["role"]) == {"leader", "reference", "lessons", "context"}


# ----------------------------------------------------------------------------- the evidence-class citation rule

def test_a_catalogued_record_backs_no_rule_check_or_page(tmp_path):
    root = _planted2(tmp_path, {"guides-inserts": _shard([GUIDE])},
                     sources=[{**GOOD, "used_for": ["src", "docs", "README.md", "docs/research"]}])
    (root / "src" / "cadagent" / "uses.py").write_text('SRC = {"maker-insert-guide": "p. 1"}\n')
    (root / "docs" / "rule.md").write_text("Insert holes are 4.0 mm [ref:maker-insert-guide].\n")
    (root / "docs" / "research" / "survey.md").write_text("Also seen: [ref:maker-insert-guide].\n")
    pp = yaml.safe_load((root / "docs" / "research" / "process-profiles.yaml").read_text())
    pp["rules"].append({"id": "insert-hole", "source": "maker-insert-guide"})
    (root / "docs" / "research" / "process-profiles.yaml").write_text(yaml.safe_dump(pp))
    problems, warnings = check(root)
    bad = sorted(p.split(":", 1)[0] for p in problems if "a snippet-only record: a rule, check or page" in p)
    assert set(bad) == {"docs/rule.md", "docs/research/process-profiles.yaml", "src/cadagent/uses.py"} and len(bad) == 3, problems
    assert [w for w in warnings if "maker-insert-guide" in w] == [
        "docs/research/survey.md:1: cites 'maker-insert-guide', a snippet-only record (listed, not read)"]


def test_a_read_shard_record_may_be_cited(tmp_path):
    read = {**GUIDE, "evidence": {**GUIDE["evidence"], "class": "read"}, "used_for": ["docs/rule.md"],
            "verified": "2026-11-02: opened the page; read the M3 row of the hole table"}
    root = _planted2(tmp_path, {"guides-inserts": _shard([read])},
                     sources=[{**GOOD, "used_for": ["src", "docs", "README.md", "docs/research"]}])
    (root / "docs" / "rule.md").write_text("Insert holes are 4.0 mm [ref:maker-insert-guide].\n")
    reg = load(root / "docs" / "research" / "references.yaml")
    assert reg.resolve("maker-insert-guide").kind == "source"
    problems, _ = check(root)
    assert not [p for p in problems if "maker-insert-guide" in p], problems


@pytest.mark.parametrize("change,message", [
    ({"evidence": {"class": "read"}}, "evidence class read needs `verified`"),
    ({"evidence": {"class": "verified-at-source"}, "verified": "2026-11-02: read"},
     "evidence class verified-at-source needs a claim corroborated_by another record"),
    ({"used_for": ["src/cadagent/mod.py"]}, "a snippet-only record backs nothing outside docs/research/"),
    ({"checks": ["inserts.check_joint"]}, "a snippet-only record may not back a rule or a check"),
])
def test_the_ladder_rules(tmp_path, change, message):
    root = _planted2(tmp_path, {"guides-inserts": _shard([{**GUIDE, **change}])})
    assert any(message in p for p in _problems(root)), _problems(root)


def test_an_encoded_secondary_source_needs_a_second_record_and_a_primary_one_may_stand_alone(tmp_path):
    enc = {**GUIDE, "verified": "2026-11-02: read", "checks": ["inserts.check_joint"], "used_for": [],
           "evidence": {"class": "encoded", "authority": "primary"}}
    root = _planted2(tmp_path, {"guides-inserts": _shard([enc])})
    assert not [p for p in _problems(root) if "corroborated_by" in p], _problems(root)
    root = _planted2(tmp_path / "b", {"guides-inserts": _shard([{**enc, "evidence": {"class": "encoded",
                                                                                     "authority": "reference"}}])})
    assert any("evidence class encoded needs a claim corroborated_by another record" in p for p in _problems(root))


def test_an_encoded_record_names_what_encodes_it(tmp_path):
    other = {**GUIDE, "id": "lab-insert-test", "org": "A Lab", "used_for": [],
             "evidence": {"class": "read", "authority": "independent-tested"}, "verified": "2026-11-02: read"}
    enc = {**GUIDE, "verified": "2026-11-02: read", "evidence": {"class": "encoded", "authority": "primary"},
           "claims": [{"text": "M3 hole 4.0 mm", "status": "corroborated", "corroborated_by": ["lab-insert-test"]}]}
    root = _planted2(tmp_path, {"guides-inserts": _shard([enc, other])})
    assert any("evidence class encoded needs `rules` or `checks`" in p for p in _problems(root))


def test_a_core_entry_is_never_snippet_only(tmp_path):
    root = _planted2(tmp_path, {}, sources=[{**GOOD, "kind": "guide", "evidence": {"class": "snippet-only"}}])
    assert any("good-guide: a core entry is read" in p for p in _problems(root))


# ----------------------------------------------------------------------------- derived confidence (#143)

def _conf_registry(main, *others):
    return Registry({"schema": 1, "sources": [GOOD]},
                    shards=[refs.Shard("docs/research/references/s.yaml", _shard([main, *others]))],
                    vocab=yaml.safe_load((ROOT / "docs" / "research" / "references" / "vocab.yaml").read_text()))


def _rec(rid, cls, org="Maker", authority="primary", by=(), status="corroborated"):
    rec = {**GUIDE, "id": rid, "org": org, "evidence": {"class": cls, "authority": authority},
           "verified": "2026-11-02: read", "claims": [{"text": "M3 hole 4.0 mm", "status": status,
                                                       "corroborated_by": list(by)}]}
    return rec


LAB_READ = _rec("lab-read", "read", org="Lab", authority="independent-tested")
LAB_VERIFIED = _rec("lab-verified", "verified-at-source", org="Lab", by=["good-guide"])
SAME_ORG = _rec("maker-other", "read")
SNIPPET = _rec("lab-snippet", "snippet-only", org="Lab")


@pytest.mark.parametrize("main,others,want", [
    # not assessed: a core source with no evidence block, as every one is today
    (None, (), ("unknown", None, 0)),
    # a search snippet, whatever its authority
    (_rec("m", "snippet-only", authority="independent-tested"), (), ("low", 0.4, 1)),
    # one read primary source, examples not reproduced
    (_rec("m", "read"), (), ("low", 0.4, 1)),
    # one read primary source whose examples tests reproduce
    (_rec("m", "encoded"), (), ("medium", 0.7, 1)),
    # a secondary source reproduced is still one secondary source
    (_rec("m", "encoded", authority="reference"), (), ("low", 0.4, 1)),
    # two agreeing sources, independent and read
    (_rec("m", "read", authority="reference", by=["lab-read"]), (LAB_READ,), ("medium", 0.7, 2)),
    # the same publisher twice is one source
    (_rec("m", "read", by=["maker-other"]), (SAME_ORG,), ("low", 0.4, 1)),
    # a snippet corroborates nothing
    (_rec("m", "read", by=["lab-snippet"]), (SNIPPET,), ("low", 0.4, 1)),
    # a claim not marked corroborated counts nothing, whatever it lists
    (_rec("m", "read", by=["lab-read"], status="unconfirmed"), (LAB_READ,), ("low", 0.4, 1)),
    # reproduced, and corroborated by an independent record checked at source: high
    (_rec("m", "encoded", by=["lab-verified"]), (LAB_VERIFIED,), ("high", 0.9, 2)),
    # reproduced, corroborated by a record only read: medium
    (_rec("m", "encoded", authority="reference", by=["lab-read"]), (LAB_READ,), ("medium", 0.7, 2)),
    # each corroborator counted once, the same-publisher one not at all
    (_rec("m", "measured", by=["lab-verified", "lab-verified", "maker-other"]), (LAB_VERIFIED, SAME_ORG),
     ("high", 0.9, 2)),
])
def test_confidence_golden_cases(main, others, want):
    if main is None:
        reg = Registry({"schema": 1, "sources": [GOOD]})
        ref = reg.resolve("good-guide")
    else:
        reg = _conf_registry(main, *others)
        ref = reg.resolve(main["id"])
    got = refs.confidence(ref, reg)
    assert (got["level"], got["estimate"], got["sources"]) == want


def test_a_stored_confidence_must_equal_the_derived_one(tmp_path):
    good = {**GUIDE, "confidence": {"level": "low", "estimate": 0.4, "sources": 1}}
    assert not _problems(_planted2(tmp_path, {"guides-inserts": _shard([good])}))
    typed = {**GUIDE, "confidence": {"level": "high", "estimate": 0.9, "sources": 1}}
    problems = _problems(_planted2(tmp_path / "b", {"guides-inserts": _shard([typed])}))
    assert any("is not the derived {'level': 'low', 'estimate': 0.4, 'sources': 1}" in p for p in problems), problems


# ----------------------------------------------------------------------------- the imported map (#323 phase 2)

def test_the_imported_records_are_catalogued_and_project_neutral(registry):
    """The map's 546 new records and 21 extensions (tools/import_refmap.py) load as one registry with the core. A
    record leaves `snippet-only` only by being read and promoted by hand, and a record is promoted, never dropped, so
    the count of shard records only grows. Nothing in the shards names a project of docs/areas.yaml or judges a record
    against one project's target."""
    own = [r for s in registry.shards for r in s.records if not r.get("extends")]
    ext = [r for s in registry.shards for r in s.records if r.get("extends")]
    assert len(own) >= 546 and len(ext) >= 21
    for rec in own:
        if rec["evidence"]["class"] == "snippet-only":
            assert rec["used_for"] == [] and registry.resolve(rec["id"]).kind == "catalogued", rec["id"]
        if rec["licence"]["read"] is False:
            assert rec["reuse"].get("geometry") != "copy", rec["id"]
    tree = yaml.safe_load((ROOT / "docs" / "areas.yaml").read_text())
    banned = [k for k in tree["projects"]] + [p["title"].lower() for p in tree["projects"].values()] + [
        "rs-04", "off-target", "our robot", "our own tests"]
    hidden = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")    # bidi and zero-width controls
    banned += ["not wheel-legged", "relevance to the robot", "seed for this map"]
    for file in [s.file for s in registry.shards] + [f"docs/research/references/{refs.COVERAGE}"]:
        shard = refs.Shard(file, {})
        text = (ROOT / shard.file).read_text(encoding="utf-8").lower()
        assert not [b for b in banned if b in text], shard.file
        assert not hidden.search(text), f"{shard.file}: a bidi or zero-width control character in imported text"


def test_the_coverage_rows_keep_their_drafts_unposted(registry):
    rows = registry.coverage["rows"]
    assert len(rows) == 16 and len({r["id"] for r in rows}) == 16
    drafts = [r["draft_issue"] for r in rows if "draft_issue" in r]
    assert drafts and all(d["posted"] is False or (isinstance(d["posted"], int) and not isinstance(d["posted"], bool))
                          for d in drafts)
    assert {w["group"] for w in registry.coverage["wanted"]} == set(registry.vocab["process_group"])
