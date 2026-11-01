"""Old module paths, kept importing after the move into domain packages (v0.5.0, #114).

``import cadagent.fea``, ``from cadagent.fea import X`` (private names too), ``from cadagent import fea``,
``cadagent.fea`` after ``import cadagent``, ``importlib.import_module("cadagent.fea")`` and
``monkeypatch.setattr("cadagent.fea.X", ...)`` all give the module now at ``cadagent.simulation.fea``: the same
object, not a copy, so patching a name through either path reaches the code, and module state is shared. A moved
package takes its submodules with it: ``cadagent.gates.motion`` is ``cadagent.review.gates.motion``. The first import
of an old path warns (DeprecationWarning) with the new one, reported at the line that imported it, and says to move the
import (the table below, or docs/toolkit.md, Package layout).

When the old paths go: not yet. They stay until a release whose CHANGELOG announces their removal at least one minor
release ahead, under **Projects must change** (announced in vX.Y.0, removed no earlier than vX.(Y+1).0), and
``REMOVED_IN`` then names that release, so the warning does too. Downstream projects hash their source folders in
evidence receipts, so moving an import changes a receipt: a project needs the warning to plan that. Up to v0.8.0 this
said v0.7.0, which shipped with every old path. ``tests/test_package_layout.py`` pins the table, so a path cannot go
unannounced.

Two published modules became packages and keep their paths, so they need nothing here: ``cadagent.geometry`` (the
shared CAD helpers) and ``cadagent.review`` (the review workbench, now also the review domain's package).

Replacing a *whole module* through its old path does not reach cad-agent's own code, which imports the new paths:
after ``monkeypatch.setitem(sys.modules, "cadagent.report", fake)`` or ``monkeypatch.setattr(cadagent, "report",
fake)``, ``cadagent.mechanical.holes`` still uses the real ``cadagent.publish.report``. To replace a whole module (to
fake an optional one in a test, say), replace it at its new path: ``sys.modules["cadagent.publish.report"]``.

Importing by hand also needs the new path. The finder puts the real module into ``sys.modules`` in place of the one
the import machinery made, so the ``find_spec`` → ``module_from_spec`` → ``exec_module`` recipe leaves the caller
holding an empty module, and ``importlib.util.LazyLoader`` refuses the swap (``ValueError``). Every import statement,
``importlib.import_module`` and ``__import__`` get the real module.

``python -m cadagent.<old>`` (the gate worker was ``python -m cadagent.gates.run`` in v0.4) warns and runs the module
at its new path, as ``python -m <new>`` would.

One finder instead of a shim file per module, so the package's top level stays as tidy as the move made it. It sits
first in ``sys.meta_path``: an old package's submodule (``cadagent.gates.motion``) is looked up in the real package's
folder, where the standard finder would find the file and load a second copy under the old name. Importing an old
package also puts each of its submodules into ``sys.modules`` under its old name, so a finder that a later tool puts
in front of this one cannot load such a copy either (it costs 10-30 ms on the deprecated path only, and imports no
optional dependency). It also keeps a leftover ``gates/__pycache__/`` from a checkout before the move from importing
as an empty namespace package.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import os
import pkgutil
import sys
import warnings

MOVED = {                                     # old name under cadagent -> the module or package now
    # mechanical
    "holes": "cadagent.mechanical.holes",
    "fasteners": "cadagent.mechanical.fasteners",
    "mcmaster": "cadagent.mechanical.mcmaster",
    "connectors": "cadagent.mechanical.connectors",
    "markings": "cadagent.mechanical.markings",
    "compliant": "cadagent.mechanical.compliant",
    "motion_trace": "cadagent.mechanical.motion_trace",
    # manufacturing
    "slicer": "cadagent.manufacturing.slicer",
    "mesh3mf": "cadagent.manufacturing.mesh3mf",
    # thermal
    "heatsink": "cadagent.thermal.heatsink",
    # simulation
    "fea": "cadagent.simulation.fea",
    "cfd": "cadagent.simulation.cfd",
    "topopt": "cadagent.simulation.topopt",
    "explore": "cadagent.simulation.explore",
    "robot": "cadagent.simulation.robot",
    "simviz": "cadagent.simulation.simviz",
    "simreport": "cadagent.simulation.simreport",
    # electrical
    "pcb": "cadagent.electrical.pcb",
    "pcb_routing": "cadagent.electrical.pcb_routing",
    # review (practice: design process, review and evidence)
    "gates": "cadagent.review.gates",
    "dossier": "cadagent.review.dossier",
    "packet": "cadagent.review.packet",
    "evidence": "cadagent.review.evidence",
    # publish (practice: publishing)
    "report": "cadagent.publish.report",
    "htmlreport": "cadagent.publish.htmlreport",
    "site": "cadagent.publish.site",
    "site_review": "cadagent.publish.site_review",
    "view": "cadagent.publish.view",
    "serve": "cadagent.publish.serve",
    "release": "cadagent.publish.release",
    "render": "cadagent.publish.render",
    "dotsvg": "cadagent.publish.dotsvg",
}
REMOVED_IN = None   # the release that removes the old paths, once a CHANGELOG has announced it a minor release ahead
PACKAGE_LAYOUT = "docs/toolkit.md, Package layout"     # where the warning sends a project for every move


_IMPORTLIB = os.path.dirname(importlib.__file__) + os.sep
_SHIM = {os.path.abspath(__file__), os.path.join(os.path.dirname(os.path.abspath(__file__)), "__init__.py")}


def _importer_stacklevel() -> int:
    """The ``stacklevel`` that makes a warning raised in this module's caller name the line that asked for the import.

    Walks out past importlib (its ``_bootstrap`` frames, and ``import_module``, which ``from cadagent import x``,
    ``cadagent.x`` and string-path monkeypatching go through) and past this shim (``cadagent/__init__.py``'s
    ``__getattr__``). Counts as ``warnings`` does: it skips importlib's ``_bootstrap`` frames itself, so those add no
    level. Plain ``stacklevel=2`` named ``importlib/__init__.py`` for three of the import forms, and Python's default
    filters show a DeprecationWarning only when it names ``__main__``, so a script never saw it."""
    try:
        frame = sys._getframe(2)                  # 1 is the warn() caller (exec_module), 2 the frame it was called from
    except ValueError:                            # no Python caller (exec_module called from C, at exit say)
        return 2
    level = 2
    while frame is not None:
        name = frame.f_code.co_filename
        internal = "importlib" in name and "_bootstrap" in name
        if not (internal or name.startswith(_IMPORTLIB) or os.path.abspath(name) in _SHIM):
            return level
        if not internal:
            level += 1
        frame = frame.f_back
    return 2


def new_name(fullname: str):
    """The current path for an old one (``cadagent.gates.motion`` -> ``cadagent.review.gates.motion``), else None."""
    if not fullname.startswith("cadagent."):
        return None
    head, dot, rest = fullname[len("cadagent."):].partition(".")
    return MOVED[head] + dot + rest if head in MOVED else None


def _message(old: str, new: str) -> str:
    when = (f"the old path goes in v{REMOVED_IN}" if REMOVED_IN else
            "the old path stays until a release that the CHANGELOG announces a minor release ahead")
    return f"{old} moved to {new}: import it from there (every move: {PACKAGE_LAYOUT}); {when}"


def _alias_submodules(old: str, package) -> None:
    """Every submodule of a moved package under its old name too (``cadagent.gates.motion``), so no finder in front
    of this one can load a second copy from the package's folder. Best effort: a submodule that fails to import is
    left out, and importing it later raises its own error. Skipped while Python locates a ``python -m`` module
    (``sys.argv[0]`` is ``"-m"`` then): runpy imports the parent first and would warn that the module it is about to
    run was imported already."""
    if sys.argv[:1] == ["-m"]:
        return
    for info in pkgutil.walk_packages(package.__path__, package.__name__ + ".", onerror=lambda name: None):
        try:
            sys.modules.setdefault(old + info.name[len(package.__name__):], importlib.import_module(info.name))
        except Exception:                         # noqa: BLE001 - see the docstring
            continue


class _MovedFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolves ``cadagent.<old>`` (and ``cadagent.<old package>.<module>``) to the module at its new path."""

    def find_spec(self, fullname, path=None, target=None):
        new = new_name(fullname)
        if new is None:
            return None
        # The real file as the origin, so find_spec(old).origin names it before the first import too, and a moved
        # package's folders, so it reads as a package (runpy, pkgutil). Finding the new module's spec imports only its
        # parent package, not the module. No real module, no spec: the import fails as for any missing module.
        real = importlib.util.find_spec(new)
        if real is None:
            return None
        spec = importlib.util.spec_from_loader(fullname, self, origin=real.origin,
                                               is_package=real.submodule_search_locations is not None)
        if real.submodule_search_locations is not None:
            spec.submodule_search_locations = list(real.submodule_search_locations)
        return spec

    def is_package(self, fullname):
        real = importlib.util.find_spec(new_name(fullname))
        return real is not None and real.submodule_search_locations is not None

    def get_code(self, fullname):
        """For ``python -m cadagent.<old>``: runpy runs this code in ``__main__``. It warns from there, where Python's
        default filters show a DeprecationWarning, then runs the new module's code in the same namespace under the
        new module's spec, as ``python -m <new>`` would: its relative imports, usage line and exit status are the new
        module's. runpy has imported the old parent package by then; that warning names runpy, so it stays hidden."""
        new = new_name(fullname)
        source = (f"import importlib.util as _u, warnings as _w; _w.warn({_message(fullname, new)!r}, "
                  f"DeprecationWarning, stacklevel=1)\n"
                  f"__spec__ = _u.find_spec({new!r}); __package__ = __spec__.parent; __loader__ = __spec__.loader\n"
                  f"__file__ = __spec__.origin; __cached__ = __spec__.cached; del _u, _w\n"
                  f"exec(__spec__.loader.get_code({new!r}), globals())\n")
        return compile(source, f"<python -m {fullname}>", "exec")

    def create_module(self, spec):
        return None                               # a throwaway module: exec_module puts the real one in its place

    def exec_module(self, module):
        old = module.__name__
        new = new_name(old)
        warnings.warn(_message(old, new), DeprecationWarning, stacklevel=_importer_stacklevel())
        # The import machinery hands back whatever sys.modules holds for the old name once exec_module returns, and
        # binds that as the parent's attribute. Swapping here (instead of returning the real module from
        # create_module) keeps the real module's own __spec__: the machinery sets __spec__ on the module it is
        # given, so the real one used to end up with the shim's spec (no origin; reload renamed it).
        real = sys.modules[old] = importlib.import_module(new)
        if hasattr(real, "__path__"):
            _alias_submodules(old, real)


def _ours(finder) -> bool:
    """A finder this module installed, including one from before an ``importlib.reload`` of it (another class)."""
    kind = type(finder)
    return kind.__module__ == __name__ and kind.__qualname__ == "_MovedFinder"


def install() -> None:
    """Puts the finder first in ``sys.meta_path`` (see the module docstring). Once: after a reload of this module the
    new finder takes the old one's place instead of joining it."""
    for i, finder in enumerate(sys.meta_path):
        if _ours(finder):
            sys.meta_path[i] = _MovedFinder()
            return
    sys.meta_path.insert(0, _MovedFinder())
