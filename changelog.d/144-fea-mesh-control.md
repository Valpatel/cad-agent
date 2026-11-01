**New**
- `cadagent.simulation.fea.Study(refine=[(point_mm, radius_mm, size_mm), ...])`: a finer mesh round a spot (a gmsh
  Ball field each, under a Min field). The rest of the mesh stays as it was, so one fillet or hole converges without
  refining the whole part (#144).
- `Study.converge(factor=0.75)`: the same loads on a finer mesh; it gives the design peak's change, whether it moved,
  and a `MeshWarning` past 5 % (#144).
- `result['mesh']` records the mesher (`mesher`: the gmsh and OpenCASCADE versions, the build's OS and date, a hash of
  the gmsh library, the platform) and the design peak's resolution (`peak`: where it sits, the thinnest wall round it,
  the element size there and `elements_across`). Under 3 elements across, it is flagged (`wall_resolved` false, a
  `MeshWarning`): a peak in a wall one or two elements thick is not a result (#144).
- A check before meshing lists faces under (mesh_mm/10)² and edges under mesh_mm/10 (`Study.slivers`). It warns by
  default; `slivers='raise'` stops in seconds with a `MeshRefusal`, before a long mesh (#144).
- When gmsh refuses a part ("PLC Error: A segment and a facet intersect at point"), `Study` raises a `MeshRefusal`
  with the point and the nearest faces with their areas, not gmsh's bare message (`parse_gmsh_refusal()` reads the
  log). `Study.faces_near(point)` names the faces round any point (#144).

**Fixed**
- The FEA hot-spot hint reads "sharp inside corner" where an inside corner meets a side face; it could read "outside
  edge" there (#144).

**Projects must change**
- `Study.solve()` now warns (`MeshWarning`) when the design peak's wall is under 3 elements thick, and when the part
  has sliver faces or edges. A study that treats warnings as errors fails on them: mesh finer there (`refine=`),
  remove the sliver, or filter `MeshWarning`. Meshes and results without `refine=` are unchanged, bit for bit (#144).
