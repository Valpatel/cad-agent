"""The reference registry, research/references.yaml (#118): every entry is well formed, every id the code cites
resolves, every file that cites an entry is in its used_for, and no source is vendored.

The checks run on the real registry and code, and on a planted checkout (tmp_path) with one mistake of each kind, so
each rule is shown to catch what it is for."""
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

from cadagent.review import references as refs
from cadagent.review.references import Registry, check, citations, isbn_ok, load

ROOT = Path(__file__).resolve().parents[1]

# Code that cites an `unverified` entry: each is a source the code's author read but whose URL was not recorded or
# could not be found. The list only shrinks: record the URL, move the entry up to `sources`, and drop it here.
UNVERIFIED_CITED = {"goncalves", "pem-si", "ruthex-tip", "bossard-proof", "bossard-head", "vdi2230-friction"}


@pytest.fixture(scope="module")
def registry():
    return load()


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
    pp = yaml.safe_load((ROOT / "research" / "process-profiles.yaml").read_text(encoding="utf-8"))
    assert {r["source"] for r in pp["rules"] if not r["source"].startswith("dataset:")} <= found


def test_no_pdf_is_kept_in_the_repo():
    """Sources are cited, never copied: no data sheet, guide or standard is vendored as a PDF."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.pdf", "*.PDF"], capture_output=True, text=True,
                             check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    assert not out, f"PDFs in the repo: {out}; cite the source in research/references.yaml instead"


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
    (tmp_path / "research").mkdir()
    (tmp_path / "src" / "cadagent").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
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
    (tmp_path / "research" / "process-profiles.yaml").write_text(yaml.safe_dump({
        "rules": [{"id": "fdm-wall-maker", "source": "good-guide"}, {"id": "fdm-x", "source": "dataset:tds"}],
        "datasets": [{"id": "tds", "cites": "prose, not an id"}]}))
    (tmp_path / "research" / "references.yaml").write_text(yaml.safe_dump(
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
                     ("good-guide", "research/process-profiles.yaml", "process-profile")}


def test_check_reports_unknown_keys_and_missing_used_for(tmp_path):
    root = _planted(tmp_path, [GOOD])
    problems, warnings = check(root)
    assert any("cites 'gone'" in p for p in problems) and any("cites 'elsewhere'" in p for p in problems)
    assert any("add docs/page.md to used_for of good-guide" in p for p in problems)
    assert any("add README.md to used_for of good-guide" in p for p in problems)
    assert any("add research/process-profiles.yaml to used_for" in p for p in problems)
    assert not any("src/cadagent/mod.py to used_for" in p for p in problems) and not warnings


def test_check_warns_on_code_citing_an_unverified_entry(tmp_path):
    root = _planted(tmp_path, [{**GOOD, "used_for": ["src/cadagent/mod.py", "docs/page.md", "README.md#top",
                                                     "research/process-profiles.yaml"]}],
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
    problems = load(root / "research" / "references.yaml").problems(root)
    assert any(message in p for p in problems), problems
    assert not Registry({"schema": 1, "sources": [GOOD]}).problems(root)


def test_uncited_and_unverified_entries_are_checked_too(tmp_path):
    root = _planted(tmp_path, [GOOD], unverified=[{"id": "lost", "title": "Lost", "org": "Maker"}],
                    uncited=[{"id": "mine", "kind": "hunch", "note": ""},
                             {"id": "inner", "kind": "internal", "note": "a module", "cites": ["lost"]}])
    problems = "\n".join(load(root / "research" / "references.yaml").problems(root))
    assert "lost: an unverified entry needs `why`" in problems
    assert "mine: kind 'hunch'" in problems and "mine: no note" in problems
    assert "inner: cites 'lost', which is not a read source" in problems
    assert "inner: an internal key needs `where`" in problems


def test_used_for_may_name_a_folder_or_an_anchor(tmp_path):
    root = _planted(tmp_path, [{**GOOD, "used_for": ["src/cadagent", "docs/page.md#rules", "README.md",
                                                     "research/process-profiles.yaml"]}],
                    unverified=[{"id": "gone", "title": "Lost", "org": "Maker", "why": "no URL", "used_for": ["src/"]}],
                    uncited=[{"id": "elsewhere", "kind": "general", "note": "common knowledge"}])
    problems, _ = check(root)
    assert not problems, problems
    assert refs.lists(["src/cadagent"], "src/cadagent/mod.py") and not refs.lists(["src/cad"], "src/cadagent/mod.py")
    assert not refs.lists(["proposed: src/cadagent/mod.py"], "src/cadagent/mod.py")


def test_a_malformed_tag_is_reported_not_skipped(tmp_path):
    root = _planted(tmp_path, [{**GOOD, "used_for": ["src", "docs", "README.md", "research"]}],
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
