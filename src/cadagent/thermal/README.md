# cadagent.thermal

The thermal domain of the [topic tree](../../../docs/areas.yaml): keeping parts and electronics within their
temperature limits. Airflow and conjugate heat transfer are simulations, so `cfd.py` lives in
[`simulation/`](../simulation/README.md).

Arrows follow the data. `heatsink.py` and `fans.py` import nothing from cad-agent; the heatsink's porous-zone
coefficients reach `simulation/cfd.py` through a project's script, and the datasheet fan curves go to
`formulas.fan_operating_point`.

```mermaid
flowchart TD
    D["fins and fan curve<br/>the project's numbers"] --> HS["heatsink.py<br/>plate fins · fan point"]
    F["fans.py<br/>datasheet fan curves"] -->|"curve"| FX["formulas/thermal.py<br/>operating point · stall"]
    HS -->|"R_th, pressure drop"| O["operating point<br/>air flow, temperature"]
    FX --> O
    HS -->|"porous zone"| CFD["simulation/cfd.py<br/>air and heat"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class HS,F here
    class D,CFD,FX near
    class O out
```

| Module | What it does |
|---|---|
| `heatsink.py` | Plate-fin heat sinks: thermal resistance, pressure drop, fan operating point, porous-zone coefficients |
| `fans.py` | Fan curves read from datasheets (ebm-papst W2G115-AD15-13 at 8, 12 and 16 V) with the operating points the datasheet tabulates; the site's fan-curve explorer uses them |

Related: [package map](../README.md) · [simulation](../simulation/README.md) ·
[toolkit: heatsinks](../../../docs/toolkit.md#heatsinks-cadagentthermalheatsink) ·
[Airflow and fans](../../../docs/fans.md)
