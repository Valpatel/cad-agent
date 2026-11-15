# tests/repo/ci

Tests of the CI support tools in [`tools/ci/`](../../../tools/ci/README.md): the hosted-runner apt-mirror correction,
and the local preflight with the guard that keeps its mapping in step with the workflows.

Arrows: what a test imports or reads.

Runner provisioning

```mermaid
flowchart TD
    A["test_apt_mirror.py"]
    M["tools/ci/<br/>apt_mirror.py"]
    A -->|"imports"| M
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class A here
    class M near
```

Local preflight and its drift guard

```mermaid
flowchart TD
    C["test_ci_checks.py"]
    P["tools/ci/<br/>preflight.py"]
    W[".github/<br/>workflows/ · ci-checks.json"]
    C -->|"imports"| P
    C -->|"reads"| W
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    class C here
    class P,W near
```

| File | What it tests |
|---|---|
| `__init__.py` | Empty: a package, so these files may share names with tests elsewhere |
| `test_apt_mirror.py` | Hosted runner profile and mirror priorities; isolated loopback apt failover preserves signature rejection |
| `test_ci_checks.py` | `.github/ci-checks.json` mirrors every check a pull-request workflow runs, in its working directory (and nothing stale), naming the step that lacks an entry; every other command of a step is known setup or inert; every repo file a suite names selects that suite. `tools/ci/preflight.py` matches paths, reports what cannot run here as not run, and never reports passed for a check that did not run: exit 0 passed or nothing selected, 1 failed, 2 setup error, 3 incomplete, 130 interrupted |

Run: `pytest tests/repo/ci` (with `PYTHONPATH=software`).

Related: [tests/repo](../README.md) · [tools/ci](../../../tools/ci/README.md)
