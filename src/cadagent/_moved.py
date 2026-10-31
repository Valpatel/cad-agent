"""Old module paths, kept importing after the move into packages (v0.5.0, #114).

``import cadagent.fea``, ``from cadagent.fea import X`` (private names too), ``from cadagent import fea`` and
``monkeypatch.setattr("cadagent.fea.X", ...)`` all give the module now at ``cadagent.sim.fea``: the same object, not a
copy, so patches and module state are shared. The first import of an old path warns (DeprecationWarning) with the new
one. Old paths are removed in v0.7.0; move imports before then (the table below, or CHANGELOG.md).

One finder instead of a shim file per module, so the package's top level stays as tidy as the move made it.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
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


class _MovedFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Resolves ``cadagent.<old>`` to the module at its new path."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("cadagent.") and fullname[len("cadagent."):] in MOVED:
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec):
        new = MOVED[spec.name[len("cadagent."):]]
        # stacklevel 2 is the importing line: warnings skips importlib's own frames when it counts.
        warnings.warn(f"{spec.name} moved to {new}; the old path goes in v{REMOVED_IN}", DeprecationWarning, stacklevel=2)
        return importlib.import_module(new)       # import machinery keeps this module's own name and spec

    def exec_module(self, module):
        pass                                      # already executed under its new name



def install() -> None:
    if not any(isinstance(f, _MovedFinder) for f in sys.meta_path):
        sys.meta_path.append(_MovedFinder())
