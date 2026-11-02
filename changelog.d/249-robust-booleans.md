**New**
- `cadagent.geometry.robust_union` and `robust_cut`: booleans that check every result (not null, valid, at least one solid, volume within the inputs' bounds) and fall back to one shape at a time, then, for a cut, to tools nudged by 0.01 mm. Each fallback and nudge is reported (`report=[]`) and logged; when nothing passes they raise `GeometryError` instead of returning a bad shape (#249).

**Fixed**
- `cadagent.geometry.export_print_stl`: open-edge vertices within 1 µm are welded before the watertight check, so a valid solid whose tessellation split a vertex no longer fails as non-watertight. The report adds `vertices_welded`, `mesh_volume_before_weld_mm3` and `mesh_volume_mm3`; a real hole still fails (#249).
