"""`cad-agent update` (cadagent/agentkit.py, cli.cmd_update): a temporary git repository plays cad-agent's GitHub.

Each test clones a throwaway "remote" into tmp_path the way the installer does (shallow, `main`), then moves the
remote on and checks what the update does: fast-forward only, refuse what it must not touch, follow a tag, notice a
dependency change, show the changelog with "Projects must change" first, and tell a project what to re-run. Nothing
here touches the network or the kit's own checkout.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import types
from pathlib import Path

import pytest

from cadagent import agentkit, cli

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env=ENV).stdout.strip()


def release(version: str, **sections) -> str:
    body = "".join(f"\n**{name.replace('_', ' ')}**\n" + "".join(f"- {b}\n" for b in bullets)
                   for name, bullets in sections.items())
    return f"## {version} (2026-11-01)\n{body}\n"


def commit(repo: Path, message: str, files: dict) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def kit(tmp_path, monkeypatch):
    """A remote with one release, and a shallow clone of its main (what the installer makes)."""
    monkeypatch.setattr(os, "environ", ENV)
    remote = tmp_path / "remote"
    remote.mkdir()
    git(remote, "init", "-q", "-b", "main")
    head = "# Changelog\n\n## Unreleased\n\n"
    commit(remote, "v0.1.0", {"pyproject.toml": '[project]\nname = "cad-agent"\nversion = "0.1.0"\n',
                              "CHANGELOG.md": head + release("v0.1.0", New=["the first thing"])})
    git(remote, "tag", "v0.1.0")
    clone = tmp_path / "cad-agent"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "main", f"file://{remote}", str(clone)],
                   check=True, env=ENV)
    return remote, clone, head


def test_main_fast_forwards_and_notices_what_changed(kit):
    remote, clone, head = kit
    new = commit(remote, "v0.2.0", {"CHANGELOG.md": head + release("v0.2.0", New=["a new check"], Fixed=["a fix"],
                                                                   Projects_must_change=["re-run the FEA"])
                                    + release("v0.1.0", New=["the first thing"])})
    moved = agentkit.pull(clone)
    assert moved["new"] == new == git(clone, "rev-parse", "HEAD") and moved["at"] == "main"
    assert moved["changed"] == ["CHANGELOG.md"] and not moved["dependencies_changed"]
    notes = agentkit.release_notes(clone, moved["old"])
    assert [n["version"] for n in notes] == ["v0.2.0"], "only the releases gained since the old commit"
    lines = agentkit.notes_lines(notes)
    assert lines[:2] == ["Projects must change:", "  v0.2.0: re-run the FEA"], "what projects must do comes first"
    assert "v0.2.0: 1 new, 1 fixed" in lines and "  + a new check" in lines
    assert agentkit.pull(clone)["old"] == new, "a second update finds nothing new"
    commit(remote, "deps", {"pyproject.toml": '[project]\nname = "cad-agent"\nversion = "0.2.1"\n'})
    assert agentkit.pull(clone)["dependencies_changed"], "a pyproject.toml change means a reinstall"


@pytest.mark.parametrize("break_it, says", [
    (lambda clone: (clone / "pyproject.toml").write_text("changed\n"), "has changes to tracked files"),
    (lambda clone: git(clone, "switch", "-q", "-c", "my-work"), "is on branch 'my-work'"),
    (lambda clone: (commit(clone, "mine", {"x.txt": "x"}), git(clone, "checkout", "-q", "--detach", "HEAD")),
     "neither main nor a release tag"),
])
def test_it_refuses_what_it_must_not_touch_and_says_to_fork(kit, break_it, says):
    remote, clone, _ = kit
    break_it(clone)
    before = git(clone, "rev-parse", "HEAD")
    with pytest.raises(agentkit.UpdateRefused, match=says) as err:
        agentkit.pull(clone)
    assert "fork Valpatel/cad-agent" in str(err.value)
    assert git(clone, "rev-parse", "HEAD") == before, "nothing moved"


def test_a_local_commit_on_main_is_not_overwritten(kit):
    remote, clone, _ = kit
    commit(clone, "mine", {"x.txt": "x"})
    commit(remote, "theirs", {"y.txt": "y"})
    with pytest.raises(agentkit.UpdateRefused, match="cannot fast-forward"):
        agentkit.pull(clone)
    assert (clone / "x.txt").exists()


def test_ref_pins_a_tag_and_a_later_update_returns_to_main(kit):
    remote, clone, head = kit
    newest = commit(remote, "v0.2.0", {"CHANGELOG.md": head + release("v0.2.0", New=["b"])})
    git(remote, "tag", "v0.2.0")
    commit(remote, "after", {"z.txt": "z"})
    moved = agentkit.pull(clone, "v0.2.0")
    assert moved["new"] == newest and moved["at"] == "v0.2.0"
    assert agentkit.checkout_state(clone)["tag"] == "v0.2.0"
    back = agentkit.pull(clone)
    assert back["new"] == git(remote, "rev-parse", "HEAD") and agentkit.checkout_state(clone)["branch"] == "main"
    with pytest.raises(agentkit.UpdateRefused, match="tag or branch name"):
        agentkit.pull(clone, "--upload-pack=x")



def test_a_clone_of_a_branch_updates_with_that_ref(kit, tmp_path):
    """`install.sh --ref <branch>` clones the branch; running it again (update --ref <branch>) follows that branch."""
    remote, _, _ = kit
    git(remote, "switch", "-q", "-c", "try-this")
    commit(remote, "a", {"a.txt": "a"})
    clone = tmp_path / "branch-clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "try-this", f"file://{remote}", str(clone)],
                   check=True, env=ENV)
    newer = commit(remote, "b", {"b.txt": "b"})
    assert agentkit.pull(clone, "try-this")["new"] == newer
    newest = commit(remote, "c", {"c.txt": "c"})
    assert agentkit.pull(clone, "try-this")["new"] == newest, "and again: it stays on the branch"
    assert agentkit.checkout_state(clone)["branch"] == "try-this"
    with pytest.raises(agentkit.UpdateRefused, match="is on branch 'try-this'"):
        agentkit.pull(clone)
    git(remote, "switch", "-q", "main")
    main_clone = tmp_path / "main-clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{remote}", str(main_clone)], check=True, env=ENV)
    assert agentkit.pull(main_clone, "try-this")["new"] == newest, "from main, --ref <branch> moves onto the branch"
    assert agentkit.checkout_state(main_clone)["branch"] == "try-this"


def test_versions_staleness_and_project_advice(kit, tmp_path):
    _, clone, _ = kit
    assert agentkit.version_ok("0.14.2", "0.14") and agentkit.version_ok("v1.0", "0.99.9")
    assert agentkit.version_ok("0.13.0", "0.14") is False and agentkit.version_ok("0+unknown", "0.14") is None
    stamp = int(git(clone, "log", "-1", "--format=%ct"))
    assert agentkit.staleness(clone, now=stamp + 13 * 86400) is None, "nothing to say inside 14 days"
    assert "20 days old" in agentkit.staleness(clone, now=stamp + 20 * 86400)
    project = tmp_path / "box"
    (project / "out").mkdir(parents=True)
    (project / "cad-agent.yaml").write_text("cad:\n  exports_dir: out\n  cad-agent: '0.3'\n")
    advice = agentkit.project_advice(project, "0.2.0")
    assert "needs cad-agent 0.3 or newer" in advice[0] and "no record" in advice[1]
    (project / "out" / "cad-agent-results.json").write_text(json.dumps({"cad_agent": "0.1.0"}))
    assert "last built with cad-agent 0.1.0" in agentkit.project_advice(project, "0.3.0")[0]
    (project / "out" / "cad-agent-results.json").write_text(json.dumps({"cad_agent": "0.3.0"}))
    assert agentkit.project_advice(project, "0.3.0") == []


def test_reinstall_keeps_the_extras_and_uses_how_it_was_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(agentkit, "_uv_tool_env", lambda: True)
    monkeypatch.setattr(agentkit.shutil, "which", lambda name: "/bin/uv")
    cmd = agentkit.reinstall_command(tmp_path, ["cad", "fea"])
    assert cmd[:6] == ["uv", "tool", "install", "--quiet", "--force", "--editable"] and cmd[-1] == f"{tmp_path}[cad,fea]"
    monkeypatch.setattr(agentkit, "_uv_tool_env", lambda: False)
    assert agentkit.reinstall_command(tmp_path, [])[1:4] == ["-m", "pip", "install"]


def test_the_cli_reports_a_refusal_and_prints_the_reinstall_command(kit, monkeypatch, capsys):
    _, clone, _ = kit
    monkeypatch.setattr(agentkit, "kit_root", lambda: clone)
    (clone / "pyproject.toml").write_text("changed\n")
    assert cli.main(["update"]) == 2
    assert "fork Valpatel/cad-agent" in capsys.readouterr().err
    git(clone, "checkout", "-q", "--", "pyproject.toml")
    monkeypatch.setattr(agentkit, "installed_extras", lambda root: ["cad"])
    assert cli.main(["update", "--reinstall-command", "--extras", "fea"]) == 0
    cmd = json.loads(capsys.readouterr().out)
    assert cmd[-1].endswith("[cad,fea]")


def test_all_refuses_a_project_that_needs_a_newer_cad_agent(tmp_path, capsys):
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  cad-agent: '999.0'\n  steps: []\n")
    assert cli.main(["all", "--project", str(tmp_path)]) == 2
    assert "needs cad-agent 999.0 or newer" in capsys.readouterr().err
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  cad-agent: 'soon'\n")
    from cadagent.project import CadConfigError, load_project
    with pytest.raises(CadConfigError, match="oldest cad-agent release"):
        load_project(tmp_path)


def test_a_dependency_change_keeps_the_extras_and_a_failed_reinstall_is_retried(kit, monkeypatch, capsys):
    """The extras are read before the pull (a newer pyproject.toml may list a package that is not installed yet), and
    a reinstall that failed is tried again by the next update, even though the checkout no longer moves."""
    remote, clone, _ = kit
    monkeypatch.setattr(agentkit, "kit_root", lambda source=None: clone)
    monkeypatch.setattr(agentkit, "_receipt_extras", lambda: None)
    # What metadata would say: with the old pyproject every package of [cad] is installed; the new one adds a package.
    monkeypatch.setattr(agentkit, "installed_extras",
                        lambda root: ["cad"] if 'version = "0.1.0"' in (root / "pyproject.toml").read_text() else [])
    commit(remote, "deps", {"pyproject.toml": '[project]\nname = "cad-agent"\nversion = "0.2.0"\n'})
    ran, results = [], iter([1, 0, 0, 0])
    fake = lambda cmd, **kw: (ran.append(cmd), subprocess.CompletedProcess(cmd, next(results)))[1]
    monkeypatch.setattr(cli, "subprocess", types.SimpleNamespace(run=fake))     # cli's runs only, not agentkit's git
    assert cli.main(["update"]) == 1, "the reinstall failed"
    assert ran[0][-1] == f"{clone}[cad]", "the extras it had before the pull"
    assert agentkit.reinstall_pending(clone) == ["cad"], "remembered with its extras"
    assert "run update again to retry" in capsys.readouterr().err
    assert cli.main(["update"]) == 0
    out = capsys.readouterr().out
    assert "already at the newest" in out and "an earlier reinstall did not finish" in out
    assert ran[1][-1] == f"{clone}[cad]" and ran[2][3:5] == ["agents", "install"], "reinstalled, then relinked"
    assert agentkit.reinstall_pending(clone) is None


def test_the_receipt_says_which_extras_uv_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(agentkit.sys, "prefix", str(tmp_path))
    assert agentkit._receipt_extras() is None
    (tmp_path / "uv-receipt.toml").write_text(
        '[tool]\nrequirements = [{ name = "cad-agent", editable = "/x/cad-agent", extras = ["sim", "cad"] }]\n')
    assert agentkit._receipt_extras() == ["cad", "sim"]
    assert agentkit.installed_extras(tmp_path) == ["cad", "sim"]


def test_an_unquoted_version_and_a_pinned_tag(kit, tmp_path):
    from cadagent.project import CadConfigError, load_project
    (tmp_path / "cad-agent.yaml").write_text("cad:\n  cad-agent: 0.10\n")
    with pytest.raises(CadConfigError, match="must be a string"):
        load_project(tmp_path)
    assert "as a string" in agentkit.project_advice(tmp_path, "0.2.0")[0]
    _, clone, _ = kit
    stamp = int(git(clone, "log", "-1", "--format=%ct"))
    agentkit.pull(clone, "v0.1.0")
    assert agentkit.staleness(clone, now=stamp + 99 * 86400) is None, "a release pinned on purpose is not nagged"
