**New**
- `cadagent.simulation.fea.Study(refine=[(point_mm, radius_mm, size_mm), ...])`: a finer mesh round a spot (a gmsh
  Ball field each, under a Min field). The rest of the mesh stays as it was, so one fillet or hole converges without
  refining the whole part (#144).
- `Study.converge(factor=0.75)`: the same loads on a finer mesh; it gives the design peak's change and whether it
  moved. Past 5 %, or when the finer mesh does not resolve the peak either, it is not converged (a `MeshWarning`)
  (#144).
- `result['mesh']` records the mesher (`mesher`: the gmsh and OpenCASCADE versions, the build's OS and date, a hash of
  the gmsh library, the platform) and the design peak's resolution (`peak`: where it sits, the thinnest wall round it,
  the element size there and `elements_across`). Under 3 elements across, it is flagged (`wall_resolved` false, a
  `MeshWarning`): a peak in a wall one or two elements thick is not a result. At an inside fillet or a hole,
  elements larger than its radius are flagged too (`radius_mm`, `radius_resolved`) (#144).
- A check before meshing lists faces under (mesh_mm/10)² in area, long faces under mesh_mm/10 in width, and edges
  under mesh_mm/10
  (`Study.slivers`). It warns by default; `slivers='raise'` stops in seconds with a `MeshRefusal`, before a long mesh
  (#144).
- When gmsh refuses a part ("PLC Error: A segment and a facet intersect at point", or "Could not recover boundary
  mesh"), `Study` raises a `MeshRefusal` with the point and the nearest faces with their areas when gmsh gives a
  point, not gmsh's bare message (`parse_gmsh_refusal()` reads the log). A second try that meshes is used, with a
  `MeshWarning`. `Study.faces_near(point)` names the faces round any point (#144).

**Fixed**
- The FEA hot-spot hint reads "sharp inside corner" where an inside corner meets a side face; it could read "outside
  edge" there (#144).

**Projects must change**
- `Study()` now warns (`MeshWarning`) when the part has sliver faces or edges, and `Study.solve()` when the design
  peak's wall is under 3 elements thick or its inside fillet or hole is smaller than the elements there. A study that treats
  warnings as errors fails on them: mesh finer there (`refine=`), remove the sliver, or filter `MeshWarning`. Without
  `refine=`, meshes are unchanged, bit for bit; results are too, apart from the hot-spot hint fix above (#144).
