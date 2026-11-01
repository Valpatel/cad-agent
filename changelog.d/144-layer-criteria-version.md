**New**
- `cadagent.__version__`: the toolkit's version, for a record of what made a result. It reads the checkout's
  `pyproject.toml` when the package sits in a source tree (a checkout run with `PYTHONPATH=src`, or an editable
  install, whose installed metadata can be stale), else the installed metadata, else `0+unknown`. It imports nothing
  heavy (#144).
- `Study.layer_check(..., criterion='max-stress')`: the layers' bond as two separate checks, `tension` (max(σn, 0)
  against S_z) and `shear` (τn against S_s), instead of the combined quadratic one. `bulk_stress='in-plane'` takes the
  bulk check's von Mises of the layer plane's own stress, leaving σn and τn to the bond. With
  `strength_shear=S_z / 2` the two options give a project's own three maximum-stress checks, such as Gyropup's turret,
  so it can keep one implementation. `layer_modes()` and `in_plane_von_mises()` give the same for stress tensors
  (#144).
- `LayerCheck.stats`: how far past the worst corner the stress reaches. Per check it gives the 99th percentile over
  the judged volume and the elements past the allowable, with their volume. `LayerCheck.modes` gives each check per
  element. `worst['resolution']` measures the mesh at the worst corner, as `result['mesh']['peak']` does at the design
  peak (#144).
- `Study.render(path, field=lc)` colours a part by its layer check, or by any per-element utilisation. Elements past
  the allowable are black, and the ones not judged are grey (#144).

**Changed**
- The old flat import paths (`cadagent.fea` and the rest) are no longer said to go in v0.7.0, which shipped with
  them. They stay until a release whose CHANGELOG announces their removal at least one minor release ahead, under
  **Projects must change**. Their `DeprecationWarning` now says to move the import and points to the table in
  docs/toolkit.md (Package layout). No old path is removed (#144).

**Projects must change**
- Nothing for existing layer checks: the defaults (`criterion='combined'`, `bulk_stress='full'`) give the same
  numbers as before. `LayerCheck.as_dict()` adds `criterion`, `bulk_stress`, `stats` and `worst['resolution']`, and
  every key it had keeps its value. A test that compares the whole dict must allow the new keys (#144).
- A project that hashes its source folders in evidence receipts can move its old-path imports when it next
  regenerates them: no removal release is set yet (#144).
