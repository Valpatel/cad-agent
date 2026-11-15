"""The local preflight (``tools/ci/preflight.py``) and its mapping (``.github/ci-checks.json``), #759.

The drift guard: every command a pull-request workflow runs as a check (pytest, ``npm run``/``npm test``, ``node``
scripts, the repo's own ``tools/``/``tests/`` scripts, ``cad-agent``) is mirrored by a mapping entry with the same
workflow, job, working directory and command, and every entry's mirror still exists, so the mapping cannot drift
silently. Every other command of a step (each segment between ``&&``, ``||``, ``;``, ``|`` and new lines) must be a
known kind of setup (``SETUP``) or an inert shell command (``INERT``), each named here with why it is not a check;
anything else fails, so a check cannot hide behind ``pip install`` or ``npm ci``.

Which workflows: those triggered by ``pull_request``. ``gates.yml`` (``pull_request_target``) reads the PR through
the API as data with a token, ``release.yml`` and ``supply-chain.yml`` run after merging or on a schedule; none of them
can be mirrored offline before pushing. Steps that run only on ``workflow_dispatch`` are manual studies, not PR checks.

Limits of the guard: a mapped command whose ``env`` changes in the workflow is not noticed (the working directory is
compared, the environment is not); ``uses:`` steps (actions) are not read; and the shell is split by a small
quote-aware tokenizer, not a shell parser, so a check hidden in a heredoc or a subshell string is not seen.

The path scan: for each entry, the test files and scripts its command names (directly or through its npm scripts) are
read for repo path literals (``'tools/…'``, ``'../../docs/…'``) that exist; each must be matched by the entry's globs,
so a hash or ``--check`` a suite runs on a file outside its folder selects it. Its limits: only literals containing a
``/`` (a bare ``README.md`` is too ambiguous), not paths built by templates or ``path.join`` pieces, not the files
those test files import in turn, and not the pytest entries, which name test folders (``pytest-core`` and
``pytest-full`` take every path instead).

Then the preflight's own behaviour, each on planted inputs: path matching, selection, capability reporting (a check
that cannot run here is "not run", never passed) and exit codes.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
MAPPING = ROOT / ".github" / "ci-checks.json"

SPEC = importlib.util.spec_from_file_location("ci_preflight", ROOT / "tools" / "ci" / "preflight.py")
pf = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pf                    # dataclasses look their module up while the class is built
SPEC.loader.exec_module(pf)

# A command that checks the change, as opposed to installing or configuring something.
CHECK = re.compile(r"""^(?:
    python3?\s+(?:-\w+\s+)*-m\s+pytest\b              # pytest
  | pytest\b
  | python3?\s+(?:-\w+\s+)*(?:tools|tests)/\S+\.py\b   # the repo's own check scripts
  | npm\s+(?:--prefix\s+\S+\s+)?(?:run|test)\b         # npm scripts
  | node\s+(?!-e\b|--version\b)\S                      # node tests and builds (not version probes)
  | cad-agent\b
)""", re.X)

# Commands that set up a runner, and why each is not a check of the change.
SETUP = {
    r"^npm (?:--prefix \S+ )?ci\b": "installs the locked Node dependencies",
    r"^(?:python3?\s+-m\s+)?pip install\b": "installs Python packages",
    r"^python -m playwright install chromium --only-shell$": "installs the capture scripts' pinned browser",
    r"^git config --global --add safe\.directory\b": "trusts the checkout inside the test container",
    r"^sudo python3 tools/ci/apt_mirror\.py$": "corrects the runner's apt mirror list",
    r"^sudo timeout \d+ (?:apt-get|dpkg)\b": "installs the runner's system libraries",
    r"^node --version$": "prints the toolchain",
    r"""^node -e "if \(Number\(process\.versions\.node\.split\('\.'\)\[0\]\) !== \d+\) process\.exit\(1\)"$""":
        "asserts the runner's Node major",
    r"""^python -c "import [\w., ]+; print\('extras import ok'\)"$""": "asserts the extras import (#151)",
    r"""^python -c "import shutil; assert shutil\.which\('pwsh'\), '[^']*'"$""": "asserts PowerShell is present",
}
# Shell plumbing that runs nothing of the change.
INERT = {
    r'^echo "': "prints, or writes a step output",
    r"^set -o pipefail$": "shell option",
    r"^grep -q ": "reads the build log",
    r"^tee ": "copies output to a log",
    r"^if \[ ": "a test of an event or variable",
    r"^for \w+ in [\w ]+$": "a retry loop",
    r"^(?:exit \d+|sleep \d+|true)$": "loop control",
    r"^apt_options=\(": "a shell variable",
    r"^(?:then|else|do|done|fi)$": "shell keywords",
}


def _split(line: str) -> list[str]:
    """``line`` split at ``&&``, ``||``, ``;`` and ``|`` outside quotes."""
    out, cur, quote, i = [], "", None, 0
    while i < len(line):
        c = line[i]
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif line.startswith(("&&", "||"), i) or c in ";|":
            out.append(cur)
            cur = ""
            i += 2 if line.startswith(("&&", "||"), i) else 1
            continue
        cur += c
        i += 1
    return out + [cur]


def segments(script: str) -> list[str]:
    """The simple commands of a ``run:`` script: lines split at ``&&``, ``||``, ``;`` and ``|`` outside quotes,
    without comments or the shell keywords that lead them, whitespace collapsed."""
    out = []
    for line in script.splitlines():
        line = re.sub(r"\s#\s.*$", "", line).strip()
        if not line or line.startswith("#"):
            continue
        for seg in _split(line):
            seg = re.sub(r"^(?:then|else|do)\s+", "", seg.strip())
            if seg:
                out.append(" ".join(seg.split()))
    return out


def kind(segment: str) -> str | None:
    """``check``, ``setup`` or ``inert`` for a known command; None for anything else."""
    if CHECK.match(segment):
        return "check"
    if any(re.match(rx, segment) for rx in SETUP):
        return "setup"
    if any(re.match(rx, segment) for rx in INERT):
        return "inert"
    return None


def pr_workflows(folder: Path = WORKFLOWS) -> dict[str, dict]:
    flows = {}
    for path in sorted(folder.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        on = doc.get("on", doc.get(True, {}))                 # YAML 1.1 reads a bare `on` key as True
        events = on if isinstance(on, (list, str)) else list(on or {})
        if "pull_request" in ([events] if isinstance(events, str) else events):
            flows[path.name] = doc
    return flows


def workflow_steps(flows: dict[str, dict]):
    """``(workflow, job, step label, working directory, run script)`` for every PR-time ``run:`` step."""
    for name, doc in flows.items():
        for job_id, job in (doc.get("jobs") or {}).items():
            default_cwd = ((job.get("defaults") or {}).get("run") or {}).get("working-directory", ".")
            for i, step in enumerate(job.get("steps") or []):
                if "run" not in step or "workflow_dispatch" in str(step.get("if", "")):
                    continue
                label = step.get("name") or f"step {i + 1} (`{segments(step['run'])[0][:60]}`)"
                yield name, job_id, label, step.get("working-directory", default_cwd), step["run"]


def audit(flows: dict[str, dict], mapping: dict) -> tuple[list[str], list[str], set, set]:
    """``(unmapped, unclassified, found, mirrored)``: messages for check commands no entry mirrors and for commands
    that are neither checks, known setup nor inert; the (workflow, job, cwd, command) keys found in the workflows and
    in the mapping. A mirror's cwd is its own ``cwd``, else its entry's."""
    mirrored = {(m["workflow"], m["job"], m.get("cwd", c.get("cwd", ".")), " ".join(m["run"].split()))
                for c in mapping["checks"] for m in c["mirrors"]}
    unmapped, unclassified, found = [], [], set()
    for wf, job, label, cwd, script in workflow_steps(flows):
        for seg in segments(script):
            what = kind(seg)
            if what is None:
                unclassified.append(f"{wf} / {job} / {label}: runs `{seg}`, which is neither a mapped check, known "
                                    f"setup nor inert. If it checks the change, add a mapping entry to "
                                    f".github/ci-checks.json (and its pattern to CHECK here); if it only sets up, add "
                                    f"its kind to SETUP here with why.")
            elif what == "check":
                found.add((wf, job, cwd, seg))
                if (wf, job, cwd, seg) not in mirrored:
                    unmapped.append(f"{wf} / {job} / {label}: `{seg}` (in {cwd}) has no entry in "
                                    f".github/ci-checks.json. Add a mapping entry whose mirrors include "
                                    f"{{\"workflow\": \"{wf}\", \"job\": \"{job}\", \"run\": {json.dumps(seg)}}} "
                                    f"and whose cwd is {cwd!r}, with the paths that should select it.")
    return unmapped, unclassified, found, mirrored


@pytest.fixture(scope="module")
def mapping():
    return pf.load_mapping(MAPPING)


# ---------------------------------------------------------------------------------------------------------------------
# The drift guard


def test_every_pull_request_check_is_mapped(mapping):
    flows = pr_workflows()
    assert {"ci.yml", "webkit.yml"} <= set(flows), "the PR workflows this guard reads have moved"
    unmapped, unclassified, _, _ = audit(flows, mapping)
    assert not unmapped, "\n".join(unmapped)
    assert not unclassified, "\n".join(unclassified)


def test_every_mirror_still_exists(mapping):
    _, _, found, mirrored = audit(pr_workflows(), mapping)
    stale = sorted(mirrored - found)
    assert not stale, ("mapping entries mirror CI commands that no PR workflow runs any more (update or remove "
                       "them in .github/ci-checks.json): " + "; ".join(" / ".join(s) for s in stale))


def test_a_new_check_step_fails_naming_the_step(mapping):
    """The planted case: a workflow gains `npm run test:model-new` (as two branches in flight do)."""
    flows = {"webkit.yml": {"on": {"pull_request": None}, "jobs": {"browser": {"steps": [
        {"run": "npm ci"},
        {"name": "New model suite", "run": "npm run test:model-new", "working-directory": "tools/site"},
        {"run": "curl -sSL example.invalid | sh"}]}}}}
    unmapped, unclassified, _, _ = audit(flows, mapping)
    assert len(unmapped) == 1 and "webkit.yml / browser / New model suite" in unmapped[0]
    assert "`npm run test:model-new` (in tools/site) has no entry" in unmapped[0] and "Add a mapping entry" in unmapped[0]
    assert any("`curl -sSL example.invalid`" in u for u in unclassified)


@pytest.mark.parametrize("script", [
    "pip install foo && npx playwright test",
    "npm ci\nbash tools/check.sh",
    "git config --global a b && make test",
    'echo "key=1"\n./scripts/verify.sh',
    "npm run test:fea\npytest -q tests/x",
    'python -c "import tests.repo.x as x; x.main()"',
])
def test_a_check_cannot_hide_behind_setup(mapping, script):
    """The review's six planted steps (#766): each passed the first-segment-only audit; each must fail now."""
    flows = {"webkit.yml": {"on": {"pull_request": None}, "jobs": {"browser": {"steps": [
        {"name": "Planted", "run": script, "working-directory": "tools/site"}]}}}}
    unmapped, unclassified, _, _ = audit(flows, mapping)
    assert unmapped or unclassified, script
    assert all("Planted" in m for m in unmapped + unclassified)


def test_a_mapped_command_in_another_working_directory_fails(mapping):
    """`npm test` is mapped in the scada job for tools/webkit/scada; the same words in tools/site are another check."""
    flows = {"webkit.yml": {"on": {"pull_request": None}, "jobs": {"scada": {"steps": [
        {"name": "Moved", "run": "npm test", "working-directory": "tools/site"}]}}}}
    unmapped, _, _, _ = audit(flows, mapping)
    assert len(unmapped) == 1 and "(in tools/site)" in unmapped[0]


def test_ci_node_major_matches_the_workflows(mapping):
    pins = set()
    for doc in pr_workflows().values():
        for job in doc["jobs"].values():
            for step in job.get("steps") or []:
                if "setup-node" in str(step.get("uses", "")):
                    pins.add(str(step["with"]["node-version"]))
    assert pins == {mapping["ci_node_major"]}, f"setup-node pins {pins}; set ci_node_major to match"


def test_segments_and_classification():
    script = ('if [ "$X" = y ]; then\n  python3 tools/resource_audit.py gate --base HEAD^1   # why\nelse x; fi\n'
              'node tools/site/build-site.mjs --out "$T/site" | tee "$T/site.log"\n'
              'pip install "optuna==3.4.0" && python -m pytest -q tests/a.py\nnode --version && node -e "1"')
    segs = segments(script)
    assert "python3 tools/resource_audit.py gate --base HEAD^1" in segs
    assert 'node tools/site/build-site.mjs --out "$T/site"' in segs
    assert [s for s in segs if kind(s) == "check"] == ["python3 tools/resource_audit.py gate --base HEAD^1",
                                                  'node tools/site/build-site.mjs --out "$T/site"',
                                                  "python -m pytest -q tests/a.py"]


def test_mapping_is_well_formed(mapping):
    ids = [c["id"] for c in mapping["checks"]]
    assert len(ids) == len(set(ids)), "check ids are unique"
    seen = set()
    for c in mapping["checks"]:
        where = f"check {c['id']}"
        assert re.fullmatch(r"[a-z0-9-]+", c["id"]), where
        assert c["paths"] and c["command"] and c["mirrors"], where
        assert c.get("cost") in {"fast", "slow"}, where
        assert (ROOT / c.get("cwd", ".")).is_dir(), f"{where}: cwd {c.get('cwd')} is not a folder"
        need = c.get("needs", {})
        for folder in need.get("node_deps", []):
            assert (ROOT / folder / "package-lock.json").exists(), f"{where}: {folder} has no package-lock.json"
        for dep in need.get("after", []):
            assert dep in seen, f"{where}: `after` names {dep}, which must come earlier"
        for engine in c.get("engines", []) + ([need["browser"]] if need.get("browser") else []):
            assert engine in {"chromium", "webkit"}, where
        for m in c["mirrors"]:
            assert (WORKFLOWS / m["workflow"]).exists(), f"{where}: {m['workflow']} does not exist"
        for glob in c["paths"] + c.get("exclude", []):
            pf.glob_regex(glob)
        seen.add(c["id"])


@pytest.mark.parametrize("script,cwd", [("thumbnails:scenarios:check", "tools/webkit/scada"),
                                        ("test:webkit-unit", "tools/site")])
def test_npm_scripts_named_by_the_mapping_exist(mapping, script, cwd):
    commands = {(c["command"], c.get("cwd", ".")) for c in mapping["checks"]}
    assert (f"npm run {script}", cwd) in commands
    assert script in json.loads((ROOT / cwd / "package.json").read_text())["scripts"]


# ---------------------------------------------------------------------------------------------------------------------
# The path scan: every repo file a suite names is a path that selects it

PATH_LITERAL = re.compile(r"""['"`]((?:\.{1,2}/)*(?:[\w@.-]+/)+[\w@.-]+\.\w+)['"`]""")


def suite_files(check: dict) -> list[Path]:
    """The test files and scripts ``check``'s command names, directly or through the npm scripts it runs."""
    cmd, cwd = check["command"], ROOT / check.get("cwd", ".")
    m = re.match(r"npm (?:--prefix (\S+) )?(?:run (\S+)|test\b)", cmd)
    words = cmd.split()
    if m:
        cwd = ROOT / (m.group(1) or check.get("cwd", "."))
        scripts = json.loads((cwd / "package.json").read_text())["scripts"]
        todo, seen, words = [m.group(2) or "test"], set(), []
        while todo:
            name = todo.pop()
            if name not in seen:
                seen.add(name)
                todo += re.findall(r"npm run ([\w:-]+)", scripts[name])
                words += scripts[name].split()
    files = []
    for w in (w.strip("'\"") for w in words):
        if "/" in w and re.search(r"\.(mjs|js|py)$", w):
            files += [Path(os.path.normpath(f)) for f in glob.glob(str(cwd / w)) if Path(f).is_file()]
    return files


def unmatched_references(check: dict) -> dict[str, set[str]]:
    """Existing repo files the suite's files name by a literal path, which the entry's globs do not select."""
    missing: dict[str, set[str]] = {}
    for f in suite_files(check):
        for lit in set(PATH_LITERAL.findall(f.read_text(encoding="utf-8", errors="replace"))):
            for base in (ROOT, f.parent):
                p = Path(os.path.normpath(base / lit))
                if not p.is_file() or ROOT not in p.parents or "node_modules" in p.parts:
                    continue
                rel = p.relative_to(ROOT).as_posix()
                if not pf.matched_paths(check, [rel]):
                    missing.setdefault(rel, set()).add(f.relative_to(ROOT).as_posix())
                break
    return missing


def test_every_file_a_suite_names_selects_it(mapping):
    """#766: webkit-unit hashed tools/gyropup_showcase.py and five figure stills but was not selected by them."""
    problems, scanned = [], 0
    for check in mapping["checks"]:
        scanned += bool(suite_files(check))
        for rel, by in sorted(unmatched_references(check).items()):
            problems.append(f"{check['id']}: {rel} (named in {', '.join(sorted(by))}) is not in its paths")
    assert scanned >= 20, f"only {scanned} entries had files to scan: the scan has stopped finding them"
    assert not problems, "add these paths (or a glob over them) to the entries:\n" + "\n".join(problems)


def test_the_scan_finds_a_planted_reference(tmp_path):
    check = {"id": "w", "paths": ["software/cadagent/webkit/**"], "command": "npm run test:webkit-unit",
             "cwd": "tools/site"}
    assert "tools/gyropup_showcase.py" in unmatched_references(check)
    check["paths"].append("tools/**")
    assert "tools/gyropup_showcase.py" not in unmatched_references(check)


# ---------------------------------------------------------------------------------------------------------------------
# Path matching and selection


@pytest.mark.parametrize("glob,path,hit", [
    ("**", "README.md", True),
    ("**/*.md", "README.md", True),
    ("**/*.md", "docs/a/b.md", True),
    ("software/cadagent/*.py", "software/cadagent/cli.py", True),
    ("software/cadagent/*.py", "software/cadagent/mechanical/holes.py", False),
    ("software/cadagent/webkit/**", "software/cadagent/webkit/scada/explorer/main.mjs", True),
    ("tests/webkit/*.test.mjs", "tests/webkit/files/x.test.mjs", False),
    ("tools/site/assets/install.*", "tools/site/assets/install.ps1", True),
    ("docs/?.md", "docs/ab.md", False),
])
def test_glob_matching(glob, path, hit):
    assert bool(pf.glob_regex(glob).match(path)) is hit


def test_the_real_case_selects_the_scada_provenance_check(mapping):
    """#753's first commit changed the explorer's main.mjs without regenerating thumbnails.json."""
    ids = {i.id for i in pf.select(mapping, ["software/cadagent/webkit/scada/explorer/main.mjs"])}
    assert {"scada-scenario-thumbnails", "scada-explorer-browser[chromium]", "scada-explorer-browser[webkit]",
            "pytest-repo"} <= ids
    assert "webkit-unit" not in ids and "fea[chromium]" not in ids          # the scada kit is excluded there


def test_acceptance_coverage(mapping):
    """The issue's floor: model and SCADA source hashes, browser suites per component, tests/repo, the site build."""
    def ids(path):
        return {i.check["id"] for i in pf.select(mapping, [path])}
    assert "webkit-unit" in ids("software/cadagent/webkit/model/model.js")          # renderer_sha256
    assert {"site-build", "site-browser"} <= ids("docs/practice/agent-workflow.md")
    assert {"fea", "stage", "part-table", "file-viewer", "assembly-guide"} <= ids("software/cadagent/webkit/ui/x.js")
    assert "pytest-repo" in ids("tools/ci/preflight.py")
    assert "repo-map" in ids("tests/repo/ci/README.md")                               # a new folder needs docs/map.md


@pytest.mark.parametrize("readme", ["tests/repo/ci/README.md", "tools/ci/README.md", "README.md",
                                    "software/cadagent/mechanical/README.md", ".github/CONTRIBUTING.md"])
def test_a_readme_anywhere_selects_the_site_browser_diagram_widths(mapping, readme):
    """#766: tests/repo/ci/README.md's new map was 748 px wide at 1100 px and failed website-browser.mjs's diagram
    widths in CI. Every README (and CONTRIBUTING, which owns .github's map) is published as a page, so a change to one
    selects the site build, the browser test that measures its diagrams in both engines, and the folder-map drawing."""
    ids = {i.id for i in pf.select(mapping, [readme])}
    assert {"site-build", "site-browser[chromium]", "site-browser[webkit]", "folder-maps", "repo-map"} <= ids, ids


@pytest.mark.parametrize("path", ["docs/research/process-profiles.yaml", "tools/research_figures.py", "x.txt"])
def test_whole_suite_entries_take_every_path(mapping, path):
    """CI runs the whole pytest suite on every pull request; its tests read docs/ and tools/ too (#766)."""
    ids = {i.check["id"] for i in pf.select(mapping, [path])}
    assert {"pytest-core", "pytest-full"} <= ids


@pytest.mark.parametrize("path", ["tools/gyropup_showcase.py", "tools/site/figures/fan-curve-still.mjs",
                                  "tools/mermaid/package-lock.json", "docs/img/gyropup/SOURCE.json"])
def test_webkit_unit_hash_sources_select_it(mapping, path):
    assert "webkit-unit" in {i.check["id"] for i in pf.select(mapping, [path])}


def test_engines_exclude_and_per_match():
    mapping = {"checks": [
        {"id": "b", "paths": ["kit/**"], "exclude": ["kit/scada/**"], "engines": ["chromium", "webkit"],
         "command": "x", "mirrors": []},
        {"id": "d", "paths": ["software/cadagent/**"], "per_match": r"^software/cadagent/(?P<domain>[a-z]+)/",
         "per_match_requires": ["tests/{domain}"], "command": "pytest tests/{domain}", "mirrors": []}]}
    sel = pf.select(mapping, ["kit/a.js", "kit/scada/b.js", "software/cadagent/repo/x.py",
                              "software/cadagent/nowhere/y.py"], ROOT)
    assert [i.id for i in sel] == ["b[chromium]", "b[webkit]", "d:repo"]
    assert sel[0].because == ["kit/a.js"]
    assert sel[2].command({}) == "pytest tests/repo"


# ---------------------------------------------------------------------------------------------------------------------
# Capability reporting: what cannot run here is "not run", with the reason


def _machine(tmp_path, probes=None, browsers=(), node=(), chrome=False, monkeypatch=None):
    root = tmp_path / "repo"
    for folder in node:
        (root / folder / "node_modules").mkdir(parents=True)
        (root / folder / "node_modules" / ".package-lock.json").write_text("{}")
    pw = root / "tools/site/node_modules/playwright-core"
    pw.mkdir(parents=True, exist_ok=True)
    (pw / "browsers.json").write_text(json.dumps({"browsers": [
        {"name": "chromium", "revision": "1194"}, {"name": "chromium-headless-shell", "revision": "1194"},
        {"name": "webkit", "revision": "2215"}]}))
    cache = tmp_path / "browsers"
    for b in browsers:
        (cache / b).mkdir(parents=True)
    machine = pf.Machine(root, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PLAYWRIGHT_BROWSERS_PATH": str(cache)})
    if monkeypatch is not None:
        monkeypatch.setattr(pf, "CHROME_CHANNEL", tmp_path / ("chrome" if chrome else "absent"))
        if chrome:
            (tmp_path / "chrome").write_text("")
    if probes is not None:
        machine.python_candidates = lambda: list(probes)
        machine.probe = lambda exe, modules, dists, pythonpath: probes[exe]
    return machine


def _probe(version, mods=(), dists=None, playwright=None):
    return {"version": version, "prefix": f"/env/{version}/{'-'.join(mods)}", "modules": {m: True for m in mods},
            "dists": dists or {}, "playwright": playwright}


def _assess(check, machine, slow=False, engine=None, done=None):
    inst = pf.Instance(check, engine)
    pf.assess(inst, machine, slow, done or {}, {"tmp": "/t", "base": "b", "root": "/r"})
    return inst


def test_exact_python_minor_that_differs_is_not_run(tmp_path):
    need = {"python": {"version": "3.12", "exact": True, "modules": ["PIL"], "why": "fingerprint"}}
    machine = _machine(tmp_path, probes={"/py313": _probe("3.13.1", ["PIL"]), "/py312": _probe("3.12.4")})
    inst = _assess({"id": "x", "command": "c", "needs": need}, machine)
    assert inst.status == "not run"
    assert "version differs: /py313 is 3.13, CI pins 3.12 (fingerprint)" in inst.reason
    assert "/py312 (3.12) lacks PIL" in inst.reason


def test_inexact_python_minor_runs_with_a_note(tmp_path):
    need = {"python": {"version": "3.12", "modules": ["yaml"]}}
    machine = _machine(tmp_path, probes={"/py313": _probe("3.13.1", ["yaml"])})
    inst = _assess({"id": "x", "command": "c", "needs": need}, machine)
    assert inst.status == "runnable" and inst.python == "/py313"
    assert any("CI pins 3.12: evidence only" in n for n in inst.notes)


def test_matching_minor_is_preferred_and_dist_pins_are_checked(tmp_path):
    need = {"python": {"version": "3.12", "modules": [], "dists": ["optuna==3.4.0"]}}
    probes = {"/a": _probe("3.13.0", dists={"optuna": "3.4.0"}), "/b": _probe("3.12.1", dists={"optuna": "3.4.0"}),
              "/c": _probe("3.12.2", dists={"optuna": "4.0.0"})}
    inst = _assess({"id": "x", "command": "c", "needs": need}, _machine(tmp_path, probes=probes))
    assert inst.python == "/b" and not inst.notes
    del probes["/a"], probes["/b"]
    inst = _assess({"id": "x", "command": "c", "needs": need}, _machine(tmp_path / "2", probes=probes))
    assert inst.status == "not run" and "lacks optuna==3.4.0" in inst.reason


def test_browser_engines(tmp_path, monkeypatch):
    check = {"id": "s", "command": "c", "engines": ["chromium", "webkit"]}
    m = _machine(tmp_path, monkeypatch=monkeypatch)
    inst = _assess(check, m, engine="webkit")
    assert inst.status == "not run" and "WebKit r2215" in inst.reason and "Not installed for you" in inst.reason
    assert _assess(check, m, engine="chromium").status == "not run"
    m = _machine(tmp_path / "chrome", chrome=True, browsers=["chromium-1243"], monkeypatch=monkeypatch)
    inst = _assess(check, m, engine="chromium")
    assert inst.status == "runnable" and "PLAYWRIGHT_CHANNEL" not in inst.env
    assert any("not CI's Playwright Chromium r1194" in n and "chromium-1243" in n for n in inst.notes)
    m = _machine(tmp_path / "exact", browsers=["chromium-1194", "chromium_headless_shell-1194", "webkit-2215"],
                 monkeypatch=monkeypatch)
    assert _assess(check, m, engine="chromium").env == {"PLAYWRIGHT_BROWSER": "chromium", "PLAYWRIGHT_CHANNEL": "chromium"}
    assert _assess(check, m, engine="webkit").env == {"PLAYWRIGHT_BROWSER": "webkit"}


def test_node_deps_os_slow_and_order(tmp_path):
    m = _machine(tmp_path, node=["tools/a"])
    assert _assess({"id": "x", "command": "c", "needs": {"node_deps": ["tools/a"]}}, m).status == "runnable"
    inst = _assess({"id": "x", "command": "c", "needs": {"node_deps": ["tools/b"]}}, m)
    assert inst.status == "not run" and "npm ci" in inst.reason
    inst = _assess({"id": "x", "command": "c", "needs": {"os": "plan9"}}, m)
    assert inst.status == "not run" and "Plan9" in inst.reason
    inst = _assess({"id": "x", "command": "c", "cost": "slow", "cost_note": "big"}, m)
    assert inst.status == "skipped" and "big" in inst.reason and "--slow" in inst.reason
    assert _assess({"id": "x", "command": "c", "cost": "slow"}, m, slow=True).status == "runnable"
    inst = _assess({"id": "x", "command": "c", "needs": {"after": ["site-build"]}}, m)
    assert inst.status == "not run" and "not selected" in inst.reason
    built = pf.Instance({"id": "site-build", "provides_env": {"SITE": "{tmp}/site"}}, status="passed")
    inst = _assess({"id": "x", "command": "c", "needs": {"after": ["site-build"]}}, m, done={"site-build": built})
    assert inst.status == "runnable" and inst.env == {"SITE": "/t/site"}
    built.status = "failed"
    assert _assess({"id": "x", "command": "c", "needs": {"after": ["site-build"]}}, m,
                   done={"site-build": built}).status == "not run"


# ---------------------------------------------------------------------------------------------------------------------
# Exit codes, end to end on a scratch repository


def _repo(tmp_path, checks):
    root = tmp_path / "repo"
    root.mkdir()
    for cmd in (["init", "-q"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(["git", *cmd], cwd=root, check=True)
    mapping = tmp_path / "checks.json"
    mapping.write_text(json.dumps({"checks": checks}))
    return ["--root", str(root), "--mapping", str(mapping)]


def _check(id_, command, **kw):
    return {"id": id_, "paths": ["a/**"], "command": command, "mirrors": [], "cost": "fast", **kw}


def test_exit_codes(tmp_path, capsys):
    args = _repo(tmp_path, [_check("ok", "true"), _check("bad", "echo boom; exit 3"),
                            _check("away", "true", needs={"os": "plan9"}), _check("big", "false", cost="slow")])
    assert pf.main(args + ["--paths", "b/x"]) == 0                                     # nothing selected
    assert "No CI check" in capsys.readouterr().out
    assert pf.main(args + ["--paths", "a/x", "--only", "ok"]) == 0
    capsys.readouterr()
    assert pf.main(args + ["--paths", "a/x"]) == 1
    out = capsys.readouterr().out
    for expected in (r"ok +passed", r"bad +failed: exit 3", r"\| boom", r"away +not run: CI runs this on Plan9",
                     r"big +skipped: slow"):
        assert re.search(expected, out), expected
    assert pf.main(args + ["--paths", "a/x", "--list"]) == 0                           # lists, runs nothing
    assert "would run" in capsys.readouterr().out
    assert pf.main(args + ["--paths", "a/x", "--only", "nope"]) == 2


def test_json_report_never_counts_not_run_as_passed(tmp_path, capsys):
    args = _repo(tmp_path, [_check("ok", "true"), _check("away", "true", needs={"os": "plan9"})])
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 3                   # incomplete, not passed
    report = json.loads(capsys.readouterr().out)
    assert {c["id"]: c["status"] for c in report["checks"]} == {"ok": "passed", "away": "not run"}
    assert report["verdict"] == "incomplete" and [n["id"] for n in report["not_run"]] == ["away"]
    assert report["paths"] == ["a/x"] and "evidence" in report["limits"]
    assert pf.main(args + ["--paths", "a/x", "--json", "--only", "ok"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "passed"


def test_a_selected_check_that_did_not_run_is_listed_at_the_end(tmp_path, capsys):
    """#766: a slow site browser check was selected, reported as skipped among many lines, and missed. The report now
    ends with every selected check that did not run and why, and the exit status says the run was incomplete."""
    args = _repo(tmp_path, [_check("ok", "true"), _check("browser", "true", cost="slow", cost_note="whole site",
                                                          title="The built site in a browser: diagram widths")])
    assert pf.main(args + ["--paths", "a/x"]) == 3
    tail = capsys.readouterr().out.splitlines()[-3:]
    assert tail[0].startswith("NOT RUN HERE: 1 of 2 selected checks")
    assert tail[1] == "  - browser (The built site in a browser: diagram widths): skipped: slow (whole site); --slow runs it"
    assert tail[2] == "Verdict: incomplete"
    assert pf.main(args + ["--paths", "a/x", "--slow"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "Verdict: passed"


def test_diff_base_and_uncommitted_paths(tmp_path, capsys):
    args = _repo(tmp_path, [_check("ok", "true")])
    root = Path(args[1])
    subprocess.run(["git", "branch", "-q", "base"], cwd=root, check=True)
    (root / "a").mkdir()
    (root / "a" / "committed.txt").write_text("1")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "y"], cwd=root, check=True)
    (root / "a" / "new.txt").write_text("2")
    assert pf.main(args + ["--base", "base", "--json", "--list"]) == 0
    assert json.loads(capsys.readouterr().out)["paths"] == ["a/committed.txt", "a/new.txt"]
    assert pf.main(args + ["--base", "base", "--json", "--list", "--committed-only"]) == 0
    assert json.loads(capsys.readouterr().out)["paths"] == ["a/committed.txt"]
    assert pf.main(args + ["--base", "no-such-ref"]) == 2


def test_a_hung_check_is_stopped_and_fails(tmp_path, capsys):
    args = _repo(tmp_path, [_check("hang", "sleep 30 & sleep 30")])
    assert pf.main(args + ["--paths", "a/x", "--timeout", "1", "--json"]) == 1
    (report,) = json.loads(capsys.readouterr().out)["checks"]
    assert report["status"] == "failed" and report["reason"] == "timed out after 1 s" and report["seconds"] < 10


def test_large_output_and_stdin_do_not_block_a_check(tmp_path, capsys):
    """Output goes to a file, not an undrained pipe, and stdin is closed: a check that writes megabytes and reads
    stdin finishes instead of waiting (the site-unit timeout on #766 was the suite's own site builds, not this). It
    fails on purpose, so its log is kept to measure."""
    args = _repo(tmp_path, [_check("chatty", "head -c 3000000 /dev/zero | tr '\\0' x; cat; exit 4")])
    assert pf.main(args + ["--paths", "a/x", "--timeout", "60", "--json"]) == 1
    (report,) = json.loads(capsys.readouterr().out)["checks"]
    assert report["reason"] == "exit 4" and report["seconds"] < 30
    assert Path(report["log"]).stat().st_size >= 3_000_000


def test_logs_are_deleted_when_everything_passed(tmp_path, capsys):
    args = _repo(tmp_path, [_check("ok", "echo hi")])
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert not Path(report["workdir"]).exists()


def test_a_checks_own_timeout_and_heap_need(tmp_path, monkeypatch):
    m = _machine(tmp_path)
    m.node_heap_mb = lambda: 2096
    need = {"node_heap_mb": 4096, "node_heap_why": "big suite"}
    inst = _assess({"id": "x", "command": "c", "needs": need}, m)
    assert inst.status == "runnable" and inst.env["NODE_OPTIONS"].endswith("--max-old-space-size=4096")
    assert any("default Node heap is 2096 MB" in n and "big suite" in n for n in inst.notes)
    m.node_heap_mb = lambda: 4144
    assert "NODE_OPTIONS" not in _assess({"id": "x", "command": "c", "needs": need}, m).env
    seen = []
    monkeypatch.setattr(pf, "run", lambda inst, ctx, machine, workdir, timeout: seen.append(timeout))
    (tmp_path / "t").mkdir()
    args = _repo(tmp_path / "t", [_check("own", "true", timeout=5400), _check("plain", "true")])
    pf.main(args + ["--paths", "a/x", "--json"])
    pf.main(args + ["--paths", "a/x", "--json", "--timeout", "7"])
    assert seen == [5400, pf.DEFAULT_TIMEOUT, 7, 7]


# ---------------------------------------------------------------------------------------------------------------------
# Review of #766: never "passed" for something that did not run; malformed mappings are setup errors


def test_only_runs_a_named_check_the_paths_do_not_select(tmp_path, capsys):
    args = _repo(tmp_path, [_check("ok", "true"), _check("other", "echo ran", paths=["b/**"])])
    assert pf.main(args + ["--paths", "a/x", "--only", "other", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert [(c["id"], c["status"]) for c in report["checks"]] == [("other", "passed")]
    assert report["checks"][0]["because"] == ["named with --only; no changed path selects it"]


def test_only_a_per_match_check_without_a_value_is_not_run(tmp_path, capsys):
    args = _repo(tmp_path, [_check("dom", "echo {domain}", per_match=r"^a/(?P<domain>[a-z]+)/")])
    assert pf.main(args + ["--paths", "zzz", "--only", "dom", "--json"]) == 3
    (check,) = json.loads(capsys.readouterr().out)["checks"]
    assert check["status"] == "not run" and "no changed path gives it a value" in check["reason"]


def test_nothing_selected_is_not_called_passed(tmp_path, capsys):
    args = _repo(tmp_path, [_check("ok", "true")])
    assert pf.main(args + ["--paths", "b/x"]) == 0
    out = capsys.readouterr().out
    assert "Verdict: nothing selected" in out and "Verdict: passed" not in out
    assert pf.main(args + ["--paths", "b/x", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "nothing selected"


@pytest.mark.parametrize("checks,needle", [
    (None, "no `checks` list"),
    ([{"id": "a", "paths": ["a/**"], "command": "echo ${HOME}", "mirrors": []}], "names {HOME}"),
    ([{"id": "a", "paths": ["a/**"], "command": "echo {", "mirrors": []}], "stray brace"),
    ([{"id": "a", "paths": ["a/**"], "command": "x", "per_match": "^(?P<d>[a-z]+", "mirrors": []}], "not a regex"),
    ([{"id": "a", "paths": ["a/**"], "command": "echo {d}", "per_match": "^(?P<d>.*)$", "mirrors": []}],
     "plain character class"),
    ([{"id": "a", "paths": ["a/**"], "mirrors": []}], "no `command`"),
])
def test_a_malformed_mapping_exits_2_with_a_message(tmp_path, capsys, checks, needle):
    args = _repo(tmp_path, [])
    Path(args[3]).write_text(json.dumps({} if checks is None else {"checks": checks}))
    assert pf.main(args + ["--paths", "a/x"]) == 2
    assert needle in capsys.readouterr().err


def test_per_match_values_are_shell_quoted(tmp_path):
    inst = pf.Instance({"id": "d", "command": "echo {d}"}, subs={"d": "x; touch PWNED"})
    assert inst.command({}) == "echo 'x; touch PWNED'"


def test_a_pass_on_another_runtime_is_counted_and_flagged(tmp_path, capsys, monkeypatch):
    args = _repo(tmp_path, [_check("same", "true"), _check("other", "node -e 1", needs={"python": {"version": "3.12"}})])
    monkeypatch.setattr(pf.Machine, "choose_python",
                        lambda self, need, pp: ("/py313", {"version": "3.13.0", "prefix": "/p"}, ""))
    monkeypatch.setattr(pf.Machine, "node_major", lambda self: "20")
    mapping = json.loads(Path(args[3]).read_text())
    mapping["ci_node_major"] = "22"
    Path(args[3]).write_text(json.dumps(mapping))
    assert pf.main(args + ["--paths", "a/x"]) == 0
    out = capsys.readouterr().out
    assert "1 passed on a different browser, Python or Node than CI's (evidence, not CI's result): other (python/node)" in out
    assert "runs on Node 20, CI pins 22" in out
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 0
    flags = {c["id"]: c["differs"] for c in json.loads(capsys.readouterr().out)["checks"]}
    assert flags == {"same": [], "other": ["python", "node"]}


def test_ctrl_c_stops_the_running_check_and_its_children(tmp_path, capsys, monkeypatch):
    marker = tmp_path / "child.pid"
    args = _repo(tmp_path, [_check("long", f"sleep 60 & echo $! > {marker}; wait")])
    real_wait, calls = subprocess.Popen.wait, []

    def interrupted(self, timeout=None):
        if not calls and self.args[:2] == ["/bin/sh", "-c"]:                # the check, not git or a probe
            calls.append(1)
            for _ in range(100):
                if marker.exists() and marker.read_text().strip():
                    break
                time.sleep(0.05)
            raise KeyboardInterrupt
        return real_wait(self, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, "wait", interrupted)
    assert pf.main(args + ["--paths", "a/x"]) == 130
    assert "interrupted; stopped long" in capsys.readouterr().err
    child = int(marker.read_text())
    time.sleep(0.2)
    status = Path(f"/proc/{child}/status")
    state = re.search(r"^State:\s+(\S)", status.read_text(), re.M).group(1) if status.exists() else "gone"
    assert state in {"gone", "Z", "X"}, f"the check's child {child} still runs ({state})"   # killed; maybe unreaped
