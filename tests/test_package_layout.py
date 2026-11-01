"""The package layout (#114): modules live in packages by job, old paths keep importing, the top level stays tidy."""
import importlib
import pkgutil
import subprocess
import sys
import types
import warnings
from pathlib import Path

import pytest

import cadagent
from cadagent._moved import MOVED

PKG = Path(cadagent.__file__).parent
TOP_MODULES = {"__init__", "_deps", "_moved", "agentkit", "cli", "evidence", "links", "package", "project"}
PACKAGES = {"compliant", "dossier", "explore", "gates", "geometry", "make", "publish", "sim", "webkit"}


def test_top_level_stays_tidy():
    modules = {p.stem for p in PKG.glob("*.py")}
    packages = {p.name for p in PKG.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))}
    assert modules == TOP_MODULES, (
        f"new top-level modules {sorted(modules - TOP_MODULES)}: put them in the package for their job "
        f"(geometry, sim, make, publish, ...), or agree a new top-level module and add it here")
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


def test_old_path_leaves_the_real_modules_spec_and_reload_alone():
    """The real module keeps its own spec, so find_spec has its file and reload re-runs it under its own name. In a
    fresh interpreter: reloading here would swap classes under the other tests."""
    code = """
import importlib, importlib.util, warnings
warnings.simplefilter("ignore", DeprecationWarning)
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
    from cadagent.geometry import holes
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
