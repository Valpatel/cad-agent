"""Manufacturing (docs/areas.yaml: manufacturing): print files (mesh3mf), slicing (slicer), build plates (plates), fit
coupons, and the process profiles (process) that the minimum-feature check (dfm) and the sheet-metal calculator
(sheet_metal) read.

Each package holds one domain of the topic tree (docs/areas.yaml), and tests/test_package_areas.py keeps the two in
step. Old flat paths (``cadagent.fea`` and so on) still import, with a DeprecationWarning, until a release that the
CHANGELOG announces a minor release ahead; see ``cadagent._moved``."""
