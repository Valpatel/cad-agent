import hashlib
import json
import zipfile

import pytest

from cadagent.cli import main
from cadagent.project import CadConfigError, from_dict
from cadagent.release import build_release


def project(tmp_path, release=None):
    root = tmp_path / "proj"
    (root / "exports").mkdir(parents=True)
    (root / "preview").mkdir()
    (root / "cad").mkdir()
    (root / "cad/__pycache__").mkdir()
    (root / "tools").mkdir()
    (root / "docs").mkdir()
    (root / "exports/geometry-checks.json").write_text(json.dumps({"lid": {}, "base": {}}))
    for part in ("lid", "base"):
        for suffix in (".step", ".stl", ".3mf"):
            (root / f"exports/{part}{suffix}").write_bytes(f"{part}{suffix} bytes".encode())
    (root / "exports/sim.json").write_text("{}")                       # review evidence: never released
    (root / "preview/part-lid.png").write_bytes(b"\x89PNG lid")
    (root / "cad/build.py").write_text("print('build')\n")
    (root / "cad/__pycache__/build.cpython-312.pyc").write_bytes(b"\0")
    (root / "tools/helper.py").write_text("x = 1\n")
    (root / "tools/scratch.tmp").write_text("scratch\n")
    (root / "README.md").write_text("# Demo\n")
    (root / "docs/step.png").write_bytes(b"\x89PNG step")
    (root / "docs/assembly.md").write_text("# Assembly\n\n1. Fit the lid.\n\n![step](step.png)\n\n"
                                          "See [the readme](../README.md) and [the lid](../exports/lid.stl).\n")
    sha = lambda p: hashlib.sha256((root / "exports" / p).read_bytes()).hexdigest()
    (root / "exports/slice-report.json").write_text(json.dumps({
        "slicer": "Bambu Studio (command line)", "printer": "Bambu Lab P1S 0.4 nozzle", "process": "0.20mm Standard",
        "filament": "Bambu PLA Basic @BBL P1S", "parts": {
            "lid": {"grams": 50.0, "minutes": 90.0, "sha256": sha("lid.3mf")},
            "base": {"grams": 80.0, "minutes": 150.0, "sha256": "0" * 64}}}))       # stale: base.3mf changed since
    cfg = {"name": "demo", "title": "Demo box", "revision": "1.2", "printer": {"name": "P1S", "bed_mm": [256, 256]}}
    if release is not None:
        cfg["release"] = release
    return from_dict(root, cfg)


def test_page_lists_parts_with_files_settings_and_slice_state(tmp_path):
    p = project(tmp_path, {"quantities": {"lid": 2}, "notes": {"lid": {"orientation": "roof down"}},
                           "pages": ["docs/assembly.md"], "exclude": ["**/__pycache__/**", "**/*.tmp"],
                           "hardware": [{"item": "M3 x 10 socket head", "qty": "4"}]})
    r = build_release(p, out=tmp_path / "out/demo-rev1.2")
    page = (r.folder / "index.html").read_text()
    assert "Demo box" in page and "1.2" in page
    assert 'id="part-lid"' in page and 'id="part-base"' in page
    assert 'href="cad/lid.step"' in page and 'href="cad/base.3mf"' in page and 'src="images/lid.png"' in page
    assert "× 2" in page and "roof down" in page and "50.0 g · 1 h 30 min" in page
    assert "0.20mm Standard" in page and "Bambu PLA Basic" in page
    # base's 3MF no longer matches its slice row: shown as not sliced and left out of the totals
    base_card = page[page.index('id="part-base"'):]
    assert "not sliced" in base_card[:base_card.index("</article>")]
    assert "100 g" in page                                                # 2 x 50 g, base excluded
    assert "M3 x 10 socket head" in page
    assert (r.folder / "docs/assembly.md").is_file()
    assert any(w.startswith("base: not sliced") for w in r.warnings) and any("base: no thumbnail" in w for w in r.warnings)


def test_source_globs_exclude_and_no_review_evidence(tmp_path):
    p = project(tmp_path, {"exclude": ["**/__pycache__/**", "**/*.tmp"]})
    r = build_release(p, out=tmp_path / "out/demo")
    files = set(r.files)
    assert {"source/cad/build.py", "source/tools/helper.py", "source/README.md"} <= files
    assert not any(f.endswith(".pyc") or f.endswith(".tmp") for f in files)
    assert not any("sim.json" in f or "slice-report" in f for f in files)
    manifest = json.loads((r.folder / "manifest.json").read_text())
    assert manifest["format"] == "cad-agent.release/1" and manifest["files"] == r.files


def test_zip_is_byte_identical_across_runs(tmp_path):
    p = project(tmp_path, {"pages": ["docs/assembly.md"]})
    a = build_release(p, out=tmp_path / "out/demo")
    first = a.zip_path.read_bytes()
    b = build_release(p, out=tmp_path / "out/demo")                      # rewrites the folder from scratch
    assert b.zip_path.read_bytes() == first
    names = zipfile.ZipFile(b.zip_path).namelist()
    assert names == sorted(names) and all(n.startswith("demo/") for n in names) and "demo/index.html" in names


def test_markdown_pages_and_their_images(tmp_path):
    pytest.importorskip("markdown")
    p = project(tmp_path, {"pages": ["docs/assembly.md"]})
    r = build_release(p, out=tmp_path / "out/demo")
    assert "docs/assembly.md" in r.files and "docs/step.png" in r.files       # the image it links to comes along
    html = (r.folder / "docs/assembly.html").read_text()
    assert "Fit the lid" in html and 'src="step.png"' in html and 'href="../index.html"' in html
    assert 'href="docs/assembly.html"' in (r.folder / "index.html").read_text()
    # links to files the release carries elsewhere point at those copies
    assert 'href="../source/README.md"' in html and 'href="../cad/lid.stl"' in html


def test_groups_and_bad_config(tmp_path):
    p = project(tmp_path, {"groups": [{"title": "Print these", "parts": ["base"], "note": "The set."},
                                      {"title": "Optional", "parts": ["lid"]}]})
    page = (build_release(p, out=tmp_path / "out/g").folder / "index.html").read_text()
    assert page.index("Print these") < page.index('id="part-base"') < page.index("Optional") < page.index('id="part-lid"')
    for bad in ({"parts": ["lid"], "groups": [{"title": "x", "parts": ["base"]}]}, {"parts": ["lid", "lid"]},
                {"quantities": {"lid": 0}}, {"notes": {"ghost": {"a": "b"}}}, {"colour": "red"},
                {"notes": {"lid": {"use": "desktop", "or any setup": None}}}, {"hardware": [{"item": "M3", "qty": None}]}):
        with pytest.raises(CadConfigError):
            build_release(project(tmp_path / str(abs(hash(str(bad)))), bad), out=tmp_path / "out/bad")
    with pytest.raises(FileNotFoundError):
        build_release(project(tmp_path / "missing", {"parts": ["ghost"]}), out=tmp_path / "out/missing")


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
    assert main(["release", "--project", str(p.root), "--out", str(tmp_path / "cli/demo"), "--no-zip"]) == 0
    out = capsys.readouterr().out
    assert "release: 2 part(s)" in out and not (tmp_path / "cli/demo.zip").exists()
