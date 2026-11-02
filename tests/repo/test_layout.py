"""Where files go: the layout gate that keeps the repo from sprawling (owner, 2026-11-02: "tests/ folder for example
will turn into an absolute mountain garage pile").

The rules (AGENTS.md "Repo structure and where files go", CONTRIBUTING.md "Where files go"):

* no test file sits directly in ``tests/``: it goes in ``tests/<domain>/``, the folder named after the
  ``src/cadagent/<domain>/`` package its subject lives in, or in one of the few areas that are not packages;
* each ``tests/`` folder is a package or such an area, and has a README and an ``__init__.py``;
* no new top-level folder in the repo;
* no new file at the top of ``src/`` or ``src/cadagent/`` (``tests/repo/test_package_layout.py`` keeps its modules);
* a folder that grows past ``CLUTTER_LIMIT`` files is split, by the growth rule; the folders over it today are listed in
  ``OVER_LIMIT``, which may only shrink.

Every failure says where the file goes, so an agent can fix it in one step. Each rule is a pure function of a file list,
and each is shown here to fail on a planted case as well as to pass on the repo.
"""
from __future__ import annotations

import functools
import re
import subprocess
import warnings
from collections import Counter
from pathlib import Path

import pytest

from tests.repo.test_package_layout import PACKAGES, TOP_MODULES

ROOT = Path(__file__).resolve().parents[2]

# Test areas that are not packages under src/cadagent/, and what each holds (tests/README.md has the same table).
AREAS = {
    "cli": "cli.py and the modules beside it at the top of the package (project, links, package, agentkit, _deps, "
           "the version)",
    "site": "cad-agent's own website and its build (tools/build-site.mjs and the site-*.mjs tools, the catalogue)",
    "repo": "the repository's own rules and tooling: the topic tree, this layout, private names, skills, the merge "
            "gates, releases, the supply-chain audit, vendored files",
    "fixtures": "shared test data, used by tests in any folder",
}
TEST_ROOT_FILES = {"__init__.py", "README.md", "conftest.py"}            # all that may sit directly in tests/
# .claude/ and .codex/ (wiring for the agent kit: links and generated files only) join this list in the PR that
# adds them.
TOP_DIRS = {".agents", ".github", "agents", "changelog.d", "docs", "examples", "lessons", "mining", "research",
            "skills", "src", "tests", "tools", "upstreams", "vendor", "web"}
SRC_FILES = {"cadagent"}                                                  # src/ holds the package and nothing else
PKG_FILES = {f"{m}.py" for m in TOP_MODULES} | {"README.md"}             # the top of src/cadagent/: may only shrink

# The growth rule: a folder with more files than this directly in it (its README.md and __init__.py aside) is split
# into subfolders named after the domains. Vendored trees keep their upstream layout; fixtures and the figure folders
# under docs/img/ hold one tool's output each, so splitting them would scatter it.
CLUTTER_LIMIT = 20
NOT_COUNTED = re.compile(r"^(vendor|upstreams)/|/vendor/|^tests/fixtures/|^docs/img/")
# Folders over the limit today. Each one is split in a PR that touches it, and comes off this list. The list may only
# shrink: a folder newly over the limit is split in the PR that takes it over, not added here.
OVER_LIMIT = {
    "docs": "#145 moves pages into docs/<domain>/ as each area reaches three pages",
    "tools": "figure generators and site build tools side by side; split into tools/<domain>/ and tools/site/",
    "src/cadagent/webkit": "browser modules served as one folder (pyproject package-data webkit/*); a split moves "
                           "their URLs",
}

IMPORT = re.compile(r"^\s*(?:from|import)\s+cadagent\.([a-z_.]+)", re.M)     # cadagent.<pkg>[.<sub>...]
FROM_TOP = re.compile(r"^\s*from\s+cadagent\s+import\s+\(?([^)\n]+)", re.M)  # from cadagent import a, b as c
README_GUIDE = "the table in tests/README.md"


def repo_files(untracked: bool = True) -> list[str]:
    """Tracked files, and with ``untracked`` the new (not ignored) ones too, so a file an agent just made is checked
    before it is committed."""
    cmd = ["git", "ls-files", "-z", "--cached"] + (["--others", "--exclude-standard"] if untracked else [])
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.split("\0") if p and (ROOT / p).exists())


def _git_files(untracked: bool):
    try:
        return repo_files(untracked)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout (an sdist): the layout is checked in the repo")


@pytest.fixture(scope="module")
def files():
    return _git_files(untracked=True)


@pytest.fixture(scope="module")
def tracked():
    """Tracked files only: an editor's or a harness's untracked folder (.vscode/, .idea/, .claude/settings.local.json)
    is not a new top-level folder anyone means to commit."""
    return _git_files(untracked=False)


def imported_modules(text: str) -> list[str]:
    """Every ``cadagent.<pkg>[.<sub>]`` a file imports, in both forms: ``from cadagent.review.gates import x`` and
    ``from cadagent import geometry, formulas as fx``."""
    mods = IMPORT.findall(text)
    for names in FROM_TOP.findall(text):
        mods += [n.split(" as ")[0].strip() for n in names.split(",") if n.strip() and not n.strip().startswith("#")]
    return [m.rstrip(".") for m in mods]


@functools.lru_cache(maxsize=1)
def _module_index() -> dict[str, frozenset[str]]:
    """Each module or subpackage name inside the domain packages, mapped to its dotted path(s) under cadagent."""
    index: dict[str, set[str]] = {}
    pkg = ROOT / "src" / "cadagent"
    for top in PACKAGES:
        for f in (pkg / top).rglob("*"):
            if "vendor" in f.parts or "__pycache__" in f.parts or f.name.startswith("_"):
                continue
            if f.suffix == ".py" or (f.is_dir() and (f / "__init__.py").exists()):
                rel = f.relative_to(pkg).with_suffix("") if f.suffix == ".py" else f.relative_to(pkg)
                index.setdefault(f.stem, set()).add(".".join(rel.parts))
    return {k: frozenset(v) for k, v in index.items()}


def _mirror(mod: str, dirs: set[str]) -> str:
    """The deepest tests/ folder that mirrors ``mod``'s package path (``simulation.explore.design`` →
    ``simulation/explore`` when that folder exists), else its top package."""
    parts = mod.split(".")
    for n in range(len(parts), 1, -1):
        if "/".join(parts[:n]) in dirs:
            return "/".join(parts[:n])
    return parts[0]


def domain_for(name: str, text: str, files: list[str] = ()) -> str:
    """The tests/ folder a test file belongs in (relative to tests/): a webkit or site suite by its name prefix; a test
    named after a package, a top-level module or a module inside a package (``test_geometry.py``, ``test_cli.py``,
    ``test_holes.py`` for ``mechanical/holes.py``; or its first word, ``test_anim_*`` for ``publish/anim/``) by that
    name; otherwise by the cadagent package it imports most (its main subject), in the deepest folder that mirrors the
    subpackage it imports most; else the folder of the tests that share its first word (``test_process_figures.py``
    beside ``test_process_profiles.py``); else ``cli`` when it imports a top-level module; else ``repo`` for the
    repo's own rules."""
    if name.startswith("webkit-"):
        return "webkit"
    if name.startswith(("website-", "site-")):
        return "site"
    stem = re.match(r"test_(.+)\.py$", name)
    if stem and stem.group(1) in PACKAGES:                    # test_geometry.py: named after its package
        return stem.group(1)
    if stem and ({f"{stem.group(1)}.py", f"_{stem.group(1)}.py"} & PKG_FILES):   # test_cli.py, test_deps.py
        return "cli"
    dirs = {str(Path(p).parent)[len("tests/"):] for p in files if p.startswith("tests/") and p.count("/") >= 2}
    if stem:                                                  # test_holes.py: named after mechanical/holes.py
        index = _module_index()
        for key in (stem.group(1), stem.group(1).split("_")[0]):
            if len(index.get(key, ())) == 1:
                return _mirror(next(iter(index[key])), dirs)
    mods = imported_modules(text)
    tops = Counter(m.split(".")[0] for m in mods if m.split(".")[0] in PACKAGES)
    if tops:
        top = max(tops, key=lambda k: (tops[k], -mods.index(next(m for m in mods if m.split(".")[0] == k))))
        deep = Counter(_mirror(m, dirs) for m in mods if m.split(".")[0] == top)
        best, n = deep.most_common(1)[0]
        return best if n * 2 > sum(deep.values()) else top
    word = re.match(r"test_([a-z0-9]+)", name)
    kin = sorted({str(Path(p).parent)[len("tests/"):] for p in files if word and p.count("/") >= 2
                  and p.startswith("tests/") and not p.startswith("tests/fixtures/")
                  and Path(p).name.startswith(f"test_{word.group(1)}")})
    if len(kin) == 1:
        return kin[0]
    if any(f"{m.split('.')[0]}.py" in PKG_FILES for m in mods):
        return "cli"
    return "repo"


def flat_test_problems(files: list[str], read=lambda p: (ROOT / p).read_text(encoding="utf-8", errors="replace")):
    """A file directly in tests/ that is not on the short allowlist, with the folder it goes in."""
    out = []
    for p in files:
        parts = p.split("/")
        if len(parts) != 2 or parts[0] != "tests" or parts[1] in TEST_ROOT_FILES:
            continue
        dom = domain_for(parts[1], read(p), files)
        out.append(f"{p}: test files go in tests/<domain>/, not in tests/. This one belongs in tests/{dom}/: "
                   f"git mv {p} tests/{dom}/ (and fix paths relative to __file__: one more parent). "
                   f"If its main subject is another package, use that folder instead ({README_GUIDE}).")
    return out


def folder_problems(files: list[str]):
    """Each folder under tests/ is a package of src/cadagent/ (a nested one mirrors a subpackage) or a listed area, and
    has its README.md and __init__.py."""
    out = []
    dirs = {str(Path(p).parent) for p in files if p.startswith("tests/") and not p.startswith("tests/fixtures/")}
    dirs = {d for d in dirs if d != "tests"}
    known = sorted(PACKAGES | AREAS.keys())
    for d in sorted(dirs):
        parts = d.split("/")[1:]
        top = parts[0]
        if top not in PACKAGES and top not in AREAS:
            out.append(f"{d}/: tests/ holds one folder per src/cadagent/ package or listed area ({', '.join(known)}); "
                       f"move its files to the folder of the package they test, or add the area to AREAS in "
                       f"tests/repo/test_layout.py and to {README_GUIDE}")
            continue
        if top in PACKAGES and len(parts) > 1 and not (ROOT / "src" / "cadagent" / Path(*parts)).is_dir():
            out.append(f"{d}/: a nested test folder mirrors a subpackage, and src/cadagent/{'/'.join(parts)}/ does "
                       f"not exist; name it after one (as tests/review/gates/ would mirror src/cadagent/review/gates/)")
        for need in ("README.md", "__init__.py"):
            if f"{d}/{need}" not in files:
                why = ("a README with a Mermaid map (docs/style-guide.md)" if need == "README.md"
                       else "an empty __init__.py, so two folders may hold test files of the same name")
                out.append(f"{d}/: add {d}/{need}: {why}")
    return out


def top_dir_problems(files: list[str]):
    out = []
    for top in sorted({p.split("/")[0] for p in files if "/" in p} - TOP_DIRS):
        out.append(f"{top}/: never add a top-level folder. Put the files in the folder for their kind: code in "
                   f"src/cadagent/<domain>/, tests in tests/<domain>/, pages in docs/, scripts in tools/ (AGENTS.md, "
                   f"'Repo structure and where files go'). A new kind of folder is the owner's call, in its own PR "
                   f"that adds it to TOP_DIRS in tests/repo/test_layout.py.")
    return out


def src_problems(files: list[str]):
    out = []
    for p in files:
        parts = p.split("/")
        if parts[0] != "src":
            continue
        if len(parts) == 2 and parts[1] not in SRC_FILES:
            out.append(f"{p}: src/ holds only the cadagent package; move it into src/cadagent/<domain>/")
        elif len(parts) == 3 and parts[1] == "cadagent" and parts[2] not in PKG_FILES:
            out.append(f"{p}: no new files at the top of src/cadagent/; put it in the package for its domain, "
                       f"src/cadagent/<domain>/ ({', '.join(sorted(PACKAGES))}), with its line in that domain's api: "
                       f"list in docs/areas.yaml (src/cadagent/README.md)")
    return out


def clutter(files: list[str]) -> dict[str, int]:
    """Files directly in each folder, not counting its README.md and __init__.py, where over the limit."""
    counts = Counter(str(Path(p).parent) for p in files
                     if "/" in p and not NOT_COUNTED.search(p) and Path(p).name not in ("README.md", "__init__.py"))
    return {d: n for d, n in counts.items() if n > CLUTTER_LIMIT}


def clutter_problems(files: list[str]):
    """Folders newly over the limit fail; listed ones that came under it fail too, so the list only shrinks."""
    over = clutter(files)
    out = [f"{d}/ holds {n} files, over the growth limit of {CLUTTER_LIMIT}: split it into subfolders named after the "
           f"domains (src/cadagent/<domain>/), each with a README and a Mermaid map, using git mv and updating every "
           f"reference (AGENTS.md growth rule). Do not add it to OVER_LIMIT: that list only shrinks."
           for d, n in sorted(over.items()) if d not in OVER_LIMIT]
    out += [f"{d}/ is at or under {CLUTTER_LIMIT} files now: take it off OVER_LIMIT in tests/repo/test_layout.py"
            for d in sorted(OVER_LIMIT) if d not in over]
    return out


# --- the repo passes -------------------------------------------------------------------------------------------------

def test_no_test_file_sits_directly_in_tests(files):
    problems = flat_test_problems(files)
    assert not problems, "\n".join(problems)


def test_each_tests_folder_is_a_package_or_a_listed_area(files):
    problems = folder_problems(files)
    assert not problems, "\n".join(problems)


def test_no_new_top_level_folder(tracked):
    problems = top_dir_problems(tracked)
    assert not problems, "\n".join(problems)


def test_no_new_file_at_the_top_of_src(files):
    problems = src_problems(files)
    assert not problems, "\n".join(problems)


def test_folders_grow_into_subfolders_not_mountains(files):
    problems = clutter_problems(files)
    assert not problems, "\n".join(problems)
    over = clutter(files)
    for d in sorted(OVER_LIMIT):
        warnings.warn(f"{d}/ holds {over[d]} files (limit {CLUTTER_LIMIT}): split it in the next PR that touches it "
                      f"({OVER_LIMIT[d]})", UserWarning, stacklevel=1)


def test_every_listed_area_and_package_folder_is_documented_in_the_tests_readme(files):
    """Folders read from the file list, not the disk: a folder a move emptied keeps its __pycache__ on disk."""
    text = (ROOT / "tests" / "README.md").read_text(encoding="utf-8")
    present = sorted({p.split("/")[1] for p in files if p.startswith("tests/") and p.count("/") >= 2})
    missing = [d for d in present if f"[`{d}/`]({d}/" not in text]
    assert not missing, f"tests/README.md has no row linking {missing}"
    assert set(present) <= PACKAGES | AREAS.keys()


def test_the_lists_name_what_exists():
    """An allowlist naming a folder or file that is gone hides nothing, but reads as a rule that is not there."""
    assert all((ROOT / d).is_dir() for d in TOP_DIRS)
    assert all((ROOT / "src" / "cadagent" / f).is_file() for f in PKG_FILES)
    assert all((ROOT / d).is_dir() for d in OVER_LIMIT)
    assert all((ROOT / "src" / "cadagent" / p).is_dir() for p in PACKAGES)


# --- each rule fails on a planted case, and says where the file goes -------------------------------------------------

def _plant(extra, base=None):
    return sorted((base or []) + extra)


def test_a_flat_test_file_is_sent_to_the_folder_of_the_package_it_imports(files):
    texts = {"tests/test_new_gate.py": "from cadagent.review.gates import relations\nfrom cadagent import project\n",
             "tests/test_new_cli.py": "from cadagent.cli import main\n",
             "tests/test_new_rule.py": "import yaml\n",
             "tests/webkit-new.test.mjs": "import x from '../src/cadagent/webkit/x.js';\n",
             "tests/website-new.test.mjs": ""}
    got = flat_test_problems(_plant(list(texts), files), read=lambda p: texts.get(p, ""))
    assert len(got) == 5, got
    want = {"test_new_gate.py": "tests/review/", "test_new_cli.py": "tests/cli/", "test_new_rule.py": "tests/repo/",
            "webkit-new.test.mjs": "tests/webkit/", "website-new.test.mjs": "tests/site/"}
    for name, folder in want.items():
        (line,) = [g for g in got if g.startswith(f"tests/{name}:")]
        assert f"git mv tests/{name} {folder}" in line, line
    assert flat_test_problems(["tests/__init__.py", "tests/README.md", "tests/conftest.py"]) == []


def test_the_main_subject_wins_over_a_helper_import():
    text = ("from cadagent.mechanical import fasteners\nfrom cadagent.review.gates import fasteners as g\n"
            "from cadagent.review import evidence\nimport cadagent.review.gates.verdict\n")
    assert domain_for("test_x.py", text) == "review"
    assert domain_for("test_x.py", "from cadagent.project import load_project\n") == "cli"
    assert domain_for("site-walls.mjs", "") == "site"
    # a package beats the CLI it is driven through; with no package import, a test of the same first word decides
    assert domain_for("test_x.py", "from cadagent.cli import main\nfrom cadagent.cli import x\n"
                                   "from cadagent.geometry import overhang_regions\n") == "geometry"
    assert domain_for("test_zebra_figures.py", "import subprocess\n",
                      ["tests/manufacturing/test_zebra_profiles.py"]) == "manufacturing"
    assert domain_for("test_zebra_figures.py", "import subprocess\n",
                      ["tests/manufacturing/test_zebra_a.py", "tests/review/test_zebra_b.py"]) == "repo"
    # `from cadagent import <pkg>` counts (review of #276): it is how test_geometry.py and test_formulas.py import
    assert domain_for("test_new.py", "from cadagent import geometry\n") == "geometry"
    assert domain_for("test_new.py", "from cadagent import formulas as fx\nfrom cadagent.thermal import fans\n"
                                     "from cadagent import formulas\n") == "formulas"
    assert domain_for("test_new.py", "from cadagent import MissingDependency\n") == "repo"
    # named after what it tests: a package, a top-level module, a module inside a package
    assert domain_for("test_formulas.py", "from cadagent.thermal import fans\n") == "formulas"
    assert domain_for("test_cli.py", "from cadagent.publish import serve\n") == "cli"
    assert domain_for("test_holes.py", "from cadagent.publish import report\nfrom cadagent.publish import x\n") == \
        "mechanical"
    # a subpackage with its own test folder gets the nested folder, by import or by a test of the same first word
    nested = ["tests/simulation/explore/test_explore_design.py", "tests/simulation/test_fea.py"]
    assert domain_for("test_new.py", "from cadagent.simulation.explore import design\n", nested) == \
        "simulation/explore"
    assert domain_for("test_new.py", "from cadagent.simulation import fea\n", nested) == "simulation"
    assert domain_for("test_explore_new.py", "import json\n", nested) == "simulation/explore"


def test_an_unknown_or_undocumented_tests_folder_is_refused(files):
    got = folder_problems(_plant(["tests/misc/test_a.py", "tests/review/gates/test_b.py",
                                       "tests/review/nosuch/test_c.py", "tests/thermal/test_d.py"],
                                      [f for f in files if not f.startswith("tests/thermal/")]))
    assert any(g.startswith("tests/misc/: tests/ holds one folder per") for g in got), got
    assert any(g.startswith("tests/review/nosuch/: a nested test folder mirrors a subpackage") for g in got), got
    assert any(g.startswith("tests/review/gates/: add tests/review/gates/README.md") for g in got), got
    assert any(g.startswith("tests/thermal/: add tests/thermal/__init__.py") for g in got), got
    assert not any(g.startswith("tests/review/gates/: a nested") for g in got), "review/gates is a real subpackage"


def test_a_new_top_level_folder_is_refused(files):
    got = top_dir_problems(_plant(["scripts/run.sh", "evals/job.yaml"], files))
    assert [g.split(":")[0] for g in got] == ["evals/", "scripts/"]
    assert "src/cadagent/<domain>/" in got[0] and "tests/<domain>/" in got[0]


def test_a_new_file_at_the_top_of_src_is_refused(files):
    got = src_problems(_plant(["src/cadagent/bearings.py", "src/helpers.py", "src/cadagent/mechanical/new.py"], files))
    assert [g.split(":")[0] for g in got] == ["src/cadagent/bearings.py", "src/helpers.py"]
    assert "src/cadagent/<domain>/" in got[0] and "docs/areas.yaml" in got[0]


def test_a_folder_over_the_limit_is_told_to_split_and_the_list_only_shrinks(files):
    crowd = [f"lessons/printing/note-{i}.md" for i in range(CLUTTER_LIMIT + 1)]
    got = clutter_problems(_plant(crowd, files))
    assert len(got) == 1 and got[0].startswith(f"lessons/printing/ holds {CLUTTER_LIMIT + 1} files"), got
    assert "only shrinks" in got[0]
    assert clutter_problems(_plant(crowd[:CLUTTER_LIMIT], files)) == []
    thinned = [f for f in files if not f.startswith("tools/") or f.count("/") > 1]
    assert clutter_problems(thinned) == ["tools/ is at or under 20 files now: take it off OVER_LIMIT in "
                                         "tests/repo/test_layout.py"]
    vendored = [f"vendor/x/f{i}.py" for i in range(50)] + [f"docs/img/x/f{i}.svg" for i in range(50)]
    assert clutter_problems(_plant(vendored, files)) == []
