# Evaluation controllers

`standard_eval.py` prepares and grades the versioned analytical starter corpus. It does not run subject code while grading. See [design and testing](../../docs/practice/standard-evaluation.md).

```mermaid
flowchart LR
    J[tests/fixtures/evaluation/jobs] --> P[prepare]
    P --> W[fresh project directory]
    W --> G[grade / ingest-run]
    J --> G
```
