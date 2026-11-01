"""Simulation and validation (docs/areas.yaml: simulation): FEA (fea), CFD (cfd), topology optimisation (topopt), robot
dynamics (robot), design exploration (explore), and the charts and reports of simulation results (simviz, simreport).

Each package holds one domain of the topic tree (docs/areas.yaml), and tests/test_package_areas.py keeps the two in
step. Old flat paths (``cadagent.fea`` and so on) still import until v0.7.0, see ``cadagent._moved``."""
