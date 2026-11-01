"""Mechanical design (docs/areas.yaml: mechanical): holes (holes), fastener envelopes and stacks (fasteners), bought
hardware (mcmaster), connector windows (connectors), engraved markings (markings), snap fits and flexures
(compliant), closed-loop linkages (linkages), and motion traces (motion_trace).

Each package holds one domain of the topic tree (docs/areas.yaml), and tests/test_package_areas.py keeps the two in
step. Old flat paths (``cadagent.fea`` and so on) still import until v0.7.0, see ``cadagent._moved``."""
