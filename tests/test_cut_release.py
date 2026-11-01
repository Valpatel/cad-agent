"""tools/cut_release.py: the release-branch edits, checked against CI's own release gate."""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("cut_release", ROOT / "tools" / "cut_release.py")
cut_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cut_release)
_gspec = importlib.util.spec_from_file_location("ci_gates", ROOT / "tools" / "ci_gates.py")
ci_gates = importlib.util.module_from_spec(_gspec)
_gspec.loader.exec_module(ci_gates)

PYPROJECT = """[build-system]
requires = ["setuptools"]

[tool.before]
version = "8.8.8"

[project]
name = "cadagent"
version = "0.4.2"

[tool.other]
version = "9.9.9"
"""
CHANGELOG = """# Changelog

Intro.

## Unreleased

**New**
- A thing (#1).

## v0.4.2 (2026-10-29)

- Older.
"""


def test_minor_bumps_and_dates_and_opens_a_new_unreleased():
    py, cl, v = cut_release.cut(PYPROJECT, CHANGELOG, bump="minor", date="2026-11-01")
    assert v == "0.5.0"
    # only the [project] table changes, not a version line in a table before or after it
    assert 'version = "0.5.0"' in py and 'version = "8.8.8"' in py and 'version = "9.9.9"' in py
    assert "## Unreleased\n\n## v0.5.0 (2026-11-01)\n\n**New**\n- A thing (#1).\n\n## v0.4.2" in cl
    assert ci_gates.release_gate(py, PYPROJECT, cl)[0]


def test_patch_and_explicit_version():
    assert cut_release.cut(PYPROJECT, CHANGELOG, bump="patch", date="2026-11-01")[2] == "0.4.3"
    assert cut_release.cut(PYPROJECT, CHANGELOG, version="1.0.0", date="2026-11-01")[2] == "1.0.0"


def test_the_older_unreleased_heading_is_accepted():
    old = CHANGELOG.replace("## Unreleased", "## v0.5.0 (unreleased)")
    _, cl, _ = cut_release.cut(PYPROJECT, old, bump="minor", date="2026-11-01")
    assert "## v0.5.0 (unreleased)" not in cl and "## v0.5.0 (2026-11-01)" in cl


@pytest.mark.parametrize("changelog, message", [
    (CHANGELOG.replace("## Unreleased\n", ""), "found 0"),
    (CHANGELOG + "\n## Unreleased\n\n- again\n", "found 2"),
    (CHANGELOG.replace("**New**\n- A thing (#1).\n", ""), "nothing to release"),
])
def test_refuses_a_changelog_it_cannot_release(changelog, message):
    with pytest.raises(ValueError, match=message):
        cut_release.cut(PYPROJECT, changelog, bump="minor", date="2026-11-01")


@pytest.mark.parametrize("body", ["**New**\n", "### Fixed\n\n", "<!-- nothing yet -->\n", "**New**\n<!--\n- a\n-->\n"])
def test_an_entry_with_only_headings_or_comments_is_empty(body):
    with pytest.raises(ValueError, match="nothing to release"):
        cut_release.cut(PYPROJECT, CHANGELOG.replace("**New**\n- A thing (#1).\n", body), bump="minor",
                        date="2026-11-01")


def test_refuses_a_heading_that_names_another_version():
    old = CHANGELOG.replace("## Unreleased", "## v0.6.0 (unreleased)")
    with pytest.raises(ValueError, match="names v0.6.0, not v0.5.0"):
        cut_release.cut(PYPROJECT, old, bump="minor", date="2026-11-01")
    assert "## v0.6.0 (2026-11-01)" in cut_release.cut(PYPROJECT, old, version="0.6.0", date="2026-11-01")[1]


@pytest.mark.parametrize("version", ["v0.5.0", "abc", "0.5.0-rc1", ""])
def test_refuses_a_version_that_is_not_digits(version):
    with pytest.raises(ValueError, match="X.Y.Z digits"):
        cut_release.cut(PYPROJECT, CHANGELOG, version=version, date="2026-11-01")


def test_the_default_date_is_utc(monkeypatch):
    class Clock(cut_release.dt.datetime):
        @classmethod
        def now(cls, tz=None):  # 2026-10-31 23:30 at -07:00 is 2026-11-01 06:30 UTC
            moment = cut_release.dt.datetime(2026, 11, 1, 6, 30, tzinfo=cut_release.dt.timezone.utc)
            return moment.astimezone(tz) if tz else moment.astimezone(cut_release.dt.timezone(
                cut_release.dt.timedelta(hours=-7))).replace(tzinfo=None)
    monkeypatch.setattr(cut_release.dt, "datetime", Clock)
    assert cut_release.utc_today() == "2026-11-01"
    assert "## v0.5.0 (2026-11-01)" in cut_release.cut(PYPROJECT, CHANGELOG, bump="minor")[1]


def test_cli_reports_a_missing_root_without_a_traceback(tmp_path, capsys):
    assert cut_release.main(["--minor", "--root", str(tmp_path / "nowhere")]) == 1
    assert capsys.readouterr().err.startswith("cut_release: ")


def test_refuses_a_version_not_above_the_current_one():
    with pytest.raises(ValueError, match="release gate would fail"):
        cut_release.cut(PYPROJECT, CHANGELOG, version="0.4.1", date="2026-11-01")
    with pytest.raises(ValueError, match="already has an entry for v0.4.2"):
        cut_release.cut(PYPROJECT, CHANGELOG, version="0.4.2", date="2026-11-01")


def test_refuses_an_impossible_date_and_a_missing_choice():
    with pytest.raises(ValueError):
        cut_release.cut(PYPROJECT, CHANGELOG, bump="minor", date="2026-02-30")
    with pytest.raises(ValueError, match="exactly one"):
        cut_release.cut(PYPROJECT, CHANGELOG, date="2026-11-01")


def test_cli_dry_run_writes_nothing(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG)
    assert cut_release.main(["--minor", "--date", "2026-11-01", "--root", str(tmp_path), "--dry-run"]) == 0
    assert (tmp_path / "pyproject.toml").read_text() == PYPROJECT
    assert cut_release.main(["--minor", "--date", "2026-11-01", "--root", str(tmp_path)]) == 0
    assert 'version = "0.5.0"' in (tmp_path / "pyproject.toml").read_text()
    assert cut_release.main(["--patch", "--root", str(tmp_path)]) == 1  # Unreleased is now empty


FIX = ("changelog.d/175-cfd.md", "**Fixed**\n- CFD settles within 1 °C (#175).\n")
PMC = ("changelog.d/135-names.md", "**Projects must change**\n- Rename the key (#135).\n\n**New**\n- A check (#135).\n")


def test_fragments_fold_into_their_sections_in_order():
    new = cut_release.fold_fragments(CHANGELOG, [FIX, PMC, ("changelog.d/9.md", "**New**\n- Another (#9).\n")])
    entry = new.split("## Unreleased\n\n", 1)[1].split("\n## v0.4.2", 1)[0]
    assert entry == ("**New**\n- A thing (#1).\n- A check (#135).\n- Another (#9).\n\n**Fixed**\n"
                     "- CFD settles within 1 °C (#175).\n\n**Projects must change**\n- Rename the key (#135).\n")
    assert new.endswith("## v0.4.2 (2026-10-29)\n\n- Older.\n")


def test_fragments_fill_an_empty_entry_and_keep_a_colon_heading():
    empty = CHANGELOG.replace("**New**\n- A thing (#1).\n", "")
    _, cl, _ = cut_release.cut(PYPROJECT, empty, bump="patch", date="2026-11-01", fragments=[FIX])
    assert "## Unreleased\n\n## v0.4.3 (2026-11-01)\n\n**Fixed**\n- CFD settles within 1 °C (#175).\n\n## v0.4.2" in cl
    colon = CHANGELOG.replace("**New**\n- A thing (#1).\n",
                              "**New**\n- A thing (#1).\n\n**Projects must change:**\n- Old.\n")
    folded = cut_release.fold_fragments(colon, [PMC])
    assert "**Projects must change:**\n- Old.\n- Rename the key (#135).\n" in folded
    assert folded.count("Projects must change") == 1
    assert "- A thing (#1).\n- A check (#135).\n\n**Projects must change:**" in folded


@pytest.mark.parametrize("text, message", [
    ("- no heading\n", "text before the first section heading"),
    ("**Removed**\n- gone\n", "unknown section"),
    ("**Fixed**\nprose only\n", "has no '- ' bullet"),
    ("\n\n", "no section heading"),
    ("**Fixed**\n- a\n## v9.9.9 (2099-01-01)\n", "would split the CHANGELOG entry"),
    ("### Fixed\n- a\n", "would split the CHANGELOG entry"),
])
def test_refuses_a_malformed_fragment(text, message):
    with pytest.raises(ValueError, match=message):
        cut_release.fold_fragments(CHANGELOG, [("changelog.d/x.md", text)])


def test_a_missing_section_goes_between_the_ones_around_it():
    both = CHANGELOG.replace("**New**\n- A thing (#1).\n",
                             "**New**\n- A thing (#1).\n\n**Projects must change**\n- Old.\n")
    folded = cut_release.fold_fragments(both, [FIX])
    assert ("**New**\n- A thing (#1).\n\n**Fixed**\n- CFD settles within 1 °C (#175).\n\n**Projects must change**\n"
            "- Old.\n") in folded


def test_a_lead_in_paragraph_opens_its_section():
    # "**Projects must change:** text" on one line, the CHANGELOG's form up to v0.5.0 (from the review of #190)
    lead = CHANGELOG.replace("**New**\n- A thing (#1).\n",
                             "**New**\n- A thing (#1).\n\n"
                             "**Projects must change:** write STEP files\nwith export_step.\n")
    folded = cut_release.fold_fragments(lead, [FIX, PMC])
    entry = folded.split("## Unreleased\n\n", 1)[1].split("\n## v0.4.2", 1)[0]
    assert entry == ("**New**\n- A thing (#1).\n- A check (#135).\n\n**Fixed**\n- CFD settles within 1 °C (#175).\n\n"
                     "**Projects must change:** write STEP files\nwith export_step.\n\n- Rename the key (#135).\n")
    # a bold lead-in that is not a section stays inside the section it is in
    note = CHANGELOG.replace("- A thing (#1).\n", "- A thing (#1).\n\n**Note:** read this.\n")
    assert "**Note:** read this.\n\n- Another (#9).\n" in cut_release.fold_fragments(
        note, [("changelog.d/9.md", "**New**\n- Another (#9).\n")])


def test_cli_folds_and_deletes_fragments_but_not_on_a_dry_run(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG.replace("**New**\n- A thing (#1).\n", ""))
    frags = tmp_path / "changelog.d"
    frags.mkdir()
    (frags / "README.md").write_text("# changelog.d\n\nNot a fragment.\n")
    (frags / "175-cfd.md").write_text(FIX[1])
    assert cut_release.main(["--patch", "--date", "2026-11-01", "--root", str(tmp_path), "--dry-run"]) == 0
    assert (frags / "175-cfd.md").exists() and "#175" not in (tmp_path / "CHANGELOG.md").read_text()
    assert cut_release.main(["--patch", "--date", "2026-11-01", "--root", str(tmp_path)]) == 0
    assert sorted(p.name for p in frags.iterdir()) == ["README.md"]
    written = (tmp_path / "CHANGELOG.md").read_text()
    assert "## v0.4.3 (2026-11-01)\n\n**Fixed**\n- CFD settles within 1 °C (#175)." in written


def test_this_repo_can_be_released():
    """The real files parse: one Unreleased entry with content, and a [project] version."""
    py = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    for p in cut_release.fragment_files(ROOT):  # every fragment in the repo parses
        cut_release.read_fragment(p.name, p.read_text(encoding="utf-8"))
    if not cut_release.fragment_files(ROOT) and not cl[cut_release.UNRELEASED.search(cl).end():].split(
            "\n## ", 1)[0].strip():
        pytest.skip("nothing unreleased yet")
    frags = [(p.name, p.read_text(encoding="utf-8")) for p in cut_release.fragment_files(ROOT)]
    cut_release.cut(py, cl, bump="patch", date="2099-01-01", fragments=frags)
