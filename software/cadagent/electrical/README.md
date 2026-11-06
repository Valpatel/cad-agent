# cadagent.electrical

The electrical domain of the [topic tree](../../../docs/areas.yaml): evidence that a circuit board is ready to order,
and measurements of a routed board. CAD validity and production qualification stay separate.

Arrows follow the data. `pcb.py` imports `review/evidence.py`'s `hashes_are_current` to tell a current report from a
stale one; `pcb_routing.py` imports nothing from cad-agent and needs no KiCad.

```mermaid
flowchart TD
    K["kicad-cli reports<br/>ERC · DRC JSON"] --> PCB["pcb.py<br/>cad-agent pcb-check"]
    EV["review/evidence.py<br/>content hashes"] --> PCB
    PCB --> PE["exports/<br/>pcb-evidence.json"]
    PE ~~~ CU["routed copper<br/>pads · tracks · vias"]
    CU --> PR["pcb_routing.py<br/>path lengths"]
    PR --> PL["the project's checks<br/>its own limits"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class PCB,PR here
    class K,EV,CU,PL near
    class PE out
```

| Module | What it does |
|---|---|
| `pcb.py` | PCB evidence adapters (`cad-agent pcb-check`); CAD validity and production qualification stay separate |
| `pcb_routing.py` | Geometry-only path measurements for routed boards, without KiCad |

Related: [package map](../README.md) · [PCB docs](../../../docs/pcb.md) · [review](../review/README.md) (evidence
hashes)
