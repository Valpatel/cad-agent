"""Mechanical design (docs/areas.yaml: mechanical): holes (holes), fastener envelopes and stacks (fasteners), bought
hardware (mcmaster), connector windows (connectors), engraved markings (markings), snap fits and flexures
(compliant), and motion traces (motion_trace).

Each package holds one domain of the topic tree (docs/areas.yaml), and tests/test_package_areas.py keeps the two in
step. Old flat paths (``cadagent.fea`` and so on) still import, with a DeprecationWarning, until a release that the
CHANGELOG announces a minor release ahead; see ``cadagent._moved``."""
