"""``cad-agent gates`` (plan T14): configuration, the plan of which gates apply, the worker processes, the verdict
files, staleness, ``check``/``report`` rows, ``all`` and the site stat.

The first part needs no CAD kernel: the project is the dossier lint's fixture (a geometry record as JSON) and the
gate workers are replaced by a small script that writes verdicts the way ``run_one`` does. The end-to-end part at
the bottom runs the real gates on the gate-bench project (``tests/fixtures/gate_bench/project``) and skips without
CadQuery.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import textwrap
import time
import types
from pathlib import Path
from typing import Iterable, Optional

import pytest

from cadagent import cli
from cadagent.cli import main
from cadagent.review.gates import run as gr
from cadagent.project import load_project

from . import test_dossier_registry as reg_fixture
from .test_dossier_lint import base_geometry, make_project


def bind_verdicts(root: Path, gates: Optional[Iterable[str]] = None, failing: Iterable[str] = ()) -> None:
    """Write a verdict for every gate the plan runs (or ``gates``), bound to the current inputs, as
    ``cad-agent gates`` would: one passing check, or one failing check naming ``lid`` for gates in ``failing``."""
    project = load_project(root)
    cfg = gr.gates_config(project)
    record, extra, dossier = gr.load_record(cfg), gr.load_extra(cfg), gr.load_dossier(project)
    names = list(gates) if gates is not None else [p.gate for p in gr.plan(project, cfg, record, dossier, extra)
                                                   if p.state == "run" and p.gate != gr.LINT]
    for g in names:
        bad = g in set(failing)
        data = gr.verdict(g, [gr.Check(f"{g}:x", "fail" if bad else "pass", "bad" if bad else "ok",
                                       parts=["lid"] if bad else ())], assumptions=["a test verdict"])
        gr.bind_inputs(data, record, record_file=cfg.rel(cfg.geometry), **gr.expected_inputs(g, cfg, dossier, extra))
        gr.write_outputs(project.exports_dir / "gates", data)


FAKE_WORKER = textwrap.dedent('''
    """A stand-in for `python -m cadagent.review.gates.run <root> <gate>`: writes the verdict run_one would, no
    kernel."""
    import os, sys, time
    from pathlib import Path
    from cadagent.review.gates import run as gr
    from cadagent.project import load_project
    root, gate = sys.argv[1], sys.argv[2]
    mode = os.environ.get("FAKE_GATE_MODE", "pass")
    target = os.environ.get("FAKE_GATE_TARGET", "")
    Path(root, "exports", f"started-{gate}").write_text(str(time.time()))
    if os.environ.get("FAKE_GATE_SLEEP"):
        time.sleep(float(os.environ["FAKE_GATE_SLEEP"]))
    if target in ("", gate) and mode == "crash":
        print("boom: the kernel fell over"); sys.exit(3)
    project = load_project(root)
    cfg = gr.gates_config(project)
    record, extra, dossier = gr.load_record(cfg), gr.load_extra(cfg), gr.load_dossier(project)
    bad = target in ("", gate) and mode == "fail"
    data = gr.verdict(gate, [gr.Check(f"{gate}:x", "fail" if bad else "pass", "bad" if bad else "ok",
                                      parts=["lid"] if bad else ())], assumptions=["a fake gate"])
    gr.bind_inputs(data, record, record_file=cfg.rel(cfg.geometry), **gr.expected_inputs(gate, cfg, dossier, extra))
    gr.write_outputs(Path(project.exports_dir) / "gates", data)
    Path(root, "exports", f"ended-{gate}").write_text(str(time.time()))
    sys.exit(0 if data["pass"] else 1)
''')


@pytest.fixture
def project(tmp_path, monkeypatch):
    """The lint fixture project with no verdicts, and gate workers replaced by FAKE_WORKER."""
    root = make_project(tmp_path / "p", gates=())
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER)
    monkeypatch.setattr(gr, "worker_command", lambda r, g, no_cache=False: [sys.executable, str(script), str(r), g])
    return root


def _config(root: Path, text: str) -> None:
    path = root / "cad-agent.yaml"
    path.write_text(path.read_text() + textwrap.indent(textwrap.dedent(text), "  "))


def _results(root: Path, capsys):
    capsys.readouterr()
    main(["check", "--project", str(root), "--json"])
    out = json.loads(capsys.readouterr().out)
    return {c["name"]: c for f in out["features"] if f["feature_id"] == "cad-gates" for c in f["checks"]}


# ----------------------------------------------------------------------------------------------- configuration

def test_config_defaults_and_paths(tmp_path):
    root = make_project(tmp_path)
    cfg = gr.gates_config(load_project(root))
    assert cfg.geometry == (root / "exports" / "dossier-geometry.json").resolve()
    assert (cfg.jobs, cfg.timeout_s, cfg.build, cfg.declarations) == (1, 3600, None, None)
    assert cfg.cache == (root / ".cadagent-cache" / "gates").resolve()


@pytest.mark.parametrize("text, error", [
    ("gates: {jbos: 2}\n", "unknown key"),
    ("gates: {jobs: 0}\n", "positive integer"),
    ("gates: {skip: {motion: ''}}\n", "needs a reason"),
    ("gates: {skip: {flux: why}}\n", "not a gate"),
    ("gates: {assembly: {max_step: 2}}\n", "unknown option"),
    ("gates: {assembly: {max_step_mm: 0}}\n", "max_step_mm must be positive"),
    ("gates: {motion: {tol: {touch_mm: -1}}}\n", "non-negative"),
    ("gates: {fasteners: {lines: 2}}\n", "at least 3"),
])
def test_bad_config_is_unusable(tmp_path, capsys, text, error):
    root = make_project(tmp_path)
    _config(root, text)
    assert main(["gates", "--project", str(root)]) == 2
    assert error in capsys.readouterr().err


def test_assembly_options_reach_the_gate_as_access_options():
    """#54: a project tunes the assembly gate's sweep (a long slide is slow at the default step)."""
    kw = gr.gate_kwargs("assembly", {"max_step_mm": 2.5, "margin_mm": 0.5, "refine_steps": 6, "max_samples": 900,
                                     "tool_access": False, "missing_direction": "fail", "service": ["board"],
                                     "tol": {"touch_mm": 0.02}})
    assert (kw["options"].max_step_mm, kw["options"].margin_mm, kw["options"].refine_steps) == (2.5, 0.5, 6)
    assert (kw["options"].max_samples, kw["options"].tool_access, kw["options"].missing_direction) == (900, False,
                                                                                                         "fail")
    assert kw["service"] == ["board"] and kw["tol"].touch_mm == 0.02
    kw = gr.gate_kwargs("fasteners", {"tip_clearance_mm": 0.3, "stock_lengths_mm": [6, 8]})
    assert kw["options"].tip_clearance_mm == 0.3 and kw["options"].stock_lengths_mm == (6.0, 8.0)
    assert set(gr.options_allowed("assembly")) >= {"max_step_mm", "margin_mm", "refine_steps", "max_samples",
                                                   "tool_access", "missing_direction", "service"}


def test_without_dossier_or_gates_key_nothing_changes(tmp_path, capsys):
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  name: plain\n")
    assert main(["gates", "--project", str(tmp_path)]) == 2
    assert "no dossier: or gates: key" in capsys.readouterr().err
    from cadagent.publish.report import collect
    features = [f["feature_id"] for f in collect(load_project(tmp_path))["features"]]
    assert "cad-gates" not in features and "cad-dossier" not in features


def test_no_geometry_record_and_no_build_is_unusable(tmp_path, capsys):
    root = make_project(tmp_path, geometry=False)
    assert main(["gates", "--project", str(root)]) == 2
    assert "no geometry record at exports/dossier-geometry.json" in capsys.readouterr().err
    assert main(["gates", "--project", str(root), "--build"]) == 2
    assert "needs cad.gates.build" in capsys.readouterr().err


# ----------------------------------------------------------------------------------------------- the plan

def test_dry_run_lists_what_applies_and_why(project, capsys):
    assert main(["gates", "--project", str(project), "--dry-run"]) == 0
    out = capsys.readouterr().out
    for gate in ("connectivity", "containment", "fasteners", "assembly", "wall", "dossier-lint"):
        assert f"RUN  {gate}" in out, out
    assert "N/A  motion" in out and "no joint that moves" in out
    assert not list((project / "exports" / "gates").glob("*.json"))


def test_plan_reads_walls_contains_and_steps_from_every_source(tmp_path):
    root = make_project(tmp_path)
    (root / "decl.yaml").write_text("wall_mm: {lid: 2.0}\ncontains: []\n")
    _config(root, "gates:\n  declarations: decl.yaml\n  wall: {parts: {base: 3.0}}\n")
    project = load_project(root)
    cfg = gr.gates_config(project)
    record, extra, dossier = gr.load_record(cfg), gr.load_extra(cfg), gr.load_dossier(project)
    assert gr.walls(record, dossier, extra, cfg.options["wall"]) == {"base": 3.0, "hopper": 2.4, "lid": 2.0}
    record["joints"] = {"J1": {"kind": "fixed"}}
    assert gr.applies("motion", record, dossier, extra, cfg)[0] is False
    record["joints"]["J2"] = {"kind": "revolute"}
    assert gr.applies("motion", record, dossier, extra, cfg)[0] is True
    (root / "decl.yaml").write_text("walls: {}\n")
    with pytest.raises(gr.GatesConfigError, match="unknown key"):
        gr.load_extra(cfg)


# ----------------------------------------------------------------------------------------------- running

def test_gates_run_every_applicable_gate_and_the_lint(project, capsys):
    assert main(["gates", "--project", str(project)]) == 0
    out = capsys.readouterr().out
    gates = project / "exports" / "gates"
    for g in ("connectivity", "containment", "fasteners", "assembly", "wall"):
        data = json.loads((gates / f"{g}.json").read_text())
        assert data["pass"] is True and data["inputs"]["geometry"]["file"] == "exports/dossier-geometry.json"
        assert (gates / f"{g}.md").read_text().startswith(f"# Gate: {g}")
        assert f"PASS {g}" in out
    assert not (gates / "motion.json").exists()
    assert (gates / "dossier-lint.json").is_file() and (project / "exports" / "dossier-status.json").is_file()
    assert "gates: 6 pass, 0 fail, 1 not applicable" in out
    assert (project / ".cadagent-cache" / ".gitignore").read_text().strip().endswith("*")


def test_a_failing_gate_fails_the_command_and_check(project, capsys, monkeypatch):
    monkeypatch.setenv("FAKE_GATE_MODE", "fail")
    monkeypatch.setenv("FAKE_GATE_TARGET", "containment")
    assert main(["gates", "--project", str(project)]) == 1
    out = capsys.readouterr().out
    assert "FAIL containment" in out and "containment:x" in out
    md = (project / "exports" / "gates" / "containment.md").read_text()
    assert "| `containment:x` | fail | lid | bad |" in md
    rows = _results(project, capsys)
    assert rows["gate containment"]["status"] == "fail" and rows["gate connectivity"]["status"] == "pass"
    assert main(["check", "--project", str(project)]) == 1


def test_a_crashed_gate_gets_a_failing_verdict_with_the_log(project, capsys, monkeypatch):
    bind_verdicts(project, ["fasteners"])               # an old passing verdict must not survive the crash
    monkeypatch.setenv("FAKE_GATE_MODE", "crash")
    monkeypatch.setenv("FAKE_GATE_TARGET", "fasteners")
    assert main(["gates", "--project", str(project), "--only", "fasteners"]) == 1
    data = json.loads((project / "exports" / "gates" / "fasteners.json").read_text())
    assert data["pass"] is False and "exit code 3" in data["findings"][0]["message"]
    assert "boom: the kernel fell over" in data["findings"][0]["message"]
    assert data["inputs"]["geometry"]["digest"]
    assert "gate-fasteners.log" in capsys.readouterr().out


def test_a_gate_that_hangs_times_out(project, capsys, monkeypatch):
    _config(project, "gates: {timeout_s: 1}\n")
    monkeypatch.setenv("FAKE_GATE_SLEEP", "5")
    assert main(["gates", "--project", str(project), "--only", "wall"]) == 1
    data = json.loads((project / "exports" / "gates" / "wall.json").read_text())
    assert "timed out after 1 s" in data["findings"][0]["message"]


def test_jobs_run_gates_at_the_same_time(project, capsys, monkeypatch):
    monkeypatch.setenv("FAKE_GATE_SLEEP", "1.5")
    assert main(["gates", "--project", str(project), "--jobs", "5", "--skip", "dossier-lint"]) == 0
    ex = project / "exports"
    spans = [(float((ex / f"started-{g}").read_text()), float((ex / f"ended-{g}").read_text()))
             for g in ("connectivity", "containment", "fasteners", "assembly", "wall")]
    first_end = min(e for _, e in spans)
    assert sum(1 for s, _ in spans if s < first_end) >= 2, spans     # overlapping, not one after another
    assert "5 at a time" in capsys.readouterr().out
    assert main(["gates", "--project", str(project), "--jobs", "0"]) == 2


def test_only_and_skip_select_gates(project, capsys):
    assert main(["gates", "--project", str(project), "--only", "wall", "connectivity"]) == 0
    written = sorted(p.stem for p in (project / "exports" / "gates").glob("*.json"))
    assert written == ["connectivity", "wall"]
    assert main(["gates", "--project", str(project), "--skip", "wall", "dossier-lint"]) == 0
    assert "SKIP wall" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["gates", "--project", str(project), "--only", "flux"])


def test_a_gate_with_nothing_to_check_loses_its_old_verdict(project, capsys):
    bind_verdicts(project, ["motion"])
    assert (project / "exports" / "gates" / "motion.json").is_file()
    assert main(["gates", "--project", str(project), "--only", "motion"]) == 0
    assert not (project / "exports" / "gates" / "motion.json").exists()


# ----------------------------------------------------------------------------------------------- check rows

def test_check_rows_missing_stale_skipped_and_custom(project, capsys):
    rows = _results(project, capsys)
    assert rows["gate wall"]["status"] == "fail" and "not run" in rows["gate wall"]["message"]
    assert rows["gate motion"]["status"] == "skip" and "no joint that moves" in rows["gate motion"]["message"]

    bind_verdicts(project)
    rows = _results(project, capsys)
    assert {n: r["status"] for n, r in rows.items()} == {
        "gate connectivity": "pass", "gate containment": "pass", "gate fasteners": "pass", "gate motion": "skip",
        "gate assembly": "pass", "gate wall": "pass"}
    assert rows["gate wall"]["evidence"]["label"] == "wall.md"

    geo = project / "exports" / "dossier-geometry.json"            # the hopper is rebuilt; the gates are not
    record = json.loads(geo.read_text())
    record["parts"]["hopper"]["instances"] = [{"key": "hopper", "sha256": "0" * 64}]
    geo.write_text(json.dumps(record))
    rows = _results(project, capsys)
    assert all(rows[f"gate {g}"]["status"] == "fail" and "stale: geometry changed" in rows[f"gate {g}"]["message"]
               and "hopper" in rows[f"gate {g}"]["message"]
               for g in ("connectivity", "containment", "fasteners", "assembly", "wall"))
    assert main(["check", "--project", str(project)]) == 1

    bind_verdicts(project)
    _config(project, "gates:\n  skip: {wall: printed by a vendor who checks walls}\n  assembly: {max_step_mm: 2}\n")
    rows = _results(project, capsys)
    assert rows["gate wall"]["status"] == "skip" and "vendor" in rows["gate wall"]["message"]
    assert rows["gate assembly"]["status"] == "fail" and "options changed" in rows["gate assembly"]["message"]
    assert rows["gate connectivity"]["status"] == "pass"

    bad = gr.verdict("clearance", [gr.Check("c", "pass", "ok")], assumptions=["a project's own gate"])
    (project / "exports" / "gates" / "clearance.json").write_text(json.dumps(bad))
    rows = _results(project, capsys)
    assert rows["gate clearance"]["status"] == "fail" and "no inputs" in rows["gate clearance"]["message"]


def test_check_after_a_dossier_declaration_changes(project, capsys):
    bind_verdicts(project)
    path = project / "dossier" / "sections" / "store.yaml"
    path.write_text(path.read_text().replace("count: 2", "count: 3"))
    rows = _results(project, capsys)
    row = rows["gate containment"]
    assert row["status"] == "fail" and "declarations changed" in row["message"]
    path.write_text(path.read_text().replace("count: 3", "count: 2").replace("Carries the hopper", "Holds it all"))
    rows = _results(project, capsys)
    assert rows["gate containment"]["status"] == "pass"           # card texts are not gate inputs


def test_check_and_report_need_no_cad_kernel(project):
    bind_verdicts(project)
    code = ("import sys; from cadagent.project import load_project; from cadagent.publish.report import collect; "
            "from cadagent.review.gates.run import gates_config, plan; "
            f"r = collect(load_project({str(project)!r})); "
            "assert any(f['feature_id'] == 'cad-gates' for f in r['features']); "
            "print(any(m in sys.modules for m in ('cadquery', 'OCP', 'trimesh')))")
    src = str(Path(__file__).resolve().parents[2] / "software")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": src, "PATH": ""})
    assert out.stdout.strip() == "False", out.stderr


# ----------------------------------------------------------------------------------------------- all, site

def test_all_runs_the_gates_after_the_build(project, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_build", lambda p, a: calls.append("build") or 0)
    monkeypatch.setattr(cli, "cmd_export_3mf", lambda p, a: calls.append("3mf") or 0)
    monkeypatch.setattr(cli, "cmd_holes", lambda p, a: calls.append("holes") or 0)
    monkeypatch.setattr(cli, "cmd_report", lambda p, a: calls.append("report") or 0)
    monkeypatch.setattr(cli, "cmd_package", lambda p, a: calls.append("package") or 0)
    real = cli.cmd_gates
    monkeypatch.setattr(cli, "cmd_gates", lambda p, a: calls.append("gates") or real(p, a))
    assert main(["all", "--project", str(project)]) == 0
    assert calls == ["build", "3mf", "holes", "gates", "report", "package"]
    assert (project / "exports" / "gates" / "wall.json").is_file()
    assert (project / "exports" / "dossier-status.json").is_file()


def test_all_without_a_geometry_record_still_lints(tmp_path, capsys, monkeypatch):
    root = make_project(tmp_path, geometry=False, gates=())
    for name in ("cmd_build", "cmd_export_3mf", "cmd_report", "cmd_package"):
        monkeypatch.setattr(cli, name, lambda p, a: 0)
    assert main(["all", "--project", str(root)]) == 0
    assert "gates not run: no geometry record" in capsys.readouterr().out
    assert (root / "exports" / "dossier-status.json").is_file()


def test_site_overview_counts_current_passing_gates(project):
    from cadagent.publish.site import build_site
    bind_verdicts(project, failing=["wall"])
    build_site(project, {}, "Demo")
    assert "integrity gates" not in (project / "site" / "index.html").read_text()   # only for a gates project
    assert main(["site", "--project", str(project)]) == 0
    html = (project / "site" / "index.html").read_text()
    assert "<b>4 / 5</b><span>integrity gates pass</span>" in html
    geo = project / "exports" / "dossier-geometry.json"
    record = json.loads(geo.read_text())
    record["parts"]["lid"]["instances"] = [{"key": "lid", "sha256": "1" * 64}]
    geo.write_text(json.dumps(record))
    build_site(project, {}, "Demo", gates_exports=project / "exports")
    assert "<b>0 / 5</b><span>integrity gates pass (5 stale)</span>" in (project / "site" / "index.html").read_text()


# ----------------------------------------------------------------------------------------------- review fixes

def test_a_part_named_like_a_volatile_field_is_still_digested():
    from cadagent.review.gates.verdict import geometry_digest
    rec = {"actor": "a", "parts": {"file": {"sha256": "1" * 64, "declared_at": "x:1"}},
           "joints": {"hash": {"kind": "revolute", "range": [0, 10]}}}
    moved = {**rec, "actor": "b", "parts": {"file": {"sha256": "1" * 64, "declared_at": "x:9"}}}
    assert geometry_digest(moved) == geometry_digest(rec)
    for changed in ({**rec, "parts": {"file": {"sha256": "2" * 64}}},
                    {**rec, "joints": {"hash": {"kind": "revolute", "range": [0, 20]}}}):
        assert geometry_digest(changed) != geometry_digest(rec)


def test_a_failed_build_removes_the_old_verdicts(project, capsys, monkeypatch):
    _config(project, "gates: {build: cad/build.py}\n")
    bind_verdicts(project)
    monkeypatch.setenv("FAKE_GATE_MODE", "crash")
    monkeypatch.setenv("FAKE_GATE_TARGET", "--build")
    assert main(["gates", "--project", str(project), "--build"]) == 1
    out = capsys.readouterr().out
    assert "FAIL build" in out and "exit code 3" in out and "gate-build.log" in out
    assert not list((project / "exports" / "gates").glob("wall.*"))
    rows = _results(project, capsys)
    assert rows["gate wall"]["status"] == "fail" and "not run" in rows["gate wall"]["message"]


def test_dry_run_before_the_first_build(tmp_path, capsys):
    root = make_project(tmp_path, geometry=False)
    _config(root, "gates: {build: cad/build.py}\n")
    assert main(["gates", "--project", str(root), "--dry-run"]) == 0
    assert "would build cad/build.py first" in capsys.readouterr().out


def test_a_configured_skip_removes_the_verdict_the_lint_would_read(project, capsys):
    bind_verdicts(project)
    _config(project, "gates:\n  skip: {wall: checked by the vendor}\n")
    assert main(["gates", "--project", str(project)]) == 1      # the hopper's card asks for gate:wall
    assert not (project / "exports" / "gates" / "wall.json").exists()
    assert "SKIP wall" in capsys.readouterr().out
    status = json.loads((project / "exports" / "dossier-status.json").read_text())
    assert "gate:wall unrun" in status["parts"]["hopper"]["blocked_by"][0]     # the old verdict no longer counts
    assert status["parts"]["lid"]["status"] == "gated"


def test_the_lint_compares_declarations_and_options_for_a_project(project):
    from cadagent.review.dossier.lint import lint_project
    bind_verdicts(project)
    assert "verdict-stale" not in lint_project(load_project(project)).codes()
    _config(project, "gates:\n  assembly: {max_step_mm: 2}\n")
    res = lint_project(load_project(project))
    [f] = [f for f in res.findings if f.code == "verdict-stale"]
    assert f.item == "gate:assembly" and "options changed" in f.message


@pytest.mark.parametrize("text, error", [
    ("contains: [hopper]\n", "list of mappings"),
    ("intended_overlaps: [{parts: [a, b]}]\n", "two parts and a reason"),
    ("contains: [{what: ball}]\n", "needs container"),
    ("tools: [hex]\n", "must be a mapping"),
])
def test_a_malformed_declarations_file_is_unusable(project, capsys, text, error):
    (project / "decl.yaml").write_text(text)
    _config(project, "gates: {declarations: decl.yaml}\n")
    assert main(["gates", "--project", str(project)]) == 2
    assert error in capsys.readouterr().err
    rows = _results(project, capsys)
    assert rows["gates configuration"]["status"] == "fail"


def test_all_builds_with_the_gates_script_unless_a_step_runs_it(project, monkeypatch):
    seen = []
    for name in ("cmd_build", "cmd_export_3mf", "cmd_report", "cmd_package"):
        monkeypatch.setattr(cli, name, lambda p, a: 0)
    monkeypatch.setattr(cli, "cmd_gates", lambda p, a: seen.append(a.build) or 0)
    _config(project, "gates: {build: cad/build.py}\n")
    assert main(["all", "--project", str(project)]) == 0
    _config(project, "steps: [{name: build, run: cad/build.py}]\n")
    assert main(["all", "--project", str(project)]) == 0
    assert seen == [True, False]


def test_the_worker_path_leaves_an_installed_package_alone(monkeypatch, tmp_path):
    import cadagent
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    assert gr._env()["PYTHONPATH"].split(":")[0] == str(Path(cadagent.__file__).resolve().parents[1])
    fake = tmp_path / "lib" / "site-packages" / "cadagent" / "__init__.py"
    monkeypatch.setattr(cadagent, "__file__", str(fake))
    assert gr._env()["PYTHONPATH"] == "/somewhere"


# ----------------------------------------------------------------------------------------------- end to end
# The real gates on the gate-bench project, through the CLI: the clean bench passes every gate, and each seeded
# defect fails the gate the plan assigns it, with a finding that names the seeded part. Needs CadQuery.

BENCH = Path(__file__).resolve().parents[1] / "fixtures" / "gate_bench"


@pytest.fixture(scope="module")
def clean_bench(tmp_path_factory):
    pytest.importorskip("cadquery")
    pytest.importorskip("trimesh")
    base = tmp_path_factory.mktemp("bench")
    shutil.copytree(BENCH, base / "gate_bench", ignore=shutil.ignore_patterns("__pycache__"))
    root = base / "gate_bench" / "project"
    cache = base / "pair-cache"              # shared by every copy: the seeds reuse the clean bench's pairs
    cfg = root / "cad-agent.yaml"
    cfg.write_text(cfg.read_text().replace("  gates:\n", f"  gates:\n    cache: {cache}\n"))
    started = time.monotonic()
    code = main(["gates", "--project", str(root), "--build", "--jobs", "3"])
    return root, code, time.monotonic() - started


def _seeded(clean, tmp_path, seed: str) -> Path:
    src = clean[0].parents[0]
    dst = tmp_path / "gate_bench"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "logs"))
    params = dst / "project" / "cad" / "parameters.json"
    params.write_text(json.dumps({"seed": seed}))
    return dst / "project"


def test_clean_bench_passes_every_gate_through_the_cli(clean_bench, capsys):
    root, code, seconds = clean_bench
    gates = root / "exports" / "gates"
    summary = {g: json.loads((gates / f"{g}.json").read_text()) for g in gr.NAMES}
    bad = {g: v["findings"] for g, v in summary.items() if v["pass"] is not True}
    assert code == 0 and not bad, bad
    for g in gr.GATES:
        assert summary[g]["findings"] == [], (g, summary[g]["findings"])
        assert (gates / f"{g}.md").is_file()
    assert (gates / "connectivity.dot").is_file()
    # the screw-in-insert exemptions name fasteners in the dossier (#56) and reach the gates as exclusions
    for g in ("containment", "motion"):
        assert any(set(e["parts"]) == {"screw_0", "insert_0"} and "thread envelope" in e["reason"]
                   for e in summary[g]["exclusions"]), (g, summary[g]["exclusions"])
    status = json.loads((root / "exports" / "dossier-status.json").read_text())
    assert {s["status"] for s in status["sections"].values()} == {"gated"}, status["sections"]
    rows = _results(root, capsys)
    assert {r["status"] for r in rows.values()} == {"pass"}, rows
    print(f"clean bench, every gate through the CLI: {seconds:.1f} s")


SEEDS = ["ball_through_wall", "bracket_floats", "bracket_hovers", "screw_too_long", "screw_too_short",
         "gusset_over_screw", "flap_hits_frame", "thin_wall", "lid_before_board"]


@pytest.mark.parametrize("seed", SEEDS)
def test_each_seed_fails_its_gate_through_the_cli(clean_bench, tmp_path, capsys, seed):
    from .test_gate_bench import gb
    spec = gb.SEEDS[seed]
    root = _seeded(clean_bench, tmp_path, seed)
    assert main(["gates", "--project", str(root), "--build", "--only", spec["gate"]]) == 1
    v = json.loads((root / "exports" / "gates" / f"{spec['gate']}.json").read_text())
    assert v["pass"] is False
    named = [f for f in v["findings"] if f["status"] == "fail" and set(f.get("parts", [])) & set(spec["parts"])]
    assert named, f"{seed}: no failing finding names {spec['parts']}: {v['findings']}"
    rows = _results(root, capsys)                  # the gate fails check; the others are stale for the new build
    assert rows[f"gate {spec['gate']}"]["status"] == "fail"
    assert any("stale" in r["message"] for n, r in rows.items() if n != f"gate {spec['gate']}"
               and r["status"] == "fail"), rows


def test_the_dossier_seed_fails_the_lint_through_the_cli(clean_bench, tmp_path, capsys):
    root = _seeded(clean_bench, tmp_path, None)
    path = root / "dossier" / "sections" / "store.yaml"
    text = path.read_text()
    start = text.index("alternatives:", text.index("id: D1"))
    end = text.index("\n", text.index("rejected:", text.index("rejected:", start) + 1))
    path.write_text(text[:start] + "alternatives: []" + text[end:])
    assert main(["gates", "--project", str(root), "--only", "dossier-lint"]) == 1
    v = json.loads((root / "exports" / "gates" / "dossier-lint.json").read_text())
    named = [f for f in v["findings"] if f["evidence"]["code"] == "decision-incomplete"]
    assert named and "hopper" in named[0]["parts"], v["findings"]
    rows = _results(root, capsys)
    assert {r["status"] for r in rows.values()} == {"pass"}    # the geometric verdicts are still current

# ------------------------------------------------------------------- components declared not drawn (#722)
# What `not_drawn()` puts in the record (tests/review/test_dossier_registry.py) is stated in every verdict, the
# summary and the lint. Kernel-free except the last test, which runs the real gates.

from cadagent.review.dossier import join, load_dossier  # noqa: E402
from cadagent.review.dossier.lint import lint_project  # noqa: E402
from cadagent.review.gates.verdict import (NOT_DRAWN_NOTE_ONLY, Check, geometry_digest,  # noqa: E402
                                           not_drawn_of, not_drawn_summary, note_not_drawn, stale_reason, verdict)

NOT_DRAWN = {"bevel_pinion": {"reason": "sized in analysis/gears.py; no solid yet", "near": ["hopper", "lid"],
                              "declared_at": "cad/build.py:40"},
             "motor_shaft": {"reason": "vendor STEP not imported", "near": [], "declared_at": "cad/build.py:41"}}


def geometry_with(table=None):
    geo = base_geometry()
    geo["not_drawn"] = copy.deepcopy(NOT_DRAWN if table is None else table)
    return geo


def passing(gate: str):
    return verdict(gate, [Check(f"{gate}:x", "pass", "ok")], assumptions=["a test verdict"])


def test_a_record_without_declarations_leaves_every_verdict_byte_for_byte():
    for record in (base_geometry(), {}, None, {"not_drawn": {}}, {"not_drawn": "nonsense"}):
        for gate in gr.GATES:
            data = passing(gate)
            before = json.dumps(data, indent=2)
            assert note_not_drawn(data, record) is data and json.dumps(data, indent=2) == before
            assert gr.verdict_markdown(data) == gr.verdict_markdown(json.loads(before))
        assert not_drawn_of(record) == [] and not_drawn_summary(not_drawn_of(record)) == ""


@pytest.mark.parametrize("gate", gr.GATES)
def test_every_gate_verdict_names_what_is_not_drawn(gate):
    data = note_not_drawn(passing(gate), geometry_with())
    assert [m["name"] for m in data["not_drawn"]] == ["bevel_pinion", "motor_shaft"]
    assert data["not_drawn"][0] == {"name": "bevel_pinion", "reason": NOT_DRAWN["bevel_pinion"]["reason"],
                                    "near": ["hopper", "lid"]}
    said = data["assumptions"][-1]
    assert "2 components of the design are declared not drawn" in said and "did not see them" in said
    assert "bevel_pinion (near hopper, lid), motor_shaft" in said
    assert data["pass"] is True and data["physical_fit_verified"] is False
    row = [c for c in data["checks"] if c["id"] == f"{gate}:not-drawn"]
    if gate in NOT_DRAWN_NOTE_ONLY:                 # the wall of a drawn part does not depend on an absent one
        assert not row and data["status"] == "pass" and data["counts"] == {"pass": 1, "warn": 0, "fail": 0}
        assert data["findings"] == []
    else:
        assert data["status"] == "warn" and data["counts"] == {"pass": 1, "warn": 1, "fail": 0}
        assert row == data["findings"] and row[0]["status"] == "warn" and row[0]["parts"] == ["hopper", "lid"]
        assert "not in the model: bevel_pinion (near hopper, lid), motor_shaft" in row[0]["message"]
        assert row[0]["evidence"]["not_drawn"] == data["not_drawn"]
    md = gr.verdict_markdown(data)
    assert "## Not in the model" in md and md.index("## Not in the model") < md.index("## Findings")
    assert "| `bevel_pinion` | hopper, lid | sized in analysis/gears.py; no solid yet |" in md
    assert "| `motor_shaft` | - | vendor STEP not imported |" in md
    again = json.dumps(data)
    assert json.dumps(note_not_drawn(data, geometry_with())) == again          # stated once


def test_one_component_reads_in_the_singular():
    data = note_not_drawn(passing("motion"), geometry_with({"pinion": {"reason": "later", "near": ["hopper"]}}))
    assert "1 component of the design is declared not drawn (pinion (near hopper)): this gate did not see it" in \
        data["assumptions"][-1]
    assert "does not cover this component" in data["findings"][0]["message"]
    assert not_drawn_summary(data["not_drawn"]) == ("1 component of the design is declared not drawn, so no gate "
                                                    "saw it: pinion (near hopper)")


def test_a_declaration_never_turns_a_fail_into_anything_else():
    failing = verdict("motion", [Check("motion:x", "fail", "collides")], assumptions=["a"])
    data = note_not_drawn(failing, geometry_with())
    assert (data["pass"], data["status"]) == (False, "fail") and data["counts"] == {"pass": 0, "warn": 1, "fail": 1}
    assert [f["id"] for f in data["findings"]] == ["motion:x", "motion:not-drawn"]
    empty = note_not_drawn(verdict("assembly", [], assumptions=["a"]), geometry_with())
    assert (empty["pass"], empty["status"]) == (False, "fail")            # an empty gate still proves nothing
    assert [f["id"] for f in empty["findings"]] == ["assembly:nothing-checked", "assembly:not-drawn"]


def test_a_declaration_is_part_of_the_geometry_digest_but_not_its_line():
    base, declared = base_geometry(), geometry_with()
    assert geometry_digest(base) != geometry_digest(declared)
    moved = geometry_with()
    moved["not_drawn"]["bevel_pinion"]["declared_at"] = "cad/build.py:99"
    assert geometry_digest(moved) == geometry_digest(declared)
    reworded = geometry_with()
    reworded["not_drawn"]["bevel_pinion"]["near"] = ["hopper"]
    assert geometry_digest(reworded) != geometry_digest(declared)
    bound = gr.bind_inputs(passing("motion"), base)
    assert "components declared not drawn" in stale_reason(bound, declared)     # declared after the gates ran


def test_many_components_are_counted_in_the_summary_line():
    table = {f"part_{i}": {"reason": "later", "near": []} for i in range(5)}
    data = note_not_drawn(passing("motion"), geometry_with(table))
    assert gr._summary(data) == "2 checks, 1 warning(s); 5 not drawn, not seen: part_0, part_1, part_2 and 2 more"
    assert gr._summary(passing("motion")) == "1 checks, 0 warning(s)"


# ------------------------------------------------------------------------------- run_one and cad-agent gates

def _fake_gates(monkeypatch):
    """``run_one`` with the kernel left out: the record is read as JSON and every gate passes one check."""
    from cadagent.review.dossier import registry
    monkeypatch.setattr(registry, "load_geometry",
                        lambda path, shapes=True: types.SimpleNamespace(geometry=json.loads(Path(path).read_text())))
    monkeypatch.setattr(gr, "ADAPTERS", {g: (lambda g: lambda *a: passing(g))(g) for g in gr.GATES})


def _record(geo):
    return {**geo, "out_dir": "exports"}


def test_run_one_writes_the_statement_into_every_gate_file(tmp_path, monkeypatch):
    root = make_project(tmp_path / "p", geometry=_record(geometry_with()), gates=())
    _fake_gates(monkeypatch)
    project = load_project(root)
    for gate in gr.GATES:
        gr.run_one(project, gate, no_cache=True)
        data = json.loads((root / "exports" / "gates" / f"{gate}.json").read_text())
        assert len(data["not_drawn"]) == 2 and data["pass"] is True
        assert data["status"] == ("pass" if gate in NOT_DRAWN_NOTE_ONLY else "warn"), gate
        assert stale_reason(data, json.loads((root / "exports" / "dossier-geometry.json").read_text())) is None
        assert "## Not in the model" in (root / "exports" / "gates" / f"{gate}.md").read_text()
    rows = {r["name"]: r for r in gr.gate_rows(project)}                 # cad-agent check and the report
    assert rows["gate connectivity"]["status"] == "pass"
    assert "2 not drawn, not seen: bevel_pinion (near hopper, lid), motor_shaft" in rows["gate connectivity"]["message"]


def test_run_one_without_declarations_writes_what_it_wrote_before(tmp_path, monkeypatch):
    root = make_project(tmp_path / "p", geometry=_record(base_geometry()), gates=())
    _fake_gates(monkeypatch)
    project = load_project(root)
    record = json.loads((root / "exports" / "dossier-geometry.json").read_text())
    cfg = gr.gates_config(project)
    for gate in gr.GATES:
        gr.run_one(project, gate, no_cache=True)
        expected = gr.bind_inputs(passing(gate), record, record_file="exports/dossier-geometry.json",
                                  **gr.expected_inputs(gate, cfg, gr.load_dossier(project), {}))
        assert (root / "exports" / "gates" / f"{gate}.json").read_text() == json.dumps(expected, indent=2) + "\n"
        assert "Not in the model" not in (root / "exports" / "gates" / f"{gate}.md").read_text()


@pytest.fixture
def cli_project(tmp_path, monkeypatch):
    def make(geometry):
        root = make_project(tmp_path / "p", geometry=geometry, gates=())
        script = tmp_path / "fake_worker.py"
        script.write_text(FAKE_WORKER)
        monkeypatch.setattr(gr, "worker_command", lambda r, g, no_cache=False: [sys.executable, str(script), str(r), g])
        return root
    return make


def test_the_gates_summary_says_what_is_not_in_the_model(cli_project, capsys, monkeypatch):
    root = cli_project(geometry_with())
    assert main(["gates", "--project", str(root)]) == 0                # a declaration alone fails nothing
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("not in the model:"))
    assert "2 components of the design are declared not drawn, so no gate saw them: bevel_pinion (near hopper, " \
           "lid), motor_shaft" in line and "does not cover what is not drawn" in line
    assert out.index("gates: ") < out.index("not in the model:")
    assert main(["gates", "--project", str(root), "--dry-run"]) == 0
    assert "not in the model: 2 components" in capsys.readouterr().out
    monkeypatch.setenv("FAKE_GATE_MODE", "crash")                      # a gate that died still names them
    monkeypatch.setenv("FAKE_GATE_TARGET", "connectivity")
    assert main(["gates", "--project", str(root)]) == 1
    crashed = json.loads((root / "exports" / "gates" / "connectivity.json").read_text())
    assert crashed["pass"] is False and len(crashed["not_drawn"]) == 2
    assert "2 not drawn, not seen" in capsys.readouterr().out


def test_the_gates_summary_is_unchanged_without_declarations(cli_project, capsys):
    root = cli_project(None)
    assert main(["gates", "--project", str(root)]) == 0
    out = capsys.readouterr().out
    assert "not in the model" not in out and "not drawn" not in out
    assert main(["gates", "--project", str(root), "--dry-run"]) == 0
    assert "not in the model" not in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------- the lint

def test_the_lint_lists_each_component_as_a_warning_on_its_neighbours(tmp_path):
    root = make_project(tmp_path, geometry=geometry_with())
    res = lint_project(load_project(root))
    found = [f for f in res.warnings if f.code == "not-drawn"]
    assert res.passed and len(found) == 2, [f.code for f in res.errors]
    pinion = next(f for f in found if "'bevel_pinion'" in f.message)
    assert set(pinion.parts) == {"hopper", "lid"} and pinion.where.file == "cad/build.py" and pinion.where.line == 40
    assert "No gate saw it" in pinion.message and "sized in analysis/gears.py" in pinion.message
    assert not [f for f in lint_project(load_project(make_project(tmp_path / "q"))).warnings if f.code == "not-drawn"]


def test_the_join_refuses_a_neighbour_that_is_not_a_part(tmp_path):
    root = make_project(tmp_path)
    geo = geometry_with({"pinion": {"reason": "later", "near": ["ghost"], "declared_at": "cad/build.py:7"}})
    issues = join(load_dossier(root / "dossier" / "project.yaml", strict=False), geo)
    assert [(i.code, i.severity) for i in issues if "pinion" in i.message] == [("not-drawn", "warning"),
                                                                              ("unknown-part", "error")]


def test_the_real_gates_warn_on_a_build_with_a_declared_omission(tmp_path, capsys):
    pytest.importorskip("cadquery")
    pytest.importorskip("trimesh")
    root = reg_fixture.make_project(tmp_path, build=reg_fixture.DECLARED)
    (root / "cad-agent.yaml").write_text("cad:\n  name: demo\n  dossier: dossier/project.yaml\n"
                                         "  gates:\n    build: cad/build.py\n")
    main(["gates", "--project", str(root), "--build", "--only", "connectivity", "motion", "assembly", "--jobs", "3"])
    out = capsys.readouterr().out
    assert "not in the model: 2 components of the design are declared not drawn" in out
    for gate in ("connectivity", "motion", "assembly"):
        data = json.loads((root / "exports" / "gates" / f"{gate}.json").read_text())
        assert all(c["id"] != f"{gate}:run" for c in data["checks"]), (gate, data["findings"])   # the gate ran
        row = next(c for c in data["checks"] if c["id"] == f"{gate}:not-drawn")
        assert row["status"] == "warn" and row["parts"] == ["hopper", "hopper_flap"]
        assert data["status"] != "pass" and [m["name"] for m in data["not_drawn"]] == ["flap_spring", "vent_plug"]
        assert "## Not in the model" in (root / "exports" / "gates" / f"{gate}.md").read_text()
