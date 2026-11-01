# cadagent.simulation

The simulation domain of the [topic tree](../../../docs/areas.yaml): predicting how designs behave (stiffness and
strength, airflow and heat, optimised material layouts, robot descriptions, whole designs compared), and the pictures
and pages that show the results honestly, assumptions and limits included.

Arrows follow the data. Only `topopt.py` imports its neighbours (`cfd.py`'s mesher and `simviz.py`'s drawing
helpers); the other arrows are objects and files that a project's script passes on. `explore/` and `robot.py` stand
alone.

```mermaid
flowchart TD
    P["part or assembly<br/>STEP · CadQuery"] --> FEA["fea.py<br/>stiffness, strength"]
    P --> CFD["cfd.py<br/>air and heat"]
    CFD -->|"mesher"| T["topopt.py<br/>material layout"]
    FEA -->|"export_viewer"| W["webkit/fea.html<br/>FEA viewer"]
    FEA & T & CFD --> V["simviz.py<br/>pictures, videos"]
    V -->|"PNG · MP4"| SR["simreport.py<br/>results page"]
    SR ~~~ E["explore/<br/>pick, evaluate, rank"]
    SR ~~~ RB["robot.py<br/>URDF, MJCF"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class FEA,CFD,T,V,SR,E,RB here
    class P near
    class W out
```

| Module | What it does |
|---|---|
| `fea.py` | Linear-elastic stiffness and strength studies for any CAD part; a printed part's stress against its layers (`layer_check`); the material data each result used; mesh control (local refinement, a finer-mesh check, the mesher and the peak's resolution in each result, slivers and mesher refusals); exports the interactive FEA viewer's data |
| `cfd.py` | Steady conjugate heat transfer cases for OpenFOAM, written from CAD |
| `topopt.py` | Topology optimisation with [pyMOTO](https://github.com/aatmdelissen/pyMOTO) (Arnoud Delissen, MIT) |
| `robot.py` | Mass properties from CAD, links and joints, URDF writing and checking |
| [`explore/`](explore/__init__.py) | Pick parts from catalogues, evaluate whole designs, rank the trade-offs (`cad-agent catalogue`, `compare`, `optimise`) |
| `simviz.py` | Pictures and animations of results with [PyVista](https://github.com/pyvista/pyvista) / VTK, off screen |
| `simreport.py` | A standalone HTML page: before/after metrics, figures, videos, limits |

A peak is only as good as the mesh under it. `fea.py` refines round a peak (`refine=`), says how well each mesh
resolves it (`result['mesh']['peak']`) and checks it on a finer mesh (`converge()`):

![An L-bracket's inside corner refined step by step, refine= asking for 2 mm down to 0.25 mm there: sharp, the peak stress rises from 443 to 1,094 MPa and converge() never passes it; with an R1.5 fillet it stays between 432 and 447 MPa and converge() passes it from the 1 mm step](../../../docs/img/fea/mesh-convergence.svg)

*A recorded run of the toolkit (cad-agent 0.7.0 on gmsh 4.15.2 with OpenCASCADE 7.8.1, 2026-11-01), redrawn from
[its record](../../../tools/anim/fea-convergence.scene.json) by `tools/readme_anim.py`; the
[toolkit's meshing section](../../../docs/toolkit.md#stiffness-and-strength-cadagentsimulationfea) explains it.
Linear-elastic FEA: a converged peak does not prove that the part holds.*

Related: [package map](../README.md) · [thermal](../thermal/README.md) (heat sinks) ·
[simulation tools research](../../../research/simulation-tools.md) ·
[lesson: simulation and material](../../../lessons/simulation/simulation-and-material.md)
