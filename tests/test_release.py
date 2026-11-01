import hashlib
import json
import os
import subprocess
import zipfile

import pytest

from cadagent.cli import main
from cadagent.project import CadConfigError, from_dict
from cadagent.publish.release import build_release
from cadagent.manufacturing.slicer import _settings

CFG = {"name": "demo", "title": "Demo box", "revision": "1.2", "printer": {"name": "P1S", "bed_mm": [256, 256]}}


def make_root(tmp_path):
    root = tmp_path / "proj"
    for d in ("exports", "preview", "cad/__pycache__", "tools", "docs"):
        (root / d).mkdir(parents=True)
    (root / "exports/geometry-checks.json").write_text(json.dumps({"lid": {}, "base": {}}))
    for part in ("lid", "base"):
        for suffix in (".step", ".stl", ".3mf"):
            (root / f"exports/{part}{suffix}").write_bytes(f"{part}{suffix} bytes".encode())
    (root / "exports/sim.json").write_text("{}")                       # review evidence: never released
    (root / "preview/part-lid.png").write_bytes(b"\x89PNG lid")
    (root / "cad/build.py").write_text("print('build')\n")
    (root / "cad/__pycache__/build.cpython-312.pyc").write_bytes(b"\0")
    (root / "cad/.env").write_text("SECRET=1\n")                       # hidden: never released
    (root / "tools/helper.py").write_text("x = 1\n")
    (root / "tools/scratch.tmp").write_text("scratch\n")
    (root / "README.md").write_text("# Demo\n")
    (root / "cad-agent.yaml").write_text("cad:\n  name: demo\n")
    (root / "docs/step.png").write_bytes(b"\x89PNG step")
    (root / "docs/assembly.md").write_text("# Assembly\n\n1. Fit the lid.\n\n![step](step.png)\n\n"
                                          "See [the readme](../README.md) and [the lid](../exports/lid.stl).\n")
    (root / "GUIDE.md").write_text("# Guide\n\n![step](docs/step.png) and [the build](cad/build.py)\n")
    return root


def project(tmp_path, release=None, slice_ok=True, root=None):
    root = root or make_root(tmp_path)
    p = from_dict(root, dict(CFG, **({"release": release} if release is not None else {})))
    sha = lambda f: hashlib.sha256((root / "exports" / f).read_bytes()).hexdigest()
    settings = _settings(p) if slice_ok else dict(_settings(p), filament="Some PETG")
    (root / "exports/slice-report.json").write_text(json.dumps(dict(settings, **{
        "slicer": "Bambu Studio (command line)", "parts": {
            "lid": {"grams": 50.0, "minutes": 90.0, "sha256": sha("lid.3mf")},
            "base": {"grams": 80.0, "minutes": 150.0, "sha256": "0" * 64}}})))       # stale: base.3mf changed since
    return p


def card(page, part):
    s = page[page.index(f'id="part-{part}"'):]
    return s[:s.index("</article>")]


def test_page_lists_parts_with_files_settings_and_slice_state(tmp_path):
    p = project(tmp_path, {"quantities": {"lid": 2}, "notes": {"lid": {"orientation": "roof down"}},
                           "pages": ["docs/assembly.md"], "exclude": ["**/__pycache__/**", "**/*.tmp"],
                           "hardware": [{"item": "M3 x 10 socket head", "qty": "4"}]})
    r = build_release(p, out=tmp_path / "out/demo-rev1.2")
    page = (r.folder / "index.html").read_text()
    assert "Demo box" in page and "1.2" in page
    assert 'href="cad/lid.step"' in page and 'href="cad/base.3mf"' in page and 'src="images/lid.png"' in page
    assert "× 2" in card(page, "lid") and "roof down" in card(page, "lid") and "50.0 g · 1 h 30 min" in card(page, "lid")
    assert "not sliced" in card(page, "base")              # its 3MF no longer matches the slice row
    assert "100 g" in page and "parts in this release" in page and "pieces to print" not in page
    assert "M3 x 10 socket head" in page
    assert any(w.startswith("base: not sliced") for w in r.warnings) and any("base: no thumbnail" in w for w in r.warnings)
    # the zip is named in the page, not linked: the link would be dead in an unpacked copy
    assert "demo-rev1.2.zip" in page and 'href="../demo-rev1.2.zip"' not in page
    assert r.zip_path == tmp_path / "out/demo-rev1.2.zip"


def test_slice_numbers_need_the_current_slicer_settings(tmp_path):
    p = project(tmp_path, slice_ok=False)
    r = build_release(p, out=tmp_path / "out/demo")
    page = (r.folder / "index.html").read_text()
    assert "not sliced" in card(page, "lid") and "other settings" in page
    assert json.loads((r.folder / "manifest.json").read_text())["slicer"]["report_current"] is False


def test_groups_count_honestly_and_flag_optional(tmp_path):
    p = project(tmp_path, {"groups": [{"title": "Print these", "parts": ["lid"], "note": "The set."},
                                      {"title": "Extras", "parts": ["base"], "optional": True}]})
    r = build_release(p, out=tmp_path / "out/g")
    page = (r.folder / "index.html").read_text()
    assert page.index("Print these") < page.index('id="part-lid"') < page.index("Extras") < page.index('id="part-base"')
    assert "optional</span>" in page and "1 part · 50 g, 1 h 30 min for all of them" in page
    parts = json.loads((r.folder / "manifest.json").read_text())["parts"]
    assert [(x["part"], x["optional"]) for x in parts] == [("lid", False), ("base", True)]


def test_pick_one_groups_and_the_build_total(tmp_path):
    p = project(tmp_path, {"groups": [{"title": "Lid or base (print one)", "parts": ["lid", "base"], "pick_one": True}],
                           "build": {"title": "Desktop <build>", "parts": ["lid"]}, "quantities": {"lid": 2}})
    r = build_release(p, out=tmp_path / "out/b")
    page = (r.folder / "index.html").read_text()
    assert "pick one</span>" in page and "2 parts · print one of these" in page
    assert "<b>100 g</b><span>3 h 00 min for one build: Desktop &lt;build&gt;" in page    # quantities count
    assert "filament for" not in page and "print time for" not in page     # no total that adds up alternatives
    m = json.loads((r.folder / "manifest.json").read_text())
    assert m["build"] == {"title": "Desktop <build>", "parts": ["lid"], "grams": 100.0, "minutes": 180.0}
    assert [(x["part"], x["pick_one"]) for x in m["parts"]] == [("lid", True), ("base", True)]
    assert not any("not a complete build" in w for w in r.warnings)


def test_a_build_missing_a_required_pick_one_group_is_warned(tmp_path):
    p = project(tmp_path, {"groups": [{"title": "Lid", "parts": ["lid"]},
                                      {"title": "Base", "parts": ["base", "lid2"], "pick_one": True}],
                           "build": {"title": "No base", "parts": ["lid"]}}, root=_with_lid2(tmp_path))
    assert any("'Base'" in w and "not a complete build" in w for w in build_release(p, out=tmp_path / "out/m").warnings)


def _with_lid2(tmp_path):
    root = make_root(tmp_path)
    for suffix in (".step", ".stl", ".3mf"):
        (root / f"exports/lid2{suffix}").write_bytes(b"lid2")
    return root


def test_a_build_with_an_unsliced_part_has_no_total(tmp_path):
    p = project(tmp_path, {"build": {"title": "All", "parts": ["lid", "base"]}})     # base's slice row is stale
    r = build_release(p, out=tmp_path / "out/u")
    page = (r.folder / "index.html").read_text()
    assert "one build: All (slice every part in it for its total)" in page and "filament for" in page
    assert json.loads((r.folder / "manifest.json").read_text())["build"]["grams"] is None


def test_parts_left_out_of_groups_are_warned(tmp_path):
    p = project(tmp_path, {"groups": [{"title": "Only", "parts": ["lid"]}]})
    assert any("not released" in w and "base" in w for w in build_release(p, out=tmp_path / "out/w").warnings)


def test_source_globs_skip_excluded_hidden_and_evidence(tmp_path):
    p = project(tmp_path, {"exclude": ["**/__pycache__/**", "**/*.tmp"]})
    r = build_release(p, out=tmp_path / "out/demo")
    files = set(r.files)
    assert {"source/cad/build.py", "source/tools/helper.py", "source/README.md", "source/cad-agent.yaml"} <= files
    assert not any(f.endswith((".pyc", ".tmp", ".env")) for f in files)
    assert any("cad/.env: hidden" in w for w in r.warnings)
    assert not any("sim.json" in f or "slice-report" in f for f in files)
    manifest = json.loads((r.folder / "manifest.json").read_text())
    assert manifest["format"] == "cad-agent.release/1" and manifest["files"] == r.files
    assert "cad-agent all" in (r.folder / "index.html").read_text()      # the config is in the source


def test_git_ignored_files_are_skipped_and_a_dirty_tree_is_recorded(tmp_path):
    root = make_root(tmp_path)
    (root / ".gitignore").write_text("*.vendor\n")
    (root / "cad/model.vendor").write_text("licensed\n")
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    run("init", "-q")
    run("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
    (root / "cad/kept.vendor").write_text("our own\n")
    run("add", "-f", "cad/kept.vendor")                                     # force-added: tracked, so released
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "y")
    (root / "cad/build.py").write_text("print('changed')\n")
    (root / "cad/new.py").write_text("x = 2\n")                            # untracked but matched by cad/**
    p = project(tmp_path, {}, root=root)
    r = build_release(p, out=tmp_path / "out/git")
    assert "source/cad/model.vendor" not in r.files and any("ignored by git" in w for w in r.warnings)
    assert "source/cad/kept.vendor" in r.files and "source/cad/new.py" in r.files
    assert any("not in git" in w and "cad/new.py" in w for w in r.warnings)
    m = json.loads((r.folder / "manifest.json").read_text())
    assert m["git"]["dirty"] is True and "cad/build.py" in m["git"]["modified"] and len(m["git"]["commit"]) == 40
    assert "cad/new.py" in m["git"]["untracked_released"]
    assert any("uncommitted" in w for w in r.warnings) and "uncommitted changes" in (r.folder / "index.html").read_text()


def test_zip_is_byte_identical_across_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    p = project(tmp_path, {"pages": ["docs/assembly.md"]})
    a = build_release(p, out=tmp_path / "out/demo")
    first = a.zip_path.read_bytes()
    b = build_release(p, out=tmp_path / "out/demo")                      # rewrites the folder from scratch
    assert b.zip_path.read_bytes() == first
    names = zipfile.ZipFile(b.zip_path).namelist()
    assert names == sorted(names) and all(n.startswith("demo/") for n in names) and "demo/index.html" in names
    m = json.loads((b.folder / "manifest.json").read_text())
    assert m["date"] == "2023-11-14" and m["date_reproducible"] is True


def test_revision_and_date_override(tmp_path):
    p = project(tmp_path, {"revision": "1.2.1"})
    r = build_release(p, out=tmp_path / "out/r", date="2026-10-29")
    m = json.loads((r.folder / "manifest.json").read_text())
    assert (m["revision"], m["date"]) == ("1.2.1", "2026-10-29")
    assert build_release(p, out=tmp_path / "out/r", revision="9").parts and \
        json.loads((tmp_path / "out/r/manifest.json").read_text())["revision"] == "9"


def test_pages_keep_working_links_raw_and_rendered(tmp_path):
    p = project(tmp_path, {"pages": ["docs/assembly.md", "GUIDE.md"]})
    r = build_release(p, out=tmp_path / "out/demo")
    # pages and their images sit at their project paths under docs/, so the raw copies' own links resolve
    assert {"docs/docs/assembly.md", "docs/docs/step.png", "docs/GUIDE.md"} <= set(r.files)
    raw = (r.folder / "docs/docs/assembly.md").read_text()
    assert "](step.png)" in raw and "](../../source/README.md)" in raw and "](../../cad/lid.stl)" in raw
    guide = (r.folder / "docs/GUIDE.md").read_text()
    assert "](docs/step.png)" in guide and "](../source/cad/build.py)" in guide
    for page in (r.folder / "docs/docs/assembly.md", r.folder / "docs/GUIDE.md"):
        import re
        for url in re.findall(r"\]\(([^)]+)\)", page.read_text()):
            assert (page.parent / url).exists(), (page, url)
    pytest.importorskip("markdown")
    html = (r.folder / "docs/docs/assembly.html").read_text()
    assert "Fit the lid" in html and 'src="step.png"' in html and 'href="../../index.html"' in html
    assert 'href="../../source/README.md"' in html and 'href="../../cad/lid.stl"' in html
    assert 'href="docs/docs/assembly.html"' in (r.folder / "index.html").read_text()


def test_names_are_url_encoded(tmp_path):
    root = make_root(tmp_path)
    (root / "exports/geometry-checks.json").write_text(json.dumps({"a#b c": {}}))
    (root / "exports/a#b c.stl").write_bytes(b"solid")
    p = project(tmp_path, {}, root=root)
    page = (build_release(p, out=tmp_path / "out/u").folder / "index.html").read_text()
    assert 'href="cad/a%23b%20c.stl"' in page


@pytest.mark.parametrize("bad", [
    {"include": ["../outside/**"]}, {"include": ["/etc/*"]}, {"exclude": ["../x"]}, {"pages": ["../outside/v.txt"]},
    {"extra_cad": ["../outside/secret/*"]}, {"thumbnail": "../outside/secret/key.txt"}, {"hardware": "../x.csv"},
    {"thumbnail": "{nope}.png"}, {"thumbnail": "{0}.png"}, {"thumbnail": ["a"]},
    {"parts": ["lid"], "groups": [{"title": "x", "parts": ["base"]}]}, {"parts": ["lid", "lid"]}, {"parts": []},
    {"include": None}, {"quantities": {"lid": 0}}, {"notes": {"ghost": {"a": "b"}}}, {"colour": "red"},
    {"groups": [{"title": "x", "parts": ["lid"], "notes": "typo"}]}, {"max_file_mb": 0},
    {"notes": {"lid": {"use": "desktop", "or any setup": None}}}, {"hardware": [{"item": "M3", "qty": None}]},
    {"groups": [{"title": "x", "parts": ["lid"], "pick_one": "yes"}]},
    {"groups": [{"title": "x", "parts": ["lid"], "pick_one": True}, {"title": "y", "parts": ["base"]}]}, {"build": {"title": "b", "parts": ["ghost"]}},
    {"build": {"title": "b", "parts": ["lid", "lid"]}}, {"build": {"parts": ["lid"]}}, {"build": ["lid"]},
    {"build": {"title": "b", "parts": ["lid"], "note": "typo"}},
    {"groups": [{"title": "x", "parts": ["lid", "base"], "pick_one": True}], "build": {"title": "b", "parts": ["lid", "base"]}}])
def test_bad_config(tmp_path, bad):
    with pytest.raises(CadConfigError):
        build_release(project(tmp_path, bad), out=tmp_path / "out/bad")


def test_missing_part_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_release(project(tmp_path, {"parts": ["ghost"]}), out=tmp_path / "out/missing")


def test_symlinks_out_of_the_project_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "key.txt").write_text("secret\n")
    root = make_root(tmp_path)
    os.symlink(outside / "key.txt", root / "cad/link.txt")
    os.symlink(outside, root / "tools/outdir")
    r = build_release(project(tmp_path, {}, root=root), out=tmp_path / "out/s")
    assert not any("link.txt" in f or "outdir" in f for f in r.files)
    assert any("link.txt: links outside the project" in w for w in r.warnings)
    assert not any("secret" in p.read_text(errors="ignore") for p in (tmp_path / "out/s").rglob("*") if p.is_file())


def test_large_files_warn(tmp_path):
    p = project(tmp_path, {"max_file_mb": 0.00001})
    assert any("max_file_mb" in w for w in build_release(p, out=tmp_path / "out/big").warnings)


def test_refuses_to_overwrite_a_foreign_folder(tmp_path):
    p = project(tmp_path, {})
    foreign = tmp_path / "out/mine"
    foreign.mkdir(parents=True)
    (foreign / "notes.txt").write_text("keep me\n")
    with pytest.raises(FileExistsError):
        build_release(p, out=foreign)
    assert (foreign / "notes.txt").read_text() == "keep me\n"


def test_cli(tmp_path, capsys):
    p = project(tmp_path, {})
    (p.root / "cad-agent.yaml").write_text("cad:\n  name: demo\n  revision: '1.2'\n  printer: {name: P1S, bed_mm: [256, 256]}\n")
    assert main(["release", "--project", str(p.root), "--out", str(tmp_path / "cli/demo"), "--no-zip",
                 "--revision", "1.2.1", "--date", "2026-10-29"]) == 0
    out = capsys.readouterr().out
    assert "release: 2 part(s)" in out and not (tmp_path / "cli/demo.zip").exists()
    assert json.loads((tmp_path / "cli/demo/manifest.json").read_text())["revision"] == "1.2.1"
    (p.root / "cad-agent.yaml").write_text("cad:\n  name: demo\n  release: {include: ['../x']}\n")
    assert main(["release", "--project", str(p.root), "--out", str(tmp_path / "cli/bad")]) == 2


def test_no_slicer_settings_without_config_or_current_report(tmp_path):
    p = project(tmp_path, {})
    (p.root / "exports/slice-report.json").unlink()
    page = (build_release(p, out=tmp_path / "out/n").folder / "index.html").read_text()
    assert "no slicer settings configured" in page and "Bambu" not in page and "Recommended print settings" not in page
    assert "<dt>Material</dt>" not in page


def test_settings_from_config_do_not_claim_slicing_when_nothing_is_current(tmp_path):
    p = project(tmp_path, {}, slice_ok=False)
    p.slicer = {"filament": "petg"}
    page = (build_release(p, out=tmp_path / "out/c").folder / "index.html").read_text()
    assert "Recommended print settings" in page and "PETG" in page and "were sliced with them" not in page


def test_prusa_project_release_says_prusaslicer_presets(tmp_path):
    p = project(tmp_path, {})
    p.slicer = {"engine": "prusa", "filament": "pla"}
    report = json.loads((p.root / "exports/slice-report.json").read_text())
    report.update(_settings(p), slicer="PrusaSlicer (command line)")
    (p.root / "exports/slice-report.json").write_text(json.dumps(report))
    page = (build_release(p, out=tmp_path / "out/demo").folder / "index.html").read_text()
    assert "PrusaSlicer presets" in page and "Bambu" not in page
