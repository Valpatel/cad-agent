"""CAD design verification and review reports for printed-part projects.

A CAD project adopts this toolkit by following one contract (full description
and a worked example in ``docs/toolkit.md``):

* ``cad-agent.yaml`` at the project root carries a
  ``cad:`` section (``cadagent.project.load_project``): name, title, revision,
  the ordered build ``steps`` (scripts run with the project's own python), the
  parts file, the project-specific ``checks``, the printer bed, packaging and
  the pages whose local links must resolve.
* The build writes one STL + 3MF (print orientation) and one STEP (assembly
  coordinates) per printable part into ``exports/``, plus a parts file
  (default ``exports/geometry-checks.json``) mapping each part to
  ``{cad_valid, solid_count, watertight, print_bounds_mm, ...}``.
* Every project-specific check writes ``exports/<name>.json`` with a top-level
  boolean ``pass`` (or the key named by ``pass_key``). A missing file, a
  missing key or a non-boolean value is a failure, never a pass.
* CAD checks never claim physical fit: reports always record
  ``physical_fit_verified`` as false, and ``slicer_run`` as false unless
  ``cad-agent slice`` has sliced the current 3MF files (sha256 checked).

Heavy dependencies (cadquery/OCP, trimesh, vtk, PIL) are imported inside the
functions that need them; a missing one raises ``MissingDependency`` naming the
``cad`` extra instead of quietly skipping work.

``cadagent.__version__`` is the toolkit's version, for a record of what made a
result (see ``_version()``).
"""

import importlib
import os
import re

from cadagent._deps import MissingDependency
from cadagent import _moved

_moved.install()          # old module paths (cadagent.fea, ...) keep importing; see cadagent._moved

__all__ = ["MissingDependency"]

_PROJECT_TABLE = re.compile(r"^\[project\][ \t]*$(.*?)(?=^\[|\Z)", re.M | re.S)


def _pyproject_version(path: str):
    """The ``[project]`` table's version in the pyproject.toml at ``path`` when that table names ``cad-agent``, else
    None (no file, another project's file, no version line). A regex, not tomllib, which Python 3.10 lacks: the
    lines it reads are the ones ``tools/cut_release.py`` writes."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    table = _PROJECT_TABLE.search(text)
    if not table or not re.search(r'^name\s*=\s*"cad-agent"\s*$', table.group(1), re.M):
        return None
    m = re.search(r'^version\s*=\s*"([^"\s]+)"\s*$', table.group(1), re.M)
    return m.group(1) if m else None


def _version() -> str:
    """The version of the cad-agent these files are.

    A source tree first: ``src/cadagent`` beside the checkout's ``pyproject.toml`` (a checkout run with
    ``PYTHONPATH=src``, or an editable install). Its pyproject.toml is what ``tools/cut_release.py`` bumps, and the
    installed metadata can be stale there: an editable install keeps the version it was installed at, and a venv
    can hold another checkout's install while ``PYTHONPATH`` points here. Otherwise the installed metadata
    (``importlib.metadata``), when that distribution's ``cadagent/__init__.py`` is this file (a wheel install).
    Else ``0+unknown``, rather than another copy's version. Reads one small file at most; imports nothing heavy."""
    here = os.path.dirname(os.path.abspath(__file__))
    found = _pyproject_version(os.path.join(here, os.pardir, os.pardir, "pyproject.toml"))
    if found:
        return found
    try:
        from importlib import metadata
        dist = metadata.distribution("cad-agent")
        if os.path.realpath(str(dist.locate_file("cadagent/__init__.py"))) == os.path.realpath(__file__):
            return dist.version
    except Exception:                             # noqa: BLE001 - not installed, or metadata we cannot read
        pass
    return "0+unknown"


__version__ = _version()


def __getattr__(name):
    """``cadagent.fea`` after a bare ``import cadagent`` (the attribute appears once the module is imported)."""
    if name in _moved.MOVED:
        return importlib.import_module(f"cadagent.{name}")
    raise AttributeError(f"module 'cadagent' has no attribute {name!r}")
