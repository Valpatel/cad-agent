"""`cad-agent init` (#291): it copies the starter box (docs/examples/starter-box), refuses a folder that is not empty, works
from a wheel's copy too, and what it writes passes `cad-agent all` as it stands."""
from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from cadagent import project
from cadagent import cli
from cadagent.cli import main

ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "docs" / "examples" / "starter-box"
OUTPUTS = set(project.STARTER_OUTPUTS)


def starter_files(folder: Path = STARTER) -> set:
    """The starter's own files, without what a `cad-agent all` run there left behind."""
    return {f.relative_to(folder).as_posix() for f in folder.rglob("*")
            if f.is_file() and not OUTPUTS & set(f.relative_to(folder).parts)}


def test_init_copies_the_starter_and_says_what_to_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda name: "/installed/bin/cad-agent")
    monkeypatch.chdir(tmp_path)
    assert main(["init", "my box"]) == 0
    dest = tmp_path / "my box"
    assert starter_files(dest) == starter_files() >= {"cad-agent.yaml", "cad/build.py", "tools/checks.py", "README.md"}
    for name in starter_files():
        assert (dest / name).read_bytes() == (STARTER / name).read_bytes(), name
    out = capsys.readouterr().out
    assert "  cd 'my box'\n  cad-agent all" in out, "the next two commands, quoted for the shell"
    assert project.load_project(dest).name == "my box", "the project is named after its folder"


def test_init_here_says_only_cad_agent_all(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda name: "/installed/bin/cad-agent")
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / "cad-agent.yaml").is_file()
    out = capsys.readouterr().out
    assert "cd " not in out and "  cad-agent all" in out


@pytest.mark.skipif(os.name == "nt", reason="executes the POSIX shell handoff")
@pytest.mark.parametrize("spaced_interpreter", [False, True])
def test_init_next_command_runs_without_cad_agent_on_path(tmp_path, monkeypatch, capsys, spaced_interpreter):
    """A custom install need not change PATH: execute the suggested command after its suggested cd."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "software"))
    if spaced_interpreter:
        interpreter = tmp_path / "python with 'quotes' and spaces"
        interpreter.symlink_to(sys.executable)
        monkeypatch.setattr(sys, "executable", str(interpreter))
    assert shutil.which("cad-agent") is None
    assert main(["init", "my box"]) == 0
    lines = capsys.readouterr().out.split("next:\n", 1)[1].splitlines()
    command = lines[-1].split("          #", 1)[0].strip()
    # --help exercises command discovery, import and argument dispatch without requiring CAD extras.
    result = subprocess.run(["/bin/sh", "-c", lines[0].strip() + "\n" + command + " --help"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "cad-agent all" in result.stdout


def test_init_windows_fallback_is_literal_powershell(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "executable", "C:/Users/O'Brien/$tools/python.exe")
    assert main(["init", "my box"]) == 0
    out = capsys.readouterr().out
    assert "  cd 'my box'\n  & 'C:/Users/O''Brien/$tools/python.exe' -m cadagent.cli all" in out


def test_init_refuses_a_folder_that_is_not_empty_unless_forced(tmp_path, capsys):
    dest = tmp_path / "taken"
    dest.mkdir()
    (dest / "notes.txt").write_text("mine\n")
    (dest / "cad-agent.yaml").write_text("cad: {}\n")
    assert main(["init", str(dest)]) == 2
    err = capsys.readouterr().err
    assert "is not empty" in err and "--force" in err
    assert sorted(p.name for p in dest.iterdir()) == ["cad-agent.yaml", "notes.txt"], "nothing written"
    assert (dest / "cad-agent.yaml").read_text() == "cad: {}\n"
    assert main(["init", str(dest), "--force"]) == 0
    assert (dest / "cad-agent.yaml").read_bytes() == (STARTER / "cad-agent.yaml").read_bytes()
    assert (dest / "notes.txt").read_text() == "mine\n", "--force leaves the other files"
    fresh = tmp_path / "fresh-repo"
    (fresh / ".git").mkdir(parents=True)
    assert main(["init", str(fresh)]) == 0, "a folder holding only .git (git init, gh repo create --clone) is empty"
    assert (fresh / "cad-agent.yaml").is_file()
    (tmp_path / "a-file").write_text("x")
    assert main(["init", str(tmp_path / "a-file"), "--force"]) == 2
    assert "is a file" in capsys.readouterr().err


def test_init_never_copies_a_runs_outputs(tmp_path, monkeypatch):
    """A starter that `cad-agent all` ran in where it lives (a checkout) still copies as the bare starter."""
    src = tmp_path / "starter-box"
    project.init_project(src)
    for junk in ("exports/box.stl", "build/slicer/x.json", "docs/cad-agent-report.html", "cad/__pycache__/b.pyc"):
        (src / junk).parent.mkdir(parents=True, exist_ok=True)
        (src / junk).write_text("x")
    monkeypatch.setattr(project, "starter_dir", lambda: src)
    written = project.init_project(tmp_path / "copy")
    assert {f.relative_to(tmp_path / "copy").as_posix() for f in written} == starter_files()
    assert {f.relative_to(tmp_path / "copy").as_posix() for f in (tmp_path / "copy").rglob("*") if f.is_file()} \
        == starter_files()
    ignored = (STARTER / ".gitignore").read_text().split()
    for out in ("build/", "exports/", "preview/", "site/"):
        assert out in ignored, f"the starter's .gitignore leaves {out} out of the user's repo"


def test_wheel_data_declarations_cover_the_starter():
    """Fast declaration parity. Actual wheel installation is exercised once in full CI by --wheel-smoke below."""
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["data-files"]
    listed = set()
    for into, files in data.items():
        assert into.startswith("share/cad-agent/starter-box"), into
        sub = into[len("share/cad-agent/starter-box"):].strip("/")
        for f in files:
            assert f.startswith("docs/examples/starter-box/"), f
            rel = f[len("docs/examples/starter-box/"):]
            assert Path(rel).parent.as_posix() == (sub or "."), f"{f} is installed into {into}"
            listed.add(rel)
    assert listed == starter_files(), "list each starter file in pyproject.toml's [tool.setuptools.data-files]"


def _wheel_smoke(tmp_path):
    """Mandatory full-CI smoke: consume the committed starter and SDK outside the removed build source."""
    tmp_path = Path(tmp_path).resolve()
    source, wheels, outside = (tmp_path / name for name in ("source", "wheels", "outside"))
    env_dir = outside / ".venv"
    source.mkdir(); wheels.mkdir(); outside.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "NODE_OPTIONS")}

    def run(args, *, cwd=outside, check=True):
        result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
        if check and result.returncode:
            raise AssertionError(f"{args[0]} exited {result.returncode}\n{result.stdout}\n{result.stderr}")
        return result

    archive = tmp_path / "source.tar"
    run(["git", "archive", "--format=tar", "--output", archive, "HEAD"], cwd=ROOT)
    with tarfile.open(archive) as package:
        package.extractall(source, filter="data")
    # Expectations and wheel input come from the same immutable archive, never from a dirty working tree.
    committed_starter = source / STARTER.relative_to(ROOT)
    expected = {p.relative_to(committed_starter).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in committed_starter.rglob("*") if p.is_file()}
    assert expected and "cad-agent.yaml" in expected
    sdk_source = source / "software" / "cadagent" / "webkit"
    sdk_expected = {name: hashlib.sha256((sdk_source / name).read_bytes()).hexdigest()
                    for name in (p.relative_to(sdk_source).as_posix() for p in sdk_source.rglob("*") if p.is_file())}
    run([sys.executable, "-m", "pip", "wheel", "--disable-pip-version-check", "--no-deps", "--wheel-dir", wheels, source])
    built = list(wheels.glob("cad_agent-*.whl"))
    assert len(built) == 1, f"expected one cad-agent wheel, found {built}"
    with zipfile.ZipFile(built[0]) as wheel:
        names = wheel.namelist()
        unexpected = [name for name in names if name.split("/", 1)[0] != "cadagent"
                      and not name.split("/", 1)[0].startswith("cad_agent-")]
        assert not unexpected, f"non-package software (including imported vendor trees) leaked into wheel: {unexpected[:10]}"
        assert any(name.startswith("cadagent/webkit/vendor/") for name in names), "the packaged SDK keeps its own runtime dependencies"
        # Read what pip consumes, not just pyproject.toml: an optional Intel solver must not make ARM/macOS unresolvable.
        from email.parser import BytesParser
        from packaging.requirements import Requirement
        metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
        assert len(metadata_paths) == 1
        metadata = BytesParser().parsebytes(wheel.read(metadata_paths[0]))
        pardiso = [Requirement(r) for r in metadata.get_all("Requires-Dist", []) if Requirement(r).name == "pypardiso"]
        assert len(pardiso) == 1 and pardiso[0].marker is not None
        for system, machine, expected_pardiso in (("Linux", "x86_64", True), ("Windows", "AMD64", True),
                                          ("Linux", "aarch64", False), ("Darwin", "arm64", False),
                                          ("Darwin", "x86_64", False), ("Windows", "ARM64", False)):
            env = {"platform_system": system, "platform_machine": machine}
            assert pardiso[0].marker.evaluate({**env, "extra": "fea"}) is expected_pardiso, env
            assert not pardiso[0].marker.evaluate({**env, "extra": ""}), "PARDISO leaked into the core install"
    shutil.rmtree(source)
    assert not source.exists()
    # Package type follows the installed file's physical ancestors, not the process CWD. This explicit ancestor
    # prevents Node 22's automatic syntax detection from hiding a missing installed SDK scope declaration.
    (outside / "package.json").write_text('{"type":"commonjs"}\n')
    venv.EnvBuilder(with_pip=True).create(env_dir)
    python, cli = env_dir / "bin/python", env_dir / "bin/cad-agent"
    run([python, "-I", "-m", "pip", "install", "--disable-pip-version-check", built[0]])
    target = outside / "copied"
    run([cli, "init", target])
    probe = '''import json
from pathlib import Path
from importlib import metadata
import cadagent
from cadagent import project
dist = metadata.distribution("cad-agent")
records = [p for p in dist.files or () if p.as_posix().endswith("share/cad-agent/starter-box/cad-agent.yaml")]
assert len(records) == 1
print(json.dumps({"package": str(Path(cadagent.__file__).resolve()), "project": str(Path(project.__file__).resolve()),
 "distribution": str(Path(dist.locate_file("")).resolve()), "declared_config": str(Path(dist.locate_file(records[0])).resolve()),
 "starter": str(project.starter_dir().resolve())}))'''
    paths = json.loads(run([python, "-I", "-c", probe]).stdout)
    assert all(Path(p).is_relative_to(env_dir) for p in paths.values()), paths
    actual = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in target.rglob("*") if p.is_file()}
    assert actual == expected, f"installed wheel starter files differ from committed source bytes: expected={expected}, actual={actual}"
    sdk = Path(paths["package"]).parent / "webkit"
    for name, digest in sdk_expected.items():
        installed = (sdk / name).resolve()
        assert installed.is_relative_to(env_dir), installed
        assert hashlib.sha256(installed.read_bytes()).hexdigest() == digest, installed
    scopes = [parent / "package.json" for parent in (sdk, *sdk.parents) if (parent / "package.json").is_file()]
    assert scopes[:2] == [sdk / "package.json", outside / "package.json"], scopes
    node = shutil.which("node", path=env.get("PATH"))
    assert node, "the required wheel SDK consumer needs Node 22+; it must not be skipped"
    node_version = run([node, "-p", "process.versions.node"]).stdout.strip()
    assert int(node_version.split(".")[0]) >= 22, node_version
    sdk_probe = """import { pathToFileURL } from 'node:url';
const sdk = await import(pathToFileURL(process.argv[1]).href);
if (typeof sdk.snapArm !== 'function' || sdk.SMALL_DEFLECTION !== 0.1) throw new Error('wrong installed SDK exports');
console.log('installed SDK ESM PASS');"""
    good_sdk = run([node, "--input-type=module", "-e", sdk_probe, sdk / "formulas.js"])
    assert "installed SDK ESM PASS" in good_sdk.stdout
    # Only the installed scope metadata changes; source is gone, starter remains installed and module bytes match.
    (sdk / "package.json").unlink()
    assert Path(paths["declared_config"]).is_file() and not source.exists()
    assert hashlib.sha256((sdk / "formulas.js").read_bytes()).hexdigest() == sdk_expected["formulas.js"]
    bad_sdk = run([node, "--input-type=module", "-e", sdk_probe, sdk / "formulas.js"], check=False)
    assert bad_sdk.returncode != 0 and "SyntaxError" in bad_sdk.stderr and "export" in bad_sdk.stderr, (bad_sdk.stdout, bad_sdk.stderr)
    assert str(sdk / "formulas.js") in bad_sdk.stderr and "installed SDK ESM PASS" not in bad_sdk.stdout
    print(f"installed SDK scope PASS on Node {node_version}: real file-URL import and missing-metadata rejection")
    Path(paths["declared_config"]).unlink()
    rejected = outside / "missing-starter"
    bad = run([cli, "init", rejected], check=False)
    assert bad.returncode == 2 and "the starter project (starter-box) is not installed with this cad-agent" in bad.stderr, (bad.stdout, bad.stderr)
    assert not rejected.exists(), "missing installed data must not copy a checkout fallback"
    print("real wheel starter PASS: isolated imports, committed bytes and missing-installed-data rejection")


def test_a_project_command_without_a_project_points_at_init(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 2
    assert "`cad-agent init` starts one" in capsys.readouterr().err


def test_the_starter_passes_cad_agent_all_as_copied(tmp_path, monkeypatch, capsys):
    """What CI runs on the starter (the full job has the cad extra): init, then `cad-agent all` passes every row, with
    the insert hole inserts.hole_design gives (4.20 mm for the M3 insert, #317), and leaves only its outputs."""
    pytest.importorskip("cadquery")
    pytest.importorskip("trimesh")
    pytest.importorskip("scipy")
    dest = tmp_path / "my-box"
    assert main(["init", str(dest)]) == 0
    capsys.readouterr()
    assert main(["all", "--project", str(dest)]) == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert re.search(r"\d+ pass / 0 fail", out), out
    results = json.loads((dest / "exports" / "cad-agent-results.json").read_text())
    ids = json.dumps(results)
    for row in ("inserts", "overhangs", "cad-holes"):
        assert row in ids, f"the report has the {row} rows"
    from cadagent.mechanical import inserts
    joint = json.loads((dest / "exports" / "insert-joints.json").read_text())["joints"][0]
    design = inserts.hole_design(inserts.insert(joint["insert"]))
    assert joint["hole_mm"] == design["diameter_mm"] == 4.2 and joint["hole_depth_mm"] == design["depth_mm"]
    assert json.loads((dest / "exports" / "inserts.json").read_text())["pass"] is True
    assert json.loads((dest / "exports" / "overhangs.json").read_text())["pass"] is True
    assert starter_files(dest) == starter_files(), "a run writes only into the folders init never copies"
    # a check that cannot run stops the build instead of leaving the last run's file for the report to read
    build = dest / "cad" / "build.py"
    build.write_text(build.read_text().replace('MATERIAL = "pla-bambu-basic"', 'MATERIAL = "pla-typo"'))
    assert main(["all", "--project", str(dest)]) == 1
    assert "inserts: the check did not run" in (dest / "exports" / "checks.log").read_text()
    assert not (dest / "exports" / "inserts.json").exists()


if __name__ == "__main__":
    if sys.argv[1:] != ["--wheel-smoke"]:
        raise SystemExit("internal validation entry: --wheel-smoke")
    with tempfile.TemporaryDirectory(prefix="cad-agent-wheel-") as folder:
        _wheel_smoke(folder)
