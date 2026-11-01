**New**
- An animated figure of a recorded FEA mesh-convergence study, in the toolkit's meshing section and the simulation
  README (`docs/img/fea/mesh-convergence.svg`). An L-bracket's sharp and R1.5-filleted inside corner are refined step
  by step with `refine=`. It shows the mesh at the corner, the design peak, the result's flags and `converge()`'s
  verdict. The sharp peak keeps rising; the fillet's settles. It is drawn from a committed record of a real run
  (`tools/anim/fea-convergence.scene.json`) that names the gmsh and OpenCASCADE versions.
  `tools/readme_anim.py --extract convergence` records it again, and `--check` fails when the SVG is stale (#167).
- `cadagent.publish.anim.convergence`: `record()` runs this study from its spec (the bracket's size, the material, the
  load, the sizes asked for at the corner) and `render()` draws two corners' records (#167).

**Fixed**
- `cadagent.simulation.fea.Study.converge()` no longer passes a peak at a sharp inside corner when the two meshes
  happen to agree. An L-bracket's corner refined to 0.25 mm moved only +1.8 % on the finer mesh and was called
  converged, while its own note said the corner never converges (#167).

**Projects must change**
- `converge()` on a peak at a sharp inside corner now always returns `converged: False` with a `MeshWarning`, even
  when the change is within the tolerance. Model the fillet the part will have, or filter `MeshWarning` where
  warnings are errors (#167).
