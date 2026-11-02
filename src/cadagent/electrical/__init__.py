"""Electrical design (docs/areas.yaml: electrical): circuit-board checks and fabrication files (pcb) and their routing
(pcb_routing).

Each package holds one domain of the topic tree (docs/areas.yaml), and tests/repo/test_package_areas.py keeps the two in
step. Old flat paths (``cadagent.fea`` and so on) still import, with a DeprecationWarning, until a release that the
CHANGELOG announces a minor release ahead; see ``cadagent._moved``."""
