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

from .test_report import make_project

def write_steps_project(root: Path, fail_at: str = "") -> Path:
    (root / "tools").mkdir(parents=True)
    for name in ("one", "two", "three"):
        code = "import sys; print('running %s'); " % name
        code += "sys.exit(3)" if name == fail_at else (
            f"import os; open('exports/{name}.done', 'w').write(os.environ['CAD_AGENT_PROJECT'] + '|' "
            "+ os.environ['VPTEST_CAD_PROJECT'])")
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
    assert set(sub.choices) == {"build", "export-3mf", "check", "report", "package", "serve", "site", "view", "slice", "webkit", "all",
                                "mcmaster", "catalogue", "compare", "optimise"}
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
    assert err.startswith("cad-agent: check:") and "cad-agent.yaml" in err and "vptest.yaml" in err
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
    from cadagent.serve import make_server

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

def test_vptest_yaml_still_works(tmp_path, capsys):
    root = make_project(tmp_path)
    (root / "cad-agent.yaml").rename(root / "vptest.yaml")
    assert main(["check", "--project", str(root)]) == 0

def test_module_runs_as_a_script(tmp_path):
    import subprocess

    root = make_project(tmp_path)
    src = Path(__file__).resolve().parents[1] / "src"
    proc = subprocess.run([sys.executable, "-m", "cadagent.cli", "check", "--project", str(root)],
                          capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(src)))
    assert proc.returncode == 0, proc.stderr
    assert "0 fail" in proc.stdout


def test_slice_reports_a_part_without_a_print_time(tmp_path, monkeypatch, capsys):
    from cadagent import cli, slicer
    monkeypatch.setattr(slicer, "executable", lambda: "/bin/true")
    monkeypatch.setattr(slicer, "slice_project", lambda project, parts=None: {
        "parts": {"box": {"grams": 5.0, "minutes": None}}, "total_grams": 5.0, "total_hours": 0.0,
        "process": "p", "filament": "f", "path": "x", "pass": True})
    assert cli.cmd_slice(None, type("A", (), {"parts": []})()) == 0
    assert "time not reported" in capsys.readouterr().out
