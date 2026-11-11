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
    assert set(expected) == {
        "cad-motion-validation", "cad-pr-review", "cad-remote-runs", "cad-supply-chain",
        "cad-work-tracking", "design-process", "mcmaster-parts", "pem-fastener-selection", "sheet-metal-hardware",
    }
    assert skills == expected
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


def _owned_windows_command(argv, env, cwd, stdout, stderr, timeout, status):
    """Test-only anonymous Job Object; a trusted trampoline joins before spawning the command."""
    import ctypes
    import time
    from ctypes import wintypes as w

    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', w.DWORD), ('min_working_set', ctypes.c_size_t),
                    ('max_working_set', ctypes.c_size_t), ('process_limit', w.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                    ('peak_job', ctypes.c_size_t)]

    class Accounting(ctypes.Structure):
        _fields_ = [(name, ctypes.c_longlong) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
            (name, w.DWORD) for name in ('page_faults', 'total', 'active', 'terminated')]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
    kernel.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, w.LPVOID]
    kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    assert job, ctypes.get_last_error()
    child = None
    errors = []

    def active():
        row = Accounting()
        assert kernel.QueryInformationJobObject(job, 1, ctypes.byref(row), ctypes.sizeof(row), None), ctypes.get_last_error()
        return row.active

    try:
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway permission.
        assert kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)), ctypes.get_last_error()
        os.set_handle_inheritable(job, True)
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {'handle_list': [job]}
        trampoline = r'''
import ctypes,json,subprocess,sys
from ctypes import wintypes as w
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.GetCurrentProcess.restype=w.HANDLE
k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
k.CloseHandle.argtypes=[w.HANDLE]
handle=int(sys.argv[1])
assert k.AssignProcessToJobObject(handle,k.GetCurrentProcess()),ctypes.get_last_error()
assert k.CloseHandle(handle),ctypes.get_last_error()
sys.exit(subprocess.call(json.loads(sys.argv[2])))
'''
        # Until assignment this trusted launcher can only join the job, not start installers.
        child = subprocess.Popen([sys.executable, '-c', trampoline, str(job), json.dumps(argv)],
                                 env=env, cwd=cwd, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                                 startupinfo=startup, close_fds=True)
        status['trampoline_pid'] = child.pid
        try:
            status.update(finished=True, exit=child.wait(timeout=timeout))
        except subprocess.TimeoutExpired:
            status['timed_out'] = True
            raise
    except BaseException as exc:
        status['original_error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        primary_error = sys.exc_info()[0] is not None
        try:
            remaining = active()
            status['active_before_cleanup'] = remaining
            if remaining:
                assert kernel.TerminateJobObject(job, 124), ctypes.get_last_error()
            # Also settle a launcher interrupted before its self-assignment; it cannot have spawned commands.
            if child is not None and child.poll() is None:
                child.terminate()
            if child is not None:
                child.wait(timeout=5)
            deadline = time.monotonic() + 10
            while active() and time.monotonic() < deadline:
                time.sleep(.02)
            status['active_after_cleanup'] = active()
            status['owned_processes_quiescent'] = status['active_after_cleanup'] == 0 and (child is None or child.poll() is not None)
            assert status['owned_processes_quiescent'], 'owned Windows job did not settle'
        except BaseException as exc:
            status['owned_processes_quiescent'] = False
            errors.append(type(exc).__name__ + ': ' + str(exc))
        finally:
            if not kernel.CloseHandle(job):
                errors.append('CloseHandle: ' + str(ctypes.get_last_error()))
        if errors:
            status['cleanup_errors'] = errors
            if not primary_error:
                raise RuntimeError('; '.join(errors))
    return status['exit']


@pytest.mark.skipif(os.name != 'nt' or os.environ.get('CAD_AGENT_REAL_INSTALLER') != '1',
                    reason='explicit real Windows installer study only; downloads CAD dependencies')
@pytest.mark.parametrize('shell', ['powershell', 'pwsh'])
def test_actual_windows_installer_body_and_uv_receipt(tmp_path, shell):
    """Opt-in real body/uv/exit-3 consumer. Fast guards above retain their separate scope."""
    assert shell in ('powershell', 'pwsh') and shutil.which(shell), 'the named PowerShell must actually run'
    base = Path(os.environ['CAD_AGENT_INSTALL_EVIDENCE_DIR']) / shell
    base.mkdir(parents=True, exist_ok=False)
    home = base / 'home'
    home.mkdir()
    for relative in ('tmp', 'AppData/Roaming', 'AppData/Local'):
        (home / relative).mkdir(parents=True)
    # Existing machine tools only; no original user configuration, token or package directories are lent.
    keep = ('SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'ProgramFiles', 'ProgramFiles(x86)',
            'ProgramW6432', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'PATH')
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / 'AppData/Roaming'),
               LOCALAPPDATA=str(home / 'AppData/Local'), TEMP=str(home / 'tmp'), TMP=str(home / 'tmp'),
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, PYTHONNOUSERSITE='1', PYTHONUTF8='1',
               CAD_AGENT_REF='v0.26.1')
    expected = '02cbc3c9cef53ef34a97fb24c14a133499af91ec'
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    result = {'shell': shell, 'ok': False, 'expected_commit': expected, 'completed': []}
    import time
    deadline = time.monotonic() + 30 * 60  # five minutes remain for cleanup/upload before the job's wall.

    def run(name, argv, accepted=(0,), timeout=1200):
        (base / (name + '-command.json')).write_text(json.dumps(argv))
        status = {'finished': False}
        try:
            remaining = min(timeout, deadline - time.monotonic() - 20)
            assert remaining > 0, 'study deadline reached before the next command'
            with (base / (name + '.stdout')).open('w') as out, (base / (name + '.stderr')).open('w') as err:
                code = _owned_windows_command(argv, env, home, out, err, remaining, status)
        finally:
            primary_error = sys.exc_info()[0] is not None
            try:
                (base / (name + '-status.json')).write_text(json.dumps(status))
            except BaseException:
                if not primary_error:
                    raise
        assert code in accepted and status['owned_processes_quiescent'], f'{name}: {status}; raw command/stdout/stderr retained'
        result['completed'].append(name)
        return (base / (name + '.stdout')).read_bytes().decode('utf-8-sig', errors='replace')

    def ps(name, text):
        script = base / (name + '.ps1')
        script.write_text(text, encoding='utf-8-sig')  # PS5.1 must read Unicode paths correctly.
        return run(name, [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)])

    try:
        runtime = json.loads(ps('runtime', "$ErrorActionPreference='Stop'; "
            f"if ($HOME -ne {quote(home)}) {{ throw 'PowerShell HOME escaped owned profile' }}; "
            "[pscustomobject]@{major=$PSVersionTable.PSVersion.Major; minor=$PSVersionTable.PSVersion.Minor; "
            "executable=(Get-Process -Id $PID).Path} | ConvertTo-Json -Compress"))
        assert ((runtime['major'], runtime['minor']) == (5, 1) if shell == 'powershell' else runtime['major'] == 7)
        result['runtime'] = runtime
        tag = run('tag-pin', ['git', 'ls-remote', 'https://github.com/Valpatel/cad-agent.git',
                              'refs/tags/v0.26.1'], timeout=60).split()[0]
        assert tag == expected, 'released source drift; no installation started'
        worker = ("import subprocess,sys,time; "
                  "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                  "sys.exit(7)")
        run('lifecycle-child-failure', [sys.executable, '-c', worker], accepted=(7,), timeout=10)
        with pytest.raises(subprocess.TimeoutExpired):
            run('lifecycle-timeout', [sys.executable, '-c', worker.replace('sys.exit(7)', 'time.sleep(60)')], timeout=3)
        timeout_record = json.loads((base / 'lifecycle-timeout-status.json').read_text())
        assert timeout_record['timed_out'] and timeout_record['owned_processes_quiescent']
        assert timeout_record['active_after_cleanup'] == 0
        result['actual_child_grandchild_lifecycle_controls'] = True
        # Both calls execute the exact canonical checksum/download/child procedure and the real installer body.
        first = ps('first-install', _checked_block('powershell'))
        assert 'installing the cad-agent command' in first
        exe = home / '.local/bin/cad-agent.exe'
        assert exe.is_file()
        env['PATH'] = str(exe.parent) + os.pathsep + env['PATH']
        # A machine may already supply uv. Record its real identity without requiring an unnecessary bootstrap.
        uv = Path(ps('uv-origin', '(Get-Command uv -ErrorAction Stop).Source').strip())
        assert uv.is_file()
        run('uv-version', [str(uv), '--version'])
        clone = home / 'cad-agent'
        assert run('installed-head', ['git', '-C', str(clone), 'rev-parse', 'HEAD']).strip() == expected
        tools = Path(run('tool-dir', [str(uv), 'tool', 'dir']).strip())
        assert home.resolve() in tools.resolve().parents, 'uv tools must stay inside the owned profile'
        py = tools / 'cad-agent/Scripts/python.exe'
        assert py.is_file()
        receipt_path = tools / 'cad-agent/uv-receipt.toml'

        def receipt(name, wanted):
            raw = receipt_path.read_bytes()
            (base / (name + '-uv-receipt.toml')).write_bytes(raw)
            text = run(name, [str(py), '-c',
                "import json,pathlib,tomllib; from cadagent import agentkit; import cadagent; "
                "r=tomllib.loads(pathlib.Path(__import__('sys').prefix,'uv-receipt.toml').read_text()); "
                "print(json.dumps({'requirements':r['tool']['requirements'],'origin':cadagent.__file__,"
                "'extras':agentkit.installed_extras(pathlib.Path.home()/'cad-agent')}))"])
            data = json.loads(text)
            (base / (name + '.json')).write_text(json.dumps(data, indent=2))
            req = [r for r in data['requirements'] if r.get('name') == 'cad-agent']
            assert len(req) == 1 and Path(req[0]['editable']).resolve() == clone.resolve()
            assert sorted(req[0].get('extras', [])) == data['extras'] == wanted
            assert (clone / 'software').resolve() in Path(data['origin']).resolve().parents

        receipt('before-extra', ['cad'])
        second = ps('second-install', _checked_block('powershell'))
        assert 'updating ' in second and 'nothing to reinstall' in second
        # This real cad-agent.exe holds itself open and must hand uv reinstall back with exit 3.
        pending = run('actual-exit-three', [str(exe), 'update', '--dir', str(clone), '--ref', 'v0.26.1',
                                          '--extras', 'site'], accepted=(3,))
        assert 'finish with:' in pending
        marker = clone / '.git/cad-agent-reinstall-pending'
        assert json.loads(marker.read_text())['extras'] == ['cad', 'site']
        handoff = json.loads(run('actual-reinstall-json', [str(exe), 'update', '--dir', str(clone),
                                                          '--reinstall-command']))
        assert handoff[:3] == ['uv', 'tool', 'install'] and handoff[-1] == str(clone) + '[cad,site]'
        # The unchanged body must flatten ConvertFrom-Json in THIS shell, execute real uv after exit 3,
        # acknowledge --reinstalled, then relink. No function, executable or OS call is replaced.
        third = ps('finish-pending-install', _checked_block('powershell'))
        assert 'finish with:' in third and not marker.exists()
        receipt('after-handoff', ['cad', 'site'])
        run('post-handoff-smoke', [str(py), '-c',
            "import cadquery as cq,markdown; s=cq.Workplane().box(60,40,25).shell(-2); "
            "cq.exporters.export(s,'windows-box.stl'); assert round(s.val().Volume())==17664; "
            "print(round(s.val().Volume()),markdown.__version__)"])
        run('actual-agent-instructions', [str(exe), 'agents', 'list'])
        assert run('final-head', ['git', '-C', str(clone), 'rev-parse', 'HEAD']).strip() == expected
        # Reduce only this new child's own token privilege, never machine policy or the runner's token.
        # If Developer Mode still permits symlinks, fail honestly rather than substitute an injected OSError.
        fallback = run('actual-os-denied-fallback', [str(py), '-c', r"""
import ctypes,json,os,pathlib,sys
from ctypes import wintypes as w
from cadagent import agentkit
class LUID(ctypes.Structure): _fields_=[('LowPart',w.DWORD),('HighPart',w.LONG)]
class LA(ctypes.Structure): _fields_=[('Luid',LUID),('Attributes',w.DWORD)]
class TP(ctypes.Structure): _fields_=[('PrivilegeCount',w.DWORD),('Privileges',LA*1)]
a=ctypes.WinDLL('advapi32',use_last_error=True)
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.GetCurrentProcess.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE]
a.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
a.LookupPrivilegeValueW.argtypes=[w.LPCWSTR,w.LPCWSTR,ctypes.POINTER(LUID)]
a.AdjustTokenPrivileges.argtypes=[w.HANDLE,w.BOOL,ctypes.POINTER(TP),w.DWORD,w.LPVOID,w.LPVOID]
token=w.HANDLE()
assert a.OpenProcessToken(k.GetCurrentProcess(),0x20|0x8,ctypes.byref(token)),ctypes.get_last_error()
try:
    luid=LUID()
    assert a.LookupPrivilegeValueW(None,'SeCreateSymbolicLinkPrivilege',ctypes.byref(luid)),ctypes.get_last_error()
    disable=TP(1,(LA*1)(LA(luid,0)))
    ctypes.set_last_error(0)
    assert a.AdjustTokenPrivileges(token,False,ctypes.byref(disable),0,None,None),ctypes.get_last_error()
    assert ctypes.get_last_error() in (0,1300)  # not assigned is already without that privilege
finally:
    k.CloseHandle(token)
root=pathlib.Path(sys.argv[1]); home=pathlib.Path(sys.argv[2]); home.mkdir()
probe=home/'probe-target';probe.mkdir(); link=home/'probe-link'
try:
    link.symlink_to(probe,target_is_directory=True)
except OSError as exc:
    assert exc.winerror==1314,repr(exc)
    error={'winerror':exc.winerror,'message':str(exc)}
    print(json.dumps({'actual_os_denial':error}),flush=True)
else:
    link.unlink()
    raise AssertionError('OS still permits symlinks: denied-symlink criterion remains unproven')
foreign=home/'.claude/skills/foreign/SKILL.md';foreign.parent.mkdir(parents=True);foreign.write_text('foreign keep')
result=agentkit.install(home,root)
assert not result['conflicts'] and result['done'] and all(x.startswith(('copy ','generate ')) for x in result['done']),result
skills=list((root/'.agents/skills').glob('*/SKILL.md'));roles=[p for p in (root/'.agents/agents').glob('*.md') if p.name!='README.md']
assert {p.parent.name for p in skills} == {
    'cad-motion-validation', 'cad-pr-review', 'cad-remote-runs', 'cad-supply-chain',
    'cad-work-tracking', 'design-process', 'mcmaster-parts', 'pem-fastener-selection', 'sheet-metal-hardware',
}
assert {p.stem for p in roles} == {'cad-pr-reviewer', 'cad-resume'}
for src in skills:
    target=home/'.claude/skills'/src.parent.name
    assert not target.is_symlink() and (target/'SKILL.md').read_bytes()==src.read_bytes()
for src in roles:
    target=home/'.claude/agents'/src.name
    assert not target.is_symlink() and target.read_text().startswith(src.read_text())
shared=home/'.agents/skills'
assert {p.name for p in shared.iterdir()}=={p.parent.name for p in skills}|{p.stem for p in roles}
assert all(not p.is_symlink() and (p/'SKILL.md').is_file() for p in shared.iterdir())
assert foreign.read_text()=='foreign keep'
print(json.dumps({'ok':True,'actual_os_denial':error,'installed':result,'privilege_scope':'only this disposable child process'}))
""", str(clone), str(base / 'denied-symlink-home')], timeout=120)
        assert json.loads(fallback.strip().splitlines()[-1])['ok']
        result.update(ok=True, actual_exit_three=True, actual_receipt_extras=['cad', 'site'],
                      fallback='actual OS error1314 in privilege-reduced disposable child; real agentkit copy install')
    finally:
        primary_error = sys.exc_info()[0] is not None
        try:
            (base / 'result.json').write_text(json.dumps(result, indent=2))
        except BaseException:
            if not primary_error:
                raise


def _assert_complete_copied_role(path, expected):
    assert not path.is_symlink() and path.read_text() == expected, "copied role text differs from source plus known marker"


def test_complete_copied_role_rejects_appended_instructions(tmp_path):
    from cadagent import agentkit

    home = tmp_path / 'copy-home'
    item = next(i for i in agentkit.items(ROOT) if i.kind == 'agent')
    result = agentkit.install(home, ROOT, targets=('claude',), copy=True)
    assert not result['conflicts']
    path = home / '.claude/agents' / (item.name + '.md')
    expected = item.path.read_text() + f"\n<!-- {agentkit.COPY_MARK}: copied from {item.path} -->\n"
    _assert_complete_copied_role(path, expected)
    with path.open('a') as stream:
        stream.write('Unexpected appended instruction.\n')
    with pytest.raises(AssertionError, match='copied role text differs'):
        _assert_complete_copied_role(path, expected)


@pytest.mark.skipif(os.name != 'nt' or os.environ.get('CAD_AGENT_REAL_COPY') != '1',
                    reason='explicit actual Windows copy consumer only')
def test_actual_windows_copy_content_resources_and_foreign_files(tmp_path):
    """Real --copy/CLI/filesystem, not an OS-denial or offline repository-guide claim."""
    from cadagent import agentkit

    base = Path(os.environ['CAD_AGENT_INSTALL_EVIDENCE_DIR']) / 'explicit-copy'
    base.mkdir(parents=True, exist_ok=False)
    fixture = tmp_path / 'disposable-kit'
    for part in ('.agents/skills', '.agents/agents'):
        shutil.copytree(ROOT / part, fixture / part)
    (fixture / 'software/cadagent').mkdir(parents=True)
    items = agentkit.items(fixture)
    assert sum(i.kind == 'skill' for i in items) == 8 and sum(i.kind == 'agent' for i in items) == 2
    home = tmp_path / 'copy-home'
    home.mkdir()
    # All package imports and readiness subprocesses stay in the new home; no original profile is lent.
    keep = ('SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'ProgramFiles', 'ProgramFiles(x86)',
            'ProgramW6432', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'PATH')
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONPATH=str(ROOT / 'software'),
               PYTHONNOUSERSITE='1', PYTHONUTF8='1', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               APPDATA=str(home / 'AppData/Roaming'), LOCALAPPDATA=str(home / 'AppData/Local'),
               TEMP=str(tmp_path), TMP=str(tmp_path))
    result = {'ok': False, 'scope': 'actual explicit Windows copy only; automatic OS-denied fallback unproven'}

    def run(name, target_home, accepted=(0,)):
        argv = [sys.executable, '-m', 'cadagent.cli', 'agents', 'install', '--source', str(fixture),
                '--home', str(target_home), '--copy']
        (base / (name + '-command.json')).write_text(json.dumps(argv))
        status = {'finished': False}
        try:
            with (base / (name + '.stdout')).open('w') as out, (base / (name + '.stderr')).open('w') as err:
                code = _owned_windows_command(argv, env, home, out, err, 120, status)
        finally:
            primary_error = sys.exc_info()[0] is not None
            try:
                (base / (name + '-status.json')).write_text(json.dumps(status))
            except BaseException:
                if not primary_error:
                    raise
        assert code in accepted and status['owned_processes_quiescent'], status

    expected = {}
    for item in items:
        if item.kind == 'skill':
            rows = {p.relative_to(item.path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in item.path.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
            expected[item.name] = rows
        else:
            expected[item.name] = {'role': item.path.read_text() + f'\n<!-- {agentkit.COPY_MARK}: copied from {item.path} -->\n',
                                   'generated': agentkit.codex_agent_skill(item)}
    (base / 'expected-instructions.json').write_text(json.dumps(expected, indent=2))
    foreign = home / '.claude/skills/foreign/SKILL.md'
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b'foreign instructions: keep exact\n')
    original_foreign = foreign.read_bytes()
    try:
        run('first-copy', home)
        run('second-copy', home)
        collision_home = tmp_path / 'collision-home'
        collision = collision_home / '.claude/skills/design-process/SKILL.md'
        collision.parent.mkdir(parents=True)
        collision.write_bytes(b'foreign same-name instructions: keep exact\n')
        run('foreign-collision', collision_home, accepted=(1,))
        assert collision.read_bytes() == b'foreign same-name instructions: keep exact\n'
        # Only this disposable fixture is removed, never ROOT, a worktree or an existing environment.
        shutil.rmtree(fixture)
        for item in items:
            if item.kind == 'skill':
                for relative in ('.claude/skills', '.agents/skills'):
                    copied = home / relative / item.name
                    assert not copied.is_symlink()
                    actual = {p.relative_to(copied).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in copied.rglob('*') if p.is_file() and p.name != agentkit.COPY_MARK}
                    assert actual == expected[item.name], (relative, item.name)
            else:
                role = home / '.claude/agents' / (item.name + '.md')
                shared = home / '.agents/skills' / item.name
                _assert_complete_copied_role(role, expected[item.name]['role'])
                assert not shared.is_symlink() and (shared / 'SKILL.md').read_text() == expected[item.name]['generated']
        assert foreign.read_bytes() == original_foreign
        assert {p.name for p in (home / '.agents/skills').iterdir()} == {i.name for i in items}
        result.update(ok=True, claude_skills=sum(i.kind == 'skill' for i in items),
                      claude_roles=sum(i.kind == 'agent' for i in items), shared_skills=len(items),
                      copied_resource_files=sum(len(expected[i.name]) for i in items if i.kind == 'skill'),
                      unrelated_foreign_unchanged=True, same_name_foreign_unchanged=True,
                      source_removed='only owned disposable fixture', automatic_denial=False)
    finally:
        primary_error = sys.exc_info()[0] is not None
        try:
            (base / 'result.json').write_text(json.dumps(result, indent=2))
        except BaseException:
            if not primary_error:
                raise
