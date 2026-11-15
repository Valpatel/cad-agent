"""The local preflight (``tools/ci/preflight.py``) and its mapping (``.github/ci-checks.json``), #759.

The drift guard: every command a pull-request workflow runs as a check (pytest, ``npm run``/``npm test``, ``node``
scripts, the repo's own ``tools/``/``tests/`` scripts, ``cad-agent``) is mirrored by a mapping entry, and every entry's
mirror still exists, so the mapping cannot drift silently. A step that runs no check must be one of a few kinds of
setup (``SETUP``), named here with the reason each is not a check.

Which workflows: those triggered by ``pull_request``. ``gates.yml`` (``pull_request_target``) reads the PR through
the API as data with a token, ``release.yml`` and ``supply-chain.yml`` run after merging or on a schedule; none of them
can be mirrored offline before pushing. Steps that run only on ``workflow_dispatch`` are manual studies, not PR checks.

Then the preflight's own behaviour, each on planted inputs: path matching, selection, capability reporting (a check
that cannot run here is "not run", never passed) and exit codes.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
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
  | python3?\s+(?:-\w+\s+)*(?:tools|tests)/\S+\.py\b   # the repo's own check scripts
  | npm\s+(?:--prefix\s+\S+\s+)?(?:run|test)\b         # npm scripts
  | node\s+(?!-e\b|--version\b)\S                      # node tests and builds (not version probes)
  | cad-agent\b
)""", re.X)

# Steps that run no check. Each kind, and why it is not one; a step matching none of these and running no check fails
# the test, so a new kind is a decision made here, not a silent gap.
SETUP = {
    r"^npm (?:--prefix \S+ )?ci\b": "installs the locked Node dependencies",
    r"^(?:python3?\s+-m\s+)?pip install\b": "installs Python packages",
    r"^git config\b": "configures git inside the test container",
    r'^echo "key=': "computes a cache key",
    r"^sudo python3 tools/ci/apt_mirror\.py\b": "provisions the runner's system libraries",
    r'^node --version\b|^python -c "': "asserts the runner's own toolchain or imports, not the change",
}


def segments(script: str) -> list[str]:
    """The simple commands of a ``run:`` script: lines split at ``&&``, ``||``, ``;`` and ``|``, without comments or
    the shell keywords that lead them, whitespace collapsed."""
    out = []
    for line in script.splitlines():
        line = re.sub(r"\s#\s.*$", "", line).strip()
        if not line or line.startswith("#"):
            continue
        for seg in re.split(r"\s*(?:&&|\|\||;|\|)\s*", line):
            seg = re.sub(r"^(?:then|else|do)\s+", "", seg.strip())
            if seg and seg not in {"then", "else", "do", "done", "fi"}:
                out.append(" ".join(seg.split()))
    return out


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
    """``(workflow, job, step label, run script)`` for every PR-time ``run:`` step."""
    for name, doc in flows.items():
        for job_id, job in (doc.get("jobs") or {}).items():
            for i, step in enumerate(job.get("steps") or []):
                if "run" not in step or "workflow_dispatch" in str(step.get("if", "")):
                    continue
                label = step.get("name") or f"step {i + 1} (`{segments(step['run'])[0][:60]}`)"
                yield name, job_id, label, step["run"]


def audit(flows: dict[str, dict], mapping: dict) -> tuple[list[str], list[str], set, set]:
    """``(unmapped, unclassified, found, mirrored)``: messages for check commands no entry mirrors and for steps that
    are neither checks nor known setup; the (workflow, job, command) keys found in the workflows and in the mapping."""
    mirrored = {(m["workflow"], m["job"], " ".join(m["run"].split())) for c in mapping["checks"] for m in c["mirrors"]}
    unmapped, unclassified, found = [], [], set()
    for wf, job, label, script in workflow_steps(flows):
        segs = segments(script)
        checks = [s for s in segs if CHECK.match(s)]
        if not checks:
            if not any(re.match(rx, segs[0]) for rx in SETUP):
                unclassified.append(f"{wf} / {job} / {label}: runs `{segs[0]}`, which is neither a mapped check nor "
                                    f"known setup. If it checks the change, add a mapping entry to "
                                    f".github/ci-checks.json; if it only sets up, add its kind to SETUP here with why.")
            continue
        for cmd in checks:
            found.add((wf, job, cmd))
            if (wf, job, cmd) not in mirrored:
                unmapped.append(f"{wf} / {job} / {label}: `{cmd}` has no entry in .github/ci-checks.json. Add a "
                                f"mapping entry whose mirrors include {{\"workflow\": \"{wf}\", \"job\": \"{job}\", "
                                f"\"run\": {json.dumps(cmd)}}}, with the paths that should select it.")
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
    assert "`npm run test:model-new` has no entry" in unmapped[0] and "Add a mapping entry" in unmapped[0]
    assert len(unclassified) == 1 and "curl" in unclassified[0]


def test_segments_and_classification():
    script = ('if [ "$X" = y ]; then\n  python3 tools/resource_audit.py gate --base HEAD^1   # why\nelse x; fi\n'
              'node tools/site/build-site.mjs --out "$T/site" | tee "$T/site.log"\n'
              'pip install "optuna==3.4.0" && python -m pytest -q tests/a.py\nnode --version && node -e "1"')
    segs = segments(script)
    assert "python3 tools/resource_audit.py gate --base HEAD^1" in segs
    assert 'node tools/site/build-site.mjs --out "$T/site"' in segs
    assert [s for s in segs if CHECK.match(s)] == ["python3 tools/resource_audit.py gate --base HEAD^1",
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
    assert pf.main(args + ["--paths", "a/x", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert {c["id"]: c["status"] for c in report["checks"]} == {"ok": "passed", "away": "not run"}
    assert report["paths"] == ["a/x"] and "evidence" in report["limits"]


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
