# cadagent.review

The practice domain's design-process and review-and-evidence areas of the [topic tree](../../../docs/areas.yaml):
the design dossier, the integrity gates that check an assembly against it, the section packets a reviewer reads, and
the hashes that tell current evidence from stale. `from cadagent.review import review_html` is the in-page review
workbench, as it was before this folder existed.

Arrows follow the data. Each arrow between pieces here is also an import, and `dossier/` imports `gates/` back to
lint the verdicts it reads. `packet.py` asks `publish/render.py` for its views; `publish/site.py` imports the
workbench.

Dossier inputs and gate results

```mermaid
flowchart TD
    Y["cad-agent.yaml<br/>dossier: · gates:"]
    DS["dossier/<br/>sections, cards, lint"]
    EV["evidence.py<br/>content hashes"]
    G["gates/<br/>access · motion · walls"]
    GJ["exports/gates/<br/>gate verdicts"]
    Y --> DS
    EV --> DS
    DS --> G
    G -->|"verdicts"| GJ
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class DS,EV,G here
    class Y near
    class GJ out
```

Packets and rendered review evidence

```mermaid
flowchart TD
    DS["dossier/<br/>sections, cards, lint"]
    G["gates/<br/>access · motion · walls"]
    PK["packet.py<br/>section packet"]
    RN["publish/render.py<br/>captioned PNGs"]
    PO["exports/review/<br/>manifest.json"]
    DS & G --> PK
    PK -->|"views"| RN
    PK --> PO
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class DS,G,PK here
    class RN near
    class PO out
```

Workbench pages

```mermaid
flowchart TD
    W["cadagent.review<br/>the workbench"]
    ST["publish/site.py<br/>review pages"]
    W --> ST
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class W here
    class ST near
```

Reference lookup

```mermaid
flowchart TD
    RY["docs/research/references.yaml<br/>sources by id"]
    RF["references.py<br/>lookup · check"]
    RY --> RF
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class RF here
    class RY near
```

| Module | What it does |
|---|---|
| `__init__.py` | The in-page review workbench for PCBs, housings and assemblies (`review_html`) |
| [`dossier/`](dossier/__init__.py) | The design dossier: requirements, sections, spec cards, interfaces, decisions, and its lint (`cad-agent dossier`) |
| [`gates/`](gates/__init__.py) | Assembly integrity gates (access order, connectivity, containment, fasteners, motion, walls), each written as a verdict (`cad-agent gates`) |
| `packet.py` | The section review packet: captioned renders with the measurements first (`cad-agent review-packet`) |
| `references.py` | The reference registry (`docs/research/references.yaml`, #118): look up a cited source by id or alias (`lookup`, `citation`), and `check()` that every id the code cites resolves, every entry is well formed and no source is copied (`python -m cadagent.review.references --check`) |
| `evidence.py` | Shared integrity screen for source-bound CAD and PCB records: content hashes and whether a record is current, the platform a hash was made on (`hash_platform`, `record_hash_platform`), and a platform-stable `geometry_identity` |

Related: [package map](../README.md) · [publish](../publish/README.md) (the review pages) ·
[design process](../../../docs/practice/design-process-plan.md) · [gates](../../../docs/practice/gates.md) ·
[dossier](../../../docs/practice/dossier.md) · [review packet](../../../docs/practice/review-packet.md)

## File and child ownership

| File or folder | Purpose |
|---|---|
| [dossier/](dossier/README.md) | Dossier declarations, lint and independent sign-off. |
| [gates/](gates/README.md) | Assembly integrity checks and verdict records. |
