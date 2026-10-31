# cadagent.sim

Simulation and what it produces: stiffness and strength, airflow and heat, optimised material layouts, robot
descriptions, and the pictures and pages that show the results honestly (assumptions and limits included).

```mermaid
flowchart LR
    P["part or assembly<br/>STEP · CadQuery"] --> FEA["fea<br/>stiffness · strength"]
    P --> CFD["cfd<br/>OpenFOAM cases"]
    P --> T["topopt<br/>material layout"]
    P --> RB["robot<br/>URDF · mass"]
    HS["heatsink<br/>fins · fan point"] --> CFD
    MT["motion_trace<br/>render vs CAD intent"]
    FEA & CFD & T --> V["simviz<br/>pictures · animations"]
    V --> SR["simreport<br/>HTML page"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class FEA,CFD,T,RB,HS,MT here
    class P near
    class V,SR out
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
