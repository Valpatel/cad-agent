"""The package layout (#114): modules live in packages by job, old paths keep importing, the top level stays tidy."""
import importlib
import pkgutil
import subprocess
import sys
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
    assert not (PKG / f"{old}.py").exists(), f"cadagent/{old}.py is back next to its new home {new}"


def test_old_path_warns_with_the_new_one():
    code = "import warnings; warnings.simplefilter('always'); import cadagent.fea"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert out.returncode == 0, out.stderr
    assert "cadagent.fea moved to cadagent.sim.fea" in out.stderr and "<string>:1" in out.stderr


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
        package = list(rel.parts[:-1]) if rel.name != "__init__" else list(rel.parts[:-1])
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
                if len(parts) >= 2 and parts[0] == "cadagent" and parts[1] in MOVED and (len(parts) == 2 or parts[1] != "geometry"):
                    bad.append(f"{path.relative_to(PKG.parent)}:{node.lineno}: {t}")
    assert not bad, "imports through old paths:\n" + "\n".join(sorted(set(bad)))
