# tests/formulas

Tests for [`src/cadagent/formulas/`](../../src/cadagent/formulas/README.md): each closed form against a published
worked example or a derivation written out in the test.

Arrows: what a test imports, runs or reads.

```mermaid
flowchart TD
    F["test_formulas.py<br/>test_inserts_formulas.py"] -->|"golden vectors"| X["formulas/<br/>closed forms"]
    T["test_torsion_snap_boss.py"] --> X
    X -->|"same vectors"| V["fixtures/formula-vectors.json<br/>read by webkit/"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class F,T here
    class X near
    class V out
```

| File | What it tests |
|---|---|
| `__init__.py` | Empty: makes the folder a package, so a test here may share a file name with one in another folder |
| `test_bearings.py` | Rolling bearings: ISO 281 life and ISO 76 static safety against the makers' worked examples |
| `test_formulas.py` | `cadagent.formulas` against worked examples from the cited sources, or derivations written out here |
| `test_inserts_formulas.py` | Threaded inserts and compression limiters: golden vectors and an independent derivation |
| `test_torsion_snap_boss.py` | The torsion-bar snap and the screw in a printed boss, against Saint-Venant and thread statics |

Run: `pytest tests/formulas` (with `PYTHONPATH=src`).

Related: [tests](../README.md) · [where files go](../../CONTRIBUTING.md#where-files-go)
