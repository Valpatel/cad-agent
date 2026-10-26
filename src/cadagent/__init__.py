"""CAD design verification and review reports for printed-part projects.

A CAD project adopts this toolkit by following one contract (full description
and a worked example in ``docs/toolkit.md``):

* ``cad-agent.yaml`` (or ``vptest.yaml``) at the project root carries a
  ``cad:`` section (``cadagent.project.load_project``): name, title, revision,
  the ordered build ``steps`` (scripts run with the project's own python), the
  parts file, the project-specific ``checks``, the printer bed, packaging and
  the pages whose local links must resolve.
* The build writes one STL + 3MF (print orientation) and one STEP (assembly
  coordinates) per printable part into ``exports/``, plus a parts file
  (default ``exports/geometry-checks.json``) mapping each part to
  ``{cad_valid, solid_count, watertight, print_bounds_mm, ...}``.
* Every project-specific check writes ``exports/<name>.json`` with a top-level
  boolean ``pass`` (or the key named by ``pass_key``). A missing file, a
  missing key or a non-boolean value is a failure, never a pass.
* CAD checks never claim physical fit: reports always record
  ``physical_fit_verified`` as false, and ``slicer_run`` as false unless
  ``cad-agent slice`` has sliced the current 3MF files (sha256 checked).

Heavy dependencies (cadquery/OCP, trimesh, vtk, PIL) are imported inside the
functions that need them; a missing one raises ``MissingDependency`` naming the
``cad`` extra instead of quietly skipping work.
"""

from cadagent._deps import MissingDependency

__all__ = ["MissingDependency"]
