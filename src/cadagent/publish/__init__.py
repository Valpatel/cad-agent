"""Showing the work (docs/areas.yaml: practice / publishing): reports (report, htmlreport), renders and views (render,
view, dotsvg), animated SVGs drawn from real CAD and real results (anim: README heroes and headers), the project site
(site, site_review), the local server (serve) and releases (release).

Each package holds one domain of the topic tree (docs/areas.yaml), and tests/repo/test_package_areas.py keeps the two in
step. Old flat paths (``cadagent.fea`` and so on) still import, with a DeprecationWarning, until a release that the
CHANGELOG announces a minor release ahead; see ``cadagent._moved``."""
