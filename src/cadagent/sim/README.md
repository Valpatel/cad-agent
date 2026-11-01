# cadagent.sim

Simulation and what it produces: stiffness and strength, airflow and heat, optimised material layouts, robot
descriptions, and the pictures and pages that show the results honestly (assumptions and limits included).

Arrows follow the data. Only `topopt.py` imports its neighbours (`cfd.py`'s mesher and `simviz.py`'s drawing
helpers); the other arrows are objects and files that a project's script passes on. `robot.py` and `motion_trace.py`
stand alone.

```mermaid
flowchart TD
    P["part or assembly<br/>STEP · CadQuery"] --> FEA["fea.py<br/>stiffness, strength"]
    P --> CFD["cfd.py<br/>air and heat"]
    HS["heatsink.py<br/>fins · fan point"] -->|"porous zone"| CFD
    CFD -->|"mesher"| T["topopt.py<br/>material layout"]
    P --> T
    FEA -->|"export_viewer"| W["webkit/fea.html<br/>FEA viewer"]
    FEA & T & CFD --> V["simviz.py<br/>pictures, videos"]
    V -->|"PNG · MP4"| SR["simreport.py<br/>results page"]
    W ~~~ RB["robot.py<br/>URDF, MJCF"]
    RB ~~~ MT["motion_trace.py<br/>renders vs joints"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class FEA,CFD,HS,RB,MT,T,V,SR here
    class P near
    class W out
```

| Module | What it does |
|---|---|
| `fea.py` | Linear-elastic stiffness and strength studies for any CAD part; exports the interactive FEA viewer's data |
| `cfd.py` | Steady conjugate heat transfer cases for OpenFOAM, written from CAD |
| `heatsink.py` | Plate-fin heat sinks: thermal resistance, pressure drop, fan operating point, porous-zone coefficients |
| `topopt.py` | Topology optimisation with [pyMOTO](https://github.com/aatmdelissen/pyMOTO) (Arnoud Delissen, MIT) |
| `robot.py` | Mass properties from CAD, links and joints, URDF writing and checking |
| `motion_trace.py` | Compares rendered landmarks with CAD joint intent, without a CAD kernel |
| `simviz.py` | Pictures and animations of results with [PyVista](https://github.com/pyvista/pyvista) / VTK, off screen |
| `simreport.py` | A standalone HTML page: before/after metrics, figures, videos, limits |

Related: [package map](../README.md) · [simulation tools research](../../../research/simulation-tools.md) ·
[lesson: simulation and material](../../../lessons/10-simulation-and-material.md)
