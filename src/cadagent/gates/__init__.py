"""Integrity gates: assembly-level checks computed from the model, each written as a verdict file.

The machinery here is shared by every gate (the plan, ``docs/design-process-plan.md`` §4):

* ``Assembly``: named parts in assembly coordinates, with body and group labels;
* ``relation_table(assembly)``: the pairwise relation table (apart / touching / overlapping /
  contains, with witnesses), an AABB broad phase first, cached by shape content hash;
* ``relate(a, b)``: one exact pair (a part against a declared cavity solid, say);
* ``verdict(...)`` / ``write_verdict(...)``: the pass/warn/fail file with its assumptions.

Gates built on it: ``cadagent.gates.wall`` (minimum wall). The gates check the CAD model
against declared intent; none of them proves that printed parts fit, move or hold.
The API reference is ``docs/gates.md``. CadQuery/OCP is imported only when a query runs.
"""

from cadagent.gates.cache import DEFAULT_CACHE_DIR, PairCache, shape_hash
from cadagent.gates.relations import (CONTACT_STATES, STATES, Assembly, Part, Relation, RelationTable, Tolerances,
                                      aabb_distances, bounding_box, relate, relation_table)
from cadagent.gates.verdict import SCHEMA, Check, verdict, write_verdict

__all__ = ["Assembly", "Part", "Tolerances", "Relation", "RelationTable", "relation_table", "relate",
           "aabb_distances", "bounding_box", "STATES", "CONTACT_STATES", "PairCache", "shape_hash",
           "DEFAULT_CACHE_DIR", "Check", "verdict", "write_verdict", "SCHEMA"]
