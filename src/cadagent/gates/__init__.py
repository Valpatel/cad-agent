"""Integrity gates: assembly-level checks computed from the model, each written as a verdict file.

The machinery here is shared by every gate (the plan, ``docs/design-process-plan.md`` §4):

* ``Assembly``: named parts in assembly coordinates, with body and group labels;
* ``relation_table(assembly)``: the pairwise relation table (apart / touching / overlapping /
  contains, with witnesses), an AABB broad phase first, cached by shape content hash;
* ``relate_pair(assembly, a, b)``: one cached exact pair by name (a part against a declared cavity);
* ``relate(a, b)``: one exact pair of bare shapes, uncached;
* ``verdict(...)`` / ``write_verdict(...)``: the pass/warn/fail file with its assumptions.

Gates built on it: ``cadagent.gates.wall`` (minimum wall); ``cadagent.gates.connectivity`` (floating parts,
contacts against interfaces); ``cadagent.gates.containment`` (contents inside their container's registered cavity, per pose);
``cadagent.gates.fasteners`` (each screw's seat, stack, holes, engagement, tip and length, and its tool's reach at
the step that installs it);
``cadagent.gates.motion`` (collisions over every joint's sampled range).
The gates check the CAD model against declared intent; none of them proves that printed parts fit, move or hold.
The API reference is ``docs/gates.md``. CadQuery/OCP is imported only when a query runs.
"""

from cadagent.evidence import shape_content_hash
from cadagent.gates.cache import DEFAULT_CACHE_DIR, PairCache
from cadagent.gates.relations import (CONTACT_STATES, INTERFERENCE_STATES, STATES, Assembly, Part, Relation,
                                      RelationTable, Tolerances, aabb_distances, bounding_box, relate, relate_pair,
                                      relation_table, solid_interference)
from cadagent.gates.verdict import SCHEMA, Check, verdict, write_verdict

__all__ = ["Assembly", "Part", "Tolerances", "Relation", "RelationTable", "relation_table", "relate", "relate_pair",
           "solid_interference", "aabb_distances", "bounding_box", "STATES", "CONTACT_STATES", "INTERFERENCE_STATES",
           "PairCache", "shape_content_hash",
           "DEFAULT_CACHE_DIR", "Check", "verdict", "write_verdict", "SCHEMA"]
