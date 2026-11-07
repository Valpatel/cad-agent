"""The installers and their canonical checksum-before-execution guide (#282, #322).

install.sh runs here for real, twice, in a temporary HOME against a file:// copy of this checkout: the first run
clones and installs, the second takes the `cad-agent update` path. uv is a stand-in that records what it was asked and
puts a `cad-agent` that runs the clone's code in ~/.local/bin, so nothing is downloaded; the real uv and PyPI path is
proved by `tools/quickstart_eval.py install` (README in tests/cli). The two scripts must say the same things, and both
must pass their linters when those are installed (shellcheck; PowerShell's own parser).
The actual pasted guards run with inert downloads and handoff fixtures: success reaches the real POSIX option
parser, failures reach no shell/child; PowerShell guards also run in the bounded Windows CI job.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SH = ROOT / "tools" / "site" / "assets" / "install.sh"
PS1 = ROOT / "tools" / "site" / "assets" / "install.ps1"
INSTALL_GUIDE = ROOT / "docs" / "practice" / "agent-workflow.md"
PASTE = (ROOT / "docs" / "agent-prompt.txt").read_text().split("\n", 1)[0]
GIT = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_NOSYSTEM": "1"}
FAKE_UV = """#!/bin/sh
# Stand-in for uv: records each call. `tool install --editable <dir>[extras]` puts a cad-agent that runs <dir>'s code
# in a tool environment with uv's receipt (so cad-agent knows uv installed it, and with which extras).
printf '%s\\n' "$*" >> "${HOME:?}/uv-calls.log"
[ "$1 $2" = "tool install" ] || [ "$1 $2" = "tool uninstall" ] || exit 0
mkdir -p "${HOME:?}/.local/bin"
if [ "$2" = uninstall ]; then rm -f "${HOME:?}/.local/bin/cad-agent"; exit 0; fi
for last; do :; done
extras=$(printf '%s' "$last" | sed -n 's/.*\\[\\(.*\\)\\]$/\\1/p' | sed 's/\\([^,]*\\)/"\\1"/g; s/,/, /g')
printf '[tool]\\nrequirements = [{ name = "cad-agent", editable = "%s", extras = [%s] }]\\n' "${last%%[*}" "$extras" \\
    > "@ENV@/uv-receipt.toml"
printf '#!/bin/sh\\nPYTHONPATH="%s:@SITE@" exec "@ENV@/bin/python" -m cadagent.cli "$@"\\n' "${last%%[*}/software" \\
    > "${HOME:?}/.local/bin/cad-agent"
chmod +x "${HOME:?}/.local/bin/cad-agent"
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT, "GIT_CONFIG_GLOBAL": os.devnull}).stdout.strip()


@pytest.fixture
def world(tmp_path):
    """A remote holding this checkout's kit (as it is on disk), an empty HOME, and a PATH with the fake uv."""
    remote = tmp_path / "remote"
    for part in ("software/cadagent", ".agents"):
        shutil.copytree(ROOT / part, remote / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("pyproject.toml", "CHANGELOG.md"):
        shutil.copy(ROOT / f, remote / f)
    _git(remote, "init", "-q", "-b", "main")
    _git(remote, "add", "-A")
    _git(remote, "commit", "-q", "-m", "kit")
    tools = tmp_path / "tools"
    tools.mkdir()
    env_dir = tmp_path / "tool-env"                 # what `uv tool install` makes: a Python of its own
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(env_dir)], check=True)
    site = ":".join(dict.fromkeys(sysconfig.get_paths()[k] for k in ("purelib", "platlib")))   # PyYAML, NumPy
    (tools / "uv").write_text(FAKE_UV.replace("@ENV@", str(env_dir)).replace("@SITE@", site))
    (tools / "uv").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {**GIT, "HOME": str(home), "PATH": f"{tools}:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
           "CAD_AGENT_REPO": f"file://{remote}", "GIT_CONFIG_GLOBAL": os.devnull}
    return remote, home, env


def _install(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["sh", str(SH), *args], env=env, capture_output=True, text=True, timeout=300)


def _checked_block(platform):
    guide = INSTALL_GUIDE.read_text()
    language = "sh" if platform == "posix" else "powershell"
    blocks = re.findall(r"<!-- checked-installer:" + platform + r" -->\n```" + language + r"\n(.*?)\n```", guide, re.S)
    assert len(blocks) == 1, "one canonical executable procedure per platform"
    return blocks[0]


def _snapshot_bytes(source):
    # The immutable download is Git's blob, not a Windows checkout's possible CRLF conversion.
    return subprocess.run(["git", "show", "HEAD:" + source.relative_to(ROOT).as_posix()], cwd=ROOT,
                          check=True, capture_output=True).stdout


def test_checked_installers_pin_the_actual_snapshot_bytes():
    for platform, source in (("posix", SH), ("powershell", PS1)):
        block = _checked_block(platform)
        assert hashlib.sha256(_snapshot_bytes(source)).hexdigest() in block
        assert re.search(r"https://raw\.githubusercontent\.com/Valpatel/cad-agent/[a-f0-9]{40}/tools/site/assets/" + re.escape(source.name), block)
        assert "Installer checksum mismatch" in block


@pytest.mark.parametrize("hasher", ["sha256sum", "shasum"])
@pytest.mark.parametrize("outcome", ["good", "corrupt", "download-failed"])
def test_actual_posix_guide_checks_before_real_installer_handoff(tmp_path, hasher, outcome):
    """Execute the pasted block, with an inert download and sh --help handoff: no network or real install."""
    command = _checked_block("posix")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for executable in ("mktemp", "rm", hasher):
        target = shutil.which(executable)
        if not target:
            pytest.skip(f"{executable} is not installed")
        (bindir / executable).symlink_to(target)
    downloaded, handed = tmp_path / "download.json", tmp_path / "handoff.json"
    payload = tmp_path / "source.sh"
    payload.write_bytes(_snapshot_bytes(SH))
    curl = bindir / "curl"
    curl.write_text(f'''#!{sys.executable}
import json,sys
from pathlib import Path
args=sys.argv[1:]; output=Path(args[args.index('-o')+1])
Path({str(downloaded)!r}).write_text(json.dumps({{'args':args,'output':str(output)}}))
data=Path({str(payload)!r}).read_bytes()
output.write_bytes(data + (b'\\ncorrupt' if {outcome!r}=='corrupt' else b''))
sys.exit(22 if {outcome!r}=='download-failed' else 0)
''')
    curl.chmod(0o755)
    shell = bindir / "sh"
    shell.write_text(f'''#!{sys.executable}
import hashlib,json,os,sys
from pathlib import Path
file=Path(sys.argv[1])
Path({str(handed)!r}).write_text(json.dumps({{'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'args':sys.argv[1:]}}))
os.execv('/bin/sh',['sh',str(file),'--help'])
''')
    shell.chmod(0o755)
    env = {**os.environ, "PATH": str(bindir), "TMPDIR": str(tmp_path), "PYTHONNOUSERSITE": "1"}
    result = subprocess.run(["/bin/bash", "-c", command], env=env, capture_output=True, text=True, timeout=15)
    download = json.loads(downloaded.read_text())
    assert not Path(download["output"]).exists(), "the pasted procedure cleans its temporary script"
    assert "--proto" in download["args"] and "=https" in download["args"]
    if outcome == "good":
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(handed.read_text())["sha256"] == hashlib.sha256(_snapshot_bytes(SH)).hexdigest()
        assert "cad-agent: install or update cad-agent:" in result.stdout, "the real installer option parser was reached"
    else:
        assert result.returncode != 0 and not handed.exists(), "failed input must never reach the shell"
        if outcome == "corrupt":
            assert "Installer checksum mismatch" in result.stderr


@pytest.mark.skipif(not shutil.which("pwsh"), reason="PowerShell (pwsh) is not installed")
@pytest.mark.parametrize("outcome", ["good", "corrupt", "download-failed", "child-failed"])
def test_actual_powershell_guide_checks_before_process_handoff(tmp_path, outcome):
    """Real PowerShell/hash/try-finally, inert downloader and child sink; no network or real installation."""
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    downloaded, handed = tmp_path / "download.json", tmp_path / "handoff.json"
    payload = tmp_path / "source.ps1"
    payload.write_bytes(_snapshot_bytes(PS1))
    sink = tmp_path / "child.ps1"
    sink.write_text('param([switch]$NoProfile, [string]$ExecutionPolicy, [string]$File)\n'
                    f"@{{sha256=(Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant(); "
                    "noProfile=[bool]$NoProfile; policy=$ExecutionPolicy} | ConvertTo-Json -Compress | "
                    f"Set-Content -LiteralPath {quote(handed)}\n"
                    f"$global:LASTEXITCODE = {7 if outcome == 'child-failed' else 0}\n")
    prefix = f'''
function Invoke-WebRequest {{
  param([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing, [string]$ErrorAction)
  @{{uri=$Uri; output=$OutFile}} | ConvertTo-Json -Compress | Set-Content -LiteralPath {quote(downloaded)}
  if ({quote(outcome)} -eq 'download-failed') {{ throw 'fixture download refused' }}
  Copy-Item -LiteralPath {quote(payload)} -Destination $OutFile
  if ({quote(outcome)} -eq 'corrupt') {{ [IO.File]::WriteAllBytes($OutFile, [byte[]]([IO.File]::ReadAllBytes($OutFile) + 0)) }}
}}
function Get-Process {{ param([int]$Id) [pscustomobject]@{{Path={quote(sink)}}} }}
'''
    script = tmp_path / "checked.ps1"
    script.write_text(prefix + _checked_block("powershell"))
    result = subprocess.run(["pwsh", "-NoProfile", "-File", str(script)], capture_output=True, text=True, timeout=20)
    download = json.loads(downloaded.read_text(encoding="utf-8-sig"))
    assert not Path(download["output"]).exists(), "finally cleans the downloaded script"
    assert re.search(r"/[a-f0-9]{40}/tools/site/assets/install\.ps1$", download["uri"])
    if outcome in ("good", "child-failed"):
        receipt = json.loads(handed.read_text(encoding="utf-8-sig"))
        assert receipt == {"sha256": hashlib.sha256(_snapshot_bytes(PS1)).hexdigest(), "noProfile": True, "policy": "Bypass"}
        assert (result.returncode == 0) is (outcome == "good"), result.stdout + result.stderr
        if outcome == "child-failed":
            assert "Installer exited with code 7" in result.stderr
    else:
        assert result.returncode != 0 and not handed.exists(), "failed input never reaches a child process"
        if outcome == "corrupt":
            assert "Installer checksum mismatch" in result.stderr


def test_it_installs_then_a_second_run_updates(world):
    remote, home, env = world
    first = _install(env)
    assert first.returncode == 0, first.stdout + first.stderr
    kit = home / "cad-agent"
    assert _git(kit, "rev-parse", "HEAD") == _git(remote, "rev-parse", "HEAD")
    assert _git(kit, "rev-parse", "--is-shallow-repository") == "true", "a shallow clone of main"
    calls = (home / "uv-calls.log").read_text().splitlines()
    assert calls == [f"tool install --quiet --force --editable --python 3.12 {kit}[cad]"]
    skills = sorted(p.name for p in (home / ".claude" / "skills").iterdir())
    expected = sorted(p.parent.name for p in (kit / ".agents/skills").glob("*/SKILL.md"))
    assert len(expected) == 8 and skills == expected
    assert (kit / "software/cadagent/cli.py").is_file()
    assert (home / ".claude" / "skills" / "design-process").resolve() == kit / ".agents/skills/design-process"
    assert {p.name for p in (home / ".agents" / "skills").iterdir()} >= set(skills), "the same skills for the other agents"
    assert (home / ".claude" / "agents" / "cad-pr-reviewer.md").is_symlink()
    assert PASTE in first.stdout, "it ends with the line to paste into an agent"
    assert "is not on your PATH yet" in first.stdout
    assert not (home / ".bashrc").exists() and not (home / ".profile").exists(), "no shell profile is edited"

    new = (remote / "NEWS.txt")
    new.write_text("x\n")
    _git(remote, "add", "-A")
    _git(remote, "commit", "-q", "-m", "more")
    second = _install(env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "cad-agent: updating" in second.stdout and "update: " in second.stdout
    assert "dependencies unchanged, nothing to reinstall" in second.stdout
    assert _git(kit, "rev-parse", "HEAD") == _git(remote, "rev-parse", "HEAD"), "fast-forwarded to the new main"
    assert len((home / "uv-calls.log").read_text().splitlines()) == 1, "no reinstall when the dependencies are the same"

    log = lambda: (home / "uv-calls.log").read_text().splitlines()
    with (remote / "pyproject.toml").open("a") as f:      # a dependency change: reinstall, with the extras it had
        f.write("# a new dependency would go here\n")
    _git(remote, "commit", "-qam", "deps")
    third = _install(env)
    assert third.returncode == 0, third.stdout + third.stderr
    assert "the dependencies changed" in third.stdout and log()[-1].endswith(f"{kit}[cad]"), log()
    fourth = _install(env, "--extras", "fea")               # adding an extra: reinstall with both
    assert fourth.returncode == 0, fourth.stdout + fourth.stderr
    assert "extras added: fea" in fourth.stdout and log()[-1].endswith(f"{kit}[cad,fea]"), log()
    calls = len(log())
    _git(remote, "tag", "v9.9.9")
    (remote / "NEWS.txt").write_text("after the release\n")
    _git(remote, "commit", "-qam", "after v9.9.9")
    pinned = _install(env, "--ref", "v9.9.9")               # a release tag: pinned, detached
    assert pinned.returncode == 0, pinned.stdout + pinned.stderr
    assert _git(kit, "rev-parse", "HEAD") == _git(remote, "rev-parse", "v9.9.9"), pinned.stdout
    back = _install(env)                                    # and back to main
    assert back.returncode == 0 and _git(kit, "rev-parse", "HEAD") == _git(remote, "rev-parse", "main"), back.stderr
    assert log()[calls:] == [], "moving between commits with the same dependencies reinstalls nothing"

    (kit / "pyproject.toml").write_text("mine\n")
    refused = _install(env)
    assert refused.returncode != 0 and "fork Valpatel/cad-agent" in refused.stderr + refused.stdout
    (kit / "pyproject.toml").write_text((remote / "pyproject.toml").read_text())

    gone = _install(env, "--uninstall")
    assert gone.returncode == 0, gone.stderr
    left = lambda d: sorted(p.name for p in d.iterdir()) if d.is_dir() else []
    assert not (home / ".local" / "bin" / "cad-agent").exists()
    assert left(home / ".claude" / "skills") == left(home / ".agents" / "skills") == [], "every skill it placed is gone"
    assert kit.is_dir(), "the checkout stays"


def test_bad_options_and_a_folder_that_is_not_a_checkout_are_refused(world):
    _, home, env = world
    for args, says in ((["--extras", "fea;rm -rf ~"], "comma-separated"), (["--ref", "--upload-pack=x"], "tag or branch"),
                       (["--frobnicate"], "unknown option")):
        r = _install(env, *args)
        assert r.returncode != 0 and says in r.stderr, (args, r.stderr)
    (home / "cad-agent").mkdir()
    r = _install(env)
    assert r.returncode != 0 and "is not a git checkout" in r.stderr
    assert not (home / "uv-calls.log").exists(), "nothing was installed"


def test_the_two_scripts_say_the_same_things():
    sh, ps = SH.read_text(), PS1.read_text()
    pin = lambda text: re.search(r"UV_?VERSION\s*=\s*['\"]([\d.]+)['\"]", text, re.I).group(1)
    assert pin(sh) == pin(ps), "the same uv release"
    for url in ("https://astral.sh/uv/", "https://github.com/Valpatel/cad-agent", "https://docs.astral.sh/uv/"):
        assert url in sh and url in ps, url
    from cadagent.cli import OPT_OUTS
    in_sh = dict(re.findall(r'(\w+)="\$\{\1:-(\w+)\}"', sh))
    in_ps = dict(re.findall(r"(\w+) = '(\w+)'", ps.split("$optOuts = @{", 1)[1].split("}", 1)[0]))
    assert in_sh == in_ps and in_sh, "the same usage-reporting opt-outs, with the same values"
    assert all(OPT_OUTS[k][0] == v for k, v in in_sh.items()), "the values cadagent.cli.OPT_OUTS gives"
    for text in (sh, ps):
        assert PASTE in text, "both end with the paste-in line"
        assert "--python 3.12" in text and "--editable" in text and "agents install" in text
        assert "update" in text and "UV_NO_MODIFY_PATH" in text
    assert not re.search(r"^\s*sudo\b", sh, re.M) and "RunAs" not in ps, "no elevation"
    assert sh.rstrip().endswith('main "$@"') and ps.rstrip().endswith("Install-CadAgent"), \
        "the work happens on the last line, so a download cut short runs nothing"


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck is not installed")
def test_install_sh_passes_shellcheck():
    r = subprocess.run(["shellcheck", "-s", "sh", str(SH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


@pytest.mark.skipif(not shutil.which("pwsh"), reason="PowerShell (pwsh) is not installed")
def test_install_ps1_parses(tmp_path):
    check = tmp_path / "parse.ps1"
    check.write_text("param($Path)\n$e = $null\n"
                     "[System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$null, [ref]$e) | Out-Null\n"
                     "if ($e) { $e | ForEach-Object { $_.ToString() }; exit 1 }\n")
    r = subprocess.run(["pwsh", "-NoProfile", "-File", str(check), str(PS1)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_cad_agent_from_somewhere_else_on_path_is_left_alone(world):
    """Only the installer's own cad-agent (uv's, in ~/.local/bin) takes the update path; another one on PATH (a venv
    the person has active) is never asked to update, and the command is installed from the checkout instead."""
    remote, home, env = world
    assert _install(env).returncode == 0
    decoy = Path(env["PATH"].split(":")[0]) / "cad-agent"
    decoy.write_text(f'#!/bin/sh\ntouch "{home}/decoy-ran"\nexit 1\n')
    decoy.chmod(0o755)
    (home / ".local" / "bin" / "cad-agent").unlink()
    again = _install(env)
    assert again.returncode == 0, again.stdout + again.stderr
    assert not (home / "decoy-ran").exists() and "found " in again.stdout
    assert len((home / "uv-calls.log").read_text().splitlines()) == 2, "installed again from the checkout"
