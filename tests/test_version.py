"""cadagent.__version__ (#144): the version of the files that run, from a checkout, an editable install or a wheel.

Each case runs in a fresh interpreter (``python -I``-like: an explicit PYTHONPATH and nothing else), because the
version is read once, at import.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import cadagent

PKG = Path(cadagent.__file__).resolve().parent
ROOT = PKG.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from ci_gates import parse_version  # noqa: E402  (the release gate's own reader of pyproject.toml)

HEAVY = {"numpy", "yaml", "cadquery", "OCP", "trimesh", "vtk", "matplotlib", "PIL", "gmsh", "skfem", "scipy"}


def _run(code: str, path: Path, cwd: Path) -> str:
    out = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True, cwd=cwd,
                         env={"PYTHONPATH": str(path), "PATH": ""})
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _bare_package(into: Path) -> Path:
    """The three files ``import cadagent`` reads, copied into ``into/cadagent``, with no pyproject.toml beside them."""
    dest = into / "cadagent"
    dest.mkdir(parents=True)
    for name in ("__init__.py", "_deps.py", "_moved.py"):
        shutil.copy(PKG / name, dest / name)
    return dest


def test_the_version_is_pyproject_tomls():
    """In this checkout (CI runs it as an editable install, these suites with PYTHONPATH=src): what cut_release.py
    bumps. An installed copy's metadata can be stale here, so it does not count."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert cadagent.__version__ == ".".join(map(str, parse_version(text)))


def test_a_checkout_on_the_path_reads_its_own_pyproject_and_imports_nothing_heavy(tmp_path):
    code = ("import sys, cadagent; print(cadagent.__version__); "
            f"print(sorted(set({sorted(HEAVY)!r}) & set(sys.modules)))")
    version, heavy = _run(code, ROOT / "src", tmp_path).splitlines()
    assert version == ".".join(map(str, parse_version((ROOT / "pyproject.toml").read_text(encoding="utf-8"))))
    assert heavy == "[]"
    assert _run("from cadagent import __version__; print(__version__)", ROOT / "src", tmp_path) == version


def test_a_wheel_install_reads_the_installed_metadata(tmp_path):
    """No pyproject.toml beside the package, and the cad-agent distribution on the path is the one holding these
    files: its version."""
    site = tmp_path / "site"
    _bare_package(site)
    info = site / "cad_agent-9.9.9.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: cad-agent\nVersion: 9.9.9\n", encoding="utf-8")
    (info / "RECORD").write_text("cadagent/__init__.py,,\n", encoding="utf-8")
    assert _run("import cadagent; print(cadagent.__version__)", site, tmp_path) == "9.9.9"


def test_a_copy_that_no_metadata_describes_is_unknown_not_another_installs_version(tmp_path):
    """A vendored copy of the package, while a cad-agent of another version is installed (this test venv may hold
    one installed from another checkout): that version is not this copy's."""
    _bare_package(tmp_path / "vendored")
    other = tmp_path / "other-site"
    info = other / "cad_agent-1.2.3.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: cad-agent\nVersion: 1.2.3\n", encoding="utf-8")
    path = f"{tmp_path / 'vendored'}:{other}"
    assert _run("import cadagent; print(cadagent.__version__)", Path(path), tmp_path) == "0+unknown"


@pytest.mark.parametrize("pyproject, expected", [
    ('[project]\nname = "my-robot"\nversion = "3.1.0"\n', "0+unknown"),                 # another project's file
    ('[tool.x]\nversion = "5"\n[project]\nname = "cad-agent"\nversion = "0.9.1"\n', "0.9.1"),
    ('[project]\nname = "cad-agent"\ndynamic = ["version"]\n', "0+unknown"),          # no version line to read
])
def test_only_cad_agents_own_project_table_counts(tmp_path, pyproject, expected):
    """A project that vendors src/cadagent into its own src/ has its own pyproject.toml two folders up."""
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    _bare_package(tmp_path / "src")
    assert _run("import cadagent; print(cadagent.__version__)", tmp_path / "src", tmp_path) == expected
