# cadagent.manufacturing

The manufacturing domain of the [topic tree](../../../docs/areas.yaml): getting from a checked model to print files and
real slicer numbers.

Arrows follow the files. `slicer.py` imports `publish/report.py`'s `load_parts` to find the parts it slices, and
`publish/report.py` and `publish/release.py` import `slicer.py` to read a current slice report; `mesh3mf.py` imports
nothing from cad-agent.

```mermaid
flowchart TD
    B["build script<br/>STL · parts file"] -->|"STL"| M3["mesh3mf.py<br/>3MF + read-back"]
    M3 -->|"3MF"| SL["slicer.py<br/>Bambu Studio CLI"]
    SL --> SR["exports/<br/>slice report"]
    SR --> R["publish/report.py<br/>results JSON"]
    SR --> REL["publish/release.py<br/>print release"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class M3,SL here
    class B,R,REL near
    class SR out
```

| Module | What it does |
|---|---|
| `mesh3mf.py` | A minimal 3MF writer with an independent read-back check (`cad-agent export-3mf`) |
| `slicer.py` | Real filament grams and print time from Bambu Studio's command line, run as a separate program (`cad-agent slice`) |

Related: [package map](../README.md) · [publish](../publish/README.md) (the print release) ·
[toolkit: print files](../../../docs/toolkit.md#print-files)
