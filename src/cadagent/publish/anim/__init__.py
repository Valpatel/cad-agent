"""Animated SVG figures for READMEs and the site, drawn from real CAD and real results.

One family, shared parts:

* ``svg``: compact numbers and paths, a CSS keyframe timeline, light and dark themes, the document wrapper, and
  ``problems()``, the rules a figure must pass to embed as a GitHub ``<img>`` (no script, no external references,
  a reduced-motion still, a title, a size budget);
* ``cad``: STEP solids to visible edges by OpenCASCADE hidden-line removal, and to triangles (needs CadQuery);
* ``raster``: triangle depth rasters, outlines and simplification, for silhouettes and painter's order;
* ``linkage``: planar linkage poses by circle intersection (now ``cadagent.mechanical.linkages``, re-exported here);
* ``field``: an FEA viewer field (``cadagent.simulation.fea``) for stress colours;
* ``text``: text as outlines, so no web font is needed.

Scenes build on them, one per subject: ``hero`` (an assembly drawn in, assembled and checked). Each scene has an
``extract`` step that needs the CAD kernel and the project's files and writes a JSON scene, and a ``render`` step
that is plain Python, so a committed SVG can be regenerated and compared anywhere (``tools/readme_anim.py
--check``).
"""
