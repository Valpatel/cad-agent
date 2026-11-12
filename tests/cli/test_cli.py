"""`cad-agent ...` end to end through cadagent.cli.main, on throwaway projects."""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

from cadagent.cli import SUBCOMMANDS, build_parser, main

from tests.publish.test_report import make_project

def write_steps_project(root: Path, fail_at: str = "") -> Path:
    (root / "tools").mkdir(parents=True)
    for name in ("one", "two", "three"):
        code = "import sys; print('running %s'); " % name
        code += "sys.exit(3)" if name == fail_at else (
            f"import os; open('exports/{name}.done', 'w').write(os.environ['CAD_AGENT_PROJECT'] + '|' "
            "+ os.getcwd())")
        (root / "tools" / f"{name}.py").write_text(code + "\n")
    (root / "exports").mkdir()
    (root / "cad-agent.yaml").write_text(textwrap.dedent(f"""\
        cad:
          name: steps
          python: {sys.executable}
          steps:
            - {{name: one, run: tools/one.py, log: one.log}}
            - {{name: two, run: tools/two.py, log: two.log, needs: [one]}}
            - {{name: three, run: tools/three.py}}
        """))
    return root

def done(root: Path):
    return sorted(p.stem for p in (root / "exports").glob("*.done"))

def test_parser_exposes_every_subcommand():
    parser = build_parser()
    assert parser.prog == "cad-agent"
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert set(sub.choices) == {"build", "export-3mf", "holes", "check", "report", "package", "serve", "site", "view", "slice", "prusa-view", "webkit",
                                "pcb-check", "all", "mcmaster", "catalogue", "compare", "optimise", "dossier",
                                "gates", "review-packet", "review-section", "agents", "update", "motion-trace", "release", "snapfit",
                                "inserts", "bearings", "overhangs", "library", "init", "rules", "choose", "bambu-status"}
    assert set(sub.choices) == set(SUBCOMMANDS)
    args = parser.parse_args(["build", "--project", "/p", "--from", "two", "--only", "two", "three"])
    assert (args.cad_command, args.project, args.from_step, args.only) == ("build", "/p", "two", ["two", "three"])
    assert parser.parse_args(["--project", "/q", "check", "--json"]).project == "/q"
    assert parser.parse_args(["check"]).project is None
    args = parser.parse_args(["serve", "--port", "8123", "--host", "0.0.0.0"])
    assert (args.port, args.host) == (8123, "0.0.0.0")
    assert parser.parse_args(["report", "--open"]).open is True

def test_build_runs_steps_in_order_with_logs(tmp_path, capsys):
    root = write_steps_project(tmp_path)
    assert main(["build", "--project", str(root)]) == 0
    assert done(root) == ["one", "three", "two"]
    assert (root / "exports" / "one.done").read_text() == f"{root.resolve()}|{root.resolve()}"
    assert "running one" in (root / "exports" / "one.log").read_text()
    out = capsys.readouterr().out
    assert "[1/3] one" in out and "build ok: 3 step(s)" in out

def test_build_stops_at_the_first_failure_with_exit_1(tmp_path, capsys):
    root = write_steps_project(tmp_path, fail_at="two")
    assert main(["build", "--project", str(root)]) == 1
    assert done(root) == ["one"]
    out = capsys.readouterr().out
    assert "FAILED two" in out and "exit code 3" in out and "running two" in out
    assert "three" not in out.split("FAILED two")[1].split("build stopped")[0]

def test_build_from_and_only(tmp_path, capsys):
    root = write_steps_project(tmp_path)
    assert main(["build", "--project", str(root), "--from", "two"]) == 0
    assert done(root) == ["three", "two"]
    for p in (root / "exports").glob("*.done"):
        p.unlink()
    assert main(["build", "--project", str(root), "--only", "three"]) == 0
    assert done(root) == ["three"]
    assert main(["build", "--project", str(root), "--only", "nope"]) == 2

def test_missing_script_fails_the_build(tmp_path, capsys):
    root = write_steps_project(tmp_path)
    (root / "tools" / "two.py").unlink()
    assert main(["build", "--project", str(root)]) == 1
    assert "script not found" in capsys.readouterr().out

def test_unusable_project_exits_2(tmp_path, capsys):
    assert main(["check", "--project", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("cad-agent: check:") and "cad-agent.yaml not found" in err and "rename" not in err
    assert main(["--project", str(tmp_path)]) == 2
    assert "cad-agent --help" in capsys.readouterr().err

def test_check_exit_code_follows_the_results(tmp_path, capsys):
    root = make_project(tmp_path)
    assert main(["check", "--project", str(root)]) == 0
    assert "physical fit not verified" in capsys.readouterr().out
    assert main(["check", "--project", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pass"] is True
    (root / "exports" / "lid.stl").unlink()
    assert main(["check", "--project", str(root)]) == 1
    assert "FAIL" in capsys.readouterr().out


@pytest.mark.parametrize('command', ['check', 'report', 'all'])
@pytest.mark.parametrize('invalid', ['json', 'missing-slicer', 'numeric-slicer', 'warnings', 'code', 'code-without-ok'])
def test_persisted_invalid_slice_fails_check_report_and_all(tmp_path, monkeypatch, capsys, command, invalid):
    from cadagent import cli
    import hashlib
    from cadagent.project import load_project
    from cadagent.manufacturing.slicer import _settings
    root = make_project(tmp_path)
    # Keep the all orchestration and real report; replace the unrelated build/native/package steps.
    for name in ('cmd_build', 'cmd_export_3mf', 'cmd_holes', 'cmd_package'):
        monkeypatch.setattr(cli, name, lambda project, args: 0)
    path = root / 'exports/slice-report.json'
    data = {'slicer': 'Bambu Studio (command line)', **_settings(load_project(root)),
            'total_grams': 8, 'total_hours': 0.5,
            'parts': {name: {'grams': 4, 'ok': True, 'exit_code': 0, 'return_code': 0,
                             'sha256': hashlib.sha256((root / 'exports' / f'{name}.3mf').read_bytes()).hexdigest()}
                      for name in ('box', 'lid')}}
    if invalid == 'missing-slicer':
        del data['slicer']
    elif invalid == 'numeric-slicer':
        data['slicer'] = 1
    elif invalid == 'warnings':
        data['parts']['lid']['warnings'] = 5
    elif invalid in ('code', 'code-without-ok'):
        data['parts']['lid']['return_code'] = -17
        if invalid == 'code-without-ok':
            del data['parts']['lid']['ok']
    path.write_text('{' if invalid == 'json' else json.dumps(data))
    assert main([command, '--project', str(root)]) == 1
    output = capsys.readouterr().out
    assert 'FAIL' in output and 'slicer not run' not in output
    assert ('return_code -17' if invalid in ('code', 'code-without-ok') else 'slice again with cad-agent slice') in output
    path.unlink()
    assert main([command, '--project', str(root)]) == 0

def test_report_and_package(tmp_path, capsys):
    root = make_project(tmp_path)
    with open(root / "cad-agent.yaml", "a") as fh:
        fh.write("  package: {name: demo-review, include: ['exports/*.stl', 'exports/*.json', 'nothing/*']}\n")
    assert main(["report", "--project", str(root)]) == 0
    assert (root / "docs" / "cad-agent-report.html").is_file()
    assert main(["package", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "matched nothing: nothing/*" in out
    zip_path = root / "exports" / "demo-review.zip"
    manifest = json.loads((root / "exports" / "demo-review-manifest.json").read_text())
    assert "exports/box.stl" in manifest and "exports/cad-agent-results.json" in manifest
    with zipfile.ZipFile(zip_path) as z:
        assert set(manifest) | {"exports/demo-review-manifest.json"} == set(z.namelist())

def test_export_3mf_without_trimesh_says_so(tmp_path, capsys, monkeypatch):
    root = make_project(tmp_path)
    monkeypatch.setitem(sys.modules, "trimesh", None)
    assert main(["export-3mf", "--project", str(root)]) == 2
    assert "needs 'trimesh'" in capsys.readouterr().err

def test_serve_binds_and_records_the_url(tmp_path):
    from urllib.request import urlopen
    import threading

    from cadagent.project import load_project
    from cadagent.publish.serve import make_server

    root = make_project(tmp_path)
    server, url = make_server(load_project(root), port=0)
    try:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        assert url.startswith("http://127.0.0.1:") and url.endswith("/preview/")
        assert (root / "preview" / "server-url.txt").read_text().strip() == url
        assert urlopen(url + "index.html", timeout=5).read().startswith(b"<a href")
    finally:
        server.shutdown()
        server.server_close()

def test_a_cad_section_under_another_file_name_is_named_not_read(tmp_path, capsys):
    root = make_project(tmp_path)
    (root / "cad-agent.yaml").rename(root / "project.yaml")
    assert main(["check", "--project", str(root)]) == 2
    err = capsys.readouterr().err
    assert "cad-agent.yaml not found" in err
    assert "project.yaml has a cad: section but only cad-agent.yaml is read: rename it to cad-agent.yaml" in err

def test_module_runs_as_a_script(tmp_path):
    import subprocess

    root = make_project(tmp_path)
    src = Path(__file__).resolve().parents[2] / "software"
    proc = subprocess.run([sys.executable, "-m", "cadagent.cli", "check", "--project", str(root)],
                          capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(src)))
    assert proc.returncode == 0, proc.stderr
    assert "0 fail" in proc.stdout


def test_slice_reports_a_part_without_a_print_time(tmp_path, monkeypatch, capsys):
    from cadagent import cli
    from cadagent.manufacturing import slicer
    monkeypatch.setattr(slicer, "executable", lambda: "/bin/true")
    monkeypatch.setattr(slicer, "slice_project", lambda project, parts=None: {
        "parts": {"box": {"grams": 5.0, "minutes": None}}, "total_grams": 5.0, "total_hours": 0.0,
        "process": "p", "filament": "f", "path": "x", "pass": True})
    assert cli.cmd_slice(None, type("A", (), {"parts": []})()) == 0
    assert "time not reported" in capsys.readouterr().out


# ----------------------------------------------------------------------------------------- cad-agent dossier (T2)

def _dossier_project(root: Path) -> Path:
    from tests.review.test_dossier_lint import make_project as make_dossier_project
    return make_dossier_project(root)


def test_dossier_writes_status_and_verdict(tmp_path, capsys):
    root = _dossier_project(tmp_path)
    assert main(["dossier", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "GATED      S1  Store" in out and "0 error(s)" in out
    status = json.loads((root / "exports" / "dossier-status.json").read_text())
    assert status["pass"] is True and status["sections"]["S1"]["status"] == "gated"
    verdict = json.loads((root / "exports" / "gates" / "dossier-lint.json").read_text())
    assert verdict["schema"] == "cadagent.gate/1" and verdict["pass"] is True


def test_dossier_fails_with_file_line_and_code(tmp_path, capsys):
    root = _dossier_project(tmp_path)
    path = root / "dossier" / "sections" / "store.yaml"
    path.write_text(path.read_text().replace("why: prints flat", "why: ''"))
    assert main(["dossier", "--project", str(root)]) == 1
    out = capsys.readouterr().out
    assert "decision-incomplete" in out and "dossier/sections/store.yaml:" in out
    assert json.loads((root / "exports" / "gates" / "dossier-lint.json").read_text())["pass"] is False


def test_dossier_min_status_json_and_no_write(tmp_path, capsys):
    root = _dossier_project(tmp_path)
    (root / "exports" / "gates" / "wall.json").unlink()
    assert main(["dossier", "--project", str(root), "--no-write"]) == 1          # hopper: gate:wall unrun
    assert not (root / "exports" / "dossier-status.json").exists()
    capsys.readouterr()
    assert main(["dossier", "--project", str(root), "--min-status", "none", "--json", "--no-write"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["parts"]["hopper"]["status"] == "built" and data["required_section_status"] is None


def test_dossier_without_a_dossier_key_is_unusable(tmp_path, capsys):
    make_project(tmp_path)
    assert main(["dossier", "--project", str(tmp_path)]) == 2
    assert "no dossier" in capsys.readouterr().err


def test_check_runs_the_dossier_lint(tmp_path, capsys):
    from tests.publish.test_report import GOOD
    root = _dossier_project(tmp_path)
    (root / "exports" / "geometry-checks.json").write_text(json.dumps({"box": GOOD}))
    for ext in ("stl", "3mf", "step"):
        (root / "exports" / f"box.{ext}").write_text("x")
    from tests.publish.test_report import bind_holes
    bind_holes(root, ["box"])
    from tests.review.test_gates_cli import bind_verdicts
    bind_verdicts(root)                       # as `cad-agent gates` writes them: bound to the current inputs
    assert main(["check", "--project", str(root), "--json"]) == 0
    results = json.loads(capsys.readouterr().out)
    gates = next(f for f in results["features"] if f["feature_id"] == "cad-gates")
    assert {c["name"]: c["status"] for c in gates["checks"]} == {
        "gate connectivity": "pass", "gate containment": "pass", "gate fasteners": "pass",
        "gate motion": "skip", "gate assembly": "pass", "gate wall": "pass"}
    feature = next(f for f in results["features"] if f["feature_id"] == "cad-dossier")
    names = {c["name"]: c["status"] for c in feature["checks"]}
    assert names == {"dossier lint": "pass", "section S1 · Store": "pass"}
    path = root / "dossier" / "sections" / "store.yaml"
    path.write_text(path.read_text().replace("function: Closes the hopper", "function: ''"))
    assert main(["check", "--project", str(root)]) == 1
    out = capsys.readouterr().out
    assert "dossier card-no-function" in out and "section S1" in out


def test_slice_without_prusaslicer_is_unusable(tmp_path, monkeypatch, capsys):
    from cadagent.manufacturing import slicer_prusa
    root = make_project(tmp_path)
    (root / "cad-agent.yaml").write_text((root / "cad-agent.yaml").read_text() + "  slicer: {engine: prusa}\n")
    monkeypatch.setattr(slicer_prusa, "executable", lambda: None)
    assert main(["slice", "--project", str(root)]) == 2
    captured = capsys.readouterr()
    assert "PrusaSlicer is not installed" in captured.out + captured.err


@pytest.mark.parametrize("slicer_cfg, said", [
    ("{engine: cura}", "cad.slicer.engine must be one of bambu, prusa, got 'cura'"),
    ("{engine: prusa, printer: Test MK4S, process: 0.20mm TEST, filament: Test PLA, overrides: {wall_loops: '3'}}",
     "cannot slice: Unknown PrusaSlicer setting(s) 'wall_loops'"),
    ("{engine: prusa, printer: Test MK4S, process: 0.20mm TSET, filament: Test PLA}",
     "cannot slice: PrusaSlicer print profile '0.20mm TSET' not found"),
])
def test_slice_config_errors_exit_2_with_the_reason(tmp_path, monkeypatch, capsys, slicer_cfg, said):
    import shutil
    from cadagent.manufacturing import slicer_prusa
    from tests.manufacturing.test_slicer_prusa import FIXTURE, fake_run
    shutil.copytree(FIXTURE, tmp_path / "PrusaSlicer")
    monkeypatch.setenv("CADAGENT_PRUSA_PROFILES", str(tmp_path / "PrusaSlicer" / "vendor"))
    root = make_project(tmp_path / "p")
    (root / "cad-agent.yaml").write_text((root / "cad-agent.yaml").read_text() + f"  slicer: {slicer_cfg}\n")
    monkeypatch.setattr(slicer_prusa, "executable", lambda: ["/fake/prusa-slicer"])
    monkeypatch.setattr(slicer_prusa.subprocess, "run", fake_run([]))
    assert main(["slice", "--project", str(root)]) == 2
    captured = capsys.readouterr()
    assert said in captured.out + captured.err


@pytest.mark.parametrize("command", ["report", "check"])
def test_a_misspelt_engine_is_a_config_error_everywhere(tmp_path, capsys, command):
    root = make_project(tmp_path)
    (root / "cad-agent.yaml").write_text((root / "cad-agent.yaml").read_text() + "  slicer: {engine: Prusa}\n")
    assert main([command, "--project", str(root)]) == 2
    captured = capsys.readouterr()
    assert "cad.slicer.engine" in captured.out + captured.err


def test_slice_lists_what_prusaslicer_said_and_exits_1_when_a_part_is_not_ok(tmp_path, monkeypatch, capsys):
    from cadagent.manufacturing import slicer, slicer_prusa
    monkeypatch.setattr(slicer_prusa, "executable", lambda: ["/fake/prusa-slicer"])
    monkeypatch.setattr(slicer, "engine_of", lambda project: "prusa")
    rows = {"box": {"grams": 5.0, "minutes": 10.0, "ok": True, "warnings": [], "errors": [], "stability_issues": []},
            "lid": {"grams": 7.0, "minutes": 12.0, "ok": False, "stability_issues": ["Floating bridge anchors"],
                    "warnings": ["Detected print stability issues:"],
                    "errors": ["gcode path conflicts found between WipeTower and lid.stl"]}}
    monkeypatch.setattr(slicer, "slice_project", lambda project, parts=None: {
        "parts": rows, "total_grams": 12.0, "total_hours": 0.4, "process": "p", "filament": "f", "path": "x",
        "pass": False})
    assert cli_cmd_slice() == 1
    out = capsys.readouterr().out
    assert "NOT OK" in out and "stability: Floating bridge anchors" in out
    assert "error: gcode path conflicts found between WipeTower and lid.stl" in out
    assert "warning: Detected print stability" not in out and "not ok" in out and ": lid" in out


def cli_cmd_slice():
    from cadagent import cli
    return cli.cmd_slice(None, type("A", (), {"parts": []})())


@pytest.mark.parametrize("parts, said", [
    ("{box: {overrides: [1]}}", "cad.slicer.parts.box.overrides must be a mapping"),
    ("{box: {brim: 3}}", "cad.slicer.parts.box: unknown keys ['brim']"),
    ("box", "cad.slicer.parts must be a list of part names or a mapping"),
])
def test_bad_part_overrides_are_config_errors(tmp_path, capsys, parts, said):
    root = make_project(tmp_path)
    (root / "cad-agent.yaml").write_text((root / "cad-agent.yaml").read_text() + f"  slicer: {{parts: {parts}}}\n")
    assert main(["slice", "--project", str(root)]) == 2
    captured = capsys.readouterr()
    assert said in captured.out + captured.err


def test_library_build_and_audit_from_the_command_line(tmp_path, capsys):
    """`cad-agent library build --no-models` writes footprints whose model paths are relative to the project, and
    `library audit` fails on the missing models, then passes once a waiver covers a footprint with no model."""
    from cadagent.cli import main
    proj = tmp_path / "board"
    assert main(["library", "build", str(proj / "lib"), "--project", str(proj), "--no-models",
                 "--parts", "lug_stud_m4", "slot_4x10"]) == 0
    text = next((proj / "lib" / "cad-agent.pretty").glob("LugStud_M4*")).read_text()
    assert '(model "${KIPRJMOD}/lib/cad-agent.3dshapes/LugStud_M4.step"' in text
    assert main(["library", "audit", str(proj / "lib" / "cad-agent.pretty")]) == 1
    out = capsys.readouterr().out
    assert "missing_model" in out and "no_model" in out
    (proj / "lib" / "cad-agent.3dshapes").mkdir()
    (proj / "lib" / "cad-agent.3dshapes" / "LugStud_M4.step").write_text("ISO-10303-21;")
    # a library alone has no project: ${KIPRJMOD} is the folder holding the .pretty unless --env names the project
    assert main(["library", "audit", str(proj / "lib" / "cad-agent.pretty"), "--waive", "Slot_*=a hole",
                 "--env", f"KIPRJMOD={proj}", "--output", str(tmp_path / "audit.json")]) == 0
    assert json.loads((tmp_path / "audit.json").read_text())["waived"][0]["reason"] == "a hole"
    assert main(["library", "build", str(tmp_path / "x"), "--no-models", "--parts", "nope"]) == 2


def _write_torsion_project_check(root, monkeypatch):
    """Actual CLI child, through the existing configured step/check contract (not a new project schema)."""
    from tests.mechanical.test_snapfit import _torsion_spec
    import yaml
    config = yaml.safe_load((root / "cad-agent.yaml").read_text())
    config["cad"]["python"] = sys.executable
    config["cad"].setdefault("steps", []).append({"name": "torsion", "run": "tools/check_torsion.py"})
    config["cad"].setdefault("checks", []).append({"id": "torsion", "title": "Cover rocker",
                                                    "file": "exports/torsion.json"})
    (root / "cad-agent.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    (root / "tools").mkdir(exist_ok=True)
    import re
    guide = (Path(__file__).resolve().parents[2] / "docs/mechanical/compliant.md").read_text()
    section = guide.split("## Declaring a rectangular torsion snap\n", 1)[1].split("## Materials", 1)[0]
    declared = yaml.safe_load(re.search(r"```yaml\n(.*?)```", section, re.S).group(1))
    assert declared == {"snaps": [_torsion_spec()]}, "the actual published guide is the checked declaration"
    (root / "tools" / "check_torsion.py").write_text(re.search(r"```python\n(.*?)```", section, re.S).group(1))
    spec = root / "torsion.yaml"
    spec.write_text(yaml.safe_dump(declared))
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2] / "software"))
    return spec


def test_torsion_cli_and_real_project_step_report_reject_bad_and_missing_result(tmp_path, monkeypatch, capsys):
    import yaml
    root = make_project(tmp_path)
    spec = _write_torsion_project_check(root, monkeypatch)
    assert main(["snapfit", str(spec), "--output", str(root / "exports/torsion.json")]) == 0
    out = capsys.readouterr().out
    assert "shear strain 1.11 % (allowed 1.28 %)" in out and "root strain" not in out
    assert main(["build", "--project", str(root)]) == 0
    assert main(["report", "--project", str(root)]) == 0
    results = json.loads((root / "exports/cad-agent-results.json").read_text())
    checks = next(f["checks"] for f in results["features"] if f["feature_id"] == "cad-checks")
    assert checks[0]["status"] == "pass"
    assert not results["physical_fit_verified"]
    declared = yaml.safe_load(spec.read_text())
    declared["snaps"][0]["twist_deg"] = 12
    spec.write_text(yaml.safe_dump(declared))
    assert main(["build", "--project", str(root)]) == 1
    assert json.loads((root / "exports/torsion.json").read_text())["pass"] is False
    assert main(["check", "--project", str(root)]) == 1
    # Invalid units remove the previous report before the child fails, so the project cannot reuse a stale pass.
    declared["snaps"][0]["twist_rad"] = 0.1
    spec.write_text(yaml.safe_dump(declared))
    assert main(["build", "--project", str(root)]) == 1
    assert not (root / "exports/torsion.json").exists()
    capsys.readouterr()
    assert main(["check", "--project", str(root), "--json"]) == 1
    missing = json.loads(capsys.readouterr().out)
    row = next(f["checks"][0] for f in missing["features"] if f["feature_id"] == "cad-checks")
    assert row["status"] == "fail" and "file not found" in row["error"]


def test_torsion_declaration_actual_all_in_existing_starter(tmp_path, monkeypatch, capsys):
    """The full-extra CI runs actual starter CAD/export/report plus the new existing-contract check."""
    pytest.importorskip("cadquery")
    pytest.importorskip("trimesh")
    pytest.importorskip("scipy")
    root = tmp_path / "box"
    assert main(["init", str(root)]) == 0
    _write_torsion_project_check(root, monkeypatch)
    assert main(["all", "--project", str(root)]) == 0, capsys.readouterr().out
    results = json.loads((root / "exports/cad-agent-results.json").read_text())
    checks = next(f["checks"] for f in results["features"] if f["feature_id"] == "cad-checks")
    assert any(v["name"].startswith("torsion") and v["status"] == "pass" for v in checks)
    assert results["pass"] and not results["physical_fit_verified"]


# ------------------------------------------------------------------------- parts that are not printed (#577)

def _mixed(tmp_path, extra=""):
    """box and lid are printed (real STLs); frame is welded and has no STL."""
    trimesh = pytest.importorskip("trimesh")
    from tests.publish.test_report import GOOD
    root = make_project(tmp_path, parts={"box": dict(GOOD), "lid": dict(GOOD), "frame": dict(GOOD)},
                        checks_yaml="  part_process: {frame: weldment}\n" + extra)
    for name in ("box", "lid"):
        trimesh.creation.box(extents=(10, 10, 10)).export(root / "exports" / f"{name}.stl")
    for ext in ("stl", "3mf"):
        (root / "exports" / f"frame.{ext}").unlink()
    return root


def test_export_3mf_leaves_out_a_part_that_is_not_printed(tmp_path, capsys):
    root = _mixed(tmp_path)
    assert main(["export-3mf", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "not printed, no per-part 3MF written: frame" in out and "2 3MF file(s) written" in out
    assert not (root / "exports" / "frame.3mf").exists()
    plates = json.loads((root / "exports" / "demo-plates.json").read_text())
    assert sorted(plates["quantities"]) == ["box", "lid"]
    assert any("not printed, left off the plates: frame" in w for w in plates["warnings"])
    assert main(["check", "--project", str(root)]) == 0         # the frame's rows are skips, not failures
    out = capsys.readouterr().out
    assert out.count("SKIP  frame") == 2 and "0 fail" in out


def test_all_finishes_on_a_project_with_no_printed_part(tmp_path, monkeypatch, capsys):
    """The welded machine with bought parts: no bed, no STL, no trimesh needed, and `all` reaches its report."""
    from cadagent import cli
    root = make_project(tmp_path, checks_yaml='  part_process: {"*": weldment, lid: purchased}\n')
    cfg = root / "cad-agent.yaml"
    cfg.write_text(cfg.read_text().replace("  printer: {name: Bed, bed_mm: [256, 256, 256]}\n", ""))
    for name in ("box", "lid"):
        for ext in ("stl", "3mf"):
            (root / "exports" / f"{name}.{ext}").unlink()
    monkeypatch.setitem(sys.modules, "trimesh", None)
    assert main(["export-3mf", "--project", str(root)]) == 0
    assert "no printed part: no per-part 3MF written" in capsys.readouterr().out
    assert main(["export-3mf", "--project", str(root), "--require-project-settings"]) == 1
    for name in ("cmd_build", "cmd_holes", "cmd_package"):      # unrelated steps; the export and the report are real
        monkeypatch.setattr(cli, name, lambda project, args: 0)
    assert main(["all", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "0 fail" in out and "SKIP" in out and "welded fabrication" in out and "bought, not made" in out
    results = json.loads((root / "exports" / "cad-agent-results.json").read_text())
    status = {f["feature_id"]: [c["status"] for c in f["checks"]] for f in results["features"]}
    assert status["cad-parts"] == status["cad-print-files"] == ["skip", "skip"] and results["pass"] is True


def test_overhangs_screens_the_printed_parts_unless_one_is_named(tmp_path, capsys):
    root = _mixed(tmp_path)
    assert main(["overhangs", "--project", str(root)]) == 0
    assert "not printed, not screened: frame" in capsys.readouterr().out
    assert sorted(json.loads((root / "exports" / "overhang-screen.json").read_text())["parts"]) == ["box", "lid"]
    assert main(["overhangs", "--project", str(root), "frame"]) == 1       # asked for by name: it has no STL
    assert "frame.stl not found" in capsys.readouterr().out
