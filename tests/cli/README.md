# tests/cli

Tests for `cli.py` and the modules beside it at the top of [`src/cadagent/`](../../src/cadagent/README.md): the
project file, links, the review zip, the agent kit, lazy dependencies and the version.

Arrows: what a test imports, runs or reads.

```mermaid
flowchart TD
    C["test_cli.py<br/>test_project.py"] -->|"runs"| CLI["cadagent/cli.py<br/>project.py"]
    K["test_agentkit.py<br/>test_links.py · test_deps.py"] -->|"imports"| T["agentkit.py · links.py<br/>_deps.py"]
    CLI --> O["throwaway projects<br/>in tmp_path"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef near fill:#eef1e4,stroke:#6f8a80,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class C,K here
    class CLI,T near
    class O out
```

| File | What it tests |
|---|---|
| `__init__.py` | Empty: makes the folder a package, so a test here may share a file name with one in another folder |
| `test_agentkit.py` | `cad-agent agents install`: which skills and subagents land where, for Claude Code and Codex |
| `test_cli.py` | `cad-agent ...` end to end through `cadagent.cli.main`, on throwaway projects |
| `test_deps.py` | A missing heavy dependency raises `MissingDependency` naming the module, never a quiet skip |
| `test_links.py` | `cadagent.links`: local link checks for HTML and Markdown pages |
| `test_project.py` | `cadagent.project`: the `cad:` section of `cad-agent.yaml`, beside other tools' sections |
| `test_version.py` | `cadagent.__version__` from a checkout, an editable install or a wheel |

Run: `pytest tests/cli` (with `PYTHONPATH=src`).

Related: [tests](../README.md) · [where files go](../../CONTRIBUTING.md#where-files-go)
