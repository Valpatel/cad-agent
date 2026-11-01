# cadagent.publish

Showing the work: results files, reports, renders, 3D views, review packets and the project site. Every page states
what was checked and what was not (CAD never proves physical fit).

Arrows follow the data, and each one between modules here is an import. `view.py` (STEP files to the 3D viewer's
data) and `serve.py` (the project over http, so pages can hand 3MF files to a slicer) stand alone.

```mermaid
flowchart TD
    X["exports/*.json<br/>check outputs"] -->|"collect()"| R["report.py<br/>results JSON"]
    R -->|"render_page()"| H["htmlreport.py<br/>report page"]
    D["dossier/<br/>gates/<br/>intent, verdicts"] --> PK["packet.py<br/>section packet"]
    PK -->|"views"| RN["render.py<br/>captioned PNGs"]
    D --> ST["site.py<br/>site_review.py"]
    DR["dotsvg.py<br/>review.py"] -->|"graph, workbench"| ST
    ST --> O["site/<br/>project site"]
    H ~~~ V["view.py<br/>3D viewer data"]
    O ~~~ SV["serve.py<br/>local http"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class R,H,PK,RN,ST,DR,V,SV here
    class X,D near
    class O out
```

| Module | What it does |
|---|---|
| `report.py` | Collects a project's check outputs into results JSON (schema 1.0) |
| `htmlreport.py` | A standalone HTML page for a results file |
| `render.py` | Off-screen VTK renders of CadQuery shapes and STL meshes, captioned |
| `view.py` | Every part in assembly position, for the browser viewer (`webkit/viewer.html`) |
| `dotsvg.py` | Graphviz DOT to SVG without Graphviz: a small parser and a layered layout |
| `packet.py` | The section review packet: captioned renders with the measurements first |
| `review.py` | The in-page review workbench for PCBs, housings and assemblies |
| `site.py`, `site_review.py` | The project site: progress, designs, decisions, documents; review pages, requirements, gates |
| `serve.py` | Serves a project over http so pages can hand 3MF files to a slicer |

Related: [package map](../README.md) · [web kit](../webkit/README.md) · [review packet docs](../../../docs/review-packet.md)
