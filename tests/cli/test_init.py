"""`cad-agent init` (#291): it copies the starter box (examples/starter-box), refuses a folder that is not empty, works
from a wheel's copy too, and what it writes passes `cad-agent all` as it stands."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cadagent import project
from cadagent.cli import main

ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "examples" / "starter-box"
OUTPUTS = set(project.STARTER_OUTPUTS)


def starter_files(folder: Path = STARTER) -> set:
    """The starter's own files, without what a `cad-agent all` run there left behind."""
    return {f.relative_to(folder).as_posix() for f in folder.rglob("*")
            if f.is_file() and not OUTPUTS & set(f.relative_to(folder).parts)}


def test_init_copies_the_starter_and_says_what_to_run(tmp_path, monkeypatch, capsys):
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
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / "cad-agent.yaml").is_file()
    out = capsys.readouterr().out
    assert "cd " not in out and "  cad-agent all" in out


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


def test_a_wheel_installs_every_file_of_the_starter():
    """pyproject.toml's data-files list is the starter's files, so a wheel's `cad-agent init` copies all of them."""
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["data-files"]
    listed = set()
    for into, files in data.items():
        assert into.startswith("share/cad-agent/starter-box"), into
        sub = into[len("share/cad-agent/starter-box"):].strip("/")
        for f in files:
            assert f.startswith("examples/starter-box/"), f
            rel = f[len("examples/starter-box/"):]
            assert Path(rel).parent.as_posix() == (sub or "."), f"{f} is installed into {into}"
            listed.add(rel)
    assert listed == starter_files(), "list each starter file in pyproject.toml's [tool.setuptools.data-files]"


def test_a_wheel_install_finds_the_starter_under_share(tmp_path, monkeypatch):
    """No checkout beside the package: the copy the wheel put under <prefix>/share/cad-agent/, found through the
    distribution's file list (any install scheme)."""
    site = tmp_path / "venv" / "lib" / "python3" / "site-packages"
    share = tmp_path / "venv" / "share" / "cad-agent" / "starter-box"
    project.init_project(share)
    monkeypatch.setattr(project, "__file__", str(site / "cadagent" / "project.py"))

    class Dist:
        files = [Path("cadagent/project.py"), Path("../../../share/cad-agent/starter-box/cad-agent.yaml")]

        def locate_file(self, f):
            return site / f

    from importlib import metadata
    monkeypatch.setattr(metadata, "distribution", lambda name: Dist())
    assert project.starter_dir() == share.resolve()
    Dist.files = Dist.files[:1]
    with pytest.raises(FileNotFoundError, match="not installed with this cad-agent"):
        project.starter_dir()
    assert main(["init", str(tmp_path / "x")]) == 2


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
