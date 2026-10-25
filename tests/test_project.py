"""The cad: section of cad-agent.yaml (or vptest.yaml, beside vptest's own sections)."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from cadagent.project import CadConfigError, find_config, load_project

YAML = textwrap.dedent("""\
    project:
      name: widget
      display_name: Widget Enclosure
    projects:
      - name: widget-tests
        path: .
        runner: pytest
        test_args: [tests/]
    cad:
      name: widget
      title: Widget enclosure
      revision_from: cad/parameters.json:meta.revision
      printer: {name: Test printer, bed_mm: [220, 220, 250]}
      steps:
        - {name: build, run: cad/build.py, log: build.log}
        - name: check
          run: tools/check.py
          timeout_s: 60
          needs: [build]
      part_ids: {base: P1}
      checks:
        - {id: fit, title: Fit check, file: exports/fit.json}
        - id: review
          title: Review
          file: exports/review.json
          pass_key: [a.ok, b]
          evidence: [preview/fit.png]
          links: [docs/notes.html, {url: docs/x.csv, label: X}]
      package: {include: ["exports/*.stl"]}
      html_pages: [preview/index.html]
      colour_scheme: blue
    """)

@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / "cad-agent.yaml").write_text(YAML)
    (tmp_path / "cad").mkdir()
    (tmp_path / "cad" / "parameters.json").write_text(json.dumps({"meta": {"revision": "0.7"}}))
    return tmp_path

def test_full_section_loads(project_root):
    p = load_project(project_root)
    assert p.name == "widget" and p.title == "Widget enclosure"
    assert p.resolve_revision() == "0.7"
    assert p.printer.bed_mm == (220.0, 220.0, 250.0)
    assert [s.name for s in p.steps] == ["build", "check"]
    assert p.steps[0].log == "build.log" and p.steps[0].timeout_s == 1800
    assert p.steps[1].timeout_s == 60 and p.steps[1].needs == ["build"]
    assert p.checks[0].pass_keys == ["pass"]
    assert p.checks[1].pass_keys == ["a.ok", "b"]
    assert p.checks[1].links == [{"url": "docs/notes.html", "label": "docs/notes.html"},
                                 {"url": "docs/x.csv", "label": "X"}]
    assert p.part_label("base") == "P1 · base" and p.part_label("lid_top") == "lid top"
    assert p.unknown_keys == ["colour_scheme"]

def test_defaults(tmp_path):
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: bare\n")
    p = load_project(tmp_path)
    root = tmp_path.resolve()
    assert p.exports_dir == root / "exports"
    assert p.preview_dir == root / "preview"
    assert p.docs_dir == root / "docs"
    assert p.parts_file == root / "exports" / "geometry-checks.json"
    assert p.python == sys.executable
    assert p.steps == [] and p.checks == [] and p.printer.bed_mm is None
    assert (p.serve.host, p.serve.port) == ("127.0.0.1", 0)
    assert p.resolve_revision() is None

def test_project_venv_python_is_the_default_when_present(tmp_path):
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: v\n")
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    assert load_project(tmp_path).python == str(venv_python.resolve())

def test_literal_revision_wins_and_missing_revision_file_is_unknown(tmp_path):
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  revision_from: cad/p.json:revision\n")
    assert load_project(tmp_path).resolve_revision() is None
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  revision: '3'\n  revision_from: cad/p.json:revision\n")
    assert load_project(tmp_path).resolve_revision() == "3"

@pytest.mark.parametrize(
    "cad, match",
    [
        ("  revision_from: no-colon.json\n", "revision_from"),
        ("  steps:\n    - {name: a}\n", "'name' and 'run'"),
        ("  steps:\n    - {name: a, run: a.py}\n    - {name: a, run: b.py}\n", "duplicate"),
        ("  steps:\n    - {name: a, run: a.py, needs: [b]}\n    - {name: b, run: b.py}\n", "earlier step"),
        ("  checks:\n    - {id: x}\n", "'id' and 'file'"),
        ("  printer: {bed_mm: [1]}\n", "bed_mm"),
        ("  steps: build.py\n", "must be a list"),
    ],
)
def test_malformed_sections_are_rejected_with_the_reason(tmp_path, cad, match):
    (tmp_path / "cad-agent.yaml").write_text("cad:\n" + cad)
    with pytest.raises(CadConfigError, match=match):
        load_project(tmp_path)

def test_missing_config_or_section_is_an_error(tmp_path):
    with pytest.raises(CadConfigError, match="not found"):
        load_project(tmp_path)
    (tmp_path / "cad-agent.yaml").write_text("project:\n  name: x\n")
    with pytest.raises(CadConfigError, match="no cad: section"):
        load_project(tmp_path)

def test_vptest_yaml_is_read_beside_its_other_sections(tmp_path):
    (tmp_path / "vptest.yaml").write_text(YAML)
    p = load_project(tmp_path)
    assert p.name == "widget" and [s.name for s in p.steps] == ["build", "check"]
    assert p.unknown_keys == ["colour_scheme"]

def test_cad_agent_yaml_wins_over_vptest_yaml(tmp_path):
    (tmp_path / "vptest.yaml").write_text("cad:\n  name: old\n")
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: new\n")
    assert find_config(tmp_path.resolve()) == tmp_path.resolve() / "cad-agent.yaml"
    assert load_project(tmp_path).name == "new"

def test_first_config_found_is_the_config(tmp_path):
    (tmp_path / "vptest.yaml").write_text("cad:\n  name: old\n")
    (tmp_path / "cad-agent.yaml").write_text("other: {}\n")
    with pytest.raises(CadConfigError, match="cad-agent.yaml has no cad: section"):
        load_project(tmp_path)
