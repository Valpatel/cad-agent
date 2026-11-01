"""The package layout (#114): modules live in packages by domain (docs/areas.yaml; tests/test_package_areas.py keeps the
two in step), old paths keep importing, the top level stays tidy."""
import importlib
import importlib.util
import pkgutil
import re
import subprocess
import sys
import types
import warnings
from pathlib import Path

import pytest

import cadagent
from cadagent import _moved
from cadagent._moved import MOVED

PKG = Path(cadagent.__file__).parent
TOP_MODULES = {"__init__", "_deps", "_moved", "agentkit", "cli", "links", "package", "project"}
DOMAINS = {"mechanical", "manufacturing", "thermal", "simulation", "electrical", "review", "publish"}
PACKAGES = DOMAINS | {"geometry", "formulas", "webkit"}  # shared core: CAD helpers, equations; webkit: browser files
# Paths of the job layout (#121 before the owner chose domains): never on dev, so nothing keeps them importing.
NEVER_SHIPPED = ["cadagent.sim", "cadagent.make", "cadagent.geometry.holes", "cadagent.geometry.fasteners",
                 "cadagent.geometry.connectors", "cadagent.geometry.markings", "cadagent.publish.packet",
                 "cadagent.publish.review"]


def _leftover(folder: Path) -> bool:
    """A folder git left behind: it holds only ``__pycache__`` (a checkout from before the move removed its files)."""
    files = (f for f in folder.rglob("*") if f.is_file())
    return folder.is_dir() and all("__pycache__" in f.relative_to(folder).parts for f in files)


def test_no_folder_is_left_over_from_before_the_move():
    """After pulling the move, git leaves compliant/, dossier/, explore/ and gates/ holding their __pycache__. The old
    paths still import (the finder claims them first), but the folder is clutter, and a leftover sim/ or make/ (this
    PR's first layout) imports as an empty namespace package."""
    leftovers = sorted(p for p in PKG.iterdir() if _leftover(p))
    assert not leftovers, "\n".join(
        f"{p.relative_to(PKG.parents[1])}/ holds only __pycache__, left by a checkout from before the move (#121): "
        f"delete it (rm -r {p.relative_to(PKG.parents[1])})" for p in leftovers)


def test_top_level_stays_tidy():
    modules = {p.stem for p in PKG.glob("*.py")}
    packages = {p.name for p in PKG.iterdir()
                if p.is_dir() and not p.name.startswith(("_", ".")) and not _leftover(p)}   # leftovers: the test above
    assert modules == TOP_MODULES, (
        f"new top-level modules {sorted(modules - TOP_MODULES)}: put them in the package for their domain "
        f"({', '.join(sorted(DOMAINS))}; see docs/areas.yaml), or agree a new shared module and add it here")
    assert packages == PACKAGES, f"packages changed: {sorted(packages ^ PACKAGES)} (update the README map too)"


@pytest.mark.parametrize("old,new", sorted(MOVED.items()))
def test_old_paths_are_the_same_module(old, new):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        module = importlib.import_module(f"cadagent.{old}")
    assert module is importlib.import_module(new)
    assert getattr(cadagent, old) is module
    assert module.__name__ == new and module.__spec__.name == new, "the old path replaced the real module's spec"
    assert not (PKG / f"{old}.py").exists(), f"cadagent/{old}.py is back next to its new home {new}"
    assert not (PKG / old).is_dir() or _leftover(PKG / old), (
        f"cadagent/{old}/ is back next to its new home {new}: move its files to {new.replace('.', '/')}/")


def _submodules(package):
    return sorted(m.name for m in pkgutil.walk_packages(package.__path__, package.__name__ + "."))


def _is_package(name):
    """Whether ``name`` is a package, without importing it: a missing target gives False here and fails
    test_old_paths_are_the_same_module, instead of stopping collection."""
    spec = importlib.util.find_spec(name)
    return spec is not None and spec.submodule_search_locations is not None


MOVED_PACKAGES = sorted(old for old, new in MOVED.items() if _is_package(new))


def test_the_moved_packages_are_the_published_ones():
    assert MOVED_PACKAGES == ["compliant", "dossier", "explore", "gates"]


# Every old path v0.5.0 published (#114). Downstream projects hash their source folders in evidence receipts, so moving
# an import changes a receipt; an old path goes only in the release _moved.REMOVED_IN names, after a CHANGELOG entry
# has announced it at least one minor release ahead.
PUBLISHED_OLD_PATHS = {
    "holes", "fasteners", "mcmaster", "connectors", "markings", "compliant", "motion_trace", "slicer", "mesh3mf",
    "heatsink", "fea", "cfd", "topopt", "explore", "robot", "simviz", "simreport", "pcb", "pcb_routing", "gates",
    "dossier", "packet", "evidence", "report", "htmlreport", "site", "site_review", "view", "serve", "release",
    "render", "dotsvg"}
ROOT = PKG.parents[1]


def _release(text: str):
    return tuple(int(p) for p in text.split("."))


def _announced(changelog: str, removed_in: str) -> list:
    """The released entries whose **Projects must change** block has a bullet saying the old paths go in
    v<removed_in>, as release tuples."""
    out = []
    for v, body in re.findall(r"^## v([0-9.]+) \([0-9-]+\)\n(.*?)(?=^## |\Z)", changelog, re.M | re.S):
        block = re.search(r"^\*\*Projects must change:?\*\*:?[ \t]*\n(.*?)(?=^\*\*[^*\n]+\*\*|\Z)", body, re.M | re.S)
        bullet = rf"^- [^\n]*\bold (?:import |module )?paths\b[^\n]*\bv{re.escape(removed_in)}\b"
        if block and re.search(bullet, block.group(1), re.M):
            out.append(_release(v))
    return out


def test_the_announcement_check_reads_a_projects_must_change_bullet():
    log = ("## Unreleased\n\n## v0.10.0 (2027-01-02)\n\n**New**\n- the old paths go in v0.11.0 (not here)\n\n"
           "**Projects must change**\n- Move imports: the old import paths go in v0.11.0.\n\n"
           "## v0.9.0 (2026-12-01)\n\n**Projects must change:**\n- A folder threshold for v0.11.0 holds.\n")
    assert _announced(log, "0.11.0") == [(0, 10, 0)]
    assert _announced(log, "0.12.0") == []
    assert _announced(log.replace("**Projects must change**\n- Move", "**Fixed**\n- Move"), "0.11.0") == []


def test_no_old_path_goes_unannounced():
    current = _release(cadagent.__version__.split("+")[0])
    removed = _release(_moved.REMOVED_IN) if _moved.REMOVED_IN else None
    if removed is None or current < removed:
        assert set(MOVED) == PUBLISHED_OLD_PATHS, (
            "an old import path was removed or added without an announced release: set _moved.REMOVED_IN and "
            "announce it in the CHANGELOG at least one minor release ahead")
    if removed is not None:
        assert removed > current, f"REMOVED_IN names v{_moved.REMOVED_IN}, which has shipped: update the plan"
        announced = _announced((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), _moved.REMOVED_IN)
        assert any(a[:2] < removed[:2] for a in announced), (
            f"no released CHANGELOG entry before v{removed[0]}.{removed[1]} announces the removal in "
            f"v{_moved.REMOVED_IN} under **Projects must change**")


def test_the_warning_says_to_move_the_import_and_when_the_old_path_goes():
    msg = _moved._message("cadagent.fea", "cadagent.simulation.fea")
    assert msg.startswith("cadagent.fea moved to cadagent.simulation.fea: import it from there")
    assert "docs/toolkit.md, Package layout" in msg
    assert "### Package layout" in (ROOT / "docs" / "toolkit.md").read_text(encoding="utf-8")
    if _moved.REMOVED_IN is None:
        assert "a release that the CHANGELOG announces a minor release ahead" in msg
        assert not re.search(r"v[0-9]+\.[0-9]", msg)                 # names no release, and none that has shipped


STATES_THE_PLAN = [PKG / d / "__init__.py" for d in sorted(DOMAINS)] + [
    PKG / "README.md", PKG / "_moved.py", ROOT / "docs" / "toolkit.md", ROOT / "docs" / "areas.yaml",
    ROOT / "tests" / "test_package_areas.py", ROOT / "tests" / "test_areas.py"]


@pytest.mark.parametrize("path", STATES_THE_PLAN, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_page_states_the_same_plan_for_the_old_paths(path):
    """v0.7.0 shipped with every old path while these still said it removed them (#144)."""
    text = " ".join(path.read_text(encoding="utf-8").split())
    if _moved.REMOVED_IN is None:
        assert "announces a minor release ahead" in text or "at least one minor release ahead" in text, path
    else:
        assert f"v{_moved.REMOVED_IN}" in text, path
    current = _release(cadagent.__version__.split("+")[0])
    for v in re.findall(r"(?:until|goes in|go in|removed in) v([0-9]+\.[0-9]+\.[0-9]+)", text, re.I):
        assert _release(v) > current, f"{path.name} says the old paths go in v{v}, which has shipped"


@pytest.mark.parametrize("old", MOVED_PACKAGES)
def test_an_old_package_path_takes_its_submodules_with_it(old):
    """cadagent.gates.motion is cadagent.review.gates.motion: the same object, through every submodule."""
    new = MOVED[old]
    subs = _submodules(importlib.import_module(new))
    assert subs, f"{new} has no submodules"
    for real in subs:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            module = importlib.import_module(f"cadagent.{old}" + real[len(new):])
        assert module is importlib.import_module(real) and module.__name__ == real
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"cadagent.{old}.no_such_module")


def test_modules_that_became_packages_keep_their_paths_without_a_warning():
    """cadagent.geometry and cadagent.review were published as modules; each is now its package's __init__, the
    same module as before at the same path, so it does not warn."""
    code = """
import warnings
warnings.simplefilter("error")
from cadagent.geometry import export_step, solid_report
from cadagent.review import review_html, REVIEW_CSS
import cadagent.geometry, cadagent.review
assert cadagent.geometry.__name__ == "cadagent.geometry" and cadagent.review.__name__ == "cadagent.review"
assert cadagent.geometry.__path__ and cadagent.review.__path__
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0, out.stderr
    assert "geometry" not in MOVED and "review" not in MOVED


@pytest.mark.parametrize("name", NEVER_SHIPPED)
def test_the_job_layout_paths_are_gone(name):
    assert importlib.util.find_spec(name.rsplit(".", 1)[0]) is not None
    folder = PKG.parent.joinpath(*name.split("."))
    assert importlib.util.find_spec(name) is None, (
        f"{name} still resolves: {folder.relative_to(PKG.parents[1])}/ holds only __pycache__ from a checkout before "
        f"the move (delete it)" if _leftover(folder) else
        f"{name} still resolves: a folder or module under src/cadagent, or a shim for a path that never shipped")


# Each form that reaches a moved module, as the last line of a script. dotsvg needs only the standard library.
IMPORT_FORMS = {
    "import": "import cadagent.dotsvg",
    "import as": "import cadagent.dotsvg as dot",
    "from module import name": "from cadagent.dotsvg import parse_dot",
    "from package import module": "from cadagent import dotsvg",
    "attribute": "import cadagent\ncadagent.dotsvg",
    "import_module": "import importlib\nimportlib.import_module('cadagent.dotsvg')",
    "__import__": "__import__('cadagent.dotsvg')",
    "new path loaded first": "import cadagent.publish.dotsvg\nfrom cadagent import dotsvg",
}
# The same through a moved package (cadagent.gates is now cadagent.review.gates): each line, the warnings it raises.
# Importing the old package brings its submodules under their old names, so its one warning covers them.
PACKAGE_FORMS = {
    "import": ("import cadagent.gates.verdict", ["cadagent.gates"]),
    "from module import name": ("from cadagent.gates.verdict import SCHEMA", ["cadagent.gates"]),
    "from package import module": ("from cadagent.gates import verdict", ["cadagent.gates"]),
    "import_module": ("import importlib\nimportlib.import_module('cadagent.gates.verdict')", ["cadagent.gates"]),
    "new path loaded first": ("import cadagent.review.gates.verdict\nimport cadagent.gates.verdict",
                              ["cadagent.gates"]),
}


@pytest.mark.parametrize("form", IMPORT_FORMS)
def test_old_path_warns_at_the_importing_line(form, tmp_path):
    """Run as a plain script with Python's default warning filters, which show a DeprecationWarning only when it names
    __main__: a warning reported at importlib's own line would not be shown at all."""
    script = tmp_path / "uses_old_path.py"
    script.write_text("# a project script\n" + IMPORT_FORMS[form] + "\n")
    line = IMPORT_FORMS[form].count("\n") + 2
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=tmp_path,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0, out.stderr
    expected = f"{script}:{line}: DeprecationWarning: cadagent.dotsvg moved to cadagent.publish.dotsvg"
    assert out.stderr.count(expected) == 1, out.stderr


@pytest.mark.parametrize("form", PACKAGE_FORMS)
def test_an_old_package_path_warns_at_the_importing_line(form, tmp_path):
    code, warned = PACKAGE_FORMS[form]
    script = tmp_path / "uses_old_package_path.py"
    script.write_text("# a project script\n" + code + "\n")
    line = code.count("\n") + 2
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=tmp_path,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0, out.stderr
    for old in warned:
        expected = f"{script}:{line}: DeprecationWarning: {old} moved to {_moved.new_name(old)}"
        assert out.stderr.count(expected) == 1, out.stderr
    assert out.stderr.count("DeprecationWarning") == len(warned), out.stderr


# python -m through an old path, and the same through the new one: (old, new, exit status). The gate worker was
# `python -m cadagent.gates.run` in v0.4's docs/gates.md; with no arguments it prints its usage line.
PYTHON_M = [("cadagent.gates.run", "cadagent.review.gates.run", 2),
            ("cadagent.dotsvg", "cadagent.publish.dotsvg", 0),
            ("cadagent.gates", "cadagent.review.gates", 1)]


@pytest.mark.parametrize("old,new,status", PYTHON_M)
def test_python_m_through_an_old_path_runs_the_new_module(old, new, status, tmp_path):
    """As on dev before the move, with one DeprecationWarning that Python's default filters show. A package gives
    runpy's own error, naming the path that was asked for."""
    env = {"PYTHONPATH": str(PKG.parent), "PATH": ""}
    run = {name: subprocess.run([sys.executable, "-m", name], capture_output=True, text=True, cwd=tmp_path, env=env)
           for name in (old, new)}
    assert run[old].returncode == run[new].returncode == status, run[old].stderr
    assert run[old].stdout == run[new].stdout
    warning = f"<python -m {old}>:1: DeprecationWarning: {_moved._message(old, new)}"
    rest = [line for line in run[old].stderr.splitlines() if line != warning]
    if status == 1:
        assert f"'{old}' is a package and cannot be directly executed" in run[old].stderr, run[old].stderr
        assert rest == [line.replace(new, old) for line in run[new].stderr.splitlines()]
    else:
        assert run[old].stderr.count(warning) == 1, run[old].stderr
        assert rest == run[new].stderr.splitlines(), run[old].stderr
        assert "RuntimeWarning" not in run[old].stderr


def test_an_old_package_brings_its_submodules_whatever_finder_comes_first():
    """Importing cadagent.gates puts every submodule into sys.modules under its old name too, so a finder another
    tool puts in front of ours (one that resolves cadagent.* through the path finder, as instrumenting hooks do)
    cannot load a second copy from the package's folder."""
    leftovers = sorted(p.name for p in PKG.iterdir() if _leftover(p))
    assert not leftovers, (f"{', '.join(leftovers)}/ left over from before the move: a finder in front then "
                           "imports them as empty packages. Delete them first "
                           "(test_no_folder_is_left_over_from_before_the_move)")
    code = """
import importlib.abc, importlib.machinery, pkgutil, sys, warnings
warnings.simplefilter("ignore", DeprecationWarning)
import cadagent

class Front(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        return importlib.machinery.PathFinder.find_spec(name, path, target) if name.startswith("cadagent.") else None

sys.meta_path.insert(0, Front())
import cadagent.gates.motion
import cadagent.review.gates as real
assert sys.modules["cadagent.gates.motion"] is sys.modules["cadagent.review.gates.motion"]
for info in pkgutil.walk_packages(real.__path__, "cadagent.review.gates."):
    old = "cadagent.gates" + info.name[len("cadagent.review.gates"):]
    assert sys.modules[old] is sys.modules[info.name], old
modules = {id(m): m for m in list(sys.modules.values())}.values()   # an alias is the same object twice
files = [m.__file__ for m in modules if getattr(m, "__file__", None)]
assert len(files) == len(set(files)), "a file is behind two module objects"
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0, out.stderr


def test_reloading_the_shim_keeps_one_finder():
    code = """
import importlib, sys, warnings
warnings.simplefilter("ignore", DeprecationWarning)
import cadagent, cadagent._moved as moved
importlib.reload(moved)
moved.install()
mine = [f for f in sys.meta_path if type(f).__qualname__ == "_MovedFinder"]
assert len(mine) == 1 and isinstance(mine[0], moved._MovedFinder), sys.meta_path
import cadagent.dotsvg, cadagent.publish.dotsvg
assert cadagent.dotsvg is cadagent.publish.dotsvg
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0, out.stderr


def test_old_path_leaves_the_real_modules_spec_and_reload_alone():
    """The real module keeps its own spec, so find_spec has its file and reload re-runs it under its own name. In a
    fresh interpreter: reloading here would swap classes under the other tests."""
    code = """
import importlib, importlib.util, sys, warnings
warnings.simplefilter("ignore", DeprecationWarning)
import cadagent
assert importlib.util.find_spec("cadagent.dotsvg").origin.endswith("dotsvg.py"), "no file before the first import"
assert "cadagent.publish.dotsvg" not in sys.modules, "find_spec imported the module itself"
import cadagent.dotsvg
import cadagent.publish.dotsvg as real
assert real.__spec__.name == "cadagent.publish.dotsvg", real.__spec__.name
assert importlib.util.find_spec("cadagent.publish.dotsvg").origin.endswith("dotsvg.py")
assert importlib.util.find_spec("cadagent.dotsvg").origin.endswith("dotsvg.py")
real.parse_dot = None
again = importlib.reload(cadagent.dotsvg)
assert again is real and real.__name__ == "cadagent.publish.dotsvg" and real.__package__ == "cadagent.publish"
assert callable(real.parse_dot), "reload did not run the module again"
"""
    out = subprocess.run([sys.executable, "-W", "error::ImportWarning", "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0, out.stderr


def test_the_warning_survives_a_call_without_a_python_caller():
    """exec_module called from C (an atexit callback) has no frame two levels up; the stacklevel falls back."""
    code = """
import atexit, types, warnings, cadagent
from cadagent import _moved
warnings.simplefilter("ignore")
atexit.register(_moved._MovedFinder().exec_module, types.ModuleType("cadagent.dotsvg"))
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0 and "Error" not in out.stderr, out.stderr


def test_importing_by_hand_needs_the_new_path():
    """The documented limit (cadagent._moved): the finder swaps the real module into sys.modules, so the
    module_from_spec recipe leaves the caller an empty module and LazyLoader refuses the swap. Both work at the new
    path."""
    code = """
import importlib.util, sys, warnings
warnings.simplefilter("ignore", DeprecationWarning)
import cadagent

def by_hand(name, lazy=False):
    spec = importlib.util.find_spec(name)
    if lazy:
        spec.loader = importlib.util.LazyLoader(spec.loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

old = by_hand("cadagent.dotsvg")
assert not hasattr(old, "parse_dot") and sys.modules["cadagent.dotsvg"].parse_dot
del sys.modules["cadagent.dotsvg"], sys.modules["cadagent.publish.dotsvg"]
try:
    by_hand("cadagent.dotsvg", lazy=True).parse_dot
    raise SystemExit("LazyLoader accepted the swap: update the docstring in cadagent._moved")
except ValueError:
    pass
for key in ("cadagent.dotsvg", "cadagent.publish.dotsvg"):
    sys.modules.pop(key, None)
assert callable(by_hand("cadagent.publish.dotsvg").parse_dot)
del sys.modules["cadagent.publish.dotsvg"]
assert callable(by_hand("cadagent.publish.dotsvg", lazy=True).parse_dot)
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0, out.stderr


class _Reached(Exception):
    pass


def _fake_report():
    fake = types.ModuleType("fake_report")

    def load_parts(project):
        raise _Reached
    fake.load_parts = load_parts
    return fake


@pytest.mark.parametrize("how,reaches", [
    ("sys.modules, old path", False),
    ("package attribute, old path", False),
    ("sys.modules, new path", True),
])
def test_replacing_a_whole_module_reaches_internal_code_only_at_its_new_path(how, reaches, monkeypatch, tmp_path):
    """The documented limit (cadagent._moved, CHANGELOG): patching a *name* works through either path, but cad-agent's
    own code imports the new paths, so a whole module replaced at its old path is not seen. holes.current() imports
    load_parts from cadagent.publish.report when it runs; the stand-in project has no parts file, so the real one
    fails on that and the fake one raises _Reached."""
    from cadagent.mechanical import holes
    fake = _fake_report()
    if how == "sys.modules, old path":
        monkeypatch.setitem(sys.modules, "cadagent.report", fake)
    elif how == "package attribute, old path":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            monkeypatch.setattr(cadagent, "report", fake)
    else:
        monkeypatch.setitem(sys.modules, "cadagent.publish.report", fake)
    (tmp_path / "hole-checks.json").write_text("{}")
    project = types.SimpleNamespace(exports_dir=tmp_path)
    with pytest.raises(_Reached if reaches else AttributeError, match=None if reaches else "parts_file"):
        holes.current(project, "part")


def _all_modules():
    return sorted(m.name for m in pkgutil.walk_packages([str(PKG)], "cadagent.")
                  if ".webkit" not in m.name)


def test_every_module_imports_alone_without_old_paths():
    """Each module imported first in a fresh interpreter: catches import cycles that only bite in one order, and any
    internal import still using an old path (those raise here)."""
    failures = []
    for name in _all_modules():
        out = subprocess.run([sys.executable, "-W", "error:cadagent.:DeprecationWarning", "-c", f"import {name}"],
                             capture_output=True, text=True, env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
        if out.returncode:
            failures.append(f"{name}: {out.stderr.strip().splitlines()[-1]}")
    assert not failures, "\n".join(failures)


def test_no_internal_import_uses_an_old_path():
    """Every import in the package, at module level or inside a function, relative or absolute, resolved and checked
    against the moved table (lazy imports are invisible to the fresh-interpreter test above)."""
    import ast
    bad = []
    for path in PKG.rglob("*.py"):
        if "webkit" in path.parts:
            continue
        rel = path.relative_to(PKG.parent).with_suffix("")
        package = list(rel.parts[:-1])            # a module's package; for __init__.py, the package itself
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            targets = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = package[: len(package) - node.level + 1] if node.level else []
                mod = ".".join(base + ([node.module] if node.module else [])) if node.level else node.module
                targets = [mod] + [f"{mod}.{a.name}" for a in node.names]
            for t in targets:
                parts = (t or "").split(".")
                if len(parts) >= 2 and parts[0] == "cadagent" and parts[1] in MOVED:
                    bad.append(f"{path.relative_to(PKG.parent)}:{node.lineno}: {t}")
    assert not bad, "imports through old paths:\n" + "\n".join(sorted(set(bad)))


def test_every_internal_import_resolves():
    """Every module an internal import names (absolute or relative, at module level or lazy) exists: a relative import
    that climbs out of a package (``from ..project import``) silently changes meaning when the package moves."""
    import ast
    missing = []
    for path in PKG.rglob("*.py"):
        if "webkit" in path.parts:
            continue
        rel = path.relative_to(PKG.parent).with_suffix("")
        package = list(rel.parts[:-1])
        for node in ast.walk(ast.parse(path.read_text(), str(path))):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = package[: len(package) - node.level + 1] if node.level else []
                mods = [".".join(base + ([node.module] if node.module else [])) if node.level else node.module]
            else:
                continue
            for mod in mods:
                if mod.split(".")[0] == "cadagent" and importlib.util.find_spec(mod) is None:
                    missing.append(f"{path.relative_to(PKG.parent)}:{node.lineno}: {mod}")
    assert not missing, "imports of modules that do not exist:\n" + "\n".join(sorted(missing))
