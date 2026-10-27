"""Explore and compare designs: pick parts from a catalogue, evaluate each design, rank the trade-offs.

For any product built from bought and made parts (a housing, a robot, a board, a fixture), configured under
``cad: explore:`` in ``cad-agent.yaml`` (``docs/explore.md``):

* ``catalogue``: part lists with specs, prices (with the date checked), sources and confidence flags; loaded and
  checked by ``cadagent.explore.catalogue``.
* ``design``: a design file names one catalogue part per slot (or an inline custom part) plus free-form parameters,
  and may ``extend`` another design; ``cadagent.explore.design`` resolves it and costs and weighs it (the BOM).
* ``evaluate``: the project's own evaluator (a Python function, or any command speaking JSON) turns a design into
  metrics and checks; the evaluator stays in the project.
* ``compare``: Pareto ranking over the objectives, constraints, one-part swaps, ``comparison.json``, a standalone
  HTML page (``page``) and design cards for the project site.
* ``optimise``: a search over slots and parameters (random and grid built in; NSGA-II and TPE with optuna) that
  evaluates each trial the same way and keeps a leaderboard.

Everything is a comparison on paper: as good as the catalogue's numbers and the evaluator's model, and never a
substitute for weighing, testing and pricing the real parts.
"""

from cadagent.explore.catalogue import Catalogue, Issue, check_catalogue, load_catalogue, load_configured
from cadagent.explore.compare import comparison, compare_designs, rank, swaps, write_comparison
from cadagent.explore.config import ExploreConfig, explore_config
from cadagent.explore.design import Candidate, DesignError, bom, load_design, resolve
from cadagent.explore.evaluate import EvaluatorError, evaluate_design, load_evaluator

__all__ = [
    "Catalogue", "Issue", "check_catalogue", "load_catalogue", "load_configured",
    "comparison", "compare_designs", "rank", "swaps", "write_comparison",
    "ExploreConfig", "explore_config",
    "Candidate", "DesignError", "bom", "load_design", "resolve",
    "EvaluatorError", "evaluate_design", "load_evaluator",
]
