"""Integrity gates: assembly-level checks computed from the model, each written as a verdict file.

The machinery here is shared by every gate (the plan, ``docs/design-process-plan.md`` §4):

* ``Assembly``: named parts in assembly coordinates, with body and group labels;
* ``relation_table(assembly)``: the pairwise relation table (apart / touching / overlapping /
  contains, with witnesses), an AABB broad phase first, cached by shape content hash;
* ``relate_pair(assembly, a, b)``: one cached exact pair by name (a part against a declared cavity);
* ``relate(a, b)``: one exact pair of bare shapes, uncached;
* ``verdict(...)`` / ``write_verdict(...)``: the pass/warn/fail file with its assumptions.

Gates built on it: ``cadagent.review.gates.wall`` (minimum wall); ``cadagent.review.gates.connectivity`` (floating
parts, contacts against interfaces); ``cadagent.review.gates.containment`` (contents inside their container's registered
cavity, per pose); ``cadagent.review.gates.fasteners`` (each screw's seat, stack, holes, engagement, tip and length, and
its tool's reach at the step that installs it);
``cadagent.review.gates.motion`` (collisions over every joint's sampled range);
``cadagent.review.gates.assembly`` (every part in one assembly step, going in along its direction past the parts already
fitted, and each screw's tool reaching it at that step).
The gates check the CAD model against declared intent; none of them proves that printed parts fit, move or hold.
The API reference is ``docs/gates.md``. CadQuery/OCP is imported only when a query runs.
"""

from cadagent.review.evidence import shape_content_hash
from cadagent.review.gates.cache import DEFAULT_CACHE_DIR, PairCache
from cadagent.review.gates.relations import (CONTACT_STATES, INTERFERENCE_STATES, STATES, Assembly, Part, Relation,
                                             RelationTable, Tolerances, aabb_distances, bounding_box, relate,
                                             relate_pair, relation_table, solid_interference)
from cadagent.review.gates.verdict import SCHEMA, Check, verdict, write_verdict

__all__ = ["Assembly", "Part", "Tolerances", "Relation", "RelationTable", "relation_table", "relate", "relate_pair",
           "solid_interference", "aabb_distances", "bounding_box", "STATES", "CONTACT_STATES", "INTERFERENCE_STATES",
           "PairCache", "shape_content_hash",
           "DEFAULT_CACHE_DIR", "Check", "verdict", "write_verdict", "SCHEMA"]
