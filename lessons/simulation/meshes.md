# Meshes: a peak is only as good as the mesh under it

```mermaid
flowchart TD
    S["a stress peak<br/>from one mesh"] --> W{"3 or more elements<br/>across its wall?"}
    W -->|"no"| R["refine there<br/>or mesh finer"]
    R --> S
    W -->|"yes"| C{"a sharp inside<br/>corner?"}
    C -->|"yes"| F["model the fillet:<br/>a sharp corner<br/>never converges"]
    F --> S
    C -->|"no"| V{"same on a mesh<br/>0.75x as fine?"}
    V -->|"no"| R
    V -->|"yes"| G["a result, recorded<br/>with the mesher<br/>that made it"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class W,C,V here
    class S,R,F near
    class G out
```

These lessons come from Gyropup's hip frame and front link (Valpatel/gyropup#29), studied in October 2026 with
`cadagent.simulation.fea`. The tools they asked for are in the toolkit now (#144): `refine=`, `converge()`, the
`mesh` record in every result, the sliver check and `MeshRefusal`. See the
[toolkit's meshing section](../../docs/toolkit.md#stiffness-and-strength-cadagentsimulationfea).

### A sharp inside corner never converges: model the fillet
- **Rule:** before trusting a peak, see where it is. A peak at a sharp re-entrant corner is singular: it rises with
  every refinement. A finer mesh does not fix it. Model the fillet the part will have, then refine round it.
- **Incident:** the hip frame's E1 case read a safety factor of 1.85 at a 6 mm mesh and 1.65 at 4 mm, with the peak at
  a sharp inside corner. Later the optimiser's leader read 2.06 at 4 mm and 1.81 at 3 mm, for the same reason. Part
  of its front was made of mesh artefacts.
- **Check:** `result['mesh']['peak']['where']` says "sharp inside corner", and its `note` says the corner is singular.
  The chart below is a real study of an L-bracket. Sharp, the peak grows about 1.37x for each halving of the elements
  there, the rate of Williams' corner solution. With an R1.5 fillet it stays within 3.4 %.
- **Source:** Gyropup #29 study notes; `tools/fea_mesh_figure.py`.

![Peak stress at an L-bracket's inside corner as the mesh there goes from 2 mm to 0.125 mm: sharp, it rises from 443 to 1448 MPa; with an R1.5 fillet it stays between 432 and 447 MPa](../../docs/img/fea/corner-convergence.svg)

### A peak in a wall one or two elements thick is not a result
- **Rule:** count the elements across the wall at the peak. Under 3, refine there and solve again before reading a
  safety factor, or comparing two designs, off it.
- **Incident:** at a 4 mm mesh, the front link's peak sat in the 6 mm wall of its apex bearing ring, one or two elements
  thick. It read SF 1.69 before a knee change and 1.53 after, which looked like a regression. At 3.5 and 3 mm the peak
  moved to the knee boss, and the change went the other way: 1.82 / 1.87 before, 2.04 / 1.96 after.
- **Check:** `result['mesh']['peak']['elements_across']` is 3 or more (`wall_resolved`). Otherwise the study warns
  (`MeshWarning`). `Study.converge()` solves again at 0.75x the mesh and says whether the peak changed or moved.
- **Source:** Gyropup #29 study notes.

### Say which mesher made a result
- **Rule:** a gate read at one mesh size names the mesher build that made it. Before and after are compared on one
  build, and a close call is checked on a second.
- **Incident:** the same hip-frame study, on the same commit with gmsh 4.15.2, was meshed by the PyPI wheel on x86-64
  and by conda-forge's build on aarch64. That gave 151,459 and 151,136 tets. Where the peak sat at a sharp corner, the
  safety factors came out 6 % apart (1.59 and 1.50).
- **Check:** `result['mesh']['mesher']` records the gmsh and OpenCASCADE versions, the build's OS and date, a hash of
  the gmsh library and the platform. Two records from different builds are not a design change.
- **Source:** Gyropup #29 study notes.

### When the mesher refuses a part, look for slivers
- **Rule:** a CAD kernel's "valid solid" can still be unmeshable. Check for sliver faces and short edges before a long
  mesh, and read the faces near the point when gmsh refuses.
- **Incident:** a revolved fillet round a block's foot, clipped to an outline, gave a solid that OpenCASCADE called
  valid. gmsh stopped with "PLC Error: A segment and a facet intersect at point" in all three runs, after the CAD build,
  and named no faces. The cause was slivers where the fillet ring met the outline almost tangentially. The variant
  was dropped as a failed trial.
- **Check:** `Study.slivers` lists faces under (mesh_mm/10)² and edges under mesh_mm/10, and `slivers='raise'` fails
  the trial in seconds. A refusal raises `MeshRefusal` with the point and the nearest faces and their areas.
- **Source:** Gyropup #29 study notes (the `ear_boss_fillet` variant).

Back to the [simulation lessons](README.md) or [all lessons](../README.md).
