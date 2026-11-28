"""`cad-agent update` (cadagent/agentkit.py, cli.cmd_update): a temporary git repository plays cad-agent's GitHub.

Each test clones a throwaway "remote" into tmp_path the way the installer does (shallow, `main`), then moves the
remote on and checks what the update does: fast-forward only, refuse what it must not touch, follow a tag, notice a
dependency change, show the changelog with "Projects must change" first, and tell a project what to re-run. Nothing
here touches the network or the kit's own checkout.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
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
    monkeypatch.setattr(agentkit.shutil, "which", lambda name, path=None: "/bin/uv")
    cmd = agentkit.reinstall_command(tmp_path, ["cad", "fea"])
    assert cmd[:6] == ["/bin/uv", "tool", "install", "--quiet", "--force", "--editable"] and cmd[-1] == f"{tmp_path}[cad,fea]"
    monkeypatch.setattr(agentkit, "_uv_tool_env", lambda: False)
    assert agentkit.reinstall_command(tmp_path, [])[1:4] == ["-m", "pip", "install"]


RECEIPT = """[tool]
requirements = [
    { name = "cad-agent", editable = "/k/cad-agent", extras = ["cad", "fea"] },
    { name = "playwright", specifier = "==1.62.0" },
    { name = "requests", extras = ["socks"], specifier = ">=2" },
    { name = "idna", marker = "python_full_version >= '3.8'", specifier = ">=3" },
]
python = "3.12"
"""


@pytest.mark.parametrize("reader", ["tomllib", "python-3.10"])
def test_the_receipt_reads_the_same_without_tomllib(monkeypatch, reader):
    """Python 3.10 has no tomllib (#799, CI's core 3.10): the receipt's requirements read the same either way, for the
    forms uv writes: several lines, one line, and a Windows path as a TOML literal string."""
    one_line = '[tool]\nrequirements = [{ name = "cad-agent", editable = \'C:\\Users\\u\\cad-agent\', extras = ["cad"] }]\n'
    expected = [
        [{"name": "cad-agent", "editable": "/k/cad-agent", "extras": ["cad", "fea"]},
         {"name": "playwright", "specifier": "==1.62.0"},
         {"name": "requests", "extras": ["socks"], "specifier": ">=2"},
         {"name": "idna", "marker": "python_full_version >= '3.8'", "specifier": ">=3"}],
        [{"name": "cad-agent", "editable": "C:\\Users\\u\\cad-agent", "extras": ["cad"]}],
    ]
    if reader == "python-3.10":
        monkeypatch.setitem(sys.modules, "tomllib", None)            # `import tomllib` raises ImportError
    else:
        pytest.importorskip("tomllib")
    assert [agentkit._receipt_requirements(t) for t in (RECEIPT, one_line)] == expected


def test_a_uv_tool_install_keeps_its_with_packages_and_is_told_uvs_way_to_add_one(tmp_path, monkeypatch):
    """uv rebuilds a tool environment from exactly the requirements it is given, and it has no pip (#799): a reinstall
    passes the receipt's --with packages back, and the hint to add one is uv's own `tool install --with`."""
    (tmp_path / "uv-receipt.toml").write_text(RECEIPT)          # the receipt's format, as uv 0.11 writes it
    monkeypatch.setattr(agentkit.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(agentkit.shutil, "which", lambda name, path=None: "/home/u/.local/bin/uv")
    kept = ["--with", "playwright==1.62.0", "--with", "requests[socks]>=2", "--with", "idna>=3; python_full_version >= '3.8'"]
    cmd = agentkit.reinstall_command(tmp_path / "k", ["cad", "fea"])
    assert cmd[:3] == ["/home/u/.local/bin/uv", "tool", "install"] and cmd[-6:] == kept and f"{tmp_path / 'k'}[cad,fea]" in cmd
    hint = agentkit.add_packages_command("playwright")
    root = agentkit.kit_root()
    assert hint.startswith("/home/u/.local/bin/uv tool install --force --editable --python ")
    assert f"'{root}[cad,fea]'" in hint and hint.endswith("--with playwright") and "pip" not in hint
    assert "--quiet" not in hint and "--with playwright==1.62.0" in hint, "earlier --with packages stay"
    req = root / "tools" / "webkit" / "scada" / "ui" / "requirements.txt"
    assert agentkit.add_packages_command(requirements=req).endswith(f"--with-requirements {req}")
    monkeypatch.setattr(agentkit.importlib.util, "find_spec", lambda name: None)     # Playwright absent
    assert agentkit._playwright().startswith("Playwright is not installed in this Python (`/home/u/.local/bin/uv tool")
    assert f"--with-requirements {req}`" in agentkit._scada_browser()
    (tmp_path / "uv-receipt.toml").unlink()                       # a venv install: pip in this Python
    assert agentkit.add_packages_command("playwright").endswith("-m pip install playwright")


# Rows as uv 0.13.5 wrote them for `--with <folder>`, `--with-editable <folder>`, `--with <wheel>`, `--with 'name @ <url>'`
# and `--with 'name @ git+<url>@<ref>#subdirectory=<dir>'` (checked in a scratch tool install, #799), and rows uv's command
# line cannot say again exactly.
SOURCES = """[tool]
requirements = [
    { name = "cad-agent", editable = "/k/cad-agent", extras = ["cad"] },
    { name = "local-pkg", directory = "/src/local pkg" },
    { name = "dir-pkg", extras = ["x"], marker = "python_full_version >= '3.8'", directory = "/src/dirpkg" },
    { name = "ed-pkg", editable = "/src/edpkg" },
    { name = "whl-pkg", path = "/dist/whl_pkg-0.1.0-py3-none-any.whl" },
    { name = "url-pkg", url = "https://example.org/url_pkg-0.1.0-py3-none-any.whl" },
    { name = "git-pkg", git = "https://example.org/mono?subdirectory=sub&rev=v1" },
    { name = "git-head", git = "file:///src/gitpkg" },
    { name = "ed-extras", editable = "/src/edx", extras = ["x"] },
    { name = "url-query", url = "https://example.org/u.whl?token=1" },
    { name = "git-lfs", git = "https://example.org/r?rev=v1&lfs=true" },
    { name = "rel-dir", directory = "relative/dir" },
    { name = "named-index", index = "https://example.org/simple" },
]
"""


def test_packages_from_folders_files_urls_and_git_come_back_from_their_source(tmp_path, monkeypatch, capsys):
    """A row from a folder, file, URL or Git is passed back from that source, never as a bare name the index could answer
    with another package (#799 review); one uv's command line cannot say again exactly is left out and named."""
    (tmp_path / "uv-receipt.toml").write_text(SOURCES)
    monkeypatch.setattr(agentkit.sys, "prefix", str(tmp_path))
    args, dropped = agentkit._receipt_with()
    assert args == [
        "--with", "local-pkg @ file:///src/local%20pkg",
        "--with", "dir-pkg[x] @ file:///src/dirpkg ; python_full_version >= '3.8'",
        "--with-editable", "/src/edpkg",
        "--with", "whl-pkg @ file:///dist/whl_pkg-0.1.0-py3-none-any.whl",
        "--with", "url-pkg @ https://example.org/url_pkg-0.1.0-py3-none-any.whl",
        "--with", "git-pkg @ git+https://example.org/mono@v1#subdirectory=sub",
        "--with", "git-head @ git+file:///src/gitpkg",
    ]
    assert dropped == ["ed-extras", "url-query", "git-lfs", "rel-dir", "named-index"]
    for name in ("local-pkg", "ed-pkg", "whl-pkg", "url-pkg", "git-pkg"):
        assert name not in args, f"{name} is never passed as a bare name"
    monkeypatch.setattr(agentkit.shutil, "which", lambda name, path=None: "/u/bin/uv")
    monkeypatch.setattr(agentkit, "_uv_tool_env", lambda: True)
    cmd = agentkit.reinstall_command(Path("/k/cad-agent"), ["cad"])
    assert cmd[-len(args):] == args
    assert capsys.readouterr().err == ("cad-agent: not carried over by the reinstall (add them again yourself, from where "
                                       "they came): ed-extras, url-query, git-lfs, rel-dir, named-index\n")


# Hand-edited rows (#808): uv writes none of these. Each would turn the rebuilt `--with` word into something else: a URL
# requirement through the specifier or an extra, a Git remote helper that runs a command, a marker that is not one, a
# control character in the printed hint. The reinstall leaves each out and names it, as it does an unreadable row.
EDITED = """[tool]
requirements = [
    { name = "cad-agent", editable = "/k/cad-agent", extras = ["cad"] },
    { name = "kept", extras = ["socks"], specifier = ">=2", marker = "python_version >= '3'" },
    { name = "spec-url", specifier = " @ https://example.invalid/evil-0.1-py3-none-any.whl" },
    { name = "spec-junk", specifier = ">=1 --index-url https://example.invalid" },
    { name = "extra-url", extras = ["x] @ https://example.invalid/e.whl ; python_version>'0'"] },
    { name = "extra-empty", extras = [""] },
    { name = "marker-junk", specifier = ">=1", marker = "python_version >= '3' @ https://example.invalid" },
    { name = "git-ext", git = "ext::sh -c touch% /tmp/pwned" },
    { name = "git-plus-ext", git = "git+ext::sh -c touch% /tmp/pwned" },
    { name = "git-fd", git = "fd::17" },
    { name = "git-no-host", git = "https:///r?rev=v1" },
    { name = "control", directory = "/src/a\\u001b[31mred" },
    { name = "git-ssh", git = "ssh://git@example.org/r?tag=v2" },
]
"""


def test_hand_edited_receipt_rows_are_left_out_and_named(tmp_path, monkeypatch, capsys):
    (tmp_path / "uv-receipt.toml").write_text(EDITED)
    monkeypatch.setattr(agentkit.sys, "prefix", str(tmp_path))
    args, dropped = agentkit._receipt_with()
    assert args == ["--with", "kept[socks]>=2; python_version >= '3'",
                    "--with", "git-ssh @ git+ssh://git@example.org/r@v2"]
    assert dropped == ["spec-url", "spec-junk", "extra-url", "extra-empty", "marker-junk", "git-ext", "git-plus-ext",
                       "git-fd", "git-no-host", "control"]
    monkeypatch.setattr(agentkit.shutil, "which", lambda name, path=None: "/u/bin/uv")
    monkeypatch.setattr(agentkit, "_uv_tool_env", lambda: True)
    cmd = agentkit.reinstall_command(Path("/k/cad-agent"), ["cad"])
    assert cmd[-len(args):] == args and not any("example.invalid" in w or "ext::" in w for w in cmd)
    assert "spec-url, spec-junk, extra-url" in capsys.readouterr().err


# What uv 0.11.32 writes for `--with 'credpkg @ http://user:token@host/credpkg-0.1.0-py2.py3-none-any.whl'`: the URL as
# given, credentials and all (checked in a scratch tool install against a local server that asks for basic auth, #808).
# For `--with 'credpkg @ git+http://user:token@host/credpkg.git@main'` it wrote `git = "http://host/credpkg.git?rev=main"`:
# a Git row's credentials are stripped. The other rows are hand-edited.
CREDENTIALS = """[tool]
requirements = [
    { name = "cad-agent", editable = "/k/cad-agent", extras = ["cad"] },
    { name = "credpkg", url = "http://user:dummytoken@127.0.0.1:8765/credpkg-0.1.0-py2.py3-none-any.whl" },
    { name = "tokpkg", url = "https://dummytoken@example.org/tokpkg-0.1.0-py3-none-any.whl" },
    { name = "gitcred", git = "https://user:dummytoken@example.org/r?rev=v1" },
    { name = "gitssh", git = "ssh://git:dummytoken@example.org/r" },
    { url = "https://user:dummytoken@example.org/nameless.whl" },
    { name = "fine", url = "https://example.org/fine-0.1.0-py3-none-any.whl" },
]
"""


def test_a_url_holding_credentials_is_never_printed(kit, monkeypatch, capsys):
    """uv writes a `url` row's credentials into the receipt. The row is left out and named without its URL, so the token
    is in neither the hint, the reinstall command (printed when it fails, or by `update --reinstall-command`), nor stderr."""
    _, clone, _ = kit
    receipt = clone.parent / "env"
    receipt.mkdir()
    (receipt / "uv-receipt.toml").write_text(CREDENTIALS)
    monkeypatch.setattr(agentkit.sys, "prefix", str(receipt))
    monkeypatch.setattr(agentkit.shutil, "which", lambda name, path=None: "/u/bin/uv")
    args, dropped = agentkit._receipt_with()
    assert args == ["--with", "fine @ https://example.org/fine-0.1.0-py3-none-any.whl"]
    assert dropped == [f"{n} (its URL holds credentials, not shown)" for n in
                       ("credpkg", "tokpkg", "gitcred", "gitssh", "(a row without a valid name)")]
    monkeypatch.setattr(agentkit, "kit_root", lambda source=None: clone)
    monkeypatch.setattr(agentkit, "installed_extras", lambda root: ["cad"])
    assert cli.main(["update", "--reinstall-command"]) == 0
    hint = agentkit.add_packages_command("playwright")
    out, err = capsys.readouterr()
    assert "fine @ https://example.org/fine-0.1.0-py3-none-any.whl" in json.loads(out) and "fine @" in hint
    assert "dummytoken" not in out + err + hint
    assert "credpkg (its URL holds credentials, not shown)" in err


def test_the_310_reader_reads_requirements_only_from_the_tool_table(monkeypatch):
    """#808: another table's `requirements = [` before [tool] is not the receipt's list (tomllib does not read it)."""
    text = ('[other]\nrequirements = [\n    { name = "evil", specifier = "==6.6.6" },\n]\n\n[tool]\nrequirements = [\n'
            '    { name = "cad-agent", editable = "/k", extras = ["cad"] },\n]\n')
    wanted = [{"name": "cad-agent", "editable": "/k", "extras": ["cad"]}]
    if importlib.util.find_spec("tomllib"):
        import tomllib
        assert tomllib.loads(text)["tool"]["requirements"] == wanted
    monkeypatch.setitem(sys.modules, "tomllib", None)
    assert agentkit._receipt_requirements(text) == wanted
    only_other = '[other]\nrequirements = [\n    { name = "evil", specifier = "==6.6.6" },\n]\n[tool]\npython = "3.12"\n'
    with pytest.raises(agentkit.ReceiptUnreadable):              # refused rather than guessed at
        agentkit._receipt_requirements(only_other)
    top = 'requirements = [\n    { name = "evil" },\n]\n[tool]\nrequirements = [\n    { name = "cad-agent", editable = "/k" },\n]\n'
    assert agentkit._receipt_requirements(top) == [{"name": "cad-agent", "editable": "/k"}]


def test_the_310_reader_reads_a_crlf_receipt(monkeypatch):
    monkeypatch.setitem(sys.modules, "tomllib", None)
    text = '[tool]\r\nrequirements = [\r\n    { name = "cad-agent", editable = "/k" },\r\n]\r\npython = "3.12"\r\n'
    assert agentkit._receipt_requirements(text) == [{"name": "cad-agent", "editable": "/k"}]


def test_receipt_extras_that_are_not_extra_names_are_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr(agentkit.sys, "prefix", str(tmp_path))
    (tmp_path / "uv-receipt.toml").write_text(
        '[tool]\nrequirements = [{ name = "cad-agent", editable = "/x", extras = ["cad] @ https://example.invalid/x"] }]\n')
    assert agentkit._receipt_extras() is None, "the installed packages decide instead"


# The #868 review's rows: a typographic quote PowerShell reads as `'`, a `"` that Windows PowerShell 5.1 does not
# escape when it passes the argument on, non-ASCII where uv writes ASCII, and option-shaped Git hosts, refs and folders.
HOSTILE = """[tool]
requirements = [
    { name = "u1", url = "https://h/a\u2019;calc;\u2019.whl" },
    { name = "m2", specifier = ">=1", marker = "os_name != '\u2019; calc; \u2019'" },
    { name = "m3", specifier = ">=1", marker = 'python_version >= "3" and os_name != " --index-url=https://evil.example/simple "' },
    { name = "g-nonascii", git = "https://h\u00e9.example/r" },
    { name = "m-bidi", specifier = ">=1", marker = "os_name != '\u202e'" },
    { name = "q-editable", editable = '/src/a"b' },
    { name = "g-ref", git = "https://h.example/r?rev=--upload-pack=evil" },
    { name = "g-host", git = "ssh://-oProxyCommand=calc/r" },
    { name = "g-subdir", git = "https://h.example/r?subdirectory=-x" },
    { name = "kept", specifier = ">=1", marker = "os_name != 'nt'" },
]
"""


def test_review_rows_that_could_break_a_powershell_line_are_left_out(tmp_path, monkeypatch):
    (tmp_path / "uv-receipt.toml").write_text(HOSTILE, encoding="utf-8")
    monkeypatch.setattr(agentkit.sys, "prefix", str(tmp_path))
    args, dropped = agentkit._receipt_with()
    assert args == ["--with", "kept>=1; os_name != 'nt'"]
    assert dropped == ["u1", "m2", "m3", "g-nonascii", "m-bidi", "q-editable", "g-ref", "g-host", "g-subdir"]


@pytest.mark.parametrize("quote", ["'", "\u2018", "\u2019", "\u201a", "\u201b"])
def test_powershell_doubles_every_quote_it_reads_as_a_single_quote(quote):
    """PowerShell opens and closes a single-quoted string with any of these (#868 review): each is doubled inside."""
    word = f"C:\\Users\\D{quote}Angelo\\cad-agent[cad]"
    assert agentkit._shell_line(["uv", word], windows=True) == f"uv 'C:\\Users\\D{quote}{quote}Angelo\\cad-agent[cad]'"


@pytest.mark.parametrize("failed", [True, False])
def test_the_update_prints_its_reinstall_command_quoted_for_the_shell(kit, monkeypatch, capsys, failed):
    """The failure message and the Windows "finish with" line are pasted into a shell: quoted like every other hint."""
    remote, clone, _ = kit
    monkeypatch.setattr(agentkit, "kit_root", lambda source=None: clone)
    monkeypatch.setattr(agentkit, "installed_extras", lambda root: [])
    cmd = ["/u/bin/uv", "tool", "install", "--with", "idna>=3", "--with", "it\u2019s ok"]
    monkeypatch.setattr(agentkit, "reinstall_command", lambda root, extras: cmd)
    commit(remote, "deps", {"pyproject.toml": '[project]\nname = "cad-agent"\nversion = "0.2.0"\n'})
    if failed:
        monkeypatch.setattr(cli, "subprocess", types.SimpleNamespace(run=lambda c, **kw: subprocess.CompletedProcess(c, 1)))
        assert cli.main(["update"]) == 1
        assert "run update again to retry): /u/bin/uv tool install --with 'idna>=3' --with 'it\u2019s ok'" in \
            capsys.readouterr().err
    else:
        monkeypatch.setattr(cli, "os", types.SimpleNamespace(**{**vars(os), "name": "nt"}))
        assert cli.main(["update"]) == agentkit.REINSTALL_LATER
        assert "finish with: /u/bin/uv tool install --with 'idna>=3' --with 'it\u2019\u2019s ok', then" in \
            capsys.readouterr().out


# The reviewer's receipts on which a hand-written reader and tomllib could disagree (#799 review). Each is valid TOML;
# uv writes none of them. Without tomllib the reader either reads what tomllib reads or refuses: never something else.
ODD_RECEIPTS = {
    "brace in a string": '[tool]\nrequirements = [\n    { name = "cad-agent", editable = "/h/{weird}/c", extras = ["cad"] },\n]\n',
    "bracket in an extra": '[tool]\nrequirements = [\n    { name = "cad-agent", editable = "/k", extras = ["a]b"] },\n]\n',
    "comment holding a table": '[tool]\nrequirements = [\n    { name = "cad-agent", editable = "/k" },\n'
                               '    # { name = "commented", specifier = "==9" },\n]\n',
    "array of tables": '[[tool.requirements]]\nname = "cad-agent"\neditable = "/k"\n[[tool.requirements]]\nname = "x"\n',
    "nested inline table": '[tool]\nrequirements = [\n    { name = "x", index = { url = "https://example.org" } },\n]\n',
    "multi-line string before the list": '[tool]\nnote = """\nrequirements = [\n    { name = "evil" },\n]\n"""\n'
                                         'requirements = [\n    { name = "cad-agent", editable = "/k" },\n]\n',
    "multi-line literal string holding a tool table": "x = '''\n[tool]\nrequirements = [\n    { name = \"evil\" },\n]\n'''\n"
                                                      '[tool]\nrequirements = [\n    { name = "cad-agent", editable = "/k" },\n]\n',
    "duplicate tool table": '[tool]\nrequirements = [\n    { name = "evil" },\n]\n[tool]\npython = "3.12"\n',
    "duplicate requirements key": '[tool]\nrequirements = [\n    { name = "evil" },\n]\nrequirements = [\n'
                                  '    { name = "cad-agent", editable = "/k" },\n]\n',
    "indented close, entrypoints after": '[tool]\nrequirements = [\n    { name = "cad-agent", editable = "/k" },\n'
                                         '    { name = "x", specifier = ">=1" },\n    ]\nentrypoints = [\n'
                                         '    { name = "cad-agent", install-path = "/b/cad-agent", from = "cad-agent" },\n]\n',
}


@pytest.mark.parametrize("case", sorted(ODD_RECEIPTS))
def test_the_310_reader_reads_what_tomllib_reads_or_refuses(monkeypatch, case):
    text = ODD_RECEIPTS[case]
    tomllib = pytest.importorskip("tomllib")          # the reference; the fallback runs on every Python below
    try:
        wanted = [r for r in tomllib.loads(text).get("tool", {}).get("requirements", []) if isinstance(r, dict)]
    except tomllib.TOMLDecodeError:                   # not TOML (a duplicate table or key): the reader must refuse it too
        wanted = None
    monkeypatch.setitem(sys.modules, "tomllib", None)
    try:
        got = agentkit._receipt_requirements(text)
    except agentkit.ReceiptUnreadable:
        got = None
    assert got in (None, wanted), f"{case}: read {got}, tomllib reads {wanted}"


@pytest.mark.parametrize("case", ["brace in a string", "comment holding a table", "array of tables",
                                  "nested inline table", "multi-line string before the list",
                                  "multi-line literal string holding a tool table", "duplicate tool table",
                                  "duplicate requirements key"])
def test_an_unreadable_receipt_gives_no_with_rows_and_says_so(tmp_path, monkeypatch, case):
    monkeypatch.setitem(sys.modules, "tomllib", None)
    with pytest.raises(agentkit.ReceiptUnreadable):
        agentkit._receipt_requirements(ODD_RECEIPTS[case])
    (tmp_path / "uv-receipt.toml").write_text(ODD_RECEIPTS[case])
    monkeypatch.setattr(agentkit.sys, "prefix", str(tmp_path))
    args, dropped = agentkit._receipt_with()
    assert args == [] and dropped and "could not be read" in dropped[0]
    assert agentkit._receipt_extras() is None, "the installed packages decide the extras instead"


def test_the_reinstall_finds_uv_in_the_installers_folder_off_path(tmp_path, monkeypatch):
    """`~/.local/bin/cad-agent update` with that folder off PATH still reinstalls with uv (#799 review), not pip."""
    bin_dir = tmp_path / "home" / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "uv").write_text("#!/bin/sh\n")
    (bin_dir / "uv").chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_BIN_HOME", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(agentkit, "_uv_tool_env", lambda: True)
    monkeypatch.setattr(agentkit.sys, "prefix", str(tmp_path))          # no receipt: no --with rows
    assert agentkit.reinstall_command(tmp_path / "k", ["cad"])[:3] == [str(bin_dir / "uv"), "tool", "install"]


@pytest.mark.parametrize("word, pasted", [
    ("idna>=3", "'idna>=3'"),                                   # a redirect if left bare
    ("x<1", "'x<1'"), ("a|b", "'a|b'"), ("^x", "'^x'"), ("%PATH%", "'%PATH%'"),
    ("x$(touch /tmp/x)", "'x$(touch /tmp/x)'"),                 # PowerShell expands this inside double quotes
    ("it's", "'it''s'"), ("C:\\Users\\a\\cad-agent[cad]", "'C:\\Users\\a\\cad-agent[cad]'"),
    ("a,b", "'a,b'"), ("@x", "'@x'"), ("x y", "'x y'"),
    ("--with", "--with"), ("--python", "--python"), ("3.12", "3.12"), ("C:\\Users\\a\\req.txt", "C:\\Users\\a\\req.txt"),
])
def test_the_windows_hint_is_safe_to_paste_into_powershell(word, pasted):
    """#799 review: the PowerShell line single-quotes every word that is not plainly safe (quotes doubled), so nothing
    in it is a redirect, a pipe or an expansion. Checked on the text; not run on Windows here."""
    assert agentkit._shell_line(["uv", word], windows=True) == f"uv {pasted}"


def test_a_windows_uv_path_with_a_space_is_called_with_the_call_operator():
    line = agentkit._shell_line(["C:\\Users\\First Last\\.local\\bin\\uv.exe", "tool", "install", "--with", "idna>=3"],
                                windows=True)
    assert line == "& 'C:\\Users\\First Last\\.local\\bin\\uv.exe' tool install --with 'idna>=3'"
    assert agentkit._shell_line(["uv", "--with", "idna>=3"], windows=False) == "uv --with 'idna>=3'"


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


@pytest.mark.parametrize("system,machine,wants_pardiso", [
    ("Linux", "x86_64", True), ("Windows", "AMD64", True),
    ("Linux", "aarch64", False), ("Darwin", "arm64", False),
    ("Darwin", "x86_64", False), ("Windows", "ARM64", False),
    ("Linux", "i686", False), ("FreeBSD", "x86_64", False),
])
def test_fea_markers_and_update_preserve_the_platforms_installed_extra(tmp_path, monkeypatch, system, machine, wants_pardiso):
    """Use the actual project requirement, not a copied expression; absent optional MKL must not lose FEA on update."""
    import importlib.metadata as md
    from packaging import markers
    from packaging.requirements import Requirement
    from pathlib import Path
    try:
        import tomllib
    except ImportError:  # pytest supplies tomli on Python 3.10
        import tomli as tomllib

    project = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    fea = tomllib.loads(project)["project"]["optional-dependencies"]["fea"]
    pardiso = next(Requirement(r) for r in fea if Requirement(r).name == "pypardiso")
    environment = {**markers.default_environment(), "platform_system": system, "platform_machine": machine}
    # packaging 26.3 caches process facts; supply the controlled marker environment, not patched platform calls.
    monkeypatch.setattr(markers, "default_environment", lambda: dict(environment))
    assert (pardiso.marker is None or pardiso.marker.evaluate(environment)) is wants_pardiso
    monkeypatch.setattr(agentkit, "_receipt_extras", lambda: None)
    (tmp_path / "pyproject.toml").write_text(project)
    available = {Requirement(r).name for r in fea} - {"pypardiso"}

    def version(name):
        if name not in available:
            raise md.PackageNotFoundError(name)
        return "1.0"

    monkeypatch.setattr(md, "version", version)
    assert ("fea" in agentkit.installed_extras(tmp_path)) is not wants_pardiso
    available.add("pypardiso")
    assert "fea" in agentkit.installed_extras(tmp_path)
    available.remove("scikit-fem")
    assert "fea" not in agentkit.installed_extras(tmp_path), "a genuinely missing active requirement still excludes FEA"


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
