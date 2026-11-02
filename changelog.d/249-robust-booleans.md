**New**
- `cadagent.geometry.robust_union` and `robust_cut`: booleans that check every result (not null, valid by the relation gate's strict checks, at least one solid, a volume within the inputs' bounds by its adaptive integration) and fall back to one shape at a time, then, for a cut, to tools nudged by 0.01 mm. Each fallback and nudge is reported (`report=[]`) and logged; when nothing passes they raise `GeometryError` instead of returning a bad shape. Contributed by Jeff Patrick, from failures he met on a real build (#249).

**Fixed**
- `cadagent.geometry.export_print_stl`: open-edge vertices within 1 µm are welded before the watertight check, so a valid solid whose tessellation split a vertex no longer fails as non-watertight. The report adds `vertices_welded`, `mesh_volume_before_weld_mm3` and `mesh_volume_mm3`; a real hole still fails (#249).
