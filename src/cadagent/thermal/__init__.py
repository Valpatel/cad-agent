"""Thermal design (docs/areas.yaml: thermal): plate-fin heat sinks and fan operating points (heatsink), and fan curves
from datasheets (fans).

Each package holds one domain of the topic tree (docs/areas.yaml), and tests/test_package_areas.py keeps the two in
step. Old flat paths (``cadagent.fea`` and so on) still import, with a DeprecationWarning, until a release that the
CHANGELOG announces a minor release ahead; see ``cadagent._moved``."""
