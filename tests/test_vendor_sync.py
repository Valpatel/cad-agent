"""tools/vendor_sync.py notices: it rebuilds only the vendored table in THIRD_PARTY_NOTICES.md (#154).

It used to rewrite the whole file from vendor/manifest.json, and every `import` calls it, so the next vendor import
would have deleted the hand-kept showcase, runtime-dependency and web kit sections (their licence records)."""
import argparse
import importlib.util
import json
import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("vendor_sync", ROOT / "tools" / "vendor_sync.py")
vendor_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vendor_sync)

HAND_KEPT = ["## Showcase on the site (Gyropup)", "## Runtime dependencies and external programs (not vendored)",
             "## Web kit (copied into project sites and published on cad-agent.valpatel.com)", "```mermaid"]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A copy of the real notices and manifest, with the script pointed at it."""
    (tmp_path / "vendor").mkdir()
    shutil.copy(ROOT / "THIRD_PARTY_NOTICES.md", tmp_path / "THIRD_PARTY_NOTICES.md")
    shutil.copy(ROOT / "vendor" / "manifest.json", tmp_path / "vendor" / "manifest.json")
    monkeypatch.setattr(vendor_sync, "ROOT", tmp_path)
    monkeypatch.setattr(vendor_sync, "MAN", tmp_path / "vendor" / "manifest.json")
    return tmp_path


def test_committed_notices_match_the_manifest():
    """Regenerating from the committed manifest changes nothing: the table is in sync and every other line stays."""
    text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    projects = json.loads((ROOT / "vendor" / "manifest.json").read_text())["projects"]
    assert vendor_sync.notices_text(text, projects) == text


def test_notices_after_an_import_keep_every_hand_kept_section(repo):
    """What `import` does: the manifest gets a new pin, then `notices` runs. Only that project's row changes."""
    before = (repo / "THIRD_PARTY_NOTICES.md").read_text()
    man = json.loads((repo / "vendor" / "manifest.json").read_text())
    e = man["projects"][1]
    old_row = next(line for line in before.splitlines() if line.startswith(f"| {e['name']} |"))
    e["sha"], e["imported"] = "ab" * 20, "2026-11-01"
    (repo / "vendor" / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")

    vendor_sync.cmd_notices(None)
    after = (repo / "THIRD_PARTY_NOTICES.md").read_text()
    new_row = f"| {e['name']} | {e['license']} | {e['url']} | `{'ab' * 6}` | 2026-11-01 |"
    assert after == before.replace(old_row, new_row)
    for heading in HAND_KEPT:
        assert heading in after


def test_notices_follow_the_manifest_when_a_project_is_added_or_removed(repo):
    man = json.loads((repo / "vendor" / "manifest.json").read_text())
    gone = man["projects"].pop(0)
    man["projects"].append({"name": "new-lib", "url": "https://example.org/new-lib", "license": "MIT"})
    (repo / "vendor" / "manifest.json").write_text(json.dumps(man, indent=2) + "\n")

    vendor_sync.cmd_notices(None)
    lines = (repo / "THIRD_PARTY_NOTICES.md").read_text().splitlines()
    head = lines.index(vendor_sync.TABLE_HEAD)
    table = lines[head:head + 2 + len(man["projects"])]
    assert table[-1] == "| new-lib | MIT | https://example.org/new-lib | `-` | - |"
    assert not any(line.startswith(f"| {gone['name']} |") for line in lines)
    assert not lines[head + 2 + len(man["projects"])].startswith("|"), "the old table's extra row is left behind"
    for heading in HAND_KEPT:
        assert any(line.startswith(heading) for line in lines)


@pytest.mark.parametrize("damage", ["drop", "twice"])
def test_notices_refuse_a_file_without_exactly_one_vendored_table(repo, damage):
    """No table header, or two, is a file someone rewrote by hand: stop and change nothing rather than guess."""
    path = repo / "THIRD_PARTY_NOTICES.md"
    text = path.read_text()
    text = (text.replace(vendor_sync.TABLE_HEAD, "| Project | Licence |") if damage == "drop"
            else text + "\n" + vendor_sync.TABLE_HEAD + "\n|---|---|---|---|---|\n")
    path.write_text(text)
    with pytest.raises(SystemExit, match="expected one vendored table"):
        vendor_sync.cmd_notices(None)
    assert path.read_text() == text


def test_import_refuses_a_damaged_notices_file_before_it_changes_anything(repo, monkeypatch):
    """`import` checks the notices file first, so a file `notices` would refuse cannot stop an import half done."""
    path = repo / "THIRD_PARTY_NOTICES.md"
    path.write_text(path.read_text().replace(vendor_sync.TABLE_HEAD, "| Project | Licence |"))
    manifest = (repo / "vendor" / "manifest.json").read_text()

    def went_ahead(*args, **kwargs):
        raise AssertionError("the import went ahead")
    for step in ("run", "remote_head", "export_tree"):
        monkeypatch.setattr(vendor_sync, step, went_ahead)
    monkeypatch.setattr(vendor_sync, "V", repo / "vendor")
    name = json.loads(manifest)["projects"][0]["name"]
    with pytest.raises(SystemExit, match="expected one vendored table"):
        vendor_sync.cmd_import(argparse.Namespace(name=name, sha="ab" * 20, initial=False))
    assert (repo / "vendor" / "manifest.json").read_text() == manifest
    assert sorted(p.name for p in (repo / "vendor").iterdir()) == ["manifest.json"]


def test_notices_start_a_missing_file_with_the_header_and_table(repo):
    (repo / "THIRD_PARTY_NOTICES.md").unlink()
    vendor_sync.cmd_notices(None)
    text = (repo / "THIRD_PARTY_NOTICES.md").read_text()
    assert text.startswith("# Third-party notices\n")
    assert vendor_sync.TABLE_HEAD in text and text.endswith(" |\n")
