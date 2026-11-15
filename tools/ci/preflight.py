#!/usr/bin/env python3
"""Local preflight: from the files a branch changes, list and run the checks CI will run on them (#759).

    python3 tools/ci/preflight.py                      # changes since origin/dev, plus uncommitted ones; run what can run
    python3 tools/ci/preflight.py --list               # print the selected checks and what this machine lacks; run nothing
    python3 tools/ci/preflight.py --json               # the same report as JSON, for agents
    python3 tools/ci/preflight.py --base origin/main   # another diff base (the merge base with it, as `git diff A...HEAD`)
    python3 tools/ci/preflight.py --paths a.mjs b.py   # explicit paths instead of a diff
    python3 tools/ci/preflight.py --only scada-scenario-thumbnails --python ~/venvs/scada312/bin/python
    python3 tools/ci/preflight.py --slow               # also the checks the repo marks slow (site build, full suites)

The mapping from changed paths to checks is data: ``.github/ci-checks.json``, next to the workflows it mirrors.
``tests/repo/ci/test_ci_checks.py`` fails when a check a pull-request workflow runs has no entry there, so it cannot drift.

Each selected check is reported as one of:

* ``passed`` / ``failed``: it ran here. A pass on a different browser or Python than CI's is evidence, not CI's result;
  the report says what differed.
* ``not run: <reason>``: this machine lacks what it needs (a Playwright engine of the right revision, the Python minor
  CI pins when the check is sensitive to it, installed Node dependencies, Windows). Never counted as passed.
* ``skipped: slow``: the repo marks it slow; ``--slow`` runs it.

Exit status: 0 when every check that ran passed (or none was selected), 1 when a check that ran failed, 2 on a usage
or setup error. ``--list`` exits 0.

Limits, stated plainly:

* It mirrors CI; it does not replace it. CI's container image, browser builds and pinned Python are what decide.
* It installs nothing and uses no network: no ``npm ci``, ``pip install`` or ``playwright install``. It says what to
  install instead.
* It runs the checkout's own check commands (npm scripts, tests), exactly as CI does, so it executes the branch's code.
  Run it only on branches you would run the tests of.
* Path globs choose what to run. A change whose effect reaches a check through a path the mapping does not name is
  missed here and caught by CI.
* The site build reads HEAD (committed files); other checks read the working tree.

Stdlib only, so it runs under any Python 3.10+ without the toolkit's dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAPPING = ROOT / ".github" / "ci-checks.json"
NODE_PLAYWRIGHT = "tools/site/node_modules/playwright-core/browsers.json"
CHROME_CHANNEL = Path("/opt/google/chrome/chrome")        # where Playwright's `chrome` channel looks on Linux
PYTHON_NAMES = ["python3", "python3.10", "python3.11", "python3.12", "python3.13", "python3.14"]
TAIL_LINES = 20

# Run by each candidate interpreter (with -I, so nothing from the checkout is imported): its version, which of the
# asked modules it can find (find_spec only locates, it runs no package code), installed distribution versions, and
# where its Python Playwright keeps browsers.json.
PROBE = r"""
import importlib.util, importlib.metadata, json, sys, os
mods, dists = json.loads(sys.argv[1]), json.loads(sys.argv[2])
found = {}
for m in mods:
    try: found[m] = importlib.util.find_spec(m) is not None
    except Exception: found[m] = False
versions = {}
for d in dists:
    try: versions[d] = importlib.metadata.version(d)
    except Exception: versions[d] = None
pw = None
try:
    spec = importlib.util.find_spec("playwright")
    if spec and spec.submodule_search_locations:
        cand = os.path.join(list(spec.submodule_search_locations)[0], "driver", "package", "browsers.json")
        pw = cand if os.path.exists(cand) else None
except Exception: pass
print(json.dumps({"version": "%d.%d.%d" % sys.version_info[:3], "prefix": sys.prefix, "modules": found, "dists": versions, "playwright": pw}))
"""


# ---------------------------------------------------------------------------------------------------------------------
# Path matching


def glob_regex(pattern: str) -> re.Pattern:
    """A repo-relative glob as a regex: ``**`` spans folders, ``*`` and ``?`` stay inside one path segment."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, globs: list[str]) -> bool:
    return any(glob_regex(g).match(path) for g in globs)


def matched_paths(check: dict, paths: list[str]) -> list[str]:
    """The changed paths that select ``check``: in its ``paths`` and not in its ``exclude``."""
    return [p for p in paths if matches(p, check.get("paths", [])) and not matches(p, check.get("exclude", []))]


@dataclass
class Instance:
    """One selected check: an entry of the mapping, expanded over its engine matrix and ``per_match`` captures."""
    check: dict
    engine: str | None = None
    subs: dict = field(default_factory=dict)
    because: list = field(default_factory=list)
    status: str = "selected"           # selected | passed | failed | not run | skipped
    reason: str = ""
    notes: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    python: str | None = None
    seconds: float | None = None
    log: str | None = None
    tail: str = ""

    @property
    def id(self) -> str:
        name = self.check["id"]
        if self.subs:
            name += ":" + ",".join(str(v) for v in self.subs.values())
        return name + (f"[{self.engine}]" if self.engine else "")

    def command(self, ctx: dict) -> str:
        return self.check["command"].format(**ctx, **self.subs)


def select(mapping: dict, paths: list[str], root: Path = ROOT) -> list[Instance]:
    """Every check the changed ``paths`` select, in the mapping's order (the order CI runs them in)."""
    selected = []
    for check in mapping["checks"]:
        hit = matched_paths(check, paths)
        if not hit:
            continue
        groups: dict[tuple, list[str]] = {}
        if check.get("per_match"):
            rx = re.compile(check["per_match"])
            for p in hit:
                m = rx.match(p)
                if m and all(next(root.glob(v.format(**m.groupdict())), None)
                             for v in check.get("per_match_requires", [])):
                    groups.setdefault(tuple(sorted(m.groupdict().items())), []).append(p)
        else:
            groups[()] = hit
        for key, because in groups.items():
            for engine in check.get("engines") or [None]:
                selected.append(Instance(check, engine, dict(key), because))
    return selected


# ---------------------------------------------------------------------------------------------------------------------
# What this machine has


class Machine:
    """Capabilities, each probed once: interpreters, Playwright browser builds, installed Node dependencies."""

    def __init__(self, root: Path = ROOT, pythons: list[str] | None = None, env: dict | None = None):
        self.root = root
        self.env = dict(os.environ if env is None else env)
        self.extra_pythons = pythons or []
        self._probes: dict[tuple, dict | None] = {}

    # Interpreters ----------------------------------------------------------------------------------------------------
    def python_candidates(self) -> list[str]:
        seen, out = set(), []
        names = list(self.extra_pythons) + [sys.executable]
        if self.env.get("VIRTUAL_ENV"):
            names.append(str(Path(self.env["VIRTUAL_ENV"]) / "bin" / "python"))
        names += [shutil.which(n, path=self.env.get("PATH")) or "" for n in PYTHON_NAMES]
        for n in names:
            if n and Path(n).exists() and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def probe(self, exe: str, modules: list[str], dists: list[str], pythonpath: str | None) -> dict | None:
        key = (exe, tuple(modules), tuple(dists), pythonpath)
        if key not in self._probes:
            env = {k: v for k, v in self.env.items() if not k.startswith("PYTHON")}
            # -I ignores PYTHONPATH, so a checkout path is added by hand where the check itself sets it
            code = (f"import sys; sys.path.insert(0, {pythonpath!r})\n" if pythonpath else "") + PROBE
            try:
                out = subprocess.run([exe, "-I", "-c", code, json.dumps(modules), json.dumps(dists)], env=env,
                                     capture_output=True, text=True, timeout=30)
                self._probes[key] = json.loads(out.stdout) if out.returncode == 0 else None
            except (OSError, subprocess.SubprocessError, ValueError):
                self._probes[key] = None
        return self._probes[key]

    def choose_python(self, need: dict, pythonpath: str | None) -> tuple[str | None, dict | None, str]:
        """``(interpreter, probe, problem)`` for a check's Python need. Prefers CI's minor; takes another minor only
        when the need is not ``exact``. ``problem`` says what was found when nothing fits."""
        want = need.get("version")
        modules = need.get("modules", [])
        pins = need.get("dists", [])                      # "name==version"
        dists = [p.split("==")[0] for p in pins]
        fits, wrong_minor, lacking, seen = [], [], [], set()
        for exe in self.python_candidates():
            p = self.probe(exe, modules, dists, pythonpath)
            if not p or (p["version"], p["prefix"]) in seen:      # one line per environment, not per name for it
                continue
            seen.add((p["version"], p["prefix"]))
            minor = ".".join(p["version"].split(".")[:2])
            missing = [m for m in modules if not p["modules"].get(m)]
            missing += [pin for pin in pins if p["dists"].get(pin.split("==")[0]) != pin.split("==")[1]]
            if missing:
                lacking.append(f"{exe} ({minor}) lacks {', '.join(missing)}")
            elif want and minor != want:
                wrong_minor.append((exe, p, minor))
            else:
                fits.append((exe, p))
        if fits:
            return fits[0][0], fits[0][1], ""
        if wrong_minor and not need.get("exact"):
            exe, p, _ = wrong_minor[0]
            return exe, p, ""
        parts = []
        if wrong_minor:
            parts.append("version differs: " + "; ".join(f"{e} is {m}" for e, _, m in wrong_minor)
                         + f", CI pins {want}" + (f" ({need['why']})" if need.get("why") else ""))
        if lacking:
            parts.append("; ".join(lacking))
        if not parts:
            parts.append("no Python interpreter found")
        hint = "pass --python <interpreter>" + (f" for Python {want}" if want else "")
        if modules or pins:
            hint += " with " + ", ".join(modules + pins)
        return None, None, "; ".join(parts) + f" ({hint})"

    # Browsers --------------------------------------------------------------------------------------------------------
    def browser_dirs(self) -> list[Path]:
        dirs = []
        if self.env.get("PLAYWRIGHT_BROWSERS_PATH") not in (None, "", "0"):
            dirs.append(Path(self.env["PLAYWRIGHT_BROWSERS_PATH"]))
        dirs.append(Path(self.env.get("HOME", "~")).expanduser() / ".cache" / "ms-playwright")
        return [d for d in dirs if d.is_dir()]

    @staticmethod
    def revisions(browsers_json: Path) -> dict[str, str]:
        try:
            return {b["name"]: b["revision"] for b in json.loads(browsers_json.read_text())["browsers"]}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def installed(self, folder: str) -> Path | None:
        return next((d / folder for d in self.browser_dirs() if (d / folder).is_dir()), None)

    def present_builds(self, prefix: str) -> list[str]:
        return sorted({p.name for d in self.browser_dirs() for p in d.glob(prefix + "-*")})

    def node_engine(self, engine: str) -> tuple[dict | None, str, list[str]]:
        """``(env, problem, notes)`` to run a Node Playwright suite in ``engine``, as CI's matrix does."""
        revs = self.revisions(self.root / NODE_PLAYWRIGHT)
        if not revs:
            return None, "Node Playwright is not installed in tools/site (run `npm ci` there)", []
        if engine == "webkit":
            rev = revs.get("webkit")
            if rev and self.installed(f"webkit-{rev}"):
                return {"PLAYWRIGHT_BROWSER": "webkit"}, "", []
            have = self.present_builds("webkit")
            return None, (f"WebKit r{rev} for Playwright is not installed"
                          + (f" (found {', '.join(have)})" if have else "")
                          + "; CI runs it in its pinned Playwright container. Not installed for you."), []
        rev = revs.get("chromium-headless-shell") or revs.get("chromium")
        if rev and self.installed(f"chromium_headless_shell-{rev}") and self.installed(f"chromium-{rev}"):
            return {"PLAYWRIGHT_BROWSER": "chromium", "PLAYWRIGHT_CHANNEL": "chromium"}, "", []
        have = self.present_builds("chromium")
        if CHROME_CHANNEL.exists():
            return ({"PLAYWRIGHT_BROWSER": "chromium"}, "",
                    [f"runs on the local Chrome ({CHROME_CHANNEL}, Playwright's `chrome` channel), not CI's Playwright "
                     f"Chromium r{rev}" + (f" (installed here: {', '.join(have)})" if have else "") + ": evidence only"])
        return None, (f"Playwright Chromium r{rev} is not installed" + (f" (found {', '.join(have)})" if have else "")
                      + f" and no Chrome at {CHROME_CHANNEL}"), []

    def python_browser(self, probe: dict | None) -> str:
        """Problem text, or '' when the chosen interpreter's Python Playwright can launch Chromium."""
        if not probe or not probe.get("playwright"):
            return "the chosen Python has no Playwright"
        rev = self.revisions(Path(probe["playwright"])).get("chromium-headless-shell")
        if rev and (self.installed(f"chromium_headless_shell-{rev}") or self.installed(f"chromium-{rev}")):
            return ""
        if shutil.which("chromium", path=self.env.get("PATH")):
            return ""                                      # the capture scripts default to `chromium` on PATH
        have = self.present_builds("chromium")
        return (f"Python Playwright needs Chromium r{rev}" + (f" (found {', '.join(have)})" if have else "")
                + "; CI installs it with `python -m playwright install chromium --only-shell`. Not installed for you.")

    # Node dependencies -----------------------------------------------------------------------------------------------
    def node_deps(self, folder: str) -> bool:
        return (self.root / folder / "node_modules" / ".package-lock.json").exists()


def assess(inst: Instance, machine: Machine, slow: bool, done: dict[str, Instance], ctx: dict | None = None) -> None:
    """Decide whether ``inst`` can run here, filling ``status``/``reason``, ``env``, ``python`` and ``notes``."""
    check, need, ctx = inst.check, inst.check.get("needs", {}), ctx or {}
    if check.get("cost") == "slow" and not slow:
        inst.status, inst.reason = "skipped", "slow" + (f" ({check['cost_note']})" if check.get("cost_note") else "") \
            + "; --slow runs it"
        return
    os_need = need.get("os")
    if os_need and os_need != platform.system().lower():
        inst.status, inst.reason = "not run", f"CI runs this on {os_need.title()}; this machine is {platform.system()}"
        return
    for cmd in need.get("commands", []):
        if not shutil.which(cmd, path=machine.env.get("PATH")):
            inst.status, inst.reason = "not run", f"`{cmd}` is not on PATH"
            return
    for folder in need.get("node_deps", []):
        if not machine.node_deps(folder):
            inst.status, inst.reason = "not run", f"Node dependencies are not installed in {folder} (run `npm ci` there)"
            return
    for dep in need.get("after", []):
        prior = done.get(dep)
        if prior is None or prior.status not in ("passed", "runnable"):     # runnable: --list, nothing ran
            inst.status = "not run"
            inst.reason = f"needs `{dep}` to pass first" + (f" (it is {prior.status})" if prior else " (not selected)")
            return
        inst.env.update({k: v.format(**ctx) for k, v in prior.check.get("provides_env", {}).items()})
    if inst.engine or need.get("browser"):
        env, problem, notes = machine.node_engine(inst.engine or need["browser"])
        if problem:
            inst.status, inst.reason = "not run", problem
            return
        inst.env.update(env)
        inst.notes += notes
    if "python" in need:
        pythonpath = str(machine.root / "software") if check.get("env", {}).get("PYTHONPATH") else None
        exe, probe, problem = machine.choose_python(need["python"], pythonpath)
        if problem:
            inst.status, inst.reason = "not run", problem
            return
        inst.python = exe
        minor = ".".join(probe["version"].split(".")[:2])
        if need["python"].get("version") and minor != need["python"]["version"]:
            inst.notes.append(f"runs on Python {minor} ({exe}), CI pins {need['python']['version']}: evidence only")
        if need["python"].get("browser"):
            problem = machine.python_browser(probe)
            if problem:
                inst.status, inst.reason = "not run", problem
                return
    inst.status = "runnable"


# ---------------------------------------------------------------------------------------------------------------------
# Running


def python_shims(folder: Path, exe: str) -> None:
    """``python`` and ``python3`` in ``folder`` that exec ``exe``: npm scripts call ``python3``. A wrapper, not a
    symlink, keeps a virtual environment's interpreter inside its environment."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("python", "python3"):
        shim = folder / name
        shim.write_text(f'#!/bin/sh\nexec "{exe}" "$@"\n')
        shim.chmod(0o755)


SALIENT = re.compile(r"^not ok|Error\b|AssertionError|assert |FAIL|FATAL|Traceback|failed|stale|regenerate", re.I)


def failure_excerpt(lines: list[str], limit: int = TAIL_LINES) -> list[str]:
    """What a reader needs from a failed log: the lines that name the failure, then the last few lines."""
    salient = [line for line in lines if SALIENT.search(line)][: limit // 2]
    tail = [line for line in lines[-(limit - len(salient)):] if line not in salient]
    return salient + (["..."] if salient and tail else []) + tail


def run(inst: Instance, ctx: dict, machine: Machine, workdir: Path, timeout: int) -> None:
    check = inst.check
    env = dict(machine.env)
    env.update({k: v.format(**ctx) for k, v in check.get("env", {}).items()})
    if "PYTHONPATH" in check.get("env", {}):
        env["PYTHONPATH"] = str(machine.root / "software")
    env.update(inst.env)
    if inst.python:
        shims = workdir / "python" / re.sub(r"[^\w.-]", "_", inst.python)
        python_shims(shims, inst.python)
        env["PATH"] = f"{shims}{os.pathsep}{env.get('PATH', '')}"
        env["PYTHON"] = inst.python
    log = workdir / "logs" / (re.sub(r"[^\w.-]", "_", inst.id) + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    cwd = machine.root / check.get("cwd", ".")
    started = time.monotonic()
    with log.open("w", encoding="utf-8", errors="replace") as out:
        # its own process group, so a timeout stops the browsers and servers a suite started, not only the shell
        proc = subprocess.Popen(["/bin/sh", "-c", inst.command(ctx)], cwd=cwd, env=env, stdout=out,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            code = None
    inst.seconds = round(time.monotonic() - started, 1)
    inst.log = str(log)
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    if code == 0:
        inst.status = "passed"
    else:
        inst.status = "failed"
        inst.reason = f"timed out after {timeout} s" if code is None else f"exit {code}"
        inst.tail = "\n".join(failure_excerpt(lines))


# ---------------------------------------------------------------------------------------------------------------------
# The changed paths


def git(*args: str, root: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def changed_paths(base: str, uncommitted: bool, root: Path = ROOT) -> tuple[list[str], str]:
    """``(paths, merge_base)``: committed since the merge base with ``base`` and, unless told not to, staged,
    unstaged and untracked files too."""
    merge_base = git("merge-base", base, "HEAD", root=root).strip()
    paths = set(git("diff", "--name-only", "-z", f"{merge_base}...HEAD", root=root).split("\0"))
    if uncommitted:
        paths |= set(git("diff", "--name-only", "-z", "HEAD", root=root).split("\0"))
        paths |= set(git("ls-files", "--others", "--exclude-standard", "-z", root=root).split("\0"))
    return sorted(p for p in paths if p), merge_base


def load_mapping(path: Path = MAPPING) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------------------------
# Report


def to_json(inst: Instance, ctx: dict) -> dict:
    return {"id": inst.id, "title": inst.check.get("title", ""), "status": inst.status, "reason": inst.reason,
            "command": inst.command(ctx), "cwd": inst.check.get("cwd", "."), "engine": inst.engine,
            "python": inst.python, "notes": inst.notes, "because": inst.because, "seconds": inst.seconds,
            "log": inst.log, "tail": inst.tail,
            "mirrors": [f"{m['workflow']} / {m['job']}: {m['run']}" for m in inst.check.get("mirrors", [])]}


def text_report(instances: list[Instance], paths: list[str], ctx: dict, listing: bool) -> str:
    out = [f"{len(paths)} changed path(s); {len(instances)} check(s) selected"
           + (" (listing only, nothing run)" if listing else "")]
    if not instances:
        out.append("No CI check in .github/ci-checks.json watches these paths.")
    width = max((len(i.id) for i in instances), default=0)
    for inst in instances:
        status = {"runnable": "would run"}.get(inst.status, inst.status)
        line = f"  {inst.id:<{width}}  {status}"
        if inst.reason:
            line += f": {inst.reason}"
        if inst.seconds is not None:
            line += f" ({inst.seconds} s)"
        out.append(line)
        out.append(f"  {'':<{width}}  $ (cd {inst.check.get('cwd', '.')} && {inst.command(ctx)})")
        out.append(f"  {'':<{width}}  because: {', '.join(inst.because[:3])}"
                   + (f" and {len(inst.because) - 3} more" if len(inst.because) > 3 else ""))
        for note in inst.notes:
            out.append(f"  {'':<{width}}  note: {note}")
        if inst.status == "failed":
            out.append(f"  {'':<{width}}  log: {inst.log}")
            out += [f"  {'':<{width}}  | {t}" for t in inst.tail.splitlines()]
    counts: dict[str, int] = {}
    for inst in instances:
        counts[inst.status] = counts.get(inst.status, 0) + 1
    out.append("Summary: " + (", ".join(f"{n} {s}" for s, n in counts.items()) or "nothing selected"))
    if counts.get("not run") or counts.get("skipped"):
        out.append("Checks not run or skipped here are not passes: CI still decides them.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/dev", help="diff base: changes since the merge base with it "
                    "(default origin/dev, as `git diff origin/dev...HEAD`)")
    ap.add_argument("--paths", nargs="+", help="these repo-relative paths instead of a diff")
    ap.add_argument("--committed-only", action="store_true", help="ignore staged, unstaged and untracked changes")
    ap.add_argument("--list", action="store_true", help="print the selected checks and their readiness; run nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--only", action="append", default=[], metavar="ID",
                    help="only this check id (repeatable; `id` or `id[engine]`)")
    ap.add_argument("--slow", action="store_true", help="also run the checks the repo marks slow")
    ap.add_argument("--python", action="append", default=[], metavar="EXE",
                    help="another interpreter to consider (repeatable), e.g. a venv with CI's Python minor")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per check (default 1800)")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="the checkout to check (default: this one); the mapping still comes from --mapping")
    ap.add_argument("--mapping", type=Path, default=MAPPING, help="the path-to-check mapping (default: %(default)s)")
    a = ap.parse_args(argv)

    root = a.root.resolve()
    try:
        mapping = load_mapping(a.mapping)
    except (OSError, ValueError) as e:
        print(f"preflight: cannot read the mapping {a.mapping}: {e}", file=sys.stderr)
        return 2
    try:
        if a.paths:
            paths, merge_base = sorted(set(a.paths)), git("rev-parse", "HEAD", root=root).strip()
        else:
            paths, merge_base = changed_paths(a.base, not a.committed_only, root)
    except (OSError, subprocess.CalledProcessError) as e:
        detail = getattr(e, "stderr", "") or str(e)
        print(f"preflight: cannot list changed paths against {a.base}: {detail.strip()}", file=sys.stderr)
        return 2

    instances = select(mapping, paths, root)
    if a.only:
        known = {i.check["id"] for i in instances} | {i.id for i in instances}
        all_ids = {c["id"] for c in mapping["checks"]}
        unknown = [o for o in a.only if o not in all_ids and o not in known]
        if unknown:
            print(f"preflight: unknown check id(s): {', '.join(unknown)}; known: {', '.join(sorted(all_ids))}",
                  file=sys.stderr)
            return 2
        instances = [i for i in instances if i.check["id"] in a.only or i.id in a.only]

    workdir = Path(tempfile.mkdtemp(prefix="cad-agent-preflight-"))
    ctx = {"base": merge_base, "tmp": str(workdir), "root": str(root)}
    machine = Machine(root, pythons=a.python)
    done: dict[str, Instance] = {}
    failed = False
    for inst in instances:
        assess(inst, machine, a.slow, done, ctx)
        if inst.status == "runnable" and not a.list:
            if not a.json:
                print(f"running {inst.id} ...", file=sys.stderr, flush=True)
            run(inst, ctx, machine, workdir, a.timeout)
            failed |= inst.status == "failed"
        done.setdefault(inst.check["id"], inst)

    if a.json:
        print(json.dumps({"root": str(root), "base": a.base if not a.paths else None, "merge_base": merge_base, "paths": paths,
                          "listing": a.list, "workdir": str(workdir),
                          "checks": [to_json(i, ctx) for i in instances],
                          "limits": "Mirrors CI, does not replace it: not run or skipped is not passed, and a pass on "
                                    "another browser or Python than CI's is evidence, not CI's result."}, indent=2))
    else:
        print(text_report(instances, paths, ctx, a.list))
        if not a.list and any(i.log for i in instances):
            print(f"Logs: {workdir / 'logs'}")
    if not any(i.log for i in instances):
        shutil.rmtree(workdir, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
