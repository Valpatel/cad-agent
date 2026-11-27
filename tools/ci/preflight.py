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

* ``passed`` / ``failed``: it ran here. A pass on a different browser, Python minor or Node major than CI's is
  evidence, not CI's result: the check is flagged ``differs`` and the closing summary counts them.
* ``not run: <reason>``: this machine lacks what it needs (a Playwright engine of the right revision, the Python minor
  CI pins when the check is sensitive to it, installed Node dependencies, Windows). Never counted as passed.
* ``skipped: slow``: the repo marks it slow; ``--slow`` runs it.
* ``ci only: <reason>``: a step that exists only for CI (an entry's ``ci_only``), such as the SCADA recapture that runs
  only after the provenance step failed and uploads what it regenerates. Listed with its reason, never run here (not
  even with ``--only``) and left out of the verdict: the checks it follows are what decide.

Exit status, and the JSON report's ``verdict``:

* 0, ``passed``: every selected check ran here and passed;
* 0, ``nothing selected``: no check watches these paths and none was named, so nothing ran;
* 1, ``failed``: a check that ran failed;
* 3, ``incomplete``: nothing that ran failed, but some selected checks did not run here (not run or skipped). The
  report ends by listing each one with its reason: CI will run them, so they can still fail there;
* 2: a usage or setup error (a malformed mapping included). ``--list`` exits 0 and its verdict is ``listed``;
* 130, 143, 129: interrupted by SIGINT (Ctrl-C), SIGTERM (a harness or ``timeout``) or SIGHUP. The running check's
  whole process group is stopped first, the report for the checks that finished is still printed (valid JSON with
  ``--json``, verdict ``interrupted (SIG…)``), and the logs are kept. The checks the run never reached are listed as
  ``not reached``, apart from those that cannot run here. The first signal decides: a second one while the check is
  being stopped is ignored. A signal after the last check finished still exits 128 + its number, after the full
  report.

``--only <id>`` runs that check whether or not the changed paths select it, and even when it is slow. A ``per_match`` check named that way needs
a changed path that gives it its value (``pytest-domain`` needs a path under ``software/cadagent/<domain>/``);
without one it is ``not run``.

Logs and the run folder (``cad-agent-preflight-*`` in the system temp, or under ``--workdir``; it also holds the
built site) are deleted when every check that ran passed, with any empty parents ``--workdir`` created, and kept, with
their path printed, when one failed or the run was interrupted. A failure while the load average exceeds the CPU count
carries a note to rerun that check alone: some suites assert on wall-clock time.

A check's ``cwd`` must resolve inside the checkout. An entry whose suites never read ``CHROMIUM_EXECUTABLE`` says so
with ``needs.chromium_executable: false`` (``tests/repo/ci/test_ci_checks.py`` keeps it true to the suite files), so
a caller's value flags only the suites it changes.

Limits, stated plainly:

* It mirrors CI; it does not replace it. CI's container image, browser builds and pinned Python are what decide.
* It installs nothing and uses no network: no ``npm ci``, ``pip install`` or ``playwright install``. It says what to
  install instead.
* It runs the checkout's own check commands (npm scripts, tests), exactly as CI does, so it executes the branch's code.
  Run it only on branches you would run the tests of.
* An edited workflow file selects every check whose mirror names it (an edit to ``webkit.yml`` selects all of its
  browser and SCADA checks), since CI reruns them all; a ``per_match`` check gets no value from it.
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
import shlex
import shutil
import signal
import string
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
DEFAULT_TIMEOUT = 1800
PROBE_TIMEOUT = 30                                          # seconds for an interpreter or Node probe

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
    """The changed paths that select ``check``: in its ``paths`` and not in its ``exclude``, or a workflow file one of
    its mirrors names (editing ``.github/workflows/webkit.yml`` selects everything that workflow runs)."""
    flows = {f".github/workflows/{m.get('workflow')}" for m in check.get("mirrors", []) if isinstance(m, dict)}
    return [p for p in paths if p in flows
            or (matches(p, check.get("paths", [])) and not matches(p, check.get("exclude", [])))]


@dataclass
class Instance:
    """One selected check: an entry of the mapping, expanded over its engine matrix and ``per_match`` captures."""
    check: dict
    engine: str | None = None
    subs: dict = field(default_factory=dict)
    because: list = field(default_factory=list)
    status: str = "selected"           # selected | passed | failed | not run | skipped | ci only
    reason: str = ""
    notes: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    python: str | None = None
    seconds: float | None = None
    log: str | None = None
    tail: str = ""
    differs: list = field(default_factory=list)      # what differs from CI's runner: browser, python, node
    named: bool = False                              # named with --only: runs even when slow
    not_reached: bool = False                        # not run because the run was interrupted before it

    @property
    def id(self) -> str:
        name = self.check["id"]
        if self.subs:
            name += ":" + ",".join(str(v) for v in self.subs.values())
        return name + (f"[{self.engine}]" if self.engine else "")

    def command(self, ctx: dict) -> str:
        # per_match values come from file names: quoted, so a name can never become shell syntax
        values = _Shown({**ctx, **{k: shlex.quote(v) for k, v in self.subs.items()}})
        return string.Formatter().vformat(self.check["command"], (), values)


class _Shown(dict):
    """Format values; a field with no value yet (a named per_match check) is shown as itself, ``{domain}``."""
    def __missing__(self, key):
        return "{" + key + "}"


CONTEXT_FIELDS = {"root", "base", "tmp"}
# The only bodies a per_match group may have: plain classes of letters, digits, `_` and `-`, never a range that
# spans punctuation such as [0-z]
SAFE_CLASSES = {f"[{c}]{q}" for c in ("a-z", "a-z_", "a-z0-9", "a-z0-9_", "a-z0-9_-", "a-z_-", "A-Za-z0-9_-")
                for q in "+*"}
GROUP = re.compile(r"\(\?P<(\w+)>([^()]*)\)")
STR, LIST, DICT, INT, BOOL = str, list, dict, int, bool
# Each field an entry may carry, and its type; `needs` and `needs.python` are checked the same way
FIELDS = {"id": STR, "title": STR, "paths": LIST, "exclude": LIST, "command": STR, "cwd": STR, "env": DICT,
          "provides_env": DICT, "needs": DICT, "engines": LIST, "cost": STR, "cost_note": STR, "timeout": INT,
          "subset": BOOL, "per_match": STR, "per_match_requires": LIST, "mirrors": LIST, "ci_only": STR}
NEEDS = {"python": DICT, "node_deps": LIST, "commands": LIST, "after": LIST, "os": STR, "browser": STR,
         "node_heap_mb": INT, "node_heap_why": STR, "chromium_executable": BOOL}
PYTHON_NEED = {"version": STR, "exact": BOOL, "modules": LIST, "dists": LIST, "browser": STR, "why": STR}
MIRROR = {"workflow": STR, "job": STR, "run": STR, "cwd": STR}
TOP = {"about": STR, "ci_node_major": STR, "checks": LIST}


def _type_problems(where: str, obj: dict, fields: dict) -> list[str]:
    out = []
    for key, value in obj.items():
        want = fields.get(key)
        if want is None:
            out.append(f"{where}: unknown field `{key}`")
        elif not isinstance(value, want) or (want is INT and isinstance(value, bool)):
            out.append(f"{where}: `{key}` must be a {want.__name__}, not {type(value).__name__}")
        elif want is LIST and key != "mirrors" and not all(isinstance(v, str) for v in value):
            out.append(f"{where}: `{key}` must be a list of strings")
        elif want is DICT and key in ("env", "provides_env") and not all(isinstance(v, str) for v in value.values()):
            out.append(f"{where}: `{key}` values must be strings")
    return out


def _quoted_fields(command: str) -> set[str]:
    """Format fields that sit inside single or double quotes in ``command``, read as ``str.format`` reads it (so
    ``{d:}`` and ``{d!s}`` name ``d``) and as the shell quotes it (a backslash escapes the next character outside
    single quotes, so ``\\"`` neither opens nor closes double quotes). A stray brace yields nothing here; it is
    reported on its own."""
    out, quote = set(), None
    try:
        parsed = list(string.Formatter().parse(command))
    except ValueError:
        return out
    for literal, name, _, _ in parsed:
        i = 0
        while i < len(literal):
            c = literal[i]
            if c == "\\" and quote != "'":
                i += 2                                   # the escaped character is literal, whatever it is
                continue
            if quote and c == quote:
                quote = None
            elif not quote and c in "\"'":
                quote = c
            i += 1
        if name is not None and quote:
            m = re.match(r"\w+", name)
            if m:
                out.add(m.group(0))
    return out


def mapping_problems(mapping) -> list[str]:
    """What makes a mapping unusable, checked once after loading, so a bad entry is a setup error (exit 2) with a
    message, not a traceback part-way through a run."""
    if not isinstance(mapping, dict) or not isinstance(mapping.get("checks"), list):
        return ["the mapping has no `checks` list"]
    problems, ids = [], set()
    for key, value in mapping.items():                 # ci_node_major as the integer 22 never equals node's "22"
        if key not in TOP:
            problems.append(f"unknown top-level field `{key}`")
        elif not isinstance(value, TOP[key]):
            problems.append(f"`{key}` must be a {TOP[key].__name__}, not {type(value).__name__}")
        elif key == "ci_node_major" and not value.isdigit():
            problems.append(f"`ci_node_major` must be a Node major such as \"22\", not {value!r}")
    for n, check in enumerate(mapping["checks"]):
        where = f"check {check.get('id', f'#{n}') if isinstance(check, dict) else f'#{n}'}"
        if not isinstance(check, dict):
            problems.append(f"{where}: not an object")
            continue
        typed = _type_problems(where, check, FIELDS)
        if isinstance(check.get("needs"), dict):
            typed += _type_problems(f"{where} needs", check["needs"], NEEDS)
            if isinstance(check["needs"].get("python"), dict):
                typed += _type_problems(f"{where} needs.python", check["needs"]["python"], PYTHON_NEED)
                for pin in check["needs"]["python"].get("dists", []):
                    name, eq, version = pin.partition("==") if isinstance(pin, str) else ("", "", "")
                    if isinstance(pin, str) and not (name.strip() and eq and version.strip()):
                        typed.append(f"{where} needs.python: dists item `{pin}` must be name==version")
        for n, mirror in enumerate(check.get("mirrors", []) if isinstance(check.get("mirrors"), list) else [], 1):
            if not isinstance(mirror, dict):
                typed.append(f"{where}: mirror {n} must be an object with workflow, job and run, not "
                             f"{type(mirror).__name__}")
                continue
            typed += [f"{where}: mirror {n} has no `{key}`" for key in ("workflow", "job", "run") if key not in mirror]
            typed += _type_problems(f"{where}: mirror {n}", mirror, MIRROR)
        if typed:                                          # the checks below assume the right types
            problems += typed
            continue
        if "ci_only" in check and not check["ci_only"].strip():
            problems.append(f"{where}: ci_only must give the reason the step exists only in CI, not a blank")
        if check.get("cost", "fast") not in ("fast", "slow"):
            problems.append(f"{where}: cost must be fast or slow")
        if "timeout" in check and check["timeout"] <= 0:
            problems.append(f"{where}: timeout must be positive")
        for engine in check.get("engines", []) + ([check["needs"]["browser"]] if check.get("needs", {}).get("browser") else []):
            if engine not in ("chromium", "webkit"):
                problems.append(f"{where}: engine {engine!r} is not chromium or webkit")
        for key in ("id", "command", "paths"):
            if not check.get(key):
                problems.append(f"{where}: no `{key}`")
        if check.get("id") in ids:
            problems.append(f"{where}: duplicate id")
        ids.add(check.get("id"))
        groups = set()
        if check.get("per_match"):
            try:
                groups = set(re.compile(check["per_match"]).groupindex)
            except re.error as e:
                problems.append(f"{where}: per_match is not a regex ({e})")
            safe = {name for name, body in GROUP.findall(check["per_match"]) if body in SAFE_CLASSES}
            for name in sorted(groups - safe):
                problems.append(f"{where}: per_match group `{name}` must be one of the plain classes "
                                f"{', '.join(sorted(c for c in SAFE_CLASSES if c.endswith('+')))} (or with *)")
            for name in sorted(groups & _quoted_fields(check["command"])):
                problems.append(f"{where}: {{{name}}} sits inside quotes in the command; leave it bare (it is "
                                f"shell-quoted when filled in)")
        for key, text in [("command", check.get("command", ""))] + [
                (f"env.{k}", v) for k, v in {**check.get("env", {}), **check.get("provides_env", {})}.items()]:
            try:
                names = {f for _, f, _, _ in string.Formatter().parse(str(text)) if f is not None}
            except ValueError as e:
                problems.append(f"{where}: {key} has a stray brace ({e}); write {{{{ and }}}} for literal braces")
                continue
            unknown = names - CONTEXT_FIELDS - (groups if key == "command" else set())
            if unknown:
                problems.append(f"{where}: {key} names {{{', '.join(sorted(unknown))}}}; known: "
                                f"{', '.join(sorted(CONTEXT_FIELDS | groups))} (write {{{{ and }}}} for literal braces)")
    return problems


def root_problems(mapping: dict, root: Path) -> list[str]:
    """What the mapping names that this checkout lacks: a working directory, which must also resolve inside it (no
    ``..``, absolute path or symlink out)."""
    out, root = [], root.resolve()
    for c in mapping["checks"]:
        if not c.get("cwd"):
            continue
        where = (root / c["cwd"]).resolve()
        if where != root and root not in where.parents:
            out.append(f"check {c['id']}: cwd {c['cwd']} is outside the checkout {root} (it resolves to {where})")
        elif not where.is_dir():
            out.append(f"check {c['id']}: cwd {c['cwd']} is not a folder in {root}")
    return out


def named(mapping: dict, only: list[str], selected: list[Instance]) -> list[Instance]:
    """``--only``: the named checks, whether or not the changed paths selected them. A named ``per_match`` check that
    no changed path gives a value is ``not run``, with the reason."""
    out = []
    for check in mapping["checks"]:
        picked = [i for i in selected if i.check is check and (check["id"] in only or i.id in only)]
        wanted = check["id"] in only or any(o.startswith(check["id"] + "[") for o in only)
        if picked or not wanted:
            out += picked
            continue
        if check.get("per_match"):
            inst = Instance(check, None, {}, ["named with --only"], status="not run",
                            reason="named with --only, but no changed path gives it a value for "
                                   f"{check['per_match']}; pass one with --paths")
            out.append(inst)
            continue
        for engine in check.get("engines") or [None]:
            inst = Instance(check, engine, {}, ["named with --only; no changed path selects it"])
            if check["id"] in only or inst.id in only:
                out.append(inst)
    return out


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


def capture(cmd: list[str], env: dict, timeout: float | None = None) -> subprocess.CompletedProcess | None:
    """Run a probe in its own process group and return its output, or None when it timed out. A timeout or an
    interrupt stops the whole group (a wrapper script's children too), not only the process it started."""
    with subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                          text=True, start_new_session=True) as proc:
        try:
            out, err = proc.communicate(timeout=PROBE_TIMEOUT if timeout is None else timeout)
        except subprocess.TimeoutExpired:
            stop_group(proc.pid)
            proc.wait()
            return None
        except BaseException:                          # an interrupt: stop the group, then let it propagate
            stop_group(proc.pid)
            proc.wait()
            raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


class Machine:
    """Capabilities, each probed once: interpreters, Playwright browser builds, installed Node dependencies."""

    def __init__(self, root: Path = ROOT, pythons: list[str] | None = None, env: dict | None = None):
        self.root = root
        self.env = dict(os.environ if env is None else env)
        self.extra_pythons = pythons or []
        self.ci_node_major: str | None = None            # the mapping's `ci_node_major`, set by main
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
                out = capture([exe, "-I", "-c", code, json.dumps(modules), json.dumps(dists)], env)
                self._probes[key] = json.loads(out.stdout) if out and out.returncode == 0 else None
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

    def node_engine(self, engine: str, reads_preset: bool = True) -> tuple[dict | None, str, list[str]]:
        """``(env, problem, notes)`` to run a Node Playwright suite in ``engine``, as CI's matrix does.
        ``reads_preset`` is False for a suite that never reads CHROMIUM_EXECUTABLE (the entry's
        ``needs.chromium_executable``): a caller's value then changes nothing for it, so it is neither named nor
        flagged."""
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
        # Most Chromium suites launch CHROMIUM_EXECUTABLE when it is set, whatever the channel says: a caller's value
        # replaces CI's build, so it is named and flagged (a note sets the `browser` differs flag)
        preset = self.env.get("CHROMIUM_EXECUTABLE") if reads_preset else None
        preset_note = (f"runs on CHROMIUM_EXECUTABLE={preset} (set in your environment), not CI's Playwright "
                       f"Chromium r{rev}: evidence only")
        if rev and self.installed(f"chromium_headless_shell-{rev}") and self.installed(f"chromium-{rev}"):
            env = {"PLAYWRIGHT_BROWSER": "chromium", "PLAYWRIGHT_CHANNEL": "chromium"}
            return env, "", [preset_note] if preset else []
        have = self.present_builds("chromium")
        if CHROME_CHANNEL.exists() or preset:
            # Suites pick Chrome by the `chrome` channel or by CHROMIUM_EXECUTABLE (webkit-model-explode-browser.mjs
            # reads only the latter); name it for both, unless the caller already chose an executable.
            if preset:
                return {"PLAYWRIGHT_BROWSER": "chromium", "CHROMIUM_EXECUTABLE": preset}, "", [
                    preset_note + (f" (installed here: {', '.join(have)})" if have else "")]
            return ({"PLAYWRIGHT_BROWSER": "chromium",
                     "CHROMIUM_EXECUTABLE": self.env.get("CHROMIUM_EXECUTABLE") or str(CHROME_CHANNEL)}, "",
                    [f"runs on the local Chrome ({CHROME_CHANNEL}, as CHROMIUM_EXECUTABLE and Playwright's `chrome` "
                     f"channel), not CI's Playwright Chromium r{rev}"
                     + (f" (installed here: {', '.join(have)})" if have else "") + ": evidence only"])
        return None, (f"Playwright Chromium r{rev} is not installed" + (f" (found {', '.join(have)})" if have else "")
                      + f" and no Chrome at {CHROME_CHANNEL}"), []

    def python_browser(self, probe: dict | None) -> tuple[str, str]:
        """``(problem, note)``: a problem when the chosen interpreter's Python Playwright cannot launch Chromium; a
        note when it can only through another Chromium than the pinned one."""
        if not probe or not probe.get("playwright"):
            return "the chosen Python has no Playwright", ""
        rev = self.revisions(Path(probe["playwright"])).get("chromium-headless-shell")
        pinned = rev and (self.installed(f"chromium_headless_shell-{rev}") or self.installed(f"chromium-{rev}"))
        other = shutil.which("chromium", path=self.env.get("PATH"))
        if other:          # the capture scripts take `chromium` on PATH whenever there is one, pinned build or not
            return "", (f"runs on the `chromium` on PATH ({other}), not Python Playwright's pinned Chromium r{rev}"
                        + (" (installed here, but the PATH browser wins)" if pinned else "") + ": evidence only")
        if pinned:
            return "", ""
        have = self.present_builds("chromium")
        return (f"Python Playwright needs Chromium r{rev}" + (f" (found {', '.join(have)})" if have else "")
                + "; CI installs it with `python -m playwright install chromium --only-shell`. Not installed for you."), ""

    # Node ------------------------------------------------------------------------------------------------------------
    def node_heap_mb(self) -> int | None:
        """This machine's default V8 heap limit for ``node``: V8 sizes it from the memory it sees (a container's
        cgroup limit included), so it can be smaller here than on CI's runner."""
        if not hasattr(self, "_heap"):
            try:
                out = capture(["node", "-e", "console.log(require('v8').getHeapStatistics().heap_size_limit)"],
                              self.env)
                self._heap = int(out.stdout) // 2**20 if out and out.returncode == 0 else None
            except (OSError, ValueError, subprocess.SubprocessError):
                self._heap = None
        return self._heap

    def node_major(self) -> str | None:
        if not hasattr(self, "_node_major"):
            try:
                out = capture(["node", "--version"], self.env)
                self._node_major = out.stdout.strip().lstrip("v").split(".")[0] if out and out.returncode == 0 else None
            except (OSError, subprocess.SubprocessError):
                self._node_major = None
        return self._node_major

    def node_deps(self, folder: str) -> bool:
        return (self.root / folder / "node_modules" / ".package-lock.json").exists()


def assess(inst: Instance, machine: Machine, slow: bool, done: dict[str, Instance], ctx: dict | None = None) -> None:
    """Decide whether ``inst`` can run here, filling ``status``/``reason``, ``env``, ``python`` and ``notes``."""
    check, need, ctx = inst.check, inst.check.get("needs", {}), ctx or {}
    if inst.status == "not run":                       # decided at selection (a named per_match check)
        return
    if check.get("ci_only"):
        inst.status, inst.reason = "ci only", check["ci_only"]
        return
    if check.get("cost") == "slow" and not slow and not inst.named:
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
    if need.get("node_heap_mb"):
        want, have = need["node_heap_mb"], machine.node_heap_mb()
        if have is not None and have < want:
            inst.env["NODE_OPTIONS"] = f"{machine.env.get('NODE_OPTIONS', '')} --max-old-space-size={want}".strip()
            inst.notes.append(f"this machine's default Node heap is {have} MB, under the {want} MB this suite needs "
                              f"({need.get('node_heap_why', 'see the mapping')}); runs with --max-old-space-size={want}")
    if inst.engine or need.get("browser"):
        env, problem, notes = machine.node_engine(inst.engine or need["browser"], need.get("chromium_executable", True))
        if problem:
            inst.status, inst.reason = "not run", problem
            return
        inst.env.update(env)
        inst.notes += notes
        if notes:
            inst.differs.append("browser")
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
            inst.differs.append("python")
        if need["python"].get("browser"):
            problem, note = machine.python_browser(probe)
            if problem:
                inst.status, inst.reason = "not run", problem
                return
            if note:
                inst.notes.append(note)
                inst.differs.append("browser")
    if machine.ci_node_major and NODE_COMMAND.match(check["command"]):
        have = machine.node_major()
        if have and have != machine.ci_node_major:
            inst.notes.append(f"runs on Node {have}, CI pins {machine.ci_node_major}: evidence only")
            inst.differs.append("node")
    inst.status = "runnable"


NODE_COMMAND = re.compile(r"^(?:node|npm)\b")


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


class Interrupted(Exception):
    """SIGINT, SIGTERM or SIGHUP arrived; ``signum`` says which."""
    def __init__(self, signum: int):
        super().__init__(signal.Signals(signum).name)
        self.signum = signum


# The first signal of a run, and whether the checks are over (then it is only recorded, so the report still prints)
_SIGNALS: dict = {"first": None, "defer": False}


def _on_signal(signum, frame):
    """The first signal decides: it raises ``Interrupted`` while checks run, or is recorded once they are over. A
    later one (a second Ctrl-C, or a harness's SIGTERM right after SIGINT) is ignored, so it cannot cut short the
    stopping of the running check and leave that check unreported."""
    if _SIGNALS["first"] is not None:
        return
    _SIGNALS["first"] = signum
    if not _SIGNALS["defer"]:
        raise Interrupted(signum)


def load_note(check_id: str) -> str | None:
    """A hint for a failure under load: some suites assert on wall-clock time (``tests/webkit/files/browser.mjs``
    gives Cancel two seconds), and a load average above the CPU count can fail them where they pass alone."""
    try:
        one = os.getloadavg()[0]
    except (OSError, AttributeError):                  # not available on this platform
        return None
    cpus = os.cpu_count() or 1
    if one <= cpus:
        return None
    return (f"the load average was {one:.1f} on {cpus} CPUs when it failed: a suite with a wall-clock assertion can "
            f"fail under load, so rerun it alone (--only {check_id}) before reading the failure as the change's")


def stop_group(pid: int) -> None:
    """Kill a check's process group: the shell and every browser, server or child it started."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):      # the group has just gone
        pass


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
            stop_group(proc.pid)
            proc.wait()
            code = None
        except (KeyboardInterrupt, Interrupted) as e:  # the check runs in its own session: the signal stops here
            inst.status, inst.log = "failed", str(log)  # recorded first, before anything else can go wrong
            inst.reason = f"interrupted ({e if isinstance(e, Interrupted) else 'SIGINT'})"
            inst.seconds = round(time.monotonic() - started, 1)
            stop_group(proc.pid)
            proc.wait()
            raise
    inst.seconds = round(time.monotonic() - started, 1)
    inst.log = str(log)
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    if code == 0:
        inst.status = "passed"
    else:
        inst.status = "failed"
        inst.reason = f"timed out after {timeout} s" if code is None else f"exit {code}"
        inst.tail = "\n".join(failure_excerpt(lines))
        note = load_note(inst.id)
        if note:
            inst.notes.append(note)


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
            "log": inst.log, "tail": inst.tail, "differs": inst.differs,
            "mirrors": [f"{m['workflow']} / {m['job']}: {m['run']}" for m in inst.check.get("mirrors", [])]}


def text_report(instances: list[Instance], paths: list[str], ctx: dict, listing: bool, logs: str | None = None,
                interrupted: Interrupted | None = None) -> str:
    ci_only_n = sum(i.check.get("ci_only") is not None for i in instances)
    out = [f"{len(paths)} changed path(s); {len(instances)} check(s) selected"
           + (f", {ci_only_n} of them CI only (never run here, not in the verdict)" if ci_only_n else "")
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
    if logs:
        out.append(f"Logs: {logs}")
    counts: dict[str, int] = {}
    for inst in instances:
        counts[inst.status] = counts.get(inst.status, 0) + 1
    out.append("Summary: " + (", ".join(f"{n} {s}" for s, n in counts.items()) or "nothing selected, nothing ran"))
    ran = [i for i in instances if i.status in ("passed", "failed")]
    if listing:
        would = sum(i.status == "runnable" for i in instances)
        out.append(f"{would} of {len(instances)} selected checks would run here.")
    elif instances:
        out.append(f"{sum(i.status == 'passed' for i in ran)} of {len(ran)} checks that ran here passed"
                   + (f"; {sum(i.status == 'failed' for i in ran)} failed." if any(i.status == "failed" for i in ran)
                      else "."))
    differing = [i for i in ran if i.differs]
    if differing:
        out.append(f"{len(differing)} ran on a different browser, Python or Node than CI's (evidence, not CI's "
                   f"result): " + ", ".join(f"{i.id} ({'/'.join(i.differs)})" for i in differing))
    skipped = [i for i in instances if i.status == "skipped"]
    cannot = [i for i in instances if i.status == "not run" and not i.not_reached]
    unreached = [i for i in instances if i.status == "not run" and i.not_reached]
    ci_only = [i for i in instances if i.status == "ci only"]
    if ci_only:
        out.append("CI only, never run here and not part of the verdict: " + ", ".join(i.id for i in ci_only))
    if skipped or cannot or unreached:
        out.append(f"Not run, so not passed (CI runs them): {len(skipped)} skipped as slow (--slow runs them), "
                   f"{len(cannot)} cannot run here"
                   + (f", {len(unreached)} not reached (the run was interrupted)" if unreached else "") + ":")
        out += [f"  - skipped: {i.id} ({i.check.get('title', '')}): {i.reason}" for i in skipped]
        out += [f"  - cannot run here: {i.id} ({i.check.get('title', '')}): {i.reason}" for i in cannot]
        out += [f"  - not reached: {i.id} ({i.check.get('title', '')}): {i.reason}" for i in unreached]
    if not listing:
        out.append(f"Verdict: {verdict(instances, listing, interrupted)}")
    return "\n".join(out)


def verdict(instances: list[Instance], listing: bool = False, interrupted: Interrupted | None = None) -> str:
    """``listed``, ``nothing selected``, ``failed`` (a check that ran failed), ``incomplete`` (nothing failed, but a
    selected check did not run here) or ``passed`` (every selected check ran and passed). Never ``passed`` when
    nothing ran. ``ci only`` checks are left out: a selection of only those is ``nothing selected``."""
    if listing:
        return "listed"
    if interrupted:
        return f"interrupted ({interrupted})"
    instances = [i for i in instances if i.status != "ci only"]
    if not instances:
        return "nothing selected"
    if any(i.status == "failed" for i in instances):
        return "failed"
    if any(i.status in ("not run", "skipped") for i in instances):
        return "incomplete"
    return "passed"


EXIT = {"passed": 0, "nothing selected": 0, "listed": 0, "failed": 1, "incomplete": 3}
HANDLED = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def main(argv: list[str] | None = None) -> int:
    """Install the signal handlers, run, restore them. Anything unexpected is a setup error (exit 2), never exit 1,
    which means a check that ran failed."""
    previous = {}
    _SIGNALS.update(first=None, defer=False)
    try:
        for sig in HANDLED:
            previous[sig] = signal.signal(sig, _on_signal)
    except ValueError:                                 # not the main thread: SIGINT still works
        previous = {}
    try:
        return _main(argv)
    except (Interrupted, KeyboardInterrupt) as e:      # before any check started: nothing to report
        signum = e.signum if isinstance(e, Interrupted) else signal.SIGINT
        print(f"preflight: interrupted ({signal.Signals(signum).name}) before any check started", file=sys.stderr)
        return 128 + signum
    except Exception as e:                             # a bug or a mapping shape the checks above missed
        print(f"preflight: setup error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _main(argv: list[str] | None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/dev", help="diff base: changes since the merge base with it "
                    "(default origin/dev, as `git diff origin/dev...HEAD`)")
    ap.add_argument("--paths", nargs="+", help="these repo-relative paths instead of a diff")
    ap.add_argument("--committed-only", action="store_true", help="ignore staged, unstaged and untracked changes")
    ap.add_argument("--list", action="store_true", help="print the selected checks and their readiness; run nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--only", action="append", default=[], metavar="ID",
                    help="only this check id (repeatable; `id` or `id[engine]`); runs it even if slow or unselected")
    ap.add_argument("--slow", action="store_true", help="also run the checks the repo marks slow")
    ap.add_argument("--python", action="append", default=[], metavar="EXE",
                    help="another interpreter to consider (repeatable), e.g. a venv with CI's Python minor")
    ap.add_argument("--timeout", type=int, help=f"seconds per check (default: the check's own `timeout`, else "
                    f"{DEFAULT_TIMEOUT})")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="the checkout to check (default: this one); the mapping still comes from --mapping")
    ap.add_argument("--mapping", type=Path, default=MAPPING, help="the path-to-check mapping (default: %(default)s)")
    ap.add_argument("--workdir", type=Path, help="parent folder for the run folder (default: the system temp)")
    a = ap.parse_args(argv)

    root = a.root.resolve()
    try:
        mapping = load_mapping(a.mapping)
    except (OSError, ValueError) as e:
        print(f"preflight: cannot read the mapping {a.mapping}: {e}", file=sys.stderr)
        return 2
    problems = mapping_problems(mapping) or root_problems(mapping, root)
    if problems:
        print(f"preflight: the mapping {a.mapping} is malformed:\n  " + "\n  ".join(problems), file=sys.stderr)
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
        all_ids = {c["id"] for c in mapping["checks"]}
        unknown = [o for o in a.only if o.split("[")[0] not in all_ids]
        if unknown:
            print(f"preflight: unknown check id(s): {', '.join(unknown)}; known: {', '.join(sorted(all_ids))}",
                  file=sys.stderr)
            return 2
        instances = named(mapping, a.only, instances)
        for inst in instances:
            inst.named = True

    made: list[Path] = []                               # the folders --workdir creates, deepest first
    if a.workdir:
        a.workdir = a.workdir.resolve()                  # mkdtemp keeps a relative dir relative before Python 3.12
        made = [p for p in (a.workdir, *a.workdir.parents) if not p.exists()]
        a.workdir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="cad-agent-preflight-", dir=a.workdir))
    ctx = {"base": merge_base, "tmp": str(workdir), "root": str(root)}
    machine = Machine(root, pythons=a.python)
    machine.ci_node_major = mapping.get("ci_node_major")
    done: dict[str, Instance] = {}
    interrupted = None
    try:
        for inst in instances:
            assess(inst, machine, a.slow, done, ctx)
            if inst.status == "runnable" and not a.list:
                if not a.json:
                    print(f"running {inst.id} ...", file=sys.stderr, flush=True)
                run(inst, ctx, machine, workdir, a.timeout or inst.check.get("timeout", DEFAULT_TIMEOUT))
            done.setdefault(inst.check["id"], inst)
        _SIGNALS["defer"] = True                         # the checks are over: a signal now waits for the report
    except (Interrupted, KeyboardInterrupt) as e:
        _SIGNALS["defer"] = True
        interrupted = e if isinstance(e, Interrupted) else Interrupted(signal.SIGINT)
        for inst in instances:
            if inst.status in ("selected", "runnable"):
                inst.status, inst.not_reached = "not run", True
                inst.reason = f"the run was interrupted ({interrupted}) before it started"
        print(f"preflight: interrupted ({interrupted}); stopped the running check and everything it started. "
              f"Logs kept in {workdir / 'logs'}", file=sys.stderr)

    keep = interrupted or any(i.status == "failed" for i in instances)
    if a.json:
        ran = [i for i in instances if i.status in ("passed", "failed")]
        print(json.dumps({"root": str(root), "base": a.base if not a.paths else None, "merge_base": merge_base,
                          "paths": paths, "listing": a.list, "verdict": verdict(instances, a.list, interrupted),
                          "workdir": str(workdir) if keep else None,
                          "ran": len(ran), "passed": sum(i.status == "passed" for i in ran),
                          "differs": [{"id": i.id, "differs": i.differs} for i in ran if i.differs],
                          "skipped": [{"id": i.id, "reason": i.reason} for i in instances if i.status == "skipped"],
                          "cannot_run": [{"id": i.id, "reason": i.reason} for i in instances
                                         if i.status == "not run" and not i.not_reached],
                          "not_reached": [{"id": i.id, "reason": i.reason} for i in instances if i.not_reached],
                          "not_run": [{"id": i.id, "status": i.status, "reason": i.reason} for i in instances
                                      if i.status in ("not run", "skipped")],
                          "ci_only": [{"id": i.id, "reason": i.reason} for i in instances if i.status == "ci only"],
                          "checks": [to_json(i, ctx) for i in instances],
                          "limits": "Mirrors CI, does not replace it: not run or skipped is not passed, and a pass on "
                                    "another browser, Python or Node than CI's is evidence, not CI's result."},
                         indent=2), flush=True)
    else:
        logs = str(workdir / "logs") + " (kept)" if keep else None
        print(text_report(instances, paths, ctx, a.list, logs, interrupted), flush=True)
    if not keep:
        shutil.rmtree(workdir, ignore_errors=True)       # kept only when a check failed or the run was stopped
        for folder in made:                              # and the parents --workdir made, while they are empty
            try:
                folder.rmdir()
            except OSError:
                break
    late = _SIGNALS["first"]
    if late and not interrupted:                         # arrived after the checks: the report above is whole
        print(f"preflight: {signal.Signals(late).name} arrived after the checks finished; the report above is "
              f"complete", file=sys.stderr)
        return 128 + late
    return 128 + interrupted.signum if interrupted else EXIT[verdict(instances, a.list)]


if __name__ == "__main__":
    sys.exit(main())
