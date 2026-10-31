# cadagent.make

Getting from a checked model to real parts: print files, slicer numbers, a print release, bought hardware, and board
evidence.

```mermaid
flowchart LR
    B["build output<br/>STL · STEP"] --> M3["mesh3mf<br/>3MF + read-back"]
    M3 --> SL["slicer<br/>grams · print time"]
    M3 & SL --> REL["release<br/>print page"]
    MC["mcmaster<br/>part STEP + specs"] --> B
    PCB["pcb · pcb_routing<br/>board evidence"]
    REL --> O["what to print<br/>and order"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class M3,SL,REL,MC,PCB here
    class B near
    class O out
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
