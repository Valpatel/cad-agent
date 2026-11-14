# tests/simulation

Tests for [`software/cadagent/simulation/`](../../software/cadagent/simulation/README.md): FEA, CFD, topology optimisation,
robot export, design exploration and their pictures and reports. `cfd_fixtures.py` is a helper the CFD tests import;
design exploration has its own folder, [`explore/`](explore/README.md).

Arrows: what a test imports, runs or reads.

Finite elements and topology

```mermaid
flowchart TD
    F["test_fea*.py · test_topopt.py"]
    FE["simulation/fea.py<br/>topopt.py"]
    F -->|"imports"| FE
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class F here
    class FE near
```

Flow solver and its fixtures

```mermaid
flowchart TD
    C["test_cfd*.py"]
    H["cfd_fixtures.py<br/>fixtures/cfd_runs/"]
    CF["simulation/cfd.py"]
    C --> H
    C -->|"imports"| CF
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class C,H here
    class CF near
```

Exploration checks

```mermaid
flowchart TD
    E["explore/<br/>its own folder"]
    X["simulation/explore/"]
    E -->|"imports"| X
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class E here
    class X near
```

| File | What it tests |
|---|---|
| `__init__.py` | Empty: makes the folder a package, so a test here may share a file name with one in another folder |
| `cfd_fixtures.py` | Helper: recorded-format CFD runs from `fixtures/cfd_runs/` (no solver runs) |
| [`explore/`](explore/README.md) | Design exploration (`cadagent.simulation.explore`): catalogue, design files, evaluation, compare, optimise |
| `test_cfd.py` | `cadagent.simulation.cfd` writes a complete OpenFOAM case (running it is opt-in) |
| `test_cfd_fan_faces.py` | Fan inlet and outlet temperatures, mass-flow weighted; energy balance flagged |
| `test_cfd_history.py` | `read_results` keeps the whole run: residual and temperature histories |
| `test_fea.py` | The FEA solver against textbook answers: a cantilever and a twisted shaft |
| `test_fea_layers.py` | The layer check and material record of `cadagent.simulation.fea` |
| `test_fea_materials.py` | The FEA material table pinned to the data sheets it cites |
| `test_fea_mesh.py` | Mesh control: local refinement, the mesher's identity, slivers and refusals |
| `test_fit_mesh.py` | `fit_mesh`: an STL over its face budget comes back under it |
| [test_robot_recording.py](test_robot_recording.py) | Source-bound real solver recording, articulated transforms, physical input sensitivity and producer limits |
| `test_robot.py` | Robot export and explicit assembly-stage physics: mass/inertia, URDF/MJCF, support/freefall/tipping, timestep and false-stability controls |
| `test_simreport.py` | The simulation report page: comparison words, media and limits |
| `test_simviz.py` | House framing for simulation pictures |
| `test_simviz_convergence.py` | `convergence_chart`: the whole run and the values a convergence claim rests on |
| `test_stl_faces.py` | `stl_faces` with no optional dependencies: binary and ASCII STLs, truncated files |
| `test_topopt.py` | Topology optimisation (pyMOTO) on a small cantilever |

Run: `pytest tests/simulation` (with `PYTHONPATH=software`).

Related: [tests](../README.md) · [where files go](../../.github/CONTRIBUTING.md#where-files-go)
