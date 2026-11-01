# cadagent.make

Getting from a checked model to real parts: print files, slicer numbers, a print release, bought hardware, and board
evidence.

Arrows follow the files. Printed parts run down the left; the board checks on the right are separate.
`release.py` imports `slicer.py` to read a current slice report; the other modules here import none of each other.

```mermaid
flowchart TD
    MC["mcmaster.py<br/>bought-part STEP"] --> B["build script<br/>STL · STEP"]
    B -->|"STL"| M3["mesh3mf.py<br/>3MF + read-back"]
    M3 -->|"3MF"| SL["slicer.py<br/>Bambu Studio CLI"]
    SL -->|"slice report"| REL["release.py<br/>cad-agent release"]
    M3 -->|"3MF"| REL
    REL --> O["release/<br/>index.html + zip"]
    K["kicad-cli reports<br/>ERC · DRC JSON"] --> PCB["pcb.py<br/>cad-agent pcb-check"]
    PCB --> PE["exports/<br/>pcb-evidence.json"]
    PE ~~~ CU["routed copper<br/>pads · tracks · vias"]
    CU --> PR["pcb_routing.py<br/>path lengths"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class MC,M3,SL,REL,PCB,PR here
    class B,K,CU near
    class O,PE out
```

| Module | What it does |
|---|---|
| `mesh3mf.py` | A minimal 3MF writer with an independent read-back check |
| `slicer.py` | Real filament grams and print time from Bambu Studio's command line, run as a separate program |
| `release.py` | The print release: a browsable page of printed parts with their CAD files and the source that builds them |
| `mcmaster.py` | McMaster-Carr parts: the manufacturer's STEP and product data for a part number, in a known frame |
| `pcb.py` | PCB evidence adapters; CAD validity and production qualification stay separate |
| `pcb_routing.py` | Geometry-only path measurements for routed boards, without KiCad |

Related: [package map](../README.md) · [mcmaster-parts skill](../../../skills/mcmaster-parts/SKILL.md) ·
[PCB docs](../../../docs/pcb.md)
