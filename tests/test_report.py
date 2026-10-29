"""collect()/write_report(): schema 1.0 results, and failures that cannot read as passes."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from cadagent.project import load_project
from cadagent import report

GOOD = {"cad_valid": True, "solid_count": 1, "watertight": True, "print_bounds_mm": [100, 80, 40]}

def make_project(root: Path, parts=None, checks_yaml="") -> Path:
    (root / "exports").mkdir(parents=True)
    (root / "preview").mkdir()
    (root / "cad-agent.yaml").write_text(textwrap.dedent("""\
        cad:
          name: demo
          title: Demo box
          revision: '2'
          printer: {name: Bed, bed_mm: [256, 256, 256]}
          part_ids: {box: P1}
          html_pages: [preview/index.html]
        """) + checks_yaml)
    parts = {"box": dict(GOOD), "lid": dict(GOOD)} if parts is None else parts
    (root / "exports" / "geometry-checks.json").write_text(json.dumps(parts))
    for name in parts:
        for ext in ("stl", "3mf", "step"):
            (root / "exports" / f"{name}.{ext}").write_text("x")
    (root / "preview" / "part-box.png").write_bytes(b"\x89PNG")
    (root / "preview" / "index.html").write_text('<a href="part-box.png">box</a>')
    bind_holes(root, parts)
    return root

def bind_holes(root: Path, parts) -> None:
    """A passing hole check bound to the placeholder STEP files, as `cad-agent holes` writes it."""
    import hashlib
    rows = {n: {"pass": True, "holes": 0, "findings": [], "excepted": [], "step": f"{n}.step",
                "sha256": hashlib.sha256((root / "exports" / f"{n}.step").read_bytes()).hexdigest()} for n in parts}
    from cadagent.holes import VERSION, config, config_key
    from cadagent.project import load_project
    key = config_key(config(load_project(root)))
    (root / "exports" / "hole-checks.json").write_text(json.dumps({"version": VERSION, "config_key": key, "parts": rows,
                                                                  "pass": True}))

def rows(results, feature_id):
    feature = next(f for f in results["features"] if f["feature_id"] == feature_id)
    return {c["name"]: c for c in feature["checks"]}

TOP_KEYS = {"schema_version", "title", "features", "header_meta", "footer_meta", "project",
            "revision", "physical_fit_verified", "slicer_run", "pass"}

def assert_schema(results):
    """The schema 1.0 shape that vptest web also renders."""
    assert results["schema_version"] == "1.0"
    assert set(results) == TOP_KEYS
    assert [f["feature_id"] for f in results["features"]] == ["cad-parts", "cad-print-files", "cad-holes",
                                                              "cad-checks", "cad-links"]
    assert {"project", "revision", "generated"} == set(results["header_meta"])
    assert {"checks", "physical_fit", "slicer"} == set(results["footer_meta"])
    for feature in results["features"]:
        assert {"feature_id", "feature_title", "checks"} == set(feature) and feature["checks"]
        for check in feature["checks"]:
            assert {"name", "status"} <= set(check)
            assert set(check) <= {"name", "status", "message", "error", "evidence", "links"}
            assert check["status"] in ("pass", "fail", "skip")
            if "evidence" in check:
                assert check["evidence"]["type"] in ("screenshot", "link", "log")

CHECKS = (
    "  checks:\n"
    "    - {id: fit, title: Fit, file: exports/fit.json}\n"
    "    - {id: gone, title: Never written, file: exports/gone.json}\n"
    "    - {id: vague, title: Truthy string, file: exports/vague.json}\n"
    "    - {id: multi, title: Multi, file: exports/multi.json, pass_key: [a.ok, b]}\n"
)

@pytest.fixture
def results(tmp_path):
    root = make_project(tmp_path, checks_yaml=CHECKS)
    (root / "exports" / "fit.json").write_text(json.dumps({"pass": True, "physical_fit_verified": False}))
    (root / "exports" / "vague.json").write_text(json.dumps({"pass": "yes"}))
    (root / "exports" / "multi.json").write_text(json.dumps({"a": {"ok": True}, "b": False}))
    project = load_project(root)
    assert [c.id for c in project.checks] == ["fit", "gone", "vague", "multi"]
    return report.collect(project)

def test_results_have_the_schema_1_0_shape(results):
    assert_schema(results)
    assert json.loads(json.dumps(results)) == results

def test_part_rows_carry_screenshot_evidence_and_ids(results):
    parts = rows(results, "cad-parts")
    assert parts["P1 · box"]["status"] == "pass"
    assert parts["P1 · box"]["evidence"] == {"type": "screenshot", "path": "../preview/part-box.png",
                                             "title": "P1 · box"}
    assert "evidence" not in parts["lid"]
    assert rows(results, "cad-print-files")["lid"]["status"] == "pass"

def test_check_statuses_never_upgrade_missing_or_ambiguous_results(results):
    checks = rows(results, "cad-checks")
    assert checks["fit · Fit"]["status"] == "pass"
    assert "physical fit not verified" in checks["fit · Fit"]["message"]
    assert checks["gone · Never written"]["status"] == "fail"
    assert "file not found" in checks["gone · Never written"]["error"]
    assert checks["vague · Truthy string"]["status"] == "fail"
    assert "not a boolean" in checks["vague · Truthy string"]["error"]
    assert checks["multi · Multi"]["status"] == "fail"
    assert "b is false" in checks["multi · Multi"]["error"]
    assert results["pass"] is False
    assert results["physical_fit_verified"] is False and results["slicer_run"] is False

def test_bad_parts_fail_with_the_reason(tmp_path):
    parts = {
        "big": {**GOOD, "print_bounds_mm": [300, 10, 10]},
        "split": {**GOOD, "solid_count": 2},
        "leaky": {**GOOD, "watertight": False},
        "unknown": {"solid_count": 1},
    }
    root = make_project(tmp_path, parts=parts)
    r = rows(report.collect(load_project(root)), "cad-parts")
    assert all(row["status"] == "fail" for row in r.values()), r
    assert "exceeds" in r["big"]["error"]
    assert "solid_count is 2" in r["split"]["error"]
    assert "not watertight" in r["leaky"]["error"]
    assert "cad_valid not recorded" in r["unknown"]["error"]

def test_missing_parts_file_and_missing_print_files_fail(tmp_path):
    root = make_project(tmp_path)
    (root / "exports" / "lid.step").unlink()
    r = report.collect(load_project(root))
    assert rows(r, "cad-print-files")["lid"]["status"] == "fail"
    (root / "exports" / "geometry-checks.json").unlink()
    r = report.collect(load_project(root))
    assert rows(r, "cad-parts")["parts file"]["status"] == "fail"
    assert r["pass"] is False

def test_broken_page_link_fails(tmp_path):
    root = make_project(tmp_path)
    (root / "preview" / "index.html").write_text('<img src="nope.png">')
    r = rows(report.collect(load_project(root)), "cad-links")
    assert r["preview/index.html"]["status"] == "fail"
    assert "nope.png" in r["preview/index.html"]["error"]

def test_write_report_is_standalone_and_valid(tmp_path):
    root = make_project(tmp_path)
    json_path, html_path, results = report.write_report(load_project(root))
    assert json_path == root.resolve() / "exports" / report.RESULTS_NAME
    assert html_path == root.resolve() / "docs" / report.REPORT_NAME
    assert json_path.name == "cad-agent-results.json" and html_path.name == "cad-agent-report.html"
    assert_schema(json.loads(json_path.read_text()))
    html = html_path.read_text()
    assert 'href="/static/' not in html and 'href=""' not in html
    assert "--" in html and "<style>" in html and "prefers-color-scheme:dark" in html
    assert "<link" not in html and "<script src" not in html
    assert "P1 · box" in html and "CAD verification only" in html and report.HONESTY_NOTE in html
    assert 'href="../exports/box.stl"' in html
    assert results["pass"] is True

def test_downloads_snippet_links_files_relative_to_the_page(tmp_path):
    root = make_project(tmp_path)
    (root / "exports" / "lid.3mf").unlink()
    html = report.downloads_snippet(load_project(root))
    assert 'href="../exports/box.stl"' in html and 'href="../exports/box.step"' in html
    assert 'data-vcad-3mf="../exports/box.3mf"' in html and 'data-vcad-name="box"' in html
    assert "3MF missing" in html
    assert 'src="part-box.png"' in html and "no render" in html
    assert "bambustudio://open?file=" in html

def test_bambu_url_requires_http_and_encodes():
    url = report.bambu_studio_url("http://127.0.0.1:8000/exports/my part.3mf", "my part")
    assert url == ("bambustudio://open?file=http%3A%2F%2F127.0.0.1%3A8000%2Fexports%2Fmy%20part.3mf"
                   "&name=my%20part")
    with pytest.raises(ValueError):
        report.bambu_studio_url("../exports/x.3mf", "x")


def test_report_rejects_changed_source_and_artifact(tmp_path):
    import hashlib
    root = make_project(tmp_path, checks_yaml='  checks:\n    - {id: fit, file: exports/fit.json}\n')
    source = root / 'input.dat'
    source.write_bytes(b'reviewed')
    output = root / 'exports/fit.json'
    for field in ('source_sha256', 'mechanical_sources', 'artifact_sha256'):
        source.write_bytes(b'reviewed')
        output.write_text(json.dumps({'pass': True, field: {'input.dat': hashlib.sha256(source.read_bytes()).hexdigest()}}))
        assert rows(report.collect(load_project(root)), 'cad-checks')['fit']['status'] == 'pass'
        source.write_bytes(b'changed')
        result = rows(report.collect(load_project(root)), 'cad-checks')['fit']
        assert result['status'] == 'fail' and 'stale' in result['message']


def test_slicer_run_only_for_current_slices(tmp_path):
    import hashlib
    root = make_project(tmp_path)
    project = load_project(root)
    sha = {n: hashlib.sha256((root / "exports" / f"{n}.3mf").read_bytes()).hexdigest() for n in ("box", "lid")}
    from cadagent.slicer import _settings
    rep = {"slicer": "Bambu Studio (command line)", **_settings(project), "total_grams": 12.5,
           "total_hours": 1.2, "parts": {n: {"grams": 6.0, "minutes": 30, "sha256": sha[n]} for n in sha}}
    path = root / "exports" / "slice-report.json"
    path.write_text(json.dumps(rep))
    results = report.collect(project)
    assert results["slicer_run"] is True and "12.5 g" in results["footer_meta"]["slicer"]
    # a different profile, a missing part or an empty report is not a current slice
    for bad in ({**rep, "process": "0.28mm Draft"}, {**rep, "parts": {"box": rep["parts"]["box"]}}, {**rep, "parts": {}}):
        path.write_text(json.dumps(bad))
        assert report.collect(project)["slicer_run"] is False
    path.write_text(json.dumps(rep))
    (root / "exports" / "lid.3mf").write_text("changed after slicing")
    results = report.collect(project)
    assert results["slicer_run"] is False and results["footer_meta"]["slicer"] == "slicer not run"
