"""Old module paths, kept importing after the move into packages (v0.5.0, #114).

``import cadagent.fea``, ``from cadagent.fea import X`` (private names too), ``from cadagent import fea``,
``cadagent.fea`` after ``import cadagent``, ``importlib.import_module("cadagent.fea")`` and
``monkeypatch.setattr("cadagent.fea.X", ...)`` all give the module now at ``cadagent.sim.fea``: the same object, not a
copy, so patching a name through either path reaches the code, and module state is shared. The first import of an
old path warns (DeprecationWarning) with the new one, reported at the line that imported it. Old paths are removed in
v0.7.0; move imports before then (the table below, or CHANGELOG.md).

Replacing a *whole module* through its old path does not reach cad-agent's own code, which imports the new paths:
after ``monkeypatch.setitem(sys.modules, "cadagent.report", fake)`` or ``monkeypatch.setattr(cadagent, "report",
fake)``, ``cadagent.geometry.holes`` still uses the real ``cadagent.publish.report``. To replace a whole module (to fake
an optional one in a test, say), replace it at its new path: ``sys.modules["cadagent.publish.report"]``.

Importing by hand also needs the new path. The finder puts the real module into ``sys.modules`` in place of the one
the import machinery made, so the ``find_spec`` → ``module_from_spec`` → ``exec_module`` recipe leaves the caller
holding an empty module, and ``importlib.util.LazyLoader`` refuses the swap (``ValueError``). Every import statement,
``importlib.import_module`` and ``__import__`` get the real module.

One finder instead of a shim file per module, so the package's top level stays as tidy as the move made it.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import os
import sys
import warnings

MOVED = {
    "holes": "cadagent.geometry.holes",
    "fasteners": "cadagent.geometry.fasteners",
    "connectors": "cadagent.geometry.connectors",
    "markings": "cadagent.geometry.markings",
    "fea": "cadagent.sim.fea",
    "cfd": "cadagent.sim.cfd",
    "heatsink": "cadagent.sim.heatsink",
    "topopt": "cadagent.sim.topopt",
    "simviz": "cadagent.sim.simviz",
    "simreport": "cadagent.sim.simreport",
    "robot": "cadagent.sim.robot",
    "motion_trace": "cadagent.sim.motion_trace",
    "slicer": "cadagent.make.slicer",
    "mesh3mf": "cadagent.make.mesh3mf",
    "release": "cadagent.make.release",
    "mcmaster": "cadagent.make.mcmaster",
    "pcb": "cadagent.make.pcb",
    "pcb_routing": "cadagent.make.pcb_routing",
    "report": "cadagent.publish.report",
    "htmlreport": "cadagent.publish.htmlreport",
    "review": "cadagent.publish.review",
    "packet": "cadagent.publish.packet",
    "render": "cadagent.publish.render",
    "view": "cadagent.publish.view",
    "dotsvg": "cadagent.publish.dotsvg",
    "site": "cadagent.publish.site",
    "site_review": "cadagent.publish.site_review",
    "serve": "cadagent.publish.serve",
}
REMOVED_IN = "0.7.0"


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


class _MovedFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolves ``cadagent.<old>`` to the module at its new path."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("cadagent.") and fullname[len("cadagent."):] in MOVED:
            # The real file as the origin, so find_spec(old).origin names it before the first import too. Finding the
            # new module's spec imports only its parent package, not the module.
            real = importlib.util.find_spec(MOVED[fullname[len("cadagent."):]])
            return importlib.util.spec_from_loader(fullname, self, origin=real.origin if real else None)
        return None

    def create_module(self, spec):
        return None                               # a throwaway module: exec_module puts the real one in its place

    def exec_module(self, module):
        new = MOVED[module.__name__[len("cadagent."):]]
        warnings.warn(f"{module.__name__} moved to {new}; the old path goes in v{REMOVED_IN}", DeprecationWarning,
                      stacklevel=_importer_stacklevel())
        # The import machinery hands back whatever sys.modules holds for the old name once exec_module returns, and
        # binds that as the parent's attribute. Swapping here (instead of returning the real module from
        # create_module) keeps the real module's own __spec__: the machinery sets __spec__ on the module it is
        # given, so the real one used to end up with the shim's spec (no origin; reload renamed it).
        sys.modules[module.__name__] = importlib.import_module(new)


def install() -> None:
    if not any(isinstance(f, _MovedFinder) for f in sys.meta_path):
        sys.meta_path.append(_MovedFinder())
