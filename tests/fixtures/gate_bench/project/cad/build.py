"""Gate-bench project build: the bench mechanism (``tests/fixtures/gate_bench/build.py``) declared on the current
dossier registry, with the seeded defect named in ``cad/parameters.json`` (``{"seed": null}``: the clean bench).

``cadagent.review.dossier.build_module`` executes this file in a fresh registry (``cad-agent gates --build``); run as a
script it builds and writes ``exports/dossier-geometry.json`` itself.
"""

import importlib.util
import json
import sys
from pathlib import Path

from cadagent.review import dossier

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("gate_bench_fixture", HERE.parents[1] / "build.py")
gb = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gb            # dataclasses need the module registered
_spec.loader.exec_module(gb)

SEED = json.loads((HERE / "parameters.json").read_text()).get("seed")
gb.register(dossier.current_registry(), gb.params_for(SEED))

if __name__ == "__main__":
    dossier.build()
